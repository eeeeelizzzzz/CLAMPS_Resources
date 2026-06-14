# CLAMPS Case Gallery and Bibliometrics

This repository contains a GitHub Pages site showcasing CLAMPS example cases with instrument overview figures. Each case has a detail page that can be extended with additional plots and content. An example of data visualization code is also provided.
**Live site:** [https://eeeeelizzzzz.github.io/CLAMPS_CaseGallery/](https://eeeeelizzzzz.github.io/CLAMPS_CaseGallery/)

**Bibliometrics (726-work review corpus):** [bibliometrics/index.html](bibliometrics/index.html)  
[![Binder — bibliometrics](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/eeeeelizzzzz/CLAMPS_CaseGallery/HEAD?urlpath=lab/tree/bibliometrics/notebooks/reproduce.ipynb)

**Case figure reproduction (`ci_c1`, 2020-07-30):** [case_reproduce/index.html](case_reproduce/index.html)  
[![Binder — case figure](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/eeeeelizzzzz/CLAMPS_CaseGallery/HEAD?urlpath=lab/tree/case_reproduce/notebooks/reproduce_ci_c1.ipynb)

## Structure

| Path | Purpose |
|------|---------|
| `index.html` | Site home — links to case gallery and bibliometrics sections |
| `case-table.html` | Sortable case table |
| `gallery.html` | Card gallery with searchable case menu |
| `case.html?id=…` | Individual case pages |
| `bibliometrics/` | Review-paper bibliometric pipeline + Binder notebook |
| `case_reproduce/` | Instrument-template figure notebook + example data (`ci_c1`) |
| `binder/` | MyBinder environment (repo root; bibliometrics + case figure) |
| `data/cases.json` | Case metadata (dates, titles, images, tags) |
| `images/` | Combined instrument overview figures |
| `js/` | Page logic (ES modules) |
| `css/style.css` | Shared styles |

## Adding or updating cases

1. Place the combined plot PNG in `images/` using the naming pattern `{case_id}_instrument_template_4panel.png`.
2. Add or edit an entry in `data/cases.json` with `id`, `date`, `title`, `subtitle` (`CLAMPS1` or `CLAMPS2`), `campaign`, `location`, `image` (or `images` for multi-figure cases), and optional thematic `tags`.
3. For future per-case content, add a `sections` array to the case entry. Supported section types include `text`, `list`, `html`, and `image` (see `js/app.js`).
4. Instrument-template suptitles use **deployment metadata** from `cases.json` (`{campaign} · {location} · {subtitle}`). To refresh titles on existing PNGs: `python3 scripts/fix_gallery_suptitles.py`.


## GitHub Pages deployment

1. Push this repository to GitHub.
2. In the repo settings, enable **Pages** with source **Deploy from branch** → `main` → `/ (root)`.
3. The site will be published at `https://<username>.github.io/CLAMPS_CaseGallery/`.

## Acknowledgements
Site layout/initial implementation of this case gallery web interface were developed with assistance from Cursor AI (2026). Case selection, figures, and scientific content were curated by the human author (Elizabeth Smith). All generative AI assistance was reviewed by the human author. 

## License

See [LICENSE](LICENSE) (CC0 1.0).
