#!/usr/bin/env python3
"""
Copy plot-ready inputs for each gallery case into a self-contained export tree.

Layout (under output/case_gallery/data_export/):
  cases.yaml
  manifest.csv
  {case_id}/
    dlvad/ dlfp/ dlppi/ tropoe/   # archive inputs (real copies, not symlinks)
    windoe/                        # WINDoe .nc for cases.yaml date
    pbl_fuzzy/                     # fuzzy PBL .nc for cases.yaml date
    figure/                        # instrument_template_4panel.png (reference)

Only files selected by find_case_files / find_windoe_file / find_pbl_file are copied.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

_CODE = Path(__file__).resolve().parent.parent
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

from case_gallery.case_lib import (  # noqa: E402
    find_case_files,
    find_pbl_file,
    find_windoe_file,
    load_cases,
)
from paths import CASES_YAML, CASE_GALLERY_FIGURES_COMBINED, OUTPUT_ROOT  # noqa: E402

EXPORT_ROOT = OUTPUT_ROOT / "case_gallery" / "data_export"

PRODUCT_DIRS = ("dlvad", "dlfp", "dlppi", "tropoe", "windoe", "pbl_fuzzy", "figure")


def _copy_resolved(src: Path, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    resolved = src.resolve()
    shutil.copy2(resolved, dest)
    return resolved.stat().st_size


def export_case(case_id: str, *, force: bool) -> list[dict[str, str]]:
    cases = load_cases()
    case = cases[case_id]
    ymd = case.case_date.strftime("%Y%m%d")
    base = EXPORT_ROOT / case_id

    marker = base / ".export_complete"
    if marker.exists() and not force:
        return []

    if force and base.is_dir():
        shutil.rmtree(base)

    files = find_case_files(case)
    windoe = find_windoe_file(case)
    pbl = find_pbl_file(case)
    figure_src = case.figure_out
    combined_fig = CASE_GALLERY_FIGURES_COMBINED / f"{case_id}_instrument_template_4panel.png"

    copies: list[tuple[str, Path, Path]] = [
        ("dlvad", files.dlvad, base / "dlvad" / files.dlvad.name),
        ("dlfp", files.dlfp, base / "dlfp" / files.dlfp.name),
        ("dlppi", files.dlppi, base / "dlppi" / files.dlppi.name),
        ("tropoe", files.tropoe, base / "tropoe" / files.tropoe.name),
        ("windoe", windoe, base / "windoe" / windoe.name),
        ("pbl_fuzzy", pbl, base / "pbl_fuzzy" / pbl.name),
    ]
    if figure_src.is_file():
        copies.append(
            ("figure", figure_src, base / "figure" / "instrument_template_4panel.png")
        )
    elif combined_fig.is_file():
        copies.append(
            ("figure", combined_fig, base / "figure" / "instrument_template_4panel.png")
        )

    rows: list[dict[str, str]] = []
    for product, src, dest in copies:
        nbytes = _copy_resolved(src, dest)
        rows.append(
            {
                "case_id": case_id,
                "category": case.category,
                "project": case.project,
                "platform": case.platform,
                "case_date": str(case.case_date),
                "product": product,
                "filename": dest.name,
                "bytes": str(nbytes),
                "source": str(src.resolve()),
            }
        )

    marker.write_text(f"exported {ymd}\n", encoding="utf-8")
    return rows


def write_manifest(all_rows: list[dict[str, str]]) -> None:
    manifest = EXPORT_ROOT / "manifest.csv"
    fieldnames = [
        "case_id",
        "category",
        "project",
        "platform",
        "case_date",
        "product",
        "filename",
        "bytes",
        "source",
    ]
    with manifest.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)


def write_readme() -> None:
    readme = EXPORT_ROOT / "README.txt"
    readme.write_text(
        """CLAMPS case gallery — plot-ready data export
============================================

Each case_id/ folder mirrors what the server plot pipeline uses:
  dlvad/ dlfp/ dlppi/ tropoe/  — inputs (from data_link / RAID archive)
  windoe/                       — WINDoe retrieval for cases.yaml date
  pbl_fuzzy/                    — fuzzy PBL height for cases.yaml date
  figure/                       — reference 4-panel PNG from server

Authoritative dates: cases.yaml (copied to this directory).

Download to laptop:
  scp -r elizabeth.smith@bigbang4.winstorm.nssl:~/clamps_viz_process/output/case_gallery/data_export ~/Downloads/clamps_case_data

Local layout matches staged/{case_id}/ so you can point clamps_root at
  .../data_export/{case_id}
and windoe_dir / pbl_dir at the windoe/ and pbl_fuzzy/ subfolders.
""",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="Export only these case ids")
    parser.add_argument("--force", action="store_true", help="Overwrite existing export")
    args = parser.parse_args(argv)

    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CASES_YAML, EXPORT_ROOT / "cases.yaml")
    write_readme()

    cases = load_cases()
    case_ids = sorted(args.case) if args.case else sorted(cases)
    unknown = set(case_ids) - set(cases)
    if unknown:
        print(f"Unknown case(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 1

    all_rows: list[dict[str, str]] = []
    total_bytes = 0
    for case_id in case_ids:
        print(f"Exporting {case_id} …", flush=True)
        rows = export_case(case_id, force=args.force)
        all_rows.extend(rows)
        total_bytes += sum(int(r["bytes"]) for r in rows)
        print(f"  {len(rows)} files", flush=True)

    write_manifest(all_rows)
    print(f"Done: {len(case_ids)} cases, {len(all_rows)} files, {total_bytes/1e9:.2f} GB")
    print(f"Export root: {EXPORT_ROOT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
