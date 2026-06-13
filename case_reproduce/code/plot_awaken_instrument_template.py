"""Instrument-template 4-panel figures for the case gallery."""

from __future__ import annotations

import importlib.machinery
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize, SymLogNorm
from matplotlib.ticker import FuncFormatter
from netCDF4 import Dataset

from awaken_windoe import dlvad_snr_ceiling, smooth_snr_ceiling

_CODE = Path(__file__).resolve().parent
sys.path.insert(0, str(_CODE))
import paths  # noqa: E402

sys.modules["gallery_paths"] = importlib.machinery.SourcelessFileLoader(
    "gallery_paths", str(_CODE / "__pycache__" / "gallery_paths.cpython-312.pyc")
).load_module()
sys.modules["plot_splash_la_case"] = importlib.machinery.SourcelessFileLoader(
    "plot_splash_la_case", str(_CODE / "__pycache__" / "plot_splash_la_case.cpython-312.pyc")
).load_module()
import plot_splash_la_case as la  # noqa: E402
sys.modules["awaken_la_diagnostics"] = importlib.machinery.SourcelessFileLoader(
    "awaken_la_diagnostics", str(_CODE / "__pycache__" / "awaken_la_diagnostics.cpython-312.pyc")
).load_module()
from awaken_la_diagnostics import PblDiagnostics, ProfilerCrossSection  # noqa: E402
from awaken_windoe import WindoeData  # noqa: E402

# --- style constants (gallery defaults) ---
FIG_4PANEL_SIZE = (12.0, 13.0)
MAX_HEIGHT_KM = 2.0
PLOT_DATA_MAX_KM = 2.1
CLOUD_BASE_MAX_KM = 1.8
# TROPoe stores liquid water path as lwp (g m⁻²), not column LWC.
CLOUD_BASE_MIN_LWP_G_M2 = 5.0
THETA_V_CMAP = "RdYlBu_r"
THETA_V_VMIN, THETA_V_VMAX = 290.0, 320.0
Q_CMAP = "YlGnBu"
Q_VMIN_GKG, Q_VMAX_GKG = 3.0, 20.0
WSPD_CMAP = "viridis"
WSPD_VMIN, WSPD_VMAX = 0.0, 20.0
WVAR_CMAP = "summer"
# σ_w² symlog: log below 10⁻¹, linear 10⁻¹–10⁰, log above 10⁰ (shared across all cases)
WVAR_VMIN = 1e-3
WVAR_LINTHRESH = 0.1
WVAR_VMAX = 10.0
WVAR_CBAR_TICKS = [1e-2, 1e-1, 1.0, 10.0]
SIGMA_WSPD_CMAP = "magma_r"
SIGMA_WSPD_VMIN, SIGMA_WSPD_VMAX = 0.0, 3.0
DEFAULT_SIGMA_WSPD_MAX = 3.0
BARB_SIGMA_THRESHOLD = 2.5
DLVAD_SNR_THRESHOLD = 1.01
SIGMA_HIGH_ALPHA = 0.7
BARB_LENGTH = 5.5
BARB_STROKE_LW = 2.8
BARB_ALPHA_TRUSTED = 0.8
BARB_ALPHA_UNCERTAIN = 0.65
# Mask pcolormesh rows bracketing irregular WINDoe time gaps (nominal Δt ≈ 0.25 h).
WIND_MAX_TIME_GAP_H = 0.75
WVAR_MASK_VALUE_MAX = 5.0
PBLH_LINE_COLOR = "black"
PBLH_LINE_WIDTH = 2.0
PBLH_OUTLINE_COLOR = "white"
PBLH_OUTLINE_WIDTH = 3.5
PBLH_ZORDER_WIND = 18
TITLE_PAD = 4
CBAR_KW = {"fraction": 0.03, "pad": 0.025}
SAVE_KW = {"dpi": 150, "bbox_inches": "tight", "pad_inches": 0.2}


@dataclass
class WvarDisplay:
    field: np.ndarray
    norm: Normalize


def wvar_norm() -> SymLogNorm:
    """Shared σ_w² normalization for every gallery case."""
    return SymLogNorm(
        linthresh=WVAR_LINTHRESH,
        vmin=WVAR_VMIN,
        vmax=WVAR_VMAX,
        base=10,
        linscale=1.0,
    )


def tropoe_instrument_label(tropoe_path: Path | None) -> str | None:
    """Detect AERI / MWR / AERI+MWR from the TROPoe filename when unambiguous."""
    if tropoe_path is None:
        return None
    name = tropoe_path.name.lower()
    if "aeri_mwr" in name:
        return "AERI+MWR"
    if ".mwr." in name:
        return "MWR"
    if ".aeri." in name or "aerioe" in name:
        return "AERI"
    return None


