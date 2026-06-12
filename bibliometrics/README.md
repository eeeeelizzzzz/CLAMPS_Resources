# CLAMPS Review Bibliometric Pipeline

Reproducible bibliometric analysis for the CLAMPS mobile profiling facility review paper.
Builds a **726-work corpus** (570 articles, 20 reports, 107 datasets, 29 theses) and
generates Fig. 8, campaign heatmap (S1), and Tables X/Y.

This repository is **upload-ready**: Binder demo + full operational code for local use.

---

## Three layers

| Layer | What | Audience |
|-------|------|----------|
| **Binder notebook** | Interactive quick reproduction (~20 s) | Reviewers, curious readers |
| **Scripts + `OPERATIONS.md`** | Full pipeline you can download and adapt | Researchers implementing their own bibliometrics |
| **Zenodo DOI** | Permanent archive for citation | Anyone citing the corpus or code |

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/USER/REPO/HEAD?urlpath=lab%2Ftree%2Fnotebooks%2Freproduce.ipynb)

> Replace `USER/REPO` in the Binder badge after publishing to GitHub. See `ZENODO.md`.

---

## Quick start — Binder (no install)

1. Click the Binder badge above (first launch may take 3–5 min to build).
2. Open `notebooks/reproduce.ipynb`.
3. Run all cells → 726-work corpus + figures.

---

## Quick start — local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.yaml.example config.yaml   # set openalex.mailto
bash setup.sh                        # restore checkpoints → output/
bash verify.sh                       # rebuild + verify against deliverables/
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

## Repository layout

```
├── notebooks/reproduce.ipynb   Binder entry point
├── binder/                     Binder environment (no Playwright)
├── scripts/                    18 pipeline scripts (full operational code)
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
- **Software:** Zenodo software DOI from GitHub release
- **Paper:** CLAMPS review manuscript

---

## Related (later)

Interactive **CLAMPS Case Gallery** (observation data visualization) will be a separate
repository with its own Binder notebook.

## License

Update as appropriate. OpenAlex data used under [CC0](https://openalex.org).
