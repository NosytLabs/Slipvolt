/* Exact, read-only token-account observations. Never creates a transaction. */
(function(root){
  'use strict';
  const reasons=Object.freeze({frozen:'Frozen',native:'Wrapped native asset',delegated:'Delegate authority present',empty:'Empty',close_authority:'Different close authority',unsupported_extension:'Unsupported extension or layout'});
  const address=v=>typeof v==='string'&&/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(v);
  const quantity=v=>{if(typeof v!=='string'||!/^(0|[1-9][0-9]{0,19})$/.test(v)||BigInt(v)>18446744073709551615n)throw Error('Invalid account amount.');return BigInt(v);};
  function reason(value){if(!Object.hasOwn(reasons,value))throw Error('Unknown account restriction.');return reasons[value];}
  function format(value,decimals){
    const n=quantity(value);if(!Number.isInteger(decimals)||decimals<0||decimals>18)throw Error('Invalid token precision.');
    const scale=10n**BigInt(decimals),tail=(n%scale).toString().padStart(decimals,'0').replace(/0+$/,'');
    return (n/scale).toLocaleString('en')+(tail?'.'+tail:'');
  }
  function normalize(value,config){
    if(!value||!config||value.schema!=='holdbyte.treasury-accounts.v1'||
      value.treasury_owner!==config.treasury_owner||value.mint!==config.mint||value.decimals!==config.decimals||
      !address(value.treasury_owner)||!address(value.mint)||value.execution_enabled!==false||value.transactions_sent!==0||
      !Number.isInteger(value.decimals)||value.decimals<0||value.decimals>18||
      !['TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'].includes(value.token_program)||
      !Number.isSafeInteger(value.listing_slot)||value.listing_slot<1||!Number.isSafeInteger(value.reference_slot)||value.reference_slot<value.listing_slot||
      !Array.isArray(value.accounts)||value.accounts.length>128)throw Error('Account response does not match this treasury.');
    const seen=new Set();let total=0n;
    const accounts=value.accounts.map(row=>{
      if(!row||!address(row.address)||row.address===value.mint||row.address===value.treasury_owner||seen.has(row.address)||typeof row.review_eligible!=='boolean')throw Error('Invalid or duplicate account.');
      seen.add(row.address);const amount=quantity(row.balance_raw);total+=amount;
      if(row.reason!==null)reason(row.reason);
      if(row.review_eligible!==(row.reason===null&&amount>0n)||row.reason===null&&amount===0n||row.reason==='empty'&&amount!==0n)throw Error('Inconsistent account state.');
      return {address:row.address,balance_raw:row.balance_raw,review_eligible:row.review_eligible,reason:row.reason};
    });
    if(quantity(value.total_raw)!==total)throw Error('Inconsistent account total.');
    return {accounts,decimals:value.decimals,listing_slot:value.listing_slot,reference_slot:value.reference_slot,total_raw:value.total_raw};
  }
  const api=Object.freeze({normalize,format,reason});root.HoldbyteTreasuryAccounts=api;
  if(typeof module==='object'&&module.exports)module.exports=api;
})(typeof globalThis==='object'?globalThis:this);
