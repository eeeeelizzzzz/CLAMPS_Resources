#!/usr/bin/env python3
"""Merge channel discovery CSVs (A–G + F + H) into one deduped output."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.config import load_config
from clamps_biblio.discovered_channels import merge_discovery_sources
from clamps_biblio.relevance import qualifies_strict_high_confidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        type=Path,
        default=ROOT / "output" / "clamps_papers_discovered_channels.csv",
    )
    parser.add_argument(
        "--thesis-openalex",
        type=Path,
        default=ROOT / "output" / "clamps_theses_discovered_openalex.csv",
    )
    parser.add_argument(
        "--thesis-repos",
        type=Path,
        default=ROOT / "output" / "clamps_theses_discovered_repos.csv",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=ROOT / "data" / "ground_truth_clamps_papers.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output" / "clamps_papers_discovered_channels.csv",
    )
    parser.add_argument(
        "--skip-ground-truth",
        action="store_true",
        help="Do not inject missing rows from ground_truth_clamps_papers.csv",
    )
    args = parser.parse_args()

    if not args.base.exists():
        print(f"Base discovery CSV missing: {args.base}")
        return

    merged, stats = merge_discovery_sources(
        ROOT,
        base_path=args.base,
        thesis_repos_path=args.thesis_repos,
        thesis_openalex_path=args.thesis_openalex,
        ground_truth_path=args.ground_truth,
        include_ground_truth=not args.skip_ground_truth,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(args.output, index=False)

    cfg = load_config()
    high = merged[merged.apply(lambda r: qualifies_strict_high_confidence(r, cfg.ambiguous_campaigns), axis=1)]
    high_path = args.output.parent / "clamps_papers_high_confidence_channels.csv"
    high.to_csv(high_path, index=False)

    diss = merged[merged["type"].astype(str) == "dissertation"] if "type" in merged.columns else merged.iloc[0:0]

    print("Input rows:")
    for key in (
        "base_rows",
        "thesis_openalex_rows",
        "thesis_repos_rows",
        "ground_truth_overlay",
        "ground_truth_added",
        "ground_truth_promoted",
    ):
        if key in stats:
            print(f"  {key}: {stats[key]}")
    print(f"  raw_rows: {stats['raw_rows']}")
    print(f"  deduped_rows: {stats['deduped_rows']}")
    print(f"\nMerged: {len(merged)} unique works -> {args.output}")
    print(f"High-confidence: {len(high)} -> {high_path}")
    print(f"Dissertations in merged set: {len(diss)}")
    if "discovery_source" in merged.columns:
        ch = merged["discovery_source"].str.split(":").str[0]
        print("\nBy channel prefix:")
        print(ch.value_counts().to_string())


if __name__ == "__main__":
    main()
