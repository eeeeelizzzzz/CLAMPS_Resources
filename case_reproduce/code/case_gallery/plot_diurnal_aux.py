"""Diurnal-cycle auxiliary figures (surface met, skew-T, bulk Richardson number)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import FuncNorm, LinearSegmentedColormap
from matplotlib.lines import Line2D
from metpy.calc import dewpoint_from_specific_humidity
from metpy.plots import SkewT
from metpy.units import units
from netCDF4 import Dataset
from scipy.interpolate import RegularGridInterpolator

from awaken_la_diagnostics import build_profiler_cross_section
from awaken_windoe import WindoeData
from case_gallery.case_lib import CaseSpec, figure_suptitle
from plot_awaken_instrument_template import MAX_HEIGHT_KM, PLOT_DATA_MAX_KM, SAVE_KW, TITLE_PAD, la

from case_gallery.plot_auxiliary import (  # noqa: E402 — shared meteogram helpers
    _load_clamps_mwr_surface,
    _mesonet_hour_ticks,
    _plot_surface_meteogram_panels,
)

G = 9.81
RIB_THRESHOLD = 0.25
RIB_VMIN = -10.0
RIB_VMAX = 10.0
RIB_LOG_EPS = 0.02
RIB_LINEAR_BAND = 0.05
RIB_BAND_CMAP_FRAC = 0.14
RIB_FILL_LEVELS_EACH = 40
RIB_FILL_LEVELS_LINEAR = 18
RIB_CBAR_NUMERIC = (-1.0, -0.5, 0.0, 0.25, 0.5, 1.0)

T_COLOR = "#1565c0"
TD_COLOR = "#ef6c00"
# MetPy Skew-T display height/width for ylim 1050–250, xlim -40–40, rotation 30°.
SKEWT_PANEL_HW = 0.725
SKEWT_PANEL_W_IN = 3.2
SKEWT_PANEL_GAP_IN = 0.35
SKEWT_ROW_GAP_IN = 0.40
SKEWT_LEFT_IN = 0.70
SKEWT_BOTTOM_IN = 0.55
SKEWT_TOP_IN = 0.72
SKEWT_P_TOP_FULL = 250.0
SKEWT_P_TOP_ZOOM = 700.0
SKEWT_XLIM_FULL = (-40.0, 40.0)
SKEWT_XLIM_ZOOM = (10.0, 40.0)


def _find_clamps_met_file(case: CaseSpec) -> Path:
    return _find_clamps_met_file_for_date(case, case.case_date)


def _find_clamps_met_file_for_date(case: CaseSpec, calendar_date: date) -> Path:
    aux_dir = case.clamps_root / "aux"
    ymd = calendar_date.strftime("%Y%m%d")
    for pattern in ("*met*.cdf", "*mwr*a1*.cdf", "*mwr*a0*.cdf", "*mwr*.cdf"):
        matches = sorted(p for p in aux_dir.glob(pattern) if ymd in p.name)
        if matches:
            return matches[-1]
    raise FileNotFoundError(f"No CLAMPS met/MWR file for {ymd} under {aux_dir}")


def stitch_clamps_met_surface(case: CaseSpec, period: la.PeriodAxis) -> dict[str, np.ndarray]:
    from case_gallery.extended_period import (
        _datetime_from_hour,
        in_period_window,
        period_calendar_dates,
        period_hours,
    )

    keys = ("hour", "pres", "wspd", "wdir", "temp_c", "rh_pct", "dewpoint_c", "rain_rate")
    parts: dict[str, list[float]] = {k: [] for k in keys}
    for cal_date in period_calendar_dates(case):
        try:
            met_path = _find_clamps_met_file_for_date(case, cal_date)
        except FileNotFoundError:
            print(f"  skip met {cal_date}: no CLAMPS met file")
            continue
        surf = _load_clamps_mwr_surface(met_path)
        for i, hod in enumerate(surf["hour"]):
            dt = _datetime_from_hour(cal_date, float(hod))
            if not in_period_window(dt, case, period):
                continue
            parts["hour"].append(period_hours(period, dt))
            for key in keys:
                if key == "hour":
                    continue
                parts[key].append(float(surf[key][i]))
    if not parts["hour"]:
        raise ValueError(f"No CLAMPS met in period for {case.id}")
    order = np.argsort(parts["hour"])
    return {k: np.asarray(parts[k], dtype=float)[order] for k in keys}


def _period_window_subtitle(hour_start: float, hour_end: float, case: CaseSpec) -> str:
    from datetime import timedelta

    end_date = case.case_date + timedelta(days=1) if hour_end > 24.0 else case.case_date
    h0 = int(hour_start) % 24
    h1 = int(hour_end) if hour_end <= 24.0 else int(hour_end) % 24
    return (
        f"CLAMPS surface meteogram · {h0:02d}Z {case.case_date:%m/%d}–"
        f"{h1:02d}Z {end_date:%m/%d} UTC"
    )


def _find_sounding_files(case: CaseSpec) -> list[Path]:
    aux_dir = case.clamps_root / "aux"
    matches = sorted(aux_dir.glob("KAEFS*.nc")) + sorted(aux_dir.glob("*sounding*.nc"))
    return matches


def _parse_sounding_hour(path: Path) -> float:
    match = re.search(r"_(\d{6})\.nc$", path.name)
    if not match:
        raise ValueError(f"Cannot parse launch time from sounding filename: {path.name}")
    text = match.group(1)
    hh, mm, ss = int(text[:2]), int(text[2:4]), int(text[4:6])
    return hh + mm / 60.0 + ss / 3600.0


def _interp_met_sparse(hour: np.ndarray, values: np.ndarray) -> np.ndarray:
    hour = np.asarray(hour, dtype=float)
    values = np.asarray(values, dtype=float)
    valid = np.isfinite(values)
    if valid.sum() < 2:
        return values
    return np.interp(hour, hour[valid], values[valid], left=np.nan, right=np.nan)


def _load_raob_sounding(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with Dataset(path) as nc:
        pres = np.asarray(nc.variables["pres"][:], dtype=float)
        temp_c = np.asarray(nc.variables["tdry"][:], dtype=float)
        dpt_c = np.asarray(nc.variables["dpt"][:], dtype=float)
    ok = np.isfinite(pres) & np.isfinite(temp_c) & (pres > 0)
    order = np.argsort(pres)[::-1]
    return pres[ok][order], temp_c[ok][order], dpt_c[ok][order]


def _dewpoint_from_q_gkg(q_gkg: np.ndarray, p_hpa: np.ndarray) -> np.ndarray:
    q = np.maximum(np.asarray(q_gkg, dtype=float), 0.0) / 1000.0 * units("kg/kg")
    p = np.asarray(p_hpa, dtype=float) * units.hPa
    td = dewpoint_from_specific_humidity(p, q)
    return np.asarray(td.to("degC").magnitude, dtype=float)


def _height_km_to_pres_hpa(z_km: np.ndarray, *, p_sfc_hpa: float = 1000.0) -> np.ndarray:
    z_m = np.asarray(z_km, dtype=float) * 1000.0
    scale_h = 8500.0
    return p_sfc_hpa * np.exp(-z_m / scale_h)


def _tropoe_skewt_profile(
    tropoe_path: Path,
    hour_target: float,
    *,
    p_sfc_hpa: float,
    max_z_km: float = 3.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with Dataset(tropoe_path) as nc:
        hour = np.asarray(nc.variables["hour"][:], dtype=float)
        z_km = np.asarray(nc.variables["height"][:], dtype=float)
        idx = int(np.argmin(np.abs(hour - hour_target)))
        temp_c = np.asarray(nc.variables["temperature"][idx, :], dtype=float)
        q_gkg = np.asarray(nc.variables["waterVapor"][idx, :], dtype=float)
    pres = _height_km_to_pres_hpa(z_km, p_sfc_hpa=max(p_sfc_hpa, 850.0))
    dpt_c = _dewpoint_from_q_gkg(q_gkg, pres)
    ok = (
        np.isfinite(pres)
        & np.isfinite(temp_c)
        & np.isfinite(dpt_c)
        & (pres > 50.0)
        & (z_km <= max_z_km)
        & (q_gkg < 25.0)
    )
    order = np.argsort(pres[ok])[::-1]
    return pres[ok][order], temp_c[ok][order], dpt_c[ok][order]


def _setup_skewt_panel(
    fig: plt.Figure,
    subplot: tuple[int, int, int],
    *,
    p_top: float,
    xlim: tuple[float, float],
    zoom: bool,
    show_ylabel: bool,
    show_xlabel: bool,
) -> SkewT:
    """Create a MetPy Skew-T on a subplot tuple (not a pre-built Axes)."""
    skew = SkewT(fig, subplot=subplot, rotation=30)
    skew.plot_dry_adiabats(linewidths=0.7, colors="0.72", alpha=0.50)
    skew.plot_moist_adiabats(linewidths=0.7, colors="0.62", alpha=0.50)
    skew.plot_mixing_lines(linewidths=0.7, colors="0.78", alpha=0.85)
    skew.ax.set_ylim(1050, p_top)
    skew.ax.set_xlim(*xlim)
    if zoom:
        # Native Skew-T aspect shrinks the axes box when limits narrow instead of
        # magnifying; auto aspect fills the panel so the crop is actually zoomed.
        skew.ax.set_aspect("auto")
    if show_xlabel:
        skew.ax.set_xlabel("Temperature (°C)")
    else:
        skew.ax.set_xlabel("")
        skew.ax.tick_params(axis="x", labelbottom=False)
    if show_ylabel:
        skew.ax.set_ylabel("Pressure (hPa)")
    else:
        skew.ax.set_ylabel("")
    return skew


def _skewt_figsize(n_cols: int, n_rows: int = 2) -> tuple[float, float]:
    panel_h = SKEWT_PANEL_W_IN * SKEWT_PANEL_HW
    fig_w = SKEWT_LEFT_IN + n_cols * SKEWT_PANEL_W_IN + max(n_cols - 1, 0) * SKEWT_PANEL_GAP_IN + 0.2
    fig_h = (
        SKEWT_BOTTOM_IN
        + n_rows * panel_h
        + max(n_rows - 1, 0) * SKEWT_ROW_GAP_IN
        + SKEWT_TOP_IN
    )
    return fig_w, fig_h


def _layout_skewt_figure(fig: plt.Figure, n_cols: int, n_rows: int = 2) -> None:
    """Pack Skew-T axes in a grid using MetPy's native aspect (no distortion)."""
    panel_w = SKEWT_PANEL_W_IN
    panel_h = panel_w * SKEWT_PANEL_HW
    fig_w, fig_h = _skewt_figsize(n_cols, n_rows)
    fig.set_size_inches(fig_w, fig_h)

    w = panel_w / fig_w
    h = panel_h / fig_h
    g = SKEWT_PANEL_GAP_IN / fig_w
    l = SKEWT_LEFT_IN / fig_w
    row_step = (panel_h + SKEWT_ROW_GAP_IN) / fig_h
    b_bottom = SKEWT_BOTTOM_IN / fig_h

    for row in range(n_rows):
        for col in range(n_cols):
            idx = row * n_cols + col
            b = b_bottom + (n_rows - 1 - row) * row_step
            fig.axes[idx].set_position([l + col * (w + g), b, w, h])


