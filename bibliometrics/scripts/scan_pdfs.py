#!/usr/bin/env python3
"""Scan discovered papers for CLAMPS mentions in PDF full text."""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.clamps_signals import classify_match_strength
from clamps_biblio.config import load_config
from clamps_biblio.html_resolver import html_fulltext_target
from clamps_biblio.html_scraper import AsyncHtmlScanSession, load_playwright_cookies
from clamps_biblio.openalex_fulltext import (
    default_has_fulltext_path,
    load_has_fulltext_map,
    row_has_openalex_fulltext,
    scan_openalex_fulltext,
)
from clamps_biblio.openalex_client import OpenAlexClient
from clamps_biblio.pdf_resolver import scannable_pdf_url
from clamps_biblio.scan_patterns import build_scan_patterns
from clamps_biblio.text_scanner import load_cookie_header, make_session, scan_pdf_url

COMPLETED_STATUSES = frozenset({"mentions_found", "no_matches", "error"})


def summarize_mentions(mentions: list) -> tuple[str, str]:
    labels = sorted({m.pattern for m in mentions})
    matched_terms = "; ".join(labels)
    match_strength = classify_match_strength(set(labels))
    return matched_terms, match_strength


def make_log_entry(
    row: pd.Series | dict,
    status: str,
    mention_count: int = 0,
    error: str = "",
    pdf_url: str = "",
    matched_terms: str = "",
    match_strength: str = "",
) -> dict[str, Any]:
    get = row.get if isinstance(row, dict) else row.get
    return {
        "title": get("title", ""),
        "doi": get("doi", ""),
        "openalex_id": get("openalex_id", ""),
        "year": get("year", ""),
        "confidence_tier": get("confidence_tier", ""),
        "source_link": get("source_link", ""),
        "pdf_url": pdf_url,
        "status": status,
        "mention_count": mention_count,
        "matched_terms": matched_terms,
        "match_strength": match_strength,
        "discovery_source": get("discovery_source", "") or get("channel", ""),
        "expectation": get("expectation", ""),
        "scan_method": get("scan_method", ""),
        "error": error,
    }


def normalize_doi(doi: Any) -> str:
    text = str(doi or "").strip()
    if not text or text.lower() == "nan":
        return ""
    return text.lower()


def load_resume_state(
    log_path: Path,
    mentions_path: Path,
    *,
    retry_errors: bool = False,
) -> tuple[set[str], list[dict], dict[str, dict]]:
    """Return completed DOIs, mention rows, and prior log entries keyed by DOI."""
    if not log_path.exists():
        return set(), [], {}

    log_df = pd.read_csv(log_path)
    done_dois: set[str] = set()
    existing_log: dict[str, dict] = {}
    completed = COMPLETED_STATUSES if not retry_errors else COMPLETED_STATUSES - {"error"}
    for _, row in log_df.iterrows():
        doi = normalize_doi(row.get("doi"))
        if not doi:
            continue
        entry = row.to_dict()
        existing_log[doi] = entry
        if str(entry.get("status", "")) in completed:
            done_dois.add(doi)

    mention_rows: list[dict] = []
    if mentions_path.exists():
        mention_rows = pd.read_csv(mentions_path).to_dict("records")

    return done_dois, mention_rows, existing_log


def scan_one_paper(
    row_dict: dict,
    compiled,
    cookie_header: str | None,
    delay: float,
) -> tuple[dict, list[dict], str]:
    """Download and scan one paper. Returns (log_entry, mention_rows, status_line)."""
    title = str(row_dict.get("title", ""))
    url, url_origin = scannable_pdf_url(row_dict)
    session = make_session(cookie_header) if cookie_header else make_session()
    log_entry = make_log_entry(row_dict, "", pdf_url=url)
    mention_rows: list[dict] = []
    status_line = ""

    try:
        mentions = scan_pdf_url(url, compiled, session=session)
        log_entry["mention_count"] = len(mentions)
        if mentions:
            matched_terms, match_strength = summarize_mentions(mentions)
            log_entry["matched_terms"] = matched_terms
            log_entry["match_strength"] = match_strength
            log_entry["status"] = "mentions_found"
            status_line = (
                f"    -> {len(mentions)} mention(s) "
                f"[{match_strength}: {matched_terms[:80]}]"
            )
        else:
            log_entry["status"] = "no_matches"
            status_line = "    -> no matches"
        for mention in mentions:
            mention_rows.append(
                {
                    "title": title,
                    "doi": row_dict.get("doi", ""),
                    "openalex_id": row_dict.get("openalex_id", ""),
                    "pdf_url": url,
                    "pattern": mention.pattern,
                    "page": mention.page,
                    "context": mention.context,
                }
            )
    except Exception as exc:
        log_entry["status"] = "error"
        log_entry["error"] = str(exc)
        status_line = f"    -> error: {exc}"

    if delay > 0:
        time.sleep(delay)

    return log_entry, mention_rows, (
        f"  [pdf] {title[:70]}... ({url_origin})\n{status_line}"
    )


