# Changelog

## 0.9.2 — 2026-09-21

- Added `/developers/` with an exact customer-key quickstart, current documented OpenBroker model IDs, streaming/tool behavior, error handling and retry guidance.
- Added `/funding/` to separate the Solana access token, native GNK compute funding and official Ethereum WGNK bridge path.
- Rechecked OpenBroker, Gonka bridge and Pump.fun fee documentation; Kimi K2.6 is explicitly treated as deprecated and Pump creator-fee copy uses the current published fee schedule rather than an assumed flat rate after graduation.
- Hardened frontend API parsing for empty and non-JSON responses without echoing raw proxy bodies; expired wallet sessions now clear ephemeral customer state.
- Removed unused legacy calculator/bridge-planner helpers from the customer JavaScript bundle.
- Added targeted SQLite indexes for reservation/review, wallet-state and global member-usage time queries.
- Fixed documentation navigation overflow at 320px and expanded browser coverage to the new pages.

## 0.9.0 — customer controls and honest readiness

## 2026-09-21 — reliability and cleanup (local, unpublished)

- Keep failed network snapshots stale; bound stale lifetime and validate dates.
- Amortize bounded SQLite housekeeping, index wallet-session removal, and recover interrupted transactions.
- Fix byte-fragmented SSE boundaries, stop at `[DONE]`, and batch text rendering.
- Cancel obsolete request checks, clear stale success states and prevent button races.
- Fail incomplete offline preview builds before replacing output; preserve prior setup/security work and all customer pages.
- Verification: 290 Python tests, 93 Node tests and 336 browser assertions passed; see `CLEANUP-2026-09-21.md` for fixture and publication limits.


Added wallet-wide key revocation, wallet-wide browser logout, configurable public brand, output budgeting, stop/copy/request-ID controls, environment-key SDK examples, and read-only admin launch readiness. Quotas and costs are preserved during credential revocation. Configured integrations do not count as proof of live acceptance. No payment, staking, treasury, or launch executor added.

# 2026-09-20 — QuickNode readiness and budget safety

- Import canonical source onto the existing remote README ancestry.
- Private HTTP/WSS configuration, bounded/paced Solana reads and production mainnet identity check.
- Read-only admin diagnostics/priority-fee estimates and sanitized ExactIn Metis quote previews; no transaction execution.
- Enforce conservative context admission and reserve output for all requested choices.
- Apply per-user allowance overrides and suspension at the ledger transaction boundary.
- Fix cached output-policy display after administrator changes.
- Make duplicate budget allocations idempotent at the live-balance ceiling.
- Restrict risky request/template/schema shapes and validate mint decimals.
- Keep master admin secrets in memory only; do not display unknown provider costs as zero.
- Flatten the public/admin design; isolate technical connection controls in admin.
- Add admin browser checks to the verification command and CI.
- Add explicit launch/utility/payments and private QuickNode setup documentation.

Previous release notes (historical):

# Slipvolt 0.8.0 — OpenBroker/Gonka production hardening

- Verified current active OpenBroker models against live Gonka metadata: MiniMax M2.7 (180K context), DeepSeek V4 Flash 0731 (400K), GLM 5.3 Flash (400K), each advertising a 16,384 completion-token ceiling.
- Kept a 4,096 default output while exposing the verified 16,384 hard cap; live upstream metadata may tighten but never expand the configured cap.
- Expanded OpenAI/Gonka Chat Completions compatibility and mirrored key request safety bounds (10 MiB body, nesting depth 32, <=2,048 messages, n<=5).
- Preserved actionable upstream/client HTTP statuses and Retry-After instead of flattening 400/413/422/429/503 conditions into generic 502 responses.
- Added live model-health gating before dispatch.
- Added operator controls for RPM/concurrency, allowance budgets, GNK reservation factor, pricing references, model enable/disable and maintenance mode.
- Expanded `/admin/` with OpenBroker cost windows, GNK fund capacity, customer/key management, per-wallet overrides, request/reconciliation views, business ledger and operator audit history.
- Added audit events for sensitive operator changes and sign validation for realized revenue/outflow entries.
- Removed stale Gridraft/Laprelay evidence and legacy browser scripts from the release tree.
- Release gate: 146 Python tests, 60 Node tests, 74 holder browser checks and 45 admin browser checks.

