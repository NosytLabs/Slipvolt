"""Browser checks for the operator console using intercepted HTTP fixtures.
No real provider, wallet, money, or admin secret is used.
"""
import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/'public/admin/index.html').read_text();CSS=(ROOT/'public/admin/styles.css').read_text();JS=(ROOT/'public/admin/app.js').read_text()
CONJS=(ROOT/'public/admin/connections.js').read_text()
READJS=(ROOT/'public/admin/readiness.js').read_text()
ADMIN='fixture-admin-key'
config={'wallet_rpm':30,'wallet_concurrency':4,'global_rpm':300,'global_concurrency':50,'holder_daily_tokens':250000,'global_daily_tokens':1000000,'default_output_tokens':4096,'max_output_tokens':16384,'retail_input_nusd_per_token':75,'retail_output_nusd_per_token':300,'retail_input_per_million_usd':0.075,'retail_output_per_million_usd':0.3,'ngonka_per_token_budget':25,'maintenance_mode':False,'disabled_models':[],'gnk_usd':'0.164'}
overview={'window_days':30,'fund_capacity':{'budget_ngonka_per_token':25,'local_available_ai_tokens':3580000000,'wallet_days_at_full_allowance':14320,'broker_available_ai_tokens':3600000000},'provider_balance':{'available_ngonka':90000000000},'provider_usage':{'totals':{'cost_ngonka':3000000000}},'local':{'tokens':2500000,'users':18},'pool':{'allocated_ngonka':100000000000,'budget_spent_ngonka':10000000000,'reserved_ngonka':500000000,'available_budget_ngonka':89500000000},'provider_status':{'status':'ok','models':[{'model':'MiniMaxAI/MiniMax-M2.7','status':'healthy','routable':True,'capacity_available_pct':90,'load_pct':10,'in_flight_requests':4},{'model':'deepseek-ai/DeepSeek-V4-Flash-0731','status':'healthy','routable':True,'capacity_available_pct':60,'load_pct':40,'in_flight_requests':20}]},'provider_errors':[],'business':{'revenue_usd':3000,'expense_usd':900,'cash_net_usd':2100,'recent':[{'category':'creator_fee','amount_usd':3000,'reference':'claim-1','created':1789780000}]},'economics':{'metered_revenue_reference_usd':450},'runway_days_at_recent_provider_spend':900,'config':config}
users={'data':[{'wallet':'11111111111111111111111111111111','active_keys':1,'requests':10,'tokens':10000,'cost_ngonka':150000,'disabled':False}]}
audit={'data':[{'id':1,'action':'config_updated','target':'runtime','note':'fixture','created':1789780000}]}
keys={'data':[{'id':'k1','prefix':'sv_fixture','name':'default','created':1789780000,'revoked':False}]}
requests={'data':[{'id':'r1','wallet':'11111111111111111111111111111111','model':'MiniMaxAI/MiniMax-M2.7','tokens':100,'reserved_tokens':0,'cost_ngonka':1500,'reserved_ngonka':0,'state':'settled','created':1789780000}]}

