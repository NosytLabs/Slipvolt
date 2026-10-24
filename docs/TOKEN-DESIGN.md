# Token, lock vault, burn, and treasury design

Research checked **24 October 2026**. This is a proposed design, not activated token terms. No mint, lock program, creator-fee collector, buyback, burn, swap, payout, or custody authority is deployed by this document. The current application remains holder-gated AI with bounded allowances. Any published mint, program ID, threshold, fee recipient, authority, or benefit schedule must come from the final reviewed deployment rather than this proposal.

## Current recommendation

Use one ordinary creator-fee token as an access credential. Wallet holdings may support a limited onboarding check, but a recurring period allowance should activate only from principal locked before the next published period boundary and committed through that entire period. Do not grant one recurring allowance from liquid holdings and another from the same principal after it is locked. Creator fees may replenish compute only after finalized receipts are reconciled. They do not guarantee that the service will be funded, that the token will trade, or that its price will rise.

The recommended control model has three deliberately separate parts:

| Part | Owner and purpose | Permitted control |
|---|---|---|
| User wallet and proposed lock vault | Liquid tokens remain under the user's control. One position-owned vault per wallet may prove next-period eligibility without transferring principal to the project. | The owner signs deposits and mature withdrawals. A pause may stop deposits but never a mature owner withdrawal. No admin can sweep or burn principal. |
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

Do not add an extra transfer tax. Transfer taxes complicate holder balances, locks, routing, venue support, and accounting. The minimal vault prototype may support the original Token Program and an explicitly reviewed Token-2022 mint shape. It must reject transfer-fee, transfer-hook, permanent-delegate, confidential-transfer, and unknown extensions until each extension's authority, accounting, withdrawal, and client-compatibility effects have been reviewed.

## Optional Anchor lock vault

The lock is a service-benefit vault, not validator staking, pooled investment, revenue sharing, or an interest account. The website may grant an off-chain benefit while an eligible lock is active, but the program does not promise an APY, token appreciation, GNK, creator fees, or project revenue.

### Accounts

The proposed Anchor program uses these accounts. Exact seeds, sizes, program IDs, and rent calculations must be fixed in an audited implementation.

| Account | Proposed fields and constraint |
|---|---|
| `ProgramConfig` PDA, seeds `["config", mint]` | Project mint, allowed token program, decimals, disclosed admin multisig, pause authority, period boundary rules, minimum amount, duration bounds, policy version/hash, total locked, and bump. One config per mint. |
| `LockPosition` PDA, seeds `["position", config, owner]` | The owner address's single position and vault authority: immutable owner, deposited amount, creation time, eligibility start, unlock time, accepted policy version, withdrawn state, and bump. Beneficiary rights are non-transferable. |
| Position vault ATA | Holds only the configured mint for one `LockPosition` PDA. It is never a shared treasury, fee recipient, or source for another owner's withdrawal. |

No treasury key, fee collector, or developer wallet is a vault authority. The program contains no instruction that transfers user principal to the project, burns it, uses it in a swap, delegates it, or extends its lock without the owner's signature. If a future program intentionally offers slashable, cancellable, or project-spendable deposits, that is a different product and must obtain explicit agreement under separately reviewed terms.

### Instructions

1. **`initialize_config`** — authorized by the disclosed deployment multisig. It fixes the project mint, token program, decimals, period rules, and benefit-policy identifier. It rejects a mint, token program, or unsupported extension mismatch.
2. **`create_position(requested_amount, unlock_time)`** — the owner signs. The program permits one position for that owner, validates raw units and the next eligibility boundary, transfers into the position-owned ATA, and records the verified credited amount. The unlock must fall at or after the end of every allowance period the position can qualify for.
3. **`withdraw_position`** — owner-signed and available at the recorded unlock time. It transfers that position's remaining amount to the owner's ATA and returns refundable account rent to the owner. Mature withdrawal remains available when new deposits or policy changes are paused.
4. **`update_future_policy`** — multisig-only and limited to future deposits and off-chain policy metadata. It cannot change an existing position's owner, principal, eligibility start, accepted policy, or unlock time.
5. **`pause_new_deposits`** — multisig-only. It prevents new positions during an incident while preserving owner withdrawals when their locks mature.

