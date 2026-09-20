# Publish the verified project to NosytLabs/Slipvolt

The existing GitHub repository was inspected directly. At audit start it contained only `README.md` on root commit `dd0c4db53486f97e21a135ad55b8fea9388c331c`.

The original README bytes match Git blob `62711a95cbd30fcbb93537d47e478252a37b1091`. The root tree/commit were reconstructed and their SHA values verified against GitHub metadata. The canonical source import and fixes are descendants of that exact root, so the release can be fast-forwarded normally if remote main is unchanged.

This execution environment exposes GitHub reads but not file/tree/ref writes. Its command-line runtime also cannot resolve external hosts and has no authenticated Git CLI session. Therefore there is **no claimed remote source upload, GitHub CI run or deployment** from this audit.

## From the companion Git bundle

On a machine with GitHub write access and internet, from the directory containing the bundle:

```bash
git clone slipvolt-ready.bundle Slipvolt
cd Slipvolt
git remote set-url origin https://github.com/NosytLabs/Slipvolt.git
git fetch origin main
git merge-base --is-ancestor origin/main main
git push -u origin main
```

Stop if the ancestry check fails. Fetch and review the new remote commits; do not force-push over them. The repository bundle contains only committed source and tests, not the supplied RPC credential or local runtime database.

## From an existing checkout

```bash
git fetch /absolute/path/to/slipvolt-ready.bundle main:review/slipvolt-ready
git diff --stat main...review/slipvolt-ready
# Review and run scripts/verify.sh on the review branch before merging.
git switch main
git merge --ff-only review/slipvolt-ready
git push origin main
```

Run `sh scripts/verify.sh` after installing Python/Node dependencies and Chromium. Source ZIPs do not contain `.git`; use the bundle for exact ancestry. The application still requires private host configuration and persistent storage after publishing. Do not commit `.env`, databases or logs.
