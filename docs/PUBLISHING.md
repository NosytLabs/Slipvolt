# Publishing Slipvolt

## Canonical repository

The full application is published at https://github.com/NosytLabs/Slipvolt on `main`.

PR #1 was merged on September 20, 2026. The verified application release is commit `22aaf364c400d4be9e616ac3304bf1944319b5e6`, with source tree `bd54dc97d3895b584dfb2e10c3244da78ad3e8cb`. All 78 tracked files matched the tested local source before merge. Temporary upload-recovery workflows and manifests are absent from the merged tree.

GitHub Actions run `35490832137` passed Python tests, Node tests, JavaScript syntax checks, Python compilation, and both browser suites before merge. This is repository/CI publication, **not a live service deployment**.

- Merge: https://github.com/NosytLabs/Slipvolt/pull/1
- CI: https://github.com/NosytLabs/Slipvolt/actions/runs/35490832137

## Work from the actual repository

```bash
git clone https://github.com/NosytLabs/Slipvolt.git
cd Slipvolt
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m playwright install --with-deps chromium
sh scripts/verify.sh
```

For further changes, create a branch from current `origin/main`, run the complete test suite, open a pull request, and merge only after checks pass. Fetch and reconcile intervening work; do not force-push over it.

## Deployment is separate

The service requires persistent single-instance storage for the SQLite ledger, private server configuration, an actual project mint and holder threshold, and a dedicated funded OpenBroker account. The tests use controlled wallet/provider responses and do not verify funded production operation.

See `DEPLOYMENT.md`, `QUICKNODE.md`, and `SECURITY.md`. Configure `.env` or your host's secret store outside Git. Never commit private RPC URLs, provider credentials, databases or logs. Rotate credentials previously shared in chat before production use.

## Earlier archives

Companion ZIPs and Git bundles from before publication are historical snapshots, not a substitute for fetching current `main`. Do not push an old bundle over the canonical repository. The separate `NosytLabs/oma-ai` repository and its hosting configuration were not changed by this release.
