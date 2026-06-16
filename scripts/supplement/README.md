# BAMS supplemental PDF builder

Builds a submission-ready PDF from `data/cases.json` and `images/`.

## Requirements

- Python 3.10+
- [Pillow](https://pypi.org/project/pillow/) (GIF still frames)
- A LaTeX distribution with `pdflatex` (MacTeX, TeX Live, or BasicTeX)

```bash
pip install Pillow
```

## Build

From the repository root:

```bash
python3 scripts/build_supplement_pdf.py
```

Outputs:

| File | Purpose |
|------|---------|
| `output/supplement/clamps_case_gallery_supplement.tex` | Generated LaTeX source |
| `output/supplement/clamps_case_gallery_supplement.pdf` | Upload this to BAMS as Supplemental Material |
| `output/supplement/_frames/` | First-frame PNGs extracted from GIF loops |

## Options

```bash
# Customize title page / intro
python3 scripts/build_supplement_pdf.py \
  --author "Elizabeth Smith, NOAA/NSSL" \
  --title "Supplemental Material: CLAMPS Example Case Gallery"

# Edit scripts/supplement/intro.tex, then rebuild

# Generate LaTeX only (no pdflatex required)
python3 scripts/build_supplement_pdf.py --latex-only

# Manual compile
cd output/supplement
pdflatex clamps_case_gallery_supplement.tex
pdflatex clamps_case_gallery_supplement.tex
```

## Document structure

1. Title page
2. Introduction (`scripts/supplement/intro.tex`)
3. Case index table (all entries from `cases.json`)
4. Table of contents
5. One section per case — primary 4-panel figures, auxiliary figures, overview, highlights

Figure order matches the online gallery: standard observations first, narrative second, auxiliary diagnostics last.

GIF animations are embedded as a static first frame with a note pointing readers to the live site.

## BAMS submission notes

- Upload the PDF exactly as produced; BAMS does not reformat supplements.
- Mention the supplement in the main manuscript and provide the editor justification (extended visual catalog; article stands alone).
- Archive the full interactive site and reproduction code on Zenodo separately; cite that DOI in the paper.
