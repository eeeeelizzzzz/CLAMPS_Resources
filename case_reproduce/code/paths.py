"""Central paths for clamps_viz_process (code / logs / output layout)."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CODE_ROOT = PROJECT_ROOT / "code"
OUTPUT_ROOT = PROJECT_ROOT / "output"
LOGS_ROOT = PROJECT_ROOT / "logs"

DATA_LINK = Path(os.environ.get("CLAMPS_DATA_LINK", Path.home() / "data_link")).expanduser()

# WINDoe install (default: code/windoe/WINDoe)
_DEFAULT_WINDOE = CODE_ROOT / "windoe" / "WINDoe"
_LEGACY_WINDOE = Path.home() / "Documents" / "SCALES" / "WINDoe"
WINDOE_ROOT = Path(os.environ.get("WINDOE_ROOT", _DEFAULT_WINDOE)).expanduser()
if not WINDOE_ROOT.is_dir() and _LEGACY_WINDOE.is_dir():
    WINDOE_ROOT = _LEGACY_WINDOE

WINDOE_PRIORS_SGP = WINDOE_ROOT / "priors" / "SGP"

# Matplotlib cache (set MPLCONFIGDIR to this in shell scripts)
MPLCONFIG_DIR = PROJECT_ROOT / ".mplconfig"

# --- Quicklooks (archiveQL) ---
QUICKLOOKS_OUTPUT = OUTPUT_ROOT
QUICKLOOKS_LOG = LOGS_ROOT / "quicklooks.log"

# --- Case gallery candidates ---
CASE_GALLERY_CODE = CODE_ROOT / "case_gallery"
CASES_YAML = CASE_GALLERY_CODE / "cases.yaml"

CASE_GALLERY_STAGED = OUTPUT_ROOT / "case_gallery" / "staged"
CASE_GALLERY_FIGURES = OUTPUT_ROOT / "case_gallery" / "figures"
CASE_GALLERY_FIGURES_COMBINED = OUTPUT_ROOT / "case_gallery" / "figures_combined"
CASE_GALLERY_WINDOE = OUTPUT_ROOT / "case_gallery" / "windoe"
CASE_GALLERY_PBL_FUZZY = OUTPUT_ROOT / "case_gallery" / "pbl_fuzzy"
CASE_GALLERY_LOG = LOGS_ROOT / "case_gallery.log"

# AWAKEN / SPLASH libs and optional preprocessed data (under code/)
AWAKEN_DATA = CODE_ROOT / "CLAMPS1"
AWAKEN_WINDOE_OUTPUT = CODE_ROOT / "windoe_output"
AWAKEN_PBL_FUZZY_OUTPUT = CODE_ROOT / "pbl_fuzzy_output"
AWAKEN_FIGURES = CODE_ROOT / "figures"
SPLASH_DATA_ROOT = Path(
    os.environ.get("SPLASH_DATA_ROOT", CODE_ROOT / "SPLASH_data")
).expanduser()


def staged_case_dir(case_id: str) -> Path:
    return CASE_GALLERY_STAGED / case_id


def figure_path(case_id: str) -> Path:
    return CASE_GALLERY_FIGURES / case_id / "instrument_template_4panel.png"


def ensure_output_dirs() -> None:
    for d in (
        QUICKLOOKS_OUTPUT,
        CASE_GALLERY_STAGED,
        CASE_GALLERY_FIGURES,
        CASE_GALLERY_WINDOE,
        CASE_GALLERY_PBL_FUZZY,
        MPLCONFIG_DIR,
        LOGS_ROOT,
    ):
        d.mkdir(parents=True, exist_ok=True)
