/* Read-only token evidence. Never connects a wallet or receives an admin key. */
(function(root){
'use strict';
function tokenAmount(raw,decimals){
  if(typeof raw!=='string'||!/^(0|[1-9][0-9]{0,79})$/.test(raw)||!Number.isInteger(decimals)||decimals<0||decimals>18)return 'Unavailable';
  const amount=BigInt(raw),scale=10n**BigInt(decimals);
  const whole=(amount/scale).toLocaleString('en-US');
  const fraction=decimals?(amount%scale).toString().padStart(decimals,'0').replace(/0+$/,''):'';
  return whole+(fraction?'.'+fraction:'');
}
function explorerLink(value,kind){
  const pattern=kind==='transaction'?/^[1-9A-HJ-NP-Za-km-z]{64,88}$/:/^[1-9A-HJ-NP-Za-km-z]{32,44}$/;
  if(typeof value!=='string'||!pattern.test(value))return '';
  return 'https://explorer.solana.com/'+(kind==='transaction'?'tx/':'address/')+value;
}
function snapshotReady(data){
  const mint=data?.mint_state;
  return Boolean(data?.status==='available'&&mint&&mint.mint===data.mint&&explorerLink(mint.mint,'account')&&
    tokenAmount(mint.supply_raw,mint.decimals)!=='Unavailable'&&Number.isSafeInteger(mint.slot)&&mint.slot>0);
}
const helpers={tokenAmount,explorerLink,snapshotReady};root.HoldbyteToken=helpers;
if(typeof module==='object'&&module.exports)module.exports=helpers;
if(typeof document==='undefined')return;
const $=id=>document.getElementById(id);
let serial=0;
function linkValue(id,value,empty='Unavailable'){
  const target=$(id);target.replaceChildren();
  const url=explorerLink(value,'account');
  if(!url){target.textContent=empty;return;}
  const a=document.createElement('a');a.href=url;a.textContent=value;a.target='_blank';a.rel='noopener noreferrer';target.append(a);
}
function clearSnapshot(){
  for(const id of ['supply','mint-authority','freeze-authority','program','slot'])$(id).textContent='Unavailable';
  $('checked').textContent='No verified snapshot';
}
function render(data){
  clearSnapshot();$('receipt-list').replaceChildren();
  $('burned').textContent='Unavailable';$('receipt-count').textContent='Unavailable';
  linkValue('mint',data?.mint,'Not published');
  const ready=snapshotReady(data),mint=data?.mint_state,burns=data?.burns;
  $('state').textContent=ready?'Finalized mint snapshot · reads only; no transaction execution.':data?.status==='unconfigured'?'No project mint is configured. No token purchase or deposit is enabled here.':'Live mint data is unavailable. Previously recorded receipts remain separate from this failed check.';
  if(ready){
    $('supply').textContent=tokenAmount(mint.supply_raw,mint.decimals);
    linkValue('mint-authority',mint.mint_authority,mint.mint_authority===null?'None at this snapshot':'Unavailable');
    linkValue('freeze-authority',mint.freeze_authority,mint.freeze_authority===null?'None at this snapshot':'Unavailable');
    linkValue('program',mint.token_program);
    $('slot').textContent=String(mint.slot);
    if(Number.isSafeInteger(data.checked_at)&&data.checked_at>0)$('checked').textContent='Checked '+new Date(data.checked_at*1000).toLocaleString();
  }
  const hasLedger=burns&&Number.isSafeInteger(burns.receipt_count)&&burns.receipt_count>=0;
  const decimals=burns?.decimals??(ready?mint.decimals:null);
  if(hasLedger){
    $('receipt-count').textContent=burns.receipt_count.toLocaleString('en-US');
    $('burned').textContent=burns.receipt_count===0&&burns.burned_raw==='0'?'0':tokenAmount(burns.burned_raw,decimals);
  }
  const rows=hasLedger&&Array.isArray(burns.recent)?burns.recent.slice(0,25):[];
  $('empty').hidden=rows.length>0;
  $('empty').textContent=hasLedger?'No finalized burn receipts have been recorded here. This does not prove that no burns exist.':'Receipt history is unavailable.';
  for(const row of rows){
    const url=explorerLink(row.signature,'transaction');if(!url)continue;
    const article=document.createElement('article');article.className='receipt';
    const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=row.signature.slice(0,12)+'…'+row.signature.slice(-12);a.setAttribute('aria-label','View burn transaction '+row.signature);
    const amount=document.createElement('strong');amount.textContent=tokenAmount(row.burned_raw,decimals)+' tokens';
    const note=document.createElement('small');note.textContent='Finalized receipt · slot '+(Number.isSafeInteger(row.slot)?row.slot:'unavailable');
    article.append(a,amount,note);$('receipt-list').append(article);
  }
}
async function refresh(){
  const mine=++serial;$('refresh').disabled=true;$('state').textContent='Checking the configured token…';
  try{
    const response=await fetch('/api/token',{credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(22000)});
    if(!response.ok)throw new Error('Token evidence unavailable');
    const data=await response.json();if(mine===serial)render(data);
  }catch{
    if(mine===serial){render({status:'unavailable'});$('state').textContent='Could not load token evidence. No transaction was sent. Try again later.';}
  }finally{if(mine===serial)$('refresh').disabled=false;}
}
$('refresh').addEventListener('click',refresh);
helpers.refresh=refresh;
refresh();
})(typeof globalThis==='object'?globalThis:this);
