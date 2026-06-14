#!/usr/bin/env python3
"""Rewrite instrument-template suptitles on gallery PNGs from data/cases.json."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CODE = REPO_ROOT / "case_reproduce" / "code"
MPLCONFIGDIR = REPO_ROOT / "case_reproduce" / ".matplotlib"
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIGDIR))

if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from case_gallery.gallery_suptitle import (  # noqa: E402
    load_gallery_image_metadata,
    patch_figure_suptitle,
    suptitle_for_image_stem,
)

IMAGES_DIR = REPO_ROOT / "images"
SUFFIX = "_instrument_template_4panel.png"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=IMAGES_DIR,
        help="Directory containing gallery PNGs (default: repo images/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned suptitles without modifying files",
    )
    args = parser.parse_args()

    meta = load_gallery_image_metadata()
    pngs = sorted(args.images_dir.glob(f"*{SUFFIX}"))
    if not pngs:
        raise SystemExit(f"No figures matching *{SUFFIX} in {args.images_dir}")

    for path in pngs:
        stem = path.name.removesuffix(SUFFIX)
        if stem not in meta:
            print(f"skip {path.name}: no entry in cases.json")
            continue
        suptitle = suptitle_for_image_stem(stem)
        print(f"{path.name}:")
        for line in suptitle.split("\n"):
            print(f"  {line}")
        if not args.dry_run:
            patch_figure_suptitle(path, suptitle)

    print(f"Done — {len(pngs)} figure(s) processed.")


if __name__ == "__main__":
    main()
