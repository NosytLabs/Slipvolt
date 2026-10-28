"""Live-directory UI exercised with fixtures, not real provider acceptance."""
from pathlib import Path
from scripts.browser_support import launch_chromium

ROOT = Path(__file__).resolve().parents[1]
CATALOG = {'live':True,'source':'OpenBroker catalog + local service policy','inference_tested':False,'data':[
    {'id':'MiniMaxAI/MiniMax-M2.7','name':'MiniMax M2.7','context_length':180000,'max_completion_tokens':4096,'default_completion_tokens':1024,'availability':'healthy','routable':True,'limits_source':'Reviewed local policy'},
    {'id':'deepseek-ai/DeepSeek-V4-Flash-0731','name':'DeepSeek V4 Flash','context_length':400000,'max_completion_tokens':8192,'default_completion_tokens':4096,'availability':'unavailable','routable':False,'operator_override_configured':True,'discovered_max_completion_tokens':16384}]}


def test_model_directory_search_refresh_fallback_and_keyboard(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    directory = ROOT/'public/models'
    assert (directory/'index.html').exists(), 'Model directory is not implemented'
    html = (directory/'index.html').read_text()
    html = html.replace('<link rel="stylesheet" href="styles.css">','<style>'+(directory/'styles.css').read_text()+'</style>')
    for name in ('view.js','app.js'):
        html = html.replace(f'<script src="{name}" defer></script>', '<script>'+(directory/name).read_text()+'</script>')
    with sync_playwright() as p:
        browser=launch_chromium(p)
        for width in (320,390,768,1280):
            page=browser.new_page(viewport={'width':width,'height':900})
            errors=[];page.on('pageerror',lambda e: errors.append(str(e)))
            page.evaluate('''catalog=>{
                window.fixture=catalog;window.calls=[];window.fail=false;window.delay=false;window.pending=null;window.copied=null;
                Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async v=>window.copied=v}});
                window.fetch=async(url,options)=>{
                    calls.push(url);
                    if(window.delay)return await new Promise(resolve=>window.pending=resolve);
                    if(window.fail)return new Response('private provider error',{status:503});
                    return new Response(JSON.stringify(fixture),{status:200});
                };
            }''',CATALOG)
            page.set_content(html,wait_until='load')
            expect(page.locator('.model-card')).to_have_count(2)
            assert page.locator('#catalog-state').inner_text()=='Live catalog'
            page.locator('#model-search').fill('deepseek');expect(page.locator('.model-card')).to_have_count(1)
            assert '8192' not in page.locator('.model-card').inner_text() # grouped human display
            assert '8,192' in page.locator('.model-card').inner_text()
            page.locator('#model-search').fill('');page.locator('#availability-filter').select_option('listed')
            expect(page.locator('.model-card')).to_have_count(1)
            page.locator('.copy-id').click();page.wait_for_function('window.copied!==null')
            assert page.evaluate('window.copied')==CATALOG['data'][0]['id']
            page.locator('#model-search').fill('no-matching-model');expect(page.locator('#empty-state')).to_be_visible()
            page.locator('#model-search').fill('');page.locator('#availability-filter').select_option('all')
            page.evaluate('window.fixture={...fixture,live:false}')
            page.locator('#refresh-models').click();expect(page.locator('#catalog-state')).to_have_text('Snapshot only')
            assert 'not live availability' in page.locator('#catalog-message').inner_text()
            page.evaluate('window.fail=true');page.locator('#refresh-models').click()
            expect(page.locator('#catalog-state')).to_have_text('Unavailable')
            expect(page.locator('.model-card')).to_have_count(0)
            assert 'private provider error' not in page.locator('body').inner_text()
            page.evaluate('window.fail=false;window.delay=true');page.locator('#refresh-models').click()
            page.wait_for_function('window.pending!==null')
            page.evaluate('window.dispatchEvent(new Event("pagehide"));window.pending(new Response(JSON.stringify(fixture),{status:200}))')
            page.wait_for_timeout(40)
            expect(page.locator('.model-card')).to_have_count(0)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert page.evaluate('calls.every(url=>url==="/api/models")')
            assert errors==[]
            page.close()
        browser.close()
