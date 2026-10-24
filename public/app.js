/* One-page holder access. No upstream credential, persistent browser storage, or simulated usage. */
'use strict';
const $=id=>document.getElementById(id),C=globalThis.SlipvoltCore;
const OFFLINE=document.documentElement.dataset.preview==='offline';
const snapshot=[
  {id:'MiniMaxAI/MiniMax-M2.7',name:'MiniMax M2.7',label:'Coding & everyday tasks',mark:'M / 01'},
  {id:'deepseek-ai/DeepSeek-V4-Flash-0731',name:'DeepSeek V4 Flash',label:'Reasoning & generation',mark:'D / 02'},
  {id:'zai-org/GLM-5.3-Flash',name:'GLM 5.3 Flash',label:'General-purpose AI',mark:'G / 03'}
];
const S={models:snapshot,selected:snapshot[0].id,catalogLive:OFFLINE,status:null,wallet:null,provider:null,key:'',epoch:0,memberSerial:0,requestSerial:0,authOps:0,busy:false,authBusy:false,controller:null,memberController:null,revoke:null,handlers:null,conversation:[],conversationFull:false};
const CHAT_LIMITS=Object.freeze({maxTurns:24,maxChars:250000});
let toastTimer;

function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,7500);}
const compact=value=>C.safeCount(value)!==null?new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:1}).format(value):'Unavailable';
const whole=value=>C.safeCount(value)!==null?new Intl.NumberFormat('en').format(value):'Unavailable';
function nonnegativeBigInt(raw){try{if(typeof raw==='bigint')return raw>=0n?raw:null;if(typeof raw==='number')return Number.isSafeInteger(raw)&&raw>=0?BigInt(raw):null;if(typeof raw==='string'&&/^\d+$/.test(raw))return BigInt(raw);return null;}catch{return null;}}
function gnk(raw){const n=nonnegativeBigInt(raw);if(n===null)return 'Unavailable';const units=n/1000000000n,frac=(n%1000000000n).toString().padStart(9,'0').replace(/0+$/,'');return units.toLocaleString('en')+(frac?'.'+frac:'');}
function rawTokens(raw,decimals){try{const n=nonnegativeBigInt(raw);if(n===null||!Number.isSafeInteger(decimals)||decimals<0||decimals>30)return 'Set at launch';const scale=10n**BigInt(decimals);return (n/scale).toLocaleString('en')+(n%scale?'.'+(n%scale).toString().padStart(decimals,'0').replace(/0+$/,''):'');}catch{return 'Set at launch';}}
const safeInteger=C.safeCount;
async function api(path,options={}){if(OFFLINE)throw Error('This is the offline preview. Run the included server to connect your wallet.');const r=await fetch(path,{...options,credentials:'same-origin',headers:{...(options.body?{'Content-Type':'application/json'}:{}),...options.headers}});return C.readApiResponse(r);}
async function copy(value){if(!value)return toast('Nothing to copy yet.');try{await navigator.clipboard.writeText(value);toast('Copied.');}catch{toast('Clipboard unavailable here. Select the text and copy it manually.');}}
function beginAuthOperation(){S.authOps++;S.authBusy=true;let active=true;return()=>{if(!active)return;active=false;S.authOps=Math.max(0,S.authOps-1);S.authBusy=S.authOps>0;};}

