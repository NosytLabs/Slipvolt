const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../public/admin/index.html'),'utf8');
const js=fs.readFileSync(path.join(__dirname,'../public/admin/app.js'),'utf8');
test('admin exposes configurable conservative GNK budget',()=>assert.ok(html.includes('ngonka_per_token_budget')));
test('admin supports user search and key management',()=>{assert.ok(html.includes('user-search'));assert.ok(html.includes('user-detail'));assert.ok(js.includes('/keys'));});
test('admin displays audit activity',()=>{assert.ok(html.includes('audit-log'));assert.ok(js.includes('/api/admin/audit'));});
test('admin supports usage window selection',()=>{assert.ok(html.includes('window-days'));assert.ok(js.includes('days='));});
test('admin renders fund capacity, not just raw GNK',()=>assert.ok(js.includes('local_available_ai_tokens')));
test('public model picker surfaces live availability',()=>{const publicJs=fs.readFileSync(path.join(__dirname,'../public/app.js'),'utf8');assert.ok(publicJs.includes('availability'));assert.ok(publicJs.includes('temporarily unavailable'));});
test('admin has credential-free connection diagnostics and quote-only operations',()=>{assert.ok(html.includes('connections-check'));assert.ok(html.includes('quote-form'));assert.ok(html.includes('connections.js'));});
test('admin master credential is not persisted in web storage',()=>{assert.equal(js.includes('sessionStorage.setItem'),false);assert.equal(js.includes('localStorage.setItem'),false);});
test('admin dashboard includes measured charts and grouped settings without decorative widgets',()=>{
  const css=fs.readFileSync(path.join(__dirname,'../public/admin/styles.css'),'utf8');
  assert.ok(html.includes('/chart.js'));
  assert.ok(html.includes('usage-chart'));
  assert.ok(html.includes('business-chart'));
  assert.ok(html.includes('config-state'));
  assert.ok(html.includes('settings-group'));
  assert.ok(js.includes('renderCharts'));
  assert.ok(js.includes('markConfigDirty'));
  assert.ok(js.includes('loadSecondary'));
  assert.ok(css.includes('.analytics-grid'));
  assert.ok(css.includes('.chart-frame'));
});

test('secondary admin panel failures replace stale tables instead of leaving old data visible',()=>{
  assert.ok(js.includes("loadSecondary(loadUsers,'users'"));
  assert.ok(js.includes("loadSecondary(loadRequests,'requests'"));
  assert.ok(js.includes("loadSecondary(loadAudit,'audit-log'"));
  assert.ok(js.includes('renderPanelError(id'));
});
test('admin invalidates stale overview and validates cross-field settings before save',()=>{
  assert.ok(js.includes('renderOverviewUnavailable'));
  assert.ok(js.includes('validateConfigPayload'));
  assert.ok(js.includes("Global allowance cannot be smaller than per-wallet allowance"));
  assert.ok(js.includes("Global concurrency cannot be smaller than wallet concurrency"));
});

test('settings preserve unsaved edits across refreshes and offer explicit discard',()=>{
  assert.ok(html.includes('discard-config'));
  assert.ok(js.includes('configDirty'));
  assert.ok(js.includes('discardConfig'));
});
test('overview outage does not block independent admin panels',()=>{
  assert.ok(js.includes('overviewError'));
  assert.ok(js.includes("loadSecondary(loadUsers,'users'"));
});
test('operator scorecard includes measured request wallet and review counts',()=>{
  assert.ok(js.includes("metric(`${days}d requests`"));
  assert.ok(js.includes("metric(`${days}d wallets`"));
  assert.ok(js.includes("metric('Needs review'"));
});
