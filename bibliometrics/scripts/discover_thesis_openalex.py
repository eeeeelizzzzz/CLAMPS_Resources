#!/usr/bin/env python3
"""Channel F: OpenAlex thesis/dissertation discovery via thesis_institutions.yaml."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.channel_config import load_discovery_channels, load_topic_filters
from clamps_biblio.clamps_signals import all_signals_in_text, has_clamps_signal
from clamps_biblio.config import load_config
from clamps_biblio.openalex_client import OpenAlexClient
from clamps_biblio.relevance import metadata_text, score_work
from clamps_biblio.repository_links import repository_signals_in_text
from clamps_biblio.thesis_config import iter_institutions, load_thesis_institutions
from clamps_biblio.topic_filters import is_excluded


def dedupe_rows(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for row in rows:
        key = row.get("openalex_id") or row.get("doi") or row.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def thesis_phrases(channel_a: dict, cfg) -> list[str]:
    phrases = list(channel_a.get("phrases") or [])
    if not phrases:
        phrases = [
            p for p in cfg.search_phrases
            if p.strip().upper() != "CLAMPS"
        ]
    return phrases


def build_institution_queries(
    inst: dict,
    phrases: list[str],
    campaigns: list[str],
) -> list[tuple[str, str]]:
    mode = inst.get("search_mode", "full_phrases")
    name = inst.get("name", "?")
    queries: list[tuple[str, str]] = []

    if mode == "full_phrases":
        for phrase in phrases:
            q = f'"{phrase.strip().strip(chr(34))}"'
            label = f"{name}+{phrase}"
            queries.append((q, label))
    elif mode == "campaign_compounds":
        facility = ["CLAMPS-1", "CLAMPS-2"]
        for campaign in campaigns:
            camp_q = f'"{campaign}"'
            for fac in facility:
                q = f'{camp_q} "{fac}"'
                label = f"{name}+{campaign}+{fac}"
                queries.append((q, label))
    return queries


def discover_channel_f(
    client: OpenAlexClient,
    institutions: list[dict],
    phrases: list[str],
    campaigns: list[str],
    work_types: list[str],
    from_year: int,
    *,
    require_clamps_signal: bool = True,
) -> list[dict]:
    rows: list[dict] = []
    skipped = 0
    query_count = 0

    for inst in institutions:
        oid = inst.get("openalex_id")
        if not oid:
            skipped += 1
            continue
        name = inst.get("name", oid)
        queries = build_institution_queries(inst, phrases, campaigns)
        type_filter = "|".join(work_types) if work_types else "dissertation"
        extra = [f"institutions.id:{oid}", f"type:{type_filter}"]

        for query, label in queries:
            query_count += 1
            results = client.search_works(
                query,
                from_year=from_year,
                max_results=100,
                extra_filters=extra,
            )
            if results:
                print(f"  {label}: {len(results)} works")
            for work in results:
                row = client.flatten_work(work, discovery_source=f"channel_f:{label}")
                if require_clamps_signal and not has_clamps_signal(metadata_text(row)):
                    continue
                rows.append(row)

    print(f"  Institutions skipped (no openalex_id): {skipped}")
    print(f"  Total OpenAlex queries: {query_count}")
    return rows


def enrich_rows(rows: list[dict], cfg) -> list[dict]:
    for row in rows:
        score, tier = score_work(row)
        row["relevance_score"] = score
        row["confidence_tier"] = tier
        meta_terms = all_signals_in_text(metadata_text(row))
        meta_terms.extend(repository_signals_in_text(metadata_text(row), cfg.data_repository_links))
        row["metadata_matched_terms"] = "; ".join(dict.fromkeys(meta_terms))
        row["discovery_match"] = str(row.get("discovery_source", "")).split(":", 1)[-1]
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Channel F OpenAlex thesis discovery.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--institutions-file",
        type=Path,
        default=ROOT / "data" / "thesis_institutions.yaml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output" / "clamps_theses_discovered_openalex.csv",
    )
    parser.add_argument("--tier", action="append", dest="tiers", help="Limit to tier name(s)")
    parser.add_argument("--no-topic-filter", action="store_true")
    parser.add_argument("--no-clamps-filter", action="store_true", help="Keep all dissertation keyword hits")
    parser.add_argument("--openalex-delay", type=float, default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    channels_cfg = load_discovery_channels()
    thesis_cfg = load_thesis_institutions(args.institutions_file)
    topic_filters = load_topic_filters()

    disc = thesis_cfg.get("discovery") or {}
    from_year = int(disc.get("from_year", 2015))
    work_types = list(disc.get("work_types") or ["dissertation"])

    institutions = iter_institutions(thesis_cfg)
    if args.tiers:
        wanted = set(args.tiers)
        institutions = [i for i in institutions if i.get("tier") in wanted]

    channel_a = (channels_cfg.get("channels") or {}).get("A", {})
    phrases = thesis_phrases(channel_a, cfg)
    campaigns = list(cfg.field_campaigns)

    openalex_delay = args.openalex_delay if args.openalex_delay is not None else cfg.openalex_delay
    client = OpenAlexClient(mailto=cfg.openalex_mailto, request_delay=openalex_delay)

    print(f"Channel F: {len(institutions)} institutions | phrases: {len(phrases)} | from {from_year}")
    rows = discover_channel_f(
        client,
        institutions,
        phrases,
        campaigns,
        work_types,
        from_year,
        require_clamps_signal=not args.no_clamps_filter,
    )
    print(f"Raw hits: {len(rows)}")
    rows = dedupe_rows(rows)
    print(f"After dedupe: {len(rows)}")

    if not args.no_topic_filter:
        kept, dropped = [], []
        for row in rows:
            excluded, reason = is_excluded(row, topic_filters)
            if excluded:
                row = dict(row)
                row["exclusion_reason"] = reason
                dropped.append(row)
            else:
                kept.append(row)
        rows = kept
        print(f"After topic filter: {len(rows)} kept, {len(dropped)} dropped")
        if dropped:
            pd.DataFrame(dropped).to_csv(
                args.output.parent / "clamps_theses_openalex_excluded_by_topic.csv",
                index=False,
            )

    rows = enrich_rows(rows, cfg)
    df = pd.DataFrame(rows)
    if not df.empty:
        tier_order = {"high": 0, "medium": 1, "low": 2}
        df["_tier_order"] = df["confidence_tier"].map(tier_order)
        df = df.sort_values(
            ["_tier_order", "relevance_score", "year", "title"],
            ascending=[True, False, False, True],
            na_position="last",
        ).drop(columns="_tier_order")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Saved {len(df)} thesis hits -> {args.output}")
    if not df.empty:
        print(df["confidence_tier"].value_counts().to_string())


if __name__ == "__main__":
    main()
