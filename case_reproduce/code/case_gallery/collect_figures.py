#!/usr/bin/env python3
"""Copy per-case 4-panel figures into one directory with case id in the filename."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_CODE = Path(__file__).resolve().parent.parent
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

from paths import CASE_GALLERY_FIGURES, CASE_GALLERY_FIGURES_COMBINED  # noqa: E402


def collect_figures(*, force: bool = False) -> list[Path]:
    CASE_GALLERY_FIGURES_COMBINED.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for case_dir in sorted(CASE_GALLERY_FIGURES.iterdir()):
        if not case_dir.is_dir():
            continue
        src = case_dir / "instrument_template_4panel.png"
        if not src.is_file():
            continue
        dst = CASE_GALLERY_FIGURES_COMBINED / f"{case_dir.name}_instrument_template_4panel.png"
        if dst.exists() and not force:
            copied.append(dst)
            continue
        shutil.copy2(src, dst)
        copied.append(dst)
        print(f"Copied {dst.name}")
    return copied


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--force", action="store_true", help="Overwrite existing copies")
    args = p.parse_args(argv)
    paths = collect_figures(force=args.force)
    print(f"Combined directory: {CASE_GALLERY_FIGURES_COMBINED} ({len(paths)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
