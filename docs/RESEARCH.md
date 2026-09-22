# Slipvolt research/audit snapshot — September 20, 2026

This document records the external facts that drive the current implementation. Re-check them before a public launch because model catalogs, network parameters, provider pricing and launchpad fees can change.

## OpenBroker setup

OpenBroker describes itself as “a broker for brokers”: create an account, create a private `obk-` key, deposit **native GNK** to the dashboard's dedicated Deposit & top-up address, then use the OpenAI-compatible base `https://api.openbroker.gonka.gg/v1`.

Documented endpoints used by Slipvolt:

- `GET /v1/models` — live OpenBroker catalog.
- `POST /v1/chat/completions` — standard chat, streaming and function calling.
- `GET /v1/balance` — account/spendable GNK.
- `GET /v1/usage/summary`, `/v1/usage`, `/v1/usage/{id}` — usage/cost/reconciliation.

The public `/api/status` and `/api/registry/brokers` feeds power OpenBroker's public statistics. They are treated as best-effort observability rather than a stable billing contract.

OpenBroker says the old 1-ngonka governance price is stale for DevShard billing. Current DevShard token price is **10 ngonka/token/attempt**; retries/racing commonly produce **10–25 effective ngonka/token (~15 average)**. Estimated usage rows use the observed redundancy factor when the gateway does not return settled cost. Epoch accounting is separate. OpenBroker's documented markup is 0%.

## Models and context/output limits

OpenBroker currently lists MiniMax M2.7, DeepSeek V4 Flash 0731 and GLM 5.3 Flash. Kimi K2.6 is deprecated there.

The current Gonka chain model configuration (`/productscience/inference/inference/models_all`) uses:

- MiniMax M2.7: `--max-model-len 180000`
- DeepSeek V4 Flash 0731: `--max-model-len 400000`
- GLM 5.3 Flash: `--max-model-len 400000`

The current Gonka proxy `/v1/models` advertises those same context lengths and **16,384 max completion tokens** for all three. OpenBroker's docs accept `max_tokens` but do not separately publish a numeric ceiling, so Slipvolt uses live Gonka metadata and labels it as upstream capability rather than an OpenBroker SLA.

Gonka's Chat Completions docs also define: 10 MiB max body, nesting depth 32, max 2,048 messages, `n<=5`, max 16 stop sequences x 256 bytes, standard function tools, `max_tokens`/`max_completion_tokens`, and bounded response/tool schemas.

## Retail price references

Current matched/direct references researched for the rate-card decision:

- MiniMax M2.7: $0.30/M uncached input, $1.20/M output, $0.06/M cache read.
- Z.AI GLM-5.3 Flash: $0.15/M input, $0.03/M cached input, $0.50/M output.
- DeepSeek direct currently references V4.1 Flash, not OpenBroker's V4 Flash 0731. Off-peak cache-miss reference is $0.15/M input and $0.60/M output; cached input is materially cheaper. Do not call the two revisions the “same model.”

Slipvolt's planned metered reference defaults to **$0.075/M input and $0.30/M output**. That is intentionally simple and materially below uncached direct rates, but it is not guaranteed to beat cached direct-provider traffic.

Critical math: at an 80/20 mix, the planned rate averages $0.12/M total tokens. **1B tokens = $120 revenue**, not $120,000. The business can have a very high compute gross percentage margin while still needing enormous token volume for meaningful absolute revenue.

## Rate limits

Gonka's self-host gateway defaults are not a reseller business policy. Slipvolt starts lower per customer and uses a separate global guard:

- 30 RPM/wallet, 2 concurrent/wallet.
- 300 RPM global, 50 concurrent global.

OpenBroker publishes live model capacity. Raise these only after real latency/failure/cost observations. Returning “queued” is misleading unless Slipvolt actually implements a queue, so capacity failures are surfaced as temporary upstream unavailability with no fabricated queue state.

## Native GNK treasury

The compute treasury asset is **native GNK**, not an SPL imitation and not WGNK held indefinitely.

Candidate acquisition path A: HOT/NEAR Intents advertises swaps from SOL/USDC and other major assets into native GNK; its SDK includes Gonka mainnet and native `ngonka`. This supports quote-testing the path but does not guarantee a route/liquidity/fee in every region or amount.

Fallback path B: acquire official Ethereum WGNK, then use Gonka's official bridge back to native GNK. The destination Gonka account is derived from the **same signing key** used for the Ethereum bridge action; it is not an arbitrary broker deposit address. Verify the key/address relationship first.

