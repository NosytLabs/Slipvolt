# Gonka RPC integration and focused audit

Reviewed September 20, 2026 (America/Phoenix). Source base: `585b7cf9f3d6622f2c6f74899a27a8ca75d46695`.

## What is connected

The existing `/api/treasury` GNK reader now uses a shared read-only `GonkaRPC` adapter at **https://rpc.gonka.gg**. The provider documents keyless, open-access reads; no new RPC account, API key, or deposit is needed. This does not make paid model inference free.

| Purpose | Interface |
|---|---|
| Mainnet identity, sync and recent block | `GET /chain-rpc/status` |
| Configured native wallet's GNK balance | `GET /chain-api/cosmos/bank/v1beta1/balances/{address}/by_denom?denom=ngonka` |
| Operator model discovery | `GET /v1/models` |
| Human documentation | `/endpoints` and `/agents` |
| Agent reference data | `/llms.txt`, `/llms-full.txt`, `/api/endpoints` |

Only the first three GET routes are callable through the adapter. Documentation/discovery is never treated as authority to execute additional routes. Transaction broadcasting, raw RPC method forwarding, swaps, treasury signing, and `/v1/chat/completions` are deliberately absent.

The native wallet still comes from `GONKA_TREASURY_ADDRESS`. Leave it blank to publish no self-custody balance. Do not use the public OpenBroker operator address as your own treasury or deposit address. Existing API keys, Solana RPC secrets, mint configuration, quotas, pricing and OpenBroker inference routing are unchanged. `/api/admin/connections/check` remains the Solana diagnostic; use the CLI below for Gonka.

## Operator checks

```bash
# Keyless chain health only; add the native wallet through the existing .env setting.
python scripts/check_gonka.py --env-file .env

# Include the Gonka model catalog (not a paid inference test).
python scripts/check_gonka.py --env-file .env --models

# Optional: read a specific public Gonka wallet without changing the service config.
python scripts/check_gonka.py --treasury-address gonka1YOUR_VALID_ADDRESS

# Existing Solana diagnostic can also include Gonka, explicitly requested.
python scripts/check_connections.py --env-file .env --gonka
```

The illustrative wallet placeholder is not valid; replace it with a checksum-valid address you intend to inspect. Do not supply a private key or seed phrase. Exit code 0 means all requested reads passed; 2 means a requested check failed. Successful diagnostics do not authorize launch, prove spendable OpenBroker credit, or transfer funds.

## Safety and failure handling

Status must report `gonka-mainnet`, `catching_up: false`, a positive decimal block height, a 64-character hex block hash, and a timezone-aware timestamp no more than 180 seconds old or 30 seconds ahead. These are conservative local health thresholds, not provider guarantees. A server clock error or slow block can therefore make the display unavailable.

The status is cached for 15 seconds and native balance for 30 seconds. Failed status/balance reads have a shared 10-second cooldown to prevent concurrent visitors amplifying an outage. Failed refreshes clear the balance rather than displaying an old amount as current. Returned caches are copied, so a caller cannot mutate the retained balance. No missing balance is represented as zero.

Every request uses a fixed HTTPS origin, explicit credential-free request construction, redirects disabled, an 8-second deadline, and a decoded response-size limit. Even a shared HTTPX client with default authentication, cookies or secret query parameters does not send them to Gonka through this adapter. The adapter does not introduce a generic client-controlled URL proxy.

`rpc_block_height` is the height observed in the separate status response, **not a proof that the bank balance was read at that exact block**. Gateway reports are not independently verified light-client proofs. The bank response is total native balance, not necessarily transferable/spendable balance. No treasury display value credits the local ledger or replaces OpenBroker's authenticated spendable-balance check.

## Model metadata finding

A live external fetch of the gateway's `/v1/models` listed MiniMax M2.7, DeepSeek V4 Flash 0731 and GLM 5.3 Flash, but returned `context_length: 0` and `max_output_length: 0`. These zeros are **unknown**, not unlimited capacity. The new model-discovery result reports null for unknown limits, recognizes the output-length alias, and uses the tighter value when two positive output fields exist. Duplicate/invalid IDs are rejected.

Do not replace measured or reviewed OpenBroker policy with those zeros. The existing `Broker.model_metadata()` source and local inference caps remain unchanged. No extra model, higher output cap, free inference route, or provider availability guarantee was enabled.

The human agents page described 352 endpoints while the fetched full reference reported 354. Do not hard-code a claimed endpoint count or execute every discovered method. The main documentation says accounts are deprecated and keys must not be sent; older agent examples still mention an optional tracking key. This integration sends none.

## Audit findings addressed

1. Native GNK display lacked a network/sync/freshness check. It now fails closed when the gateway's status is unsuitable.
2. A failing native balance read could generate one upstream attempt per queued request. Negative caching now coalesces those failures.
3. The native balance cache returned its mutable dictionary directly. Callers now receive a copy.
4. The previous native reader could inherit a supplied HTTPX client's credentials. Explicit requests prevent that inheritance.
5. Solana's first mainnet check could be skipped if the monotonic clock was below 300 seconds. An explicit uninitialized sentinel now ensures the first check always runs.

## Validation and limits of this audit

The 78-file core archive was available locally and its backend sources matched the current GitHub tree. This audit runs its 188 existing Python tests plus the new Gonka tests, and 72 JavaScript tests. The later customer-content-only files are preserved from GitHub, not replaced by the archive. Their additional 19 content tests are not part of this local snapshot, so this is **not a claim that the full current repository CI was rerun**.

GitHub issues were empty at inspection. The newer manual-only test workflow and repository cost controls are preserved; no workflow is re-enabled or dispatched by this change. No production site restart or deployment is performed.

An external live fetch through Firecrawl returned HTTP 200 for chain status, the model catalog, and a public operator-wallet balance query. That wallet is a read-only test target, not a project treasury. Direct requests from this development runtime failed DNS resolution, so live success through the application's own transport is still unverified. Regression tests use HTTPX MockTransport, not funded inference or real wallets.

Remaining launch work includes a configured project mint/threshold, funded dedicated OpenBroker account, live extension/provider tests, reliable persistent hosting, finalized customer policies and protection against moving tokens between wallets to farm allowances. The RPC integration does not solve those separate requirements.

## Primary references

- https://rpc.gonka.gg/endpoints
- https://rpc.gonka.gg/agents
- https://rpc.gonka.gg/llms-full.txt
- https://rpc.gonka.gg/api/endpoints
- https://openbroker.gonka.gg/docs
- https://www.python-httpx.org/advanced/clients/#request-instances
