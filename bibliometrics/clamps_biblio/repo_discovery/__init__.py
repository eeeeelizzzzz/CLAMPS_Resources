"""Institutional repository discovery for theses and dissertations (Tier 6)."""

from __future__ import annotations

from clamps_biblio.repo_discovery.models import RepoHit
from clamps_biblio.repo_discovery.router import search_repository

__all__ = ["RepoHit", "search_repository"]
