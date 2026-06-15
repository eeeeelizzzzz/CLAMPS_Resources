#!/usr/bin/env python3
"""Case-gallery auxiliary figures (NLLJ; stable-BL; CI/waves; diurnal cycle)."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from matplotlib.ticker import FuncFormatter
from netCDF4 import Dataset

_CODE = Path(__file__).resolve().parent.parent
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

import plot_awaken_instrument_template  # noqa: F401,E402 — bootstrap pyc deps
from awaken_la_diagnostics import build_profiler_cross_section  # noqa: E402
from awaken_windoe import WindoeData  # noqa: E402
from case_gallery.case_lib import CaseSpec, figure_suptitle, find_case_files, get_case  # noqa: E402
from case_gallery.plot_limits import limits_for_case  # noqa: E402
from case_gallery.winds import load_case_winds  # noqa: E402
from paths import MPLCONFIG_DIR, ensure_output_dirs  # noqa: E402
from plot_awaken_instrument_template import (  # noqa: E402
    MAX_HEIGHT_KM,
    PLOT_DATA_MAX_KM,
    SAVE_KW,
    TITLE_PAD,
    la,
)

DLFP_SNR_THRESHOLD = 1.01
DLFP_MIN_GATE = 2  # skip lowest 2 gates (lidar blind-zone artifacts)
RAW_W_VMAX = 2.5
HODOGRAPH_HEIGHT_KM = 0.6
SNR_DB_VMIN = -30.0
SNR_DB_VMAX = -10.0
SNR_LINEAR_VMIN = 10.0 ** (SNR_DB_VMIN / 10.0)  # display floor for sub-threshold / negative SNR
SNR_LINEAR_VMAX = 10.0 ** (SNR_DB_VMAX / 10.0)  # −10 dB → linear SNR 0.1 → intensity 1.1
SNR_LINEAR_THRESHOLD = DLFP_SNR_THRESHOLD - 1.0  # intensity 1.01 → SNR 0.01 → −20 dB
SNR_DB_QC = 10.0 * np.log10(SNR_LINEAR_THRESHOLD)  # −20 dB
WD_COLOR = "0.45"
WS_COLOR = "0.15"
THETA_COLOR = "0.15"

PROFILE_TIME_STYLES: tuple[dict[str, float | str], ...] = (
    {"hour": 0.0, "label": "00Z", "lighten": 0.55, "lw": 1.2, "ls": "-"},
    {"hour": 6.0, "label": "06Z", "lighten": 0.0, "lw": 2.5, "ls": "-"},
    {"hour": 12.0, "label": "12Z", "lighten": 0.55, "lw": 1.2, "ls": "--"},
)


@dataclass(frozen=True)
class NlljAuxConfig:
    kind: str = "nllj"
    peak_hour_utc: float = 6.0
    hodograph_hour_end: float = 14.0
    hodograph_height_km: float = HODOGRAPH_HEIGHT_KM


@dataclass(frozen=True)
class StableBadDlAuxConfig:
    kind: str = "stable_bad_dl"
    snr_db_vmin: float = SNR_DB_VMIN
    snr_db_vmax: float = SNR_DB_VMAX
    metar_station: str = "KMSL"


@dataclass(frozen=True)
class CiWavesAuxConfig:
    kind: str = "ci_waves"
    w_hour_start: float = 11.0
    w_hour_end: float = 15.0
    w_vmax: float = 2.0
    metar_hour_start: float = 10.0
    metar_hour_end: float = 14.0
    surface_label: str = "CLAMPS MWR"


@dataclass(frozen=True)
class DiurnalAuxConfig:
    kind: str = "diurnal"
    met_hour_start: float = 0.0
    met_hour_end: float = 24.0
    period_plot_start_hour: float | None = None  # hours from case_date 00 UTC (may exceed 24)
    period_plot_end_hour: float | None = None
    rib_threshold: float = 0.25


@dataclass(frozen=True)
class SeaBreezeAuxConfig:
    kind: str = "sea_breeze"
    coastal_case_id: str = "sea_breeze_c2"
    inland_case_id: str = "sea_breeze_c1"
    hour_start: float = 17.0
    hour_end: float = 22.5
    rh_snr_hour_start: float = 4.0
    rh_snr_hour_end: float = 15.0
    bin_minutes: float = 5.0


AuxCaseConfig = (
    NlljAuxConfig
    | StableBadDlAuxConfig
    | CiWavesAuxConfig
    | DiurnalAuxConfig
    | SeaBreezeAuxConfig
)

AUX_CONFIG: dict[str, AuxCaseConfig] = {
    "nllj_c1": NlljAuxConfig(),
    "nllj_c2": NlljAuxConfig(),
    "stable_bad_dl_c1": StableBadDlAuxConfig(),
    "ci_c1": CiWavesAuxConfig(),
    "diurnal_c2": DiurnalAuxConfig(
        period_plot_start_hour=18.0,
        period_plot_end_hour=30.0,  # 06Z on case_date + 1 day
    ),
    "sea_breeze_c1": SeaBreezeAuxConfig(),
    "sea_breeze_c2": SeaBreezeAuxConfig(),
}


def _nearest_time_index(hour: np.ndarray, target: float) -> int:
    h = np.asarray(hour, dtype=float)
    return int(np.argmin(np.abs(h - target)))


def _height_mask(height_km: np.ndarray, max_km: float = MAX_HEIGHT_KM) -> np.ndarray:
    z = np.asarray(height_km, dtype=float)
    return np.isfinite(z) & (z >= 0.0) & (z <= max_km + 1e-9)


def _shade_color(base: str, *, lighten: float = 0.0, darken: float = 1.0) -> tuple[float, float, float]:
    rgb = np.array(mcolors.to_rgb(base), dtype=float)
    if lighten > 0.0:
        rgb = lighten * np.ones(3) + (1.0 - lighten) * rgb
    if darken < 1.0:
        rgb *= darken
    return tuple(rgb)


def _profile_at_hour(
    hour: np.ndarray,
    height_km: np.ndarray,
    field: np.ndarray,
    target_hour: float,
) -> tuple[np.ndarray, np.ndarray]:
    idx = _nearest_time_index(hour, target_hour)
    mask = _height_mask(height_km)
    return np.asarray(field[idx, mask], dtype=float), np.asarray(height_km[mask], dtype=float)


def _suptitle(case: CaseSpec, subtitle: str) -> str:
    return figure_suptitle(case, subtitle=subtitle)


def _find_metar_file(case: CaseSpec) -> Path:
    aux_dir = case.clamps_root / "aux"
    matches = sorted(aux_dir.glob("*metar*.csv"))
    if not matches:
        raise FileNotFoundError(f"No METAR CSV under {aux_dir}")
    return matches[0]


def _metar_float(value: str) -> float:
    text = str(value).strip()
    if not text or text.upper() in {"M", "T", "NA", "NAN"}:
        return np.nan
    try:
        return float(text)
    except ValueError:
        return np.nan


def _load_metar_csv(path: Path) -> dict[str, np.ndarray]:
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    if not rows:
        raise ValueError(f"No METAR rows in {path}")

    hour: list[float] = []
    temp_c: list[float] = []
    dewpoint_c: list[float] = []
    wspd: list[float] = []
    wgust: list[float] = []
    wdir: list[float] = []
    mslp: list[float] = []
    vsby: list[float] = []
    station = rows[0].get("station", "METAR")

    for row in rows:
        valid = datetime.strptime(row["valid"].strip(), "%Y-%m-%d %H:%M")
        hour.append(valid.hour + valid.minute / 60.0 + valid.second / 3600.0)

        tmpf = _metar_float(row["tmpf"])
        temp_c.append((tmpf - 32.0) * 5.0 / 9.0 if np.isfinite(tmpf) else np.nan)
        dwpf = _metar_float(row["dwpf"])
        dewpoint_c.append((dwpf - 32.0) * 5.0 / 9.0 if np.isfinite(dwpf) else np.nan)

        sknt = _metar_float(row["sknt"])
        wspd.append(sknt * 0.514444 if np.isfinite(sknt) else np.nan)
        gust_kt = _metar_float(row.get("gust", "M"))
        wgust.append(gust_kt * 0.514444 if np.isfinite(gust_kt) else np.nan)
        wdir.append(_metar_float(row["drct"]))

        pres = _metar_float(row["mslp"])
        if not np.isfinite(pres):
            alti = _metar_float(row["alti"])
            if np.isfinite(alti):
                pres = alti * 33.863886667
        mslp.append(pres)
        vsby.append(_metar_float(row["vsby"]))

    order = np.argsort(hour)
    arrays = {
        "station": np.array(station),
        "hour": np.asarray(hour, dtype=float)[order],
        "temp_c": np.asarray(temp_c, dtype=float)[order],
        "dewpoint_c": np.asarray(dewpoint_c, dtype=float)[order],
        "wspd": np.asarray(wspd, dtype=float)[order],
        "wgust": np.asarray(wgust, dtype=float)[order],
        "wdir": np.asarray(wdir, dtype=float)[order],
        "mslp": np.asarray(mslp, dtype=float)[order],
        "vsby": np.asarray(vsby, dtype=float)[order],
    }
    return arrays


def _intensity_to_snr(intensity: np.ndarray) -> np.ndarray:
    """Linear SNR from CLAMPS ``intensity`` (= 1 + SNR)."""
    return np.asarray(intensity, dtype=float) - 1.0


def _intensity_to_snr(intensity: np.ndarray) -> np.ndarray:
    """Linear SNR from CLAMPS ``intensity`` (= 1 + SNR)."""
    return np.asarray(intensity, dtype=float) - 1.0


def _snr_linear_to_db(snr_linear: np.ndarray, *, db_floor: float = SNR_DB_VMIN) -> np.ndarray:
    """Map linear SNR to dB; non-positive values clip to *db_floor*."""
    linear_floor = 10.0 ** (db_floor / 10.0)
    return 10.0 * np.log10(np.maximum(np.asarray(snr_linear, dtype=float), linear_floor))


def _snr_db_cbar_ticks(
    db_min: float,
    db_max: float,
    *,
    step: float | None = None,
) -> tuple[np.ndarray, list[str]]:
    """dB tick positions and labels for a linear-in-dB colorbar."""
    if step is None:
        step = 5.0 if (db_max - db_min) > 25.0 else 2.0
    start = np.ceil(db_min / step) * step
    db_vals = np.arange(start, db_max + 0.01, step)
    if db_vals.size == 0 or abs(db_vals[0] - db_min) > 0.25:
        db_vals = np.insert(db_vals, 0, db_min)
    if abs(db_vals[-1] - db_max) > 0.25:
        db_vals = np.append(db_vals, db_max)
    labels = [f"{v:.0f}" for v in db_vals]
    return db_vals, labels


def _make_snr_split_cmap(
    norm: mcolors.Normalize,
    threshold: float,
    *,
    n: int = 256,
    gray_lo: str = "#121212",
    gray_hi: str = "#cccccc",
    cmap_above: str = "viridis",
    reverse_gray: bool = True,
) -> mcolors.ListedColormap:
    """Grayscale below *threshold*, *cmap_above* at and above (sharp break at QC).

    With *reverse_gray*, light gray sits at vmin and dark gray at *threshold* so
    viridis purple can meet the gray band at the QC cutoff.
    """
    t_frac = float(np.clip(norm(threshold), 1e-6, 1.0 - 1e-6))
    n_below = max(2, int(round(n * t_frac)))
    n_above = max(2, n - n_below)
    lo = np.array(mcolors.to_rgb(gray_lo))
    hi = np.array(mcolors.to_rgb(gray_hi))
    ts = np.linspace(0.0, 1.0, n_below)
    if reverse_gray:
        below = [hi + t * (lo - hi) for t in ts]
    else:
        below = [lo + t * (hi - lo) for t in ts]
    vir = plt.get_cmap(cmap_above)
    above = [vir(t)[:3] for t in np.linspace(0.0, 1.0, n_above)]
    return mcolors.ListedColormap(below + above, name="snr_split")


def _axis_edges(centers: np.ndarray) -> np.ndarray:
    c = np.asarray(centers, dtype=float)
    if c.size == 0:
        return c
    if c.size == 1:
        half = 0.01
        return np.array([c[0] - half, c[0] + half], dtype=float)
    mid = 0.5 * (c[:-1] + c[1:])
    left = c[0] - (mid[0] - c[0])
    right = c[-1] + (c[-1] - mid[-1])
    return np.concatenate([[left], mid, [right]])


def _dlfp_snr_profiles(
    hour: np.ndarray,
    height_km: np.ndarray,
    field: np.ndarray,
    *,
    max_km: float = MAX_HEIGHT_KM,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return scan-based (t_edges, z_edges, snr[scan, gate]) for pcolormesh."""
    field = np.asarray(field[:, DLFP_MIN_GATE:], dtype=float)
    z = np.asarray(height_km[DLFP_MIN_GATE:], dtype=float)
    z_mask = _height_mask(z, max_km=max_km)
    field = field[:, z_mask]
    z = z[z_mask]
    hour = np.asarray(hour, dtype=float)

    order = np.argsort(hour)
    hour = hour[order]
    field = field[order, :]
    return _axis_edges(hour), _axis_edges(z), field


