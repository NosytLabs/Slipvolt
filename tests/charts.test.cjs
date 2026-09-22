const test=require('node:test');
const assert=require('node:assert/strict');
const Charts=require('../public/chart.js');

test('line chart model keeps valid measured rows and preserves order',()=>{
  const model=Charts.lineModel([
    {day:'2026-09-20',tokens:1200},{day:'2026-09-21',tokens:1800},{day:'bad',tokens:NaN}
  ],{x:'day',series:[{key:'tokens',label:'AI tokens'}]});
  assert.deepEqual(model.labels,['2026-09-20','2026-09-21']);
  assert.deepEqual(model.series[0].values,[1200,1800]);
  assert.equal(model.max,1800);
});

test('bar chart model never invents missing values',()=>{
  const model=Charts.barModel([
    {day:'2026-09-20',revenue_usd:12,expense_usd:5},
    {day:'2026-09-21',revenue_usd:0,expense_usd:8}
  ],{x:'day',series:[{key:'revenue_usd',label:'Revenue'},{key:'expense_usd',label:'Expenses'}]});
  assert.deepEqual(model.series[0].values,[12,0]);
  assert.deepEqual(model.series[1].values,[5,8]);
  assert.equal(model.max,12);
});

test('chart models reject duplicate or unsafe keys rather than executing arbitrary access',()=>{
  assert.throws(()=>Charts.lineModel([{day:'x',tokens:1}],{x:'__proto__',series:[{key:'tokens',label:'Tokens'}]}),/Invalid chart key/);
  assert.throws(()=>Charts.lineModel([{day:'x',tokens:1}],{x:'day',series:[{key:'tokens',label:'A'},{key:'tokens',label:'B'}]}),/Duplicate chart series/);
});

test('short date labels are deterministic and locale independent',()=>{
  assert.equal(Charts.shortDate('2026-09-21'),'Sep 21');
  assert.equal(Charts.shortDate('bad'),'bad');
});
