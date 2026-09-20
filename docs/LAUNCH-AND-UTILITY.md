# Slipvolt launch, membership and payments decision

Research checked 2026-09-20. **Proposal, not activated token terms.** No mint, lock program, checkout, live swap execution or fee collector has been deployed. The current holder-only mode remains a bounded included allowance with no second payment step. The proposed metered rate card is not activated checkout.

## Recommended sequence

Prove the dedicated OpenBroker account first, then launch one ordinary creator-fee token and a small funded holder pilot. Add optional locks only after their ownership, withdrawal and Token-2022 behavior have been tested. Add token-paid credits only after a finalized settlement verifier exists. Do not start by building a whole launchpad.

The customer should see **Hold → Connect → Get key → Use AI**. API-key creation is not an NFT mint or an on-chain financial transaction. The web application, not Pump, issues the key. No token holder receives ownership of the GNK reserve or a claim on developer revenue.

## Venue comparison

| Venue | Relevant finding | Decision for this project |
|---|---|---|
| Pump.fun regular launch | Published bonding-curve creator fee is 0.30%; canonical PumpSwap rates change by tier | First candidate for a single conventional token, subject to eligibility and final program checks |
| Raydium LaunchLab | Curve creator fees, CPMM creator fees and locked-LP Fee Key rights are distinct; `platform_cp_creator` can change the post-migration beneficiary | Use when explicit configuration control justifies more integration work |
| Meteora DBC | Protocol takes 20% of the **trading fee**, with the remaining fee split according to creator/partner configuration | Flexible alternative; not 20% of trading volume and not a guarantee of demand |
| StonkFun | Platform-specific fee forwarding/eligibility cannot be inferred from Raydium infrastructure alone | Not selected; obtain a current eligibility/terms check before any use |

