# Verification — September 20, 2026

## Current release

- 188 Python tests passed.
- 72 Node tests passed.
- 94 holder/customer browser checks passed.
- 100 admin browser checks passed.
- JavaScript syntax checks, Python compilation and `git diff --check` passed.
- New account-control tests were observed failing before implementation.
- A fresh extraction of the release ZIP passed the Python and Node suites again.
- Publishable source was scanned for the supplied private RPC credential; no match was present. Runtime credentials, databases and generated verification artifacts are not tracked.

## Repository publication

The full application was merged through https://github.com/NosytLabs/Slipvolt/pull/1 at commit `22aaf364c400d4be9e616ac3304bf1944319b5e6`. All 78 source files and executable modes matched the tested local tree `bd54dc97d3895b584dfb2e10c3244da78ad3e8cb` before merge.

GitHub CI run https://github.com/NosytLabs/Slipvolt/actions/runs/35490832137 passed backend tests, Node tests, syntax/compilation checks and both browser suites. Temporary recovery workflows and manifests were removed from the merged tree. Subsequent documentation-only publication notes do not change application behavior.

## What these tests establish

The suites cover wallet-signature authentication, holder verification using controlled RPC responses, owner-isolated key/session controls, shared allowances, rate/concurrency limits, request validation, model policy, reservations, streaming/tool-call handling, uncertain-cost reconciliation, admin authorization and overrides, launch-readiness warnings, business calculations, integration response validation, and desktop/mobile interactions.

Key revocation does not erase usage history. Signing out sessions does not revoke API keys. Multiple keys do not create additional wallet allowances. A configuration check is not labeled a live provider/funding check.

## Limitations

Wallet, RPC and OpenBroker responses are controlled fixtures. Local native browser navigation was blocked, so customer integration used a browser-to-local-HTTP adapter and the admin suite used explicit HTTP fixtures. The tests do not establish native browser CSP/cookie enforcement, real Phantom/Solflare interoperability, or provider capacity/latency.

No funded OpenBroker inference, real payment receipt, staking deposit, live swap quote, mainnet transaction, token launch, automatic developer payout, public deployment or independent security audit was performed. No treasury signing keys are stored by the application. Token thresholds and pricing proposals still require owner-approved live configuration and measured operating costs.

The separate OMA-AI repository and production hosting configuration were not changed. Optional `SITE_NAME` changes display branding only.

## Reproduce

```bash
python -m pip install -r requirements-dev.txt
python -m playwright install --with-deps chromium
sh scripts/verify.sh
```

`CHROMIUM_PATH` can select an installed Chromium executable. Tests do not require or spend private RPC/OpenBroker credentials. For live provider diagnostics, use the separate operator script and its explicit paid-inference opt-in only after privately configuring the account.
