"""Gallery figure suptitles from data/cases.json (deployment metadata)."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import Rectangle

REPO_ROOT = Path(__file__).resolve().parents[3]
GALLERY_CASES_JSON = REPO_ROOT / "data" / "cases.json"

# Top banner height (px) — covers both suptitle lines in saved 150 dpi figures.
TITLE_BAND_PX = 105
SUPTITLE_FONTSIZE = 10
FIGURE_DPI = 150


def format_suptitle(campaign: str, location: str, platform: str, case_date: date) -> str:
    """Build the two-line instrument-template suptitle."""
    line1 = f"{campaign} · {location} · {platform}"
    line2 = f"{case_date.isoformat()} · CLAMPS observations · PBLH (fuzzy logic)"
    return f"{line1}\n{line2}"


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def load_gallery_image_metadata(
    cases_path: Path | None = None,
) -> dict[str, dict[str, str]]:
    """Map image stem (e.g. nllj_c2) to campaign, location, subtitle, date."""
    path = cases_path or GALLERY_CASES_JSON
    with path.open(encoding="utf-8") as f:
        entries = json.load(f)

    meta: dict[str, dict[str, str]] = {}
    for entry in entries:
        base = {
            "campaign": entry["campaign"],
            "location": entry["location"],
            "subtitle": entry["subtitle"],
            "date": entry["date"],
        }
        image = entry.get("image")
        if image:
            stem = Path(image).name.removesuffix("_instrument_template_4panel.png")
            meta[stem] = base
        for figure in entry.get("images") or []:
            stem = Path(figure["src"]).name.removesuffix("_instrument_template_4panel.png")
            figure_meta = {
                **base,
                **{
                    key: figure[key]
                    for key in ("location", "subtitle", "campaign")
                    if figure.get(key)
                },
            }
            meta[stem] = figure_meta
    return meta


def suptitle_for_image_stem(stem: str, cases_path: Path | None = None) -> str:
    meta = load_gallery_image_metadata(cases_path)[stem]
    return format_suptitle(
        meta["campaign"],
        meta["location"],
        meta["subtitle"],
        _parse_date(meta["date"]),
    )


def patch_figure_suptitle(image_path: Path, suptitle: str) -> None:
    """Replace the top suptitle band on an existing 4-panel PNG."""
    img = mpimg.imread(image_path)
    height, width = img.shape[:2]

    fig, ax = plt.subplots(figsize=(width / FIGURE_DPI, height / FIGURE_DPI), dpi=FIGURE_DPI)
    ax.imshow(img, extent=[0, width, height, 0], aspect="auto", interpolation="nearest")
    ax.set_xlim(0, width)
    ax.set_ylim(height, 0)
    ax.axis("off")

    ax.add_patch(
        Rectangle(
            (0, 0),
            width,
            TITLE_BAND_PX,
            facecolor="white",
            edgecolor="none",
            zorder=5,
        )
    )

    lines = suptitle.split("\n", 1)
    ax.text(
        width / 2,
        24,
        lines[0],
        ha="center",
        va="top",
        fontsize=SUPTITLE_FONTSIZE,
        zorder=6,
    )
    if len(lines) > 1:
        ax.text(
            width / 2,
            54,
            lines[1],
            ha="center",
            va="top",
            fontsize=SUPTITLE_FONTSIZE,
            zorder=6,
        )

    fig.savefig(
        image_path,
        dpi=FIGURE_DPI,
        facecolor="white",
        edgecolor="none",
        pad_inches=0,
    )
    plt.close(fig)
