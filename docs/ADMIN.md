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


## Measured dashboard and settings

The overview uses only recorded data from the selected 7/30/90-day window:

- **Local usage** is settled Slipvolt holder traffic from the local native-GNK usage ledger, with explicit zero-usage UTC days.
- **Business cash flow** is realized entries from the manual business ledger; market cap, unclaimed creator fees and projected token volume are excluded.
- The public `/status/` chart uses sanitized OpenBroker public-registry requests and is labelled provider-wide, not Slipvolt traffic or uptime.

The top scorecard shows OpenBroker spendable GNK, local funded AI-token capacity, settled local tokens/requests, active wallets, unresolved reviews, provider cost and approximate runway. Missing upstream data renders as unavailable rather than zero.

Settings are grouped by traffic, allowance/funding, generation and reference economics. Editing a field marks the form **Unsaved changes**; **Discard** restores the last server-confirmed configuration. Browser validation catches obvious conflicts (default output <= hard output, shared daily allowance >= wallet allowance, global concurrency >= wallet concurrency) before the server performs authoritative validation.

Refresh failures are scoped: a failed overview clears the old overview and disables settings until a current snapshot loads; failures in users, requests or the audit log clear only that panel so stale rows are not left looking current.

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