def scan_one_paper_openalex(
    row_dict: dict,
    client: OpenAlexClient,
    cfg,
) -> tuple[dict, list[dict], str]:
    """Probe OpenAlex indexed full text instead of downloading a PDF."""
    title = str(row_dict.get("title", ""))
    log_entry = make_log_entry(row_dict, "", pdf_url="openalex:fulltext.search")
    log_entry["scan_method"] = "openalex_fulltext"
    mention_rows: list[dict] = []
    status_line = ""

    try:
        hits, matched_terms, match_strength = scan_openalex_fulltext(row_dict, client, cfg)
        log_entry["mention_count"] = len(hits)
        if hits:
            log_entry["matched_terms"] = matched_terms
            log_entry["match_strength"] = match_strength
            log_entry["status"] = "mentions_found"
            status_line = (
                f"    -> {len(hits)} fulltext probe hit(s) "
                f"[{match_strength}: {matched_terms[:80]}]"
            )
        else:
            log_entry["status"] = "no_matches"
            status_line = "    -> no fulltext probe matches"
        for hit in hits:
            mention_rows.append(
                {
                    "title": title,
                    "doi": row_dict.get("doi", ""),
                    "openalex_id": row_dict.get("openalex_id", ""),
                    "pdf_url": "openalex:fulltext.search",
                    "pattern": hit.label,
                    "page": 0,
                    "context": hit.context,
                }
            )
    except Exception as exc:
        log_entry["status"] = "error"
        log_entry["error"] = str(exc)
        status_line = f"    -> error: {exc}"

    return log_entry, mention_rows, f"  [openalex] {title[:70]}...\n{status_line}"


def _html_scan_result(
    row_dict: dict,
    target,
    mentions: list | None,
    error: str | None,
) -> tuple[dict, list[dict], str]:
    """Build log/mention rows from a completed HTML scrape."""
    title = str(row_dict.get("title", ""))
    log_entry = make_log_entry(row_dict, "", pdf_url=target.url)
    log_entry["scan_method"] = "html_scrape"
    mention_rows: list[dict] = []
    status_line = ""

    if error:
        log_entry["status"] = "error"
        log_entry["error"] = error
        status_line = f"    -> error: {error}"
    elif mentions:
        log_entry["mention_count"] = len(mentions)
        matched_terms, match_strength = summarize_mentions(mentions)
        log_entry["matched_terms"] = matched_terms
        log_entry["match_strength"] = match_strength
        log_entry["status"] = "mentions_found"
        status_line = (
            f"    -> {len(mentions)} mention(s) "
            f"[{match_strength}: {matched_terms[:80]}]"
        )
        for mention in mentions:
            mention_rows.append(
                {
                    "title": title,
                    "doi": row_dict.get("doi", ""),
                    "openalex_id": row_dict.get("openalex_id", ""),
                    "pdf_url": target.url,
                    "pattern": mention.pattern,
                    "page": mention.page,
                    "context": mention.context,
                }
            )
    else:
        log_entry["status"] = "no_matches"
        status_line = "    -> no matches"

    return log_entry, mention_rows, (
        f"  [html:{target.publisher}] {title[:70]}... ({target.reason})\n{status_line}"
    )


