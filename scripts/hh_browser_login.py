#!/usr/bin/env python3
"""Headed Playwright login: save storage_state JSON for HH UI apply.

Run from project root with the venv activated:
  python scripts/hh_browser_login.py

After login in the opened window, press Enter. The file ``hh_browser_storage_state.json``
is written to the project root. Encrypt its contents with ``HhTokenCipher`` using
``HH_TOKEN_ENCRYPTION_KEY`` and store in ``hh_linked_accounts.browser_storage_enc``
(see README).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install playwright: pip install playwright && playwright install chromium", file=sys.stderr)
        return 1

    root = Path(__file__).resolve().parent.parent
    out = root / "hh_browser_storage_state.json"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://hh.ru/account/login", wait_until="domcontentloaded")
        input("Log in to hh.ru in the browser window, then press Enter here... ")
        state = context.storage_state()
        browser.close()

    out.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {out}")
    print("Next: encrypt JSON with HH_TOKEN_ENCRYPTION_KEY and set hh_linked_accounts.browser_storage_enc.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
