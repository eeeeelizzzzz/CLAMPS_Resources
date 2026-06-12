"""Load, repair, dedupe, and merge channel discovery CSVs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from clamps_biblio.channel_config import load_ground_truth
from clamps_biblio.config import load_config
from clamps_biblio.enrichment import enrich_row, enrich_rows
from clamps_biblio.pdf_resolver import normalize_doi
from clamps_biblio.work_keys import CHANNEL_PRIORITY, channel_bucket, row_key

DISCOVERY_DEDUPE_PRIORITY: dict[str, int] = {
    **CHANNEL_PRIORITY,
    "unknown": 0,
}


def _priority_for_row(row: dict[str, Any]) -> int:
    return DISCOVERY_DEDUPE_PRIORITY.get(channel_bucket(str(row.get("discovery_source", ""))), 0)


def dedupe_discovered_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one row per work, preferring the strongest discovery channel label."""
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row_key(row)
        if key not in best or _priority_for_row(row) >= _priority_for_row(best[key]):
            best[key] = row
    return list(best.values())


def _present_dois(rows: list[dict[str, Any]]) -> set[str]:
    dois: set[str] = set()
    for row in rows:
        doi = normalize_doi(str(row.get("doi", "") or ""))
        if doi:
            dois.add(doi)
    return dois


def missing_ground_truth_rows(
    rows: list[dict[str, Any]],
    root: Path,
    *,
    ground_truth_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Registry entries not already represented in *rows* by DOI."""
    present = _present_dois(rows)
    return [
        row
        for row in ground_truth_overlay_rows(rows, root, ground_truth_path=ground_truth_path)
        if normalize_doi(str(row.get("doi", "") or "")) not in present
    ]


def ground_truth_overlay_rows(
    rows: list[dict[str, Any]],
    root: Path,
    *,
    ground_truth_path: Path | None = None,
) -> list[dict[str, Any]]:
    """One row per ground-truth registry DOI, preserving OpenAlex metadata when present."""
    gt = load_ground_truth(ground_truth_path or root / "data" / "ground_truth_clamps_papers.csv")
    by_doi: dict[str, dict[str, Any]] = {}
    for row in rows:
        doi = normalize_doi(str(row.get("doi", "") or ""))
        if doi:
            by_doi[doi] = row

    overlay: list[dict[str, Any]] = []
    for _, gt_row in gt.iterrows():
        doi = str(gt_row.get("doi", "") or "").strip()
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            continue
        base = dict(by_doi.get(doi_norm, {}))
        title = str(gt_row.get("title", "") or "").strip()
        authors = str(gt_row.get("authors", "") or "").strip()
        overlay.append(
            {
                **base,
                "title": title or str(base.get("title", "") or ""),
                "doi": doi,
                "year": gt_row.get("year") if pd.notna(gt_row.get("year")) else base.get("year"),
                "authors": authors or str(base.get("authors", "") or ""),
                "type": str(base.get("type", "") or "").strip() or "article",
                "discovery_source": "channel_g:ground_truth",
            }
        )
    return overlay


def _sort_discovered_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    tier_order = {"high": 0, "medium": 1, "low": 2}
    out = df.copy()
    out["_tier_order"] = out["confidence_tier"].map(tier_order)
    out = out.sort_values(
        ["_tier_order", "relevance_score", "year", "title"],
        ascending=[True, False, False, True],
        na_position="last",
    ).drop(columns="_tier_order")
    return out


def merge_discovery_sources(
    root: Path,
    *,
    base_path: Path,
    thesis_repos_path: Path | None = None,
    thesis_openalex_path: Path | None = None,
    ground_truth_path: Path | None = None,
    include_ground_truth: bool = True,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Merge channel CSVs, add missing ground truth, dedupe, and enrich."""
    cfg = load_config(root / "config.yaml")
    records: list[dict[str, Any]] = []

    def _append_csv(path: Path | None, label: str, stats: dict[str, int]) -> None:
        if path is None or not path.exists():
            stats[f"{label}_rows"] = 0
            return
        df = pd.read_csv(path)
        stats[f"{label}_rows"] = len(df)
        records.extend(df.to_dict(orient="records"))

    stats: dict[str, int] = {}
    _append_csv(base_path, "base", stats)
    _append_csv(thesis_openalex_path, "thesis_openalex", stats)
    _append_csv(thesis_repos_path, "thesis_repos", stats)

    if include_ground_truth:
        gt_overlay = ground_truth_overlay_rows(records, root, ground_truth_path=ground_truth_path)
        present_before = _present_dois(records)
        stats["ground_truth_overlay"] = len(gt_overlay)
        stats["ground_truth_added"] = sum(
            1
            for row in gt_overlay
            if normalize_doi(str(row.get("doi", "") or "")) not in present_before
        )
        stats["ground_truth_promoted"] = stats["ground_truth_overlay"] - stats["ground_truth_added"]
        records.extend(gt_overlay)
    else:
        stats["ground_truth_overlay"] = 0
        stats["ground_truth_added"] = 0
        stats["ground_truth_promoted"] = 0

    stats["raw_rows"] = len(records)
    deduped = dedupe_discovered_records(records)
    stats["deduped_rows"] = len(deduped)
    enriched = enrich_rows(deduped, cfg)
    df = _sort_discovered_df(pd.DataFrame(enriched))
    stats["final_rows"] = len(df)
    return df, stats


def repair_discovered_dataframe(df: pd.DataFrame, root: Path) -> pd.DataFrame:
    """Dedupe discovery rows and fill missing relevance scores / tiers."""
    cfg = load_config(root / "config.yaml")
    records = df.to_dict(orient="records")
    deduped = dedupe_discovered_records(records)
    repaired = [enrich_row(row, cfg) for row in deduped]
    return pd.DataFrame(repaired)


def load_repaired_discovered_channels(path: Path, root: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return repair_discovered_dataframe(pd.read_csv(path), root)
