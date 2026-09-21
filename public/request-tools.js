/* Pure customer helpers. Export only explicitly reviewed diagnostic fields. */
(function(root){
  'use strict';
  const reasons=Object.freeze({
    wallet_allowance_exhausted:'This request exceeds your remaining daily allowance. Reduce input/output or wait for the UTC reset.',
    shared_allowance_exhausted:'The shared daily pool cannot fit this request. Reduce its size or wait for the UTC reset.',
    allowance_pool_unfunded_or_exhausted:'The operator needs to replenish the funded GNK budget. Buying more project tokens will not fix it.',
    broker_balance_too_low:'The provider working balance cannot cover this request. The operator must check funding.',
    reconciliation_required:'An uncertain provider cost needs operator review before requests resume.',
    wallet_rpm_limit:'Wait for your per-minute request limit to reset.',
    global_rpm_limit:'The service request rate is currently full. Try again later.',
    wallet_concurrency_limit:'Wait for one of your running requests to finish.',
    global_concurrency_limit:'Service concurrency is full. Try again after a running request finishes.',
    invalid_key:'This API key is invalid or revoked. Sign in and create a replacement.',
    user_disabled:'This account needs operator review.'
  });
  function connectionKit(origin,model){
    const u=new URL(origin);
    if(!['https:','http:'].includes(u.protocol)||u.username||u.password||u.search||u.hash||u.pathname!=='/'||!u.hostname)throw Error('Use the service origin only.');
    if(u.protocol==='http:'&&!['localhost','127.0.0.1','[::1]'].includes(u.hostname))throw Error('HTTPS required outside localhost.');
    if(typeof model!=='string'||!/^[A-Za-z0-9][A-Za-z0-9_./:+-]{0,149}$/.test(model))throw Error('Select a model.');
    return {base_url:u.origin+'/v1',model,api_key_environment:'SLIPVOLT_API_KEY',api_style:'chat.completions',automatic_retries:0};
  }
  function supportReport(input={}){
    return {schema:'slipvolt.support.v1',created_at:new Date().toISOString(),
      version:/^\d+\.\d+\.\d+$/.test(input.version||'')?input.version:'unknown',
      model:/^[A-Za-z0-9][A-Za-z0-9_./:+-]{0,149}$/.test(input.selected||'')&&!/^(obk-|sv_|grd_|ghp_|sk-)/.test(input.selected)?input.selected:'unknown',
      last_preflight_code:Object.hasOwn(reasons,input.code)?input.code:null,
      request_id:/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(input.requestId||'')?input.requestId:null,
      scope:'Interface diagnostics only; no keys, wallet addresses, prompts, cookies or private endpoints.'};
  }
  async function readCompletionStream(response,onText){
    if(!response.body)throw Error('Streaming response body is unavailable.');
    const reader=response.body.getReader(),decoder=new TextDecoder('utf-8',{fatal:true});
    let line='',data=[],skipLF=false,output='',complete=false,received=0,lastRendered='';
    const limit=2000000;
    function endLine(){
      if(line===''){
        if(data.length){
          const value=data.join('\n');data=[];
          if(value==='[DONE]'){complete=true;return;}
          const event=JSON.parse(value);
          if(event.error)throw Error(typeof event.error.message==='string'?event.error.message:'The provider reported an error.');
          const text=event.choices?.[0]?.delta?.content;
          if(text!==null&&text!==undefined){
            if(typeof text!=='string')throw Error('Invalid streamed text.');
            output+=text;
            if(output.length>limit)throw Error('Response too large.');
          }
        }
      }else if(line.startsWith('data:')){
        let value=line.slice(5);if(value.startsWith(' '))value=value.slice(1);
        data.push(value);
      }else if(line==='data')data.push('');
      line='';
    }
    function consume(text){
      // CR, LF and CRLF are valid SSE line endings, even across byte chunks.
      for(const char of text){
        if(skipLF){skipLF=false;if(char==='\n')continue;}
        if(char==='\r'||char==='\n'){
          endLine();skipLF=char==='\r';
          if(complete)break;
        }else line+=char;
      }
    }
    try{
      while(!complete){
        const {value,done}=await reader.read();
        received+=value?.byteLength||0;
        if(received>limit)throw Error('Response too large.');
        consume(decoder.decode(value||new Uint8Array(),{stream:!done}));
        // A read can contain hundreds of events; update the page just once.
        if(output!==lastRendered){onText(output);lastRendered=output;}
        if(done)break;
      }
      if(!complete)throw Error('Stream ended without confirmation. Check usage before retrying.');
      return output;
    }finally{
      try{await reader.cancel();}catch{ /* Keep the original result/error. */ }
      reader.releaseLock();
    }
  }
  const api={connectionKit,supportReport,readCompletionStream,explain:code=>reasons[code]||'Request status is unknown or unavailable. Check the service status before retrying.'};
  root.SlipvoltRequestTools=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(globalThis);
