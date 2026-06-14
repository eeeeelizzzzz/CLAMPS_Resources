"""Gallery figure suptitles from data/cases.json (deployment metadata)."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GALLERY_ROOT = REPO_ROOT.parent.parent
if str(GALLERY_ROOT) not in sys.path:
    sys.path.insert(0, str(GALLERY_ROOT))

from gallery_suptitle import (  # noqa: E402
    format_suptitle,
    load_gallery_image_metadata,
    suptitle_for_case_id as suptitle_for_image_stem,
)

GALLERY_CASES_JSON = REPO_ROOT / "data" / "cases.json"


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def patch_figure_suptitle(image_path: Path, suptitle: str) -> None:
    """Deprecated: regenerate figures with plot_instrument instead of patching PNGs."""
    raise RuntimeError(
        "PNG suptitle patching is disabled. Regenerate gallery figures with "
        "candidates/sync_webhost_figures.py from the case_gallery workspace."
    )


__all__ = [
    "format_suptitle",
    "load_gallery_image_metadata",
    "suptitle_for_image_stem",
    "patch_figure_suptitle",
]
