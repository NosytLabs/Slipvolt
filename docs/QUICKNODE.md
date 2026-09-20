# QuickNode setup and connection checks

Updated 2026-09-20. This application has **read-only RPC diagnostics and indicative swap quotes**. It does not launch tokens, sign transactions, bridge GNK, execute 0x swaps, or credit customers from a quote.

## Private configuration

Keep the endpoint URL in a server secret store or a mode-600 `.env`. RPC and WSS URLs often contain a bearer credential in the path. Do not place them in the repository, frontend bundle, customer logs, screenshots, or browser storage. Rotate a credential that has been shared beyond its intended operators. This audit did not rotate it or change QuickNode access rules.

Set these on the actual deployment host:

```env
SOLANA_RPC_URL=<your private HTTPS Solana endpoint>
SOLANA_WSS_URL=<your private WSS Solana endpoint>
SOLANA_RPC_RPS=15
SOLANA_RPC_CONCURRENCY=8
METIS_API_URL=<exact installed add-on API base, or leave blank>
ZEROX_API_URL=
```

The first two values are separate from an OpenBroker API key. WSS is stored for future server subscriptions but **no WSS subscription is started**. `ZEROX_API_URL` is reserved configuration; the current server does not use it.

The QuickNode connection reported an active Solana endpoint with a 50-RPS ceiling during this audit. The application deliberately starts at 15 RPC reads/second and eight simultaneous reads for one persistent process. This is independent of the customer limit of 30 inference requests/minute and four simultaneous requests per wallet. Other clients on the same QuickNode account can consume the remaining capacity.

## What each integration does

| Integration | Purpose | Current implementation |
|---|---|---|
| Solana HTTP RPC | Mainnet identity, finalized holdings and health reads | Implemented server-side; wrong-chain configuration fails closed in production |
| Solana WSS | Future subscriptions | Configuration only; not active |
| Priority-fee add-on | Estimates for future transaction construction | Read-only button; micro-lamports/CU and lamports are labeled separately |
| Metis/Jupiter | Solana asset conversion quotes | Quote only to canonical native USDC; no transaction construction/submission |
| 0x | EVM-side routing | Not implemented; not a native-GNK bridge |

QuickNode's [Swap API overview](https://www.quicknode.com/docs/solana/swap-api) and [provider table](https://www.quicknode.com/swap-api) describe the products. Copy the exact API base from the installed product configuration: a dashboard get-started link is not an API base. Do not assume an RPC credential path can be reused for another product. No automatic fallback to a fee-charging public endpoint is enabled.

## Test from your deployment host

```bash
python scripts/check_connections.py --env-file .env
python scripts/check_connections.py --env-file .env --priority-fees
```

These commands never print credentialed endpoints. They return nonzero when mainnet health cannot be verified. In `/admin/`, unlock the console and use **Check RPC** and **Check priority fees**. “Configured” means a value exists; only a successful check means connectivity was verified.

The QuickNode connector's Tooling Access returned the Solana-mainnet genesis hash in this audit. The application runtime could not resolve the external endpoint, so **the supplied endpoint was not verified end-to-end from this server**. Tooling Access is a different transport. The connector rejected the priority-fee method as not allowlisted; that is not evidence the user's add-on is missing.

## Quote-only contract

`POST /api/admin/swap/quote` requires the separate admin bearer key and same-origin mutation protection. It accepts `asset: SOL` or `PROJECT`, a plain decimal amount, and slippage of at most 100 basis points. The project mint must be configured for PROJECT.

The adapter checks returned mints, ExactIn mode, raw input amount, slippage, positive minimum output, a route, and a context slot. It rejects excessive price impact and strips transaction payloads, metadata and endpoint URLs. The 15-second expiry is a **local display policy**, not a provider fill guarantee. The slot is present but is not yet compared with a live current slot; these quotes must not be used as a settlement oracle.

[QuickNode quote reference](https://www.quicknode.com/docs/solana/quote) and [priority-fee reference](https://www.quicknode.com/docs/solana/qn_estimatePriorityFees) are the source contracts. Future payments must credit only finalized net received USDC, not the displayed quote.
