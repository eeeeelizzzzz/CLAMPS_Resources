"""Deep CBL auxiliary figures — surface meteogram and midday θ_v / q profiles."""

from __future__ import annotations

from pathlib import Path

import matplotlib.cm as cm
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize

from awaken_la_diagnostics import build_profiler_cross_section
from case_gallery.case_lib import CaseSpec, figure_suptitle, find_case_files, get_case
from case_gallery.plot_diurnal_aux import (  # noqa: E402
    _find_clamps_met_file,
    plot_clamps_met_meteogram,
)
from case_gallery.plot_limits import limits_for_case
from plot_awaken_instrument_template import SAVE_KW, TITLE_PAD

from case_gallery.plot_auxiliary import (  # noqa: E402
    _height_mask,
    _nearest_time_index,
)

PROFILE_HOUR_START = 12.0
PROFILE_HOUR_END = 24.0  # 00 UTC end of case day
THETA_V_XLIM = (302.0, 320.0)
PROFILE_LINEWIDTH = 1.3


def _hourly_profile_hours(start: float = PROFILE_HOUR_START, end: float = PROFILE_HOUR_END) -> np.ndarray:
    return np.arange(int(start), int(end) + 1, dtype=float)


def plot_theta_v_q_profiles(
    case: CaseSpec,
    prof,
    output_path: Path,
    *,
    hour_start: float = PROFILE_HOUR_START,
    hour_end: float = PROFILE_HOUR_END,
    max_km: float = 4.0,
    theta_v_xlim: tuple[float, float] = THETA_V_XLIM,
) -> Path:
    limits = limits_for_case(case.id)
    t_mask = _height_mask(prof.tropoe_height_km, max_km=max_km)
    z = np.asarray(prof.tropoe_height_km[t_mask], dtype=float)
    profile_hours = _hourly_profile_hours(hour_start, hour_end)
    cmap = cm.Greys_r
    norm = Normalize(vmin=hour_start, vmax=hour_end)

    fig, (ax_tv, ax_q) = plt.subplots(1, 2, figsize=(9.0, 5.2), layout="constrained")

    for hour in profile_hours:
        color = cmap(norm(hour))
        t_idx = _nearest_time_index(prof.tropoe_hour, hour)
        theta_v = np.asarray(prof.theta_v_k[t_idx, t_mask], dtype=float)
        q_gkg = np.asarray(prof.q_kgkg[t_idx, t_mask], dtype=float) * 1000.0

        ok_tv = np.isfinite(theta_v) & np.isfinite(z)
        ok_q = np.isfinite(q_gkg) & np.isfinite(z)
        ax_tv.plot(theta_v[ok_tv], z[ok_tv], color=color, lw=PROFILE_LINEWIDTH)
        ax_q.plot(q_gkg[ok_q], z[ok_q], color=color, lw=PROFILE_LINEWIDTH)

    ax_tv.set_xlabel(r"$\theta_v$ (K)")
    ax_tv.set_ylabel("Height (km)")
    ax_tv.set_xlim(*theta_v_xlim)
    ax_tv.set_ylim(0.0, max_km)
    ax_tv.grid(True, alpha=0.25, ls=":")
    ax_tv.set_title(r"$\theta_v$", fontsize=9, pad=TITLE_PAD)

    ax_q.set_xlabel(r"$q$ (g kg$^{-1}$)")
    ax_q.set_ylabel("Height (km)")
    ax_q.set_xlim(*limits.q_gkg)
    ax_q.set_ylim(0.0, max_km)
    ax_q.grid(True, alpha=0.25, ls=":")
    ax_q.set_title(r"$q$", fontsize=9, pad=TITLE_PAD)

    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=[ax_tv, ax_q], orientation="horizontal", fraction=0.05, pad=0.06)
    cbar.set_label("UTC hour")
    cbar.set_ticks([12, 15, 18, 21, 24])
    cbar.set_ticklabels(["12", "15", "18", "21", "00"])

    fig.suptitle(
        figure_suptitle(
            case,
            subtitle="Hourly boundary-layer evolution (12–00 UTC)",
        ),
        fontsize=10,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, **SAVE_KW)
    plt.close(fig)
    print(f"  saved {output_path.name}")
    return output_path


def plot_deep_cbl_auxiliary(
    case_id: str = "deep_cbl_c2",
    *,
    met_hour_start: float = 0.0,
    met_hour_end: float = 24.0,
    profile_max_km: float = 4.0,
    force: bool = False,
) -> list[Path]:
    import os

    from case_gallery.plot_auxiliary import MPLCONFIG_DIR

    case = get_case(case_id)
    files = find_case_files(case)
    prof = build_profiler_cross_section(
        files.tropoe, files.dlfp, max_km=profile_max_km + 0.1, apply_tropoe_qc=False
    )

    out_dir = case.figure_dir
    outputs = {
        "surface_met": out_dir / "aux_surface_meteogram.png",
        "profiles": out_dir / "aux_theta_v_q_profiles.png",
    }

    met_path: Path | None = None
    try:
        met_path = _find_clamps_met_file(case)
    except FileNotFoundError:
        print(f"  skip surface meteogram: no CLAMPS met file under {case.clamps_root / 'aux'}")

    expected = [outputs["profiles"]]
    if met_path is not None:
        expected.append(outputs["surface_met"])

    if all(p.exists() for p in expected) and not force:
        print(f"{case_id}: auxiliary figures exist")
        return expected

    os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))
    saved: list[Path] = []

    if force or not outputs["profiles"].exists():
        saved.append(
            plot_theta_v_q_profiles(
                case,
                prof,
                outputs["profiles"],
                max_km=profile_max_km,
            )
        )
    else:
        saved.append(outputs["profiles"])

    if met_path is not None:
        if force or not outputs["surface_met"].exists():
            saved.append(
                plot_clamps_met_meteogram(
                    case,
                    met_path,
                    outputs["surface_met"],
                    hour_start=met_hour_start,
                    hour_end=met_hour_end,
                )
            )
        else:
            saved.append(outputs["surface_met"])

    return saved