def _skewt_legend_handles() -> list[Line2D]:
    return [
        Line2D([0], [0], color=T_COLOR, lw=2.0, ls="-", label="$T$"),
        Line2D([0], [0], color=TD_COLOR, lw=2.0, ls="-", label="$T_d$"),
        Line2D([0], [0], color="k", lw=2.0, ls="-", label="TROPoe"),
        Line2D([0], [0], color="k", lw=0.9, ls="--", label="RAOB"),
    ]


def _plot_skewt_profile(
    skew: SkewT,
    pres_hpa: np.ndarray,
    temp_c: np.ndarray,
    dpt_c: np.ndarray | None,
    *,
    ls: str,
    lw: float,
    alpha: float = 1.0,
) -> None:
    pres = np.asarray(pres_hpa, dtype=float)
    temp = np.asarray(temp_c, dtype=float)
    p = pres * units.hPa
    skew.plot(p, temp * units.degC, color=T_COLOR, lw=lw, ls=ls, alpha=alpha, zorder=5)
    if dpt_c is None:
        return
    dpt = np.asarray(dpt_c, dtype=float)
    skew.plot(
        p,
        dpt * units.degC,
        color=TD_COLOR,
        lw=max(lw - 0.25, 0.7),
        ls=ls,
        alpha=alpha,
        zorder=4,
    )


