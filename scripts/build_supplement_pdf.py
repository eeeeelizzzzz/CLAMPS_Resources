#!/usr/bin/env python3
"""Build a BAMS-style supplemental PDF from data/cases.json and images/."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from calendar import month_name
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_JSON = REPO_ROOT / "data" / "cases.json"
IMAGES_DIR = REPO_ROOT / "images"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "supplement"
DEFAULT_INTRO = REPO_ROOT / "scripts" / "supplement" / "intro.tex"
TEX_BASENAME = "clamps_case_gallery_supplement"

LATEX_SPECIAL = re.compile(r"([\\%#&_{}~^])")
HTML_LINK = re.compile(
    r'<a\s+href="([^"]+)"(?:\s+target="[^"]*")?(?:\s+rel="[^"]*")?>'
    r"(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
HREF_PLACEHOLDER = "@@HREF{index}@@"


def stash_html_links(text: str, hrefs: list[str]) -> str:
    """Replace HTML anchors with placeholders and collect LaTeX \\href commands."""

    def replace(match: re.Match[str]) -> str:
        url = match.group(1).replace("%", r"\%")
        label = escape_latex_plain(match.group(2))
        hrefs.append(rf"\href{{{url}}}{{{label}}}")
        return HREF_PLACEHOLDER.format(index=len(hrefs) - 1)

    return HTML_LINK.sub(replace, text)


def restore_href_placeholders(text: str, hrefs: list[str]) -> str:
    for index, href in enumerate(hrefs):
        text = text.replace(HREF_PLACEHOLDER.format(index=index), href)
    return text


def format_date(iso_date: str) -> str:
    year, month, day = (int(part) for part in iso_date.split("-"))
    return f"{month_name[month]} {day}, {year}"


def escape_latex_plain(text: str) -> str:
    text = (
        text.replace("\\", r"\textbackslash{}")
        .replace("—", "---")
        .replace("–", "--")
        .replace("…", r"\ldots{}")
        .replace("°", r"\textdegree{}")
    )
    text = re.sub(r"~", r"$\\sim$", text)
    return LATEX_SPECIAL.sub(r"\\\1", text)


def latex_mixed(text: str) -> str:
    """Preserve $...$ math segments; escape plain text elsewhere."""
    if not text:
        return ""

    hrefs: list[str] = []
    text = stash_html_links(text, hrefs)
    parts: list[str] = []
    index = 0
    while index < len(text):
        start = text.find("$", index)
        if start == -1:
            parts.append(escape_latex_plain(text[index:]))
            break
        if start > index:
            parts.append(escape_latex_plain(text[index:start]))
        end = text.find("$", start + 1)
        if end == -1:
            parts.append(escape_latex_plain(text[start:]))
            break
        parts.append(text[start : end + 1])
        index = end + 1
    return restore_href_placeholders("".join(parts), hrefs)


def is_four_panel_figure(src: str) -> bool:
    return "instrument_template_4panel" in src


def split_case_figures(entry: dict) -> tuple[list[dict], list[dict]]:
    images = entry.get("images") or []
    if not images and entry.get("image"):
        images = [{"src": entry["image"], "label": "Standard CLAMPS observations"}]

    primary = [figure for figure in images if is_four_panel_figure(figure["src"])]
    auxiliary = [figure for figure in images if not is_four_panel_figure(figure["src"])]

    if not primary and images:
        return [images[0]], images[1:]

    return primary, auxiliary


def resolve_image_for_latex(
    src: str,
    repo_root: Path,
    frames_dir: Path,
) -> tuple[str, str | None]:
    """Return a LaTeX-relative image path and optional animation note."""
    image_path = repo_root / src
    if not image_path.is_file():
        raise FileNotFoundError(f"Missing image referenced in cases.json: {src}")

    suffix = image_path.suffix.lower()
    if suffix == ".gif":
        frame_path = frames_dir / f"{image_path.stem}_frame0.png"
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError(
                "Pillow is required to embed GIF still frames. Install with: pip install Pillow"
            ) from exc

        with Image.open(image_path) as image:
            image.seek(0)
            image.convert("RGB").save(frame_path)

        rel = frame_path.relative_to(frames_dir.parent).as_posix()
        note = (
            "Static first frame shown; animated loop available in the online "
            "CLAMPS Case Gallery."
        )
        return rel, note

    rel = Path(os.path.relpath(image_path, frames_dir.parent)).as_posix()
    return rel, None


def latex_includegraphics(rel_path: str, *, width: str = r"\textwidth") -> str:
    return (
        f"\\noindent\\includegraphics[width={width},keepaspectratio]"
        f"{{{rel_path}}}\n"
    )


def render_figure_block(
    figure: dict,
    repo_root: Path,
    frames_dir: Path,
    *,
    primary: bool,
) -> str:
    rel_path, animation_note = resolve_image_for_latex(
        figure["src"], repo_root, frames_dir
    )
    label = latex_mixed(figure.get("label", ""))
    if figure.get("caption"):
        caption = latex_mixed(figure["caption"])
    elif label:
        caption = label
    else:
        caption = "CLAMPS observation"

    if animation_note:
        caption = f"{caption} {animation_note}"
    width = r"\textwidth" if primary else r"0.92\textwidth"

    return (
        "\\begin{figure}[!htbp]\n"
        "\\centering\n"
        f"{latex_includegraphics(rel_path, width=width)}"
        f"\\caption{{{caption}}}\n"
        "\\end{figure}\n"
    )


def render_sections(sections: list[dict] | None) -> str:
    if not sections:
        return (
            "\\subsection*{Additional content}\n"
            "More case information and visualizations will be added here "
            "as they are developed.\n"
        )

    blocks: list[str] = []
    for section in sections:
        title = latex_mixed(section.get("title", ""))
        blocks.append(f"\\subsection*{{{title}}}")

        if section.get("type") == "list":
            items = section.get("items") or []
            lines = ["\\begin{itemize}[leftmargin=*]"]
            lines.extend(f"  \\item {latex_mixed(item)}" for item in items)
            lines.append("\\end{itemize}")
            blocks.append("\n".join(lines))
        else:
            content = latex_mixed(section.get("content", ""))
            blocks.append(content)

    return "\n\n".join(blocks)


def render_case_index_table(cases: list[dict]) -> str:
    rows = []
    for index, entry in enumerate(cases, start=1):
        tags = ", ".join(entry.get("tags") or [])
        rows.append(
            f"{index} & {format_date(entry['date'])} & "
            f"{latex_mixed(entry['subtitle'])} & "
            f"{latex_mixed(entry['title'])} & "
            f"{latex_mixed(entry['campaign'])} & "
            f"{latex_mixed(entry['location'])} & "
            f"{latex_mixed(tags)} \\\\"
        )

    return (
        "\\begingroup\n"
        "\\small\n"
        "\\setlength{\\LTleft}{0pt}\n"
        "\\setlength{\\LTright}{0pt}\n"
        "\\begin{longtable}{@{}clllll>{\\raggedright\\arraybackslash}p{0.18\\textwidth}@{}}\n"
        "\\caption{CLAMPS example case index.}\\\\\n"
        "\\toprule\n"
        "\\# & Date & Platform & Case type & Campaign & Location & Tags \\\\\n"
        "\\midrule\n"
        "\\endfirsthead\n"
        "\\toprule\n"
        "\\# & Date & Platform & Case type & Campaign & Location & Tags \\\\\n"
        "\\midrule\n"
        "\\endhead\n"
        "\\midrule\n"
        "\\multicolumn{7}{r}{\\emph{Continued on next page}} \\\\\n"
        "\\endfoot\n"
        "\\bottomrule\n"
        "\\endlastfoot\n"
        + "\n".join(rows)
        + "\n\\end{longtable}\n"
        "\\endgroup\n"
    )


def render_case(entry: dict, repo_root: Path, frames_dir: Path) -> str:
    primary, auxiliary = split_case_figures(entry)
    tags = ", ".join(entry.get("tags") or [])
    metadata = (
        f"\\textbf{{Date:}} {format_date(entry['date'])} \\quad "
        f"\\textbf{{Platform:}} {latex_mixed(entry['subtitle'])} \\quad "
        f"\\textbf{{Campaign:}} {latex_mixed(entry['campaign'])} \\quad "
        f"\\textbf{{Location:}} {latex_mixed(entry['location'])}"
    )
    if tags:
        metadata += f"\\\\\n\\textbf{{Tags:}} {latex_mixed(tags)}"

    primary_blocks = [
        render_figure_block(figure, repo_root, frames_dir, primary=True)
        for figure in primary
    ]
    auxiliary_blocks = [
        render_figure_block(figure, repo_root, frames_dir, primary=False)
        for figure in auxiliary
    ]

    return (
        f"\\section{{{latex_mixed(entry['title'])}}}\n"
        f"\\label{{case:{entry['id']}}}\n\n"
        f"{metadata}\n\n"
        + "".join(primary_blocks)
        + "\n"
        + render_sections(entry.get("sections"))
        + "\n"
        + "".join(auxiliary_blocks)
        + "\n\\clearpage\n"
    )


def load_intro(intro_file: Path) -> str:
    if intro_file.is_file():
        return intro_file.read_text(encoding="utf-8").strip() + "\n"
    return ""


def build_latex_document(
    cases: list[dict],
    *,
    output_dir: Path,
    intro_file: Path,
    author: str,
    manuscript_title: str,
) -> str:
    frames_dir = output_dir / "_frames"
    intro = load_intro(intro_file)
    sorted_cases = sorted(cases, key=lambda entry: (entry["date"], entry["id"]))
    case_blocks = [
        render_case(entry, REPO_ROOT, frames_dir) for entry in sorted_cases
    ]

    return f"""\\documentclass[11pt]{{article}}

