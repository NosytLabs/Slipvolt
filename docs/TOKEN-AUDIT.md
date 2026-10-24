# Token supply and burn evidence

Holdbyte's `/token/` page is a read-only view of the configured access mint and submitted burn receipts. It never requests a wallet signature or accepts an admin credential. The Funding page links to it.

## Run and configure

The production entry point `gridraft.main:app` installs the evidence routes before the root static mount. Existing `HOLDER_MINT`, `HOLDER_TOKEN_DECIMALS`, `HOLDER_TOKEN_SYMBOL`, `SOLANA_RPC_URL`, `ADMIN_API_KEY`, `APP_ORIGIN`, and persistent database settings are reused. No new secret or signing key is required. Factory-based hosts using `create_app` directly must also call `install_token_audit_routes(app, settings)` from `gridraft.token_audit_api`.

No configured mint means **unconfigured**, not zero supply. An unavailable RPC means **unavailable**, not a stale live snapshot. Successful and failed snapshot reads are cached for 20 seconds; HTTP responses are marked `no-store`. Public requests are rate-limited, and only the latest 25 saved receipts are displayed.

## Read and record

`GET /api/token` returns the finalized mint supply, mint/freeze authority fields, token program, slot, and an independently scoped local receipt summary. Raw token amounts are decimal strings throughout the database and API. The browser formats them with `BigInt`, without rounding through JavaScript numbers.

An operator can submit an **already completed** transaction using `POST /api/admin/token/burns`. This is a local evidence write, not a blockchain transaction. It accepts only a signature; clients cannot choose the mint or declare the burn amount.

```bash
# Configure these privately. BASE_URL is the origin without a trailing slash.
: "${BASE_URL:?Set the deployed origin}"
: "${ADMIN_API_KEY:?Set the separate operator credential}"
curl --fail-with-body --retry 0 "$BASE_URL/api/admin/token/burns" \
  -H "Origin: $BASE_URL" \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @burn-receipt.json
```

`burn-receipt.json` contains `{"signature":"THE_FINALIZED_TRANSACTION_SIGNATURE"}`. Do not use a seed, private key, or OpenBroker credential. The endpoint requires the separate operator credential and an exact matching Origin, limits verification attempts, and returns `transactions_sent: 0` and `credits_issued: 0`.

## What is checked

The verifier checks mainnet genesis identity, successful finalized signature status, a matching transaction signature and slot, supported legacy/v0 transaction metadata, the configured mint's token program and decimals, and a finalized mint snapshot at least as recent as the transaction. It parses ordinary `Burn` and `BurnChecked` instructions from the original Token Program or Token-2022, including inner instructions. Missing instruction metadata, unknown token-program instruction encodings, pending/failed transactions, wrong mints, and transfers to other addresses are rejected rather than treated as burns.

Evidence is stored separately from customer allowance and business cash ledgers. The mainnet/mint/signature tuple is unique. Repeating identical evidence does not add to totals; conflicting evidence cannot replace a recorded transaction. Amounts are summed exactly in Python rather than SQLite floating-point aggregation.

## What this does not prove

The source of trust is the operator-configured RPC, not an independently operated validator. The receipt ledger covers submitted successful burns, **not complete historical burns**. Gross burned tokens are not net supply change: issuance can offset burns. The current mint snapshot is not historical pre/post supply proof for each receipt.

A burn does not establish its funding source, a treasury-owned buyback, creator-fee revenue, the legitimacy of any custody, or a right to user deposits. Mint and freeze authority fields are not a complete Token-2022 extension, delegate, vault, or program-upgrade audit. No lock, fee collection, swap, burn execution, or custody feature is enabled by these routes.

Sources: [Solana burn instructions](https://solana.com/docs/tokens/basics/burn-tokens), [signature status](https://solana.com/docs/rpc/http/getsignaturestatuses), [transaction RPC](https://solana.com/docs/rpc/http/gettransaction), and [JSON structures](https://solana.com/docs/rpc/json-structures).

## Verification

Run the existing full `sh scripts/verify.sh` release gate. New Python, JavaScript and browser tests cover receipt parsing, finality, duplicates, amount precision, credential isolation, route ordering, authentication, failed/empty refreshes and responsive layout. All supplied chain data is a fixture. A browser runner that explicitly blocks localhost records an offline inlined render test instead of claiming native HTTP acceptance. Real RPC verification and live deployment acceptance remain separate.
