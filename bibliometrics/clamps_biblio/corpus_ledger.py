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
    ("Final collection", "726 works after deduplication across streams"),
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
                "stream": "Final collection (deduplicated)",
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


def _discovered_path(root: Path) -> Path:
    return root / "output" / "clamps_papers_discovered_channels.csv"


def _hc_publications_path(root: Path) -> Path:
    return root / "output" / "clamps_papers_high_confidence_channels_with_pdfs.csv"


_ARTICLE_TYPES = frozenset({"article", "preprint", "review"})
_EXCLUDED_HC_TYPES = frozenset({"dissertation", "peer-review"})


def _load_discovered(root: Path) -> pd.DataFrame:
    path = _discovered_path(root)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def discovery_confidence_distribution(root: Path) -> pd.DataFrame:
    """Confidence tier counts for works in the merged discovery ledger."""
    disc = _load_discovered(root)
    if disc.empty or "confidence_tier" not in disc.columns:
        return pd.DataFrame(columns=["tier", "works", "score_range"])

    tier_order = ["high", "medium", "low"]
    tier_ranges = {
        "high": "score ≥ 6",
        "medium": "score 3–5",
        "low": "score < 3",
    }
    counts = disc["confidence_tier"].astype(str).value_counts()
    rows = [
        {
            "tier": tier,
            "works": int(counts.get(tier, 0)),
            "score_range": tier_ranges[tier],
        }
        for tier in tier_order
        if counts.get(tier, 0)
    ]
    return pd.DataFrame(rows)


def publication_filter_funnel(root: Path) -> pd.DataFrame:
    """Sequential publication filters, showing how Phase 1 scores are applied."""
    from clamps_biblio.relevance import qualifies_strict_high_confidence

    disc = _load_discovered(root)
    hc_path = _hc_publications_path(root)
    if disc.empty:
        return pd.DataFrame(columns=["step", "works", "notes"])

    eligible = disc[disc["exclusion_reason"].isna()] if "exclusion_reason" in disc.columns else disc
    n_disc = len(disc)
    n_topic_flagged = n_disc - len(eligible)
    n_low_tier = int((eligible["confidence_tier"].astype(str) == "low").sum()) if "confidence_tier" in eligible.columns else 0
    tier_ok = eligible[eligible["confidence_tier"].astype(str).isin(["high", "medium"])] if "confidence_tier" in eligible.columns else eligible
    strict_pass = tier_ok[tier_ok.apply(lambda r: qualifies_strict_high_confidence(r.to_dict()), axis=1)]
    n_hc_pool = len(pd.read_csv(hc_path)) if hc_path.exists() else 0

    n_pub_types = 0
    if hc_path.exists():
        hc = pd.read_csv(hc_path)
        for otype in hc["type"].astype(str).str.lower():
            if otype in _EXCLUDED_HC_TYPES or otype == "dataset":
                continue
            if otype in _ARTICLE_TYPES or otype == "report":
                n_pub_types += 1

    rows = [
        {
            "step": "1. Merged discovery ledger",
            "works": n_disc,
            "notes": "Unique works after channel merge; each has relevance_score + confidence_tier",
        },
        {
            "step": "2. Topic exclusions removed",
            "works": len(eligible),
            "notes": f"{n_topic_flagged} works flagged (non-meteorology / literary false positives)",
        },
        {
            "step": "3. Low-confidence tier removed",
            "works": len(tier_ok),
            "notes": f"{n_low_tier} low-tier works dropped (score < 3); gate requires medium or high",
        },
        {
            "step": "4. Strict HC gate (channel rules)",
            "works": len(strict_pass),
            "notes": "Medium/high tier plus channel-specific CLAMPS evidence rules (see Phase 2 table)",
        },
        {
            "step": "5. HC publication checkpoint",
            "works": n_hc_pool,
            "notes": "Curated pool after strict gate + pipeline export (`…_with_pdfs.csv`)",
        },
        {
            "step": "6. Publication type filter",
            "works": n_pub_types,
            "notes": "Articles, preprints, reviews, reports — excludes theses and peer-review comments",
        },
    ]
    return pd.DataFrame(rows)