def plot_vertical_profiles_peak_jet(
    case: CaseSpec,
    wind: WindoeData,
    prof,
    *,
    tropoe_path: Path,
    output_path: Path,
    profile_times: tuple[dict[str, float | str], ...] = PROFILE_TIME_STYLES,
) -> Path:
    del tropoe_path
    limits = limits_for_case(case.id)
    z_w = np.asarray(wind.height_km[_height_mask(wind.height_km)], dtype=float)
    t_mask = _height_mask(prof.tropoe_height_km, max_km=PLOT_DATA_MAX_KM)
    z_t = np.asarray(prof.tropoe_height_km[t_mask], dtype=float)

    wind_vals: list[np.ndarray] = []
    fig, axes = plt.subplots(1, 3, figsize=(12.0, 5.0), layout="constrained")
    ax_speed = axes[0]
    ax_uv = axes[1]
    ax_theta = axes[2]
    ax_dir = ax_speed.twiny()

    for style in (profile_times[0], profile_times[2], profile_times[1]):
        target = float(style["hour"])
        lw = float(style["lw"])
        lighten = float(style["lighten"])
        ls = str(style["ls"])
        label = str(style["label"])

        ws, _ = _profile_at_hour(wind.hour, wind.height_km, wind.wind_speed, target)
        wd, _ = _profile_at_hour(wind.hour, wind.height_km, wind.wind_direction, target)
        u, _ = _profile_at_hour(wind.hour, wind.height_km, wind.u_wind, target)
        v, _ = _profile_at_hour(wind.hour, wind.height_km, wind.v_wind, target)

        t_idx = _nearest_time_index(prof.tropoe_hour, target)
        theta_v = np.asarray(prof.theta_v_k[t_idx, t_mask], dtype=float)

        wind_vals.extend([
            ws[np.isfinite(ws)],
            u[np.isfinite(u)],
            v[np.isfinite(v)],
        ])

        ws_c = _shade_color(WS_COLOR, lighten=lighten)
        wd_c = _shade_color(WD_COLOR, lighten=lighten)
        u_c = _shade_color(WS_COLOR, lighten=lighten)
        v_c = _shade_color(WD_COLOR, lighten=lighten)
        tv_c = _shade_color(THETA_COLOR, lighten=lighten)

        ax_speed.plot(ws, z_w, color=ws_c, lw=lw, ls=ls, label=label)
        ax_dir.plot(wd, z_w, color=wd_c, lw=lw, ls="-")
        ax_uv.plot(u, z_w, color=u_c, lw=lw, ls=ls)
        ax_uv.plot(v, z_w, color=v_c, lw=lw, ls=ls)

        ok = np.isfinite(theta_v) & np.isfinite(z_t)
        ax_theta.plot(theta_v[ok], z_t[ok], color=tv_c, lw=lw, ls=ls)

    wind_xpad = 1.0
    all_wind = np.concatenate(wind_vals)
    wind_xlim = (float(np.nanmin(all_wind) - wind_xpad), float(np.nanmax(all_wind) + wind_xpad))

    ax_speed.set_xlabel("Wind speed (m s$^{-1}$)")
    ax_speed.set_ylabel("Height (km)")
    ax_speed.set_xlim(wind_xlim)
    ax_speed.set_ylim(0.0, MAX_HEIGHT_KM)
    ax_speed.grid(True, alpha=0.25, ls=":")
    ax_speed.legend(loc="upper right", fontsize=7, framealpha=0.9, title="UTC")
    ax_dir.set_xlabel("Wind direction (°)", color=WD_COLOR)
    ax_dir.set_xlim(0.0, 360.0)
    ax_dir.set_xticks(range(0, 361, 45))
    ax_dir.tick_params(axis="x", colors=WD_COLOR)
    ax_dir.spines["top"].set_color(WD_COLOR)
    ax_speed.set_title("Wind speed & direction", fontsize=9, pad=TITLE_PAD)

    ax_uv.axvline(0.0, color="0.6", lw=0.8, ls=":")
    ax_uv.plot([], [], color=WS_COLOR, lw=2.0, label="$u$")
    ax_uv.plot([], [], color=WD_COLOR, lw=2.0, label="$v$")
    ax_uv.set_xlabel("Wind component (m s$^{-1}$)")
    ax_uv.set_ylabel("Height (km)")
    ax_uv.set_xlim(wind_xlim)
    ax_uv.set_ylim(0.0, MAX_HEIGHT_KM)
    ax_uv.legend(loc="lower right", fontsize=8, framealpha=0.9)
    ax_uv.grid(True, alpha=0.25, ls=":")
    ax_uv.set_title("$u$ and $v$ components", fontsize=9, pad=TITLE_PAD)

    ax_theta.set_xlabel(r"$\theta_v$ (K)")
    ax_theta.set_ylabel("Height (km)")
    ax_theta.set_ylim(0.0, MAX_HEIGHT_KM)
    ax_theta.set_xlim(*limits.theta_v)
    ax_theta.grid(True, alpha=0.25, ls=":")
    ax_theta.set_title("TROPoe", fontsize=9, pad=TITLE_PAD)

    fig.suptitle(
        _suptitle(case, "Vertical profiles (00, 06, 12 UTC)"),
        fontsize=10,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def _dlfp_w_grid(
    hour: np.ndarray,
    height_km: np.ndarray,
    w: np.ndarray,
    snr: np.ndarray,
    *,
    max_km: float = MAX_HEIGHT_KM,
    bin_seconds: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Place each stare scan in a time bin without temporal averaging."""
    w = np.asarray(w[:, DLFP_MIN_GATE:], dtype=float)
    snr = np.asarray(snr[:, DLFP_MIN_GATE:], dtype=float)
    z = np.asarray(height_km[DLFP_MIN_GATE:], dtype=float)
    z_mask = _height_mask(z, max_km=max_km)
    w = w[:, z_mask]
    snr = snr[:, z_mask]
    z = z[z_mask]
    hour = np.asarray(hour, dtype=float)

    w = np.where(np.abs(w) > 100.0, np.nan, w)
    w = np.where(snr >= DLFP_SNR_THRESHOLD, w, np.nan)

    order = np.argsort(hour)
    hour = hour[order]
    w = w[order, :]

    dt_h = bin_seconds / 3600.0
    n_t = int(np.ceil(24.0 / dt_h))
    grid = np.full((z.size, n_t), np.nan, dtype=float)
    for i, t in enumerate(hour):
        j = int(round(t / dt_h))
        if 0 <= j < n_t:
            grid[:, j] = w[i, :]

    t_centers = (np.arange(n_t, dtype=float) + 0.5) * dt_h
    return t_centers, z, grid


def _dlfp_w_profiles(
    hour: np.ndarray,
    height_km: np.ndarray,
    w: np.ndarray,
    snr: np.ndarray,
    *,
    hour_min: float | None = None,
    hour_max: float | None = None,
    max_km: float = MAX_HEIGHT_KM,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return scan-based (t_edges, z_edges, w[scan, gate]) for pcolormesh."""
    w = np.asarray(w[:, DLFP_MIN_GATE:], dtype=float)
    snr = np.asarray(snr[:, DLFP_MIN_GATE:], dtype=float)
    z = np.asarray(height_km[DLFP_MIN_GATE:], dtype=float)
    z_mask = _height_mask(z, max_km=max_km)
    w = w[:, z_mask]
    snr = snr[:, z_mask]
    z = z[z_mask]
    hour = np.asarray(hour, dtype=float)

    w = np.where(np.abs(w) > 100.0, np.nan, w)
    w = np.where(snr >= DLFP_SNR_THRESHOLD, w, np.nan)

    t_mask = np.ones(hour.shape, dtype=bool)
    if hour_min is not None:
        t_mask &= hour >= hour_min
    if hour_max is not None:
        t_mask &= hour <= hour_max
    hour = hour[t_mask]
    w = w[t_mask, :]

    order = np.argsort(hour)
    hour = hour[order]
    w = w[order, :]
    return _axis_edges(hour), _axis_edges(z), w


def plot_dlfp_w_zoom_timeheight(
    case: CaseSpec,
    dlfp_path: Path,
    output_path: Path,
    *,
    hour_start: float = 11.0,
    hour_end: float = 15.0,
    w_vmax: float = 2.0,
) -> Path:
    with Dataset(dlfp_path) as nc:
        hour = np.asarray(nc.variables["hour"][:], dtype=float)
        height_km = np.asarray(nc.variables["height"][:], dtype=float)
        w = np.asarray(nc.variables["velocity"][:], dtype=float)
        snr = np.asarray(nc.variables["intensity"][:], dtype=float)

    t_edges, z_edges, grid = _dlfp_w_profiles(
        hour,
        height_km,
        w,
        snr,
        hour_min=hour_start,
        hour_max=hour_end,
    )

    fig, ax = plt.subplots(figsize=(12.0, 4.5), layout="constrained")
    mesh = ax.pcolormesh(
        t_edges,
        z_edges,
        grid.T,
        cmap="seismic",
        vmin=-w_vmax,
        vmax=w_vmax,
        shading="flat",
        rasterized=True,
    )
    la._set_profile_ylim(ax, MAX_HEIGHT_KM)
    ax.set_xlim(hour_start, hour_end)
    ax.set_xlabel("UTC time", labelpad=10)
    ax.set_ylabel("Height (km)")
    ax.set_title(r"Vertical velocity $w$ (DL-FP stare)", fontsize=9, pad=TITLE_PAD)
    cbar = fig.colorbar(mesh, ax=ax, fraction=0.046, pad=0.025, extend="both")
    cbar.set_label(r"$w$ (m s$^{-1}$)")

    fig.suptitle(
        _suptitle(
            case,
            f"DL-FP $w$ ({hour_start:02.0f}:00–{hour_end:02.0f}:00 UTC)",
        ),
        fontsize=10,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def _find_clamps_mwr_file(case: CaseSpec) -> Path:
    aux_dir = case.clamps_root / "aux"
    matches = sorted(aux_dir.glob("*mwr*.cdf"))
    if not matches:
        raise FileNotFoundError(f"No CLAMPS MWR file under {aux_dir}")
    return matches[0]


def _dewpoint_from_rh(temp_c: np.ndarray, rh_pct: np.ndarray) -> np.ndarray:
    """Dewpoint (°C) from temperature and relative humidity (Magnus)."""
    temp_c = np.asarray(temp_c, dtype=float)
    rh_pct = np.asarray(rh_pct, dtype=float)
    es = 6.112 * np.exp(17.67 * temp_c / (temp_c + 243.5))
    e = (rh_pct / 100.0) * es
    return 243.5 * np.log(e / 6.112) / (17.67 - np.log(e / 6.112))


def _mask_clamps_sentinel(values: np.ndarray, *, bad: float = -999.0) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    return np.where(np.abs(arr - bad) < 0.01, np.nan, arr)


def _load_clamps_mwr_surface(path: Path) -> dict[str, np.ndarray]:
    with Dataset(path) as nc:
        temp_c = _mask_clamps_sentinel(nc.variables["sfc_temp"][:])
        rh_pct = _mask_clamps_sentinel(nc.variables["sfc_rh"][:])
        return {
            "hour": np.asarray(nc.variables["hour"][:], dtype=float),
            "pres": _mask_clamps_sentinel(nc.variables["sfc_pres"][:]),
            "wspd": _mask_clamps_sentinel(nc.variables["sfc_wspd"][:]),
            "wdir": _mask_clamps_sentinel(nc.variables["sfc_wdir"][:]),
            "temp_c": temp_c,
            "rh_pct": rh_pct,
            "dewpoint_c": _dewpoint_from_rh(temp_c, rh_pct),
            "rain_rate": _mask_clamps_sentinel(nc.variables["rain_rate"][:]),
        }


def _subsample_indices(n: int, *, n_markers: int) -> np.ndarray:
    if n <= 0:
        return np.array([], dtype=int)
    if n <= n_markers:
        return np.arange(n, dtype=int)
    return np.unique(np.linspace(0, n - 1, n_markers, dtype=int))


def _plot_surface_meteogram_panels(
    hour: np.ndarray,
    wspd: np.ndarray,
    wdir: np.ndarray,
    pres: np.ndarray,
    *,
    hour_start: float,
    hour_end: float,
    case_date: date | None = None,
    pres_label: str = "Surface pressure (hPa)",
    wdir_marker_min: float = 5.0,
    temp_c: np.ndarray | None = None,
    dewpoint_c: np.ndarray | None = None,
    rh_pct: np.ndarray | None = None,
    rain_rate: np.ndarray | None = None,
) -> tuple[plt.Figure, np.ndarray]:
    from matplotlib.lines import Line2D

    t_mask = (hour >= hour_start) & (hour <= hour_end)
    hour = np.asarray(hour[t_mask], dtype=float)
    wspd = np.asarray(wspd[t_mask], dtype=float)
    wdir = np.asarray(wdir[t_mask], dtype=float)
    pres = np.asarray(pres[t_mask], dtype=float)
    if temp_c is not None:
        temp_c = np.asarray(temp_c[t_mask], dtype=float)
    if dewpoint_c is not None:
        dewpoint_c = np.asarray(dewpoint_c[t_mask], dtype=float)
    if rh_pct is not None:
        rh_pct = np.asarray(rh_pct[t_mask], dtype=float)
    if rain_rate is not None:
        rain_rate = np.asarray(rain_rate[t_mask], dtype=float)

    cross_midnight = hour_end > 24.0
    fill_alpha = 0.7
    line_lw = 2.6
    thin_lw = 1.0
    n_markers = max(int((hour_end - hour_start) * 60.0 / wdir_marker_min) + 1, 2)
    mark_idx = _subsample_indices(hour.size, n_markers=n_markers)

    show_temp = temp_c is not None and dewpoint_c is not None
    n_rows = 3 if show_temp else 2
    height_ratios = [1.15, 1.0, 1.0] if show_temp else [1.0, 1.0]
    fig_h = 7.0 if show_temp else 5.0

    fig, axes = plt.subplots(
        n_rows,
        1,
        figsize=(12.0, fig_h),
        sharex=True,
        layout="constrained",
        gridspec_kw={"height_ratios": height_ratios},
    )
    if show_temp:
        ax_t, ax_wind, ax_pres = axes
    else:
        ax_wind, ax_pres = axes

    if show_temp:
        t_lo = float(np.nanmin(np.concatenate([temp_c, dewpoint_c])) - 2.0)
        ax_t.fill_between(
            hour,
            t_lo,
            dewpoint_c,
            color="#2d6a4f",
            alpha=fill_alpha,
            interpolate=True,
            linewidth=0,
            zorder=1,
            rasterized=True,
        )
        ax_t.fill_between(
            hour,
            dewpoint_c,
            temp_c,
            color="#d4a59a",
            alpha=fill_alpha,
            interpolate=True,
            linewidth=0,
            zorder=2,
            rasterized=True,
        )
        ax_t.plot(hour, temp_c, color="#8b1a1a", lw=line_lw, alpha=1.0, zorder=4, label="$T$")
        ax_t.plot(hour, dewpoint_c, color="#1b4332", lw=line_lw, alpha=1.0, zorder=4, label="$T_d$")
        ax_t.set_ylim(t_lo, float(np.nanmax(temp_c) + 1.5))
        ax_t.set_ylabel("Temperature (°C)")
        temp_legend = [
            Line2D([0], [0], color="#8b1a1a", lw=line_lw, label="$T$"),
            Line2D([0], [0], color="#1b4332", lw=line_lw, label="$T_d$"),
        ]
        if rh_pct is not None and np.any(np.isfinite(rh_pct)):
            ax_rh = ax_t.twinx()
            ax_rh.plot(hour, rh_pct, color="#5c4d7d", lw=thin_lw, alpha=0.95, zorder=3, rasterized=True)
            rh_lo = max(float(np.nanmin(rh_pct)) - 5.0, 0.0)
            ax_rh.set_ylim(rh_lo, min(float(np.nanmax(rh_pct)) + 5.0, 100.0))
            ax_rh.set_ylabel("RH (%)", color="0.45")
            ax_rh.tick_params(axis="y", colors="0.45")
            ax_rh.spines["right"].set_color("0.45")
            temp_legend.append(
                Line2D([0], [0], color="#5c4d7d", lw=thin_lw, label="RH"),
            )
        ax_t.legend(handles=temp_legend, loc="lower left", fontsize=7, framealpha=0.92)
        _mesonet_hour_ticks(
            ax_t,
            x_min=hour_start,
            x_max=hour_end,
            period_utc_labels=cross_midnight,
            case_date=case_date,
            show_tick_labels=False,
        )

    ax_wspd = ax_wind.twinx()
    ax_wind.set_zorder(2)
    ax_wspd.set_zorder(1)
    ax_wind.patch.set_visible(False)
    ax_wspd.fill_between(
        hour,
        0.0,
        wspd,
        color="#1f4e79",
        alpha=fill_alpha,
        interpolate=True,
        linewidth=0,
        zorder=1,
        rasterized=True,
    )
    ax_wspd.plot(hour, wspd, color="#204EA8", lw=thin_lw, alpha=1.0, zorder=3, rasterized=True)
    wdir_ok = np.isfinite(wdir[mark_idx]) & np.isfinite(hour[mark_idx])
    ax_wind.scatter(
        hour[mark_idx][wdir_ok],
        wdir[mark_idx][wdir_ok],
        s=28,
        facecolors="0.72",
        edgecolors="0.15",
        linewidths=0.9,
        zorder=4,
    )
    ax_wind.set_ylabel("Wind direction (°)")
    ax_wind.set_ylim(0.0, 360.0)
    ax_wind.set_yticks(range(0, 361, 45))
    wspd_max = float(np.nanmax(wspd)) if np.any(np.isfinite(wspd)) else 1.0
    ax_wspd.set_ylabel("Wind speed (m s$^{-1}$)")
    ax_wspd.set_ylim(0.0, max(wspd_max * 1.15, 1.0))
    ax_wind.legend(
        handles=[
            Line2D([0], [0], color="#204EA8", lw=thin_lw, label="Wind speed"),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="0.72",
                markeredgecolor="0.15",
                markeredgewidth=0.9,
                markersize=6,
                lw=0,
                label="Direction",
            ),
        ],
        loc="lower left",
        fontsize=7,
        framealpha=0.92,
    )
    _mesonet_hour_ticks(
        ax_wind,
        x_min=hour_start,
        x_max=hour_end,
        period_utc_labels=cross_midnight,
        case_date=case_date,
        show_tick_labels=False,
    )

    pres_ok = np.isfinite(pres)
    if np.any(pres_ok):
        pres_lo = float(np.floor(np.nanmin(pres) - 1.0))
        pres_hi = float(np.ceil(np.nanmax(pres) + 0.5))
        ax_pres.fill_between(
            hour,
            pres_lo,
            pres,
            color="#9c7a3c",
            alpha=fill_alpha,
            interpolate=True,
            linewidth=0,
            zorder=1,
            rasterized=True,
        )
        ax_pres.plot(hour, pres, color="#4a3728", lw=thin_lw, alpha=1.0, zorder=2, rasterized=True)
        ax_pres.set_ylim(pres_lo, pres_hi)
    ax_pres.set_ylabel(pres_label)
    ax_pres.set_xlabel("UTC time", labelpad=14 if cross_midnight else 10)
    pres_legend = [Line2D([0], [0], color="#4a3728", lw=thin_lw, label="Pressure")]
    if rain_rate is not None and np.any(np.isfinite(rain_rate)):
        ax_rain = ax_pres.twinx()
        rain_max = float(np.nanmax(rain_rate))
        ax_rain.fill_between(
            hour,
            0.0,
            rain_rate,
            color="#58A4B0",
            alpha=0.35,
            interpolate=True,
            linewidth=0,
            zorder=3,
            rasterized=True,
        )
        ax_rain.plot(
            hour,
            rain_rate,
            color="#2E6F7E",
            lw=thin_lw,
            alpha=1.0,
            zorder=4,
            rasterized=True,
        )
        ax_rain.set_ylim(0.0, max(rain_max * 1.2, 0.05))
        ax_rain.set_ylabel(r"Rain (mm h$^{-1}$)", color="0.45")
        ax_rain.tick_params(axis="y", colors="0.45")
        ax_rain.spines["right"].set_color("0.45")
        pres_legend.append(
            Line2D([0], [0], color="#2E6F7E", lw=thin_lw, label="Rain"),
        )
    ax_pres.legend(
        handles=pres_legend,
        loc="lower left",
        fontsize=7,
        framealpha=0.92,
    )
    _mesonet_hour_ticks(
        ax_pres,
        x_min=hour_start,
        x_max=hour_end,
        period_utc_labels=cross_midnight,
        case_date=case_date,
    )
    return fig, axes


def plot_clamps_surface_meteogram(
    case: CaseSpec,
    mwr_path: Path,
    output_path: Path,
    *,
    source_label: str = "CLAMPS MWR",
    hour_start: float = 10.0,
    hour_end: float = 18.0,
) -> Path:
    surf = _load_clamps_mwr_surface(mwr_path)
    fig, _ = _plot_surface_meteogram_panels(
        surf["hour"],
        surf["wspd"],
        surf["wdir"],
        surf["pres"],
        hour_start=hour_start,
        hour_end=hour_end,
        pres_label="Surface pressure (hPa)",
        temp_c=surf["temp_c"],
        dewpoint_c=surf["dewpoint_c"],
        rain_rate=surf["rain_rate"],
    )
    fig.suptitle(
        _suptitle(
            case,
            f"{source_label} surface meteogram ({hour_start:02.0f}:00–{hour_end:02.0f}:00 UTC)",
        ),
        fontsize=10,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def plot_surface_meteogram(
    case: CaseSpec,
    metar_path: Path,
    output_path: Path,
    *,
    station_label: str = "KPNC",
    hour_start: float = 10.0,
    hour_end: float = 18.0,
) -> Path:
    met = _load_metar_csv(metar_path)
    fig, _ = _plot_surface_meteogram_panels(
        met["hour"],
        met["wspd"],
        met["wdir"],
        met["mslp"],
        hour_start=hour_start,
        hour_end=hour_end,
        pres_label="MSLP (hPa)",
        wdir_marker_min=60.0,
    )
    fig.suptitle(
        _suptitle(
            case,
            f"{station_label} surface meteogram ({hour_start:02.0f}:00–{hour_end:02.0f}:00 UTC)",
        ),
        fontsize=10,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def plot_dlfp_snr_timeheight(
    case: CaseSpec,
    dlfp_path: Path,
    output_path: Path,
    *,
    snr_db_vmin: float = SNR_DB_VMIN,
    snr_db_vmax: float = SNR_DB_VMAX,
    split_cmap: bool = True,
) -> Path:
    with Dataset(dlfp_path) as nc:
        hour = np.asarray(nc.variables["hour"][:], dtype=float)
        height_km = np.asarray(nc.variables["height"][:], dtype=float)
        intensity = np.asarray(nc.variables["intensity"][:], dtype=float)

    snr = _intensity_to_snr(intensity)
    t_edges, z_edges, grid_lin = _dlfp_snr_profiles(hour, height_km, snr)
    grid = _snr_linear_to_db(grid_lin, db_floor=snr_db_vmin)

    snr_norm = Normalize(vmin=snr_db_vmin, vmax=snr_db_vmax)
    cmap: str | mcolors.Colormap = (
        _make_snr_split_cmap(snr_norm, SNR_DB_QC, cmap_above="viridis", reverse_gray=True)
        if split_cmap
        else "viridis"
    )

    fig, ax = plt.subplots(figsize=(12.0, 4.5), layout="constrained")
    mesh = ax.pcolormesh(
        t_edges,
        z_edges,
        grid.T,
        cmap=cmap,
        norm=snr_norm,
        shading="flat",
        rasterized=True,
    )
    la._set_profile_ylim(ax, MAX_HEIGHT_KM)
    ax.set_xlim(0.0, 24.0)
    ax.set_xlabel("UTC time", labelpad=10)
    ax.set_ylabel("Height (km)")
    ax.set_title("SNR (DL-FP)", fontsize=9, pad=TITLE_PAD)
    cbar = fig.colorbar(mesh, ax=ax, fraction=0.046, pad=0.025, extend="max")
    cbar.set_label("SNR (dB)")
    tick_db, tick_labels = _snr_db_cbar_ticks(snr_db_vmin, snr_db_vmax)
    cbar.set_ticks(tick_db)
    cbar.set_ticklabels(tick_labels)
    cbar.ax.axhline(
        SNR_DB_QC,
        color="white",
        ls="--",
        lw=1.2,
        zorder=5,
    )

    fig.suptitle(_suptitle(case, "Doppler lidar SNR time–height"), fontsize=10)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def _period_utc_hour_tick_label(period_hour: float, *, case_date: date | None = None) -> str:
    """Map case-midnight period hour to UTC clock label (18–23, 0 at midnight, 0–6 next day)."""
    h = int(round(period_hour))
    if case_date is not None:
        if h == 21:
            return f"21 UTC\n{case_date:%m/%d}"
        if h == 27:
            return f"03 UTC\n{(case_date + timedelta(days=1)):%m/%d}"
    if h >= 24:
        return str(h - 24)
    return str(h)


def _mesonet_hour_ticks(
    ax,
    *,
    x_min: float = 1.0,
    x_max: float = 24.0,
    period_utc_labels: bool = False,
    case_date: date | None = None,
    show_tick_labels: bool = True,
) -> None:
    ax.set_xlim(x_min, x_max)
    span = x_max - x_min
    if period_utc_labels and x_max > 24.0:
        step = 3 if span > 9.0 else 1
        start = int(np.ceil(x_min))
        end = int(np.floor(x_max))
        ticks = list(range(start, end + 1, step))
        ax.set_xticks(ticks)
        if show_tick_labels:
            ax.set_xticklabels(
                [_period_utc_hour_tick_label(t, case_date=case_date) for t in ticks],
                fontsize=8,
            )
        else:
            ax.tick_params(axis="x", labelbottom=False)
        ax.axvline(24.0, color="0.70", lw=0.9, ls=":", zorder=1)
        ax.grid(True, axis="x", color="0.82", lw=0.8, ls="-", zorder=0)
        return
    if span <= 6.0:
        step = 1
    else:
        step = 3
    start = int(np.ceil(x_min))
    end = int(np.floor(x_max))
    ax.set_xticks(list(range(start, end + 1, step)))
    ax.grid(True, axis="x", color="0.82", lw=0.8, ls="-", zorder=0)


def plot_metar_meteogram(
    case: CaseSpec,
    metar_path: Path,
    output_path: Path,
    *,
    station_label: str = "KMSL",
) -> Path:
    from matplotlib.lines import Line2D

    met = _load_metar_csv(metar_path)
    hour = met["hour"]
    temp_c = met["temp_c"]
    dewpoint_c = met["dewpoint_c"]
    wspd = met["wspd"]
    wgust = met["wgust"]
    wdir = met["wdir"]
    mslp = met["mslp"]
    vsby = met["vsby"]

    x_min = 1.0
    fill_alpha = 0.7
    line_lw = 2.6

    fig, axes = plt.subplots(
        3,
        1,
        figsize=(12.0, 7.0),
        sharex=True,
        layout="constrained",
        gridspec_kw={"height_ratios": [1.15, 1.0, 1.0]},
    )
    ax_t, ax_wind, ax_pres = axes

    # --- Temperature / dewpoint (Mesonet-style fills) ---
    t_lo = float(np.nanmin(np.concatenate([temp_c, dewpoint_c])) - 2.0)
    ax_t.fill_between(
        hour,
        t_lo,
        dewpoint_c,
        color="#2d6a4f",
        alpha=fill_alpha,
        interpolate=True,
        linewidth=0,
        zorder=1,
    )
    ax_t.fill_between(
        hour,
        dewpoint_c,
        temp_c,
        color="#d4a59a",
        alpha=fill_alpha,
        interpolate=True,
        linewidth=0,
        zorder=2,
    )
    ax_t.plot(hour, temp_c, color="#8b1a1a", lw=line_lw, alpha=1.0, zorder=4, label="$T$")
    ax_t.plot(hour, dewpoint_c, color="#1b4332", lw=line_lw, alpha=1.0, zorder=4, label="$T_d$")
    ax_t.set_ylim(t_lo, float(np.nanmax(temp_c) + 1.5))
    ax_t.set_ylabel("Temperature (°C)")
    ax_t.legend(loc="lower left", fontsize=7, framealpha=0.92)
    _mesonet_hour_ticks(ax_t, x_min=x_min)

    # --- Wind speed fill (+ gust if reported) / direction markers ---
    ax_wspd = ax_wind.twinx()
    ax_wind.set_zorder(2)
    ax_wspd.set_zorder(1)
    ax_wind.patch.set_visible(False)
    wspd_max = float(np.nanmax(wspd))
    gust_ok = np.isfinite(wgust) & (wgust > wspd)
    if np.any(gust_ok):
        ax_wspd.fill_between(
            hour,
            0.0,
            wspd,
            color="#1f4e79",
            alpha=fill_alpha,
            interpolate=True,
            linewidth=0,
            zorder=1,
        )
        ax_wspd.fill_between(
            hour,
            wspd,
            wgust,
            where=gust_ok,
            color="#85c1e9",
            alpha=fill_alpha,
            interpolate=True,
            linewidth=0,
            zorder=2,
        )
        ax_wspd.plot(hour, wgust, color="#2874a6", lw=line_lw, alpha=1.0, zorder=3)
        wspd_max = max(wspd_max, float(np.nanmax(wgust[gust_ok])))
    else:
        ax_wspd.fill_between(
            hour,
            0.0,
            wspd,
            color="#1f4e79",
            alpha=fill_alpha,
            interpolate=True,
            linewidth=0,
            zorder=1,
        )
    ax_wspd.plot(hour, wspd, color="#1a252f", lw=line_lw, alpha=1.0, zorder=3)
    wdir_ok = np.isfinite(hour) & np.isfinite(wdir)
    ax_wind.scatter(
        hour[wdir_ok],
        wdir[wdir_ok],
        s=28,
        facecolors="0.72",
        edgecolors="0.15",
        linewidths=0.9,
        zorder=4,
    )
    ax_wind.set_ylabel("Wind direction (°)")
    ax_wind.set_ylim(0.0, 360.0)
    ax_wind.set_yticks(range(0, 361, 45))
    ax_wspd.set_ylabel("Wind speed (m s$^{-1}$)")
    ax_wspd.set_ylim(0.0, max(wspd_max * 1.15, 1.0))
    ax_wind.legend(
        handles=[
            Line2D([0], [0], color="#1a252f", lw=line_lw, label="Wind speed"),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="0.72",
                markeredgecolor="0.15",
                markeredgewidth=0.9,
                markersize=6,
                lw=0,
                label="Direction",
            ),
        ],
        loc="lower left",
        fontsize=7,
        framealpha=0.92,
    )
    _mesonet_hour_ticks(ax_wind, x_min=x_min)

    # --- MSLP filled area + visibility markers ---
    ax_vis = ax_pres.twinx()
    p_lo = float(np.floor(np.nanmin(mslp) - 1.0))
    p_hi = float(np.ceil(np.nanmax(mslp) + 0.5))
    ax_pres.fill_between(
        hour,
        p_lo,
        mslp,
        color="#9c7a3c",
        alpha=fill_alpha,
        interpolate=True,
        linewidth=0,
        zorder=1,
    )
    ax_pres.plot(hour, mslp, color="#4a3728", lw=line_lw, alpha=1.0, zorder=2)
    ax_pres.set_ylim(p_lo, p_hi)
    ax_pres.set_ylabel("MSLP (hPa)")
    vsby_ok = np.isfinite(hour) & np.isfinite(vsby)
    ax_vis.scatter(
        hour[vsby_ok],
        vsby[vsby_ok],
        s=32,
        facecolors="0.72",
        edgecolors="0.25",
        linewidths=0.9,
        zorder=5,
    )
    ax_vis.set_ylim(0.0, 10.5)
    ax_vis.set_yticks(list(range(0, 11, 2)))
    ax_vis.set_ylabel("Visibility (SM)", color="0.45")
    ax_vis.tick_params(axis="y", colors="0.45")
    ax_vis.spines["right"].set_color("0.45")
    ax_pres.set_xlabel("UTC time", labelpad=10)
    ax_pres.legend(
        handles=[
            Line2D([0], [0], color="#4a3728", lw=line_lw, label="MSLP"),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="0.72",
                markeredgecolor="0.25",
                markeredgewidth=0.9,
                markersize=7,
                lw=0,
                label="Visibility",
            ),
        ],
        loc="lower left",
        fontsize=7,
        framealpha=0.92,
    )
    _mesonet_hour_ticks(ax_pres, x_min=x_min)

    fig.suptitle(
        _suptitle(
            case,
            f"{station_label} METAR meteogram (Muscle Shoals ASOS)",
        ),
        fontsize=10,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def plot_raw_w_timeheight(
    case: CaseSpec,
    dlfp_path: Path,
    output_path: Path,
) -> Path:
    with Dataset(dlfp_path) as nc:
        hour = np.asarray(nc.variables["hour"][:], dtype=float)
        height_km = np.asarray(nc.variables["height"][:], dtype=float)
        w = np.asarray(nc.variables["velocity"][:], dtype=float)
        snr = np.asarray(nc.variables["intensity"][:], dtype=float)

    t_centers, z, grid = _dlfp_w_grid(hour, height_km, w, snr)
    dt_h = float(t_centers[1] - t_centers[0]) if len(t_centers) > 1 else 1.0 / 3600.0
    extent = [
        float(t_centers[0] - 0.5 * dt_h),
        float(t_centers[-1] + 0.5 * dt_h),
        float(z[0]),
        float(min(z[-1], MAX_HEIGHT_KM)),
    ]

    fig, ax = plt.subplots(figsize=(12.0, 4.5), layout="constrained")
    im = ax.imshow(
        grid,
        origin="lower",
        aspect="auto",
        extent=extent,
        cmap="seismic",
        vmin=-RAW_W_VMAX,
        vmax=RAW_W_VMAX,
        interpolation="nearest",
        rasterized=True,
    )
    la._set_profile_ylim(ax, MAX_HEIGHT_KM)
    ax.set_xlim(0.0, 24.0)
    ax.set_xlabel("UTC time", labelpad=10)
    ax.set_ylabel("Height (km)")
    ax.set_title(r"Vertical velocity $w$ (DL-FP stare)", fontsize=9, pad=TITLE_PAD)
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.025, extend="both")
    cbar.set_label(r"$w$ (m s$^{-1}$)")

    fig.suptitle(_suptitle(case, "DL-FP vertical velocity"), fontsize=10)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def _utc_hour_cbar_fmt(value: float, _pos) -> str:
    return f"{int(round(value))}"


def plot_io_hodograph(
    case: CaseSpec,
    wind: WindoeData,
    *,
    height_km: float,
    hour_end: float,
    output_path: Path,
) -> Path:
    z_idx = int(np.argmin(np.abs(wind.height_km - height_km)))
    z_plot = float(wind.height_km[z_idx])
    hour_end_int = int(round(hour_end))

    t_mask = np.isfinite(wind.hour) & (wind.hour >= 0.0) & (wind.hour <= hour_end)
    hour = np.asarray(wind.hour[t_mask], dtype=float)
    u = np.asarray(wind.u_wind[t_mask, z_idx], dtype=float)
    v = np.asarray(wind.v_wind[t_mask, z_idx], dtype=float)
    ok = np.isfinite(hour) & np.isfinite(u) & np.isfinite(v)
    hour, u, v = hour[ok], u[ok], v[ok]
    order = np.argsort(hour)
    hour, u, v = hour[order], u[order], v[order]

    points = np.column_stack([u, v]).reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    seg_hour = 0.5 * (hour[:-1] + hour[1:])

    fig, ax = plt.subplots(figsize=(6.5, 6.0), layout="constrained")
    norm = Normalize(vmin=0.0, vmax=float(hour_end_int))
    lc = LineCollection(segments, cmap=plt.get_cmap("Blues"), norm=norm, linewidths=2.2)
    lc.set_array(seg_hour)
    ax.add_collection(lc)

    for h_mark in range(0, hour_end_int + 1):
        idx = int(np.argmin(np.abs(hour - h_mark)))
        ax.scatter(
            u[idx],
            v[idx],
            s=42,
            facecolors="white",
            edgecolors="0.2",
            linewidths=1.0,
            zorder=6,
        )
        ax.annotate(
            str(h_mark),
            (u[idx], v[idx]),
            textcoords="offset points",
            xytext=(5, 5),
            fontsize=7,
            color="0.15",
            zorder=7,
        )

    ax.axhline(0.0, color="0.75", lw=0.8, zorder=0)
    ax.axvline(0.0, color="0.75", lw=0.8, zorder=0)
    ax.set_aspect("equal", adjustable="box")

    pad = 2.0
    ok_lim = np.isfinite(u) & np.isfinite(v)
    ax.set_xlim(float(np.min(u[ok_lim]) - pad), float(np.max(u[ok_lim]) + pad))
    ax.set_ylim(float(np.min(v[ok_lim]) - pad), float(np.max(v[ok_lim]) + pad))
    ax.set_xlabel(r"Zonal wind $u$ (m s$^{-1}$)")
    ax.set_ylabel(r"Meridional wind $v$ (m s$^{-1}$)")
    ax.set_title(
        f"Inertial oscillation hodograph ({z_plot * 1000:.0f} m AGL)",
        fontsize=9,
        pad=TITLE_PAD,
    )
    cbar = fig.colorbar(lc, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("UTC hour")
    cbar.set_ticks(list(range(0, hour_end_int + 1, 2)))
    cbar.ax.yaxis.set_major_formatter(FuncFormatter(_utc_hour_cbar_fmt))

    fig.suptitle(
        _suptitle(case, f"Temporal hodograph (00:00–{hour_end_int}:00 UTC)"),
        fontsize=10,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def _plot_nllj_auxiliary(case_id: str, cfg: NlljAuxConfig, *, force: bool) -> list[Path]:
    case = get_case(case_id)
    files = find_case_files(case)
    wind, _ = load_case_winds(case, prefer="auto")
    prof = build_profiler_cross_section(
        files.tropoe, files.dlfp, max_km=PLOT_DATA_MAX_KM, apply_tropoe_qc=False
    )

    out_dir = case.figure_dir
    outputs = {
        "vertical_profiles": out_dir / "aux_vertical_profiles_peak_jet.png",
        "raw_w": out_dir / "aux_raw_w_timeheight.png",
        "hodograph": out_dir / "aux_io_hodograph.png",
    }
    if all(p.exists() for p in outputs.values()) and not force:
        print(f"{case_id}: auxiliary figures exist")
        return list(outputs.values())

    os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))
    saved: list[Path] = []
    saved.append(
        plot_vertical_profiles_peak_jet(
            case,
            wind,
            prof,
            tropoe_path=files.tropoe,
            output_path=outputs["vertical_profiles"],
        )
    )
    saved.append(plot_raw_w_timeheight(case, files.dlfp, outputs["raw_w"]))
    saved.append(
        plot_io_hodograph(
            case,
            wind,
            height_km=cfg.hodograph_height_km,
            hour_end=cfg.hodograph_hour_end,
            output_path=outputs["hodograph"],
        )
    )
    return saved


def _plot_stable_bad_dl_auxiliary(
    case_id: str,
    cfg: StableBadDlAuxConfig,
    *,
    force: bool,
) -> list[Path]:
    case = get_case(case_id)
    files = find_case_files(case)
    metar_path = _find_metar_file(case)

    out_dir = case.figure_dir
    outputs = {
        "snr": out_dir / "aux_dlfp_snr_timeheight.png",
        "metar": out_dir / "aux_metar_meteogram.png",
    }
    if all(p.exists() for p in outputs.values()) and not force:
        print(f"{case_id}: auxiliary figures exist")
        return list(outputs.values())

    os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))
    saved: list[Path] = []
    saved.append(
        plot_dlfp_snr_timeheight(
            case,
            files.dlfp,
            outputs["snr"],
            snr_db_vmin=cfg.snr_db_vmin,
            snr_db_vmax=cfg.snr_db_vmax,
        )
    )
    saved.append(
        plot_metar_meteogram(
            case,
            metar_path,
            outputs["metar"],
            station_label=cfg.metar_station,
        )
    )
    return saved


