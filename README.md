# CLAMPS Case Gallery

A GitHub Pages site showcasing CLAMPS example cases with instrument overview figures. Each case has a detail page that can be extended with additional text, plots, and interactive content as it is developed.

**Live site:** [https://eeeeelizzzzz.github.io/CLAMPS_CaseGallery/](https://eeeeelizzzzz.github.io/CLAMPS_CaseGallery/)

**Bibliometrics (726-work review corpus):** [bibliometrics/index.html](bibliometrics/index.html) ·
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/eeeeelizzzzz/CLAMPS_CaseGallery/HEAD?urlpath=lab/tree/bibliometrics/notebooks/reproduce.ipynb)

## Structure

| Path | Purpose |
|------|---------|
| `index.html` | Home page with a sortable case table |
| `gallery.html` | Card gallery with searchable case menu |
| `case.html?id=…` | Individual case pages |
| `bibliometrics/` | Review-paper bibliometric pipeline + Binder notebook |
| `binder/` | MyBinder environment (repo root; builds `bibliometrics/`) |
| `data/cases.json` | Case metadata (dates, titles, images, tags) |
| `images/` | Combined instrument overview figures |
| `js/` | Page logic (ES modules) |
| `css/style.css` | Shared styles |

## Adding or updating cases

1. Place the combined plot PNG in `images/` using the naming pattern `{case_id}_instrument_template_4panel.png`.
2. Add or edit an entry in `data/cases.json` with `id`, `date`, `title`, `subtitle` (`CLAMPS1` or `CLAMPS2`), `campaign`, `location`, `image` (or `images` for multi-figure cases), and optional thematic `tags`.
3. For future per-case content, add a `sections` array to the case entry. Supported section types include `text`, `html`, and `image` (see `js/app.js`).


## GitHub Pages deployment

1. Push this repository to GitHub.
2. In the repo settings, enable **Pages** with source **Deploy from branch** → `main` → `/ (root)`.
3. The site will be published at `https://<username>.github.io/CLAMPS_CaseGallery/`.

## Acknowledgements
Site layout/initial implementation of this case gallery web interface were developed with assistance from Cursor AI (2026). Case selection, figures, and scientific content were curated by the human author (Elizabeth Smith). All generative AI assistance was reviewed by the human author. 

## License

See [LICENSE](LICENSE) (CC0 1.0).
