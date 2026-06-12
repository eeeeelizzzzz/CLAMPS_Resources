"""Probe OpenAlex indexed full text via the fulltext.search filter.

OpenAlex exposes searchable full text for many works (``has_fulltext=True``) without
downloading publisher PDFs. This module uses ``fulltext.search`` filters to detect
CLAMPS-related terms. Bare ``CLAMPS`` is intentionally excluded — it matches
engineering homophones in full text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from clamps_biblio.clamps_signals import classify_match_strength
from clamps_biblio.config import Config, load_config
from clamps_biblio.openalex_client import OpenAlexClient

# (label, pipe-OR query for fulltext.search). Order: strong facility terms first.
FULLTEXT_PROBE_GROUPS: tuple[tuple[str, str], ...] = (
    ("CLAMPS-1/2", "CLAMPS-1|CLAMPS-2|CLAMPS1|CLAMPS2"),
    (
        "full_name",
        "Collaborative Lower Atmospheric Mobile Profiling System",
    ),
    ("MP-1", "MP-1|MP1"),
    ("Mobile PISA", "Mobile PISA"),
    ("NSSL mobile profiler", "NSSL mobile profiler|NSSL mobile profiling|NSSL profiler"),
    ("NSSL lidar", "NSSL lidar|NSSL Doppler lidar"),
    ("OU lidar", "University of Oklahoma lidar|OU lidar"),
    ("NSSL AERI", "NSSL AERI|NSSL AERIoe"),
    ("OU AERI", "University of Oklahoma AERI|OU AERI|OU AERIoe"),
    ("NSSL MWR", "NSSL MWR|NSSL microwave radiometer"),
    ("OU MWR", "University of Oklahoma MWR|OU microwave radiometer"),
    ("NSSL sounding", "NSSL radiosonde|NSSL sounding"),
    ("OU sounding", "University of Oklahoma radiosonde|OU sounding"),
    ("AERI retrieval", "AERI retrieval|AERIoe retrieval"),
    ("lidar retrieval", "lidar retrieval"),
)

OPENALEX_WORK_ID_RE = re.compile(r"^W\d+$")


@dataclass(frozen=True)
class FulltextProbeHit:
    label: str
    context: str = "OpenAlex fulltext.search probe (no snippet available)"


def openalex_work_id(row: dict[str, Any] | Any) -> str:
    get = row.get if hasattr(row, "get") else lambda k, d="": ""
    raw = str(get("openalex_id", "") or "").strip()
    if not raw or raw.lower() == "nan":
        return ""
    if raw.startswith("repo:"):
        return ""
    tail = raw.rsplit("/", 1)[-1]
    return tail if OPENALEX_WORK_ID_RE.match(tail) else ""


def load_has_fulltext_map(path: Path) -> dict[str, bool]:
    """Map OpenAlex work id -> has_fulltext from a prior export."""
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    out: dict[str, bool] = {}
    for _, row in df.iterrows():
        oid = openalex_work_id(row.to_dict())
        if not oid:
            continue
        out[oid] = bool(row.get("has_fulltext"))
    return out


def row_has_openalex_fulltext(
    row: dict[str, Any],
    has_fulltext_map: dict[str, bool] | None = None,
) -> bool:
    oid = openalex_work_id(row)
    if not oid:
        return False
    if has_fulltext_map is not None and oid in has_fulltext_map:
        return bool(has_fulltext_map[oid])
    return bool(row.get("has_fulltext"))


def probe_fulltext_groups(
    client: OpenAlexClient,
    work_id: str,
    groups: tuple[tuple[str, str], ...] | None = None,
) -> list[FulltextProbeHit]:
    """Return labels whose probe query matches in OpenAlex indexed full text."""
    clean_id = work_id.rsplit("/", 1)[-1]
    if not OPENALEX_WORK_ID_RE.match(clean_id):
        return []

    hits: list[FulltextProbeHit] = []
    for label, query in groups or FULLTEXT_PROBE_GROUPS:
        filt = f"ids.openalex:{clean_id},fulltext.search:{query}"
        data = client._get("works", {"filter": filt, "per-page": 1})
        if data.get("meta", {}).get("count", 0) > 0:
            hits.append(FulltextProbeHit(label=label))
    return hits


def scan_openalex_fulltext(
    row: dict[str, Any],
    client: OpenAlexClient,
    cfg: Config,
    *,
    grant_numbers: list[str] | None = None,
    dataset_dois: list[str] | None = None,
) -> tuple[list[FulltextProbeHit], str, str]:
    """
    Probe one work's OpenAlex full text.

    Returns (hits, matched_terms_str, match_strength).
    """
    work_id = openalex_work_id(row)
    if not work_id:
        return [], "", ""

    hits = probe_fulltext_groups(client, work_id)
    labels = {h.label for h in hits}

    grants = grant_numbers if grant_numbers is not None else cfg.grant_numbers
    for grant in grants:
        filt = f"ids.openalex:{work_id},fulltext.search:{grant}"
        if client._get("works", {"filter": filt, "per-page": 1}).get("meta", {}).get("count", 0) > 0:
            labels.add(f"grant:{grant}")
            hits.append(FulltextProbeHit(label=f"grant:{grant}"))

    dois = dataset_dois if dataset_dois is not None else cfg.dataset_dois
    for doi in dois:
        filt = f"ids.openalex:{work_id},fulltext.search:{doi}"
        if client._get("works", {"filter": filt, "per-page": 1}).get("meta", {}).get("count", 0) > 0:
            labels.add(f"dataset_doi:{doi}")
            hits.append(FulltextProbeHit(label=f"dataset_doi:{doi}"))

    matched_terms = "; ".join(sorted(labels))
    match_strength = classify_match_strength(labels)
    return hits, matched_terms, match_strength


def default_has_fulltext_path(cfg: Config) -> Path:
    return cfg.output_dir / "openalex_has_fulltext_by_work.csv"
