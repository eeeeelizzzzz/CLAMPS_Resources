"""Build a broad PDF scan pool without the strict high-confidence gate."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from clamps_biblio.channel_config import load_dataset_dois, load_ground_truth
from clamps_biblio.config import load_config
from clamps_biblio.homophone_filters import homophone_reason, is_homophone
from clamps_biblio.pdf_resolver import normalize_doi
from clamps_biblio.channel_a import passes_channel_a_filter
from clamps_biblio.channel_b import (
    channel_b_ambiguous_needs_metadata_clamps,
    channel_b_metadata_confidence,
    channel_b_metadata_screening_reason,
)
from clamps_biblio.discovered_channels import load_repaired_discovered_channels
from clamps_biblio.enrichment import enrich_row
from clamps_biblio.relevance import qualifies_strict_high_confidence
from clamps_biblio.work_exclusions import is_broad_pool_excluded, is_publication_year_excluded
from clamps_biblio.work_keys import CHANNEL_PRIORITY, channel_bucket, row_key

INSTITUTION_LIKE = re.compile(
    r"\b(university|college|institut|laborator|school of|"
    r"national severe storms|national oceanic|cooperative institute|"
    r"NSSL|NOAA|NSF|department of|center for|meteorolog)\b",
    re.I,
)


def _clean_field(value: Any) -> str:
    text = str(value or "").strip()
    return "" if not text or text.lower() == "nan" else text


def first_author_from_row(row: dict[str, Any], gt_authors: dict[str, str]) -> str:
    doi = normalize_doi(_clean_field(row.get("doi")))
    src = _clean_field(row.get("discovery_source"))

    if doi and doi in gt_authors and src.startswith("channel_g:"):
        lead = gt_authors[doi].split(",")[0].strip()
        if lead:
            return lead

    for field in ("first_author", "authors"):
        raw = _clean_field(row.get(field))
        if raw:
            lead = raw.split(",")[0].strip()
            if lead and not INSTITUTION_LIKE.search(lead):
                return lead

    is_thesis = src.startswith(("channel_h:", "tier6_repo:")) or bool(_clean_field(row.get("repo_id")))
    if not is_thesis:
        return ""

    inst = str(row.get("institutions", "") or "").strip()
    if not inst or inst.lower() == "nan":
        return ""
    first = inst.split(";")[0].strip()
    if first and not INSTITUTION_LIKE.search(first):
        return first
    return ""


def prior_strict_exclusion_reason(row: dict[str, Any], ambiguous_campaigns: list[str]) -> str:
    """Why the legacy strict gate would have dropped this row (empty if it would pass)."""
    if qualifies_strict_high_confidence(row, ambiguous_campaigns):
        return ""

    tier = str(row.get("confidence_tier", "") or "").strip()
    if tier not in ("high", "medium"):
        label = tier if tier and tier.lower() != "nan" else "missing"
        return f"strict_gate:confidence_tier={label}"

    source = str(row.get("discovery_source", "") or "")
    if source.startswith(("channel_c:dataset_registry", "channel_g:")):
        return ""

    if "campaign_candidate:" in source:
        return "strict_gate:channel_h_campaign_candidate"

    if source.startswith("channel_a:"):
        return "strict_gate:channel_a_no_phrase_in_metadata"

    if source.startswith(("channel_f:", "channel_h:", "tier6_repo:")):
        return "strict_gate:thesis_no_clamps_in_title_inst_topics"

    if source.startswith(("campaign_clamps:", "channel_b:")):
        if channel_b_ambiguous_needs_metadata_clamps(row, ambiguous_campaigns):
            return "strict_gate:ambiguous_b2_no_campaign_token_in_metadata"
        return "strict_gate:channel_b_filtered"

    if source.startswith(("channel_d:", "channel_e:")):
        return "strict_gate:author_bibliography_no_clamps_in_metadata"

    return "strict_gate:no_clamps_signal_in_metadata"


def _normalize_row(row: dict[str, Any], gt_authors: dict[str, str], ambiguous_campaigns: list[str]) -> dict[str, str]:
    return {
        "title": str(row.get("title", "") or "").strip(),
        "first_author": first_author_from_row(row, gt_authors),
        "doi": str(row.get("doi", "") or "").strip(),
        "type": str(row.get("type", "") or "").strip() or "unknown",
        "channel": str(row.get("discovery_source", "") or "").strip(),
        "channel_b_metadata_confidence": channel_b_metadata_confidence(row, ambiguous_campaigns),
        "prior_strict_exclusion_reason": prior_strict_exclusion_reason(row, ambiguous_campaigns),
        "_bucket": channel_bucket(str(row.get("discovery_source", "") or "")),
        "_key": row_key(row),
    }


def _lookup_discovered_row(normalized: dict[str, Any], discovered: pd.DataFrame) -> dict[str, Any]:
    doi = normalize_doi(_clean_field(normalized.get("doi")))
    if doi and "doi" in discovered.columns:
        hits = discovered[discovered["doi"].astype(str).map(normalize_doi) == doi]
        if not hits.empty:
            return hits.iloc[0].to_dict()
    return normalized


def filter_channel_a_winners(
    rows: list[dict[str, str]],
    discovered: pd.DataFrame,
    gt_authors: dict[str, str],
    ambiguous_campaigns: list[str],
    cfg,
) -> tuple[list[dict[str, str]], int]:
    """Drop Channel A rows that lack the full query phrase in metadata (post-dedupe only)."""
    kept: list[dict[str, str]] = []
    dropped = 0
    for row in rows:
        if is_broad_pool_excluded(row):
            dropped += 1
            continue
        if is_publication_year_excluded(row):
            dropped += 1
            continue
        screen = channel_b_metadata_screening_reason(row, ambiguous_campaigns)
        if screen:
            dropped += 1
            continue
        channel = _clean_field(row.get("channel"))
        if not channel.startswith("channel_a:"):
            kept.append(row)
            continue
        full = _lookup_discovered_row(row, discovered)
        full = dict(full)
        full["discovery_source"] = channel
        if not passes_channel_a_filter(full):
            dropped += 1
            continue
        enriched = enrich_row(full, cfg)
        kept.append(_normalize_row(enriched, gt_authors, ambiguous_campaigns))
    return kept, dropped


def _dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    best: dict[str, dict[str, str]] = {}
    for row in rows:
        key = row["_key"]
        pri = CHANNEL_PRIORITY.get(row["_bucket"], 0)
        if key not in best or pri > CHANNEL_PRIORITY.get(best[key]["_bucket"], 0):
            best[key] = row
    out = list(best.values())
    for row in out:
        row.pop("_bucket", None)
        row.pop("_key", None)
    return out


def load_channel_g_rows(
    root: Path,
    gt_authors: dict[str, str],
    ambiguous_campaigns: list[str],
    discovered: pd.DataFrame,
) -> list[dict[str, str]]:
    """All ground-truth registry entries (current G filter: always include)."""
    gt = load_ground_truth(root / "data" / "ground_truth_clamps_papers.csv")
    disc_by_doi: dict[str, pd.Series] = {}
    if not discovered.empty and "doi" in discovered.columns:
        for _, r in discovered.iterrows():
            d = normalize_doi(str(r.get("doi", "")))
            if d:
                disc_by_doi[d] = r

    rows: list[dict[str, str]] = []
    for _, gt_row in gt.iterrows():
        doi = str(gt_row.get("doi", "") or "").strip()
        doi_norm = normalize_doi(doi)
        if doi_norm in disc_by_doi:
            base = disc_by_doi[doi_norm].to_dict()
            base["discovery_source"] = "channel_g:ground_truth"
        else:
            authors = str(gt_row.get("authors", "") or "")
            base = {
                "title": str(gt_row.get("title", "") or ""),
                "doi": doi,
                "type": "article",
                "year": gt_row.get("year"),
                "authors": authors,
                "institutions": "",
                "abstract": "",
                "openalex_id": "",
                "discovery_source": "channel_g:ground_truth",
            }
        if not is_broad_pool_excluded(base):
            rows.append(_normalize_row(base, gt_authors, ambiguous_campaigns))
    return rows


def load_dataset_registry_rows(
    root: Path,
    gt_authors: dict[str, str],
    ambiguous_campaigns: list[str],
    dataset_meta: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    dois = load_dataset_dois(root / "data" / "clamps_dataset_dois.txt")
    rows: list[dict[str, str]] = []
    for doi in dois:
        meta = (dataset_meta or {}).get(normalize_doi(doi), {})
        base = {
            "title": meta.get("title") or f"CLAMPS-related dataset ({doi})",
            "doi": doi,
            "type": "dataset",
            "openalex_id": meta.get("openalex_id", ""),
            "institutions": meta.get("institutions", ""),
            "abstract": meta.get("abstract", ""),
            "confidence_tier": "high",
            "discovery_source": "channel_c:dataset_registry",
        }
        if meta.get("first_author"):
            base["first_author"] = meta["first_author"]
        rows.append(_normalize_row(base, gt_authors, ambiguous_campaigns))
    return rows


def load_discovered_channel_rows(
    discovered: pd.DataFrame,
    gt_authors: dict[str, str],
    ambiguous_campaigns: list[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Channels A–E and C from main discovery CSV; homophone filter only."""
    kept: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    if discovered.empty:
        return kept, rejected

    for _, row in discovered.iterrows():
        if is_broad_pool_excluded(row):
            continue
        if is_publication_year_excluded(row):
            continue
        screen = channel_b_metadata_screening_reason(row, ambiguous_campaigns)
        if screen:
            continue
        src = str(row.get("discovery_source", "") or "")
        bucket = channel_bucket(src)
        if bucket in ("channel_g", "channel_h", "channel_f"):
            continue
        reason = homophone_reason(row)
        if reason:
            rejected.append({**_normalize_row(row.to_dict(), gt_authors, ambiguous_campaigns), "homophone_reason": reason})
            continue
        kept.append(_normalize_row(row.to_dict(), gt_authors, ambiguous_campaigns))
    return kept, rejected


