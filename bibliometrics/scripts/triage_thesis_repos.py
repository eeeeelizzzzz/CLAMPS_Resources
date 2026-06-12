#!/usr/bin/env python3
"""Auto-triage Channel H thesis hits into reject / PDF-scan / short manual queues."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.clamps_signals import has_clamps_signal

CAMPAIGNS = (
    "PECAN",
    "LAPSE-RATE",
    "VORTEX-SE",
    "TORUS",
    "PERiLS",
    "Perdigão",
    "CHEESEHEAD",
    "AWAKEN",
)

MET_TITLE = re.compile(
    r"\b(atmospheric|meteorolog|weather|convection|tornado|supercell|mesoscale|"
    r"boundary layer|nocturnal|lidar|profiler|doppler|radiosonde|NSSL|"
    r"severe storm|wind farm|hydrolog)\b",
    re.I,
)

MET_ABSTRACT = re.compile(
    r"\b(atmospheric|meteorolog|boundary layer|convection|tornado|lidar|profiler|"
    r"nocturnal|mesoscale|NSSL|mobile profiling|Doppler wind|AERI|microwave radiometer|"
    r"PECAN|VORTEX|elevated convection)\b",
    re.I,
)

STRONG_CLAMPS = re.compile(
    r"(Collaborative Lower Atmospheric Mobile Profiling System|"
    r"\bCLAMPS[-\s]?[12]\b|\bCLAMPS1\b|\bCLAMPS2\b|"
    r"NSSL mobile profil)",
    re.I,
)

REJECT = re.compile(
    r"\b(insulin|BCAA|glucose|diabetes|checkpoint signaling|pipe clamp|steel clamp|"
    r"kolache|klobasnik|Drosophila|gastrulation|soybean|herbicid|magnetism|"
    r"kolache|ptychograph|transposase|DNA|RNA|surgery|nursing|psycholog|"
    r"economics|education|archaeolog|bicycl|chatgpt|manufacturing|"
    r"willmore|torus knot|jones polynomial|atomic norm|reservoir model|"
    r"time-lapse gravity|dicamba|magnetism|foodways|czech cultural)\b",
    re.I,
)

NON_MET_CAMPAIGN = re.compile(
    r"\b(Drosophila|kolache|Willmore|torus knot|atomic norm|reservoir|dicamba|"
    r"foodways|magnetism|ptychograph|vision-based|satellite tracking)\b",
    re.I,
)


def campaign_from_row(row: pd.Series) -> str:
    src = str(row.get("discovery_source", ""))
    for c in CAMPAIGNS:
        if c in src or c.lower() in src.lower():
            return c
    match = str(row.get("discovery_match", ""))
    for c in CAMPAIGNS:
        if c in match:
            return c
    return ""


def score_row(row: pd.Series) -> tuple[int, str, str]:
    title = str(row.get("title") or "")
    abstract = str(row.get("abstract") or "")
    text = f"{title} {abstract}"
    inst = str(row.get("institutions") or "")
    campaign = campaign_from_row(row)

    if REJECT.search(title) or (campaign and NON_MET_CAMPAIGN.search(title)):
        return -10, "auto_reject", "homograph / non-met title"

    has_met = bool(MET_TITLE.search(title) or MET_ABSTRACT.search(abstract))
    if campaign and not has_met and not STRONG_CLAMPS.search(text):
        return -5, "auto_reject", f"campaign:{campaign}; campaign_only_no_met"

    score = 0
    reasons: list[str] = []

    if STRONG_CLAMPS.search(text):
        score += 8
        reasons.append("strong_clamps_phrase")
    elif has_clamps_signal(text):
        score += 3
        reasons.append("weak_clamps_token")

    if MET_TITLE.search(title):
        score += 4
        reasons.append("met_title")
    elif MET_ABSTRACT.search(abstract):
        score += 2
        reasons.append("met_abstract")

    if campaign in ("PECAN", "VORTEX-SE", "TORUS", "LAPSE-RATE", "PERiLS", "AWAKEN"):
        score += 2
        reasons.append(f"campaign:{campaign}")

    if re.search(r"school of meteorology|NSSL|National Severe Storms|atmospheric science", inst, re.I):
        score += 2
        reasons.append("met_institution")

    year = row.get("year")
    if pd.notna(year) and 2015 <= float(year) <= 2024:
        score += 1
        reasons.append("year_window")

    if score >= 10:
        bucket = "pdf_priority"
    elif score >= 6:
        bucket = "pdf_scan"
    elif score >= 3:
        bucket = "maybe"
    else:
        bucket = "auto_reject"

    return score, bucket, "; ".join(reasons)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "output" / "clamps_theses_discovered_repos.csv",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    parser.add_argument(
        "--pdf-scan",
        action="store_true",
        help="PDF-scan pdf_scan + pdf_priority queues (slow; uses scan_pdfs.py logic)",
    )
    parser.add_argument("--pdf-limit", type=int, default=80, help="Max theses to PDF-scan")
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    scores, buckets, reasons = zip(*[score_row(r) for _, r in df.iterrows()])
    df = df.copy()
    df["triage_score"] = scores
    df["triage_bucket"] = buckets
    df["triage_reason"] = reasons

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    reject = df[df["triage_bucket"] == "auto_reject"]
    pdf_queue = df[df["triage_bucket"].isin(["pdf_scan", "pdf_priority"])].sort_values(
        "triage_score", ascending=False
    )
    maybe = df[df["triage_bucket"] == "maybe"].sort_values("triage_score", ascending=False)

    cols = [
        "triage_score",
        "triage_bucket",
        "triage_reason",
        "repo_id",
        "year",
        "title",
        "discovery_source",
        "source_link",
        "confidence_tier",
    ]

    reject_path = out / "clamps_theses_auto_rejected.csv"
    pdf_path = out / "clamps_theses_pdf_scan_queue.csv"
    short_path = out / "clamps_theses_manual_short.csv"

    reject.to_csv(reject_path, index=False)
    pdf_queue.to_csv(pdf_path, index=False)
    maybe.head(30).to_csv(short_path, index=False)

    print(f"Input rows: {len(df)}")
    print(f"  auto_reject:   {len(reject):4d}  -> {reject_path.name}")
    print(f"  pdf_scan queue:{len(pdf_queue):4d}  -> {pdf_path.name}")
    print(f"  maybe (top 30): {min(30, len(maybe)):4d}  -> {short_path.name}")
    print("\nBucket counts:")
    print(df["triage_bucket"].value_counts().sort_index().to_string())

    if len(pdf_queue):
        print("\nTop 10 PDF-scan candidates:")
        for _, r in pdf_queue.head(10).iterrows():
            print(f"  [{r['triage_score']}] {r['repo_id']} | {str(r['title'])[:65]}")

    if args.pdf_scan and len(pdf_queue):
        import subprocess

        to_scan = pdf_queue.head(args.pdf_limit)
        scan_in = out / "clamps_theses_pdf_scan_input.csv"
        to_scan.to_csv(scan_in, index=False)
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "scan_pdfs.py"),
            "--input",
            str(scan_in),
            "--delay",
            str(args.delay),
            "--limit",
            str(args.pdf_limit),
            "--workers",
            "4",
        ]
        print(f"\nRunning PDF scan on up to {args.pdf_limit} rows...")
        print(f"  input: {scan_in}")
        print(f"  log:   {out / 'clamps_scan_log.csv'} (shared with paper scan log)")
        subprocess.run(cmd, cwd=ROOT, check=False)
        print("Then: grep mentions_found output/clamps_scan_log.csv")


if __name__ == "__main__":
    main()