function conversationMessages(prompt){return C.chatMessages(S.conversation,prompt);}
function clearVisibleResponse(){
  $('request-id').textContent='';$('result').textContent='Your answer will appear here.';$('result').classList.remove('has-output','partial-output');
  if($('download-response'))$('download-response').disabled=true;
}
function renderConversationContext(note=''){
  const stats=C.chatStats(S.conversation),summary=$('conversation-context'),history=$('conversation-history'),details=$('conversation-history-details'),count=$('conversation-history-count');
  if(summary)summary.textContent=note||(stats.turns?`${stats.turns} completed turn${stats.turns===1?'':'s'} · ${stats.characters.toLocaleString()} characters kept in this tab. Sending includes these messages; token fit is checked when you send.`:'History is kept in this tab. Sending a follow-up includes previous messages.');
  if(history){
    history.replaceChildren();
    for(const turn of S.conversation){
      for(const [role,content] of [['You',turn.user],['Assistant',turn.assistant]]){
        const message=document.createElement('div'),label=document.createElement('strong'),body=document.createElement('p');message.className='conversation-message';message.dataset.role=role.toLowerCase();label.textContent=role;body.textContent=content;message.append(label,body);history.append(message);
      }
    }
  }
  if(details)details.hidden=stats.turns===0;
  if(count)count.textContent=stats.turns?`(${stats.turns} turn${stats.turns===1?'':'s'})`:'';
  if($('download-chat'))$('download-chat').disabled=stats.turns===0;
}
function resetConversation({clearDraft=true,note=''}={}){
  S.requestSerial++;const controller=S.controller;S.controller=null;controller?.abort();S.busy=false;S.conversation=[];S.conversationFull=false;
  if(clearDraft)$('prompt').value='';clearVisibleResponse();$('stop-request').hidden=true;$('send').textContent='Send prompt ↑';
  document.dispatchEvent(new Event('slipvolt:conversation-reset'));renderConversationContext(note);syncRequestActions();
}
function rememberConversationTurn(prompt,answer){
  const update=C.appendChatTurn(S.conversation,prompt,answer,CHAT_LIMITS);S.conversation=update.turns;S.conversationFull=update.full===true;
  document.dispatchEvent(new Event('slipvolt:conversation-changed'));
  renderConversationContext(S.conversationFull?'This chat reached its in-tab memory limit. Download it or start a new chat before sending another follow-up.':'');
}

function selectedModel(){return S.catalogLive?C.selectableModelId(S.models,S.selected):'';}
function selectedOutputCeiling(){const value=safeInteger(S.models.find(model=>model.id===selectedModel())?.max_completion_tokens);return value&&value>0?value:OFFLINE?16384:null;}
function syncRequestActions(){
  const available=Boolean(selectedModel()&&selectedOutputCeiling()&&!S.conversationFull);
  $('send').disabled=S.busy||!available;
  $('check-request').disabled=S.busy||!available;
  for(const button of document.querySelectorAll('.model-tab')){
    const model=S.models.find(item=>item.id===button.dataset.model);
    button.disabled=S.busy||!S.catalogLive||model?.availability==='unavailable'||model?.routable===false;
  }
}
function selectModel(id){
  const previous=S.selected,next=S.catalogLive?C.selectableModelId(S.models,id):'';
  S.selected=next;
  if(previous&&next!==previous)resetConversation({clearDraft:false,note:'Model changed · previous turns were cleared. Your draft is still editable.'});
  for(const button of document.querySelectorAll('.model-tab')){
    const active=button.dataset.model===S.selected;
    button.setAttribute('aria-pressed',active?'true':'false');
    button.tabIndex=0;
  }
  $('selected-name').textContent=S.models.find(model=>model.id===S.selected)?.name||'No model available';
  if(typeof refreshRequestControls==='function')refreshRequestControls();
  syncRequestActions();
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
  if(!S.models.length){const empty=document.createElement('p');empty.className='empty-copy';empty.textContent='No service models are currently listed.';list.append(empty);}
  for(const model of S.models){
    const button=document.createElement('button');
    const unavailable=!S.catalogLive||model.availability==='unavailable'||model.routable===false;
    const context=safeInteger(model.context_length);
    const output=safeInteger(model.max_completion_tokens);
    button.className='model-tab'+(unavailable?' model-unavailable':'');
    button.dataset.model=model.id;
    button.disabled=unavailable;
    button.setAttribute('aria-pressed',model.id===S.selected?'true':'false');
    const discoveredContext=safeInteger(model.discovered_context_length),discoveredOutput=safeInteger(model.discovered_max_completion_tokens);
    const discovered=model.discovery_limits_status==='reported'||model.discovery_limits_status==='partial'?'discovered metadata '+(discoveredContext?compact(discoveredContext)+' context':'context unknown')+' · '+(discoveredOutput?compact(discoveredOutput)+' output':'output unknown'):'discovered limits unknown';
    button.title=discovered+'. OpenBroker route limits are unverified.';
    button.innerHTML='<span class="model-mark">'+C.escape(model.mark||'AI')+'</span><strong>'+C.escape(model.name||model.id)+'</strong><small>'+C.escape(model.label||'Gonka model')+'</small><small class="model-limits">'+C.escape(context?'context service limit '+compact(context):'context limit unavailable')+'<br>'+C.escape(output?'output service limit '+compact(output):'output limit unavailable')+'</small><small class="model-health">'+C.escape(modelAvailability(model))+'</small>';
    button.addEventListener('click',()=>selectModel(model.id));
    list.append(button);
  }
  selectModel(S.selected);
}

