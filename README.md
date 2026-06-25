# CLAMPS Resources

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20709965.svg)](https://doi.org/10.5281/zenodo.20709965)

GitHub Pages site for the Collaborative Lower Atmospheric Mobile Profiling System (CLAMPS): facility information, curated example cases, first-decade deployment history, bibliometric analysis, and figure-reproduction notebooks.

**Live site:** [https://eeeeelizzzzz.github.io/CLAMPS_Resources/](https://eeeeelizzzzz.github.io/CLAMPS_Resources/index.html)

**Bibliometrics (726-work review corpus)** [![Binder — bibliometrics](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/eeeeelizzzzz/CLAMPS_Resources/HEAD?urlpath=lab/tree/bibliometrics/notebooks/reproduce.ipynb)

**Case figure reproduction (`ci_c1`, 2020-07-30)** [![Binder — case figure](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/eeeeelizzzzz/CLAMPS_Resources/HEAD?urlpath=lab/tree/case_reproduce/notebooks/reproduce_ci_c1.ipynb)

## Structure

| Path | Purpose |
|------|---------|
| `index.html` | Site home — links to CLAMPS Info, Case Gallery, and Deployment History |
| `clamps-info.html` | Facility overview, photos, official links, bibliometrics entry |
| `case-gallery.html` | Case gallery landing (table, full gallery, notebook, surprise me) |
| `case-table.html` | Sortable case table |
| `gallery.html` | Card gallery with searchable case menu |
| `case.html?id=…` | Individual case pages |
| `deployments.html` | Sortable deployment history (2015–2024) |
| `deployment.html?id=…` | Individual deployment pages |
| `bibliometrics/` | Review-paper bibliometric pipeline + Binder notebook |
| `case_reproduce/` | Instrument-template figure notebook + example data (`ci_c1`) |
| `binder/` | MyBinder environment (repo root; bibliometrics + case figure) |
| `data/cases.json` | Case metadata (dates, titles, images, tags) |
| `data/deployments.json` | Deployment metadata (campaigns, dates, references) |
| `images/` | Combined instrument overview figures |
| `js/` | Page logic (ES modules) |
| `css/style.css` | Shared styles |

## BAMS supplemental PDF

Build a submission-ready case-gallery PDF from `data/cases.json`:

```bash
python3 scripts/build_supplement_pdf.py
```

See [scripts/supplement/README.md](scripts/supplement/README.md) for requirements, options, and manual `pdflatex` steps.

## Adding or updating cases

1. Place the combined plot PNG in `images/` using the naming pattern `{case_id}_instrument_template_4panel.png`.
2. Add or edit an entry in `data/cases.json` with `id`, `date`, `title`, `subtitle` (`CLAMPS1` or `CLAMPS2`), `campaign`, `location`, `image` (or `images` for multi-figure cases), and optional thematic `tags`.
3. For future per-case content, add a `sections` array to the case entry. Supported section types include `text`, `list`, `html`, and `image` (see `js/app.js`).
4. Instrument-template suptitles use **deployment metadata** from `cases.json` (`{campaign} · {location} · {subtitle}`). To refresh titles on existing PNGs: `python3 scripts/fix_gallery_suptitles.py`.

## Adding or updating deployments

Deployment records live in `data/deployments.json`. Each page can include campaign photos with captions, combined subproject stints (e.g. VORTEX-USA, TRACER, AWAKEN), reference DOIs, and related website links. Source deployment intervals are tracked in `bibliometrics/data/clamps_deployments.csv`.

## GitHub Pages deployment

1. Push this repository to GitHub.
2. In the repo settings, enable **Pages** with source **Deploy from branch** → `main` → `/ (root)`.
3. The site will be published at `https://<username>.github.io/CLAMPS_Resources/`.

## Acknowledgements
Site layout/initial implementation of this case gallery web interface were developed with assistance from Cursor AI (2026). Case selection, figures, and scientific content were curated by the human author (Elizabeth Smith). All generative AI assistance was reviewed by the human author. 

## License

See [LICENSE](LICENSE) (CC0 1.0).
