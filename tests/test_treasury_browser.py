"""Browser workflow fixtures, not wallet signing or a live-chain test."""
import json
import os
from pathlib import Path

import pytest

from test_treasury_burn import MINT, OWNER, SOURCE, fixture, plan

ROOT = Path(__file__).resolve().parents[1]


def test_treasury_operator_review_and_reset_flows(tmp_path):
    path = ROOT/'public/admin/burns/index.html'
    assert path.exists(), 'Operator burn workflow is missing'
    from playwright.sync_api import sync_playwright, expect
    html = path.read_text()
    html = html.replace('<link rel="stylesheet" href="styles.css">',
        '<style>'+(path.parent/'styles.css').read_text()+'</style>')
    html = html.replace('<script src="app.js" defer></script>',
        '<script>'+(path.parent/'app.js').read_text()+'</script>')
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or
            ('/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else p.chromium.executable_path),
            headless=True, args=['--no-sandbox'])
        for width in (320, 390, 768, 1280):
            page = browser.new_page(viewport={'width':width,'height':960}, accept_downloads=True)
            errors=[]; page.on('pageerror', lambda e:errors.append(str(e)))
            page.add_init_script('window.__unused=true')
            page.set_content(html, wait_until='load')
            page.evaluate("""([mint, owner, template]) => {
                window.fixtureCalls=[]; window.fixtureDeferred=null;
                window.fixturePlan=template;
                window.fixtureFail=false;
                window.fetch=async (url, options={}) => {
                    window.fixtureCalls.push({url,options});
                    if(window.fixtureFail)return new Response('private upstream secret',{status:503});
                    if(url.endsWith('/burn-plan')){
                        if(window.fixtureDelay)return await new Promise(resolve=>window.fixtureDeferred=resolve);
                        const now=Math.floor(Date.now()/1000);
                        return new Response(JSON.stringify({...window.fixturePlan,created_at:now,local_review_expires_at:now+60}),{status:200,headers:{'content-type':'application/json'}});
                    }
                    if(url.endsWith('/burns'))return new Response(JSON.stringify({recorded:false,transactions_sent:0,receipt:{burned_raw:'1250000',signature:'1'.repeat(64)}}),{status:200,headers:{'content-type':'application/json'}});
                    return new Response(JSON.stringify({treasury_owner:owner,mint,decimals:6,planning_enabled:true,signing_enabled:false}),{status:200,headers:{'content-type':'application/json'}});
                };
            }""",[MINT,OWNER,plan()])
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert page.locator('#download-plan').is_disabled()
            page.locator('#operator-key').fill('adm_fixture');page.locator('#unlock').click()
            expect(page.locator('#treasury-owner')).to_have_text(OWNER)
            page.locator('#source-account').fill(SOURCE);page.locator('#burn-amount').fill('1.25')
            page.locator('#project-owned').check();page.locator('#prepare').click()
            expect(page.locator('#download-plan')).to_be_enabled()
            assert 'Unsigned' in page.locator('#plan-status').inner_text()
            assert page.locator('#amount-review').inner_text()=='1.25'
            assert 'adm_fixture' not in page.locator('#plan-json').inner_text()
            assert page.evaluate('fixtureCalls.filter(x=>x.url.endsWith("/burn-plan")).length')==1
            with page.expect_download() as info:page.locator('#download-plan').click()
            assert info.value.suggested_filename=='holdbyte-burn-instruction.json'
            assert 'signature' not in json.loads(Path(info.value.path()).read_text())
            page.locator('#burn-amount').fill('2')
            expect(page.locator('#download-plan')).to_be_disabled()
            assert page.locator('#plan-json').inner_text()==''
            # A response for a now-edited input cannot restore the previous plan.
            page.locator('#burn-amount').fill('1.25')
            page.evaluate('window.fixtureDelay=true');page.locator('#prepare').click()
            page.wait_for_function('window.fixtureDeferred!==null')
            page.locator('#burn-amount').fill('3')
            page.evaluate("""() => {const now=Math.floor(Date.now()/1000);fixtureDeferred(new Response(JSON.stringify({...fixturePlan,created_at:now,local_review_expires_at:now+60}),{status:200}));}""")
            page.wait_for_timeout(30)
            assert page.locator('#download-plan').is_disabled()
            # Errors clear old content and do not echo proxy response bodies.
            page.evaluate('window.fixtureDelay=false;window.fixtureFail=true')
            page.locator('#prepare').click()
            expect(page.locator('#plan-status')).to_contain_text('503')
            assert 'private upstream secret' not in page.locator('body').inner_text()
            page.evaluate('window.fixtureFail=false')
            page.locator('#signature').fill('1'*64);page.locator('#verify-receipt').click()
            expect(page.locator('#receipt-status')).to_contain_text('already recorded')
            # Lock and changing operator keys must erase data and cancel pending work.
            page.locator('#lock').click()
            assert page.locator('#operator-key').input_value()==''
            assert page.locator('#source-account').input_value()==''
            assert page.locator('#signature').input_value()==''
            assert page.locator('#treasury-owner').text_content()=='Not loaded'
            assert page.locator('#download-plan').is_disabled()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert errors==[]
            page.close()
        browser.close()
