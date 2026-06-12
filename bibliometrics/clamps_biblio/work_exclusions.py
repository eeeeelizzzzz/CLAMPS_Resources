"""Global exclusions for the broad PDF scan pool."""

from __future__ import annotations

from typing import Any

from clamps_biblio.clamps_signals import has_clamps_signal
from clamps_biblio.deposit_classifications import search_exclusion_reason
from clamps_biblio.pdf_resolver import normalize_doi

CLAMPS_DEPLOYMENT_START_YEAR = 2015

# Known CLAMPS registry rows bypass the year floor (ground truth, dataset DOIs).
_YEAR_FLOOR_EXEMPT_SOURCES = frozenset(
    {
        "channel_g:ground_truth",
        "channel_c:dataset_registry",
    }
)

EXCLUDED_BROAD_POOL_TYPES = frozenset({"peer-review"})

EXCLUDED_BROAD_POOL_DOIS = frozenset(
    {
        normalize_doi("10.1109/access.2023.3262560"),  # 3D point cloud false positive
        normalize_doi("10.1175/jas-d-20-0028.1"),  # density current / Mobile PISA false lead
        normalize_doi("10.48550/arxiv.2111.15207"),  # NeeDrop point clouds
    }
)


def broad_pool_exclusion_reason(row: dict[str, Any] | Any) -> str:
    get = row.get if hasattr(row, "get") else lambda k, d="": ""
    deposit_reason = search_exclusion_reason(row)
    if deposit_reason:
        return deposit_reason
    work_type = str(get("type", "") or "").strip().lower()
    if work_type in EXCLUDED_BROAD_POOL_TYPES:
        return "excluded:peer-review"
    doi = normalize_doi(str(get("doi", "") or ""))
    if doi and doi in EXCLUDED_BROAD_POOL_DOIS:
        return "excluded:manual_doi_blocklist"
    return ""


def is_broad_pool_excluded(row: dict[str, Any] | Any) -> bool:
    return bool(broad_pool_exclusion_reason(row))


def _metadata_text(row: dict[str, Any] | Any) -> str:
    get = row.get if hasattr(row, "get") else lambda k, d="": ""
    return " ".join(str(get(k, "") or "") for k in ("title", "abstract", "institutions", "topics"))


def _parse_publication_year(row: dict[str, Any] | Any) -> int | None:
    get = row.get if hasattr(row, "get") else lambda k, d="": ""
    raw = get("year", None)
    if raw is None or str(raw).strip().lower() in {"", "nan", "none"}:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def publication_year_floor_reason(
    row: dict[str, Any] | Any,
    min_year: int = CLAMPS_DEPLOYMENT_START_YEAR,
) -> str:
    """
    Drop pre-min_year works unless OpenAlex metadata carries a strong CLAMPS signal.

    Rows without a parseable year are kept. Registry sources (channel G/C) are exempt.
    """
    get = row.get if hasattr(row, "get") else lambda k, d="": ""
    source = str(get("discovery_source", "") or "").strip()
    if source in _YEAR_FLOOR_EXEMPT_SOURCES or source.startswith("channel_g:"):
        return ""

    year = _parse_publication_year(row)
    if year is None or year >= min_year:
        return ""

    if has_clamps_signal(_metadata_text(row)):
        return ""

    return f"excluded:pre_{min_year}_no_strong_clamps"


def is_publication_year_excluded(
    row: dict[str, Any] | Any,
    min_year: int = CLAMPS_DEPLOYMENT_START_YEAR,
) -> bool:
    return bool(publication_year_floor_reason(row, min_year=min_year))
