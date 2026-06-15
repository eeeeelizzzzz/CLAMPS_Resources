#!/usr/bin/env python3
"""Download GOES-16 W Gulf Coast true-color imagery for the sea-breeze case."""

from __future__ import annotations

import argparse
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import certifi

_CODE = Path(__file__).resolve().parent.parent
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

from paths import PROJECT_ROOT

_SSL_CTX = ssl.create_default_context(cafile=certifi.where())

ARCHIVE_BASE = (
    "https://mtarchive.geol.iastate.edu/{year}/{month:02d}/{day:02d}/"
    "cod/sat/goes16/subregional/W_Gulf_Coast/truecolor"
)
DEFAULT_OUT = PROJECT_ROOT / "data" / "sea_breeze" / "goes16_truecolor"
DEFAULT_CROP_OUT = PROJECT_ROOT / "data" / "sea_breeze" / "goes16_truecolor_cropped"
# Square Houston-area crop (1024×576 reference); same width as original selection.
CROP_REF_SIZE = (1024, 576)
CROP_BOX_REF = (262, 82, 435, 255)  # left, top, right, bottom
# CLAMPS site markers on square crop (271×270 px); stored as crop fractions.
CLAMPS1_COLOR = "#c62828"  # inland
CLAMPS2_COLOR = "#1565c0"  # coastal
MARKER_SITES = (
    ("C1", 130 / 271, 100 / 270, CLAMPS1_COLOR),
    ("C2", 152 / 271, 150 / 270, CLAMPS2_COLOR),
)
FILENAME_RE = re.compile(r"W_Gulf_Coast_truecolor_(?P<stamp>\d{14})\.jpg")


def _archive_dir_url(case_date: date) -> str:
    return ARCHIVE_BASE.format(
        year=case_date.year,
        month=case_date.month,
        day=case_date.day,
    )


def _image_url(case_date: date, stamp: str) -> str:
    return f"{_archive_dir_url(case_date)}/W_Gulf_Coast_truecolor_{stamp}.jpg"


def _five_min_stamps(
    case_date: date,
    *,
    hour_start: int,
    hour_end: int,
) -> list[str]:
    """Archive stamps at :01, :06, … :56 past each hour (second always 17)."""
    ymd = case_date.strftime("%Y%m%d")
    minutes = list(range(1, 60, 5))
    stamps: list[str] = []
    for hour in range(hour_start, hour_end + 1):
        for minute in minutes:
            stamps.append(f"{ymd}{hour:02d}{minute:02d}17")
    return stamps


def _list_archive(case_date: date) -> list[str]:
    url = f"{_archive_dir_url(case_date)}/"
    with urllib.request.urlopen(url, timeout=60, context=_SSL_CTX) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    names = []
    for match in FILENAME_RE.finditer(html):
        names.append(f"W_Gulf_Coast_truecolor_{match.group('stamp')}.jpg")
    return sorted(set(names))


def _filter_names(
    names: list[str],
    *,
    hour_start: int,
    hour_end: int,
) -> list[str]:
    out: list[str] = []
    for name in names:
        stamp = FILENAME_RE.match(name)
        if not stamp:
            continue
        hour = int(stamp.group("stamp")[8:10])
        if hour_start <= hour <= hour_end:
            out.append(name)
    return out


