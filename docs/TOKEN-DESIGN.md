# Token, lock vault, burn, and treasury design

Research checked **24 October 2026**. This is a proposed design, not activated token terms. No mint, lock program, creator-fee collector, buyback, burn, swap, payout, or custody authority is deployed by this document. The current application remains holder-gated AI with bounded allowances. Any published mint, program ID, threshold, fee recipient, authority, or benefit schedule must come from the final reviewed deployment rather than this proposal.

## Current recommendation

Use one ordinary creator-fee token as an access credential. Keep the holder experience simple: hold the disclosed minimum, connect a wallet, create a revocable API key, and consume a funded allowance. Creator fees may replenish compute only after they have actually been received. They do not guarantee that the service will be funded, that the token will trade, or that its price will rise.

The recommended control model has three deliberately separate parts:

| Part | Owner and purpose | Permitted control |
|---|---|---|
| User wallet and optional lock vault | The user remains the beneficial owner of deposited project tokens. A lock proves time-bound commitment for service benefits. | The user signs deposits and withdrawals. The program enforces the disclosed unlock time. The developer cannot withdraw or burn user principal. |
| Project operating treasury | Holds creator fees and other earned project revenue after collection. It never contains refundable user lock principal. | A disclosed project multisig, with developer signers, may pay costs, acquire GNK, fund reserves, make approved developer distributions, or execute an optional treasury buyback and burn. |
| Provider working balance | Prepaid OpenBroker balance used for inference. It is operational working capital, not a holder reserve or redemption pool. | Funded from approved project resources. Provider debits and epoch adjustments must be reconciled before surplus is calculated. |

Developer management of the operating treasury is reasonable when it is stated plainly. The public disclosure should identify the treasury address, signer policy, upgrade authority, fee recipient, and all powers to move project-owned funds. Do not describe an account as decentralized, immutable, non-custodial, or community controlled while a developer key can change or move it. A transparent custodian is acceptable; concealed custody is not.

The working brand candidate is **Holdbyte AI / HBYTE**. It expresses holder access without implying equity, yield, or compute ownership. **Slipvolt / SVLT** preserves current product continuity, and **MintRelay / MRELAY** is a more neutral alternative. These are uncleared working names: no trademark, domain, social handle, mint, or ticker availability is claimed. Avoid VoltPass, MintLane, and Voltmint because current public uses already create unnecessary confusion.

## What each token action means

Holding, locking, burning, and spending are different acts and must remain different in the product and ledger.

- **Holding** is a wallet-balance eligibility signal. It does not transfer custody or pay for inference.
- **Locking** transfers tokens into a program vault until a disclosed time. It temporarily removes liquidity but does not reduce supply, generate GNK, or create yield.
- **Burning** permanently reduces the mint's supply. It neither transfers value to the treasury nor pays OpenBroker. Sending tokens to a so-called dead address is not equivalent to an SPL burn because the supply remains unchanged.
- **Paying for service** requires finalized settlement in an accepted asset and creates a service obligation. A token burn is not payment unless explicit commercial terms say so and the operator separately funds the resulting service credit.

For a standard SPL or Token-2022 mint, a voluntary user burn can use the token program's `BurnChecked` instruction directly. It does not require a new Anchor program. The wallet should display the exact mint, decimals, whole-token and raw amount, and irreversible supply reduction before signing. A treasury burn must be signed under the treasury multisig. The application must verify the finalized transaction and mint supply change before displaying a completed burn; an unsigned plan or submitted signature is not a burn receipt.

Do not add an extra transfer tax. Transfer taxes complicate holder balances, locks, routing, venue support, and accounting. If the final mint nevertheless has a Token-2022 transfer-fee extension, every deposit and payment must use the net amount credited to the destination rather than the sender's nominal amount. The user may also receive less on withdrawal if the token program charges a transfer fee; do not promise exact principal return in that configuration.

## Optional Anchor lock vault

The lock is a service-benefit vault, not validator staking, pooled investment, revenue sharing, or an interest account. The website may grant an off-chain benefit while an eligible lock is active, but the program does not promise an APY, token appreciation, GNK, creator fees, or project revenue.

### Accounts

