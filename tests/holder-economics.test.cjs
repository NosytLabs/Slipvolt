const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const filename = path.join(__dirname, '../operator/holder-economics.js');
const math = fs.existsSync(filename) ? require(filename) : {};
const assumptions = {
  days: 30, activeHolders: 1000, dailyTokensPerHolder: 100000, utilizationPct: 100,
  effectiveNgonka: 25, gnkUsd: 0.18, dailyTradingVolumeUsd: 10000,
  creatorFeeBps: 30, collectedPct: 100, operatingUsd: 300, otherProviderGnk: 50,
  reserveTopupUsd: 200, burnSurplusPct: 10, developerSurplusPct: 70,
};
function project(patch = {}) {
  assert.equal(typeof math.project, 'function', 'Holder economics engine is missing');
  return math.project({...assumptions, ...patch});
}
test('prices three billion combined AI tokens in GNK without a million-fold error', () => {
  const result = project();
  assert.equal(result.periodAiTokens, 3000000000);
  assert.equal(result.computeGnk, 75);
  assert.equal(result.computeUsd, 13.5);
});
test('uses the creator slice of eligible volume and actual collection fraction', () => {
  assert.equal(project().creatorFeesUsd, 900);
  assert.equal(project({collectedPct: 50}).creatorFeesUsd, 450);
});
test('scales monthly provider, operating and reserve assumptions over the whole chosen period', () => {
  const base = project();
  for (const days of [60, 366]) {
    const x = project({days});
    assert.equal(x.serviceCostUsd, Math.round(base.serviceCostUsd * days / 30 * 100) / 100);
    assert.equal(x.reserveTopupUsd, Math.round(base.reserveTopupUsd * days / 30 * 100) / 100);
    assert.equal(x.periodDays, days);
    assert.equal(x.monthlyBasisDays, 30);
  }
});
test('funds costs and reserves before any burn or developer allocation', () => {
  const x = project();
  assert.equal(x.providerOtherUsd, 9);
  assert.equal(x.serviceCostUsd, 322.5);
  assert.equal(x.surplusUsd, 377.5);
  assert.equal(x.burnBudgetUsd, 37.75);
  assert.equal(x.developerBudgetUsd, 264.25);
  assert.equal(x.retainedUsd, 75.5);
});
test('zero trading shows the funding gap and never spends deposited principal', () => {
  const x = project({dailyTradingVolumeUsd: 0});
  assert.equal(x.fundingGapUsd, 522.5);
  assert.equal(x.burnBudgetUsd, 0);
  assert.equal(x.developerBudgetUsd, 0);
  assert.equal(x.surplusUsd, 0);
});
test('zero creator fee or collection cannot be fixed by more volume', () => {
  assert.equal(project({creatorFeeBps: 0}).breakEvenDailyVolumeUsd, null);
  assert.equal(project({collectedPct: 0}).breakEvenDailyVolumeUsd, null);
});
test('break-even volume solves full costs plus the requested reserve addition', () => {
  const x = project();
  assert.ok(Math.abs(x.breakEvenDailyVolumeUsd - 5805.555555555556) < 0.00001);
  const atBreakEven = project({dailyTradingVolumeUsd: x.breakEvenDailyVolumeUsd});
  assert.equal(atBreakEven.fundingGapUsd, 0);
  assert.equal(atBreakEven.surplusUsd, 0);
});
test('higher GNK acquisition cost raises costs without fabricating fee income', () => {
  const a = project(), b = project({gnkUsd: 0.36});
  assert.equal(b.computeUsd, a.computeUsd * 2);
  assert.equal(b.providerOtherUsd, a.providerOtherUsd * 2);
  assert.equal(b.creatorFeesUsd, a.creatorFeesUsd);
});
test('burn is a cash budget rather than a claimed token burn or price increase', () => {
  const x = project();
  assert.equal(x.tokensBurned, null);
  assert.equal(x.scenarioOnly, true);
  assert.equal(x.transactionsPrepared, 0);
  assert.equal(x.payoutAuthorized, false);
});
test('cent rounding never overallocates the surplus', () => {
  for (const volume of [0, 100, 5806, 10000, 12345.67, 100000]) {
    const x = project({dailyTradingVolumeUsd: volume, burnSurplusPct: 17.3, developerSurplusPct: 71.1});
    assert.equal(Math.round((x.burnBudgetUsd + x.developerBudgetUsd + x.retainedUsd) * 100), Math.round(x.surplusUsd * 100));
  }
});
test('zero holders have zero variable compute cost but still have operating costs', () => {
  const x = project({activeHolders: 0});
  assert.equal(x.computeGnk, 0);
  assert.equal(x.serviceCostUsd, 309);
});
test('rejects invalid inputs, excess allocations and refundable deposit revenue', () => {
  for (const patch of [
    {activeHolders: 0.5}, {days: 0}, {gnkUsd: 0}, {effectiveNgonka: 0},
    {dailyTradingVolumeUsd: Infinity}, {dailyTradingVolumeUsd: -1},
    {collectedPct: 101}, {burnSurplusPct: 40, developerSurplusPct: 70},
    {stakedPrincipalUsd: 1000000}, {tokenMarketCapUsd: 1000000}, {gnkUsd: true},
    {operatingUsd: ''}, {toString: 10},
  ]) assert.throws(() => project(patch));
});
test('rejects combined token counts outside exact integer arithmetic', () => {
  assert.throws(() => project({activeHolders: 10000000, dailyTokensPerHolder: 1000000000, days: 366}));
});