def run():
    passed=0
    with sync_playwright() as p:
        b=p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or ('/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else p.chromium.executable_path),headless=True,args=['--no-sandbox'])
        for width in (320,390,768,1280,1600):
            page=b.new_page(viewport={'width':width,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            def route(r):
                nonlocal passed
                u=r.request.url;path=u.split('admin.test',1)[-1]
                if path=='/admin/' or path=='/admin':return r.fulfill(status=200,body=HTML,content_type='text/html')
                if path=='/admin/styles.css':return r.fulfill(status=200,body=CSS,content_type='text/css')
                if path=='/admin/app.js':return r.fulfill(status=200,body=JS,content_type='text/javascript')
                if path=='/admin/readiness.js':return r.fulfill(status=200,body=READJS,content_type='text/javascript')
                if path=='/admin/connections.js':return r.fulfill(status=200,body=CONJS,content_type='text/javascript')
                if path.startswith('/api/admin/'):
                    if r.request.headers.get('authorization')!='Bearer '+ADMIN:return r.fulfill(status=401,json={'error':{'message':'Invalid admin credential'}})
                    if path=='/api/admin/readiness':return r.fulfill(status=200,json={'status':'review_required','checked_at':1789878000,'checks':[{'id':'pool_sizing','title':'Shared daily capacity','status':'review','detail':'Pool covers four complete allowances.'}], 'capacity':{'full_allowances_per_day':4},'accounting_notice':'Epoch adjustments are excluded from usage summaries.'})
                    if path=='/api/admin/connections':return r.fulfill(status=200,json={'solana_rpc':{'configured':True,'rps_budget':15},'solana_websocket':{'configured':True},'openbroker':{'configured':True},'metis':{'configured':True},'token':{'mint':None}})
                    if path=='/api/admin/connections/check':return r.fulfill(status=200,json={'status':'ready','mainnet_verified':True,'slot':12345})
                    if path=='/api/admin/connections/priority-fee':return r.fulfill(status=200,json={'estimates':{'per_compute_unit':{'recommended':12,'unit':'micro_lamports_per_compute_unit'}},'transactions_sent':0})
                    if path=='/api/admin/swap/quote':return r.fulfill(status=200,json={'asset':'SOL','input_amount':'0.1','expected_usdc':'12.50','minimum_usdc':'12.4375','local_expires_at':__import__('time').time()+15,'notice':'Read-only quote. No transaction was sent.'})
                    if path.startswith('/api/admin/config'):
                        return r.fulfill(status=200,json=config)
                    if path.startswith('/api/admin/overview'):return r.fulfill(status=200,json=overview)
                    if path.startswith('/api/admin/audit'):return r.fulfill(status=200,json=audit)
                    if '/keys/' in path and r.request.method=='DELETE':return r.fulfill(status=200,json={'revoked':True})
                    if path.endswith('/keys'):return r.fulfill(status=200,json=keys)
                    if path.startswith('/api/admin/users'):return r.fulfill(status=200,json=users if r.request.method=='GET' else users['data'][0])
                    if path.startswith('/api/admin/requests'):return r.fulfill(status=200,json=requests)
                    if path.startswith('/api/admin/allowance/fund'):return r.fulfill(status=200,json={'allocated':True,'crypto_transferred':False})
                    if path.startswith('/api/admin/business'):return r.fulfill(status=201,json={'recorded':True})
                return r.fulfill(status=404,body='not found')
            page.route('http://admin.test/**',route)
            markup=HTML.replace('<head>','<head><base href="http://admin.test/admin/">',1).replace('<link rel="stylesheet" href="/admin/styles.css">','<style>'+CSS+'</style>').replace('<script src="/admin/app.js" defer></script>','').replace('<script src="/admin/connections.js" defer></script>','').replace('<script src="/admin/readiness.js" defer></script>','').replace('</body>','<script>'+READJS+'</script><script>'+JS+'</script><script>'+CONJS+'</script></body>')
            page.set_content(markup,wait_until='load')
            assert page.locator('#login').is_visible();passed+=1
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth');passed+=1
            page.locator('#admin-key').fill(ADMIN);page.locator('#unlock').click();page.locator('#console').wait_for(state='visible')
            assert page.get_by_text('90 GNK',exact=False).count()>=1;passed+=1
            assert page.get_by_text('MiniMaxAI/MiniMax-M2.7',exact=True).count()==1;passed+=1
            assert page.locator('#price-input').input_value()=='0.075';passed+=1
            assert page.locator('[data-k=ngonka_per_token_budget]').input_value()=='25';passed+=1
            assert page.get_by_text('3.58B',exact=False).count()>=1;passed+=1
            assert page.get_by_text('config_updated',exact=True).count()==1;passed+=1
            page.locator('#connection-list .connection-row').first.wait_for()
            assert page.locator('#connection-list').get_by_text('Solana RPC',exact=True).count()==1;passed+=1
            page.locator('#connections-check').click()
            page.wait_for_function("document.querySelector('#connections-result').textContent.includes('mainnet_verified')")
            assert 'true' in page.locator('#connections-result').inner_text();passed+=1
            page.locator('#priority-check').click()
            page.wait_for_function("document.querySelector('#connections-result').textContent.includes('micro_lamports_per_compute_unit')")
            assert 'transactions_sent' in page.locator('#connections-result').inner_text();passed+=1
            page.locator('#quote-form').evaluate("e=>e.closest('details').open=true");page.locator('#quote-amount').fill('0.1');page.locator('#quote-form button').click()
            page.wait_for_function("document.querySelector('#quote-result').textContent.includes('12.4375')")
            assert 'No transaction' in page.locator('#quote-result').inner_text();passed+=1
            page.locator('#quote-amount').fill('0.2')
            assert 'Inputs changed' in page.locator('#quote-result').inner_text();passed+=1
            page.wait_for_function("document.querySelector('#readiness-list').textContent.includes('Shared daily capacity')")
            assert 'Review required' in page.locator('#readiness-state').inner_text();passed+=1
            page.locator('#readiness-list').evaluate("e=>e.closest('details').open=true")
            assert 'four complete allowances' in page.locator('#readiness-list').inner_text();passed+=1
            assert 'Epoch adjustments' in page.locator('#readiness-accounting').inner_text();passed+=1
            assert page.locator('#admin-key').input_value()=='';passed+=1
            if os.getenv('CAPTURE_CONTROLS') and width in (390,1280):
                page.evaluate('window.scrollTo(0,0)')
                page.screenshot(path=f'/mnt/data/slipvolt-controls-admin-{width}.png',full_page=False)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth');passed+=1
            page.evaluate('(d)=>render(d)', {**overview,'provider_usage':None})
            assert 'Unavailable' in page.locator('#metrics .metric').filter(has_text='provider cost').inner_text();passed+=1
            assert not errors, errors;passed+=1
            page.close()
        b.close()
    print(f'PASS admin browser checks: {passed}')
if __name__=='__main__':run()
