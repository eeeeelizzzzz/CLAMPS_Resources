"""Gravity-wave auxiliary figures — DL-FP vertical velocity and surface meteogram."""

from __future__ import annotations

import shutil
from pathlib import Path

from case_gallery.case_lib import find_case_files, get_case
from case_gallery.plot_diurnal_aux import (  # noqa: E402
    _find_clamps_met_file,
    plot_clamps_met_meteogram,
)

WEBHOST_IMAGES_DIR = Path(__file__).resolve().parents[3] / "images"


def _sync_gallery_images(case_id: str, figure_paths: list[Path]) -> list[Path]:
    WEBHOST_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    synced: list[Path] = []
    for src in figure_paths:
        if not src.is_file():
            continue
        dst = WEBHOST_IMAGES_DIR / f"{case_id}_{src.name}"
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            shutil.copy2(src, dst)
        synced.append(dst)
    return synced


def plot_gravity_waves_auxiliary(
    case_id: str = "gravity_waves_c2",
    *,
    w_hour_start: float = 0.0,
    w_hour_end: float = 14.0,
    w_vmax: float = 2.0,
    met_hour_start: float = 0.0,
    met_hour_end: float = 24.0,
    met_zoom_hour_start: float = 0.0,
    met_zoom_hour_end: float = 14.0,
    force: bool = False,
    sync_webhost: bool = True,
) -> list[Path]:
    import os

    from case_gallery.plot_auxiliary import MPLCONFIG_DIR, plot_dlfp_w_zoom_timeheight

    case = get_case(case_id)
    files = find_case_files(case)

    out_dir = case.figure_dir
    outputs = {
        "w_timeheight": out_dir / "aux_dlfp_w_timeheight.png",
        "surface_met": out_dir / "aux_surface_meteogram.png",
        "surface_met_zoom": out_dir / "aux_surface_meteogram_0_14.png",
    }

    met_path: Path | None = None
    try:
        met_path = _find_clamps_met_file(case)
    except FileNotFoundError:
        print(f"  skip surface meteogram: no CLAMPS met file under {case.clamps_root / 'aux'}")

    expected = [outputs["w_timeheight"]]
    if met_path is not None:
        expected.extend([outputs["surface_met"], outputs["surface_met_zoom"]])

    if all(p.exists() for p in expected) and not force:
        print(f"{case_id}: auxiliary figures exist")
        saved = expected
    else:
        os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))
        saved = []

        if force or not outputs["w_timeheight"].exists():
            saved.append(
                plot_dlfp_w_zoom_timeheight(
                    case,
                    files.dlfp,
                    outputs["w_timeheight"],
                    hour_start=w_hour_start,
                    hour_end=w_hour_end,
                    w_vmax=w_vmax,
                )
            )
        else:
            saved.append(outputs["w_timeheight"])

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

            if force or not outputs["surface_met_zoom"].exists():
                saved.append(
                    plot_clamps_met_meteogram(
                        case,
                        met_path,
                        outputs["surface_met_zoom"],
                        hour_start=met_zoom_hour_start,
                        hour_end=met_zoom_hour_end,
                    )
                )
            else:
                saved.append(outputs["surface_met_zoom"])

    radar_candidates = sorted(out_dir.glob("*88D*.png")) + sorted(out_dir.glob("*88d*.png"))
    saved.extend(radar_candidates)

    if sync_webhost and WEBHOST_IMAGES_DIR.is_dir():
        for dst in _sync_gallery_images(case_id, saved):
            print(f"  synced {dst.name}")

    return saved
