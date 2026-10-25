# Holdbyte product and architecture

## Customer path

**Hold → connect/sign → create key → chat or use the API.** A qualifying Solana wallet receives a bounded AI allowance backed by native GNK. Multiple API keys share the same wallet allowance. Selling below the configured threshold blocks new requests after the finalized holding check reflects the change.

The home page presents the promise, wallet access, workspace and measured usage in that order. Prompt starters populate an editable draft without sending it. Chat context stays in tab memory and is included in each follow-up request; it is never silently truncated. Request settings, preflight and support diagnostics sit behind an expandable control. Help, funding and developer detail have their own pages.

The service never invents a mint, purchase URL, holder count or usage figure. The official Pump.fun link requires an explicit launch setting and a validated configured mint. See [brand assets and domains](BRAND.md) and [token design](TOKEN-DESIGN.md).

## Boundaries

- `gridraft/app.py` — FastAPI routes, authentication flow, runtime configuration and policy wiring. It re-exports the existing request schema/middleware names for import compatibility.
- `gridraft/schemas.py` — strict wallet, chat, admin and swap-quote request models and validators.
- `gridraft/body_boundary.py` — ASGI body-size and nesting guard, independent of route setup.
- `gridraft/membership.py` — wallet/global RPM, concurrency and token allowance admission.
- `gridraft/member_gateway.py` — pre-dispatch reservation, OpenBroker forwarding, settlement and uncertain-request reconciliation.
- `gridraft/broker.py` — OpenBroker catalog, balance, usage and public health reads.
- `gridraft/store.py` — persistent SQLite state, API keys, usage, business ledger and operator audit log.
- `gridraft/model_policy.py` — reviewed local limits, discovered metadata/provenance, explicit operator overrides and direct-price reference metadata.
- `public/` — customer app; `public/admin/` — operator-only control plane.

No module stores a treasury signing key or executes swaps. GNK allocation in the admin console only mirrors already verified operating funds into Holdbyte's local allowance ledger.

## Capacity policy

The live OpenBroker catalog is intersected with reviewed local policies. Their defaults are 180K context for MiniMax M2.7, 400K for DeepSeek V4 Flash and GLM 5.3 Flash, and a conservative 4,096 output-token default and cap for each. These are informed by Gonka deployment configuration and configurable gateway defaults, not verified OpenBroker serving limits. Missing or zero discovery remains unknown; positive discovery can only tighten reviewed policy. Explicit server-side overrides are separately labelled unverified and cannot silently enable new models. See [API policy](API-POLICY.md).

Provider health, local wallet/global quotas and spendable GNK are independent gates. A model advertised in a catalog but explicitly unavailable in OpenBroker health is blocked before provider spend.
