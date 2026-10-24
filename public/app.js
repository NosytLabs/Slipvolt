/* One-page holder access. No upstream credential, persistent browser storage, or simulated usage. */
'use strict';
const $=id=>document.getElementById(id),C=globalThis.SlipvoltCore;
const OFFLINE=document.documentElement.dataset.preview==='offline';
const snapshot=[
  {id:'MiniMaxAI/MiniMax-M2.7',name:'MiniMax M2.7',label:'Coding & everyday tasks',mark:'M / 01'},
  {id:'deepseek-ai/DeepSeek-V4-Flash-0731',name:'DeepSeek V4 Flash',label:'Reasoning & generation',mark:'D / 02'},
  {id:'zai-org/GLM-5.3-Flash',name:'GLM 5.3 Flash',label:'General-purpose AI',mark:'G / 03'}
];
const S={models:snapshot,selected:snapshot[0].id,status:null,wallet:null,provider:null,key:'',epoch:0,busy:false,authBusy:false,controller:null,revoke:null,handlers:null};
let toastTimer;

function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,7500);}
const compact=value=>Number.isFinite(Number(value))?new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:1}).format(Number(value)):'Unavailable';
const whole=value=>Number.isFinite(Number(value))?new Intl.NumberFormat('en').format(Number(value)):'Unavailable';
function gnk(raw){try{const n=BigInt(raw),whole=n/1000000000n,frac=(n%1000000000n).toString().padStart(9,'0').replace(/0+$/,'');return whole.toLocaleString('en')+(frac?'.'+frac:'');}catch{return 'Unavailable';}}
function rawTokens(raw,decimals){try{const n=BigInt(raw),scale=10n**BigInt(decimals);return (n/scale).toLocaleString('en')+(n%scale?'.'+(n%scale).toString().padStart(decimals,'0').replace(/0+$/,''):'');}catch{return 'Set at launch';}}
function safeInteger(value){return Number.isSafeInteger(value)&&value>=0?value:null;}
async function api(path,options={}){if(OFFLINE)throw Error('This is the offline preview. Run the included server to connect your wallet.');const r=await fetch(path,{...options,credentials:'same-origin',headers:{...(options.body?{'Content-Type':'application/json'}:{}),...options.headers}});return C.readApiResponse(r);}
async function copy(value){if(!value)return toast('Nothing to copy yet.');try{await navigator.clipboard.writeText(value);toast('Copied.');}catch{toast('Clipboard unavailable here. Select the text and copy it manually.');}}

function selectModel(id){
  S.selected=id;
  for(const button of document.querySelectorAll('.model-tab'))button.setAttribute('aria-pressed',button.dataset.model===id?'true':'false');
  $('selected-name').textContent=S.models.find(model=>model.id===id)?.name||id;
  if(typeof refreshRequestControls==='function')refreshRequestControls();
  renderCode();
}

function modelAvailability(model){
  if(model.availability==='unavailable'||model.routable===false)return 'temporarily unavailable';
  if(model.readiness==='verified'||model.inference_tested===true)return 'available';
  if(model.availability==='healthy')return 'catalog healthy';
  if(model.availability==='degraded')return 'catalog degraded';
  if(model.availability==='listed')return 'listed in catalog';
  return model.availability||'availability unverified';
}

