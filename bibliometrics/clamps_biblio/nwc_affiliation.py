"""National Weather Center (NWC) affiliation classification from OpenAlex institution strings."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
import pandas as pd

# Internal bucket keys used in CSVs and figures
NWC_AFFILIATED = "nwc_affiliated"
NON_AFFILIATED = "non_affiliated"
UNKNOWN = "unknown"
EXCLUDED = "exclude"

AFFILIATION_LABELS = {
    NWC_AFFILIATED: "NWC-affiliated",
    NON_AFFILIATED: "Non-NWC",
    UNKNOWN: "Unknown",
}

NWC_AFFILIATION_CAPTION = (
    "NWC-affiliated includes co-authors from any National Weather Center entity: "
    "University of Oklahoma (incl. School of Meteorology), CIWRO (formerly CIMMS), "
    "NSSL, Oklahoma Climatological Survey, NWS WFO Norman, NWS Storm Prediction Center, "
    "CAPS, or ARRC."
)

# CIMMS was renamed to CIWRO; OpenAlex metadata still uses the legacy name.
CIWRO_LEGACY_LABEL = "CIMMS"
CIWRO_CURRENT_LABEL = "CIWRO"
CIWRO_LEGACY_PATTERNS = [
    r"cooperative institute for mesoscale meteorological",
    r"\bCIMMS\b",
]


@dataclass(frozen=True)
class NwcEntity:
    entity_id: str
    label: str
    patterns: tuple[re.Pattern[str], ...]


def _compile_patterns(raw: list[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.I) for p in raw)


DEFAULT_NWC_ENTITIES: list[dict[str, Any]] = [
    {
        "id": "ou",
        "label": "OU",
        "patterns": [
            r"university of oklahoma",
            r"school of meteorology",
        ],
    },
    {
        "id": "ciwro",
        "label": CIWRO_CURRENT_LABEL,
        "patterns": [
            r"cooperative institute for severe and high-impact weather",
            r"\bCIWRO\b",
            *CIWRO_LEGACY_PATTERNS,
        ],
    },
    {
        "id": "nssl",
        "label": "NSSL",
        "patterns": [
            r"national severe storms laboratory",
            r"noaa national severe storms laboratory",
            r"\bNSSL\b",
        ],
    },
    {
        "id": "ocs",
        "label": "Oklahoma Climatological Survey",
        "patterns": [
            r"oklahoma climatological survey",
            r"oklahoma climatological center",
        ],
    },
    {
        "id": "wfo_norman",
        "label": "NWS WFO Norman",
        "patterns": [
            r"norman weather forecast office",
            r"weather forecast office.*norman",
            r"norman.*weather forecast office",
            r"\bWFO\b.*\bNorman\b",
        ],
    },
    {
        "id": "spc",
        "label": "NWS SPC",
        "patterns": [
            r"storm prediction center",
            r"noaa storm prediction center",
        ],
    },
    {
        "id": "caps",
        "label": "CAPS",
        "patterns": [
            r"center for analysis and prediction of storms",
        ],
    },
    {
        "id": "arrd",
        "label": "ARRC",
        "patterns": [
            r"advanced radar research center",
            r"\bARRC\b",
        ],
    },
]


def _merge_cimms_into_ciwro(raw_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold legacy CIMMS entry into CIWRO (same institute, renamed)."""
    ciwro: dict[str, Any] | None = None
    cimms_patterns: list[str] = []
    rest: list[dict[str, Any]] = []

    for entry in raw_entities:
        eid = str(entry.get("id", "")).lower()
        if eid == "ciwro":
            ciwro = dict(entry)
        elif eid == "cimms":
            cimms_patterns.extend(entry.get("patterns", []))
        else:
            rest.append(entry)

    if ciwro is None:
        ciwro = next((e for e in DEFAULT_NWC_ENTITIES if e["id"] == "ciwro"), None)
        if ciwro:
            ciwro = dict(ciwro)

    if ciwro is not None:
        patterns = list(dict.fromkeys(list(ciwro.get("patterns", [])) + cimms_patterns + CIWRO_LEGACY_PATTERNS))
        ciwro["label"] = CIWRO_CURRENT_LABEL
        ciwro["patterns"] = patterns
        return [ciwro, *rest]

    return raw_entities