def download_seabreeze_sat(
    *,
    case_date: date = date(2022, 7, 17),
    hour_start: int = 17,
    hour_end: int = 23,
    output_dir: Path = DEFAULT_OUT,
    force: bool = False,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        archive_names = _filter_names(
            _list_archive(case_date),
            hour_start=hour_start,
            hour_end=hour_end,
        )
    except urllib.error.URLError as exc:
        print(f"Could not list archive: {exc}", file=sys.stderr)
        archive_names = [
            f"W_Gulf_Coast_truecolor_{stamp}.jpg"
            for stamp in _five_min_stamps(
                case_date,
                hour_start=hour_start,
                hour_end=hour_end,
            )
        ]

    saved: list[Path] = []
    missing: list[str] = []
    for name in archive_names:
        dest = output_dir / name
        if dest.exists() and not force:
            saved.append(dest)
            continue
        url = f"{_archive_dir_url(case_date)}/{name}"
        try:
            with urllib.request.urlopen(url, timeout=60, context=_SSL_CTX) as resp:
                dest.write_bytes(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                missing.append(name)
                continue
            raise
        print(f"  saved {name}")
        saved.append(dest)

    print(
        f"{len(saved)} images in {output_dir} "
        f"({case_date} {hour_start:02d}–{hour_end:02d} UTC)"
    )
    if missing:
        print(f"  {len(missing)} not found in archive", file=sys.stderr)
    return saved


def crop_box_for_size(width: int, height: int) -> tuple[int, int, int, int]:
    ref_w, ref_h = CROP_REF_SIZE
    left, top, right, bottom = CROP_BOX_REF
    return (
        round(left / ref_w * width),
        round(top / ref_h * height),
        round(right / ref_w * width),
        round(bottom / ref_h * height),
    )


def crop_seabreeze_sat(
    *,
    input_dir: Path = DEFAULT_OUT,
    output_dir: Path = DEFAULT_CROP_OUT,
    force: bool = False,
) -> list[Path]:
    from PIL import Image

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sources = sorted(input_dir.glob("W_Gulf_Coast_truecolor_*.jpg"))
    if not sources:
        raise FileNotFoundError(f"No GOES true-color images in {input_dir}")

    saved: list[Path] = []
    box: tuple[int, int, int, int] | None = None
    for src_path in sources:
        dest = output_dir / src_path.name
        if dest.exists() and not force:
            saved.append(dest)
            continue
        with Image.open(src_path) as img:
            if box is None:
                box = crop_box_for_size(*img.size)
                print(f"  crop box (px): {box[0]}, {box[1]}, {box[2]}, {box[3]}")
            cropped = img.crop(box)
            cropped.save(dest, quality=95)
        saved.append(dest)

    print(f"{len(saved)} cropped images in {output_dir}")
    return saved


def _utc_label_from_name(name: str) -> str:
    match = FILENAME_RE.match(name)
    if not match:
        raise ValueError(f"Unexpected GOES filename: {name}")
    stamp = match.group("stamp")
    return f"{stamp[8:10]}{stamp[10:12]} UTC"


def _draw_site_markers(img: "Image.Image") -> "Image.Image":
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    radius = max(4, round(min(img.width, img.height) * 0.022))
    for label, fx, fy, color in MARKER_SITES:
        x = round(fx * img.width)
        y = round(fy * img.height)
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=color,
            outline="black",
            width=2,
        )
        tx = min(x + radius + 3, img.width - 18)
        ty = max(y - radius - 2, 2)
        draw.text(
            (tx, ty),
            label,
            fill="black",
            font=font,
            stroke_width=2,
            stroke_fill="white",
        )
    return img


def _stamp_timestamp(img: "Image.Image", label: str) -> "Image.Image":
    from PIL import ImageDraw, ImageFont

    stamped = img.convert("RGBA")
    draw = ImageDraw.Draw(stamped)
    font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad = 4
    x0 = 6
    y0 = stamped.height - th - pad - 6
    draw.rectangle(
        (x0 - pad, y0 - pad, x0 + tw + pad, y0 + th + pad),
        fill=(255, 255, 255, 255),
    )
    draw.text((x0, y0), label, fill=(0, 0, 0, 255), font=font)
    return stamped.convert("RGB")


def annotate_seabreeze_sat(
    *,
    input_dir: Path = DEFAULT_OUT,
    output_dir: Path = DEFAULT_CROP_OUT,
    force: bool = False,
) -> list[Path]:
    from PIL import Image

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sources = sorted(input_dir.glob("W_Gulf_Coast_truecolor_*.jpg"))
    if not sources:
        raise FileNotFoundError(f"No GOES true-color images in {input_dir}")

    saved: list[Path] = []
    box: tuple[int, int, int, int] | None = None
    for src_path in sources:
        dest = output_dir / src_path.name
        if dest.exists() and not force:
            saved.append(dest)
            continue
        with Image.open(src_path) as img:
            if box is None:
                box = crop_box_for_size(*img.size)
            out = img.crop(box).convert("RGB")
        out = _draw_site_markers(out)
        out = _stamp_timestamp(out, _utc_label_from_name(src_path.name))
        out.save(dest, quality=95)
        saved.append(dest)

    print(f"{len(saved)} annotated images in {output_dir}")
    return saved


DEFAULT_GIF_OUT = DEFAULT_CROP_OUT / "goes16_houston_seabreeze.gif"


def make_seabreeze_sat_gif(
    *,
    input_dir: Path = DEFAULT_CROP_OUT,
    output_path: Path = DEFAULT_GIF_OUT,
    duration_ms: int = 400,
    loop: int = 0,
) -> Path:
    from PIL import Image

    input_dir = Path(input_dir)
    frames = sorted(input_dir.glob("W_Gulf_Coast_truecolor_*.jpg"))
    if not frames:
        raise FileNotFoundError(f"No cropped GOES images in {input_dir}")

    images = [Image.open(path).convert("RGB") for path in frames]
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        output_path,
        save_all=True,
        append_images=images[1:],
        duration=duration_ms,
        loop=loop,
        optimize=True,
    )
    for img in images:
        img.close()
    print(f"  saved {output_path.name} ({len(frames)} frames, {duration_ms} ms/frame)")
    return output_path