def strict_gate_by_channel(root: Path) -> pd.DataFrame:
    """How many eligible works pass the strict HC gate, by discovery channel."""
    from clamps_biblio.relevance import qualifies_strict_high_confidence
    from clamps_biblio.work_keys import channel_bucket

    disc = _load_discovered(root)
    if disc.empty:
        return pd.DataFrame(columns=["channel", "eligible", "pass_strict_gate", "pct_pass"])

    eligible = disc[disc["exclusion_reason"].isna()] if "exclusion_reason" in disc.columns else disc
    tier_ok = eligible[eligible["confidence_tier"].astype(str).isin(["high", "medium"])] if "confidence_tier" in eligible.columns else eligible
    if tier_ok.empty:
        return pd.DataFrame(columns=["channel", "eligible", "pass_strict_gate", "pct_pass"])

    tier_ok = tier_ok.copy()
    tier_ok["_channel"] = _discovery_channel_series(tier_ok)
    tier_ok["_pass"] = tier_ok.apply(lambda r: qualifies_strict_high_confidence(r.to_dict()), axis=1)

    rows = []
    for ch, grp in tier_ok.groupby("_channel"):
        passed = int(grp["_pass"].sum())
        total = len(grp)
        rows.append(
            {
                "channel": CHANNEL_LABELS.get(ch, ch),
                "eligible_medium_high": total,
                "pass_strict_gate": passed,
                "pct_pass": round(100 * passed / total, 1) if total else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values("eligible_medium_high", ascending=False)


def inclusion_stream_counts(root: Path) -> pd.DataFrame:
    """Four parallel streams merged into the final corpus (pre-deduplication)."""
    streams = merge_stream_counts(root)
    if streams.empty:
        return streams
    return streams[~streams["stream"].astype(str).str.startswith("Final collection")].copy()


def corpus_composition(root: Path) -> pd.DataFrame:
    """Work-type breakdown of the finalized review collection."""
    path = root / "output" / "clamps_review_corpus_clean.csv"
    if not path.exists():
        path = root / "output" / "clamps_review_corpus.csv"
    if not path.exists():
        return pd.DataFrame(columns=["work_type", "count"])
    corpus = pd.read_csv(path)
    col = "work_type" if "work_type" in corpus.columns else "corpus_class"
    counts = corpus[col].astype(str).value_counts().sort_index()
    return counts.rename_axis("work_type").reset_index(name="count")


def fulltext_impact_funnel(root: Path) -> pd.DataFrame:
    """Full-text evidence funnel for the published-literature subset."""
    from clamps_biblio.pdf_use_classifier import classify_pdf_confirmed
    from clamps_biblio.review_metrics_data import load_corpus_review_frames

    try:
        frames = load_corpus_review_frames(root)
    except FileNotFoundError:
        return pd.DataFrame(columns=["step", "works", "notes"])

    pub = frames["pdf_confirmed"]
    classified = classify_pdf_confirmed(pub, frames["mentions"], id_col="openalex_id")

    def _has_evidence(row: pd.Series) -> bool:
        ctx = str(row.get("sample_context", "") or "").strip()
        if ctx:
            return True
        count = pd.to_numeric(row.get("pdf_mention_count", 0), errors="coerce")
        return pd.notna(count) and count > 0

    with_mention = classified[classified.apply(_has_evidence, axis=1)]
    substantive = classified[classified["use_tier"].isin([1, 2])]

    rows = [
        {
            "step": "Published literature in collection",
            "works": len(pub),
            "notes": "Articles, reports, and preprints (590 of 726 total works)",
        },
        {
            "step": "Full-text CLAMPS mention found",
            "works": len(with_mention),
            "notes": "PDF/HTML scan produced CLAMPS mention snippets",
        },
        {
            "step": "Substantive use (Tier 1+2)",
            "works": len(substantive),
            "notes": "Classified as data, analysis, or discussion — not peripheral references",
        },
    ]
    return pd.DataFrame(rows)
