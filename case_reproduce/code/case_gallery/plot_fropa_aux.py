"""Frontal-passage auxiliary figures — surface meteogram and thermal/turbulence profiles."""

from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from netCDF4 import Dataset

from awaken_la_diagnostics import build_profiler_cross_section
from awaken_windoe import WindoeData
from case_gallery.case_lib import CaseSpec, CaseFiles, figure_suptitle, find_case_files, get_case
from case_gallery.plot_diurnal_aux import _interp_met_sparse
from case_gallery.plot_limits import limits_for_case, theta_v_ticks
from paths import PROJECT_ROOT
from plot_awaken_instrument_template import SAVE_KW, TITLE_PAD

from case_gallery.plot_auxiliary import (  # noqa: E402
    WD_COLOR,
    _height_mask,
    _nearest_time_index,
)

MET_HOUR_START = 6.0
MET_HOUR_END = 15.0
PROFILE_MAX_KM = 1.0
SIGMA_W_MIN_KM = 0.075
FROPA_PROFILE_TIMES: tuple[dict[str, float | str], ...] = (
    {"hour": 3.0, "label": "03Z"},
    {"hour": 6.0, "label": "06Z"},
    {"hour": 9.25, "label": "09:15Z"},
    {"hour": 12.0, "label": "12Z"},
)
THETA_COLOR = "0.15"
MESONET_MISSING = -995.0


def _aux_search_roots(case: CaseSpec) -> tuple[Path, ...]:
    roots: list[Path] = []
    for path in (case.clamps_root / "aux", case.clamps_root):
        if path.is_dir():
            roots.append(path)
    data_aux = PROJECT_ROOT / "data" / case.id / "aux"
    if data_aux.is_dir():
        roots.append(data_aux)
    return tuple(roots)


def _find_ok_mesonet_file(case: CaseSpec) -> Path | None:
    ymd = case.case_date.strftime("%Y%m%d")
    patterns = (f"*{ymd}*.mts", "*nrmn*.mts", "*.mts")
    for root in _aux_search_roots(case):
        for pattern in patterns:
            matches = sorted(root.glob(pattern))
            if matches:
                return matches[-1]
    return None


def _mts_float(token: str) -> float:
    try:
        value = float(token)
    except ValueError:
        return np.nan
    if value <= MESONET_MISSING + 1.0:
        return np.nan
    return value


def _load_ok_mesonet_mts(path: Path) -> dict[str, np.ndarray]:
    """Load Oklahoma Mesonet 5-minute surface archive (.mts)."""
    from case_gallery.plot_auxiliary import _dewpoint_from_rh

    minutes: list[float] = []
    temp_c: list[float] = []
    rh_pct: list[float] = []
    pres: list[float] = []
    wspd: list[float] = []
    wdir: list[float] = []
    rain: list[float] = []

    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("!") or line.startswith("STID"):
                continue
            parts = line.split()
            if len(parts) < 13 or parts[0] != "NRMN":
                continue
            minutes.append(_mts_float(parts[2]))
            rh_pct.append(_mts_float(parts[3]))
            temp_c.append(_mts_float(parts[4]))
            wspd.append(_mts_float(parts[5]))
            wdir.append(_mts_float(parts[7]))
            rain.append(_mts_float(parts[11]))
            pres.append(_mts_float(parts[12]))

    if not minutes:
        raise ValueError(f"No NRMN rows parsed from {path}")

    hour = np.asarray(minutes, dtype=float) / 60.0
    temp_c_arr = np.asarray(temp_c, dtype=float)
    rh_arr = np.asarray(rh_pct, dtype=float)
    order = np.argsort(hour)
    return {
        "hour": hour[order],
        "temp_c": temp_c_arr[order],
        "rh_pct": rh_arr[order],
        "dewpoint_c": _dewpoint_from_rh(temp_c_arr[order], rh_arr[order]),
        "pres": np.asarray(pres, dtype=float)[order],
        "wspd": np.asarray(wspd, dtype=float)[order],
        "wdir": np.asarray(wdir, dtype=float)[order],
        "rain_rate": np.asarray(rain, dtype=float)[order],
    }


