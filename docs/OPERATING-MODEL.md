# Operating model

## User product

1. Hold the configured Solana project token.
2. Connect a supported wallet and sign a login-only message.
3. Slipvolt checks finalized holdings.
4. Create a revocable `sv_` API key.
5. Use the live OpenBroker/Gonka model catalog through `/v1/chat/completions`.
6. Wallet and global allowances, RPM/concurrency and native-GNK funding all limit dispatch.

No token burn or transfer is required to create a key. The holder coin is an access credential, not a claim on the GNK treasury.

## Funding loop

Initial owner GNK + collected creator fees + earned service revenue → operating costs/reserves → native GNK acquired by an owner-approved route → dedicated OpenBroker deposit address → funded holder allowance.

The safest implementation keeps swaps/bridges owner-approved and outside the web server. Slipvolt never stores a treasury signing key.

HOT/NEAR Intents currently advertises native GNK routes from SOL/USDC and should be quote-tested first. The official WGNK Ethereum bridge remains a fallback; its same-signing-key Gonka destination rule must be followed. Neither route is assumed executable without a current quote and a small test transfer.

## Developer economics

Pump.fun creator fees can be one revenue source, but creator fee percentage, trading volume and post-graduation tiers are not guaranteed. Service revenue should be independently viable. The admin cash ledger records only realized entries.

The operator can choose a disclosed developer compensation policy from genuine surplus after compute, infrastructure, customer obligations/reserves and tax provisions. Slipvolt does not automate developer payouts.
