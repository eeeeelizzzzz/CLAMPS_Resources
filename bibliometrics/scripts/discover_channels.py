#!/usr/bin/env python3
"""Channel-based CLAMPS discovery (A–G) using data/discovery_channels.yaml."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.channel_config import (
    load_author_seeds,
    load_campaign_anchors,
    load_dataset_dois,
    load_discovery_channels,
    load_ground_truth,
    load_topic_filters,
)
from clamps_biblio.config import load_config
from clamps_biblio.enrichment import enrich_rows
from clamps_biblio.openalex_client import OpenAlexClient
from clamps_biblio.field_campaigns import discovery_campaign_items
from clamps_biblio.relevance import qualifies_strict_high_confidence
from clamps_biblio.topic_filters import is_excluded

# Channel B budget: 2 facility × 3 instruments (B1) + 2 facility × 2 obs (B3) + 2 instrument-only (B2)
B_INSTRUMENTS_PRIMARY = ["remote profiler", "Doppler lidar", "AERI"]
B_INSTRUMENTS_B2 = ["remote profiler", "Doppler lidar"]
B_OBS_PRIMARY_COUNT = 2


def dedupe_works(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for row in rows:
        key = row.get("openalex_id") or row.get("doi") or row.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def build_channel_b_queries(campaign: str, channel_b: dict) -> list[tuple[str, str]]:
    facility_terms = channel_b.get("facility_terms", ["CLAMPS-1", "CLAMPS-2"])
    obs_terms = channel_b.get("observational_terms", ["boundary layer", "wind profile"])
    obs_subset = obs_terms[:B_OBS_PRIMARY_COUNT]
    queries: list[tuple[str, str]] = []

    for facility in facility_terms:
        for instrument in B_INSTRUMENTS_PRIMARY:
            q = f'"{campaign}" "{facility}" "{instrument}"'
            queries.append((q, f"B1:{campaign}+{facility}+{instrument}"))

    for facility in facility_terms:
        for obs in obs_subset:
            q = f'"{campaign}" "{facility}" "{obs}"'
            queries.append((q, f"B3:{campaign}+{facility}+{obs}"))

    for instrument in B_INSTRUMENTS_B2:
        q = f'"{campaign}" "{instrument}"'
        queries.append((q, f"B2:{campaign}+{instrument}"))

    return queries


def discover_channel_a(client: OpenAlexClient, phrases: list[str], from_year: int) -> list[dict]:
    rows: list[dict] = []
    for phrase in phrases:
        q = f'"{phrase.strip().strip(chr(34))}"'
        results = client.search_works(q, from_year=from_year, max_results=500)
        print(f"  Channel A '{phrase}': {len(results)} works")
        for work in results:
            rows.append(client.flatten_work(work, discovery_source=f"channel_a:{phrase}"))
    return rows


def discover_channel_b(
    client: OpenAlexClient,
    campaigns: dict,
    channel_b: dict,
) -> list[dict]:
    rows: list[dict] = []
    total_queries = 0
    for campaign, meta in discovery_campaign_items(campaigns):
        from_year = meta.get("floor_year", 2012)
        queries = build_channel_b_queries(campaign, channel_b)
        total_queries += len(queries)
        for query, label in queries:
            results = client.search_works(query, from_year=from_year, max_results=200)
            if results:
                print(f"  Channel B '{query}' (floor {from_year}): {len(results)} works")
            for work in results:
                rows.append(client.flatten_work(work, discovery_source=f"channel_b:{label}"))
    print(f"  Channel B total queries: {total_queries}")
    return rows


def discover_channel_c(
    client: OpenAlexClient,
    dataset_dois: list[str],
    grant_numbers: list[str],
    from_year: int,
) -> list[dict]:
    rows: list[dict] = []
    for doi in dataset_dois:
        work = client.work_by_doi(doi)
        if not work:
            continue
        citing = client.works_citing(work["id"])
        if citing:
            print(f"  Channel C cites dataset {doi}: {len(citing)} works")
        for cited in citing:
            rows.append(client.flatten_work(cited, discovery_source=f"channel_c:dataset_cites:{doi}"))
        for found in client.search_works(doi, from_year=from_year, max_results=200):
            rows.append(client.flatten_work(found, discovery_source=f"channel_c:dataset_search:{doi}"))

    for grant in grant_numbers:
        results = client.search_works(grant, from_year=from_year, max_results=200)
        if results:
            print(f"  Channel C grant '{grant}': {len(results)} works")
        for work in results:
            rows.append(client.flatten_work(work, discovery_source=f"channel_c:grant:{grant}"))
    return rows


def discover_channel_d(
    client: OpenAlexClient,
    author_seeds: dict,
    global_floor: int,
) -> list[dict]:
    rows: list[dict] = []
    for author in author_seeds.get("authors", []):
        oid = author.get("openalex_id")
        if not oid:
            continue
        name = author.get("name", oid)
        results = client.works_by_author_ids([oid], from_year=global_floor, max_results=100)
        print(f"  Channel D {name} ({oid}): {len(results)} works")
        for work in results:
            rows.append(client.flatten_work(work, discovery_source=f"channel_d:{name}"))
    return rows


def _author_works_batched(
    client: OpenAlexClient,
    author_ids: list[str],
    from_year: int,
    max_results: int,
    batch_size: int = 12,
) -> list[dict]:
    """OpenAlex rejects very long authorships.author.id filters (HTTP 400)."""
    all_works: list[dict] = []
    for i in range(0, len(author_ids), batch_size):
        batch = author_ids[i : i + batch_size]
        all_works.extend(
            client.works_by_author_ids(batch, from_year=from_year, max_results=max_results)
        )
    return all_works


def discover_channel_e(
    client: OpenAlexClient,
    campaigns: dict,
    max_authors_per_anchor: int = 15,
) -> list[dict]:
    rows: list[dict] = []
    seen_authors: set[str] = set()
    for campaign, meta in campaigns.items():
        anchor_dois = meta.get("anchor_dois") or []
        if not anchor_dois:
            continue
        from_year = meta.get("floor_year", 2012)
        author_ids: list[str] = []
        for anchor in anchor_dois:
            if anchor.get("primary") is False:
                continue
            doi = anchor.get("doi", "")
            work = client.work_by_doi(doi)
            if not work:
                print(f"  Channel E warning: could not resolve anchor {doi}")
                continue
            for auth in work.get("authorships", [])[:max_authors_per_anchor]:
                a = auth.get("author") or {}
                oid = (a.get("id") or "").rsplit("/", 1)[-1]
                if oid and oid not in seen_authors:
                    seen_authors.add(oid)
                    author_ids.append(oid)
        if not author_ids:
            continue
        results = _author_works_batched(
            client, author_ids, from_year=from_year, max_results=150, batch_size=12
        )
        print(
            f"  Channel E {campaign} ({len(author_ids)} anchor authors, floor {from_year}): "
            f"{len(results)} works"
        )
        for work in results:
            rows.append(client.flatten_work(work, discovery_source=f"channel_e:{campaign}"))
    return rows


def discover_channel_g(client: OpenAlexClient, ground_truth: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for doi in ground_truth["doi"].dropna().unique():
        clean = str(doi).strip().lower()
        if not clean.startswith("10."):
            continue
        work = client.work_by_doi(clean)
        if work:
            rows.append(client.flatten_work(work, discovery_source="channel_g:ground_truth"))
        else:
            print(f"  Channel G warning: DOI not in OpenAlex: {clean}")
    print(f"  Channel G ground truth resolved: {len(rows)}/{ground_truth['doi'].nunique()} DOIs")
    return rows


def apply_topic_exclusions(rows: list[dict], topic_filters: dict) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    dropped: list[dict] = []
    for row in rows:
        excluded, reason = is_excluded(row, topic_filters)
        if excluded:
            row = dict(row)
            row["exclusion_reason"] = reason
            dropped.append(row)
        else:
            kept.append(row)
    return kept, dropped


def main() -> None:
    parser = argparse.ArgumentParser(description="Channel-based CLAMPS discovery.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output" / "clamps_papers_discovered_channels.csv",
    )
    parser.add_argument("--skip-a", action="store_true")
    parser.add_argument("--skip-b", action="store_true")
    parser.add_argument("--skip-c", action="store_true")
    parser.add_argument("--skip-d", action="store_true")
    parser.add_argument("--skip-e", action="store_true")
    parser.add_argument("--skip-g", action="store_true")
    parser.add_argument("--no-topic-filter", action="store_true")
    parser.add_argument("--openalex-delay", type=float, default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    channels_cfg = load_discovery_channels()
    author_seeds = load_author_seeds()
    campaign_anchors = load_campaign_anchors()
    topic_filters = load_topic_filters()
    ground_truth = load_ground_truth()

    global_floor = int(channels_cfg.get("global_floor_year", 2012))
    campaigns = campaign_anchors.get("campaigns", {})
    channel_defs = channels_cfg.get("channels", {})
    openalex_delay = args.openalex_delay if args.openalex_delay is not None else cfg.openalex_delay

    client = OpenAlexClient(mailto=cfg.openalex_mailto, request_delay=openalex_delay)
    print(f"OpenAlex delay: {openalex_delay}s | global floor: {global_floor}")
    print(f"Campaigns for Channel B: {len(campaigns)}")

    all_rows: list[dict] = []

    if not args.skip_a:
        print("Channel A: explicit facility identity...")
        phrases = channel_defs.get("A", {}).get("phrases", [])
        all_rows.extend(discover_channel_a(client, phrases, global_floor))

    if not args.skip_b:
        print("Channel B: campaign compound queries...")
        all_rows.extend(discover_channel_b(client, campaigns, channel_defs.get("B", {})))

    if not args.skip_c:
        print("Channel C: data products...")
        c_cfg = channel_defs.get("C", {})
        dataset_dois = load_dataset_dois(ROOT / c_cfg.get("dataset_dois_file", "data/clamps_dataset_dois.txt"))
        grants = c_cfg.get("grant_numbers", [])
        all_rows.extend(discover_channel_c(client, dataset_dois, grants, global_floor))

    if not args.skip_d:
        print("Channel D: author seeds...")
        all_rows.extend(discover_channel_d(client, author_seeds, global_floor))

    if not args.skip_e:
        print("Channel E: campaign anchor author groups...")
        all_rows.extend(discover_channel_e(client, campaigns))

    if not args.skip_g:
        print("Channel G: ground truth registry...")
        all_rows.extend(discover_channel_g(client, ground_truth))

    print(f"Raw hits before dedupe: {len(all_rows)}")
    unique_rows = dedupe_works(all_rows)
    print(f"After dedupe: {len(unique_rows)}")

    if not args.no_topic_filter:
        unique_rows, dropped = apply_topic_exclusions(unique_rows, topic_filters)
        print(f"After topic exclusions: {len(unique_rows)} kept, {len(dropped)} dropped")
        if dropped:
            drop_path = args.output.parent / "clamps_papers_excluded_by_topic.csv"
            pd.DataFrame(dropped).to_csv(drop_path, index=False)

    unique_rows = enrich_rows(unique_rows, cfg)
    df = pd.DataFrame(unique_rows)
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

    high_path = args.output.parent / "clamps_papers_high_confidence_channels.csv"
    if not df.empty:
        high_df = df[df.apply(lambda r: qualifies_strict_high_confidence(r, cfg.ambiguous_campaigns), axis=1)]
        high_df.to_csv(high_path, index=False)
        print(f"\nSaved {len(df)} works -> {args.output}")
        print(f"High-confidence: {len(high_df)} -> {high_path}")
        print("\nConfidence tiers:")
        print(df["confidence_tier"].value_counts().to_string())
        print("\nDiscovery sources:")
        print(df["discovery_source"].str.split(":").str[0].value_counts().to_string())
    else:
        print("No works discovered.")


if __name__ == "__main__":
    main()
