#!/usr/bin/env python3
"""Ensure ground-truth seed datasets are catalogued as validated deposits (work_class=x)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.deposit_classifications import WORK_CLASS_COLUMN
from clamps_biblio.openalex_client import OpenAlexClient
from clamps_biblio.pdf_resolver import normalize_doi

DATASET_DOI_SOURCE = "channel_c:dataset_registry"


def load_seed_dois(path: Path) -> list[str]:
    dois: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.split("#", 1)[0].strip()
        if not text:
            continue
        doi = normalize_doi(text)
        if doi:
            dois.append(doi)
    return dois


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seeds",
        type=Path,
        default=ROOT / "data" / "clamps_dataset_dois.txt",
    )
    parser.add_argument(
        "--deposits",
        type=Path,
        default=ROOT / "output" / "clamps_data_deposits.csv",
    )
    args = parser.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    mailto = (cfg.get("openalex") or {}).get("mailto")
    delay = float((cfg.get("discovery") or {}).get("openalex_delay", 1.5))

    seeds = load_seed_dois(args.seeds)
    if args.deposits.exists():
        dep = pd.read_csv(args.deposits)
    else:
        dep = pd.DataFrame()

    if WORK_CLASS_COLUMN not in dep.columns:
        dep[WORK_CLASS_COLUMN] = ""

    by_doi: dict[str, pd.Series] = {}
    for _, row in dep.iterrows():
        doi = normalize_doi(row.get("doi"))
        if doi:
            by_doi[doi.lower()] = row

    promoted = 0
    for doi in seeds:
        key = doi.lower()
        if key in by_doi:
            row = by_doi[key].copy()
            if str(row.get(WORK_CLASS_COLUMN, "") or "").strip().lower() != "x":
                row[WORK_CLASS_COLUMN] = "x"
                row["deposit_reason"] = row.get("deposit_reason") or "seed_doi_promoted"
                by_doi[key] = row
                promoted += 1

    client = OpenAlexClient(mailto=mailto, request_delay=delay)
    added = 0
    stubbed = 0

    def _resolve_work(doi: str) -> dict | None:
        work = client.work_by_doi(doi)
        if work:
            return work
        lower = doi.lower()
        if lower != doi:
            return client.work_by_doi(lower)
        return None

    for doi in seeds:
        key = doi.lower()
        if key in by_doi:
            continue
        work = _resolve_work(doi)
        if work:
            flat = OpenAlexClient.flatten_work(work, discovery_source=DATASET_DOI_SOURCE)
            flat[WORK_CLASS_COLUMN] = "x"
            flat["deposit_reason"] = "seed_doi_registry"
            flat["confidence_tier"] = "high"
            flat["type"] = flat.get("type") or "dataset"
            by_doi[key] = pd.Series(flat)
            added += 1
            continue
        by_doi[key] = pd.Series(
            {
                "doi": key,
                "title": f"CLAMPS dataset registry entry ({key})",
                "type": "dataset",
                WORK_CLASS_COLUMN: "x",
                "discovery_source": DATASET_DOI_SOURCE,
                "deposit_reason": "seed_doi_stub",
                "confidence_tier": "medium",
            }
        )
        stubbed += 1

    out = pd.DataFrame(list(by_doi.values()))
    args.deposits.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.deposits, index=False)

    x_count = int((out[WORK_CLASS_COLUMN].astype(str).str.lower() == "x").sum())
    print(f"Seed DOIs listed: {len(seeds)}")
    print(f"Deposits rows: {len(out)} (work_class=x: {x_count})")
    print(f"Promoted existing rows to x: {promoted}")
    print(f"Added from OpenAlex: {added}")
    print(f"Stubbed (no OpenAlex metadata): {stubbed}")


if __name__ == "__main__":
    main()
