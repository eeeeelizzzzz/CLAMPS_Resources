"""Channel A phrase matching and metadata checks."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from clamps_biblio.channel_config import load_discovery_channels

DEFAULT_CHANNEL_A_PHRASES: tuple[str, ...] = (
    "CLAMPS-1",
    "CLAMPS-2",
    "CLAMPS 1",
    "CLAMPS 2",
    "CLAMPS1",
    "CLAMPS2",
    "Collaborative Lower Atmospheric Mobile Profiling System",
    "NSSL mobile profiling",
    "NSSL mobile profiler",
    "NSSL profiling",
    "Mobile PISA",
)

FACILITY_PHRASE_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"CLAMPS-1", "CLAMPS 1", "CLAMPS1"}),
    frozenset({"CLAMPS-2", "CLAMPS 2", "CLAMPS2"}),
)

METEOROLOGY_CHANNEL_A_KEYWORDS: tuple[str, ...] = (
    "atmospheric",
    "meteorolog",
    "boundary layer",
    "convection",
    "tornado",
    "lidar",
    "profiler",
    "radiosonde",
    "aeri",
    "microwave radiometer",
    "nocturnal",
    "mesoscale",
    "wind profile",
    "planetary boundary",
    "severe storm",
    "field campaign",
    "nssl",
    "national severe storms",
)


def load_channel_a_phrases(path: Path | None = None) -> list[str]:
    cfg = load_discovery_channels(path)
    phrases = cfg.get("channels", {}).get("A", {}).get("phrases") or []
    return list(phrases) if phrases else list(DEFAULT_CHANNEL_A_PHRASES)


def channel_a_query_phrase(discovery_source: str) -> str:
    src = str(discovery_source or "")
    if not src.startswith("channel_a:"):
        return ""
    return src.split(":", 1)[-1].strip()


def equivalent_phrases(phrase: str) -> list[str]:
    """Hyphen/space/case variants for CLAMPS-1/2 facility tokens."""
    for group in FACILITY_PHRASE_GROUPS:
        if phrase in group:
            return sorted(group)
    return [phrase]


@lru_cache(maxsize=64)
def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    """Match the complete query phrase only (not embedded substrings)."""
    text = phrase.strip()
    if not text:
        return re.compile(r"(?!x)x")
    escaped = re.escape(text)
    escaped = re.sub(r"\\\ ", r"\\s+", escaped)
    flags = 0 if text in {"CLAMPS1", "CLAMPS2"} else re.IGNORECASE
    return re.compile(rf"(?<!\w){escaped}(?!\w)", flags)


def phrase_in_text(text: str, phrase: str) -> bool:
    if not text or not phrase:
        return False
    return bool(_phrase_pattern(phrase).search(text))


def channel_a_metadata_text(row: dict[str, Any] | Any) -> str:
    get = row.get if hasattr(row, "get") else lambda k, d="": ""
    return " ".join(str(get(k, "") or "") for k in ("title", "abstract", "institutions", "topics"))


def has_channel_a_phrase_in_metadata(row: dict[str, Any] | Any, phrase: str | None = None) -> bool:
    """True when metadata contains the query phrase or a facility spelling alias."""
    if phrase is None:
        phrase = channel_a_query_phrase(str(row.get("discovery_source", "") if hasattr(row, "get") else ""))
    if not phrase:
        return False
    text = channel_a_metadata_text(row)
    return any(phrase_in_text(text, form) for form in equivalent_phrases(phrase))


def is_meteorology_channel_a_fallback(row: dict[str, Any] | Any) -> bool:
    """
    Retain Channel A OpenAlex hits with atmospheric metadata when the exact
    facility phrase is absent from stored title/abstract/institutions/topics.
    """
    from clamps_biblio.homophone_filters import homophone_reason

    if homophone_reason(row):
        return False
    text = channel_a_metadata_text(row).lower()
    if not text.strip():
        return False
    return any(keyword in text for keyword in METEOROLOGY_CHANNEL_A_KEYWORDS)


def passes_channel_a_filter(row: dict[str, Any] | Any) -> bool:
    """Step-4 Channel A retention: phrase (with aliases) or meteorology fallback."""
    return has_channel_a_phrase_in_metadata(row) or is_meteorology_channel_a_fallback(row)


def channel_a_retention_reason(row: dict[str, Any] | Any) -> str:
    if has_channel_a_phrase_in_metadata(row):
        phrase = channel_a_query_phrase(str(row.get("discovery_source", "") if hasattr(row, "get") else ""))
        text = channel_a_metadata_text(row)
        if phrase and phrase_in_text(text, phrase):
            return "phrase_exact"
        return "phrase_alias"
    if is_meteorology_channel_a_fallback(row):
        return "meteorology_fallback"
    return "rejected"


def matches_channel_a_phrase(row: dict[str, Any] | Any, phrase: str | None = None) -> bool:
    """Backward-compatible alias for phrase match including facility spelling variants."""
    return has_channel_a_phrase_in_metadata(row, phrase)


def matches_any_channel_a_phrase(row: dict[str, Any] | Any, phrases: list[str] | None = None) -> bool:
    if phrases is None:
        phrases = load_channel_a_phrases()
    text = channel_a_metadata_text(row)
    for phrase in phrases:
        if any(phrase_in_text(text, form) for form in equivalent_phrases(phrase)):
            return True
    return False
