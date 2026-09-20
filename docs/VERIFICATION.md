# Current verification — September 20, 2026

This release: 188 Python tests, 72 Node tests, 94 holder UI checks and 100 admin UI checks passed locally. New account-control tests were run failing before implementation. Browser tests use controlled provider and wallet fixtures; localhost navigation was blocked, so the integration used a local HTTP adapter. This is not a live wallet, paid inference, payment, staking, or production test.

`./scripts/verify.sh` runs all current tests. No dependency on a private RPC or upstream credential exists in the test suite.

## Historical reports (not current execution proof)

# Verification — QuickNode / launch-readiness release

Executed 2026-09-20 against the consolidated source imported onto the real remote README ancestry.

## Verified here

- 177 Python tests passed (146 baseline; 31 additional regressions/integration cases).
- 62 Node tests passed.
- 74 holder/public UI checks passed.
- 85 admin UI checks passed.
- Python compilation and JavaScript syntax checks passed; `git diff --check` passed.
- Actual local Uvicorn app was started and restarted on port 8090; `/healthz`, public page and admin page returned 200. Unauthenticated admin connection read returned 401.
- Ten separate checks of the actual local HTTP-served pages/API passed using a browser-to-local-HTTP adapter: desktop/mobile layouts, admin authentication, cleared password input, no credentialed RPC URL in DOM, correct unconfigured labels and no JavaScript errors.
- The supplied private RPC URL, credential path, WSS URL, generated pepper and admin key were scanned against source files; zero matches. Runtime credentials are outside the repository and not included in artifacts.
- Existing source tests and history were preserved. Imported README matches the actual remote root blob.

## Limitations

Native Chromium URL navigation was blocked (`ERR_BLOCKED_BY_ADMINISTRATOR`). Public integration checks therefore use a local HTTP adapter; admin interaction checks use explicit HTTP fixtures. This does not test native browser CSP/cookie/origin enforcement or a real Phantom/Solflare extension. Backend security behaviors have separate tests.

External DNS/network resolution from the application runtime failed. Direct supplied-RPC calls and priority-fee calls could not be verified. The connected QuickNode account reported the endpoint active, and its separate Tooling Access returned Solana mainnet's genesis hash. Those are different checks, not a successful application-to-private-endpoint test. The tooling RPC disallowed the priority-fee extension method; no add-on absence is inferred.

No OpenBroker credential, project mint or private Metis API base was provided to the runtime. There were no paid inference calls, successful live swap quotes, staking deposits, on-chain payments, token launches or treasury transfers. Proposed limits are not a live OpenBroker throughput/context benchmark. Hosted GitHub CI, Docker build, external deployment and independent security audit were not performed.

The public repository contained only its README when checked. Current GitHub tools provide reads but no publishing actions; the command-line environment has no authenticated Git writer and no external DNS. The companion bundle is a verified descendant of remote root `dd0c4db53486f97e21a135ad55b8fea9388c331c`, not a claim that the source was pushed.

## Reproduce

```bash
python -m pip install -r requirements-dev.txt
python -m playwright install --with-deps chromium
sh scripts/verify.sh
```

`CHROMIUM_PATH` can select an installed Chromium executable. All automated service responses are fixtures; running these tests does not require or spend the private RPC/OpenBroker credentials.
