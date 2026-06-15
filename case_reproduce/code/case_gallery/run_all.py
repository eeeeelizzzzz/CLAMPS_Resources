#!/usr/bin/env python3
"""
Run the full case-gallery pipeline for each case in cases.yaml.

Steps per case (unless reuse_awaken or --skip-*):
  1. download (THREDDS) — skip on server with --skip-download
  2. stage_from_data_link (if inputs missing)
  3. WINDoe
  4. PBL fuzzy (WINDoe winds)
  5. instrument_template_4panel plot
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from pathlib import Path

_CODE = Path(__file__).resolve().parent.parent
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

from case_gallery.case_lib import CaseSpec, get_case, load_cases  # noqa: E402
from paths import CASE_GALLERY_LOG, DATA_LINK, ensure_output_dirs  # noqa: E402

LOGGER = logging.getLogger("case_gallery")


def _setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.handlers.clear()
    LOGGER.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    LOGGER.addHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)


def _import_step(name: str):
    try:
        return importlib.import_module(f"case_gallery.{name}")
    except ImportError as exc:
        raise SystemExit(
            f"Missing case_gallery/{name}.py — upload from laptop. "
            f"See code/case_gallery/UPLOAD.md\n  ({exc})"
        ) from exc


def _needs_run(case: CaseSpec, only_missing: bool) -> bool:
    if not only_missing:
        return True
    return not case.figure_out.exists()


def _staged_ok(case: CaseSpec) -> bool:
    root = case.clamps_root
    return (
        (root / "dlvad").is_dir()
        and any((root / "dlvad").glob("*dlvad*"))
        and (root / "dlfp").is_dir()
        and any((root / "dlfp").glob("*dlfp*"))
        and (root / "tropoe").is_dir()
        and any((root / "tropoe").glob("*"))
    )


def run_case(
    case: CaseSpec,
    *,
    skip_download: bool,
    skip_stage: bool,
    force: bool,
    data_link: Path,
) -> bool:
    if case.reuse_awaken:
        plot = _import_step("plot_instrument")
        LOGGER.info("%s: reuse_awaken plot only", case.id)
        plot.run_case(case, force=force)
        return case.figure_out.exists()

    if not skip_download:
        download = _import_step("download")
        download.run_case(case, force=force)

    if not _staged_ok(case) and not skip_stage:
        from case_gallery import stage_from_data_link

        rc = stage_from_data_link.main(
            ["--data-link", str(data_link), "--case", case.id]
        )
        if rc != 0:
            LOGGER.error("%s: staging failed", case.id)
            return False

    windoe = _import_step("windoe")
    pbl = _import_step("pbl_fuzzy")
    plot = _import_step("plot_instrument")

    windoe.run_case(case, force=force)
    pbl.run_case(case, force=force)
    plot.run_case(case, force=force)
    return case.figure_out.exists()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="Run only these case_id(s)")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-stage", action="store_true")
    parser.add_argument("--only-missing", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--data-link", type=Path, default=DATA_LINK)
    args = parser.parse_args(argv)

    ensure_output_dirs()
    _setup_logging(CASE_GALLERY_LOG)

    cases = load_cases()
    if args.case:
        unknown = set(args.case) - set(cases)
        if unknown:
            print(f"Unknown case(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 1
        cases = {k: v for k, v in cases.items() if k in args.case}

    ok = fail = skip = 0
    for case_id, case in sorted(cases.items()):
        if not args.force and not _needs_run(case, args.only_missing):
            LOGGER.info("SKIP %s (figure exists)", case_id)
            skip += 1
            continue
        LOGGER.info("RUN  %s", case_id)
        try:
            success = run_case(
                case,
                skip_download=args.skip_download,
                skip_stage=args.skip_stage,
                force=args.force,
                data_link=args.data_link,
            )
        except SystemExit:
            raise
        except Exception as exc:
            LOGGER.error("FAIL %s: %s", case_id, exc)
            fail += 1
            continue
        if success:
            LOGGER.info("OK   %s -> %s", case_id, case.figure_out)
            ok += 1
        else:
            LOGGER.error("FAIL %s: no figure", case_id)
            fail += 1

    LOGGER.info("Finished: %d ok, %d skipped, %d failed", ok, skip, fail)
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
