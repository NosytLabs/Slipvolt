#!/bin/sh
# Requires requirements-dev.txt and Chromium to be installed. No paid services used.
set -eu
cd "$(dirname "$0")/.."
python -m pytest -q
node --test tests/*.test.cjs
find public operator -type f \( -name '*.js' -o -name '*.cjs' \) -print | sort | while IFS= read -r file; do
  node --check "$file"
done
python -m compileall -q gridraft scripts
python scripts/check_holder_ui.py
python scripts/check_admin_ui.py
python scripts/check_status_ui.py
python scripts/check_content_ui.py
python scripts/check_holder_economics_ui.py
python scripts/package_preview.py slipvolt-preview.html
