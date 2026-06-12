#!/usr/bin/env python3
"""Classify PDF-confirmed CLAMPS publications by substantive use tier."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.nwc_affiliation import NWC_AFFILIATED, NON_AFFILIATED, UNKNOWN
from clamps_biblio.pdf_use_classifier import TIER_LABELS, classify_pdf_confirmed
from clamps_biblio.review_metrics_data import load_review_frames


def tier_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for tier in sorted(df["use_tier"].unique()):
        sub = df[df["use_tier"] == tier]
        peer = sub[sub["is_peer_reviewed"] == True]  # noqa: E712
        rows.append(
            {
                "use_tier": int(tier),
                "use_tier_label": TIER_LABELS[int(tier)],
                "all_works": len(sub),
                "peer_reviewed": len(peer),
                "nwc_affiliated": int((sub["affiliation"] == NWC_AFFILIATED).sum()),
                "non_affiliated": int((sub["affiliation"] == NON_AFFILIATED).sum()),
                "unknown_affiliation": int((sub["affiliation"] == UNKNOWN).sum()),
                "needs_manual_review": int(sub["needs_manual_review"].sum()),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify PDF-confirmed papers by CLAMPS use tier.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "review_metrics")
    args = parser.parse_args()
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    frames = load_review_frames(ROOT)
    pdf = frames["pdf_confirmed"]
    mentions = frames["mentions"]

    classified = classify_pdf_confirmed(pdf, mentions, id_col="openalex_id")
    classified.to_csv(out_dir / "pdf_use_classification.csv", index=False)

    review_queue = classified[classified["needs_manual_review"] | (classified["use_tier"] == 3)].copy()
    review_queue = review_queue.sort_values(["use_tier", "pdf_mention_count"], ascending=[True, False])
    review_queue.to_csv(out_dir / "pdf_use_manual_review_queue.csv", index=False)

    summary = tier_summary(classified)
    summary.to_csv(out_dir / "pdf_use_tier_summary.csv", index=False)

    # Local PDFs (filename-keyed mentions)
    local_log = frames["local_log"]
    local_mentions = pd.read_csv(ROOT / "output/clamps_local_mentions.csv")
    local_hits = local_log[local_log["status"] == "mentions_found"].copy()
    local_classified = pd.DataFrame()
    if not local_hits.empty:
        local_hits["openalex_id"] = local_hits["filename"]
        local_hits["affiliation"] = ""
        local_hits["is_peer_reviewed"] = True
        local_hits["pdf_mention_count"] = local_hits["mention_count"]
        local_hits["discovery_source"] = "manual_download"
        local_classified = classify_pdf_confirmed(local_hits, local_mentions, id_col="openalex_id")
        local_classified.to_csv(out_dir / "pdf_use_classification_local.csv", index=False)

    # Console summary
    print(f"Wrote classification to {out_dir}/")
    print(f"  pdf_use_classification.csv ({len(classified)} remote PDF-confirmed)")
    print(f"  pdf_use_manual_review_queue.csv ({len(review_queue)} for review)")
    print(f"  pdf_use_tier_summary.csv")
    if not local_hits.empty:
        print(f"  pdf_use_classification_local.csv ({len(local_classified)} local PDFs)")

    print("\nUse tier summary (remote):")
    for _, r in summary.iterrows():
        print(
            f"  Tier {int(r['use_tier'])} {r['use_tier_label']}: "
            f"{int(r['all_works'])} total, {int(r['peer_reviewed'])} peer-reviewed "
            f"({int(r['needs_manual_review'])} need manual review)"
        )

    substantive = classified[classified["use_tier"].isin([1, 2])]
    peer_sub = substantive[substantive["is_peer_reviewed"] == True]  # noqa: E712
    print(
        f"\nSubstantive use (Tier 1+2): {len(substantive)} works, "
        f"{len(peer_sub)} peer-reviewed"
    )


if __name__ == "__main__":
    main()
