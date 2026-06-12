"""Playwright-based HTML full-text scraper for AMS and open-access articles."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from clamps_biblio.text_scanner import TextMention, scan_text

# Per-publisher article body selectors (first match wins).
ARTICLE_SELECTORS: dict[str, tuple[str, ...]] = {
    "ams": ("article", "#pb-page-content", ".article__body", "[data-core-wrapper='article']"),
    "copernicus": ("#maincontent", "article", ".article-sections"),
    "wiley": ("article", "#section-main", ".article-section__content", "main"),
    "springer": ("article", "#main-content", "main", ".c-article-body"),
    "elsevier": ("article", "#body", "div.Body", "#articleBody"),
    "nature": ("article", "main", "#main-content", "div.c-article-body"),
    "mdpi": ("article", "#html-body", ".html-pub"),
    "plos": ("article", "#article-container", ".article-content"),
    "frontiers": ("article", ".JournalFullText", ".Body", "main"),
    "taylor_francis": ("article", ".hlFld-Fulltext", "#mainContent", "main"),
    "iop": ("article", "div.article-text", "main"),
    "ieee": ("article", "div.article", "main"),
    "aip": ("article", "main", "#article-body"),
    "acs": ("article", ".article_content-left", "main"),
    "cambridge": ("article", "#article-tab", "main"),
    "oxford": ("article", "#ContentColumn", "main"),
    "science": ("article", "main", "#content-block"),
    "sage": ("article", "main", "#body"),
    "bmc": ("article", "#main-content", "main"),
    "hindawi": ("article", ".article-content", "main"),
    "pnas": ("article", "main", "#article-content"),
    "royal_society": ("article", "main", "#content"),
    "rsc": ("article", ".article_control", "main"),
    "arxiv": ("article", "#content-inner", "main", "body"),
    "zenodo": ("article", ".record-container", "main", "#record-details"),
    "osti": ("article", "main", "#content"),
    "aiaa": ("article", "main", "#ContentTab"),
    "jove": ("article", "main", "#article-content"),
    "repository": ("article", "main", "#content"),
    "publisher_html": ("article", "main", "#content", "#maincontent"),
}

DEFAULT_SELECTORS = ("article", "main", "#content", "body")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def load_playwright_cookies(path: Path | None) -> list[dict[str, Any]]:
    """
    Load cookies for Playwright context.add_cookies().

    Supports:
    - JSON array (EditThisCookie / browser export)
    - Plain Cookie header file (ams_cookies.txt style) -> mapped to ametsoc.org
    """
    if not path or not path.exists():
        return []

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    if text.startswith("["):
        raw = json.loads(text)
        cookies: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict) or "name" not in item or "value" not in item:
                continue
            cookie = {
                "name": str(item["name"]),
                "value": str(item["value"]),
                "domain": str(item.get("domain") or ".ametsoc.org"),
                "path": str(item.get("path") or "/"),
            }
            if cookie["domain"] and not cookie["domain"].startswith("."):
                if "ametsoc" in cookie["domain"]:
                    cookie["domain"] = "." + cookie["domain"].lstrip(".")
            cookies.append(cookie)
        return cookies

    # Header format: merge lines, split on ';'
    parts: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            parts.append(line.removeprefix("Cookie:").strip())
    merged = "; ".join(parts)
    cookies = []
    for pair in merged.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        # AMS session cookies
        if any(
            name.startswith(prefix)
            for prefix in ("JSESSIONID", "cf_clearance", "aws-waf", "AWSALB", "HLApi", "_ga", "SaneID")
        ) or "ametsoc" in name.lower():
            domain = ".ametsoc.org"
        elif name.startswith("MDPI") or name.startswith("bm_"):
            domain = ".mdpi.com"
        else:
            domain = ".ametsoc.org"
        cookies.append(
            {"name": name, "value": value, "domain": domain, "path": "/"}
        )
    return cookies


async def extract_article_text(page: Any, publisher: str) -> str:
    selectors = ARTICLE_SELECTORS.get(publisher, DEFAULT_SELECTORS)
    for selector in selectors:
        locator = page.locator(selector)
        if await locator.count() > 0:
            text = await locator.first.inner_text()
            if text and len(text.strip()) > 200:
                return text
    return await page.locator("body").inner_text()


class AsyncHtmlScanSession:
    """Single shared headless Chromium browser with concurrent page workers."""

    def __init__(self, cookies: list[dict[str, Any]] | None = None, *, headless: bool = True):
        self._cookies = cookies or []
        self._headless = headless
        self._playwright = None
        self._browser = None
        self._context = None

    async def __aenter__(self) -> AsyncHtmlScanSession:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ImportError(
                "playwright is required for HTML scraping. "
                "Install with: pip install playwright && playwright install chromium"
            ) from exc

        self._playwright_cm = async_playwright()
        self._playwright = await self._playwright_cm.__aenter__()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context(user_agent=DEFAULT_USER_AGENT)
        if self._cookies:
            try:
                await self._context.add_cookies(self._cookies)
            except Exception:
                # Some exported cookies may be invalid; continue without them.
                pass
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright_cm:
            await self._playwright_cm.__aexit__(exc_type, exc_val, exc_tb)
            self._playwright_cm = None

    async def fetch_article_text(
        self,
        url: str,
        publisher: str,
        *,
        timeout_ms: int = 25000,
    ) -> str:
        page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # Springer/Elsevier/Nature keep polling; networkidle often never settles.
            if publisher in {"elsevier", "nature", "springer"}:
                try:
                    await page.wait_for_load_state("networkidle", timeout=timeout_ms)
                except Exception:
                    await page.wait_for_timeout(2000)
            else:
                await page.wait_for_timeout(1000)
            return await extract_article_text(page, publisher)
        finally:
            await page.close()

    async def scan_url(
        self,
        url: str,
        publisher: str,
        compiled_patterns: list,
        *,
        timeout_ms: int = 25000,
    ) -> list[TextMention]:
        text = await self.fetch_article_text(url, publisher, timeout_ms=timeout_ms)
        if not text or len(text.strip()) < 50:
            raise ValueError(f"Insufficient article text from {url}")
        return scan_text(text, compiled_patterns)


async def scan_urls_concurrent(
    session: AsyncHtmlScanSession,
    jobs: list[tuple[str, str]],
    compiled_patterns: list,
    *,
    concurrency: int = 4,
    timeout_ms: int = 25000,
) -> list[tuple[str, str, list[TextMention] | None, str | None]]:
    """
    Scan multiple (url, publisher) pairs with one browser and limited parallelism.

    Returns list of (url, publisher, mentions_or_none, error_or_none).
    """
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def worker(url: str, publisher: str) -> tuple[str, str, list[TextMention] | None, str | None]:
        async with semaphore:
            try:
                mentions = await session.scan_url(
                    url,
                    publisher,
                    compiled_patterns,
                    timeout_ms=timeout_ms,
                )
                return url, publisher, mentions, None
            except Exception as exc:
                return url, publisher, None, str(exc).split("\n")[0][:200]

    tasks = [asyncio.create_task(worker(url, publisher)) for url, publisher in jobs]
    return [await task for task in asyncio.as_completed(tasks)]


def cookie_header_to_playwright(path: Path) -> list[dict[str, Any]]:
    return load_playwright_cookies(path)
