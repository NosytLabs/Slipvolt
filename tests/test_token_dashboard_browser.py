"""Public dashboard browser checks. All RPC data is a fixture, never live."""
import functools
import base64
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright, expect
from scripts.browser_support import launch_chromium

ROOT = Path(__file__).resolve().parents[1]


def test_token_dashboard_layout_empty_error_and_exact_fixture_values(tmp_path):
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT / 'public')))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    origin = 'http://127.0.0.1:' + str(server.server_port)
    mint = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
    fixture = {'status': 'available', 'mint': mint, 'checked_at': 1700000000,
        'mint_state': {'mint': mint, 'decimals': 6, 'supply_raw': '18446744073709551615',
            'slot': 200, 'mint_authority': None, 'freeze_authority': None,
            'token_program': 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'},
        'burns': {'receipt_count': 1, 'decimals': 6, 'burned_raw': '9007199254740993', 'recent': [
            {'signature': '1' * 64, 'slot': 100, 'burned_raw': '9007199254740993'}]}}
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            offline = False
            for width in (320, 390, 768, 1280):
                page = browser.new_page(viewport={'width': width, 'height': 1000})
                errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
                page.route('**/api/token', lambda route: route.fulfill(json=fixture))
                if not offline:
                    try:
                        page.goto(origin + '/token/', wait_until='networkidle')
                    except Exception as exc:
                        if 'ERR_BLOCKED_BY_ADMINISTRATOR' not in str(exc):
                            raise
                        offline = True
                if offline:
                    # Explicit offline DOM/render test, not a bypass or a claim of native HTTP coverage.
                    page.unroute('**/api/token')
                    markup = (ROOT / 'public/token/index.html').read_text()
                    icon = 'data:image/svg+xml;base64,' + base64.b64encode((ROOT / 'public/assets/brand-mark.svg').read_bytes()).decode()
                    markup = markup.replace('../assets/brand-mark.svg', icon)
                    markup = markup.replace('<link rel="stylesheet" href="token.css">', '<style>' + (ROOT / 'public/token/token.css').read_text() + '</style>')
                    fake = 'window.__tokenData=' + json.dumps(fixture) + '; window.__tokenStatus=200; window.fetch=async()=>new Response(JSON.stringify(window.__tokenData),{status:window.__tokenStatus,headers:{"content-type":"application/json"}});'
                    markup = markup.replace('<script src="token.js" defer></script>', '<script>' + fake + (ROOT / 'public/token/token.js').read_text() + '</script>')
                    # Defer is ignored for inline scripts; run the script at the end of body.
                    start = markup.index('<script>'); end = markup.index('</script>', start) + len('</script>')
                    script = markup[start:end]; markup = markup[:start] + markup[end:]
                    markup = markup.replace('</body>', script + '</body>')
                    page.set_content(markup, wait_until='load')
                expect(page.locator('#supply')).to_have_text('18,446,744,073,709.551615')
                expect(page.locator('#burned')).to_have_text('9,007,199,254.740993')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert page.locator('#receipt-list a').count() == 1
                assert page.locator('input').count() == 0
                page.unroute('**/api/token')
                empty = {'status': 'unconfigured', 'mint': None, 'mint_state': None, 'burns': None}
                if offline: page.evaluate('data => window.__tokenData=data', empty)
                else: page.route('**/api/token', lambda route: route.fulfill(json=empty))
                page.locator('#refresh').click()
                expect(page.locator('#state')).to_contain_text('No project mint')
                expect(page.locator('#supply')).to_have_text('Unavailable')
                assert page.locator('#receipt-list a').count() == 0
                assert page.locator('#mint a').count() == 0
                screenshot_dir = os.getenv('HOLDBYTE_SCREENSHOT_DIR')
                if screenshot_dir and width in (390, 1280):
                    Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(Path(screenshot_dir) / f'holdbyte-token-{width}.png'), full_page=True)
                page.unroute('**/api/token')
                if offline: page.evaluate('window.__tokenStatus=503; window.__tokenData="private RPC error"')
                else: page.route('**/api/token', lambda route: route.fulfill(status=503, content_type='text/html', body='<h1>private RPC error</h1>'))
                page.locator('#refresh').click()
                expect(page.locator('#state')).to_contain_text('Could not load')
                assert 'private RPC error' not in page.locator('body').inner_text()
                expect(page.locator('#refresh')).to_be_enabled()
                assert not errors
                page.close()
            print('Token dashboard browser transport:', 'offline inlined fixture' if offline else 'native localhost')
            browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
