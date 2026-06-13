"""Discovery funnel and corpus-merge summaries for notebook display."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

CHANNEL_LABELS: dict[str, str] = {
    "channel_a": "A — Facility identity phrases",
    "channel_b": "B — Campaign × instrument compound queries",
    "channel_c": "C — Dataset DOI & grant citations",
    "channel_d": "D — Author seed bibliographies",
    "channel_e": "E — Campaign anchor-paper author groups",
    "channel_f": "F — OpenAlex thesis institutions",
    "channel_g": "G — Ground-truth DOI registry",
    "channel_h": "H — Institutional repository thesis crawl",
}

FUNNEL_STEPS: list[tuple[str, str]] = [
    ("OpenAlex multi-channel discovery", "Channels A–H merged (see breakdown below)"),
    ("Deduplication", "Unique works by DOI / OpenAlex ID"),
    ("Topic exclusions", "Non-meteorology topics removed"),
    ("Strict high-confidence gate", "CLAMPS evidence required in metadata"),
    ("Type filter (articles/reports)", "Excludes dissertations, peer-review comments"),
    ("Add validated datasets", "Seed registry + discovered deposits"),
    ("Add ground-truth bypass", "Mandatory registry works"),
    ("Add manual theses", "Channel H/F with manual_flag=y"),
    ("Final corpus", "726 works after deduplication across streams"),
]


def _discovery_channel_series(disc: pd.DataFrame) -> pd.Series:
    """Channel key per row; checkpoints may only have discovery_source."""
    if "discovery_channel" in disc.columns:
        return disc["discovery_channel"].astype(str)
    if "discovery_source" in disc.columns:
        from clamps_biblio.work_keys import channel_bucket

        return disc["discovery_source"].map(channel_bucket).astype(str)
    return pd.Series(dtype=str)


def discovery_channel_counts(root: Path) -> pd.DataFrame:
    """Count works per discovery channel from the discovery checkpoint."""
    path = root / "output" / "clamps_papers_discovered_channels.csv"
    if not path.exists():
        return pd.DataFrame(columns=["channel", "label", "works"])
    disc = pd.read_csv(path)
    channels = _discovery_channel_series(disc)
    if channels.empty:
        return pd.DataFrame(columns=["channel", "label", "works"])
    counts = channels.value_counts().sort_index()
    rows = [
        {
            "channel": ch,
            "label": CHANNEL_LABELS.get(ch, ch),
            "works": int(n),
        }
        for ch, n in counts.items()
    ]
    return pd.DataFrame(rows)


def merge_stream_counts(root: Path) -> pd.DataFrame:
    """Counts for the four corpus inclusion streams (pre-deduplication)."""
    rows: list[dict] = []

    hc_path = root / "output" / "clamps_papers_high_confidence_channels_with_pdfs.csv"
    if hc_path.exists():
        hc = pd.read_csv(hc_path)
        rows.append(
            {
                "stream": "HC publications",
                "source_file": hc_path.name,
                "works": len(hc),
                "description": "Articles/reports after discovery gate and type filter",
            }
        )

    dep_path = root / "output" / "clamps_data_deposits.csv"
    if dep_path.exists():
        dep = pd.read_csv(dep_path)
        validated = dep[dep["work_class"].astype(str).str.lower() == "x"] if "work_class" in dep.columns else dep
        rows.append(
            {
                "stream": "Validated datasets",
                "source_file": dep_path.name,
                "works": len(validated),
                "description": "work_class=x deposits (65 seed + 42 discovered)",
            }
        )

    thesis_path = root / "output" / "clamps_theses_master_list.csv"
    if thesis_path.exists():
        th = pd.read_csv(thesis_path)
        accepted = th[th["manual_flag"].astype(str).str.strip().str.lower() == "y"]
        rows.append(
            {
                "stream": "Manual theses",
                "source_file": thesis_path.name,
                "works": len(accepted),
                "description": "Channel H/F theses with manual_flag=y",
            }
        )

    disc_path = root / "output" / "clamps_papers_discovered_channels.csv"
    gt_path = root / "data" / "ground_truth_clamps_papers.csv"
    if disc_path.exists() and gt_path.exists():
        from clamps_biblio.channel_config import load_ground_truth
        from clamps_biblio.pdf_resolver import normalize_doi

        gt = load_ground_truth(gt_path)
        gt_dois = {
            normalize_doi(d).lower()
            for d in gt.get("doi", pd.Series(dtype=str)).dropna()
            if normalize_doi(d)
        }
        disc = pd.read_csv(disc_path)
        n_gt = 0
        for row in disc.to_dict("records"):
            doi = normalize_doi(row.get("doi"))
            src = str(row.get("discovery_source", "") or "")
            if (doi and doi.lower() in gt_dois) or "channel_g:ground_truth" in src:
                n_gt += 1
        rows.append(
            {
                "stream": "Ground-truth mandatory",
                "source_file": f"{disc_path.name} + {gt_path.name}",
                "works": n_gt,
                "description": "Registry bypass (Channel G); overlaps other streams",
            }
        )

    corpus_path = root / "output" / "clamps_review_corpus.csv"
    if corpus_path.exists():
        corpus = pd.read_csv(corpus_path)
        rows.append(
            {
                "stream": "Final corpus (deduplicated)",
                "source_file": corpus_path.name,
                "works": len(corpus),
                "description": "Unique works after merge; 61 overlaps removed",
            }
        )

    return pd.DataFrame(rows)


def funnel_summary_table() -> pd.DataFrame:
    """Static funnel steps with narrative (checkpoint reproduction path)."""
    return pd.DataFrame(
        [{"step": step, "notes": notes} for step, notes in FUNNEL_STEPS]
    )