function renderModels(){
  const list=$('model-list');list.replaceChildren();
  for(const model of S.models){
    const button=document.createElement('button');
    const unavailable=model.availability==='unavailable'||model.routable===false;
    const context=safeInteger(model.context_length);
    const output=safeInteger(model.max_completion_tokens);
    button.className='model-tab'+(unavailable?' model-unavailable':'');
    button.dataset.model=model.id;
    button.setAttribute('aria-pressed',model.id===S.selected?'true':'false');
    const discoveredContext=safeInteger(model.discovered_context_length),discoveredOutput=safeInteger(model.discovered_max_completion_tokens);
    const discovered=model.discovery_limits_status==='reported'||model.discovery_limits_status==='partial'?'discovered metadata '+(discoveredContext?compact(discoveredContext)+' context':'context unknown')+' · '+(discoveredOutput?compact(discoveredOutput)+' output':'output unknown'):'discovered limits unknown';
    button.title=discovered+'. OpenBroker route limits are unverified.';
    button.innerHTML='<span class="model-mark">'+C.escape(model.mark||'AI')+'</span><strong>'+C.escape(model.name||model.id)+'</strong><small>'+C.escape(model.label||'Gonka model')+'</small><small class="model-limits">'+C.escape(context?'context service limit '+compact(context):'context limit unavailable')+'<br>'+C.escape(output?'output service limit '+compact(output):'output limit unavailable')+'</small><small class="model-health">'+C.escape(modelAvailability(model))+'</small>';
    button.addEventListener('click',()=>{if(unavailable)return toast('This model is currently unavailable. Choose another model.');selectModel(model.id);});
    list.append(button);
  }
  if(!S.models.some(model=>model.id===S.selected&&model.availability!=='unavailable'&&model.routable!==false)&&S.models.length){
    const available=S.models.find(model=>model.availability!=='unavailable'&&model.routable!==false);
    S.selected=(available||S.models[0]).id;
  }
  selectModel(S.selected);
}

function renderCode(){
  const base=OFFLINE?'https://YOUR_HOST/v1':location.origin+'/v1';
  const budget=Number($('output-tokens')?.value)||4096;
  try{$('api-code').textContent=globalThis.SlipvoltExamples.example($('example-language')?.value||'curl',base,S.selected,budget);}catch{}
}

function tab(name){for(const value of ['chat','api']){$('tab-'+value).setAttribute('aria-selected',String(name===value));$(value+'-panel').hidden=name!==value;}}
for(const value of ['chat','api']){
  $('tab-'+value).addEventListener('click',()=>tab(value));
  $('tab-'+value).addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();const next=value==='chat'?'api':'chat';tab(next);$('tab-'+next).focus();}});
}
$('copy-code').addEventListener('click',()=>copy($('api-code').textContent));
for(const button of document.querySelectorAll('dialog .close'))button.addEventListener('click',()=>button.closest('dialog').close());

function clearUsage(message='Connect to load your private usage'){
  $('usage-dashboard').hidden=true;
  $('usage-locked').hidden=false;
  $('usage-source').textContent=message;
  for(const id of ['usage-used','usage-total','usage-requests','usage-cost'])$(id).textContent='—';
  $('usage-reserved').textContent='— reserved now';
  $('usage-breakdown').textContent='All-time reported breakdown: unavailable.';
  $('usage-reset').textContent='Reset time unavailable';
  $('usage-models').replaceChildren();
  $('usage-history').replaceChildren();
}

function usageBreakdown(row){
  const parts=[];
  const fields=[['prompt_tokens','input'],['completion_tokens','output'],['cached_input_tokens','cached input'],['reasoning_tokens','reasoning']];
  for(const [field,label] of fields){const value=safeInteger(row[field]);if(value!==null)parts.push(whole(value)+' '+label);}
  if(!parts.length){const tokens=safeInteger(row.tokens);if(tokens!==null)parts.push(whole(tokens)+' total tokens');}
  if(row.usage_status==='unreported')parts.push('provider split unreported');
  return parts;
}

function costSourceLabel(source){
  if(typeof source!=='string'||!source)return 'Recorded allocation';
  if(source.startsWith('devshard_'))return 'Provider record';
  if(source==='conservative_budget_estimate'||source==='budget_estimate')return 'Budget estimate';
  if(source==='operator_verified'||source==='operator')return 'Operator verified';
  if(source==='provider_rejected')return 'Provider rejected · no charge';
  return 'Recorded allocation';
}

