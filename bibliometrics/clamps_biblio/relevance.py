from __future__ import annotations

import re
from typing import Any

from clamps_biblio.channel_a import channel_a_metadata_text, passes_channel_a_filter
from clamps_biblio.channel_b import channel_b_ambiguous_needs_metadata_clamps, channel_b_metadata_confidence
from clamps_biblio.clamps_signals import has_clamps_signal, is_campaign_only_signal

METEOROLOGY_TOPIC_KEYWORDS = (
    "atmospheric",
    "meteorolog",
    "boundary layer",
    "aerosol",
    "weather",
    "climate",
    "lidar",
    "radiosonde",
    "convection",
    "tornado",
    "wind farm",
)

RELEVANT_INSTITUTION_KEYWORDS = (
    "national severe storms laboratory",
    "nssl",
    "cimms",
    "cooperative institute for mesoscale",
    "noaa",
    "school of meteorology",
    "atmospheric",
)

FALSE_POSITIVE_TITLE_KEYWORDS = (
    "cas12",
    "dna",
    "bicycl",
    "chatbot",
    "hemophil",
    "archaeolog",
    "copper circulation",
    "chatgpt",
    "manufacturing",
    "adhesion",
    "erythrocyte",
    "cremation",
    "paleontolog",
    "nursing",
    "psychological",
)


def metadata_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key, "") or "")
        for key in ("title", "institutions", "topics")
    )


def score_work(row: dict[str, Any]) -> tuple[int, str]:
    """Return (score, tier) where tier is high / medium / low."""
    score = 0
    source = str(row.get("discovery_source", ""))
    title = str(row.get("title", "")).lower()
    combined = metadata_text(row)
    topics = str(row.get("topics", "")).lower()

    if source.startswith("cites:"):
        score += 5

    if source.startswith(("dataset_cites:", "dataset_search:", "channel_c:")):
        score += 6

    if source.startswith(("campaign_clamps:", "channel_b:")):
        score += 5
        if has_clamps_signal(combined):
            score += 2
        meta_conf = channel_b_metadata_confidence(row, ambiguous_campaigns=None)
        if meta_conf == "campaign_plus_obs":
            score += 2
        elif meta_conf == "campaign_token":
            score += 1

    if source.startswith("channel_a:"):
        score += 5
        if has_clamps_signal(combined):
            score += 2

    if source.startswith(("channel_d:", "channel_e:", "channel_g:")):
        score += 4

    if source.startswith("channel_f:"):
        score += 5
        if has_clamps_signal(combined):
            score += 2

    if source.startswith(("channel_h:", "tier6_repo:")):
        score += 5
        if "campaign_candidate:" in source:
            score -= 2
        elif has_clamps_signal(combined):
            score += 2

    signals = has_clamps_signal(combined)
    if signals:
        score += 4

    if is_campaign_only_signal(combined):
        score -= 4

    for kw in METEOROLOGY_TOPIC_KEYWORDS:
        if kw in topics or kw in title:
            score += 1
            break

    for kw in RELEVANT_INSTITUTION_KEYWORDS:
        if kw in str(row.get("institutions", "")).lower():
            score += 1
            break

    for kw in FALSE_POSITIVE_TITLE_KEYWORDS:
        if kw in title:
            score -= 4
            break

    if source.startswith("search:") and not (
        has_clamps_signal(combined) or "data.nssl.noaa.gov" in combined.lower()
    ):
        score -= 3

    if score >= 6:
        tier = "high"
    elif score >= 3:
        tier = "medium"
    else:
        tier = "low"

    return score, tier


def qualifies_strict_high_confidence(
    row: dict[str, Any],
    ambiguous_campaigns: list[str] | None = None,
) -> bool:
    """Exclude weak keyword-only hits; trust compound campaign+CLAMPS queries."""
    tier = row.get("confidence_tier")
    if tier not in ("high", "medium"):
        return False

    source = str(row.get("discovery_source", ""))
    if source.startswith(("cites:", "dataset_cites:", "dataset_search:", "channel_c:", "channel_g:")):
        return True

    if source.startswith(("campaign_clamps:", "channel_b:")):
        from clamps_biblio.channel_b import passes_channel_b_metadata_screening

        if channel_b_ambiguous_needs_metadata_clamps(row, ambiguous_campaigns):
            return passes_channel_b_metadata_screening(row, ambiguous_campaigns)
        return True

    if source.startswith("channel_a:"):
        meta = channel_a_metadata_text(row)
        return passes_channel_a_filter(row) or "data.nssl.noaa.gov" in meta.lower()

    if "campaign_candidate:" in source:
        return False

    if source.startswith(("channel_f:", "channel_h:", "tier6_repo:")):
        meta = metadata_text(row)
        return has_clamps_signal(meta) or "data.nssl.noaa.gov" in meta.lower()

    meta = metadata_text(row)
    return has_clamps_signal(meta) or "data.nssl.noaa.gov" in meta.lower()
