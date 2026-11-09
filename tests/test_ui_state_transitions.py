"""Exercise actual browser controls with delayed, reordered local responses."""
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from scripts.browser_support import launch_chromium
from scripts.check_admin_ui import overview

PUBLIC = Path(__file__).resolve().parents[1] / 'public'


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/*', lambda route: route.fulfill(body=''))
        page.goto('https://holdbyte.test/')
        yield page
        browser.close()
        assert not errors


def load_holder(page):
    html = re.sub(r'<script\b[^>]*>.*?</script>', '',
                  (PUBLIC / 'index.html').read_text(), flags=re.S)
    page.set_content(html)
    page.evaluate('''() => {
      window.calls = [];
      window.pending = [];
      window.fetch = async (path, options) => {
        calls.push({path, options});
        const reply = (data, status=200) => new Response(JSON.stringify(data), {
          status, headers: {'content-type':'application/json'}
        });
        if (path === '/api/status') return reply({capabilities:{streaming:false}});
        if (path === '/api/models') return reply({live:true,data:[{
          id:'MiniMaxAI/MiniMax-M2.7',routable:true,availability:'healthy',
          default_completion_tokens:512,max_completion_tokens:4096
        }]});
        if (path === '/api/account') return reply({error:'Not signed in'},401);
        if (path === '/api/preflight') return reply({allowed:true,estimated_ai_tokens:100,estimated_budget_ngonka:1500});
        // Deliberately ignore abort to simulate a late queued response.
        return new Promise(resolve => pending.push(data => resolve(reply(data))));
      };
    }''')
    for name in ('core.js', 'request-examples.js', 'request-tools.js',
                 'app.js', 'account-tools.js', 'launch-tools.js'):
        page.add_script_tag(content=(PUBLIC / name).read_text())
    expect(page.locator('#model-source')).to_contain_text('Live OpenBroker')
    page.locator('#existing-key').evaluate("node => node.closest('details').open = true")
    page.locator('#existing-key').fill('sv_' + 'a' * 43)
    page.locator('#prompt').fill('Example prompt')


def test_send_invalidates_preflight_and_editing_cannot_reenable_it(page):
    load_holder(page)
    page.locator('#check-request').click()
    expect(page.locator('#preflight-result')).to_have_attribute('data-verdict', 'fits')
    page.locator('#send').click()
    expect(page.locator('#preflight-result')).not_to_have_attribute('data-verdict', 'fits')
    page.locator('#prompt').fill('Next prompt')
    expect(page.locator('#check-request')).to_be_disabled()
    page.evaluate("document.getElementById('check-request').dispatchEvent(new Event('click'))")
    assert page.evaluate("calls.filter(call => call.path === '/api/preflight').length") == 1


def test_stop_and_reset_reject_late_completion_without_poisoning_next_request(page):
    load_holder(page)
    page.locator('#send').click()
    page.locator('#stop-request').click()
    expect(page.locator('#stop-request')).to_be_disabled()
    page.evaluate("pending[0]({choices:[{message:{content:'Late cancelled answer'}}]})")
    expect(page.locator('#result')).to_contain_text('Request stopped')
    expect(page.locator('#send')).to_be_enabled()
    assert page.evaluate('S.conversation.length') == 0
    page.locator('#send').click()
    page.locator('#new-chat').click()
    page.locator('#prompt').fill('New chat prompt')
    page.locator('#send').click()
    page.evaluate("pending[1]({choices:[{message:{content:'Obsolete answer'}}]})")
    expect(page.locator('#send')).to_be_disabled()
    page.evaluate("pending[2]({choices:[{message:{content:'Current answer'}}]})")
    expect(page.locator('#result')).to_have_text('Current answer')
    expect(page.locator('#send')).to_be_enabled()
    assert page.evaluate('S.conversation') == [
        {'user': 'New chat prompt', 'assistant': 'Current answer'}]


def test_send_cancels_pending_preflight_and_ignores_its_late_result(page):
    load_holder(page)
    page.evaluate('''() => {
      const original = fetch;
      window.fetch = (path, options) => {
        if (path !== '/api/preflight') return original(path, options);
        window.checkSignal = options.signal;
        return new Promise(resolve => { window.finishCheck = () => resolve(new Response(
          JSON.stringify({allowed:true,estimated_ai_tokens:100,estimated_budget_ngonka:1500}),
          {headers:{'content-type':'application/json'}})); });
      };
    }''')
    page.locator('#check-request').click()
    page.locator('#send').click()
    assert page.evaluate('checkSignal.aborted')
    page.evaluate('finishCheck()')
    expect(page.locator('#check-request')).to_be_disabled()
    expect(page.locator('#preflight-result')).not_to_have_attribute('data-verdict', 'fits')


def load_admin(page):
    html = re.sub(r'<script\b[^>]*>.*?</script>', '',
                  (PUBLIC / 'admin/index.html').read_text(), flags=re.S)
    page.set_content(html)
    page.add_script_tag(content=(PUBLIC / 'admin/app.js').read_text())
    page.evaluate('overview => render(overview)', overview)


def test_admin_policy_save_serializes_writes_and_ignores_older_overview(page):
    load_admin(page)
    result = page.evaluate('''async overview => {
      const writes = [], reads = [];
      api = (path, options) => {
        if (options?.method === 'PUT') return new Promise(resolve => writes.push({resolve,body:JSON.parse(options.body)}));
        if (path.startsWith('/api/admin/overview')) return new Promise(resolve => reads.push(resolve));
        return Promise.resolve({data:[]});
      };
      const older = load();
      const input = document.querySelector('[data-k=wallet_rpm]');
      input.value = '42'; input.dispatchEvent(new Event('input'));
      const first = document.getElementById('save-config').onclick();
      const second = document.getElementById('save-config').onclick();
      const locked = input.disabled && document.getElementById('save-config').disabled
        && document.getElementById('discard-config').disabled;
      reads[0](overview); await older;
      const oldReadIgnored = input.value === '42' && input.disabled;
      const count = writes.length;
      // Complete all writes so a buggy implementation cannot hang this regression.
      for (const write of writes) write.resolve({...overview.config,wallet_rpm:42});
      await new Promise(resolve => setTimeout(resolve, 0));
      for (const read of reads.slice(1)) read({...overview,config:{...overview.config,wallet_rpm:42}});
      await Promise.all([first,second]);
      return {locked,oldReadIgnored,count,value:input.value,enabled:!input.disabled,
        saved:document.getElementById('config-state').textContent};
    }''', overview)
    assert result == {'locked': True, 'oldReadIgnored': True, 'count': 1,
                      'value': '42', 'enabled': True, 'saved': 'Saved'}


def test_admin_failed_policy_save_keeps_draft_for_explicit_retry(page):
    load_admin(page)
    result = page.evaluate('''async overview => {
      let writes = 0;
      api = (path, options) => {
        if (options?.method === 'PUT') {
          writes++;
          return writes === 1 ? Promise.reject(Error('Fixture outage')) : Promise.resolve({});
        }
        return Promise.resolve(path.startsWith('/api/admin/overview')
          ? {...overview,config:{...overview.config,wallet_rpm:42}} : {data:[]});
      };
      const input = document.querySelector('[data-k=wallet_rpm]');
      input.value='42'; input.dispatchEvent(new Event('input'));
      await document.getElementById('save-config').onclick();
      const failed={writes,value:input.value,enabled:!input.disabled,
        state:document.getElementById('config-state').textContent,
        retry:!document.getElementById('save-config').disabled};
      await document.getElementById('save-config').onclick();
      return {failed,writes,saved:document.getElementById('config-state').textContent};
    }''', overview)
    assert result == {'failed': {'writes': 1, 'value': '42', 'enabled': True,
                                'state': 'Unsaved changes', 'retry': True},
                      'writes': 2, 'saved': 'Saved'}