function renderUsage(membership,totals){
  const rows=Array.isArray(membership.history)?membership.history:[];
  const summary=C.summarizeUsage(rows);
  $('usage-locked').hidden=true;$('usage-dashboard').hidden=false;
  $('usage-source').textContent='Private wallet records · daily and all-time totals';
  $('usage-used').textContent=whole(membership.used_tokens);
  $('usage-reserved').textContent=whole(membership.reserved_tokens)+' reserved now';
  $('usage-total').textContent=whole(totals.total_tokens);
  $('usage-requests').textContent=whole(totals.requests);
  $('usage-cost').textContent=safeInteger(totals.cost_ngonka)!==null?gnk(totals.cost_ngonka)+' GNK':'Unavailable';
  const exact=[['prompt_tokens','input'],['completion_tokens','output']].filter(([field])=>safeInteger(totals[field])!==null).map(([field,label])=>whole(totals[field])+' '+label);
  const reported=safeInteger(totals.usage_reported_requests),unreported=safeInteger(totals.usage_unreported_requests);
  for(const [field,label,coverageField] of [['cached_input_tokens','cached input','cached_usage_reported_requests'],['reasoning_tokens','reasoning','reasoning_usage_reported_requests']]){
    const value=safeInteger(totals[field]),coverage=safeInteger(totals[coverageField]);
    if(value!==null)exact.push(whole(value)+' '+label+(coverage!==null?' · reported on '+whole(coverage)+' request'+(coverage===1?'':'s'):''));
  }
  $('usage-breakdown').textContent='All-time reported breakdown: '+(exact.length?exact.join(' · ')+(unreported?' · '+whole(unreported)+' request'+(unreported===1?'':'s')+' lacked an exact provider split':''):reported===0&&unreported?'exact input/output split unavailable for '+whole(unreported)+' recorded request'+(unreported===1?'':'s')+'.':'unavailable.');
  const reset=safeInteger(membership.resets_at);
  $('usage-reset').textContent=reset?'Resets '+new Date(reset*1000).toLocaleString([],{timeZone:'UTC',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short'}):'Reset time unavailable';

  const models=$('usage-models');models.replaceChildren();
  const largest=summary.models[0]?.tokens||0;
  if(!summary.models.length){const p=document.createElement('p');p.className='empty-copy';p.textContent='No measured model tokens in the recent records.';models.append(p);}
  for(const item of summary.models){
    const row=document.createElement('div');row.className='model-usage-row';
    const meta=document.createElement('div');meta.className='model-usage-meta';
    const name=document.createElement('strong');name.textContent=S.models.find(model=>model.id===item.model)?.name||item.model;
    const value=document.createElement('span');value.textContent=whole(item.tokens)+' tokens';meta.append(name,value);
    const track=document.createElement('div');track.className='usage-track';track.setAttribute('aria-hidden','true');
    const fill=document.createElement('span');fill.style.width=(largest?Math.max(2,item.tokens/largest*100):0)+'%';track.append(fill);row.append(meta,track);models.append(row);
  }

  const history=$('usage-history');history.replaceChildren();
  if(!rows.length){const p=document.createElement('p');p.className='empty-copy';p.textContent='No requests recorded for this wallet yet.';history.append(p);}
  for(const item of rows){
    const row=document.createElement('div');row.className='history-row';
    const name=document.createElement('div');name.className='history-model';name.textContent=S.models.find(model=>model.id===item.model)?.name||item.model||'Unknown model';
    const state=document.createElement('span');state.className='history-state';state.dataset.state=typeof item.state==='string'?item.state:'unknown';state.textContent=state.dataset.state.replaceAll('_',' ');
    const breakdown=document.createElement('div');breakdown.className='history-breakdown';
    const bits=usageBreakdown(item);if(!bits.length)bits.push('Token breakdown unavailable');
    const cost=safeInteger(item.cost_ngonka);if(cost!==null&&item.state==='settled')bits.push(gnk(cost)+' GNK · '+costSourceLabel(item.cost_source));
    for(const bit of bits){const span=document.createElement('span');span.textContent=bit;breakdown.append(span);}
    const time=document.createElement('time');time.className='history-time';
    const created=Number(item.created);if(Number.isFinite(created)&&created>0){const date=new Date(created*1000);time.dateTime=date.toISOString();time.textContent=date.toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});}else time.textContent='Time unavailable';
    row.append(name,state,breakdown,time);history.append(row);
  }
}

