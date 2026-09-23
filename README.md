# Slipvolt — hold, connect, use AI

Slipvolt is a holder-access AI API built on **OpenBroker / Gonka**. A qualifying Solana wallet signs in, creates a revocable `sv_` API key, and uses a finite native-GNK-funded allowance through an OpenAI-compatible Chat Completions endpoint.

The public experience stays simple. Operational complexity lives at **`/admin/`**.

> Status: prelaunch software. No project mint, treasury signing key, payment processor, token launch, automatic swap, or automatic developer payout is included. The code can make real OpenBroker calls once a dedicated server-side `OPENBROKER_API_KEY` is configured.



## Operations dashboard (0.9.4)

The operator console now prioritizes measured service state instead of configuration chrome: local usage and realized cash-flow charts use only ledgered data, settings are grouped by task with saved/unsaved state, and failed secondary refreshes invalidate only the affected panel instead of leaving stale tables looking current. The public status page adds one source-labelled OpenBroker network trend from sanitized provider-wide daily aggregates; it is explicitly not Slipvolt traffic or uptime.

## Security baseline (0.9.3)

Production validates the Host authority against `APP_ORIGIN`, uses the routed ASGI path for API security decisions, and pins the current reviewed FastAPI/Starlette/cryptography/Pydantic security baseline. Run the manual GitHub test workflow after dependency changes; local fixture success is not a substitute for a clean dependency install.

## Functional setup and request tools (0.9.1)

Use `python -m gridraft.cli doctor` for a secret-safe, local-only setup check.
The playground now has an authenticated **Check request** action that uses shared
admission logic without submitting inference or reserving allowance. `/status/`
separates service configuration, model availability and GNK funding. The API tab
includes a credential-free connection kit; a reviewed support report excludes
prompts, keys, wallet addresses and private endpoints.

See [functional setup and limits](docs/FUNCTIONAL-SETUP.md). These are implemented
software features, not a claim of deployed service, paid inference or token launch.

## Customer documentation

- [Developer quickstart](public/developers/index.html), served at `/developers/`: exact customer API setup, current documented model IDs, streaming/tools and retry guidance.
- [GNK funding explainer](public/funding/index.html), served at `/funding/`: project-token, native-GNK, WGNK and OpenBroker funding boundaries.
- [Help and API guide](public/help/index.html), served at `/help/`: wallet setup, supported endpoints, allowance resets, pricing examples, errors and key recovery.
- [Data-handling disclosure](public/privacy/index.html), served at `/privacy/`: local records, upstream processing, cookies and retention limitations.
- [Draft service rules](public/terms/index.html), served at `/terms/`: current access versus planned staking/payments, funding and developer compensation.
- [Launch content checklist](docs/CONTENT.md): facts and policies that must be finalized before launch. Public guides do not imply legal review or a deployed service.

The account area links to a wallet-authenticated export of the latest 100 usage records. `public/llms.txt` now matches the implemented function-tool support.

## Account tools and launch readiness (0.9.0)

- Owners can revoke every API key for their wallet without losing usage history, or sign out all browser sessions without revoking API keys. These are separate confirmed actions.
- The playground has an explicit output budget, stop control, response copy, request trace ID, and wallet-shared rate information. Canceling the browser request does not prove zero provider cost.
- cURL, Python, and JavaScript examples reflect the selected model and output budget, and use an environment variable rather than inserting a private key. Automatic retries are disabled in examples where applicable.
- `/api/admin/readiness` and the admin checklist distinguish missing configuration, accounting blockers, and items still needing real testing. A configured key is never presented as a successful inference test.
- The checklist highlights the difference between a context window and a funded allowance: 400K context cannot be fully used under a 250K daily quota. A 1M shared pool covers four full 250K allowances, not every possible holder.
- `SITE_NAME=OMA-AI` changes the running public brand without renaming this repository or moving the unrelated OMA production deployment. Key prefixes, cookies, and database identity remain migration-compatible.

Staking, payment settlement, token launching, and automatic treasury transactions remain out of scope of this release.

## Current upstream policy snapshot — September 21, 2026

OpenBroker currently lists three active models. Slipvolt intersects the live OpenBroker catalog with current Gonka model metadata:

