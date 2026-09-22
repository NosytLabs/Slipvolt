#!/bin/sh
# Install requirements-dev.txt and Chromium. No paid services used.
set -eu
cd "$(dirname "$0")/.."
python -m pytest -q
node --test tests/*.test.cjs
node --check public/chart.js
node --check public/request-tools.js
node --check public/launch-tools.js
node --check public/status/app.js
node --check public/app.js
node --check public/admin/app.js
node --check public/admin/connections.js
node --check public/core.js
node --check public/request-examples.js
node --check public/account-tools.js
node --check public/admin/readiness.js
node --check operator/profit-core.js
node --check operator/calculate.cjs
python -m compileall -q gridraft
python scripts/check_holder_ui.py
python scripts/check_admin_ui.py
python scripts/check_status_ui.py
python scripts/check_content_ui.py
python scripts/package_preview.py slipvolt-preview.html
