/* Pure shared browser logic. No network calls, credentials or side effects. */
(function(root,factory){const core=factory();if(typeof module==='object'&&module.exports)module.exports=core;else root.SlipvoltCore=core;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const WGNK='0x972a7a92d92796a98801a8818bcf91f1648f2f68';
  function number(value,max=1e12){
    if(value===null||value===undefined||String(value).trim()==='')throw new Error('Enter a value in every field.');
    const n=Number(value);if(!Number.isFinite(n)||n<0||n>max)throw new Error('Use a finite, non-negative number within the displayed limits.');
    return n;
  }
  function compare(input,output,rate,referenceInput,referenceOutput){
    input=number(input,1e9);output=number(output,1e9);rate=number(rate,1000);
    const service=(input+output)*rate;
    const reference=referenceInput==null||referenceOutput==null?null:input*number(referenceInput)+output*number(referenceOutput);
    const saved=reference==null?null:reference-service;
    return {service,reference,saved,percent:reference>0?saved/reference*100:null,tokens:input+output};
  }
  function treasury(values){
    const volume=number(values.volume,1e10),fee=number(values.fee,10),earned=number(values.earned,1e9),costs=number(values.costs,1e9),reserves=number(values.reserves,1e9);
    const fees=volume*fee/100,revenue=fees+earned,net=revenue-costs-reserves;
    // Integer cents: never allocate cash that does not exist; residual goes to compute.
    const cents=Math.max(0,Math.floor((net+1e-9)*100));
    const wgnk=Math.floor(cents*30/100),developer=Math.floor(cents*20/100),compute=cents-wgnk-developer;
    return {fees,revenue,net,surplus:cents/100,compute:compute/100,wgnk:wgnk/100,developer:developer/100,scenario_only:true,executable:false};
  }
  function publicKey(value){
    const alphabet='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
    if(typeof value!=='string'||value.length<32||value.length>44)throw new Error('Enter the exact SPL mint address, not a ticker.');
    let n=0n;for(const c of value){const x=alphabet.indexOf(c);if(x<0)throw new Error('Invalid base58 mint address.');n=n*58n+BigInt(x);}
    let bytes=0;while(n>0n){bytes++;n>>=8n;}
    for(const c of value){if(c!=='1')break;bytes++;}
    if(bytes!==32)throw new Error('The mint must decode to exactly 32 bytes.');
    return value;
  }
  function route(source,target,amount,mint){
    if(!['SOL','USDC','SPL'].includes(source)||!['GNK','WGNK'].includes(target))throw new Error('Select SOL/SPL and an official destination asset.');
    if(number(amount,1e9)<=0)throw new Error('Amount must be greater than zero.');
    if(source==='SPL')publicKey(mint);
    const steps=[];
    if(source!=='USDC')steps.push({asset:'USDC',chain:'Solana',description:'Quote '+source+' → native USDC on Solana. A liquid market and SOL for fees are required.'});
    steps.push({asset:'USDC',chain:'Ethereum',description:'Use a verified cross-chain route. Receive USDC in your own Ethereum wallet, never directly at the Gonka bridge.'});
    steps.push({asset:'WGNK',chain:'Ethereum',description:'Quote USDC → the official WGNK contract. Verify minimum output, exact token address and ETH for fees.'});
    if(target==='GNK')steps.push({asset:'GNK',chain:'Gonka',description:'Use the official Gonka dashboard with the matching signing key. After receipt, send native GNK to your actual OpenBroker deposit address.'});
    return {source,target,amount:String(amount),source_mint:mint||null,steps,executable:false,quote_status:'not_requested',destination_contract:WGNK};
  }
  function escape(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function isCustomerKey(value){return /^(sv_|grd_)[A-Za-z0-9_-]{20,96}$/.test(value);}
  return {number,compare,treasury,route,escape,isCustomerKey,WGNK};
});
