#!/usr/bin/env python3
"""Export data-product / repository deposit rows from the discovery CSV.

These are excluded from the publications HTML queue (Option B): Zenodo records,
NCAR/EOL dataset DOIs, Authority deposits, and other non-journal data products.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.deposit_classifications import WORK_CLASS_COLUMN
from clamps_biblio.html_resolver import html_fulltext_target
from clamps_biblio.pdf_resolver import normalize_doi

DATASET_DOI_PREFIXES = (
    "10.5281/",  # Zenodo
    "10.5439/",  # NCAR/EOL
    "10.21947/",  # Authority
    "10.5067/",  # NASA
    "10.7910/",  # Harvard Dataverse
    "10.5061/",  # Dataverse
    "10.17632/",  # Mendeley Data
    "10.5445/",  # PANGAEA
    "10.25394/",  # Figshare / PGS
)


def is_thesis_row(row: dict) -> bool:
    typ = str(row.get("type", "") or "").lower()
    src = str(row.get("discovery_source", "") or "")
    return typ == "dissertation" or src.startswith("channel_h")


def classify_data_deposit(row: dict) -> tuple[bool, str]:
    if is_thesis_row(row):
        return False, ""
    typ = str(row.get("type", "") or "").lower()
    doi = normalize_doi(row.get("doi"))
    src = str(row.get("discovery_source", "") or "")

    if typ == "dataset":
        return True, "type:dataset"
    if src.startswith("channel_c:dataset"):
        return True, "channel_c:dataset"
    if "dataset_registry" in src:
        return True, "channel_c:dataset_registry"
    for prefix in DATASET_DOI_PREFIXES:
        if doi.startswith(prefix):
            return True, f"doi_prefix:{prefix.rstrip('/')}"
    target = html_fulltext_target(row, institutional_network=True)
    if target and target.publisher in {"zenodo", "authority"} and target.reason == "repository_landing":
        return True, f"html:{target.publisher}"
    return False, ""


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
        default=ROOT / "output" / "clamps_data_deposits.csv",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    existing_classes: dict[str, str] = {}
    if args.output.exists():
        prev = pd.read_csv(args.output)
        if WORK_CLASS_COLUMN not in prev.columns and "Unnamed: 2" in prev.columns:
            prev = prev.rename(columns={"Unnamed: 2": WORK_CLASS_COLUMN})
        if WORK_CLASS_COLUMN in prev.columns:
            for _, row in prev.iterrows():
                doi = normalize_doi(row.get("doi"))
                cls = str(row.get(WORK_CLASS_COLUMN, "") or "").strip()
                if doi and cls:
                    existing_classes[doi] = cls

    rows: list[dict] = []
    reasons: Counter[str] = Counter()

    for _, row in df.iterrows():
        row_dict = row.to_dict()
        is_deposit, reason = classify_data_deposit(row_dict)
        if not is_deposit:
            continue
        target = html_fulltext_target(row_dict, institutional_network=True)
        row_dict["deposit_reason"] = reason
        row_dict["html_publisher"] = target.publisher if target else ""
        row_dict["html_url"] = target.url if target else ""
        row_dict["html_reason"] = target.reason if target else ""
        doi = normalize_doi(row_dict.get("doi"))
        row_dict[WORK_CLASS_COLUMN] = existing_classes.get(doi, "")
        rows.append(row_dict)
        reasons[reason] += 1

    out = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    print(f"Input:  {len(df)} rows from {args.input.name}")
    print(f"Output: {len(out)} data deposits -> {args.output}")
    print("\nBy deposit_reason:")
    for reason, count in reasons.most_common():
        print(f"  {count:4d}  {reason}")


if __name__ == "__main__":
    main()
