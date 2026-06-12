from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import quote, urljoin

import requests

from clamps_biblio.repo_discovery.models import RepoHit

USER_AGENT = "clamps-biblio/0.1 (thesis repository discovery; mailto:elizabeth.n.smith@ou.edu)"


def _has_clamps_preview(text: str) -> bool:
    from clamps_biblio.clamps_signals import has_clamps_signal

    return has_clamps_signal(text)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    s.headers["Accept"] = "application/json, text/html, application/xml;q=0.9, */*;q=0.8"
    return s


def _meta_values(metadata: dict[str, Any], key: str) -> list[str]:
    out: list[str] = []
    for entry in metadata.get(key, []) or []:
        if isinstance(entry, dict):
            val = entry.get("value") or entry.get("authority") or ""
            if val:
                out.append(str(val))
        elif entry:
            out.append(str(entry))
    return out


def _first_meta(metadata: dict[str, Any], *keys: str) -> str:
    for key in keys:
        vals = _meta_values(metadata, key)
        if vals:
            return vals[0]
    return ""


def _parse_year(raw: str) -> int | None:
    if not raw:
        return None
    m = re.search(r"(19|20)\d{2}", str(raw))
    return int(m.group(0)) if m else None


def _dspace_rest_paths(base_url: str, version: int | None) -> list[str]:
    base = base_url.rstrip("/")
    if version == 6:
        return [f"{base}/rest/discover/search/objects"]
    return [
        f"{base}/server/api/discover/search/objects",
        f"{base}/rest/discover/search/objects",
    ]


def _dspace_item_pdf(session: requests.Session, base_url: str, item_uuid: str) -> str:
    base = base_url.rstrip("/")
    for prefix in ("/server/api", "/rest"):
        url = f"{base}{prefix}/core/items/{item_uuid}/bitstreams"
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code != 200:
                continue
            data = resp.json()
            for bs in data.get("_embedded", {}).get("bitstreams", []):
                name = (bs.get("name") or "").lower()
                if name.endswith(".pdf"):
                    link = bs.get("_links", {}).get("content", {}).get("href", "")
                    if link:
                        return link
        except (requests.RequestException, ValueError):
            continue
    return ""


def search_dspace(
    repo: dict[str, Any],
    query: str,
    *,
    max_results: int,
    request_delay: float,
    from_year: int | None,
    require_clamps: bool = False,
) -> list[RepoHit]:
    base_url = repo["base_url"].rstrip("/")
    repo_id = repo["id"]
    institutions = repo.get("institution_names") or []
    version = repo.get("dspace_version")
    session = _session()
    hits: list[RepoHit] = []
    seen: set[str] = set()
    repo = dict(repo)
    repo["_require_clamps"] = require_clamps

    for api_url in _dspace_rest_paths(base_url, version):
        page = 0
        while len(hits) < max_results:
            params = {
                "query": query,
                "dsoType": "ITEM",
                "size": min(20, max_results - len(hits)),
                "page": page,
            }
            try:
                resp = session.get(api_url, params=params, timeout=45)
            except requests.RequestException as exc:
                print(f"    {repo_id}: request error ({exc})")
                break
            time.sleep(request_delay)

            if resp.status_code in (403, 503) or "Just a moment" in resp.text[:500]:
                print(f"    {repo_id}: blocked or unavailable (HTTP {resp.status_code})")
                break
            if resp.status_code != 200:
                break
            try:
                data = resp.json()
            except ValueError:
                break

            objects = (
                data.get("_embedded", {})
                .get("searchResult", {})
                .get("_embedded", {})
                .get("objects", [])
            )
            if not objects:
                break

            for obj in objects:
                item = obj.get("_embedded", {}).get("indexableObject", {})
                uuid = item.get("uuid") or item.get("id")
                metadata = item.get("metadata") or {}
                title = _first_meta(metadata, "dc.title")
                if not title or not uuid:
                    continue

                abstract = _first_meta(metadata, "dc.description.abstract", "dc.description")
                preview_text = f"{title} {abstract}"
                if repo.get("_require_clamps") and not _has_clamps_preview(preview_text):
                    continue

                handle = item.get("handle") or ""
                key = handle or str(uuid)
                if key in seen:
                    continue
                seen.add(key)

                year = _parse_year(
                    _first_meta(metadata, "dc.date.issued", "dc.date.accessioned", "thesis.degree.year")
                )
                if from_year and year and year < from_year:
                    continue

                authors = _meta_values(metadata, "dc.contributor.author")
                doi = _first_meta(metadata, "dc.identifier.doi", "dc.identifier.uri")
                if doi.startswith("http"):
                    doi = doi.rsplit("/", 1)[-1]
                doi = doi.replace("https://doi.org/", "").strip()

                landing = f"{base_url}/handle/{handle}" if handle else f"{base_url}/items/{uuid}"
                pdf_url = _dspace_item_pdf(session, base_url, str(uuid))
                time.sleep(request_delay * 0.25)

                hits.append(
                    RepoHit(
                        repo_id=repo_id,
                        repo_name=repo.get("name", repo_id),
                        platform="dspace_rest",
                        title=title,
                        year=year,
                        doi=doi,
                        handle=handle,
                        source_link=pdf_url,
                        landing_page=landing,
                        institution_names=list(institutions),
                        authors=authors,
                        abstract=abstract,
                        query=query,
                        discovery_label=f"{repo_id}+{query}",
                    )
                )
                if len(hits) >= max_results:
                    break

            page += 1
            if page > 4:
                break

        if hits:
            break

    return hits