| Model | Context | Max completion | Slipvolt default output |
|---|---:|---:|---:|
| MiniMax M2.7 | 180,000 | 16,384 | 4,096 |
| DeepSeek V4 Flash 0731 | 400,000 | 16,384 | 4,096 |
| GLM 5.3 Flash | 400,000 | 16,384 | 4,096 |

OpenBroker currently marks **Kimi-K2.6 as deprecated** because the chain has no validation weights for it; it is intentionally not offered in the customer picker.

The 16,384 output ceiling comes from Gonka's current model metadata; OpenBroker's own documentation supports `max_tokens` but does not publish a separate numeric ceiling. Live metadata is checked at runtime and admin settings may only tighten the cap.

Gonka's documented Chat Completions safeguards are mirrored where practical: 10 MiB body, <=2,048 messages, `n<=5`, <=16 stop strings, standard function tools, SSE streaming, and `max_tokens` / `max_completion_tokens` compatibility.

See [API policy](docs/API-POLICY.md). Numeric upstream metadata is **not** a funded OpenBroker account benchmark; context admission uses a conservative byte estimate and may reject early.

## Pricing and GNK accounting

OpenBroker documents **10 ngonka per token per attempt**, commonly **10–25 ngonka/token effective** because the DevShard gateway races/retries hosts (~15 typical), plus separate epoch accounting. OpenBroker states that its markup is 0%.

Slipvolt's configurable planned metered/overage reference card defaults to:

- **$0.075 / 1M input tokens**
- **$0.30 / 1M output tokens**

Holder allowance is funded separately and no checkout is enabled in the default holder mode. This rate card is useful for modeling future overage/business access; it is not presented as already activated billing.

At an 80/20 input/output mix, the reference revenue is **$0.12 per million total tokens**. Therefore 1 billion tokens is about **$120 revenue**, not $120,000. High compute gross-margin percentages do not imply high absolute profit without high usage volume.

## User flow

1. Hold the configured Solana token.
2. Connect Phantom/Solflare and sign a login-only message.
3. Slipvolt checks finalized token holdings.
4. Create a private `sv_` API key; the operator's `obk-` credential never reaches the browser.
5. Call `/v1/chat/completions` or use the playground.
6. Wallet/global daily allowances, RPM/concurrency, live model availability and spendable native GNK all constrain dispatch.

Selling below the threshold blocks new requests when the finalized balance check reflects the change. Multiple API keys share one wallet allowance.

## Run locally

Python 3.13 is tested.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt   # tests/browser checks
python -m gridraft.cli init-env
python -m gridraft.cli serve
```

Open:

- Public app: `http://127.0.0.1:8000/`
- Admin: `http://127.0.0.1:8000/admin/`

`init-env` creates a private pepper and admin key. Preserve `KEY_PEPPER` and the database across upgrades.

## QuickNode and new operational safeguards

Read [QuickNode setup](docs/QUICKNODE.md) and [launch / holder / lock / payment decisions](docs/LAUNCH-AND-UTILITY.md).

The server now has private Solana RPC configuration, paced read-only calls, mainnet identity checks, exact mint-decimal validation, admin diagnostics and indicative Metis quotes. **No swap or payment execution is enabled.** WSS and 0x are configuration-only. Customer allowance still needs no second checkout.

Fixed: missing context admission checks; reserving only one output for `n>1`; unenforced per-wallet quota overrides; suspension during provider lookup; stale displayed operator caps; duplicate GNK allocation errors; missing-cost displays implying zero; and admin credentials persisted in browser storage.

```bash
python scripts/check_connections.py --env-file .env
python scripts/check_connections.py --env-file .env --priority-fees
```

## Required production configuration

At minimum:

```env
APP_ENV=production
APP_ORIGIN=https://your-domain.example
KEY_PEPPER=<stable 32+ chars>
ADMIN_API_KEY=<separate 32+ char secret>
OPENBROKER_API_KEY=obk-...
ACCESS_MODE=holder_allowance
HOLDER_MINT=<actual Solana mint>
MIN_HOLDING_RAW=<raw base units>
HOLDER_TOKEN_DECIMALS=<mint decimals>
HOLDER_TOKEN_SYMBOL=<ticker/name>
SOLANA_RPC_URL=https://...
```

Recommended defaults are in `.env.example`. Keep SQLite on persistent single-instance storage; do not put this build unchanged on ephemeral multi-instance serverless storage.

## Admin console

`/admin/` provides:

- OpenBroker spendable GNK and provider usage/cost.
- Local native-GNK allowance allocation and reconciliation state.
- Provider/model health and capacity.
- Wallet/global RPM and concurrency, with 30 RPM / 4 concurrent per wallet as the initial defaults.
- Wallet/global daily token allowances.
- Default/hard output caps and planned input/output pricing.
- Maintenance mode and per-model enable/disable controls.
- Wallet search, user disable/enable, per-wallet quota overrides, key inspection/revocation and operator audit history.
- Recent requests and uncertain reservations.
- Actual business cash ledger for creator fees/API revenue/subscriptions and hosting/RPC/support/refunds/taxes/developer payouts/GNK purchases.
- Selectable 7/30/90-day provider usage, configured-rate contribution reference and approximate provider-balance runway.

See [admin operations](docs/ADMIN.md).

## Funding native GNK

The web server does **not** hold treasury signing keys or automatically swap assets.

Operationally:

1. Acquire native GNK into an owner-controlled Gonka wallet using a currently verified route.
2. Transfer the operating amount to **your dedicated OpenBroker dashboard deposit address** (not the registration wallet and not OpenBroker's public operator wallet).
3. Verify `/v1/balance` with the dedicated `obk-` key.
4. Use the admin console or `allocate-gnk` CLI only to mirror already-credited GNK into Slipvolt's local allowance ledger.

HOT/NEAR Intents currently advertises third-party native GNK routes from SOL/USDC and is the first route to quote-test. Gonka’s own FAQ still points users to the official Ethereum WGNK bridge, whose return path has a critical same-signing-key Gonka destination rule. Always verify route, fees, min received and destination with a small test before moving operating funds.

See [operating model](docs/OPERATING-MODEL.md) and [research](docs/RESEARCH.md).

## OpenAI-compatible API

```bash
curl https://YOUR_HOST/v1/chat/completions \
  -H "Authorization: Bearer $SLIPVOLT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model":"MiniMaxAI/MiniMax-M2.7",
    "messages":[{"role":"user","content":"Hello"}],
    "max_tokens":4096,
    "stream":false
  }'
```

Supported surface includes text Chat Completions, standard roles, sampling fields, `max_tokens` / `max_completion_tokens`, SSE streaming, function tool definitions/tool calls, `response_format`, `structured_outputs`, `n<=5`, stop sequences, logit/logprob options, reasoning/thinking hints and selected vLLM-compatible sampling extensions. Slipvolt passes tools to the model but **never executes a tool itself**.

`GET /v1/models` returns the live intersection with `context_length` and `max_completion_tokens` metadata.

## Real OpenBroker smoke check

The repository includes a read-only catalog/balance check and an explicitly opt-in paid inference smoke test. Keep the provider key in the environment.

```bash
python scripts/check_openbroker.py
python scripts/check_openbroker.py --allow-paid-inference --acknowledge-cost \
  --model MiniMaxAI/MiniMax-M2.7
```

Do not blindly retry uncertain requests; inspect OpenBroker usage first.

## Publishing

This is the canonical `NosytLabs/Slipvolt` repository. See [publishing](docs/PUBLISHING.md) for the release checklist and hosting boundaries. Do not force-push shared history or treat a GitHub commit as proof that a public deployment is live.

## Verification

Latest local maintenance: [reliability fixes, measured optimizations and verification](docs/CLEANUP-2026-09-21.md).


```bash
sh scripts/verify.sh
```

The suite covers wallet auth, holder checks, key lifecycle, quota/rate concurrency, billing reservations/reconciliation, streaming, tool calls, current model metadata policy, admin authorization/config/user controls/GNK allocation/business ledger, frontend helpers and browser UI checks.

Passing fixtures do not establish real Phantom/Solflare interoperability, live provider latency, a successful paid OpenBroker call, Solana mainnet traffic, token popularity, profitability, or a production security audit.

## Business model

A reasonable structure is:

- holder token unlocks a bounded funded allowance;
- optional future paid overage/business usage uses explicit metered pricing;
- Pump.fun creator fees can be additional realized operating revenue;
- operating costs/reserves and native-GNK compute are funded before developer distributions;
- developer compensation comes from disclosed actual surplus, not from treating token market cap as cash.

The admin ledger records actual cash entries rather than projecting market cap or unclaimed fees as revenue. No outcome, trading-volume or profit guarantee is made.
