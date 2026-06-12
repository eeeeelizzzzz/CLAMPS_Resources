#!/usr/bin/env python3
"""Tier 6: discover theses/dissertations in institutional repositories."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.clamps_signals import all_signals_in_text, has_clamps_signal
from clamps_biblio.config import load_config
from clamps_biblio.relevance import metadata_text, qualifies_strict_high_confidence, score_work
from clamps_biblio.repo_discovery.models import RepoHit
from clamps_biblio.repo_discovery.router import search_oatd_aggregator, search_repository
from clamps_biblio.repository_links import repository_signals_in_text
from clamps_biblio.thesis_config import (
    RepoQuery,
    build_repo_queries,
    discovery_label_for_hit,
    load_channel_h_exclusions,
    load_thesis_repositories,
    repos_by_priority,
)


def _is_campaign_candidate(hit: RepoHit) -> bool:
    return hit.discovery_label.startswith("campaign_candidate:")


def dedupe_hits(hits: list[RepoHit]) -> list[RepoHit]:
    by_key: dict[str, RepoHit] = {}
    for hit in hits:
        key = hit.dedupe_key()
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = hit
        elif _is_campaign_candidate(existing) and not _is_campaign_candidate(hit):
            by_key[key] = hit
    return list(by_key.values())


def tag_hits(hits: list[RepoHit], repo_id: str, query: RepoQuery) -> list[RepoHit]:
    label = discovery_label_for_hit(repo_id, query)
    for hit in hits:
        hit.discovery_label = label
    return hits


def dedupe_rows(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for row in rows:
        doi = str(row.get("doi") or "").strip().lower()
        oid = str(row.get("openalex_id") or "").strip()
        title = str(row.get("title") or "").strip().lower()
        year = str(row.get("year") or "")
        key = doi or oid or f"{title}|{year}"
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def filter_hits(hits: list[RepoHit], *, require_clamps: bool, from_year: int | None) -> list[RepoHit]:
    kept: list[RepoHit] = []
    for hit in hits:
        if from_year and hit.year and hit.year < from_year:
            continue
        text = " ".join(filter(None, [hit.title, hit.abstract]))
        if require_clamps and not has_clamps_signal(text):
            continue
        kept.append(hit)
    return kept


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


def merge_with_existing(existing_path: Path, new_rows: list[dict]) -> list[dict]:
    if not existing_path.exists():
        return new_rows
    old = pd.read_csv(existing_path).to_dict(orient="records")
    return dedupe_rows(old + new_rows)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def hits_to_rows(hits: list[RepoHit], cfg) -> list[dict]:
    rows = [h.to_discovery_row() for h in dedupe_hits(hits)]
    rows = dedupe_rows(rows)
    return enrich_rows(rows, cfg)


def write_checkpoint(hits: list[RepoHit], cfg, path: Path) -> int:
    rows = hits_to_rows(hits, cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    return len(rows)


def write_status(path: Path, status: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


def discover_repos(
    repo_cfg: dict[str, Any],
    *,
    max_priority: int | None,
    repo_ids: list[str] | None,
    include_campaigns: bool,
    include_oatd: bool,
    apply_channel_h_exclusions: bool = True,
    skip_crawled: bool = False,
    skip_crawl_errors: bool = False,
    cfg=None,
    checkpoint_path: Path | None = None,
    status_path: Path | None = None,
) -> list[RepoHit]:
    disc = repo_cfg.get("discovery") or {}
    delay = float(disc.get("request_delay", 2.0))
    from_year = int(disc.get("from_year", 2015))
    max_results = int(disc.get("max_results_per_query", 30))
    default_require_clamps = bool(disc.get("require_clamps_signal", True))

    queries = build_repo_queries(repo_cfg, include_campaigns=include_campaigns)
    repos = repos_by_priority(
        repo_cfg,
        max_priority=max_priority,
        repo_ids=repo_ids,
        apply_channel_h_exclusions=apply_channel_h_exclusions,
        skip_crawled=skip_crawled,
        skip_crawl_errors=skip_crawl_errors,
    )
    all_hits: list[RepoHit] = []
    facility_q = sum(1 for q in queries if q.mode == "facility")
    compound_q = sum(1 for q in queries if q.mode == "campaign_compound")
    campaign_q = sum(1 for q in queries if q.mode == "campaign_only")

    print(
        f"Repositories: {len(repos)} | queries: {len(queries)} "
        f"(facility {facility_q}, compound {compound_q}, campaign-only {campaign_q}) | delay: {delay}s",
        flush=True,
    )
    if checkpoint_path:
        print(f"Checkpoint CSV: {checkpoint_path}", flush=True)
    if status_path:
        print(f"Status file: {status_path}", flush=True)

    status: dict[str, Any] | None = None
    if status_path:
        status = {
            "started_at": _utc_now(),
            "updated_at": None,
            "repos_total": len(repos),
            "repos_completed": 0,
            "queries_per_repo": len(queries),
            "hits_raw": 0,
            "hits_deduped": 0,
            "hits_confirmed": 0,
            "hits_campaign_candidate": 0,
            "repos": [],
            "complete": False,
        }

    for repo in repos:
        rid = repo.get("id", "?")
        print(f"\n  [{repo.get('priority', '?')}] {repo.get('name', rid)} ({repo.get('platform')})")
        repo_hits_before = len(all_hits)
        for query in queries:
            require_clamps = default_require_clamps and query.requires_clamps_signal()
            mode_tag = query.mode.replace("_", "-")
            print(f"    query [{mode_tag}]: {query.text!r}")
            hits = search_repository(
                repo,
                query.text,
                max_results=max_results,
                request_delay=delay,
                from_year=from_year,
                require_clamps=require_clamps,
            )
            hits = filter_hits(hits, require_clamps=require_clamps, from_year=from_year)
            hits = tag_hits(hits, rid, query)
            if hits:
                kind = "campaign candidate(s)" if query.mode == "campaign_only" else "CLAMPS-relevant hit(s)"
                print(f"      -> {len(hits)} {kind}")
            all_hits.extend(hits)

        if checkpoint_path and cfg is not None:
            deduped = write_checkpoint(all_hits, cfg, checkpoint_path)
            repo_slice = all_hits[repo_hits_before:]
            repo_confirmed = sum(1 for h in repo_slice if not _is_campaign_candidate(h))
            repo_candidates = len(repo_slice) - repo_confirmed
            print(
                f"    checkpoint: {deduped} total hits (+{len(repo_slice)} this repo) -> {checkpoint_path}",
                flush=True,
            )
            if status is not None and status_path is not None:
                status["repos_completed"] += 1
                status["updated_at"] = _utc_now()
                status["hits_raw"] = len(all_hits)
                status["hits_deduped"] = deduped
                status["hits_confirmed"] = sum(1 for h in all_hits if not _is_campaign_candidate(h))
                status["hits_campaign_candidate"] = sum(1 for h in all_hits if _is_campaign_candidate(h))
                status["repos"].append(
                    {
                        "id": rid,
                        "name": repo.get("name", rid),
                        "priority": repo.get("priority"),
                        "platform": repo.get("platform"),
                        "hits_raw": len(repo_slice),
                        "hits_confirmed": repo_confirmed,
                        "hits_campaign_candidate": repo_candidates,
                        "crawl_error": repo.get("crawl_error"),
                        "completed_at": status["updated_at"],
                    }
                )
                write_status(status_path, status)

    if include_oatd:
        agg = (repo_cfg.get("aggregators") or {}).get("oatd") or {}
        if agg.get("enabled", True):
            max_pages = int(agg.get("max_pages", 3))
            print(f"\n  [aggregator] OATD ({len(queries)} queries, max {max_pages} pages each)")
            for query in queries:
                require_clamps = default_require_clamps and query.requires_clamps_signal()
                print(f"    oatd query [{query.mode.replace('_', '-')}]: {query.text!r}")
                hits = search_oatd_aggregator(
                    query.text,
                    max_results=max_results,
                    request_delay=delay,
                    max_pages=max_pages,
                )
                hits = filter_hits(hits, require_clamps=require_clamps, from_year=from_year)
                hits = tag_hits(hits, "oatd", query)
                if hits:
                    print(f"      -> {len(hits)} hit(s)")
                all_hits.extend(hits)

    return dedupe_hits(all_hits)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tier 6 institutional repository thesis discovery.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--repos-file", type=Path, default=ROOT / "data" / "thesis_repositories.yaml")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output" / "clamps_theses_discovered_repos.csv",
    )
    parser.add_argument(
        "--merge-into",
        type=Path,
        default=None,
        help="Merge results into an existing discovery CSV (e.g. clamps_papers_discovered.csv)",
    )
    parser.add_argument("--max-priority", type=int, default=None, help="Only repos with priority <= N")
    parser.add_argument("--repo-id", action="append", dest="repo_ids", help="Limit to repository id(s)")
    parser.add_argument("--skip-oatd", action="store_true")
    parser.add_argument("--skip-campaigns", action="store_true", help="Facility phrases only")
    parser.add_argument("--no-clamps-filter", action="store_true", help="Keep all keyword hits (noisy)")
    parser.add_argument(
        "--include-excluded",
        action="store_true",
        help="Search repos for Channel-H excluded institutions (default: skip per channel_h_exclusions.yaml)",
    )
    parser.add_argument(
        "--skip-crawled",
        action="store_true",
        help="Omit repositories with crawled: true in thesis_repositories.yaml",
    )
    parser.add_argument(
        "--skip-crawl-errors",
        action="store_true",
        help="Omit repositories with crawl_error set in thesis_repositories.yaml",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Incremental CSV written after each repo (default: <output>.checkpoint.csv)",
    )
    parser.add_argument(
        "--status-file",
        type=Path,
        default=None,
        help="JSON progress file updated after each repo (default: output/discover_thesis_repos_status.json)",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Disable incremental checkpoint/status writes",
    )
    parser.add_argument(
        "--from-status",
        type=Path,
        default=None,
        help="Re-crawl repo ids listed in a discover_thesis_repos_status.json (ignores --skip-crawled)",
    )
    args = parser.parse_args()

    if args.from_status:
        status = json.loads(args.from_status.read_text(encoding="utf-8"))
        recovered_ids = [r["id"] for r in status.get("repos", []) if r.get("complete", True)]
        if not recovered_ids:
            recovered_ids = [r["id"] for r in status.get("repos", [])]
        args.repo_ids = list(dict.fromkeys(recovered_ids))
        print(
            f"Recovering {len(args.repo_ids)} repo(s) from {args.from_status} "
            f"(explicit --repo-id overrides --from-status)",
            flush=True,
        )

    cfg = load_config(args.config)
    repo_cfg = load_thesis_repositories(args.repos_file)
    if args.no_clamps_filter:
        repo_cfg.setdefault("discovery", {})["require_clamps_signal"] = False

    excluded = load_channel_h_exclusions()
    if excluded and not args.include_excluded:
        print(f"Channel H exclusions: {len(excluded)} institutions (see data/channel_h_exclusions.yaml)")
    if args.skip_crawled:
        n_crawled = sum(1 for r in (repo_cfg.get("repositories") or []) if r.get("crawled"))
        print(f"Skipping {n_crawled} repo(s) marked crawled: true")
    if args.skip_crawl_errors:
        err_repos = [r for r in (repo_cfg.get("repositories") or []) if r.get("crawl_error")]
        if err_repos:
            print(
                f"Skipping {len(err_repos)} repo(s) with crawl_error: "
                + ", ".join(f"{r['id']} ({r['crawl_error']})" for r in err_repos),
                flush=True,
            )

    checkpoint_path = None if args.no_checkpoint else (args.checkpoint or args.output.with_suffix(".checkpoint.csv"))
    status_path = None if args.no_checkpoint else (args.status_file or args.output.parent / "discover_thesis_repos_status.json")

    cfg_out = load_config(args.config)
    hits = discover_repos(
        repo_cfg,
        max_priority=args.max_priority,
        repo_ids=args.repo_ids,
        include_campaigns=not args.skip_campaigns,
        include_oatd=not args.skip_oatd,
        apply_channel_h_exclusions=not args.include_excluded,
        skip_crawled=args.skip_crawled,
        skip_crawl_errors=args.skip_crawl_errors,
        cfg=cfg_out,
        checkpoint_path=checkpoint_path,
        status_path=status_path,
    )
    print(f"\nRaw repo hits: {len(hits)}")
    candidates = sum(1 for h in hits if _is_campaign_candidate(h))
    confirmed = len(hits) - candidates
    print(f"  metadata-confirmed: {confirmed} | campaign_candidate (needs PDF): {candidates}")
    rows = hits_to_rows(hits, cfg_out)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output, index=False)
    print(f"Saved {len(rows)} thesis repo hits -> {args.output}")
    if checkpoint_path:
        pd.DataFrame(rows).to_csv(checkpoint_path, index=False)
        print(f"Checkpoint up to date -> {checkpoint_path}")
    if status_path:
        status: dict[str, Any] = {
            "updated_at": _utc_now(),
            "hits_raw": len(hits),
            "hits_deduped": len(rows),
            "hits_confirmed": confirmed,
            "hits_campaign_candidate": candidates,
            "complete": True,
        }
        if status_path.exists():
            try:
                prior = json.loads(status_path.read_text(encoding="utf-8"))
                status = {**prior, **status}
            except (json.JSONDecodeError, OSError):
                status.setdefault("repos", [])
                status.setdefault("repos_total", len(status.get("repos", [])))
                status.setdefault("repos_completed", len(status.get("repos", [])))
                status.setdefault("started_at", _utc_now())
        else:
            status["started_at"] = _utc_now()
            status["repos"] = []
            status["repos_total"] = 0
            status["repos_completed"] = 0
        write_status(status_path, status)
        print(f"Status complete -> {status_path}")

    if args.merge_into:
        merged = merge_with_existing(args.merge_into, rows)
        pd.DataFrame(merged).to_csv(args.merge_into, index=False)
        print(f"Merged total {len(merged)} works -> {args.merge_into}")

        hc_path = args.merge_into.parent / "clamps_papers_high_confidence.csv"
        if hc_path.exists() or rows:
            df = pd.DataFrame(merged)
            if not df.empty:
                high_df = df[df.apply(lambda r: qualifies_strict_high_confidence(r, cfg.ambiguous_campaigns), axis=1)]
                high_df.to_csv(hc_path, index=False)
                print(f"High-confidence subset: {len(high_df)} -> {hc_path}")


if __name__ == "__main__":
    main()
