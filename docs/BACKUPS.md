# Private SQLite backups and restore checks

Holdbyte currently runs a **single-writer, persistent SQLite database**. Its data includes hashed API/session credentials, wallet identifiers and financial/usage accounting, so backup files are sensitive even though they are not signing keys.

## Back up a live database

Use the CLI on the same host/container and `DATABASE_PATH` as the running application. It uses the SQLite online backup API to capture a consistent committed snapshot while WAL-mode writes may continue; it does **not** copy the raw `.db` file without its associated WAL state.

```sh
# Create a unique new filename in an already-existing PRIVATE directory.
python -m gridraft.cli --env-file .env backup-db \
  --output /secure/backups/holdbyte-2026-10-25.db

# Verify the newly created copy (read-only).
python -m gridraft.cli verify-db \
  --file /secure/backups/holdbyte-2026-10-25.db
```

The command **refuses to overwrite or follow an existing destination**, fails if the source does not exist or is not an initialized Holdbyte SQLite database, rejects destinations under the public web directory, checks the snapshot's SQLite integrity and required tables, and creates files with owner-only permissions (0600 on POSIX). It stages the snapshot in the destination directory and publishes it atomically. Temporary files are removed on failure. No `KEY_PEPPER` is required just to copy or verify the database.

Successful output reports only status, byte count and SHA-256 digest. It does not dump paths, wallet records, session values or database content. The CLI never sends a token, request to OpenBroker or Solana transaction. A backup captures committed database state at a point in time; it does not freeze the application's activity.

Verify a stable, standalone snapshot, not a live database. `verify-db` refuses files with a nonempty SQLite WAL or rollback journal: those files may contain state that the main database file's checksum does not cover. Use `backup-db` to capture a live database first, and keep the snapshot unchanged while verifying or transferring it.

**An integrity pass is not a full restoration drill.** It also does not mean the file is encrypted, safe to publish, or current after a subsequent service write.

## Docker Compose

Compose mounts the active database at `/app/data`. A copy left there is **on the same named volume**, so it is only an intermediate snapshot, not disaster recovery:

```sh
docker compose exec gridraft python -m gridraft.cli backup-db \
  --output /app/data/holdbyte-2026-10-25.db
docker compose exec gridraft python -m gridraft.cli verify-db \
  --file /app/data/holdbyte-2026-10-25.db

# From the Docker host, transfer to restricted storage off that volume.
mkdir -p private-backups
chmod 700 private-backups
CONTAINER_ID=$(docker compose ps -q gridraft)
docker cp "$CONTAINER_ID:/app/data/holdbyte-2026-10-25.db" private-backups/
chmod 600 private-backups/holdbyte-2026-10-25.db
```

Verify the **copied-out** file using a compatible local Holdbyte checkout or a separate isolated verification container. Compare its SHA-256 to the CLI report. Then encrypt and move it off-host under an established retention/access policy. Clean temporary on-volume copies only after confirming a recoverable off-host version.

## Restore drill and operational checklist

1. Keep the original stable `KEY_PEPPER`, server secrets and environment configuration **separately** in an approved secrets manager. They are not embedded in the SQLite backup. Never put secrets in Git or the published `public/` tree.
2. Retain multiple dated, encrypted, access-controlled off-host copies and verify SHA-256 after transfer. Never count a backup solely on the same server/volume as recovery protection.
3. For a restore drill, create an isolated clean host/volume; do **not** overwrite the active production database.
4. Run `verify-db` on the transferred file, start a single worker with the restored database and matched private configuration, and manually check account, session, API-key, allowance/reservation and admin-ledger workflows. Disable public ingress and provider spending during the drill.
5. Before a real restore, stop the production writer and preserve a separate emergency snapshot; document the last consistent backup, expected data loss window, recovery point and audited operator approval.
6. Schedule backups, expiry, encrypted storage, off-host transfer, restore rehearsals and alerting **outside** this app. This repository does not configure a scheduler or automatically ship backups elsewhere.

Avoid SQLite files on network filesystems, independent concurrent app replicas, and copying only the live main `.db` file in WAL mode. This utility does not verify upstream provider settlement or on-chain treasury state; those are separate reconciliation procedures.
