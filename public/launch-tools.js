/* On-demand tools for the existing one-page app. Nothing submits inference automatically. */
(function(){
  'use strict';
  const el=id=>document.getElementById(id),T=globalThis.SlipvoltRequestTools;
  let serial=0,lastCode=null,activeCheck=null;
  const clear=()=>{serial++;lastCode=null;activeCheck?.abort();activeCheck=null;el('check-request').disabled=false;el('preflight-result').textContent='Check the current request without running the model.';el('preflight-result').removeAttribute('data-verdict');};
  function selected(){return document.querySelector('.model-tab[aria-pressed="true"]')?.dataset.model||'';}
  function modelState(){return typeof S!=='undefined'?S:null;}
  for(const id of ['prompt','output-tokens','existing-key'])el(id)?.addEventListener('input',clear);
  el('model-list')?.addEventListener('click',clear);
  document.addEventListener('slipvolt:account-cleared',clear);
  el('check-request').addEventListener('click',async()=>{
    const button=el('check-request'),state=modelState();
    clear();
    if(document.documentElement.dataset.preview==='offline'){el('preflight-result').textContent='Offline preview. Start the server and sign in to check a request. No inference was sent.';return;}
    const text=el('prompt').value.trim(),key=el('existing-key').value.trim()||state?.key||'';
    if(!text){el('preflight-result').textContent='Write a prompt first.';return;}
    if(key&&!globalThis.SlipvoltCore.isCustomerKey(key)){el('preflight-result').textContent='Use a Slipvolt customer key, never the OpenBroker master key.';return;}
    let output;try{output=requestedOutput();}catch(e){el('preflight-result').textContent=e.message;return;}
    const mine=++serial,epoch=state?.epoch,controller=new AbortController();
    activeCheck=controller;button.disabled=true;lastCode=null;
    const timeoutHandle=setTimeout(()=>controller.abort(new DOMException('The check timed out.','TimeoutError')),15000);
    el('preflight-result').textContent='Checking local limits and funding. No model generation…';
    try{
      const response=await fetch('/api/preflight',{method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json',...(key?{Authorization:'Bearer '+key}:{})},signal:controller.signal,
        body:JSON.stringify({model:selected(),messages:[{role:'user',content:text}],max_tokens:output,stream:!!state?.status?.capabilities?.streaming})});
      const data=await response.json();if(mine!==serial||epoch!==state?.epoch)return;
      if(!response.ok)throw Error(data.error?.message||'Request check unavailable.');
      lastCode=data.reason_code;
      el('preflight-result').dataset.verdict=data.allowed?'fits':'blocked';
      el('preflight-result').textContent=(data.allowed?'Fits the current limits. ':T.explain(data.reason_code)+' ')+
        'Estimated reservation: '+Number(data.estimated_ai_tokens).toLocaleString()+' AI tokens / '+gnk(data.estimated_budget_ngonka)+' GNK. '+
        'Nothing was spent or reserved. Sending checks again.';
    }catch(e){if(mine===serial)el('preflight-result').textContent=e.name==='TimeoutError'?'The check timed out. No inference was requested.':e.message;}
    finally{clearTimeout(timeoutHandle);if(activeCheck===controller){activeCheck=null;button.disabled=false;}}
  });
  function kit(){return T.connectionKit(document.documentElement.dataset.preview==='offline'?'https://YOUR_DEPLOYED_HOST':location.origin,selected());}
  function renderKit(){try{el('connection-kit').textContent=JSON.stringify(kit(),null,2);}catch{el('connection-kit').textContent='Connection settings need the deployed service origin and a selected model.';}}
  el('copy-connection').addEventListener('click',()=>{renderKit();copy(el('connection-kit').textContent);});
  el('connection-details').addEventListener('toggle',renderKit);
  el('model-list').addEventListener('click',renderKit);
  el('review-support').addEventListener('click',()=>{
    const requestId=(el('request-id').textContent||'').replace(/^Request /,'');
    el('support-report').textContent=JSON.stringify(T.supportReport({version:modelState()?.status?.version,selected:selected(),code:lastCode,requestId}),null,2);
    el('support-dialog').showModal();
  });
  el('copy-support').addEventListener('click',()=>copy(el('support-report').textContent));
  el('support-close').addEventListener('click',()=>el('support-dialog').close());
  el('clear-response').addEventListener('click',()=>{
    if(modelState()?.busy){toast('Stop or finish the current request before clearing.');return;}
    el('result').textContent='Your model’s response appears here.';el('result').classList.remove('has-output');el('request-id').textContent='';clear();
  });
  renderKit();
})();