function clearSecrets(){
  document.dispatchEvent(new Event('slipvolt:account-cleared'));
  $('request-id').textContent='';S.key='';$('created-key').value='';$('created-key').type='password';$('show-key').textContent='Show';$('existing-key').value='';$('new-key').hidden=true;$('prompt').value='';$('result').textContent='Your model’s response appears here.';$('result').classList.remove('has-output');S.controller?.abort();S.controller=null;
}
function clearAccount(){
  S.epoch++;S.wallet=null;clearSecrets();clearUsage();$('main-connect').hidden=false;$('member-actions').hidden=true;$('keys-detail').hidden=true;$('access-pill').textContent='Not connected';$('access-title').textContent='Your wallet is your login.';$('access-description').textContent='No email or checkout. Sign a login message to prove the wallet is yours.';$('request-note').textContent='Create a key above to start.';for(const button of document.querySelectorAll('.connect'))button.textContent='Connect wallet ↗';
}
function detachProvider(){if(S.provider?.removeListener&&S.handlers){S.provider.removeListener('accountChanged',S.handlers.change);S.provider.removeListener('disconnect',S.handlers.disconnect);}S.provider=null;S.handlers=null;}
async function invalidate(message){clearAccount();try{await api('/api/auth/logout',{method:'POST'});}catch{}toast(message);}
function bindProvider(provider){detachProvider();S.provider=provider;S.handlers={change:key=>{if(S.wallet&&key?.toString()!==S.wallet)invalidate('Wallet changed. Sign in again.');},disconnect:()=>{if(S.wallet)invalidate('Wallet disconnected.');}};provider.on?.('accountChanged',S.handlers.change);provider.on?.('disconnect',S.handlers.disconnect);}
function walletCandidates(){return [['Phantom',window.phantom?.solana||window.solana],['Solflare',window.solflare]].filter(([,provider],index,all)=>provider?.connect&&provider?.signMessage&&all.findIndex(([,other])=>other===provider)===index);}
function showWallets(){
  if(S.wallet)return toast('You are signed in. Get or manage your API keys in the access card.');
  $('wallet-options').replaceChildren();$('wallet-message').textContent='';$('wallet-dialog').showModal();
  if(OFFLINE){$('wallet-message').textContent='Offline preview. Start the included backend to sign in and create a real key. No key has been generated.';return;}
  const candidates=walletCandidates();
  if(!candidates.length)$('wallet-message').textContent='Open this site in a supported wallet browser, or enable Phantom or Solflare in your desktop browser.';
  for(const [name,provider] of candidates){const button=document.createElement('button');button.className='wallet-option';button.textContent=name+' ↗';button.addEventListener('click',()=>connect(provider,button));$('wallet-options').append(button);}
}
for(const button of document.querySelectorAll('.connect'))button.addEventListener('click',showWallets);

async function connect(provider,button){
  if(S.authBusy)return;S.authBusy=true;button.disabled=true;const epoch=S.epoch;
  try{
    const connected=await provider.connect(),wallet=(connected?.publicKey||provider.publicKey)?.toString();
    if(typeof wallet!=='string'||!/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(wallet))throw Error('Wallet did not provide a valid Solana address.');
    const challenge=await api('/api/auth/challenge',{method:'POST',body:JSON.stringify({wallet})});
    const signed=await provider.signMessage(new TextEncoder().encode(challenge.message),'utf8'),bytes=signed.signature||signed;
    if((provider.publicKey?.toString()||wallet)!==wallet||S.epoch!==epoch)throw Error('Wallet changed during sign-in.');
    const signature=btoa(String.fromCharCode(...bytes));await api('/api/auth/verify',{method:'POST',body:JSON.stringify({id:challenge.id,signature})});
    S.wallet=wallet;bindProvider(provider);$('wallet-dialog').close();await refreshMember();
  }catch(error){$('wallet-message').textContent=error.code===4001?'Signature declined. Nothing was authorized.':error.message;}
  finally{S.authBusy=false;button.disabled=false;}
}

