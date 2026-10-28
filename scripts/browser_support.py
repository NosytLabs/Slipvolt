"""Shared Chromium setup for offline browser verification, not application code."""
import os
from pathlib import Path


def launch_chromium(playwright):
    """Honor an explicit browser, then system Chromium, then Playwright's install."""
    executable = os.getenv('CHROMIUM_PATH') or (
        '/usr/bin/chromium' if Path('/usr/bin/chromium').exists()
        else playwright.chromium.executable_path)
    return playwright.chromium.launch(
        executable_path=executable, headless=True, args=['--no-sandbox'])
