from clamps_biblio.homophone_filters import homophone_reason, scales_homograph_reason


def test_scales_campaign_homograph_rejects_generic_lidar_hit():
    row = {
        "discovery_source": "channel_b:B2:SCALES+Doppler lidar",
        "title": "Dissipation Scaling in the Stable Atmospheric Boundary Layer",
        "abstract": "Doppler lidar observations of turbulence scaling.",
    }
    assert homophone_reason(row) == "homograph:scales_campaign"


def test_scales_campaign_kept_with_clamps_in_metadata():
    row = {
        "discovery_source": "channel_b:B2:SCALES+Doppler lidar",
        "title": "Boundary-layer profiles during SCALES with CLAMPS-2",
        "abstract": "",
    }
    assert scales_homograph_reason(row) == ""


def test_scales_campaign_kept_with_scales_acronym_in_metadata():
    row = {
        "discovery_source": "channel_b:B2:SCALES+remote profiler",
        "title": "Preliminary SCALES deployment overview",
        "abstract": "Remote profiler operations during the SCALES field campaign.",
    }
    assert scales_homograph_reason(row) == ""
