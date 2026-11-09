"""Cross-pane cancellation must end the visible operation without inventing rollback."""
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from scripts.browser_support import launch_chromium
from test_treasury_burn import MINT, OWNER

PUBLIC = Path(__file__).resolve().parents[1] / 'public/admin/burns'


@pytest.fixture
def page():
    html = (PUBLIC / 'index.html').read_text()
    for name in ('account-view.js', 'app.js'):
        html = html.replace(f'<script src="{name}" defer></script>',
                            '<script>' + (PUBLIC / name).read_text() + '</script>')
    with sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_content(html)
        page.evaluate('''([mint,owner]) => {
          window.calls=[];window.pending=[];
          window.fetch=(url,options) => {
            calls.push({url,options});
            if(url==='/api/admin/treasury')return Promise.resolve(new Response(JSON.stringify({
              mint,treasury_owner:owner,decimals:6,planning_enabled:true,signing_enabled:false
            }),{status:200}));
            // Ignore abort: a queued server reply must still not reclaim the UI.
            return new Promise(resolve=>pending.push(data=>resolve(new Response(
              JSON.stringify(data),{status:200}))));
          };
        }''', [MINT, OWNER])
        page.locator('#operator-key').fill('adm_fixture')
        page.locator('#unlock').click()
        expect(page.locator('#load-accounts')).to_be_enabled()
        yield page
        browser.close()
        assert not errors


def test_editing_another_pane_ends_cancelled_account_lookup(page):
    page.locator('#load-accounts').click()
    expect(page.locator('#accounts-status')).to_have_text('Checking…')
    page.locator('#claim-signature').fill('1' * 64)
    expect(page.locator('#accounts-status')).to_contain_text('Check stopped')
    expect(page.locator('#load-accounts')).to_be_enabled()
    assert page.evaluate('calls[1].options.signal.aborted')
    # A late malformed result would otherwise run account normalization.
    page.evaluate('pending[0]({})')
    expect(page.locator('#accounts-status')).to_contain_text('Check stopped')
    expect(page.locator('#account-select')).to_be_disabled()


@pytest.mark.parametrize('button,signature,output,other', [
    ('verify-receipt', 'signature', 'receipt-status', 'claim-signature'),
    ('verify-creator-claim', 'claim-signature', 'claim-status', 'signature'),
])
def test_cancelled_evidence_write_warns_and_cannot_release_newer_operation(
        page, button, signature, output, other):
    page.locator('#' + signature).fill('1' * 64)
    page.locator('#' + button).click()
    expect(page.locator('#' + output)).to_have_text('Checking…')
    page.locator('#' + other).fill('2' * 64)
    expect(page.locator('#' + output)).to_contain_text('may already have recorded evidence')
    expect(page.locator('#' + output)).to_contain_text('check recorded receipts or claims')
    assert page.evaluate('calls[1].options.signal.aborted')
    assert page.evaluate('calls[1].options.method') == 'POST'
    # The stopped write's finally must not re-enable controls for a newer read.
    page.locator('#load-accounts').click()
    page.evaluate("pending[0]({recorded:true,transactions_sent:0,receipt:{signature:'1'.repeat(64)}})")
    expect(page.locator('#load-accounts')).to_be_disabled()
    expect(page.locator('#accounts-status')).to_have_text('Checking…')
    expect(page.locator('#' + output)).to_contain_text('may already have recorded evidence')
    assert page.evaluate('calls.length') == 3


def test_editing_pending_burn_signature_keeps_reconciliation_guidance(page):
    page.locator('#signature').fill('1' * 64)
    page.locator('#verify-receipt').click()
    page.locator('#signature').fill('2' * 64)
    expect(page.locator('#receipt-status')).to_contain_text('check recorded burns before retrying')
    page.evaluate("pending[0]({recorded:true,transactions_sent:0,receipt:{signature:'1'.repeat(64)}})")
    expect(page.locator('#receipt-status')).to_contain_text('check recorded burns before retrying')
    assert page.evaluate('calls[1].options.signal.aborted')


def test_timeout_cannot_publish_a_queued_successful_receipt(page):
    page.evaluate('''() => {
      const schedule=window.setTimeout;
      window.setTimeout=(callback,delay,...args)=>{
        if(delay===25000)window.expireOperation=callback;
        return schedule(callback,delay,...args);
      };
    }''')
    page.locator('#signature').fill('1' * 64)
    page.locator('#verify-receipt').click()
    page.evaluate('expireOperation()')
    assert page.evaluate('calls[1].options.signal.aborted')
    page.evaluate("pending[0]({recorded:true,transactions_sent:0,receipt:{signature:'1'.repeat(64)}})")
    expect(page.locator('#receipt-status')).to_contain_text('Request stopped or timed out')
    expect(page.locator('#receipt-status')).to_contain_text('Check recorded receipts or claims before retrying')
    expect(page.locator('#verify-receipt')).to_be_enabled()
