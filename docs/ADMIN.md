# Admin console

Run the server and open `/admin/`. The console uses a dedicated `ADMIN_API_KEY`; it never accepts the OpenBroker key in the browser. In production use a long random secret, HTTPS and separate operator access controls at the reverse proxy as defense in depth.

## What the console controls

- OpenBroker spendable balance and selectable 7/30/90-day provider usage/cost.
- Native-GNK holder allowance pool: allocated, spent, held/reconciliation state, funded AI-token capacity and full-allowance member-days.
- Provider/model health and capacity from OpenBroker's public status feed.
- Wallet and global RPM/concurrency plus the conservative ngonka-per-AI-token reservation factor.
- Holder and global daily AI-token allowance.
- Default/hard output limits (hard upper bound remains Gonka's advertised 16,384).
- Planned input/output metered pricing.
- Maintenance mode.
- Wallet search, user disable/enable, optional per-wallet daily token overrides, API-key inspection and immediate revocation.
- Recent holder requests and uncertain reservations.
- Actual business ledger entries: creator fees/API revenue/subscriptions and expenses including hosting/RPC/support/refunds/tax/developer payouts/GNK purchases.
- Cash ledger net, configured-rate compute contribution reference, and approximate OpenBroker runway at recent provider spend.
- Operator audit log for config, user, key, funding and business-ledger changes.

## GNK fund accounting

`POST /api/admin/allowance/fund` does **not transfer cryptocurrency**. It only allocates GNK that the operator confirms is already credited to the dedicated OpenBroker account, and refuses a local allocation above the current spendable provider balance.

Keep three things separate:

1. self-custody native GNK treasury,
2. spendable native-GNK balance inside the dedicated OpenBroker account,
3. local allowance accounting available to Slipvolt holders.

Do not count the same GNK twice.

## Cash/profit ledger

Business entries are manual, auditable records. Positive amounts are revenue/cash inflow; negative amounts are costs/outflows. The console never infers token market cap as revenue and never treats unclaimed creator fees as collected cash.

The dashboard is operational accounting, **not formal bookkeeping or tax accounting**.


## Connections and credential handling

The master admin credential stays in JavaScript memory only and is cleared from its password field after authentication. Refresh/lock requires entering it again. It is not stored in localStorage/sessionStorage. This does not replace HTTPS, operator-only reverse-proxy access and independent authentication review.

Connections reports configured/not-configured states without returning credentialed URLs. Read-only buttons check mainnet identity/health and priority-fee recommendations. Quote preview accepts SOL or the configured project token and exposes only sanitized indicative USDC amounts. Invalid quotes fail closed; editing input invalidates the displayed quote. No transaction or credit is created.

RPC/WSS keys and installed Metis API bases belong in server configuration, never in this console. WSS and 0x are not active adapters. See [QuickNode setup](QUICKNODE.md).

A missing provider cost appears as **Unavailable**, not zero. Configured-price usage value is labeled as modeled value, not collected revenue. Provider usage summaries can omit epoch adjustment lines: reconcile full account movements before formal financial decisions. GNK allocation retries with the same reference/amount are idempotent; a different amount on an existing reference is rejected. Per-wallet allowance overrides now affect actual admission, not just displayed entitlement.
