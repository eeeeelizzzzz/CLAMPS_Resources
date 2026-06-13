"""Per-case color limits and color-bar tick helpers for gallery figures."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PanelLimits:
    theta_v: tuple[float, float]
    q_gkg: tuple[float, float]
    wspd: tuple[float, float]


# θv: 270–285 | 282–307 | 297–315 | 300–315
# q:   2–12   | 3–18    | 5–28
# ws:  3–18   | 3–28
CASE_LIMITS: dict[str, PanelLimits] = {
    "ci_c1": PanelLimits((297, 315), (5, 28), (3, 18)),
    "ci_c2": PanelLimits((297, 315), (5, 28), (3, 18)),
    "cold_pool_c2": PanelLimits((297, 315), (3, 18), (3, 28)),
    "deep_cbl_c1": PanelLimits((300, 315), (5, 28), (3, 18)),
    "deep_cbl_c2": PanelLimits((300, 315), (3, 18), (3, 18)),
    "diurnal_c2": PanelLimits((297, 315), (3, 18), (3, 18)),
    "gravity_waves_c1": PanelLimits((297, 315), (5, 28), (3, 28)),
    "gravity_waves_c2": PanelLimits((297, 315), (3, 18), (3, 28)),
    "la_interaction_c1": PanelLimits((297, 315), (3, 18), (3, 18)),
    "nllj_c1": PanelLimits((297, 315), (3, 18), (3, 18)),
    "nllj_c2": PanelLimits((297, 315), (3, 18), (3, 18)),
    "sea_breeze_c1": PanelLimits((297, 315), (3, 18), (3, 18)),
    "sea_breeze_c2": PanelLimits((297, 315), (3, 18), (3, 18)),
    "fropa_c2": PanelLimits((282, 307), (3, 18), (3, 28)),
    "sharp_grad_c2": PanelLimits((282, 307), (2, 12), (3, 18)),
    "stable_bad_dl_c1": PanelLimits((270, 285), (2, 12), (3, 18)),
    "stable_good_dl_c2": PanelLimits((282, 307), (2, 12), (3, 28)),
}

DEFAULT_LIMITS = PanelLimits((297, 315), (3, 18), (3, 18))


def limits_for_case(case_id: str) -> PanelLimits:
    return CASE_LIMITS.get(case_id, DEFAULT_LIMITS)


def theta_v_ticks(vmin: float, vmax: float) -> list[float]:
    start = int(5 * np.ceil(vmin / 5.0))
    ticks = list(range(start, int(vmax) + 1, 5))
    return [float(t) for t in ticks if vmin <= t <= vmax]


def q_ticks(vmin: float, vmax: float) -> list[float]:
    start = 3 if vmin < 3 else (6 if vmin <= 5 else int(3 * np.ceil(vmin / 3.0)))
    ticks = list(range(start, int(vmax) + 1, 3))
    return [float(t) for t in ticks if vmin <= t <= vmax]


def wspd_ticks(vmin: float, vmax: float) -> list[float]:
    ticks = list(range(5, int(vmax) + 1, 5))
    return [float(t) for t in ticks if t <= vmax]
