"""Shared data loading for CLAMPS review metrics and figures."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from clamps_biblio.channel_config import load_campaign_anchors
from clamps_biblio.pdf_resolver import normalize_doi
from clamps_biblio.work_keys import channel_bucket
from clamps_biblio.nwc_affiliation import (
    AFFILIATION_LABELS,
    EXCLUDED,
    NWC_AFFILIATION_CAPTION,
    NON_AFFILIATED,
    NWC_AFFILIATED,
    UNKNOWN,
    affiliation_detail,
    apply_affiliation_overrides,
    classify_affiliation,
    load_affiliation_overrides,
    load_nwc_entities,
)

PEER_REVIEW_TYPES = {"article", "review", "letter"}
THESIS_TYPES = {"dissertation"}

# Broad-scan channels reviewed and locked into the all-works export.
VALIDATED_BROAD_POOL_BUCKETS = frozenset({"channel_a"})

# Legacy aliases for scripts not yet migrated
ou_affiliated = NWC_AFFILIATED
non_affiliated = NON_AFFILIATED

SIGNAL_GROUPS = [
    "CLAMPS",
    "full_name",
    "MP-1 / Mobile PISA",
    "AERI retrieval",
    "lidar retrieval",
    "dataset DOI",
    "NSSL/OU instruments",
    "repository URL",
]


def _affiliation_overrides_path(root: Path | None) -> Path | None:
    if not root:
        return None
    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    rel = cfg.get("affiliation_overrides_file", "data/affiliation_overrides.csv")
    path = root / rel
    return path if path.exists() else None


def enrich(df: pd.DataFrame, root: Path | None = None) -> pd.DataFrame:
    config_path = (root / "config.yaml") if root else None
    entities = load_nwc_entities(config_path)
    out = df.copy()
    out["affiliation"] = out["institutions"].apply(lambda t: classify_affiliation(t, entities))
    out["affiliation_detail"] = out["institutions"].apply(lambda t: affiliation_detail(t, entities))
    out["is_peer_reviewed"] = out["type"].astype(str).isin(PEER_REVIEW_TYPES)
    out["is_thesis"] = out["type"].astype(str).isin(THESIS_TYPES)
    overrides = load_affiliation_overrides(_affiliation_overrides_path(root))
    out = apply_affiliation_overrides(out, overrides)
    # Treat missing OpenAlex affiliation as non-NWC for counts and figures.
    out.loc[out["affiliation"] == UNKNOWN, "affiliation"] = NON_AFFILIATED
    return out


def _drop_excluded(df: pd.DataFrame) -> pd.DataFrame:
    if "affiliation" not in df.columns:
        return df
    return df[df["affiliation"] != EXCLUDED].copy()


def normalize_signal(term: str) -> str | None:
    t = term.strip()
    if not t:
        return None
    lower = t.lower()
    if t == "CLAMPS" or lower == "clamps":
        return "CLAMPS"
    if t == "full_name":
        return "full_name"
    if t in ("MP-1", "Mobile PISA") or "mp-1" in lower or "mobile pisa" in lower:
        return "MP-1 / Mobile PISA"
    if "aeri" in lower:
        return "AERI retrieval"
    if "lidar" in lower:
        return "lidar retrieval"
    if t.startswith("dataset_doi:"):
        return "dataset DOI"
    if any(k in lower for k in ("nssl", "ou lidar", "ou mwr", "nssl mwr", "ou sounding", "nssl sounding")):
        return "NSSL/OU instruments"
    if "data.nssl.noaa.gov" in lower or "thredds" in lower:
        return "repository URL"
    return None


def _first_existing_csv(root: Path, names: tuple[str, ...]) -> Path:
    out = root / "output"
    for name in names:
        path = out / name
        if path.exists():
            return path
    return out / names[-1]


def _enrich_corpus_df(df: pd.DataFrame, root: Path | None) -> pd.DataFrame:
    """Normalize clamps_review_corpus.csv rows for figure/metrics code."""
    out = df.copy()
    if "openalex_type" in out.columns:
        out["type"] = out["openalex_type"].fillna(out.get("corpus_class", ""))
    out["type"] = out["type"].astype(str).replace({"nan": ""})
    out.loc[out["corpus_class"].astype(str) == "thesis", "type"] = "dissertation"
    out.loc[out["corpus_class"].astype(str) == "dataset", "type"] = "dataset"
    out.loc[out["type"].astype(str).str.strip() == "", "type"] = out["corpus_class"]
    return enrich(out, root)


def load_corpus_review_frames(root: Path) -> dict[str, pd.DataFrame]:
    """
    Review-article corpus: all finalized works plus a published-literature subset.

    - flagged_yd / All works: full clamps_review_corpus.csv
    - pdf_confirmed / Published literature: corpus_class article or report
    """
    corpus_path = root / "output" / "clamps_review_corpus.csv"
    if not corpus_path.exists():
        raise FileNotFoundError(
            f"Review corpus not found: {corpus_path}\n"
            "Run: python scripts/build_review_corpus.py"
        )

    all_works = _enrich_corpus_df(pd.read_csv(corpus_path), root)
    published = all_works[
        all_works["corpus_class"].astype(str).isin(["article", "report"])
    ].copy()

    disc_path = _first_existing_csv(
        root,
        ("clamps_papers_discovered_channels.csv", "clamps_papers_discovered.csv"),
    )
    disc = enrich(pd.read_csv(disc_path), root) if disc_path.exists() else all_works.copy()
    hc = all_works.copy()

    def _read_csv_or_empty(path: Path) -> pd.DataFrame:
        if not path.exists() or path.stat().st_size == 0:
            return pd.DataFrame()
        try:
            return pd.read_csv(path)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

    scan_path = root / "output" / "clamps_scan_log.csv"
    local_path = root / "output" / "clamps_local_scan_log.csv"
    mentions_path = root / "output" / "clamps_text_mentions.csv"
    html_mentions_path = root / "output" / "clamps_publications_html_mentions.csv"
    scan = _read_csv_or_empty(scan_path)
    local_log = _read_csv_or_empty(local_path)
    mentions = _read_csv_or_empty(mentions_path)
    if mentions.empty:
        mentions = _read_csv_or_empty(html_mentions_path)
    else:
        html_mentions = _read_csv_or_empty(html_mentions_path)
        if not html_mentions.empty:
            mentions = pd.concat([mentions, html_mentions], ignore_index=True)

    empty_scan = pd.DataFrame(
        columns=["openalex_id", "doi", "pdf_scan_status", "pdf_mention_count", "match_strength", "matched_terms"]
    )
    if not scan.empty and "status" in scan.columns:
        scan_cols = scan[
            ["openalex_id", "doi", "status", "mention_count", "match_strength", "matched_terms"]
        ].rename(columns={"status": "pdf_scan_status", "mention_count": "pdf_mention_count"})
    else:
        scan_cols = empty_scan

    all_works = all_works.merge(scan_cols, on=["openalex_id", "doi"], how="left")
    published = published.merge(scan_cols, on=["openalex_id", "doi"], how="left")
    for frame in (all_works, published):
        if "pdf_mention_count" in frame.columns:
            frame["pdf_mention_count"] = (
                pd.to_numeric(frame["pdf_mention_count"], errors="coerce").fillna(0).astype(int)
            )

    return {
        "discovered": disc,
        "high_confidence": hc,
        "flagged_ym": all_works.copy(),
        "flagged_yd": all_works,
        "flagged_y": all_works.copy(),
        "pdf_confirmed": published,
        "scan_log": scan,
        "local_log": local_log,
        "mentions": mentions,
        "review_corpus": all_works,
    }


def load_review_frames(root: Path, *, prefer_corpus: bool = True) -> dict[str, pd.DataFrame]:
    corpus_path = root / "output" / "clamps_review_corpus.csv"
    if prefer_corpus and corpus_path.exists():
        return load_corpus_review_frames(root)

    disc_path = _first_existing_csv(
        root,
        ("clamps_papers_discovered_channels.csv", "clamps_papers_discovered.csv"),
    )
    hc_path = _first_existing_csv(
        root,
        (
            "clamps_papers_high_confidence_channels_with_pdfs.csv",
            "clamps_papers_high_confidence_channels.csv",
            "clamps_papers_high_confidence.csv",
        ),
    )
    flagged_path = _first_existing_csv(
        root,
        ("clamps_papers_high_confidence_channels_with_pdfs.csv", "clamps_papers_with_pdf_urls_FFLAGGED.csv"),
    )

    disc = enrich(pd.read_csv(disc_path), root)
    hc = enrich(pd.read_csv(hc_path), root)
    flagged = enrich(pd.read_csv(flagged_path), root)
    scan = pd.read_csv(root / "output/clamps_scan_log.csv")
    local_log = pd.read_csv(root / "output/clamps_local_scan_log.csv")
    mentions = pd.read_csv(root / "output/clamps_text_mentions.csv")

    scan_cols = scan[
        ["openalex_id", "doi", "status", "mention_count", "match_strength", "matched_terms"]
    ].rename(columns={"status": "pdf_scan_status", "mention_count": "pdf_mention_count"})

    if "expectation" in flagged.columns and flagged["expectation"].notna().any():
        exp = flagged["expectation"].astype(str).str.strip().str.upper()
        ym = _drop_excluded(flagged[exp.isin(["Y", "M"])].copy())
        yd = _drop_excluded(flagged[exp.isin(["Y", "D"])].copy())
        y_flagged = _drop_excluded(flagged[exp == "Y"].copy())
    else:
        # Channel discovery: high-confidence pool is the review universe (Fig. 8 "All works").
        yd = _drop_excluded(flagged.copy())
        ym = yd.copy()
        y_flagged = yd.copy()

    ym = ym.merge(scan_cols, on=["openalex_id", "doi"], how="left")
    y_flagged = y_flagged.merge(scan_cols, on=["openalex_id", "doi"], how="left")
    yd = yd.merge(scan_cols, on=["openalex_id", "doi"], how="left")
    pdf_conf = yd[yd["pdf_scan_status"] == "mentions_found"].copy()

    return {
        "discovered": disc,
        "high_confidence": hc,
        "flagged_ym": ym,
        "flagged_yd": yd,
        "flagged_y": y_flagged,
        "pdf_confirmed": pdf_conf,
        "scan_log": scan,
        "local_log": local_log,
        "mentions": mentions,
    }


def load_campaign_names(root: Path) -> list[str]:
    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    return list(cfg.get("field_campaigns", []))


def load_clamps_deployments(root: Path) -> pd.DataFrame:
    """Load CLAMPS field deployment records (one row per facility deployment)."""
    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    rel = cfg.get("clamps_deployments_file", "data/clamps_deployments.csv")
    path = root / rel
    if not path.exists():
        return pd.DataFrame(
            columns=["start_year", "start_month", "end_year", "end_month", "campaign", "platform", "notes"]
        )
    df = pd.read_csv(path)
    df["start_year"] = pd.to_numeric(df["start_year"], errors="coerce")
    df["end_year"] = pd.to_numeric(df["end_year"], errors="coerce").fillna(df["start_year"])
    df["start_month"] = pd.to_numeric(df.get("start_month"), errors="coerce").fillna(1).astype(int)
    df["end_month"] = pd.to_numeric(df.get("end_month"), errors="coerce").fillna(12).astype(int)
    return df[df["start_year"].notna()].copy()


DEPLOYMENT_PLATFORMS = ("CLAMPS1", "CLAMPS2")


def _iter_deployment_months(
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
) -> list[tuple[int, int]]:
    """Return (calendar year, month) pairs for each active month, inclusive."""
    months: list[tuple[int, int]] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def deployment_months_by_year_platform(root: Path) -> pd.DataFrame:
    """
    Count active deployment-months per calendar year, stacked by platform.
    Each calendar month counts at most once per platform (overlapping deployments are merged).
    A full year with both CLAMPS1 and CLAMPS2 deployed every month totals 24.
    """
    df = load_clamps_deployments(root)
    if df.empty:
        return pd.DataFrame(columns=list(DEPLOYMENT_PLATFORMS))
    active: dict[tuple[int, str], set[int]] = {}
    for _, r in df.iterrows():
        platform = str(r["platform"])
        for year, month in _iter_deployment_months(
            int(r["start_year"]),
            int(r["start_month"]),
            int(r["end_year"]),
            int(r["end_month"]),
        ):
            active.setdefault((year, platform), set()).add(month)
    rows = [{"year": year, "platform": platform, "months": len(months)} for (year, platform), months in active.items()]
    counts = (
        pd.DataFrame(rows)
        .pivot(index="year", columns="platform", values="months")
        .fillna(0)
        .reindex(columns=list(DEPLOYMENT_PLATFORMS), fill_value=0)
        .astype(int)
    )
    return counts.sort_index()


def deployments_by_year_platform(root: Path) -> pd.DataFrame:
    """Alias for deployment-month counts used by Fig. 8 variant."""
    return deployment_months_by_year_platform(root)


def deployments_by_year(root: Path) -> pd.Series:
    """Total CLAMPS deployment-months per calendar year."""
    pivot = deployment_months_by_year_platform(root)
    if pivot.empty:
        return pd.Series(dtype=int)
    return pivot.sum(axis=1)


def _campaign_match_key(name: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]", "", name.lower())


def match_deployment_to_heatmap_row(
    deploy_campaign: str,
    heatmap_rows: list[str],
    field_campaigns: list[str],
) -> str | None:
    """Map a deployment CSV campaign name to a heatmap row label, if present."""
    heatmap_set = set(heatmap_rows)
    key = _campaign_match_key(deploy_campaign)

    aliases = {
        "vortexse2016": "VORTEX-SE",
        "vortexse2017": "VORTEX-SE",
        "vortexse2018": "VORTEX-SE",
        "vortexsemeso": "VORTEX-SE",
        "minimpex": "mini-MPEX",
        "traceraq": "TRACER",
        "tracer": "TRACER",
        "splashsail": "SPLASH",
        "perils": "PERiLS",
        "cheesehead": "CHEESEHEAD",
        "blissful": "BLISSFUL",
        "laperate": "LAPSE-RATE",
        "pecan": "PECAN",
        "perdigao": "Perdigão",
        "lafe": "LAFE",
        "torus": "TORUS",
        "awaken": "AWAKEN",
        "pbltops": "PBLTops",
    }
    for alias_key, field_name in sorted(aliases.items(), key=lambda item: -len(item[0])):
        if key.startswith(alias_key) or alias_key in key:
            if field_name in heatmap_set:
                return field_name

    best: str | None = None
    best_len = 0
    for fc in field_campaigns:
        if fc not in heatmap_set:
            continue
        fc_key = _campaign_match_key(fc)
        if fc_key in key and len(fc_key) > best_len:
            best = fc
            best_len = len(fc_key)
    return best


def deployment_heatmap_platform_cells(
    root: Path,
    heatmap_rows: list[str],
    years: list[int],
    field_campaigns: list[str] | None = None,
) -> dict[tuple[int, int], set[str]]:
    """Map (row_index, col_index) to CLAMPS platforms deployed that campaign/year."""
    if field_campaigns is None:
        field_campaigns = load_campaign_names(root)
    row_idx = {name: i for i, name in enumerate(heatmap_rows)}
    col_idx = {int(y): j for j, y in enumerate(years)}
    cells: dict[tuple[int, int], set[str]] = {}
    df = load_clamps_deployments(root)
    for _, rec in df.iterrows():
        row_name = match_deployment_to_heatmap_row(str(rec["campaign"]), heatmap_rows, field_campaigns)
        if row_name is None:
            continue
        ri = row_idx[row_name]
        platform = str(rec["platform"])
        for year in range(int(rec["start_year"]), int(rec["end_year"]) + 1):
            if year in col_idx:
                key = (ri, col_idx[year])
                cells.setdefault(key, set()).add(platform)
    return cells


def deployment_heatmap_outline_cells(
    root: Path,
    heatmap_rows: list[str],
    years: list[int],
    field_campaigns: list[str] | None = None,
) -> set[tuple[int, int]]:
    """Return (row_index, col_index) for cells with a CLAMPS deployment in that campaign/year."""
    return set(deployment_heatmap_platform_cells(root, heatmap_rows, years, field_campaigns))


NO_CAMPAIGN_TAG = "(no campaign tag)"
MULTI_CAMPAIGN_ROW = "Multiple campaigns"


def campaigns_in_text(text: str, campaign_names: list[str]) -> list[str]:
    """Return campaign names found in free text (case-sensitive token matching)."""
    from clamps_biblio.field_campaigns import campaigns_in_text as _campaigns_in_text

    return _campaigns_in_text(text, campaign_names)


def _campaigns_from_anchor_dois(doi: str, campaign_names: list[str], root: Path) -> list[str]:
    """Map a work DOI to campaign(s) listed in campaign_anchors.yaml anchor_dois."""
    key = normalize_doi(doi)
    if not key:
        return []
    anchor_path = (root / "data" / "campaign_anchors.yaml") if root is not None else None
    anchors = load_campaign_anchors(anchor_path)
    found: list[str] = []
    for camp, meta in anchors.get("campaigns", {}).items():
        if camp not in campaign_names:
            continue
        for anchor in meta.get("anchor_dois") or []:
            anchor_doi = normalize_doi(str(anchor.get("doi", "") or ""))
            if anchor_doi and anchor_doi == key:
                found.append(camp)
    return found


def _campaigns_from_discovery_source(src: str, campaign_names: list[str]) -> list[str]:
    """Parse campaign labels embedded in discovery_source strings."""
    found: list[str] = []
    if src.startswith("campaign_clamps:"):
        label = src.split(":", 1)[-1]
        camp = label.split("+", 1)[0].strip()
        if camp in campaign_names:
            found.append(camp)
    if src.startswith("channel_"):
        # e.g. channel_b:B2:LAPSE-RATE+Doppler lidar
        tail = src.split(":", 2)[-1]
        if ":" in tail and not tail.startswith("B"):
            tail = tail.split(":", 1)[-1]
        camp = tail.split("+", 1)[0].strip()
        if camp in campaign_names:
            found.append(camp)
    return found


def paper_campaigns(
    row: pd.Series,
    campaign_names: list[str],
    extra_text: str = "",
    root: Path | None = None,
) -> list[str]:
    """
    Best-guess campaign assignment from review corpus metadata and PDF signals.

    Priority for automatic labels:
    1. Campaign names in the title
    2. Discovery pipeline (campaign_clamps / channel_b sources)
    3. Anchor DOIs from campaign_anchors.yaml
    4. Abstract, topics, matched terms, and PDF mention context
    """
    found: set[str] = set()

    title = str(row.get("title", "") or "")
    found.update(campaigns_in_text(title, campaign_names))

    src = str(row.get("discovery_source", "") or "")
    found.update(_campaigns_from_discovery_source(src, campaign_names))

    if root is not None:
        found.update(_campaigns_from_anchor_dois(str(row.get("doi", "") or ""), campaign_names, root))

    body = " ".join(
        str(row.get(k, "") or "")
        for k in ("abstract", "topics", "discovery_match", "matched_terms", "institutions")
    )
    if extra_text:
        body = f"{body} {extra_text}"
    found.update(campaigns_in_text(body, campaign_names))

    return sorted(found) if found else [NO_CAMPAIGN_TAG]


def _collapse_non_specific_labels(labels: set[str]) -> set[str]:
    """Drop legacy Multiple campaigns bucket (no separate S1 row)."""
    out = set(labels)
    out.discard(MULTI_CAMPAIGN_ROW)
    return out


def paper_campaign_labels_s1(
    row: pd.Series,
    campaign_names: list[str],
    mention_contexts: dict[str, str] | None = None,
    root: Path | None = None,
) -> list[str]:
    """Campaign row labels for one paper (matches Supp. Fig. S1 heatmap assignment)."""
    extra = (mention_contexts or {}).get(str(row.get("openalex_id", "") or ""), "")
    labels = set(paper_campaigns(row, campaign_names, extra_text=extra, root=root))
    return _finalize_campaign_labels(labels)


NON_SPECIFIC_LABEL = "Multi/None"
CAMPAIGN_OVERRIDES_PATH = "data/campaign_review_overrides.csv"


def normalize_override_campaign(label: str, campaign_names: list[str]) -> str:
    """Map a reviewer target label to a canonical campaign or NO_CAMPAIGN_TAG."""
    text = str(label or "").strip()
    if not text or text in (NON_SPECIFIC_LABEL, "Non-Specific", NO_CAMPAIGN_TAG, MULTI_CAMPAIGN_ROW):
        return NO_CAMPAIGN_TAG
    if text in campaign_names:
        return text
    lower = text.lower()
    for name in campaign_names:
        if name.lower() == lower:
            return name
    from clamps_biblio.field_campaigns import SPEC_BY_NAME

    spec = SPEC_BY_NAME.get(text) or SPEC_BY_NAME.get(text.upper()) or SPEC_BY_NAME.get(text.title())
    if spec and spec.canonical in campaign_names:
        return spec.canonical
    return text


def load_campaign_review_overrides(root: Path) -> pd.DataFrame:
    path = root / CAMPAIGN_OVERRIDES_PATH
    cols = [
        "entry_key",
        "work_key",
        "source_campaign",
        "review_flag",
        "target_campaign",
        "title",
    ]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(path)
    for col in cols:
        if col not in df.columns:
            df[col] = ""
    return df[cols].fillna("")


def _finalize_campaign_labels(labels: set[str]) -> list[str]:
    """Non-Specific row only for untagged works; multi-campaign papers use named rows only."""
    labels = _collapse_non_specific_labels(set(labels))
    named = sorted(c for c in labels if c != NO_CAMPAIGN_TAG)
    if not named:
        return [NO_CAMPAIGN_TAG]
    return named


def paper_campaign_labels_adjusted(
    row: pd.Series,
    campaign_names: list[str],
    mention_contexts: dict[str, str] | None,
    overrides: pd.DataFrame,
    root: Path | None = None,
) -> list[str]:
    """S1 labels after manual remove/move overrides from campaign review."""
    labels = set(paper_campaign_labels_s1(row, campaign_names, mention_contexts, root=root))
    work_key = str(row.get("work_key", "") or "").strip()
    if not work_key or overrides.empty:
        return _finalize_campaign_labels(labels)

    work_ov = overrides[overrides["work_key"].astype(str) == work_key]
    manual_named: set[str] = set()
    manual_none = False

    for _, ov in work_ov.iterrows():
        src = str(ov.get("source_campaign", "") or "").strip()
        flag = str(ov.get("review_flag", "") or "").strip().lower()
        if flag == "r":
            if src in labels:
                labels.discard(src)
            elif src in (MULTI_CAMPAIGN_ROW, NON_SPECIFIC_LABEL):
                labels.discard(NO_CAMPAIGN_TAG)
        elif flag == "m":
            tgt = normalize_override_campaign(
                str(ov.get("target_campaign", "") or "").strip(),
                campaign_names,
            )
            if tgt == NO_CAMPAIGN_TAG:
                manual_none = True
            elif tgt in campaign_names:
                manual_named.add(tgt)

    if manual_named:
        return _finalize_campaign_labels(manual_named)
    if manual_none:
        return [NO_CAMPAIGN_TAG]
    return _finalize_campaign_labels(labels)


def _read_mentions_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def load_campaign_mention_contexts(root: Path) -> dict[str, str]:
    """Merge PDF mention snippets (text + HTML scans) keyed by openalex_id."""
    paths = (
        root / "output" / "clamps_text_mentions.csv",
        root / "output" / "clamps_publications_html_mentions.csv",
    )
    chunks: list[pd.DataFrame] = []
    for path in paths:
        df = _read_mentions_csv(path)
        if df.empty or "context" not in df.columns or "openalex_id" not in df.columns:
            continue
        part = df[["openalex_id", "context"]].copy()
        part["openalex_id"] = part["openalex_id"].astype(str).str.strip()
        chunks.append(part)

    if not chunks:
        return {}

    merged = pd.concat(chunks, ignore_index=True)
    merged = merged[merged["openalex_id"].astype(str).str.len() > 0]
    return (
        merged.groupby("openalex_id")["context"]
        .apply(lambda s: " ".join(s.astype(str)))
        .to_dict()
    )


def mention_context_by_paper(mentions: pd.DataFrame, root: Path | None = None) -> dict[str, str]:
    """Concatenate PDF mention context snippets per openalex_id."""
    if root is not None:
        return load_campaign_mention_contexts(root)

    if mentions.empty or "openalex_id" not in mentions.columns or "context" not in mentions.columns:
        return {}
    grouped = (
        mentions.groupby("openalex_id")["context"]
        .apply(lambda s: " ".join(s.astype(str)))
        .to_dict()
    )
    return grouped


def paper_signals(row: pd.Series) -> set[str]:
    signals: set[str] = set()
    for term in str(row.get("matched_terms", "") or "").split(";"):
        norm = normalize_signal(term)
        if norm:
            signals.add(norm)
    return signals


def _load_manual_hit_notes(root: Path) -> dict[str, str]:
    path = root / "data" / "manual_pdf_scan_hits.csv"
    if not path.exists():
        return {}
    hits = pd.read_csv(path)
    notes: dict[str, str] = {}
    for _, row in hits.iterrows():
        key = normalize_doi(str(row.get("doi", "")))
        if key:
            notes[key] = str(row.get("notes", "") or "").strip()
    return notes


def _validated_broad_pool_rows(root: Path, discovered: pd.DataFrame) -> pd.DataFrame:
    """Rows from broad scan pool that are approved for the all-works universe."""
    pool_path = root / "output" / "clamps_works_broad_scan_pool.csv"
    if not pool_path.exists():
        return pd.DataFrame()

    pool = pd.read_csv(pool_path)
    if pool.empty or "channel" not in pool.columns:
        return pd.DataFrame()

    validated = pool[
        pool["channel"].astype(str).map(channel_bucket).isin(VALIDATED_BROAD_POOL_BUCKETS)
    ].copy()
    if validated.empty:
        return pd.DataFrame()

    disc_by_doi: dict[str, dict[str, Any]] = {}
    if not discovered.empty and "doi" in discovered.columns:
        for _, row in discovered.iterrows():
            doi = normalize_doi(str(row.get("doi", "") or ""))
            if doi:
                disc_by_doi[doi] = row.to_dict()

    rows: list[dict[str, Any]] = []
    for _, pool_row in validated.iterrows():
        doi = normalize_doi(str(pool_row.get("doi", "") or ""))
        base = dict(disc_by_doi.get(doi, pool_row.to_dict()))
        base["discovery_source"] = str(pool_row.get("channel", "") or "")
        for field in ("title", "doi", "type"):
            val = pool_row.get(field)
            if val is not None and str(val).strip() and str(val).lower() != "nan":
                base[field] = val
        rows.append(base)

    return pd.DataFrame(rows)


def confirmation_reason(row: pd.Series, manual_notes: dict[str, str]) -> str:
    """Explain how/why a work counts as CLAMPS-confirmed (empty when not confirmed)."""
    if str(row.get("pdf_scan_status", "")) != "mentions_found":
        return ""
    strength = str(row.get("match_strength", "") or "").strip()
    if strength == "manual_verified":
        key = normalize_doi(str(row.get("doi", "")))
        if key in manual_notes and manual_notes[key]:
            return manual_notes[key]
        return "Manual review — CLAMPS hit confirmed"
    terms = str(row.get("matched_terms", "") or "").strip()
    if terms:
        return f"Automated PDF text scan ({strength}): {terms}"
    if strength:
        return f"Automated PDF text scan ({strength})"
    return "Automated PDF text scan"


def build_all_works_enriched(root: Path) -> pd.DataFrame:
    """One row per high-confidence channel work with confirmation labels."""
    frames = load_review_frames(root)
    works = frames["flagged_yd"].copy()
    manual_notes = _load_manual_hit_notes(root)

    validated = _validated_broad_pool_rows(root, frames["discovered"])
    if not validated.empty:
        hc_dois = {
            normalize_doi(str(d))
            for d in works["doi"].dropna().astype(str)
            if normalize_doi(str(d))
        }
        add = validated[
            ~validated["doi"].astype(str).map(lambda d: normalize_doi(d) in hc_dois)
        ]
        if not add.empty:
            scan_cols = frames["scan_log"][
                ["openalex_id", "doi", "status", "mention_count", "match_strength", "matched_terms"]
            ].rename(columns={"status": "pdf_scan_status", "mention_count": "pdf_mention_count"})
            add = add.merge(scan_cols, on=["openalex_id", "doi"], how="left")
            works = pd.concat([works, add], ignore_index=True)

    out = pd.DataFrame(
        {
            "title": works["title"],
            "type": works["type"],
            "source": works["discovery_source"],
            "doi": works["doi"],
            "confirmed": works["pdf_scan_status"].eq("mentions_found").map({True: "yes", False: "no"}),
            "confirmation_reason": works.apply(lambda r: confirmation_reason(r, manual_notes), axis=1),
        }
    )
    return out