async def scan_one_paper_html_async(
    row_dict: dict,
    html_session: AsyncHtmlScanSession,
    compiled,
    semaphore: asyncio.Semaphore,
    *,
    institutional_network: bool = True,
) -> tuple[dict, dict, list[dict], str]:
    """Scrape one publisher HTML page via shared async Playwright session."""
    target = html_fulltext_target(row_dict, institutional_network=institutional_network)
    if not target:
        raise ValueError("No HTML full-text target for row")

    async with semaphore:
        try:
            mentions = await html_session.scan_url(target.url, target.publisher, compiled)
            log_entry, mention_rows, status_line = _html_scan_result(row_dict, target, mentions, None)
        except Exception as exc:
            log_entry, mention_rows, status_line = _html_scan_result(row_dict, target, None, str(exc))
    return row_dict, log_entry, mention_rows, status_line


async def run_html_scrape_batch(
    pending_html: list[dict],
    compiled,
    cookies: list,
    *,
    html_workers: int,
    institutional_network: bool,
    on_result: Callable[[dict, dict, list[dict], str], None],
) -> None:
    """Scan HTML targets with one browser and limited concurrent pages."""
    semaphore = asyncio.Semaphore(max(1, html_workers))
    total = len(pending_html)
    completed = 0

    async with AsyncHtmlScanSession(cookies) as html_session:
        tasks = [
            asyncio.create_task(
                scan_one_paper_html_async(
                    row_dict,
                    html_session,
                    compiled,
                    semaphore,
                    institutional_network=institutional_network,
                )
            )
            for row_dict in pending_html
        ]

        for future in asyncio.as_completed(tasks):
            row_dict, log_entry, mention_rows, status_line = await future
            on_result(row_dict, log_entry, mention_rows, status_line)
            completed += 1
            if completed % 50 == 0 or completed == total:
                print(f"  HTML progress: {completed}/{total} completed...")


def build_ordered_log(
    df: pd.DataFrame,
    results_by_doi: dict[str, dict],
    limit: int | None,
    pdf_count: int,
    *,
    hybrid_openalex: bool = False,
    has_fulltext_map: dict[str, bool] | None = None,
    html_scrape: bool = False,
    institutional_network: bool = True,
) -> list[dict]:
    """One log row per input CSV row, preserving order."""
    log_rows: list[dict] = []
    pdf_seen = 0
    to_scan = pdf_count if limit is None else min(limit, pdf_count)

    for _, row in df.iterrows():
        row_dict = row.to_dict()
        if html_scrape and html_fulltext_target(row_dict, institutional_network=institutional_network):
            doi = normalize_doi(row_dict.get("doi"))
            if doi and doi in results_by_doi:
                log_rows.append(results_by_doi[doi])
            else:
                target = html_fulltext_target(row_dict, institutional_network=institutional_network)
                log_rows.append(
                    make_log_entry(
                        row_dict,
                        "skipped_not_processed",
                        pdf_url=target.url if target else "",
                    )
                )
            continue
        if hybrid_openalex and row_has_openalex_fulltext(row_dict, has_fulltext_map):
            doi = normalize_doi(row_dict.get("doi"))
            if doi and doi in results_by_doi:
                log_rows.append(results_by_doi[doi])
            else:
                log_rows.append(
                    make_log_entry(
                        row_dict,
                        "skipped_not_processed",
                        pdf_url="openalex:fulltext.search",
                    )
                )
            continue
        url, _ = scannable_pdf_url(row_dict)
        if not url:
            log_rows.append(make_log_entry(row_dict, "skipped_no_pdf"))
            continue

        doi = normalize_doi(row_dict.get("doi"))
        if doi and doi in results_by_doi:
            log_rows.append(results_by_doi[doi])
            pdf_seen += 1
            continue

        if pdf_seen >= to_scan:
            log_rows.append(make_log_entry(row_dict, "skipped_limit", pdf_url=url))
            continue

        pdf_seen += 1
        log_rows.append(make_log_entry(row_dict, "skipped_not_processed", pdf_url=url))

    return log_rows


