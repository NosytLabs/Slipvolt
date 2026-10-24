'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
function view(){assert.ok(fs.existsSync(require('node:path').join(__dirname,'../public/token/token.js')),'Token dashboard is missing');return require('../public/token/token.js');}
test('token amounts remain exact above the JavaScript integer limit',()=>{
  assert.equal(view().tokenAmount('9007199254740993',6),'9,007,199,254.740993');
  assert.equal(view().tokenAmount('18446744073709551615',6),'18,446,744,073,709.551615');
});
test('real zero and unavailable are separate',()=>{
  assert.equal(view().tokenAmount('0',6),'0');assert.equal(view().tokenAmount(null,6),'Unavailable');
});
test('invalid precision and malformed amounts are not formatted as money',()=>{
  for(const [raw,d] of [[1,6],['01',6],['-1',6],['0x10',6],['1e9',6],['3',null],['3',true],['3',19]])
    assert.equal(view().tokenAmount(raw,d),'Unavailable');
});
test('explorer links cannot point to an arbitrary URL',()=>{
  assert.equal(view().explorerLink('javascript:alert(1)','account'),'');
  assert.equal(view().explorerLink('11111111111111111111111111111111','account'),'https://explorer.solana.com/address/11111111111111111111111111111111');
  assert.equal(view().explorerLink('1'.repeat(64),'transaction'),'https://explorer.solana.com/tx/'+'1'.repeat(64));
});
test('only a consistent valid snapshot receives the finalized label',()=>{
  assert.equal(view().snapshotReady({status:'available'}),false);
  assert.equal(view().snapshotReady({status:'unavailable',mint_state:{}}),false);
});