def _plot_ci_waves_auxiliary(
    case_id: str,
    cfg: CiWavesAuxConfig,
    *,
    force: bool,
) -> list[Path]:
    case = get_case(case_id)
    files = find_case_files(case)

    out_dir = case.figure_dir
    outputs = {
        "w_zoom": out_dir / "aux_dlfp_w_zoom_timeheight.png",
        "surface_met": out_dir / "aux_surface_meteogram.png",
    }

    mwr_path: Path | None = None
    try:
        mwr_path = _find_clamps_mwr_file(case)
    except FileNotFoundError:
        print(f"  skip surface meteogram: no CLAMPS MWR file under {case.clamps_root / 'aux'}")

    expected = [outputs["w_zoom"]] + ([outputs["surface_met"]] if mwr_path else [])
    if all(p.exists() for p in expected) and not force:
        print(f"{case_id}: auxiliary figures exist")
        return expected

    os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))
    saved: list[Path] = []
    saved.append(
        plot_dlfp_w_zoom_timeheight(
            case,
            files.dlfp,
            outputs["w_zoom"],
            hour_start=cfg.w_hour_start,
            hour_end=cfg.w_hour_end,
            w_vmax=cfg.w_vmax,
        )
    )
    if mwr_path is not None:
        saved.append(
            plot_clamps_surface_meteogram(
                case,
                mwr_path,
                outputs["surface_met"],
                source_label=cfg.surface_label,
                hour_start=cfg.metar_hour_start,
                hour_end=cfg.metar_hour_end,
            )
        )
    return saved


