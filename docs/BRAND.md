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
- The original `public/assets/holdbyte-hero.webp` remains available for existing
  consumers. It is transparent and 1,254 × 1,254 pixels. Declare image dimensions
  in markup to avoid layout shifts.
- The October workspace refresh uses `public/assets/holdbyte-relay.png` for the
  new hero and `public/assets/holdbyte-sprites.png` for the four-state mascot
  atlas. Both are original transparent images derived from the established
  mascot. Keep the earlier WebP for existing consumers. The sprite order is
  idle, thinking, key-ready and resting in a two-by-two grid.
- Use system fonts; do not add a remote font/icon dependency just for branding.
- Prefer concrete actions such as **Open workspace**, **Connect wallet**, **Send**, and **Start new chat**.
- Avoid invented user counts, unlimited-use claims, price predictions and vague performance claims.

The official token link is derived from the configured mint and appears only when `TOKEN_LAUNCHED=true`. Verify the listing before enabling it. A holding does not guarantee service capacity. Keep provider, funding and control details accessible from Help, Funding and Terms.

## Illustration source

The current hero is an original generated asset encoded as WebP. Its retained art direction is: a compact acid-lime pocket-computer mascot with a charcoal face, lavender pixel eyes and a small metallic membership-token companion; premium industrial-design materials, transparent background, no existing-company logos, price imagery, charts, rockets or text.

## October 2026 asset refresh

The relay and sprite atlas were generated with the built-in imagegen tool,
using the original WebP as the mascot reference. The PNGs preserve transparency
and are committed alongside the site. Only the idle and thinking atlas cells
are currently used; the key-ready and resting cells are available for later UI
states. Do not imply that a mascot animation proves provider availability.

### Relay hero prompt

> Use case: stylized-concept. Asset type: production website hero cutout for
> Holdbyte, a Solana wallet-gated AI developer service. The attached image is
> the established mascot reference. Create a NEW scene preserving this mascot
> identity: premium little acid-lime rounded pocket-computer body, black inset
> glass face, two lavender pixel eyes, subtle industrial-design seams. Show the
> device in an attractive three-quarter view floating gently above a small
> brushed-metal rounded platform, accompanied by a small metallic square
> access-token charm and two compact lavender translucent compute modules,
> connected visually with short precise luminous lime paths. Cohesive
> sophisticated miniature product photography / 3D render, tactile plastics and
> anodized metal, restrained not noisy. Layout square 1024x1024 with every object
> fully visible and 10% breathing room all sides. Hero has a clear big silhouette
> and remains legible at 400px. Crisp excellent materials, softly lit, realistic
> delicate contact shadow. Actual transparent background with alpha, no
> background plate, no text or letters, no logos of other companies, no price
> charts or rockets. Designed to sit on a very dark graphite website panel.

### Mascot sprite prompt

> Use case: stylized-concept. Asset type: UI mascot sprite atlas for the Holdbyte
> AI website. Use the attached existing acid-lime pocket-computer mascot as
> reference and preserve its lime rounded shell, black inset glass face and
> exactly two lavender pixel eyes. Create one transparent 1024x1024 sprite atlas
> arranged in an EXACT evenly spaced 2 by 2 grid. Each cell is exactly half the
> canvas, contains one entire same small mascot, centered at the cell center
> with generous padding. Top-left: friendly idle mascot upright. Top-right:
> same mascot thinking, tilted 10 degrees, three small lavender dots above it.
> Bottom-left: same mascot happily presenting a tiny brushed silver key with
> lime detail. Bottom-right: same mascot resting, lavender eye pixels closed
> into two short lines. Premium playful industrial-design 3D render, consistent
> orthographic three-quarter camera and size in all four cells,
> lime/graphite/lavender only with silver accents. All separate objects stay
> well inside their own quadrant, do not touch or overlap adjacent cells. Actual
> transparent background with alpha. No grid lines, no text, no cell labels, no
> border, no floating background slabs. Keep each pose discernible at 100px.
> Production-ready distinct status sprites.
