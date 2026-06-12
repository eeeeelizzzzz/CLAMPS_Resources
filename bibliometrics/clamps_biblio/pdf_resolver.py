"""Resolve DOIs to PDF URLs via Unpaywall and publisher heuristics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, urljoin

import requests

COPERNICUS_DOI = re.compile(
    r"^10\.5194/(?P<journal>[a-z]+)-(?P<vol>\d+)-(?P<page>\d+)-(?P<year>\d{4})$",
    re.IGNORECASE,
)
COPERNICUS_PREPRINT = re.compile(
    r"^10\.5194/(?P<journal>[a-z]+)-(?P<year>\d{4})-(?P<num>\d+)$",
    re.IGNORECASE,
)
COPERNICUS_SLUG_PREPRINT = re.compile(
    r"^10\.5194/(?P<slug>[a-z]+-\d{4}-\d+(?:-rc\d+)?)$",
    re.IGNORECASE,
)
NOAA_IR_BASE = "https://repository.library.noaa.gov"
NOAA_VIEW_PID_RE = re.compile(r"/view/noaa/(\d+)", re.IGNORECASE)
OSTI_PURL_RE = re.compile(r"osti\.gov/(?:servlets/purl|biblio)/", re.IGNORECASE)
DOI_LANDING_RE = re.compile(r"^https?://(dx\.)?doi\.org/10\.", re.IGNORECASE)
AMS_DOI_PDF_RE = re.compile(r"journals\.ametsoc\.org/doi/pdf/", re.IGNORECASE)
AMS_DOWNLOADPDF_RE = re.compile(
    r"https://journals\.ametsoc\.org/downloadpdf[^\"'\s<>]+",
    re.IGNORECASE,
)
HTML_PDF_LINK_RE = re.compile(
    r"https?://[^\"'\s<>]+(?:\.pdf(?:[/?#]|[\"'])|/pdf(?:[/?#]|[\"'])|pdfdirect|downloadpdf)[^\"'\s<>]*",
    re.IGNORECASE,
)


@dataclass
class ResolvedPdf:
    url: str
    method: str


def normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    clean = str(doi).strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix) :]
    return clean.strip()


def publisher_pdf_guess(doi: str) -> ResolvedPdf | None:
    """Best-effort PDF URLs from DOI prefix patterns (no network)."""
    doi = normalize_doi(doi)
    if not doi:
        return None

    m = COPERNICUS_DOI.match(doi)
    if m:
        j, vol, page, year = m.group("journal"), m.group("vol"), m.group("page"), m.group("year")
        slug = f"{j}-{vol}-{page}-{year}"
        url = f"https://{j}.copernicus.org/articles/{vol}/{page}/{year}/{slug}.pdf"
        return ResolvedPdf(url, "publisher:copernicus")

    m = COPERNICUS_PREPRINT.match(doi)
    if m:
        j = m.group("journal")
        slug = doi.split("/", 1)[1]
        url = f"https://{j}.copernicus.org/preprints/{slug}/{slug}.pdf"
        return ResolvedPdf(url, "publisher:copernicus_preprint")

    m = COPERNICUS_SLUG_PREPRINT.match(doi)
    if m:
        slug = m.group("slug")
        journal = slug.split("-", 1)[0]
        url = f"https://{journal}.copernicus.org/preprints/{slug}/{slug}.pdf"
        return ResolvedPdf(url, "publisher:copernicus_preprint")

    if doi.startswith("10.1175/"):
        return None

    if doi.startswith(("10.1029/", "10.1002/", "10.1111/")):
        return ResolvedPdf(
            f"https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}",
            "publisher:wiley_pdfdirect",
        )

    if doi.startswith("10.2172/"):
        osti_id = doi.split("/", 1)[1]
        return ResolvedPdf(f"https://www.osti.gov/servlets/purl/{osti_id}", "publisher:osti_purl")

    if doi.startswith("10.5281/zenodo."):
        record_id = doi.rsplit(".", 1)[-1]
        return ResolvedPdf(
            f"https://zenodo.org/api/records/{record_id}",
            "publisher:zenodo_api",
        )

    if doi.startswith("10.1371/"):
        return ResolvedPdf(
            f"https://journals.plos.org/plosone/article/file?id={doi}&type=printable",
            "publisher:plos",
        )

    return None


def unpaywall_lookup(
    doi: str,
    email: str,
    session: requests.Session | None = None,
) -> ResolvedPdf | None:
    doi = normalize_doi(doi)
    if not doi or not email:
        return None
    client = session or requests.Session()
    response = client.get(
        f"https://api.unpaywall.org/v2/{doi}",
        params={"email": email},
        timeout=30,
    )
    if response.status_code != 200:
        return None
    data = response.json()
    location = data.get("best_oa_location") or {}
    url = location.get("url_for_pdf") or location.get("url")
    if not url or not is_usable_pdf_url(url):
        return None
    return ResolvedPdf(url, "unpaywall")


def resolve_ams_pdf(doi: str, session: requests.Session) -> ResolvedPdf | None:
    """Scrape AMS article page for a downloadpdf link (needs institutional cookies)."""
    doi = normalize_doi(doi)
    if not doi.startswith("10.1175/"):
        return None
    response = session.get(f"https://journals.ametsoc.org/doi/{doi}", timeout=30)
    if response.status_code != 200:
        return None
    match = AMS_DOWNLOADPDF_RE.search(response.text)
    if not match:
        return None
    return ResolvedPdf(match.group(0), "publisher:ams_downloadpdf")


def zenodo_pdf_from_api(api_url: str, session: requests.Session) -> str | None:
    """Return a public Zenodo PDF download URL, or None if the record has no PDF."""
    response = session.get(api_url, timeout=30)
    if response.status_code != 200:
        return None
    data = response.json()
    record_id = str(data.get("id", ""))
    if not record_id:
        return None

    for file_info in data.get("files", []):
        key = str(file_info.get("key", ""))
        mime = str(file_info.get("mimetype") or "").lower()
        if not key.lower().endswith(".pdf") and mime != "application/pdf":
            continue
        # Public download URL works; API .../content URLs often return 403.
        return f"https://zenodo.org/records/{record_id}/files/{quote(key)}?download=1"
    return None


def resolve_openalex_pdf(
    doi: str,
    mailto: str | None,
    session: requests.Session | None = None,
) -> ResolvedPdf | None:
    """Re-fetch OpenAlex work and use primary_location.pdf_url if present."""
    doi = normalize_doi(doi)
    if not doi:
        return None
    client = session or requests.Session()
    params: dict[str, str] = {"filter": f"doi:{doi}"}
    if mailto:
        params["mailto"] = mailto
    response = client.get("https://api.openalex.org/works", params=params, timeout=30)
    if response.status_code != 200:
        return None
    results = response.json().get("results", [])
    if not results:
        return None
    work = results[0]
    location = work.get("primary_location") or {}
    pdf = location.get("pdf_url") or ""
    if pdf and is_usable_pdf_url(pdf):
        return ResolvedPdf(pdf, "pass2:openalex_pdf")
    landing = location.get("landing_page_url") or ""
    if landing and looks_like_pdf_url(landing) and is_usable_pdf_url(landing):
        return ResolvedPdf(landing, "pass2:openalex_landing_pdf")
    return None


def resolve_landing_page_pdf(
    url: str,
    session: requests.Session,
    doi: str | None = None,
) -> ResolvedPdf | None:
    """Fetch HTML landing page and extract direct PDF links."""
    text = clean_repo_pdf_url(url)
    if not text:
        return None
    if "viewcontent.cgi" in text:
        direct = follow_to_pdf_url(text, session)
        if direct:
            return ResolvedPdf(direct, "pass2:digital_commons_viewcontent")
    if "/handle/" in text and "/bitstream/" not in text:
        _authors, dspace_pdf = resolve_dspace_handle(text, session)
        if dspace_pdf:
            return ResolvedPdf(dspace_pdf, "pass2:dspace_handle")
    if DOI_LANDING_RE.match(text) and doi:
        text = f"https://doi.org/{normalize_doi(doi)}"
    try:
        response = session.get(text, timeout=30, allow_redirects=True)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    links = extract_pdf_links_from_html(response.text, response.url)
    if not links:
        doi_norm = normalize_doi(doi)
        if doi_norm and doi_norm.startswith("10.1175/"):
            ams = resolve_ams_pdf(doi_norm, session)
            if ams:
                return ResolvedPdf(ams.url, "pass2:ams_downloadpdf")
        direct = follow_to_pdf_url(response.url, session)
        if direct:
            return ResolvedPdf(direct, "pass2:doi_redirect")
        return None
    return ResolvedPdf(links[0], "pass2:landing_scrape")


def noaa_ir_pdf_from_pid(pid: str) -> str:
    return f"{NOAA_IR_BASE}/view/noaa/{pid}/noaa_{pid}_DS1.pdf"


def resolve_noaa_ir_pdf(doi: str, session: requests.Session) -> ResolvedPdf | None:
    """
    Look up DOI in NOAA Institutional Repository and return DS1 PDF URL.
    Uses gsearch customQueryBox; may be blocked by WAF from some networks.
    """
    doi = normalize_doi(doi)
    if not doi:
        return None
    query = f'"{doi}"[DOI]'
    try:
        response = session.get(
            f"{NOAA_IR_BASE}/gsearch",
            params={"customQueryBox": query},
            timeout=45,
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    pids = NOAA_VIEW_PID_RE.findall(response.text)
    if not pids:
        return None
    for pid in dict.fromkeys(pids):
        pdf_url = noaa_ir_pdf_from_pid(pid)
        try:
            head = session.head(pdf_url, timeout=20, allow_redirects=True)
        except requests.RequestException:
            continue
        if head.status_code == 200:
            return ResolvedPdf(pdf_url, "pass2:noaa_ir")
        try:
            view = session.get(f"{NOAA_IR_BASE}/view/noaa/{pid}", timeout=30)
        except requests.RequestException:
            continue
        if view.status_code == 200:
            links = extract_pdf_links_from_html(view.text, view.url)
            for link in links:
                if "repository.library.noaa.gov" in link.lower():
                    return ResolvedPdf(link, "pass2:noaa_ir")
    return None


def resolve_pdf_pass2(
    row: dict,
    *,
    email: str | None,
    mailto: str | None,
    session: requests.Session,
) -> ResolvedPdf | None:
    """Second-pass resolver chain for manual-queue papers."""
    doi = normalize_doi(row.get("doi"))
    source_link = clean_repo_pdf_url(str(row.get("source_link", "") or ""))

    if not doi:
        if source_link:
            if "viewcontent.cgi" in source_link:
                direct = follow_to_pdf_url(source_link, session)
                if direct:
                    return ResolvedPdf(direct, "pass2:digital_commons_viewcontent")
            if "/handle/" in source_link:
                _authors, dspace_pdf = resolve_dspace_handle(source_link, session)
                if dspace_pdf:
                    return ResolvedPdf(dspace_pdf, "pass2:dspace_handle")
            landing = resolve_landing_page_pdf(source_link, session)
            if landing:
                return landing
        return None

    steps = [
        lambda: resolve_openalex_pdf(doi, mailto, session),
        lambda: publisher_pdf_guess(doi),
        lambda: resolve_noaa_ir_pdf(doi, session),
    ]
    if source_link:
        redirect_target = (
            f"https://doi.org/{doi}"
            if DOI_LANDING_RE.match(source_link) and doi
            else source_link
        )
        steps.append(
            lambda target=redirect_target: (
                ResolvedPdf(url, "pass2:doi_redirect")
                if (url := follow_to_pdf_url(target, session))
                else None
            )
        )
        steps.append(lambda: resolve_landing_page_pdf(source_link, session, doi=doi))

    if email:
        steps.append(lambda: unpaywall_lookup(doi, email, session))

    for step in steps:
        try:
            result = step()
        except requests.RequestException:
            result = None
        if not result:
            continue
        if result.method == "publisher:zenodo_api":
            pdf = zenodo_pdf_from_api(result.url, session)
            if pdf:
                return ResolvedPdf(pdf, "pass2:zenodo")
            continue
        if is_valid_resolved_pdf_url(result.url) or _is_osti_scannable(result.url):
            return result
    return None


def _is_osti_scannable(url: str) -> bool:
    return bool(OSTI_PURL_RE.search(str(url or "")))


def resolve_pdf_url(
    doi: str,
    email: str | None,
    session: requests.Session | None = None,
) -> ResolvedPdf | None:
    """Try Unpaywall first, then publisher heuristics."""
    client = session or requests.Session()

    if email:
        result = unpaywall_lookup(doi, email, client)
        if result:
            return result

    doi_norm = normalize_doi(doi)
    if doi_norm.startswith("10.1175/"):
        ams = resolve_ams_pdf(doi_norm, client)
        if ams:
            return ams

    guess = publisher_pdf_guess(doi)
    if guess and guess.method == "publisher:zenodo_api":
        pdf = zenodo_pdf_from_api(guess.url, client)
        if pdf:
            return ResolvedPdf(pdf, "publisher:zenodo")
        return None

    return guess


PDF_PATH_RE = re.compile(
    r"\.pdf(?:[/?#]|$)|/pdf(?:[/?#]|$)|pdfdirect|downloadpdf|/_pdf(?:[/?#]|$)"
    r"|/download(?:[/?#]|/|\?)|/bitstream/|viewcontent\.cgi",
    re.IGNORECASE,
)
DSPACE_BITSTREAM_HTML_RE = re.compile(
    r'href="([^"]*?/bitstream/[^"]+)"',
    re.IGNORECASE,
)
DIGITAL_COMMONS_VIEWCONTENT_HTML_RE = re.compile(
    r'href="([^"]*?viewcontent\.cgi[^"]+)"',
    re.IGNORECASE,
)
DSPACE_HANDLE_RE = re.compile(
    r"(https?://[^/]+)/handle/([^?#]+)",
    re.IGNORECASE,
)
DSPACE_BITSTREAM_UUID_RE = re.compile(
    r"/bitstream/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)
JUNK_PDF_URL_RE = re.compile(
    r"ns\.adobe\.com/|xmlns\.com/|purl\.org/dc/|prismstandard\.org/",
    re.IGNORECASE,
)


def looks_like_pdf_url(url: str) -> bool:
    if not url:
        return False
    return bool(PDF_PATH_RE.search(str(url)))


def _dspace_meta_values(metadata: dict, key: str) -> list[str]:
    return [
        str(entry.get("value", "")).strip()
        for entry in metadata.get(key, [])
        if entry.get("value")
    ]


def _dspace_pick_pdf_bitstream(bitstreams: list[dict]) -> str:
    for bs in bitstreams:
        name = (bs.get("name") or "").lower()
        if name.endswith(".pdf") and not name.endswith(".pdf.jpg"):
            link = bs.get("_links", {}).get("content", {}).get("href", "")
            if link:
                return link
    return ""


def _dspace_item_pdf_url(
    base_url: str, item_uuid: str, session: requests.Session
) -> str:
    base = base_url.rstrip("/")
    for prefix in ("/server/api", "/rest"):
        url = f"{base}{prefix}/core/items/{item_uuid}/bitstreams"
        try:
            resp = session.get(url, timeout=30)
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue
        try:
            data = resp.json()
        except ValueError:
            continue
        pdf = _dspace_pick_pdf_bitstream(data.get("_embedded", {}).get("bitstreams", []))
        if pdf:
            return pdf

    for prefix in ("/server/api", "/rest"):
        bundles_url = f"{base}{prefix}/core/items/{item_uuid}/bundles"
        try:
            resp = session.get(bundles_url, timeout=30)
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue
        try:
            bundles = resp.json().get("_embedded", {}).get("bundles", [])
        except ValueError:
            continue
        ordered = sorted(
            bundles,
            key=lambda b: 0 if (b.get("name") or "").upper() == "ORIGINAL" else 1,
        )
        for bundle in ordered:
            bitstreams_href = (
                bundle.get("_links", {}).get("bitstreams", {}).get("href", "")
            )
            if not bitstreams_href:
                continue
            try:
                bs_resp = session.get(bitstreams_href, timeout=30)
            except requests.RequestException:
                continue
            if bs_resp.status_code != 200:
                continue
            try:
                bitstreams = bs_resp.json().get("_embedded", {}).get("bitstreams", [])
            except ValueError:
                continue
            pdf = _dspace_pick_pdf_bitstream(bitstreams)
            if pdf:
                return pdf
    return ""


def _dspace_bitstream_pdf_from_html(
    html: str, base_url: str, session: requests.Session
) -> str:
    base = base_url.rstrip("/")
    for uuid in dict.fromkeys(DSPACE_BITSTREAM_UUID_RE.findall(html)):
        try:
            resp = session.get(f"{base}/server/api/core/bitstreams/{uuid}", timeout=30)
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue
        try:
            data = resp.json()
        except ValueError:
            continue
        name = (data.get("name") or "").lower()
        if name.endswith(".pdf") and not name.endswith(".pdf.jpg"):
            link = data.get("_links", {}).get("content", {}).get("href", "")
            if link:
                return link
    return ""


def resolve_dspace_handle(
    url: str, session: requests.Session
) -> tuple[list[str], str]:
    """
    Resolve a DSpace /handle/ URL to (authors, pdf_content_url).

    Uses discover search when available; falls back to bitstream UUIDs in HTML.
    """
    match = DSPACE_HANDLE_RE.search(str(url or "").strip())
    if not match:
        return [], ""
    base_url, handle = match.group(1), match.group(2).strip("/")
    authors: list[str] = []
    pdf_url = ""

    for prefix in ("/server/api", "/rest"):
        api = f"{base_url.rstrip('/')}{prefix}/discover/search/objects"
        try:
            resp = session.get(
                api,
                params={"query": f"handle:{handle}", "dsoType": "ITEM", "size": 1},
                timeout=45,
            )
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue
        try:
            data = resp.json()
        except ValueError:
            continue
        objects = (
            data.get("_embedded", {})
            .get("searchResult", {})
            .get("_embedded", {})
            .get("objects", [])
        )
        if not objects:
            continue
        item = objects[0].get("_embedded", {}).get("indexableObject", {})
        metadata = item.get("metadata") or {}
        authors = _dspace_meta_values(metadata, "dc.contributor.author")
        if not authors:
            authors = _dspace_meta_values(metadata, "dc.creator")
        item_uuid = item.get("uuid") or item.get("id")
        if item_uuid:
            pdf_url = _dspace_item_pdf_url(base_url, str(item_uuid), session)
        if pdf_url:
            break

    if not pdf_url:
        try:
            page = session.get(f"{base_url.rstrip('/')}/handle/{handle}", timeout=45)
        except requests.RequestException:
            page = None
        if page is not None and page.status_code == 200:
            pdf_url = _dspace_bitstream_pdf_from_html(page.text, base_url, session)

    return authors, pdf_url


def clean_repo_pdf_url(raw_url: str) -> str:
    """
    Normalize repository URLs before PDF resolution.

    Digital Commons (e.g. Iowa State ir.lib.iastate.edu) serves PDFs via
    viewcontent.cgi; DSpace uses /bitstream/ under /handle/ landing pages.
    """
    url_str = str(raw_url or "").strip()
    if not url_str or url_str.lower() == "nan":
        return ""
    if "viewcontent.cgi" in url_str:
        return url_str
    if "iastate.edu" in url_str and "/cgi/" in url_str:
        return url_str
    if "/handle/" in url_str and "/bitstream/" not in url_str:
        return url_str
    return url_str


def _is_junk_pdf_url(url: str) -> bool:
    """Reject XMP/XML namespace URLs mistaken for PDF links during HTML scrape."""
    text = str(url or "").strip()
    if not text:
        return True
    return bool(JUNK_PDF_URL_RE.search(text))


def follow_to_pdf_url(url: str, session: requests.Session) -> str | None:
    """Follow redirects on a landing/download URL; return final URL if body is a PDF."""
    text = clean_repo_pdf_url(url)
    if not text:
        return None
    try:
        response = session.get(text, timeout=30, allow_redirects=True)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    if response.content.startswith(b"%PDF"):
        return response.url
    return None


def is_usable_pdf_url(url: str) -> bool:
    """Stricter check: reject DOI landing pages and AMS HTML wrapper URLs."""
    text = str(url or "").strip()
    if not text:
        return False
    if _is_junk_pdf_url(text):
        return False
    if _is_osti_scannable(text) or "repository.library.noaa.gov/view/noaa/" in text.lower():
        return True
    if not looks_like_pdf_url(text):
        return False
    if DOI_LANDING_RE.match(text):
        return False
    if AMS_DOI_PDF_RE.search(text):
        return False
    return True


def _clean_scraped_url(url: str) -> str:
    link = str(url or "").strip().rstrip("'\"/,;)")
    while link.endswith('"') or link.endswith("/"):
        link = link.rstrip('"').rstrip("/")
    return link


def extract_pdf_links_from_html(html: str, base_url: str = "") -> list[str]:
    links = []
    for match in HTML_PDF_LINK_RE.finditer(html):
        link = _clean_scraped_url(match.group(0))
        if _is_junk_pdf_url(link):
            continue
        if is_usable_pdf_url(link):
            links.append(link)
    for pattern in (DSPACE_BITSTREAM_HTML_RE, DIGITAL_COMMONS_VIEWCONTENT_HTML_RE):
        for match in pattern.finditer(html):
            link = _clean_scraped_url(match.group(1))
            if link.startswith("/"):
                link = urljoin(base_url, link)
            if _is_junk_pdf_url(link):
                continue
            if is_usable_pdf_url(link):
                links.append(link)
    if "ametsoc.org/doi/pdf/" in base_url.lower() or "ametsoc.org/doi/10." in base_url.lower():
        for match in AMS_DOWNLOADPDF_RE.finditer(html):
            links.append(match.group(0))
    # Prefer direct PDF / downloadpdf links
    links.sort(key=lambda u: (0 if u.lower().endswith(".pdf") else 1, len(u)))
    seen: set[str] = set()
    unique: list[str] = []
    for link in links:
        if link not in seen:
            seen.add(link)
            unique.append(link)
    return unique


def is_valid_resolved_pdf_url(url: str) -> bool:
    """True if a resolved pdf_url is worth attempting to download."""
    text = str(url or "").strip()
    if not text or text.lower() == "nan":
        return False
    lower = text.lower()
    if "zenodo.org/api/" in lower:
        return False
    if lower.endswith(".cdf") or ".cdf/" in lower or ".cdf?" in lower:
        return False
    if _is_junk_pdf_url(text):
        return False
    if _is_osti_scannable(text):
        return True
    return is_usable_pdf_url(text)


def scannable_pdf_url(row: dict, source_link_key: str = "source_link") -> tuple[str, str]:
    """
    Return (url, origin) for a CSV row.
    origin is one of: pdf_url, source_link, none
    """
    pdf_url = str(row.get("pdf_url", "") or "").strip()
    if pdf_url and pdf_url.lower() != "nan" and is_valid_resolved_pdf_url(pdf_url):
        return pdf_url, "pdf_url"

    source = clean_repo_pdf_url(str(row.get(source_link_key, "") or ""))
    if source:
        if is_valid_resolved_pdf_url(source):
            return source, "source_link"
        if looks_like_pdf_url(source):
            return source, "source_link"

    return "", "none"
