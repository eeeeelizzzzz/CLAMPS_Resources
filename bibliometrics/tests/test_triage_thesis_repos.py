import pandas as pd

from scripts.triage_thesis_repos import score_row


def test_campaign_only_without_met_keywords_is_auto_rejected():
    row = pd.Series(
        {
            "title": "Mrs. Lucas' selected pecan recipes",
            "abstract": "",
            "discovery_source": "channel_h:campaign_candidate:ttu_ir+PECAN",
            "year": 2020,
        }
    )
    score, bucket, reason = score_row(row)
    assert bucket == "auto_reject"
    assert "campaign_only_no_met" in reason


def test_campaign_with_met_title_is_not_auto_rejected():
    row = pd.Series(
        {
            "title": "Lidar observations of the nocturnal boundary layer during PERiLS",
            "abstract": "",
            "discovery_source": "channel_h:campaign_candidate:ttu_ir+PERiLS",
            "year": 2022,
        }
    )
    score, bucket, reason = score_row(row)
    assert bucket != "auto_reject"
    assert "met_title" in reason


def test_campaign_with_strong_clamps_in_abstract_kept():
    row = pd.Series(
        {
            "title": "Instrument intercomparison study",
            "abstract": "Data were collected by the CLAMPS-1 facility during AWAKEN.",
            "discovery_source": "channel_h:campaign_candidate:ttu_ir+AWAKEN",
            "year": 2023,
        }
    )
    score, bucket, reason = score_row(row)
    assert bucket != "auto_reject"
    assert "strong_clamps_phrase" in reason
