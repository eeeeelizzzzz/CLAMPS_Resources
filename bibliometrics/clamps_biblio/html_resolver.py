"""Resolve DOIs and CSV rows to publisher HTML full-text URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from clamps_biblio.pdf_resolver import (
    COPERNICUS_DOI,
    COPERNICUS_PREPRINT,
    COPERNICUS_SLUG_PREPRINT,
    DOI_LANDING_RE,
    normalize_doi,
    looks_like_pdf_url,
)

# DOI prefixes where HTML full-text is typically open access.
OPEN_ACCESS_DOI_PREFIXES = (
    "10.5194/",  # Copernicus
    "10.1371/",  # PLOS
    "10.3390/",  # MDPI
    "10.1080/",  # Taylor & Francis (mixed; HTML often works for OA)
    "10.3389/",  # Frontiers
    "10.1186/",  # BMC / Springer Nature OA
    "10.1155/",  # Hindawi
    "10.1051/",  # EDP Sciences
    "10.1098/",  # Royal Society (often OA)
    "10.1039/",  # RSC (mixed)
    "10.1073/",  # PNAS (often OA)
    "10.1139/",  # NRC Research Press
    "10.1525/",  # University of California Press
    "10.5334/",  # Ubiquity Press
)

AMS_DOI_PREFIX = "10.1175/"

# DOI prefixes commonly reachable via university / agency IP authentication.
INSTITUTIONAL_DOI_PREFIXES = (
    "10.1175/",  # AMS
    "10.1029/",  # Wiley (AGU, etc.)
    "10.1002/",  # Wiley
    "10.1111/",  # Wiley
    "10.1016/",  # Elsevier / ScienceDirect
    "10.1007/",  # Springer
    "10.1038/",  # Nature portfolio
    "10.1088/",  # IOP
    "10.1109/",  # IEEE
    "10.1063/",  # AIP
    "10.1017/",  # Cambridge
    "10.1021/",  # ACS
    "10.1093/",  # Oxford
    "10.1126/",  # Science / AAAS
    "10.1177/",  # SAGE
    "10.2514/",  # AIAA
    "10.1364/",  # Optica / OSA
    "10.1117/",  # SPIE
    "10.1115/",  # ASME
    "10.1061/",  # ASCE
)

COPERNICUS_COMMENT = re.compile(
    r"^10\.5194/(?P<journal>[a-z]+)-(?P<year>\d{4})-(?P<num>\d+)-[a-z]+\d+$",
    re.IGNORECASE,
)
COPERNICUS_EGUSPHERE = re.compile(
    r"^10\.5194/(?P<slug>egusphere-.+)$",
    re.IGNORECASE,
)
COPERNICUS_SHORT_SLUG = re.compile(
    r"^10\.5194/(?P<slug>[a-z]+\d*-\d+)$",
    re.IGNORECASE,
)

# source_link host fragments -> publisher key
LANDING_PUBLISHER_TOKENS: tuple[tuple[str, str], ...] = (
    ("copernicus.org", "copernicus"),
    ("frontiersin.org", "frontiers"),
    ("mdpi.com", "mdpi"),
    ("plos.org", "plos"),
    ("ametsoc.org", "ams"),
    ("onlinelibrary.wiley.com", "wiley"),
    ("wiley.com", "wiley"),
    ("link.springer.com", "springer"),
    ("sciencedirect.com", "elsevier"),
    ("tandfonline.com", "taylor_francis"),
    ("iopscience.iop.org", "iop"),
    ("ieeexplore.ieee.org", "ieee"),
    ("pubs.acs.org", "acs"),
    ("acs.org", "acs"),
    ("cambridge.org", "cambridge"),
    ("academic.oup.com", "oxford"),
    ("oup.com", "oxford"),
    ("pnas.org", "pnas"),
    ("science.org", "science"),
    ("sciencemag.org", "science"),
    ("royalsocietypublishing.org", "royal_society"),
    ("rsc.org", "rsc"),
    ("hindawi.com", "hindawi"),
    ("biomedcentral.com", "bmc"),
    ("springeropen.com", "bmc"),
    ("essopenarchive.org", "wiley"),
    ("aip.org", "aip"),
    ("pubs.aip.org", "aip"),
    ("arxiv.org", "arxiv"),
    ("zenodo.org", "zenodo"),
    ("osti.gov", "osti"),
    ("essentia.pub", "essentia"),
    ("authority.esa.int", "authority"),
    ("jove.com", "jove"),
    ("aiaa.org", "aiaa"),
    ("arc.aiaa.org", "aiaa"),
    ("nrcresearchpress.com", "nrc"),
    ("ingentaconnect.com", "ingenta"),
    ("degruyter.com", "degruyter"),
    ("sagepub.com", "sage"),
    ("spiedigitalibrary.org", "spie"),
)


@dataclass(frozen=True)
class HtmlFulltextTarget:
    url: str
    publisher: str
    reason: str


def _doi_landing(doi: str) -> str:
    return f"https://doi.org/{doi}"


def _copernicus_html_url(doi: str) -> str | None:
    m = COPERNICUS_DOI.match(doi)
    if m:
        j, vol, page, year = m.group("journal"), m.group("vol"), m.group("page"), m.group("year")
        slug = f"{j}-{vol}-{page}-{year}"
        return f"https://{j}.copernicus.org/articles/{vol}/{page}/{year}/{slug}.html"

    m = COPERNICUS_PREPRINT.match(doi)
    if m:
        j = m.group("journal")
        slug = doi.split("/", 1)[1]
        return f"https://{j}.copernicus.org/preprints/{slug}/{slug}.html"

    m = COPERNICUS_SLUG_PREPRINT.match(doi)
    if m:
        slug = m.group("slug")
        journal = slug.split("-", 1)[0]
        return f"https://{journal}.copernicus.org/preprints/{slug}/{slug}.html"

    m = COPERNICUS_COMMENT.match(doi)
    if m:
        journal = m.group("journal")
        base = f"{journal}-{m.group('year')}-{m.group('num')}"
        slug = doi.split("/", 1)[1]
        return f"https://{journal}.copernicus.org/preprints/{base}/{slug}.html"

    m = COPERNICUS_EGUSPHERE.match(doi)
    if m:
        slug = m.group("slug")
        return f"https://egusphere.copernicus.org/preprints/{slug}/{slug}.html"

    m = COPERNICUS_SHORT_SLUG.match(doi)
    if m:
        slug = m.group("slug")
        journal = re.match(r"^[a-z]+", slug, re.I)
        if journal:
            return f"https://{journal.group(0)}.copernicus.org/preprints/{slug}/{slug}.html"

    if doi.startswith("10.5194/"):
        slug = doi.split("/", 1)[1]
        journal = slug.split("-", 1)[0]
        if journal.isalpha():
            return f"https://{journal}.copernicus.org/preprints/{slug}/{slug}.html"
        return _doi_landing(doi)

    return None


def _ams_html_url(doi: str) -> str:
    return f"https://journals.ametsoc.org/doi/full/{doi}"


def _wiley_html_url(doi: str) -> str:
    return f"https://onlinelibrary.wiley.com/doi/full/{doi}"


def _springer_html_url(doi: str) -> str:
    return f"https://link.springer.com/article/{doi}"


def _frontiers_html_url(doi: str) -> str:
    return f"https://www.frontiersin.org/articles/{doi}/full"


def _tandf_html_url(doi: str) -> str:
    return f"https://www.tandfonline.com/doi/full/{doi}"


def _iop_html_url(doi: str) -> str:
    return f"https://iopscience.iop.org/article/{doi}"


def _zenodo_html_url(doi: str) -> str | None:
    if not doi.startswith("10.5281/zenodo."):
        return None
    record_id = doi.rsplit(".", 1)[-1]
    if record_id.isdigit():
        return f"https://zenodo.org/records/{record_id}"
    return _doi_landing(doi)


def _osti_html_url(doi: str) -> str | None:
    if not doi.startswith("10.2172/"):
        return None
    osti_id = doi.split("/", 1)[1]
    return f"https://www.osti.gov/biblio/{osti_id}"


def _institutional_html_url(doi: str) -> tuple[str, str] | None:
    """Return (url, publisher_key) for IP-authenticated HTML full text."""
    if doi.startswith("10.1175/"):
        return _ams_html_url(doi), "ams"
    if doi.startswith(("10.1029/", "10.1002/", "10.1111/")):
        return _wiley_html_url(doi), "wiley"
    if doi.startswith("10.1007/"):
        return _springer_html_url(doi), "springer"
    if doi.startswith("10.1016/"):
        return _doi_landing(doi), "elsevier"
    if doi.startswith("10.1038/"):
        return _doi_landing(doi), "nature"
    if doi.startswith("10.1088/"):
        return _iop_html_url(doi), "iop"
    if doi.startswith("10.1109/"):
        return _doi_landing(doi), "ieee"
    if doi.startswith(("10.1063/", "10.1061/")):
        return _doi_landing(doi), "aip"
    if doi.startswith("10.1017/"):
        return _doi_landing(doi), "cambridge"
    if doi.startswith("10.1021/"):
        return _doi_landing(doi), "acs"
    if doi.startswith("10.1093/"):
        return _doi_landing(doi), "oxford"
    if doi.startswith("10.1126/"):
        return _doi_landing(doi), "science"
    if doi.startswith("10.1177/"):
        return _doi_landing(doi), "sage"
    if doi.startswith("10.2514/"):
        return _doi_landing(doi), "aiaa"
    if doi.startswith(("10.1364/", "10.1117/", "10.1115/")):
        return _doi_landing(doi), "optica"
    return None


def _open_access_html_url(doi: str) -> tuple[str, str] | None:
    """Return (url, publisher_key) for open-access HTML targets."""
    if doi.startswith("10.5194/"):
        url = _copernicus_html_url(doi)
        if url:
            return url, "copernicus"
    if doi.startswith("10.3389/"):
        return _frontiers_html_url(doi), "frontiers"
    if doi.startswith("10.1080/"):
        return _tandf_html_url(doi), "taylor_francis"
    if doi.startswith("10.3390/"):
        return _doi_landing(doi), "mdpi"
    if doi.startswith("10.1371/"):
        return _doi_landing(doi), "plos"
    if doi.startswith("10.1186/"):
        return _doi_landing(doi), "bmc"
    if doi.startswith("10.1155/"):
        return _doi_landing(doi), "hindawi"
    if doi.startswith("10.1051/"):
        return _doi_landing(doi), "edp"
    for prefix, key in (
        ("10.1098/", "royal_society"),
        ("10.1073/", "pnas"),
        ("10.1039/", "rsc"),
        ("10.1139/", "nrc"),
        ("10.1525/", "uc_press"),
        ("10.5334/", "ubiquity"),
    ):
        if doi.startswith(prefix):
            return _doi_landing(doi), key
    return None


_DEPOSIT_PREFIXES: tuple[tuple[str, str], ...] = (
    ("10.48550/", "arxiv"),
    ("10.21947/", "authority"),
    ("10.22541/", "essentia"),
    ("10.3791/", "jove"),
    ("10.15191/", "scholarworks"),
    ("10.17190/", "scholarworks"),
    ("10.18130/", "scholarworks"),
    ("10.5821/", "scholarworks"),
)


def _special_deposit_html_url(doi: str) -> tuple[str, str] | None:
    """Preprints, repositories, and grey literature with HTML landing pages."""
    if doi.startswith("10.5281/"):
        url = _zenodo_html_url(doi)
        return (url, "zenodo") if url else None
    if doi.startswith("10.2172/"):
        url = _osti_html_url(doi)
        return (url, "osti") if url else None
    for prefix, key in _DEPOSIT_PREFIXES:
        if doi.startswith(prefix):
            return _doi_landing(doi), key
    if doi.startswith(("10.25394/", "10.7910/", "10.5061/", "10.17632/", "10.5445/", "10.5067/", "10.5439/")):
        return _doi_landing(doi), "repository"
    return None


def _landing_to_html(source_link: str, doi: str) -> str | None:
    link = str(source_link or "").strip()
    if not link or link.lower() == "nan":
        return None
    if looks_like_pdf_url(link):
        html = re.sub(r"\.pdf(?:\?.*)?$", ".html", link, flags=re.I)
        if html != link:
            return html
        html = link.replace("/pdf", "/full").replace("/pdfdirect/", "/full/")
        if html != link:
            return html
        return None
    if DOI_LANDING_RE.match(link) and doi:
        return _doi_landing(doi)
    return link


def _landing_publisher(source_link: str) -> str | None:
    lower = source_link.lower()
    for token, publisher in LANDING_PUBLISHER_TOKENS:
        if token in lower:
            return publisher
    return None


def is_ams_doi(doi: str) -> bool:
    return normalize_doi(doi).startswith(AMS_DOI_PREFIX)


def is_open_access_doi(doi: str) -> bool:
    doi = normalize_doi(doi)
    return any(doi.startswith(prefix) for prefix in OPEN_ACCESS_DOI_PREFIXES)


def is_institutional_doi(doi: str) -> bool:
    doi = normalize_doi(doi)
    return any(doi.startswith(prefix) for prefix in INSTITUTIONAL_DOI_PREFIXES)


def html_fulltext_target(
    row: dict,
    *,
    source_link_key: str = "source_link",
    institutional_network: bool = True,
) -> HtmlFulltextTarget | None:
    """Return an HTML full-text URL when this row should use web scraping."""
    doi = normalize_doi(row.get("doi"))
    source = str(row.get(source_link_key, "") or "").strip()

    if institutional_network and doi:
        inst = _institutional_html_url(doi)
        if inst:
            url, publisher = inst
            return HtmlFulltextTarget(url, publisher, "institutional_network")

    if doi and is_ams_doi(doi):
        return HtmlFulltextTarget(_ams_html_url(doi), "ams", "ams_library")

    if doi:
        oa = _open_access_html_url(doi)
        if oa:
            url, publisher = oa
            if publisher in {"mdpi", "plos"}:
                url = _landing_to_html(source, doi) or url
            return HtmlFulltextTarget(url, publisher, "open_access")

        deposit = _special_deposit_html_url(doi)
        if deposit:
            url, publisher = deposit
            return HtmlFulltextTarget(url, publisher, "repository_landing")

    # HTML landings from discovery metadata
    if source and not looks_like_pdf_url(source):
        lower = source.lower()
        if institutional_network and "onlinelibrary.wiley.com" in lower:
            html = _landing_to_html(source, doi) or source
            return HtmlFulltextTarget(html, "wiley", "institutional_landing")
        if institutional_network and "link.springer.com" in lower:
            return HtmlFulltextTarget(source, "springer", "institutional_landing")
        if institutional_network and "sciencedirect.com" in lower:
            html = source.replace("/pdfft", "").replace("/pdf", "")
            return HtmlFulltextTarget(html, "elsevier", "institutional_landing")
        publisher = _landing_publisher(source)
        if publisher:
            reason = (
                "open_access_landing"
                if publisher
                in {
                    "copernicus",
                    "frontiers",
                    "mdpi",
                    "plos",
                    "bmc",
                    "hindawi",
                    "arxiv",
                    "zenodo",
                    "essentia",
                }
                else "institutional_landing"
            )
            return HtmlFulltextTarget(_landing_to_html(source, doi) or source, publisher, reason)

    # Institutional repository pages (theses often store handles in doi/source_link).
    if source and not looks_like_pdf_url(source):
        lower = source.lower()
        if any(
            token in lower
            for token in (
                "/handle/",
                "/items/",
                "/bitstream/",
                "dspace",
                "etd.",
                "ir.tdl.org",
                "ecommons.",
                "shareok.org",
                "mospace.",
                "trace.",
                "scholarworks.",
                "vtechworks.",
                "digitalcommons.",
                "oatd.org",
            )
        ):
            return HtmlFulltextTarget(source, "repository", "repository_landing")

    # Universal fallback: let Playwright follow doi.org to the publisher page.
    if doi and doi.startswith("10."):
        return HtmlFulltextTarget(_doi_landing(doi), "publisher_html", "doi_landing")

    return None
