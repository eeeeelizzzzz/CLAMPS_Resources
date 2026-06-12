"""Manual deposit/work classifications from output/clamps_data_deposits.csv.

work_class codes (user-maintained):
  x   dataset — data product, not a publication scan target
  n   not relevant — exclude from discovery / scan pools
  a   article — include in publication HTML queue even if hosted on Zenodo/repo
  r   report — include in publication HTML queue
  dup duplicate — treat like n
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from clamps_biblio.pdf_resolver import normalize_doi

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CLASSIFICATIONS_PATH = ROOT / "output" / "clamps_data_deposits.csv"
WORK_CLASS_COLUMN = "work_class"
SEARCH_EXCLUDE_CLASSES = frozenset({"n", "dup"})
PUBLICATION_INCLUDE_CLASSES = frozenset({"a", "r"})


def _normalize_class(value: Any) -> str:
    return str(value or "").strip().lower()


@lru_cache(maxsize=4)
def _load_by_doi(path_str: str) -> dict[str, str]:
    path = Path(path_str)
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    if WORK_CLASS_COLUMN not in df.columns and "Unnamed: 2" in df.columns:
        df = df.rename(columns={"Unnamed: 2": WORK_CLASS_COLUMN})
    if WORK_CLASS_COLUMN not in df.columns:
        return {}
    by_doi: dict[str, str] = {}
    for _, row in df.iterrows():
        doi = normalize_doi(row.get("doi"))
        cls = _normalize_class(row.get(WORK_CLASS_COLUMN))
        if doi and cls:
            by_doi[doi] = cls
    return by_doi


def classifications_path(path: Path | None = None) -> Path:
    return path or DEFAULT_CLASSIFICATIONS_PATH


def get_work_class(row: dict[str, Any] | Any, path: Path | None = None) -> str:
    get = row.get if hasattr(row, "get") else lambda k, d="": ""
    doi = normalize_doi(str(get("doi", "") or ""))
    if doi:
        cls = _load_by_doi(str(classifications_path(path))).get(doi, "")
        if cls:
            return cls
    return _normalize_class(get(WORK_CLASS_COLUMN, ""))


def is_search_excluded(row: dict[str, Any] | Any, path: Path | None = None) -> bool:
    return get_work_class(row, path=path) in SEARCH_EXCLUDE_CLASSES


def search_exclusion_reason(row: dict[str, Any] | Any, path: Path | None = None) -> str:
    cls = get_work_class(row, path=path)
    if cls in SEARCH_EXCLUDE_CLASSES:
        return f"excluded:deposit_class:{cls}"
    return ""


def is_publication_override(row: dict[str, Any] | Any, path: Path | None = None) -> bool:
    return get_work_class(row, path=path) in PUBLICATION_INCLUDE_CLASSES


def excluded_dois(path: Path | None = None) -> set[str]:
    by_doi = _load_by_doi(str(classifications_path(path)))
    return {doi for doi, cls in by_doi.items() if cls in SEARCH_EXCLUDE_CLASSES}


def clear_cache() -> None:
    _load_by_doi.cache_clear()
