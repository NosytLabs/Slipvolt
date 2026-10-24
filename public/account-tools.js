/* Customer quality-of-life controls. No secrets persist outside this tab. */
'use strict';
function refreshRequestControls() {
  const ceiling=selectedOutputCeiling(),candidateDefault=selectedOutputDefault();
  const effectiveDefault=candidateDefault&&ceiling&&candidateDefault<=ceiling?candidateDefault:null;
  const input = $('output-tokens');
  input.disabled=!ceiling;
  if(ceiling){
    input.max=String(ceiling);
    if(!S.outputBudgetEdited)input.value=effectiveDefault?String(effectiveDefault):'';
    else if(Number(input.value)>ceiling)input.value=String(ceiling);
    $('output-ceiling').textContent=`Service limit ${ceiling.toLocaleString()} tokens; provider acceptance may vary.`;
  }else{
    input.removeAttribute('max');if(!S.outputBudgetEdited)input.value='';
    $('output-ceiling').textContent='Output service limit unavailable.';
  }
  $('policy-default-output').textContent=effectiveDefault?`${effectiveDefault.toLocaleString()} tokens`:'Unknown';
  $('policy-max-output').textContent=ceiling?`${ceiling.toLocaleString()} tokens`:'Unknown';
  const rpm=SlipvoltCore.safeCount(S.status?.limits?.wallet_rpm),concurrency=SlipvoltCore.safeCount(S.status?.limits?.wallet_concurrency);
  if(rpm!==null&&concurrency!==null)$('account-limits').textContent=`${rpm} requests/minute · ${concurrency} concurrent · shared across your keys`;
  else if(S.status)$('account-limits').textContent='Wallet request limits unavailable.';
}
function requestedOutput() {
  const value = Number($('output-tokens').value);
  const maximum = Number($('output-tokens').max);
  if (!Number.isInteger(value) || value < 1 || value > maximum) throw new Error(`Choose an output budget between 1 and ${maximum.toLocaleString()}.`);
  return value;
}
$('output-tokens').addEventListener('input',()=>{S.outputBudgetEdited=true;});
$('output-tokens').addEventListener('change', () => {
  S.outputBudgetEdited=true;
  try { requestedOutput(); renderCode(); } catch (error) { toast(error.message); }
});
$('stop-request').addEventListener('click', () => {
  if(!S.controller)return;
  S.controller.abort();
  $('request-note').textContent = 'Stopping this browser request. Provider charges may still need reconciliation.';
});
$('copy-response').addEventListener('click', async () => {
  if (!$('result').classList.contains('has-output')) return toast('There is no completed response to copy yet.');
  try { await navigator.clipboard.writeText($('result').textContent); toast('Response copied.'); }
  catch { toast('Clipboard unavailable. Select and copy the response text.'); }
});
$('revoke-all-keys').addEventListener('click', async () => {
  if (OFFLINE) return toast('Offline preview. No keys were changed.');
  if (!confirm('Revoke all API keys for this wallet? Existing applications will stop making new calls. In-flight requests may finish.')) return;
  const button=$('revoke-all-keys'),epoch=S.epoch,wallet=S.wallet;if(button.disabled)return;button.disabled=true;
  try {
    const result = await api('/api/keys/revoke-all', {method:'POST'});
    if(S.epoch!==epoch||S.wallet!==wallet)return;clearSecrets(); await refreshMember();
    if(S.epoch===epoch&&S.wallet===wallet)toast(`${result.revoked_count} keys revoked. Usage history was kept.`);
  } catch (error) { if(S.epoch===epoch&&S.wallet===wallet)toast(error.message); }
  finally{if(S.epoch===epoch&&S.wallet===wallet)button.disabled=false;}
});
$('logout-everywhere').addEventListener('click', async () => {
  if (OFFLINE) return toast('Offline preview. No sessions were changed.');
  if(S.authBusy)return toast('Finishing the previous wallet session. Try again in a moment.');
  if (!confirm('Sign out every browser session for this wallet? API keys will remain active.')) return;
  const button=$('logout-everywhere'),epoch=S.epoch,wallet=S.wallet,releaseAuth=beginAuthOperation();if(button.disabled){releaseAuth();return;}button.disabled=true;
  try {
    await api('/api/auth/logout-all', {method:'POST'});
    if(S.epoch!==epoch||S.wallet!==wallet)return;clearAccount(); toast('Signed out all browser sessions. API keys were not revoked.');
  } catch (error) { if(S.epoch===epoch&&S.wallet===wallet)toast(error.message); }
  finally{releaseAuth();if(S.epoch===epoch&&S.wallet===wallet)button.disabled=false;}
});
$('example-language').addEventListener('change', renderCode);
refreshRequestControls();
