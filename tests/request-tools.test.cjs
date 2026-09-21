const test = require('node:test');
const assert = require('node:assert/strict');
let tools; try { tools = require('../public/request-tools.js'); } catch {}
test('connection kit contains no key or upstream URL', () => {
  assert.ok(tools, 'request-tools implementation is missing');
  const kit = tools.connectionKit('https://service.example', 'MiniMaxAI/MiniMax-M2.7');
  assert.equal(kit.base_url, 'https://service.example/v1');
  assert.equal(kit.api_key_environment, 'SLIPVOLT_API_KEY');
  assert.ok(!JSON.stringify(kit).includes('obk-'));
});
test('connection kit rejects credential-bearing or query origins', () => {
  assert.ok(tools);
  for (const value of ['https://user:secret@host', 'https://host?key=SECRET', 'javascript:alert(1)', 'https://host/path']) {
    assert.throws(() => tools.connectionKit(value, 'm'));
  }
});
test('support export is an allowlist, not an arbitrary object dump', () => {
  assert.ok(tools);
  const report=tools.supportReport({version:'0.9.0',selected:'MiniMaxAI/MiniMax-M2.7',code:'wallet_allowance_exhausted',
    wallet:'PRIVATE',key:'sv_PRIVATE',prompt:'PRIVATE',origin:'https://host/PRIVATE',note:'PRIVATE',
    requestId:'fd9bba28-8e82-4ed2-8fbb-16320fdb9451'});
  assert.ok(!JSON.stringify(report).includes('PRIVATE'));
  assert.equal(report.last_preflight_code,'wallet_allowance_exhausted');
});
test('untrusted status text is never echoed into support reports', () => {
  assert.ok(tools);
  const r=tools.supportReport({version:'obk-SECRET',selected:'<script>',code:'SECRET',requestId:'obk-SECRET'});
  assert.equal(r.version,'unknown');assert.equal(r.model,'unknown');assert.equal(r.request_id,null);
  assert.ok(!JSON.stringify(r).includes('SECRET'));
});
test('each preflight failure has useful copy, not a fake success', () => {
  assert.ok(tools);
  assert.match(tools.explain('allowance_pool_unfunded_or_exhausted'),/operator|funded/i);
  assert.match(tools.explain('reconciliation_required'),/review|reconcil/i);
  assert.match(tools.explain('made_up'),/unavailable|unknown/i);
});
test('credential-looking model text is excluded from diagnostic export', () => {
  const r=tools.supportReport({selected:'obk-DO_NOT_COPY_SECRET'});
  assert.equal(r.model,'unknown');
});
