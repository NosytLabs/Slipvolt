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
            check(f'offline {width}px: no invented balances',page.locator('#broker-available').inner_text()=='Not published')
            page.locator('.model-tab').nth(1).click();page.locator('#tab-api').click()
            page.locator('#output-tokens').evaluate("e=>{e.value='8192';e.dispatchEvent(new Event('change'))}")
            page.locator('#example-language').select_option('python')
            check(f'offline {width}px: Python reflects output and avoids retry', 'max_tokens=8192' in page.locator('#api-code').inner_text() and 'max_retries=0' in page.locator('#api-code').inner_text())
            page.locator('#example-language').select_option('javascript')
            check(f'offline {width}px: JavaScript uses env key', 'process.env.SLIPVOLT_API_KEY' in page.locator('#api-code').inner_text())
            check(f'offline {width}px: exact selected model in code','deepseek-ai/DeepSeek-V4-Flash-0731' in page.locator('#api-code').inner_text())
            page.locator('#tab-api').focus();page.keyboard.press('ArrowLeft')
            check(f'offline {width}px: keyboard tab navigation',page.locator('#chat-panel').is_visible())
            page.locator('#existing-key').evaluate("e=>e.closest('details').open=true")
            page.locator('#existing-key').fill('obk-never-send-master-key');page.locator('#prompt').fill('Hello')
            page.locator('#send').click()
            check(f'offline {width}px: blocks upstream key','Never paste' in page.locator('#toast').inner_text())
            check(f'offline {width}px: zero requests',not requests)
            page.locator('#check-request').click()
            check(f'offline {width}px: preflight stays offline','Offline preview' in page.locator('#preflight-result').inner_text())
            page.locator('#tab-api').click();page.locator('#connection-details').evaluate('e=>e.open=true')
            check(f'offline {width}px: connection kit excludes credentials','SLIPVOLT_API_KEY' in page.locator('#connection-kit').inner_text() and 'obk-' not in page.locator('#connection-kit').inner_text())
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
        context=browser.new_context(viewport={'width':1280,'height':1000});http=httpx.Client(base_url=origin,headers={'Origin':origin})
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
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
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
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.set_content(markup.replace('data-preview="offline"','data-preview="http-fixture"'),wait_until='load')
        page.set_default_timeout(7000)
        expect(page.locator('#model-source')).to_contain_text('Live OpenBroker')
        check('served catalog obtains provider fixture',page.locator('.model-tab').count()==1)
        check('GNK stats separate from project usage','not Slipvolt' in page.locator('#network-window').inner_text())
        page.locator('#main-connect').click()
        page.locator('#wallet-options button').first.click()
        expect(page.locator('#member-actions')).to_be_visible()
        check('wallet sign-in needs no email',page.locator('#create-key').is_enabled())
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
        page.on('dialog',lambda dialog:dialog.accept())
        page.locator('#revoke-all-keys').evaluate("e=>e.closest('details').open=true")
        page.locator('#revoke-all-keys').click()
        expect(page.locator('#toast')).to_contain_text('keys revoked')
        check('revocation clears tab secret',page.locator('#created-key').input_value()=='')
        check('revocation preserves consumed allowance',app.state.membership.totals(WALLET)['used_tokens']==15)
        page.evaluate('window.setTestWalletSilently()')
        page.evaluate('refreshMember()')
        expect(page.locator('#member-actions')).to_be_hidden()
        check('restored session mismatch clears ephemeral key',page.locator('#created-key').input_value()=='')
        check('restored session mismatch clears prompt',page.locator('#prompt').input_value()=='')
        check('no JavaScript exceptions during integration',not errors)
        context.close();http.close();server.should_exit=True;thread.join(5)
        browser.close()
        output={'checks':len(results),'passed':sum(r['passed'] for r in results),'browser_transport':mode,
            'navigation_error_type':navigation_error,'wallet':'generated Ed25519 fixture, not a real extension',
            'provider':'httpx fixture, no paid inference','results':results}
        (OUT/'holder-browser.json').write_text(json.dumps(output,indent=2))
        print(json.dumps({k:v for k,v in output.items() if k!='results'},indent=2))

if __name__=='__main__':run()
