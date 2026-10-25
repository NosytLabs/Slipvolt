/* Operator review only. No wallet adapter, signing, persistent secrets or broadcast. */
(function(){
  'use strict';
  function start(){
    const $=id=>document.getElementById(id),S={serial:0,controller:null,busy:false,config:null,plan:null,timer:null};
    const address=v=>typeof v==='string'&&/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(v);
    const raw=(v,d)=>{
      if(typeof v!=='string'||!/^\d{1,20}(?:\.\d{1,18})?$/.test(v)||!Number.isInteger(d)||d<0||d>18)throw Error('Invalid token amount.');
      const [whole,fraction='']=v.split('.');if(fraction.length>d)throw Error('Amount exceeds token precision.');
      const n=BigInt(whole)*10n**BigInt(d)+BigInt(fraction.padEnd(d,'0')||'0');if(n<=0n||n>18446744073709551615n)throw Error('Amount is outside the token range.');return n.toString();
    };
    const format=(v,d)=>{if(typeof v!=='string'||!/^\d+$/.test(v))throw Error('Invalid amount in response.');const n=BigInt(v),scale=10n**BigInt(d),tail=(n%scale).toString().padStart(d,'0').replace(/0+$/,'');return (n/scale).toLocaleString('en')+(tail?'.'+tail:'');};
    function sync(){
      $('unlock').disabled=S.busy;
      $('prepare').disabled=S.busy||S.config?.planning_enabled!==true;
      $('verify-receipt').disabled=S.busy||!S.config;
      $('download-plan').disabled=!S.plan||S.busy||Math.floor(Date.now()/1000)>=S.plan.local_review_expires_at;
    }
    function cancel(){S.serial++;S.controller?.abort();S.controller=null;S.busy=false;sync();}
    function clearPlan(){clearTimeout(S.timer);S.timer=null;S.plan=null;$('review').hidden=true;$('plan-json').textContent='';$('warnings').replaceChildren();for(const id of ['amount-review','balance-review','remaining-review','slot-review'])$(id).textContent='—';sync();}
    function reset(){cancel();clearPlan();S.config=null;for(const id of ['source-account','burn-amount','signature'])$(id).value='';$('project-owned').checked=false;$('treasury-owner').textContent='Not loaded';$('project-mint').textContent='Not loaded';$('receipt-status').textContent='No receipt submitted.';$('plan-status').textContent='Load treasury configuration first.';sync();}
    function key(){const v=$('operator-key').value.trim();if(!v||v.startsWith('obk-')||v.startsWith('sv_')||v.startsWith('grd_'))throw Error('Use the separate admin API key, not a provider or customer key.');return v;}
    async function run(path,body,output,done){
      let secret;try{secret=key();}catch(e){$(output).textContent=e.message;return;}
      cancel();const serial=S.serial,controller=new AbortController();S.controller=controller;S.busy=true;sync();
      const timeout=setTimeout(()=>controller.abort(),25000);$(output).textContent='Checking…';
      try{
        const r=await fetch(path,{method:body===null?'GET':'POST',credentials:'omit',cache:'no-store',signal:controller.signal,
          headers:{Authorization:'Bearer '+secret,...(body===null?{}:{'Content-Type':'application/json'})},...(body===null?{}:{body:JSON.stringify(body)})});
        if(!r.ok)throw Error('Request failed ('+r.status+'). Check configuration, permissions and source account. No transaction was sent.');
        const text=await r.text();if(text.length>50000)throw Error('Unexpected response size.');const value=JSON.parse(text);
        if(serial!==S.serial)return;done(value);
      }catch(e){if(serial===S.serial)$(output).textContent=e.name==='AbortError'?'Request stopped or timed out. Check recorded receipts before retrying.':e instanceof SyntaxError?'Invalid service response.':e.message;}
      finally{clearTimeout(timeout);if(serial===S.serial){S.controller=null;S.busy=false;sync();}}
    }
    $('operator-key').addEventListener('input',()=>{reset();$('access-status').textContent='Credential changed. Reload treasury configuration.';});
    $('lock').addEventListener('click',()=>{reset();$('operator-key').value='';$('access-status').textContent='Locked. Credentials and review data cleared from this tab.';});
    $('unlock').addEventListener('click',()=>{
      reset();run('/api/admin/treasury',null,'access-status',value=>{
        if(!value||typeof value.planning_enabled!=='boolean'||value.signing_enabled!==false||
          (value.treasury_owner!==null&&!address(value.treasury_owner))||(value.mint!==null&&!address(value.mint))||
          !Number.isInteger(value.decimals)||value.decimals<0||value.decimals>18)throw Error('Invalid treasury configuration response.');
        S.config=value;$('treasury-owner').textContent=value.treasury_owner||'Not configured';$('project-mint').textContent=value.mint||'Not configured';
        $('access-status').textContent='Operator access loaded. Signing and execution are disabled.';
        $('plan-status').textContent=value.planning_enabled?'Enter a project-owned treasury token account and amount.':'Set SOLANA_TREASURY_OWNER, the project mint and RPC on the server.';
      });
    });
    for(const id of ['source-account','burn-amount','project-owned'])$(id).addEventListener('input',()=>{cancel();clearPlan();$('plan-status').textContent='Inputs changed. Prepare a fresh instruction before export.';});
    $('plan-form').addEventListener('submit',event=>{
      event.preventDefault();clearPlan();if(!S.config?.planning_enabled)return;
      const source=$('source-account').value.trim(),amount=$('burn-amount').value,config=S.config;
      if(!address(source)||!$('project-owned').checked){$('plan-status').textContent='Enter a token account and confirm project ownership.';return;}
      let expected;try{expected=raw(amount,config.decimals);}catch(e){$('plan-status').textContent=e.message;return;}
      run('/api/admin/treasury/burn-plan',{source_account:source,amount,confirm_project_owned:true},'plan-status',value=>{
        const now=Math.floor(Date.now()/1000),ix=value?.instruction;
        if(!value||value.schema!=='holdbyte.burn-instruction.v1'||value.unsigned!==true||value.transactions_sent!==0||value.simulation_performed!==false||
          value.amount_raw!==expected||value.mint!==config.mint||value.source_account!==source||value.treasury_owner!==config.treasury_owner||value.decimals!==config.decimals||
          !Number.isSafeInteger(value.created_at)||!Number.isSafeInteger(value.local_review_expires_at)||value.created_at>now+5||
          value.local_review_expires_at!==value.created_at+60||value.local_review_expires_at<=now||!ix||ix.program_id!==value.token_program||
          !['TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'].includes(ix.program_id)||
          JSON.stringify(ix.accounts)!==JSON.stringify([{pubkey:source,is_signer:false,is_writable:true},{pubkey:config.mint,is_signer:false,is_writable:true},{pubkey:config.treasury_owner,is_signer:true,is_writable:false}])||
          !Array.isArray(value.warnings)||!value.warnings.every(x=>typeof x==='string'&&x.length<1000))throw Error('Burn proposal does not match the reviewed inputs.');
        const data=Uint8Array.from(atob(ix.data_base64),x=>x.charCodeAt(0));let n=BigInt(expected);
        if(data.length!==10||data[0]!==15||data[9]!==config.decimals)throw Error('Invalid burn instruction encoding.');
        for(let i=1;i<=8;i++){if(data[i]!==Number(n&255n))throw Error('Burn instruction amount mismatch.');n>>=8n;}
        const rendered=[format(value.amount_raw,value.decimals),format(value.source_balance_raw,value.decimals),format(value.expected_source_remaining_raw,value.decimals)];
        S.plan=value;$('amount-review').textContent=rendered[0];$('balance-review').textContent=rendered[1];$('remaining-review').textContent=rendered[2];$('slot-review').textContent=String(value.snapshot_slot);
        for(const text of value.warnings){const li=document.createElement('li');li.textContent=text;$('warnings').append(li);}
        $('plan-json').textContent=JSON.stringify(value,null,2);$('review').hidden=false;$('plan-status').textContent='Unsigned instruction ready for review. Nothing was signed or sent.';
        S.timer=setTimeout(()=>{$('plan-status').textContent='Review expired. Prepare a fresh instruction before signing elsewhere.';sync();},Math.max(0,value.local_review_expires_at*1000-Date.now()));
      });
    });
    $('download-plan').addEventListener('click',()=>{
      sync();if($('download-plan').disabled)return;
      const url=URL.createObjectURL(new Blob([JSON.stringify(S.plan,null,2)+'\n'],{type:'application/json'})),link=document.createElement('a');
      link.href=url;link.download='holdbyte-burn-instruction.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),0);
    });
    $('receipt-form').addEventListener('submit',event=>{
      event.preventDefault();const signature=$('signature').value.trim();if(!S.config)return;
      if(!/^[1-9A-HJ-NP-Za-km-z]{64,88}$/.test(signature)){$('receipt-status').textContent='Enter an existing Solana transaction signature.';return;}
      run('/api/admin/token/burns',{signature},'receipt-status',value=>{
        if(!value||typeof value.recorded!=='boolean'||value.transactions_sent!==0||value.receipt?.signature!==signature)throw Error('Unexpected receipt response. Check the token dashboard.');
        $('receipt-status').textContent=value.recorded?'Finalized burn recorded. No transaction was sent by this page.':'This burn was already recorded. Totals were not increased.';
      });
    });
    $('signature').addEventListener('input',()=>{cancel();$('receipt-status').textContent='No receipt submitted for this signature.';});
    sync();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
