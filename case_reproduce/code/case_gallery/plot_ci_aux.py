"""Convection-initiation auxiliary figures — surface meteogram with precipitation."""

from __future__ import annotations

from pathlib import Path

from case_gallery.case_lib import find_case_files, get_case
from case_gallery.plot_diurnal_aux import (  # noqa: E402
    _find_clamps_met_file,
    plot_clamps_met_meteogram,
)


def plot_ci_auxiliary(
    case_id: str = "ci_c2",
    *,
    met_hour_start: float = 0.0,
    met_hour_end: float = 24.0,
    force: bool = False,
) -> list[Path]:
    import os

    from case_gallery.plot_auxiliary import MPLCONFIG_DIR

    case = get_case(case_id)
    find_case_files(case)

    out_dir = case.figure_dir
    outputs = {
        "surface_met": out_dir / "aux_surface_meteogram.png",
    }

    met_path: Path | None = None
    try:
        met_path = _find_clamps_met_file(case)
    except FileNotFoundError:
        print(f"  skip surface meteogram: no CLAMPS met file under {case.clamps_root / 'aux'}")
        return []

    if outputs["surface_met"].exists() and not force:
        print(f"{case_id}: auxiliary figures exist")
        return [outputs["surface_met"]]

    os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))
    return [
        plot_clamps_met_meteogram(
            case,
            met_path,
            outputs["surface_met"],
            hour_start=met_hour_start,
            hour_end=met_hour_end,
        )
    ]
