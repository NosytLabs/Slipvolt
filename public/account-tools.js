/* Customer quality-of-life controls. No secrets persist outside this tab. */
'use strict';
function refreshRequestControls() {
  const model = S.models.find(item => item.id === S.selected);
  const ceiling = model?.max_completion_tokens || S.status?.limits?.max_output_tokens || 16384;
  const input = $('output-tokens');
  input.max = String(ceiling);
  if (Number(input.value) > ceiling) input.value = String(ceiling);
  $('output-ceiling').textContent = `Maximum ${ceiling.toLocaleString()} · reasoning may consume part of the output budget`;
  if (S.status?.limits) $('account-limits').textContent = `${S.status.limits.wallet_rpm} requests/minute · ${S.status.limits.wallet_concurrency} concurrent · shared across your keys`;
}
function requestedOutput() {
  const value = Number($('output-tokens').value);
  const maximum = Number($('output-tokens').max);
  if (!Number.isInteger(value) || value < 1 || value > maximum) throw new Error(`Choose an output budget between 1 and ${maximum.toLocaleString()}.`);
  return value;
}
$('output-tokens').addEventListener('change', () => {
  try { requestedOutput(); renderCode(); } catch (error) { toast(error.message); }
});
$('stop-request').addEventListener('click', () => {
  S.controller?.abort();
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
  try {
    const result = await api('/api/keys/revoke-all', {method:'POST'});
    clearSecrets(); await refreshMember();
    toast(`${result.revoked_count} keys revoked. Usage history was kept.`);
  } catch (error) { toast(error.message); }
});
$('logout-everywhere').addEventListener('click', async () => {
  if (OFFLINE) return toast('Offline preview. No sessions were changed.');
  if (!confirm('Sign out every browser session for this wallet? API keys will remain active.')) return;
  try {
    await api('/api/auth/logout-all', {method:'POST'});
    clearAccount(); toast('Signed out all browser sessions. API keys were not revoked.');
  } catch (error) { toast(error.message); }
});
$('example-language').addEventListener('change', renderCode);
refreshRequestControls();
