from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from clamps_biblio.repository_links import repository_search_phrases

DOI_PATTERN = re.compile(r"10\.\d+/[^\s\"']+")


@dataclass
class Config:
    openalex_mailto: str | None
    institutions: dict[str, str]
    institution_filter: bool
    strict_high_confidence: bool
    ambiguous_campaigns: list[str]
    seed_works: list[dict[str, str]]
    dataset_dois: list[str]
    field_campaigns: list[str]
    campaign_extra_terms: dict[str, list[str]]
    search_phrases: list[str]
    repository_search_phrases: list[str]
    openalex_delay: float
    text_patterns: list[str]
    grant_numbers: list[str]
    data_repository_links: list[dict[str, str] | str]
    output_dir: Path
    papers_csv: str
    mentions_csv: str
    scan_log_csv: str


def load_dataset_dois(path: Path) -> list[str]:
    if not path.exists():
        return []
    dois: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for match in DOI_PATTERN.findall(line):
            if match not in seen:
                seen.add(match)
                dois.append(match)
    return sorted(dois)


def load_config(path: Path | None = None) -> Config:
    root = Path(__file__).resolve().parent.parent
    config_path = path or root / "config.yaml"
    with config_path.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    discovery = raw.get("discovery", {})
    dataset_dois_file = discovery.get("dataset_dois_file", "data/clamps_dataset_dois.txt")
    dataset_dois_path = Path(dataset_dois_file)
    if not dataset_dois_path.is_absolute():
        dataset_dois_path = root / dataset_dois_path

    output = raw.get("output", {})
    data_repository_links = raw.get("data_repository_links", [])
    search_phrases = list(raw.get("search_phrases", []))
    repo_phrases = repository_search_phrases(data_repository_links)

    return Config(
        openalex_mailto=raw.get("openalex", {}).get("mailto"),
        institutions=raw.get("institutions", {}),
        institution_filter=discovery.get("institution_filter", False),
        strict_high_confidence=discovery.get("strict_high_confidence", True),
        ambiguous_campaigns=discovery.get("ambiguous_campaigns", []),
        seed_works=raw.get("seed_works", []),
        dataset_dois=load_dataset_dois(dataset_dois_path),
        field_campaigns=raw.get("field_campaigns", []),
        campaign_extra_terms=raw.get("campaign_extra_terms", {}),
        search_phrases=search_phrases,
        repository_search_phrases=repo_phrases,
        openalex_delay=float(discovery.get("openalex_delay", 1.0)),
        text_patterns=raw.get("text_patterns", []),
        grant_numbers=raw.get("grant_numbers", []),
        data_repository_links=data_repository_links,
        output_dir=Path(output.get("directory", "output")),
        papers_csv=output.get("papers_csv", "clamps_papers_discovered.csv"),
        mentions_csv=output.get("mentions_csv", "clamps_text_mentions.csv"),
        scan_log_csv=output.get("scan_log_csv", "clamps_scan_log.csv"),
    )
