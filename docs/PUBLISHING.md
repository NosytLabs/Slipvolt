# Publishing Holdbyte

## Canonical repository

The Holdbyte application is maintained in [NosytLabs/Slipvolt](https://github.com/NosytLabs/Slipvolt) on `main`. The repository name is a compatibility identifier; work from current shared history rather than an archive, generated preview or unrelated deployment.

```bash
git clone https://github.com/NosytLabs/Slipvolt.git
cd Slipvolt
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m playwright install --with-deps chromium
sh scripts/verify.sh
```

Create a branch from current `origin/main`, reconcile intervening work, run the canonical verifier, open a pull request and merge only after required checks pass. Do not force-push shared history. Pull requests and Actions runs provide revision-specific evidence; avoid copying one run ID or test count into current operating instructions.

## Source publication is not deployment

A commit, pull request, release tag or passing fixture suite does not establish a live service. Production still requires:

- one persistent application instance and a durable SQLite database;
- HTTPS and a reverse proxy with bounded ingress;
- stable private `KEY_PEPPER`, separate `ADMIN_API_KEY`, private RPC endpoints and a dedicated OpenBroker credential;
- a verified project mint, decimals, holder threshold and funded allowance policy;
- a dedicated funded OpenBroker account and reconciled usage;
- backups, restore testing, monitoring, incident response and private support;
- final privacy, retention, service, payment and refund terms.

See [deployment](DEPLOYMENT.md), [security](SECURITY.md), [verification](VERIFICATION.md) and [launch gates](LAUNCH_RUNBOOK.md). Keep `.env`, provider credentials, private RPC URLs, databases and logs outside Git. Rotate any credential previously disclosed through an insecure channel.

## Repository boundaries

The separate `NosytLabs/oma-ai` repository and its hosting configuration are not part of Holdbyte. Do not overwrite, rename or deploy into that project while publishing this one.

Historical ZIP files, bundles and previews are recovery artifacts only. They must not replace current shared history or be treated as evidence that production matches the repository.
