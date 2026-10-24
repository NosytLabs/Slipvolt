/* Pure shared browser logic. No network calls, credentials or side effects. */
(function(root,factory){const core=factory();if(typeof module==='object'&&module.exports)module.exports=core;else root.SlipvoltCore=core;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  function escape(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function isCustomerKey(value){return /^(sv_|grd_)[A-Za-z0-9_-]{20,96}$/.test(value);}

  function safeCount(value){return Number.isSafeInteger(value)&&value>=0?value:null;}
  function selectableModelId(models,current){
    const usable=model=>model&&typeof model.id==='string'&&model.id.length>0&&model.availability!=='unavailable'&&model.routable!==false;
    const rows=Array.isArray(models)?models:[];
    return rows.find(model=>model.id===current&&usable(model))?.id||rows.find(usable)?.id||'';
  }
  function summarizeUsage(rows){
    const items=Array.isArray(rows)?rows:[],models=new Map();
    const summary={requests:0,settled:0,inFlight:0,needsReview:0,recentTokens:0,recentCostNgonka:0,models:[]};
    for(const row of items){
      if(!row||typeof row!=='object')continue;
      summary.requests++;
      const state=typeof row.state==='string'?row.state:'unknown';
      if(state==='settled')summary.settled++;
      if(state==='reserved')summary.inFlight++;
      if(state==='needs_review')summary.needsReview++;
      const tokens=safeCount(row.tokens);
      const cost=safeCount(row.cost_ngonka);
      if(tokens!==null)summary.recentTokens+=tokens;
      if(cost!==null)summary.recentCostNgonka+=cost;
      if(tokens!==null&&typeof row.model==='string'&&row.model.length>0&&row.model.length<=150){
        models.set(row.model,(models.get(row.model)||0)+tokens);
      }
    }
    summary.models=[...models].map(([model,tokens])=>({model,tokens})).sort((a,b)=>b.tokens-a.tokens||a.model.localeCompare(b.model));
    return summary;
  }

  function chatMessages(turns,prompt){
    const messages=[];
    for(const turn of Array.isArray(turns)?turns:[]){
      if(!turn||typeof turn.user!=='string'||typeof turn.assistant!=='string'||!turn.user.trim()||!turn.assistant.trim())continue;
      messages.push({role:'user',content:turn.user},{role:'assistant',content:turn.assistant});
    }
    if(typeof prompt==='string'&&prompt.trim())messages.push({role:'user',content:prompt.trim()});
    return messages;
  }

  function appendChatTurn(turns,user,assistant,limits={}){
    const maxTurns=Number.isSafeInteger(limits.maxTurns)&&limits.maxTurns>0?limits.maxTurns:24;
    const maxChars=Number.isSafeInteger(limits.maxChars)&&limits.maxChars>0?limits.maxChars:250000;
    const next=[];
    for(const turn of Array.isArray(turns)?turns:[]){
      if(turn&&typeof turn.user==='string'&&typeof turn.assistant==='string'&&turn.user.trim()&&turn.assistant.trim())next.push({user:turn.user,assistant:turn.assistant});
    }
    if(typeof user!=='string'||typeof assistant!=='string'||!user.trim()||!assistant.trim()){
      const characters=next.reduce((sum,turn)=>sum+turn.user.length+turn.assistant.length,0);
      return {turns:next,dropped:0,retained:false,full:next.length>=maxTurns||characters>=maxChars};
    }
    next.push({user:user.trim(),assistant:assistant.trim()});
    const characters=next.reduce((sum,turn)=>sum+turn.user.length+turn.assistant.length,0);
    return {turns:next,dropped:0,retained:true,full:next.length>=maxTurns||characters>=maxChars};
  }

  function chatStats(turns){
    const valid=(Array.isArray(turns)?turns:[]).filter(turn=>turn&&typeof turn.user==='string'&&typeof turn.assistant==='string'&&turn.user.trim()&&turn.assistant.trim());
    return {turns:valid.length,characters:valid.reduce((sum,turn)=>sum+turn.user.length+turn.assistant.length,0)};
  }

  function chatTranscript(turns){
    const messages=chatMessages(turns,'');
    return messages.map(message=>(message.role==='user'?'You':'Assistant')+'\n'+message.content).join('\n\n');
  }

  async function readApiResponse(response){
    const contentType=(response.headers?.get?.('content-type')||'').toLowerCase();
    let data=null,raw='';
    if(response.status!==204){
      raw=await response.text();
      if(raw&&contentType.includes('application/json')){
        try{data=JSON.parse(raw);}catch{data=null;}
      }
    }
    if(!response.ok){
      const message=(data&&typeof data.error?.message==='string'&&data.error.message.trim())||
        (data&&typeof data.error==='string'&&data.error.trim())||
        `Request failed (${response.status}).`;
      const err=new Error(message);err.status=response.status;throw err;
    }
    if(response.status===204||raw==='')return null;
    if(data!==null)return data;
    const err=new Error('The server returned an invalid response.');err.status=response.status;throw err;
  }
  return {appendChatTurn,chatMessages,chatStats,chatTranscript,escape,isCustomerKey,readApiResponse,safeCount,selectableModelId,summarizeUsage};
});