function renderCode(){
  if(!selectedModel()){$('api-code').textContent='No service model is currently available.';return;}
  const base=OFFLINE?'https://YOUR_HOST/v1':location.origin+'/v1';
  const budget=Number($('output-tokens')?.value)||4096;
  try{$('api-code').textContent=globalThis.SlipvoltExamples.example($('example-language')?.value||'curl',base,S.selected,budget);}catch{$('api-code').textContent='Connection example unavailable.';}
}

function tab(name){for(const value of ['chat','api']){const active=name===value;$('tab-'+value).setAttribute('aria-selected',String(active));$('tab-'+value).tabIndex=active?0:-1;$(value+'-panel').hidden=!active;}}
for(const value of ['chat','api']){
  $('tab-'+value).addEventListener('click',()=>tab(value));
  $('tab-'+value).addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();const next=value==='chat'?'api':'chat';tab(next);$('tab-'+next).focus();}});
}
tab('chat');
$('copy-code').addEventListener('click',()=>copy($('api-code').textContent));
for(const button of document.querySelectorAll('dialog .close'))button.addEventListener('click',()=>button.closest('dialog').close());

const promptStarters=Object.freeze({
  write:'Write a clear, engaging draft about [topic] for [audience]. Use a [tone] tone and include [key points].',
  code:'Help me build [feature] using [language or framework]. Requirements: [requirements]. Explain the approach, then provide complete code and checks.',
  understand:'Explain [topic or text] in plain language. Start with the main idea, then walk through an example and the details that matter.'
});
for(const button of document.querySelectorAll('.prompt-starter'))button.addEventListener('click',()=>{
  const starter=promptStarters[button.dataset.starter];if(!starter||S.busy)return;
  $('prompt').value=starter;$('prompt').dispatchEvent(new Event('input',{bubbles:true}));$('prompt').focus();$('prompt').setSelectionRange(0,starter.length);
});
$('prompt').addEventListener('keydown',event=>{
  if(event.isComposing||event.keyCode===229||event.key!=='Enter'||(!event.ctrlKey&&!event.metaKey))return;
  event.preventDefault();if(!$('send').disabled)$('send').click();
});
$('new-chat')?.addEventListener('click',()=>{resetConversation();$('request-note').textContent='New chat started. Previous prompts and answers were cleared from this tab.';$('prompt').focus();});
function downloadText(filename,value){
  const url=URL.createObjectURL(new Blob([value],{type:'text/plain;charset=utf-8'})),link=document.createElement('a');link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),0);
}
$('download-response')?.addEventListener('click',()=>{
  if(!$('result').classList.contains('has-output'))return toast('There is no completed answer to download yet.');
  downloadText('holdbyte-answer.txt',$('result').textContent);
});
$('download-chat')?.addEventListener('click',()=>{
  const transcript=C.chatTranscript(S.conversation);if(!transcript)return toast('There is no completed chat to download yet.');
  downloadText('holdbyte-chat.txt',transcript);
});
$('existing-key').addEventListener('input',()=>{
  if(S.conversation.length||S.busy||$('result').classList.contains('has-output'))resetConversation({clearDraft:false,note:'Customer key changed · previous turns were cleared. Your draft is still editable.'});
});
renderConversationContext();

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

