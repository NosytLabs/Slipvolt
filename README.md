# Holdbyte

Holdbyte gives eligible token holders a finite, operator-funded AI allowance. A user signs in with a Solana wallet, creates a revocable `sv_` API key, and calls an OpenAI-style Chat Completions endpoint backed by OpenBroker and Gonka.

This repository is still named `Slipvolt`, and compatibility names such as `SLIPVOLT_API_KEY`, `gridraft_session`, and legacy key handling remain supported. Holdbyte is the customer-facing display brand. This is a display migration, not a package, database, or API namespace migration.

## What works

- Phantom and Solflare message-signature login with finalized holder checks.
- Revocable customer API keys tied to one wallet allowance.
- Text chat, SSE streaming, function definitions, and returned tool calls through `POST /v1/chat/completions`.
- A live usable model catalog at `GET /v1/models` and source-labelled policy metadata at `GET /api/models`.
- Conservative context admission, output bounds, per-wallet and global quotas, rate limits, and concurrency limits.
- Native-GNK reservations, provider-reported settlement, and manual review for uncertain outcomes.
- Request preflight without inference, recent usage, CSV export, key revocation, and browser-session logout.
- An operator console for configuration, provider health, funding, reconciliation, users, requests, and realized ledger entries.
- Read-only Solana, Gonka, and provider diagnostics.

The server does not hold a treasury signing key or provide token checkout, automatic swaps, buybacks, burns, developer payouts, or overage billing. Production requires persistent storage, backups, HTTPS, a stable pepper, private credentials, and approved operating terms.

## Customer flow

1. Verify the published mint, threshold, and funded allowance.
2. Connect a supported wallet and sign the login message. It is not a transaction or token approval.
3. Create a private `sv_` key and store it outside public browser code.
4. Choose a model from the live catalog and send a bounded request.
5. Review usage before retrying an interrupted or uncertain request.

All keys for a wallet share one allowance. Selling below the threshold blocks new calls once finalized holdings reflect the change.

**Known cycling limit:** the same fungible tokens can move to another wallet and unlock that wallet’s separate allowance. Global limits still apply, but this build has no allowance-period lock or fixed-boundary eligibility snapshot. Resolve the [sequential-reuse design](docs/TOKEN-DESIGN.md#prevent-sequential-allowance-reuse) before describing the benefit as one daily allowance per holding rather than per currently eligible wallet.

## API quickstart

```bash
export SLIPVOLT_BASE_URL="https://YOUR_DEPLOYED_HOST/v1"
export SLIPVOLT_API_KEY="sv_..."

curl --fail-with-body -sS "$SLIPVOLT_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $SLIPVOLT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"MiniMaxAI/MiniMax-M2.7","messages":[{"role":"user","content":"Hello"}],"max_tokens":256}'
```

Call `GET $SLIPVOLT_BASE_URL/models` before relying on a model ID. The reviewed source snapshot includes `MiniMaxAI/MiniMax-M2.7`, `deepseek-ai/DeepSeek-V4-Flash-0731`, and `zai-org/GLM-5.3-Flash`. Their published context and output values are local admission policy, not verified OpenBroker account limits. Missing or zero provider metadata stays unknown. See [API policy](docs/API-POLICY.md).

## Run locally

Python 3.13 is tested.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m gridraft.cli init-env
python -m gridraft.cli serve
```

Open `http://127.0.0.1:8000/` for the customer app and `http://127.0.0.1:8000/admin/` for the operator console. Preserve `KEY_PEPPER` and the database across upgrades.

```bash
python -m gridraft.cli --env-file .env doctor
```

The setup doctor is local and makes no network calls. Read-only live diagnostics are separate:

```bash
python scripts/check_gonka.py --env-file .env
python scripts/check_connections.py --env-file .env
python scripts/check_openbroker.py --env-file .env
```

The OpenBroker check reads catalog and account state by default. Paid inference requires both explicit paid-test flags.

## Production configuration

Start with [.env.example](.env.example). Required production values include `APP_ORIGIN`, a stable `KEY_PEPPER`, a separate `ADMIN_API_KEY`, `OPENBROKER_API_KEY`, holder-mode mint settings, a Solana RPC URL, and persistent `DATABASE_PATH`.

`TOKEN_LAUNCHED=false` is the safe default. Set it to `true` only after the operator verifies the configured holder mint’s listing on Pump.fun. The flag controls whether the customer interface shows a link derived as `https://pump.fun/coin/{mint}`; it does not mint a token, validate a launch, prove liquidity, or prove funded inference. The link appears only with holder mode and a valid configured mint. Follow the [launch runbook](docs/LAUNCH_RUNBOOK.md).

Use `SITE_NAME` for a deployment-specific display name where supported. Keep compatibility environment names and `sv_` customer keys unless a separately planned namespace migration updates clients, tests, stored data, and support material together.

Review [deployment](docs/DEPLOYMENT.md), [security](docs/SECURITY.md), [RPC setup](docs/QUICKNODE.md), and [admin operations](docs/ADMIN.md). Restrict `/admin/` at the reverse proxy or VPN as well as with its application credential.

## Funding boundaries

The project token controls eligibility. Native GNK funds OpenBroker inference. WGNK is a separate Ethereum representation used only in an operator-chosen bridge route. Holding does not create a claim on GNK, treasury assets, creator fees, or developer revenue.

Keep these values separate:

- self-custody native GNK, if the operator publishes it;
- spendable credit in the dedicated OpenBroker account;
- local allowance reservations and settled usage.

An admin allocation records provider funds the operator has already verified; it does not transfer cryptocurrency. A reservation is an admission estimate, and final provider cost can exceed it. Market capitalization, unclaimed creator fees, and user lock principal are not operating cash.

## Documentation

**For customers**

- [Developer quickstart](public/developers/index.html)
- [Help](public/help/index.html)
- [Funding](public/funding/index.html)
- [Privacy disclosure](public/privacy/index.html)
- [Draft service rules](public/terms/index.html)

**For operators**

- [Functional setup](docs/FUNCTIONAL-SETUP.md)
- [Admin operations](docs/ADMIN.md)
- [Launch gates](docs/LAUNCH_RUNBOOK.md)
- [Publication checklist](docs/CONTENT.md)
- [Security](docs/SECURITY.md)
- [Verification](docs/VERIFICATION.md)

**Design and evidence**

- [Holdbyte brand and domains](docs/BRAND.md)
- [Product and architecture](docs/DESIGN.md)

- [Operating model](docs/OPERATING-MODEL.md)
- [Token and treasury proposal](docs/TOKEN-DESIGN.md)
- [Research snapshot](docs/RESEARCH.md)
- [Changelog](docs/CHANGELOG.md)

## Verify

Run the canonical offline verifier:

```bash
sh scripts/verify.sh
```

It runs Python and JavaScript regressions, compilation checks, and browser checks. Local fixtures do not prove live wallet interoperability, provider capacity, successful paid inference, a token launch, legal review, profitability, or deployment. See [verification and production acceptance](docs/VERIFICATION.md).

This is the canonical `NosytLabs/Slipvolt` repository. Publishing code does not deploy the service.
