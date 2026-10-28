"""Operator claim evidence UI uses local fixtures, never live Solana or funds."""
from pathlib import Path
import json

import httpx
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect

from gridraft.app import Settings, create_app
from gridraft.creator_claims_api import install_creator_claim_routes
from gridraft.integrations import MAINNET_GENESIS
from gridraft.treasury_api import install_treasury_routes
from scripts.browser_support import launch_chromium
from test_creator_claims import CREATOR, SIGNATURE, claim, status
from test_treasury_burn import MINT

ROOT = Path(__file__).resolve().parents[1]


def test_creator_claims_are_explicit_unattributed_and_clear_on_lock():
    directory = ROOT/'public/admin/burns'
    html = (directory/'index.html').read_text()
    html = html.replace('<link rel="stylesheet" href="styles.css">',
                        '<style>'+(directory/'styles.css').read_text()+'</style>')
    for name in ('account-view.js', 'app.js'):
        html = html.replace(f'<script src="{name}" defer></script>',
                            '<script>'+(directory/name).read_text()+'</script>')
    with sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        try:
            page = browser.new_page(viewport={'width': 390, 'height': 960})
            page.evaluate('''([creator,mint,signature]) => {
                window.claimCalls = [];
                window.fetch = async (url, options={}) => {
                    claimCalls.push({url, method: options.method});
                    if (url.endsWith('/creator-claims')) {
                        if (options.method === 'POST' && window.delayClaim)
                            await new Promise(resolve => { window.releaseClaim = resolve; });
                        const data = options.method === 'GET'
                            ? {creator, count: 1, total_lamports: '125000000',
                               complete_history: false, project_attribution: 'unverified', recognized_revenue: false}
                            : {recorded: true, transactions_sent: 0, credits_issued: 0,
                               receipt: {schema: 'holdbyte.creator-claim.v1', signature, creator, asset: 'SOL', amount_lamports: '125000000',
                                         project_attribution: 'unverified', recognized_revenue: false}};
                        return new Response(JSON.stringify(data), {status: 200});
                    }
                    return new Response(JSON.stringify({treasury_owner: creator, mint, decimals: 6,
                        planning_enabled: true, signing_enabled: false, execution_enabled: false}), {status: 200});
                };
            }''', [CREATOR, MINT, SIGNATURE])
            page.set_content(html, wait_until='load')
            assert page.locator('#verify-creator-claim').is_disabled()
            page.locator('#operator-key').fill('adm_fixture')
            page.locator('#unlock').click()
            expect(page.locator('#verify-creator-claim')).to_be_enabled()
            page.locator('#claim-signature').fill(SIGNATURE)
            page.locator('#creator-claim-form').locator('button').click()
            expect(page.locator('#claim-status')).to_contain_text('0.125 SOL')
            assert 'not project revenue' in page.locator('#claim-status').inner_text().lower()
            page.locator('#load-creator-claims').click()
            expect(page.locator('#claim-summary')).to_contain_text('0.125 SOL')
            assert page.evaluate('claimCalls.map(c=>c.method)') == ['GET', 'POST', 'GET']
            page.evaluate('window.delayClaim = true')
            page.locator('#creator-claim-form').locator('button').click()
            page.wait_for_function('typeof window.releaseClaim === "function"')
            page.locator('#lock').click()
            page.evaluate('window.releaseClaim()')
            assert page.locator('#operator-key').input_value() == ''
            assert page.locator('#claim-signature').input_value() == ''
            assert page.locator('#verify-creator-claim').is_disabled()
            assert '0.125' not in page.locator('#claim-summary').inner_text()
            assert page.locator('#claim-status').inner_text() == 'No creator claim submitted.'
        finally:
            browser.close()


def test_claim_screen_records_through_the_real_api_with_offline_rpc(tmp_path):
    directory = ROOT/'public/admin/burns'
    html = (directory/'index.html').read_text()
    html = html.replace('<link rel="stylesheet" href="styles.css">',
                        '<style>'+(directory/'styles.css').read_text()+'</style>')
    for name in ('account-view.js', 'app.js'):
        html = html.replace(f'<script src="{name}" defer></script>',
                            '<script>'+(directory/name).read_text()+'</script>')
    settings = Settings(origin='http://testserver', admin_key='adm_fixture', access_mode='prepaid',
                        solana_rpc='https://rpc.example.invalid/private')
    rpc_calls = []
    def upstream(request):
        body = json.loads(request.content); rpc_calls.append(body['method'])
        value = MAINNET_GENESIS if body['method'] == 'getGenesisHash' else status() if body['method'] == 'getSignatureStatuses' else claim()
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': body['id'], 'result': value})
    transport = httpx.MockTransport(upstream)
    app = create_app(settings, str(tmp_path/'browser.db'))
    install_treasury_routes(app, settings, treasury_owner=CREATOR, transport=transport)
    install_creator_claim_routes(app, settings, treasury_owner=CREATOR, transport=transport)
    with TestClient(app) as client, sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        try:
            page = browser.new_page(viewport={'width': 320, 'height': 960})
            def bridge(path, method, auth, body):
                assert path in ('/api/admin/treasury', '/api/admin/treasury/creator-claims')
                response = client.request(method, path, headers={
                    'Authorization': auth, 'Origin': 'http://testserver',
                    'Content-Type': 'application/json'}, content=body)
                return {'status': response.status_code, 'body': response.text}
            page.expose_function('fixtureBridge', bridge)
            page.evaluate('''() => { window.fetch = async (path, options={}) => {
                const result = await window.fixtureBridge(path, options.method || 'GET',
                    options.headers?.Authorization || '', options.body || '');
                return new Response(result.body, {status: result.status,
                    headers: {'content-type': 'application/json'}});
            }; }''')
            page.set_content(html, wait_until='load')
            page.locator('#operator-key').fill('adm_fixture')
            page.locator('#unlock').click()
            expect(page.locator('#verify-creator-claim')).to_be_enabled()
            page.locator('#claim-signature').fill(SIGNATURE)
            page.locator('#verify-creator-claim').click()
            expect(page.locator('#claim-status')).to_contain_text('0.125 SOL')
            assert 'not project revenue' in page.locator('#claim-status').inner_text().lower()
            page.locator('#load-creator-claims').click()
            expect(page.locator('#claim-summary')).to_contain_text('1 recorded claim')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert rpc_calls == ['getGenesisHash', 'getSignatureStatuses', 'getTransaction']
            assert app.state.store.business_summary()['entries'] == 0
            assert app.state.membership.pool()['allocated_ngonka'] == 0
        finally:
            browser.close()
