#!/usr/bin/env python3
"""Standalone thermo layout demos: θᵥ+q contours both ways."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import uniform_filter1d

_CODE = Path(__file__).resolve().parent.parent
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

import plot_awaken_instrument_template  # noqa: F401,E402 — bootstrap pyc deps
from awaken_la_diagnostics import (  # noqa: E402
    CROSS_SECTION_MAX_KM,
    build_profiler_cross_section,
    load_fuzzy_pblh,
)
from plot_awaken_instrument_template import (  # noqa: E402
    MAX_HEIGHT_KM,
    PLOT_DATA_MAX_KM,
    Q_CMAP,
    THETA_V_CMAP,
    TITLE_PAD,
    _add_colorbar,
    _bounded_cmap,
    _height_edges_for_panel,
    _overlay_cloud_base_markers,
    _overlay_pblh_km,
    la,
    load_cloud_base,
)
from case_gallery.case_lib import find_case_files, find_pbl_file, get_case  # noqa: E402
from case_gallery.plot_limits import limits_for_case, q_ticks, theta_v_ticks  # noqa: E402
from paths import MPLCONFIG_DIR, OUTPUT_ROOT  # noqa: E402

DEMO_CASES = ("sharp_grad_c2", "nllj_c1", "deep_cbl_c2")
SMOOTH_WINDOW = 7
OUT_DIR = OUTPUT_ROOT / "case_gallery" / "figures_examples" / "theta_v_q_contours"


def _day_period(case_date: date) -> la.PeriodAxis:
    start = datetime(case_date.year, case_date.month, case_date.day, tzinfo=timezone.utc)
    return la.PeriodAxis(start=start, end=start + timedelta(hours=24))


def _q_contour_levels(q_min: float, q_max: float) -> list[float]:
    start = max(3.0, q_min + 1.0)
    return [float(v) for v in np.arange(start, q_max + 0.1, 3.0) if v < q_max]


def _theta_v_contour_levels(tv_min: float, tv_max: float) -> list[float]:
    start = int(5 * np.ceil(tv_min / 5.0))
    return [float(t) for t in range(start, int(tv_max) + 1, 5) if tv_min <= t <= tv_max]


def _smooth_time(field: np.ndarray, window: int = SMOOTH_WINDOW) -> np.ndarray:
    out = np.array(field, dtype=float, copy=True)
    if out.shape[0] < window:
        return out
    for j in range(out.shape[1]):
        col = out[:, j]
        ok = np.isfinite(col)
        if np.sum(ok) < window:
            continue
        filled = np.interp(np.arange(len(col)), np.flatnonzero(ok), col[ok])
        sm = uniform_filter1d(filled, size=window, mode="nearest")
        out[:, j] = np.where(ok, sm, np.nan)
    return out


def _add_contours(ax, hour, height, field, levels, *, color="0.15") -> None:
    h_mask = np.isfinite(height) & (height <= PLOT_DATA_MAX_KM + 1e-9)
    h_plot = height[h_mask]
    if not levels or h_plot.size < 2:
        return
    cs = ax.contour(
        hour,
        h_plot,
        field[:, h_mask].T,
        levels=levels,
        colors=color,
        linewidths=0.9,
        alpha=0.85,
    )
    ax.clabel(cs, cs.levels, inline=True, fontsize=7, fmt="%g")


def _decorate_thermo_ax(ax, period, pbl, cb_h, cb_z) -> None:
    _overlay_pblh_km(ax, pbl.hour_decimal, pbl.pblh_m)
    _overlay_cloud_base_markers(ax, cb_h, cb_z)
    la._set_profile_ylim(ax, MAX_HEIGHT_KM)
    la.apply_period_xaxis(ax, period)
    ax.axvspan(0.0, 24.0, color="0.92", alpha=0.22, zorder=0)
    ax.set_ylabel("Height (km)")


def plot_case(case_id: str, *, force: bool = False) -> tuple[Path, Path]:
    case = get_case(case_id)
    files = find_case_files(case)
    pbl = load_fuzzy_pblh(find_pbl_file(case))
    limits = limits_for_case(case_id)
    prof = build_profiler_cross_section(
        files.tropoe, files.dlfp, max_km=CROSS_SECTION_MAX_KM, apply_tropoe_qc=False
    )
    period = _day_period(case.case_date)
    cb_h, cb_z = load_cloud_base(files.tropoe)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_tv = OUT_DIR / f"{case_id}_theta_v_q_contours.png"
    out_q = OUT_DIR / f"{case_id}_q_theta_v_contours.png"
    if out_tv.exists() and out_q.exists() and not force:
        print(f"{case_id}: exists")
        return out_tv, out_q

    hour = np.asarray(prof.tropoe_hour, dtype=float)
    height = np.asarray(prof.tropoe_height_km, dtype=float)
    theta_v = np.asarray(prof.theta_v_k, dtype=float)
    q_gkg = np.asarray(prof.q_kgkg, dtype=float) * 1000.0
    q_smooth = _smooth_time(q_gkg)
    tv_smooth = _smooth_time(theta_v)
    q_levels = _q_contour_levels(*limits.q_gkg)
    tv_levels = _theta_v_contour_levels(*limits.theta_v)

    # --- θᵥ shaded + q contours ---
    fig, ax = plt.subplots(figsize=(12.0, 4.5), layout="constrained")
    pcm = ax.pcolormesh(
        la.centers_to_edges(hour),
        _height_edges_for_panel(height),
        theta_v.T,
        cmap=_bounded_cmap(THETA_V_CMAP),
        vmin=limits.theta_v[0],
        vmax=limits.theta_v[1],
        shading="flat",
    )
    _add_contours(ax, hour, height, q_smooth, q_levels)
    _decorate_thermo_ax(ax, period, pbl, cb_h, cb_z)
    ax.set_xlabel("UTC time", labelpad=10)
    ax.set_title(
        rf"$\theta_v$ (shaded) + smoothed $q$ contours (g kg$^{{-1}}$) — {case_id} ({case.case_date})",
        fontsize=10,
        pad=TITLE_PAD,
    )
    _add_colorbar(
        fig, pcm, ax, label=r"$\theta_v$ (K)",
        ticks=theta_v_ticks(*limits.theta_v), extend="both",
    )
    fig.savefig(out_tv, dpi=150, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    print(f"Saved {out_tv}")

    # --- q shaded + θᵥ contours ---
    fig, ax = plt.subplots(figsize=(12.0, 4.5), layout="constrained")
    pcm = ax.pcolormesh(
        la.centers_to_edges(hour),
        _height_edges_for_panel(height),
        q_gkg.T,
        cmap=_bounded_cmap(Q_CMAP),
        vmin=limits.q_gkg[0],
        vmax=limits.q_gkg[1],
        shading="flat",
    )
    _add_contours(ax, hour, height, tv_smooth, tv_levels)
    _decorate_thermo_ax(ax, period, pbl, cb_h, cb_z)
    ax.set_xlabel("UTC time", labelpad=10)
    ax.set_title(
        rf"$q$ (shaded) + smoothed $\theta_v$ contours (K) — {case_id} ({case.case_date})",
        fontsize=10,
        pad=TITLE_PAD,
    )
    _add_colorbar(
        fig, pcm, ax, label=r"$q$ (g kg$^{-1}$)",
        ticks=q_ticks(*limits.q_gkg), extend="both",
    )
    fig.savefig(out_q, dpi=150, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    print(f"Saved {out_q}")
    return out_tv, out_q


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", action="append", help=f"Default: {', '.join(DEMO_CASES)}")
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)
    os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))
    for case_id in args.case or list(DEMO_CASES):
        plot_case(case_id, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
