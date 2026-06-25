# Case gallery — instrument template reproduction

Interactive walkthrough for **loading plot-ready CLAMPS inputs** and building the gallery **4-panel instrument figure** for one case. Each notebook cell reads NetCDF variables, performs array work, and plots explicitly — no project wrapper functions (no THREDDS, no WINDoe re-run in the notebook).

**Demo case:** `ci_c1` — NWCRIL2020 CLAMPS1, **2020-07-30 UTC**. The gallery merges this day with `gravity_waves_c1` (same inputs, different science tag).

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/eeeeelizzzzz/CLAMPS_Resources/HEAD?urlpath=lab/tree/case_reproduce/notebooks/reproduce_ci_c1.ipynb)

**Binder launch URL:**  
`https://mybinder.org/v2/gh/eeeeelizzzzz/CLAMPS_Resources/HEAD?urlpath=lab/tree/case_reproduce/notebooks/reproduce_ci_c1.ipynb`

## Quick start — Binder

1. Click the badge above (first build may take several minutes; data ≈ 620 MB).
2. Run all cells in `notebooks/reproduce_ci_c1.ipynb` (step-by-step data load + plot).
3. Output figure: `output/case_gallery/figures/ci_c1/instrument_template_4panel.png`

`binder/postBuild` at the repo root links `data/ci_c1/` into the pipeline layout before the notebook runs.

## Local run

```bash
cd case_reproduce
bash scripts/link_data.sh
python -m venv .venv && source .venv/bin/activate
pip install matplotlib numpy netCDF4 pandas ipykernel jupyterlab
export MPLCONFIGDIR="$PWD/.matplotlib"
jupyter lab notebooks/reproduce_ci_c1.ipynb
```

Batch plotting for all gallery cases: `python code/case_gallery/plot_instrument.py ci_c1 --force` (wrapper around the same steps).

## Structure

| Path | Purpose |
|------|---------|
| `notebooks/reproduce_ci_c1.ipynb` | Binder entry point — CLAMPS data + visualization walkthrough |
| `code/` | Vendored gallery plotting pipeline (from HPC `clamps_viz_process`) |
| `data/ci_c1/` | Plot-ready NetCDF inputs (~620 MB; use Git LFS) |
| `scripts/link_data.sh` | Symlink data → `output/case_gallery/` layout |
| `output/` | Generated figures (gitignored) |

## Cloud-base markers

CBH dots are plotted only when TROPoe **`lwp` > 5 g m⁻²** (liquid water path), per the current gallery plotting code.

## Data in git

Example data (~620 MB) is **not** committed — it is downloaded from a [GitHub Release](https://github.com/eeeeelizzzzz/CLAMPS_Resources/releases/tag/case-data-v1) during Binder `postBuild` or via `scripts/fetch_ci_c1_data.sh`. See [`data/README.md`](data/README.md) to publish/update the release asset.
