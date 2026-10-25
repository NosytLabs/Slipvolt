# Treasury burn preparation

`/admin/burns/` prepares an **unsigned instruction** and verifies already-completed burn receipts. It does not sign, broadcast, swap, collect fees, accept deposits, or change AI allowances. The existing public evidence page remains `/token/`.

## Enable preparation

Set `SOLANA_TREASURY_OWNER` to the project treasury's **public Solana authority address**, alongside `HOLDER_MINT`, `HOLDER_TOKEN_DECIMALS`, `SOLANA_RPC_URL`, `ADMIN_API_KEY`, and the existing application origin. Use the production `gridraft.main:app` entry point. Empty treasury configuration disables preparation. Never put a treasury private key or seed phrase in this app.

The authority must be a system-owned, zero-data wallet or vault PDA. Native SPL multisig accounts are not supported by this initial planner. A vault PDA requires its separately approved external executor; a PDA cannot directly sign a wallet transaction. Treasury identity, signers, administrative powers and custody policies must be disclosed independently.

## Operator flow

1. Open **Treasury burns** from the operator console. Enter the separate admin API credential; it stays in memory in that tab, not web storage.
2. Enter the source **token account** and a positive decimal amount in human token units. Confirm the tokens belong to the project, not users or refundable lock positions.
3. Review mint, source, authority, program, exact amount, finalized snapshot slot, and warnings. The server reads all three accounts in a single `getMultipleAccounts` finalized response. No plan is cached or treated as an actual burn.
4. Download instruction JSON and review it in an external signing workflow. This JSON is not a serialized transaction, a generic multisig import format, an approval, or a signature. Construct the transaction with a current blockhash and a fee payer, verify the exact instruction/accounts, then simulate before obtaining the required approval and signatures. The application does not perform these steps.
5. After an independently executed burn finalizes, submit its signature under **Record a completed burn**. This invokes the existing finalized receipt verifier. Existing receipts are not counted twice.

Edits, key changes and Lock clear stale review data. A 60-second local review timer prevents exporting an aged proposal through the page; it is advisory, **not on-chain expiry or replay protection**. Downloaded instructions can be reused externally, so the signing system must enforce its own intent, nonce, fresh-state and approval rules. Aborting receipt verification may not prevent a database record already being written; check `/token/` before retrying.

## API

- `GET /api/admin/treasury`: authenticated configuration, no RPC calls. Returns the configured public mint/authority, planning readiness, and disabled execution/signing flags.
- `POST /api/admin/treasury/burn-plan`: admin bearer credential plus exact same-origin header. Body: `source_account`, decimal-string `amount`, and strict boolean `confirm_project_owned: true`. Caller-selected mints, authorities, programs, signing keys or extra fields are rejected.
- `POST /api/admin/token/burns`: existing receipt verification, unchanged.

Preparation accepts only `getGenesisHash` and `getMultipleAccounts` reads. It constructs a standard `BurnChecked` instruction: discriminator 15, u64 little-endian raw amount, decimals byte; writable source and mint; readonly signer authority. It emits no transaction, recent blockhash, signature, AI credit or ledger revenue.

## Conservative token coverage

Original SPL Token and Token-2022 base layouts are supported. Token-2022 mint extensions are limited to MetadataPointer and well-formed TokenMetadata; token accounts may have ImmutableOwner. Unknown/duplicate/truncated extensions, extra behavior such as transfer fees, permanent delegates, hooks, confidential balances, scaled amounts, pause/permissioned-burn settings, native/wrapped-SOL accounts, frozen or delegated sources, mismatched mint/owner/program/precision, and insufficient balances fail closed. This is intentionally narrower than all valid Token-2022 mints. Metadata is never fetched from its external URI.

Amount arithmetic is integer/string-only. A remaining mint authority is disclosed because new issuance can offset burns. Proposed post-burn balances assume no intervening activity; they are not measurements of a completed burn.

## Boundaries and research

RPC responses are trusted as data from the configured node, not independently proven by a validator. RPC authority ownership and operator confirmation do **not** establish legal ownership or provenance of funds. Never co-mingle user lock principal with treasury funds.

A future creator-fee policy can reserve funds for operations and compute, then approve a surplus buyback/burn budget. This planner does not claim or spend any trading fees. Pump's current create_v2 uses Token-2022, so token-program identity cannot be inferred from a ticker or assumed to be the original SPL program. StockLaunch was not verified as an operational dependency in this pass.

Primary references checked October 24, 2026:
- https://solana.com/docs/tokens/basics/burn-tokens
- https://solana.com/docs/rpc/http/getmultipleaccounts
- https://github.com/solana-program/token/blob/main/interface/src/instruction.rs
- https://github.com/solana-program/token/blob/main/interface/src/state.rs
- https://github.com/solana-program/token-2022/blob/main/interface/src/extension/mod.rs
- https://github.com/pump-fun/pump-public-docs/blob/main/docs/instructions/COIN_CREATION.md
- https://pump.fun/docs/fees
- https://pump.fun/docs/tokenized-agent-disclaimer

The existing model policy is unchanged: OpenBroker documents model IDs but not a numeric account-specific hard output ceiling; Gonka gateway default caps are configurable. Host documentation uses 180K context for MiniMax and 400K for DeepSeek/GLM. Native model capacity, host configuration, broker route limits and local allowance budgets are distinct. Paid boundary tests were not run. See API-POLICY.md and issue #17.

The custom lock vault and cross-wallet allowance-reuse protection remain unimplemented. This feature does not make a token launch or custodial staking service production-ready.
