"""Key mutations retain ownership across refreshes and account changes."""
import pytest
from playwright.sync_api import expect

from test_ui_state_transitions import load_holder, page  # noqa: F401


def load_member(page):
    load_holder(page)
    page.evaluate('''async () => {
      window.memberWallet='11111111111111111111111111111111';
      window.memberEligible=true;
      window.memberKeys=[{id:'existing',name:'Existing',prefix:'sv_existing',revoked:false}];
      window.keyWrites=[];
      window.confirm=()=>true;
      S.wallet=memberWallet;
      api=(path,options={})=>{
        if(path==='/api/member-key'||options.method==='DELETE'||path==='/api/keys/revoke-all'){
          return new Promise((resolve,reject)=>keyWrites.push({path,resolve,reject,wallet:S.wallet}));
        }
        if(path==='/api/account')return Promise.resolve({wallet:memberWallet});
        if(path==='/api/membership')return Promise.resolve({eligibility:{eligible:memberEligible},
          funded_allowance_mode:true,daily_tokens:1000,used_tokens:0,reserved_tokens:0,
          remaining_tokens:1000,history:[],pool:{}});
        if(path==='/api/usage/summary')return Promise.resolve({});
        if(path==='/api/keys')return Promise.resolve({data:memberKeys});
        throw Error('Unexpected fixture request: '+path);
      };
      await refreshMember();
    }''')


def test_refresh_cannot_unlock_pending_creation_or_allow_competing_key_writes(page):
    load_member(page)
    page.locator('#create-key').click()
    page.evaluate('refreshMember()')
    expect(page.locator('#create-key')).to_be_disabled()
    expect(page.locator('#revoke-all-keys')).to_be_disabled()
    expect(page.locator('#key-list button')).to_be_disabled()
    # Controls are a projection, not the authority: synthetic events must also fail.
    page.evaluate('''() => {
      $('create-key').dispatchEvent(new Event('click'));
      $('revoke-all-keys').dispatchEvent(new Event('click'));
      S.revoke='existing';$('confirm-revoke').dispatchEvent(new Event('click'));
    }''')
    assert page.evaluate('keyWrites.map(write=>write.path)') == ['/api/member-key']
    page.evaluate("keyWrites[0].resolve({id:'new',key:'sv_'+'a'.repeat(43)})")
    expect(page.locator('#created-key')).to_have_value('sv_' + 'a' * 43)
    expect(page.locator('#create-key')).to_be_enabled()


@pytest.mark.parametrize('operation', ['revoke', 'revoke-all'])
def test_refresh_cannot_admit_creation_during_revocation(page, operation):
    load_member(page)
    page.evaluate('''operation => {
      if(operation==='revoke'){
        document.querySelector('#key-list button').click();$('confirm-revoke').click();
      }else $('revoke-all-keys').click();
    }''', operation)
    page.evaluate('refreshMember()')
    expect(page.locator('#create-key')).to_be_disabled()
    page.evaluate("$('create-key').dispatchEvent(new Event('click'))")
    assert page.evaluate('keyWrites.length') == 1
    page.evaluate('''() => {memberKeys=[];keyWrites[0].resolve({revoked_count:1});}''')
    expect(page.locator('#create-key')).to_be_enabled()
    expect(page.locator('#new-key')).to_be_hidden()


def test_failed_creation_does_not_restore_obsolete_eligibility(page):
    load_member(page)
    page.locator('#create-key').click()
    page.evaluate('''async () => {memberEligible=false;await refreshMember();}''')
    page.evaluate("keyWrites[0].reject(Error('Creation failed'))")
    page.wait_for_function('S.keyOperation===null')
    expect(page.locator('#create-key')).to_be_disabled()
    expect(page.locator('#revoke-all-keys')).to_be_enabled()
    expect(page.locator('#new-key')).to_be_hidden()


@pytest.mark.parametrize('late_error', [False, True])
def test_former_accounts_response_cannot_release_or_replace_current_key_operation(page, late_error):
    load_member(page)
    page.locator('#create-key').click()
    page.evaluate('''async () => {
      clearAccount();memberWallet='22222222222222222222222222222222';S.wallet=memberWallet;
      await refreshMember();$('create-key').click();
    }''')
    page.evaluate('''lateError => {
      if(lateError)keyWrites[0].reject(Error('Old account failure'));
      else keyWrites[0].resolve({id:'old',key:'sv_'+'o'.repeat(43)});
    }''', late_error)
    expect(page.locator('#create-key')).to_be_disabled()
    expect(page.locator('#created-key')).to_have_value('')
    assert page.evaluate('keyWrites.map(write=>write.wallet)') == [
        '11111111111111111111111111111111', '22222222222222222222222222222222']
    page.evaluate("keyWrites[1].resolve({id:'current',key:'sv_'+'c'.repeat(43)})")
    expect(page.locator('#created-key')).to_have_value('sv_' + 'c' * 43)
    expect(page.locator('#create-key')).to_be_enabled()
