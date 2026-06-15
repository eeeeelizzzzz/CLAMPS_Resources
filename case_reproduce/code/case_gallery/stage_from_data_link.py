#!/usr/bin/env python3
"""
Stage DLVAD, DLFP, DL PPI, and TROPoe into output/case_gallery/staged/{case_id}/.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_CODE = Path(__file__).resolve().parent.parent
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

from archive_discovery import ArchiveTriplet, build_triplet_lookup, find_ppi, find_triplet
from case_gallery.case_lib import CaseSpec, load_cases
from paths import CASE_GALLERY_STAGED, DATA_LINK, ensure_output_dirs, staged_case_dir


def _clear_staged_dir(directory: Path) -> None:
    if not directory.is_dir():
        return
    for entry in directory.iterdir():
        if entry.is_symlink() or entry.is_file():
            entry.unlink()


def _link_or_copy(src: Path, dest: Path, copy: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    if copy:
        shutil.copy2(src, dest)
    else:
        dest.symlink_to(src.resolve())


def stage_case(case: CaseSpec, triplet: ArchiveTriplet, copy: bool) -> None:
    base = staged_case_dir(case.id)
    ymd = case.case_date.strftime("%Y%m%d")
    ppi = find_ppi(DATA_LINK, case.platform, ymd)
    mapping = [
        (base / "dlvad", triplet.vad),
        (base / "dlfp", triplet.fp),
        (base / "tropoe", triplet.profile),
    ]
    if ppi is not None:
        mapping.append((base / "dlppi", ppi))
    for dest_dir, src in mapping:
        _clear_staged_dir(dest_dir)
        _link_or_copy(src, dest_dir / src.name, copy)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-link", type=Path, default=DATA_LINK)
    parser.add_argument("--case", action="append")
    parser.add_argument("--copy", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    ensure_output_dirs()
    cases = load_cases()
    if args.case:
        unknown = set(args.case) - set(cases)
        if unknown:
            print(f"Unknown case(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 1
        cases = {k: v for k, v in cases.items() if k in args.case}

    print(f"Indexing {args.data_link.resolve()} …")
    lookup = build_triplet_lookup(args.data_link)
    print(f"  {len(lookup)} complete (platform, date) triplets in archive")

    ok = skip = fail = 0
    for case_id, case in sorted(cases.items()):
        if case.reuse_awaken:
            print(f"SKIP {case_id}: reuse_awaken")
            skip += 1
            continue
        ymd = case.case_date.strftime("%Y%m%d")
        triplet = find_triplet(lookup, case.platform, ymd)
        if triplet is None:
            print(f"FAIL {case_id}: no VAD+FP+profile for {case.platform} {ymd}")
            fail += 1
            continue
        if args.dry_run:
            print(f"OK   {case_id}: {triplet.profile.name}")
            ok += 1
            continue
        stage_case(case, triplet, args.copy)
        print(f"OK   {case_id} -> {CASE_GALLERY_STAGED / case_id}")
        ok += 1

    print(f"Done: {ok} staged, {skip} skipped, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
