"""Homograph / false-positive filters for broad scan-pool inclusion."""

from __future__ import annotations

import re
from typing import Any

from clamps_biblio.clamps_signals import has_clamps_signal
from clamps_biblio.relevance import FALSE_POSITIVE_TITLE_KEYWORDS, metadata_text

HOMOGRAPH_TITLE = re.compile(
    r"\b(insulin|BCAA|glucose|diabetes|checkpoint signaling|pipe clamp|steel clamp|"
    r"vessel clamp|kolache|klobasnik|Drosophila|gastrulation|soybean|herbicid|"
    r"ptychograph|transposase|\bDNA\b|\bRNA\b|surgery|nursing|psycholog|"
    r"economics|education|archaeolog|bicycl|chatgpt|manufacturing|"
    r"willmore|torus knot|jones polynomial|atomic norm|reservoir model|"
    r"time-lapse gravity|dicamba|magnetism|foodways|czech cultural|"
    r"piezoelectric|contactless energy|inductive contactless)\b",
    re.I,
)

NON_MET_CLAMP = re.compile(
    r"\b(pipe|steel|vessel|surgical|wire|hose|inductive|contactless|mobile)\s+clamp",
    re.I,
)

# Channel B queries for the SCALES campaign collide with generic "scale/scales" in lidar literature.
SCALES_CAMPAIGN_SOURCE = re.compile(r":SCALES(?:\+|$)")
SCALES_CAMPAIGN_TOKEN = re.compile(r"\bSCALES\b")


def row_text(row: dict[str, Any] | Any) -> str:
    get = row.get if hasattr(row, "get") else lambda k, d="": ""
    return " ".join(
        str(get(k, "") or "")
        for k in ("title", "abstract", "institutions", "topics", "metadata_matched_terms")
    )


def is_scales_campaign_discovery(source: str) -> bool:
    return bool(SCALES_CAMPAIGN_SOURCE.search(str(source or "")))


def scales_homograph_reason(row: dict[str, Any] | Any) -> str:
    """Drop Channel B SCALES hits unless metadata carries CLAMPS or the SCALES acronym."""
    get = row.get if hasattr(row, "get") else lambda k, d="": ""
    source = str(get("discovery_source", "") or get("channel", "") or "")
    if not is_scales_campaign_discovery(source):
        return ""
    text = row_text(row)
    if has_clamps_signal(text) or SCALES_CAMPAIGN_TOKEN.search(text):
        return ""
    return "homograph:scales_campaign"


def homophone_reason(row: dict[str, Any] | Any) -> str:
    """Return a short reason if the row is an obvious homograph; else empty string."""
    get = row.get if hasattr(row, "get") else lambda k, d="": ""
    title = str(get("title", "") or "")
    title_lower = title.lower()
    text = row_text(row)

    scales_reason = scales_homograph_reason(row)
    if scales_reason:
        return scales_reason

    for kw in FALSE_POSITIVE_TITLE_KEYWORDS:
        if kw in title_lower:
            return f"homograph:title_keyword:{kw}"

    if HOMOGRAPH_TITLE.search(title):
        return "homograph:title_pattern"

    if NON_MET_CLAMP.search(title) and not has_clamps_signal(text):
        return "homograph:non-meteorology_clamp"

    # Bare "CLAMPS" substring homographs (e.g. contactless, clamps in biology)
    if re.search(r"\bclamps?\b", title_lower) and not has_clamps_signal(text):
        if re.search(r"cas12|hemophil|erythrocyte|insulin|graft|anastomos", title_lower):
            return "homograph:bare_clamps_token"

    return ""


def is_homophone(row: dict[str, Any] | Any) -> bool:
    return bool(homophone_reason(row))
