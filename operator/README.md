# Operator-only planning tools

Open `profit-planner.html` locally or run:

```sh
node operator/calculate.cjs operator/scenario.json
```

This preserves the previously supplied founder calculator. It makes no network calls, prepares no transactions and performs no payout. It is outside the public server root. The optional paid-plan fields are scenarios, not activated products or user entitlements. Native-GNK holder limits and customer authentication are unchanged.

## Holder allowance and burn scenario

Open `holder-economics.html` locally to model fully active holders, a daily AI allowance, collected creator fees, GNK acquisition cost, other provider charges, operating costs, new reserves, and optional burn/developer budgets. It includes zero-trading and doubled-GNK-price stress cases, a break-even volume calculation and a JSON export.

The $0.18 GNK default is a sensitivity assumption, not a live or executable purchase quote. Burn and developer percentages apply only to positive surplus after costs and reserves. The engine cannot accept refundable staking principal or token market capitalization as revenue; a burn budget is never reported as an executed token burn. Nothing is signed, swapped, burned, deposited or paid.

Monthly operating costs, other provider charges and reserve additions use a 30-day basis and scale with the selected scenario duration. Results cover that entire period. If a doubled-price stress case exceeds the planner's numerical bounds, it is marked unavailable without invalidating the main scenario.

Run the focused checks with `node --test tests/holder-economics.test.cjs`. The module is also usable from Node through `require('./operator/holder-economics.js')` and `project({...defaults, ...yourAssumptions})`.
