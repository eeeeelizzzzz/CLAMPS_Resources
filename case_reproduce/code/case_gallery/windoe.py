#!/usr/bin/env python3
"""Run WINDoe for one gallery candidate case."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

_PKG = Path(__file__).resolve().parent
_CODE = _PKG.parent
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

from case_gallery.case_lib import find_dlppi_file_for_date, get_case  # noqa: E402
from paths import WINDOE_PRIORS_SGP, WINDOE_ROOT  # noqa: E402

PRIORS_DIR = WINDOE_PRIORS_SGP
VIP_PATH = _PKG / "windoe.vip"

# Retrieval grid: high resolution in the lowest 3 km (see WINDoe.py zgrid regrid fix).
ZGRID_MAX_KM = 3.0
ZGRID_DZ_KM = 0.03  # 30 m vertical spacing (0–3 km)
RAW_LIDAR_MAXRNG_KM = 3.0
# PPI radial velocities use the non-linear forward model; run_fast must stay 0.
RUN_FAST = 0
MAX_ITERATIONS = 8
TRES_MIN = 15  # increase to 30 for ~2x fewer time steps if still too slow


def _zgrid_km(max_km: float = ZGRID_MAX_KM, dz_km: float = ZGRID_DZ_KM) -> np.ndarray:
    n = int(round(max_km / dz_km)) + 1
    grid = np.round(np.linspace(0.0, max_km, n), 4)
    grid[-1] = max_km
    return grid


def vip_path_for_case(case_id: str, output_dir: Path) -> Path:
    """Per-case VIP path so parallel workers do not clobber the same file."""
    return output_dir / f"{case_id}.vip"


def write_vip(case, dlppi_dir: Path, output_dir: Path, vip_path: Path) -> None:
    zgrid = _zgrid_km()
    zgrid_line = ", ".join(f"{z:.3f}" for z in zgrid)
    text = f"""#
# Candidate {case.id} — WINDoe VIP (auto-generated)
#
tres                     = {TRES_MIN}
first_guess              = 1
max_iterations           = {MAX_ITERATIONS}
diagonal_covariance      = 1
w_mean                   = 2.0
w_lengthscale            = 1.0
run_fast                 = {RUN_FAST}

station_lat              = {case.lat}
station_lon              = {case.lon}
station_alt              = {case.alt_m}

raw_lidar_number         = 1
raw_lidar_type           = 1
raw_lidar_paths          = {dlppi_dir}
raw_lidar_minrng         = 0.06
raw_lidar_maxrng         = {RAW_LIDAR_MAXRNG_KM}
raw_lidar_maxsnr         = 5
raw_lidar_minsnr         = -22
raw_lidar_altitude       = {case.alt_m}
raw_lidar_timedelta      = 15
raw_lidar_fix_heading    = 0
raw_lidar_average_rv     = 1
raw_lidar_fix_csm_azimuths = 0
raw_lidar_eff_N          = -10
raw_lidar_sig_thresh     = 10

proc_lidar_number        = 0

cons_profiler_number     = 0
insitu_number            = 0
use_model                = 0

output_rootname          = {case.windoe_rootname}
output_path              = {output_dir}
output_clobber           = 1
keep_file_small          = 1

zgrid                    = {zgrid_line}

globatt_Site             = {case.project} {case.platform}
globatt_Instruments      = CLAMPS {case.platform} DL PPI radial velocities
globatt_Dataset_contact  = case gallery candidates
globatt_Processing_comment = WINDoe OE winds from DL PPI; SGP monthly prior
"""
    vip_path.write_text(text)


def ppi_hour_bounds(dlppi_path: Path) -> tuple[float, float]:
    with Dataset(dlppi_path) as nc:
        hour = np.asarray(nc.variables["hour"][:], dtype=float)
    hour = hour[np.isfinite(hour)]
    if hour.size == 0:
        return 0.0, 23.99
    return max(0.0, float(np.nanmin(hour))), min(23.99, float(np.nanmax(hour)))


def run_windoe(
    case_id: str,
    *,
    calendar_date: date | None = None,
    verbose: int = 1,
    force: bool = False,
) -> None:
    case = get_case(case_id)
    run_date = calendar_date or case.case_date
    if case.reuse_awaken:
        find_windoe = case.windoe_dir.glob(
            f"awaken_clamps1.WINDoe.c1.{run_date:%Y%m%d}*.nc"
        )
        if any(find_windoe):
            print(f"{case_id}: WINDoe already exists (reuse_awaken)")
            return

    dlppi_path = find_dlppi_file_for_date(case, run_date)
    dlppi_dir = case.clamps_root / "dlppi"
    out_dir = case.windoe_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    pattern = f"{case.windoe_rootname}.{run_date:%Y%m%d}*.nc"
    existing = list(out_dir.glob(pattern))
    if existing and not force:
        print(f"{case_id}: WINDoe already exists for {run_date} ({existing[-1].name})")
        return
    if existing and force:
        for f in existing:
            f.unlink()

    prior = PRIORS_DIR / f"Xa_Sa_wind_datafile.month_{run_date.month:02d}.cdf"
    if not WINDOE_ROOT.is_dir():
        raise SystemExit(f"WINDoe not found at {WINDOE_ROOT}")
    if not prior.is_file():
        raise SystemExit(f"Prior file not found: {prior}")

    vip_path = vip_path_for_case(case_id, out_dir)
    write_vip(case, dlppi_dir, out_dir, vip_path)
    shour, ehour = ppi_hour_bounds(dlppi_path)
    if (
        calendar_date is not None
        and calendar_date > case.case_date
        and case.period_extend_hours > 0
    ):
        ehour = min(ehour, float(case.period_extend_hours))
        print(f"{case_id}: extension-day WINDoe limited to 0–{ehour:.2f} UTC")
    ymd = int(run_date.strftime("%Y%m%d"))
    cmd = [
        sys.executable,
        str(WINDOE_ROOT / "WINDoe.py"),
        str(ymd),
        str(vip_path),
        str(prior),
        "--shour",
        f"{shour:.4f}",
        "--ehour",
        f"{ehour:.4f}",
        "--verbose",
        str(verbose),
    ]
    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(WINDOE_ROOT))
    n = len(list(out_dir.glob(pattern)))
    if proc.returncode != 0:
        print(f"WINDoe exited {proc.returncode}")
    if n == 0:
        print(f"{case_id}: WINDoe produced no files for {run_date}; plot may use DLVAD winds")
    else:
        print(f"Done. {n} WINDoe file(s) for {run_date} in {out_dir}")


def main() -> None:
    p = argparse.ArgumentParser(description="Run WINDoe for a candidate case")
    p.add_argument("case_id")
    p.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Calendar date to process (default: case date in cases.yaml)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Delete existing WINDoe .nc for this date and re-run",
    )
    p.add_argument("--verbose", type=int, default=1)
    args = p.parse_args()
    run_date = date.fromisoformat(args.date) if args.date else None
    run_windoe(args.case_id, calendar_date=run_date, verbose=args.verbose, force=args.force)


def run_case(case, *, force: bool = False, verbose: int = 1) -> None:
    run_windoe(case.id, verbose=verbose, force=force)


if __name__ == "__main__":
    main()
