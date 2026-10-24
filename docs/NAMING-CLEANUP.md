# Holdbyte naming and content migration checklist

Public brand: **Holdbyte**. Technical repository remains `NosytLabs/Slipvolt` until a separately tested migration. Existing `sv_` keys, `gridraft_session` cookies, database paths, and `SLIPVOLT_*` integrations must keep working.

## Naming rules

- Customer-facing site name, navigation, page titles, alt text, screenshots, download names and support copy: **Holdbyte**.
- Provider descriptions: **OpenBroker** as the routing provider, **Gonka** as the model network. Do not imply Holdbyte created or exclusively operates those models.
- Token ticker: **HBYTE** is only a proposal; never call it the verified token. Show the full verified mint address when configured.
- `holdbyte.ai` is a proposed domain, not an owned or deployed domain. Do not publish a fake production URL.
- Technical identifiers may retain `Slipvolt`/`gridraft` during the compatibility window. Mark them explicitly as legacy in documentation.

## Content and functionality acceptance

- [ ] Search all tracked text/assets for Slipvolt, Gridraft, `sv_`, `SLIPVOLT`, stale dates, placeholder URLs, broken anchors and duplicated copy. Classify compatibility references before changing them.
- [ ] Introduce documented `HOLDBYTE_API_KEY` and `HOLDBYTE_BASE_URL` examples with tested fallback to legacy environment names; never invalidate existing keys.
- [ ] Update CSV names, support-report labels, browser titles and accessibility text without changing API response fields used by clients.
- [ ] Verify desktop/mobile layout, keyboard navigation, wallet connect/disconnect, model selection, chat continuation, downloads, and empty/error states.
- [ ] Keep Help, Developers, Funding, Privacy, Terms, Status and Admin content accurate and mutually consistent. No invented fees, burns, holder counts, uptime, or live token claims.
- [ ] Include public launch disclosures: official mint, threshold, daily allowance/reset, fair-use limits, operator contact, custody/admin authority, actual creator-fee allocation, and processor disclosure. Display “not published” until verified.
- [ ] Run `sh scripts/verify.sh`, inspect browser screenshots and accessibility, and use a PR with passing CI before merge.

## Unbuilt launch features

Allowance-period token lock, automated fee ingestion, on-chain buyback/burn, swaps, and live account-specific output-boundary testing are **not implemented**. Track them in issues #16–#19; do not market them as live.

## Release safeguards

No mainnet mint creation, custody transfers, developer sweep powers, buyback or swap transactions, domain purchases, or production deployment during a naming-only cleanup. Publish the operator's custody powers clearly if a future staking design grants any such powers.
