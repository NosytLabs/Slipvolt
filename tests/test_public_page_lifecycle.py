"""Public evidence reads belong to the visible page and latest refresh."""
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_ui_state_transitions import page  # noqa: F401

PUBLIC = Path(__file__).resolve().parents[1] / 'public'


def load_public_page(page, kind):
    html = re.sub(r'<script\b[^>]*>.*?</script>', '',
                  (PUBLIC / kind / 'index.html').read_text(), flags=re.S)
    page.set_content(html)
    page.evaluate('''() => {
      window.reads=[];window.deadlines=[];
      const originalTimeout=window.setTimeout;
      window.setTimeout=(callback,delay,...args)=>{
        if(delay===12000||delay===22000)deadlines.push(callback);
        return originalTimeout(callback,delay,...args);
      };
      // Ignore abort deliberately: queued responses must also lose ownership.
      fetch=(path,options)=>new Promise((resolve,reject)=>reads.push({path,options,resolve,reject}));
      window.settleReads=(start,end,version=1,fail=false)=>{
        for(const read of reads.slice(start,end)){
          if(fail){read.reject(Error('Fixture unavailable'));continue;}
          let value;
          if(read.path==='/api/token')value={status:'available',mint:'1'.repeat(32),checked_at:1700000000,
            mint_state:{mint:'1'.repeat(32),supply_raw:String(version*1000),decimals:0,slot:version,
              mint_authority:null,freeze_authority:null},
            burns:{receipt_count:0,burned_raw:'0',recent:[]}};
          else if(read.path==='/api/status')value={holder_gate_configured:true,provider_configured:true};
          else if(read.path==='/api/models')value={live:true,data:[{id:'fixture-model-'+version}]};
          else if(read.path==='/api/treasury')value={};
          else value={totals:{requests:version,tokens:version*10}};
          read.resolve(new Response(JSON.stringify(value),{headers:{'content-type':'application/json'}}));
        }
      };
    }''')
    page.add_script_tag(content=(PUBLIC / kind / ('token.js' if kind == 'token' else 'app.js')).read_text())
    return 1 if kind == 'token' else 4


def refresh_button(page, kind):
    return page.locator('#refresh' if kind == 'token' else '#status-refresh')


def assert_current_evidence(page, kind, version):
    if kind == 'token':
        expect(page.locator('#supply')).to_have_text(f'{version},000')
        expect(page.locator('#state')).to_contain_text('Finalized mint snapshot')
    else:
        expect(page.locator('#network-value')).to_have_text(f'{version} requests')
        expect(page.locator('#status-models')).to_contain_text(f'fixture-model-{version}')


@pytest.mark.parametrize('kind', ['token', 'status'])
def test_pagehide_invalidates_reads_and_restored_page_rechecks(page, kind):
    count = load_public_page(page, kind)
    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))")
    assert page.evaluate('reads.every(read=>read.options.signal.aborted)')
    page.evaluate('count=>settleReads(0,count)', count)
    expect(refresh_button(page, kind)).to_be_enabled()
    if kind == 'token':
        expect(page.locator('#supply')).to_have_text('Unavailable')
        expect(page.locator('#state')).to_contain_text('has not been checked')
    else:
        expect(page.locator('#service-state')).to_have_text('Not checked')
        expect(page.locator('#status-models')).to_be_empty()
    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:false}))")
    assert page.evaluate('reads.length') == count
    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
    assert page.evaluate('reads.length') == 2 * count
    expect(refresh_button(page, kind)).to_be_disabled()
    page.evaluate('count=>settleReads(count,2*count,2)', count)
    assert_current_evidence(page, kind, 2)
    expect(refresh_button(page, kind)).to_be_enabled()


@pytest.mark.parametrize('kind', ['token', 'status'])
@pytest.mark.parametrize('old_failure', [False, True])
def test_replaced_read_cannot_render_or_unlock_new_refresh(page, kind, old_failure):
    count = load_public_page(page, kind)
    refresh_button(page, kind).dispatch_event('click')
    assert page.evaluate('count=>reads.slice(0,count).every(read=>read.options.signal.aborted)', count)
    page.evaluate('args=>settleReads(0,args.count,1,args.failure)', {'count': count, 'failure': old_failure})
    expect(refresh_button(page, kind)).to_be_disabled()
    if kind == 'token':
        expect(page.locator('#state')).to_contain_text('Checking')
        expect(page.locator('#supply')).to_have_text('Unavailable')
    else:
        expect(page.locator('#service-state')).to_have_text('Checking…')
        expect(page.locator('#status-models')).to_be_empty()
    page.evaluate('count=>settleReads(count,2*count,2)', count)
    assert_current_evidence(page, kind, 2)
    expect(refresh_button(page, kind)).to_be_enabled()


@pytest.mark.parametrize('kind', ['token', 'status'])
def test_response_after_timeout_cannot_be_presented_as_success(page, kind):
    count = load_public_page(page, kind)
    page.evaluate('deadlines[0]()')
    assert page.evaluate('reads.every(read=>read.options.signal.aborted)')
    page.evaluate('count=>settleReads(0,count)', count)
    expect(refresh_button(page, kind)).to_be_enabled()
    if kind == 'token':
        expect(page.locator('#supply')).to_have_text('Unavailable')
        expect(page.locator('#state')).to_contain_text('Could not load')
    else:
        expect(page.locator('#service-state')).to_have_text('Unavailable')
        expect(page.locator('#network-value')).to_have_text('Unavailable')
        expect(page.locator('#status-models')).to_be_empty()


@pytest.mark.parametrize('kind', ['token', 'status'])
def test_new_refresh_clears_old_evidence_and_failure_keeps_values_unknown(page, kind):
    count = load_public_page(page, kind)
    page.evaluate('count=>settleReads(0,count)', count)
    assert_current_evidence(page, kind, 1)
    refresh_button(page, kind).click()
    if kind == 'token':
        expect(page.locator('#supply')).to_have_text('Unavailable')
        expect(page.locator('#receipt-count')).to_have_text('Unavailable')
    else:
        expect(page.locator('#network-value')).to_have_text('Checking…')
        expect(page.locator('#status-models')).to_be_empty()
    page.evaluate('count=>settleReads(count,2*count,2,true)', count)
    expect(refresh_button(page, kind)).to_be_enabled()
    if kind == 'token':
        expect(page.locator('#burned')).to_have_text('Unavailable')
        expect(page.locator('#receipt-count')).to_have_text('Unavailable')
    else:
        for field in ('reserve-value', 'provider-value', 'network-value'):
            expect(page.locator('#' + field)).to_have_text('Unavailable')


def test_status_timeout_preserves_sources_completed_before_deadline(page):
    load_public_page(page, 'status')
    page.evaluate('settleReads(0,1)')
    page.evaluate('deadlines[0]();settleReads(1,4)')
    expect(refresh_button(page, 'status')).to_be_enabled()
    expect(page.locator('#service-state')).to_contain_text('Configured')
    expect(page.locator('#network-value')).to_have_text('Unavailable')
    expect(page.locator('#status-observed')).to_contain_text('3 source(s) unavailable')
