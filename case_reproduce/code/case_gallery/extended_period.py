"""Stitch multi-day CLAMPS inputs onto one period axis (e.g. 24 h + next-day extension)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np
from scipy.interpolate import interp1d

import plot_awaken_instrument_template as _pat  # noqa: F401 — bootstrap pyc deps
import plot_splash_la_case as la
from awaken_la_diagnostics import (
    ProfilerCrossSection,
    PblDiagnostics,
    build_profiler_cross_section,
    load_fuzzy_pblh,
)
from awaken_windoe import WindoeData, dlvad_snr_ceiling, load_dlvad_snr, load_windoe
from case_gallery.case_lib import (
    CaseSpec,
    find_dlvad_file_for_date,
    find_pbl_file_for_date,
    find_profiler_files_for_date,
    find_tropoe_file_for_date,
    find_windoe_file_for_date,
)
from case_gallery.winds import load_dlvad_winds
from plot_awaken_instrument_template import DLVAD_SNR_THRESHOLD, load_cloud_base


def case_period(case: CaseSpec) -> la.PeriodAxis:
    start = datetime(
        case.case_date.year,
        case.case_date.month,
        case.case_date.day,
        tzinfo=timezone.utc,
    )
    end = start + timedelta(hours=24 + case.period_extend_hours)
    return la.PeriodAxis(start=start, end=end)


def period_calendar_dates(case: CaseSpec) -> list[date]:
    dates = [case.case_date]
    if case.period_extend_hours > 0:
        dates.append(case.case_date + timedelta(days=1))
    return dates


def period_hours(period: la.PeriodAxis, dt: datetime) -> float:
    return (dt - period.start).total_seconds() / 3600.0


def in_period_window(dt: datetime, case: CaseSpec, period: la.PeriodAxis) -> bool:
    if not (period.start <= dt < period.end):
        return False
    if dt.date() == case.case_date:
        return True
    if case.period_extend_hours <= 0:
        return False
    if dt.date() != case.case_date + timedelta(days=1):
        return False
    hod = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    return hod < float(case.period_extend_hours) + 1e-9


def _datetime_from_hour(calendar_date: date, hour_decimal: float) -> datetime:
    return datetime(
        calendar_date.year,
        calendar_date.month,
        calendar_date.day,
        tzinfo=timezone.utc,
    ) + timedelta(hours=float(hour_decimal))


def _filter_profile_times(
    hour: np.ndarray,
    fields: list[np.ndarray],
    calendar_date: date,
    case: CaseSpec,
    period: la.PeriodAxis,
) -> tuple[np.ndarray, list[np.ndarray]] | None:
    period_h: list[float] = []
    kept_idx: list[int] = []
    for i, hod in enumerate(hour):
        dt = _datetime_from_hour(calendar_date, float(hod))
        if not in_period_window(dt, case, period):
            continue
        kept_idx.append(i)
        period_h.append(period_hours(period, dt))
    if not kept_idx:
        return None
    idx = np.asarray(kept_idx, dtype=int)
    order = np.argsort(np.asarray(period_h, dtype=float))
    ph = np.asarray(period_h, dtype=float)[order]
    out_fields = [f[idx][order] for f in fields]
    return ph, out_fields


def _resample_wind_vertical(wind: WindoeData, height_km: np.ndarray) -> WindoeData:
    z_tgt = np.asarray(height_km, dtype=float)
    z_src = np.asarray(wind.height_km, dtype=float)
    if z_src.shape == z_tgt.shape and np.allclose(z_src, z_tgt, equal_nan=True):
        return wind

    def _resample_field(field: np.ndarray) -> np.ndarray:
        src = np.asarray(field, dtype=float)
        out = np.full((len(wind.hour), len(z_tgt)), np.nan)
        for i in range(len(wind.hour)):
            y = src[i]
            ok = np.isfinite(y) & np.isfinite(z_src)
            if np.count_nonzero(ok) < 2:
                continue
            out[i] = interp1d(z_src[ok], y[ok], bounds_error=False, fill_value=np.nan)(z_tgt)
        return out

    u = _resample_field(wind.u_wind)
    v = _resample_field(wind.v_wind)
    ws = np.hypot(u, v)
    wd = (np.rad2deg(np.arctan2(-u, -v)) + 360.0) % 360.0
    return WindoeData(
        hour=wind.hour,
        height_km=z_tgt,
        u_wind=u,
        v_wind=v,
        wind_speed=ws,
        wind_direction=wd,
        sigma_u=_resample_field(wind.sigma_u),
        sigma_v=_resample_field(wind.sigma_v),
        sigma_wspd=_resample_field(wind.sigma_wspd),
    )


def stitch_profiler_cross_section(
    case: CaseSpec,
    period: la.PeriodAxis,
    *,
    max_km: float,
) -> ProfilerCrossSection:
    theta_parts: list[np.ndarray] = []
    q_parts: list[np.ndarray] = []
    t_parts: list[np.ndarray] = []
    wvar_parts: list[np.ndarray] = []
    w_t_parts: list[np.ndarray] = []
    height_km: np.ndarray | None = None
    w_height_km: np.ndarray | None = None

    for cal_date in period_calendar_dates(case):
        try:
            tropoe_path, dlfp_path = find_profiler_files_for_date(case, cal_date)
        except FileNotFoundError as exc:
            print(f"  skip profiler {cal_date}: {exc}")
            continue
        prof = build_profiler_cross_section(
            tropoe_path,
            dlfp_path,
            max_km=max_km,
            apply_tropoe_qc=False,
        )
        height_km = prof.tropoe_height_km
        w_height_km = prof.w_variance_height_km

        trop = _filter_profile_times(
            prof.tropoe_hour,
            [prof.theta_v_k, prof.q_kgkg],
            cal_date,
            case,
            period,
        )
        if trop is not None:
            ph, (theta, q) = trop
            t_parts.append(ph)
            theta_parts.append(theta)
            q_parts.append(q)

        wv = _filter_profile_times(
            prof.w_variance_hour,
            [prof.w_variance],
            cal_date,
            case,
            period,
        )
        if wv is not None:
            ph, (wvar,) = wv
            w_t_parts.append(ph)
            wvar_parts.append(wvar)

    if not t_parts or height_km is None:
        raise ValueError(
            f"No profiler data in period window for {case.id} "
            f"(need inputs for {', '.join(d.isoformat() for d in period_calendar_dates(case))})"
        )

    return ProfilerCrossSection(
        tropoe_hour=np.concatenate(t_parts),
        tropoe_height_km=height_km,
        theta_v_k=np.concatenate(theta_parts, axis=0),
        q_kgkg=np.concatenate(q_parts, axis=0),
        w_variance_hour=np.concatenate(w_t_parts) if w_t_parts else np.array([]),
        w_variance_height_km=w_height_km if w_height_km is not None else height_km,
        w_variance=np.concatenate(wvar_parts, axis=0) if wvar_parts else np.empty((0, 0)),
    )


def _resample_profile_heights(
    fields: list[np.ndarray],
    z_src: np.ndarray,
    z_tgt: np.ndarray,
) -> list[np.ndarray]:
    z_src = np.asarray(z_src, dtype=float)
    z_tgt = np.asarray(z_tgt, dtype=float)
    if z_src.shape == z_tgt.shape and np.allclose(z_src, z_tgt, equal_nan=True):
        return fields
    out_fields: list[np.ndarray] = []
    for field in fields:
        src = np.asarray(field, dtype=float)
        out = np.full((src.shape[0], len(z_tgt)), np.nan)
        for i in range(src.shape[0]):
            y = src[i]
            ok = np.isfinite(y) & np.isfinite(z_src)
            if np.count_nonzero(ok) < 2:
                continue
            out[i] = interp1d(z_src[ok], y[ok], bounds_error=False, fill_value=np.nan)(z_tgt)
        out_fields.append(out)
    return out_fields


def stitch_wind(
    case: CaseSpec,
    period: la.PeriodAxis,
    *,
    prefer: str = "auto",
) -> tuple[WindoeData, str]:
    hour_parts: list[np.ndarray] = []
    u_parts: list[np.ndarray] = []
    v_parts: list[np.ndarray] = []
    ws_parts: list[np.ndarray] = []
    wd_parts: list[np.ndarray] = []
    su_parts: list[np.ndarray] = []
    sv_parts: list[np.ndarray] = []
    sw_parts: list[np.ndarray] = []
    height_km: np.ndarray | None = None
    source = "WINDoe"

    for cal_date in period_calendar_dates(case):
        wind: WindoeData | None = None
        day_source = "WINDoe"
        if prefer in ("windoe", "auto"):
            try:
                wind = load_windoe(find_windoe_file_for_date(case, cal_date))
            except FileNotFoundError:
                if prefer == "windoe":
                    raise
        if wind is None and prefer in ("dlvad", "auto"):
            try:
                wind = load_dlvad_winds(find_dlvad_file_for_date(case, cal_date))
                day_source = "DLVAD"
            except FileNotFoundError:
                print(f"  skip wind {cal_date}: no WINDoe or DLVAD")
                continue

        filt = _filter_profile_times(
            wind.hour,
            [wind.u_wind, wind.v_wind, wind.wind_speed, wind.wind_direction,
             wind.sigma_u, wind.sigma_v, wind.sigma_wspd],
            cal_date,
            case,
            period,
        )
        if filt is None:
            continue
        ph, arrs = filt
        if height_km is None:
            height_km = np.asarray(wind.height_km, dtype=float)
        arrs = _resample_profile_heights(arrs, wind.height_km, height_km)
        hour_parts.append(ph)
        u_parts.append(arrs[0])
        v_parts.append(arrs[1])
        ws_parts.append(arrs[2])
        wd_parts.append(arrs[3])
        su_parts.append(arrs[4])
        sv_parts.append(arrs[5])
        sw_parts.append(arrs[6])
        if day_source == "DLVAD":
            source = "DLVAD"

    if not hour_parts or height_km is None:
        raise ValueError(f"No wind data in period window for {case.id}")

    return WindoeData(
        hour=np.concatenate(hour_parts),
        height_km=height_km,
        u_wind=np.concatenate(u_parts, axis=0),
        v_wind=np.concatenate(v_parts, axis=0),
        wind_speed=np.concatenate(ws_parts, axis=0),
        wind_direction=np.concatenate(wd_parts, axis=0),
        sigma_u=np.concatenate(su_parts, axis=0),
        sigma_v=np.concatenate(sv_parts, axis=0),
        sigma_wspd=np.concatenate(sw_parts, axis=0),
    ), source


def stitch_pbl(case: CaseSpec, period: la.PeriodAxis) -> PblDiagnostics:
    period_h: list[float] = []
    pblh: list[float] = []
    stdev: list[float] = []

    for cal_date in period_calendar_dates(case):
        try:
            pbl_path = find_pbl_file_for_date(case, cal_date)
        except FileNotFoundError:
            print(f"  skip PBL {cal_date}: no fuzzy output")
            continue
        pbl = load_fuzzy_pblh(pbl_path)
        for hod, z, s in zip(pbl.hour_decimal, pbl.pblh_m, pbl.pblh_stdev_m):
            dt = _datetime_from_hour(cal_date, float(hod))
            if not in_period_window(dt, case, period):
                continue
            period_h.append(period_hours(period, dt))
            pblh.append(float(z))
            stdev.append(float(s))

    if not period_h:
        raise ValueError(f"No fuzzy PBL in period window for {case.id}")

    order = np.argsort(np.asarray(period_h, dtype=float))
    ph = np.asarray(period_h, dtype=float)[order]
    return PblDiagnostics(
        hour_decimal=ph,
        pblh_m=np.asarray(pblh, dtype=float)[order],
        pblh_stdev_m=np.asarray(stdev, dtype=float)[order],
    )


def stitch_snr_ceiling(case: CaseSpec, period: la.PeriodAxis) -> tuple[np.ndarray, np.ndarray]:
    snr_h: list[float] = []
    snr_z: list[float] = []

    for cal_date in period_calendar_dates(case):
        try:
            dlvad_path = find_dlvad_file_for_date(case, cal_date)
        except FileNotFoundError:
            print(f"  skip SNR ceiling {cal_date}: no DLVAD")
            continue
        h_day, z_day = dlvad_snr_ceiling(
            load_dlvad_snr(dlvad_path),
            threshold=DLVAD_SNR_THRESHOLD,
        )
        for hod, zval in zip(h_day, z_day):
            dt = _datetime_from_hour(cal_date, float(hod))
            if not in_period_window(dt, case, period):
                continue
            snr_h.append(period_hours(period, dt))
            snr_z.append(float(zval))

    if not snr_h:
        return np.array([]), np.array([])
    order = np.argsort(np.asarray(snr_h, dtype=float))
    h = np.asarray(snr_h, dtype=float)[order]
    z = np.asarray(snr_z, dtype=float)[order]
    return h, z


def stitch_cloud_base(case: CaseSpec, period: la.PeriodAxis) -> tuple[np.ndarray, np.ndarray]:
    cb_h: list[float] = []
    cb_z: list[float] = []

    for cal_date in period_calendar_dates(case):
        try:
            tropoe_path = find_tropoe_file_for_date(case, cal_date)
        except FileNotFoundError:
            print(f"  skip cloud base {cal_date}: no TROPoe")
            continue
        h_day, z_day = load_cloud_base(tropoe_path)
        for hod, zval in zip(h_day, z_day):
            dt = _datetime_from_hour(cal_date, float(hod))
            if not in_period_window(dt, case, period):
                continue
            cb_h.append(period_hours(period, dt))
            cb_z.append(float(zval))

    if not cb_h:
        return np.array([]), np.array([])
    order = np.argsort(np.asarray(cb_h, dtype=float))
    return np.asarray(cb_h, dtype=float)[order], np.asarray(cb_z, dtype=float)[order]