---

# Maintenance 0.3.1 — consolidation and correctness

- Restored the supplied operator-only founder planner and its 38 tests without replacing the holder backend.
- Corrected holder account, usage summary and CSV endpoints to report the native-GNK ledger.
- Added transactional lifetime GNK projections with safe backfill, indexed current-day/pending allowance queries, and expiry indexes.
- Added a 15-second sanitized display-only balance cache and an eight-second total metadata read deadline; authorization reads remain fresh.
- CI and local verification now include every JavaScript test file and the operator scripts.
- Preserved the simple customer flow, current mint configuration, pilot quotas, original commits, database and key pepper.

# v0.3 — simpler native-GNK holder access

- Replace the public pricing/calculator/treasury-planning console with one access card, model selector and text playground.
- Add `holder_allowance`: eligible holders can create customer keys without a second dollar-credit checkout.
- Add integer-ngonka allocation/usage ledger and shared UTC-day AI-token quotas, separate from legacy dollar credits.
- Add documented OpenBroker balance/cost integration, text SSE forwarding and retained uncertainty holds.
- Add optional native Gonka wallet balance, separate opt-in broker balances and sanitized source-labeled network aggregates.
- Add exact model catalog discovery, conservative estimate labels, operator GNK allocation/reconciliation commands and explicit-opt-in paid smoke script.
- Preserve original database, pepper, module, cookie and old-key compatibility. Archive earlier design instructions.
- Fix changed stream IDs, review status, pre-header cancellation, restored wallet mismatch, model-name command injection risk and invalid boolean configuration.
- Verify 108 Python tests, 16 helper tests and 74 browser checks. No paid calls, token launch, remote merge or public deployment.

---

# Slipvolt v0.2 — 19 September 2026

This pass edits the latest supplied Gridraft source. Original supplied archives are untouched.

## Product and visual changes

- New provisional Slipvolt identity, local SVG mark, carbon/cream/lime palette, responsive navigation and reduced-motion support. No font download or third-party runtime dependency.
- Product-first homepage: exact model IDs, filter/search, uncached matched-model comparisons, chosen input/output workload, coherent proposed rate, member-access explanation and developer quickstart.
- Separate console with Overview, API Keys, Playground and Activity; real zero/empty/error states instead of demo account values.
- Modal model details, code-language tabs, accessible keyboard console tabs, explicit one-time-key controls and revocation confirmation.
- Scenario export and zero-volume stress test. Positive surplus only, after costs/reserves: proposed 50% compute, 30% WGNK, 20% operator. Never a transaction or earnings forecast.
- Funding inputs invalidate obsolete plans; unknown SPL mint inputs fail validation. No executable quote or swap action.

## Correctness and security changes

- Retain uncertain upstream HTTP responses, timeouts, redirects and malformed success responses rather than assuming no compute was consumed.
- Mark unresolved consumption for review; block subsequent dispatch until an operator reconciles it. Include request IDs in error bodies/headers where a reservation exists.
- Atomic global and wallet-level daily retail-ledger budgets, shared across keys and carrying unresolved prior-day holds.
- Reject mismatched upstream model IDs when supplied, malformed choice payloads, and blank/invisible key names.
- Authenticated all-time/7-day summary and latest-100 CSV export; neutralize spreadsheet-formula prefixes and exclude prompt/key content.
- New `sv_` keys with legacy `grd_` lookup retained. Existing import path, schema, DB default, deployment-volume name and session cookie retained deliberately.
- Source the displayed rate from server configuration; preserve sub-cent rate precision rather than displaying “$0.00”.
- Rebind wallet-change detection when restoring a cookie session. Clear transient credentials and content on logout or selected-wallet changes.
- Environment initializer includes documented default budgets and preserves restrictive permissions.

## Evidence and limitations

See `VERIFICATION.md` for the current release gate. Earlier regression details are retained in version history rather than shipped as stale evidence artifacts.

There is no claim of independent review, real paid inference, native browser extension testing, public deployment, domain availability, token launch, collection of customer money, or treasury execution. Historical pre-Slipvolt design archives are not shipped in the consolidated release.
