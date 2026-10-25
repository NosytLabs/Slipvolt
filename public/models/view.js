/* Policy metadata is not proof of paid inference or a provider boundary test. */
(function(root){
  'use strict';
  function text(value,fallback='',maximum=1000){
    if(value===undefined||value===null)return fallback;
    if(typeof value!=='string'||value.length>maximum||/[\u0000-\u001f\u007f]/.test(value))throw Error('Invalid catalog text.');
    return value.trim()||fallback;
  }
  function limit(value){
    if(value===undefined||value===null||value===0)return null;
    if(!Number.isSafeInteger(value)||value<1||value>1048576)throw Error('Invalid model limit.');
    return value;
  }
  function catalog(value){
    if(!value||typeof value.live!=='boolean'||!Array.isArray(value.data)||value.data.length>64)throw Error('Invalid model catalog.');
    const seen=new Set();
    const models=value.data.map(row=>{
      if(!row||typeof row!=='object')throw Error('Invalid model entry.');
      const id=text(row.id,'',150);if(!id||seen.has(id))throw Error('Missing or duplicate model ID.');seen.add(id);
      const context=limit(row.context_length),output=limit(row.max_completion_tokens),defaultOutput=limit(row.default_completion_tokens);
      if(output!==null&&context!==null&&output>context||defaultOutput!==null&&output!==null&&defaultOutput>output)throw Error('Inconsistent model limits.');
      return {id,name:text(row.name,id,200),category:text(row.category||row.label,'Text generation',200),
        context,output,defaultOutput,discoveredContext:limit(row.discovered_context_length),discoveredOutput:limit(row.discovered_max_completion_tokens),
        availability:['healthy','degraded','unavailable','listed','unverified'].includes(row.availability)?row.availability:'unverified',
        routable:typeof row.routable==='boolean'?row.routable:null,override:row.operator_override_configured===true,
        source:text(row.limits_source,'Source not provided'),contextSource:text(row.context_limit_source,'Not provided'),
        outputSource:text(row.completion_limit_source,'Not provided')};
    });
    return {live:value.live,source:text(value.source,'Source not provided'),inferenceTested:value.inference_tested===true,models};
  }
  function status(model,live){return !live?'Snapshot only':model.routable===false||model.availability==='unavailable'?'Unavailable':model.availability==='degraded'?'Degraded':'Listed';}
  function filter(value,query,mode='all'){
    const needle=String(query||'').trim().toLowerCase();
    return value.models.filter(model=>(model.id+' '+model.name+' '+model.category).toLowerCase().includes(needle)&&
      (mode!=='listed'||value.live&&model.routable!==false&&model.availability!=='unavailable'));
  }
  const api=Object.freeze({catalog,status,filter});root.HoldbyteModelDirectory=api;
  if(typeof module==='object'&&module.exports)module.exports=api;
})(typeof globalThis==='object'?globalThis:this);