After native GNK arrives in an owner-controlled account, send only the intended operating amount to the **dedicated OpenBroker deposit address shown in the account dashboard**. Then verify `available_ngonka` before allocating it inside Slipvolt.

The web server contains no treasury private key and does not automate bridge/swap signing.

## Holder access and abuse

A current holder check is simple, legible utility: hold token → sign in → get API key → use a funded allowance. The same wallet's multiple keys share one allowance.

Current-balance eligibility is not Sybil resistance. A transferable threshold can be moved between wallets to seek repeated allowances. Global GNK and AI-token budgets cap total exposure, but a public-scale launch should add an admission/cooldown or reviewed time-weighted/locking mechanism before offering large recurring subsidies.

## Pump.fun creator fees

Pump.fun's published bonding-curve creator fee is 0.30%; the total trading fee is not all creator revenue. Post-graduation canonical PumpSwap creator fees vary by market-cap tier. Creator fee revenue therefore depends on actual eligible trading volume and configuration.

Example only: $100,000 eligible volume x 0.30% = $300 gross creator fees. Market cap is not trading volume, revenue or treasury cash.

A regular creator-fee coin is compatible with funding operations. Holder-reward launch modes that redirect creator fees to holders should not simultaneously be budgeted as developer/compute revenue.

## Admin/business accounting

The admin console separates:

1. OpenBroker spendable native GNK,
2. local holder allowance allocation,
3. optional self-custody public GNK treasury,
4. OpenBroker usage/cost,
5. local usage/holds/reconciliation,
6. actual cash business entries.

The business ledger only records explicit realized entries. It does not count token market cap or unclaimed fees as income. Its “profit” view is a cash ledger for operations, not GAAP/tax financial statements.

## Sources

- https://openbroker.gonka.gg/docs
- https://openbroker.gonka.gg/stats
- https://rpc.gonka.gg/chain-api/productscience/inference/inference/models_all
- https://proxy.gonka.gg/v1/models
- https://github.com/gonka-ai/gonka/blob/main/docs/chat-api/README.md
- https://github.com/gonka-ai/gonka/blob/main/devshard/docs/proxy.md
- https://gonka.ai/docs/developer/quickstart/
- https://gonka.ai/docs/network-updates/
- https://gonka.ai/docs/cross-chain-transfers/ethereum-bridge/withdraw-gnk/
- https://hot-labs.org/chains/gonka
- https://github.com/hot-dao/omni-sdk
- https://pump.fun/docs/fees
- https://platform.minimax.io/subscribe/token-plan?tab=api-enterprise
- https://docs.z.ai/guides/overview/pricing
- https://api-docs.deepseek.com/quick_start/pricing/

## September 21, 2026 follow-up

- OpenBroker's current docs continue to expose an OpenAI-compatible `/v1` surface and GNK-native billing. The documented DevShard protocol rate is 10 ngonka per token per attempt, with retries/racing commonly increasing effective usage; the project therefore keeps a conservative local allowance factor rather than treating the protocol rate as an all-in guarantee.
- Gonka's FAQ still identifies the official Ethereum WGNK contract/bridge as `0x972a7a92d92796a98801a8818bcf91f1648f2f68` and warns that coins claiming to be GNK on Solana are not official GNK.
- HOT now advertises HOT Exchange / NEAR Intents swaps from SOL, USDC and other assets into native GNK. This is treated only as a third-party route candidate because it is not the canonical Gonka bridge and availability/fees can change.
- Pump.fun's current holder-rewards mode redirects the creator fee to holders, leaving no creator fee to claim. Slipvolt's proposed holder AI utility therefore remains an application-level benefit and does not use Pump holder-rewards mode when creator fees are intended to replenish compute.
- Dependency review found the previous `cryptography==46.0.4` and Starlette 0.50.x baseline behind patched 2026 security releases. The runtime pins now target cryptography 50.0.1 and Starlette 1.6.0 with FastAPI 0.141.1.

References: https://openbroker.gonka.gg/docs · https://gonka.ai/docs/FAQ/ · https://gonka.ai/docs/cross-chain-transfers/ethereum-bridge/overview/ · https://hot-labs.org/chains/gonka · https://pump.fun/docs/fees · https://github.com/pump-fun/pump-public-docs/blob/main/docs/HOLDER_REWARDS_README.md
