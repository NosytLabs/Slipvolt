# Solana AI workspace revamp

Requested 28 October 2026. Integration owner: Astra. Preserve the existing
Holdbyte customer identity and the canonical `NosytLabs/Slipvolt` repository.

## Product outcome

Eligible holders of the configured Solana token sign a login message, create
their own revocable customer API keys, and use the browser workspace or
`/v1/chat/completions`. The operator keeps a dedicated OpenBroker credential
server-side and funds its native-GNK inference balance. A pump.fun launch
publishes the actual mint; it does not create inference credit by itself.

## Work and acceptance

| Work | Owner | Scope | Evidence required |
| --- | --- | --- | --- |
| Verify Gonka, OpenBroker, and pump.fun integration assumptions | Research agent / Astra | Primary-source research and operating docs | Current source URLs; separate verified behavior from proposed mechanisms |
| Revamp customer UI and asset system | Terra | `public/`, frontend checks | Desktop/mobile inspection, functional wallet/key/chat controls, no fabricated live state |
| Create original hero and status sprites | Astra / imagegen | `public/assets/` | Transparent artwork committed with the site and used by the UI |
| Fix API response boundaries and interrupted-stream cleanup | Sol | `gridraft/`, backend regression tests | Bounded reads, validated usage, reliable cleanup, compatible error responses |
| Integrate and verify | Astra | Docs, full repository verification, branch and PR | Canonical offline suite; read-only provider checks; explicit remaining launch configuration |

## Retained boundaries

Keep `sv_` customer keys, `gridraft_session`, deployed API paths, database
identifiers, stable secrets, and existing accounting compatible. Customer keys
are distinct from the operator's `obk-` key. Native GNK, OpenBroker credit, and
the local reservation ledger are separate balances.

The current product offers a finite holder allowance. It does not spend or burn
the customer's Solana token per request. Token-paid invoices and program-based
locks remain separate future work with their own settlement requirements.

No token, mainnet transaction, account funding, production deployment, or paid
inference is performed as part of this code-only revamp. Live account acceptance
requires the operator's funded OpenBroker configuration.

## Verification record

All implementation and offline acceptance work is complete. The canonical
verification command passed, and public provider GET checks returned HTTP 200.
Final evidence, operational limits and remaining account configuration are in
[REVAMP-REVIEW.md](REVAMP-REVIEW.md). Code publication remains separate from
production deployment and token launch.
