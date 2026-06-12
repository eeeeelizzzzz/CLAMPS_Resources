#!/usr/bin/env python3
"""Build one deduplicated master list of all discovered CLAMPS theses."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.work_keys import channel_bucket, row_key
from scripts.triage_thesis_repos import score_row

BASE_COLUMNS = [
    "work_key",
    "openalex_id",
    "title",
    "year",
    "doi",
    "type",
    "discovery_source",
    "discovery_channel",
    "discovery_match",
    "source_link",
    "repo_id",
    "repo_handle",
    "repo_platform",
    "confidence_tier",
    "institutions",
    "abstract",
    "in_main_discovery",
    "in_recovered_crawl",
    "in_review_queue",
    "source_pools",
    "review_tier",
    "manual_flag",
    "triage_score",
    "triage_bucket",
    "triage_reason",
]


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _row_dict(row: pd.Series) -> dict:
    return {k: row.get(k) for k in row.index}


def _prefer_row(existing: dict, incoming: dict) -> dict:
    """Fill missing fields in existing from incoming."""
    out = dict(existing)
    for key, value in incoming.items():
        if key in {"work_key", "source_pools", "in_main_discovery", "in_recovered_crawl", "in_review_queue"}:
            continue
        if pd.isna(out.get(key)) or str(out.get(key, "")).strip().lower() in {"", "nan", "none"}:
            if pd.notna(value) and str(value).strip().lower() not in {"", "nan", "none"}:
                out[key] = value
    return out


def _normalize_row(row: dict, *, pool: str) -> dict:
    out = dict(row)
    out["discovery_channel"] = channel_bucket(str(out.get("discovery_source", "") or ""))
    out.setdefault("type", "dissertation")
    pools = {p for p in str(out.get("source_pools", "") or "").split("|") if p}
    pools.add(pool)
    out["source_pools"] = "|".join(sorted(pools))
    out["in_main_discovery"] = "main" in pools
    out["in_recovered_crawl"] = "recovered" in pools
    out["in_review_queue"] = "review_queue" in pools
    return out


def build_master_list(root: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    out_dir = root / "output"
    disc = _load_csv(out_dir / "clamps_papers_discovered_channels.csv")
    recovered = _load_csv(out_dir / "clamps_theses_discovered_repos_recovered.csv")
    review = _load_csv(out_dir / "clamps_theses_review_queue.csv")

    by_key: dict[str, dict] = {}
    stats: dict[str, int] = {}

    main = disc[disc["type"].astype(str).str.lower() == "dissertation"].copy()
    stats["main_discovery_rows"] = len(main)

    for _, row in main.iterrows():
        key = row_key(_row_dict(row))
        entry = _normalize_row(_row_dict(row), pool="main")
        entry["work_key"] = key
        by_key[key] = entry

    for _, row in recovered.iterrows():
        key = row_key(_row_dict(row))
        incoming = _normalize_row(_row_dict(row), pool="recovered")
        incoming["work_key"] = key
        if key in by_key:
            by_key[key] = _prefer_row(by_key[key], incoming)
            pools = {p for p in by_key[key]["source_pools"].split("|") if p}
            pools.add("recovered")
            by_key[key]["source_pools"] = "|".join(sorted(pools))
        else:
            by_key[key] = incoming

    review_by_key: dict[str, dict] = {}
    for _, row in review.iterrows():
        key = row_key(_row_dict(row))
        review_by_key[key] = _row_dict(row)
        incoming = _normalize_row(_row_dict(row), pool="review_queue")
        incoming["work_key"] = key
        if key in by_key:
            by_key[key] = _prefer_row(by_key[key], incoming)
            pools = set(by_key[key]["source_pools"].split("|"))
            pools.add("review_queue")
            by_key[key]["source_pools"] = "|".join(sorted(pools))
        else:
            by_key[key] = incoming
        by_key[key]["in_review_queue"] = True

    rows: list[dict] = []
    for key, entry in by_key.items():
        pools = {p for p in str(entry.get("source_pools", "") or "").split("|") if p}
        entry["in_main_discovery"] = "main" in pools
        entry["in_recovered_crawl"] = "recovered" in pools
        entry["in_review_queue"] = "review_queue" in pools
        for bool_col in ("in_main_discovery", "in_recovered_crawl", "in_review_queue"):
            entry[bool_col] = "y" if entry[bool_col] else "n"

        rev = review_by_key.get(key, {})
        tier = str(rev.get("review_tier", "") or "").strip()
        flag = str(rev.get("Flag", "") or "").strip()
        entry["review_tier"] = "" if tier.lower() == "nan" else tier
        entry["manual_flag"] = "" if flag.lower() == "nan" else flag

        score, bucket, reason = score_row(pd.Series(entry))
        entry["triage_score"] = score
        entry["triage_bucket"] = bucket
        entry["triage_reason"] = reason
        rows.append(entry)

    df = pd.DataFrame(rows)
    for col in BASE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[BASE_COLUMNS].sort_values(["discovery_channel", "year", "title"], na_position="last")

    stats["unique_theses"] = len(df)
    stats["in_main_discovery"] = int((df["in_main_discovery"] == "y").sum())
    stats["recovered_only"] = int(
        ((df["in_recovered_crawl"] == "y") & (df["in_main_discovery"] == "n")).sum()
    )
    stats["review_queue_only"] = int(
        ((df["in_review_queue"] == "y") & (df["in_main_discovery"] == "n")).sum()
    )
    stats["with_manual_flag"] = int((df["manual_flag"] != "").sum())
    stats["with_review_tier"] = int((df["review_tier"] != "").sum())
    return df, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output" / "clamps_theses_master_list.csv",
    )
    args = parser.parse_args()

    df, stats = build_master_list(ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)

    print(f"Wrote {len(df)} unique theses -> {args.output}")
    print(f"  Main discovery subset:     {stats['in_main_discovery']}")
    print(f"  Recovered-only additions:  {stats['recovered_only']}")
    print(f"  Review-queue-only adds:    {stats['review_queue_only']}")
    print(f"  With manual_flag:          {stats['with_manual_flag']}")
    print(f"  With review_tier:          {stats['with_review_tier']}")
    print("\nBy discovery_channel:")
    print(df["discovery_channel"].value_counts().to_string())
    print("\nBy triage_bucket:")
    print(df["triage_bucket"].value_counts().to_string())
    print("\nBy review_tier (non-empty):")
    print(df[df["review_tier"] != ""]["review_tier"].value_counts().to_string())
    print("\nBy manual_flag (non-empty):")
    print(df[df["manual_flag"] != ""]["manual_flag"].value_counts().to_string())


if __name__ == "__main__":
    main()
