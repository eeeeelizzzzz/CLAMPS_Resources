from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

ROOT = Path(__file__).resolve().parent.parent

RepoQueryMode = Literal["facility", "campaign_compound", "campaign_only"]


@dataclass(frozen=True)
class RepoQuery:
    text: str
    mode: RepoQueryMode

    def requires_clamps_signal(self) -> bool:
        """Facility and compound queries require CLAMPS in metadata; bare campaigns do not."""
        return self.mode in ("facility", "campaign_compound")


def load_thesis_repositories(path: Path | None = None) -> dict[str, Any]:
    p = path or ROOT / "data" / "thesis_repositories.yaml"
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_thesis_institutions(path: Path | None = None) -> dict[str, Any]:
    p = path or ROOT / "data" / "thesis_institutions.yaml"
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_channel_h_exclusions(path: Path | None = None) -> set[str]:
    p = path or ROOT / "data" / "channel_h_exclusions.yaml"
    if not p.exists():
        return set()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {
        str(row.get("name", "")).strip()
        for row in (data.get("institutions") or [])
        if row.get("name")
    }


def is_channel_h_excluded(name: str, excluded: set[str] | None = None) -> bool:
    if excluded is None:
        excluded = load_channel_h_exclusions()
    return name.strip() in excluded


def filter_repos_for_channel_h(
    repos: list[dict[str, Any]],
    excluded: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Drop repos whose institution_names are all Channel-H excluded."""
    if excluded is None:
        excluded = load_channel_h_exclusions()
    if not excluded:
        return repos

    kept: list[dict[str, Any]] = []
    for repo in repos:
        names = [str(n).strip() for n in (repo.get("institution_names") or []) if n]
        if not names:
            kept.append(repo)
            continue
        if any(n not in excluded for n in names):
            kept.append(repo)
    return kept


def iter_institutions(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tier_name, block in (data.get("tiers") or {}).items():
        for inst in block.get("institutions") or []:
            row = dict(inst)
            row["tier"] = tier_name
            rows.append(row)
    return rows


def build_repo_queries(
    repo_cfg: dict[str, Any],
    *,
    include_campaigns: bool = True,
) -> list[RepoQuery]:
    queries: list[RepoQuery] = [
        RepoQuery(text=phrase, mode="facility")
        for phrase in (repo_cfg.get("search_phrases") or [])
    ]
    if not include_campaigns:
        return queries

    campaigns = repo_cfg.get("campaign_phrases") or []
    facility = ["CLAMPS-1", "CLAMPS-2"]
    for campaign in campaigns:
        queries.append(RepoQuery(text=campaign, mode="campaign_only"))
        for fac in facility:
            queries.append(
                RepoQuery(text=f'"{campaign}" "{fac}"', mode="campaign_compound")
            )
    return queries


def discovery_label_for_hit(repo_id: str, query: RepoQuery) -> str:
    q = query.text.strip().strip('"')
    if query.mode == "campaign_only":
        return f"campaign_candidate:{repo_id}+{q}"
    return f"{repo_id}+{q}"


def repos_by_priority(
    repo_cfg: dict[str, Any],
    *,
    max_priority: int | None = None,
    repo_ids: list[str] | None = None,
    apply_channel_h_exclusions: bool = True,
    skip_crawled: bool = False,
    skip_crawl_errors: bool = False,
) -> list[dict[str, Any]]:
    repos = list(repo_cfg.get("repositories") or [])
    if repo_ids:
        wanted = set(repo_ids)
        repos = [r for r in repos if r.get("id") in wanted]
    elif skip_crawled:
        repos = [r for r in repos if not r.get("crawled")]
    if skip_crawl_errors:
        repos = [r for r in repos if not r.get("crawl_error")]
    repos.sort(key=lambda r: (r.get("priority", 99), r.get("name", "")))
    if max_priority is not None:
        repos = [r for r in repos if int(r.get("priority", 99)) <= max_priority]
    if apply_channel_h_exclusions:
        repos = filter_repos_for_channel_h(repos)
    return repos
