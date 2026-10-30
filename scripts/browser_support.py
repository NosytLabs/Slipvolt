"""Shared Chromium startup for offline browser checks; not a runtime dependency."""
import os
from pathlib import Path


def launch_chromium(playwright):
    executable = os.getenv('CHROMIUM_PATH') or (
        '/usr/bin/chromium' if Path('/usr/bin/chromium').exists()
        else playwright.chromium.executable_path)
    return playwright.chromium.launch(
        executable_path=executable, headless=True, args=['--no-sandbox'])