def _find_fropa_mwr_file(case: CaseSpec) -> Path | None:
    """CLAMPS MWR tower file in aux/ or case root (optional)."""
    ymd = case.case_date.strftime("%Y%m%d")
    for root in _aux_search_roots(case):
        for pattern in ("*met*.cdf", "*mwr*a1*.cdf", "*mwr*a0*.cdf", "*mwr*.cdf"):
            matches = sorted(p for p in root.glob(pattern) if ymd in p.name)
            if matches:
                return matches[-1]
    return None


def _load_surface_from_tropoe_windoe(tropoe_path: Path, wind: WindoeData) -> dict[str, np.ndarray]:
    """Surface met from lowest TROPoe gate + lowest WINDoe gate (no MWR tower file)."""
    from case_gallery.plot_auxiliary import _dewpoint_from_rh

    with Dataset(tropoe_path) as nc:
        hour = np.asarray(nc.variables["hour"][:], dtype=float)
        temp_c = np.asarray(nc.variables["temperature"][:, 0], dtype=float)
        pres = np.asarray(nc.variables["pressure"][:, 0], dtype=float)
        q_gkg = np.asarray(nc.variables["waterVapor"][:, 0], dtype=float)

    q_kg = q_gkg / 1000.0
    e = q_kg * pres / (0.622 + q_kg)
    es = 6.112 * np.exp(17.67 * temp_c / (temp_c + 243.5))
    rh_pct = np.clip(100.0 * e / es, 0.0, 100.0)
    dewpoint_c = _dewpoint_from_rh(temp_c, rh_pct)

    gate = int(np.argmin(wind.height_km))
    u_sfc = np.interp(hour, wind.hour, wind.u_wind[:, gate], left=np.nan, right=np.nan)
    v_sfc = np.interp(hour, wind.hour, wind.v_wind[:, gate], left=np.nan, right=np.nan)
    wspd = np.hypot(u_sfc, v_sfc)
    wdir = (np.rad2deg(np.arctan2(-u_sfc, -v_sfc)) + 360.0) % 360.0

    return {
        "hour": hour,
        "pres": pres,
        "temp_c": temp_c,
        "rh_pct": rh_pct,
        "dewpoint_c": dewpoint_c,
        "wspd": wspd,
        "wdir": wdir,
        "rain_rate": np.full(hour.shape, np.nan, dtype=float),
    }


def _load_fropa_surface(
    case: CaseSpec,
    files: CaseFiles,
    wind: WindoeData,
) -> tuple[dict[str, np.ndarray], str]:
    from case_gallery.plot_auxiliary import _load_clamps_mwr_surface

    mesonet_path = _find_ok_mesonet_file(case)
    if mesonet_path is not None:
        return _load_ok_mesonet_mts(mesonet_path), "OK Mesonet NRMN"

    mwr_path = _find_fropa_mwr_file(case)
    if mwr_path is not None:
        return _load_clamps_mwr_surface(mwr_path), "CLAMPS MWR tower"

    print("  no Mesonet/MWR in aux — using TROPoe lowest gate + WINDoe surface wind")
    return _load_surface_from_tropoe_windoe(files.tropoe, wind), "TROPoe + WINDoe surface"


def _find_radar_image(case: CaseSpec) -> Path | None:
    patterns = ("*88D*.png", "*KTLX*.png", "*radar*.png")
    for root in _aux_search_roots(case) + (case.figure_dir,):
        if not root.is_dir():
            continue
        matches: list[Path] = []
        for pattern in patterns:
            matches.extend(sorted(root.glob(pattern)))
        if matches:
            return matches[0]
    return None


def sync_radar_gallery_image(case: CaseSpec, gallery_images_dir: Path) -> Path | None:
    src = _find_radar_image(case)
    if src is None:
        return None
    gallery_images_dir.mkdir(parents=True, exist_ok=True)
    dst = gallery_images_dir / f"{case.id}_{src.name}"
    if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
        shutil.copy2(src, dst)
    return dst


