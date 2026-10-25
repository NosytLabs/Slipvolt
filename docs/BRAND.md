# Holdbyte

**Hold tokens. Use AI.**

Holdbyte is the customer-facing name. The canonical repository remains `NosytLabs/Slipvolt`; compatibility identifiers are deliberately stable until a separately tested migration.

## Naming rules

- Customer-facing product copy, page titles, navigation, accessibility text and support material use **Holdbyte**.
- Existing `sv_` keys, `gridraft_session` cookies, database names and `SLIPVOLT_*` environment variables remain supported.
- New client examples prefer `HOLDBYTE_API_KEY` and `HOLDBYTE_BASE_URL`.
- OpenBroker is the routing provider and Gonka is the model network. Do not imply Holdbyte created or exclusively operates those upstream models.
- `HBYTE` remains only a proposed ticker until an actual mint is published and verified.
- A configured mint is the source of truth for token links; never substitute a ticker or marketing name for the full mint address.

`SITE_NAME` controls the app/API display name and wallet sign-in message. A repository/package rename is intentionally out of scope because it would require coordinated API, cookie, database, deployment and client migration.

## Domain research

Registrar lookup through Vercel on **2026-10-24**, in USD:

| Domain | Result at lookup time | Registration term | Registration / renewal quote |
| --- | --- | --- | --- |
| `holdbyte.ai` | Available | 2 years | $160 / $160 |
| `getholdbyte.com` | Available | 1 year | $11.25 / $11.25 |
| `holdbyte.com` | Unavailable | — | — |

These are historical lookup results, not reservations or current availability. No domain was purchased or connected. Search checks did not establish trademark or ticker clearance.

## Identity

- Warm white `#F5F2E8`, charcoal `#151515`, lime `#C7FF5E`, and violet `#7867FF` for the interface. The illustrated mark uses the closely matched `#C9F564` / `#17211D` palette.
- Use `public/assets/brand-mark.svg` for the mark and `public/favicon.svg` for the browser icon.
- Use `public/assets/holdbyte-hero.webp` for the hero illustration. It has a transparent background and is 1,254 × 1,254 pixels. Declare dimensions in markup to avoid layout shifts.
- Use system fonts; do not add a remote font/icon dependency just for branding.
- Prefer concrete actions such as **Open workspace**, **Connect wallet**, **Send**, and **Start new chat**.
- Avoid invented user counts, unlimited-use claims, price predictions and vague performance claims.

The official token link is derived from the configured mint and appears only when `TOKEN_LAUNCHED=true`. Verify the listing before enabling it. A holding does not guarantee service capacity. Keep provider, funding and control details accessible from Help, Funding and Terms.

## Illustration source

The current hero is an original generated asset encoded as WebP. Its retained art direction is: a compact acid-lime pocket-computer mascot with a charcoal face, lavender pixel eyes and a small metallic membership-token companion; premium industrial-design materials, transparent background, no existing-company logos, price imagery, charts, rockets or text.
