'use strict';
// Server-only credentials are never returned by these endpoints.
async function loadConnections(parent = () => true) {
  const isCurrent = nextRefresh('connections', parent);
  const target=document.getElementById('connection-list');
  if (!target || !key) return;
  try {
    const d=await api('/api/admin/connections');
    if (!isCurrent()) return;
    const labels=[['Solana RPC',d.solana_rpc?.configured,'Server side · '+d.solana_rpc?.rps_budget+' requests/s budget'],
      ['Solana WebSocket',d.solana_websocket?.configured,'Configured only; no subscription running'],
      ['OpenBroker',d.openbroker?.configured,'Private inference credential'],
      ['Metis / Jupiter',d.metis?.configured,'Read-only quotes; no swap execution'],
      ['Project mint',Boolean(d.token?.mint),'No token launch is implied by configuration']];
    target.replaceChildren();
    for (const [label,ready,note] of labels) {
      const row=document.createElement('div');row.className='connection-row';
      const name=document.createElement('strong');name.textContent=label;
      const status=document.createElement('span');status.className=ready?'good':'muted';status.textContent=ready?'Configured':'Not configured';
      const sub=document.createElement('small');sub.textContent=note;
      row.append(name,status,sub);target.append(row);
    }
    document.getElementById('connections-note').textContent='Configuration is not a successful connectivity test. 0x execution, staking and customer checkout remain off.';
  } catch { if (isCurrent()) target.textContent='Connection settings unavailable. Unlock the console and retry.'; }
}
function showReadOnlyResult(id,result) {
  document.getElementById(id).textContent=typeof result==='string'?result:JSON.stringify(result,null,2);
}
async function runConnectionCheck(button,path,message) {
  if(button.disabled)return;
  const isCurrent=nextRefresh('connections-result');
  button.disabled=true;showReadOnlyResult('connections-result',message);
  try{
    const result=await api(path,{method:'POST'});
    if(isCurrent())showReadOnlyResult('connections-result',result);
  }catch(e){if(isCurrent())showReadOnlyResult('connections-result',e.message);}
  finally{button.disabled=false;}
}
const checkButton=document.getElementById('connections-check'),priorityButton=document.getElementById('priority-check');
checkButton.addEventListener('click',()=>runConnectionCheck(checkButton,'/api/admin/connections/check','Checking the configured RPC…'));
priorityButton.addEventListener('click',()=>runConnectionCheck(priorityButton,'/api/admin/connections/priority-fee','Checking priority fee estimates…'));
let quoteGeneration=0;
const quoteForm=document.getElementById('quote-form');
quoteForm.addEventListener('input',()=>{quoteGeneration++;showReadOnlyResult('quote-result','Inputs changed. Request a fresh quote.');});
quoteForm.addEventListener('submit',async event=>{
  event.preventDefault();const generation=++quoteGeneration;
  const button=quoteForm.querySelector('button');button.disabled=true;
  showReadOnlyResult('quote-result','Requesting an indicative quote…');
  try {
    const d=await api('/api/admin/swap/quote',{method:'POST',body:JSON.stringify({
      asset:document.getElementById('quote-asset').value,
      amount:document.getElementById('quote-amount').value,
      slippage_bps:50})});
    if(generation!==quoteGeneration)return;
    showReadOnlyResult('quote-result',`${d.input_amount} ${d.asset} → ${d.expected_usdc} USDC\nMinimum at 0.5% slippage: ${d.minimum_usdc} USDC\n${d.notice}`);
    setTimeout(()=>{if(generation===quoteGeneration)showReadOnlyResult('quote-result','Quote expired. Request a fresh quote.');},Math.max(0,d.local_expires_at*1000-Date.now()));
  }catch(e){if(generation===quoteGeneration)showReadOnlyResult('quote-result',e.message);}
  finally{button.disabled=false;}
});