\\usepackage[margin=1in]{{geometry}}
\\usepackage[utf8]{{inputenc}}
\\usepackage[T1]{{fontenc}}
\\usepackage{{textcomp}}
\\usepackage{{graphicx}}
\\usepackage{{grffile}}
\\usepackage{{booktabs}}
\\usepackage{{longtable}}
\\usepackage{{array}}
\\usepackage{{caption}}
\\usepackage{{enumitem}}
\\usepackage{{amsmath,amssymb}}
\\usepackage[hidelinks]{{hyperref}}

\\setlist{{nosep}}
\\setcounter{{secnumdepth}}{{0}}
\\renewcommand{{\\thefigure}}{{S\\arabic{{figure}}}}
\\renewcommand{{\\thetable}}{{S\\arabic{{table}}}}

\\title{{{latex_mixed(manuscript_title)}}}
\\author{{{latex_mixed(author)}}}
\\date{{}}

\\begin{{document}}
\\maketitle
\\thispagestyle{{empty}}

{intro}

{render_case_index_table(sorted_cases)}

\\tableofcontents
\\clearpage

{"".join(case_blocks)}
\\end{{document}}
"""


def find_pdflatex() -> str | None:
    candidates = [
        shutil.which("pdflatex"),
        "/Library/TeX/texbin/pdflatex",
        "/usr/local/texlive/2025/bin/universal-darwin/pdflatex",
        "/usr/local/texlive/2024/bin/universal-darwin/pdflatex",
        "/opt/homebrew/bin/pdflatex",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def compile_pdf(tex_path: Path, pdflatex: str) -> Path:
    pdf_path = tex_path.with_suffix(".pdf")
    env = os.environ.copy()
    texbin = str(Path(pdflatex).parent)
    env["PATH"] = f"{texbin}:{env.get('PATH', '')}"

    command = [
        pdflatex,
        "-interaction=nonstopmode",
        "-halt-on-error",
        tex_path.name,
    ]

    for _ in range(2):
        result = subprocess.run(
            command,
            cwd=tex_path.parent,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            log_path = tex_path.with_suffix(".log")
            log_tail = ""
            if log_path.is_file():
                log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            raise RuntimeError(
                "pdflatex failed.\n"
                f"stdout:\n{result.stdout[-4000:]}\n"
                f"stderr:\n{result.stderr[-2000:]}\n"
                f"log tail:\n{log_tail}"
            )

    if not pdf_path.is_file():
        raise RuntimeError(f"pdflatex completed but PDF not found: {pdf_path}")

    return pdf_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for .tex/.pdf output (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--intro-file",
        type=Path,
        default=DEFAULT_INTRO,
        help="Optional LaTeX fragment inserted after the title page",
    )
    parser.add_argument(
        "--author",
        default="Elizabeth Smith, NOAA/NSSL",
        help="Author line on the supplement title page",
    )
    parser.add_argument(
        "--title",
        default="Supplemental Material: CLAMPS Example Case Gallery",
        help="Supplement title",
    )
    parser.add_argument(
        "--cases-json",
        type=Path,
        default=CASES_JSON,
        help="Path to cases.json",
    )
    parser.add_argument(
        "--latex-only",
        action="store_true",
        help="Write the .tex file but do not run pdflatex",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    cases = json.loads(args.cases_json.read_text(encoding="utf-8"))
    document = build_latex_document(
        cases,
        output_dir=args.output_dir,
        intro_file=args.intro_file,
        author=args.author,
        manuscript_title=args.title,
    )

    tex_path = args.output_dir / f"{TEX_BASENAME}.tex"
    tex_path.write_text(document, encoding="utf-8")
    print(f"Wrote {tex_path}")

    if args.latex_only:
        print("Skipped PDF compilation (--latex-only).")
        return 0

    pdflatex = find_pdflatex()
    if not pdflatex:
        print(
            "pdflatex not found. Install MacTeX/TeX Live, then re-run:\n"
            f"  python3 {Path(__file__).relative_to(REPO_ROOT)}",
            file=sys.stderr,
        )
        print(f"Or compile manually:\n  cd {args.output_dir} && pdflatex {tex_path.name}")
        return 1

    pdf_path = compile_pdf(tex_path, pdflatex)
    print(f"Wrote {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
