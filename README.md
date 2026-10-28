# Holdbyte

Wallet-gated AI with a finite, operator-funded allowance. Eligible Solana wallets sign in, create revocable `sv_` API keys, and use chat or an OpenAI-style API backed by OpenBroker and Gonka.

**[Documentation](docs/README.md) · [Setup](docs/FUNCTIONAL-SETUP.md) · [Deployment](docs/DEPLOYMENT.md) · [Security](docs/SECURITY.md)**

## Run locally

Python 3.13 is tested. The development requirements include the runtime dependencies.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m gridraft.cli init-env
python -m gridraft.cli --env-file .env doctor
python -m gridraft.cli serve
```

The doctor checks local configuration without network calls. `init-env` creates a private `.env` and refuses to overwrite an existing file. Leave launch and treasury settings unconfigured until verified, and preserve `KEY_PEPPER` and the database across upgrades. See [.env.example](.env.example) and the [setup guide](docs/FUNCTIONAL-SETUP.md) for configuration.

| Route | Purpose |
| --- | --- |
| `/` | Wallet login, chat, API keys, request preflight and private usage |
| `/models/` | Search the current catalog and inspect source-labelled limits |
| `/token/` | Finalized supply/authority reads and recorded burn receipts |
| `/status/` | Provider, funding and eligibility-check status |
| `/admin/` | Limits, funding, reconciliation, users and realized ledger entries |
| `/admin/burns/` | Treasury discovery, unsigned burn preparation and creator-claim evidence |

The local server uses `http://127.0.0.1:8000`. These pages need configured services for live data; opening them is not proof of deployment or readiness.

## API quickstart

Replace the host and key, then check `GET /v1/models` for current IDs.

```bash
export HOLDBYTE_BASE_URL="https://YOUR_DEPLOYED_HOST/v1"
export HOLDBYTE_API_KEY="sv_..."

curl --fail-with-body --retry 0 -sS "$HOLDBYTE_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $HOLDBYTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"MiniMaxAI/MiniMax-M2.7","messages":[{"role":"user","content":"Hello"}],"max_tokens":256}'
```

`GET /api/models` explains local context/output policy and discovered metadata separately. Neither catalog health nor a local limit proves upstream inference acceptance. See [API policy](docs/API-POLICY.md) and the [developer guide](public/developers/index.html).

## Repository layout

| Directory | Responsibility |
| --- | --- |
| `gridraft/` | Python API, provider adapters, usage accounting and token evidence |
| `public/` | Customer pages, shared browser assets and operator console |
| `operator/` | Operator planning tools; not customer checkout |
| `scripts/` | Verification, previews and explicit diagnostics |
| `tests/` | Python/JavaScript regressions and browser-flow coverage |
| `docs/` | Setup, operations, security, design and research; [start here](docs/README.md) |

The canonical repository remains `NosytLabs/Slipvolt`. `gridraft`, `gridraft_session`, existing `sv_` keys, and legacy `SLIPVOLT_API_KEY` integrations remain compatible. New client examples use Holdbyte names; changing those example variables does not rename server configuration or stored data.

## Operating boundaries

All keys for a wallet share its allowance. Selling below the threshold blocks new calls once finalized holdings reflect the change. **The same tokens can still qualify another wallet after transfer**; an allowance-period lock is not implemented. See the [sequential-reuse design](docs/TOKEN-DESIGN.md#prevent-sequential-allowance-reuse).

Native GNK in self-custody, OpenBroker spendable credit, and local reservations are different balances. Admin funding entries do not move funds. Reservations are estimates, not guaranteed final provider charges; token market cap, unclaimed fees and user principal are not operating revenue.

Unsuccessful dispatched requests and unresolved reservations can pause new inference until an operator checks provider billing and reconciles the hold. See [admin operations](docs/ADMIN.md) for the pending and reconciliation commands. This protects accounting but may interrupt service after an ordinary provider error.

The production image includes the read-only provider-usage and mint-screening diagnostics described in the [deployment guide](docs/DEPLOYMENT.md). They do not settle accounts or approve a vault.

Treasury tools discover accounts, prepare unsigned instructions and record completed burns. The optional Pump creator-claim check records unattributed evidence, not verified project revenue. These tools do not sign, broadcast, execute swaps/buybacks, collect fees, accept staking deposits, or pay developers. Recorded gross burns and claims are not complete history or proof of net deflation.

Production needs persistent storage, [tested private backups and restore drills](docs/BACKUPS.md), HTTPS, stable secrets and reviewed operating terms. Keep `TOKEN_LAUNCHED=false` until the configured mint's listing is verified; the flag only publishes a link. Follow the [launch runbook](docs/LAUNCH_RUNBOOK.md). Restrict `/admin/` at the reverse proxy or VPN as well as with its separate credential.

## Verify

```bash
python -m playwright install chromium
sh scripts/verify.sh
```

Verification requires Node.js and Playwright Chromium in addition to the development requirements; CI uses Node.js 22. On Linux, Chromium may also need system packages; see [verification](docs/VERIFICATION.md). This is the canonical offline test command. Live read-only diagnostics and explicitly opted-in paid probes are separate. Fixtures do not establish real-wallet interoperability, paid provider acceptance, profitability, an audited contract, or a production deployment. Publishing code does not deploy the service.