function publicAccessMessage(){return S.status?.holder_gate_configured?'Connect to verify your holdings.':'Connect a wallet when holder access is configured.';}
function publicAllowance(){
  const daily=safeInteger(S.status?.holder_daily_tokens);
  $('allowance-label').textContent=daily!==null?compact(daily)+' AI tokens / day':'Published at launch';
}
function validMint(value){return typeof value==='string'&&/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(value);}
function canonicalBuyUrl(value,mint){
  if(!validMint(mint)||typeof value!=='string')return '';
  try{const url=new URL(value);return url.origin==='https://pump.fun'&&!url.username&&!url.password&&!url.search&&!url.hash&&url.pathname==='/coin/'+mint?url.href:'';}catch{return '';}
}
function renderTokenLaunch(){
  const mint=validMint(S.status?.holder_mint)?S.status.holder_mint:'',mintText=$('token-mint'),copyButton=$('copy-token-mint'),buyLink=$('token-buy-link'),note=$('token-launch-note'),heroConnect=document.querySelector('.hero-connect');
  if(mintText){mintText.textContent=mint||'Not published';mintText.hidden=!mint;}
  if(copyButton){copyButton.disabled=!mint;copyButton.hidden=!mint;}
  const buyUrl=S.status?.token_launched===true?canonicalBuyUrl(S.status?.token_buy_url,mint):'';
  if(buyLink){buyLink.hidden=!buyUrl;if(buyUrl)buyLink.href=buyUrl;else buyLink.removeAttribute('href');}
  if(heroConnect)heroConnect.hidden=Boolean(buyUrl);
  if(note)note.textContent=buyUrl?'Token launch is published. Verify this exact mint before opening the external market.':mint?'Mint configured · buying is not published here. Verify the mint, not a ticker.':'No project mint is published. Do not rely on a ticker alone.';
}
$('copy-token-mint')?.addEventListener('click',()=>copy(validMint(S.status?.holder_mint)?S.status.holder_mint:''));
function clearMemberData(){
  S.revoke=null;
  if($('revoke-dialog').open)$('revoke-dialog').close();
  $('key-list').replaceChildren();
  $('create-key').disabled=true;
  for(const id of ['confirm-revoke','revoke-all-keys','logout-everywhere'])$(id).disabled=false;
  $('quota-used').textContent='—';$('quota-left').textContent='—';$('quota-bar').max=1;$('quota-bar').value=0;
  publicAllowance();
}
function clearSecrets(){
  document.dispatchEvent(new Event('slipvolt:account-cleared'));
  resetConversation();S.key='';$('created-key').value='';$('created-key').type='password';$('show-key').textContent='Show';$('existing-key').value='';$('new-key').hidden=true;
}
function clearAccount(){
  S.epoch++;S.memberSerial++;const memberController=S.memberController;S.memberController=null;memberController?.abort();S.wallet=null;clearSecrets();clearMemberData();clearUsage();$('main-connect').hidden=false;$('member-actions').hidden=true;$('keys-detail').hidden=true;$('access-pill').textContent='Not connected';$('access-title').textContent='Your wallet is your login.';$('access-description').textContent='No email or checkout. Sign a login message to prove the wallet is yours.';$('access-message').textContent=publicAccessMessage();$('request-note').textContent='Create a key above to start.';for(const button of document.querySelectorAll('.connect'))button.textContent='Connect wallet ↗';
}
function detachProvider(){if(S.provider?.removeListener&&S.handlers){S.provider.removeListener('accountChanged',S.handlers.change);S.provider.removeListener('disconnect',S.handlers.disconnect);}S.provider=null;S.handlers=null;}
async function invalidate(message){
  const releaseAuth=beginAuthOperation();
  clearAccount();
  try{await api('/api/auth/logout',{method:'POST'});}catch{}
  finally{releaseAuth();}
  toast(message);
}
function bindProvider(provider){detachProvider();S.provider=provider;S.handlers={change:key=>{if(S.wallet&&key?.toString()!==S.wallet)invalidate('Wallet changed. Sign in again.');},disconnect:()=>{if(S.wallet)invalidate('Wallet disconnected.');}};provider.on?.('accountChanged',S.handlers.change);provider.on?.('disconnect',S.handlers.disconnect);}
function walletCandidates(){return [['Phantom',window.phantom?.solana||window.solana],['Solflare',window.solflare]].filter(([,provider],index,all)=>provider?.connect&&provider?.signMessage&&all.findIndex(([,other])=>other===provider)===index);}
function showWallets(){
  if(S.authBusy)return toast('Finishing the previous wallet session. Try again in a moment.');
  if(S.wallet)return toast('You are signed in. Get or manage your API keys in the access card.');
  $('wallet-options').replaceChildren();$('wallet-message').textContent='';$('wallet-dialog').showModal();
  if(OFFLINE){$('wallet-message').textContent='Offline preview. Start the included backend to sign in and create a real key. No key has been generated.';return;}
  const candidates=walletCandidates();
  if(!candidates.length)$('wallet-message').textContent='Open this site in a supported wallet browser, or enable Phantom or Solflare in your desktop browser.';
  for(const [name,provider] of candidates){const button=document.createElement('button');button.className='wallet-option';button.textContent=name+' ↗';button.addEventListener('click',()=>connect(provider,button));$('wallet-options').append(button);}
}
for(const button of document.querySelectorAll('.connect'))button.addEventListener('click',showWallets);

