# Security and operational limits


## HTTP boundary and dependency baseline

Production rejects unexpected or malformed `Host` authorities against the configured `APP_ORIGIN`, normalizing only default HTTP/HTTPS ports. Security-sensitive API path checks use the ASGI routed path instead of a URL reconstructed from the Host header. This is defense in depth for malformed-host/path confusion even with patched framework versions.

The September 21, 2026 dependency review pins FastAPI 0.141.1, Starlette 1.6.0, cryptography 50.0.1 and Pydantic 2.13.5. The cryptography update moves past 2026 advisories affecting older releases; the Starlette update moves past the malformed-Host routing advisory. HTTPX remains on the current stable 0.28.1. Re-run GitHub Actions on the change's pull request after dependency updates so a clean environment installs and exercises the exact pins.

The holder flow proves control of a Solana address with an exact-origin, expiring one-time Ed25519 challenge. Sessions remain HttpOnly/SameSite and keys are stored hashed. Provider credentials are server-only. No wallet seed, private key, approval transaction or treasury signing key is requested.

Every new holder inference rechecks a finalized balance from the configured RPC. The key's wallet must meet the exact mint threshold. RPC or catalog uncertainty denies dispatch. Already-dispatched calls may finish after holdings change. RPC providers are trusted infrastructure; one valid balance is not proof of a real human or an untransferred membership position.

Wallet quotas are shared across keys. Atomic local GNK reservations limit a finite operator allocation, plus global/day and per-wallet/day limits. All unresolved holds count, even from earlier dates. Reusing a funding reference cannot allocate it twice. An operator can still make a mistaken allocation under another reference; the command is not a deposit verifier.

`available_ngonka` is checked immediately before dispatch and local outstanding holds are conservatively deducted. This does not make a locally modeled 25-ngonka/token ceiling a hard provider billing limit. Provider redundancy, charges that arrive later, model overhead and epoch allocations may exceed assumptions. Use a dedicated broker account, meaningful reserve, low pilot concurrency, and reconcile the actual balance. Local budgets do not prove treasury solvency.

Successful request usage is verified and matched to provider request IDs. Confirmed devshard costs are distinguished from conservative estimates. Truncation, model/identity mismatch, malformed usage, an unsuccessful dispatched HTTP response and disconnected streams retain a hold and require review. There is no blind retry. This pauses new inference across the affected ledger until the operator reconciles the request; even routine provider 4xx or 429 responses can cause a pause. Previously recorded zero-cost rejection entries remain unchanged and do not establish that the provider charged nothing. Review historical provider account movements independently.

Public statistics contain only aggregates and attribution, not the broker directory. Registry schema is observational and can change. Native self-custody balance is public by explicit address configuration; private broker balance requires a separate opt-in. These are different accounts and should not be misrepresented as a user-redeemable reserve.

Admin API authentication is shared across the console and optional treasury/token routes. Both reject oversized or non-ASCII credentials without an unhandled comparison error; a configured admin secret must be printable ASCII (at most 512 characters, with at least 32 required in production). Read-only admin endpoints require a valid key; write endpoints also require the exact application Origin. Keep the operator credential separate from customer and provider keys.

New table migrations are additive. Keep the original pepper, database and [private backups](BACKUPS.md). The application is single-worker/single-instance SQLite. Rate limiting, HTTPS ingress, consistent backups, bounded logs, process supervision and OS security require operator configuration. The app avoids prompt/response persistence locally; upstream services and wallet extensions have independent data policies. No end-to-end zero-retention guarantee is claimed.

Known gaps: no independent audit; no live extension or paid provider E2E test; no automatic epoch reconciliation; no cross-wallet Sybil/transfer protection; no automatic creator-fee claims, executable token swaps or settlement signer. Read-only Metis quote previews are not executed transactions. Simulated wallet/browser tests do not validate third-party extensions. Read-only public endpoint success is not a successful paid inference call.
