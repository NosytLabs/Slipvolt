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

The runner could not clone GitHub (DNS failure). The working copy was recovered
from existing project archives and the previously merged Gonka RPC patch. Each
modified existing file's baseline blob was checked against the actual GitHub
source. Newer homepage help links and source content were preserved while creating
the delta. The delivery is an **update patch**, not a replacement full repository.

Existing `/help/`, `/privacy/`, `/terms/`, their content-only tests and their browser
runner are left untouched. Those guide-only checks were not reconstructed/rerun
locally; run the complete repository verification script after applying the patch.
The existing manual-only Actions policy, concurrency limits, timeout and credential
persistence settings are retained. No Actions run was triggered here.

No authenticated GitHub publishing CLI or write action was available. A GitHub git
transport check failed to resolve github.com. Local commits are not remote commits;
no merge, public deployment or token launch is established by this package.

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