def _plot_diurnal_auxiliary(
    case_id: str,
    cfg: DiurnalAuxConfig,
    *,
    force: bool,
) -> list[Path]:
    from case_gallery.plot_diurnal_aux import (
        _find_clamps_met_file,
        _find_sounding_files,
        plot_clamps_met_meteogram,
        plot_rib_timeheight,
        plot_skewt_overlay,
    )

    case = get_case(case_id)
    files = find_case_files(case)
    wind, _ = load_case_winds(case, prefer="auto")

    out_dir = case.figure_dir
    outputs = {
        "surface_met": out_dir / "aux_surface_meteogram.png",
        "skewt": out_dir / "aux_skewt_overlay.png",
        "rib": out_dir / "aux_rib_timeheight.png",
    }

    met_path: Path | None = None
    sounding_paths: list[Path] = []
    try:
        met_path = _find_clamps_met_file(case)
    except FileNotFoundError:
        print(f"  skip surface meteogram: no CLAMPS met file under {case.clamps_root / 'aux'}")
    sounding_paths = _find_sounding_files(case)
    if not sounding_paths:
        print(f"  skip skew-T: no RAOB files under {case.clamps_root / 'aux'}")

    expected = [outputs["rib"]]
    uses_period_met = (
        cfg.period_plot_start_hour is not None and cfg.period_plot_end_hour is not None
    )
    if met_path is not None or uses_period_met:
        expected.append(outputs["surface_met"])
    if sounding_paths:
        expected.append(outputs["skewt"])
    if all(p.exists() for p in expected) and not force:
        print(f"{case_id}: auxiliary figures exist")
        return expected

    os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))
    saved: list[Path] = []
    if cfg.period_plot_start_hour is not None and cfg.period_plot_end_hour is not None:
        from case_gallery.extended_period import case_period

        period = case_period(case)
        h0 = cfg.period_plot_start_hour
        h1 = cfg.period_plot_end_hour
        saved.append(
            plot_clamps_met_meteogram(
                case,
                None,
                outputs["surface_met"],
                period=period,
                hour_start=h0,
                hour_end=h1,
            )
        )
    elif met_path is not None:
        saved.append(
            plot_clamps_met_meteogram(
                case,
                met_path,
                outputs["surface_met"],
                hour_start=cfg.met_hour_start,
                hour_end=cfg.met_hour_end,
            )
        )
    if sounding_paths:
        p_sfc = 1000.0
        met_for_sfc = met_path
        if met_for_sfc is None:
            try:
                met_for_sfc = _find_clamps_met_file(case)
            except FileNotFoundError:
                met_for_sfc = None
        if met_for_sfc is not None:
            surf = _load_clamps_mwr_surface(met_for_sfc)
            pres = surf["pres"]
            good = pres[(pres > 800.0) & (pres < 1100.0)]
            if good.size:
                p_sfc = float(np.nanmedian(good))
        saved.append(
            plot_skewt_overlay(
                case,
                files.tropoe,
                sounding_paths,
                outputs["skewt"],
                p_sfc_hpa=p_sfc,
            )
        )
    if cfg.period_plot_start_hour is not None and cfg.period_plot_end_hour is not None:
        from case_gallery.extended_period import case_period

        period = case_period(case)
        saved.append(
            plot_rib_timeheight(
                case,
                outputs["rib"],
                period=period,
                hour_start=cfg.period_plot_start_hour,
                hour_end=cfg.period_plot_end_hour,
                rib_threshold=cfg.rib_threshold,
            )
        )
    else:
        saved.append(
            plot_rib_timeheight(
                case,
                files.tropoe,
                files.dlfp,
                wind,
                outputs["rib"],
                rib_threshold=cfg.rib_threshold,
            )
        )
    return saved


