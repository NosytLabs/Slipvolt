'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const tools=require('../public/request-tools.js');
const core=require('../public/core.js');

function setup(){
  const elements=new Map(),listeners=new Map(),calls=[];
  function el(id){
    if(!elements.has(id))elements.set(id,{value:'',textContent:'',disabled:false,dataset:{},handlers:{},
      classList:{remove(){}},addEventListener(type,fn){this.handlers[type]=fn},
      removeAttribute(name){if(name==='data-verdict')delete this.dataset.verdict},showModal(){},close(){}});
    return elements.get(id);
  }
  const model='MiniMaxAI/MiniMax-M2.7';
  const ctx={AbortController,AbortSignal,URL,DOMException,setTimeout,clearTimeout,SlipvoltRequestTools:tools,SlipvoltCore:core,
    S:{epoch:1,key:'sv_'+'a'.repeat(43),status:{}},location:{origin:'https://slipvolt.test'},
    requestedOutput:()=>512,gnk:n=>String(n),copy(){},toast(){},
    document:{documentElement:{dataset:{}},getElementById:el,
      querySelector:()=>({dataset:{model}}),addEventListener(type,fn){listeners.set(type,fn)}},
    fetch(path,options){return new Promise((resolve,reject)=>{calls.push({path,options,resolve,reject});options.signal.addEventListener('abort',()=>reject(options.signal.reason),{once:true});})}};
  vm.createContext(ctx);vm.runInContext(fs.readFileSync('public/launch-tools.js','utf8'),ctx);
  el('prompt').value='test prompt';
  const click=()=>el('check-request').handlers.click();
  const respond=(index,ok=true)=>calls[index].resolve({ok,json:async()=>ok?{allowed:true,estimated_ai_tokens:1000,estimated_budget_ngonka:15000}:{error:{message:'Unavailable'}}});
  return {el,calls,click,respond,clearAccount:()=>listeners.get('slipvolt:account-cleared')()};
}
test('editing aborts obsolete request checks and restores the button',async()=>{
  const t=setup(),pending=t.click();assert(t.el('check-request').disabled);
  t.el('prompt').handlers.input();
  assert(t.calls[0].options.signal.aborted);assert.equal(t.el('check-request').disabled,false);
  await pending;
  assert.match(t.el('preflight-result').textContent,/without running/);
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
