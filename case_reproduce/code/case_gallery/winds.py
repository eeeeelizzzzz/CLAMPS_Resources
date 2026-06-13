"""Load gallery-case winds (WINDoe preferred, DLVAD fallback)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

_CODE = Path(__file__).resolve().parent.parent
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

from awaken_windoe import MAX_GATE_KM, WindoeData, load_windoe  # noqa: E402
from case_gallery.case_lib import CaseSpec, find_case_files, find_windoe_file  # noqa: E402


def load_dlvad_winds(dlvad_path: Path) -> WindoeData:
    with Dataset(dlvad_path) as nc:
        hour = np.asarray(nc.variables["hour"][:], dtype=float)
        height_km = np.asarray(nc.variables["height"][:], dtype=float)
        wspd = np.asarray(nc.variables["wspd"][:], dtype=float)
        wdir = np.asarray(nc.variables["wdir"][:], dtype=float)

    h_mask = height_km <= MAX_GATE_KM
    height_km = height_km[h_mask]
    wspd = wspd[:, h_mask]
    wdir = wdir[:, h_mask]

    rad = np.deg2rad(wdir)
    u = -wspd * np.sin(rad)
    v = -wspd * np.cos(rad)
    u[~np.isfinite(wspd)] = np.nan
    v[~np.isfinite(wspd)] = np.nan
    ws = np.hypot(u, v)
    wd = (np.rad2deg(np.arctan2(-u, -v)) + 360.0) % 360.0
    nan_sig = np.full_like(u, np.nan)
    return WindoeData(hour, height_km, u, v, ws, wd, nan_sig, nan_sig, nan_sig)


def load_case_winds(case: CaseSpec, *, prefer: str = "windoe") -> tuple[WindoeData, str]:
    """Return (wind field, source label). prefer: 'windoe', 'dlvad', or 'auto'."""
    files = find_case_files(case)
    if prefer == "dlvad":
        return load_dlvad_winds(files.dlvad), "DLVAD"

    if prefer in ("windoe", "auto"):
        try:
            path = find_windoe_file(case)
            return load_windoe(path), "WINDoe"
        except FileNotFoundError:
            if prefer == "windoe":
                raise
            print(f"{case.id}: no WINDoe — using DLVAD {files.dlvad.name}")
            return load_dlvad_winds(files.dlvad), "DLVAD"

    raise ValueError(f"Unknown prefer={prefer!r}")
