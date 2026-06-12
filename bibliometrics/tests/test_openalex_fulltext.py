from clamps_biblio.openalex_fulltext import (
    FULLTEXT_PROBE_GROUPS,
    openalex_work_id,
    row_has_openalex_fulltext,
)


def test_openalex_work_id_from_url():
    row = {"openalex_id": "https://openalex.org/W4413363116"}
    assert openalex_work_id(row) == "W4413363116"


def test_openalex_work_id_rejects_repo_rows():
    assert openalex_work_id({"openalex_id": "repo:mit:123"}) == ""


def test_row_has_openalex_fulltext_from_map():
    row = {"openalex_id": "https://openalex.org/W123"}
    assert row_has_openalex_fulltext(row, {"W123": True})
    assert not row_has_openalex_fulltext(row, {"W123": False})


def test_probe_groups_exclude_bare_clamps():
    for _, query in FULLTEXT_PROBE_GROUPS:
        for part in query.split("|"):
            assert part.strip() != "CLAMPS"
    labels = [label for label, _ in FULLTEXT_PROBE_GROUPS]
    assert "CLAMPS-1/2" in labels