async function connect(provider,button){
  if(S.authBusy)return;const releaseAuth=beginAuthOperation();button.disabled=true;const epoch=S.epoch;
  try{
    const connected=await provider.connect(),wallet=(connected?.publicKey||provider.publicKey)?.toString();
    if(typeof wallet!=='string'||!/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(wallet))throw Error('Wallet did not provide a valid Solana address.');
    const challenge=await api('/api/auth/challenge',{method:'POST',body:JSON.stringify({wallet})});
    const signed=await provider.signMessage(new TextEncoder().encode(challenge.message),'utf8'),bytes=signed.signature||signed;
    if((provider.publicKey?.toString()||wallet)!==wallet||S.epoch!==epoch)throw Error('Wallet changed during sign-in.');
    const signature=btoa(String.fromCharCode(...bytes));await api('/api/auth/verify',{method:'POST',body:JSON.stringify({id:challenge.id,signature})});
    if((provider.publicKey?.toString()||wallet)!==wallet||S.epoch!==epoch){
      try{await api('/api/auth/logout',{method:'POST'});}catch{throw Error('Wallet changed during sign-in, and server sign-out could not be confirmed. Reload before trying again.');}
      throw Error('Wallet changed during sign-in. No session was kept.');
    }
    S.wallet=wallet;bindProvider(provider);$('wallet-dialog').close();await refreshMember();
  }catch(error){$('wallet-message').textContent=error.code===4001?'Signature declined. Nothing was authorized.':error.message;}
  finally{releaseAuth();button.disabled=false;}
}

async function refreshMember(){
  const epoch=S.epoch,mine=++S.memberSerial,startedWallet=S.wallet,previousController=S.memberController,controller=new AbortController();S.memberController=controller;previousController?.abort();const current=()=>S.epoch===epoch&&S.memberSerial===mine;
  clearMemberData();clearUsage('Refreshing private usage…');if(startedWallet)$('access-message').textContent='Refreshing wallet access…';
  try{
    const account=await api('/api/account',{signal:controller.signal});if(!current())return;
    if(typeof account?.wallet!=='string'||!/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(account.wallet))throw Error('The account response did not contain a valid wallet.');
    if(S.wallet&&S.wallet!==account.wallet){await invalidate('The server wallet changed. Sign in again.');return;}
    if(S.wallet!==account.wallet)clearSecrets();
    S.wallet=account.wallet;
    const candidates=walletCandidates(),provider=candidates.find(([,item])=>item.publicKey?.toString()===S.wallet)?.[1];
    if(!provider&&candidates.some(([,candidate])=>candidate.publicKey)){await invalidate('Connected wallet differs from this session. Sign in again.');return;}
    if(provider&&S.provider!==provider)bindProvider(provider);
    $('main-connect').hidden=true;$('member-actions').hidden=false;$('keys-detail').hidden=false;$('access-pill').textContent=S.wallet.slice(0,4)+'…'+S.wallet.slice(-4);$('access-title').textContent='Your funded allowance.';$('access-description').textContent='Your coins stay in your wallet. All API keys share this daily limit.';
    for(const button of document.querySelectorAll('.connect'))button.textContent=S.wallet.slice(0,4)+'…'+S.wallet.slice(-4);

    const options={signal:controller.signal};const [membership,totals,keys]=await Promise.all([api('/api/membership',options),api('/api/usage/summary',options),api('/api/keys',options)]);if(!current())return;
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
    if(!current())return;
    const hadSession=Boolean(startedWallet||S.wallet);clearMemberData();
    if(!hadSession){clearUsage(error.status===401?'Connect to load your private usage':'Usage unavailable');return;}
    clearSecrets();clearUsage(error.status===401?'Session expired · usage cleared':'Usage unavailable · private data cleared');
    if(error.status===401){detachProvider();clearAccount();$('access-message').textContent='Session expired. Connect your wallet again.';return;}
    if(S.wallet)$('access-message').textContent=error.message;
  }finally{if(S.memberController===controller)S.memberController=null;}
}

function renderKeys(keys){
  $('key-list').replaceChildren();const live=keys.filter(key=>!key.revoked);
  if(!live.length){$('key-list').textContent='No keys yet.';return;}
  for(const key of live){const row=document.createElement('div');row.className='key-item';const text=document.createElement('span');text.textContent=key.name+' · '+key.prefix+'…';const button=document.createElement('button');button.textContent='Revoke';button.addEventListener('click',()=>{S.revoke=key.id;$('revoke-dialog').showModal();});row.append(text,button);$('key-list').append(row);}
}

