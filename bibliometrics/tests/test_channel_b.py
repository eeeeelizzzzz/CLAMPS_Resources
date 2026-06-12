from clamps_biblio.channel_b import (
    channel_b_ambiguous_needs_metadata_clamps,
    channel_b_metadata_confidence,
    channel_b_query_includes_facility,
    parse_channel_b_source,
    passes_channel_b_metadata_screening,
)
from clamps_biblio.relevance import qualifies_strict_high_confidence


def test_parse_channel_b_b1_label():
    family, campaign, terms = parse_channel_b_source(
        "channel_b:B1:AWAKEN+CLAMPS-2+Doppler lidar"
    )
    assert family == "B1"
    assert campaign == "AWAKEN"
    assert terms == ["CLAMPS-2", "Doppler lidar"]


def test_b1_ambiguous_campaign_trusted_without_metadata_clamps():
    row = {
        "discovery_source": "channel_b:B1:AWAKEN+CLAMPS-2+Doppler lidar",
        "confidence_tier": "high",
        "title": "Operational wind plants increase planetary boundary layer height",
        "abstract": "American WAKE experimeNt (AWAKEN) campaign observations.",
        "institutions": "University of Oklahoma; NOAA National Severe Storms Laboratory",
        "topics": "Wind Energy Research and Development",
    }
    assert channel_b_query_includes_facility(row["discovery_source"])
    assert not channel_b_ambiguous_needs_metadata_clamps(row, ["AWAKEN"])
    assert qualifies_strict_high_confidence(row, ["AWAKEN"])


def test_b2_ambiguous_drops_without_campaign_token_or_clamps():
    row = {
        "discovery_source": "channel_b:B2:TRACER+Doppler lidar",
        "title": "Urban trace gas formation with lidar",
        "abstract": "Volatile chemical products dominate ozone.",
        "institutions": "",
        "topics": "",
    }
    assert not passes_channel_b_metadata_screening(row, ["TRACER"])


def test_b2_ambiguous_kept_with_campaign_token_and_observation_keyword():
    row = {
        "discovery_source": "channel_b:B2:AWAKEN+Doppler lidar",
        "title": "AWAKEN Site A1 NREL scanning lidar derived data",
        "abstract": "",
        "institutions": "",
        "topics": "",
    }
    assert passes_channel_b_metadata_screening(row, ["AWAKEN"])


def test_b2_ambiguous_kept_with_campaign_token_only():
    row = {
        "discovery_source": "channel_b:B2:AWAKEN+Doppler lidar",
        "title": "Holistic scan optimization at the AWAKEN project",
        "abstract": "Nacelle-mounted scanning strategies for wind plants.",
        "institutions": "",
        "topics": "",
    }
    assert passes_channel_b_metadata_screening(row, ["AWAKEN"])
    assert channel_b_metadata_confidence(row, ["AWAKEN"]) == "campaign_token"


def test_b2_ambiguous_higher_confidence_with_observation_terms():
    row = {
        "discovery_source": "channel_b:B2:TRACER+Doppler lidar",
        "title": "Particle flux measurements during the TRACER campaign",
        "abstract": "",
        "institutions": "",
        "topics": "",
    }
    assert passes_channel_b_metadata_screening(row, ["TRACER"])
    assert channel_b_metadata_confidence(row, ["TRACER"]) == "campaign_plus_obs"


def test_b2_ambiguous_passes_strict_with_campaign_token_not_clamps():
    row = {
        "discovery_source": "channel_b:B2:AWAKEN+Doppler lidar",
        "confidence_tier": "high",
        "title": "AWAKEN Site A1 NREL scanning lidar derived data",
        "abstract": "",
        "institutions": "",
        "topics": "",
    }
    assert channel_b_ambiguous_needs_metadata_clamps(row, ["AWAKEN"])
    assert qualifies_strict_high_confidence(row, ["AWAKEN"])


def test_b2_ambiguous_fails_strict_without_campaign_token():
    row = {
        "discovery_source": "channel_b:B2:AWAKEN+Doppler lidar",
        "confidence_tier": "high",
        "title": "Emerging mobile lidar technology for wind energy",
        "abstract": "Wind plant wakes without naming the campaign.",
        "institutions": "",
        "topics": "",
    }
    assert not qualifies_strict_high_confidence(row, ["AWAKEN"])