def tropoe_panel_title(base: str, tropoe_path: Path | None) -> str:
    inst = tropoe_instrument_label(tropoe_path)
    if inst:
        return f"{base} (TROPoe / {inst})"
    return f"{base} (TROPoe)"


def wind_panel_title(wind_source: str) -> str:
    if wind_source == "WINDoe":
        return "Horizontal wind (WINDoe / DL-PPI)"
    if wind_source == "DLVAD":
        return "Horizontal wind (DL-VAD)"
    return f"Horizontal wind ({wind_source})"


def _height_edges_for_panel(
    height_km: np.ndarray,
    data_max_km: float = PLOT_DATA_MAX_KM,
) -> np.ndarray:
    z = np.asarray(height_km, dtype=float)
    z = z[np.isfinite(z) & (z <= data_max_km + 1e-9)]
    if z.size == 0:
        return np.array([0.0, data_max_km])
    return la.centers_to_edges(z)


def _bounded_cmap(name: str):
    cmap = plt.get_cmap(name).copy()
    cmap.set_under(cmap(0.0))
    cmap.set_over(cmap(1.0))
    return cmap


def _add_colorbar(
    fig,
    mappable,
    ax,
    *,
    label: str,
    ticks: list[float] | None = None,
    extend: str | None = None,
    tick_formatter=None,
) -> None:
    cbar = fig.colorbar(mappable, ax=ax, label=label, extend=extend, **CBAR_KW)
    if ticks:
        cbar.set_ticks(ticks)
    if tick_formatter is not None:
        cbar.formatter = tick_formatter
        cbar.update_ticks()


def _wvar_tick_formatter():
    def _fmt(value: float, _pos) -> str:
        if value <= 0:
            return ""
        exp = int(np.round(np.log10(value)))
        if abs(value - 10.0**exp) < max(1e-12, value * 1e-6):
            return rf"$10^{{{exp}}}$"
        return rf"${value:g}$"

    return FuncFormatter(_fmt)


def _overlay_pblh_km(ax, hour, pblh_m, *, zorder: int = 10) -> None:
    z = np.asarray(pblh_m, dtype=float) / 1000.0
    h = np.asarray(hour, dtype=float)
    ok = np.isfinite(h) & np.isfinite(z)
    if np.sum(ok) < 2:
        return
    ax.plot(
        h[ok], z[ok],
        color=PBLH_OUTLINE_COLOR, lw=PBLH_OUTLINE_WIDTH, ls="-",
        solid_capstyle="round", zorder=zorder - 1,
    )
    ax.plot(
        h[ok], z[ok],
        color=PBLH_LINE_COLOR, lw=PBLH_LINE_WIDTH, ls="-",
        solid_capstyle="round", zorder=zorder,
    )


def _panel_label(ax, letter: str) -> None:
    ax.text(
        0.02, 0.98, letter, transform=ax.transAxes,
        fontsize=12, fontweight="bold", va="top", ha="left",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.8, edgecolor="none"),
        zorder=20,
    )


def _overlay_snr_ceiling(ax, hour, ceiling_km) -> None:
    h = np.asarray(hour, dtype=float)
    z = np.asarray(ceiling_km, dtype=float)
    ok = np.isfinite(h) & np.isfinite(z)
    if np.sum(ok) < 2:
        return
    order = np.argsort(h[ok])
    ax.plot(
        h[ok][order], z[ok][order],
        color="0.55", ls="--", lw=1.4, alpha=1.0, zorder=11, label="DLVAD SNR ceiling",
    )


def _overlay_cloud_base_markers(ax, hour, cbh_km) -> None:
    if hour.size == 0:
        return
    ax.scatter(
        hour, cbh_km, s=28, facecolors="black", edgecolors="white",
        linewidths=0.9, zorder=12, clip_on=True,
    )


def _interp_ceiling(hour, snr_h, snr_z):
    h = np.asarray(hour, dtype=float)
    sh = np.asarray(snr_h, dtype=float)
    sz = np.asarray(snr_z, dtype=float)
    ok = np.isfinite(sh) & np.isfinite(sz)
    if np.sum(ok) < 2:
        return np.full_like(h, np.nan)
    order = np.argsort(sh[ok])
    return np.interp(h, sh[ok][order], sz[ok][order], left=np.nan, right=np.nan)


