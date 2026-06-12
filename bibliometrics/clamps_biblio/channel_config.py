from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_discovery_channels(path: Path | None = None) -> dict[str, Any]:
    return _load_yaml(path or ROOT / "data" / "discovery_channels.yaml")


def load_author_seeds(path: Path | None = None) -> dict[str, Any]:
    return _load_yaml(path or ROOT / "data" / "author_seeds.yaml")


def load_campaign_anchors(path: Path | None = None) -> dict[str, Any]:
    return _load_yaml(path or ROOT / "data" / "campaign_anchors.yaml")


def load_campaign_full_names(path: Path | None = None) -> dict[str, Any]:
    return _load_yaml(path or ROOT / "data" / "campaign_full_names.yaml")


def load_topic_filters(path: Path | None = None) -> dict[str, Any]:
    return _load_yaml(path or ROOT / "data" / "topic_filters.yaml")


def load_source_allowlist(path: Path | None = None) -> dict[str, Any]:
    return _load_yaml(path or ROOT / "data" / "source_allowlist.yaml")


def load_ground_truth(path: Path | None = None) -> pd.DataFrame:
    p = path or ROOT / "data" / "ground_truth_clamps_papers.csv"
    return pd.read_csv(p)


def load_dataset_dois(path: Path | None = None) -> list[str]:
    from clamps_biblio.config import load_dataset_dois as _load

    p = path or ROOT / "data" / "clamps_dataset_dois.txt"
    return _load(p)
