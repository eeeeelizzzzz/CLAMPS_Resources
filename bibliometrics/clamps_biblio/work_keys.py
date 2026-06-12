"""Shared work identity keys and channel priority for deduplication."""

from __future__ import annotations

from typing import Any

from clamps_biblio.pdf_resolver import normalize_doi

CHANNEL_PRIORITY: dict[str, int] = {
    "channel_e": 1,
    "channel_d": 2,
    "channel_a": 3,
    "channel_b": 4,
    "channel_c": 5,
    "channel_h": 6,
    "channel_c:dataset_registry": 7,
    "channel_g": 8,
}


def channel_bucket(discovery_source: str) -> str:
    src = str(discovery_source or "")
    if src.startswith("channel_c:dataset_registry"):
        return "channel_c:dataset_registry"
    if src.startswith("channel_"):
        return src.split(":")[0]
    return src.split(":")[0] if src else "unknown"


def row_key(row: dict[str, Any]) -> str:
    doi = normalize_doi(str(row.get("doi", "") or ""))
    if doi:
        return f"doi:{doi}"
    oid = str(row.get("openalex_id", "") or "").strip()
    if oid and oid.lower() != "nan":
        return f"id:{oid}"
    handle = str(row.get("repo_handle", "") or "").strip()
    repo = str(row.get("repo_id", "") or "").strip()
    if repo and handle and repo.lower() != "nan" and handle.lower() != "nan":
        return f"repo:{repo}:{handle}"
    title = str(row.get("title", "") or "").strip().lower()
    return f"title:{title[:120]}"
