from clamps_biblio.work_exclusions import (
    broad_pool_exclusion_reason,
    is_publication_year_excluded,
    publication_year_floor_reason,
)


def test_pre_2015_dropped_without_strong_clamps():
    row = {
        "year": 2014,
        "title": "Boundary layer observations during a field campaign",
        "discovery_source": "channel_d:Example Author",
    }
    assert publication_year_floor_reason(row) == "excluded:pre_2015_no_strong_clamps"
    assert is_publication_year_excluded(row)


def test_pre_2015_kept_with_strong_clamps():
    row = {
        "year": 2013,
        "title": "Profiles from CLAMPS-2 during LAPSE-RATE",
        "discovery_source": "channel_d:Example Author",
    }
    assert publication_year_floor_reason(row) == ""
    assert not is_publication_year_excluded(row)


def test_year_floor_exempt_for_channel_g():
    row = {
        "year": 2010,
        "title": "Legacy CLAMPS paper",
        "discovery_source": "channel_g:ground_truth",
    }
    assert publication_year_floor_reason(row) == ""


def test_deposit_class_n_excluded_from_broad_pool():
    row = {"doi": "10.5281/zenodo.6713495", "type": "dataset"}
    assert broad_pool_exclusion_reason(row) == "excluded:deposit_class:n"


def test_year_2015_and_later_always_pass():
    row = {
        "year": 2015,
        "title": "Boundary layer study",
        "discovery_source": "channel_d:Example Author",
    }
    assert not is_publication_year_excluded(row)
