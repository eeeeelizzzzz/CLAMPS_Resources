from clamps_biblio.field_campaigns import (
    campaign_in_text,
    campaigns_in_text,
    is_excluded_discovery_campaign,
)
from clamps_biblio.clamps_signals import has_clamps_signal, is_campaign_only_signal


def test_mini_mpex_variants():
    for text in (
        "Observations during miniMPEX",
        "MiniMPEX spring deployment",
        "mini-MPEX field phase",
    ):
        assert campaign_in_text(text, "mini-MPEX")


def test_mini_mpex_full_name():
    assert campaign_in_text(
        "Data from the Mini-Mesoscale Predictability EXperiment",
        "mini-MPEX",
    )


def test_vortex_se_and_usa_separate():
    assert campaign_in_text("Part of VORTEX SE 2017", "VORTEX-SE")
    assert not campaign_in_text("vortex se mesoscale study", "VORTEX-SE")
    assert campaign_in_text("VORTEX USA deployment", "VORTEX-USA")
    assert not campaign_in_text("VORTEX USA deployment", "VORTEX-SE")


def test_epic_numbered_and_bare_variants():
    assert campaign_in_text("EPIC-1 at the SGP", "EPIC")
    assert campaign_in_text("during EPIC 2 operations", "EPIC")
    assert campaign_in_text("the EPIC field project at Lamont", "EPIC")
    assert not campaign_in_text("an epic boundary layer study", "EPIC")


def test_perils_case_i():
    assert campaign_in_text("datasets from PERiLS", "PERiLS")
    assert campaign_in_text("during PERILS spring phase", "PERiLS")
    assert not campaign_in_text("environmental perils and risk", "PERiLS")


def test_tracer_case_sensitive_and_full_name():
    assert campaign_in_text("the TRACER campaign in Houston", "TRACER")
    assert campaign_in_text(
        "during the Tracking Aerosol Convection Interactions Experiment",
        "TRACER",
    )
    assert campaign_in_text(
        "the TRacking Aerosol Convection interactions ExpeRiment science plan",
        "TRACER",
    )
    assert not campaign_in_text("trace gases and aerosol tracers", "TRACER")


def test_escape_requires_tracer():
    escape_name = (
        "Experiment of Sea Breeze Convection, Aerosols, Precipitation, and Environment"
    )
    assert not campaign_in_text(escape_name, "ESCAPE")
    assert not campaign_in_text(escape_name, "TRACER")
    assert campaign_in_text(f"{escape_name} alongside TRACER operations", "ESCAPE")
    assert campaign_in_text(f"{escape_name} alongside TRACER operations", "TRACER")


def test_splash_and_sail_co_occurrence():
    splash_name = (
        "Study of Precipitation, the Lower Atmosphere, and Surface for Hydrometeorology"
    )
    sail_name = "Surface Atmosphere Integrated Field Laboratory"
    assert campaign_in_text(splash_name, "SPLASH")
    assert not campaign_in_text(sail_name, "SAIL")
    assert campaign_in_text(f"{splash_name} and {sail_name}", "SAIL")
    assert campaign_in_text(f"{splash_name} and {sail_name}", "SPLASH-SAIL")
    assert not campaign_in_text("SAIL operations in Colorado", "SAIL")


def test_pbltops_only_approved_tokens():
    assert campaign_in_text("validation during PBL-Tops", "PBLTops")
    assert campaign_in_text("the BLTops deployment in 2020", "PBLTops")
    assert not campaign_in_text("PBLTops experiment at KAEFS", "PBLTops")
    assert not campaign_in_text("PBL Tops field study", "PBLTops")


def test_cheesehead_full_name_hyphen_variants():
    assert campaign_in_text(
        "Chequamegon Heterogeneous Ecosystem Energy-balance Study Enabled "
        "by a High-density Extensive Array of Detectors",
        "CHEESEHEAD",
    )
    assert campaign_in_text(
        "Chequamegon Heterogeneous Ecosystem Energy-Balance Study Enabled "
        "by a High-Density Extensive Array of Detectors",
        "CHEESEHEAD",
    )


def test_scales_subcampaign_tokens():
    assert campaign_in_text("coordinated flights during mesoSCALES", "SCALES")
    assert campaign_in_text("MicroSCALES urban profiling", "SCALES")


def test_excluded_discovery_campaigns():
    assert is_excluded_discovery_campaign("Dual Doppler")
    assert is_excluded_discovery_campaign("Mesonet/NWS")
    assert is_excluded_discovery_campaign("NWC readiness")
    assert is_excluded_discovery_campaign("SGP-MPD Compare")
    assert not is_excluded_discovery_campaign("PECAN")


def test_clamps_case_sensitive():
    assert has_clamps_signal("The CLAMPS-2 profiler operated overnight.")
    assert has_clamps_signal("Facility CLAMPS1 data product")
    assert not has_clamps_signal("contactless clamps for surgery")


def test_campaign_only_uses_case_sensitive_tokens():
    assert not is_campaign_only_signal("Urban trace gas measurements with lidar")
    assert is_campaign_only_signal("the TRACER campaign overview")
