"""Shared CLAMPS identity signals for scoring and filtering."""

from __future__ import annotations

import re

# --- Strong signals: direct CLAMPS facility identity ---
CLAMPS_SIGNAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Numbered facility tokens are case-sensitive (CLAMPS1 not clamps1 biology).
    ("CLAMPS-1/2", re.compile(r"\bCLAMPS[-\s][12]\b")),
    ("CLAMPS1/2", re.compile(r"\bCLAMPS[12]\b")),
    (
        "full_name",
        re.compile(r"Collaborative Lower Atmospheric Mobile Profiling System", re.IGNORECASE),
    ),
    ("MP-1", re.compile(r"\bMP[- ]?1\b", re.IGNORECASE)),  # PECAN: Mobile PISA 1
    ("Mobile PISA", re.compile(r"Mobile PISA[- ]?(?:1|I)?\b", re.IGNORECASE)),
    # NSSL mobile profiling AND NSSL mobile profiler (profil(?:ing|er) covers both)
    ("NSSL mobile profiler", re.compile(r"NSSL mobile profil(?:ing|er)", re.IGNORECASE)),
    ("NSSL profiler", re.compile(r"NSSL profil(?:ing|er)", re.IGNORECASE)),
]

# --- Contextual signals: instrument/data stream (weaker — verify manually) ---
INSTRUMENT_CONTEXT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("NSSL lidar", re.compile(r"NSSL[^\n]{0,120}(?:Doppler )?(?:wind )?lidar", re.IGNORECASE)),
    ("OU lidar", re.compile(
        r"(?:University of Oklahoma|\bOU\b)[^\n]{0,120}(?:Doppler )?(?:wind )?lidar", re.IGNORECASE
    )),
    ("NSSL AERI", re.compile(r"NSSL[^\n]{0,80}\bAERI(?:oe)?\b", re.IGNORECASE)),
    ("OU AERI", re.compile(
        r"(?:University of Oklahoma|\bOU\b)[^\n]{0,80}\bAERI(?:oe)?\b", re.IGNORECASE
    )),
    ("NSSL MWR", re.compile(r"NSSL[^\n]{0,80}(?:MWR|microwave radiometer)", re.IGNORECASE)),
    ("OU MWR", re.compile(
        r"(?:University of Oklahoma|\bOU\b)[^\n]{0,80}(?:MWR|microwave radiometer)", re.IGNORECASE
    )),
    ("NSSL sounding", re.compile(r"NSSL[^\n]{0,80}(?:radiosonde|soundings?)", re.IGNORECASE)),
    ("OU sounding", re.compile(
        r"(?:University of Oklahoma|\bOU\b)[^\n]{0,80}(?:radiosonde|soundings?)", re.IGNORECASE
    )),
    ("AERI retrieval", re.compile(r"\bAERI(?:oe)?\b[^\n]{0,80}retriev(?:al|e)", re.IGNORECASE)),
    ("lidar retrieval", re.compile(r"lidar[^\n]{0,80}retriev(?:al|e)", re.IGNORECASE)),
]

STRONG_MATCH_LABELS = frozenset(
    label for label, _ in CLAMPS_SIGNAL_PATTERNS
) | frozenset({"grant", "dataset_doi"})

CONTEXTUAL_MATCH_LABELS = frozenset(label for label, _ in INSTRUMENT_CONTEXT_PATTERNS)

def signals_in_text(
    text: str,
    patterns: list[tuple[str, re.Pattern[str]]],
) -> list[str]:
    if not text:
        return []
    return [label for label, pattern in patterns if pattern.search(text)]


def clamps_signals_in_text(text: str) -> list[str]:
    return signals_in_text(text, CLAMPS_SIGNAL_PATTERNS)


def instrument_signals_in_text(text: str) -> list[str]:
    return signals_in_text(text, INSTRUMENT_CONTEXT_PATTERNS)


def all_signals_in_text(text: str) -> list[str]:
    strong = clamps_signals_in_text(text)
    contextual = instrument_signals_in_text(text)
    return strong + [s for s in contextual if s not in strong]


def has_clamps_signal(text: str) -> bool:
    return bool(clamps_signals_in_text(text))


def is_campaign_only_signal(text: str) -> bool:
    from clamps_biblio.field_campaigns import is_campaign_only_signal as _campaign_only

    return _campaign_only(text)


def classify_match_strength(matched_labels: set[str]) -> str:
    """Classify a set of matched pattern labels."""
    if not matched_labels:
        return ""
    has_strong = any(
        label in STRONG_MATCH_LABELS
        or label.startswith("10.")
        or label.startswith("AGS-")
        or label.startswith("data_url:")
        or label.startswith("grant:")
        or label.startswith("dataset_doi:")
        for label in matched_labels
    )
    has_context = any(label in CONTEXTUAL_MATCH_LABELS for label in matched_labels)
    if has_strong and has_context:
        return "strong+contextual"
    if has_strong:
        return "strong"
    if has_context:
        return "contextual"
    return "other"
