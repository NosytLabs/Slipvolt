# Functional UX and setup repair — September 21, 2026

Target: NosytLabs/Slipvolt main fe1d1467fda6a5500f8411f031ef9601fde25a38.
Preserve existing token economics, rates, current catalog, key prefixes, accounting,
private configuration and manual-only CI. Patch only verified matching source files;
do not replace the newer customer guides from an older archive.

1. Reproduce and fix inherited HTTP credentials, redirect following, stale health,
   mutable cached totals and omitted Docker diagnostics.
2. Add an authenticated request preflight sharing admission checks with dispatch;
   never create a reservation, issue a key or send prompts to a provider.
3. Add local setup doctor: no network, DB creation, secret output or automatic fixes.
4. Add real status/guide pages and integrate Check request, prompt presets,
   connection details and a reviewed, allowlisted support report into the current UI.
5. Verify Python and JS suites, HTTP routing and browser interaction; publish patch,
   source changes, previews and evidence with exact limits on what was tested.
