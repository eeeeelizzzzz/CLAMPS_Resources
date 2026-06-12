#!/usr/bin/env python3
"""Pass-2 PDF URL resolution for papers still missing scannable PDFs."""

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
    resolve_pdf_pass2,
    scannable_pdf_url,
)
from clamps_biblio.text_scanner import load_cookie_header, make_session


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pass-2 PDF resolution: OpenAlex, EGUsphere, OSTI, NOAA IR, landing scrape."
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "output" / "clamps_papers_high_confidence_channels_with_pdfs.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Defaults to overwriting --input",
    )
    parser.add_argument(
        "--manual-queue",
        type=Path,
        default=ROOT / "output" / "manual_download_queue.csv",
    )
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--cookies-file",
        type=Path,
        default=ROOT / "ams_cookies.txt",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    input_path = args.input
    output_path = args.output or input_path
    if not input_path.exists():
        print(f"Input not found: {input_path}")
        sys.exit(1)

    df = pd.read_csv(input_path)
    if "pdf_url" not in df.columns:
        df["pdf_url"] = ""
    if "pdf_resolve_method" not in df.columns:
        df["pdf_resolve_method"] = ""

    session = make_session()
    if args.cookies_file and args.cookies_file.exists():
        session = make_session(load_cookie_header(args.cookies_file))
        print(f"Using cookies from {args.cookies_file}")

    before_scannable = sum(1 for _, row in df.iterrows() if scannable_pdf_url(row.to_dict())[0])
    to_resolve = [
        idx
        for idx, row in df.iterrows()
        if not scannable_pdf_url(row.to_dict())[0]
    ]
    if args.limit:
        to_resolve = to_resolve[: args.limit]

    print(f"Input: {input_path.name} ({len(df)} papers)")
    print(f"Scannable before pass 2: {before_scannable}")
    print(f"Pass-2 targets: {len(to_resolve)}")

    resolved = 0
    methods: dict[str, int] = {}
    for n, idx in enumerate(to_resolve, start=1):
        row = df.loc[idx].to_dict()
        doi = str(row.get("doi", ""))
        title = str(row.get("title", ""))[:70]
        print(f"  [{n}/{len(to_resolve)}] {doi} — {title}...")
        result = resolve_pdf_pass2(
            row,
            email=cfg.openalex_mailto,
            mailto=cfg.openalex_mailto,
            session=session,
        )
        if result:
            df.at[idx, "pdf_url"] = result.url
            df.at[idx, "pdf_resolve_method"] = result.method
            resolved += 1
            methods[result.method] = methods.get(result.method, 0) + 1
            print(f"    -> {result.method}: {result.url[:90]}")
        else:
            print("    -> no PDF URL found")
        time.sleep(args.delay)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    manual_rows = []
    for _, row in df.iterrows():
        if not scannable_pdf_url(row.to_dict())[0]:
            manual_rows.append(
                {
                    "title": row.get("title", ""),
                    "doi": row.get("doi", ""),
                    "year": row.get("year", ""),
                    "source_link": row.get("source_link", ""),
                    "openalex_id": row.get("openalex_id", ""),
                    "pdf_resolve_method": row.get("pdf_resolve_method", ""),
                }
            )
    pd.DataFrame(manual_rows).to_csv(args.manual_queue, index=False)

    after_scannable = sum(1 for _, row in df.iterrows() if scannable_pdf_url(row.to_dict())[0])
    print(f"\nPass 2 resolved: {resolved} new PDF URLs")
    if methods:
        print("By method:")
        for method, count in sorted(methods.items(), key=lambda x: -x[1]):
            print(f"  {method}: {count}")
    print(f"Scannable: {before_scannable} -> {after_scannable} / {len(df)}")
    print(f"Updated CSV: {output_path}")
    print(f"Manual queue: {len(manual_rows)} -> {args.manual_queue}")
    print(
        "\nNext: python scripts/scan_pdfs.py "
        f"--input {output_path} --cookies-file {args.cookies_file}"
    )


if __name__ == "__main__":
    main()
