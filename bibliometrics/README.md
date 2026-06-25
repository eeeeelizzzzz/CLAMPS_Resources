# CLAMPS Review Bibliometric Pipeline

Reproducible bibliometric analysis for the CLAMPS mobile profiling facility review paper.
Builds a **726-work corpus** (570 articles, 20 reports, 107 datasets, 29 theses) and
generates annual bibliometric figures and summary tables.

This package lives in the [CLAMPS Resources](https://eeeeelizzzzz.github.io/CLAMPS_Resources/) monorepo.
Binder reads `binder/` at the **repository root** and runs notebooks under `bibliometrics/`.

---

## Three layers

| Layer | What | Audience |
|-------|------|----------|
| **Binder notebook** | Interactive quick reproduction (~20 s) | Reviewers, curious readers |
| **Scripts + `OPERATIONS.md`** | Full pipeline you can download and adapt | Researchers implementing their own bibliometrics |
| **Zenodo DOI** | Permanent archive for citation | Anyone citing the corpus or code |

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/eeeeelizzzzz/CLAMPS_Resources/HEAD?urlpath=lab/tree/bibliometrics/notebooks/reproduce.ipynb)

**Binder launch URL:**  
`https://mybinder.org/v2/gh/eeeeelizzzzz/CLAMPS_Resources/HEAD?urlpath=lab/tree/bibliometrics/notebooks/reproduce.ipynb`

---

## Quick start — Binder (no install)

1. Click the Binder badge above (first launch may take 3–5 min to build).
2. Open `notebooks/reproduce.ipynb` (Binder should open it directly).
3. Run all cells → 726-work corpus + figures in `output/figures/`.

`binder/postBuild` at the repo root copies checkpoints into `bibliometrics/output/` before you run the notebook.

---

## Quick start — local

```bash
cd bibliometrics
bash setup.sh                        # restore checkpoints → output/
bash verify.sh                       # rebuild + verify against deliverables/
```

Or step by step:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.yaml.example config.yaml   # set openalex.mailto for full pipeline
python scripts/build_review_corpus.py
python scripts/plot_review_figures.py --no-archive
```

---

## Full operational pipeline (your own machine)

For OpenAlex discovery, PDF/HTML scanning, thesis review, and corpus build from scratch:

1. Install: `pip install -r requirements.txt && playwright install chromium`
2. Configure: `config.yaml` + files in `data/` (see **`OPERATIONS.md`**)
3. Run phases 1–6 in **`PIPELINE.md`**

`OPERATIONS.md` explains how to adapt channels, registries, and affiliation rules for **another facility**.

---

## Corpus composition (726 works)

| Source | Count | Description |
|--------|------:|-------------|
| HC publications | 519 | High-confidence articles/reports |
| Ground-truth mandatory | 72 | Registry bypass (Channel G) |
| Seed datasets | 65 | `data/clamps_dataset_dois.txt` |
| Validated deposits | 42 | Discovered datasets (`work_class=x`) |
| Manual theses | 28 | `manual_flag=y` in thesis master list |

---

## Key outputs (after `plot_review_figures.py`)

| File | Description |
|------|-------------|
| `fig_affiliation_by_year_with_deployments.png` | NWC vs non-NWC by year + deployment months |
| `fig_work_type_by_year_with_deployments.png` | Work-type stacks by year |
| `fig_campaign_by_year.png` | Campaign × year heatmap |
| `table_corpus_summary.csv` | Corpus subset counts |
| `table_impact_summary.csv` | PDF tier / impact metrics |

**GitHub Pages:** PNGs and summary CSVs for [bibliometrics/index.html](index.html) live in `figures/` (not gitignored `output/`). After regenerating:

```bash
cp output/figures/fig_campaign_by_year.png figures/
# combined two-panel bar chart (affiliation + work type with deployments):
# save/export as figures/fig_annual_bars_with_deployments.png
cp output/figures/table_*.csv figures/
```

---

## Repository layout

```
bibliometrics/
├── notebooks/reproduce.ipynb   Binder entry point
├── scripts/                    Pipeline scripts
├── clamps_biblio/              Core Python package
├── data/                       Discovery config + manual review decisions
├── checkpoints/                Frozen intermediates for quick reproduction
├── deliverables/               Published outputs (verification reference)
├── OPERATIONS.md               Adapt pipeline for another facility
├── PIPELINE.md                 CLAMPS full rebuild steps
├── ZENODO.md                   DOI publishing guide
└── CITATION.cff                 Citation metadata
```

---

## Citation

- **Corpus:** Zenodo data DOI (see `ZENODO.md`; update `CITATION.cff`)
- **Software:** Zenodo concept DOI [10.5281/zenodo.20709965](https://doi.org/10.5281/zenodo.20709965) from GitHub release (see `CITATION.cff`)
- **Paper:** CLAMPS review manuscript

## License

Update as appropriate. OpenAlex data used under [CC0](https://openalex.org).
