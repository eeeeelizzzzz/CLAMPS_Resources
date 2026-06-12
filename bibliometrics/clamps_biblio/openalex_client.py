from __future__ import annotations

import time
from typing import Any, Iterator

import requests

OPENALEX_BASE = "https://api.openalex.org"
MAX_RETRY_WAIT_S = 120  # cap; OpenAlex sometimes sends multi-hour Retry-After when daily limit hit


class OpenAlexClient:
    def __init__(
        self,
        mailto: str | None = None,
        per_page: int = 200,
        request_delay: float = 1.0,
        max_retries: int = 6,
    ):
        self.per_page = per_page
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "clamps-biblio/0.1"
        self.mailto = mailto

    def _params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params = {"per-page": self.per_page}
        if self.mailto:
            params["mailto"] = self.mailto
        if extra:
            params.update(extra)
        return params

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{OPENALEX_BASE}/{endpoint}"
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            if attempt > 0:
                time.sleep(self.request_delay)
            response = self.session.get(url, params=self._params(params), timeout=60)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    suggested = float(retry_after)
                    wait = min(suggested, MAX_RETRY_WAIT_S)
                    if suggested > MAX_RETRY_WAIT_S:
                        hours = suggested / 3600
                        print(
                            f"    OpenAlex rate limit (429); server suggested {hours:.1f}h wait "
                            f"(daily limit likely hit). Retrying in {wait:.0f}s..."
                        )
                        print(
                            "    Tip: add openalex.mailto in config.yaml, wait ~1 hour, or resume tomorrow."
                        )
                    else:
                        print(
                            f"    OpenAlex rate limit (429); waiting {wait:.0f}s "
                            f"(attempt {attempt + 1}/{self.max_retries})..."
                        )
                else:
                    wait = min(60, 2 ** attempt * 2)
                    print(
                        f"    OpenAlex rate limit (429); waiting {wait:.0f}s "
                        f"(attempt {attempt + 1}/{self.max_retries})..."
                    )
                time.sleep(wait)
                last_error = requests.HTTPError("429 Too Many Requests", response=response)
                continue

            if response.status_code in (500, 502, 503, 504):
                wait = min(30, 2 ** attempt)
                print(f"    OpenAlex server error ({response.status_code}); waiting {wait:.0f}s...")
                time.sleep(wait)
                last_error = requests.HTTPError(f"{response.status_code} Server Error", response=response)
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                last_error = exc
                raise

            time.sleep(self.request_delay)
            return response.json()

        if last_error:
            raise last_error
        raise RuntimeError("OpenAlex request failed after retries")

    def paginate(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        max_results: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        page = 1
        params = dict(params or {})
        yielded = 0
        while True:
            params["page"] = page
            data = self._get(endpoint, params)
            results = data.get("results", [])
            if not results:
                break
            for item in results:
                yield item
                yielded += 1
                if max_results is not None and yielded >= max_results:
                    return
            meta = data.get("meta", {})
            if page * self.per_page >= meta.get("count", 0):
                break
            if page >= 10:
                break
            page += 1

    def work_by_doi(self, doi: str) -> dict[str, Any] | None:
        clean = doi.replace("https://doi.org/", "").strip()
        data = self._get("works", {"filter": f"doi:{clean}"})
        results = data.get("results", [])
        return results[0] if results else None

    def works_citing(self, openalex_id: str) -> list[dict[str, Any]]:
        work_id = openalex_id.rsplit("/", 1)[-1]
        return list(self.paginate("works", {"filter": f"cites:{work_id}"}))

    def search_works(
        self,
        query: str,
        institution_ids: list[str] | None = None,
        from_year: int | None = None,
        max_results: int | None = None,
        extra_filters: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"search": query}
        filters: list[str] = list(extra_filters or [])
        if institution_ids:
            filters.append("institutions.id:" + "|".join(institution_ids))
        if from_year:
            filters.append(f"from_publication_date:{from_year}-01-01")
        if filters:
            params["filter"] = ",".join(filters)
        return list(self.paginate("works", params, max_results=max_results))

    def works_by_author_ids(
        self,
        author_ids: list[str],
        from_year: int | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        if not author_ids:
            return []
        clean = [aid.rsplit("/", 1)[-1] for aid in author_ids]
        params: dict[str, Any] = {
            "filter": "authorships.author.id:" + "|".join(clean),
        }
        if from_year:
            params["filter"] += f",from_publication_date:{from_year}-01-01"
        return list(self.paginate("works", params, max_results=max_results))

    @staticmethod
    def flatten_work(work: dict[str, Any], discovery_source: str) -> dict[str, Any]:
        location = work.get("primary_location") or {}
        institutions = []
        for authorship in work.get("authorships", []):
            for inst in authorship.get("institutions", []):
                name = inst.get("display_name")
                if name and name not in institutions:
                    institutions.append(name)

        topics = work.get("topics") or []
        topic_names = [t.get("display_name", "") for t in topics if t.get("display_name")]
        topic_ids = [
            (t.get("id") or "").rsplit("/", 1)[-1]
            for t in topics
            if t.get("id")
        ]
        primary_topic = work.get("primary_topic") or {}
        primary_field = primary_topic.get("field") or {}
        primary_field_id = (primary_field.get("id") or "").rsplit("/", 1)[-1]
        inv = work.get("abstract_inverted_index") or {}
        abstract = " ".join(inv.keys()) if inv else ""

        return {
            "openalex_id": work.get("id", ""),
            "title": work.get("title") or work.get("display_name", ""),
            "year": work.get("publication_year"),
            "doi": (work.get("doi") or "").replace("https://doi.org/", ""),
            "cited_by_count": work.get("cited_by_count"),
            "type": work.get("type"),
            "source_link": location.get("pdf_url") or location.get("landing_page_url") or "",
            "institutions": "; ".join(institutions),
            "topics": "; ".join(topic_names),
            "topic_ids": "; ".join(topic_ids),
            "primary_field_id": primary_field_id,
            "abstract": abstract,
            "discovery_source": discovery_source,
        }
