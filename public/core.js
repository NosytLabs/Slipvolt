/* Pure shared browser logic. No network calls, credentials or side effects. */
(function(root,factory){const core=factory();if(typeof module==='object'&&module.exports)module.exports=core;else root.SlipvoltCore=core;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  function escape(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function isCustomerKey(value){return /^(sv_|grd_)[A-Za-z0-9_-]{20,96}$/.test(value);}

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
  return {escape,isCustomerKey,readApiResponse};
});
