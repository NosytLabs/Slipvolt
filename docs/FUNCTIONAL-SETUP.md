# Slipvolt 0.9.1 — from setup to a verified request

The customer flow remains **connect wallet -> create key -> choose a model**.
This update does not change the token economics, mint, fees, funding allocations,
retail reference prices, holder thresholds or model list.

## Operator: check setup without spending

```sh
python -m gridraft.cli --env-file .env doctor
```

The doctor reads local configuration and file metadata only. It makes no network
calls, opens no database connection, creates no database and never outputs
credential values. Exit 2 means a configuration blocker; exit 0 still means
`review_required`, not a working production deployment. An invalid setting is
reported without echoing the invalid value. Keep the pepper stable across upgrades.

Next, use the existing explicit read-only checks from the repository root:

```sh
python scripts/check_gonka.py
python scripts/check_connections.py --env-file .env
python scripts/check_openbroker.py --env-file .env
```

The OpenBroker check reads the public catalog and, with your privately configured
key, the account balance. The Docker image now includes the Gonka diagnostic.
None of those commands launches a token, moves assets or runs paid inference by
default. Consult their `--help` before deliberately enabling a paid smoke check.
Do not paste provider keys or private RPC URLs into the public site.

## Customer: inspect before sending

In the playground, **Check request · no inference** sends the request body only to
Slipvolt's authenticated `/api/preflight` endpoint. The body is validated locally;
only catalog, health, wallet and balance reads go to providers. Your prompt is not
sent for model generation, and no usage reservation, API key or credit is created.
The anti-abuse rate limiter may record the check.

The check uses the same admission logic and normalized streaming/multiple-output
budget as inference. It explains wallet quota, shared quota, concurrency, rate,
reconciliation, provider balance and local pool failures. Estimates are conservative
UTF-8 admission units, not an exact tokenizer or bill. Editing the request or
changing wallets invalidates its displayed result. A successful check reserves no
capacity; **Send** verifies the conditions again.

Cookie sign-in or a valid customer bearer key is required, together with the
configured same-origin header. A revoked bearer key never falls back to a cookie.
This endpoint currently supports holder-allowance mode, not legacy prepaid mode.

## Connect an application

The **Use the API** tab has a connection kit containing the current service origin
plus `/v1`, the selected model and the environment variable name for the key. It
never copies a credential value. Existing cURL/Python/JavaScript examples remain.
No automatic paid retry or model action is introduced.

## Status and safe support

`/status/` reads configuration, the model catalog, optional treasury telemetry and
OpenBroker-wide statistics independently. Missing data remains unavailable. Failed
refreshes clear old values. A configured mint is not a confirmed launch; a catalog
entry is not an inference benchmark; a reserve balance is not broker credit.
There are no invented uptime percentages or transaction records.

**Review support report** shows an allowlisted report before copying: build version,
selected public model ID, a recognized preflight reason and a validated local UUID
request ID. No prompt, response, wallet, key, cookie, endpoint, arbitrary exception
or browser storage is exported. Account sign-out clears request-check state.
For sensitive account/security matters use an operator's private channel, not a
public issue containing secrets.

## Current source research

Rechecked September 21, 2026:

- https://openbroker.gonka.gg/docs — public catalog, API-host distinction, account
  available balance versus total balance, native-GNK deposits and epoch costs.
  Kimi K2.6 is deprecated there; the existing three-model catalog is retained.
- https://www.python-httpx.org/advanced/clients/ — client-level headers, cookies and
  query parameters are merged by convenience methods. Explicit `Request` objects
  and `send(auth=None, follow_redirects=False)` isolate each service boundary.

The production adapter preserves request-size limits and closes streamed responses.
Provider health cache failures now remove the old health claim and are negatively
cached to avoid repeatedly hammering an unavailable provider.

## Acceptance still required

No public deployment, real extension session, private balance verification, paid
OpenBroker request, swap, token launch or independently audited production security
is established by fixture tests. Review the existing Help, Privacy, Terms and launch
runbook before opening the service. The existing customer guides are not replaced
by this patch. Manual-only GitHub Actions remain manual-only.
