# Developer compensation and operating surplus

This document is a policy proposal, not an activated payout instruction, holder right or earnings forecast. The application records business entries but does not claim creator fees, buy GNK, burn tokens or pay a developer.

The current technical and custody design lives in [TOKEN-DESIGN.md](TOKEN-DESIGN.md). That document controls when a more detailed example conflicts with this summary.

## Product boundary

Holder access remains simple: **hold → connect → create key → use a bounded funded allowance**. A project-token purchase is not service revenue, a GNK deposit, a treasury share or a claim on developer income. User lock principal and customer prepayments remain segregated obligations.

The founder or an explicitly disclosed project multisig may control earned project revenue after it has been received. That authority must be published. It must not include undisclosed withdrawal, burn, transfer or seizure power over tokens owned or locked by users.

## Revenue must be realized

Potential sources are:

- creator fees actually received by the project;
- service revenue earned under final customer terms;
- operator capital deliberately contributed to the project.

Market capitalization, reported trading volume, unclaimed fees, unsold team tokens, user lock principal and refundable customer obligations are not realized revenue. At zero eligible trading volume, creator-fee revenue is zero.

Keep separate records for stablecoin cash, native GNK inventory, OpenBroker prepaid credit and debits, customer obligations, user vault principal, operating expenses, creator fees, earned service revenue, retained capital and developer payments.

## Waterfall before optional distributions

For each accounting period:

1. Reconcile cash and tokens actually received.
2. Pay or accrue provider usage and epoch adjustments, GNK acquisition, hosting, RPC, support, swaps, gas, refunds, taxes and other liabilities.
3. Restore the approved provider working balance and operating/customer-obligation reserve.
4. Calculate distributable surplus only if the remainder is positive.
5. Apply a published optional allocation policy to that surplus.

The working scenario in `TOKEN-DESIGN.md` uses 10% for an optional treasury buyback-and-burn budget, 70% for a disclosed developer distribution and 20% retained capital. These are editable planning assumptions. They are not on-chain entitlements and every optional amount becomes zero when surplus is zero or negative.

A developer salary already recorded as an operating cost must not be paid again from the distribution percentage. A buyback budget is not a completed purchase or burn. Retained capital is not automatically a token purchase.

## Controls and disclosure

Before any distribution policy is presented publicly:

- identify the operator and every treasury, fee-recipient and multisig authority;
- publish team allocations, vesting and conflicts;
- define the reserve calculation and customer-obligation treatment;
- reconcile the dedicated OpenBroker account's full balance movement, including charges not present in a summary chart;
- establish bookkeeping, tax and jurisdiction-specific legal review;
- publish how policy changes are approved and announced.

Do not promise APY, token appreciation, trading volume, creator-fee income, buyback demand, profit participation or a minimum developer payment. Service access can be useful without turning the token into a claim on project revenue.

## Offline planning

`operator/holder-economics.html` is an offline scenario tool. Use actual collected fees and measured costs, and include zero-volume, high-utilization, higher-GNK-cost and reserve-restoration cases. Its output is planning evidence only; it cannot prepare, sign or authorize a transaction.
