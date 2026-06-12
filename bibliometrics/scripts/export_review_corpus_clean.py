#!/usr/bin/env python3
"""Export a Zenodo-ready review corpus with campaign labels and inclusion metadata."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.channel_config import load_dataset_dois, load_ground_truth
from clamps_biblio.review_metrics_data import (
    NO_CAMPAIGN_TAG,
    load_campaign_names,
    load_campaign_review_overrides,
    load_corpus_review_frames,
    mention_context_by_paper,
    paper_campaign_labels_adjusted,
    paper_campaign_labels_s1,
)
from clamps_biblio.pdf_resolver import normalize_doi

NON_SPECIFIC_LABEL = "Multi/None"

CORPUS_SOURCE_LABELS = {
    "hc_publications": "High-confidence publication",
    "ground_truth_mandatory": "Ground-truth registry (mandatory)",
    "data_deposits": "Validated data deposit",
    "theses_master": "Manually accepted thesis",
}

WORK_TYPE_LABELS = {
    "article": "Article",
    "report": "Report",
    "dataset": "Dataset",
    "thesis": "Thesis",
}


def _clean_str(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _display_campaigns(labels: list[str]) -> str:
    out = [NON_SPECIFIC_LABEL if lab == NO_CAMPAIGN_TAG else lab for lab in labels]
    return "; ".join(out)


def _inclusion_detail(row: pd.Series, seed_dois: set[str], gt_dois: set[str]) -> str:
    source = str(row.get("corpus_source", "") or "")
    doi = normalize_doi(row.get("doi")).lower()
    base = CORPUS_SOURCE_LABELS.get(source, source)
    if source == "data_deposits" and doi in seed_dois:
        return "Seed dataset DOI registry (mandatory)"
    if source == "ground_truth_mandatory" or doi in gt_dois:
        return "Ground-truth registry (mandatory)"
    return base


def build_clean_corpus(root: Path) -> pd.DataFrame:
    frames = load_corpus_review_frames(root)
    df = frames["flagged_yd"].copy()
    campaigns = load_campaign_names(root)
    mentions = mention_context_by_paper(frames["mentions"], root=root)
    overrides = load_campaign_review_overrides(root)
    reviewed_keys = set(overrides["work_key"].astype(str).str.strip())

    gt_dois = {
        normalize_doi(d).lower()
        for d in load_ground_truth(root / "data" / "ground_truth_clamps_papers.csv")["doi"]
        if normalize_doi(d)
    }
    seed_dois = {normalize_doi(d).lower() for d in load_dataset_dois() if normalize_doi(d)}

    rows: list[dict] = []
    for _, row in df.iterrows():
        auto = paper_campaign_labels_s1(row, campaigns, mentions, root=root)
        final = paper_campaign_labels_adjusted(row, campaigns, mentions, overrides, root=root)
        doi = normalize_doi(row.get("doi"))
        year = row.get("year", "")
        if pd.notna(year):
            try:
                year = int(float(year))
            except (TypeError, ValueError):
                year = ""

        rows.append(
            {
                "work_key": str(row.get("work_key", "") or "").strip(),
                "doi": doi,
                "openalex_id": str(row.get("openalex_id", "") or "").strip(),
                "title": str(row.get("title", "") or "").strip(),
                "year": year,
                "work_type": WORK_TYPE_LABELS.get(
                    str(row.get("corpus_class", "") or ""), str(row.get("corpus_class", "") or "")
                ),
                "corpus_class": str(row.get("corpus_class", "") or "").strip(),
                "corpus_source": str(row.get("corpus_source", "") or "").strip(),
                "inclusion_pathway": _inclusion_detail(row, seed_dois, gt_dois),
                "in_ground_truth_registry": "yes"
                if doi.lower() in gt_dois
                or str(row.get("corpus_source", "")) == "ground_truth_mandatory"
                else "no",
                "in_seed_dataset_registry": "yes"
                if doi.lower() in seed_dois and str(row.get("corpus_class", "")) == "dataset"
                else "no",
                "discovery_channel": str(row.get("discovery_channel", "") or "").strip(),
                "discovery_source": str(row.get("discovery_source", "") or "").strip(),
                "confidence_tier": str(row.get("confidence_tier", "") or "").strip(),
                "campaign_labels_auto": _display_campaigns(auto),
                "campaign_labels_final": _display_campaigns(final),
                "manual_campaign_review": "yes"
                if str(row.get("work_key", "") or "").strip() in reviewed_keys
                else "no",
                "source_link": _clean_str(row.get("source_link")),
                "pdf_url": _clean_str(row.get("pdf_url")),
                "cited_by_count": row.get("cited_by_count", ""),
                "openalex_type": _clean_str(row.get("openalex_type")),
                "manual_thesis_flag": _clean_str(row.get("manual_flag")),
            }
        )

    out = pd.DataFrame(rows)
    out = out.sort_values(["year", "work_type", "title"], na_position="last")
    for col in ("year", "cited_by_count"):
        nums = pd.to_numeric(out[col], errors="coerce")
        out[col] = nums.astype("Int64").astype(object).where(pd.notna(nums), "")
    out = out.fillna("")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output" / "clamps_review_corpus_clean.csv",
    )
    parser.add_argument(
        "--readme",
        type=Path,
        default=ROOT / "output" / "clamps_review_corpus_clean_README.txt",
    )
    args = parser.parse_args()

    df = build_clean_corpus(ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)

    readme = f"""CLAMPS review corpus (clean export)
=====================================
File: {args.output.name}
Works: {len(df)}

This file supports the bibliometric figures in the CLAMPS review paper.
One row per work in the finalized review corpus.

Column guide
------------
work_key              Unique identifier (doi:… or openalex:…)
doi                   Digital Object Identifier (normalized)
openalex_id           OpenAlex work URL/id
title                 Work title
year                  Publication/deposit year
work_type             Article | Report | Dataset | Thesis
corpus_class          Internal class (article/report/dataset/thesis)
corpus_source         Pipeline source (hc_publications, ground_truth_mandatory,
                      data_deposits, theses_master)
inclusion_pathway     Human-readable inclusion rule applied
in_ground_truth_registry  yes if listed in data/ground_truth_clamps_papers.csv
in_seed_dataset_registry  yes if listed in data/clamps_dataset_dois.txt (datasets)
discovery_channel     Discovery channel bucket (A–H, G=ground truth)
discovery_source      Full discovery provenance string
confidence_tier       Discovery confidence (high/medium/low)
campaign_labels_auto  Campaign tags from automated rules (title, discovery,
                      anchors, abstract, PDF mentions)
campaign_labels_final Campaign tags after manual review overrides (Supp. Fig. S1)
manual_campaign_review yes if work appears in data/campaign_review_overrides.csv
source_link           Landing page or publisher link
pdf_url               Resolved PDF URL when available
cited_by_count        OpenAlex citation count at discovery time
openalex_type         OpenAlex work type
manual_thesis_flag    y for manually accepted theses

Build command
-------------
  python scripts/ensure_mandatory_corpus_inputs.py
  python scripts/build_review_corpus.py
  python scripts/export_review_corpus_clean.py

Counts by work_type
-------------------
{df['work_type'].value_counts().sort_index().to_string()}

Counts by inclusion_pathway
---------------------------
{df['inclusion_pathway'].value_counts().to_string()}
"""
    args.readme.write_text(readme, encoding="utf-8")

    print(f"Wrote {len(df)} works -> {args.output}")
    print(f"Wrote column guide -> {args.readme}")
    print("\nBy work_type:")
    print(df["work_type"].value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
