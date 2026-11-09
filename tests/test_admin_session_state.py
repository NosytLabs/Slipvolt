"""Retained operator pages require a fresh unlock and reject former-session replies."""
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from scripts.browser_support import launch_chromium
from scripts.check_admin_ui import overview

PUBLIC = Path(__file__).resolve().parents[1] / 'public/admin'


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/*', lambda route: route.fulfill(body=''))
        page.goto('https://holdbyte.test/')
        page.set_content(re.sub(r'<script\b[^>]*>.*?</script>', '',
                                (PUBLIC / 'index.html').read_text(), flags=re.S))
        page.evaluate('''overview => {
          window.fixtureOverview=overview;window.calls=[];window.pending=[];window.delayRoute='';
          window.confirm=()=>true;
          window.fetch=(path,options)=>{
            const route=options.method||'GET',name=route+' '+path.split('?')[0];
            calls.push({path,options});
            const reply=data=>({ok:true,json:async()=>data});
            if(name===delayRoute)return new Promise((resolve,reject)=>pending.push({
              resolve:data=>resolve(reply(data)),reject
            }));
            let data={data:[]};
            if(path==='/api/admin/config')data=fixtureOverview.config;
            if(path.startsWith('/api/admin/overview'))data=fixtureOverview;
            if(path==='/api/admin/connections')data={};
            if(path==='/api/admin/readiness')data={status:'blocked',checks:[],
              capacity:{full_allowances_per_day:0},accounting_notice:'Fixture',checked_at:1};
            if(path.endsWith('/keys'))data={data:[{id:'key-1',prefix:'sv_fixture',
              name:'Fixture key',created:1,revoked:false}]};
            return Promise.resolve(reply(data));
          };
        }''', overview)
        for name in ('app.js', 'connections.js', 'readiness.js'):
            page.add_script_tag(content=(PUBLIC / name).read_text())
        yield page
        browser.close()
        assert not errors


def unlock(page):
    page.locator('#admin-key').fill('fixture-admin-key')
    page.locator('#unlock').click()
    expect(page.locator('#console')).to_be_visible()
    page.wait_for_function('!unlocking')


@pytest.mark.parametrize('transition', ['lock', 'pagehide'])
def test_lock_and_retained_pagehide_clear_private_views_and_invalidate_reads(page, transition):
    unlock(page)
    page.evaluate('''() => {
      delayRoute='GET /api/admin/overview';load();
      $('user-note').value='Private operator draft';
    }''')
    calls = page.evaluate('calls.length')
    if transition == 'lock':
        page.locator('#logout').click()
    else:
        page.evaluate("dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))")
    expect(page.locator('#console')).to_be_hidden()
    expect(page.locator('#login')).to_be_visible()
    assert page.evaluate('key') == ''
    assert page.locator('#metrics').text_content() == ''
    expect(page.locator('#user-note')).to_have_value('')
    page.evaluate('''async () => {
      pending[0].resolve({...fixtureOverview,local:{...fixtureOverview.local,requests:777}});
      dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
      await new Promise(resolve=>setTimeout(resolve,0));
    }''')
    expect(page.locator('#console')).to_be_hidden()
    assert page.locator('#metrics').text_content() == ''
    assert page.evaluate('calls.length') == calls
    # Locked synthetic actions must not dispatch a credential-bearing request.
    page.evaluate("api('/api/admin/config').catch(()=>{})")
    assert page.evaluate('calls.length') == calls
    page.evaluate("delayRoute=''")
    unlock(page)


@pytest.mark.parametrize('late_error', [False, True])
def test_old_unlock_cannot_open_or_release_a_new_unlock_after_pagehide(page, late_error):
    page.evaluate("delayRoute='GET /api/admin/config'")
    page.locator('#admin-key').fill('old-fixture-key')
    page.locator('#unlock').click()
    page.evaluate("dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))")
    page.locator('#admin-key').fill('new-fixture-key')
    page.locator('#unlock').click()
    page.evaluate('''async lateError => {
      lateError?pending[0].reject(Error('Old unlock failed')):pending[0].resolve(fixtureOverview.config);
      await new Promise(resolve=>setTimeout(resolve,0));
    }''', late_error)
    expect(page.locator('#console')).to_be_hidden()
    expect(page.locator('#unlock')).to_be_disabled()
    expect(page.locator('#login-msg')).to_have_text('Checking…')
    assert page.evaluate('calls.length') == 2
    page.evaluate('pending[1].resolve(fixtureOverview.config)')
    expect(page.locator('#console')).to_be_visible()
    page.wait_for_function('!unlocking')
    assert page.evaluate('key') == 'new-fixture-key'


def start_write(page, kind):
    page.evaluate('''async kind => {
      if(kind==='config'){
        document.querySelector('[data-k=wallet_rpm]').value='42';
        markConfigDirty();$('save-config').click();
      }else if(kind==='user'){
        await manageUser('wallet-a',{note:'Current draft'});
        $('user-policy-form').requestSubmit();
      }else if(kind==='revoke'){
        await manageUser('wallet-a');document.querySelector('.revoke-key').click();
      }else{
        const fund=kind==='fund',form=$(fund?'fund-form':'business-form');
        $(fund?'fund-gnk':'biz-amount').value='42';
        $(fund?'fund-ref':'biz-ref').value='current-reference';form.requestSubmit();
      }
    }''', kind)


@pytest.mark.parametrize('kind,route,control', [
    ('config', 'PUT /api/admin/config', '#save-config'),
    ('fund', 'POST /api/admin/allowance/fund', '#fund-form button'),
    ('business', 'POST /api/admin/business', '#business-form button'),
    ('user', 'PUT /api/admin/users/wallet-a', '#user-policy-form button'),
    ('revoke', 'DELETE /api/admin/users/wallet-a/keys/key-1', '.revoke-key'),
])
@pytest.mark.parametrize('late_error', [False, True])
def test_former_session_write_cannot_refresh_reset_or_unlock_current_write(
        page, kind, route, control, late_error):
    unlock(page)
    page.evaluate('route=>{delayRoute=route;}', route)
    start_write(page, kind)
    page.locator('#logout').click()
    expect(page.locator('#login-msg')).to_contain_text('check their records before retrying')
    unlock(page)
    start_write(page, kind)
    calls = page.evaluate('calls.length')
    page.evaluate('''async lateError => {
      lateError?pending[0].reject(Error('Old write failed')):pending[0].resolve({});
      await new Promise(resolve=>setTimeout(resolve,0));
    }''', late_error)
    expect(page.locator(control)).to_be_disabled()
    assert page.evaluate('calls.length') == calls
    assert page.locator('#notice').text_content() == ''
    if kind in ('fund', 'business'):
        expect(page.locator('#fund-ref' if kind == 'fund' else '#biz-ref')).to_have_value('current-reference')
    # The current failure preserves its draft and returns control for explicit retry.
    page.evaluate("pending[1].reject(Error('Current write failed'))")
    expect(page.locator(control)).to_be_enabled()
    expect(page.locator('#notice')).to_have_text('Current write failed')


@pytest.mark.parametrize('quote', [False, True])
def test_old_diagnostic_or_quote_cannot_replace_or_unlock_new_session_operation(page, quote):
    unlock(page)
    route = '/api/admin/swap/quote' if quote else '/api/admin/connections/check'
    page.evaluate('route=>{delayRoute="POST "+route;}', route)
    if quote:
        page.locator('#quote-form').evaluate('form=>form.closest("details").open=true')
    control = '#quote-form button' if quote else '#connections-check'
    output = '#quote-result' if quote else '#connections-result'
    page.locator(control).click()
    page.locator('#logout').click()
    unlock(page)
    page.locator(control).click()
    calls = page.evaluate('calls.length')
    if quote:
        page.evaluate("$('quote-form').requestSubmit()")
        assert page.evaluate('calls.length') == calls
    page.evaluate('''async () => {
      pending[0].resolve({asset:'SOL',input_amount:'1',expected_usdc:'10',minimum_usdc:'9.95',
        local_expires_at:Date.now()/1000+15,notice:'Old quote'});
      await new Promise(resolve=>setTimeout(resolve,0));
    }''')
    expect(page.locator(control)).to_be_disabled()
    expect(page.locator(output)).to_contain_text('Requesting' if quote else 'Checking')
    page.evaluate("pending[1].reject(Error('Current check failed'))")
    expect(page.locator(control)).to_be_enabled()
    expect(page.locator(output)).to_have_text('Current check failed')


def test_quote_expiry_cannot_change_a_locked_session(page):
    unlock(page)
    page.evaluate('''() => {
      delayRoute='POST /api/admin/swap/quote';
      const schedule=setTimeout;window.setTimeout=(callback,delay,...args)=>{
        if(delay>14000&&delay<=15000)window.expireQuote=callback;
        return schedule(callback,delay,...args);
      };
    }''')
    page.locator('#quote-form').evaluate('form=>form.closest("details").open=true')
    page.locator('#quote-form button').click()
    page.evaluate('''pending[0].resolve({asset:'SOL',input_amount:'1',expected_usdc:'10',minimum_usdc:'9.95',
      local_expires_at:Date.now()/1000+15,notice:'Read-only fixture'})''')
    expect(page.locator('#quote-result')).to_contain_text('Read-only fixture')
    page.locator('#logout').click()
    page.evaluate('expireQuote()')
    expect(page.locator('#quote-result')).to_contain_text('No swap is built or submitted')
