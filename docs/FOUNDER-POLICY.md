> Preserved proposal from the supplied founder update. This calculator does not activate paid subscriptions, reserve token benefits, authorize transfers or create a payout entitlement. Current live configuration and holder limits are unchanged.

# Slipvolt: developer-income model

**Working proposal · 19 September 2026 · USD scenarios, not earnings forecasts.**

## The product stays simple

Hold the published minimum → connect a wallet → create an API key → consume a
bounded, funded daily allowance. The existing included holder experience, model
routing, wallet checks and security limits are unchanged by this update. It does
not require a second payment or burn the membership token.

The native-GNK treasury funds compute. Keep the OpenBroker working balance and
native reserve wallet separate; keep operating cash/stablecoins separately too.
Buying GNK with all incoming money leaves nothing for hosting or developer income.
No token holder is promised ownership of reserves, a redemption right or a return.

## Proposed developer compensation: 70% of surplus

First reconcile collected creator fees and earned service revenue, then pay
provider charges (including epoch adjustments), staff/hosting/RPC/gas, refunds and
other accrued obligations. Provide for taxes and restore the required cash and
native-GNK reserves. A proposed reserve objective is 90 days of budgeted operating
costs plus the unfulfilled paid-service commitment; avoid counting the same
obligation twice. Paid customers must not depend on future token trading.

Only then split remaining distributable cash: **70% operator, 30% retained**.
The retained portion is additional business capital, not automatically another
GNK purchase. This split is a proposal disclosed on the site, not an automatic
on-chain rule. Founder salary already charged as an operating cost must be
reported separately so it is not hidden or counted twice. Personal taxes can
further reduce the founder's final take-home.

A zero or negative remainder produces zero allocation. Unrealized GNK gains,
market capitalization, liquidity-pool balances, borrowed money and unused customer
top-ups are not service revenue. Prior unresolved provider charges must be settled
or adequately reserved; a spreadsheet result is never authority to transfer funds.

## Two revenue sources

1. **Standard Pump creator fees**, actually received on eligible trades. The
   bonding-curve creator share currently listed is 0.30%, not the 1.25% total fee.
   Canonical PumpSwap rates vary, including rates as low as 0.05%; non-canonical
   pools may provide no creator share. Use collected receipts, not notional volume,
   for actual books. A 0.30% scenario is not a promise of that blended future rate.
2. **Optional paid upgrades**, earned through service delivery. Keep included
   holder access free of extra subscription charges. One test candidate is
   $29/month for up to 500M combined AI tokens, with explicit per-request and
   concurrency limits. This is a hypothesis, not a live plan or guaranteed offer.

Paid plans need their own entitlement and funding accounting, verified checkout,
refund/cancellation handling, capacity tests and usage controls before charging.
A global 50M/day holder pool is not capacity for 100 new paid customers each using
500M/month. No paid quota or checkout is enabled in this release.

A buyer can compare this service with direct OpenBroker access. Convenience,
wallet onboarding, useful integrations and support must earn the premium; cheap
upstream compute alone is not a durable advantage. Do not promise dedicated
capacity or an uptime target without the infrastructure and measured results.

## Pump coin settings to evaluate

Use a standard creator-fee coin, not holder-rewards mode, because holder-rewards
redirects that fee entitlement to holders. The website's AI allowance is a
separate benefit; it does not require Pump's holder-rewards setting.

Prefer no extra transfer tax. Underlying Pump fees are set by its programs, not
by this planner. A founder share of business surplus is NOT a new per-trade tax.
Set the exact recipient and ownership process, disclose team holdings and any
vesting, publish a verified mint only after deployment, and review the final
transaction before signing. No ticker, mint, fundraising or dev buy was created.

Do not lock in a gross on-chain split by accident: Pump's documented
update_fee_shares_v2 applies a final shareholder list and revokes its admin.
That cannot implement an off-chain 'only after all business costs' condition.
Account and distribute from treasury after reconciliation instead of claiming
that an immutable gross split knows the company's liabilities.