def load_nwc_entities(config_path: Path | None = None) -> list[NwcEntity]:
    """Load NWC entity patterns from config.yaml or built-in defaults."""
    entities = DEFAULT_NWC_ENTITIES
    if config_path and config_path.exists():
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if cfg.get("nwc_affiliations"):
            entities = _merge_cimms_into_ciwro(cfg["nwc_affiliations"])

    out: list[NwcEntity] = []
    for entry in entities:
        label = str(entry.get("label", entry["id"]))
        if str(entry.get("id", "")).lower() == "cimms":
            continue
        if str(entry.get("id", "")).lower() == "ciwro":
            label = CIWRO_CURRENT_LABEL
        out.append(
            NwcEntity(
                entity_id=str(entry["id"]),
                label=label,
                patterns=_compile_patterns(list(entry["patterns"])),
            )
        )
    return out


def matched_nwc_entities(text: str, entities: list[NwcEntity] | None = None) -> list[str]:
    """Return labels of NWC entities found in an institution string."""
    if not text or str(text).lower() == "nan":
        return []
    if entities is None:
        entities = load_nwc_entities()
    found: list[str] = []
    for entity in entities:
        if any(p.search(text) for p in entity.patterns):
            label = entity.label
            if label == CIWRO_LEGACY_LABEL:
                label = CIWRO_CURRENT_LABEL
            if label not in found:
                found.append(label)
    return found


def classify_affiliation(institutions: str, entities: list[NwcEntity] | None = None) -> str:
    if matched_nwc_entities(institutions, entities):
        return NWC_AFFILIATED
    if not institutions or str(institutions).lower() == "nan":
        return UNKNOWN
    return NON_AFFILIATED


def affiliation_detail(institutions: str, entities: list[NwcEntity] | None = None) -> str:
    matched = matched_nwc_entities(institutions, entities)
    if matched:
        return "+".join(matched)
    if not institutions or str(institutions).lower() == "nan":
        return UNKNOWN
    return NON_AFFILIATED


def load_affiliation_overrides(path: Path | None) -> dict[str, dict[str, str]]:
    """Load manual affiliation fixes keyed by openalex_id."""
    if not path or not path.exists():
        return {}
    df = pd.read_csv(path)
    if "openalex_id" not in df.columns or "affiliation" not in df.columns:
        return {}
    overrides: dict[str, dict[str, str]] = {}
    for _, row in df.iterrows():
        oid = str(row["openalex_id"]).strip()
        aff = str(row["affiliation"]).strip().lower()
        if aff in ("nwc", "nwc_affiliated"):
            aff = NWC_AFFILIATED
        elif aff in ("non", "non-nwc", "non_affiliated"):
            aff = NON_AFFILIATED
        elif aff in ("exclude", "excluded", "none"):
            aff = EXCLUDED
        overrides[oid] = {
            "affiliation": aff,
            "notes": str(row.get("notes", "") or ""),
        }
    return overrides


def apply_affiliation_overrides(df: pd.DataFrame, overrides: dict[str, dict[str, str]]) -> pd.DataFrame:
    if not overrides or "openalex_id" not in df.columns:
        return df
    out = df.copy()
    for idx, row in out.iterrows():
        oid = str(row.get("openalex_id", "")).strip()
        if oid not in overrides:
            continue
        o = overrides[oid]
        out.at[idx, "affiliation"] = o["affiliation"]
        if o["affiliation"] == NWC_AFFILIATED:
            out.at[idx, "affiliation_detail"] = "NWC (manual override)"
        elif o["affiliation"] == NON_AFFILIATED:
            out.at[idx, "affiliation_detail"] = "Non-NWC (manual override)"
        elif o["affiliation"] == EXCLUDED:
            out.at[idx, "affiliation_detail"] = "excluded (manual override)"
        if o.get("notes"):
            out.at[idx, "affiliation_override_notes"] = o["notes"]
    return out
