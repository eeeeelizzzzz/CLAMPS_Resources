from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf
import requests


@dataclass
class TextMention:
    pattern: str
    page: int
    context: str


def compile_literal_patterns(strings: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    """Compile fixed strings (e.g. DOIs) as case-insensitive literal regex."""
    return [(s, re.compile(re.escape(s), re.IGNORECASE)) for s in strings if s]


def compile_patterns(patterns: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    compiled = []
    for pattern in patterns:
        compiled.append((pattern, re.compile(pattern, re.IGNORECASE)))
    return compiled


def extract_context(text: str, match: re.Match[str], window: int = 120) -> str:
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    snippet = text[start:end].replace("\n", " ")
    return re.sub(r"\s+", " ", snippet).strip()


def scan_text(text: str, compiled_patterns: list[tuple[str, re.Pattern[str]]]) -> list[TextMention]:
    mentions: list[TextMention] = []
    seen: set[tuple[str, str]] = set()
    for pattern_label, regex in compiled_patterns:
        for match in regex.finditer(text):
            context = extract_context(text, match)
            key = (pattern_label, context)
            if key in seen:
                continue
            seen.add(key)
            mentions.append(TextMention(pattern=pattern_label, page=0, context=context))
    return mentions


def load_cookie_header(path: Path) -> str:
    """Read Cookie header(s) from file; merges multiple lines (e.g. AMS + MDPI)."""
    parts: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            parts.append(line.removeprefix("Cookie:").strip())
    if not parts:
        return ""

    merged: dict[str, str] = {}
    for part in parts:
        for pair in part.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            name, value = pair.split("=", 1)
            merged[name.strip()] = value.strip()
    return "; ".join(f"{name}={value}" for name, value in merged.items())


def make_session(cookie_header: str | None = None) -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    if cookie_header:
        session.headers["Cookie"] = cookie_header
    return session


def scan_pdf_bytes(
    pdf_bytes: bytes,
    compiled_patterns: list[tuple[str, re.Pattern[str]]],
) -> list[TextMention]:
    doc = pymupdf.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    mentions: list[TextMention] = []
    seen: set[tuple[int, str, str]] = set()

    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        for pattern_label, regex in compiled_patterns:
            for match in regex.finditer(text):
                context = extract_context(text, match)
                key = (page_num, pattern_label, context)
                if key in seen:
                    continue
                seen.add(key)
                mentions.append(TextMention(pattern=pattern_label, page=page_num, context=context))
    return mentions


from clamps_biblio.pdf_resolver import AMS_DOI_PDF_RE, extract_pdf_links_from_html


def fetch_pdf_bytes(
    pdf_url: str,
    session: requests.Session,
    timeout: int = 30,
) -> bytes:
    """Download PDF bytes, following common publisher HTML wrappers."""
    tried: set[str] = set()
    queue = [pdf_url]
    last_response: requests.Response | None = None

    if AMS_DOI_PDF_RE.search(pdf_url):
        doi = pdf_url.rsplit("/doi/pdf/", 1)[-1]
        queue.insert(0, f"https://journals.ametsoc.org/doi/{doi}")

    while queue:
        url = queue.pop(0)
        if url in tried:
            continue
        tried.add(url)

        if "mdpi.com" in url.lower():
            landing = url.split("/pdf", 1)[0]
            session.headers.setdefault("Referer", landing)
            try:
                session.get(landing, timeout=timeout, allow_redirects=True)
            except requests.RequestException:
                pass

        response = session.get(url, timeout=timeout, allow_redirects=True)
        if response.status_code == 403 and "mdpi.com" in url.lower():
            raise ValueError(
                f"403 Forbidden from MDPI ({url}). "
                "MDPI blocks scripted downloads — open the article in a browser, copy the "
                "Cookie header from DevTools into --cookies-file (same format as AMS), then re-run."
            )
        response.raise_for_status()
        last_response = response
        content = response.content
        if content.startswith(b"%PDF"):
            return content

        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type and not content.lstrip().startswith(b"<!"):
            continue

        for alt in extract_pdf_links_from_html(response.text, response.url):
            if alt not in tried:
                queue.append(alt)

    if last_response is None:
        raise ValueError(f"Could not download PDF from {pdf_url}")
    raise ValueError(
        f"Response is not a PDF ({last_response.status_code}, {len(last_response.content)} bytes, "
        f"{last_response.headers.get('content-type', 'unknown')}). "
        "Publisher returned HTML — AMS papers need fresh --cookies-file; "
        "Copernicus discussion comments may have no PDF."
    )


def scan_pdf_file(
    pdf_path: Path,
    compiled_patterns: list[tuple[str, re.Pattern[str]]],
) -> list[TextMention]:
    return scan_pdf_bytes(pdf_path.read_bytes(), compiled_patterns)


def scan_pdf_url(
    pdf_url: str,
    compiled_patterns: list[tuple[str, re.Pattern[str]]],
    timeout: int = 30,
    session: requests.Session | None = None,
) -> list[TextMention]:
    client = session or make_session()
    pdf_bytes = fetch_pdf_bytes(pdf_url, client, timeout=timeout)
    return scan_pdf_bytes(pdf_bytes, compiled_patterns)
