const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const target=path.join(__dirname,'../public/core.js');
test('the browser core has a testable module',()=>assert.ok(fs.existsSync(target)));
if(fs.existsSync(target)) {
 const C=require(target);
 test('key prefixes accept migration but never operator keys',()=>{assert.ok(C.isCustomerKey('sv_'+ 'x'.repeat(40)));assert.ok(C.isCustomerKey('grd_'+ 'x'.repeat(40)));assert.equal(C.isCustomerKey('obk-abcd'),false);});
 test('markup and malicious strings are escaped',()=>assert.equal(C.escape('<img src=x onerror=1>'),'&lt;img src=x onerror=1&gt;'));
 test('API response parser handles JSON, empty success, and useful non-JSON errors',async()=>{
  assert.deepEqual(await C.readApiResponse(new Response(JSON.stringify({ok:true}),{status:200,headers:{'content-type':'application/json'}})),{ok:true});
  assert.equal(await C.readApiResponse(new Response(null,{status:204})),null);
  await assert.rejects(()=>C.readApiResponse(new Response('private proxy detail',{status:502,headers:{'content-type':'text/plain'}})),e=>e.status===502&&/Request failed \(502\)/.test(e.message)&&!e.message.includes('private proxy detail'));
 });
}
test('browser core exports only helpers used by the current product',()=>{
  const core=require(target);
  assert.deepEqual(Object.keys(core).sort(),['appendChatTurn','chatMessages','chatStats','chatTranscript','escape','isCustomerKey','readApiResponse','safeCount','selectableModelId','summarizeUsage'].sort());
});
test('unknown counts stay distinct from a measured zero',()=>{
  const core=require(target);
  assert.equal(core.safeCount(null),null);
  assert.equal(core.safeCount(undefined),null);
  assert.equal(core.safeCount('0'),null);
  assert.equal(core.safeCount(0),0);
});
test('model selection keeps a usable choice, falls forward, and fails closed',()=>{
  const core=require(target);
  const models=[
    {id:'first',availability:'unavailable'},
    {id:'listed',availability:'listed'},
    {id:'blocked',availability:'healthy',routable:false}
  ];
  assert.equal(core.selectableModelId(models,'listed'),'listed');
  assert.equal(core.selectableModelId(models,'missing'),'listed');
  assert.equal(core.selectableModelId(models,'blocked'),'listed');
  assert.equal(core.selectableModelId(models.filter(row=>row.id!=='listed'),'first'),'');
  assert.equal(core.selectableModelId([], 'listed'),'');
});
test('recent usage summary counts only measured safe values and keeps model groups separate',()=>{
  const core=require(target);
  const summary=core.summarizeUsage([
    {model:'a',state:'settled',tokens:15,cost_ngonka:150},
    {model:'a',state:'reserved',tokens:0,reserved_tokens:20,cost_ngonka:null},
    {model:'b',state:'needs_review',tokens:7,cost_ngonka:70},
    {model:'bad',state:'settled',tokens:-1,cost_ngonka:Infinity},
    null
  ]);
  assert.deepEqual({requests:summary.requests,settled:summary.settled,inFlight:summary.inFlight,needsReview:summary.needsReview,recentTokens:summary.recentTokens,recentCostNgonka:summary.recentCostNgonka},
    {requests:4,settled:2,inFlight:1,needsReview:1,recentTokens:22,recentCostNgonka:220});
  assert.deepEqual(summary.models,[{model:'a',tokens:15},{model:'b',tokens:7}]);
});
test('chat memory builds alternating full history and excludes failed or empty turns',()=>{
  const core=require(target);
  let memory=core.appendChatTurn([], 'First question', 'First answer');
  assert.equal(memory.retained,true);
  memory=core.appendChatTurn(memory.turns, 'failed question', '   ');
  assert.equal(memory.retained,false);
  assert.deepEqual(core.chatMessages(memory.turns,'Follow up'),[
    {role:'user',content:'First question'},
    {role:'assistant',content:'First answer'},
    {role:'user',content:'Follow up'}
  ]);
});
test('chat memory preserves complete turns and marks the explicit browser cap without silent eviction',()=>{
  const core=require(target);
  const first=core.appendChatTurn([],'one','ONE',{maxTurns:2,maxChars:100});
  const bounded=core.appendChatTurn(first.turns,'two','TWO',{maxTurns:2,maxChars:100});
  assert.deepEqual(bounded.turns,[{user:'one',assistant:'ONE'},{user:'two',assistant:'TWO'}]);
  assert.equal(bounded.full,true);assert.equal(bounded.dropped,0);
  const characterBound=core.appendChatTurn([],'123456','abcdef',{maxTurns:3,maxChars:10});
  assert.deepEqual(characterBound.turns,[{user:'123456',assistant:'abcdef'}]);
  assert.equal(characterBound.full,true);assert.equal(characterBound.dropped,0);
  assert.deepEqual(core.chatStats(characterBound.turns),{turns:1,characters:12});
  assert.equal(core.chatTranscript(characterBound.turns),'You\n123456\n\nAssistant\nabcdef');
});
