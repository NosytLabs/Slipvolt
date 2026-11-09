"""Initial API examples must match policy regardless of deferred-script timing."""
import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, expect

from scripts.browser_support import launch_chromium
from test_ui_state_transitions import page  # noqa: F401

PUBLIC = Path(__file__).resolve().parents[1] / 'public'


@pytest.mark.parametrize('catalog_arrives_first', [True, False])
def test_initial_example_matches_budget_with_either_script_order(catalog_arrives_first):
    html = re.sub(r'<script\b[^>]*>.*?</script>', '',
                  (PUBLIC / 'index.html').read_text(), flags=re.S)
    model = {'id': 'MiniMaxAI/MiniMax-M2.7', 'availability': 'healthy',
             'routable': True, 'default_completion_tokens': 1024,
             'max_completion_tokens': 4096}
    with sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        try:
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.route('**/*', lambda route: route.fulfill(body=''))
            page.goto('http://holdbyte.test/')
            page.set_content(html)
            page.evaluate('''model => {
                const ready = new Promise(resolve => { window.releaseCatalog = resolve; });
                window.fixtureRequests = [];
                window.fetch = async path => {
                    fixtureRequests.push(path);
                    await ready;
                    const data = path === '/api/status' ? {limits: {max_output_tokens: 16384}}
                        : path === '/api/models' ? {live: true, data: [model]}
                        : {error: 'Not signed in'};
                    return new Response(JSON.stringify(data), {
                        status: path === '/api/account' ? 401 : 200,
                        headers: {'content-type': 'application/json'}
                    });
                };
            }''', model)
            for name in ('core.js', 'request-examples.js', 'app.js'):
                page.add_script_tag(content=(PUBLIC / name).read_text())
            if catalog_arrives_first:
                page.evaluate('releaseCatalog()')
                expect(page.locator('#model-source')).to_contain_text('Live OpenBroker')
            page.add_script_tag(content=(PUBLIC / 'account-tools.js').read_text())
            if not catalog_arrives_first:
                page.evaluate('releaseCatalog()')
            expect(page.locator('#output-tokens')).to_have_value('1024')
            expect(page.locator('#api-code')).to_contain_text('"max_tokens": 1024')
            expect(page.locator('#api-code')).to_contain_text(model['id'])
            assert set(page.evaluate('fixtureRequests')) <= {
                '/api/status', '/api/models', '/api/account'}
            assert not errors
        finally:
            browser.close()


@pytest.mark.parametrize('slow_path', ['/api/status', '/api/models'])
def test_startup_sources_do_not_block_account_or_each_other(page, slow_path):
    html = re.sub(r'<script\b[^>]*>.*?</script>', '',
                  (PUBLIC / 'index.html').read_text(), flags=re.S)
    page.set_content(html)
    page.evaluate('''slowPath => {
      window.fixtureRequests=[];
      const response=data=>new Response(JSON.stringify(data),{headers:{'content-type':'application/json'}});
      const data={
        '/api/status':{provider_configured:true,holder_gate_configured:true,holder_daily_tokens:250000,
          global_daily_tokens:1000000,limits:{},holder_token_symbol:'HOLD',holder_token_decimals:0,min_holding_raw:'1'},
        '/api/models':{live:true,data:[{id:'MiniMaxAI/MiniMax-M2.7',availability:'healthy',routable:true,
          default_completion_tokens:1024,max_completion_tokens:4096}]},
        '/api/account':{wallet:'11111111111111111111111111111111'},
        '/api/membership':{eligibility:{eligible:true},funded_allowance_mode:true,daily_tokens:1234,
          used_tokens:0,reserved_tokens:0,remaining_tokens:1234,history:[],pool:{available_budget_ngonka:100}},
        '/api/usage/summary':{},'/api/keys':{data:[]}
      };
      window.fetch=async path=>{
        fixtureRequests.push(path);
        if(path===slowPath)await new Promise(resolve=>{window.releaseSlow=resolve;});
        if(!(path in data))throw Error('Unexpected startup request: '+path);
        return response(data[path]);
      };
    }''', slow_path)
    for name in ('core.js', 'request-examples.js', 'app.js', 'account-tools.js'):
        page.add_script_tag(content=(PUBLIC / name).read_text())
    expect(page.locator('#access-message')).to_contain_text('Eligible.')
    expect(page.locator('#allowance-label')).to_have_text('1.2K AI tokens / day')
    if slow_path == '/api/status':
        expect(page.locator('#model-source')).to_contain_text('Live OpenBroker')
    else:
        expect(page.locator('#setup-note')).to_contain_text('Provider configured')
    page.evaluate('releaseSlow()')
    expect(page.locator('#setup-note')).to_contain_text('Provider configured')
    expect(page.locator('#model-source')).to_contain_text('Live OpenBroker')
    expect(page.locator('#access-message')).to_contain_text('Eligible.')
    expect(page.locator('#allowance-label')).to_have_text('1.2K AI tokens / day')
    expect(page.locator('#api-code')).to_contain_text('"max_tokens": 1024')