def save_outputs(
    log_rows: list[dict],
    mention_rows: list[dict],
    cfg,
    *,
    mentions_path: Path | None = None,
    log_path: Path | None = None,
) -> tuple[Path, Path]:
    out_path = mentions_path or (cfg.output_dir / cfg.mentions_csv)
    log_out = log_path or (cfg.output_dir / cfg.scan_log_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log_out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(mention_rows).to_csv(out_path, index=False)
    pd.DataFrame(log_rows).to_csv(log_out, index=False)
    return out_path, log_out


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan paper PDFs for CLAMPS text mentions.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="CSV from discover.py (default: output/clamps_papers_high_confidence.csv)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max papers to scan per route (HTML scrape and/or PDF downloads; all CSV rows still appear in scan log)",
    )
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between PDF downloads per worker")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel download/scan threads (default: 1). Try 4 on a laptop.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip DOIs already marked mentions_found, no_matches, or error in scan log",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="With --resume, re-attempt rows previously logged as error (e.g. MDPI 403 after cookie fix)",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=10,
        help="Save scan log and mentions every N completed downloads (0 to disable)",
    )
    parser.add_argument(
        "--cookies-file",
        type=Path,
        default=None,
        help="File containing AMS Cookie header copied from browser DevTools",
    )
    parser.add_argument(
        "--expectation",
        type=str,
        default=None,
        help="Comma-separated expectation values to scan (e.g. Y,M). Requires expectation column in input CSV.",
    )
    parser.add_argument(
        "--hybrid-openalex",
        action="store_true",
        help=(
            "For works with OpenAlex has_fulltext=True, probe indexed full text via "
            "fulltext.search instead of downloading publisher PDFs. Others use PDF crawl."
        ),
    )
    parser.add_argument(
        "--has-fulltext-csv",
        type=Path,
        default=None,
        help="CSV with openalex_id + has_fulltext (default: output/openalex_has_fulltext_by_work.csv)",
    )
    parser.add_argument(
        "--scan-log",
        type=Path,
        default=None,
        help="Override scan log output path (default: output/clamps_scan_log.csv)",
    )
    parser.add_argument(
        "--mentions-csv",
        type=Path,
        default=None,
        help="Override mentions output path (default: output/clamps_text_mentions.csv)",
    )
    parser.add_argument(
        "--html-scrape",
        action="store_true",
        help=(
            "Scrape AMS (library cookies) and open-access HTML full-text pages via Playwright "
            "instead of downloading PDFs. Requires: pip install playwright && playwright install chromium"
        ),
    )
    parser.add_argument(
        "--html-workers",
        type=int,
        default=4,
        help="Concurrent Playwright pages per browser session when using --html-scrape (default: 4)",
    )
    parser.add_argument(
        "--playwright-cookies",
        type=Path,
        default=None,
        help="Playwright cookies: JSON array (EditThisCookie) or Cookie header text (default: ams_cookies.json or ams_cookies.txt)",
    )
    parser.add_argument(
        "--no-institutional-network",
        action="store_true",
        help=(
            "Disable IP-authenticated publisher HTML targets (AMS, Wiley, Elsevier, Springer). "
            "By default --html-scrape assumes university/agency network access."
        ),
    )
    args = parser.parse_args()
    args.institutional_network = not args.no_institutional_network

    if args.workers < 1:
        print("--workers must be at least 1")
        sys.exit(1)
    if args.html_workers < 1:
        print("--html-workers must be at least 1")
        sys.exit(1)

    cfg = load_config(args.config)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    default_input = cfg.output_dir / "clamps_papers_high_confidence.csv"
    if not default_input.exists():
        default_input = cfg.output_dir / cfg.papers_csv
    input_path = args.input or default_input
    if not input_path.exists():
        print(f"Input not found: {input_path}")
        print("Run scripts/discover.py first.")
        sys.exit(1)

    df = pd.read_csv(input_path)
    total_rows = len(df)

    if args.expectation:
        if "expectation" not in df.columns:
            print(f"Input has no 'expectation' column: {input_path}")
            sys.exit(1)
        allowed = {v.strip().upper() for v in args.expectation.split(",") if v.strip()}
        df = df[df["expectation"].astype(str).str.strip().str.upper().isin(allowed)]
        print(
            f"Filtered to expectation in {sorted(allowed)}: "
            f"{len(df)}/{total_rows} rows"
        )

    if "confidence_tier" in df.columns:
        df = df[df["confidence_tier"].isin(["high", "medium"])]
    if "relevance_score" in df.columns:
        df = df.sort_values("relevance_score", ascending=False)

    has_fulltext_map: dict[str, bool] = {}
    if args.hybrid_openalex:
        ft_path = args.has_fulltext_csv or default_has_fulltext_path(cfg)
        has_fulltext_map = load_has_fulltext_map(ft_path)
        if not has_fulltext_map:
            print(f"Warning: no has_fulltext map at {ft_path}; hybrid routing may be limited.")
        else:
            openalex_rows = sum(
                1 for _, row in df.iterrows() if row_has_openalex_fulltext(row.to_dict(), has_fulltext_map)
            )
            print(f"Hybrid mode: {openalex_rows}/{len(df)} rows route to OpenAlex fulltext probe")

    def _html_target(row_dict: dict):
        return html_fulltext_target(row_dict, institutional_network=args.institutional_network)

    def _pdf_eligible(row_dict: dict) -> bool:
        if args.html_scrape and _html_target(row_dict):
            return False
        if args.hybrid_openalex and row_has_openalex_fulltext(row_dict, has_fulltext_map):
            return False
        return scannable_pdf_url(row_dict)[0] != ""

    pdf_count = sum(_pdf_eligible(row.to_dict()) for _, row in df.iterrows())

    html_rows = sum(1 for _, row in df.iterrows() if args.html_scrape and _html_target(row.to_dict()))
    if args.html_scrape:
        mode = "institutional IP + open access" if args.institutional_network else "open access only"
        print(
            f"HTML scrape mode ({mode}): {html_rows}/{len(df)} rows route to Playwright "
            f"(1 browser, {args.html_workers} concurrent pages)"
        )

    cookie_header: str | None = None
    if args.cookies_file:
        if not args.cookies_file.exists():
            print(f"Cookies file not found: {args.cookies_file}")
            sys.exit(1)
        cookie_header = load_cookie_header(args.cookies_file)
        print(f"Using cookies from {args.cookies_file}")

    log_path = args.scan_log or (cfg.output_dir / cfg.scan_log_csv)
    mentions_path = args.mentions_csv or (cfg.output_dir / cfg.mentions_csv)
    done_dois: set[str] = set()
    mention_rows: list[dict] = []
    existing_log: dict[str, dict] = {}
    if args.resume:
        done_dois, mention_rows, existing_log = load_resume_state(
            log_path, mentions_path, retry_errors=args.retry_errors
        )
        if done_dois:
            print(f"Resume: skipping {len(done_dois)} already-scanned DOI(s) from {log_path.name}")

    to_scan = pdf_count if args.limit is None else min(args.limit, pdf_count)
    html_limit = args.limit if args.html_scrape and args.limit is not None else None
    pending_pdf: list[dict] = []
    pending_openalex: list[dict] = []
    pending_html: list[dict] = []
    pdf_seen = 0
    html_seen = 0
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        doi = normalize_doi(row_dict.get("doi"))
        if args.resume and doi and doi in done_dois:
            continue

        if args.html_scrape and _html_target(row_dict):
            if html_limit is not None and html_seen >= html_limit:
                continue
            html_seen += 1
            pending_html.append(row_dict)
            continue

        if args.hybrid_openalex and row_has_openalex_fulltext(row_dict, has_fulltext_map):
            pending_openalex.append(row_dict)
            continue

        url, _ = scannable_pdf_url(row_dict)
        if not url:
            continue
        if pdf_seen >= to_scan:
            continue
        pdf_seen += 1
        pending_pdf.append(row_dict)

    print(
        f"Processing {len(df)} papers from {input_path.name} "
        f"({len(pending_html)} HTML scrape @ {args.html_workers} pages, "
        f"{len(pending_openalex)} OpenAlex fulltext, "
        f"{pdf_count} PDF-eligible, {len(pending_pdf)} PDF downloads queued, "
        f"{len(done_dois)} skipped via resume; pdf_workers={args.workers})..."
    )
    compiled = build_scan_patterns(cfg)
    openalex_client = (
        OpenAlexClient(mailto=cfg.openalex_mailto, request_delay=cfg.openalex_delay)
        if args.hybrid_openalex
        else None
    )

    scanned: dict[str, dict] = {}
    write_lock = threading.Lock()
    completed = 0
    total_pending = len(pending_pdf) + len(pending_openalex) + len(pending_html)

    playwright_cookies: list = []
    if args.html_scrape:
        cookie_candidates = [
            args.playwright_cookies,
            ROOT / "ams_cookies.json",
            ROOT / "ams_cookies.txt",
            args.cookies_file,
        ]
        for candidate in cookie_candidates:
            if candidate and Path(candidate).exists():
                playwright_cookies = load_playwright_cookies(Path(candidate))
                print(f"Playwright cookies loaded from {candidate} ({len(playwright_cookies)} cookies)")
                break
        if not playwright_cookies:
            if args.institutional_network:
                print(
                    "No Playwright cookies loaded — using institutional network IP access "
                    "(AMS, Wiley, Elsevier, Springer, etc.)."
                )
            else:
                print("Warning: no Playwright cookies found (AMS paywall may block without --no-institutional-network).")

    def _write_checkpoint() -> None:
        """Persist scan log + mentions. Caller must hold write_lock."""
        merged = dict(existing_log)
        merged.update(scanned)
        log_rows = build_ordered_log(
            df,
            merged,
            args.limit,
            pdf_count,
            hybrid_openalex=args.hybrid_openalex,
            has_fulltext_map=has_fulltext_map,
            html_scrape=args.html_scrape,
            institutional_network=args.institutional_network,
        )
        save_outputs(log_rows, mention_rows, cfg, mentions_path=mentions_path, log_path=log_path)

    def maybe_checkpoint() -> None:
        if args.checkpoint_every <= 0:
            return
        with write_lock:
            _write_checkpoint()

    def record_result(row_dict: dict, log_entry: dict, new_mentions: list, status_line: str) -> None:
        nonlocal completed
        doi = normalize_doi(row_dict.get("doi"))
        with write_lock:
            scanned[doi] = log_entry
            mention_rows.extend(new_mentions)
            completed += 1
            print(f"  [{completed}/{total_pending}] {status_line}")
            if args.checkpoint_every > 0 and completed % args.checkpoint_every == 0:
                _write_checkpoint()
                print(f"  checkpoint: {completed}/{total_pending} saved", flush=True)

    if args.html_scrape and pending_html:
        asyncio.run(
            run_html_scrape_batch(
                pending_html,
                compiled,
                playwright_cookies,
                html_workers=args.html_workers,
                institutional_network=args.institutional_network,
                on_result=record_result,
            )
        )

    if args.hybrid_openalex and pending_openalex:
        for row_dict in pending_openalex:
            log_entry, new_mentions, status_line = scan_one_paper_openalex(
                row_dict, openalex_client, cfg
            )
            record_result(row_dict, log_entry, new_mentions, status_line)

    if pending_pdf and args.workers == 1:
        for row_dict in pending_pdf:
            log_entry, new_mentions, status_line = scan_one_paper(
                row_dict, compiled, cookie_header, args.delay
            )
            log_entry["scan_method"] = "pdf_crawl"
            record_result(row_dict, log_entry, new_mentions, status_line)
    elif pending_pdf:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    scan_one_paper, row_dict, compiled, cookie_header, args.delay
                ): row_dict
                for row_dict in pending_pdf
            }
            for future in as_completed(futures):
                row_dict = futures[future]
                log_entry, new_mentions, status_line = future.result()
                log_entry["scan_method"] = "pdf_crawl"
                record_result(row_dict, log_entry, new_mentions, status_line)

    merged = dict(existing_log)
    merged.update(scanned)
    log_rows = build_ordered_log(
        df,
        merged,
        args.limit,
        pdf_count,
        hybrid_openalex=args.hybrid_openalex,
        has_fulltext_map=has_fulltext_map,
        html_scrape=args.html_scrape,
        institutional_network=args.institutional_network,
    )
    out_path, log_path = save_outputs(
        log_rows, mention_rows, cfg, mentions_path=mentions_path, log_path=log_path
    )

    print(f"\nDone. {len(mention_rows)} mentions saved to {out_path}")
    print(f"Scan log ({len(log_rows)} papers — full CSV coverage) saved to {log_path}")
    log_df = pd.DataFrame(log_rows)
    if not log_df.empty:
        print("\nScan status breakdown:")
        print(log_df["status"].value_counts().to_string())


if __name__ == "__main__":
    main()