def plot_auxiliary(case_id: str, *, force: bool = False) -> list[Path]:
    if case_id not in AUX_CONFIG:
        raise KeyError(f"No auxiliary plot config for case_id: {case_id}")

    ensure_output_dirs()
    os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))

    cfg = AUX_CONFIG[case_id]
    if cfg.kind == "nllj":
        return _plot_nllj_auxiliary(case_id, cfg, force=force)
    if cfg.kind == "stable_bad_dl":
        return _plot_stable_bad_dl_auxiliary(case_id, cfg, force=force)
    if cfg.kind == "ci_waves":
        return _plot_ci_waves_auxiliary(case_id, cfg, force=force)
    if cfg.kind == "diurnal":
        return _plot_diurnal_auxiliary(case_id, cfg, force=force)
    if cfg.kind == "sea_breeze":
        from case_gallery.plot_sea_breeze_aux import plot_seabreeze_auxiliary

        return plot_seabreeze_auxiliary(
            coastal_case_id=cfg.coastal_case_id,
            inland_case_id=cfg.inland_case_id,
            hour_start=cfg.hour_start,
            hour_end=cfg.hour_end,
            rh_snr_hour_start=cfg.rh_snr_hour_start,
            rh_snr_hour_end=cfg.rh_snr_hour_end,
            bin_minutes=cfg.bin_minutes,
            force=force,
        )
    raise ValueError(f"Unknown auxiliary config kind: {cfg.kind!r}")


def main() -> None:
    p = argparse.ArgumentParser(description="Plot gallery auxiliary figures")
    p.add_argument("case_id")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    paths_out = plot_auxiliary(args.case_id, force=args.force)
    for path in paths_out:
        print(f"Saved {path.resolve()}")


if __name__ == "__main__":
    main()
