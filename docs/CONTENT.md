# Customer content and launch publication checklist

Reviewed September 20, 2026. Canonical repository: NosytLabs/Slipvolt.

## Published with this content pass

| Page | Purpose |
|---|---|
| `/help/` | Wallet-to-key setup, safe API configuration, supported API scope, quota reset, illustrative pricing, troubleshooting, key recovery and recent usage export. |
| `/privacy/` | Technical disclosure of account/usage data, third-party processing, cookies, and unfinalized retention/deletion policies. |
| `/terms/` | Draft service rules; separates existing holder access from unbuilt staking, payments, treasury redemption and automatic payouts. |
| `/llms.txt` | Machine-readable API scope, including function tools, and links to customer guides. |

Pages are static, require no JavaScript, and are available through the existing FastAPI static mount. Their Slipvolt product documentation name remains canonical; a deployment using another display brand should review the editorial/legal identity too. No framework or analytics dependency was introduced.

The homepage remains the primary connect → key → prompt flow. Detailed operating explanations belong in help rather than new marketing panels. The recent-usage CSV link uses the existing wallet-cookie endpoint and does not bypass authentication.

## Launch facts still needed — do not invent them

- [ ] Exact Solana mint, decimals, verified purchase URL, final threshold and effective allowance. Do not turn the sample raw-unit value into a launch promise.
- [ ] Final launch venue, creator-fee mode/rate, supply, team allocation/vesting and authority settings, supported by the actual on-chain configuration.
- [ ] Identified operator and private account/privacy/security contact; define support scope and response expectations. Public issues are for sanitized software bugs only.
- [ ] Reviewed production terms, privacy policy, processor/subprocessor arrangements, processing regions, record/log/backup retention and deletion/export procedure.
- [ ] Measured provider/model capacity, real wallet-extension tests, funded inference, domain/HTTPS, incident reporting and change-notice process.
- [ ] Approved paid-service prices, payment methods, credit accounting and refund/dispute policy before enabling checkout. Holder allowance remains separately funded.
- [ ] Verified current swap/deposit path and operational reserve policy. Customer token purchases do not automatically become service funding.

Do not use a green readiness/configuration indicator as a substitute for any of these facts. Do not advertise unlimited access, guaranteed developer profit, unmeasured uptime, anonymous use or zero retention across all providers.

## Accuracy rules

Read the actual `ChatInput` schema, routes and gateway behavior before adding endpoint claims. `/v1/models` fails with 503 when the live catalog cannot be verified; `/api/models` can return a labelled snapshot. A 409 Idempotency-Key conflict is duplicate protection, not cached result replay. An incomplete stream can retain a hold. CSV export is the latest 100 records, not full history. Daily quotas reset at 00:00 UTC; unresolved holds survive the reset.

Proposed prices are $0.075/M input and $0.30/M output by default. For 800M input plus 200M output, modeled revenue is $120, not $120,000. Do not book included holder usage as sales or label gross contribution as net profit. Compare model versions, cache treatment and service limits before making savings claims.

## Source checks

- OpenBroker docs: https://openbroker.gonka.gg/docs — rechecked September 20, 2026. Its upstream account/key is separate from a Slipvolt customer key; use the API host for upstream requests. The documented model IDs match the current repository snapshot. Public documentation is not a funded account benchmark.
- Local implementation: `gridraft/app.py`, `request_policy.py`, `member_gateway.py`, `membership.py`, `store.py`, and the customer frontend.
- Existing operator detail: `API-POLICY.md`, `SECURITY.md`, `FOUNDER-POLICY.md`, `LAUNCH-AND-UTILITY.md` and `QUICKNODE.md`.

## Verification

Run `python -m pytest tests/test_public_content.py -q` and `python scripts/check_content_ui.py`, then the full `sh scripts/verify.sh` suite. Tests check routing, navigation/anchors, example-schema validity, required disclosures and protected usage export. Browser checks cover small/large screens and static-page navigation; they are not real-wallet, funded-provider or legal compliance tests.
