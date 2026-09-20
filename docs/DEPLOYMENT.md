# Deployment — single persistent holder service

Use one Python worker with a persistent SQLite volume, not ephemeral serverless storage. `docker compose up --build -d` uses the supplied named volume and loopback-only port. Expose through an HTTPS reverse proxy you administer, with the exact public `APP_ORIGIN`, `APP_ENV=production`, stable `KEY_PEPPER`, trusted Solana RPC and validated mint. A blank mint is allowed only for a development preview. No domain or deployment was created by this build.

Configure `ACCESS_MODE=holder_allowance` deliberately during a v0.2 migration. Back up the database (SQLite backup API or stopped writer), existing secrets and pepper before changing anything. New tables are additive; dollar credit records are not rewritten or converted to GNK. Existing keys remain valid only under the new membership rules; legacy dollar caps are not applied to the GNK allowance. Resolve existing customer obligations first.

A CLI run on the host and a CLI run inside Docker must refer to the SAME database. For Compose, invoke operator allocation/reconciliation inside the running service:

```sh
docker compose exec gridraft python -m gridraft.cli allocate-gnk \
  --gnk 1 --reference VERIFIED_FUNDING_REFERENCE --acknowledge-funded
```

Read-only check: `docker compose exec gridraft python scripts/check_openbroker.py` requires the scripts directory copied into the image (included here). The operator console is served at `/admin/` and requires the separate `ADMIN_API_KEY`; additionally restrict `/admin/` at your reverse proxy/VPN where practical. Restrict shell access, snapshot backups consistently, and monitor account availability and review holds. Bound IP rate limiting/ingress independently at the proxy; arbitrary X-Forwarded-For is not trusted.

Private broker balance is not published unless `PUBLIC_BROKER_BALANCE=true`. A configured self-custody GNK address is public by design. The two balances have distinct scopes. Neither dashboard display authorizes a financial operation.

GitHub CI is included in `.github/workflows/test.yml`. Run the same `./scripts/verify.sh` gate before publishing or deploying.
