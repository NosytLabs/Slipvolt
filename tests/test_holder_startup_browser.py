"""Initial API examples must match policy regardless of deferred-script timing."""
import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, expect

from scripts.browser_support import launch_chromium

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
