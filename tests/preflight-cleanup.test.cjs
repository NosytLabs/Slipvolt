'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const tools=require('../public/request-tools.js');
const core=require('../public/core.js');

function setup({model='MiniMaxAI/MiniMax-M2.7'}={}){
  const elements=new Map(),listeners=new Map(),calls=[];
  function el(id){
    if(!elements.has(id))elements.set(id,{value:'',textContent:'',disabled:false,dataset:{},handlers:{},
      classList:{remove(){}},addEventListener(type,fn){this.handlers[type]=fn},
      removeAttribute(name){if(name==='data-verdict')delete this.dataset.verdict},showModal(){},close(){}});
    return elements.get(id);
  }
  const ctx={AbortController,AbortSignal,URL,DOMException,setTimeout,clearTimeout,SlipvoltRequestTools:tools,SlipvoltCore:core,
    S:{epoch:1,key:'sv_'+'a'.repeat(43),status:{}},location:{origin:'https://slipvolt.test'},
    requestedOutput:()=>512,gnk:n=>n===null||n===undefined?'Unavailable':String(n),copy(){},toast(){},
    conversationMessages:prompt=>core.chatMessages([{user:'earlier prompt',assistant:'earlier answer'}],prompt),clearVisibleResponse(){},renderConversationContext(){},
    document:{documentElement:{dataset:{}},getElementById:el,
      querySelector:()=>model?{dataset:{model}}:null,addEventListener(type,fn){listeners.set(type,fn)}},
    fetch(path,options){return new Promise((resolve,reject)=>{calls.push({path,options,resolve,reject});options.signal.addEventListener('abort',()=>reject(options.signal.reason),{once:true});})}};
  vm.createContext(ctx);vm.runInContext(fs.readFileSync('public/launch-tools.js','utf8'),ctx);
  el('prompt').value='test prompt';
  el('output-tokens').max='16384';
  const click=()=>el('check-request').handlers.click();
  const respond=(index,ok=true)=>calls[index].resolve(new Response(ok?JSON.stringify({allowed:true,estimated_ai_tokens:1000,estimated_budget_ngonka:15000}):JSON.stringify({error:{message:'Unavailable'}}),{status:ok?200:503,headers:{'content-type':'application/json'}}));
  return {el,calls,click,respond,clearAccount:()=>listeners.get('slipvolt:account-cleared')(),conversationChanged:()=>listeners.get('slipvolt:conversation-changed')()};
}
test('editing aborts obsolete request checks and restores the button',async()=>{
  const t=setup(),pending=t.click();assert(t.el('check-request').disabled);
  t.el('prompt').handlers.input();
  assert(t.calls[0].options.signal.aborted);assert.equal(t.el('check-request').disabled,false);
  await pending;
  assert.match(t.el('preflight-result').textContent,/without running/);
});
test('preflight uses the same full conversation message builder as inference',async()=>{
  const t=setup(),pending=t.click();
  const payload=JSON.parse(t.calls[0].options.body);
  assert.deepEqual(payload.messages,[
    {role:'user',content:'earlier prompt'},
    {role:'assistant',content:'earlier answer'},
    {role:'user',content:'test prompt'}
  ]);
  t.respond(0);await pending;
});
test('an earlier success cannot remain green during a retry or failed check',async()=>{
  const t=setup(),first=t.click();t.respond(0);await first;
  assert.equal(t.el('preflight-result').dataset.verdict,'fits');
  const second=t.click();assert.equal(t.el('preflight-result').dataset.verdict,undefined);
  t.respond(1,false);await second;
  assert.equal(t.el('preflight-result').dataset.verdict,undefined);
  assert.equal(t.el('preflight-result').textContent,'Unavailable');
});
test('aborted check cannot re-enable a newer pending check',async()=>{
  const t=setup(),first=t.click();t.el('prompt').handlers.input();const second=t.click();
  // This also lets the previous promise catch/finally run.
  t.respond(0);await first;
  assert.equal(t.el('check-request').disabled,true);
  t.respond(1);await second;assert.equal(t.el('check-request').disabled,false);
});
test('account change aborts check and never restores the old result',async()=>{
  const t=setup(),pending=t.click();t.clearAccount();
  assert(t.calls[0].options.signal.aborted);t.respond(0);await pending;
  assert.equal(t.el('preflight-result').dataset.verdict,undefined);
  assert.match(t.el('preflight-result').textContent,/without running/);
});
test('a completed chat turn invalidates an in-flight check built from older history',async()=>{
  const t=setup(),pending=t.click();t.conversationChanged();
  assert(t.calls[0].options.signal.aborted);t.respond(0);await pending;
  assert.equal(t.el('preflight-result').dataset.verdict,undefined);
  assert.match(t.el('preflight-result').textContent,/without running/);
});
test('preflight does not send an invalid empty model',async()=>{
  const t=setup({model:''});
  await t.click();
  assert.equal(t.calls.length,0);
  assert.match(t.el('preflight-result').textContent,/model/i);
});
test('non-JSON preflight failures remain safe and actionable',async()=>{
  const t=setup(),pending=t.click();
  t.calls[0].resolve(new Response('<h1>proxy failure with private detail</h1>',{status:502,headers:{'content-type':'text/html'}}));
  await pending;
  assert.match(t.el('preflight-result').textContent,/Request failed \(502\)/);
  assert.doesNotMatch(t.el('preflight-result').textContent,/private detail/);
});
test('unknown preflight estimates are never rendered as measured zero',async()=>{
  const t=setup(),pending=t.click();
  t.calls[0].resolve(new Response(JSON.stringify({allowed:true,reason_code:'ok',estimated_ai_tokens:null,estimated_budget_ngonka:null}),{status:200,headers:{'content-type':'application/json'}}));
  await pending;
  assert.match(t.el('preflight-result').textContent,/Unavailable AI tokens \/ Unavailable GNK/);
  assert.doesNotMatch(t.el('preflight-result').textContent,/0 AI tokens/);
});
test('editing cannot re-enable preflight when the selected model has no usable output cap',async()=>{
  const t=setup();
  t.el('output-tokens').disabled=true;
  t.el('prompt').handlers.input();
  assert.equal(t.el('check-request').disabled,true);
  await t.click();
  assert.equal(t.calls.length,0);
  assert.match(t.el('preflight-result').textContent,/limit|model/i);
});