def _mask_wind_time_gaps(hour: np.ndarray, field: np.ndarray, *, max_gap_h: float) -> np.ndarray:
    """Drop fill on rows adjacent to large time steps so pcolormesh does not span data gaps."""
    h = np.asarray(hour, dtype=float)
    out = np.asarray(field, dtype=float).copy()
    if out.ndim != 2 or len(h) != out.shape[0]:
        return out
    for i in range(len(h)):
        if (i > 0 and (h[i] - h[i - 1]) > max_gap_h) or (
            i < len(h) - 1 and (h[i + 1] - h[i]) > max_gap_h
        ):
            out[i, :] = np.nan
    return out


def _plot_barbs_styled(
    ax,
    hour,
    height,
    u,
    v,
    *,
    color: str,
    outline: str,
    alpha: float = BARB_ALPHA_TRUSTED,
    zorder: int = 13,
) -> None:
    """Single barb glyph with a contrasting stroke outline (like PBLH / cloud-base markers)."""
    if not hour:
        return
    face = mcolors.to_rgba(color, alpha)
    edge = mcolors.to_rgba(outline, alpha)
    barbs = ax.barbs(
        hour, height, u, v,
        length=BARB_LENGTH,
        barbcolor=face,
        flagcolor=face,
        linewidth=1.0,
        zorder=zorder,
    )
    barbs.set_path_effects([
        pe.Stroke(linewidth=BARB_STROKE_LW, foreground=edge),
        pe.Normal(),
    ])


