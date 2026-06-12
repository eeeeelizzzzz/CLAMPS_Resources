"""Shared row enrichment for discovery outputs."""

from __future__ import annotations

from typing import Any

from clamps_biblio.clamps_signals import all_signals_in_text
from clamps_biblio.config import Config
from clamps_biblio.relevance import metadata_text, score_work
from clamps_biblio.repository_links import repository_signals_in_text


def enrich_row(row: dict[str, Any], cfg: Config) -> dict[str, Any]:
    out = dict(row)
    score, tier = score_work(out)
    out["relevance_score"] = score
    out["confidence_tier"] = tier
    meta_terms = all_signals_in_text(metadata_text(out))
    meta_terms.extend(repository_signals_in_text(metadata_text(out), cfg.data_repository_links))
    meta_terms = list(dict.fromkeys(meta_terms))
    out["metadata_matched_terms"] = "; ".join(meta_terms) if meta_terms else ""
    out["discovery_match"] = str(out.get("discovery_source", "")).split(":", 1)[-1]
    return out


def enrich_rows(rows: list[dict[str, Any]], cfg: Config) -> list[dict[str, Any]]:
    return [enrich_row(row, cfg) for row in rows]
