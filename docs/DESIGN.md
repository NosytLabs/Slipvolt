# Slipvolt 0.8.0 design

## Customer path

**Hold → connect/sign → create key → call Gonka models.** A qualifying Solana wallet receives a bounded AI allowance backed by native GNK. Multiple API keys share the same wallet allowance. Selling below the configured threshold blocks new requests after the finalized holding check reflects the change.

## Boundaries

- `gridraft/app.py` — FastAPI surface, auth, admin API, current policy/config. The internal package name is retained for database/import compatibility.
- `gridraft/membership.py` — wallet/global RPM, concurrency and token allowance admission.
- `gridraft/member_gateway.py` — pre-dispatch reservation, OpenBroker forwarding, settlement and uncertain-request reconciliation.
- `gridraft/broker.py` — OpenBroker catalog, balance, usage and public health reads.
- `gridraft/store.py` — persistent SQLite state, API keys, usage, business ledger and operator audit log.
- `gridraft/model_policy.py` — verified model capability ceilings and direct-price reference metadata.
- `public/` — customer app; `public/admin/` — operator-only control plane.

No module stores a treasury signing key or executes swaps. GNK allocation in the admin console only mirrors already verified operating funds into Slipvolt's local allowance ledger.

## Capacity policy

The live OpenBroker catalog is intersected with verified Gonka model metadata. Current capability ceilings are 180K context for MiniMax M2.7, 400K for DeepSeek V4 Flash and GLM 5.3 Flash, and 16,384 output tokens for each. Slipvolt defaults output to 4,096 to limit latency and reservation size, while allowing up to the upstream capability.

Provider health, local wallet/global quotas and spendable GNK are independent gates. A model advertised in a catalog but explicitly unavailable in OpenBroker health is blocked before provider spend.
