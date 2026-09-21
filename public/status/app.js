'use strict';
(function(){
 const el=id=>document.getElementById(id),write=(id,value)=>{el(id).textContent=value;};
 const amount=value=>{try{if(!/^\d{1,20}$/.test(String(value)))return 'Unavailable';const n=BigInt(value);return (n/1000000000n).toLocaleString()+(n%1000000000n?'.'+(n%1000000000n).toString().padStart(9,'0').replace(/0+$/,''):'')+' GNK';}catch{return 'Unavailable';}};
 const num=n=>Number.isSafeInteger(n)&&n>=0?n.toLocaleString():'Unreported';
 const states=new Set(['healthy','degraded','unavailable','listed','unverified']);
 async function read(path){const r=await fetch(path,{credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(12000)});if(!r.ok)throw Error('Unavailable');return r.json();}
 function reset(){for(const id of ['service-state','reserve-value','provider-value','network-value'])write(id,'Checking…');write('service-detail','');write('service-limits','');write('mint-detail','');write('catalog-source','Checking the current catalog…');el('status-models').replaceChildren();write('network-detail','Provider-wide activity, not Slipvolt usage.');}
 async function refresh(){el('status-refresh').disabled=true;reset();let failures=0;
  const results=await Promise.allSettled(['/api/status','/api/models','/api/treasury','/api/network'].map(read));
  const get=i=>{if(results[i].status==='fulfilled'&&results[i].value&&typeof results[i].value==='object')return results[i].value;failures++;return null;};
  const s=get(0);
  if(s){write('service-state',s.maintenance_mode?'Maintenance':s.holder_gate_configured&&s.provider_configured?'Configured · not launch-certified':'Setup incomplete');write('service-detail',s.billing_review_required?'Provider cost reconciliation is blocking new calls.':'Holding unlocks a funded allowance. No token purchase or overage checkout is enabled here.');write('service-limits',num(s.holder_daily_tokens)+' AI tokens per wallet/day · '+num(s.global_daily_tokens)+' shared/day. Reset: 00:00 UTC.');if(typeof s.holder_mint==='string'&&/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(s.holder_mint))write('mint-detail','Configured Solana mint: '+s.holder_mint);else write('mint-detail','No project mint published. Do not buy a ticker-only imitation.');}
  else{write('service-state','Unavailable');write('service-detail','The service configuration could not be read.');}
  const m=get(1);if(m&&Array.isArray(m.data)){write('catalog-source',m.live?'Live catalog read · inference not benchmarked':'Snapshot only · availability not verified');for(const row of m.data.slice(0,100)){if(typeof row.id!=='string')continue;const item=document.createElement('div');item.className='status-model';const name=document.createElement('strong');name.textContent=row.name||row.id;const detail=document.createElement('span');const health=states.has(row.availability)?row.availability:'unverified';detail.textContent=health+' · '+num(row.context_length)+' context · '+num(row.max_completion_tokens)+' max output';item.append(name,detail);el('status-models').append(item);}}
  else write('catalog-source','Catalog unavailable. No live availability claim.');
  const t=get(2);write('reserve-value',t?.self_custody_balance?amount(t.self_custody_balance.amount_ngonka):!t||t.self_custody_status==='unavailable'?'Unavailable':'Not published');write('provider-value',t?.broker_balance?amount(t.broker_balance.available_ngonka):!t||t.status==='unavailable'?'Unavailable':'Not published');
  const n=get(3);if(n?.totals){write('network-value',num(n.totals.requests)+' requests');write('network-detail',(n.stale?'Stale snapshot. ':'')+num(n.totals.tokens)+' AI tokens across all returned provider records. Not Slipvolt activity.');}else{write('network-value','Unavailable');write('network-detail','No usable provider network snapshot was returned.');}
  write('status-observed','Checked '+new Date().toLocaleTimeString()+(failures?' · '+failures+' source(s) unavailable':' · read-only'));el('status-refresh').disabled=false;
 }
 el('status-refresh').addEventListener('click',()=>refresh().catch(()=>{write('status-observed','Status check failed. No inference sent.');el('status-refresh').disabled=false;}));
 refresh().catch(()=>{write('status-observed','Status check failed. No inference sent.');el('status-refresh').disabled=false;});
})();
