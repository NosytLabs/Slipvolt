"""Operator writes own their controls until the submitted operation settles."""
import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from scripts.browser_support import launch_chromium
from scripts.check_admin_ui import overview

PUBLIC = Path(__file__).resolve().parents[1] / 'public'


@pytest.fixture
def admin_page():
    with sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/*', lambda route: route.fulfill(body=''))
        page.goto('https://holdbyte.test/')
        html = re.sub(r'<script\b[^>]*>.*?</script>', '',
                      (PUBLIC / 'admin/index.html').read_text(), flags=re.S)
        page.set_content(html)
        page.add_script_tag(content=(PUBLIC / 'admin/app.js').read_text())
        page.evaluate('overview => render(overview)', overview)
        yield page
        browser.close()
        assert not errors


@pytest.mark.parametrize('form_id,amount,reference', [
    ('fund-form', 'fund-gnk', 'fund-ref'),
    ('business-form', 'biz-amount', 'biz-ref'),
])
@pytest.mark.parametrize('succeeds', [True, False])
def test_accounting_form_serializes_submissions_and_preserves_failed_draft(
        admin_page, form_id, amount, reference, succeeds):
    result = admin_page.evaluate('''async ({formId,amount,reference,succeeds,overview}) => {
      const writes=[];
      api=(path,options)=> {
        if(options?.method==='POST')return new Promise((resolve,reject)=>writes.push({resolve,reject,body:JSON.parse(options.body)}));
        return Promise.resolve(path.startsWith('/api/admin/overview')?overview:{data:[]});
      };
      const form=document.getElementById(formId),value=document.getElementById(amount),ref=document.getElementById(reference);
      value.value='42';ref.value='fixture-reference';
      const first=form.onsubmit({preventDefault(){},target:form});
      const locked=Array.from(form.querySelectorAll('input,select,button')).every(input=>input.disabled);
      const second=form.onsubmit({preventDefault(){},target:form});
      const count=writes.length;
      for(const write of writes) succeeds?write.resolve({recorded:true}):write.reject(Error('Fixture write failed'));
      await Promise.all([first,second]);
      return {count,locked,enabled:Array.from(form.querySelectorAll('input,select,button')).every(input=>!input.disabled),
        value:value.value,reference:ref.value,notice:document.getElementById('notice').textContent};
    }''', {'formId': form_id, 'amount': amount, 'reference': reference,
           'succeeds': succeeds, 'overview': overview})
    assert result['count'] == 1
    assert result['locked'] and result['enabled']
    assert result['value'] == ('' if succeeds else '42')
    assert result['reference'] == ('' if succeeds else 'fixture-reference')
    assert ('recorded' if succeeds else 'Fixture write failed') in result['notice']


@pytest.mark.parametrize('switch_wallet', [False, True])
def test_user_policy_fields_cannot_accept_edits_that_a_pending_save_would_erase(admin_page, switch_wallet):
    result = admin_page.evaluate('''async switchWallet => {
      api=()=>Promise.resolve({data:[]});
      await manageUser('wallet-a',{note:'Original A'});
      let finish;
      api=(path,options)=>options?.method==='PUT'
        ?new Promise(resolve=>{finish=resolve;}):Promise.resolve({data:[]});
      const form=document.getElementById('user-policy-form');
      document.getElementById('user-note').value='Saved A';
      const pending=form.onsubmit({preventDefault(){}});
      const locked=Array.from(form.querySelectorAll('input,button')).every(input=>input.disabled);
      if(switchWallet)await manageUser('wallet-b',{note:'Original B'});
      finish({note:'Saved A'});await pending;
      return {locked,enabled:Array.from(form.querySelectorAll('input,button')).every(input=>!input.disabled),
        wallet:document.getElementById('user-detail-title').textContent,note:document.getElementById('user-note').value};
    }''', switch_wallet)
    assert result == {'locked': True, 'enabled': True,
                      'wallet': 'wallet-b' if switch_wallet else 'wallet-a',
                      'note': 'Original B' if switch_wallet else 'Saved A'}