async function refreshMember(){
  const epoch=S.epoch;clearUsage('Refreshing private usage…');
  try{
    const account=await api('/api/account');if(S.epoch!==epoch)return;
    S.wallet=account.wallet;
    const candidates=walletCandidates(),provider=candidates.find(([,item])=>item.publicKey?.toString()===S.wallet)?.[1];
    if(!provider&&candidates.some(([,candidate])=>candidate.publicKey)){await invalidate('Connected wallet differs from this session. Sign in again.');return;}
    if(provider&&!S.provider)bindProvider(provider);
    $('main-connect').hidden=true;$('member-actions').hidden=false;$('keys-detail').hidden=false;$('access-pill').textContent=S.wallet.slice(0,4)+'…'+S.wallet.slice(-4);$('access-title').textContent='Your funded allowance.';$('access-description').textContent='Your coins stay in your wallet. All API keys share this daily limit.';
    for(const button of document.querySelectorAll('.connect'))button.textContent=S.wallet.slice(0,4)+'…'+S.wallet.slice(-4);

    const [membership,totals,keys]=await Promise.all([api('/api/membership'),api('/api/usage/summary'),api('/api/keys')]);if(S.epoch!==epoch)return;
    const eligible=Boolean(membership.eligibility?.eligible&&membership.funded_allowance_mode);
    $('create-key').disabled=!eligible;
    $('quota-used').textContent=compact(membership.used_tokens)+' used'+(safeInteger(membership.reserved_tokens)>0?' · '+compact(membership.reserved_tokens)+' reserved':'');
    $('quota-left').textContent=compact(membership.remaining_tokens)+' tokens left';
    $('quota-bar').max=Math.max(1,safeInteger(membership.daily_tokens)||1);$('quota-bar').value=(safeInteger(membership.used_tokens)||0)+(safeInteger(membership.reserved_tokens)||0);
    $('allowance-label').textContent=compact(membership.daily_tokens)+' AI tokens / day';
    $('access-message').textContent=!eligible?(membership.eligibility?.reason||'The holding requirement is not met.'):membership.pool?.reconciliation_required?'Provider billing needs review. New requests are paused.':safeInteger(membership.pool?.available_budget_ngonka)===0?'Key creation is available. Inference starts when the operator funds the allowance pool.':'Eligible. Daily reset at 00:00 UTC; funding and capacity limits apply.';
    renderUsage(membership,totals);
    renderKeys(Array.isArray(keys.data)?keys.data:[]);
  }catch(error){
    clearUsage(error.status===401?'Session expired · usage cleared':'Usage unavailable · private data cleared');
    if(error.status===401){detachProvider();clearAccount();$('access-message').textContent='Session expired. Connect your wallet again.';return;}
    if(S.wallet)$('access-message').textContent=error.message;
  }
}

function renderKeys(keys){
  $('key-list').replaceChildren();const live=keys.filter(key=>!key.revoked);
  if(!live.length){$('key-list').textContent='No keys yet.';return;}
  for(const key of live){const row=document.createElement('div');row.className='key-item';const text=document.createElement('span');text.textContent=key.name+' · '+key.prefix+'…';const button=document.createElement('button');button.textContent='Revoke';button.addEventListener('click',()=>{S.revoke=key.id;$('revoke-dialog').showModal();});row.append(text,button);$('key-list').append(row);}
}

