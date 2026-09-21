# Functional setup / UI repair verification — September 21, 2026

## Delivered scope

- Explicit HTTP requests isolate provider keys, cookies, query parameters and client
  authentication. Redirects are disabled per request. Cached network totals are
  returned as independent data. A failed health refresh removes stale health claims.
- Docker includes the read-only Gonka diagnostic.
- Authenticated `/api/preflight` shares admission checks with actual inference,
  including all requested outputs, quotas, rate limits and GNK reservations. It
  never creates a key, dispatches generation or reserves allowance. Normal request
  rate-limit bookkeeping still occurs.
- Secret-safe local setup doctor, a real `/status/` route, request checker,
  credential-free connection kit and reviewed diagnostic report.
- Account/request edits invalidate old preflight results. Failed public refreshes
  clear previous display values. No economics, mint, threshold or fee changes.

## Fresh local checks

| Check | Result |
|---|---|
| Available reconstructed application + new Python suites | 256 passed |
| JavaScript suites | 78 passed |
| Holder UI / adapter integration | 118 passed |
| Admin browser checks | 100 passed |
| Status-page browser checks | 45 passed |
| Actual localhost TCP / Uvicorn HTTP checks | 11 passed |
| Python compilation / JavaScript syntax / diff whitespace | Passed |

The initial combined shell check exceeded the runner's 45-second limit while
browser tests were running. Holder, admin and status checks were then rerun
individually and completed with the counts above. No interrupted partial output
was counted as a pass.

## Source fidelity and publication

Target repository: **NosytLabs/Slipvolt**. Target upstream commit:
`fe1d1467fda6a5500f8411f031ef9601fde25a38`.

The runner's direct git transport could not resolve github.com, so the working copy
was recovered from existing project archives and checked against the actual GitHub
base blobs. Publication was later completed through the connected GitHub API in PR
#5 after every changed remote blob was matched to the locally verified source.

The existing manual-only Actions policy, concurrency limits, timeout and credential
persistence settings were retained. No hosted Actions run was triggered by this
verification work. The merge establishes source publication only: it does not
establish a public deployment, token launch, live wallet acceptance, or paid
OpenBroker inference.

## External verification limits

Model/provider/RPC responses in tests were fixtures. The holder browser runner used
an HTTP adapter because native localhost navigation was blocked. Status rendering
used a read-only FastAPI TestClient bridge. The separate HTTP test did reach a real
Uvicorn server over local TCP. This does not verify browser-native TLS, CSP or cookie
enforcement, real wallet extensions, real account balances or paid OpenBroker
inference. The Dockerfile's contents were checked; no Docker image build is claimed.

The offline preview shows no invented token, balances, usage or model replies.
Its full-site links require the running application; it is not a public deployment.

## Research checked

- OpenBroker documentation: https://openbroker.gonka.gg/docs
- HTTPX client merging and explicit requests: https://www.python-httpx.org/advanced/clients/
- Gonka WGNK -> GNK recipient rules: https://gonka.ai/docs/cross-chain-transfers/ethereum-bridge/withdraw-gnk/

The browser research tool could read the documentation but not the raw public model
endpoint in this run. A paid check was not attempted; no account credential was
supplied. The existing model IDs and safe native-GNK funding boundaries are retained.