The proposed Anchor program uses these accounts. Exact seeds, sizes, program IDs, and rent calculations must be fixed in an audited implementation.

| Account | Proposed fields and constraint |
|---|---|
| `ProgramConfig` PDA, seeds `["config", mint]` | Project mint, allowed token program, decimals, disclosed admin multisig, pause authority, minimum duration, maximum duration, minimum net lock, policy version/hash, total net locked, and bumps. One config per mint. |
| `VaultAuthority` PDA, seeds `["vault_authority", mint]` | Authority for the vault associated token account. It has no general-purpose instruction and cannot sign arbitrary transfers. |
| Vault ATA | Holds only the configured mint under `VaultAuthority`. It must never be the project treasury or a fee recipient. |
| `LockPosition` PDA, seeds `["position", config, owner, position_id]` | Immutable owner, position ID, net deposited amount, creation time, unlock time, withdrawn flag, and bump. Beneficiary rights are non-transferable. |

No treasury key, fee collector, or developer wallet is a vault authority. The program contains no instruction that transfers user principal to the project, burns it, uses it in a swap, delegates it, or extends its lock without the owner's signature. If a future program intentionally offers slashable, cancellable, or project-spendable deposits, that is a different product and must obtain explicit agreement under separately reviewed terms.

### Instructions

1. **`initialize_config`** — authorized by the disclosed deployment multisig. It fixes the project mint, token program, decimals, initial duration bounds, and benefit-policy identifier. It rejects a mint or token program mismatch.
2. **`create_position(position_id, requested_amount, unlock_time)`** — the owner signs. The program validates duration and raw units, records the vault ATA balance, performs `TransferChecked`, reloads the ATA, and stores the observed balance increase as `net_deposited`. A nominal amount is never used as the position principal when transfer fees exist.
3. **`add_to_position(requested_amount)`** — optional and owner-signed. It may increase principal and extend, but never shorten, the unlock time. It records only the observed net credit.
4. **`extend_position(new_unlock_time)`** — owner-signed, monotonically increases the unlock time within configured bounds.
5. **`withdraw_position`** — owner-signed and available after the recorded unlock time. It transfers the position's remaining vault amount to the owner's ATA and closes or marks the position withdrawn. The recommended program does not let an admin pause matured withdrawals.
6. **`update_future_policy`** — multisig-only and limited to future deposits and off-chain policy metadata. It cannot change an existing position's owner, net principal, or unlock time.
7. **`pause_new_deposits`** — multisig-only. It prevents new or increased positions during an incident while preserving owner withdrawals when their locks mature.

Use checked arithmetic, Solana's `Clock`, canonical associated token accounts, exact owner and mint constraints, position-specific replay protection, and an explicit allowlist of supported Token-2022 extensions. Reject unknown transfer hooks, permanent delegates, confidential-transfer behavior, or other extensions until their authority and settlement effects have been reviewed. Six decimals may match a Pump `create_v2` token, but the program must read and pin the actual mint decimals rather than assume them.

### Entitlement calculation

Moving tokens from a wallet into the vault must not create a second copy of the same entitlement. For a wallet `w`, calculate ownership once:

`qualifying_amount(w) = finalized_liquid_balance(w) + sum(active net lock principal owned by w)`

The base holder allowance is assigned once per wallet from that combined amount. A lock tier may modify rate limits, duration, or an explicitly budgeted discount, but it must not grant another full base allowance for every receipt. Splitting 100,000 tokens among ten positions must have the same economic effect as one 100,000-token position with the same duration. Expired or withdrawn positions stop contributing. The vault's aggregate token balance is never counted as a project holding or again as a single holder.

### Prevent sequential allowance reuse

The current application checks each wallet's finalized liquid balance immediately before a new request and accounts for daily usage by wallet. It does **not** prevent the same fungible tokens from qualifying wallet A, moving to wallet B after A consumes its allowance, and qualifying B during the same UTC day. A loses permission to start new calls after the transfer is finalized, but B has a separate usage ledger. Global daily quotas and funded reservation budgets continue to limit admission; they do not establish one daily benefit per set of tokens.

