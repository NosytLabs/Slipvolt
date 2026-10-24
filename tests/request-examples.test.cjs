const test=require('node:test');
const assert=require('node:assert/strict');
const {example}=require('../public/request-examples.js');
for(const lang of ['curl','python','javascript']){
 test(`${lang} example honors model, cap and env key`,()=>{
  const s=example(lang,'https://api.example.test/v1','MiniMaxAI/MiniMax-M2.7',32768,32768);
  assert.ok(s.includes('MiniMaxAI/MiniMax-M2.7'));
  assert.ok(s.includes('32768'));
  assert.ok(s.includes('SLIPVOLT_API_KEY'));
  assert.ok(!s.includes('obk-'));
 });
}
for(const n of [0,-1,4097,1.2,NaN])test(`reject invalid output ${n}`,()=>assert.throws(()=>example('curl','https://a.test/v1','model',n)));
test('a smaller live model ceiling constrains the example',()=>{
 assert.ok(example('curl','https://a.test/v1','model',2048,2048).includes('2048'));
 assert.throws(()=>example('curl','https://a.test/v1','model',2049,2048));
});
test('unknown or malformed live limits do not generate an example',()=>{
 for(const ceiling of [null,0,-1,4096.5,NaN,Infinity,'4096',1048577])
  assert.throws(()=>example('curl','https://a.test/v1','model',1,ceiling));
});
test('unsupported language is rejected',()=>assert.throws(()=>example('bash','https://a.test/v1','model',1)));
test('python does not auto-retry uncertain paid calls',()=>assert.ok(example('python','https://a.test/v1','model',1).includes('max_retries=0')));
