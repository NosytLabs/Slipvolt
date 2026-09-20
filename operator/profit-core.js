/* Slipvolt scenario math only. No ledger, quotes, network, secrets or transactions. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SlipvoltBusiness = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const defaults = Object.freeze({
    volumeUsd:1000000, creatorFeeBps:30, customers:100, planUsd:29,
    planMillions:500, utilizationPct:100, holderMillions:1500,
    gnkUsd:1, effectiveNgonka:15, epochGnk:50, operatingUsd:600,
    paymentBps:290, paymentFixedUsd:0.30, refundsUsd:0, reserveTopupUsd:1500,
    developerSharePct:70, targetUsd:5000
  });
  const bounds = {
    volumeUsd:1e9, creatorFeeBps:95, customers:1e6, planUsd:1e6,
    planMillions:1e6, utilizationPct:100, holderMillions:1e9,
    gnkUsd:1e6, effectiveNgonka:1e6, epochGnk:1e9, operatingUsd:1e9,
    paymentBps:10000, paymentFixedUsd:1e6, refundsUsd:1e9,
    reserveTopupUsd:1e9, developerSharePct:100, targetUsd:1e9
  };
  function validate(input) {
    if (!input || typeof input !== 'object' || Array.isArray(input)) throw new TypeError('Supply a scenario object.');
    for (const key of Object.keys(input)) if (!Object.hasOwn(defaults,key)) throw new RangeError('Unsupported input: '+key);
    const out = {};
    for (const [key,max] of Object.entries(bounds)) {
      const value = input[key];
      if (!(typeof value === 'number' || (typeof value === 'string' && value.trim() !== ''))) throw new TypeError('Enter a number for '+key+'.');
      const n = Number(value);
      if (!Number.isFinite(n) || n < 0 || n > max) throw new RangeError(key+' is outside the allowed range.');
      if (key === 'customers' && !Number.isSafeInteger(n)) throw new RangeError('Customer count must be a whole number.');
      if ((key === 'gnkUsd' || key === 'effectiveNgonka') && n === 0) throw new RangeError(key+' must be positive.');
      out[key]=n;
    }
    return out;
  }
  function cents(n) {
    const v = Math.round(n*100);
    if (!Number.isSafeInteger(v)) throw new RangeError('Combined scenario is too large for safe cent rounding.');
    return v;
  }
  function money(n) { return cents(n)/100; }
  function project(input) {
    const s=validate(input);
    const paidMillions=s.customers*s.planMillions*s.utilizationPct/100;
    const computeGnk=(paidMillions+s.holderMillions)*s.effectiveNgonka/1000;
    const computeUsd=money(computeGnk*s.gnkUsd);
    const epochUsd=money(s.epochGnk*s.gnkUsd);
    const creatorFeesUsd=money(s.volumeUsd*s.creatorFeeBps/10000);
    const serviceRevenueUsd=money(s.customers*s.planUsd);
    const paymentFeesUsd=money(serviceRevenueUsd*s.paymentBps/10000+s.customers*s.paymentFixedUsd);
    const grossRevenueUsd=money(creatorFeesUsd+serviceRevenueUsd);
    const totalCostsUsd=money(computeUsd+epochUsd+s.operatingUsd+paymentFeesUsd+s.refundsUsd);
    const operatingCashMarginUsd=money(grossRevenueUsd-totalCostsUsd);
    const cashAfterReserves=money(operatingCashMarginUsd-s.reserveTopupUsd);
    const distributableUsd=Math.max(0,cashAfterReserves);
    const allocationCents=Math.floor(cents(distributableUsd)*s.developerSharePct/100);
    const developerUsd=allocationCents/100;
    const retainedUsd=(cents(distributableUsd)-allocationCents)/100;
    const planContributionUsd=money(s.planUsd-(s.planMillions*s.effectiveNgonka/1000*s.gnkUsd)
      -(s.planUsd*s.paymentBps/10000+s.paymentFixedUsd));
    let requiredMonthlyVolumeUsd;
    if (s.targetUsd===0) requiredMonthlyVolumeUsd=0;
    else if (s.developerSharePct===0) requiredMonthlyVolumeUsd=null;
    else {
      const need=s.targetUsd/(s.developerSharePct/100)+totalCostsUsd+s.reserveTopupUsd-serviceRevenueUsd;
      requiredMonthlyVolumeUsd=need<=0?0:s.creatorFeeBps===0?null:money(need/(s.creatorFeeBps/10000));
    }
    const warnings=[];
    if (planContributionUsd<0) warnings.push('The proposed paid plan loses money at full usage before shared operating and epoch costs.');
    if (s.utilizationPct<100) warnings.push('Usage is below the full paid allowance; also test 100% utilization.');
    if (cashAfterReserves<0) warnings.push('Revenue does not cover all modeled costs and reserve additions; developer allocation is zero.');
    if (s.creatorFeeBps!==30) warnings.push('The effective creator fee is a sensitivity assumption, not an instruction changing Pump fees.');
    if (s.reserveTopupUsd===0) warnings.push('No new reserve provision is modeled. Verify existing runway, taxes and customer obligations before any payout.');
    warnings.push('All demand, prices and costs are assumptions. No paid plan, payout, coin launch or transaction is activated.');
    return Object.freeze({scenarioOnly:true,payoutAuthorized:false,transactionsPrepared:0,
      creatorFeesUsd,serviceRevenueUsd,grossRevenueUsd,paidMillions,computeGnk,
      computeUsd,epochUsd,paymentFeesUsd,totalCostsUsd,operatingCashMarginUsd,
      reserveTopupUsd:money(s.reserveTopupUsd),distributableUsd,developerUsd,retainedUsd,
      fundingGapUsd:Math.max(0,-cashAfterReserves),planContributionUsd,
      requiredMonthlyVolumeUsd,warnings});
  }
  return Object.freeze({defaults,project});
});
