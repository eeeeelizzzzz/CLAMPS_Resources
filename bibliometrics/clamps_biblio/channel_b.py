"""Channel B campaign compound-query helpers."""

from __future__ import annotations

import re
from typing import Any

from clamps_biblio.clamps_signals import has_clamps_signal
from clamps_biblio.field_campaigns import AMBIGUOUS_CAMPAIGN_CANONICAL, campaign_in_text

OBSERVATION_KEYWORD_PATTERN = re.compile(
    r"\b(?:observations?|profiles?|measurements?|retrievals?|soundings?|"
    r"boundary\s+layer|wind\s+profiles?|deployments?|"
    r"doppler\s+lidar|(?:remote\s+)?profiler|radiometer|aeri(?:oe)?|lidar)\b",
    re.I,
)

# B1/B3 OpenAlex queries include an explicit CLAMPS-1/CLAMPS-2 facility term.
FACILITY_QUERY_FAMILIES = frozenset({"B1", "B3"})


def _metadata_text(row: dict[str, Any] | Any) -> str:
    get = row.get if hasattr(row, "get") else lambda k, d="": ""
    return " ".join(str(get(k, "") or "") for k in ("title", "abstract", "institutions", "topics"))


def parse_channel_b_source(source: str) -> tuple[str, str, list[str]]:
    """
    Parse channel_b:B1:AWAKEN+CLAMPS-2+Doppler lidar
    -> (family='B1', campaign='AWAKEN', terms=['CLAMPS-2', 'Doppler lidar'])
    """
    src = str(source or "")
    if not src.startswith(("channel_b:", "campaign_clamps:")):
        return "", "", []

    label = src.split(":", 1)[1]
    if ":" in label:
        family, rest = label.split(":", 1)
    else:
        family, rest = "", label

    parts = rest.split("+")
    campaign = parts[0] if parts else ""
    terms = parts[1:] if len(parts) > 1 else []
    return family, campaign, terms


def channel_b_query_family(source: str) -> str:
    family, _, _ = parse_channel_b_source(source)
    return family


def channel_b_campaign(source: str) -> str:
    _, campaign, _ = parse_channel_b_source(source)
    return campaign


def channel_b_query_includes_facility(source: str) -> bool:
    """True when the discovery label is B1/B3 (query paired campaign with CLAMPS-1/2)."""
    return channel_b_query_family(source) in FACILITY_QUERY_FAMILIES


def has_observation_keyword(text: str) -> bool:
    return bool(OBSERVATION_KEYWORD_PATTERN.search(str(text or "")))


def channel_b_metadata_confidence(
    row: dict[str, Any] | Any,
    ambiguous_campaigns: list[str] | None,
) -> str:
    """
    Metadata support level for B2 + ambiguous campaign rows.

    Returns empty string when not applicable. Otherwise:
    - clamps_in_metadata — strongest
    - campaign_plus_obs — case-sensitive campaign token + observation keyword
    - campaign_token — case-sensitive campaign token only (retain, lower confidence)
    """
    if not channel_b_ambiguous_needs_metadata_clamps(row, ambiguous_campaigns):
        return ""
    text = _metadata_text(row)
    if has_clamps_signal(text):
        return "clamps_in_metadata"
    campaign = channel_b_campaign(
        str(row.get("discovery_source", "") or row.get("channel", "") or "")
    )
    if not campaign_in_text(text, campaign):
        return ""
    if has_observation_keyword(text):
        return "campaign_plus_obs"
    return "campaign_token"


def passes_channel_b_metadata_screening(
    row: dict[str, Any] | Any,
    ambiguous_campaigns: list[str] | None,
) -> bool:
    """B2 + ambiguous campaign: retain if CLAMPS or case-sensitive campaign token in metadata."""
    if not channel_b_ambiguous_needs_metadata_clamps(row, ambiguous_campaigns):
        return True
    return bool(channel_b_metadata_confidence(row, ambiguous_campaigns))


def channel_b_metadata_screening_reason(
    row: dict[str, Any] | Any,
    ambiguous_campaigns: list[str] | None,
) -> str:
    if passes_channel_b_metadata_screening(row, ambiguous_campaigns):
        return ""
    return "screening:ambiguous_b2_no_clamps_or_campaign_token"


def _ambiguous_campaign_set(ambiguous_campaigns: list[str] | None) -> frozenset[str]:
    if ambiguous_campaigns:
        return frozenset(ambiguous_campaigns)
    return AMBIGUOUS_CAMPAIGN_CANONICAL


def channel_b_ambiguous_needs_metadata_clamps(
    row: dict[str, Any] | Any,
    ambiguous_campaigns: list[str] | None,
) -> bool:
    """
    For ambiguous campaign names, B2 hits still need CLAMPS in metadata (or PDF).
    B1/B3 hits already matched a facility term in the OpenAlex query string.
    """
    get = row.get if hasattr(row, "get") else lambda k, d="": ""
    source = str(get("discovery_source", "") or get("channel", "") or "")
    if not source.startswith(("channel_b:", "campaign_clamps:")):
        return False
    campaign = channel_b_campaign(source)
    if campaign not in _ambiguous_campaign_set(ambiguous_campaigns):
        return False
    return not channel_b_query_includes_facility(source)
