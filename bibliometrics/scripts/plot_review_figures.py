#!/usr/bin/env python3
"""Generate bibliometric figures and summary tables for the CLAMPS review corpus."""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle
from matplotlib.ticker import NullLocator
import numpy as np
import numpy.ma as ma
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clamps_biblio.pdf_use_classifier import classify_pdf_confirmed
from clamps_biblio.nwc_affiliation import NWC_AFFILIATION_CAPTION, NWC_AFFILIATED, NON_AFFILIATED, UNKNOWN
from clamps_biblio.review_metrics_data import (
    AFFILIATION_LABELS,
    DEPLOYMENT_PLATFORMS,
    NO_CAMPAIGN_TAG,
    deployments_by_year_platform,
    deployment_heatmap_platform_cells,
    load_campaign_names,
    load_campaign_review_overrides,
    load_review_frames,
    mention_context_by_paper,
    paper_campaign_labels_adjusted,
)

AFFIL_ORDER = (NWC_AFFILIATED, NON_AFFILIATED, UNKNOWN)
AFFIL_LEGEND_ORDER = (NWC_AFFILIATED, NON_AFFILIATED)

# Generic output filenames (no manuscript figure numbers)
FIG_AFFILIATION = "fig_affiliation_by_year"
FIG_AFFILIATION_DEPLOY = "fig_affiliation_by_year_with_deployments"
FIG_WORK_TYPE_DEPLOY = "fig_work_type_by_year_with_deployments"
FIG_CAMPAIGN = "fig_campaign_by_year"
TABLE_CORPUS_SUMMARY = "table_corpus_summary"
TABLE_IMPACT_SUMMARY = "table_impact_summary"

# Fig. 8: one hue family per evidence tier; affiliation = dark / light shade (NWC, Non-NWC)
TIER_AFFIL_COLORS: list[tuple[str, str, str]] = [
    ("#4A4A4A", "#8A8A8A", "#C4C4C4"),  # all works — manual review (gray)
    ("#7A5C10", "#C9A227", "#E8D48B"),  # published literature — PDF confirmed (gold)
]

TIER_LABELS = [
    "All works",
    "Published literature",
]

TIER_FRAME_KEYS = [
    ("flagged_yd", "All works"),
    ("pdf_confirmed", "Published literature"),
]

DEPLOYMENT_PLATFORM_COLORS = {
    "CLAMPS1": "#841617",  # OU crimson
    "CLAMPS2": "#003087",  # NOAA blue
}
DEPLOYMENT_PLATFORM_LABELS = {
    "CLAMPS1": "C1",
    "CLAMPS2": "C2",
}
DEPLOYMENT_LABEL = "Months deployed"
DEPLOYMENT_LEGEND_LABEL = DEPLOYMENT_LABEL
BAR_ALPHA_WITH_DEPLOYMENTS = 0.78
FIG8_MAX_YEAR = 2026
FIG8_PROVISIONAL_START_YEAR = 2025
FIG8_DIVIDER_AFTER_YEAR = 2024
FIG8_PROVISIONAL_BAR_ALPHA = 0.38
FIG8_PROVISIONAL_LINE_ALPHA = 0.38
FIG8_PROVISIONAL_DEPLOYMENT_MONTHS = 0.5
FIG8_DIVIDER_COLOR = "#D8D8D8"
FIG8_C2_START_YEAR = 2016
DEPLOYMENT_LINE_WIDTH = 3.0

CORPUS_CLASS_ORDER = ("article", "report", "dataset", "thesis")
CORPUS_CLASS_LABELS = {
    "article": "Articles",
    "report": "Reports",
    "dataset": "Datasets",
    "thesis": "Theses",
}
# Per-tier hues (all works = grey family, published literature = gold family)
TIER_TYPE_COLORS: list[dict[str, str]] = [
    {
        "article": "#3D3D3D",
        "report": "#666666",
        "dataset": "#949494",
        "thesis": "#C4C4C4",
    },
    {
        "article": "#7A5C10",
        "report": "#C9A227",
        "dataset": "#E8D48B",
        "thesis": "#F5E6B8",
    },
]
# Single-bar Fig. 8 work-type stack: grey family (articles, theses) + gold family (datasets, reports)
WORK_TYPE_COLORS = {
    "article": TIER_TYPE_COLORS[0]["article"],   # dark grey
    "report": TIER_TYPE_COLORS[1]["report"],     # light gold
    "dataset": TIER_TYPE_COLORS[1]["article"],   # dark gold
    "thesis": TIER_TYPE_COLORS[0]["thesis"],     # light grey
}

# Supp. Fig. S1 — upper totals use Fig. 8 gray; heatmap uses published-literature gold
SUPP_S1_NO_CAMPAIGN_LABEL = "Multi/None"
SUPP_S1_TOTAL_BAR_CMAP = LinearSegmentedColormap.from_list(
    "fig8_gray",
    [TIER_AFFIL_COLORS[0][2], TIER_AFFIL_COLORS[0][1], TIER_AFFIL_COLORS[0][0]],
)
SUPP_S1_HEATMAP_CMAP = LinearSegmentedColormap.from_list(
    "fig8_gold",
    ["#FFF8E7", TIER_AFFIL_COLORS[1][2], TIER_AFFIL_COLORS[1][1], TIER_AFFIL_COLORS[1][0]],
)
SUPP_S1_MIN_YEAR = 2015
SUPP_S1_DEPLOYMENT_OUTLINE_LW = 1.4
SUPP_S1_BAR_LABEL_INSIDE_MIN = 31  # counts >30 inside bar; ≤30 above bar
SUPP_S1_HEATMAP_CELL_FONTSIZE = 8


def _add_supp_s1_deployment_outline(
    ax: plt.Axes,
    row_i: int,
    col_j: int,
    x_half: float,
    platforms: set[str],
) -> None:
    """Draw C1 (crimson), C2 (blue), or split outline for a heatmap cell."""
    x0 = col_j - x_half
    y0 = row_i - x_half
    c1 = DEPLOYMENT_PLATFORM_COLORS["CLAMPS1"]
    c2 = DEPLOYMENT_PLATFORM_COLORS["CLAMPS2"]
    lw = SUPP_S1_DEPLOYMENT_OUTLINE_LW
    has1 = "CLAMPS1" in platforms
    has2 = "CLAMPS2" in platforms

    if has1 and has2:
        xm = x0 + 0.5
        x1 = x0 + 1.0
        y1 = y0 + 1.0
        # Shared outer border; top/bottom split by color, no interior vertical line.
        ax.plot([x0, x0], [y0, y1], color=c1, linewidth=lw, zorder=5, solid_capstyle="butt")
        ax.plot([x0, xm], [y1, y1], color=c1, linewidth=lw, zorder=5, solid_capstyle="butt")
        ax.plot([x0, xm], [y0, y0], color=c1, linewidth=lw, zorder=5, solid_capstyle="butt")
        ax.plot([x1, x1], [y0, y1], color=c2, linewidth=lw, zorder=5, solid_capstyle="butt")
        ax.plot([xm, x1], [y1, y1], color=c2, linewidth=lw, zorder=5, solid_capstyle="butt")
        ax.plot([xm, x1], [y0, y0], color=c2, linewidth=lw, zorder=5, solid_capstyle="butt")
    elif has1:
        ax.add_patch(Rectangle((x0, y0), 1.0, 1.0, fill=False, edgecolor=c1, linewidth=lw, zorder=5))
    elif has2:
        ax.add_patch(Rectangle((x0, y0), 1.0, 1.0, fill=False, edgecolor=c2, linewidth=lw, zorder=5))


def _pchip_endpoint_derivative(h0: float, h1: float, m0: float, m1: float) -> float:
    """Endpoint slope for shape-preserving (PCHIP) cubic Hermite."""
    d = ((2 * h0 + h1) * m0 - h0 * m1) / (h0 + h1)
    if np.sign(d) != np.sign(m0):
        return 0.0
    if np.sign(m0) != np.sign(m1) and abs(d) > abs(3 * m0):
        return 3 * m0
    return d


