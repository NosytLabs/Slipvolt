# Gonka RPC integration

Slipvolt uses a bounded, read-only `GonkaRPC` adapter for public chain health, an optional configured native-wallet balance and operator model discovery. These reads are separate from authenticated OpenBroker inference and never receive an `obk-` key, Solana credential, customer cookie or treasury secret.

## Connected reads

| Purpose | Public interface |
|---|---|
| Mainnet identity, sync and recent block | `GET https://rpc.gonka.gg/chain-rpc/status` |
| Configured native wallet balance | `GET /chain-api/cosmos/bank/v1beta1/balances/{address}/by_denom?denom=ngonka` |
| Operator model discovery | `GET /v1/models` |
| Human documentation | `https://rpc.gonka.gg/endpoints` and `/agents` |

Only the allowlisted GET routes are callable through the adapter. It does not forward arbitrary RPC methods, broadcast transactions, sign messages, execute swaps or call `/v1/chat/completions`.

`GONKA_TREASURY_ADDRESS` is an optional public address to inspect. Leave it blank to publish no self-custody balance. Never use the public OpenBroker operator address as the project's treasury or dashboard deposit address.

## Operator checks

```bash
# Keyless chain health; reads configured public address when present.
python scripts/check_gonka.py --env-file .env

# Include the public Gonka model catalog. This is not inference.
python scripts/check_gonka.py --env-file .env --models

# Inspect a specific public address without changing service configuration.
python scripts/check_gonka.py --treasury-address gonka1YOUR_VALID_ADDRESS

# Run existing Solana checks and explicitly add Gonka health.
python scripts/check_connections.py --env-file .env --gonka
```

The placeholder is intentionally invalid. Supply a checksum-valid public address, never a private key or seed phrase. Exit 0 means the requested reads passed the script's local validation; it does not prove spendable OpenBroker credit, authorize launch or transfer assets.

## Validation and failure handling

The local health policy requires:

- network `gonka-mainnet`;
- `catching_up: false`;
- a positive decimal block height;
- a 64-character hexadecimal block hash;
- a timezone-aware recent block timestamp.

These are conservative display checks, not consensus verification or an SLA. Clock skew or a slow public gateway can make telemetry unavailable.

Status and balance reads use short caches and negative cooldowns so public page traffic does not amplify an outage. Failed refreshes display unavailable rather than retaining a stale balance or inventing zero. Returned cached objects are copied before use.

The status block height and a separately returned bank balance are not an atomic light-client proof. Bank balance is not necessarily transferable balance. A native-wallet read never credits the local ledger and never replaces the authenticated OpenBroker spendable-balance check.

## Model metadata boundary

A public Gonka gateway may return zero or missing context/output fields. Slipvolt treats those values as unknown, never unlimited. The separate proxy metadata used by model policy is also capability discovery rather than verified OpenBroker account behavior.

The live OpenBroker catalog determines which model IDs are eligible for routing. Reviewed local policy determines whether a listed ID has usable admission limits. Discovery may tighten those limits but cannot raise them or activate an unknown model. Explicit operator overrides are labelled unverified and still require deployment-specific evidence.

No public catalog read establishes latency, availability, output behavior, cost, privacy or successful inference for the operator's funded account.

## Primary references

- [Gonka RPC endpoints](https://rpc.gonka.gg/endpoints)
- [Gonka agent guidance](https://rpc.gonka.gg/agents)
- [Structured endpoint discovery](https://rpc.gonka.gg/api/endpoints)
- [OpenBroker documentation](https://openbroker.gonka.gg/docs)
- [Local API policy](API-POLICY.md)