Before a public launch, choose and implement one explicit entitlement policy. The recommended lock option qualifies principal only for allowance periods during which it remains locked to the same owner; publish the activation cutoff and require the unlock time to cover the entire period. Moving or withdrawing the same principal must not create another benefit in that period. A fixed-boundary daily holder snapshot is an alternative: only wallets eligible at the published cutoff receive that day's allowance, and later recipients wait until the next cutoff. That alternative intentionally keeps the original wallet's snapshotted benefit after a sale and changes the current immediate holder-check policy.

An on-demand positive eligibility cache is not a mitigation: caching A when A first calls and B when B later receives the tokens can preserve both entitlements. The current software implements neither period locks nor fixed-boundary snapshots. Treat this as an unresolved launch requirement, and test transfers, cutoff boundaries, withdrawn positions, and split positions before claiming reuse prevention.

### Upgrade authority

An upgradeable Solana program can acquire new custody behavior after users deposit. That is a material custody risk even if version one has no seizure instruction. Before accepting deposits, either revoke the upgrade authority after independent review or place it behind a published multisig and time-delayed, monitored upgrade process. Publish the authority address and change policy. A website promise cannot offset an undisclosed unilateral upgrade key.

## Treasury, fees, and optional burns

Use actual creator-fee receipts, not market capitalization, reported trading volume, unclaimed fees, unsold team tokens, borrowed funds, user lock principal, or customer prepayments, when determining spendable revenue. Keep separate ledger accounts for creator fees, earned service revenue, customer obligations, stablecoin cash, native GNK inventory, OpenBroker prepaid balance and debits, user vault principal, developer compensation, and burn expenditure.

Apply this monthly waterfall before any optional allocation:

1. Reconcile received creator fees and earned service revenue.
2. Pay or accrue inference usage, OpenBroker `escrow_epoch` adjustments, hosting, RPC, support, swaps, gas, refunds, taxes, and other operating liabilities.
3. Restore the prepaid-provider requirement and the approved operating/customer-obligation reserve.
4. If the remainder is positive, a **working proposal** allocates 10% to an optional treasury buyback-and-burn budget, 70% to a disclosed developer distribution, and 20% to retained project capital.
5. If the remainder is zero or negative, every optional allocation is zero.

The 10/70/20 figures are editable policy assumptions consistent with the offline holder-economics tool, not on-chain entitlements. A developer salary already recorded as an operating cost must not also be hidden inside the 70% allocation. Retained capital is not automatically another token purchase. No holder owns the treasury or has a claim on these percentages.

At 1,000 fully active holders, 100,000 combined AI tokens per holder per day, and 30 days, maximum modeled use is **3 billion AI tokens**. At 25 ngonka per token, the upper end of OpenBroker's [documented usual effective range](https://openbroker.gonka.gg/docs/pricing), variable provider cost is **75 GNK**. At an illustrative acquisition price of **$0.18/GNK**, that is **$13.50**. OpenBroker [epoch adjustments](https://openbroker.gonka.gg/docs/usage), hosting, RPC, support, slippage, tax, and other costs are excluded, so $13.50 is not the total bill. That typical range is not a contractual maximum provider charge.

At $10,000 of eligible daily trading volume and a 0.30% creator share, gross creator fees are $30/day or **$900 over 30 days**, before venue behavior, collection failures, costs, reserves, and tax. At zero trading volume, creator-fee revenue is zero while service costs remain. Thin liquidity or ineligible/non-canonical pools may also produce little or no creator revenue. These examples show a possible funding margin; they do not create demand or guarantee profitability.

For a hypothetical one-billion-token supply, 100,000 tokens are 0.01% of supply and 1,000,000 are 0.1%. The affordability changes sharply with valuation:

| Hypothetical fully diluted value | Price per token | 100,000 tokens | 1,000,000 tokens |
|---:|---:|---:|---:|
| $100,000 | $0.0001 | $10 | $100 |
| $1,000,000 | $0.001 | $100 | $1,000 |
| $10,000,000 | $0.01 | $1,000 | $10,000 |

These are arithmetic examples, not price targets or an economic commitment. Select a pilot threshold only after observing real supply, liquidity, acquisition slippage, funded capacity, and holder distribution. Publish how and when the threshold may change.

