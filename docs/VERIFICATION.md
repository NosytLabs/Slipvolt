# Verification

Holdbyte (the Slipvolt repository) uses one canonical verification command:

```sh
sh scripts/verify.sh
```

The verifier is intentionally local/offline by default. It runs the backend and JavaScript regression suites, syntax/compile checks, and the holder, admin, status, and customer-documentation browser checks. The GitHub Actions workflow runs on pushes to `main`, pull requests, and manual dispatch. It installs the pinned development dependencies and Chromium, then runs this same command.

## What a green verifier establishes

A passing run establishes that the checked source tree satisfies the repository's automated contracts for:

- wallet-signature authentication and session/key lifecycle;
- explicit token-link publication, configured-brand sign-in, tab-memory conversation ownership and request/preflight agreement;
- holder-balance admission and shared allowance accounting;
- request validation, rate/concurrency limits, model policy, streaming and tool-call handling;
- uncertain-cost reservations and operator reconciliation;
- admin settings, customer controls, measured usage/cash-flow charts, and stale-panel handling;
- public status rendering and source-labelled OpenBroker network aggregates;
- Help, Developers, Funding, Privacy, Terms, navigation, responsive layouts, and protected account endpoints;
- Python compilation and JavaScript syntax;
- a self-contained offline preview with embedded styles, scripts and brand images.

A green configuration/readiness check is not a live-service certificate.

## Evidence policy

Do not keep pass-specific verification snapshots as separate "latest" documents. They become stale quickly and previously caused contradictory counts in this repository.

Use these sources instead:

1. **GitHub pull requests and Actions runs** for exact commit/run evidence.
2. **This file** for the current verification scope and limitations.
3. **CHANGELOG.md** for release-specific behavior changes.

Run the canonical verifier again after every change and before deployment. Test counts and individual run links belong to their pull request or Actions record rather than this current operating guide.

## Production acceptance still required

Automated fixtures do **not** establish:

- real Phantom/Solflare extension interoperability;
- a paid OpenBroker inference request, latency, capacity, or final settled cost;
- current private Solana RPC/account behavior;
- a token launch, creator-fee claim, native-GNK acquisition, WGNK bridge, or treasury transfer;
- a production reverse proxy, TLS/CSP/cookie enforcement, a successful isolated restore drill, monitoring, or independent security audit. The `backup-db` and `verify-db` commands provide consistent snapshots and integrity checks, not off-host storage or a tested disaster-recovery procedure; see [database backups](BACKUPS.md).

No treasury signing key is stored by the application. The server remains a single-worker/single-instance SQLite service and requires persistent storage.

Before production deployment:

1. Run the GitHub verifier successfully on the exact release commit.
2. Run the setup doctor and read-only provider/RPC diagnostics with private credentials.
3. Perform a deliberately authorized small paid OpenBroker acceptance test, including streaming/tools if those surfaces will be advertised.

   The `scripts/check_openbroker.py` command is **read-only by default**. A fixed 32-output-token smoke request is attempted once per selected model only when **both** `--allow-paid-inference` and `--acknowledge-cost` are supplied, with a private dedicated credential. Non-JSON provider failures retain the HTTP status and sanitized request ID without echoing the body. `ok: true` indicates one parseable response with consistent prompt/completion/total usage; it is not proof of the route's maximum output, final GNK charges, or capacity. If usage, response or post-probe balance cannot be verified, the diagnostic returns a nonzero exit status and requires manual provider-usage reconciliation before retrying. It never retries automatically.
4. Test real wallet-extension sign-in and holder admission on the production origin.
5. Verify backups, restore procedure, reverse-proxy limits, incident contact, privacy/retention policy, and the actual token/mint/threshold configuration.

## Reproduce

```sh
python -m pip install -r requirements-dev.txt
python -m playwright install --with-deps chromium
sh scripts/verify.sh
```

`CHROMIUM_PATH` may point to an existing Chromium executable. The verifier does not intentionally spend provider funds. Live provider diagnostics are separate commands and paid inference requires explicit opt-in.