$('create-key').addEventListener('click',async()=>{const button=$('create-key'),epoch=S.epoch,wallet=S.wallet;let created=false;button.disabled=true;try{const key=await api('/api/member-key',{method:'POST'});if(S.epoch!==epoch||S.wallet!==wallet)return;created=true;resetConversation({clearDraft:false,note:'New key ready · previous turns were cleared. Your draft is still editable.'});$('existing-key').value='';S.key=key.key;$('created-key').value=key.key;$('new-key').hidden=false;$('request-note').textContent='Key ready. This request uses your daily allowance.';toast('Key created. Save it now—it is shown only once.');await refreshMember();}catch(error){if(S.epoch===epoch&&S.wallet===wallet)toast(error.message);}finally{if(S.epoch===epoch&&S.wallet===wallet&&!created)button.disabled=false;}});
$('show-key').addEventListener('click',()=>{const reveal=$('created-key').type==='password';$('created-key').type=reveal?'text':'password';$('show-key').textContent=reveal?'Hide':'Show';});
$('copy-key').addEventListener('click',()=>copy(S.key));
$('confirm-revoke').addEventListener('click',async()=>{const button=$('confirm-revoke'),epoch=S.epoch,wallet=S.wallet,keyId=S.revoke;if(!keyId||button.disabled)return;button.disabled=true;try{await api('/api/keys/'+encodeURIComponent(keyId),{method:'DELETE'});if(S.epoch!==epoch||S.wallet!==wallet)return;clearSecrets();$('revoke-dialog').close();S.revoke=null;await refreshMember();if(S.epoch===epoch&&S.wallet===wallet)toast('Key revoked.');}catch(error){if(S.epoch===epoch&&S.wallet===wallet)toast(error.message);}finally{if(S.epoch===epoch&&S.wallet===wallet)button.disabled=false;}});
$('logout').addEventListener('click',async()=>{if(S.authBusy)return;const releaseAuth=beginAuthOperation(),provider=S.provider;detachProvider();clearAccount();let serverSignedOut=true;try{await api('/api/auth/logout',{method:'POST'});}catch{serverSignedOut=false;}try{await provider?.disconnect?.();}catch{}finally{releaseAuth();}toast(serverSignedOut?'Disconnected. Temporary keys, prompts, and usage were cleared.':'Local data cleared. Server sign-out could not be confirmed.');});