Before launch, get Canadian legal/tax review of the actual offering and marketing.
This document is a business design, not clearance to conduct a regulated activity.

## Worked example: full paid usage, not only idle subscribers

Assumptions: $1M monthly eligible trading volume, a 0.30% effective creator share,
100 paying customers at $29, 500M AI tokens used by each, plus 1.5B holder tokens
monthly. GNK acquisition value is assumed to be $1, NOT a live price. Effective
compute uses the documented 15-ngonka estimate; it is not a maximum cost.

| Item | Hypothetical monthly USD |
|---|---:|
| Collected creator-fee equivalent | 3,000.00 |
| Earned paid-service revenue | 2,900.00 |
| Token-level compute (772.5 GNK at assumed $1) | -772.50 |
| Assumed extra epoch/provider cost (50 GNK) | -50.00 |
| Assumed operating costs | -600.00 |
| Assumed payment fees (2.9% + $0.30/customer) | -114.10 |
| New tax/customer/runway provisions | -1,500.00 |
| Distributable surplus | 2,863.40 |
| Proposed developer allocation (70%) | **2,004.38** |
| Additional retained capital (30%) | 859.02 |

Payment costs and operating costs here are assumptions, not provider quotes.
The $1,500 line is a modeled reserve ADDITION, not an assertion that an existing
reserve is funded. Replace it with actual required additions before each period.
The holder cost intentionally tests the full 50M/day headline pool for 30 days;
existing GNK reservation limits can admit less usage. An operational usage cap
must not be mistaken for a guaranteed upper bound on upstream cost.

At unchanged costs/customers, $5,000 developer allocation requires approximately
$2.426M eligible monthly volume at 0.30%. At 0.05% it requires approximately
$14.559M. These are algebraic requirements, not predictions, growth advice or a
reason to manufacture trading volume. More genuinely paying customers reduces
dependence on speculative volume. In the zero-volume example, reserve additions
leave no developer allocation; the funding gap is $136.60.

The $29 plan has approximately $20.36 per-customer contribution after full included
compute and assumed payment fees, but BEFORE shared epoch costs, overhead, taxes,
refunds, customer acquisition and support. At $2/GNK and 30 effective ngonka per
token, it loses money at full usage. Validate both price and capacity before sale.

## Run the local planner

Open operator/profit-planner.html or the standalone HTML supplied with this build.
It runs entirely locally. No analytics, keys, wallets, network calls or storage.
Change assumptions and export the resulting scenario, not a transaction.

```sh
node operator/calculate.cjs
node operator/calculate.cjs operator/scenario.json
node --test tests/business.test.cjs tests/frontend.test.cjs
```

The same math module drives the CLI and browser. Refunds, deficits and reserve
additions reduce the distributable remainder. The target solver reports no finite
solution when the fee or developer share is zero and service earnings do not
satisfy the target. Inputs reject non-finite, unknown or nonsensical values. Money
is rounded for scenario display; this is intentionally NOT a settlement ledger.

## Sources checked on 19 September 2026

- Pump fee schedule: https://pump.fun/docs/fees
- Pump holder rewards: https://github.com/pump-fun/pump-public-docs/blob/main/docs/HOLDER_REWARDS_README.md
- Pump creator fee sharing: https://github.com/pump-fun/pump-public-docs/blob/main/docs/instructions/CREATOR_FEE_SHARING.md
- OpenBroker accounting, balance and usage: https://openbroker.gonka.gg/docs
- OpenBroker activation/capacity: https://openbroker.gonka.gg/
- Native GNK bridge: https://gonka.ai/docs/cross-chain-transfers/ethereum-bridge/withdraw-gnk/

OpenBroker documents per-attempt 10-ngonka pricing, typical redundancy leading to
10–25 effective ngonka, estimated vs settled usage and extra escrow_epoch charges.
Neither the typical range nor this planner's assumptions bound future bills.
Public docs were refreshed. No private account, live paid request, coin launch,
bridge, swap, checkout, developer payout or remote repository change was executed.
