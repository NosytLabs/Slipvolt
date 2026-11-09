'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function setup(){
  const elements=new Map(),calls=[],generations=new Map();
  const el=id=>{
    if(!elements.has(id))elements.set(id,{value:'',textContent:'',disabled:false,handlers:{},
      addEventListener(name,fn){this.handlers[name]=fn;},querySelector(){return el('quote-submit');}});
    return elements.get(id);
  };
  const context={document:{getElementById:el},key:'fixture',setTimeout,clearTimeout,
    nextRefresh(name){const generation=(generations.get(name)||0)+1;generations.set(name,generation);return()=>generations.get(name)===generation;},
    api(path,options){return new Promise((resolve,reject)=>calls.push({path,options,resolve,reject}));}};
  vm.createContext(context);vm.runInContext(fs.readFileSync('public/admin/connections.js','utf8'),context);
  return {el,calls,click:id=>el(id).handlers.click()};
}

test('the most recent diagnostic owns the shared result even when replies arrive backwards',async()=>{
  const app=setup(),older=app.click('connections-check'),latest=app.click('priority-check');
  assert.match(app.el('connections-result').textContent,/priority fee/i);
  app.calls[1].resolve({estimates:{recommended:12}});await latest;
  const expected=app.el('connections-result').textContent;
  app.calls[0].resolve({status:'ready'});await older;
  assert.equal(app.el('connections-result').textContent,expected);
  assert.deepEqual(app.calls.map(call=>[call.path,call.options.method]),[
    ['/api/admin/connections/check','POST'],['/api/admin/connections/priority-fee','POST']]);
});

test('an older failure cannot replace a pending or completed newer diagnostic',async()=>{
  const app=setup(),older=app.click('priority-check'),latest=app.click('connections-check');
  app.calls[0].reject(Error('old fee failure'));await older;
  assert.equal(app.el('connections-result').textContent,'Checking the configured RPC…');
  assert.equal(app.el('connections-check').disabled,true);
  app.calls[1].resolve({status:'ready'});await latest;
  assert.match(app.el('connections-result').textContent,/ready/);
});

test('reentering the same pending diagnostic does not dispatch or unlock it',async()=>{
  const app=setup(),pending=app.click('connections-check');
  await app.click('connections-check');
  assert.equal(app.calls.length,1);assert.equal(app.el('connections-check').disabled,true);
  app.calls[0].resolve({status:'ready'});await pending;
  assert.equal(app.el('connections-check').disabled,false);
  const next=app.click('connections-check');assert.equal(app.calls.length,2);
  app.calls[1].reject(Error('current RPC failure'));await next;
  assert.equal(app.el('connections-result').textContent,'current RPC failure');
  assert.equal(app.el('connections-check').disabled,false);
});