def main() -> None:
    p = argparse.ArgumentParser(
        description="Download and crop GOES-16 W Gulf Coast true-color for sea-breeze timing"
    )
    sub = p.add_subparsers(dest="command")

    dl = sub.add_parser("download", help="Download images from Iowa State archive")
    dl.add_argument("--date", default="2022-07-17", help="Case date (YYYY-MM-DD)")
    dl.add_argument("--hour-start", type=int, default=17)
    dl.add_argument("--hour-end", type=int, default=23)
    dl.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    dl.add_argument("--force", action="store_true")

    cr = sub.add_parser("crop", help="Crop downloaded images to TRACER coastal box")
    cr.add_argument("--input-dir", type=Path, default=DEFAULT_OUT)
    cr.add_argument("--output-dir", type=Path, default=DEFAULT_CROP_OUT)
    cr.add_argument("--force", action="store_true")

    an = sub.add_parser("annotate", help="Add CLAMPS markers and UTC stamp to cropped frames")
    an.add_argument("--input-dir", type=Path, default=DEFAULT_OUT)
    an.add_argument("--output-dir", type=Path, default=DEFAULT_CROP_OUT)
    an.add_argument("--force", action="store_true")

    gf = sub.add_parser("gif", help="Build animated GIF from cropped frames")
    gf.add_argument("--input-dir", type=Path, default=DEFAULT_CROP_OUT)
    gf.add_argument("--output", type=Path, default=DEFAULT_GIF_OUT)
    gf.add_argument("--duration-ms", type=int, default=400)
    gf.add_argument("--loop", type=int, default=0, help="0 = repeat forever")

    # Back-compat: bare invocation runs download.
    p.add_argument("--date", default="2022-07-17", help=argparse.SUPPRESS)
    p.add_argument("--hour-start", type=int, default=17, help=argparse.SUPPRESS)
    p.add_argument("--hour-end", type=int, default=23, help=argparse.SUPPRESS)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT, help=argparse.SUPPRESS)
    p.add_argument("--force", action="store_true", help=argparse.SUPPRESS)

    args = p.parse_args()
    if args.command == "crop":
        crop_seabreeze_sat(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            force=args.force,
        )
        return
    if args.command == "annotate":
        annotate_seabreeze_sat(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            force=args.force,
        )
        return
    if args.command == "gif":
        make_seabreeze_sat_gif(
            input_dir=args.input_dir,
            output_path=args.output,
            duration_ms=args.duration_ms,
            loop=args.loop,
        )
        return
    if args.command == "download" or args.command is None:
        case_date = date.fromisoformat(args.date)
        download_seabreeze_sat(
            case_date=case_date,
            hour_start=args.hour_start,
            hour_end=args.hour_end,
            output_dir=args.output_dir,
            force=args.force,
        )
        return
    p.error(f"Unknown command: {args.command!r}")


if __name__ == "__main__":
    main()