def plot_skewt_overlay(
    case: CaseSpec,
    tropoe_path: Path,
    sounding_paths: list[Path],
    output_path: Path,
    *,
    p_sfc_hpa: float = 1000.0,
) -> Path:
    n_cols = max(len(sounding_paths), 1)
    n_rows = 2
    fig = plt.figure(figsize=_skewt_figsize(n_cols, n_rows))
    row_specs = (
        {"p_top": SKEWT_P_TOP_FULL, "xlim": SKEWT_XLIM_FULL, "zoom": False},
        {"p_top": SKEWT_P_TOP_ZOOM, "xlim": SKEWT_XLIM_ZOOM, "zoom": True},
    )

    for row, spec in enumerate(row_specs):
        for j, snd_path in enumerate(sounding_paths):
            subplot_idx = row * n_cols + j + 1
            skew = _setup_skewt_panel(
                fig,
                (n_rows, n_cols, subplot_idx),
                p_top=spec["p_top"],
                xlim=spec["xlim"],
                zoom=spec["zoom"],
                show_ylabel=(j == 0),
                show_xlabel=(row == n_rows - 1),
            )
            launch_h = _parse_sounding_hour(snd_path)
            pres, temp, dpt = _load_raob_sounding(snd_path)
            _plot_skewt_profile(skew, pres, temp, dpt, ls="--", lw=0.9, alpha=0.85)
            tp, tt, td = _tropoe_skewt_profile(tropoe_path, launch_h, p_sfc_hpa=p_sfc_hpa)
            _plot_skewt_profile(skew, tp, tt, td, ls="-", lw=2.2)
            hh = int(launch_h)
            mm = int(round((launch_h - hh) * 60))
            skew.ax.set_title(f"Skew-T ({hh:02d}:{mm:02d} UTC)", fontsize=9, pad=TITLE_PAD)
            if row == 0 and j == 0:
                skew.ax.legend(
                    handles=_skewt_legend_handles(),
                    loc="upper right",
                    fontsize=6.5,
                    framealpha=0.92,
                    ncol=2,
                )

    _layout_skewt_figure(fig, n_cols, n_rows)
    for idx, ax in enumerate(fig.axes[: n_cols * n_rows]):
        col = idx % n_cols
        row = idx // n_cols
        if col > 0:
            ax.set_ylabel("")
            ax.tick_params(axis="y", labelleft=False, labelright=False)
            ax.yaxis.get_label().set_visible(False)
        if row < n_rows - 1:
            ax.set_xlabel("")
            ax.tick_params(axis="x", labelbottom=False)
    fig.suptitle(
        figure_suptitle(case, subtitle="Skew-T — TROPoe vs co-located RAOB"),
        fontsize=10,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def _interp_wind_to_prof(wind: WindoeData, prof_hour: np.ndarray, prof_z_km: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h = np.asarray(prof_hour, dtype=float)
    z = np.asarray(prof_z_km, dtype=float)
    fu = RegularGridInterpolator(
        (wind.hour, wind.height_km),
        wind.u_wind,
        bounds_error=False,
        fill_value=np.nan,
    )
    fv = RegularGridInterpolator(
        (wind.hour, wind.height_km),
        wind.v_wind,
        bounds_error=False,
        fill_value=np.nan,
    )
    tt, zz = np.meshgrid(h, z, indexing="ij")
    pts = np.column_stack([tt.ravel(), zz.ravel()])
    u = fu(pts).reshape(len(h), len(z))
    v = fv(pts).reshape(len(h), len(z))
    return u, v


def _rib_split_colormap(*, reverse: bool = False) -> LinearSegmentedColormap:
    """Blue = stable (high Ri_b), red = unstable (low Ri_b); optional reverse."""
    eps = 1e-4
    cmap = LinearSegmentedColormap.from_list(
        "rib_split",
        [
            (0.0, "#2166ac"),
            (0.5 - eps, "#d1e5f0"),
            (0.5 + eps, "#fddbc7"),
            (1.0, "#b2182b"),
        ],
        N=256,
    )
    return cmap.reversed() if reverse else cmap


def _rib_log_linear_band_norm(
    *,
    vmin: float = RIB_VMIN,
    threshold: float = RIB_THRESHOLD,
    vmax: float = RIB_VMAX,
    log_eps: float = RIB_LOG_EPS,
    linear_band: float = RIB_LINEAR_BAND,
    band_frac: float = RIB_BAND_CMAP_FRAC,
) -> FuncNorm:
    """Log spread away from Ri_c, with a narrow linear band at the threshold."""
    linear_lo = threshold - linear_band
    linear_hi = threshold + linear_band
    mid = 0.5
    n_lo = mid - band_frac / 2.0
    n_hi = mid + band_frac / 2.0
    linear_width = 2.0 * linear_band
    below_log_denom = np.log1p((linear_lo - vmin) / log_eps)
    above_log_denom = np.log1p((vmax - linear_hi) / log_eps)

    def forward(values: np.ndarray) -> np.ndarray:
        v = np.clip(np.asarray(values, dtype=float), vmin, vmax)
        out = np.empty_like(v)

        log_lo = v < linear_lo
        d = linear_lo - v[log_lo]
        out[log_lo] = n_lo * (1.0 - np.log1p(d / log_eps) / below_log_denom)

        lin = (v >= linear_lo) & (v <= linear_hi)
        out[lin] = n_lo + (n_hi - n_lo) * (v[lin] - linear_lo) / linear_width

        log_hi = v > linear_hi
        d = v[log_hi] - linear_hi
        out[log_hi] = n_hi + (1.0 - n_hi) * (np.log1p(d / log_eps) / above_log_denom)
        return out

    def inverse(normed: np.ndarray) -> np.ndarray:
        n = np.clip(np.asarray(normed, dtype=float), 0.0, 1.0)
        out = np.empty_like(n)

        log_lo = n < n_lo
        t = 1.0 - n[log_lo] / n_lo
        out[log_lo] = linear_lo - np.expm1(t * below_log_denom) * log_eps

        lin = (n >= n_lo) & (n <= n_hi)
        out[lin] = linear_lo + linear_width * (n[lin] - n_lo) / (n_hi - n_lo)

        log_hi = n > n_hi
        t = (n[log_hi] - n_hi) / (1.0 - n_hi)
        out[log_hi] = linear_hi + np.expm1(t * above_log_denom) * log_eps
        return out

    return FuncNorm((forward, inverse), vmin=vmin, vmax=vmax, clip=True)


def _rib_fill_levels(
    *,
    vmin: float = RIB_VMIN,
    threshold: float = RIB_THRESHOLD,
    vmax: float = RIB_VMAX,
    log_eps: float = RIB_LOG_EPS,
    linear_band: float = RIB_LINEAR_BAND,
    n_each: int = RIB_FILL_LEVELS_EACH,
    n_linear: int = RIB_FILL_LEVELS_LINEAR,
) -> np.ndarray:
    linear_lo = threshold - linear_band
    linear_hi = threshold + linear_band
    t = np.linspace(0.0, 1.0, n_each)
    below_log_denom = np.log1p((linear_lo - vmin) / log_eps)
    above_log_denom = np.log1p((vmax - linear_hi) / log_eps)
    below = linear_lo - np.expm1(t * below_log_denom) * log_eps
    linear = np.linspace(linear_lo, linear_hi, n_linear)
    above = linear_hi + np.expm1(t * above_log_denom) * log_eps
    return np.unique(np.concatenate([below, linear, above]))


def _style_rib_colorbar(cbar) -> None:
    """Fixed numeric ticks in the mapped core; endpoint text at the bar ends."""
    cbar.set_ticks(list(RIB_CBAR_NUMERIC))
    cbar.set_ticklabels([f"{t:g}" for t in RIB_CBAR_NUMERIC])
    cbar.ax.minorticks_off()
    cbar.ax.tick_params(axis="y", labelsize=8)
    cbar.ax.text(
        1.12,
        0.02,
        "very unstable",
        transform=cbar.ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=7,
    )
    cbar.ax.text(
        1.12,
        0.98,
        "very stable",
        transform=cbar.ax.transAxes,
        ha="left",
        va="top",
        fontsize=7,
    )


def _gradient_richardson(
    theta_v: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    z_km: np.ndarray,
) -> np.ndarray:
    z_m = np.asarray(z_km, dtype=float) * 1000.0
    dtheta = np.gradient(theta_v, z_m, axis=1)
    du = np.gradient(u, z_m, axis=1)
    dv = np.gradient(v, z_m, axis=1)
    shear2 = np.maximum(du * du + dv * dv, 1e-8)
    theta_safe = np.maximum(theta_v, 250.0)
    return (G / theta_safe) * dtheta / shear2


def _mask_period_hour_range(
    hour: np.ndarray,
    fields: list[np.ndarray],
    *,
    hour_start: float,
    hour_end: float,
) -> tuple[np.ndarray, list[np.ndarray]]:
    h = np.asarray(hour, dtype=float)
    mask = (h >= hour_start) & (h <= hour_end)
    return h[mask], [np.asarray(f, dtype=float)[mask] for f in fields]


def plot_rib_timeheight(
    case: CaseSpec,
    output_path: Path,
    *,
    period: la.PeriodAxis | None = None,
    hour_start: float | None = None,
    hour_end: float | None = None,
    tropoe_path: Path | None = None,
    dlfp_path: Path | None = None,
    wind: WindoeData | None = None,
    max_km: float = MAX_HEIGHT_KM,
    rib_threshold: float = RIB_THRESHOLD,
) -> Path:
    if period is not None:
        from case_gallery.extended_period import stitch_profiler_cross_section, stitch_wind

        prof = stitch_profiler_cross_section(case, period, max_km=PLOT_DATA_MAX_KM)
        wind, _ = stitch_wind(case, period)
        hour = np.asarray(prof.tropoe_hour, dtype=float)
        z = np.asarray(prof.tropoe_height_km, dtype=float)
        theta_v = np.asarray(prof.theta_v_k, dtype=float)
        if hour_start is not None and hour_end is not None:
            hour, (theta_v,) = _mask_period_hour_range(
                hour, [theta_v], hour_start=hour_start, hour_end=hour_end
            )
        z_ok = np.isfinite(z) & (z <= PLOT_DATA_MAX_KM + 1e-9)
        hour_ok = np.isfinite(hour)
        theta_v = theta_v[:, z_ok][hour_ok, :]
        hour = hour[hour_ok]
        z = z[z_ok]
        xlim = (
            (float(hour_start), float(hour_end))
            if hour_start is not None and hour_end is not None
            else (float(np.nanmin(hour)), float(np.nanmax(hour)))
        )
        rib_subtitle = _period_window_subtitle(
            float(hour_start), float(hour_end), case
        ).replace("CLAMPS surface meteogram · ", "Bulk Richardson number · ")
    else:
        if tropoe_path is None or dlfp_path is None or wind is None:
            raise ValueError("plot_rib_timeheight requires tropoe_path, dlfp_path, and wind")
        prof = build_profiler_cross_section(
            tropoe_path,
            dlfp_path,
            max_km=PLOT_DATA_MAX_KM,
            apply_tropoe_qc=False,
        )
        hour = np.asarray(prof.tropoe_hour, dtype=float)
        z = np.asarray(prof.tropoe_height_km, dtype=float)
        z_ok = np.isfinite(z) & (z <= PLOT_DATA_MAX_KM + 1e-9)
        hour_ok = np.isfinite(hour)
        theta_v = np.asarray(prof.theta_v_k, dtype=float)[:, z_ok][hour_ok, :]
        hour = hour[hour_ok]
        z = z[z_ok]
        xlim = (0.0, 24.0)
        rib_subtitle = "Bulk Richardson number time–height"

    u, v = _interp_wind_to_prof(wind, hour, z)
    rib = _gradient_richardson(theta_v, u, v, z)
    norm = _rib_log_linear_band_norm(threshold=rib_threshold)
    cmap = _rib_split_colormap(reverse=True)
    fill_levels = _rib_fill_levels(threshold=rib_threshold)
    rib_plot = np.clip(rib, RIB_VMIN, RIB_VMAX)

    fig, ax = plt.subplots(figsize=(12.0, 4.5), layout="constrained")
    mesh = ax.contourf(
        hour,
        z,
        rib_plot.T,
        levels=fill_levels,
        cmap=cmap,
        norm=norm,
        extend="both",
    )
    ax.contour(
        hour,
        z,
        rib.T,
        levels=[0.0],
        colors="k",
        linewidths=0.35,
        linestyles="--",
    )
    ax.contour(
        hour,
        z,
        rib.T,
        levels=[rib_threshold],
        colors="k",
        linewidths=0.55,
        linestyles="-",
    )
    ax.set_xlim(*xlim)
    ax.set_ylim(0.0, MAX_HEIGHT_KM)
    ax.set_xlabel("UTC time", labelpad=14)
    ax.set_ylabel("Height (km)")
    ax.set_title(r"Bulk Richardson number $Ri_b$", fontsize=9, pad=TITLE_PAD)
    if xlim[1] > 24.0:
        _mesonet_hour_ticks(
            ax,
            x_min=xlim[0],
            x_max=xlim[1],
            period_utc_labels=True,
            case_date=case.case_date,
        )
    else:
        _mesonet_hour_ticks(ax, x_min=xlim[0], x_max=xlim[1])
    cbar = fig.colorbar(mesh, ax=ax, fraction=0.046, pad=0.04, extend="both")
    cbar.set_label(r"$Ri_b$")
    _style_rib_colorbar(cbar)

    fig.suptitle(figure_suptitle(case, subtitle=rib_subtitle), fontsize=10)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def plot_clamps_met_meteogram(
    case: CaseSpec,
    met_path: Path | None,
    output_path: Path,
    *,
    hour_start: float = 0.0,
    hour_end: float = 24.0,
    period: la.PeriodAxis | None = None,
) -> Path:
    if period is not None:
        surf = stitch_clamps_met_surface(case, period)
        subtitle = _period_window_subtitle(hour_start, hour_end, case)
    else:
        if met_path is None:
            raise ValueError("met_path required when period is not set")
        surf = _load_clamps_mwr_surface(met_path)
        subtitle = "CLAMPS surface meteogram"
    hour = surf["hour"]
    temp_c = _interp_met_sparse(hour, surf["temp_c"])
    rh_pct = _interp_met_sparse(hour, surf["rh_pct"])
    dewpoint_c = _interp_met_sparse(hour, surf["dewpoint_c"])
    pres = _interp_met_sparse(hour, surf["pres"])
    fig, _ = _plot_surface_meteogram_panels(
        hour,
        surf["wspd"],
        surf["wdir"],
        pres,
        hour_start=hour_start,
        hour_end=hour_end,
        case_date=case.case_date if hour_end > 24.0 else None,
        pres_label="Surface pressure (hPa)",
        temp_c=temp_c,
        dewpoint_c=dewpoint_c,
        rh_pct=rh_pct,
        rain_rate=surf["rain_rate"],
        wdir_marker_min=10.0,
    )
    fig.suptitle(
        figure_suptitle(case, subtitle=subtitle),
        fontsize=10,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path
