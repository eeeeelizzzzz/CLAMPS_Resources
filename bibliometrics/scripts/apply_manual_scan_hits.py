#!/usr/bin/env python3
"""Apply human-verified CLAMPS hits to scan log and mentions (failed automated scans)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.config import load_config


def normalize_doi(doi: str) -> str:
    text = str(doi or "").strip().lower()
    if text.startswith("https://doi.org/"):
        text = text[len("https://doi.org/") :]
    return text.rstrip("/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Label manual PDF scan hits in output CSVs.")
    parser.add_argument(
        "--hits",
        type=Path,
        default=ROOT / "data" / "manual_pdf_scan_hits.csv",
    )
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()

    if not args.hits.exists():
        print(f"Hits file not found: {args.hits}")
        sys.exit(1)

    cfg = load_config(args.config)
    hits = pd.read_csv(args.hits)
    log_path = cfg.output_dir / cfg.scan_log_csv
    mentions_path = cfg.output_dir / cfg.mentions_csv

    log = pd.read_csv(log_path)
    mentions = pd.read_csv(mentions_path) if mentions_path.exists() else pd.DataFrame()
    log["error"] = log["error"].astype("string")

    log["doi_norm"] = log["doi"].astype(str).map(normalize_doi)
    hit_dois = {normalize_doi(row["doi"]): row for _, row in hits.iterrows()}

    updated = 0
    new_mentions: list[dict] = []
    for doi_norm, hit in hit_dois.items():
        mask = log["doi_norm"] == doi_norm
        if not mask.any():
            # try without /v1 suffix etc.
            base = doi_norm.split("/v")[0]
            mask = log["doi_norm"].str.startswith(base)
        if not mask.any():
            print(f"WARNING: not in scan log: {hit['doi']}")
            continue

        idx = log.index[mask][0]
        row = log.loc[idx]
        if str(row.get("match_strength", "")) == "manual_verified":
            continue
        log.at[idx, "status"] = "mentions_found"
        log.at[idx, "mention_count"] = max(int(row.get("mention_count") or 0), 1)
        log.at[idx, "matched_terms"] = "manual_verified"
        log.at[idx, "match_strength"] = "manual_verified"
        log.at[idx, "error"] = pd.NA
        updated += 1

        already = False
        if not mentions.empty and "doi" in mentions.columns:
            m_norm = mentions["doi"].astype(str).map(normalize_doi)
            already = (m_norm == normalize_doi(row["doi"])).any()
        if not already:
            new_mentions.append(
                {
                    "title": row.get("title", hit.get("title", "")),
                    "doi": row.get("doi", hit["doi"]),
                    "openalex_id": row.get("openalex_id", ""),
                    "pdf_url": row.get("pdf_url", ""),
                    "pattern": "manual_verified",
                    "page": 0,
                    "context": str(hit.get("notes", "Human-verified CLAMPS hit")),
                }
            )

    log.drop(columns=["doi_norm"], inplace=True)
    log.to_csv(log_path, index=False)

    if new_mentions:
        mentions = pd.concat([mentions, pd.DataFrame(new_mentions)], ignore_index=True)
    mentions.to_csv(mentions_path, index=False)

    print(f"Updated {updated} row(s) in {log_path}")
    print(f"Added {len(new_mentions)} manual mention row(s) -> {mentions_path}")


if __name__ == "__main__":
    main()
