from __future__ import annotations

from typing import Any

from clamps_biblio.repo_discovery.adapters import (
    search_digital_commons,
    search_dspace,
    search_eprints,
    search_oatd,
)
from clamps_biblio.repo_discovery.models import RepoHit

DSPACE_PLATFORMS = frozenset({"dspace_rest", "dspace_rest6", "dspace_oai"})


def search_repository(
    repo: dict[str, Any],
    query: str,
    *,
    max_results: int,
    request_delay: float,
    from_year: int | None,
    require_clamps: bool = False,
) -> list[RepoHit]:
    platform = (repo.get("platform") or "").lower()
    if platform in DSPACE_PLATFORMS:
        version = 6 if platform == "dspace_rest6" else repo.get("dspace_version")
        repo = dict(repo)
        repo["dspace_version"] = version
        return search_dspace(
            repo,
            query,
            max_results=max_results,
            request_delay=request_delay,
            from_year=from_year,
            require_clamps=require_clamps,
        )
    if platform == "digital_commons":
        return search_digital_commons(
            repo, query, max_results=max_results, request_delay=request_delay, from_year=from_year
        )
    if platform == "eprints":
        return search_eprints(
            repo, query, max_results=max_results, request_delay=request_delay, from_year=from_year
        )
    print(f"    {repo.get('id')}: unknown platform {platform!r}")
    return []


def search_oatd_aggregator(
    query: str,
    *,
    max_results: int,
    request_delay: float,
    max_pages: int,
) -> list[RepoHit]:
    return search_oatd(
        query, max_results=max_results, request_delay=request_delay, max_pages=max_pages
    )
