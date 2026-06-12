from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin


@dataclass
class RepoHit:
    repo_id: str
    repo_name: str
    platform: str
    title: str
    year: int | None
    doi: str
    handle: str
    source_link: str
    landing_page: str
    institution_names: list[str]
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    query: str = ""
    discovery_label: str = ""

    def dedupe_key(self) -> str:
        if self.doi:
            return f"doi:{self.doi.lower()}"
        if self.handle:
            return f"handle:{self.handle.lower()}"
        if self.landing_page:
            return f"url:{self.landing_page.lower()}"
        return f"title:{self.title.lower()}|{self.year or ''}"

    def to_discovery_row(self) -> dict[str, Any]:
        inst = "; ".join(self.institution_names)
        if self.authors:
            inst = "; ".join(dict.fromkeys([*self.authors, *self.institution_names]))

        openalex_id = ""
        if self.handle:
            openalex_id = f"repo:{self.repo_id}:{self.handle}"
        elif self.landing_page:
            openalex_id = f"repo:{self.repo_id}:{self.dedupe_key()}"

        return {
            "openalex_id": openalex_id,
            "title": self.title,
            "year": self.year,
            "doi": self.doi,
            "cited_by_count": None,
            "type": "dissertation",
            "source_link": self.source_link or self.landing_page,
            "institutions": inst,
            "topics": "",
            "topic_ids": "",
            "primary_field_id": "",
            "abstract": self.abstract,
            "discovery_source": f"channel_h:{self.discovery_label or self.repo_id}",
            "repo_id": self.repo_id,
            "repo_platform": self.platform,
            "repo_handle": self.handle,
        }
