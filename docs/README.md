# Holdbyte documentation

Start with the guide for the task. Proposed mechanics and historical research are not descriptions of live services.

## Setup and operation

| Guide | Use it for |
| --- | --- |
| [Functional setup](FUNCTIONAL-SETUP.md) | Local configuration and first run |
| [Deployment](DEPLOYMENT.md) | Hosting, storage and production setup |
| [Database backups](BACKUPS.md) | Live SQLite snapshots, private storage and restore drills |
| [Admin operations](ADMIN.md) | Service limits, funding, users and reconciliation |
| [Verification](VERIFICATION.md) | Offline tests versus real-environment acceptance |
| [Security](SECURITY.md) | Credentials, trust boundaries and deployment controls |
| [Solana / QuickNode](QUICKNODE.md) | Private RPC and quote-only integration |
| [Gonka RPC](GONKA-RPC.md) | Keyless chain reads, separate from paid inference |
| [API policy](API-POLICY.md) | Model IDs, local limits and provider evidence |
| [Token evidence](TOKEN-AUDIT.md) | Supply reads and completed-burn verification |
| [Treasury burns and claims](TREASURY-BURNS.md) | Account discovery, unsigned burn preparation, burn receipts and unattributed creator-claim evidence |

## Release and content

| Guide | Use it for |
| --- | --- |
| [Launch runbook](LAUNCH_RUNBOOK.md) | Preconditions before activating a public service |
| [Content checklist](CONTENT.md) | Customer-page facts and publication checks |
| [Publishing](PUBLISHING.md) | Source and deployment handoff |
| [Brand](BRAND.md) | Current Holdbyte naming/compatibility rules and historical domain research |
| [Changelog](CHANGELOG.md) | Historical changes; CI and code establish current behavior |
| [Revamp plan](REVAMP-PLAN.md) | Scope and acceptance for the October 2026 workspace refresh |
| [Revamp review](REVAMP-REVIEW.md) | Current implementation, research, endpoint checks and launch handoff |

## Architecture and proposals

| Guide | Scope |
| --- | --- |
| [Design](DESIGN.md) | Product and application architecture |
| [Operating model](OPERATING-MODEL.md) | Allowance and accounting boundaries |
| [Token design](TOKEN-DESIGN.md) | Proposed locking, fee allocation and custody; not a deployed vault |
| [Launch and utility](LAUNCH-AND-UTILITY.md) | Launch research and utility design |
| [Founder policy](FOUNDER-POLICY.md) | Proposed business controls, not an automated payout service |
| [Research](RESEARCH.md) | Dated external findings, not guaranteed current prices or availability |

Customer-facing guidance lives in [Developers](../public/developers/index.html), [Help](../public/help/index.html), [Funding](../public/funding/index.html), [Privacy](../public/privacy/index.html) and [Terms](../public/terms/index.html).

## Code boundaries

The [architecture map](DESIGN.md#boundaries) describes module responsibilities and shared infrastructure. Configuration, request schemas and body enforcement have dedicated modules; `gridraft.app` retains their existing import names. Keep rate-limit namespaces and endpoint paths stable when refactoring.

`gridraft`, `gridraft_session`, database paths and existing `sv_` keys are compatibility identifiers, not abandoned branding. Avoid a global rename. New client examples prefer `HOLDBYTE_API_KEY`; supported legacy `SLIPVOLT_API_KEY` integrations remain valid.

Browser verification support belongs in `scripts/browser_support.py`, shared by the standalone checks and browser tests in `tests/`. It is separate from the application package. Run `sh scripts/verify.sh` to exercise every suite with the same browser-selection policy.
