# Launch, membership and payment decisions

**Proposal only.** No project mint, lock program, customer checkout, live swap, fee collector, buyback, burn schedule or developer payout is deployed by this repository. The implemented customer product is a bounded holder allowance with no second payment step.

Detailed token custody, Anchor vault, burn, treasury-waterfall and launch-venue research lives in [TOKEN-DESIGN.md](TOKEN-DESIGN.md). Re-check its dated external evidence immediately before any transaction or public launch decision.

## Recommended sequence

1. Fund and benchmark the dedicated OpenBroker account.
2. Publish the verified Solana mint, decimals, holder threshold, allowance, pool-exhaustion behavior and operator identity.
3. Run a small holder pilot with the existing hold → connect → key → AI flow.
4. Measure provider cost, capacity, abuse, support load and realized revenue.
5. Add a lock benefit only after its program, upgrade authority, withdrawal path and entitlement accounting are independently reviewed.
6. Add token-paid service credit only after finalized payment verification, replay protection, refund/dispute rules and accounting are implemented.

Do not start by building a launchpad or by presenting research as a working customer feature.

## Holding threshold and allowance

Choose an affordable pilot threshold from actual supply, liquidity, slippage, holder distribution and funded capacity. A round token count in a planning document is not a launch commitment. Publish how the threshold can change and give holders notice; do not silently authorize access from a manipulable spot-price feed.

The base allowance belongs to a wallet, not to each key, session or lock receipt. Multiple choices reserve every requested output. Moving tokens between wallets can defeat per-wallet fairness, so the finite global pool and provider budget remain necessary.

No context window is a promise of included compute. Effective model policy, remaining wallet/global quota, live capacity and native-GNK funding all constrain a request.

## Optional lock benefit

Call the proposed mechanism a **lock for service benefits**, not validator staking or guaranteed yield. Locking does not create GNK, reduce token supply or produce revenue.

Any future vault must:

- segregate user principal from the project treasury;
- count liquid and locked ownership once, without duplicate base entitlement;
- record the net amount received when transfer fees exist;
- preserve mature owner withdrawals;
- disclose admin, pause and upgrade authority;
- avoid any undisclosed project withdrawal, swap, burn or seizure path.

Use the Anchor account/instruction design and offline test requirements in `TOKEN-DESIGN.md`. Do not enable a lock based only on a website balance or an unreviewed third-party receipt.

## Optional token-paid service credit

A future payment flow should settle into a liquid accepted asset under final commercial terms. A quote widget or token transfer alone is insufficient.

1. Issue a single-use, owner-bound invoice with expiry and required net amount.
2. Obtain a fresh ExactIn quote with verified mints, raw units, slippage and minimum output.
3. Let the customer wallet review and sign the exact transaction; never request a seed phrase.
4. Independently verify finalized success, payer, recipient, mints, all instructions, fees and net amount received.
5. Atomically consume the invoice/payment identity once and create the disclosed non-transferable service credit.

Handle underpayment, expiration, failed routes, replay, forks, refunds and disputes before enabling payment. The existing Metis integration is an operator quote preview only. It does not build or send a transaction and does not credit a customer.

## Native-GNK operations

Acquire native GNK only through a route re-verified at execution time. Confirm the exact asset, custody model, destination, fees and minimum received with an owner-approved small test. The official WGNK return workflow has a same-signing-key destination constraint; it is not an arbitrary-recipient swap.

Receive native GNK into the intended owner-controlled account, then fund the deposit address assigned in the dedicated OpenBroker dashboard. Keep self-custody reserve, provider spendable balance and local allowance allocation separate. Neither QuickNode Metis nor an EVM router is automatically a Solana-to-native-GNK bridge.

## Revenue and launch gates

Creator fees can fund service only after the project actually receives them. Zero trading means zero creator-fee revenue. Platform reward modes, recipient rules, jurisdiction restrictions and fee schedules can change, so select the venue only after a fresh primary-source and on-chain configuration review.

Before launch:

- publish mint/program/treasury and material authority addresses;
- publish supply, team allocation, vesting, fee recipients and conflicts;
- fund and acceptance-test the provider;
- test the production origin, wallet extensions, quotas and failure recovery;
- establish reserves, bookkeeping, taxes, privacy, retention, support, payment and refund policy;
- obtain jurisdiction-specific platform eligibility and legal review;
- independently review any program that takes custody of user assets.

Do not describe the token as a share in an AI fund, promise returns or imply that a venue, wallet, Gonka or OpenBroker endorses the project.
