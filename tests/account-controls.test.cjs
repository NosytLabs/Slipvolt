const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(require('node:path').join(__dirname, '../public/account-tools.js'), 'utf8');
function controls(offline, max = '') {
  const elements = new Map(); let copied = '', message = '';
  function $(id) {
    if (!elements.has(id)) elements.set(id, {value: '', max: '', textContent: '', addEventListener(name, fn) { this[name] = fn; }, removeAttribute(name) { this[name] = ''; }});
    return elements.get(id);
  }
  const context = { $, OFFLINE: offline, location: {origin:'https://preview.example'}, navigator: {clipboard:{writeText: async text => {copied = text;}}}, toast: text => {message = text;}, selectedOutputCeiling:()=>null, selectedOutputDefault:()=>null, S:{outputBudgetEdited:false}, SlipvoltCore:{safeCount:()=>null}, renderCode:()=>{} };
  vm.createContext(context); vm.runInContext(source, context);
  $('output-tokens').max = max;
  return {context, $, copied:()=>copied, message:()=>message};
}
test('missing output limit reports unavailable instead of an impossible range', () => {
  const h=controls(false); assert.throws(()=>vm.runInContext('requestedOutput()',h.context),/limit is unavailable/i);
  h.$('output-tokens').max='4096'; h.$('output-tokens').value='0';
  assert.throws(()=>vm.runInContext('requestedOutput()',h.context),/between 1 and 4,096/);
});
test('offline endpoint is visibly a placeholder and copying it explains replacement', async () => {
  const h=controls(true); assert.equal(h.$('endpoint-address').textContent,'https://YOUR_HOST/v1/chat/completions');
  await h.$('copy-endpoint').click(); assert.equal(h.copied(),h.$('endpoint-address').textContent); assert.match(h.message(),/replace YOUR_HOST/i);
});
test('online endpoint matches the current service origin', async () => {
  const h=controls(false); await h.$('copy-endpoint').click();
  assert.equal(h.copied(),'https://preview.example/v1/chat/completions');
});
