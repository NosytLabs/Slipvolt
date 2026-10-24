/* Offline assumptions only. No wallet, network, custody, quote or transaction API. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.HolderEconomics = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const defaults = Object.freeze({
    days: 30, activeHolders: 1000, dailyTokensPerHolder: 100000, utilizationPct: 100,
    effectiveNgonka: 25, gnkUsd: 0.18, dailyTradingVolumeUsd: 10000,
    creatorFeeBps: 30, collectedPct: 100, operatingUsd: 300, otherProviderGnk: 50,
    reserveTopupUsd: 200, burnSurplusPct: 10, developerSurplusPct: 70,
  });
  const bounds = Object.freeze({
    days: 366, activeHolders: 10000000, dailyTokensPerHolder: 1000000000,
    utilizationPct: 100, effectiveNgonka: 1000000, gnkUsd: 1000000,
    dailyTradingVolumeUsd: 1000000000, creatorFeeBps: 10000, collectedPct: 100,
    operatingUsd: 1000000000, otherProviderGnk: 1000000000,
    reserveTopupUsd: 1000000000, burnSurplusPct: 100, developerSurplusPct: 100,
  });
  function cents(value) {
    const result = Math.round(value * 100);
    if (!Number.isSafeInteger(result)) throw new RangeError('Combined scenario exceeds safe arithmetic.');
    return result;
  }
  function project(input) {
    if (!input || typeof input !== 'object' || Array.isArray(input)) throw new TypeError('Supply a scenario object.');
    for (const key of Object.keys(input)) {
      if (!Object.hasOwn(defaults, key)) throw new RangeError('Unsupported assumption: ' + key);
    }
    const s = {};
    for (const [key, max] of Object.entries(bounds)) {
      const value = input[key];
      if (typeof value !== 'number' && !(typeof value === 'string' && value.trim() !== '')) {
        throw new TypeError('Enter a number for ' + key + '.');
      }
      const number = Number(value);
      if (!Number.isFinite(number) || number < 0 || number > max) throw new RangeError(key + ' is outside the allowed range.');
      if (['days', 'activeHolders', 'dailyTokensPerHolder'].includes(key) && !Number.isSafeInteger(number)) {
        throw new RangeError(key + ' must be a whole number.');
      }
      if (['days', 'effectiveNgonka', 'gnkUsd'].includes(key) && number === 0) throw new RangeError(key + ' must be positive.');
      s[key] = number;
    }
    if (s.burnSurplusPct + s.developerSurplusPct > 100) throw new RangeError('Burn and developer shares together cannot exceed 100%.');
    const fullUseTokens = s.days * s.activeHolders * s.dailyTokensPerHolder;
    if (!Number.isSafeInteger(fullUseTokens)) throw new RangeError('Combined AI token count exceeds safe integer arithmetic.');
    const periodAiTokens = Math.floor(fullUseTokens * (s.utilizationPct / 100));
    const monthFraction = s.days / 30;
    // 1 GNK = 1,000,000,000 ngonka. This rate already includes the assumed retry factor.
    const computeGnk = periodAiTokens * s.effectiveNgonka / 1e9;
    const computeCents = cents(computeGnk * s.gnkUsd);
    const providerOtherCents = cents(s.otherProviderGnk * s.gnkUsd * monthFraction);
    const serviceCostCents = computeCents + providerOtherCents + cents(s.operatingUsd * monthFraction);
    const reserveCents = cents(s.reserveTopupUsd * monthFraction);
    const requiredCents = serviceCostCents + reserveCents;
    const collectedFeeRate = s.creatorFeeBps / 10000 * (s.collectedPct / 100);
    const revenueCents = cents(s.dailyTradingVolumeUsd * s.days * collectedFeeRate);
    if (![serviceCostCents, requiredCents, revenueCents].every(Number.isSafeInteger)) {
      throw new RangeError('Combined cash amounts exceed safe integer arithmetic.');
    }
    const surplusCents = Math.max(0, revenueCents - requiredCents);
    const burnCents = Math.floor(surplusCents * s.burnSurplusPct / 100);
    const developerCents = Math.floor(surplusCents * s.developerSurplusPct / 100);
    return Object.freeze({
      scenarioOnly: true, payoutAuthorized: false, transactionsPrepared: 0,
      periodDays: s.days, monthlyBasisDays: 30, periodAiTokens, computeGnk, computeUsd: computeCents / 100,
      providerOtherUsd: providerOtherCents / 100, serviceCostUsd: serviceCostCents / 100,
      creatorFeesUsd: revenueCents / 100, reserveTopupUsd: reserveCents / 100,
      surplusUsd: surplusCents / 100, burnBudgetUsd: burnCents / 100,
      developerBudgetUsd: developerCents / 100,
      retainedUsd: (surplusCents - burnCents - developerCents) / 100,
      fundingGapUsd: Math.max(0, requiredCents - revenueCents) / 100,
      breakEvenDailyVolumeUsd: requiredCents === 0 ? 0 : collectedFeeRate === 0 ? null : requiredCents / 100 / (s.days * collectedFeeRate),
      tokensBurned: null,
      costPerMillionUsd: s.effectiveNgonka * s.gnkUsd / 1000,
    });
  }
  return Object.freeze({defaults, project});
});
