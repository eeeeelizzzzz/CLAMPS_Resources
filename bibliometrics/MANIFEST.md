# File manifest — bibliometrics repository

Publishable bibliometric pipeline snapshot. Parent project files outside `bibliometrics/` are **not modified**.

## Scripts (18)

| Script | Phase | Purpose |
|--------|-------|---------|
| `discover_channels.py` | 1 | OpenAlex channels A–G |
| `discover_thesis_openalex.py` | 1 | Channel F theses |
| `discover_thesis_repos.py` | 1 | Channel H IR crawl |
| `merge_channel_outputs.py` | 1 | Merge discovery streams |
| `resolve_pdf_urls.py` | 2 | PDF URL resolution (pass 1) |
| `resolve_pdf_urls_pass2.py` | 2 | PDF URL resolution (pass 2) |
| `build_publications_html_queue.py` | 2 | HTML scrape queue |
| `scan_pdfs.py` | 2 | PDF + HTML full-text scan |
| `apply_manual_scan_hits.py` | 2 | Apply manual hit corrections |
| `apply_manual_scan_misses.py` | 2 | Apply manual miss corrections |
| `build_data_deposits_export.py` | 3 | Extract dataset deposits |
| `ensure_mandatory_corpus_inputs.py` | 3/5 | Promote seed dataset DOIs |
| `triage_thesis_repos.py` | 4 | Auto-triage thesis candidates |
| `build_theses_master_list.py` | 4 | Deduplicated thesis list |
| `build_review_corpus.py` | 5 | **Merge → 726-work collection** |
| `export_review_corpus_clean.py` | 5 | Zenodo-ready clean export |
| `plot_review_figures.py` | 6 | **Figures + Tables X/Y** |
| `classify_pdf_use.py` | 6 | PDF use-tier classification (Table Y) |

## Data (16 files)

| File | Size (approx) | Role |
|------|---------------|------|
| `discovery_channels.yaml` | — | Channel A–G definitions |
| `author_seeds.yaml` | — | Channel D author groups |
| `campaign_anchors.yaml` | — | Per-campaign floor years |
| `campaign_full_names.yaml` | — | Campaign display names |
| `topic_filters.yaml` | — | Post-discovery exclusions |
| `thesis_institutions.yaml` | — | Channel F institutions |
| `thesis_repositories.yaml` | — | Channel H repo definitions |
| `channel_h_exclusions.yaml` | — | Channel H exclusions |
| `source_allowlist.yaml` | — | Source filtering |
| `ground_truth_clamps_papers.csv` | 132 rows | Mandatory registry |
| `clamps_dataset_dois.txt` | 65 DOIs | Seed datasets |
| `clamps_deployments.csv` | 40 rows | C1/C2 deployment months |
| `affiliation_overrides.csv` | — | NWC affiliation fixes |
| `campaign_review_overrides.csv` | 417 rows | Campaign label decisions |
| `manual_pdf_scan_hits.csv` | — | Verified scan hits |
| `manual_pdf_scan_misses.csv` | — | Verified non-hits |

## Checkpoints (8 files, ~17 MB)

See `checkpoints/README.md`.

## Deliverables

| File | Works/rows |
|------|------------|
| `clamps_review_corpus_clean.csv` | 726 |
| `clamps_review_corpus.csv` | 726 (internal) |
| `figures/fig_affiliation_*` | Affiliation panels by year |
| `figures/fig_work_type_*` | Work-type panels with deployments |
| `figures/fig_campaign_*` | Campaign heatmap |
| `figures/table_corpus_summary.csv` | Collection counts by subset |
| `figures/table_impact_summary.csv` | Impact tiers and theses |
| `review_metrics/pdf_use_classification.csv` | PDF use tiers |

## Python package (`clamps_biblio/`)

27 modules. Key entry points:

- `review_metrics_data.py` — collection + frame loading for figures
- `nwc_affiliation.py` — NWC co-author classification
- `discovered_channels.py` — channel merge/dedupe
- `openalex_client.py` — OpenAlex API
- `pdf_resolver.py`, `text_scanner.py`, `html_scraper.py` — scanning
- `repo_discovery/` — Channel H IR adapters

## Binder / interactive reproduction

| File | Role |
|------|------|
| `notebooks/reproduce.ipynb` | Quick-path notebook (collection + figures) |
| `binder/environment.yml` | Binder deps (no Playwright) |
| `binder/postBuild` | Restore checkpoints on Binder launch |
| `OPERATIONS.md` | Adapt full pipeline for another facility |
| `ZENODO.md` | DOI publishing guide |
| `CITATION.cff` | Citation metadata |

## Tests (11 files)

Run: `python -m pytest tests/ -q`

## Excluded from this repo

| Item | Reason |
|------|--------|
| `ams_cookies.txt` | Institutional credentials |
| `config.yaml` (with real email) | Personal info — use `config.yaml.example` |
| `output/` | Regenerated working directory |
| `discover.py` | Legacy v1 pipeline |
| `generate_review_metrics.py` | Superseded by `plot_review_figures.py` |
| `*_viewer.html` | Manual review UIs |
| `channel_h_hpc/` | HPC crawl bundle |
| `all_search_queries.txt` | 4,383-line query dump |
| `data/manualpapers/` | Locally downloaded PDFs |
| `data/thesis_institutions.yaml.bak` | Backup |

## Total size

~22 MB (mostly checkpoint CSVs and figure PNGs/PDFs).
