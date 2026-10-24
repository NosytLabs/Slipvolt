"""New holder UI browser suite. Simulated wallet/RPC/provider; no money or live inference.

Tries native localhost navigation first. If the browser runner blocks navigation,
uses a local HTTP adapter, recording that native browser transport was NOT tested.
"""
import json, os, socket, sys, tempfile, threading, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'scripts')]
import httpx, uvicorn
from playwright.sync_api import sync_playwright, expect
from gridraft.app import create_app
from test_gridraft import KEY, WALLET
from test_membership import member_settings, handler
from test_member_edges import sse
from package_preview import build

OUT=ROOT/'evidence-current';OUT.mkdir(exist_ok=True)
results=[]
def check(name,value):
    results.append({'name':name,'passed':bool(value)})
    print(('PASS ' if value else 'FAIL ')+name,flush=True)
    if not value:raise AssertionError(name)


def run():
    with tempfile.TemporaryDirectory() as temp, sync_playwright() as p:
        tmp=Path(temp);preview=tmp/'preview.html';build(preview);markup=preview.read_text()
        browser=p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or ('/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else p.chromium.executable_path),headless=True,args=['--no-sandbox'])
        for width in [320,360,390,768,900,1280,1440,1920]:
            page=browser.new_page(viewport={'width':width,'height':980});errors=[];requests=[]
            page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
            page.set_content(markup,wait_until='load')
            check(f'offline {width}px: no overflow',page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            check(f'offline {width}px: three models',page.locator('.model-tab').count()==3)
            check(f'offline {width}px: service detail stays on status page',page.locator('#service-status-link').get_attribute('href') in ('status/','/status/'))
            page.locator('.model-tab').nth(1).click();page.locator('#tab-api').click()
            page.locator('#output-tokens').evaluate("e=>{e.value='8192';e.dispatchEvent(new Event('change'))}")
            page.locator('#example-language').select_option('python')
            check(f'offline {width}px: Python reflects output and avoids retry', 'max_tokens=8192' in page.locator('#api-code').inner_text() and 'max_retries=0' in page.locator('#api-code').inner_text())
            page.locator('#example-language').select_option('javascript')
            check(f'offline {width}px: JavaScript uses env key', 'process.env.SLIPVOLT_API_KEY' in page.locator('#api-code').inner_text())
            check(f'offline {width}px: exact selected model in code','deepseek-ai/DeepSeek-V4-Flash-0731' in page.locator('#api-code').inner_text())
            page.locator('#tab-api').focus();page.keyboard.press('ArrowLeft')
            check(f'offline {width}px: keyboard tab navigation',page.locator('#chat-panel').is_visible())
            check(f'offline {width}px: inactive tab leaves keyboard order',page.locator('#tab-chat').get_attribute('tabindex')=='0' and page.locator('#tab-api').get_attribute('tabindex')=='-1')
            check(f'offline {width}px: usable models stay in keyboard order',page.locator('.model-tab:not(:disabled)').evaluate_all("els=>els.every(e=>e.tabIndex===0)"))
            page.locator('#existing-key').evaluate("e=>e.closest('details').open=true")
            page.locator('#existing-key').fill('obk-never-send-master-key');page.locator('#prompt').fill('Hello')
            page.locator('#send').click()
            check(f'offline {width}px: blocks upstream key','Never paste' in page.locator('#toast').inner_text())
            check(f'offline {width}px: zero requests',not requests)
            page.locator('#check-request').click()
            check(f'offline {width}px: preflight stays offline','Offline preview' in page.locator('#preflight-result').inner_text())
            page.locator('#tab-api').click();page.locator('#connection-details').evaluate('e=>e.open=true')
            check(f'offline {width}px: connection kit excludes credentials','SLIPVOLT_API_KEY' in page.locator('#connection-kit').inner_text() and 'obk-' not in page.locator('#connection-kit').inner_text())
            if width==390:
                page.evaluate("""() => { S.catalogLive=true; S.models=[{id:'down',name:'Unavailable model',availability:'unavailable'}]; renderModels(); }""")
                check('offline unavailable catalog: no callable fallback',page.evaluate("S.selected === ''") and page.locator('.model-tab').is_disabled())
                check('offline unavailable catalog: actions disabled',page.locator('#send').is_disabled() and page.locator('#check-request').is_disabled())
                check('offline unavailable catalog: stale API example cleared','down' not in page.locator('#api-code').inner_text())
            check(f'offline {width}px: zero page errors',not errors)
            if width in (390,1280):
                shot=browser.new_page(viewport={'width':width,'height':980})
                shot_errors=[];shot.on('pageerror',lambda e:shot_errors.append(str(e)))
                shot.set_content(markup,wait_until='load')
                check(f'screenshot {width}px: model picker rendered',shot.locator('.model-tab').count()==3)
                check(f'screenshot {width}px: no script errors',not shot_errors)
                shot.screenshot(path=str(OUT/f'app-{width}.png'),full_page=True)
                shot.close()
            page.close()
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        origin=f'http://127.0.0.1:{port}';holding={'enabled':True};dispatched=[]
        def upstream(req):
            if req.url.host=='example.invalid' and not holding['enabled']:
                return httpx.Response(200,json={'result':{'context':{'slot':500},'value':[]}})
            if req.url.path.endswith('/chat/completions'):
                dispatched.append(json.loads(req.content))
                return httpx.Response(200,text=sse(),headers={'content-type':'text/event-stream'})
            return handler(req)
        settings=member_settings();settings.origin=origin
        app=create_app(settings,str(tmp/'test.db'),httpx.MockTransport(upstream))
        app.state.membership.allocate(10000000,'fixture-allocation')
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,log_level='error'))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        # This client talks only to the local fixture server. Environment proxy
        # settings must not route fixture requests through an external proxy.
        context=browser.new_context(viewport={'width':1280,'height':1000});http=httpx.Client(base_url=origin,headers={'Origin':origin},trust_env=False)
        context.expose_function('signFixture',lambda values:list(KEY.sign(bytes(values))))
        init="""(() => {
          const listeners={};let address=WALLET;
          const p={isPhantom:true,get publicKey(){return {toString:()=>address}},
            connect:async()=>({publicKey:p.publicKey}),
            signMessage:async b=>({signature:new Uint8Array(await window.signFixture(Array.from(b)))}),
            on:(name,cb)=>{(listeners[name]||=[]).push(cb)},
            removeListener:(name,cb)=>{listeners[name]=(listeners[name]||[]).filter(f=>f!==cb)}};
          window.phantom={solana:p};window.setTestWalletSilently=()=>{address='11111111111111111111111111111111'};window.changeTestWallet=()=>{address='11111111111111111111111111111111';for(const cb of listeners.accountChanged||[])cb(p.publicKey)};
          if(!crypto.randomUUID)crypto.randomUUID=()=> '10000000-1000-4000-8000-100000000000'.replace(/[018]/g,c=>(c^crypto.getRandomValues(new Uint8Array(1))[0]&15>>c/4).toString(16));
        })();""".replace('WALLET',json.dumps(WALLET))
        context.add_init_script(init)
        page=context.new_page();errors=[];live_requests=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:live_requests.append(r.url))
        mode='native_localhost';navigation_error=None
        try:
            page.goto(origin,wait_until='networkidle',timeout=12000)
            if not page.title().startswith('Slipvolt'):raise RuntimeError('Unexpected navigation response')
        except Exception as e:
            navigation_error=type(e).__name__;mode='HTTP adapter; native browser transport NOT verified'
            def forward(path,options):
                if not path.startswith('/') or path.startswith('//'):raise ValueError('Only local routes in test adapter')
                r=http.request(options.get('method','GET'),path,headers=options.get('headers',{}),content=options.get('body'))
                return {'status':r.status_code,'headers':dict(r.headers),'body':r.text}
            context.expose_function('forwardFixtureHTTP',forward)
            page.close()
            context.add_init_script("""window.fetch=async(path,options={})=>{const r=await window.forwardFixtureHTTP(path,options);return new Response(r.body,{status:r.status,headers:r.headers})};""")
            page=context.new_page();errors=[];live_requests=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:live_requests.append(r.url))
            page.set_content(markup.replace('data-preview="offline"','data-preview="http-fixture"'),wait_until='load')
        page.set_default_timeout(7000)
        check('anonymous first visit is not called an expired session','Session expired' not in page.locator('#access-message').inner_text())
        check('homepage skips status-only network and treasury requests',not any(url.endswith(('/api/network','/api/treasury')) for url in live_requests))
        expect(page.locator('#model-source')).to_contain_text('Live OpenBroker')
        check('served catalog obtains provider fixture',page.locator('.model-tab').count()==1)
        check('operational detail links to service status',page.locator('#service-status-link').get_attribute('href') in ('status/','/status/'))
        key_only=page.evaluate("""async () => {
          const realApi=api,realFetch=fetch;let rejectAccount,resolveChat;
          api=async (path,options={})=>path==='/api/account'?await new Promise((resolve,reject)=>{rejectAccount=reject}):realApi(path,options);
          fetch=(path,options={})=>String(path).endsWith('/v1/chat/completions')?new Promise(resolve=>{resolveChat=resolve}):realFetch(path,options);
          const wait=()=>new Promise(resolve=>setTimeout(resolve,0));
          try{
            const probe=refreshMember();while(!rejectAccount)await wait();
            $('existing-key').value='sv_'+ 'k'.repeat(40);$('prompt').value='key-only request';$('send').click();while(!resolveChat)await wait();
            const unauthorized=new Error('Not signed in');unauthorized.status=401;rejectAccount(unauthorized);await probe;
            const survivedProbe=S.busy&&$('existing-key').value.startsWith('sv_');
            resolveChat(new Response(JSON.stringify({choices:[{message:{content:'key-only response'}}]}),{status:200,headers:{'content-type':'application/json'}}));
            let tries=0;while(S.busy&&tries++<100)await wait();
            return {survivedProbe,finished:!S.busy,result:$('result').textContent,key:$('existing-key').value};
          }finally{api=realApi;fetch=realFetch;clearSecrets();}
        }""")
        check('anonymous account probe preserves existing-key response',key_only['survivedProbe'] and key_only['finished'] and key_only['result']=='key-only response' and key_only['key'].startswith('sv_'))
        stale_signin=page.evaluate("""async () => {
          const realApi=api,provider=window.phantom.solana,logoutResolvers=[];let resolveVerify;
          api=async (path,options={})=>{
            if(path==='/api/auth/challenge')return {id:'fixture-stale',message:'stale sign-in fixture'};
            if(path==='/api/auth/verify')return await new Promise(resolve=>{resolveVerify=resolve});
            if(path==='/api/auth/logout')return await new Promise(resolve=>logoutResolvers.push(resolve));
            return realApi(path,options);
          };
          const wait=()=>new Promise(resolve=>setTimeout(resolve,0)),button={disabled:false};
          try{
            const pendingConnect=connect(provider,button);while(!resolveVerify)await wait();
            const pendingInvalidate=invalidate('fixture invalidation');while(logoutResolvers.length<1)await wait();
            resolveVerify({ok:true});while(logoutResolvers.length<2)await wait();
            logoutResolvers[1]({ok:true});await pendingConnect;
            const busyUntilInvalidationFinishes=S.authBusy;showWallets();const reconnectBlocked=!$('wallet-dialog').open;
            logoutResolvers[0]({ok:true});await pendingInvalidate;
            return {wallet:S.wallet,logoutCalls:logoutResolvers.length,busyUntilInvalidationFinishes,reconnectBlocked,released:!S.authBusy};
          }finally{api=realApi;clearAccount();}
        }""")
        check('stale verify and invalidation retain auth ownership until both finish',stale_signin['wallet'] is None and stale_signin['logoutCalls']==2 and stale_signin['busyUntilInvalidationFinishes'] and stale_signin['reconnectBlocked'] and stale_signin['released'])
        page.locator('#main-connect').click()
        page.locator('#wallet-options button').first.click()
        expect(page.locator('#member-actions')).to_be_visible()
        expect(page.locator('#create-key')).to_be_enabled()
        check('wallet sign-in needs no email',page.locator('#create-key').is_enabled())
        refresh_race=page.evaluate("""async () => {
          const realApi=api,wallet=S.wallet,waiting=[];
          const membership=daily=>({eligibility:{eligible:true},funded_allowance_mode:true,used_tokens:2,reserved_tokens:0,
            remaining_tokens:daily-2,daily_tokens:daily,resets_at:2000000000,pool:{available_budget_ngonka:1},history:[]});
          api=async (path,options={})=>{
            if(path==='/api/account')return {wallet};
            if(path==='/api/membership')return await new Promise(resolve=>waiting.push({resolve,signal:options.signal}));
            if(path==='/api/usage/summary')return {total_tokens:0,requests:0,cost_ngonka:0,prompt_tokens:null,completion_tokens:null,cached_input_tokens:null,reasoning_tokens:null,usage_reported_requests:0,usage_unreported_requests:0};
            if(path==='/api/keys')return {data:[]};
            return realApi(path);
          };
          const waitFor=n=>new Promise((resolve,reject)=>{let tries=0;const poll=()=>waiting.length>=n?resolve():tries++>100?reject(new Error('refresh fixture timed out')):setTimeout(poll,0);poll();});
          try{
            const older=refreshMember();await waitFor(1);
            const newer=refreshMember();await waitFor(2);
            const olderAborted=waiting[0].signal?.aborted===true;
            waiting[1].resolve(membership(222));await newer;const afterNew=$('allowance-label').textContent;
            waiting[0].resolve(membership(111));await older;const afterOld=$('allowance-label').textContent;
            return {afterNew,afterOld,olderAborted};
          }finally{api=realApi;await refreshMember();}
        }""")
        check('newest account refresh owns and cancels private state',refresh_race['olderAborted'] and refresh_race['afterNew'].startswith('222 ') and refresh_race['afterOld']==refresh_race['afterNew'])
        wallet_boundary=page.evaluate("""async () => {
          const realApi=api,savedPhantom=window.phantom,savedSolana=window.solana;let logoutCalls=0;
          window.phantom=undefined;window.solana=undefined;
          api=async (path,options={})=>{
            if(path==='/api/account')return {wallet:'11111111111111111111111111111111'};
            if(path==='/api/auth/logout'){logoutCalls++;return {ok:true};}
            throw new Error('Private endpoints must not load across a wallet boundary.');
          };
          try{await refreshMember();return {wallet:S.wallet,memberHidden:$('member-actions').hidden,logoutCalls};}
          finally{api=realApi;window.phantom=savedPhantom;window.solana=savedSolana;}
        }""")
        check('account wallet change is an isolated session boundary',wallet_boundary['wallet'] is None and wallet_boundary['memberHidden'] and wallet_boundary['logoutCalls']==1)
        page.locator('#main-connect').click();page.locator('#wallet-options button').first.click();expect(page.locator('#create-key')).to_be_enabled()
        page.locator('#create-key').click();expect(page.locator('#new-key')).to_be_visible()
        secret=page.locator('#created-key').input_value()
        check('key created without dollar balance',secret.startswith('sv_') and app.state.store.account(WALLET)['balance_nusd']==0)
        page.locator('#output-tokens').fill('8192')
        page.locator('#prompt').fill('Hello test only')
        page.locator('#check-request').click()
        expect(page.locator('#preflight-result')).to_contain_text('Fits the current limits')
        check('preflight sends no model generation',len(dispatched)==0)
        check('preflight creates no usage reservation',app.state.membership.history(WALLET)==[])
        page.locator('#prompt').fill('Edited test prompt')
        check('editing invalidates preflight','Fits' not in page.locator('#preflight-result').inner_text())
        page.locator('#review-support').click()
        expect(page.locator('#support-dialog')).to_be_visible()
        text=page.locator('#support-report').inner_text()
        check('support report excludes private state',secret not in text and WALLET not in text and 'Edited test prompt' not in text)
        page.locator('#support-close').click()
        page.locator('#prompt').fill('Hello test only');page.locator('#send').click()
        expect(page.locator('#request-note')).to_contain_text('Complete.')
        check('streamed fixture reply rendered',page.locator('#result').inner_text()=='Hello stream')
        check('actual fixture usage settles allowance',app.state.membership.totals(WALLET)['used_tokens']==15)
        check('native GNK cost ledger used',app.state.membership.pool()['budget_spent_ngonka']==150)
        check('selected output forwarded',dispatched[0]['max_tokens']==8192)
        check('request trace exposed',bool(page.locator('#request-id').inner_text().strip()))
        expect(page.locator('#usage-dashboard')).to_be_visible()
        expect(page.locator('#usage-used')).to_have_text('15')
        check('private usage dashboard shows authoritative totals',page.locator('#usage-dashboard').is_visible() and page.locator('#usage-used').inner_text()=='15' and page.locator('#usage-total').inner_text()=='15' and page.locator('#usage-requests').inner_text()=='1')
        breakdown=page.locator('#usage-breakdown').inner_text()
        check('provider token breakdown is labelled from real usage',all(value in breakdown for value in ('12 input','3 output','8 cached input','2 reasoning')))
        check('recent activity renders the measured request',page.locator('#usage-history .history-row').count()==1 and 'MiniMax' in page.locator('#usage-history .history-row').inner_text())
        page.on('dialog',lambda dialog:dialog.accept())
        page.locator('#revoke-all-keys').evaluate("e=>e.closest('details').open=true")
        page.locator('#revoke-all-keys').click()
        expect(page.locator('#toast')).to_contain_text('keys revoked')
        check('revocation clears tab secret',page.locator('#created-key').input_value()=='')
        check('revocation preserves consumed allowance',app.state.membership.totals(WALLET)['used_tokens']==15)
        request_race=page.evaluate("""async () => {
          const realFetch=fetch,pending=[],wait=()=>new Promise(resolve=>setTimeout(resolve,0));
          fetch=(path,options={})=>String(path).endsWith('/v1/chat/completions')?new Promise(resolve=>pending.push({resolve,options})):realFetch(path,options);
          const reply=text=>new Response(JSON.stringify({choices:[{message:{content:text}}]}),{status:200,headers:{'content-type':'application/json'}});
          try{
            $('existing-key').value='sv_'+ 'x'.repeat(40);$('prompt').value='older request';$('send').click();while(pending.length<1)await wait();
            clearSecrets();
            $('existing-key').value='sv_'+ 'y'.repeat(40);$('prompt').value='newer request';$('send').click();while(pending.length<2)await wait();
            const newerController=S.controller;
            pending[0].resolve(reply('obsolete'));await wait();await wait();
            const newerStillOwns=S.busy&&S.controller===newerController&&$('send').disabled;
            pending[1].resolve(reply('current'));let tries=0;while(S.busy&&tries++<100)await wait();
            return {newerStillOwns,finished:!S.busy,result:$('result').textContent};
          }finally{fetch=realFetch;clearSecrets();}
        }""")
        check('obsolete request cannot release newer request controls',request_race['newerStillOwns'] and request_race['finished'] and request_race['result']=='current')
        page.locator('#logout-everywhere').evaluate("e=>e.closest('details').open=true")
        page.locator('#logout-everywhere').click();expect(page.locator('#member-actions')).to_be_hidden()
        check('logout-everywhere control resets for a later session',page.locator('#logout-everywhere').is_enabled())
        page.locator('#main-connect').click();page.locator('#wallet-options button').first.click();expect(page.locator('#member-actions')).to_be_visible()
        for _ in range(100):
            if not page.evaluate("S.authBusy"):break
            time.sleep(.01)
        check('reconnected session releases auth ownership',not page.evaluate("S.authBusy"))
        logout_lock=page.evaluate("""async () => {
          const realApi=api;let releaseLogout;
          api=async (path,options={})=>path==='/api/auth/logout'?await new Promise(resolve=>{releaseLogout=resolve}):realApi(path,options);
          const wait=()=>new Promise(resolve=>setTimeout(resolve,0));
          try{
            $('logout').click();while(!releaseLogout)await wait();
            showWallets();const blocked=S.authBusy&&!$('wallet-dialog').open;
            releaseLogout({ok:true});let tries=0;while(S.authBusy&&tries++<100)await wait();
            return {blocked,released:!S.authBusy};
          }finally{api=realApi;}
        }""")
        check('explicit logout blocks a newer sign-in until its cookie response finishes',logout_lock['blocked'] and logout_lock['released'])
        page.locator('#main-connect').click();page.locator('#wallet-options button').first.click();expect(page.locator('#member-actions')).to_be_visible()
        page.evaluate('window.setTestWalletSilently()')
        page.evaluate('refreshMember()')
        expect(page.locator('#member-actions')).to_be_hidden()
        check('restored session mismatch clears ephemeral key',page.locator('#created-key').input_value()=='')
        check('restored session mismatch clears prompt',page.locator('#prompt').input_value()=='')
        check('restored session mismatch clears private usage',page.locator('#usage-dashboard').is_hidden() and page.locator('#usage-history .history-row').count()==0)
        check('restored session mismatch clears key metadata',page.locator('#key-list').inner_text()=='' and page.locator('#created-key').input_value()=='')
        check('restored session mismatch clears quota values',page.locator('#quota-used').inner_text()=='\u2014' and page.locator('#quota-left').inner_text()=='\u2014')
        check('no JavaScript exceptions during integration',not errors)
        context.close();http.close();server.should_exit=True;thread.join(5)
        browser.close()
        output={'checks':len(results),'passed':sum(r['passed'] for r in results),'browser_transport':mode,
            'navigation_error_type':navigation_error,'wallet':'generated Ed25519 fixture, not a real extension',
            'provider':'httpx fixture, no paid inference','results':results}
        (OUT/'holder-browser.json').write_text(json.dumps(output,indent=2))
        print(json.dumps({k:v for k,v in output.items() if k!='results'},indent=2))

if __name__=='__main__':run()
