# Functional setup and request checks

The customer path is **connect wallet → create key → choose a model → check → send**. Setup and preflight tools reduce configuration mistakes; they do not prove a deployed token, funded provider account or successful inference.

## Operator: inspect configuration without spending

```sh
python -m gridraft.cli --env-file .env doctor
```

The doctor reads local configuration and file metadata only. It makes no network calls, opens no database and never prints credential values. Exit 2 means a configuration blocker; exit 0 still means `review_required`, not a working production deployment. Preserve the same pepper and database across upgrades.

Run explicit read-only checks separately:

```sh
python scripts/check_gonka.py --env-file .env
python scripts/check_connections.py --env-file .env
python scripts/check_openbroker.py --env-file .env
```

The Gonka check reads keyless public chain state. The connection check validates configured RPC identities and capabilities. The OpenBroker check reads the public catalog and, when a private server key is configured, account balance. None launches a token, moves assets or runs paid inference by default. Consult each command's `--help` before deliberately enabling a paid smoke check.

To inspect provider-reported request costs and epoch adjustments for a particular UTC window, explicitly run the bounded read-only usage report (replace the example dates):

```sh
python scripts/reconcile_openbroker.py --env-file .env --from 2026-10-01 --to 2026-10-07
```

The command reads the private OpenBroker usage list, makes no inference request, and changes no local ledger or funds. It separates provider-reported settled requests, estimates, epoch adjustments, unbilled fallback and other sources. Amounts are decimal strings in ngonka to preserve integer precision. The default limit is five pages of 200 records; `--max-pages` accepts 1–25. A result exceeding that bound or with incomplete, duplicate or inconsistent pages fails rather than returning partial totals. Shorten the date window or deliberately raise the limit when necessary.

Pages can change during collection, and even a complete list is not an independently verified statement or final account settlement. Reconcile with actual provider account movements before treating any amount as a cost or spendable balance. The documented [usage list and cost sources](https://openbroker.gonka.gg/docs/usage) differ from the usage summary, which excludes synthetic epoch accounting lines.

Keep provider keys and private RPC URLs in the server environment or secret store. Do not paste them into the customer site, issue tracker or support report.

## Customer: check before sending

In the playground, **Check request · no inference** sends the request body to authenticated `POST /api/preflight`. It performs schema and admission checks and may read catalog, health, eligibility and spendable-balance state. It does not submit the prompt for generation, create an allowance reservation or create a new API key.

The check shares inference normalization and estimates:

- context is assessed per completion choice;
- allowance is estimated as input once plus requested output for every `n` choice;
- input uses conservative UTF-8 admission units, not the model's exact tokenizer;
- output and context use effective local policy, not a verified OpenBroker benchmark.

Editing the request or changing wallets invalidates a displayed result. A successful check reserves no capacity. **Send** repeats every authorization, eligibility, catalog, funding and quota check.

Cookie sign-in or a valid customer bearer key is required, together with the configured same-origin header. A revoked bearer key does not fall back to a cookie. Preflight supports holder-allowance mode; legacy prepaid mode does not use it.

## Connect an application

The **Use the API** tab produces cURL, Python and JavaScript examples using the selected model and output budget. The connection kit contains the service origin plus `/v1`, the selected model and the environment-variable name for the customer key. It never copies a credential value.

Use a live model ID from `GET /v1/models`. Preserve `X-Request-Id`, respect `Retry-After`, and disable automatic retries for ambiguous paid requests. A duplicate `Idempotency-Key` produces 409 duplicate protection; it is not response replay.

## Status and support

`/status/` loads configuration, the model catalog, optional treasury telemetry and source-labelled OpenBroker-wide statistics independently. Missing data remains unavailable. A configured mint is not a confirmed launch; a catalog row is not an inference benchmark; a native reserve is not provider credit; OpenBroker network traffic is not Holdbyte customer activity.

**Review support report** displays an allowlisted report before copying: build version, selected public model ID, a recognized preflight reason and a validated local UUID request ID. It excludes prompts, responses, wallets, keys, cookies, endpoints, arbitrary exception strings and browser storage. For sensitive account or security matters, use the operator's private channel rather than a public issue.

## Acceptance still required

Before production onboarding:

1. Run the canonical verifier on the exact release revision.
2. Test the deployed origin, HTTPS, headers, cookies, reverse-proxy limits and backup restore.
3. Verify the published mint, decimals, threshold and allowance against finalized mainnet reads.
4. Perform an explicitly authorized small provider acceptance call and reconcile its usage and cost.
5. Test real supported wallet extensions and every advertised request mode.
6. Publish final operator identity, support, privacy/retention, service and payment/refund terms.

GitHub Actions runs on pushes to `main`, pull requests and manual dispatch. Fixture success does not establish provider capacity, production wallet interoperability, a token launch, a live deployment or legal review.