def _pchip_slopes(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Slopes at knots for PCHIP (local extrema occur only at knots)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(x)
    h = np.diff(x)
    mk = np.diff(y) / h
    dk = np.zeros(n)
    if n == 2:
        dk[0] = mk[0]
        dk[1] = mk[0]
        return dk
    dk[0] = _pchip_endpoint_derivative(h[0], h[1], mk[0], mk[1])
    dk[-1] = _pchip_endpoint_derivative(h[-1], h[-2], mk[-1], mk[-2])
    for k in range(1, n - 1):
        if mk[k - 1] * mk[k] <= 0:
            dk[k] = 0.0
        else:
            w1 = 2 * h[k] + h[k - 1]
            w2 = h[k] + 2 * h[k - 1]
            dk[k] = (w1 + w2) / (w1 / mk[k - 1] + w2 / mk[k])
    return dk


def _pchip_interp(x_knots: np.ndarray, y_knots: np.ndarray, x_eval: np.ndarray) -> np.ndarray:
    """
    Piecewise cubic Hermite (PCHIP) through knots.
    Smooth between years; does not overshoot segment endpoints; extrema at knots only.
    """
    x = np.asarray(x_knots, dtype=float)
    y = np.asarray(y_knots, dtype=float)
    x_eval = np.asarray(x_eval, dtype=float)
    n = len(x) - 1
    if n < 1:
        return np.full_like(x_eval, y[0], dtype=float)

    h = np.diff(x)
    dk = _pchip_slopes(x, y)
    seg = np.searchsorted(x, x_eval, side="right") - 1
    seg = np.clip(seg, 0, n - 1)
    t = (x_eval - x[seg]) / h[seg]
    t2 = t * t
    t3 = t2 * t
    h00 = 2 * t3 - 3 * t2 + 1
    h10 = t3 - 2 * t2 + t
    h01 = -2 * t3 + 3 * t2
    h11 = t3 - t2
    return (
        h00 * y[seg]
        + h10 * h[seg] * dk[seg]
        + h01 * y[seg + 1]
        + h11 * h[seg] * dk[seg + 1]
    )


def _smooth_deployment_curve(x: np.ndarray, y: np.ndarray, n: int = 250) -> tuple[np.ndarray, np.ndarray]:
    """Smooth curve through deployment-month points without inter-year overshoot."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 2:
        return x, y
    x_smooth = np.linspace(x.min(), x.max(), n)
    y_smooth = _pchip_interp(x, y, x_smooth)
    return x_smooth, np.clip(y_smooth, 0, 12)


def _extend_fig8_years(years: list[int]) -> list[int]:
    start = min(years) if years else 2015
    return list(range(start, FIG8_MAX_YEAR + 1))


def _fig8_provisional_mask(years: list[int]) -> np.ndarray:
    return np.array(years) >= FIG8_PROVISIONAL_START_YEAR


def _add_fig8_provisional_divider(ax: plt.Axes, years: list[int]) -> None:
    if FIG8_DIVIDER_AFTER_YEAR in years:
        ax.axvline(
            years.index(FIG8_DIVIDER_AFTER_YEAR) + 0.5,
            color=FIG8_DIVIDER_COLOR,
            linewidth=1.2,
            zorder=1,
        )


def _plot_fig8_bar_stack_layer(
    ax: plt.Axes,
    xpos: np.ndarray,
    years: list[int],
    heights: np.ndarray,
    bottom: np.ndarray,
    width: float,
    color: str,
    *,
    base_alpha: float = BAR_ALPHA_WITH_DEPLOYMENTS,
    zorder: int = 3,
) -> None:
    prov = _fig8_provisional_mask(years)
    conf = ~prov
    kw = dict(width=width, color=color, edgecolor="white", linewidth=0.4, zorder=zorder)
    if conf.any():
        ax.bar(xpos[conf], heights[conf], bottom=bottom[conf], alpha=base_alpha, **kw)
    if prov.any():
        ax.bar(xpos[prov], heights[prov], bottom=bottom[prov], alpha=FIG8_PROVISIONAL_BAR_ALPHA, **kw)


def _style_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def tier_affiliation_counts(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    mapping = {
        TIER_LABELS[0]: frames["flagged_yd"],
        TIER_LABELS[1]: frames["pdf_confirmed"],
    }
    for tier, df in mapping.items():
        for aff in AFFIL_ORDER:
            rows.append({"tier": tier, "affiliation": aff, "count": int((df["affiliation"] == aff).sum())})
    return pd.DataFrame(rows)


def year_tier_affiliation_data(frames: dict[str, pd.DataFrame]) -> tuple[list[int], list[pd.DataFrame], pd.DataFrame]:
    """Build per-year affiliation counts for each evidence tier."""
    years: set[int] = set()
    pivots: list[pd.DataFrame] = []
    long_rows: list[dict] = []

    for frame_key, tier_label in TIER_FRAME_KEYS:
        df = frames[frame_key].copy()
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        df = df[df["year"].notna()].copy()
        df["year"] = df["year"].astype(int)
        years.update(df["year"].unique())

        pivot = (
            df.groupby(["year", "affiliation"])
            .size()
            .unstack(fill_value=0)
            .reindex(columns=list(AFFIL_ORDER), fill_value=0)
        )
        pivots.append(pivot)

    year_list = sorted(years)
    for pivot, (_, tier_label) in zip(pivots, TIER_FRAME_KEYS):
        aligned = pivot.reindex(year_list, fill_value=0)
        for year in year_list:
            for aff in AFFIL_ORDER:
                long_rows.append(
                    {
                        "year": year,
                        "tier": tier_label,
                        "affiliation": aff,
                        "count": int(aligned.loc[year, aff]),
                    }
                )

    return year_list, pivots, pd.DataFrame(long_rows)


def _corpus_class_series(df: pd.DataFrame) -> pd.Series:
    if "corpus_class" in df.columns:
        return df["corpus_class"].astype(str).str.strip().str.lower()
    mapping = {
        "dissertation": "thesis",
        "article": "article",
        "preprint": "article",
        "review": "article",
        "report": "report",
        "dataset": "dataset",
    }
    return df["type"].astype(str).str.strip().str.lower().map(lambda t: mapping.get(t, t))


def year_tier_corpus_type_data(
    frames: dict[str, pd.DataFrame],
) -> tuple[list[int], list[pd.DataFrame], pd.DataFrame]:
    """Build per-year corpus_class counts for each evidence tier."""
    years: set[int] = set()
    pivots: list[pd.DataFrame] = []
    long_rows: list[dict] = []

    for frame_key, tier_label in TIER_FRAME_KEYS:
        df = frames[frame_key].copy()
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        df = df[df["year"].notna()].copy()
        df["year"] = df["year"].astype(int)
        df["corpus_class"] = _corpus_class_series(df)
        years.update(df["year"].unique())

        pivot = (
            df.groupby(["year", "corpus_class"])
            .size()
            .unstack(fill_value=0)
            .reindex(columns=list(CORPUS_CLASS_ORDER), fill_value=0)
        )
        pivots.append(pivot)

    year_list = sorted(years)
    for pivot, (_, tier_label) in zip(pivots, TIER_FRAME_KEYS):
        aligned = pivot.reindex(year_list, fill_value=0)
        for year in year_list:
            for cls in CORPUS_CLASS_ORDER:
                long_rows.append(
                    {
                        "year": year,
                        "tier": tier_label,
                        "corpus_class": cls,
                        "count": int(aligned.loc[year, cls]),
                    }
                )

    return year_list, pivots, pd.DataFrame(long_rows)


def _fig8_deploy_aligned_for_display(
    deploy_aligned: pd.DataFrame,
    years: list[int],
) -> pd.DataFrame:
    """Observed months through 2024; provisional placeholder (~0.5 mo) for 2025+."""
    out = deploy_aligned.reindex(years, fill_value=0).astype(float).copy()
    for year in years:
        if year >= FIG8_PROVISIONAL_START_YEAR:
            for platform in DEPLOYMENT_PLATFORMS:
                out.loc[year, platform] = FIG8_PROVISIONAL_DEPLOYMENT_MONTHS
    return out


def _plot_deployment_line_segment(
    ax2: plt.Axes,
    x_line: np.ndarray,
    y_line: np.ndarray,
    color: str,
    alpha: float,
) -> None:
    if len(x_line) == 0:
        return
    marker_kw = dict(
        linestyle="none",
        color=color,
        marker="o",
        markersize=5,
        markerfacecolor=color,
        markeredgecolor="white",
        markeredgewidth=0.6,
        alpha=alpha,
        zorder=3,
    )
    if len(x_line) < 2:
        ax2.plot(x_line, y_line, **marker_kw)
        return
    x_smooth, y_smooth = _smooth_deployment_curve(x_line, y_line)
    ax2.plot(
        x_smooth,
        y_smooth,
        color=color,
        linewidth=DEPLOYMENT_LINE_WIDTH,
        alpha=alpha,
        zorder=2,
    )
    ax2.plot(x_line, y_line, **marker_kw)


def _plot_deployment_lines(
    ax2: plt.Axes,
    deploy_aligned: pd.DataFrame,
    years: list[int],
    x_groups: np.ndarray,
) -> None:
    year_arr = np.array(years)
    for platform in DEPLOYMENT_PLATFORMS:
        y_vals = deploy_aligned[platform].to_numpy(dtype=float)
        color = DEPLOYMENT_PLATFORM_COLORS[platform]
        platform_mask = np.ones(len(years), dtype=bool)
        if platform == "CLAMPS2":
            platform_mask = year_arr >= FIG8_C2_START_YEAR

        conf_mask = platform_mask & (year_arr < FIG8_PROVISIONAL_START_YEAR)
        # Include last observed year so the faded tail connects to the main curve.
        tail_mask = platform_mask & (year_arr >= FIG8_DIVIDER_AFTER_YEAR)

        _plot_deployment_line_segment(
            ax2,
            x_groups[conf_mask],
            y_vals[conf_mask],
            color,
            BAR_ALPHA_WITH_DEPLOYMENTS,
        )
        if tail_mask.any() and (year_arr >= FIG8_PROVISIONAL_START_YEAR).any():
            _plot_deployment_line_segment(
                ax2,
                x_groups[tail_mask],
                y_vals[tail_mask],
                color,
                FIG8_PROVISIONAL_LINE_ALPHA,
            )


def _add_fig8_type_key(ax: plt.Axes, *, deployment_lines: bool = False) -> None:
    """Legend for work-type stacked bars (+ optional deployment lines)."""
    from matplotlib.patches import Rectangle

    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ax_px = ax.get_window_extent()

    fontsize = 9
    swatch_pt = 35.0
    swatch_h = swatch_pt / ax_px.height
    swatch_w = swatch_pt / ax_px.width
    row_gap_pt = 8.0
    row_gap = row_gap_pt / ax_px.height
    label_to_grid_pt = 10.0
    header_to_swatch_pt = 6.0
    header_pad_pt = 5.0
    pad_x_pt, pad_top_pt, pad_bottom_pt = 3.0, 10.0, 3.0
    pad_x = pad_x_pt / ax_px.width
    pad_top = pad_top_pt / ax_px.height
    pad_bottom = pad_bottom_pt / ax_px.height
    text_kw = {"fontsize": fontsize, "linespacing": 0.9, "transform": ax.transAxes}

    tier_labels = ["All works", "Published\nliterature"]
    if deployment_lines:
        tier_labels.append(DEPLOYMENT_LABEL)
    type_labels = [CORPUS_CLASS_LABELS[c] for c in CORPUS_CLASS_ORDER]
    n_tiers = len(tier_labels)
    n_cols = len(CORPUS_CLASS_ORDER)

    def _text_px(text: str) -> tuple[float, float]:
        tmp = ax.text(0, 0, text, transform=ax.transAxes, fontsize=fontsize, linespacing=0.9)
        bb = tmp.get_window_extent(renderer)
        tmp.remove()
        return bb.width, bb.height

    max_tier_label_w_px = max(_text_px(label)[0] for label in tier_labels)
    col_label_w_px = [_text_px(label)[0] for label in type_labels]
    header_h_px = max(_text_px(label)[1] for label in type_labels)
    min_col_gap_pt = max(col_label_w_px) / 2 + min(col_label_w_px) / 2 + header_pad_pt - swatch_pt
    col_gap_pt = max(10.0, min_col_gap_pt)
    col_gap = col_gap_pt / ax_px.width

    x_grid = 0.118
    tier_label_x = x_grid - label_to_grid_pt / ax_px.width
    y_top = 0.945
    label_y = y_top - 1.0 / ax_px.height
    first_row_y = label_y - header_h_px / ax_px.height - header_to_swatch_pt / ax_px.height - swatch_h
    row_ys = [first_row_y - i * (swatch_h + row_gap) for i in range(n_tiers)]

    grid_right = x_grid + n_cols * swatch_w + (n_cols - 1) * col_gap
    bg_left = tier_label_x - max_tier_label_w_px / ax_px.width - pad_x
    bg_right = grid_right + pad_x
    bg_bottom = row_ys[-1] - pad_bottom
    bg_top = y_top + pad_top

    ax.add_patch(
        Rectangle(
            (bg_left, bg_bottom),
            bg_right - bg_left,
            bg_top - bg_bottom,
            transform=ax.transAxes,
            facecolor="white",
            edgecolor="none",
            zorder=20,
            clip_on=False,
        )
    )

    for col_idx, label in enumerate(type_labels):
        cx = x_grid + col_idx * (swatch_w + col_gap) + swatch_w / 2
        ax.text(cx, label_y, label, ha="center", va="top", zorder=22, **text_kw)

    if deployment_lines and n_tiers > 2:
        sep_y = row_ys[1] - row_gap / 2
        ax.plot(
            [bg_left, bg_right],
            [sep_y, sep_y],
            transform=ax.transAxes,
            color="#999999",
            linewidth=0.9,
            zorder=21,
            clip_on=False,
        )

    for tier_idx, label in enumerate(tier_labels):
        row_y = row_ys[tier_idx]
        ax.text(
            tier_label_x,
            row_y + swatch_h / 2,
            label,
            ha="right",
            va="center",
            zorder=22,
            **text_kw,
        )
        if deployment_lines and tier_idx == n_tiers - 1:
            line_offset = 5.0 / ax_px.height
            text_offset = 4.0 / ax_px.height
            for aff_idx, platform in enumerate(DEPLOYMENT_PLATFORMS):
                x0 = x_grid + aff_idx * (swatch_w + col_gap)
                x1 = x0 + swatch_w
                mid_y = row_y + swatch_h / 2
                line_y = mid_y - line_offset
                text_y = mid_y + text_offset
                color = DEPLOYMENT_PLATFORM_COLORS[platform]
                ax.plot(
                    [x0 + swatch_w * 0.1, x1 - swatch_w * 0.1],
                    [line_y, line_y],
                    transform=ax.transAxes,
                    color=color,
                    linewidth=3.2,
                    solid_capstyle="round",
                    zorder=22,
                    clip_on=False,
                )
                ax.plot(
                    [x0 + swatch_w * 0.5],
                    [line_y],
                    transform=ax.transAxes,
                    color=color,
                    linewidth=0,
                    marker="o",
                    markersize=4.5,
                    zorder=23,
                    clip_on=False,
                )
                ax.text(
                    x0 + swatch_w / 2,
                    text_y,
                    DEPLOYMENT_PLATFORM_LABELS[platform],
                    ha="center",
                    va="center",
                    fontsize=9,
                    fontweight="bold",
                    color=color,
                    transform=ax.transAxes,
                    zorder=24,
                )
        elif tier_idx < len(TIER_TYPE_COLORS):
            palette = TIER_TYPE_COLORS[tier_idx]
            for col_idx, cls in enumerate(CORPUS_CLASS_ORDER):
                ax.add_patch(
                    Rectangle(
                        (x_grid + col_idx * (swatch_w + col_gap), row_y),
                        swatch_w,
                        swatch_h,
                        transform=ax.transAxes,
                        facecolor=palette[cls],
                        edgecolor="none",
                        zorder=21,
                        clip_on=False,
                    )
                )


def _align_fig8_year_axes(
    years: list[int],
    pivots: list[pd.DataFrame],
    long_df: pd.DataFrame,
    deploy_pivot: pd.DataFrame,
) -> tuple[list[int], list[pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    deploy_aligned = deploy_pivot.reindex(years, fill_value=0).astype(int)
    all_years = sorted(set(years) | set(deploy_pivot.index.astype(int)))
    if all_years != years:
        years = all_years
        pivots = [p.reindex(years, fill_value=0) for p in pivots]
        deploy_aligned = deploy_pivot.reindex(years, fill_value=0).astype(int)
        long_rows = []
        for pivot, (_, tier_label) in zip(pivots, TIER_FRAME_KEYS):
            for year in years:
                for cls in CORPUS_CLASS_ORDER:
                    long_rows.append(
                        {
                            "year": year,
                            "tier": tier_label,
                            "corpus_class": cls,
                            "count": int(pivot.loc[year, cls]) if cls in pivot.columns else 0,
                        }
                    )
        long_df = pd.DataFrame(long_rows)

    years = _extend_fig8_years(years)
    pivots = [p.reindex(years, fill_value=0) for p in pivots]
    deploy_aligned = deploy_pivot.reindex(years, fill_value=0).astype(int)
    long_rows = []
    for pivot, (_, tier_label) in zip(pivots, TIER_FRAME_KEYS):
        aligned = pivot.reindex(years, fill_value=0)
        for year in years:
            for cls in CORPUS_CLASS_ORDER:
                long_rows.append(
                    {
                        "year": year,
                        "tier": tier_label,
                        "corpus_class": cls,
                        "count": int(aligned.loc[year, cls]) if cls in aligned.columns else 0,
                    }
                )
    long_df = pd.DataFrame(long_rows)
    return years, pivots, long_df, deploy_aligned


def year_corpus_type_counts(df: pd.DataFrame) -> tuple[list[int], pd.DataFrame, pd.DataFrame]:
    """Per-year counts by corpus_class for the full review corpus."""
    work = df.copy()
    work["year"] = pd.to_numeric(work["year"], errors="coerce")
    work = work[work["year"].notna()].copy()
    work["year"] = work["year"].astype(int)
    work["corpus_class"] = _corpus_class_series(work)

    pivot = (
        work.groupby(["year", "corpus_class"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=list(CORPUS_CLASS_ORDER), fill_value=0)
    )
    years = sorted(pivot.index.astype(int))
    pivot = pivot.reindex(years, fill_value=0)

    long_rows = []
    for year in years:
        for cls in CORPUS_CLASS_ORDER:
            long_rows.append(
                {"year": year, "corpus_class": cls, "count": int(pivot.loc[year, cls])}
            )
    return years, pivot, pd.DataFrame(long_rows)


def _align_single_year_pivot(
    years: list[int],
    pivot: pd.DataFrame,
    long_df: pd.DataFrame,
    deploy_pivot: pd.DataFrame,
) -> tuple[list[int], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    all_years = sorted(set(years) | set(deploy_pivot.index.astype(int)))
    if all_years != years:
        years = all_years
        pivot = pivot.reindex(years, fill_value=0)
        long_rows = []
        for year in years:
            for cls in CORPUS_CLASS_ORDER:
                long_rows.append(
                    {"year": year, "corpus_class": cls, "count": int(pivot.loc[year, cls])}
                )
        long_df = pd.DataFrame(long_rows)

    years = _extend_fig8_years(years)
    pivot = pivot.reindex(years, fill_value=0)
    deploy_aligned = deploy_pivot.reindex(years, fill_value=0).astype(int)
    long_rows = []
    for year in years:
        for cls in CORPUS_CLASS_ORDER:
            long_rows.append(
                {"year": year, "corpus_class": cls, "count": int(pivot.loc[year, cls])}
            )
    long_df = pd.DataFrame(long_rows)
    return years, pivot, long_df, deploy_aligned


def _rebuild_affiliation_long_df(years: list[int], pivots: list[pd.DataFrame]) -> pd.DataFrame:
    long_rows = []
    for pivot, (_, tier_label) in zip(pivots, TIER_FRAME_KEYS):
        aligned = pivot.reindex(years, fill_value=0)
        for year in years:
            for aff in AFFIL_ORDER:
                long_rows.append(
                    {
                        "year": year,
                        "tier": tier_label,
                        "affiliation": aff,
                        "count": int(aligned.loc[year, aff]),
                    }
                )
    return pd.DataFrame(long_rows)


def _draw_deployment_line_key(
    ax: plt.Axes,
    *,
    x_grid: float,
    col_gap: float,
    swatch_w: float,
    row_y: float,
    swatch_h: float,
    ax_px_height: float,
    fontsize: int = 8,
) -> None:
    """C1/C2 line swatches in the first two grid columns; labels below the lines."""
    line_y = row_y + swatch_h * 0.62
    label_y = row_y - 6.0 / ax_px_height
    for aff_idx, platform in enumerate(DEPLOYMENT_PLATFORMS):
        x0 = x_grid + aff_idx * (swatch_w + col_gap)
        x1 = x0 + swatch_w
        color = DEPLOYMENT_PLATFORM_COLORS[platform]
        ax.plot(
            [x0 + swatch_w * 0.12, x1 - swatch_w * 0.12],
            [line_y, line_y],
            transform=ax.transAxes,
            color=color,
            linewidth=3.0,
            solid_capstyle="round",
            zorder=22,
            clip_on=False,
        )
        ax.plot(
            [x0 + swatch_w * 0.5],
            [line_y],
            transform=ax.transAxes,
            color=color,
            linewidth=0,
            marker="o",
            markersize=4.5,
            zorder=23,
            clip_on=False,
        )
        ax.text(
            x0 + swatch_w / 2,
            label_y,
            DEPLOYMENT_PLATFORM_LABELS[platform],
            ha="center",
            va="top",
            fontsize=fontsize,
            fontweight="bold",
            color=color,
            transform=ax.transAxes,
            zorder=24,
        )


def _add_work_type_key(ax: plt.Axes) -> None:
    """Legend: work-type swatches (label left, swatch right) and deployment lines."""
    from matplotlib.patches import Rectangle

    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ax_px = ax.get_window_extent()

    fontsize = 8
    swatch_pt = 22.0
    swatch_h = swatch_pt / ax_px.height
    swatch_w = swatch_pt / ax_px.width
    row_gap_pt = 7.0
    row_gap = row_gap_pt / ax_px.height
    label_to_swatch_pt = 8.0
    pad_x_pt, pad_top_pt, pad_bottom_pt = 4.0, 8.0, 4.0
    pad_x = pad_x_pt / ax_px.width
    pad_top = pad_top_pt / ax_px.height
    pad_bottom = pad_bottom_pt / ax_px.height
    text_kw = {"fontsize": fontsize, "transform": ax.transAxes}

    def _text_px(text: str) -> tuple[float, float]:
        tmp = ax.text(0, 0, text, transform=ax.transAxes, fontsize=fontsize)
        bb = tmp.get_window_extent(renderer)
        tmp.remove()
        return bb.width, bb.height

    type_items = [(CORPUS_CLASS_LABELS[c], c) for c in CORPUS_CLASS_ORDER]
    label_w_px = max(_text_px(label)[0] for label, _ in type_items)
    row_h_px = max(swatch_pt, _text_px("Ag")[1])

    label_x = 0.118
    swatch_x = label_x + label_w_px / ax_px.width + label_to_swatch_pt / ax_px.width
    y_top = 0.945
    first_row_y = y_top - 1.0 / ax_px.height - row_h_px / ax_px.height

    row_ys = [first_row_y - i * (row_h_px / ax_px.height + row_gap) for i in range(len(type_items))]
    sep_y = row_ys[-1] - row_gap - 2.0 / ax_px.height
    dep_row_y = sep_y - row_gap - row_h_px / ax_px.height

    bg_left = label_x - pad_x
    bg_right = swatch_x + 2 * swatch_w + 20.0 / ax_px.width + pad_x
    bg_bottom = dep_row_y - pad_bottom - 14.0 / ax_px.height
    bg_top = y_top + pad_top

    ax.add_patch(
        Rectangle(
            (bg_left, bg_bottom),
            bg_right - bg_left,
            bg_top - bg_bottom,
            transform=ax.transAxes,
            facecolor="white",
            edgecolor="none",
            zorder=20,
            clip_on=False,
        )
    )

    for (label, cls), row_y in zip(type_items, row_ys):
        mid_y = row_y + (row_h_px / ax_px.height) / 2
        ax.text(label_x, mid_y, label, ha="left", va="center", zorder=22, **text_kw)
        ax.add_patch(
            Rectangle(
                (swatch_x, row_y + (row_h_px / ax_px.height - swatch_h) / 2),
                swatch_w,
                swatch_h,
                transform=ax.transAxes,
                facecolor=WORK_TYPE_COLORS[cls],
                edgecolor="none",
                zorder=21,
                clip_on=False,
            )
        )

    ax.plot(
        [bg_left, bg_right],
        [sep_y, sep_y],
        transform=ax.transAxes,
        color="#999999",
        linewidth=0.9,
        zorder=21,
        clip_on=False,
    )

    dep_mid_y = dep_row_y + (row_h_px / ax_px.height) / 2
    ax.text(label_x, dep_mid_y, DEPLOYMENT_LABEL, ha="left", va="center", zorder=22, **text_kw)
    _draw_deployment_line_key(
        ax,
        x_grid=swatch_x,
        col_gap=swatch_w + 14.0 / ax_px.width,
        swatch_w=swatch_w,
        row_y=dep_row_y + (row_h_px / ax_px.height - swatch_h) / 2,
        swatch_h=swatch_h,
        ax_px_height=ax_px.height,
        fontsize=fontsize,
    )


def plot_fig8_work_type_with_deployments(
    frames: dict[str, pd.DataFrame],
    deploy_pivot: pd.DataFrame,
    out_dir: Path,
) -> None:
    """One stacked bar per year (work type) with C1/C2 deployment-month lines."""
    corpus = frames.get("review_corpus", frames["flagged_yd"])
    years, pivot, long_df = year_corpus_type_counts(corpus)
    years, pivot, long_df, deploy_aligned = _align_single_year_pivot(
        years, pivot, long_df, deploy_pivot
    )
    deploy_aligned = _fig8_deploy_aligned_for_display(deploy_aligned, years)

    deploy_rows = []
    for year in years:
        for platform in DEPLOYMENT_PLATFORMS:
            deploy_rows.append(
                {
                    "year": year,
                    "platform": platform,
                    "months": float(deploy_aligned.loc[year, platform]),
                }
            )
    export_df = pd.concat([long_df, pd.DataFrame(deploy_rows)], ignore_index=True)
    export_df.to_csv(out_dir / f"{FIG_WORK_TYPE_DEPLOY}_data.csv", index=False)
    deploy_aligned.to_csv(out_dir / f"{FIG_WORK_TYPE_DEPLOY}_deployment_months_by_year.csv")

    n_years = len(years)
    bar_width = 0.72

    fig, ax = plt.subplots(figsize=(max(10, n_years * 0.95), 5.5))
    ax2 = ax.twinx()
    ax2.set_zorder(1)
    ax.set_zorder(2)
    ax.patch.set_visible(False)

    x_groups = np.arange(n_years)
    _add_fig8_provisional_divider(ax, years)
    _plot_deployment_lines(ax2, deploy_aligned, years, x_groups)

    aligned = pivot.reindex(years, fill_value=0)
    bottom = np.zeros(n_years)
    for cls in CORPUS_CLASS_ORDER:
        vals = aligned[cls].to_numpy() if cls in aligned.columns else np.zeros(n_years)
        _plot_fig8_bar_stack_layer(
            ax,
            x_groups,
            years,
            vals,
            bottom,
            bar_width,
            WORK_TYPE_COLORS[cls],
        )
        bottom += vals

    ax.set_xticks(x_groups)
    ax.set_xticklabels(years)
    ax.set_xlabel("Publication year")
    ax.set_ylabel("Count")
    ax2.set_ylabel("Months deployed")
    ax2.set_ylim(0, 12)
    ax2.set_yticks(range(0, 13, 2))

    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color="#DDDDDD", linestyle="-", linewidth=0.7, zorder=0)
    ax.xaxis.grid(False)
    ax2.grid(False)

    _style_axes(ax)
    ax2.spines["top"].set_visible(False)
    _add_work_type_key(ax)

    for ext in ("png", "pdf"):
        fig.canvas.draw()
        fig.savefig(out_dir / f"{FIG_WORK_TYPE_DEPLOY}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def export_unknown_affiliation(frames: dict[str, pd.DataFrame], out_dir: Path) -> None:
    """Export papers with unknown NWC affiliation for manual institution fixes."""
    rows: list[dict] = []
    seen: set[str] = set()
    for frame_key, tier_label in TIER_FRAME_KEYS:
        df = frames[frame_key]
        unk = df[df["affiliation"] == UNKNOWN]
        for _, r in unk.iterrows():
            oid = str(r.get("openalex_id", ""))
            if oid in seen:
                continue
            seen.add(oid)
            rows.append(
                {
                    "evidence_tier": tier_label,
                    "expectation": r.get("expectation", ""),
                    "year": r.get("year", ""),
                    "openalex_id": oid,
                    "doi": r.get("doi", ""),
                    "title": r.get("title", ""),
                    "type": r.get("type", ""),
                    "institutions": r.get("institutions", ""),
                    "discovery_source": r.get("discovery_source", ""),
                    "discovery_match": r.get("discovery_match", ""),
                    "metadata_matched_terms": r.get("metadata_matched_terms", ""),
                    "pdf_scan_status": r.get("pdf_scan_status", ""),
                    "match_strength": r.get("match_strength", ""),
                    "matched_terms": r.get("matched_terms", ""),
                }
            )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["year", "title"], ascending=[False, True])
    else:
        out = pd.DataFrame(
            columns=[
                "evidence_tier",
                "expectation",
                "year",
                "openalex_id",
                "doi",
                "title",
                "type",
                "institutions",
                "discovery_source",
                "discovery_match",
                "metadata_matched_terms",
                "pdf_scan_status",
                "match_strength",
                "matched_terms",
            ]
        )
    out.to_csv(out_dir / "list_unknown_affiliation.csv", index=False)


def _add_fig8_color_key(ax: plt.Axes, *, deployment_lines: bool = False) -> None:
    """Color key in upper-left; swatches sized in points for uniform squares."""
    from matplotlib.patches import Rectangle

    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ax_px = ax.get_window_extent()

    fontsize = 9
    swatch_pt = 35.0
    swatch_h = swatch_pt / ax_px.height
    swatch_w = swatch_pt / ax_px.width
    row_gap_pt = 8.0
    row_gap = row_gap_pt / ax_px.height
    label_to_grid_pt = 10.0
    header_to_swatch_pt = 6.0
    header_pad_pt = 5.0
    pad_x_pt, pad_top_pt, pad_bottom_pt = 3.0, 10.0, 3.0
    pad_x = pad_x_pt / ax_px.width
    pad_top = pad_top_pt / ax_px.height
    pad_bottom = pad_bottom_pt / ax_px.height
    text_kw = {"fontsize": fontsize, "linespacing": 0.9, "transform": ax.transAxes}

    tier_labels = ["All works", "Published\nliterature"]
    if deployment_lines:
        tier_labels.append(DEPLOYMENT_LABEL)
    affil_labels = ["NWC", "Other"]
    n_tiers = len(tier_labels)
    n_cols = len(AFFIL_LEGEND_ORDER)

    def _text_px(text: str) -> tuple[float, float]:
        tmp = ax.text(0, 0, text, transform=ax.transAxes, fontsize=fontsize, linespacing=0.9)
        bb = tmp.get_window_extent(renderer)
        tmp.remove()
        return bb.width, bb.height

    max_tier_label_w_px = max(_text_px(label)[0] for label in tier_labels)
    affil_label_w_px = [_text_px(label)[0] for label in affil_labels]
    header_h_px = max(_text_px(label)[1] for label in affil_labels)
    min_col_gap_pt = affil_label_w_px[0] / 2 + affil_label_w_px[1] / 2 + header_pad_pt - swatch_pt
    col_gap_pt = max(14.0, min_col_gap_pt)
    col_gap = col_gap_pt / ax_px.width

    x_grid = 0.118
    tier_label_x = x_grid - label_to_grid_pt / ax_px.width
    y_top = 0.945
    label_y = y_top - 1.0 / ax_px.height
    first_row_y = label_y - header_h_px / ax_px.height - header_to_swatch_pt / ax_px.height - swatch_h
    row_ys = [first_row_y - i * (swatch_h + row_gap) for i in range(n_tiers)]

    grid_right = x_grid + n_cols * swatch_w + (n_cols - 1) * col_gap
    bg_left = tier_label_x - max_tier_label_w_px / ax_px.width - pad_x
    bg_right = grid_right + pad_x
    deploy_label_extra = (14.0 / ax_px.height) if deployment_lines else 0.0
    bg_bottom = row_ys[-1] - pad_bottom - deploy_label_extra
    bg_top = y_top + pad_top

    ax.add_patch(
        Rectangle(
            (bg_left, bg_bottom),
            bg_right - bg_left,
            bg_top - bg_bottom,
            transform=ax.transAxes,
            facecolor="white",
            edgecolor="none",
            zorder=20,
            clip_on=False,
        )
    )

    for aff_idx, label in enumerate(affil_labels):
        cx = x_grid + aff_idx * (swatch_w + col_gap) + swatch_w / 2
        ax.text(cx, label_y, label, ha="center", va="top", zorder=22, **text_kw)

    if deployment_lines and n_tiers > 2:
        sep_y = row_ys[1] - row_gap / 2
        ax.plot(
            [bg_left, bg_right],
            [sep_y, sep_y],
            transform=ax.transAxes,
            color="#999999",
            linewidth=0.9,
            zorder=21,
            clip_on=False,
        )

    for tier_idx, label in enumerate(tier_labels):
        row_y = row_ys[tier_idx]
        ax.text(
            tier_label_x,
            row_y + swatch_h / 2,
            label,
            ha="right",
            va="center",
            zorder=22,
            **text_kw,
        )
        if deployment_lines and tier_idx == n_tiers - 1:
            _draw_deployment_line_key(
                ax,
                x_grid=x_grid,
                col_gap=col_gap,
                swatch_w=swatch_w,
                row_y=row_y,
                swatch_h=swatch_h,
                ax_px_height=ax_px.height,
                fontsize=fontsize,
            )
        else:
            for aff_idx in range(n_cols):
                ax.add_patch(
                    Rectangle(
                        (x_grid + aff_idx * (swatch_w + col_gap), row_y),
                        swatch_w,
                        swatch_h,
                        transform=ax.transAxes,
                        facecolor=TIER_AFFIL_COLORS[tier_idx][aff_idx],
                        edgecolor="none",
                        zorder=21,
                        clip_on=False,
                    )
                )


def plot_fig8(frames: dict[str, pd.DataFrame], tier_df: pd.DataFrame, out_dir: Path) -> None:
    """
    Fig. 8 — per publication year, two stacked bars (all works Y/D, published literature PDF-confirmed)
    with NWC / Non-NWC stacks.
    """
    years, pivots, long_df = year_tier_affiliation_data(frames)
    years = _extend_fig8_years(years)
    pivots = [p.reindex(years, fill_value=0) for p in pivots]
    long_df = _rebuild_affiliation_long_df(years, pivots)
    long_df.to_csv(out_dir / f"{FIG_AFFILIATION}_data.csv", index=False)
    tier_df.to_csv(out_dir / f"{FIG_AFFILIATION}_totals_by_tier.csv", index=False)

    n_years = len(years)
    n_tiers = len(TIER_FRAME_KEYS)
    group_width = 0.72
    bar_width = group_width / n_tiers

    fig, ax = plt.subplots(figsize=(max(10, n_years * 0.95), 5.5))
    x_groups = np.arange(n_years)
    _add_fig8_provisional_divider(ax, years)

    for tier_idx, pivot in enumerate(pivots):
        aligned = pivot.reindex(years, fill_value=0)
        xpos = x_groups - group_width / 2 + bar_width / 2 + tier_idx * bar_width
        bottom = np.zeros(n_years)
        tier_colors = TIER_AFFIL_COLORS[tier_idx]
        for aff_idx, aff in enumerate(AFFIL_LEGEND_ORDER):
            vals = aligned[aff].to_numpy()
            _plot_fig8_bar_stack_layer(
                ax,
                xpos,
                years,
                vals,
                bottom,
                bar_width,
                tier_colors[aff_idx],
                base_alpha=1.0,
            )
            bottom += vals

    ax.set_xticks(x_groups)
    ax.set_xticklabels(years)
    ax.set_xlabel("Publication year")
    ax.set_ylabel("Number of works")
    ax.set_title(
        "Fig. 8. CLAMPS works by publication year, screening tier, and NWC affiliation"
    )

    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color="#DDDDDD", linestyle="-", linewidth=0.7, zorder=0)
    ax.xaxis.grid(False)

    _style_axes(ax)
    _add_fig8_color_key(ax)
    for ext in ("png", "pdf"):
        fig.canvas.draw()
        fig.savefig(out_dir / f"{FIG_AFFILIATION}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_fig8_with_deployments(
    frames: dict[str, pd.DataFrame],
    tier_df: pd.DataFrame,
    deploy_pivot: pd.DataFrame,
    out_dir: Path,
) -> None:
    """
    Fig. 8 variant — affiliation bars with C1/C2 deployment-month lines on a twin y-axis (0–12).
    """
    years, pivots, long_df = year_tier_affiliation_data(frames)
    deploy_aligned = deploy_pivot.reindex(years, fill_value=0).astype(int)

    # Include deployment-only years (e.g. 2015 PECAN) on the x-axis.
    all_years = sorted(set(years) | set(deploy_pivot.index.astype(int)))
    if all_years != years:
        years = all_years
        pivots = [p.reindex(years, fill_value=0) for p in pivots]
        deploy_aligned = deploy_pivot.reindex(years, fill_value=0).astype(int)
        long_rows = []
        for pivot, (_, tier_label) in zip(pivots, TIER_FRAME_KEYS):
            for year in years:
                for aff in AFFIL_ORDER:
                    long_rows.append(
                        {"year": year, "tier": tier_label, "affiliation": aff, "count": int(pivot.loc[year, aff])}
                    )
        long_df = pd.DataFrame(long_rows)

    years = _extend_fig8_years(years)
    pivots = [p.reindex(years, fill_value=0) for p in pivots]
    deploy_aligned = _fig8_deploy_aligned_for_display(
        deploy_pivot.reindex(years, fill_value=0), years
    )
    long_df = _rebuild_affiliation_long_df(years, pivots)

    deploy_rows = []
    for year in years:
        for platform in DEPLOYMENT_PLATFORMS:
            deploy_rows.append(
                {
                    "year": year,
                    "tier": DEPLOYMENT_LABEL,
                    "platform": platform,
                    "months": float(deploy_aligned.loc[year, platform]),
                }
            )
    export_df = pd.concat([long_df, pd.DataFrame(deploy_rows)], ignore_index=True)
    export_df.to_csv(out_dir / f"{FIG_AFFILIATION_DEPLOY}_data.csv", index=False)
    tier_df.to_csv(out_dir / f"{FIG_AFFILIATION_DEPLOY}_totals_by_tier.csv", index=False)
    deploy_aligned.to_csv(out_dir / f"{FIG_AFFILIATION_DEPLOY}_deployment_months_by_year.csv")

    n_years = len(years)
    n_tiers = len(TIER_FRAME_KEYS)
    group_width = 0.72
    bar_width = group_width / n_tiers

    fig, ax = plt.subplots(figsize=(max(10, n_years * 0.95), 5.5))
    ax2 = ax.twinx()
    ax2.set_zorder(1)
    ax.set_zorder(2)
    ax.patch.set_visible(False)

    x_groups = np.arange(n_years)
    _add_fig8_provisional_divider(ax, years)
    _plot_deployment_lines(ax2, deploy_aligned, years, x_groups)

    for tier_idx, pivot in enumerate(pivots):
        aligned = pivot.reindex(years, fill_value=0)
        xpos = x_groups - group_width / 2 + bar_width / 2 + tier_idx * bar_width
        bottom = np.zeros(n_years)
        tier_colors = TIER_AFFIL_COLORS[tier_idx]
        for aff_idx, aff in enumerate(AFFIL_LEGEND_ORDER):
            vals = aligned[aff].to_numpy()
            _plot_fig8_bar_stack_layer(
                ax,
                xpos,
                years,
                vals,
                bottom,
                bar_width,
                tier_colors[aff_idx],
            )
            bottom += vals

    ax.set_xticks(x_groups)
    ax.set_xticklabels(years)
    ax.set_xlabel("Publication year")
    ax.set_ylabel("Count")
    ax2.set_ylabel("Months deployed")
    ax2.set_ylim(0, 12)
    ax2.set_yticks(range(0, 13, 2))

    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color="#DDDDDD", linestyle="-", linewidth=0.7, zorder=0)
    ax.xaxis.grid(False)
    ax2.grid(False)

    _style_axes(ax)
    ax2.spines["top"].set_visible(False)

    _add_fig8_color_key(ax, deployment_lines=True)
    for ext in ("png", "pdf"):
        fig.canvas.draw()
        fig.savefig(out_dir / f"{FIG_AFFILIATION_DEPLOY}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _affil_counts(df: pd.DataFrame) -> dict[str, int | str]:
    """NWC vs non-NWC counts (unknown already folded into non-NWC in enrich())."""
    return {
        "nwc_affiliated": int((df["affiliation"] == NWC_AFFILIATED).sum()),
        "non_affiliated": int((df["affiliation"] == NON_AFFILIATED).sum()),
        "total": len(df),
    }


def build_table_x(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Corpus summary table for the review paper (counts by subset).
    Does not include legacy citation-network rows (Wagner/Bell seeds).
    """
    all_works = frames["flagged_yd"]
    pub = frames["pdf_confirmed"]
    peer = pub[pub["is_peer_reviewed"]]
    theses = all_works[all_works["corpus_class"] == "thesis"]
    datasets = all_works[all_works["corpus_class"] == "dataset"]

    def row(metric: str, df: pd.DataFrame, notes: str = "") -> dict:
        return {"metric": metric, "notes": notes, **_affil_counts(df)}

    rows: list[dict] = [
        row("Full review corpus", all_works, "726 works; all inclusion streams"),
        row("Articles + reports", pub, "Publication-type subset"),
        row(
            "Peer-reviewed articles & review papers",
            peer,
            "OpenAlex types article/review/letter; excludes peer-review comments",
        ),
        row("Theses & dissertations", theses, "Manual acceptance via Channel H/F"),
        {
            "metric": "All datasets",
            "total": len(datasets),
            "nwc_affiliated": "",
            "non_affiliated": "",
            "notes": "107 validated deposits; affiliation not applied",
        },
    ]
    return pd.DataFrame(rows)


def build_table_y(
    frames: dict[str, pd.DataFrame],
    use_classified: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Impact metrics: peer-reviewed counts, PDF use tiers, and theses."""
    hc = frames["high_confidence"]
    pdf = frames["pdf_confirmed"]
    peer_pdf = pdf[pdf["is_peer_reviewed"]]
    theses_pdf = pdf[pdf["is_thesis"]]
    theses_hc = hc[hc["is_thesis"]]

    def row(metric: str, df: pd.DataFrame, notes: str) -> dict:
        counts = _affil_counts(df)
        return {
            "impact_metric": metric,
            "count": counts["total"],
            "nwc_affiliated": counts["nwc_affiliated"],
            "non_affiliated": counts["non_affiliated"],
            "notes": notes,
        }

    use_rows: list[dict] = []
    if use_classified is not None and not use_classified.empty:
        substantive = use_classified[
            use_classified["use_tier"].isin([1, 2]) & (use_classified["is_peer_reviewed"] == True)  # noqa: E712
        ]
        tier1 = use_classified[
            (use_classified["use_tier"] == 1) & (use_classified["is_peer_reviewed"] == True)  # noqa: E712
        ]
        excluded = use_classified[use_classified["use_tier"] == 0]
        use_rows = [
            row(
                "Substantive use — Tier 1+2 (peer-reviewed, PDF-confirmed)",
                substantive,
                "Data use, analysis, or discussion — excludes peripheral refs and false positives",
            ),
            row(
                "Data / instrument use — Tier 1 only (peer-reviewed)",
                tier1,
                "Dataset DOI, repository URL, grant, or CLAMPS deployment in methods/results",
            ),
            row(
                "Excluded — false positives (Tier 0)",
                excluded,
                "Word collision or unrelated topic; removed from substantive counts",
            ),
        ]

    return pd.DataFrame(
        [
            row(
                "Peer-reviewed publications — high-confidence metadata",
                hc[hc["is_peer_reviewed"]],
                "Upper bound before PDF verification",
            ),
            row(
                "Peer-reviewed publications — PDF CLAMPS confirmed",
                peer_pdf,
                "Conservative impact count from full-text search",
            ),
            *use_rows,
            row(
                "Theses & dissertations — metadata (all fields)",
                theses_hc,
                "Includes non-meteorology false positives",
            ),
            row(
                "Theses & dissertations — PDF CLAMPS confirmed",
                theses_pdf,
                "Small sample; OU theses require repository search",
            ),
        ]
    )


MULTI_CAMPAIGN_ROW = "Multiple campaigns"


def _campaign_display_label(name: str) -> str:
    if name in (NO_CAMPAIGN_TAG, MULTI_CAMPAIGN_ROW):
        return SUPP_S1_NO_CAMPAIGN_LABEL
    return name


def _campaign_year_pivot(pair_df: pd.DataFrame) -> pd.DataFrame:
    return (
        pair_df.drop_duplicates(["paper_id", "campaign", "year"])
        .groupby(["campaign", "year"])["paper_id"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=sorted(pair_df["year"].unique()), fill_value=0)
    )


def campaign_year_matrix(
    pdf: pd.DataFrame,
    campaigns: list[str],
    mention_contexts: dict[str, str],
    top_n: int = 10,
    overrides: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.DataFrame]:
    """
    Campaign × year counts for review-corpus works (all corpus classes).
    Mention signals (CLAMPS, AERI, lidar, etc.) are collapsed to one work count per cell.
    Untagged works use the Non-Specific row; multi-campaign works appear on each named row.

    Returns total pivot (heatmap color), year totals, article pivot, non-article pivot.
    """
    df = pdf.copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df[df["year"].notna()]

    ov = overrides if overrides is not None else pd.DataFrame()
    rows: list[dict] = []
    for idx, row in df.iterrows():
        year = int(row["year"])
        is_article = str(row.get("corpus_class", "") or "").strip().lower() == "article"
        for camp in paper_campaign_labels_adjusted(row, campaigns, mention_contexts, ov, root=ROOT):
            rows.append(
                {
                    "paper_id": idx,
                    "campaign": camp,
                    "year": year,
                    "is_article": is_article,
                }
            )

    pair_df = pd.DataFrame(rows)
    if pair_df.empty:
        empty = pd.DataFrame(0, index=["(none)"], columns=[2020])
        return empty, pd.Series(dtype=int), empty.copy(), empty.copy()

    pivot = _campaign_year_pivot(pair_df)
    pivot_articles = _campaign_year_pivot(pair_df[pair_df["is_article"]])
    pivot_non_article = _campaign_year_pivot(pair_df[~pair_df["is_article"]])

    pivot = pivot.drop(index=MULTI_CAMPAIGN_ROW, errors="ignore")
    pivot_articles = pivot_articles.drop(index=MULTI_CAMPAIGN_ROW, errors="ignore")
    pivot_non_article = pivot_non_article.drop(index=MULTI_CAMPAIGN_ROW, errors="ignore")

    row_sums = pivot.sum(axis=1).sort_values(ascending=False)
    other_sums = row_sums.drop(labels=[NO_CAMPAIGN_TAG], errors="ignore")
    top_camps = list(other_sums.head(top_n).index)
    index_order: list[str] = []
    if NO_CAMPAIGN_TAG in pivot.index:
        index_order.append(NO_CAMPAIGN_TAG)
    index_order.extend(c for c in top_camps if c != NO_CAMPAIGN_TAG)
    pivot = pivot.reindex(index=index_order, fill_value=0)
    pivot_articles = pivot_articles.reindex(index=index_order, columns=pivot.columns, fill_value=0)
    pivot_non_article = pivot_non_article.reindex(index=index_order, columns=pivot.columns, fill_value=0)

    year_totals = (
        pair_df.drop_duplicates(["paper_id", "year"])
        .groupby("year")["paper_id"]
        .nunique()
        .reindex(pivot.columns, fill_value=0)
    )
    return pivot, year_totals, pivot_articles, pivot_non_article


def _extend_supp_s1_years(
    pivot: pd.DataFrame,
    year_totals: pd.Series,
    pivot_articles: pd.DataFrame | None = None,
    pivot_non_article: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.DataFrame]:
    """Pad timeline from SUPP_S1_MIN_YEAR through the latest publication year."""
    if pivot.empty:
        years = [SUPP_S1_MIN_YEAR]
        empty = pd.DataFrame(0, index=["(none)"], columns=years)
        return empty, pd.Series(0, index=years), empty.copy(), empty.copy()
    max_year = int(max(pivot.columns.max(), year_totals.index.max() if len(year_totals) else pivot.columns.max()))
    years = list(range(SUPP_S1_MIN_YEAR, max_year + 1))
    pivot = pivot.reindex(columns=years, fill_value=0)
    year_totals = year_totals.reindex(years, fill_value=0).fillna(0).astype(int)
    articles = (
        pivot_articles.reindex(index=pivot.index, columns=years, fill_value=0)
        if pivot_articles is not None
        else pd.DataFrame(0, index=pivot.index, columns=years)
    )
    non_articles = (
        pivot_non_article.reindex(index=pivot.index, columns=years, fill_value=0)
        if pivot_non_article is not None
        else pd.DataFrame(0, index=pivot.index, columns=years)
    )
    return pivot, year_totals, articles, non_articles


def plot_supp_s1(frames: dict[str, pd.DataFrame], campaigns: list[str], out_dir: Path) -> None:
    """
    Supp. Fig. S1 — campaign × year heatmap for all review-corpus works.
    Signals are aggregated (one count per work per campaign-year); time on x-axis.
    """
    pdf = frames["flagged_yd"]
    mention_contexts = mention_context_by_paper(frames["mentions"], root=ROOT)
    overrides = load_campaign_review_overrides(ROOT)
    pivot, year_totals, pivot_articles, pivot_non_article = campaign_year_matrix(
        pdf, campaigns, mention_contexts, overrides=overrides
    )
    pivot, year_totals, pivot_articles, pivot_non_article = _extend_supp_s1_years(
        pivot, year_totals, pivot_articles, pivot_non_article
    )
    deployment_platforms = deployment_heatmap_platform_cells(
        ROOT, list(pivot.index), list(pivot.columns.astype(int)), campaigns
    )

    fig = plt.figure(figsize=(max(9, len(pivot.columns) * 0.72), 5.5))
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 4], hspace=0.08)
    ax_hm = fig.add_subplot(gs[1])
    ax_bar = fig.add_subplot(gs[0])

    years = pivot.columns.astype(int)
    n_years = len(years)
    x = np.arange(n_years)
    x_half = 0.5

    # Marginal: unique review-corpus works per year (deduplicated across campaigns)
    totals = year_totals.values.astype(float)
    bar_peak = float(totals.max()) if len(totals) and totals.max() > 0 else 1.0
    bar_colors = [SUPP_S1_TOTAL_BAR_CMAP(0.35 + 0.65 * (v / bar_peak)) for v in totals]
    ax_bar.bar(x, totals, color=bar_colors, width=0.88, edgecolor="white", linewidth=0.4, align="center")
    ax_bar.set_xlim(-x_half, n_years - x_half)
    ax_bar.set_ylim(0, bar_peak * 1.15)
    ax_bar.xaxis.set_major_locator(NullLocator())
    ax_bar.xaxis.set_minor_locator(NullLocator())
    ax_bar.yaxis.set_major_locator(NullLocator())
    ax_bar.yaxis.set_minor_locator(NullLocator())
    _style_axes(ax_bar)
    ax_bar.spines["left"].set_visible(False)
    ax_bar.spines["bottom"].set_visible(False)
    for xi, val in zip(x, totals):
        if val <= 0:
            continue
        frac = val / bar_peak
        inside = val >= SUPP_S1_BAR_LABEL_INSIDE_MIN
        y = val / 2 if inside else val
        va = "center" if inside else "bottom"
        text_color = "white" if frac > 0.42 else "#2A2A2A"
        ax_bar.text(
            xi,
            y,
            str(int(val)),
            ha="center",
            va=va,
            fontsize=11,
            fontweight="bold",
            color=text_color,
        )

    data = pivot.values
    n_rows, n_cols = data.shape
    vmax = max(int(data.max()), 1)
    heatmap_cmap = SUPP_S1_HEATMAP_CMAP.copy()
    heatmap_cmap.set_bad(color="white")
    masked = ma.masked_where(data == 0, data)
    im = ax_hm.imshow(
        masked,
        aspect="auto",
        cmap=heatmap_cmap,
        vmin=0,
        vmax=vmax,
        extent=(-x_half, n_cols - x_half, n_rows - x_half, -x_half),
        origin="upper",
    )
    ax_hm.set_xlim(-x_half, n_cols - x_half)
    ax_hm.set_xticks(x)
    ax_hm.set_xticklabels(years)
    ax_hm.set_yticks(np.arange(n_rows))
    ax_hm.set_yticklabels([_campaign_display_label(c) for c in pivot.index], fontsize=9)
    ax_hm.set_xlabel("Publication year")
    ax_hm.set_xticks(np.arange(-x_half, n_cols, 1), minor=True)
    ax_hm.set_yticks(np.arange(-x_half, n_rows, 1), minor=True)
    ax_hm.grid(which="minor", color="#DDDDDD", linestyle="-", linewidth=0.7)
    ax_hm.tick_params(which="minor", size=0)

    for (row_i, col_j), platforms in deployment_platforms.items():
        _add_supp_s1_deployment_outline(ax_hm, row_i, col_j, x_half, platforms)
    article_data = pivot_articles.values
    for i in range(n_rows):
        for j in range(n_cols):
            val = int(data[i, j])
            if val <= 0:
                continue
            n_art = int(article_data[i, j])
            text_color = "white" if val > vmax * 0.55 else "#333333"
            ax_hm.text(
                j,
                i,
                f"{val}({n_art})",
                ha="center",
                va="center",
                fontsize=SUPP_S1_HEATMAP_CELL_FONTSIZE,
                fontweight="bold",
                color=text_color,
            )
    _style_axes(ax_hm)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        fig.tight_layout()
    # Match bar-panel data width to heatmap (y tick labels differ in width).
    pos_hm = ax_hm.get_position()
    pos_bar = ax_bar.get_position()
    ax_bar.set_position([pos_hm.x0, pos_bar.y0, pos_hm.width, pos_bar.height])
    ax_bar.set_xlim(-x_half, n_years - x_half)
    ax_bar.xaxis.set_major_locator(NullLocator())
    ax_bar.xaxis.set_minor_locator(NullLocator())
    # Row label for the marginal bar panel, aligned with heatmap y-tick column.
    bar_mid_y = pos_bar.y0 + pos_bar.height / 2
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ytick_labels = ax_hm.get_yticklabels()
    if ytick_labels:
        tick_exts = [
            lbl.get_window_extent(renderer).transformed(fig.transFigure.inverted())
            for lbl in ytick_labels
        ]
        label_x = (min(ext.x0 for ext in tick_exts) + max(ext.x1 for ext in tick_exts)) / 2
    else:
        label_x = pos_hm.x0 - 0.01
    annual_sum_label = fig.text(
        label_x,
        bar_mid_y,
        "Annual\nSum",
        transform=fig.transFigure,
        ha="center",
        va="center",
        fontsize=9,
        fontweight="bold",
        color="#222222",
    )
    fig.canvas.draw()
    for ext in ("png", "pdf"):
        fig.savefig(
            out_dir / f"{FIG_CAMPAIGN}.{ext}",
            dpi=300,
            bbox_inches="tight",
            bbox_extra_artists=[annual_sum_label],
            pad_inches=0.08,
        )
    plt.close(fig)

    export = pivot.astype(int).copy()
    export.columns = [f"total_{int(y)}" for y in export.columns]
    for y in pivot.columns:
        export[f"articles_{int(y)}"] = pivot_articles[int(y)].astype(int).values
        export[f"non_articles_{int(y)}"] = pivot_non_article[int(y)].astype(int).values
    export.to_csv(out_dir / f"{FIG_CAMPAIGN}_year_data.csv")
    year_totals.rename("unique_works").to_csv(out_dir / f"{FIG_CAMPAIGN}_year_totals.csv", header=True)


def table_to_latex(df: pd.DataFrame, path: Path, caption: str, label: str) -> None:
    """Write a simple LaTeX table snippet."""
    cols = list(df.columns)
    lines = [
        "\\begin{table}[ht]",
        "\\centering",
        f"\\caption{{{caption}}}",
        f"\\label{{{label}}}",
        "\\small",
        "\\begin{tabular}{" + "l" + "r" * (len(cols) - 1) + "}",
        "\\hline",
        " & ".join(c.replace("_", "\\_") for c in cols) + " \\\\",
        "\\hline",
    ]
    for _, row in df.iterrows():
        vals = [str(row[c]).replace("_", "\\_").replace("%", "\\%") for c in cols]
        lines.append(" & ".join(vals) + " \\\\")
    lines.extend(["\\hline", "\\end{tabular}", "\\end{table}"])
    path.write_text("\n".join(lines), encoding="utf-8")


def _archive_previous_figures(out_dir: Path) -> Path:
    """Move existing figure outputs into out_dir/old/ before regenerating."""
    import shutil
    from datetime import datetime

    old_dir = out_dir / "old"
    if not out_dir.exists():
        out_dir.mkdir(parents=True, exist_ok=True)
        return old_dir

    existing = [p for p in out_dir.iterdir() if p.name != "old"]
    if not existing:
        return old_dir

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = old_dir / stamp
    archive.mkdir(parents=True, exist_ok=True)
    for path in existing:
        shutil.move(str(path), str(archive / path.name))
    print(f"Archived {len(existing)} previous figure file(s) -> {archive}")
    return old_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate review figures and tables.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "figures")
    parser.add_argument(
        "--legacy-hc",
        action="store_true",
        help="Use legacy HC/scan frames instead of clamps_review_corpus.csv",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Do not move previous figure outputs to figures/old/",
    )
    args = parser.parse_args()
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.no_archive:
        _archive_previous_figures(out_dir)

    corpus_path = ROOT / "output" / "clamps_review_corpus.csv"
    if not args.legacy_hc and not corpus_path.exists():
        print("Building review corpus...")
        import subprocess

        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_review_corpus.py")],
            check=True,
            cwd=ROOT,
        )

    frames = load_review_frames(ROOT, prefer_corpus=not args.legacy_hc)
    if "review_corpus" in frames:
        n_all = len(frames["flagged_yd"])
        n_pub = len(frames["pdf_confirmed"])
        print(f"Using review corpus: {n_all} all works, {n_pub} published literature (article+report)")
    campaigns = load_campaign_names(ROOT)
    use_classified = classify_pdf_confirmed(
        frames["pdf_confirmed"], frames["mentions"], id_col="openalex_id"
    )
    metrics_dir = ROOT / "output" / "review_metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    use_classified.to_csv(metrics_dir / "pdf_use_classification.csv", index=False)
    review_queue = use_classified[
        use_classified["needs_manual_review"] | (use_classified["use_tier"] == 3)
    ].sort_values(["use_tier", "pdf_mention_count"], ascending=[True, False])
    review_queue.to_csv(metrics_dir / "pdf_use_manual_review_queue.csv", index=False)

    tier_df = tier_affiliation_counts(frames)
    export_unknown_affiliation(frames, metrics_dir)
    plot_fig8(frames, tier_df, out_dir)
    deploy_pivot = deployments_by_year_platform(ROOT)
    plot_fig8_with_deployments(frames, tier_df, deploy_pivot, out_dir)
    plot_fig8_work_type_with_deployments(frames, deploy_pivot, out_dir)

    table_x = build_table_x(frames)
    table_y = build_table_y(frames, use_classified)
    table_x.to_csv(out_dir / f"{TABLE_CORPUS_SUMMARY}.csv", index=False)
    table_y.to_csv(out_dir / f"{TABLE_IMPACT_SUMMARY}.csv", index=False)

    tx_pub = table_x[["metric", "nwc_affiliated", "non_affiliated", "total"]]
    ty_pub = table_y[["impact_metric", "count", "nwc_affiliated", "non_affiliated"]]
    table_to_latex(
        tx_pub,
        out_dir / f"{TABLE_CORPUS_SUMMARY}.tex",
        f"Corpus summary by subset. {NWC_AFFILIATION_CAPTION}",
        "tab:corpus",
    )
    table_to_latex(
        ty_pub,
        out_dir / f"{TABLE_IMPACT_SUMMARY}.tex",
        "Impact metrics complementing CLAMPS data-volume statistics.",
        "tab:impact",
    )

    plot_supp_s1(frames, campaigns, out_dir)

    print(f"Figures and tables written to {out_dir}/")
    print(f"  {FIG_AFFILIATION}.png/pdf")
    print(f"  {FIG_AFFILIATION_DEPLOY}.png/pdf")
    print(f"  {FIG_WORK_TYPE_DEPLOY}.png/pdf")
    print("  ../review_metrics/list_unknown_affiliation.csv")
    print(f"  {TABLE_CORPUS_SUMMARY}.csv / .tex")
    print(f"  {TABLE_IMPACT_SUMMARY}.csv / .tex")
    print(f"  {FIG_CAMPAIGN}.png/pdf")


if __name__ == "__main__":
    main()