The first version omits top-ups, position transfers, lock extensions, slashing, rewards, swaps, and treasury execution. Adding principal later would require separate next-period accounting and must not rewrite an already active entitlement.

Use checked arithmetic, Solana's `Clock`, canonical associated token accounts, exact owner and mint constraints, and position-specific replay protection. The minimal version uses an extension allowlist and rejects transfer fees, transfer hooks, permanent delegates, confidential-transfer behavior, and unknown extensions. Six decimals may match a Pump `create_v2` token, but the program must read and pin the actual mint decimals and extension set rather than assume them.

### Entitlement calculation

Moving tokens from a wallet into the vault must not create a second copy of the same entitlement. For recurring grants, use only the owner wallet's single active lock position at the published period boundary:

`qualifying_amount(w, period) = locked_principal(w) committed before the boundary and through period end`

Liquid balance does not add a simultaneous recurring grant. A newly created position waits until the next boundary. Expired or withdrawn principal does not qualify for a later period, and a position vault is never counted as a project holding. One position per owner address removes position-splitting within that wallet. One person can still own several wallets; each qualifying balance must independently remain locked through the period.

### Prevent sequential allowance reuse

The current application checks each wallet's finalized liquid balance immediately before a new request and accounts for daily usage by wallet. It does **not** prevent the same fungible tokens from qualifying wallet A, moving to wallet B after A consumes its allowance, and qualifying B during the same UTC day. A loses permission to start new calls after the transfer is finalized, but B has a separate usage ledger. Global daily quotas and funded reservation budgets continue to limit admission; they do not establish one daily benefit per set of tokens.

Before a public launch, implement one explicit entitlement policy. The recommended policy grants a recurring allowance only for the next period when the same owner's position was funded before the published boundary and remains locked through period end. Liquid holdings alone do not receive that recurring grant. A position created after the cutoff waits for the following period, so moving tokens between wallets cannot activate a second allowance immediately.

An on-demand positive eligibility cache is not a mitigation: caching A when A first calls and B when B later receives the tokens can preserve both entitlements. The current software does not implement lock-based period eligibility. Treat this as an unresolved launch requirement and do not advertise cycling prevention until the program and entitlement service enforce the same boundary.

### Upgrade authority

An upgradeable Solana program can acquire new custody behavior after users deposit. That is a material custody risk even if version one has no seizure instruction. Before accepting deposits, either revoke the upgrade authority after independent review or place it behind a published multisig and time-delayed, monitored upgrade process. Publish the authority address and change policy. A website promise cannot offset an undisclosed unilateral upgrade key.

## Treasury, fees, and optional burns

Use actual creator-fee receipts, not market capitalization, reported trading volume, unclaimed fees, unsold team tokens, borrowed funds, user lock principal, or customer prepayments, when determining spendable revenue. Keep separate ledger accounts for creator fees, earned service revenue, customer obligations, stablecoin cash, native GNK inventory, OpenBroker prepaid balance and debits, user vault principal, developer compensation, and burn expenditure. The application's current manual business ledger can record an operator entry, but it does not verify an on-chain receipt, custody balance, swap, or burn.

Require a traceable accounting chain before any optional allocation:

1. Verify a finalized creator-fee or earned-service receipt at the disclosed destination, including asset, raw amount, transaction, and source.
2. Recognize the receipt in the project reserve, then record any approved transfer to operating reserves or the provider working balance.
3. Reconcile inference usage, OpenBroker `escrow_epoch` adjustments, hosting, RPC, support, gas, refunds, taxes, and other liabilities before calculating surplus.
4. Authorize any optional buyback only from positive reconciled surplus, with its own transaction and custody evidence.
5. Record a burn only after `BurnChecked` is finalized and the purchased token balance and mint-supply reduction are verified.

The offline holder-economics tool may use allocation percentages as editable scenario inputs. They are planning assumptions, not this document's recommendation, on-chain entitlements, or evidence that revenue was received. A developer salary recorded as an operating cost must not also be counted as a surplus distribution. Retained capital is not automatically another token purchase, and no holder owns the treasury.

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