def test_late_public_status_cannot_replace_session_expiration_message(page):
    html = re.sub(r'<script\b[^>]*>.*?</script>', '',
                  (PUBLIC / 'index.html').read_text(), flags=re.S)
    page.set_content(html)
    page.evaluate('''() => {
      const reply=(data,status=200)=>new Response(JSON.stringify(data),{
        status,headers:{'content-type':'application/json'}});
      fetch=async path=>{
        if(path==='/api/status'){
          await new Promise(resolve=>{window.releaseStatus=resolve;});
          return reply({holder_gate_configured:true,holder_daily_tokens:250000,global_daily_tokens:1000000});
        }
        if(path==='/api/models')return reply({live:true,data:[{id:'MiniMaxAI/MiniMax-M2.7',
          default_completion_tokens:1024,max_completion_tokens:4096}]});
        if(path==='/api/account')return reply({wallet:'1'.repeat(32)});
        if(path==='/api/membership')return reply({error:'Session expired'},401);
        if(path==='/api/usage/summary')return reply({});
        if(path==='/api/keys')return reply({data:[]});
        throw Error('Unexpected startup request: '+path);
      };
    }''')
    for name in ('core.js', 'request-examples.js', 'app.js', 'account-tools.js'):
        page.add_script_tag(content=(PUBLIC / name).read_text())
    expect(page.locator('#access-message')).to_have_text('Session expired. Connect your wallet again.')
    page.evaluate('releaseStatus()')
    expect(page.locator('#setup-note')).to_contain_text('Setup mode')
    expect(page.locator('#access-message')).to_have_text('Session expired. Connect your wallet again.')
    assert page.evaluate('S.wallet') is None


def test_late_public_startup_replies_cannot_restore_timed_out_sources(page):
    html = re.sub(r'<script\b[^>]*>.*?</script>', '',
                  (PUBLIC / 'index.html').read_text(), flags=re.S)
    page.set_content(html)
    page.evaluate('''() => {
      const controller=new AbortController();
      AbortSignal.timeout=()=>controller.signal;
      window.expireStartup=()=>controller.abort(new DOMException('Timed out','TimeoutError'));
      window.startupReplies={};
      window.fetch=path=>{
        if(path==='/api/account')return Promise.resolve(new Response('{}',{status:401}));
        return new Promise(resolve=>startupReplies[path]=data=>resolve(new Response(JSON.stringify(data),{
          headers:{'content-type':'application/json'}
        })));
      };
    }''')
    for name in ('core.js', 'request-examples.js', 'app.js', 'account-tools.js'):
        page.add_script_tag(content=(PUBLIC / name).read_text())
    page.evaluate('''() => {
      expireStartup();
      startupReplies['/api/status']({provider_configured:true});
      startupReplies['/api/models']({live:true,data:[{id:'MiniMaxAI/MiniMax-M2.7',
        default_completion_tokens:1024,max_completion_tokens:4096}]});
    }''')
    expect(page.locator('#setup-note')).to_have_text('Backend unavailable')
    expect(page.locator('#model-source')).to_contain_text('live availability unavailable')
    expect(page.locator('#send')).to_be_disabled()
    assert page.evaluate('S.status') is None
