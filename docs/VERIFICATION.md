# Verification — current Slipvolt release

Slipvolt uses one canonical verification command:

```sh
sh scripts/verify.sh
```

The verifier is intentionally local/offline by default. It runs the backend and JavaScript regression suites, syntax/compile checks, and the holder, admin, status, and customer-documentation browser checks. The manual-only GitHub Actions workflow installs the pinned development dependencies and Chromium, then runs this same command.

## What a green verifier establishes

A passing run establishes that the checked source tree satisfies the repository's automated contracts for:

- wallet-signature authentication and session/key lifecycle;
- holder-balance admission and shared allowance accounting;
- request validation, rate/concurrency limits, model policy, streaming and tool-call handling;
- uncertain-cost reservations and operator reconciliation;
- admin settings, customer controls, measured usage/cash-flow charts, and stale-panel handling;
- public status rendering and source-labelled OpenBroker network aggregates;
- Help, Developers, Funding, Privacy, Terms, navigation, responsive layouts, and protected account endpoints;
- Python compilation and JavaScript syntax.

A green configuration/readiness check is not a live-service certificate.

## Evidence policy

Do not keep pass-specific verification snapshots as separate "latest" documents. They become stale quickly and previously caused contradictory counts in this repository.

Use these sources instead:

1. **GitHub pull requests and Actions runs** for exact commit/run evidence.
2. **This file** for the current verification scope and limitations.
3. **CHANGELOG.md** for release-specific behavior changes.

PR #10 (September 23, 2026) locally verified the repository cleanup with **306 Python tests** and **82 JavaScript tests**. Subsequent maintenance should run the canonical verifier again before deployment rather than treating those historical counts as permanent.

## Production acceptance still required

Automated fixtures do **not** establish:

- real Phantom/Solflare extension interoperability;
- a paid OpenBroker inference request, latency, capacity, or final settled cost;
- current private Solana RPC/account behavior;
- a token launch, creator-fee claim, native-GNK acquisition, WGNK bridge, or treasury transfer;
- a production reverse proxy, TLS/CSP/cookie enforcement, backup restore, monitoring, or independent security audit.

No treasury signing key is stored by the application. The server remains a single-worker/single-instance SQLite service and requires persistent storage.

Before production deployment:

1. Run the manual GitHub verifier successfully on the exact release commit.
2. Run the setup doctor and read-only provider/RPC diagnostics with private credentials.
3. Perform a deliberately authorized small paid OpenBroker acceptance test, including streaming/tools if those surfaces will be advertised.
4. Test real wallet-extension sign-in and holder admission on the production origin.
5. Verify backups, restore procedure, reverse-proxy limits, incident contact, privacy/retention policy, and the actual token/mint/threshold configuration.

## Reproduce

```sh
python -m pip install -r requirements-dev.txt
python -m playwright install --with-deps chromium
sh scripts/verify.sh
```

`CHROMIUM_PATH` may point to an existing Chromium executable. The verifier does not intentionally spend provider funds. Live provider diagnostics are separate commands and paid inference requires explicit opt-in.
