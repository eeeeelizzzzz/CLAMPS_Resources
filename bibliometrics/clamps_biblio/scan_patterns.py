from __future__ import annotations

import re

from clamps_biblio.clamps_signals import CLAMPS_SIGNAL_PATTERNS, INSTRUMENT_CONTEXT_PATTERNS
from clamps_biblio.repository_links import build_data_repository_patterns
from clamps_biblio.config import Config
from clamps_biblio.text_scanner import compile_literal_patterns, compile_patterns


def build_scan_patterns(cfg: Config, include_instrument_context: bool = True) -> list:
    """Build all PDF scan patterns with human-readable labels."""
    patterns: list[tuple[str, re.Pattern[str]]] = list(CLAMPS_SIGNAL_PATTERNS)
    if include_instrument_context:
        patterns.extend(INSTRUMENT_CONTEXT_PATTERNS)
    patterns.extend(compile_patterns(cfg.text_patterns))
    patterns.extend(build_data_repository_patterns(cfg.data_repository_links))
    for grant in cfg.grant_numbers:
        patterns.append((f"grant:{grant}", re.compile(re.escape(grant), re.IGNORECASE)))
    for doi in cfg.dataset_dois:
        patterns.append((f"dataset_doi:{doi}", re.compile(re.escape(doi), re.IGNORECASE)))
    return patterns