def sync_aux_gallery_images(
    case: CaseSpec,
    gallery_images_dir: Path,
    figure_paths: list[Path],
) -> list[Path]:
    gallery_images_dir.mkdir(parents=True, exist_ok=True)
    synced: list[Path] = []
    for src in figure_paths:
        if not src.is_file():
            continue
        dst = gallery_images_dir / f"{case.id}_{src.name}"
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            shutil.copy2(src, dst)
        synced.append(dst)
    return synced


def _panel_time_inset(ax, label: str) -> None:
    ax.text(
        0.97,
        0.97,
        label,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        bbox={
            "boxstyle": "round,pad=0.25",
            "facecolor": "white",
            "edgecolor": "0.75",
            "alpha": 0.92,
            "linewidth": 0.6,
        },
        zorder=10,
    )


def plot_fropa_front_theta_sigma_profiles(
    case: CaseSpec,
    prof,
    output_path: Path,
    *,
    profile_times: tuple[dict[str, float | str], ...] = FROPA_PROFILE_TIMES,
    max_km: float = PROFILE_MAX_KM,
    sigma_min_km: float = SIGMA_W_MIN_KM,
) -> Path:
    limits = limits_for_case(case.id)
    t_mask = _height_mask(prof.tropoe_height_km, max_km=max_km)
    z_theta = np.asarray(prof.tropoe_height_km[t_mask], dtype=float)

    w_mask = (
        np.isfinite(prof.w_variance_height_km)
        & (prof.w_variance_height_km >= sigma_min_km - 1e-9)
        & (prof.w_variance_height_km <= max_km + 1e-9)
    )
    z_sigma = np.asarray(prof.w_variance_height_km[w_mask], dtype=float)

    sigma_vals: list[np.ndarray] = []
    for style in profile_times:
        target = float(style["hour"])
        w_idx = _nearest_time_index(prof.w_variance_hour, target)
        sigma_w2 = np.asarray(prof.w_variance[w_idx, w_mask], dtype=float)
        sigma_vals.append(sigma_w2[np.isfinite(sigma_w2)])

    all_sigma = np.concatenate(sigma_vals) if sigma_vals else np.array([0.0])
    sigma_xmax = float(np.nanpercentile(all_sigma, 98))
    sigma_xmax = max(sigma_xmax * 1.08, 0.05)

    fig, axes = plt.subplots(
        1,
        len(profile_times),
        figsize=(6.5, 5.5),
        layout="constrained",
        sharey=True,
    )
    if len(profile_times) == 1:
        axes = [axes]

    for ax, style in zip(axes, profile_times):
        target = float(style["hour"])
        label = str(style["label"])

        t_idx = _nearest_time_index(prof.tropoe_hour, target)
        theta_v = np.asarray(prof.theta_v_k[t_idx, t_mask], dtype=float)
        w_idx = _nearest_time_index(prof.w_variance_hour, target)
        sigma_w2 = np.asarray(prof.w_variance[w_idx, w_mask], dtype=float)

        ok_theta = np.isfinite(theta_v) & np.isfinite(z_theta)
        ok_sigma = np.isfinite(sigma_w2) & np.isfinite(z_sigma)

        ax.plot(theta_v[ok_theta], z_theta[ok_theta], color=THETA_COLOR, lw=1.8)
        ax_sigma = ax.twiny()
        ax_sigma.plot(sigma_w2[ok_sigma], z_sigma[ok_sigma], color=WD_COLOR, lw=1.8)

        ax.set_xlim(*limits.theta_v)
        ax.set_xticks(theta_v_ticks(*limits.theta_v))
        ax.set_xlabel(r"$\theta_v$ (K)", fontsize=8)
        ax.grid(True, alpha=0.25, ls=":")
        _panel_time_inset(ax, label)

        ax_sigma.set_xlim(0.0, sigma_xmax)
        ax_sigma.set_xlabel(r"$\sigma_w^2$ (m$^2$ s$^{-2}$)", color=WD_COLOR, labelpad=6, fontsize=8)
        ax_sigma.tick_params(axis="x", colors=WD_COLOR, labelsize=7)
        ax_sigma.spines["top"].set_color(WD_COLOR)

    axes[0].set_ylabel("Height (km)")
    for ax in axes:
        ax.set_ylim(0.0, max_km)
        ax.tick_params(labelsize=7)

    fig.suptitle(
        f"{case.title} · {case.project} CLAMPS{case.platform[-1]}\n"
        f"{case.case_date.isoformat()}",
        fontsize=10,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def plot_fropa_surface_meteogram(
    case: CaseSpec,
    surf: dict[str, np.ndarray],
    output_path: Path,
    *,
    hour_start: float = MET_HOUR_START,
    hour_end: float = MET_HOUR_END,
    source_label: str = "CLAMPS surface",
) -> Path:
    from case_gallery.plot_auxiliary import _plot_surface_meteogram_panels

    hour = surf["hour"]
    fig, _ = _plot_surface_meteogram_panels(
        hour,
        surf["wspd"],
        surf["wdir"],
        _interp_met_sparse(hour, surf["pres"]),
        hour_start=hour_start,
        hour_end=hour_end,
        pres_label="Surface pressure (hPa)",
        temp_c=_interp_met_sparse(hour, surf["temp_c"]),
        dewpoint_c=_interp_met_sparse(hour, surf["dewpoint_c"]),
        rh_pct=_interp_met_sparse(hour, surf["rh_pct"]),
        rain_rate=surf["rain_rate"],
        wdir_marker_min=10.0,
    )
    fig.suptitle(
        figure_suptitle(
            case,
            subtitle=(
                f"Frontal surface signature ({hour_start:.0f}:00–{hour_end:.0f} UTC); "
                f"{source_label}"
            ),
        ),
        fontsize=10,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def plot_fropa_auxiliary(
    case_id: str = "fropa_c2",
    *,
    met_hour_start: float = MET_HOUR_START,
    met_hour_end: float = MET_HOUR_END,
    front_hour_start: float = MET_HOUR_START,
    front_hour_end: float = MET_HOUR_END,
    force: bool = False,
    gallery_images_dir: Path | None = None,
) -> list[Path]:
    del front_hour_start, front_hour_end
    import os

    from case_gallery.plot_auxiliary import MPLCONFIG_DIR
    from case_gallery.winds import load_case_winds

    case = get_case(case_id)
    files = find_case_files(case)
    wind, _ = load_case_winds(case, prefer="auto")
    prof = build_profiler_cross_section(
        files.tropoe, files.dlfp, max_km=PROFILE_MAX_KM + 0.1, apply_tropoe_qc=False
    )

    out_dir = case.figure_dir
    outputs = {
        "surface_met": out_dir / "aux_surface_meteogram.png",
        "front_profiles": out_dir / "aux_front_theta_sigma_profiles.png",
    }
    expected = list(outputs.values())

    if all(p.exists() for p in expected) and not force:
        print(f"{case_id}: auxiliary figures exist")
        saved = list(expected)
    else:
        os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))
        saved: list[Path] = []

        surf, surf_label = _load_fropa_surface(case, files, wind)

        if force or not outputs["front_profiles"].exists():
            saved.append(
                plot_fropa_front_theta_sigma_profiles(
                    case,
                    prof,
                    outputs["front_profiles"],
                )
            )
        else:
            saved.append(outputs["front_profiles"])

        if force or not outputs["surface_met"].exists():
            saved.append(
                plot_fropa_surface_meteogram(
                    case,
                    surf,
                    outputs["surface_met"],
                    hour_start=met_hour_start,
                    hour_end=met_hour_end,
                    source_label=surf_label,
                )
            )
        else:
            saved.append(outputs["surface_met"])

    if gallery_images_dir is not None:
        for dst in sync_aux_gallery_images(case, gallery_images_dir, saved):
            print(f"  synced {dst.name}")
        radar_dst = sync_radar_gallery_image(case, gallery_images_dir)
        if radar_dst is not None:
            print(f"  synced radar {radar_dst.name}")

    return saved
