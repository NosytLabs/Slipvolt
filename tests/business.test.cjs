const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const modulePath = path.join(__dirname,'../operator/profit-core.js');
const core = fs.existsSync(modulePath) ? require(modulePath) : {};
const base = {
 volumeUsd:1000000, creatorFeeBps:30, customers:100, planUsd:29,
 planMillions:500, utilizationPct:100, holderMillions:1500,
 gnkUsd:1, effectiveNgonka:15, epochGnk:50, operatingUsd:600,
 paymentBps:290, paymentFixedUsd:0.30, refundsUsd:0, reserveTopupUsd:1500,
 developerSharePct:70, targetUsd:5000
};
function run(patch={}){ assert.equal(typeof core.project,'function','Scenario engine is missing');return core.project({...base,...patch}); }
test('uses creator slice, not Pump total trading fee',()=>assert.equal(run().creatorFeesUsd,3000));
test('models full 500M usage for each paying customer',()=>{const x=run();assert.equal(x.paidMillions,50000);assert.equal(x.computeGnk,772.5);});
test('includes epoch charges, payment fees and operating costs',()=>{const x=run();assert.equal(x.paymentFeesUsd,114.1);assert.equal(x.totalCostsUsd,1536.6);});
test('reserve-first payout and retained remainder',()=>{const x=run();assert.equal(x.distributableUsd,2863.4);assert.equal(x.developerUsd,2004.38);assert.equal(x.retainedUsd,859.02);});
test('zero volume is evaluated, not assumed profitable',()=>{const x=run({volumeUsd:0});assert.equal(x.developerUsd,0);assert.equal(x.fundingGapUsd,136.6);});
test('loss-making month never pays developer',()=>{const x=run({volumeUsd:0,customers:0});assert.equal(x.developerUsd,0);assert.equal(x.retainedUsd,0);assert.ok(x.fundingGapUsd>0);});
test('reserves bind even when operating cash margin is positive',()=>{const x=run({volumeUsd:0});assert.ok(x.operatingCashMarginUsd>0);assert.equal(x.developerUsd,0);});
test('native GNK price doubles compute cost, not income',()=>{const a=run(), b=run({gnkUsd:2});assert.equal(b.computeUsd,a.computeUsd*2);assert.equal(b.grossRevenueUsd,a.grossRevenueUsd);assert.ok(b.developerUsd<a.developerUsd);});
test('bad full-usage unit economics produce a warning',()=>{const x=run({gnkUsd:2,effectiveNgonka:30});assert.ok(x.planContributionUsd<0);assert.ok(x.warnings.some(s=>s.includes('loses money')));});
test('no payable or transaction claim',()=>{const x=run();assert.equal(x.scenarioOnly,true);assert.equal(x.payoutAuthorized,false);assert.equal(x.transactionsPrepared,0);});
test('target volume solves developer payout equation',()=>{const x=run();const required=x.requiredMonthlyVolumeUsd;const y=run({volumeUsd:required});assert.ok(Math.abs(y.developerUsd-base.targetUsd)<0.02);});
test('zero creator fee makes unmet volume target impossible',()=>assert.equal(run({creatorFeeBps:0}).requiredMonthlyVolumeUsd,null));
test('subscriptions may satisfy the target with no token trading',()=>assert.equal(run({customers:1000,creatorFeeBps:0}).requiredMonthlyVolumeUsd,0));
test('zero developer share cannot satisfy positive target',()=>assert.equal(run({developerSharePct:0}).requiredMonthlyVolumeUsd,null));
test('zero target requires zero volume even at zero share',()=>assert.equal(run({developerSharePct:0,targetUsd:0}).requiredMonthlyVolumeUsd,0));
test('accounting never allocates more than the modeled surplus',()=>{for(const v of [0,50000,1000000,5000000]){const x=run({volumeUsd:v});assert.ok(Math.abs(x.developerUsd+x.retainedUsd-x.distributableUsd)<0.011);}});
test('input is not mutated',()=>{const before=JSON.stringify(base);run();assert.equal(JSON.stringify(base),before);});
for(const [name,value] of [['NaN',NaN],['Infinity',Infinity],['negative',-1],['boolean',true],['empty',''],['array',[]],['missing',undefined]]){
 test(`rejects ${name} input`,()=>assert.throws(()=>run({volumeUsd:value})));
}
for(const [name,patch] of [['customer fraction',{customers:1.5}],['share above 100',{developerSharePct:101}],['negative fee',{creatorFeeBps:-1}],['not standard fee',{creatorFeeBps:100}],['utilization over 100',{utilizationPct:101}],['zero GNK price',{gnkUsd:0}],['zero cost rate',{effectiveNgonka:0}],['unsafe volume',{volumeUsd:1e20}],['unknown deposit field',{prepaidDepositsUsd:1000000}]]){
 test(`rejects ${name}`,()=>assert.throws(()=>run(patch)));
}
test('public disclosure preserves included holder access and no profit promises',()=>{
 const html=fs.readFileSync(path.join(__dirname,'../public/index.html'),'utf8');
 assert.ok(html.includes('70% of distributable surplus'));
 assert.ok(html.includes('not 70% of token purchases'));
 assert.ok(html.includes('A sign-in signature only.'));
 assert.ok(html.includes('No second payment step.'));
});
test('rejects inherited-property names as unknown inputs',()=>assert.throws(()=>run({toString:'not-a-setting'})));
test('zero customers create no payment-processing expense',()=>assert.equal(run({customers:0}).paymentFeesUsd,0));
test('refunds reduce surplus before allocation',()=>assert.equal(run({refundsUsd:100}).developerUsd,1934.38));
test('higher developer percentage does not invent company profit',()=>{const a=run(),b=run({developerSharePct:100});assert.equal(a.distributableUsd,b.distributableUsd);assert.equal(b.developerUsd,b.distributableUsd);});
