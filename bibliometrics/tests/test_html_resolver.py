from clamps_biblio.html_resolver import (
    _copernicus_html_url,
    html_fulltext_target,
    is_ams_doi,
    is_open_access_doi,
)


def test_ams_html_target():
    row = {"doi": "10.1175/mwr-d-20-0359.1", "source_link": ""}
    target = html_fulltext_target(row)
    assert target is not None
    assert target.publisher == "ams"
    assert "doi/full/10.1175/mwr-d-20-0359.1" in target.url


def test_copernicus_html_target():
    row = {"doi": "10.5194/amt-18-5129-2025", "source_link": ""}
    target = html_fulltext_target(row)
    assert target is not None
    assert target.publisher == "copernicus"
    assert target.url.endswith(".html")


def test_copernicus_author_comment_target():
    doi = "10.5194/amt-2021-363-ac1"
    url = _copernicus_html_url(doi)
    assert url is not None
    assert "amt-2021-363-ac1.html" in url
    target = html_fulltext_target({"doi": doi, "source_link": ""})
    assert target is not None
    assert target.publisher == "copernicus"


def test_copernicus_egusphere_target():
    doi = "10.5194/egusphere-egu26-21748"
    target = html_fulltext_target({"doi": doi, "source_link": ""})
    assert target is not None
    assert target.publisher == "copernicus"
    assert "egusphere.copernicus.org" in target.url


def test_frontiers_html_target():
    row = {"doi": "10.3389/fenvs.2023.1185509", "source_link": ""}
    target = html_fulltext_target(row)
    assert target is not None
    assert target.publisher == "frontiers"
    assert "/full" in target.url


def test_taylor_francis_html_target():
    row = {"doi": "10.1080/12345678.2023.1234567", "source_link": ""}
    target = html_fulltext_target(row)
    assert target is not None
    assert target.publisher == "taylor_francis"


def test_iop_institutional_target():
    row = {"doi": "10.1088/1748-9326/abc123", "source_link": ""}
    target = html_fulltext_target(row, institutional_network=True)
    assert target is not None
    assert target.publisher == "iop"
    assert "iopscience.iop.org" in target.url


def test_zenodo_html_target():
    row = {"doi": "10.5281/zenodo.1234567", "source_link": ""}
    target = html_fulltext_target(row)
    assert target is not None
    assert target.publisher == "zenodo"
    assert "zenodo.org/records/1234567" in target.url


def test_osti_html_target():
    row = {"doi": "10.2172/1510259", "source_link": ""}
    target = html_fulltext_target(row)
    assert target is not None
    assert target.publisher == "osti"
    assert "osti.gov/biblio/1510259" in target.url


def test_wiley_institutional_target():
    row = {"doi": "10.1029/2018gl080667", "source_link": ""}
    target = html_fulltext_target(row, institutional_network=True)
    assert target is not None
    assert target.publisher == "wiley"
    assert "/doi/full/" in target.url


def test_wiley_doi_fallback_without_institutional():
    row = {"doi": "10.1029/2018gl080667", "source_link": ""}
    target = html_fulltext_target(row, institutional_network=False)
    assert target is not None
    assert target.publisher == "publisher_html"
    assert target.url == "https://doi.org/10.1029/2018gl080667"


def test_doi_prefix_helpers():
    assert is_ams_doi("10.1175/foo")
    assert is_open_access_doi("10.5194/bar")
    assert is_open_access_doi("10.3389/bar")
    assert not is_ams_doi("10.5194/bar")


def test_source_link_frontiers_landing():
    row = {
        "doi": "10.3389/fenvs.2023.1185509",
        "source_link": "https://www.frontiersin.org/articles/10.3389/fenvs.2023.1185509/full",
    }
    target = html_fulltext_target(row)
    assert target is not None
    assert target.publisher == "frontiers"


def test_thesis_repository_handle_landing():
    row = {
        "doi": "261990",
        "source_link": "https://conservancy.umn.edu/handle/11299/261990",
        "type": "dissertation",
    }
    target = html_fulltext_target(row)
    assert target is not None
    assert target.publisher == "repository"
    assert "/handle/" in target.url
