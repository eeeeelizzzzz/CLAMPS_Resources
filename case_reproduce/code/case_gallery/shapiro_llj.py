"""Shapiro et al. (2016) unified Great Plains NLLJ model (JAS 73, 3037–3057).

Implements eqs. (3.17)–(3.24) with piecewise K(t) and bs(t) from section 4.
Fourier coefficients D_{j,m} are evaluated by trapezoidal integration of (3.24).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DAY_S = 86400.0
_COEFF_CACHE: dict[tuple, tuple] = {}


@dataclass(frozen=True)
class ShapiroParams:
    """Reference experiment BH (Table 1)."""

    f: float = 8.6e-5
    y_g: float = 10.0
    alpha: float = 0.00158
    n: float = 0.01
    b_max: float = 0.2
    b_min: float = -0.2
    t_max_h: float = 9.0
    t_set_h: float = 12.0
    k_d: float = 100.0
    k_n: float = 1.0
    d: float = 0.2 / DAY_S
    t24_h: float = 24.0
    m_max: int = 400
    n_time: int = 3601


def _cubic_roots(f: float, d: float, n: float, alpha: float) -> tuple[float, complex, complex]:
    v2 = n**2 * np.sin(alpha) ** 2 + f**2
    a2, a1, a0 = 2.0 * d, v2 + d**2, d * n**2 * np.sin(alpha) ** 2
    q = a1 / 3.0 - a2**2 / 9.0
    r = (a1 * a2 - 3.0 * a0) / 6.0 - a2**3 / 27.0
    s1 = np.cbrt(r + np.sqrt(q**3 + r**2))
    s2 = np.cbrt(r - np.sqrt(q**3 + r**2))
    k1 = (s1 + s2) - a2 / 3.0
    k2 = -0.5 * (s1 + s2) - a2 / 3.0 + 1j * np.sqrt(3) / 2.0 * (s1 - s2)
    return float(k1), k2, np.conj(k2)


def _ml_from_k(k: complex, d: float, f: float) -> tuple[complex, complex]:
    m = -k - d
    return m, k * f / m


def _bs(t: np.ndarray, p: ShapiroParams) -> np.ndarray:
    t24 = p.t24_h * 3600.0
    t_max = p.t_max_h * 3600.0
    db = p.b_max - p.b_min
    out = np.empty_like(t, dtype=float)
    m1 = t < t_max
    out[m1] = p.b_min + db * (t[m1] / t_max)
    out[~m1] = p.b_max - db * (t[~m1] - t_max) / (t24 - t_max)
    return out


def _kappa(t: np.ndarray, p: ShapiroParams, k_bar: float) -> np.ndarray:
    t_set = p.t_set_h * 3600.0
    return np.where(
        t < t_set,
        p.k_d * t / k_bar,
        (p.k_d * t_set + p.k_n * (t - t_set)) / k_bar,
    )


def _djm_numeric(m: int, mj: complex, lj: complex, p: ShapiroParams, k_bar: float) -> complex:
    """Eq. (3.24)."""
    t24 = p.t24_h * 3600.0
    t_set = p.t_set_h * 3600.0
    ts = np.linspace(0.0, t24, p.n_time)
    kappa = _kappa(ts, p, k_bar)
    k_t = np.where(ts < t_set, p.k_d, p.k_n)
    sina = np.sin(p.alpha)
    forcing = k_t * (_bs(ts, p) * sina - lj * p.y_g)
    phase = -mj * ts + (mj - 2j * np.pi * m / t24) * kappa
    return np.trapezoid(forcing * np.exp(phase), ts) / (t24 * k_bar)


def _decaying_sqrt(lm: complex, z: float) -> complex:
    for root in (np.sqrt(lm), -np.sqrt(lm)):
        if np.real(-1j * z * root) <= 0.0:
            return root
    return np.sqrt(lm)


def _coefficients(p: ShapiroParams) -> tuple[dict[int, complex], dict[int, complex], complex, complex, float, complex, complex, float]:
    key = (
        p.f, p.y_g, p.alpha, p.n, p.b_max, p.b_min, p.t_max_h, p.t_set_h,
        p.k_d, p.k_n, p.d, p.t24_h, p.m_max, p.n_time,
    )
    if key not in _COEFF_CACHE:
        t_set = p.t_set_h * 3600.0
        t24 = p.t24_h * 3600.0
        k_bar = p.k_d * t_set / t24 + p.k_n * (1.0 - t_set / t24)
        k1, k2, _ = _cubic_roots(p.f, p.d, p.n, p.alpha)
        m1, l1 = _ml_from_k(k1, p.d, p.f)
        m2, l2 = _ml_from_k(k2, p.d, p.f)
        ms = range(-p.m_max, p.m_max + 1)
        d1 = {m: _djm_numeric(m, m1, l1, p, k_bar) for m in ms}
        d2 = {m: _djm_numeric(m, m2, l2, p, k_bar) for m in ms}
        d_den = np.imag(k2) * (l1 - np.real(l2)) - np.imag(l2) * (k1 - np.real(k2))
        _COEFF_CACHE[key] = (d1, d2, m1, m2, k_bar, k1, k2, d_den)
    return _COEFF_CACHE[key]


def _q_series(
    z: float,
    t: np.ndarray,
    *,
    mj: complex,
    djm: dict[int, complex],
    p: ShapiroParams,
    k_bar: float,
) -> np.ndarray:
    t24 = p.t24_h * 3600.0
    t_set = p.t_set_h * 3600.0
    kappa = _kappa(t, p, k_bar)
    pref = np.exp(mj * (t - kappa))
    total = np.zeros_like(t, dtype=complex)
    for m, dm in djm.items():
        lm = (mj - 2j * np.pi * m / t24) / k_bar
        root = _decaying_sqrt(lm, z)
        total += dm * np.exp(-2j * np.pi * m * kappa / t24) * np.exp(-1j * z * root)
    return pref * total


def winds_at_height(
    z_m: float,
    times_h: np.ndarray,
    *,
    p: ShapiroParams | None = None,
    sunrise_utc_h: float = 11.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (u, v) m/s at z_m for UTC hours. v is southerly (cross-slope)."""
    p = p or ShapiroParams()
    d1, d2, m1, m2, k_bar, k1, k2, d_den = _coefficients(p)
    model_t = ((np.asarray(times_h, dtype=float) - sunrise_utc_h) % 24.0) * 3600.0
    q1 = _q_series(z_m, model_t, mj=m1, djm=d1, p=p, k_bar=k_bar)
    q2 = _q_series(z_m, model_t, mj=m2, djm=d2, p=p, k_bar=k_bar)
    l1 = k1 * p.f / m1
    l2 = k2 * p.f / m2
    u = (-np.imag(l2) * q1 + np.imag(l2) * np.real(q2) + (l1 - np.real(l2)) * np.imag(q2)) / d_den
    ya = (np.imag(k2) * q1 - np.imag(k2) * np.real(q2) - (k1 - np.real(k2)) * np.imag(q2)) / d_den
    return np.real(u), np.real(ya) + p.y_g