## Launch venue findings

Pump's current [tokenized-agent disclaimer](https://pump.fun/docs/tokenized-agent-disclaimer) describes an opt-in, centrally administered hourly buyback-and-burn mechanism using a selected percentage of deposited SOL, USDC, USDT, or USD1; the remainder stays creator-claimable. Deposited assets are nonrefundable under that mechanism. It is not staking and should not be described as a user lock vault. Pump's separate holder-reward mode redirects creator fees, so it conflicts with a plan that expects the ordinary creator-fee stream to fund compute.

Pump's official [`create_v2` instructions](https://github.com/pump-fun/pump-public-docs/blob/main/docs/instructions/COIN_CREATION.md) describe a Token-2022 mint with six decimals. The arbitrary `creator_fee_bps` argument is ignored for SOL and USDC pairs, so final economics must use the actual program and pair configuration rather than a desired number in client code. Pump [terms section 21(t)](https://pump.fun/docs/terms-and-conditions) restricts capital raising, pooled investment, profit or revenue participation, and ownership-like claims. Market the token as disclosed service access, not a share in an AI business or reserve.

StonkFun's [developer documentation](https://www.stonkfun.xyz/developers) exposes StandardV2 fee-recipient configuration and platform-controlled reward tiers. Its [live public native-USDC pricing response](https://www.stonkfun.xyz/api/public/v1/launchlab/pricing?quoteMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v) reported `standardV2Enabled: false` on 24 October 2026. Standard launches do not supply the desired transfer tax, and platform withholding/reward authority is distinct from a project vault. More decisively, the Terms presented by the [StonkFun site](https://www.stonkfun.xyz/) restrict people in the United States, Canada, and United Kingdom in section 4 based on citizenship, residence, location, or access. It is therefore not a launch recommendation for a Canadian user, and those restrictions must not be bypassed.

### StockLaunch correction and current fit

The following are indexed official-page statements. Direct homepage and documentation retrieval repeatedly returned HTTP 502 during this review, so these statements are not evidence of a successful live launch or a tested program deployment.