$('create-key').addEventListener('click',async()=>{const button=$('create-key'),epoch=S.epoch;button.disabled=true;try{const key=await api('/api/member-key',{method:'POST'});if(S.epoch!==epoch)return;S.key=key.key;$('created-key').value=key.key;$('new-key').hidden=false;$('request-note').textContent='Key ready. This request uses your daily allowance.';toast('Key created. Save it now—it is shown only once.');await refreshMember();}catch(error){toast(error.message);}finally{if(S.epoch===epoch)button.disabled=false;}});
$('show-key').addEventListener('click',()=>{const reveal=$('created-key').type==='password';$('created-key').type=reveal?'text':'password';$('show-key').textContent=reveal?'Hide':'Show';});
$('copy-key').addEventListener('click',()=>copy(S.key));
$('confirm-revoke').addEventListener('click',async()=>{const epoch=S.epoch;try{await api('/api/keys/'+encodeURIComponent(S.revoke),{method:'DELETE'});if(S.epoch!==epoch)return;clearSecrets();$('revoke-dialog').close();S.revoke=null;await refreshMember();toast('Key revoked.');}catch(error){toast(error.message);}});
$('logout').addEventListener('click',async()=>{const provider=S.provider;detachProvider();clearAccount();try{await api('/api/auth/logout',{method:'POST'});await provider?.disconnect?.();toast('Disconnected. Temporary keys, prompts, and usage were cleared.');}catch{toast('Local data cleared. Server sign-out could not be confirmed.');}});

