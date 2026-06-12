#!/usr/bin/env python3
"""Build a publications-only HTML scrape queue (Option B).

Excludes datasets, thesis repos, Zenodo deposits, and repository landing pages.
Keeps journal/preprint HTML targets (AMS, Copernicus, Wiley, etc.).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.deposit_classifications import is_publication_override, is_search_excluded
from clamps_biblio.html_resolver import html_fulltext_target

SKIP_PUBLISHERS = frozenset({"zenodo", "repository", "authority", "scholarworks"})
SKIP_REASONS = frozenset({"repository_landing"})


def is_thesis_row(row: dict) -> bool:
    typ = str(row.get("type", "") or "").lower()
    src = str(row.get("discovery_source", "") or "")
    return typ == "dissertation" or src.startswith("channel_h")


def include_row(row: dict, *, institutional_network: bool) -> tuple[bool, str | None]:
    if is_search_excluded(row):
        return False, None
    target = html_fulltext_target(row, institutional_network=institutional_network)
    if is_publication_override(row):
        if target:
            return True, target.publisher
        return False, None
    if str(row.get("type", "") or "").lower() == "dataset":
        return False, None
    if is_thesis_row(row):
        return False, None
    if not target:
        return False, None
    if target.publisher in SKIP_PUBLISHERS or target.reason in SKIP_REASONS:
        return False, None
    return True, target.publisher


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "output" / "clamps_papers_discovered_channels.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output" / "clamps_publications_html_queue.csv",
    )
    parser.add_argument(
        "--no-institutional-network",
        action="store_true",
        help="Match scan_pdfs.py --no-institutional-network routing",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    institutional_network = not args.no_institutional_network

    kept_rows: list[dict] = []
    publishers: Counter[str] = Counter()
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        ok, publisher = include_row(row_dict, institutional_network=institutional_network)
        if ok:
            kept_rows.append(row_dict)
            publishers[publisher or "unknown"] += 1

    out = pd.DataFrame(kept_rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    print(f"Input:  {len(df)} rows from {args.input.name}")
    print(f"Output: {len(out)} publication HTML targets -> {args.output}")
    print("\nBy publisher:")
    for pub, count in publishers.most_common():
        print(f"  {count:4d}  {pub}")


if __name__ == "__main__":
    main()
