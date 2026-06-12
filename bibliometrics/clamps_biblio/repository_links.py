"""NSSL/OU data repository URL patterns for PDF and metadata matching."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


def _normalize_link_entry(entry: str | dict[str, Any]) -> dict[str, str]:
    if isinstance(entry, str):
        return {"label": "NSSL data catalog", "url": entry.strip()}
    return {
        "label": str(entry.get("label", "NSSL data catalog")),
        "url": str(entry["url"]).strip(),
    }


def repository_search_phrases(links: list[str | dict[str, Any]]) -> list[str]:
    """OpenAlex search phrases derived from repository URLs."""
    phrases: list[str] = []
    seen: set[str] = set()
    for entry in links:
        url = _normalize_link_entry(entry)["url"]
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        candidates = [
            url,
            url.replace("https://", "").replace("http://", ""),
            f"{parsed.netloc}/{path}" if path else parsed.netloc,
        ]
        if path:
            # e.g. thredds/catalog/FRDD/CLAMPS
            candidates.append(path)
            if "FRDD/CLAMPS" in path:
                candidates.append("data.nssl.noaa.gov FRDD CLAMPS")
                candidates.append("FRDD/CLAMPS/clamps/clamps2")
                candidates.append("FRDD/CLAMPS/clamps/clamps1")
        for phrase in candidates:
            if phrase and phrase not in seen:
                seen.add(phrase)
                phrases.append(phrase)
    return phrases


def build_data_repository_patterns(
    links: list[str | dict[str, Any]],
) -> list[tuple[str, re.Pattern[str]]]:
    """Regex patterns for full URL and common shortened forms in PDF text."""
    patterns: list[tuple[str, re.Pattern[str]]] = []
    seen: set[str] = set()

    for entry in links:
        item = _normalize_link_entry(entry)
        label = item["label"]
        url = item["url"]
        parsed = urlparse(url)
        host = re.escape(parsed.netloc)
        path = parsed.path.rstrip("/")

        # Full URL (https optional; catalog.html optional)
        if path:
            path_re = re.escape(path.lstrip("/"))
            # Exact base catalog URL
            full = rf"https?://{host}/{path_re}(?:/catalog\.html)?"
            key = f"data_url:{label}"
            if key not in seen:
                seen.add(key)
                patterns.append((key, re.compile(full, re.IGNORECASE)))

            # Base URL with optional deeper path (e.g. .../FRDD/CLAMPS/clamps/clamps2/processed/...)
            if "FRDD/CLAMPS" in path:
                base_path = path.split("FRDD/CLAMPS")[0] + "FRDD/CLAMPS"
                base_re = re.escape(base_path.lstrip("/"))
                deep = rf"https?://{host}/{base_re}(?:/[^\s)>\]]+)?(?:/catalog\.html)?"
                key_deep = f"data_url:{label} (deep path)"
                if key_deep not in seen:
                    seen.add(key_deep)
                    patterns.append((key_deep, re.compile(deep, re.IGNORECASE)))

                # Domain + FRDD/CLAMPS (allows extra path segments after CLAMPS)
                fragment = rf"{host}[^\s]{{0,40}}FRDD/CLAMPS(?:/[^\s)>\]]+)?"
                key2 = f"data_url:{label} (short)"
                if key2 not in seen:
                    seen.add(key2)
                    patterns.append((key2, re.compile(fragment, re.IGNORECASE)))

                # Path fragment only (no domain — common in text references)
                path_only = r"FRDD/CLAMPS(?:/clamps/clamps[12])?(?:/processed)?"
                key3 = f"data_url:{label} (path fragment)"
                if key3 not in seen:
                    seen.add(key3)
                    patterns.append((key3, re.compile(path_only, re.IGNORECASE)))
            else:
                fragment = rf"{host}[^\s]{{0,80}}{re.escape(path.split('/')[-1])}"
                key2 = f"data_url:{label} (short)"
                if key2 not in seen:
                    seen.add(key2)
                    patterns.append((key2, re.compile(fragment, re.IGNORECASE)))

    return patterns


def repository_signals_in_text(
    text: str,
    links: list[str | dict[str, Any]],
) -> list[str]:
    return [label for label, pat in build_data_repository_patterns(links) if pat.search(text)]
