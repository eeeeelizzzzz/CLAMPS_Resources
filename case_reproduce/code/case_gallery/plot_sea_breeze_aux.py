"""Sea-breeze auxiliary figures — coastal vs inland surface arrival timing."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from netCDF4 import Dataset
from scipy.stats import binned_statistic

from awaken_windoe import load_windoe
from case_gallery.case_lib import (
    CaseSpec,
    figure_suptitle,
    find_case_files_for_date,
    find_windoe_file,
    get_case,
)
from case_gallery.plot_auxiliary import (  # noqa: E402
    SNR_DB_VMIN,
    _dewpoint_from_rh,
    _intensity_to_snr,
    _mask_clamps_sentinel,
    _mesonet_hour_ticks,
    _snr_linear_to_db,
)
from plot_awaken_instrument_template import SAVE_KW  # noqa: E402

COASTAL_COLOR = "#1565c0"
INLAND_COLOR = "#c62828"
C1_COLOR = COASTAL_COLOR  # blue
C2_COLOR = INLAND_COLOR  # red
STYLE_GRAY = "0.45"
BIN_MINUTES = 5.0
WDIR_MARKER_SIZE = 38.0
WDIR_MARKER_FACE = "0.72"
WDIR_MARKER_LW = 2.4
HIGHLIGHT_START_H = 17.0 + 50.0 / 60.0  # 1750 UTC
HIGHLIGHT_END_H = 18.0 + 10.0 / 60.0  # 1810 UTC
INLAND_HIGHLIGHT_START_H = 21.0 + 35.0 / 60.0  # 2135 UTC
INLAND_HIGHLIGHT_END_H = 22.0  # 2200 UTC
HIGHLIGHT_ALPHA = 0.18
DLFP_SNR_GATE = 2  # third range gate (0-based); skip lowest blind-zone gates


def _utc_hhmm(hour_decimal: float) -> str:
    hh = int(hour_decimal)
    mm = int(round((hour_decimal - hh) * 60.0))
    if mm >= 60:
        hh += 1
        mm = 0
    return f"{hh:02d}:{mm:02d}"


def _find_surface_met_file(case: CaseSpec) -> Path:
    """CLAMPS surface met / MWR tower file (aux/, then case root)."""
    ymd = case.case_date.strftime("%Y%m%d")
    roots = (case.clamps_root / "aux", case.clamps_root)
    patterns = ("*met*.cdf", "*mwr*a1*.cdf", "*mwr*a0*.cdf")
    for root in roots:
        if not root.is_dir():
            continue
        for pattern in patterns:
            matches = sorted(p for p in root.glob(pattern) if ymd in p.name)
            if matches:
                return matches[-1]
    raise FileNotFoundError(
        f"No CLAMPS surface met/MWR file for {ymd} under {case.clamps_root}"
    )


def _load_surface_met(path: Path) -> dict[str, np.ndarray]:
    """Load surface fields; wind may be absent on MWR radiometer-only files."""
    with Dataset(path) as nc:
        hour = np.asarray(nc.variables["hour"][:], dtype=float)
        temp_c = _mask_clamps_sentinel(nc.variables["sfc_temp"][:])
        if float(np.nanmax(temp_c)) > 100.0:
            temp_c = temp_c - 273.15
        rh_pct = (
            _mask_clamps_sentinel(nc.variables["sfc_rh"][:])
            if "sfc_rh" in nc.variables
            else np.full_like(hour, np.nan, dtype=float)
        )
        out: dict[str, np.ndarray] = {
            "hour": hour,
            "temp_c": temp_c,
            "dewpoint_c": _dewpoint_from_rh(temp_c, rh_pct),
            "rh_pct": rh_pct,
        }
        for key, var in (("wspd", "sfc_wspd"), ("wdir", "sfc_wdir")):
            if var in nc.variables:
                out[key] = _mask_clamps_sentinel(nc.variables[var][:])
            else:
                out[key] = np.full_like(hour, np.nan, dtype=float)
    return out


def _windoe_surface(case: CaseSpec) -> dict[str, np.ndarray]:
    wind = load_windoe(find_windoe_file(case))
    gate = int(np.argmin(wind.height_km))
    return {
        "hour": np.asarray(wind.hour, dtype=float),
        "wspd": np.asarray(wind.wind_speed[:, gate], dtype=float),
        "wdir": np.asarray(wind.wind_direction[:, gate], dtype=float),
    }


def _circular_mean_deg(values: np.ndarray) -> float:
    v = np.asarray(values, dtype=float)
    ok = np.isfinite(v)
    if not np.any(ok):
        return np.nan
    rad = np.deg2rad(v[ok])
    return float((np.rad2deg(np.arctan2(np.mean(np.sin(rad)), np.mean(np.cos(rad)))) + 360.0) % 360.0)


def _bin_surface(
    hour: np.ndarray,
    fields: dict[str, np.ndarray],
    *,
    hour_start: float,
    hour_end: float,
    bin_minutes: float = BIN_MINUTES,
) -> dict[str, np.ndarray]:
    bin_h = bin_minutes / 60.0
    h = np.asarray(hour, dtype=float)
    mask = np.isfinite(h) & (h >= hour_start) & (h <= hour_end)
    h = h[mask]
    if h.size < 2:
        raise ValueError("No surface samples in requested window")

    edges = np.arange(hour_start, hour_end + bin_h * 0.5, bin_h)
    if edges.size < 2:
        edges = np.array([hour_start, hour_end + bin_h])
    centers = (edges[:-1] + edges[1:]) / 2.0
    out: dict[str, np.ndarray] = {"hour": centers}

    for key, raw in fields.items():
        if key == "hour":
            continue
        y = np.asarray(raw, dtype=float)[mask]
        if key == "wdir":
            binned = np.full(len(centers), np.nan)
            for i in range(len(edges) - 1):
                m = (h >= edges[i]) & (h < edges[i + 1])
                if np.any(m):
                    binned[i] = _circular_mean_deg(y[m])
            out[key] = binned
        else:
            stat, _, _ = binned_statistic(h, y, statistic="mean", bins=edges)
            out[key] = np.asarray(stat, dtype=float)
    return out


def _site_series(
    case: CaseSpec,
    *,
    hour_start: float,
    hour_end: float,
    bin_minutes: float,
) -> tuple[dict[str, np.ndarray], str]:
    met_path = _find_surface_met_file(case)
    met = _load_surface_met(met_path)
    temp_binned = _bin_surface(
        met["hour"],
        {"temp_c": met["temp_c"], "dewpoint_c": met["dewpoint_c"]},
        hour_start=hour_start,
        hour_end=hour_end,
        bin_minutes=bin_minutes,
    )
    if np.any(np.isfinite(met["wspd"])):
        wind_src = "MWR met"
        wind_binned = _bin_surface(
            met["hour"],
            {"wspd": met["wspd"], "wdir": met["wdir"]},
            hour_start=hour_start,
            hour_end=hour_end,
            bin_minutes=bin_minutes,
        )
    else:
        wind_src = "WINDoe 0 km"
        wo = _windoe_surface(case)
        wind_binned = _bin_surface(
            wo["hour"],
            {"wspd": wo["wspd"], "wdir": wo["wdir"]},
            hour_start=hour_start,
            hour_end=hour_end,
            bin_minutes=bin_minutes,
        )
    return {
        "hour": temp_binned["hour"],
        "temp_c": temp_binned["temp_c"],
        "dewpoint_c": temp_binned["dewpoint_c"],
        "wspd": wind_binned["wspd"],
        "wdir": wind_binned["wdir"],
    }, wind_src


def _load_dlfp_gate_snr_db(case: CaseSpec, *, gate_idx: int = DLFP_SNR_GATE) -> dict[str, np.ndarray]:
    dlfp_path = find_case_files_for_date(case, case.case_date).dlfp
    with Dataset(dlfp_path) as nc:
        hour = np.asarray(nc.variables["hour"][:], dtype=float)
        height_km = np.asarray(nc.variables["height"][:], dtype=float)
        gate = int(min(max(gate_idx, 0), len(height_km) - 1))
        snr_lin = _intensity_to_snr(np.asarray(nc.variables["intensity"][:, gate], dtype=float))
    return {
        "hour": hour,
        "snr_db": _snr_linear_to_db(snr_lin, db_floor=SNR_DB_VMIN),
        "height_km": float(height_km[gate]),
    }


def _site_rh_snr_series(
    case: CaseSpec,
    *,
    hour_start: float,
    hour_end: float,
    bin_minutes: float,
) -> tuple[dict[str, np.ndarray], float]:
    met = _load_surface_met(_find_surface_met_file(case))
    rh_binned = _bin_surface(
        met["hour"],
        {"rh_pct": met["rh_pct"]},
        hour_start=hour_start,
        hour_end=hour_end,
        bin_minutes=bin_minutes,
    )
    snr_raw = _load_dlfp_gate_snr_db(case)
    snr_binned = _bin_surface(
        snr_raw["hour"],
        {"snr_db": snr_raw["snr_db"]},
        hour_start=hour_start,
        hour_end=hour_end,
        bin_minutes=bin_minutes,
    )
    return {
        "hour": rh_binned["hour"],
        "rh_pct": rh_binned["rh_pct"],
        "snr_db": snr_binned["snr_db"],
    }, float(snr_raw["height_km"])


def _add_highlight_bands(axes) -> None:
    for ax in axes:
        ax.axvspan(
            HIGHLIGHT_START_H,
            HIGHLIGHT_END_H,
            color=COASTAL_COLOR,
            alpha=HIGHLIGHT_ALPHA,
            zorder=0,
        )
        ax.axvspan(
            INLAND_HIGHLIGHT_START_H,
            INLAND_HIGHLIGHT_END_H,
            color=INLAND_COLOR,
            alpha=HIGHLIGHT_ALPHA,
            zorder=0,
        )


def _draw_rh_snr_panel(
    ax_rh: plt.Axes,
    coastal: dict[str, np.ndarray],
    inland: dict[str, np.ndarray],
    *,
    z_coastal: float,
    z_inland: float,
    hour_start: float,
    hour_end: float,
    line_lw: float,
    show_xlabel: bool,
    legend_sites: bool = True,
) -> None:
    ax_snr = ax_rh.twinx()
    ax_rh.set_zorder(2)
    ax_snr.set_zorder(1)
    ax_rh.patch.set_visible(False)

    ax_rh.plot(coastal["hour"], coastal["rh_pct"], color=COASTAL_COLOR, lw=line_lw)
    ax_rh.plot(inland["hour"], inland["rh_pct"], color=INLAND_COLOR, lw=line_lw)
    ax_snr.plot(coastal["hour"], coastal["snr_db"], color=COASTAL_COLOR, lw=line_lw, ls="--")
    ax_snr.plot(inland["hour"], inland["snr_db"], color=INLAND_COLOR, lw=line_lw, ls="--")

    ax_rh.set_ylabel("Surface RH (%)")
    gate_note = (
        f"{z_coastal:.3f} km"
        if abs(z_coastal - z_inland) < 0.005
        else f"C2 {z_coastal:.3f} km; C1 {z_inland:.3f} km"
    )
    ax_snr.set_ylabel(f"DL-FP SNR (dB) @ gate {gate_note}", color="0.45")
    ax_snr.tick_params(axis="y", colors="0.45")
    ax_snr.spines["right"].set_color("0.45")
    if show_xlabel:
        ax_rh.set_xlabel("UTC time", labelpad=10)
    _mesonet_hour_ticks(
        ax_rh,
        x_min=hour_start,
        x_max=hour_end,
        show_tick_labels=show_xlabel,
    )

    if legend_sites:
        legend_handles = [
            Line2D([0], [0], color=INLAND_COLOR, lw=line_lw, ls="-", label="CLAMPS1"),
            Line2D([0], [0], color=COASTAL_COLOR, lw=line_lw, ls="-", label="CLAMPS2"),
            Line2D([0], [0], color=STYLE_GRAY, lw=line_lw, ls="--", label="SNR"),
            Line2D([0], [0], color=STYLE_GRAY, lw=line_lw, ls="-", label="RH"),
        ]
    else:
        legend_handles = [
            Line2D([0], [0], color=STYLE_GRAY, lw=line_lw, ls="--", label="SNR"),
            Line2D([0], [0], color=STYLE_GRAY, lw=line_lw, ls="-", label="RH"),
        ]
    ax_rh.legend(
        handles=legend_handles,
        loc="lower left",
        ncol=2,
        fontsize=7.5,
        framealpha=0.92,
    )


def plot_seabreeze_rh_snr_timeseries(
    coastal_case: CaseSpec,
    inland_case: CaseSpec,
    output_path: Path,
    *,
    hour_start: float = 4.0,
    hour_end: float = 15.0,
    bin_minutes: float = BIN_MINUTES,
) -> Path:
    coastal, z_coastal = _site_rh_snr_series(
        coastal_case,
        hour_start=hour_start,
        hour_end=hour_end,
        bin_minutes=bin_minutes,
    )
    inland, z_inland = _site_rh_snr_series(
        inland_case,
        hour_start=hour_start,
        hour_end=hour_end,
        bin_minutes=bin_minutes,
    )

    fig, ax_rh = plt.subplots(figsize=(12.0, 4.2), layout="constrained")
    line_lw = 2.2
    _draw_rh_snr_panel(
        ax_rh,
        coastal,
        inland,
        z_coastal=z_coastal,
        z_inland=z_inland,
        hour_start=hour_start,
        hour_end=hour_end,
        line_lw=line_lw,
        show_xlabel=True,
    )

    subtitle = (
        f"Surface RH (MWR) vs DL-FP SNR (gate {DLFP_SNR_GATE + 1}) · "
        f"{_utc_hhmm(hour_start)}–{_utc_hhmm(hour_end)} UTC"
    )
    fig.suptitle(
        figure_suptitle(coastal_case, subtitle=subtitle),
        fontsize=10,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def plot_seabreeze_arrival_meteogram(
    coastal_case: CaseSpec,
    inland_case: CaseSpec,
    output_path: Path,
    *,
    hour_start: float = 17.0,
    hour_end: float = 22.5,
    bin_minutes: float = BIN_MINUTES,
) -> Path:
    coastal, coastal_wind = _site_series(
        coastal_case,
        hour_start=hour_start,
        hour_end=hour_end,
        bin_minutes=bin_minutes,
    )
    inland, inland_wind = _site_series(
        inland_case,
        hour_start=hour_start,
        hour_end=hour_end,
        bin_minutes=bin_minutes,
    )
    coastal_rh_snr, z_coastal = _site_rh_snr_series(
        coastal_case,
        hour_start=hour_start,
        hour_end=hour_end,
        bin_minutes=bin_minutes,
    )
    inland_rh_snr, z_inland = _site_rh_snr_series(
        inland_case,
        hour_start=hour_start,
        hour_end=hour_end,
        bin_minutes=bin_minutes,
    )

    fig, axes = plt.subplots(
        4,
        1,
        figsize=(12.0, 9.2),
        sharex=True,
        layout="constrained",
        gridspec_kw={"height_ratios": [1.0, 1.0, 1.05, 0.95]},
    )
    ax_t, ax_td, ax_wind, ax_rh = axes
    line_lw = 2.2
    # One marker every 10 min (2 × 5-min bins).
    mark_every = max(int(10.0 / bin_minutes), 1)

    _add_highlight_bands(axes)

    ax_t.plot(
        coastal["hour"],
        coastal["temp_c"],
        color=COASTAL_COLOR,
        lw=line_lw,
        label="CLAMPS2 coastal",
    )
    ax_t.plot(
        inland["hour"],
        inland["temp_c"],
        color=INLAND_COLOR,
        lw=line_lw,
        label="CLAMPS1 inland",
    )
    ax_t.set_ylabel("Temperature (°C)")
    ax_t.legend(loc="upper left", fontsize=7.5, framealpha=0.92)
    _mesonet_hour_ticks(ax_t, x_min=hour_start, x_max=hour_end, show_tick_labels=False)

    ax_td.plot(
        coastal["hour"],
        coastal["dewpoint_c"],
        color=COASTAL_COLOR,
        lw=line_lw,
    )
    ax_td.plot(
        inland["hour"],
        inland["dewpoint_c"],
        color=INLAND_COLOR,
        lw=line_lw,
    )
    ax_td.set_ylabel(r"Dewpoint $T_d$ (°C)")
    _mesonet_hour_ticks(ax_td, x_min=hour_start, x_max=hour_end, show_tick_labels=False)

    ax_wspd = ax_wind
    ax_wdir = ax_wind.twinx()
    ax_wspd.set_zorder(2)
    ax_wdir.set_zorder(1)
    ax_wspd.patch.set_visible(False)

    ax_wspd.plot(coastal["hour"], coastal["wspd"], color=COASTAL_COLOR, lw=line_lw)
    ax_wspd.plot(inland["hour"], inland["wspd"], color=INLAND_COLOR, lw=line_lw)
    ax_wspd.set_ylabel("Wind speed (m s$^{-1}$)")
    wspd_max = float(
        np.nanmax(np.concatenate([coastal["wspd"], inland["wspd"]]))
    )
    ax_wspd.set_ylim(0.0, max(wspd_max * 1.15, 1.0))

    for series, edge_color, marker in (
        (coastal, COASTAL_COLOR, "D"),
        (inland, INLAND_COLOR, "s"),
    ):
        idx = np.arange(0, series["hour"].size, mark_every)
        ok = np.isfinite(series["wdir"][idx]) & np.isfinite(series["hour"][idx])
        ax_wdir.scatter(
            series["hour"][idx][ok],
            series["wdir"][idx][ok],
            s=WDIR_MARKER_SIZE,
            marker=marker,
            facecolors=WDIR_MARKER_FACE,
            edgecolors=edge_color,
            linewidths=WDIR_MARKER_LW,
            zorder=4,
        )
    ax_wdir.set_ylabel("Wind direction (°)", color="0.45")
    ax_wdir.set_ylim(0.0, 360.0)
    ax_wdir.set_yticks(range(0, 361, 45))
    ax_wdir.tick_params(axis="y", colors="0.45")
    ax_wdir.spines["right"].set_color("0.45")
    _mesonet_hour_ticks(ax_wind, x_min=hour_start, x_max=hour_end, show_tick_labels=False)

    _draw_rh_snr_panel(
        ax_rh,
        coastal_rh_snr,
        inland_rh_snr,
        z_coastal=z_coastal,
        z_inland=z_inland,
        hour_start=hour_start,
        hour_end=hour_end,
        line_lw=line_lw,
        show_xlabel=True,
        legend_sites=False,
    )

    wind_note = coastal_wind if coastal_wind == inland_wind else f"C2 {coastal_wind}; C1 {inland_wind}"
    subtitle = (
        f"Sea breeze arrival timing · surface T / $T_d$ / RH (MWR); "
        f"winds ({wind_note}); DL-FP SNR (gate {DLFP_SNR_GATE + 1}) · "
        f"{_utc_hhmm(hour_start)}–{_utc_hhmm(hour_end)} UTC"
    )
    fig.suptitle(
        figure_suptitle(coastal_case, subtitle=subtitle),
        fontsize=10,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def plot_seabreeze_auxiliary(
    *,
    coastal_case_id: str = "sea_breeze_c2",
    inland_case_id: str = "sea_breeze_c1",
    hour_start: float = 17.0,
    hour_end: float = 22.5,
    rh_snr_hour_start: float = 4.0,
    rh_snr_hour_end: float = 15.0,
    bin_minutes: float = BIN_MINUTES,
    force: bool = False,
) -> list[Path]:
    import shutil

    coastal = get_case(coastal_case_id)
    inland = get_case(inland_case_id)
    met_name = "aux_seabreeze_arrival_meteogram.png"
    rh_snr_name = "aux_seabreeze_rh_snr.png"
    met_paths = [coastal.figure_dir / met_name, inland.figure_dir / met_name]
    rh_snr_paths = [coastal.figure_dir / rh_snr_name, inland.figure_dir / rh_snr_name]
    all_paths = met_paths + rh_snr_paths

    need_met = force or not all(p.exists() for p in met_paths)
    need_rh_snr = force or not all(p.exists() for p in rh_snr_paths)
    if not need_met and not need_rh_snr:
        print(f"{coastal_case_id}: sea breeze auxiliary figures exist")
        return all_paths

    if need_met:
        plot_seabreeze_arrival_meteogram(
            coastal,
            inland,
            met_paths[0],
            hour_start=hour_start,
            hour_end=hour_end,
            bin_minutes=bin_minutes,
        )
        shutil.copy2(met_paths[0], met_paths[1])

    if need_rh_snr:
        plot_seabreeze_rh_snr_timeseries(
            coastal,
            inland,
            rh_snr_paths[0],
            hour_start=rh_snr_hour_start,
            hour_end=rh_snr_hour_end,
            bin_minutes=bin_minutes,
        )
        shutil.copy2(rh_snr_paths[0], rh_snr_paths[1])

    return all_paths
