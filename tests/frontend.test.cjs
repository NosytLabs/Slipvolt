const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const target=path.join(__dirname,'../public/core.js');
test('the browser calculator has a testable core',()=>assert.ok(fs.existsSync(target)));
if(fs.existsSync(target)) {
 const C=require(target);
 test('matched input and output costs',()=>{
  const x=C.compare(80,20,.05,.30,1.20);
  assert.equal(x.service,5);assert.equal(x.reference,48);assert.equal(x.saved,43);
 });
 test('zero requests have no fabricated saving percent',()=>assert.equal(C.compare(0,0,.05,.3,1.2).percent,null));
 test('unknown provider prices stay unknown',()=>assert.equal(C.compare(10,2,.05,null,null).reference,null));
 test('a higher service price produces negative savings',()=>assert.ok(C.compare(1,1,2,.3,1.2).saved<0));
 test('invalid blank inputs are not treated as zero',()=>assert.throws(()=>C.number('')));
 test('nonfinite and negative inputs are rejected',()=>{for(const x of ['NaN','Infinity',-1,'oops'])assert.throws(()=>C.number(x));});
 test('treasury covers obligations before allocating surplus',()=>{
  const x=C.treasury({volume:1000000,fee:.3,earned:500,costs:800,reserves:700});
  assert.equal(x.surplus,2000);assert.equal(x.compute,1000);assert.equal(x.wgnk,600);assert.equal(x.developer,400);
 });
 test('a deficit does not create distributions',()=>{
  const x=C.treasury({volume:0,fee:0,earned:5,costs:60,reserves:0});
  assert.equal(x.net,-55);assert.equal(x.surplus,0);assert.equal(x.compute+x.wgnk+x.developer,0);
 });
 test('treasury rounds down minor allocations and preserves every cent',()=>{
  const x=C.treasury({volume:0,fee:0,earned:1.01,costs:0,reserves:0});
  assert.ok(Math.abs(x.compute+x.wgnk+x.developer-1.01)<1e-9);
 });
 test('scenario source decimals and quote are explicit',()=>{
  const x=C.route('SOL','GNK','1');assert.equal(x.steps.length,4);assert.equal(x.executable,false);
  assert.equal(C.route('USDC','WGNK',2).steps.length,2);
 });
 test('SPL route validates raw base58 length instead of ticker',()=>assert.throws(()=>C.route('SPL','GNK',10,'USDC')));
 test('wrong-chain fake GNK destination rejected',()=>assert.throws(()=>C.route('SOL','GNK_SOL',10)));
 test('decimal base58 public keys are required to decode to 32 bytes',()=>assert.throws(()=>C.route('SPL','GNK',10,'z'.repeat(44))));
 test('key prefixes accept migration but never operator keys',()=>{assert.ok(C.isCustomerKey('sv_'+ 'x'.repeat(40)));assert.ok(C.isCustomerKey('grd_'+ 'x'.repeat(40)));assert.equal(C.isCustomerKey('obk-abcd'),false);});
 test('markup and malicious strings are escaped',()=>assert.equal(C.escape('<img src=x onerror=1>'),'&lt;img src=x onerror=1&gt;'));
}
