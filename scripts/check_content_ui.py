"""Render static guides on desktop/mobile with intercepted local files.

Falls back to set_content only when the environment explicitly blocks navigation.
No live provider, wallet, payment or deployment is used. FastAPI routing and
security headers are covered separately by tests/test_public_content.py.
"""
import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit
from playwright.sync_api import sync_playwright, Error as BrowserError

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'
OUT = ROOT / 'evidence-current'
BASE = 'https://slipvolt.test'


def run():
    OUT.mkdir(exist_ok=True)
    results = []
    unexpected = []

    def check(name, passed):
        results.append({'name': name, 'passed': bool(passed)})
        if not passed:
            raise AssertionError(name)

    def serve(route):
        url = urlsplit(route.request.url)
        target = (PUBLIC / unquote(url.path).lstrip('/')).resolve()
        if url.netloc != 'slipvolt.test' or not target.is_relative_to(PUBLIC.resolve()):
            unexpected.append(route.request.url)
            route.abort()
            return
        if target.is_dir():
            target /= 'index.html'
        if not target.is_file():
            unexpected.append(route.request.url)
            route.fulfill(status=404, body='Not found')
            return
        route.fulfill(status=200, body=target.read_bytes(),
                      content_type=mimetypes.guess_type(str(target))[0] or 'application/octet-stream')

    with sync_playwright() as p:
        chromium = os.getenv('CHROMIUM_PATH') or ('/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else p.chromium.executable_path)
        browser = p.chromium.launch(executable_path=chromium, headless=True, args=['--no-sandbox'])
        transport = 'intercepted local static files'
        probe = browser.new_page()
        probe.route('**/*', serve)
        try:
            probe.goto(f'{BASE}/help/', wait_until='load')
        except BrowserError as exc:
            if 'ERR_BLOCKED_BY_ADMINISTRATOR' not in str(exc):
                browser.close()
                raise
            transport = 'set_content; browser navigation blocked by environment'
        finally:
            probe.close()

        def navigate(page, name):
            if transport == 'intercepted local static files':
                page.goto(f'{BASE}/{name}/', wait_until='load')
            else:
                text = (PUBLIC/name/'index.html').read_text()
                for css in ('styles.css', 'content.css'):
                    text = text.replace(f'<link rel="stylesheet" href="../{css}">', '<style>'+(PUBLIC/css).read_text()+'</style>')
                text = text.replace('<link rel="icon" href="../favicon.svg">', '')
                page.set_content(text, wait_until='load')

        try:
            for width in (320, 390, 768, 1280):
                for name in ('help', 'privacy', 'terms'):
                    page = browser.new_page(viewport={'width': width, 'height': 900})
                    errors = []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.route('**/*', serve)
                    navigate(page, name)
                    check(f'{name} {width}px: no page overflow', page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                    check(f'{name} {width}px: one visible h1', page.locator('h1').count() == 1 and page.locator('h1').is_visible())
                    page.keyboard.press('Tab')
                    check(f'{name} {width}px: keyboard skip link', page.evaluate("document.activeElement.getAttribute('href') === '#main'"))
                    toc = page.get_by_role('navigation', name='On this page').locator('a').first
                    fragment = toc.get_attribute('href')
                    privacy = page.get_by_role('navigation', name='Documentation navigation').get_by_role('link', name='Privacy', exact=True)
                    if transport == 'intercepted local static files':
                        toc.click()
                        check(f'{name} {width}px: section navigation', page.url.endswith(fragment))
                        privacy.click()
                        check(f'{name} {width}px: related page navigation', page.locator('h1').inner_text() == 'Your data, explained')
                    else:
                        check(f'{name} {width}px: section target present (navigation untested)', page.locator(fragment).count() == 1)
                        check(f'{name} {width}px: related href present (navigation untested)', privacy.get_attribute('href') == '../privacy/')
                    check(f'{name} {width}px: no browser errors', not errors)
                    if name == 'help' and width in (390, 1280):
                        navigate(page, 'help')
                        page.screenshot(path=str(OUT/f'help-{width}.png'), full_page=True)
                    page.close()
            check('only local intercepted resources requested', not unexpected)
        finally:
            browser.close()
    report = {'checks': len(results), 'passed': sum(r['passed'] for r in results),
              'transport': transport, 'native_navigation_tested': transport == 'intercepted local static files', 'results': results}
    (OUT/'content-ui.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f"PASS static content browser checks: {report['passed']}/{report['checks']}")


if __name__ == '__main__':
    run()
