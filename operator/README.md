# Operator-only planning tools

Open `profit-planner.html` locally or run:

```sh
node operator/calculate.cjs operator/scenario.json
```

This preserves the previously supplied founder calculator. It makes no network calls, prepares no transactions and performs no payout. It is outside the public server root. The optional paid-plan fields are scenarios, not activated products or user entitlements. Native-GNK holder limits and customer authentication are unchanged.
