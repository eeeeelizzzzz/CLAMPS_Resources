#!/usr/bin/env python3
"""Resolve DOIs to PDF URLs and enrich the paper CSV for scanning."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.config import load_config
from clamps_biblio.pdf_resolver import (
    is_valid_resolved_pdf_url,
    looks_like_pdf_url,
    normalize_doi,
    resolve_pdf_url,
    scannable_pdf_url,
)
from clamps_biblio.text_scanner import load_cookie_header, make_session


def needs_resolution(row: pd.Series) -> bool:
    url, _ = scannable_pdf_url(row.to_dict())
    doi = normalize_doi(row.get("doi"))
    return not url and bool(doi)


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve PDF URLs from DOIs (Unpaywall + publishers).")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--delay", type=float, default=0.3, help="Seconds between Unpaywall requests")
    parser.add_argument("--limit", type=int, default=None, help="Max DOIs to resolve (for testing)")
    parser.add_argument(
        "--cookies-file",
        type=Path,
        default=None,
        help="AMS session cookies (needed to resolve AMS downloadpdf links)",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    input_path = args.input or (cfg.output_dir / "clamps_papers_high_confidence.csv")
    output_path = args.output or (cfg.output_dir / "clamps_papers_with_pdf_urls.csv")
    manual_path = cfg.output_dir / "manual_download_queue.csv"

    if not input_path.exists():
        print(f"Input not found: {input_path}")
        sys.exit(1)

    email = cfg.openalex_mailto
    if not email:
        print("Warning: openalex.mailto not set in config.yaml — Unpaywall requires an email.")
        print("Publisher-only guesses will still run.")

    df = pd.read_csv(input_path)
    if "pdf_url" not in df.columns:
        df["pdf_url"] = ""
    if "pdf_resolve_method" not in df.columns:
        df["pdf_resolve_method"] = ""

    # Drop bad Zenodo/data-file URLs from earlier runs so they can be re-resolved or skipped.
    bad_mask = df["pdf_url"].apply(
        lambda u: bool(str(u or "").strip()) and str(u).lower() != "nan" and not is_valid_resolved_pdf_url(u)
    )
    if bad_mask.any():
        cleared = int(bad_mask.sum())
        df.loc[bad_mask, ["pdf_url", "pdf_resolve_method"]] = ""
        print(f"Cleared {cleared} invalid pdf_url entries (Zenodo data files, etc.)")

    already = df.apply(
        lambda row: looks_like_pdf_url(str(row.get("source_link", "") or "")),
        axis=1,
    ).sum()
    existing_pdf_url = df["pdf_url"].apply(is_valid_resolved_pdf_url).sum()

    session = make_session()
    if args.cookies_file:
        if not args.cookies_file.exists():
            print(f"Cookies file not found: {args.cookies_file}")
            sys.exit(1)
        session = make_session(load_cookie_header(args.cookies_file))
        print(f"Using cookies from {args.cookies_file} for AMS resolution")
    to_resolve = [i for i, row in df.iterrows() if needs_resolution(row)]
    if args.limit:
        to_resolve = to_resolve[: args.limit]

    print(f"Input: {input_path.name} ({len(df)} papers)")
    print(f"Already have .pdf in source_link: {already}")
    print(f"Resolving PDF URLs for {len(to_resolve)} papers via Unpaywall + publisher patterns...")

    resolved = 0
    for n, idx in enumerate(to_resolve, start=1):
        row = df.loc[idx]
        doi = normalize_doi(row.get("doi"))
        title = str(row.get("title", ""))[:70]
        print(f"  [{n}/{len(to_resolve)}] {doi} — {title}...")
        result = resolve_pdf_url(doi, email, session=session)
        if result:
            df.at[idx, "pdf_url"] = result.url
            df.at[idx, "pdf_resolve_method"] = result.method
            resolved += 1
            print(f"    -> {result.method}: {result.url[:80]}")
        else:
            print("    -> no PDF URL found")
        time.sleep(args.delay)

    df.to_csv(output_path, index=False)

    # Papers still without any scannable URL -> manual queue
    manual_rows = []
    for _, row in df.iterrows():
        url, _ = scannable_pdf_url(row.to_dict())
        if not url:
            manual_rows.append(
                {
                    "title": row.get("title", ""),
                    "doi": row.get("doi", ""),
                    "year": row.get("year", ""),
                    "source_link": row.get("source_link", ""),
                    "openalex_id": row.get("openalex_id", ""),
                }
            )
    pd.DataFrame(manual_rows).to_csv(manual_path, index=False)

    scannable = sum(1 for _, row in df.iterrows() if scannable_pdf_url(row.to_dict())[0])
    print(f"\nDone. Resolved {resolved} new PDF URLs.")
    print(f"Scannable total (source_link or pdf_url): {scannable}/{len(df)}")
    print(f"Enriched CSV: {output_path}")
    print(f"Manual download queue ({len(manual_rows)} papers): {manual_path}")
    print("\nNext: python scripts/scan_pdfs.py --input output/clamps_papers_with_pdf_urls.csv --cookies-file ams_cookies.txt --delay 2")


if __name__ == "__main__":
    main()
