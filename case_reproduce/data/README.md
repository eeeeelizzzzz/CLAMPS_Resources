# Example case data (`ci_c1`)

Plot-ready inputs for the **2020-07-30 NWCRIL2020 CLAMPS1** gallery case (`ci_c1`). The same observational day is used for the merged gallery entry **CI / gravity waves (C1)**.

## Layout (after download/extract)

```
ci_c1/
  dlvad/ dlfp/ dlppi/ tropoe/   # archive inputs
  windoe/                       # precomputed WINDoe retrieval
  pbl_fuzzy/                    # fuzzy PBL height
  figure/                       # optional reference PNG (overwritten by notebook)
```

Total size ≈ **620 MB** (dominated by `dlfp/` stare file).

## Binder / CI (not stored in git)

Large NetCDF files are **not** in the git repo — they bloat Binder builds past mybinder.org limits.

Instead, `scripts/fetch_ci_c1_data.sh` downloads a tarball from a GitHub Release:

`https://github.com/eeeeelizzzzz/CLAMPS_CaseGallery/releases/download/case-data-v1/ci_c1_data.tar.gz`

Binder `postBuild` and the notebook call this automatically.

### One-time: publish the data release

From a machine that has the extracted `ci_c1/` folder (e.g. copy from the HPC export):

```bash
cd case_reproduce
tar -czf ci_c1_data.tar.gz -C data ci_c1
gh release create case-data-v1 ci_c1_data.tar.gz \
  --title "ci_c1 plot-ready data" \
  --notes "Bundled inputs for case_reproduce/notebooks/reproduce_ci_c1.ipynb"
```

### Local use

```bash
bash scripts/fetch_ci_c1_data.sh   # or place data/ci_c1/ manually
bash scripts/link_data.sh
```

Override download URL: `export CI_C1_DATA_URL='https://…/ci_c1_data.tar.gz'`

## Source

Exported from HPC `clamps_viz_process` (`export_case_data.py`).
