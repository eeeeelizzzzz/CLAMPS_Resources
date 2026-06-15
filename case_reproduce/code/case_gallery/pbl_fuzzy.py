#!/usr/bin/env python3
"""
Run Bonin-style PBL fuzzy logic for one candidate case.

Inputs:
  - DLFP vertical stare (w variance, SNR)
  - TROPoe thermodynamics (T, theta, water vapor)
  - WINDoe u/v winds (from case_gallery.windoe)

Uses pbl_fuzzy_lib.py / pbl_fuzzy_core.py (from clamps_fuzzyPBLh fuzzy_main.py).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import netCDF4 as nc
import numpy as np
from netCDF4 import Dataset
from scipy.interpolate import interp1d
from scipy.special import erf
from suntime import Sun

_PKG = Path(__file__).resolve().parent
_CODE = _PKG.parent
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

from case_gallery.case_lib import (  # noqa: E402
    CaseSpec,
    find_case_files_for_date,
    find_windoe_file_for_date,
    get_case,
    load_cases,
)

SNR_CUTOFF = 1.01
MAX_GATE_KM = 4.0
MAX_GATES = 278  # legacy fuzzy scripts (~5 km at CLAMPS spacing)

AUTHOR_LIST = "Elizabeth Smith (NOAA-NSSL); Jacob Carlin (OU-CIMMS/NSSL)"
CONTACT_LIST = "elizabeth.smith@noaa.gov"


def _load_fuzzy_namespace() -> dict:
    """Load fuzzy logic functions without running the THREDDS driver loop."""
    lib_path = _CODE / "pbl_fuzzy_lib.py"
    ns: dict = {"__name__": "pbl_fuzzy_lib"}
    exec(lib_path.read_text(), ns)  # noqa: S102
    return ns


def _tropoe_times_h(aeri: Dataset) -> tuple[np.ndarray, np.ndarray]:
    if "hour" in aeri.variables:
        hra = np.asarray(aeri.variables["hour"][:], dtype=float)
    elif "time_offset" in aeri.variables:
        hra = np.asarray(aeri.variables["time_offset"][:], dtype=float) / 3600.0
    else:
        raise KeyError("TROPoe file has neither hour nor time_offset")
    return hra, hra * 60.0


def _pbl_output_path(case: CaseSpec, calendar_date: date) -> Path:
    return case.pbl_dir / f"{calendar_date:%Y%m%d}_{case.platform}fuzzyPBLh.nc"


def _pbl_run_dates(case: CaseSpec, calendar_date: date | None) -> list[date]:
    if calendar_date is not None:
        return [calendar_date]
    dates = [case.case_date]
    if case.period_extend_hours > 0:
        dates.append(case.case_date + timedelta(days=1))
    return dates


def _execute_pbl_fuzzy(
    case: CaseSpec,
    calendar_date: date,
    *,
    plot: bool = False,
    write: bool = True,
    show: bool = False,
) -> Path:
    """Run first- and second-generation fuzzy PBL height for one gallery day."""
    fz = _load_fuzzy_namespace()
    files = find_case_files_for_date(case, calendar_date)
    windoe_path = find_windoe_file_for_date(case, calendar_date)

    out_path = _pbl_output_path(case, calendar_date)
    case.pbl_dir.mkdir(parents=True, exist_ok=True)

    plot_me = plot
    write_me = write
    show_me = show
    inv_check = False
    platform = case.platform
    date_label = calendar_date.strftime("%Y%m%d")
    Case = date_label
    campaign = case.project
    sun_lat = case.lat
    sun_lon = case.lon
    path_to_write = str(case.pbl_dir) + "/"
    path_to_plots = path_to_write

    base_time = datetime(
        calendar_date.year, calendar_date.month, calendar_date.day, tzinfo=timezone.utc
    ).timestamp()
    timestamp = datetime.fromtimestamp(base_time, tz=timezone.utc)

    print(f"PROCESSING {case.id} {Case}")
    print(f"  DLFP:   {files.dlfp.name}")
    print(f"  TROPoe: {files.tropoe.name}")

    # --- DLFP vertical stare ---
    with Dataset(files.dlfp) as dl:
        Z = np.asarray(dl.variables["height"][:MAX_GATES], dtype=float)
        Z[np.where(Z > 100)] = np.nan
        lower_limit = float(np.ceil(Z[0] * 100.0) / 100.0)
        lowest_gate = float(Z[2])
        HR = np.asarray(dl.variables["time_offset"][:], dtype=float) / 3600.0
        HR[np.where(HR > 100.0)] = np.nan
        t_s = HR * 60.0
        snr = np.asarray(dl.variables["intensity"][:, :MAX_GATES], dtype=float)
        bscat = np.log10(np.asarray(dl.variables["backscatter"][:, :MAX_GATES], dtype=float))
        bscat[np.where(bscat > 100)] = np.nan
        w = np.asarray(dl.variables["velocity"][:, :MAX_GATES], dtype=float)
        w[np.where(w > 100)] = np.nan

    sigw, sigw_t = fz["lenshowVar"](HR, Z, w, snr, window=0.166)
    sigw_t = sigw_t * 60.0
    bscat[np.where(snr < SNR_CUTOFF)] = np.nan
    w[np.where(snr < SNR_CUTOFF)] = np.nan
    w[:, :2] = np.nan
    bscat[:, :2] = np.nan
    sigsnr, sigsnr_t = fz["calcSigma"](HR, Z, snr, window=0.166)
    sigsnr[np.where(sigsnr > 10)] = np.nan
    print("Stare read in complete")

    # --- WINDoe winds (replaces VAD in fuzzy_main) ---
    with Dataset(windoe_path) as wo:
        height_km = np.asarray(wo.variables["height"][:], dtype=float)
        h_mask = height_km <= MAX_GATE_KM
        Zv = height_km[h_mask]
        if Zv.size > MAX_GATES:
            Zv = Zv[:MAX_GATES]
        hour = np.asarray(wo.variables["hour"][:], dtype=float)
        u = np.asarray(wo.variables["u_wind"][:, h_mask], dtype=float)[:, : Zv.size]
        v = np.asarray(wo.variables["v_wind"][:, h_mask], dtype=float)[:, : Zv.size]
        if "qc_flags" in wo.variables:
            qc = np.asarray(wo.variables["qc_flags"][:], dtype=int)
            bad = qc > 0
            u[bad, :] = np.nan
            v[bad, :] = np.nan

    print(f"  winds (WINDoe): {len(hour)} profiles")

    u_on_z = np.full((len(hour), len(Z)), np.nan)
    v_on_z = np.full((len(hour), len(Z)), np.nan)
    for i in range(len(hour)):
        if np.sum(np.isfinite(u[i])) < 2:
            continue
        fu = interp1d(Zv, u[i], bounds_error=False, fill_value=np.nan)
        fv = interp1d(Zv, v[i], bounds_error=False, fill_value=np.nan)
        u_on_z[i, :] = fu(Z)
        v_on_z[i, :] = fv(Z)
    u = u_on_z
    v = v_on_z
    Zv = Z

    ws = np.hypot(u, v)
    wd = (np.rad2deg(np.arctan2(-u, -v)) + 360.0) % 360.0
    HRv = hour
    t_v = HRv * 60.0
    snrv = np.ones_like(ws)
    snrv[~np.isfinite(ws)] = np.nan
    ws[~np.isfinite(ws)] = np.nan
    wd[~np.isfinite(ws)] = np.nan
    u[~np.isfinite(ws)] = np.nan
    v[~np.isfinite(ws)] = np.nan
    print("WINDoe read in complete")

    # --- TROPoe thermodynamics ---
    with Dataset(files.tropoe) as aeri:
        HRa, t_a = _tropoe_times_h(aeri)
        Za = np.asarray(aeri.variables["height"][:], dtype=float)
        T_orig = np.asarray(aeri.variables["temperature"][:], dtype=float)
        pt_orig = np.asarray(aeri.variables["theta"][:], dtype=float)
        wv_orig = np.asarray(aeri.variables["waterVapor"][:], dtype=float)

    T = np.full(T_orig.shape, np.nan)
    pt = np.full(pt_orig.shape, np.nan)
    wv = np.full(wv_orig.shape, np.nan)
    T[0, :] = T_orig[0, :]
    T[-1, :] = T_orig[-1, :]
    pt[0, :] = pt_orig[0, :]
    pt[-1, :] = pt_orig[-1, :]
    wv[0, :] = wv_orig[0, :]
    wv[-1, :] = wv_orig[-1, :]
    for i in range(1, len(Za) - 1):
        T[1:-1, i] = fz["moving_average"](T_orig[:, i])
        pt[1:-1, i] = fz["moving_average"](pt_orig[:, i])
        wv[1:-1, i] = fz["moving_average"](wv_orig[:, i])
    print("TROPoe read in complete")

    start_time = np.ceil(np.max([t_a[0], t_v[0], t_s[0], sigw_t[0]]) / 10.0) * 10.0
    end_time = np.floor(np.min([t_a[-1], t_v[-1], t_s[-1], sigw_t[-1]]) / 10.0) * 10.0
    x = np.arange(start_time, end_time + 10.0, 10.0)
    y = np.arange(lower_limit, 4.001, 0.01)
    gate_min = np.where(y > lowest_gate)[0][0]

    for name, val in {
        "x": x,
        "y": y,
        "gate_min": gate_min,
        "start_time": start_time,
        "end_time": end_time,
    }.items():
        fz[name] = val

    core_ns = {
        **fz,
        "np": np,
        "plt": plt,
        "erf": erf,
        "nc": nc,
        "Sun": Sun,
        "datetime": datetime,
        "timedelta": timedelta,
        "timezone": timezone,
        "plot_me": plot_me,
        "write_me": write_me,
        "show_me": show_me,
        "inv_check": inv_check,
        "platform": platform,
        "date_label": date_label,
        "Case": Case,
        "campaign": campaign,
        "author_list": AUTHOR_LIST,
        "contact_list": CONTACT_LIST,
        "sun_lat": sun_lat,
        "sun_lon": sun_lon,
        "path_to_write": path_to_write,
        "path_to_plots": path_to_plots,
        "base_time": base_time,
        "timestamp": timestamp,
        "Z": Z,
        "lower_limit": lower_limit,
        "lowest_gate": lowest_gate,
        "HR": HR,
        "t_s": t_s,
        "snr": snr,
        "bscat": bscat,
        "w": w,
        "sigw": sigw,
        "sigw_t": sigw_t,
        "sigsnr": sigsnr,
        "sigsnr_t": sigsnr_t,
        "Zv": Zv,
        "HRv": HRv,
        "t_v": t_v,
        "snrv": snrv,
        "ws": ws,
        "wd": wd,
        "u": u,
        "v": v,
        "HRa": HRa,
        "t_a": t_a,
        "Za": Za,
        "T": T,
        "pt": pt,
        "wv": wv,
        "start_time": start_time,
        "end_time": end_time,
        "x": x,
        "y": y,
        "gate_min": gate_min,
        "x_tick_labels": ["00", "03", "06", "09", "12", "15", "18", "21", "00"],
    }
    exec((_CODE / "pbl_fuzzy_core.py").read_text(), core_ns)  # noqa: S102

    print(f"Done. PBL output: {out_path}")
    return out_path


def run_case(
    case: CaseSpec,
    *,
    calendar_date: date | None = None,
    force: bool = False,
    plot: bool = False,
) -> list[Path]:
    saved: list[Path] = []
    for run_date in _pbl_run_dates(case, calendar_date):
        out_path = _pbl_output_path(case, run_date)
        if out_path.exists() and not force:
            print(f"{case.id}: PBL fuzzy already exists for {run_date} ({out_path.name})")
            saved.append(out_path)
            continue
        saved.append(
            _execute_pbl_fuzzy(case, run_date, plot=plot, write=True, show=False)
        )
    return saved


def run_pbl_fuzzy(
    case_id: str,
    *,
    calendar_date: date | None = None,
    force: bool = False,
) -> list[Path]:
    return run_case(get_case(case_id), calendar_date=calendar_date, force=force)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="PBL fuzzy logic for candidate case (WINDoe winds, not VAD)."
    )
    p.add_argument("case_id")
    p.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Single calendar day (default: case date plus extension day if configured)",
    )
    p.add_argument("--force", action="store_true")
    p.add_argument("--plot", action="store_true")
    args = p.parse_args(argv)
    run_date = date.fromisoformat(args.date) if args.date else None
    run_case(load_cases()[args.case_id], calendar_date=run_date, force=args.force, plot=args.plot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
