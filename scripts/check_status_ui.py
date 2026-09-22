"""Status rendering against local FastAPI responses; no paid requests or real wallet.

Uses set_content and a read-only TestClient bridge; does not claim native browser
navigation, TLS, cookie or CSP validation. Routes/headers are tested independently.
"""
import json
import os
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright,expect
from gridraft.app import create_app,Settings

OUT=ROOT/'evidence-current'

def run():
    OUT.mkdir(exist_ok=True);results=[]
    def check(name,ok):
        results.append({'name':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        app=create_app(Settings(access_mode='holder_allowance'),str(Path(tmp)/'a.db'),httpx.MockTransport(lambda _:httpx.Response(503)))
        with TestClient(app) as client:
            html=(ROOT/'public/status/index.html').read_text()
            for name in ('styles.css','tools.css'):
                html=html.replace(f'<link rel="stylesheet" href="../{name}">','<style>'+(ROOT/'public'/name).read_text()+'</style>')
            html=html.replace('<link rel="icon" href="../favicon.svg">','').replace('<script src="../chart.js" defer></script>','').replace('<script src="app.js" defer></script>','')
            html=html.replace('</body>','<script>'+(ROOT/'public/chart.js').read_text()+'</script><script>'+(ROOT/'public/status/app.js').read_text()+'</script></body>')
            browser=p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or ('/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else p.chromium.executable_path),headless=True,args=['--no-sandbox'])
            for width in (320,390,768,1280,1920):
                failing=[False];paths=[];errors=[]
                def read(path):
                    if path not in ('/api/status','/api/models','/api/network','/api/treasury'):raise ValueError('Unexpected route')
                    paths.append(path)
                    if failing[0]:return {'status':503,'body':'{}'}
                    if path=='/api/network':
                        data={'status':'available','scope':'OpenBroker network; not Slipvolt usage','stale':False,'totals':{'requests':24,'tokens':48000,'cost_ngonka':720000},'daily':[{'day':'2026-09-18','requests':6,'tokens':12000,'cost_ngonka':180000},{'day':'2026-09-19','requests':8,'tokens':16000,'cost_ngonka':240000},{'day':'2026-09-20','requests':10,'tokens':20000,'cost_ngonka':300000}]}
                        return {'status':200,'body':json.dumps(data)}
                    r=client.get(path);return {'status':r.status_code,'body':r.text}
                page=browser.new_page(viewport={'width':width,'height':1000})
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.expose_function('readFixtureApp',read)
                bridge="window.fetch=async path=>{const r=await window.readFixtureApp(path);return new Response(r.body,{status:r.status,headers:{'content-type':'application/json'}})};"
                page.set_content(html.replace('<head>','<head><script>'+bridge+'</script>'))
                expect(page.locator('#status-observed')).to_contain_text('Checked')
                check(f'{width}: no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                check(f'{width}: setup is not a launch',page.locator('#service-state').inner_text()=='Setup incomplete')
                check(f'{width}: catalog fallback is labelled','Snapshot only' in page.locator('#catalog-source').inner_text())
                check(f'{width}: no provider balance invented',page.locator('#provider-value').inner_text()=='Not published')
                check(f'{width}: all four actual app endpoints read',len(set(paths))==4)
                check(f'{width}: measured provider chart rendered',page.locator('#network-chart svg').count()==1)
                check(f'{width}: provider chart is explicitly not Slipvolt activity','not Slipvolt traffic or uptime' in page.locator('#network-chart').locator('xpath=..').inner_text())
                if width in (390,1280):page.screenshot(path=str(OUT/f'status-{width}.png'),full_page=True)
                failing[0]=True;page.locator('#status-refresh').click()
                expect(page.locator('#service-state')).to_have_text('Unavailable')
                check(f'{width}: failure clears old catalog',page.locator('#status-models').count()==1 and page.locator('#status-models').inner_text()=='')
                check(f'{width}: failure clears old funding',page.locator('#reserve-value').inner_text()=='Unavailable' and page.locator('#provider-value').inner_text()=='Unavailable')
                check(f'{width}: failure clears old provider chart',page.locator('#network-chart svg').count()==0 and page.locator('#network-chart-empty').is_visible())
                check(f'{width}: refresh enabled after failure',page.locator('#status-refresh').is_enabled())
                check(f'{width}: no script exceptions',not errors)
                page.close()
            browser.close()
    report={'checks':len(results),'passed':sum(x['passed'] for x in results),'transport':'set_content + read-only FastAPI TestClient bridge',
            'native_browser_transport_tested':False,'paid_inference':False,'results':results}
    (OUT/'status-browser.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))

if __name__=='__main__':run()
