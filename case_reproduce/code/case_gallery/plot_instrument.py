#!/usr/bin/env python3
"""Gallery instrument-template 4-panel figure per case."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_CODE = Path(__file__).resolve().parent.parent
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

from plot_awaken_instrument_template import (  # noqa: E402 — bootstraps pyc deps
    DEFAULT_SIGMA_WSPD_MAX,
    DLVAD_SNR_THRESHOLD,
    dlvad_snr_ceiling,
    la,
    load_cloud_base,
    plot_four_panel_template,
    smooth_snr_ceiling,
    wind_panel_title as format_wind_panel_title,
)
from awaken_la_diagnostics import (  # noqa: E402
    CROSS_SECTION_MAX_KM,
    build_profiler_cross_section,
    load_fuzzy_pblh,
)
from case_gallery.case_lib import (  # noqa: E402
    CaseSpec,
    figure_suptitle,
    find_case_files,
    find_pbl_file,
    get_case,
)
from case_gallery.extended_period import (  # noqa: E402
    case_period,
    stitch_cloud_base,
    stitch_pbl,
    stitch_profiler_cross_section,
    stitch_snr_ceiling,
    stitch_wind,
)
from case_gallery.plot_limits import (  # noqa: E402
    limits_for_case,
    q_ticks,
    theta_v_ticks,
    wspd_ticks,
)
from awaken_windoe import load_dlvad_snr  # noqa: E402
from case_gallery.winds import load_case_winds  # noqa: E402
from paths import MPLCONFIG_DIR  # noqa: E402

# Cases where PPI WINDoe is sparse/unreliable — show DLVAD on the wind panel.
DLVAD_WIND_CASES = frozenset({"stable_bad_dl_c1"})


def _day_period(case_date: date) -> la.PeriodAxis:
    start = datetime(case_date.year, case_date.month, case_date.day, tzinfo=timezone.utc)
    end = start + timedelta(hours=24)
    return la.PeriodAxis(start=start, end=end)


def _instrument_suptitle(case: CaseSpec) -> str:
    if case.period_extend_hours > 0:
        total_h = 24 + case.period_extend_hours
        return figure_suptitle(
            case,
            subtitle=(
                f"CLAMPS observations · PBLH (fuzzy logic) · "
                f"{total_h} h UTC ({case.case_date.isoformat()} + "
                f"{case.period_extend_hours} h)"
            ),
        )
    return figure_suptitle(case)


def plot_instrument(case_id: str, *, force: bool = False) -> Path:
    case = get_case(case_id)
    files = find_case_files(case)
    limits = limits_for_case(case_id)
    prefer = "dlvad" if case_id in DLVAD_WIND_CASES else "auto"

    if case.period_extend_hours > 0:
        period = case_period(case)
        prof = stitch_profiler_cross_section(
            case, period, max_km=CROSS_SECTION_MAX_KM
        )
        wind, wind_source = stitch_wind(case, period, prefer=prefer)
        pbl = stitch_pbl(case, period)
        snr_h, snr_z = stitch_snr_ceiling(case, period)
        snr_z = smooth_snr_ceiling(snr_h, snr_z)
        cb_h, cb_z = stitch_cloud_base(case, period)
    else:
        period = _day_period(case.case_date)
        wind, wind_source = load_case_winds(case, prefer=prefer)
        prof = build_profiler_cross_section(
            files.tropoe, files.dlfp, max_km=CROSS_SECTION_MAX_KM, apply_tropoe_qc=False
        )
        pbl = load_fuzzy_pblh(find_pbl_file(case))
        snr_h, snr_z = dlvad_snr_ceiling(
            load_dlvad_snr(files.dlvad), threshold=DLVAD_SNR_THRESHOLD
        )
        snr_z = smooth_snr_ceiling(snr_h, snr_z)
        cb_h, cb_z = load_cloud_base(files.tropoe)

    out_dir = case.figure_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "instrument_template_4panel.png"
    if out_path.exists() and not force:
        print(f"{case_id}: figure exists ({out_path.name})")
        return out_path

    wind_title = format_wind_panel_title(wind_source)
    suptitle = _instrument_suptitle(case)

    os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))
    plot_four_panel_template(
        prof,
        wind,
        snr_h,
        snr_z,
        pbl,
        case.case_date,
        period,
        out_path,
        sigma_wspd_max=DEFAULT_SIGMA_WSPD_MAX,
        suptitle=suptitle,
        theta_v_lim=limits.theta_v,
        q_lim=limits.q_gkg,
        wspd_lim=limits.wspd,
        theta_v_cbar_ticks=theta_v_ticks(*limits.theta_v),
        q_cbar_ticks=q_ticks(*limits.q_gkg),
        wspd_cbar_ticks=wspd_ticks(*limits.wspd),
        cloud_base_hour=cb_h,
        cloud_base_km=cb_z,
        wind_panel_title=wind_title,
        tropoe_path=files.tropoe,
        dlfp_path=files.dlfp,
    )
    print(f"  saved {out_path.name}")
    print(f"Saved {out_path}")
    return out_path


def run_case(case: CaseSpec, *, force: bool = False) -> None:
    plot_instrument(case.id, force=force)


def main() -> None:
    p = argparse.ArgumentParser(description="Plot gallery instrument template")
    p.add_argument("case_id")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    plot_instrument(args.case_id, force=args.force)


if __name__ == "__main__":
    main()
