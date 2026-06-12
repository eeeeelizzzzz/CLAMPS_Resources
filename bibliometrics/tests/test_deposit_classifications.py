from clamps_biblio.deposit_classifications import (
    get_work_class,
    is_publication_override,
    is_search_excluded,
    search_exclusion_reason,
)


def test_search_excluded_for_n_and_dup():
    assert is_search_excluded({"doi": "10.5281/zenodo.6713495"})
    assert search_exclusion_reason({"doi": "10.5281/zenodo.6713495"}) == "excluded:deposit_class:n"
    assert is_search_excluded({"doi": "10.0000/unknown-dup", "work_class": "dup"})
    assert search_exclusion_reason({"doi": "10.0000/unknown-dup", "work_class": "dup"}) == "excluded:deposit_class:dup"


def test_dataset_and_article_not_search_excluded():
    assert not is_search_excluded({"doi": "10.5281/zenodo.7826881", "work_class": "x"})
    assert not is_search_excluded({"doi": "10.5194/wes-10-1681-2025", "work_class": "a"})


def test_publication_override_for_article_and_report():
    assert is_publication_override({"doi": "10.5194/wes-10-1681-2025", "work_class": "a"})
    assert is_publication_override({"work_class": "r"})
    assert not is_publication_override({"work_class": "x"})


def test_work_class_from_row_fallback():
    assert get_work_class({"doi": "unknown", "work_class": "n"}) == "n"