def load_channel_h_rows(
    thesis_path: Path,
    gt_authors: dict[str, str],
    ambiguous_campaigns: list[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Thesis repo crawl — homophone rejection only."""
    kept: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    if not thesis_path.exists():
        return kept, rejected

    df = pd.read_csv(thesis_path)
    for _, row in df.iterrows():
        if is_broad_pool_excluded(row):
            continue
        if is_publication_year_excluded(row):
            continue
        reason = homophone_reason(row)
        if reason:
            rejected.append({**_normalize_row(row.to_dict(), gt_authors, ambiguous_campaigns), "homophone_reason": reason})
            continue
        kept.append(_normalize_row(row.to_dict(), gt_authors, ambiguous_campaigns))
    return kept, rejected


def fetch_dataset_metadata(root: Path) -> dict[str, dict[str, Any]]:
    from clamps_biblio.openalex_client import OpenAlexClient

    cfg = load_config(root / "config.yaml")
    client = OpenAlexClient(mailto=cfg.openalex_mailto, request_delay=cfg.openalex_delay)
    dois = load_dataset_dois(root / "data" / "clamps_dataset_dois.txt")
    meta: dict[str, dict[str, Any]] = {}
    for doi in dois:
        work = client.work_by_doi(doi)
        if not work:
            continue
        flat = client.flatten_work(work, discovery_source="channel_c:dataset_registry")
        authorships = work.get("authorships") or []
        first = ""
        if authorships:
            first = (authorships[0].get("author") or {}).get("display_name", "") or ""
        meta[normalize_doi(doi)] = {
            "title": flat.get("title", ""),
            "openalex_id": flat.get("openalex_id", ""),
            "institutions": flat.get("institutions", ""),
            "abstract": flat.get("abstract", ""),
            "first_author": first,
        }
    return meta


def build_broad_scan_pool(
    root: Path,
    *,
    discovered_path: Path | None = None,
    thesis_path: Path | None = None,
    fetch_dataset_titles: bool = False,
) -> pd.DataFrame:
    cfg = load_config(root / "config.yaml")
    discovered_path = discovered_path or root / "output" / "clamps_papers_discovered_channels.csv"
    thesis_path = thesis_path or root / "output" / "clamps_theses_discovered_repos.csv"

    gt = load_ground_truth(root / "data" / "ground_truth_clamps_papers.csv")
    gt_authors = {
        normalize_doi(str(r["doi"])): str(r.get("authors", "") or "")
        for _, r in gt.iterrows()
        if str(r.get("doi", "") or "").strip()
    }

    discovered = load_repaired_discovered_channels(discovered_path, root)

    dataset_meta = fetch_dataset_metadata(root) if fetch_dataset_titles else None

    parts: list[dict[str, str]] = []
    parts.extend(load_channel_g_rows(root, gt_authors, cfg.ambiguous_campaigns, discovered))
    parts.extend(load_dataset_registry_rows(root, gt_authors, cfg.ambiguous_campaigns, dataset_meta))

    h_rows, _ = load_channel_h_rows(thesis_path, gt_authors, cfg.ambiguous_campaigns)
    parts.extend(h_rows)

    disc_rows, _ = load_discovered_channel_rows(discovered, gt_authors, cfg.ambiguous_campaigns)
    parts.extend(disc_rows)

    deduped = _dedupe_rows(parts)
    filtered, _ = filter_channel_a_winners(deduped, discovered, gt_authors, cfg.ambiguous_campaigns, cfg)
    return pd.DataFrame(filtered)


def build_broad_scan_pool_with_stats(
    root: Path,
    **kwargs: Any,
) -> tuple[pd.DataFrame, dict[str, int]]:
    cfg = load_config(root / "config.yaml")
    discovered_path = kwargs.get("discovered_path") or root / "output" / "clamps_papers_discovered_channels.csv"
    thesis_path = kwargs.get("thesis_path") or root / "output" / "clamps_theses_discovered_repos.csv"
    fetch_dataset_titles = kwargs.get("fetch_dataset_titles", False)

    gt_authors = {
        normalize_doi(str(r["doi"])): str(r.get("authors", "") or "")
        for _, r in load_ground_truth(root / "data" / "ground_truth_clamps_papers.csv").iterrows()
        if str(r.get("doi", "") or "").strip()
    }

    discovered = load_repaired_discovered_channels(discovered_path, root)
    dataset_meta = fetch_dataset_metadata(root) if fetch_dataset_titles else None

    g_rows = load_channel_g_rows(root, gt_authors, cfg.ambiguous_campaigns, discovered)
    ds_rows = load_dataset_registry_rows(root, gt_authors, cfg.ambiguous_campaigns, dataset_meta)
    h_rows, h_rej = load_channel_h_rows(thesis_path, gt_authors, cfg.ambiguous_campaigns)
    disc_rows, disc_rej = load_discovered_channel_rows(discovered, gt_authors, cfg.ambiguous_campaigns)

    deduped = _dedupe_rows(g_rows + ds_rows + h_rows + disc_rows)
    filtered, a_phrase_rej = filter_channel_a_winners(
        deduped, discovered, gt_authors, cfg.ambiguous_campaigns, cfg
    )
    df = pd.DataFrame(filtered)

    stats = {
        "channel_g": len(g_rows),
        "dataset_registry": len(ds_rows),
        "channel_h_kept": len(h_rows),
        "channel_h_homophone_rejected": len(h_rej),
        "discovered_kept": len(disc_rows),
        "discovered_homophone_rejected": len(disc_rej),
        "after_dedupe": len(deduped),
        "channel_a_phrase_rejected": a_phrase_rej,
        "final_rows": len(df),
        "prior_strict_excluded": int((df["prior_strict_exclusion_reason"].fillna("") != "").sum()),
        "prior_strict_included": int((df["prior_strict_exclusion_reason"].fillna("") == "").sum()),
    }
    return df, stats
