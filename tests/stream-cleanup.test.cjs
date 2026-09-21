'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const tools=require('../public/request-tools.js');
const source=fs.readFileSync('public/app.js','utf8');
const start=source.indexOf('async function readStream(');
const end=source.indexOf("\n$('send')",start);
assert(start>=0&&end>start);

function runtime(){
  let rendered='',writes=0;
  const result={set textContent(value){rendered=value;writes++;},classList:{add(){}}};
  const ctx={TextDecoder,Uint8Array,SlipvoltRequestTools:tools,S:{epoch:1},$:()=>result};
  vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
  return {read:r=>ctx.readStream(r,1),get text(){return rendered},get writes(){return writes}};
}
function response(text,width=Infinity){
  const bytes=new TextEncoder().encode(text);let cancelled=0;
  const body=new ReadableStream({start(c){for(let p=0;p<bytes.length;p+=width)c.enqueue(bytes.slice(p,p+width));c.close();},cancel(){cancelled++;}});
  return {body,get cancelled(){return cancelled}};
}
const frame=text=>'data: '+JSON.stringify({choices:[{delta:{content:text}}]});
for(const newline of ['\n','\r\n','\r']){
  test('fragmented SSE with '+JSON.stringify(newline),async()=>{
    const app=runtime();await app.read(response(frame('Hello 🌍')+newline+newline+'data: [DONE]'+newline+newline,1));
    assert.equal(app.text,'Hello 🌍');
  });
}
test('batch rendering once per read rather than once per token event',async()=>{
  const app=runtime();await app.read(response(Array.from({length:100},()=>frame('x')+'\n\n').join('')+'data: [DONE]\n\n'));
  assert.equal(app.text,'x'.repeat(100));assert.equal(app.writes,1);
});
test('DONE cancels the reader without waiting for transport EOF',async()=>{
  const app=runtime();let count=0,cancelled=false,released=false;
  const reader={async read(){if(count++===0)return {value:new TextEncoder().encode(frame('done')+'\n\ndata: [DONE]\n\n'),done:false};throw Error('Read after terminal marker');},async cancel(){cancelled=true;},releaseLock(){released=true;}};
  await app.read({body:{getReader:()=>reader}});
  assert.equal(app.text,'done');assert(cancelled);assert(released);
});
test('an incomplete reply rejects rather than becoming a success',async()=>{
  const app=runtime();await assert.rejects(app.read(response(frame('partial')+'\n\n')),/confirmation/);
});
test('unterminated DONE frame is not proof of completion',async()=>{
  await assert.rejects(runtime().read(response(frame('partial')+'\n\ndata: [DONE]')),/confirmation/);
});
test('provider error cancels and releases the response stream',async()=>{
  let cancelled=false,released=false;
  const reader={async read(){return {value:new TextEncoder().encode('data: {"error":{"message":"fixture failure"}}\n\n'),done:false}},async cancel(){cancelled=true},releaseLock(){released=true}};
  await assert.rejects(runtime().read({body:{getReader:()=>reader}}),/fixture failure/);
  assert(cancelled);assert(released);
});
test('comment and empty frames do not affect text',async()=>{
  const app=runtime();await app.read(response(': heartbeat\r\n\r\n'+frame('ok')+'\r\n\r\ndata: [DONE]\r\n\r\n',3));assert.equal(app.text,'ok');
});
test('malformed JSON cannot be silently accepted',async()=>{
  await assert.rejects(runtime().read(response('data: {bad}\n\ndata: [DONE]\n\n')));
});
test('oversized response fails before unchecked buffering',async()=>{
  await assert.rejects(runtime().read(response('data: '+ 'x'.repeat(2000001))),/too large/i);
});
