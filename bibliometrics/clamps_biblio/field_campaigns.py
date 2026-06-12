"""Case-sensitive field campaign tokens and discovery exclusions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from clamps_biblio.channel_config import load_campaign_full_names

# Deployment / ops labels in clamps_deployments.csv — not OpenAlex discovery campaigns.
EXCLUDED_DISCOVERY_CAMPAIGN_KEYS = frozenset(
    {
        "dualdoppler",
        "mesonetnws",
        "nwcreadiness",
        "sgpmpd",
        "sgpmpdcompare",
    }
)

AMBIGUOUS_CAMPAIGN_CANONICAL = frozenset(
    {
        "PERiLS",
        "TRACER",
        "SPLASH",
        "SAIL",
        "AWAKEN",
    }
)


@dataclass(frozen=True)
class CampaignMatchSpec:
    canonical: str
    patterns: tuple[str, ...]
    aliases: tuple[str, ...] = ()


def _norm_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


CAMPAIGN_SPECS: tuple[CampaignMatchSpec, ...] = (
    CampaignMatchSpec("PECAN", (r"\bPECAN\b",)),
    CampaignMatchSpec("LAPSE-RATE", (r"\bLAPSE[-\s]RATE\b",)),
    CampaignMatchSpec(
        "VORTEX-SE",
        (r"\bVORTEX[-\s]SE\b",),
        aliases=("VORTEX SE",),
    ),
    CampaignMatchSpec(
        "VORTEX-USA",
        (r"\bVORTEX[-\s]USA\b",),
        aliases=("VORTEX USA",),
    ),
    CampaignMatchSpec("TORUS", (r"\bTORUS\b",)),
    CampaignMatchSpec("PERiLS", (r"\bPERiLS\b", r"\bPERILS\b"), aliases=("PERILS",)),
    CampaignMatchSpec("Perdigão", (r"\bPerdig[aã]o\b",), aliases=("Perdigao",)),
    CampaignMatchSpec("BLISSFUL", (r"\bBLISSFUL\b",)),
    CampaignMatchSpec(
        "mini-MPEX",
        (r"\b[Mm]ini[-\s]?MPEX\b",),
        aliases=("miniMPEX", "MiniMPEX", "mini-MPEX"),
    ),
    CampaignMatchSpec("LAFE", (r"\bLAFE\b",)),
    CampaignMatchSpec("CHEESEHEAD", (r"\bCHEESEHEAD(?:19|[-\s]?2019)?\b",)),
    CampaignMatchSpec("TRACER-AQ", (r"\bTRACER[-\s]?AQ\b",)),
    CampaignMatchSpec("TRACER", (r"\bTRACER\b",)),
    CampaignMatchSpec("ESCAPE", (r"\bESCAPE\b",)),
    CampaignMatchSpec("SPLASH-SAIL", (r"\bSPLASH[-\s]?SAIL\b",)),
    CampaignMatchSpec("SPLASH", (r"\bSPLASH\b",)),
    CampaignMatchSpec("SAIL", (r"\bSAIL\b",)),
    CampaignMatchSpec("AWAKEN", (r"\bAWAKEN\b",)),
    CampaignMatchSpec(
        "EPIC",
        (r"\bEPIC\b", r"\bEPIC[-\s]?[12]\b"),
        aliases=("EPIC-1", "EPIC-2", "EPIC 1", "EPIC 2"),
    ),
    CampaignMatchSpec("PBLTops", (r"\bBLTops\b", r"\bPBL-Tops\b")),
    CampaignMatchSpec("RIVoRS", (r"\bRIVoRS\b", r"\bRiVorS\b")),
    CampaignMatchSpec(
        "SCALES",
        (r"\bSCALES\b", r"\b[Mm]esoSCALES\b", r"\b[Mm]icroSCALES\b"),
    ),
    CampaignMatchSpec("WH2yMSIE", (r"\bWH2yMSIE\b", r"\bWHyMSIE\b")),
)


def _spec_by_canonical() -> dict[str, CampaignMatchSpec]:
    out: dict[str, CampaignMatchSpec] = {}
    for spec in CAMPAIGN_SPECS:
        out[spec.canonical] = spec
        for alias in spec.aliases:
            out[alias] = spec
    return out


SPEC_BY_NAME = _spec_by_canonical()

# Campaigns that only match when a companion campaign is also present.
CO_REQUIRED_CAMPAIGNS: dict[str, str] = {
    "SAIL": "SPLASH",
    "ESCAPE": "TRACER",
}

# Compound keys that require independent signals from each listed campaign.
REQUIRES_ALL_CAMPAIGNS: dict[str, tuple[str, ...]] = {
    "SPLASH-SAIL": ("SPLASH", "SAIL"),
}


def _normalize_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


@lru_cache(maxsize=1)
def _full_name_phrases_by_campaign() -> dict[str, tuple[str, ...]]:
    data = load_campaign_full_names()
    campaigns = data.get("campaigns") or {}
    out: dict[str, list[str]] = {}
    for name, meta in campaigns.items():
        if not isinstance(meta, dict):
            continue
        phrases = meta.get("full_names") or []
        if phrases:
            out[name] = [str(p) for p in phrases]
    return {k: tuple(v) for k, v in out.items()}


@lru_cache(maxsize=64)
def _compiled_patterns(canonical: str) -> tuple[re.Pattern[str], ...]:
    spec = SPEC_BY_NAME.get(canonical)
    if not spec:
        escaped = re.escape(canonical)
        return (re.compile(rf"(?<!\w){escaped}(?!\w)"),)
    return tuple(re.compile(p) for p in spec.patterns)


def is_excluded_discovery_campaign(name: str) -> bool:
    return _norm_key(name) in EXCLUDED_DISCOVERY_CAMPAIGN_KEYS


def discovery_campaign_items(campaigns: dict[str, Any]) -> list[tuple[str, Any]]:
    return [(name, meta) for name, meta in campaigns.items() if not is_excluded_discovery_campaign(name)]


def _canonical_name(campaign: str) -> str:
    spec = SPEC_BY_NAME.get(campaign)
    return spec.canonical if spec else campaign


def _short_token_match(text: str, canonical: str) -> bool:
    for pattern in _compiled_patterns(canonical):
        if pattern.search(text):
            return True
    return False


def _full_name_match(text: str, canonical: str) -> bool:
    phrases = _full_name_phrases_by_campaign().get(canonical)
    if not phrases:
        return False
    haystack = _normalize_phrase(text)
    return any(_normalize_phrase(phrase) in haystack for phrase in phrases)


def _campaign_signal(text: str, canonical: str, *, _stack: frozenset[str] | None = None) -> bool:
    """True when short token or approved full name matches for one campaign."""
    if not text:
        return False
    visiting = _stack or frozenset()
    if canonical in visiting:
        return False

    if canonical in REQUIRES_ALL_CAMPAIGNS:
        next_stack = visiting | {canonical}
        return all(
            _campaign_signal(text, part, _stack=next_stack)
            for part in REQUIRES_ALL_CAMPAIGNS[canonical]
        )

    co_required = CO_REQUIRED_CAMPAIGNS.get(canonical)
    if co_required:
        next_stack = visiting | {canonical}
        if not _campaign_signal(text, co_required, _stack=next_stack):
            return False

    return _short_token_match(text, canonical) or _full_name_match(text, canonical)


def campaign_in_text(text: str, campaign: str) -> bool:
    """Case-sensitive acronym match plus approved full-name phrases."""
    if not text or not campaign:
        return False
    return _campaign_signal(text, _canonical_name(campaign))


def campaigns_in_text(text: str, campaign_names: list[str] | None = None) -> list[str]:
    """Return canonical campaign names found in text (longest / specific first)."""
    if not text:
        return []
    names = campaign_names or [spec.canonical for spec in CAMPAIGN_SPECS]
    seen: set[str] = set()
    found: list[str] = []
    # Prefer longer names (TRACER-AQ before TRACER, SPLASH-SAIL before SPLASH).
    ordered = sorted({_canonical_name(n) for n in names}, key=len, reverse=True)
    for canonical in ordered:
        if canonical in seen:
            continue
        if _campaign_signal(text, canonical):
            found.append(canonical)
            seen.add(canonical)
    return found


def is_campaign_only_signal(text: str, campaign_names: list[str] | None = None) -> bool:
    from clamps_biblio.clamps_signals import has_clamps_signal

    return bool(campaigns_in_text(text, campaign_names)) and not has_clamps_signal(text)


def campaign_from_channel_b_source(source: str) -> str:
    if not source.startswith(("channel_b:", "campaign_clamps:")):
        return ""
    label = source.split(":", 1)[1]
    if ":" in label:
        _, rest = label.split(":", 1)
    else:
        rest = label
    return rest.split("+", 1)[0].strip()
