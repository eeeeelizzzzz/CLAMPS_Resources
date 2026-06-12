"""Classify PDF-confirmed CLAMPS publications by substantive use tier."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

TIER_LABELS = {
    0: "exclude (false positive)",
    1: "data / instrument use",
    2: "analytical / discussion use",
    3: "peripheral / reference only",
}

METHODS_CUES = re.compile(
    r"\b(methods?|instrument|observ|deployed|deployment|measurement|measured|"
    r"dataset|data set|during the|field campaign|colocated|co-located|site)\b",
    re.I,
)
RESULTS_CUES = re.compile(
    r"\b(results?|figure|fig\.|case stud|analysis|analyzed|compared|retrieved|"
    r"profile|profiles|boundary layer|thermodynamic|kinematic)\b",
    re.I,
)
REFERENCE_CUES = re.compile(
    r"\bet al\.|https://doi\.org|doi:|Mon\.\s*Wea\.\s*Rev|https://doi|"
    r"described by|prior work|previous stud",
    re.I,
)
FACILITY_CUES = re.compile(
    r"Collaborative Lower|Mobile Profil|CLAMPS[-\s]?[12]|nssl\.noaa\.gov/tools/clamps|"
    r"Mobile PISA|MP[- ]?1",
    re.I,
)
FALSE_POSITIVE_CLAMPS = re.compile(r"\bclamped\b|\bclamping\b", re.I)

STRONG_TERM_PREFIXES = ("CLAMPS", "full_name", "MP-1", "Mobile PISA", "NSSL mobile")
DATA_TERM_PREFIXES = ("dataset_doi:", "data_url:", "grant:")


@dataclass
class MentionFeatures:
    n_mentions: int = 0
    n_pages: int = 0
    has_clamps_label: bool = False
    has_full_name: bool = False
    has_data_signal: bool = False
    has_grant: bool = False
    has_repository: bool = False
    has_instrument: bool = False
    has_methods_cue: bool = False
    has_results_cue: bool = False
    n_reference_cues: int = 0
    n_facility_cues: int = 0
    false_positive_clamps: bool = False
    sample_contexts: list[str] = field(default_factory=list)


def _term_flags(matched_terms: str) -> dict[str, bool]:
    terms = [t.strip() for t in str(matched_terms or "").split(";") if t.strip()]
    lower = [t.lower() for t in terms]
    return {
        "has_clamps_label": any(t == "CLAMPS" for t in terms),
        "has_full_name": any(t == "full_name" for t in terms),
        "has_data_signal": any(t.startswith("dataset_doi:") for t in terms),
        "has_grant": any(t.startswith("grant:") for t in terms),
        "has_repository": any(t.startswith("data_url:") for t in terms),
        "has_instrument": any(
            any(k in t for k in ("nssl", "ou lidar", "ou aeri", "ou mwr", "ou sounding"))
            for t in lower
        ),
        "has_strong": any(
            t in ("CLAMPS", "full_name", "MP-1", "Mobile PISA")
            or any(t.startswith(p) for p in STRONG_TERM_PREFIXES)
            for t in terms
        ),
    }


def extract_mention_features(
    paper_mentions: pd.DataFrame,
    matched_terms: str,
) -> MentionFeatures:
    flags = _term_flags(matched_terms)
    feats = MentionFeatures(
        has_clamps_label=flags["has_clamps_label"],
        has_full_name=flags["has_full_name"],
        has_data_signal=flags["has_data_signal"],
        has_grant=flags["has_grant"],
        has_repository=flags["has_repository"],
        has_instrument=flags["has_instrument"],
    )
    if paper_mentions.empty:
        return feats

    feats.n_mentions = len(paper_mentions)
    if "page" in paper_mentions.columns:
        feats.n_pages = int(paper_mentions["page"].nunique())

    contexts: list[str] = []
    for _, m in paper_mentions.iterrows():
        ctx = str(m.get("context", "") or "")
        contexts.append(ctx)
        if METHODS_CUES.search(ctx):
            feats.has_methods_cue = True
        if RESULTS_CUES.search(ctx):
            feats.has_results_cue = True
        if REFERENCE_CUES.search(ctx):
            feats.n_reference_cues += 1
        if FACILITY_CUES.search(ctx):
            feats.n_facility_cues += 1

        if str(m.get("pattern", "")) == "CLAMPS":
            if FALSE_POSITIVE_CLAMPS.search(ctx) and not FACILITY_CUES.search(ctx):
                feats.false_positive_clamps = True

    feats.sample_contexts = contexts[:3]
    return feats


def classify_paper(
    row: pd.Series,
    feats: MentionFeatures,
) -> tuple[int, int, list[str], bool, str]:
    """
    Return (use_tier, use_score, reason_codes, needs_manual_review, review_reason).
    """
    reasons: list[str] = []
    score = 0
    match_strength = str(row.get("match_strength", "") or "")
    mention_count = int(row.get("pdf_mention_count", feats.n_mentions) or 0)
    discovery = str(row.get("discovery_source", "") or "")
    topics = str(row.get("topics", "") or "").lower()

    if feats.has_data_signal:
        score += 40
        reasons.append("dataset_doi")
    if feats.has_repository:
        score += 35
        reasons.append("data_repository")
    if feats.has_grant:
        score += 30
        reasons.append("grant")
    if feats.has_full_name:
        score += 25
        reasons.append("full_facility_name")
    if feats.has_clamps_label and feats.n_facility_cues > 0:
        score += 20
        reasons.append("clamps_facility_context")
    if feats.has_instrument:
        score += 15
        reasons.append("nssl_ou_instrument")
    if match_strength == "strong+contextual":
        score += 15
        reasons.append("strong+contextual")
    elif match_strength == "strong":
        score += 10
        reasons.append("strong_match")
    if mention_count >= 5:
        score += 10
        reasons.append("multiple_mentions")
    elif mention_count >= 2:
        score += 5
        reasons.append("repeated_mentions")
    if feats.has_methods_cue:
        score += 10
        reasons.append("methods_context")
    if feats.has_results_cue:
        score += 10
        reasons.append("results_context")
    if discovery.startswith("campaign_clamps:"):
        score += 5
        reasons.append("campaign_discovery")

    # Penalties
    if feats.false_positive_clamps:
        score -= 100
        reasons.append("false_positive_clamped")

    unrelated_topics = ("planetary", "europa", "astro", "spacecraft", "extraterrestrial")
    if feats.false_positive_clamps or (
        feats.has_clamps_label
        and mention_count == 1
        and any(t in topics for t in unrelated_topics)
    ):
        tier = 0
        review = False
        review_reason = ""
        if feats.false_positive_clamps:
            reasons.append("exclude_word_collision")
        else:
            reasons.append("exclude_unrelated_topic")
        return tier, score, reasons, review, review_reason

    has_substantive_context = feats.has_methods_cue or feats.has_results_cue
    has_data_evidence = feats.has_data_signal or feats.has_repository or feats.has_grant

    if has_data_evidence or (
        (feats.has_clamps_label or feats.has_full_name)
        and has_substantive_context
        and mention_count >= 2
    ):
        tier = 1
    elif match_strength == "contextual" and not feats.has_clamps_label and not has_substantive_context:
        if mention_count <= 3 and feats.n_reference_cues >= max(1, mention_count // 2):
            tier = 3
            reasons.append("reference_heavy")
        elif mention_count <= 2:
            tier = 3
            reasons.append("weak_contextual")
        else:
            tier = 2
    elif score >= 20 or (match_strength in ("strong", "strong+contextual") and mention_count >= 2):
        tier = 2
    elif score >= 5 or mention_count >= 1:
        tier = 3
    else:
        tier = 3

    needs_review = False
    review_reason = ""

    if tier == 3 and mention_count >= 4:
        needs_review = True
        review_reason = "Peripheral tier but many mentions — may be substantive"
    elif tier == 2 and match_strength == "contextual" and not feats.has_clamps_label:
        needs_review = True
        review_reason = "Tier 2 based on instrument context only"
    elif tier == 1 and not has_data_evidence and mention_count <= 2:
        needs_review = True
        review_reason = "Tier 1 with limited mention count — confirm deployment/data use"
    elif tier == 3 and feats.has_clamps_label and has_substantive_context:
        needs_review = True
        review_reason = "CLAMPS named with methods/results language but scored peripheral"

    return tier, score, reasons, needs_review, review_reason


def classify_pdf_confirmed(
    papers: pd.DataFrame,
    mentions: pd.DataFrame,
    id_col: str = "openalex_id",
) -> pd.DataFrame:
    """Classify each PDF-confirmed paper; returns enriched DataFrame."""
    mention_groups = {
        str(k): g for k, g in mentions.groupby(mentions[id_col].astype(str))
    } if id_col in mentions.columns else {}

    rows: list[dict] = []
    for _, row in papers.iterrows():
        pid = str(row.get(id_col, row.get("filename", "")))
        paper_mentions = mention_groups.get(pid, pd.DataFrame())
        feats = extract_mention_features(paper_mentions, str(row.get("matched_terms", "")))
        tier, score, reasons, needs_review, review_reason = classify_paper(row, feats)

        rows.append(
            {
                id_col: pid,
                "title": row.get("title", ""),
                "year": row.get("year", ""),
                "doi": row.get("doi", ""),
                "type": row.get("type", ""),
                "affiliation": row.get("affiliation", ""),
                "is_peer_reviewed": row.get("is_peer_reviewed", ""),
                "match_strength": row.get("match_strength", ""),
                "pdf_mention_count": row.get("pdf_mention_count", feats.n_mentions),
                "matched_terms": row.get("matched_terms", ""),
                "discovery_source": row.get("discovery_source", ""),
                "use_tier": tier,
                "use_tier_label": TIER_LABELS[tier],
                "use_score": score,
                "use_signals": "; ".join(reasons),
                "needs_manual_review": needs_review,
                "review_reason": review_reason,
                "sample_context": " | ".join(feats.sample_contexts)[:500],
            }
        )

    out = pd.DataFrame(rows)
    tier_order = {0: 0, 1: 1, 2: 2, 3: 3}
    out["_sort"] = out["use_tier"].map(tier_order)
    return out.sort_values(["_sort", "use_score"], ascending=[True, False]).drop(columns="_sort")