Sources: [Pump fees](https://pump.fun/docs/fees), [Raydium creator fees](https://docs.raydium.io/products/launchlab/creator-fees), [Meteora DBC formulas](https://docs.meteora.ag/core-products/dbc/formulas). This audit could not retrieve StonkFun's full current terms through the web reader; do not treat historical terms as a fresh eligibility determination.

The current official [Pump SDK creation instructions](https://github.com/pump-fun/pump-public-docs/blob/main/docs/instructions/COIN_CREATION.md) expose `PUMP_SDK.createV2Instruction`. For this proposal choose regular mode (`holderReward: false`) and no Mayhem mode. The SOL/USDC creator schedule is not overridden by an arbitrary creator-fee argument. Keep reward mode separate from website-provided AI benefits; it redirects the creator-fee stream away from the ordinary creator wallet. Do not auto-execute sample instructions or assume documentation equals the live deployed account configuration.

Before signing: verify mint/program/decimals, creator and fee recipient, metadata URI, supply, authority settings, quote asset, transaction simulation, expected costs and graduation destination. Publish the actual mint rather than choosing by ticker. There is no token launch button in this release.

## Holding threshold: pick an affordable service entry, not an impressive number

A reasonable **pilot candidate** is 10,000 whole SLIP tokens for the included allowance. This is not a committed threshold and is not written into live configuration. Test it against the launch's actual supply and price before announcing it.

For a hypothetical one-billion-token supply, exposure implied by a 10,000-token requirement is:

| Hypothetical fully diluted value | Price/token | 10,000-token holding | 100,000-token holding |
|---:|---:|---:|---:|
| $100,000 | $0.0001 | $1 | $10 |
| $1,000,000 | $0.001 | $10 | $100 |
| $10,000,000 | $0.01 | $100 | $1,000 |

These are arithmetic examples, not price targets, forecasts or executable purchase quotes. Liquidity and slippage can change actual acquisition cost. A rising token price should not make ordinary API access unusably expensive. Review future admission thresholds on a published schedule; do not surprise existing customers or blindly use manipulable spot prices for authorization.

At six decimals, 10,000 whole tokens means `MIN_HOLDING_RAW=10000000000`. Read the actual mint decimals. Never confuse raw base units with whole coins. The app now rejects RPC balances whose decimals disagree with the configuration.

## Included allowance and abuse resistance

The pilot defaults remain 250,000 combined input/output AI tokens per wallet per UTC day, 30 requests/minute, four concurrent requests, and a finite shared pool. The small default shared ceiling is for testing, not a promise that every prospective member has a reserved full allowance. Increase only against already funded capacity and actual admission counts.

OpenBroker [documents](https://openbroker.gonka.gg/docs) 10 ngonka per token per attempt, a typical effective estimate of 10–25 after redundancy, and additional epoch accounting. Spendable balance differs from total balance, and deposits go to the assigned dashboard deposit address. The local reservation factor of 25 is a conservative planning assumption, **not a guaranteed worst-case charge**.

A full 250,000/day × 30 days consumes 7.5M AI tokens. At 25 ngonka/token this is **0.1875 GNK/member/month** before other charges. For 100 fully active members it is **18.75 GNK/month** plus overhead and epoch costs. GNK/USD changes your acquisition expense. No balance, success rate or profitability is inferred from this arithmetic.

Holding checks alone cannot stop moving one fungible balance among many wallets. Minimum observed holding age and cooldowns can reduce but do not prove continuous ownership unless a complete event history is maintained. Global budgets bound modeled exposure; they do not solve Sybil identity. Never give a new full quota for every API key, session, lock receipt, stake account or newly seen wallet.

## Optional lock-based membership

Prefer the term **lock for service benefits**, not validator staking or guaranteed yield. A SLIP lock does not produce GNK by itself. Included compute still comes from operator funding and realized service/creator revenue.

A later candidate: lock 100,000 whole tokens for seven days for higher throughput and a 10% metered-service discount. Do not enable this before a reviewed integration. A small 10% discount is preferable to repeatedly cutting an already low unit price. If there is a compute subsidy, accrue it over time against an explicit funded budget, rather than granting a whole month's credits the instant a short lock starts.

[Streamflow's lock reference](https://developers.streamflow.finance/docs/core-concepts/streams/locks) describes escrowed time-based locks and configurable recipient transferability. For membership, require non-transferable beneficiary rights and verify the actual program account, mint, owner, locked net amount, unlock time, cancellation rules and token-program compatibility. Do not assume every SPL/Token-2022 extension is supported. Review withdrawal availability independently from the website; the operator must not need a user seed phrase. No Streamflow deployment, SDK compatibility test or lock verification is included here.

Simple proportional accrual is easier to make split-invariant than fixed bonuses per receipt. A user splitting one lock into ten receipts must not earn ten times the service subsidy. On expiry or cancellation, new grants stop; previously purchased credits remain separate service obligations. Avoid APY, revenue share, token buyback promises or using users' locked tokens to trade.

## Buying API credits with SLIP

The eventual safe payment path is **SLIP → liquid native USDC on Solana → service credit**. A price widget or balance transfer is not enough.

1. Server issues a single-use invoice, required net USDC amount, owner-bound recipient/reference and expiry.
2. Quote is ExactIn with verified asset mints, raw amounts, slippage and price impact. If there is no liquid route, do not offer token payment yet.
3. Customer wallet reviews/signs the exact payment transaction. Slipvolt does not receive their seed/private key.
4. Server independently verifies finalized success, the intended payer/recipient, correct native USDC mint, invoice binding and the **net amount actually received**, including all transaction instructions and fees.
5. Atomically consume the payment identity once and issue non-transferable service credit. Deduplicate across users and repeat submissions. Handle underpayments, failed swaps, expiration, network forks and refunds explicitly.

The current Metis adapter provides step 2 **for operator previews only**. No transaction is built/sent and no customer is credited. [QuickNode's quote contract](https://www.quicknode.com/docs/solana/quote) and [swap overview](https://www.quicknode.com/docs/solana/swap-api) separate these operations. Context7/Jupiter documentation was also checked; current direct Jupiter APIs and QuickNode Metis routes must not be substituted for each other without adapting their schemas.

Do not credit SLIP at a manipulable last-trade/spot quote, promise a fixed SLIP-to-USD redemption rate, or treat unsold received SLIP as available cash. Converting a payment to USDC creates sell-side flow; using SLIP for payments does not mechanically guarantee upward price pressure. Never finance API usage by treating refundable locks as project-owned inventory.

Discounts should be versioned at invoice creation and funded from service margin. Do not compound a holding discount, staking discount and payment bonus unintentionally. At the proposed $0.075/M input and $0.30/M output, an 80/20 mix yields **$0.12/M total tokens**; a 10% discount yields $0.108/M. One billion tokens therefore yields $108–$120 revenue, not six figures. These are proposed rates, not activated checkout.

## Native GNK funding route

[HOT advertises native GNK cross-chain swaps involving SOL and USDC](https://hot-labs.org/chains/gonka). This is a route candidate, not a verified exact-size quote or completed withdrawal. Verify that the destination is actual native GNK in the intended Gonka wallet, not an internal representation. Start with an owner-approved small test.

The [official WGNK return bridge](https://gonka.ai/docs/cross-chain-transfers/ethereum-bridge/withdraw-gnk/) is a fallback. Its native receiving address derives from the Ethereum signing key; arbitrary recipient substitution and unsupported smart wallets can lose access. Receive native GNK in a verified owner-controlled wallet first and then transfer to the dedicated broker deposit address.

QuickNode Metis routes Solana swaps; 0x is EVM-side infrastructure. Neither is automatically a Solana-to-native-GNK bridge. Treasury acquisition, protocol staking and customer payments are separate workflows.

## Developer revenue and launch gates

Keep collected creator fees, earned API revenue, customer prepaid liabilities, GNK inventory, GNK consumption, stablecoin operating reserves and developer distributions separate. A proposed 70% developer / 30% retained split applies only to **distributable surplus after all costs and required reserves**, not 70% of token purchases or deposits. An appropriate salary may instead be budgeted as an explicit operating cost. Neither payment is automated here.

The admin cash ledger is not accrual bookkeeping: purchasing GNK, consuming GNK and paying the founder are different accounting events. The provider's usage summary may exclude epoch adjustment lines; reconcile the dedicated account's full balance movement rather than assuming the chart is the entire bill.

Do not call the token a share in an AI investment fund. Pump's [terms, section 21(t)](https://pump.fun/docs/terms-and-conditions) prohibit several capital-raising, pooled-investment and revenue-participation uses. Canadian legal, tax and platform eligibility review remains necessary; utility branding is not an exemption. No token popularity, trading volume, margin or return is guaranteed.

**Before launch:** fund and benchmark OpenBroker, verify actual context/output behavior on that account, fix production secrets and HTTPS, select/publish the mint and admission rules, test funded quotas with abuse cases, independently review security, establish bookkeeping and terms, and test fee entitlement before relying on it for service commitments.