**Source check: 24 October 2026.** [StockLaunch](https://stocklaunch.world/) is a distinct, community-built Solana launch interface using Meteora Dynamic Bonding Curve; it is not StonkFun, and the separate [stocklaunch.ink](https://stocklaunch.ink/) project was not used as evidence because no relationship was verified. StockLaunch's indexed official pages describe fixed-supply launches, curve trading, and graduation to DAMM v2. The creator recipient, selected reward asset, creator/holder fee split, configuration, migration destination, and liquidity-lock policy are intended to become immutable at launch. The [flow description](https://stocklaunch.world/docs/how-it-works) says a program-derived reward vault claims curve-stage and migrated-pool fees, converts an earmarked share into an approved tokenized-stock reward, and leaves the creator and holder destinations fixed. This is planned program custody rather than creator custody; StockLaunch says the vault has no private key or privileged sweep path.

Do not conflate a **reward pairing** with the DBC pool's quote mint. StockLaunch's current flow selects a tokenized equity as the reward asset and describes unconverted SOL remaining in the vault. Meteora's [official DBC developer guide](https://github.com/MeteoraAg/docs/blob/main/developer-guides/dbc/index.mdx) separately confirms that a DBC configuration chooses its quote mint. Its standard mainnet keepers list wrapped SOL, USDC, TRUMP, JUP, USD1, MET, JupUSD and VIRTUAL, plus qualifying Stock Token quote pairs and qualifying Jupiter-verified mints; Stock Token thresholds must be at least USD 750 equivalent. The actual StockLaunch pool configuration must therefore be read on-chain before claiming that a launch trades directly against a stock token.

Fee claims are also provisional. The homepage advertises a configurable 0–50% trading-fee tier and 100% creator share by default, while the [fee documentation](https://stocklaunch.world/docs/fees) declines to publish effective percentages until verified configuration accounts exist. It says a paired launch may divide fees among Meteora, the launch partner, a fixed creator recipient, the reward vault, and keeper costs; the creator can choose only within on-chain bounds, and the split cannot change after launch. No StockLaunch page reviewed describes a project-token burn or staking feature. Meteora offers separate generic locking and farm products, but those are not part of the documented StockLaunch launch flow.

StockLaunch is not currently a usable recommendation. Its [terms](https://stocklaunch.world/terms) are version 0.1 and label the product pre-production. Its [reward registry](https://stocklaunch.world/stocks) reports no verified reward assets, its [trust model](https://stocklaunch.world/docs/trust-model) says the reward program is not deployed and reward writes are disabled, and its [eligibility page](https://stocklaunch.world/eligibility) says no compliance provider is configured. The [restricted-jurisdiction page](https://stocklaunch.world/restricted-jurisdictions) explicitly includes Canada, the United States, United Kingdom, and Australia. Even if those readiness and eligibility blocks change, diverting creator fees into stock rewards would compete with the AI compute reserve; suitability would require verified on-chain fee recipients, conversion routes, migration settings, and enough retained creator revenue to fund the holder allowance.

On current evidence, evaluate a normal Pump creator-fee coin first, with holder rewards off, no extra transfer tax, exact authorities disclosed, and no claim that Pump's optional burn service is the project's lock program. Re-check live program accounts, fees, terms, jurisdictional eligibility, graduation path, and recipient authority immediately before any proposed signing transaction.

## Swap and buyback safeguards

Any future treasury buyback uses a fresh **ExactIn** quote with explicit input mint, output mint, raw input amount, maximum slippage, minimum output, route expiry, and price impact. Permit only reviewed mints, token programs, swap programs, account metas, and instruction types. Re-fetch immediately before construction, simulate the exact transaction, invalidate stale quotes, and require the treasury multisig to inspect and sign it. Verify finalized net tokens received before preparing a separate `BurnChecked` instruction.

No quote authorizes execution. Do not silently substitute routers, wrap native assets, add unknown fee accounts, accept an output below `min_out`, or keep a signing key in the web server. The current system may show a sanitized operator preview only; it does not execute a swap or credit a customer.

## Required offline tests and launch evidence

Before a lock program is proposed for deployment, run local validator/`solana-program-test` coverage for ordinary SPL and every allowed Token-2022 extension. Tests must cover wrong mint/program/owner, decimal mismatch, nominal-versus-net transfer-fee accounting, early withdrawal, mature withdrawal, double withdrawal, replayed position IDs, overflow, clock boundaries, frozen accounts, paused deposits with withdrawals still available, and rejection of unsupported extensions. Property tests must show split-invariant entitlement and prove that liquid plus locked balances never double-count principal.

Security review must demonstrate that no admin, treasury signer, upgrade authority, transfer-hook authority, mint authority, freeze authority, or permanent delegate can seize or burn vault principal outside the published design. Test upgrades and authority rotation on a local validator. Review all PDA seeds, CPI signer scopes, account close destinations, rent recipients, token account owners, and remaining-account parsing.

Economics tests must include zero trading, zero collected-fee percentage, thin fees, doubled GNK acquisition cost, maximum holder utilization, provider epoch adjustments, missing swap liquidity, and reserve restoration. The offline scenario is planning evidence only; it cannot authorize a payment or prove future revenue.

The existing AntSeed seller remains unchanged. Its [independent public AntSeedStats listing](https://antseedstats.com/sellers/0x7b35030f77793159e86933e678b4e502c8fd9509) currently reports explicit **FREE** pricing and, since 28 September 2026, approximately **12.07M tokens, 895 requests, and 57 buyers**, while paid revenue, settlements, paid tokens, and paid requests remain zero. Advertised IDs are `deepseek-v4-flash-0731`, `glm-5.3-flash`, and `minimax-m2.7`. Buyer-signed free usage is useful demand evidence but is not collected revenue and cannot fund the waterfall. This design makes no AntSeed configuration or pricing change.

Before publishing token terms, obtain jurisdiction-specific legal and tax review, disclose every authority and material conflict, fund the provider and operating reserve, verify creator-fee entitlement on the actual launch configuration, audit the lock program, publish the final mint/program/treasury addresses, and run a small owner-approved end-to-end test. Until then, all percentages, thresholds, names, and mechanisms in this document remain proposals.