def search_digital_commons(
    repo: dict[str, Any],
    query: str,
    *,
    max_results: int,
    request_delay: float,
    from_year: int | None,
) -> list[RepoHit]:
    base_url = repo["base_url"].rstrip("/")
    repo_id = repo["id"]
    institutions = repo.get("institution_names") or []
    session = _session()
    hits: list[RepoHit] = []
    seen: set[str] = set()

    for start in range(0, max_results, 20):
        url = f"{base_url}/do/search/?q={quote(query)}&start={start}"
        try:
            resp = session.get(url, timeout=45)
        except requests.RequestException as exc:
            print(f"    {repo_id}: request error ({exc})")
            break
        time.sleep(request_delay)
        if resp.status_code != 200:
            print(f"    {repo_id}: HTTP {resp.status_code}")
            break

        html = resp.text
        # Bepress article blocks: <a href=".../items/..." ...>Title</a>
        for m in re.finditer(
            r'href="(https?://[^"]+/([^"]*?/(\d+))[^"]*)"[^>]*>([^<]+)</a>',
            html,
            re.IGNORECASE,
        ):
            landing = m.group(1)
            title = re.sub(r"\s+", " ", m.group(4)).strip()
            if len(title) < 8 or landing in seen:
                continue
            if "/download/" in landing or "/viewcontent/" in landing:
                continue
            seen.add(landing)
            pdf_url = landing.replace("/viewcontent.cgi", "/viewcontent.cgi")  # keep as landing
            hits.append(
                RepoHit(
                    repo_id=repo_id,
                    repo_name=repo.get("name", repo_id),
                    platform="digital_commons",
                    title=title,
                    year=None,
                    doi="",
                    handle=m.group(3),
                    source_link=landing,
                    landing_page=landing,
                    institution_names=list(institutions),
                    query=query,
                    discovery_label=f"{repo_id}+{query}",
                )
            )
            if len(hits) >= max_results:
                break
        if len(hits) >= max_results or "no results" in html.lower():
            break

    return hits


def search_eprints(
    repo: dict[str, Any],
    query: str,
    *,
    max_results: int,
    request_delay: float,
    from_year: int | None,
) -> list[RepoHit]:
    base_url = repo["base_url"].rstrip("/")
    repo_id = repo["id"]
    institutions = repo.get("institution_names") or []
    session = _session()
    hits: list[RepoHit] = []
    seen: set[str] = set()

    url = (
        f"{base_url}/cgi/search/advanced?"
        f"keywords={quote(query)}&_action_search=Search&_order=bydate&basic_srchtype=ALL"
    )
    try:
        resp = session.get(url, timeout=45)
    except requests.RequestException as exc:
        print(f"    {repo_id}: request error ({exc})")
        return hits
    time.sleep(request_delay)
    if resp.status_code != 200:
        print(f"    {repo_id}: HTTP {resp.status_code}")
        return hits

    html = resp.text
    for m in re.finditer(
        r'href="([^"]+/(\d+)/?)">([^<]+)</a>',
        html,
    ):
        landing = urljoin(base_url, m.group(1))
        if landing in seen:
            continue
        title = re.sub(r"\s+", " ", m.group(3)).strip()
        if len(title) < 8:
            continue
        seen.add(landing)
        hits.append(
            RepoHit(
                repo_id=repo_id,
                repo_name=repo.get("name", repo_id),
                platform="eprints",
                title=title,
                year=None,
                doi="",
                handle=m.group(2),
                source_link=landing,
                landing_page=landing,
                institution_names=list(institutions),
                query=query,
                discovery_label=f"{repo_id}+{query}",
            )
        )
        if len(hits) >= max_results:
            break

    return hits


def search_oatd(
    query: str,
    *,
    max_results: int,
    request_delay: float,
    max_pages: int = 3,
) -> list[RepoHit]:
    session = _session()
    hits: list[RepoHit] = []
    seen: set[str] = set()

    for page in range(max_pages):
        start = page * 20
        url = f"https://www.oatd.org/oatd/search?q={quote(query)}&start={start}"
        try:
            resp = session.get(url, timeout=45)
        except requests.RequestException as exc:
            print(f"    oatd: request error ({exc})")
            break
        time.sleep(request_delay)
        if resp.status_code != 200:
            break

        html = resp.text
        # OATD result titles link to record pages
        found = 0
        for m in re.finditer(
            r'class="title[^"]*"[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>',
            html,
            re.IGNORECASE | re.DOTALL,
        ):
            landing = m.group(1)
            if not landing.startswith("http"):
                landing = urljoin("https://www.oatd.org", landing)
            title = re.sub(r"\s+", " ", m.group(2)).strip()
            if landing in seen or len(title) < 8:
                continue
            seen.add(landing)
            found += 1
            hits.append(
                RepoHit(
                    repo_id="oatd",
                    repo_name="Open Access Theses and Dissertations",
                    platform="oatd",
                    title=title,
                    year=None,
                    doi="",
                    handle="",
                    source_link=landing,
                    landing_page=landing,
                    institution_names=[],
                    query=query,
                    discovery_label=f"oatd+{query}",
                )
            )
            if len(hits) >= max_results:
                break

        if found == 0 or len(hits) >= max_results:
            break

    return hits
