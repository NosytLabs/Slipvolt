const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../public/status/index.html'),'utf8');
const js=fs.readFileSync(path.join(__dirname,'../public/status/app.js'),'utf8');

test('status page reserves one source-labelled network chart, not fake uptime widgets',()=>{
  assert.ok(html.includes('network-chart'));
  assert.ok(html.includes('Provider-wide'));
  assert.equal(/uptime[^<]{0,20}%/i.test(html),false);
  assert.ok(html.includes('../chart.js'));
});

test('status refresh clears the network chart when provider data is unavailable',()=>{
  assert.ok(js.includes('clearNetworkChart'));
  assert.ok(js.includes('n.daily'));
});
