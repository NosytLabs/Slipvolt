'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {example}=require('../public/request-examples.js');
for(const lang of ['curl','python','javascript'])test(`${lang}: new brand with legacy key fallback`,()=>{
  const code=example(lang,'https://api.example.test/v1','MiniMaxAI/MiniMax-M2.7',32768,32768);
  assert.match(code,/HOLDBYTE_API_KEY/);assert.match(code,/SLIPVOLT_API_KEY/);
  assert.ok(code.includes('32768'));
});
async function run(env){
  const calls=[];
  const code=example('javascript','https://api.example.test/v1','model',1024);
  const promise=vm.runInNewContext('(async()=>{'+code+'})()',{
    process:{env},console:{log(){}},fetch:async(url,options)=>{
      calls.push(options.headers.Authorization);
      return {ok:true,json:async()=>({choices:[{message:{content:'ok'}}]})};
    }
  });
  return {promise,calls};
}
test('missing credential fails before a request is sent',async()=>{
  const {promise,calls}=await run({});await assert.rejects(promise,/HOLDBYTE_API_KEY/);assert.deepEqual(calls,[]);
});
test('preferred key wins without changing key format',async()=>{
  const {promise,calls}=await run({HOLDBYTE_API_KEY:'sv_new',SLIPVOLT_API_KEY:'sv_old'});
  await promise;assert.deepEqual(calls,['Bearer sv_new']);
});
test('old key-only setup still works',async()=>{
  const {promise,calls}=await run({SLIPVOLT_API_KEY:'sv_old'});await promise;assert.deepEqual(calls,['Bearer sv_old']);
});
test('curl reports failed HTTP responses and disables retries',()=>{
  const code=example('curl','https://api.example.test/v1','model',1024);
  assert.match(code,/--fail-with-body/);assert.match(code,/--retry 0/);
});
