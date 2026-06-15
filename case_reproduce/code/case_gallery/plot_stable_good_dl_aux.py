"""Stable boundary layer (good DL) auxiliary figures — Ri_b and surface met."""

from __future__ import annotations

from pathlib import Path

from case_gallery.case_lib import find_case_files, get_case
from case_gallery.plot_diurnal_aux import (  # noqa: E402
    _find_clamps_met_file,
    plot_clamps_met_meteogram,
    plot_rib_timeheight,
)


def plot_stable_good_dl_auxiliary(
    case_id: str = "stable_good_dl_c2",
    *,
    rib_threshold: float = 0.25,
    met_hour_start: float = 0.0,
    met_hour_end: float = 24.0,
    force: bool = False,
) -> list[Path]:
    import os

    from case_gallery.plot_auxiliary import MPLCONFIG_DIR
    from case_gallery.winds import load_case_winds

    case = get_case(case_id)
    files = find_case_files(case)
    wind, _ = load_case_winds(case, prefer="auto")

    out_dir = case.figure_dir
    outputs = {
        "rib": out_dir / "aux_rib_timeheight.png",
        "surface_met": out_dir / "aux_surface_meteogram.png",
    }

    met_path: Path | None = None
    try:
        met_path = _find_clamps_met_file(case)
    except FileNotFoundError:
        print(f"  skip surface meteogram: no CLAMPS met file under {case.clamps_root / 'aux'}")

    expected = [outputs["rib"]]
    if met_path is not None:
        expected.append(outputs["surface_met"])

    if all(p.exists() for p in expected) and not force:
        print(f"{case_id}: auxiliary figures exist")
        return expected

    os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))
    saved: list[Path] = []

    if force or not outputs["rib"].exists():
        saved.append(
            plot_rib_timeheight(
                case,
                outputs["rib"],
                tropoe_path=files.tropoe,
                dlfp_path=files.dlfp,
                wind=wind,
                rib_threshold=rib_threshold,
            )
        )
    else:
        saved.append(outputs["rib"])

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
