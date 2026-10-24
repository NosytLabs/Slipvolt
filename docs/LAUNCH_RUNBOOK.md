# Launch gates

Complete these gates in order. A passing local test suite is evidence about the software build, not a token launch, funded provider account, or production deployment.

1. Confirm the exact GitHub repository and review the full branch diff before merging. Preserve the existing database and pepper across upgrades.
2. Deploy the single-instance backend on persistent storage behind HTTPS. Configure the OpenBroker key and admin key privately, then restrict the operator console at the proxy or VPN.
3. Read the live provider catalog and account balance. Run an explicitly authorized bounded smoke test. Measure representative requests, streaming, usage identities, costs, epoch adjustments, and rate limits before publishing model claims.
4. Acquire native GNK through a currently verified route and an owner-approved test. Confirm the native receiving account and the deposit address shown by the dedicated OpenBroker dashboard. Keep self-custody reserve, provider spendable credit, and local allowance records separate.
5. Approve and publish token rights, holder threshold, daily and global limits, pool-exhaustion behavior, developer compensation, and launch-venue fee rights. Complete the appropriate legal review. This repository supplies none of those decisions.
6. Configure the real holder mint and raw threshold. Keep `TOKEN_LAUNCHED=false` while testing. Verify Phantom and Solflare signatures, wallet changes, revocation, a sale below threshold, restarts, high concurrency, and browser security headers.
7. Resolve cross-wallet transfer and allowance cycling before offering large recurring grants. Set monitoring and operating-reserve policies. Do not present manual allocations as on-chain deposits or provider network statistics as project adoption.
8. Verify the configured mint’s actual Pump.fun listing using the operator’s trusted source. Check the exact mint in the URL. Only then set `TOKEN_LAUNCHED=true`. The flag shows a customer link derived as `https://pump.fun/coin/{mint}`; it does not mint the token, verify a launch, prove liquidity, or prove that inference is funded.
9. Publish final service rules, operator identity, private support, privacy and retention terms, and refund policy before accepting users or funds.

Nothing in this application signs a coin launch, claim, transfer, bridge, swap, buyback, burn, or payout.
