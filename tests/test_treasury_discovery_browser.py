"""Inlined UI fixtures only: discovery and authentication boundaries, no signing."""
import os
from pathlib import Path

from test_treasury_burn import MINT, OWNER, SOURCE, plan
from test_treasury_accounts import parse

ROOT = Path(__file__).resolve().parents[1]


def test_treasury_account_picker_and_navigation_clear_secrets(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    directory = ROOT/'public/admin/burns'
    html = (directory/'index.html').read_text()
    assert 'id="load-accounts"' in html, 'Source account discovery UI is missing'
    html = html.replace('<link rel="stylesheet" href="styles.css">', '<style>'+(directory/'styles.css').read_text()+'</style>')
    for name in ('account-view.js', 'app.js'):
        html = html.replace(f'<script src="{name}" defer></script>', '<script>'+(directory/name).read_text()+'</script>')
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or
            ('/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else p.chromium.executable_path),
            headless=True, args=['--no-sandbox'])
        for width in (320, 390, 768, 1280):
            page = browser.new_page(viewport={'width':width,'height':960})
            errors=[];page.on('pageerror',lambda e: errors.append(str(e)))
            page.set_content(html,wait_until='load')
            page.evaluate('''([mint,owner,accounts,proposal])=>{
                window.calls=[];window.accountsFixture=accounts;window.fail=false;window.delayed=false;window.pending=null;
                window.fetch=async (url,options)=>{
                    calls.push(url);
                    if(url.endsWith('/accounts')){
                        if(window.delayed)return await new Promise(resolve=>window.pending=resolve);
                        if(window.fail)return new Response('private upstream error',{status:503});
                        return new Response(JSON.stringify(accountsFixture),{status:200});
                    }
                    if(url.endsWith('/burn-plan')){const now=Math.floor(Date.now()/1000);return new Response(JSON.stringify({...proposal,...(window.corruptPlan?{expected_source_remaining_raw:'99999999'}:{}),created_at:now,local_review_expires_at:now+60}),{status:200});}
                    return new Response(JSON.stringify({mint,treasury_owner:owner,decimals:6,planning_enabled:true,signing_enabled:false,execution_enabled:false}),{status:200});
                };
            }''',[MINT,OWNER,parse(),plan()])
            assert page.locator('#load-accounts').is_disabled()
            page.locator('#operator-key').fill('adm_fixture');page.locator('#unlock').click()
            expect(page.locator('#load-accounts')).to_be_enabled()
            page.locator('#load-accounts').click()
            expect(page.locator('#account-select')).to_be_enabled()
            assert page.locator('#source-account').input_value()==''
            page.locator('#account-select').select_option(SOURCE)
            expect(page.locator('#source-account')).to_have_value(SOURCE)
            page.locator('#burn-amount').fill('1.25');page.locator('#project-owned').check();page.locator('#prepare').click()
            expect(page.locator('#download-plan')).to_be_enabled()
            page.evaluate('window.corruptPlan=true');page.locator('#prepare').click()
            expect(page.locator('#plan-status')).to_contain_text('inconsistent')
            expect(page.locator('#download-plan')).to_be_disabled()
            page.evaluate('window.corruptPlan=false')
            page.locator('#load-accounts').click()
            expect(page.locator('#download-plan')).to_be_disabled()
            expect(page.locator('#account-select')).to_be_enabled()
            page.evaluate('window.fail=true');page.locator('#load-accounts').click()
            expect(page.locator('#accounts-status')).to_contain_text('503')
            assert page.locator('#account-select').is_disabled()
            assert page.locator('#account-select option').count()==1
            assert 'private upstream error' not in page.locator('body').inner_text()
            page.evaluate('window.fail=false;window.accountsFixture={...accountsFixture,accounts:[],total_raw:"0"}')
            page.locator('#load-accounts').click()
            expect(page.locator('#accounts-status')).to_contain_text('No project-token accounts')
            page.evaluate('window.delayed=true');page.locator('#load-accounts').click()
            page.wait_for_function('window.pending!==null')
            page.locator('#operator-key').fill('adm_changed')
            page.evaluate('window.pending(new Response(JSON.stringify(accountsFixture),{status:200}))')
            page.wait_for_timeout(40)
            assert page.locator('#source-account').input_value()==''
            assert page.locator('#load-accounts').is_disabled()
            page.locator('#unlock').click();expect(page.locator('#treasury-owner')).to_have_text(OWNER)
            page.evaluate('window.dispatchEvent(new Event("pagehide"))')
            assert page.locator('#operator-key').input_value()==''
            assert page.locator('#treasury-owner').inner_text()=='Not loaded'
            assert page.locator('#account-select').is_disabled()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert errors==[]
            page.close()
        browser.close()