def _plot_wind_panel(ax, wind, snr_h, snr_z, *, sigma_wspd_max, wspd_lim):
    h_mask = wind.height_km <= MAX_HEIGHT_KM
    height_w = wind.height_km[h_mask]
    wspd = wind.wind_speed[:, h_mask]
    u = wind.u_wind[:, h_mask]
    v = wind.v_wind[:, h_mask]
    sigma = wind.sigma_wspd[:, h_mask]
    t_edges = la.centers_to_edges(wind.hour)
    z_edges = la.centers_to_edges(height_w)

    has_sigma = np.isfinite(sigma)
    high_sigma = has_sigma & (sigma > sigma_wspd_max)
    barb_high_sigma = has_sigma & (sigma > BARB_SIGMA_THRESHOLD)

    wvmin, wvmax = wspd_lim
    valid = np.isfinite(u) & np.isfinite(v) & np.isfinite(wspd)
    wspd_plot = _mask_wind_time_gaps(
        wind.hour, np.where(valid, wspd, np.nan), max_gap_h=WIND_MAX_TIME_GAP_H,
    )
    field = np.ma.masked_invalid(wspd_plot)
    pcm = ax.pcolormesh(
        t_edges, z_edges, field.T,
        cmap=_bounded_cmap(WSPD_CMAP), vmin=wvmin, vmax=wvmax, shading="flat",
    )

    if np.any(high_sigma):
        overlay_data = np.where(high_sigma & valid, wspd_plot, np.nan)
        overlay = np.ma.masked_invalid(overlay_data)
        ax.pcolormesh(
            t_edges, z_edges, overlay.T,
            cmap=WSPD_CMAP, vmin=wvmin, vmax=wvmax, shading="flat",
            alpha=SIGMA_HIGH_ALPHA, zorder=pcm.get_zorder() + 1,
        )

    step_t = max(1, wspd.shape[0] // 20)
    step_z = max(1, wspd.shape[1] // 10)
    low_h, low_z, low_u, low_v = [], [], [], []
    high_h, high_z, high_u, high_v = [], [], [], []
    for i in range(0, wspd.shape[0], step_t):
        for j in range(0, wspd.shape[1], step_z):
            if not (np.isfinite(u[i, j]) and np.isfinite(v[i, j]) and np.isfinite(wspd[i, j])):
                continue
            hod = float(wind.hour[i])
            hgt = float(height_w[j])
            if barb_high_sigma[i, j]:
                high_h.append(hod)
                high_z.append(hgt)
                high_u.append(u[i, j])
                high_v.append(v[i, j])
            else:
                low_h.append(hod)
                low_z.append(hgt)
                low_u.append(u[i, j])
                low_v.append(v[i, j])

    _plot_barbs_styled(
        ax, low_h, low_z, low_u, low_v,
        color="white", outline="black", alpha=BARB_ALPHA_TRUSTED, zorder=13,
    )
    _plot_barbs_styled(
        ax, high_h, high_z, high_u, high_v,
        color="black", outline="white", alpha=BARB_ALPHA_UNCERTAIN, zorder=15,
    )

    _overlay_snr_ceiling(ax, snr_h, snr_z)
    return pcm


def _mask_wvar_field(field: np.ndarray) -> np.ndarray:
    """Mask only very large σ_w² (noise spikes), not the CBL interior."""
    out = np.asarray(field, dtype=float).copy()
    out[(out > WVAR_MASK_VALUE_MAX)] = np.nan
    return out


def wvar_display(
    prof: ProfilerCrossSection,
    dlfp_path: Path | None = None,
    *,
    pbl: PblDiagnostics | None = None,
) -> WvarDisplay:
    del dlfp_path, pbl  # profiler cross-section already carries lenshow variance
    field = np.asarray(prof.w_variance, dtype=float)
    field = np.where(field > 0, field, np.nan)
    field = _mask_wvar_field(field)
    return WvarDisplay(field=field, norm=wvar_norm())


def load_cloud_base(tropoe_path: Path, *, max_km: float = CLOUD_BASE_MAX_KM) -> tuple[np.ndarray, np.ndarray]:
    with Dataset(tropoe_path) as nc:
        if "hour" not in nc.variables:
            return np.array([]), np.array([])
        hour = np.asarray(nc.variables["hour"][:], dtype=float)
        if "cbh" in nc.variables:
            cbh = np.asarray(nc.variables["cbh"][:], dtype=float)
        elif "cloud_base_height" in nc.variables:
            cbh = np.asarray(nc.variables["cloud_base_height"][:], dtype=float)
        else:
            return np.array([]), np.array([])
        lwp = (
            np.asarray(nc.variables["lwp"][:], dtype=float)
            if "lwp" in nc.variables
            else None
        )

    ok = np.isfinite(hour) & np.isfinite(cbh) & (cbh > 0) & (cbh <= max_km)
    if lwp is not None:
        ok &= np.isfinite(lwp) & (lwp > CLOUD_BASE_MIN_LWP_G_M2)
    if not np.any(ok):
        return np.array([]), np.array([])
    h, z = hour[ok], cbh[ok]
    order = np.argsort(h)
    return h[order], z[order]


def _configure_period_xaxes(axes, period: la.PeriodAxis, case_date: date) -> None:
    del case_date  # gallery uses 00–24 UTC window aligned with case_date
    for ax in axes:
        la.apply_period_xaxis(ax, period)
        ax.axvspan(0.0, 24.0, color="0.92", alpha=0.22, zorder=0)


def _finalize_figure(fig, output_path: Path, **kwargs) -> None:
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print("  saved instrument_template_4panel.png")


def plot_four_panel_template(
    prof: ProfilerCrossSection,
    wind: WindoeData,
    snr_ceiling_hour: np.ndarray,
    snr_ceiling_km: np.ndarray,
    pbl: PblDiagnostics,
    case_date: date,
    period: la.PeriodAxis,
    output_path: Path,
    *,
    sigma_wspd_max: float | None = 3.0,
    show_sigma_panel: bool = False,
    suptitle: str | None = None,
    theta_v_lim: tuple[float, float] | None = None,
    q_lim: tuple[float, float] | None = None,
    wspd_lim: tuple[float, float] | None = None,
    theta_v_cbar_ticks: list[float] | None = None,
    q_cbar_ticks: list[float] | None = None,
    wspd_cbar_ticks: list[float] | None = None,
    cloud_base_hour: np.ndarray | None = None,
    cloud_base_km: np.ndarray | None = None,
    wind_panel_title: str | None = None,
    tropoe_path: Path | None = None,
    dlfp_path: Path | None = None,
) -> None:
    tv_lim = theta_v_lim or (THETA_V_VMIN, THETA_V_VMAX)
    q_lim = q_lim or (Q_VMIN_GKG, Q_VMAX_GKG)
    w_lim = wspd_lim or (WSPD_VMIN, WSPD_VMAX)
    cb_h = np.asarray([] if cloud_base_hour is None else cloud_base_hour, dtype=float)
    cb_z = np.asarray([] if cloud_base_km is None else cloud_base_km, dtype=float)
    sigma_wspd_max = DEFAULT_SIGMA_WSPD_MAX if sigma_wspd_max is None else sigma_wspd_max

    fig, axes = plt.subplots(4, 1, figsize=FIG_4PANEL_SIZE, sharex=True, layout="constrained")
    theta_title = tropoe_panel_title(r"$\theta_v$", tropoe_path)
    q_title = tropoe_panel_title(r"$q$", tropoe_path)
    panels = [
        ("A", prof.theta_v_k, prof.tropoe_hour, prof.tropoe_height_km,
         r"$\theta_v$ (K)", tv_lim[0], tv_lim[1], THETA_V_CMAP, theta_title),
        ("B", prof.q_kgkg * 1000.0, prof.tropoe_hour, prof.tropoe_height_km,
         r"$q$ (g kg$^{-1}$)", q_lim[0], q_lim[1], Q_CMAP, q_title),
    ]

    time_axes = []
    for ax, (letter, field, hour, height_km, clabel, vmin, vmax, cmap, title) in zip(
        axes[:2], panels
    ):
        pcm = ax.pcolormesh(
            la.centers_to_edges(hour),
            _height_edges_for_panel(height_km),
            np.asarray(field).T,
            cmap=_bounded_cmap(cmap), vmin=vmin, vmax=vmax, shading="flat",
        )
        _overlay_pblh_km(ax, pbl.hour_decimal, pbl.pblh_m)
        _overlay_cloud_base_markers(ax, cb_h, cb_z)
        la._set_profile_ylim(ax, MAX_HEIGHT_KM)
        ax.set_ylabel("Height (km)")
        ax.set_title(title, fontsize=9, pad=TITLE_PAD)
        tick_kw = {}
        if letter == "A":
            tick_kw["ticks"] = theta_v_cbar_ticks
        elif letter == "B":
            tick_kw["ticks"] = q_cbar_ticks
        _add_colorbar(fig, pcm, ax, label=clabel, extend="both", **tick_kw)
        _panel_label(ax, letter)
        time_axes.append(ax)

    ax_c = axes[2]
    pcm_c = _plot_wind_panel(
        ax_c, wind, snr_ceiling_hour, snr_ceiling_km,
        sigma_wspd_max=sigma_wspd_max, wspd_lim=w_lim,
    )
    _overlay_pblh_km(ax_c, pbl.hour_decimal, pbl.pblh_m, zorder=PBLH_ZORDER_WIND)
    la._set_profile_ylim(ax_c, MAX_HEIGHT_KM)
    ax_c.set_ylabel("Height (km)")
    ax_c.set_title(wind_panel_title or "Horizontal wind (WINDoe)", fontsize=9, pad=TITLE_PAD)
    _add_colorbar(
        fig, pcm_c, ax_c, label="Wind speed (m s$^{-1}$)",
        ticks=wspd_cbar_ticks, extend="both",
    )
    _panel_label(ax_c, "C")
    time_axes.append(ax_c)

    ax_d = axes[3]
    if show_sigma_panel:
        h_mask = wind.height_km <= MAX_HEIGHT_KM
        pcm_d = ax_d.pcolormesh(
            la.centers_to_edges(wind.hour),
            la.centers_to_edges(wind.height_km[h_mask]),
            wind.sigma_wspd[:, h_mask].T,
            cmap=SIGMA_WSPD_CMAP, vmin=SIGMA_WSPD_VMIN, vmax=SIGMA_WSPD_VMAX, shading="flat",
        )
        ax_d.set_title("WINDoe $\\sigma_{|V|}$ (diagnostic)", fontsize=9, pad=TITLE_PAD)
        cbar_label = r"$\sigma_{|V|}$ (m s$^{-1}$)"
    else:
        wdisp = wvar_display(prof, dlfp_path, pbl=pbl)
        pcm_d = ax_d.pcolormesh(
            la.centers_to_edges(prof.w_variance_hour),
            _height_edges_for_panel(prof.w_variance_height_km),
            wdisp.field.T,
            cmap=WVAR_CMAP, norm=wdisp.norm, shading="flat",
        )
        ax_d.set_title(r"$\sigma_w^2$ (DL-FP)", fontsize=9, pad=TITLE_PAD)
        cbar_label = r"$\sigma_w^2$ (m$^2$ s$^{-2}$)"
        wvar_extend = "both"

    _overlay_pblh_km(ax_d, pbl.hour_decimal, pbl.pblh_m)
    la._set_profile_ylim(ax_d, MAX_HEIGHT_KM)
    ax_d.set_ylabel("Height (km)")
    wvar_tick_kw = {}
    if not show_sigma_panel:
        wvar_tick_kw = {
            "ticks": WVAR_CBAR_TICKS,
            "extend": wvar_extend,
            "tick_formatter": _wvar_tick_formatter(),
        }
    _add_colorbar(fig, pcm_d, ax_d, label=cbar_label, **wvar_tick_kw)
    _panel_label(ax_d, "D")
    time_axes.append(ax_d)

    _configure_period_xaxes(time_axes, period, case_date)
    axes[-1].set_xlabel("UTC time", labelpad=10)
    if suptitle:
        fig.suptitle(suptitle, fontsize=10)
    _finalize_figure(fig, output_path)
