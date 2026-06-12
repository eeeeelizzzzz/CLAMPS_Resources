from clamps_biblio.channel_a import (
    has_channel_a_phrase_in_metadata,
    is_meteorology_channel_a_fallback,
    passes_channel_a_filter,
    phrase_in_text,
)


def test_phrase_requires_complete_token():
    assert phrase_in_text("The CLAMPS-1 lidar was deployed.", "CLAMPS-1")
    assert not phrase_in_text("A contactless piezoelectric harvester", "CLAMPS-1")
    assert phrase_in_text("Facility CLAMPS 1 operated overnight.", "CLAMPS 1")
    assert not phrase_in_text("CLAMPS1 gene expression", "CLAMPS 1")


def test_hyphen_space_alias():
    row = {
        "discovery_source": "channel_a:CLAMPS-1",
        "title": "Site Rolling Meadows Golf Course - CLAMPS 1 Lidar / Raw Data",
        "abstract": "ARM reviewed dataset.",
    }
    assert has_channel_a_phrase_in_metadata(row)
    assert passes_channel_a_filter(row)


def test_meteorology_fallback_without_phrase():
    row = {
        "discovery_source": "channel_a:CLAMPS2",
        "title": "Quantifying the Thermodynamic Impacts on the Atmospheric Boundary Layer",
        "abstract": "Sea breeze influences in coastal Houston.",
    }
    assert not has_channel_a_phrase_in_metadata(row)
    assert is_meteorology_channel_a_fallback(row)
    assert passes_channel_a_filter(row)


def test_homograph_still_rejected():
    row = {
        "discovery_source": "channel_a:CLAMPS-1",
        "title": "NiTi Shape Memory Clamps with Modified Surface for Bone Fracture Treatment",
        "abstract": "Bone healing application.",
    }
    assert not passes_channel_a_filter(row)


def test_non_meteorology_without_phrase_rejected():
    row = {
        "discovery_source": "channel_a:CLAMPS-2",
        "title": "Generic engineering study",
        "abstract": "We used CLAMPS-1 during tests.",
    }
    assert has_channel_a_phrase_in_metadata(row) is False
    assert not passes_channel_a_filter(row)