async function readStream(response,epoch,request){
  return SlipvoltRequestTools.readCompletionStream(response,output=>{
    if(epoch!==S.epoch||request!==S.requestSerial)return;
    $('result').textContent=output;
    if(output)$('result').classList.add('partial-output');
  });
}
$('send').addEventListener('click',async()=>{
  if(S.busy)return;
  if(S.conversationFull)return toast('This chat reached its in-tab memory limit. Download it or start a new chat.');
  const model=selectedModel();if(!model)return toast('No service model is currently available.');
  let outputBudget;try{outputBudget=requestedOutput();}catch(error){return toast(error.message);}
  const key=$('existing-key').value.trim()||S.key,prompt=$('prompt').value.trim();
  if(key.startsWith('obk-'))return toast('Never paste your OpenBroker key here. Use your Holdbyte customer key.');
  if(!C.isCustomerKey(key))return toast('Connect your wallet and get a key, or enter an existing Holdbyte customer key.');
  if(!prompt)return toast('Write a prompt first.');
  if(OFFLINE)return toast('Offline preview. No model request was sent.');
  const messages=conversationMessages(prompt);
  S.busy=true;$('stop-request').hidden=false;clearVisibleResponse();const epoch=S.epoch,request=++S.requestSerial,controller=new AbortController();S.controller=controller;syncRequestActions();$('send').textContent='Generating…';$('result').textContent='Connecting to your model…';
  const current=()=>epoch===S.epoch&&request===S.requestSerial;
  try{
    const response=await fetch('/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+key,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({model,messages,max_tokens:outputBudget,stream:!!S.status?.capabilities?.streaming}),signal:controller.signal});
    if(current())$('request-id').textContent=response.headers.get('x-request-id')?'Request '+response.headers.get('x-request-id'):'';
    if(!response.ok)await C.readApiResponse(response);
    let answer='';
    if(response.headers.get('content-type')?.includes('text/event-stream'))answer=await readStream(response,epoch,request);else{const data=await C.readApiResponse(response);answer=typeof data?.choices?.[0]?.message?.content==='string'?data.choices[0].message.content:'';}
    if(controller.signal.aborted)throw controller.signal.reason||new DOMException('The request was stopped.','AbortError');
    if(current()){
      $('result').classList.remove('partial-output');
      if(answer.trim()){$('result').textContent=answer;$('result').classList.add('has-output');if($('download-response'))$('download-response').disabled=false;rememberConversationTurn(prompt,answer);if($('prompt').value.trim()===prompt)$('prompt').value='';}
      else{$('result').textContent='The request completed without a text answer.';$('result').classList.remove('has-output');}
      $('request-note').textContent='Complete. Measured usage was deducted from your allowance.';if(S.wallet)await refreshMember();
    }
  }catch(error){if(current()){$('result').classList.remove('has-output','partial-output');if($('download-response'))$('download-response').disabled=true;$('result').textContent=error.name==='AbortError'?'Request stopped. Check your allowance before retrying.':error.message;$('request-note').textContent='No automatic retry. Check usage before resubmitting.';}}
  finally{if(current()){$('stop-request').hidden=true;S.busy=false;S.controller=null;$('send').textContent='Send prompt ↑';syncRequestActions();}}
});

async function init(){
  renderModels();clearUsage();
  if(OFFLINE){$('setup-note').textContent='Offline preview';return;}
  const [statusResult,catalogResult]=await Promise.allSettled([api('/api/status'),api('/api/models')]);
  if(statusResult.status==='fulfilled'){
    S.status=statusResult.value;
    const displayBrand=typeof S.status.brand==='string'&&/^[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}$/.test(S.status.brand)?S.status.brand:'Holdbyte';
    document.querySelectorAll('[data-site-name]').forEach(element=>element.textContent=displayBrand);
    document.title=displayBrand+' — Funded AI for token holders';renderTokenLaunch();
    if(typeof refreshRequestControls==='function')refreshRequestControls();
    const limits=S.status.limits||{};
    $('policy-default-output').textContent=safeInteger(limits.default_output_tokens)?whole(limits.default_output_tokens)+' tokens':'Unavailable';
    $('policy-max-output').textContent=safeInteger(limits.max_output_tokens)?whole(limits.max_output_tokens)+' tokens':'Unavailable';
    $('policy-wallet-rate').textContent=safeInteger(limits.wallet_rpm)&&safeInteger(limits.wallet_concurrency)?whole(limits.wallet_rpm)+' requests/min · '+whole(limits.wallet_concurrency)+' concurrent':'Unavailable';
    if(S.status.holder_gate_configured){const publishedBuy=canonicalBuyUrl(S.status.token_buy_url,S.status.holder_mint);$('stage').textContent=S.status.token_launched===true&&publishedBuy?'TOKEN LINK PUBLISHED':'PILOT · TOKEN GATE CONFIGURED';$('holding-requirement').textContent=rawTokens(S.status.min_holding_raw,S.status.holder_token_decimals)+' '+S.status.holder_token_symbol;$('allowance-label').textContent=compact(S.status.holder_daily_tokens)+' AI tokens / day';$('allowance-note').textContent='Shared pool: '+compact(S.status.global_daily_tokens)+' AI tokens/day. Funding and capacity limits apply.';$('access-message').textContent='Connect to verify your holdings.';}
    else $('allowance-note').textContent='Pilot setting: '+compact(S.status.holder_daily_tokens)+' AI tokens/day; final terms are not published.';
    $('setup-note').textContent=S.status.provider_configured?'Provider configured · funding checked per call':'Setup mode · provider credential needed';
  }else $('setup-note').textContent='Backend unavailable';
  if(catalogResult.status==='fulfilled'){
    const catalog=catalogResult.value;
    S.catalogLive=catalog.live===true;
    S.models=Array.isArray(catalog.data)?catalog.data.map(item=>({...snapshot.find(model=>model.id===item.id),...item})):[];renderModels();
    $('model-source').textContent=catalog.live?'Live OpenBroker catalog · reviewed service limits':'Documented model catalog · live availability unavailable';
  }else{
    S.catalogLive=false;S.models=snapshot;renderModels();$('model-source').textContent='Documented model catalog · live availability unavailable';
  }
  await refreshMember();
}
init();
