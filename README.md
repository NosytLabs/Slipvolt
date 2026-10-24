# Slipvolt — hold, connect, use AI

Slipvolt is a prelaunch holder-access AI service built on OpenBroker and Gonka. A qualifying Solana wallet signs a login-only message, creates a revocable `sv_` customer key, and uses a finite native-GNK-funded allowance through an OpenAI-compatible Chat Completions endpoint.

This repository contains working application software. It does **not** include a project-token launch, treasury signing key, payment processor, automatic swap, automatic buyback or developer payout. Real model calls begin only after an operator privately configures and funds a dedicated OpenBroker account.

## What the application implements

- Phantom and Solflare message-signature login with finalized holder checks.
- Revocable customer API keys tied to one wallet allowance.
- `POST /v1/chat/completions` for text chat, SSE streaming, function-tool definitions and returned tool calls. Slipvolt never executes tools.
- `GET /v1/models` for the live usable catalog and `GET /api/models` for source-labelled policy metadata.
- Conservative context admission, output limits, request-size bounds, per-wallet and global quotas, RPM and concurrency limits.
- Native-GNK allowance reservations, provider-reported token settlement and manual review for uncertain outcomes.
- A no-inference request preflight, recent usage, CSV export, wallet-wide key revocation and browser-session logout.
- An operator console for service settings, provider health, funded capacity, reconciliation, users, requests and realized business-ledger entries.
- Read-only Solana, Gonka and provider diagnostics. No application route signs or broadcasts treasury transactions.

The service is a single-instance SQLite application. Production requires persistent storage, backups, HTTPS, a stable pepper, private credentials and an independently reviewed operating policy.

## Customer flow

1. Read the published mint, holding threshold and funded allowance. An unconfigured mint is not a token launch.
2. Connect a supported wallet and sign the login message. It is not a transaction or token approval.
3. Create a private `sv_` API key and store it outside public browser code.
4. Choose a model from the live catalog, check a bounded request, then send it from the playground or an application.
5. Treat interrupted or uncertain requests carefully. A held reservation may require operator reconciliation before new requests can run.

Selling below the configured threshold blocks new calls after finalized holdings reflect the change. Multiple keys from one wallet share the same allowance; new keys do not create new quota.

**Remaining entitlement limitation:** the same fungible tokens can move to another wallet and unlock that wallet's separate daily allowance. Global quotas and funded admission budgets still apply, but this build has no allowance-period lock or fixed-boundary eligibility snapshot. Resolve the [sequential-reuse design](docs/TOKEN-DESIGN.md#prevent-sequential-allowance-reuse) before advertising a daily benefit per holding rather than per currently eligible wallet.

## API quickstart

```bash
export SLIPVOLT_BASE_URL="https://YOUR_DEPLOYED_HOST/v1"
export SLIPVOLT_API_KEY="sv_..."

curl --fail-with-body -sS "$SLIPVOLT_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $SLIPVOLT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model":"MiniMaxAI/MiniMax-M2.7",
    "messages":[{"role":"user","content":"Hello"}],
    "max_tokens":256
  }'
```

Use `GET $SLIPVOLT_BASE_URL/models` immediately before relying on a model ID. The reviewed source snapshot contains:

| Model | Exact ID | Reviewed local context | Reviewed local completion cap |
|---|---|---:|---:|
| MiniMax M2.7 | `MiniMaxAI/MiniMax-M2.7` | 180,000 | 16,384 |
| DeepSeek V4 Flash 0731 | `deepseek-ai/DeepSeek-V4-Flash-0731` | 400,000 | 16,384 |
| GLM 5.3 Flash | `zai-org/GLM-5.3-Flash` | 400,000 | 16,384 |

These numbers are **local admission policy**, informed by separate Gonka deployment metadata. They are not verified OpenBroker serving limits or a funded account benchmark. Automatic discovery may tighten reviewed policy but cannot raise it. Missing or zero metadata remains unknown. Explicit server-side overrides remain labelled unverified. See [API policy](docs/API-POLICY.md).

The repository default output is 4,096 tokens, subject to the effective model and runtime cap. Context is checked per choice, while allowance reservation includes the input once plus the requested output for every `n` choice.

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

Open the customer app at `http://127.0.0.1:8000/` and the operator console at `http://127.0.0.1:8000/admin/`.

`init-env` creates a private pepper and administrator key. Preserve `KEY_PEPPER` and the database across upgrades. The setup doctor checks local configuration without opening the database or making network calls:

```bash
python -m gridraft.cli --env-file .env doctor
```

Read-only diagnostics are separate and explicit:

```bash
python scripts/check_gonka.py --env-file .env
python scripts/check_connections.py --env-file .env
python scripts/check_openbroker.py --env-file .env
```

The OpenBroker script reads catalog and account state by default. Paid inference requires both explicit paid-test flags; do not blindly retry an uncertain result.

## Required production configuration

```env
APP_ENV=production
APP_ORIGIN=https://your-domain.example
KEY_PEPPER=<stable 32+ characters>
ADMIN_API_KEY=<different 32+ character secret>
OPENBROKER_API_KEY=obk-...
ACCESS_MODE=holder_allowance
HOLDER_MINT=<verified Solana mint>
MIN_HOLDING_RAW=<raw base units>
HOLDER_TOKEN_DECIMALS=<actual mint decimals>
HOLDER_TOKEN_SYMBOL=<display label>
SOLANA_RPC_URL=https://...
DATABASE_PATH=/persistent/path/gridraft.db
```

Review [.env.example](.env.example), [deployment](docs/DEPLOYMENT.md), [security](docs/SECURITY.md), [QuickNode/RPC setup](docs/QUICKNODE.md) and [admin operations](docs/ADMIN.md). Restrict `/admin/` at the reverse proxy or VPN in addition to its application credential.

## Funding and accounting boundaries

The Solana project token signals eligibility. Native GNK funds OpenBroker inference. Ethereum WGNK is a separate wrapped asset used only when an operator deliberately chooses that bridge route. Holding the project token does not create a claim on GNK, the treasury, creator fees or developer revenue.

The application keeps three values separate:

- a self-custody native-GNK balance, when the operator elects to publish one;
- spendable credit in the dedicated OpenBroker account;
- the local allowance ledger used for admission and reconciliation.

Allocating GNK in the admin console mirrors funds already verified in the provider account; it does not transfer cryptocurrency. The local reservation factor is conservative planning, not a provider-enforced maximum charge. Confirmed provider cost can exceed an estimate, so the operator must keep headroom and reconcile actual account movement.

Customer checkout and automatic overage billing are disabled. Configurable rate-card fields are planning and reporting inputs until final prices, payment settlement and refund terms are adopted. Market capitalization, unclaimed creator fees and user lock principal are not operating cash.

See the customer [funding explainer](public/funding/index.html), [operating model](docs/OPERATING-MODEL.md), and [token, lock, burn and treasury proposal](docs/TOKEN-DESIGN.md). The token document is a design proposal; no lock program, burn schedule, launch venue or treasury transaction is deployed by this repository.

## Documentation

- [Developer quickstart](public/developers/index.html): customer key, live catalog, streaming, tools and retry behavior.
- [Help](public/help/index.html): wallet setup, allowances, errors, account controls and safe support.
- [Funding](public/funding/index.html): project-token, native-GNK, WGNK and deposit boundaries.
- [Privacy](public/privacy/index.html): local records, upstream processing, cookies and unresolved retention policy.
- [Draft service rules](public/terms/index.html): current holder access and features that remain proposals.
- [Functional setup](docs/FUNCTIONAL-SETUP.md): preflight, connection kit, diagnostics and acceptance work.
- [Launch gates](docs/LAUNCH_RUNBOOK.md) and [publication checklist](docs/CONTENT.md): facts that must exist before onboarding users or funds.
- [Research snapshot](docs/RESEARCH.md): dated provider and network evidence, with uncertainty labels.
- [Changelog](docs/CHANGELOG.md): historical release details.

## Verification and publication

Run the canonical offline verifier from the repository root:

```bash
sh scripts/verify.sh
```

It runs Python and JavaScript regressions, compilation checks and browser checks for the holder, admin, status and customer-documentation surfaces. GitHub Actions runs the same command on pushes to `main`, pull requests and manual dispatch.

A green fixture suite does not prove real wallet-extension interoperability, current provider capacity, a successful paid request, Solana mainnet behavior, token popularity, profitability, legal review, a production reverse proxy or a live deployment. Follow [verification and production acceptance](docs/VERIFICATION.md) for the remaining gates.

This is the canonical `NosytLabs/Slipvolt` repository. Work from current shared history, use pull requests and do not force-push over intervening work. Publishing source code or merging a pull request does not deploy the service. See [publishing](docs/PUBLISHING.md).
