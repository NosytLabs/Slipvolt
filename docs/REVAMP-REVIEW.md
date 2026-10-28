# Holdbyte revamp review

Review date: **28 October 2026**. Repository: `NosytLabs/Slipvolt`.
Branch: `revamp/solana-ai-workspace`.

## Product and architecture

Holdbyte is a Solana holder-access layer for Gonka inference through OpenBroker.
The customer holds the configured token, signs a login-only message, creates a
private `sv_` key, and calls the Holdbyte API. The server verifies eligibility,
reserves a bounded allowance and forwards accepted requests with the operator's
server-side `obk-` key. Inference is paid from the operator's OpenBroker GNK
balance. The Solana token is not native GNK and does not pay Gonka automatically.

The current holder allowance is retained. A pump.fun purchase does not create
service credit, fund the provider, or establish a redemption rate. Token-paid
checkout would need independently verified finalized payments, single-use
invoices, net-amount accounting, replay protection and commercial terms; see
[launch and utility](LAUNCH-AND-UTILITY.md).

## Implemented changes

- Updated the customer workspace, hero, access card, model controls, guide
  styling and responsive navigation while retaining the published routes.
- Added an original transparent relay illustration and a four-state mascot
  atlas. Inline vector prompt icons avoid an external icon dependency.
- Exposed a copyable chat-completions endpoint, including a truthful placeholder
  in the offline preview; improved the unavailable-output-limit error.
- Bounded the legacy prepaid provider response and validated its usage totals
  through the same parser used by holder requests. Invalid or incomplete
  responses retain the reservation for reconciliation.
- Shielded and bounded response cleanup when a streaming client disconnects.
  Incomplete SSE output includes the existing API error type and code.

## Verified primary sources

- [Gonka developer quickstart](https://gonka.ai/docs/developer/quickstart/):
  OpenBroker is an official documented route to operating a broker without
  running an allow-listed on-chain gateway. The broker defines customer
  payment and access policies; Solana ownership checks remain Holdbyte's layer.
- [OpenBroker chat completions](https://openbroker.gonka.gg/docs/chat-completions):
  OpenAI-style `POST /v1/chat/completions`; upstream authentication uses `obk-`
  keys. Holdbyte issues separate customer keys and enforces its own schema.
- [OpenBroker deposits](https://openbroker.gonka.gg/docs/deposits): the account
  uses a dedicated native-GNK deposit address and currently requires 100 GNK to
  activate. Its spendable ledger is separate from the registered wallet.
- [OpenBroker pricing](https://openbroker.gonka.gg/docs/pricing): live DevShard
  escrows are documented at 10 ngonka per token per attempt; repeated/raced
  attempts affect effective cost. Do not use the stale governance rate as an
  operating budget or guarantee an exact cost per response.
- [Solana token account RPC](https://solana.com/docs/rpc/http/gettokenaccountsbyowner):
  program ownership and wallet ownership are different fields; authorization
  uses verified mint and raw integer amounts rather than display floats.
- [Pump fees](https://pump.fun/docs/fees), updated 17 October 2026: standard
  SOL/USDC bonding-curve trades currently allocate 0.30% as the creator fee;
  graduated canonical pools use tiers. Fees are collected in the pair's quote
  asset, not in GNK. Holder Rewards can redirect the creator-fee recipient.
  Inference budgeting must use fees actually received and separately fund the
  OpenBroker account. Volume, future fees and market capitalization are not
  guaranteed operating income.
- [Solana development skill](https://github.com/solana-foundation/solana-dev-skill/blob/main/skills/solana-dev/SKILL.md)
  and [skill index](https://solana.com/SKILL.md): applied account-validation and
  wallet-signing boundaries to the existing service.
- [Solana game skill](https://github.com/solanabr/solana-game-skill): reviewed as
  requested. Its game-engine and older frontend-stack recommendations do not
  require replacing this Python/vanilla-JavaScript application.

## Verification

The complete `sh scripts/verify.sh` command **passed** after integration:

| Check | Result |
| --- | --- |
| Python API, accounting, security and browser regression suite | 780 passed |
| JavaScript regression suite | 179 passed |
| Holder browser workflow | 174 checks passed, native localhost transport |
| Admin browser workflow | 187 checks passed |
| Status browser workflow | 65 checks passed using a local TestClient bridge |
| Static guides at 320, 390, 768 and 1280 pixels | 141 checks passed |
| Operator economics browser workflow | 69 checks passed |
| JavaScript syntax, Python compilation and self-contained preview generation | Passed |
| Desktop/mobile visual review | Inspected at 1440 and 390 pixels; no page overflow |

The environment used Python 3.12.14, Node 24.22.1 and an available Chrome
156.0.8078.73 binary selected through `CHROMIUM_PATH`. Two existing dependency
deprecation warnings concern Starlette's HTTPX TestClient and an AnyIO alias.
The browser checks use generated wallet signatures and fixture providers; they
do not prove real extension interoperability or paid upstream inference.

The homepage preview embeds all four image elements, including the sprite
atlas. Its API panel uses `https://YOUR_HOST/v1/chat/completions` and explains
that the placeholder must be replaced. Preview mode sends no model request.

### Public upstream observations

Recorded **28 October 2026, 18:49:07 UTC**. The sanitized response summary is
[provider-check-2026-10-28.json](provider-check-2026-10-28.json).

| Endpoint | HTTP status | Observation |
| --- | --- | --- |
| `https://api.openbroker.gonka.gg/v1/models` | 200 | MiniMax M2.7, DeepSeek V4 Flash 0731 and GLM 5.3 Flash |
| `https://api.openbroker.gonka.gg/api/status` | 200 | Operational; all three listed models healthy and routable |
| `https://proxy.gonka.gg/v1/models` | 200 | Discovery metadata received; extra proxy-only `jev` model remains outside the admitted OpenBroker catalog |

These were unauthenticated GET requests through the execution environment's
network proxy. Direct network access was unavailable here; application
credential isolation (`trust_env=False`) is preserved. No bearer credential,
prompt, or paid inference request was sent. The provider status is a dated
observation, not an uptime or acceptance guarantee. Discovery values do not
raise reviewed service caps.

## Configuration needed for a live service

Configure the funded `OPENBROKER_API_KEY`, stable `KEY_PEPPER`, private
`ADMIN_API_KEY`, persistent database, production HTTPS `APP_ORIGIN`, Solana RPC,
verified `HOLDER_MINT`, decimals, raw holding threshold and funded allowance
limits. Keep `TOKEN_LAUNCHED=false` until the actual listing is verified. See
[functional setup](FUNCTIONAL-SETUP.md) and [launch runbook](LAUNCH_RUNBOOK.md).

No production deployment, funded account, mint creation, purchase, transfer,
swap, burn, or paid inference has been performed in this revamp. Those states
cannot be established by local tests or a successful model-catalog read.
