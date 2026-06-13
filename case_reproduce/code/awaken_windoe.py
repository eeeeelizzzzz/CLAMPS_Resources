"""WINDoe / DLVAD wind data helpers for gallery instrument figures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from netCDF4 import Dataset

MAX_GATE_KM = 3.0


@dataclass(frozen=True)
class DlvadSnr:
    """Horizontal-wind VAD SNR (intensity) from a DLVAD file."""

    hour: np.ndarray
    height_km: np.ndarray
    intensity: np.ndarray


@dataclass(frozen=True)
class WindoeData:
    hour: np.ndarray
    height_km: np.ndarray
    u_wind: np.ndarray
    v_wind: np.ndarray
    wind_speed: np.ndarray
    wind_direction: np.ndarray
    sigma_u: np.ndarray
    sigma_v: np.ndarray
    sigma_wspd: np.ndarray


def load_windoe(path: Path) -> WindoeData:
    with Dataset(path) as nc:
        hour = np.asarray(nc.variables["hour"][:], dtype=float)
        height_km = np.asarray(nc.variables["height"][:], dtype=float)
        u = np.asarray(nc.variables["u_wind"][:], dtype=float)
        v = np.asarray(nc.variables["v_wind"][:], dtype=float)
        su = np.asarray(nc.variables["sigma_u"][:], dtype=float)
        sv = np.asarray(nc.variables["sigma_v"][:], dtype=float)
        if "sigma_wspd" in nc.variables:
            sw = np.asarray(nc.variables["sigma_wspd"][:], dtype=float)
        elif "sigma_w" in nc.variables:
            sw = np.asarray(nc.variables["sigma_w"][:], dtype=float)
        else:
            sw = np.hypot(su, sv)
    ws = np.hypot(u, v)
    wd = (np.rad2deg(np.arctan2(-u, -v)) + 360.0) % 360.0
    return WindoeData(hour, height_km, u, v, ws, wd, su, sv, sw)


def load_dlvad_snr(dlvad_path: Path) -> DlvadSnr:
    """Load horizontal-wind VAD SNR (``intensity``) from a DLVAD netCDF."""
    with Dataset(dlvad_path) as nc:
        hour = np.asarray(nc.variables["hour"][:], dtype=float)
        height = np.asarray(nc.variables["height"][:], dtype=float)
        intensity = np.asarray(nc.variables["intensity"][:], dtype=float)
    height_km = height / 1000.0 if np.nanmax(height) > 50.0 else height
    return DlvadSnr(hour, height_km, intensity)


def dlvad_snr_ceiling(dlvad, *, threshold: float = 1.01) -> tuple[np.ndarray, np.ndarray]:
    """Max good-SN R gate height (km) per DLVAD time, on a sorted hour grid.

    Expects horizontal-wind VAD ``intensity`` (SNR + 1), not DLFP vertical data.
    """
    if isinstance(dlvad, (str, Path)):
        dlvad = load_dlvad_snr(Path(dlvad))
    hour = np.asarray(dlvad.hour, dtype=float)
    height_km = np.asarray(dlvad.height_km, dtype=float)
    intensity = np.asarray(dlvad.intensity, dtype=float)
    ceiling = np.full(len(hour), np.nan, dtype=float)
    for i in range(len(hour)):
        good = intensity[i] >= threshold
        if np.any(good):
            ceiling[i] = float(np.max(height_km[good]))
    df = pd.DataFrame({"hour": hour, "ceiling": ceiling})
    df = df[np.isfinite(df["hour"]) & np.isfinite(df["ceiling"])]
    if df.empty:
        return np.array([]), np.array([])
    df["tbin"] = (df["hour"] / 0.25).round() * 0.25
    grouped = df.groupby("tbin", as_index=False)["ceiling"].max()
    order = np.argsort(grouped["tbin"].to_numpy())
    h = grouped["tbin"].to_numpy()[order]
    z = grouped["ceiling"].to_numpy()[order]
    return h, z


def smooth_snr_ceiling(
    hour: np.ndarray,
    ceiling_km: np.ndarray,
    *,
    window_hours: float = 0.5,
) -> np.ndarray:
    h = np.asarray(hour, dtype=float)
    z = np.asarray(ceiling_km, dtype=float)
    if len(h) < 2:
        return z.copy()
    order = np.argsort(h)
    h_sorted = h[order]
    z_sorted = z[order]
    dt = float(np.median(np.diff(h_sorted)))
    if not np.isfinite(dt) or dt <= 0:
        dt = 0.25
    win = max(1, int(round(window_hours / dt)))
    smoothed = pd.Series(z_sorted).rolling(win, center=True, min_periods=1).median().to_numpy()
    out = np.full_like(z, np.nan, dtype=float)
    out[order] = smoothed
    return out