async function readStream(response,epoch){
  return SlipvoltRequestTools.readCompletionStream(response,output=>{
    if(epoch!==S.epoch)return;
    $('result').textContent=output;
    $('result').classList.add('has-output');
  });
}
$('send').addEventListener('click',async()=>{
  if(S.busy)return;
  let outputBudget;try{outputBudget=requestedOutput();}catch(error){return toast(error.message);}
  const key=$('existing-key').value.trim()||S.key,prompt=$('prompt').value.trim();
  if(key.startsWith('obk-'))return toast('Never paste your OpenBroker key here. Use your Slipvolt key.');
  if(!C.isCustomerKey(key))return toast('Connect your wallet and get a key, or enter an existing Slipvolt key.');
  if(!prompt)return toast('Write a prompt first.');
  if(OFFLINE)return toast('Offline preview. No model request was sent.');
  S.busy=true;$('stop-request').hidden=false;$('request-id').textContent='';const epoch=S.epoch;S.controller=new AbortController();$('send').disabled=true;$('send').textContent='Generating…';$('result').textContent='Connecting to your model…';
  try{
    const response=await fetch('/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+key,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({model:S.selected,messages:[{role:'user',content:prompt}],max_tokens:outputBudget,stream:!!S.status?.capabilities?.streaming}),signal:S.controller.signal});
    if(epoch===S.epoch)$('request-id').textContent=response.headers.get('x-request-id')?'Request '+response.headers.get('x-request-id'):'';
    if(!response.ok){const data=await response.json();throw Error(data.error?.message||'Request failed.');}
    if(response.headers.get('content-type')?.includes('text/event-stream'))await readStream(response,epoch);else{const data=await response.json();if(epoch===S.epoch){$('result').textContent=data.choices?.[0]?.message?.content||'No text returned.';$('result').classList.add('has-output');}}
    if(epoch===S.epoch){$('request-note').textContent='Complete. Measured usage was deducted from your allowance.';await refreshMember();}
  }catch(error){if(epoch===S.epoch){$('result').textContent=error.name==='AbortError'?'Request stopped. Check your allowance before retrying.':error.message;$('request-note').textContent='No automatic retry. Check usage before resubmitting.';}}
  finally{$('stop-request').hidden=true;S.busy=false;S.controller=null;$('send').disabled=false;$('send').textContent='Send prompt ↑';}
});

async function refreshPublic(){
  if(OFFLINE)return;
  const outcomes=await Promise.allSettled([api('/api/network'),api('/api/treasury')]);
  const network=outcomes[0].status==='fulfilled'?outcomes[0].value:null;
  if(network?.totals){$('network-requests').textContent=compact(network.totals.requests);$('network-tokens').textContent=compact(network.totals.tokens);$('network-cost').textContent=gnk(network.totals.cost_ngonka);$('network-window').textContent=(network.stale?'Stale snapshot · ':'')+network.window_from+' to '+network.window_to+' · Provider-wide records, not Slipvolt usage.';}
  else{for(const id of ['network-requests','network-tokens','network-cost'])$(id).textContent='—';$('network-window').textContent='Provider network statistics unavailable. OpenBroker’s page has the full view.';}
  const treasury=outcomes[1].status==='fulfilled'?outcomes[1].value:null;
  $('broker-available').textContent=treasury?.broker_balance?gnk(treasury.broker_balance.available_ngonka)+' GNK':treasury?.status==='unavailable'?'Unavailable':'Not published';
  $('native-available').textContent=treasury?.self_custody_balance?gnk(treasury.self_custody_balance.amount_ngonka)+' GNK':treasury?.self_custody_status==='unavailable'?'Unavailable':'Not configured';
  $('native-source').textContent=treasury?.self_custody_balance?'Gonka mainnet · observed '+new Date(treasury.self_custody_balance.observed_at*1000).toLocaleString():'Public treasury address has not been configured.';
  $('treasury-source').textContent=treasury?.broker_balance?'OpenBroker service balance · observed '+new Date(treasury.broker_balance.observed_at*1000).toLocaleString():'No private service balance has been published.';
}
$('refresh').addEventListener('click',async()=>{if(OFFLINE)return toast('Offline preview. Live statistics load from the server.');$('refresh').disabled=true;try{await refreshPublic();}finally{$('refresh').disabled=false;}});

async function init(){
  renderModels();clearUsage();
  if(OFFLINE){$('setup-note').textContent='Offline preview';return;}
  try{
    S.status=await api('/api/status');
    document.querySelectorAll('[data-site-name]').forEach(element=>element.textContent=S.status.brand);
    document.title=S.status.brand+' — Funded AI for token holders';
    if(typeof refreshRequestControls==='function')refreshRequestControls();
    const limits=S.status.limits||{};
    $('policy-default-output').textContent=safeInteger(limits.default_output_tokens)?whole(limits.default_output_tokens)+' tokens':'Unavailable';
    $('policy-max-output').textContent=safeInteger(limits.max_output_tokens)?whole(limits.max_output_tokens)+' tokens':'Unavailable';
    $('policy-wallet-rate').textContent=safeInteger(limits.wallet_rpm)&&safeInteger(limits.wallet_concurrency)?whole(limits.wallet_rpm)+' requests/min · '+whole(limits.wallet_concurrency)+' concurrent':'Unavailable';
    if(S.status.holder_gate_configured){$('stage').textContent='PILOT · TOKEN GATE CONFIGURED';$('holding-requirement').textContent=rawTokens(S.status.min_holding_raw,S.status.holder_token_decimals)+' '+S.status.holder_token_symbol;$('allowance-label').textContent=compact(S.status.holder_daily_tokens)+' AI tokens / day';$('allowance-note').textContent='Shared pool: '+compact(S.status.global_daily_tokens)+' AI tokens/day. Funding and capacity limits apply.';$('access-message').textContent='Connect to verify your holdings.';}
    else $('allowance-note').textContent='Pilot setting: '+compact(S.status.holder_daily_tokens)+' AI tokens/day; final terms are not published.';
    $('setup-note').textContent=S.status.provider_configured?'Provider configured · funding checked per call':'Setup mode · provider credential needed';
  }catch{$('setup-note').textContent='Backend unavailable';}
  try{
    const catalog=await api('/api/models');
    S.models=catalog.data.map(item=>({...snapshot.find(model=>model.id===item.id),...item}));renderModels();
    $('model-source').textContent=catalog.live?'Live OpenBroker catalog · reviewed service limits':'Documented model catalog · live availability unavailable';
  }catch{$('model-source').textContent='Documented model catalog · live availability unavailable';}
  await Promise.allSettled([refreshPublic(),refreshMember()]);
}
init();
