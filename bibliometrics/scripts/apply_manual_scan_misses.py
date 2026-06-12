#!/usr/bin/env python3
"""Mark failed-scan papers as human-verified non-hits (misses)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Label scan errors as manually verified misses in scan log."
    )
    parser.add_argument(
        "--misses",
        type=Path,
        default=ROOT / "data" / "manual_pdf_scan_misses.csv",
        help="Audit CSV written from error rows (and used for reference)",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Write misses CSV from current errors without updating scan log",
    )
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    log_path = cfg.output_dir / cfg.scan_log_csv
    log = pd.read_csv(log_path)

    errors = log[log["status"] == "error"].copy()
    if errors.empty:
        print("No error rows to label.")
        return

    export = errors[["doi", "title", "error"]].copy()
    export["notes"] = "Manual review of failed scan — not a CLAMPS hit"
    export["verified_date"] = pd.Timestamp.today().strftime("%Y-%m-%d")
    args.misses.parent.mkdir(parents=True, exist_ok=True)
    export.to_csv(args.misses, index=False)
    print(f"Exported {len(export)} error row(s) -> {args.misses}")

    if args.export_only:
        return

    mask = log["status"] == "error"
    log.loc[mask, "status"] = "no_matches"
    log.loc[mask, "mention_count"] = 0
    log.loc[mask, "matched_terms"] = "manual_verified_miss"
    log.loc[mask, "match_strength"] = "manual_verified_miss"
    log.loc[mask, "error"] = ""

    log.to_csv(log_path, index=False)
    print(f"Updated {int(mask.sum())} row(s) in {log_path}")
    print(f"\nStatus breakdown:\n{log['status'].value_counts().to_string()}")


if __name__ == "__main__":
    main()
