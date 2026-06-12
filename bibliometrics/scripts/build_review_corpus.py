#!/usr/bin/env python3
"""Build unified review-article corpus (articles, reports, datasets, theses)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.channel_config import load_ground_truth
from clamps_biblio.pdf_resolver import normalize_doi
from clamps_biblio.work_keys import channel_bucket, row_key

CORPUS_COLUMNS = [
    "work_key",
    "corpus_class",
    "corpus_source",
    "openalex_id",
    "title",
    "year",
    "doi",
    "openalex_type",
    "source_link",
    "institutions",
    "abstract",
    "discovery_source",
    "discovery_channel",
    "cited_by_count",
    "confidence_tier",
    "repo_id",
    "repo_handle",
    "pdf_url",
    "manual_flag",
]

ARTICLE_TYPES = frozenset({"article", "preprint", "review"})
EXCLUDED_HC_TYPES = frozenset({"dissertation", "peer-review"})


def _cell(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _row_from_dict(row: dict, *, corpus_class: str, corpus_source: str) -> dict:
    out = {col: "" for col in CORPUS_COLUMNS}
    for key, value in row.items():
        if key in out:
            out[key] = _cell(value)
    out["corpus_class"] = corpus_class
    out["corpus_source"] = corpus_source
    if not out["discovery_channel"]:
        out["discovery_channel"] = channel_bucket(out["discovery_source"])
    if not out["work_key"]:
        out["work_key"] = row_key(out)
    out["openalex_type"] = out["openalex_type"] or _cell(row.get("type"))
    return out


def load_publications(hc_path: Path) -> list[dict]:
    df = pd.read_csv(hc_path)
    rows: list[dict] = []
    for row in df.to_dict("records"):
        otype = _cell(row.get("type")).lower()
        if otype in EXCLUDED_HC_TYPES:
            continue
        if otype in ARTICLE_TYPES:
            corpus_class = "article"
        elif otype == "report":
            corpus_class = "report"
        elif otype == "dataset":
            continue
        else:
            continue
        item = _row_from_dict(row, corpus_class=corpus_class, corpus_source="hc_publications")
        item["openalex_type"] = otype
        rows.append(item)
    return rows


def load_datasets(deposits_path: Path) -> list[dict]:
    df = pd.read_csv(deposits_path)
    if "work_class" not in df.columns:
        return []
    subset = df[df["work_class"].astype(str).str.lower() == "x"]
    rows: list[dict] = []
    for row in subset.to_dict("records"):
        item = _row_from_dict(row, corpus_class="dataset", corpus_source="data_deposits")
        item["openalex_type"] = _cell(row.get("type")) or "dataset"
        rows.append(item)
    return rows


def _corpus_class_from_type(otype: str) -> str | None:
    if otype in ARTICLE_TYPES or otype == "peer-review":
        return "article"
    if otype == "report":
        return "report"
    if otype == "dataset":
        return "dataset"
    if otype == "dissertation":
        return "thesis"
    return None


def load_ground_truth_mandatory(discovered_path: Path, ground_truth_path: Path) -> list[dict]:
    """Include every ground-truth registry work (bypasses HC/PDF gate)."""
    if not discovered_path.exists():
        return []

    gt_dois: set[str] = set()
    if ground_truth_path.exists():
        gt = load_ground_truth(ground_truth_path)
        for doi in gt.get("doi", pd.Series(dtype=str)).dropna():
            key = normalize_doi(doi)
            if key:
                gt_dois.add(key)

    disc = pd.read_csv(discovered_path)
    rows: list[dict] = []
    for row in disc.to_dict("records"):
        doi = normalize_doi(row.get("doi"))
        src = str(row.get("discovery_source", "") or "")
        if doi not in gt_dois and "channel_g:ground_truth" not in src:
            continue
        otype = _cell(row.get("type")).lower()
        corpus_class = _corpus_class_from_type(otype)
        if corpus_class is None:
            continue
        item = _row_from_dict(
            row,
            corpus_class=corpus_class,
            corpus_source="ground_truth_mandatory",
        )
        item["openalex_type"] = otype or corpus_class
        rows.append(item)
    return rows


def load_theses(master_path: Path) -> list[dict]:
    df = pd.read_csv(master_path)
    subset = df[df["manual_flag"].astype(str).str.strip().str.lower() == "y"]
    rows: list[dict] = []
    for row in subset.to_dict("records"):
        item = _row_from_dict(row, corpus_class="thesis", corpus_source="theses_master")
        item["openalex_type"] = _cell(row.get("type")) or "dissertation"
        item["manual_flag"] = "y"
        if not item["work_key"]:
            item["work_key"] = _cell(row.get("work_key"))
        rows.append(item)
    return rows


def dedupe_rows(rows: list[dict]) -> list[dict]:
    """Keep first occurrence per work_key; thesis > dataset > report > article priority."""
    priority = {"thesis": 0, "dataset": 1, "report": 2, "article": 3}
    ordered = sorted(rows, key=lambda r: priority.get(r["corpus_class"], 9))
    seen: set[str] = set()
    out: list[dict] = []
    for row in ordered:
        key = row["work_key"]
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hc",
        type=Path,
        default=ROOT / "output" / "clamps_papers_high_confidence_channels_with_pdfs.csv",
    )
    parser.add_argument(
        "--deposits",
        type=Path,
        default=ROOT / "output" / "clamps_data_deposits.csv",
    )
    parser.add_argument(
        "--theses",
        type=Path,
        default=ROOT / "output" / "clamps_theses_master_list.csv",
    )
    parser.add_argument(
        "--discovered",
        type=Path,
        default=ROOT / "output" / "clamps_papers_discovered_channels.csv",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=ROOT / "data" / "ground_truth_clamps_papers.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output" / "clamps_review_corpus.csv",
    )
    args = parser.parse_args()

    for label, path in (
        ("HC publications", args.hc),
        ("Data deposits", args.deposits),
        ("Theses master", args.theses),
    ):
        if not path.exists():
            print(f"Missing {label}: {path}")
            sys.exit(1)

    pubs = load_publications(args.hc)
    datasets = load_datasets(args.deposits)
    theses = load_theses(args.theses)
    gt_mandatory = load_ground_truth_mandatory(args.discovered, args.ground_truth)
    merged = dedupe_rows(pubs + datasets + theses + gt_mandatory)

    df = pd.DataFrame(merged, columns=CORPUS_COLUMNS)
    df = df.sort_values(["corpus_class", "year", "title"], na_position="last")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)

    print(f"Wrote {len(df)} works -> {args.output}")
    print("\nBy corpus_class:")
    print(df["corpus_class"].value_counts().sort_index().to_string())
    print("\nBy corpus_source:")
    print(df["corpus_source"].value_counts().sort_index().to_string())
    dupes = len(pubs) + len(datasets) + len(theses) + len(gt_mandatory) - len(merged)
    if dupes:
        print(f"\nDeduped {dupes} duplicate work_key(s) across sources.")
    gt_in = int((df["corpus_source"] == "ground_truth_mandatory").sum())
    print(f"\nGround-truth mandatory rows in corpus: {gt_in}")


if __name__ == "__main__":
    main()
