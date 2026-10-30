"""Exercise the offline holder-economics planner; no live APIs or wallet calls."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from browser_support import launch_chromium

ROOT = Path(__file__).resolve().parents[1]


def run():
    checked = 0
    with sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        for width in (320, 390, 1280):
            page = browser.new_page(viewport={'width': width, 'height': 960})
            errors, unexpected = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))

            def route(request):
                name = request.request.url.removeprefix('http://economics.test/')
                if name not in ('holder-economics.html', 'holder-economics.js'):
                    unexpected.append(request.request.url)
                    return request.abort()
                return request.fulfill(
                    body=(ROOT / 'operator' / name).read_text(),
                    content_type='text/html' if name.endswith('.html') else 'text/javascript')

            page.route('**/*', route)
            page.goto('http://economics.test/holder-economics.html')
            assert page.locator('#surplus').inner_text() == '$377.50'
            assert page.locator('#zero-volume').inner_text() == '$522.50'
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            checked += 3

            # A derived stress case cannot invalidate a valid main scenario.
            page.locator('#gnkUsd').fill('500001')
            assert page.locator('#error').is_hidden()
            assert page.locator('#double-price').inner_text() == 'Outside planner range'
            assert page.locator('#export').is_enabled()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            checked += 4
            page.locator('#reset').click()

            # Large valid cash figures must still fit a narrow viewport.
            page.locator('#dailyTradingVolumeUsd').fill('1000000000')
            page.locator('#creatorFeeBps').fill('10000')
            assert page.locator('#error').is_hidden()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            checked += 2
            page.locator('#reset').click()

            page.locator('#dailyTradingVolumeUsd').fill('0')
            assert page.locator('#surplus').inner_text() == '$0.00'
            assert page.locator('#breakdown').get_by_text('$0.00', exact=True).count() >= 4
            checked += 2

            page.locator('#activeHolders').fill('-1')
            assert page.locator('#error').is_visible()
            assert page.locator('#surplus').inner_text() == '—'
            assert page.locator('#breakdown').inner_text() == ''
            assert page.locator('#export').is_disabled()
            checked += 4

            page.locator('#reset').click()
            assert page.locator('#error').is_hidden()
            with page.expect_download() as download_info:
                page.locator('#export').click()
            exported = json.loads(Path(download_info.value.path()).read_text())
            assert exported['result']['surplusUsd'] == 377.5
            assert exported['result']['payoutAuthorized'] is False
            assert exported['result']['transactionsPrepared'] == 0
            assert exported['zeroTrading']['fundingGapUsd'] == 522.5
            assert exported['monthlyBasisDays'] == 30
            checked += 6

            if width in (390, 1280):
                evidence = ROOT / 'evidence-current'
                evidence.mkdir(exist_ok=True)
                page.screenshot(path=str(evidence / f'holder-economics-{width}.png'), full_page=True)
            assert not errors, errors
            assert not unexpected, unexpected
            checked += 2
            page.close()
        browser.close()
    print(f'Holder economics browser: {checked}/{checked} passed; offline fixture only.')


if __name__ == '__main__':
    run()