Pump's current [tokenized-agent disclaimer](https://pump.fun/docs/tokenized-agent-disclaimer) describes an opt-in creation flow with a centrally administered hourly buyback-and-burn mechanism using a selected percentage of deposited SOL, USDC, USDT, or USD1; the remainder stays creator-claimable. The reviewed documentation does not establish automatic forwarding of ordinary creator fees into that deposit address, so any fee-to-agent transfer must be verified and accounted for separately. It also does not by itself prove whether a later opt-in path exists for every token; confirm the actual launch interface and program state before making that claim. Deposited assets are nonrefundable under the documented mechanism. It is not staking and should not be described as a user lock vault. Pump's separate holder-reward mode redirects creator fees, so it conflicts with a plan that expects the ordinary creator-fee stream to fund compute.

Pump's official [`create_v2` instructions](https://github.com/pump-fun/pump-public-docs/blob/main/docs/instructions/COIN_CREATION.md) describe a Token-2022 mint with six decimals. The arbitrary `creator_fee_bps` argument is ignored for SOL and USDC pairs, so final economics must use the actual program and pair configuration rather than a desired number in client code. Pump [terms section 21(t)](https://pump.fun/docs/terms-and-conditions) restricts capital raising, pooled investment, profit or revenue participation, and ownership-like claims. Market the token as disclosed service access, not a share in an AI business or reserve.

StonkFun's [developer documentation](https://www.stonkfun.xyz/developers) exposes StandardV2 fee-recipient configuration and platform-controlled reward tiers. Its [live public native-USDC pricing response](https://www.stonkfun.xyz/api/public/v1/launchlab/pricing?quoteMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v) reported `standardV2Enabled: false` on 24 October 2026. Standard launches do not supply the desired transfer tax, and platform withholding/reward authority is distinct from a project vault. More decisively, the Terms presented by the [StonkFun site](https://www.stonkfun.xyz/) restrict people in the United States, Canada, and United Kingdom in section 4 based on citizenship, residence, location, or access. It is therefore unavailable under those terms to the listed users; the restrictions must not be bypassed.

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

Before a lock program is proposed for deployment, run local validator/`solana-program-test` coverage for every supported Token Program and reviewed mint shape. Cover owner, mint, decimals, early and mature withdrawal, repeat withdrawal, clock boundaries, paused deposits with mature withdrawals still available, and rejection of transfer-fee, hook, permanent-delegate, confidential, and unknown extensions. Verify that only one position exists per owner and that liquid balances cannot add a second recurring grant.

Security review must demonstrate that no admin, treasury signer, upgrade authority, transfer-hook authority, mint authority, freeze authority, or permanent delegate can seize or burn vault principal outside the published design. Test upgrades and authority rotation on a local validator. Review all PDA seeds, CPI signer scopes, account close destinations, rent recipients, token account owners, and remaining-account parsing.

Economics tests must include zero trading, zero collected-fee percentage, thin fees, doubled GNK acquisition cost, maximum holder utilization, provider epoch adjustments, missing swap liquidity, and reserve restoration. The offline scenario is planning evidence only; it cannot authorize a payment or prove future revenue.

The existing AntSeed seller remains unchanged. Its [independent public AntSeedStats listing](https://antseedstats.com/sellers/0x7b35030f77793159e86933e678b4e502c8fd9509) was checked on 24 October 2026 and identifies the verified seller as **OMA-AI**, with explicit **FREE** pricing and approximately **15.90M free tokens, 1.08K requests, and 67 buyers** since 28 September 2026. Paid revenue, settlements, paid tokens, and paid requests were zero. These are the independent dashboard's observations, not measurements by Holdbyte; its free-usage events are buyer-signed reports without payment attached. Advertised IDs are `deepseek-v4-flash-0731`, `glm-5.3-flash`, and `minimax-m2.7`. Buyer-signed free usage is useful demand evidence but is not collected revenue and cannot fund the waterfall. This design makes no AntSeed configuration or pricing change.

Before publishing token terms, obtain jurisdiction-specific legal and tax review, disclose every authority and material conflict, fund the provider and operating reserve, verify creator-fee entitlement on the actual launch configuration, audit the lock program, publish the final mint/program/treasury addresses, and run a small owner-approved end-to-end test. Until then, all percentages, thresholds, names, and mechanisms in this document remain proposals.
