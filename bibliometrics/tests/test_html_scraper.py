from __future__ import annotations

import json
from pathlib import Path

from clamps_biblio.html_scraper import load_playwright_cookies


def test_load_playwright_cookies_from_json(tmp_path: Path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text(
        json.dumps(
            [
                {
                    "name": "JSESSIONID",
                    "value": "abc123",
                    "domain": "journals.ametsoc.org",
                    "path": "/",
                }
            ]
        ),
        encoding="utf-8",
    )
    cookies = load_playwright_cookies(cookie_file)
    assert len(cookies) == 1
    assert cookies[0]["name"] == "JSESSIONID"
    assert cookies[0]["domain"].startswith(".")


def test_load_playwright_cookies_from_header_file(tmp_path: Path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("JSESSIONID=abc123; cf_clearance=xyz\n", encoding="utf-8")
    cookies = load_playwright_cookies(cookie_file)
    assert len(cookies) == 2
    assert all(cookie["domain"] == ".ametsoc.org" for cookie in cookies)
