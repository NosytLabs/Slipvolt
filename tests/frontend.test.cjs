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
  assert.deepEqual(Object.keys(core).sort(),['escape','isCustomerKey','readApiResponse'].sort());
});
