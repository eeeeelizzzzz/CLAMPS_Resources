# Adapting the CLAMPS bibliometric pipeline for your own facility

This repository ships two things:

1. **Quick reproduction** — `notebooks/reproduce.ipynb` + Binder (rebuild the published 726-work corpus)
2. **Full operational pipeline** — `scripts/` + `clamps_biblio/` (run discovery through figures for a new instrument or campaign)

---

## Quick start (local, full capabilities)

```bash
git clone <your-repo-url>
cd <repo>
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium          # only for HTML full-text scan
cp config.yaml.example config.yaml   # set openalex.mailto
bash setup.sh                        # restore checkpoints for quick path
```

**Quick path** (from checkpoints, ~1 min):

```bash
bash verify.sh
```

**Full path** (from scratch, days): follow `PIPELINE.md` phases 1–6.

---

## What to customize for another facility

### 1. `config.yaml`

| Setting | Change to |
|---------|-----------|
| `openalex.mailto` | Your email (OpenAlex polite pool) |
| `institutions.*` | OpenAlex institution IDs for your home org |
| `search_phrases` | Your instrument/facility identity terms |
| `field_campaigns` | Campaigns where the instrument deployed |
| `nwc_affiliations` | Co-author institution patterns for affiliation splits |
| `seed_works` | Foundational overview + dataset papers for citation seeds |
| `grant_numbers` | NSF/DOE grants tied to the facility |

### 2. `data/discovery_channels.yaml`

Defines channels A–G (facility search, campaign queries, dataset citations, author seeds, ground truth).
Adjust query budgets, confidence rules, and channel enable flags.

### 3. Registries (required for a rigorous corpus)

| File | Purpose |
|------|---------|
| `data/ground_truth_clamps_papers.csv` | Mandatory publication list (your curated set) |
| `data/clamps_dataset_dois.txt` | Seed dataset DOIs (mandatory inclusion) |
| `data/author_seeds.yaml` | Key author bibliographies (Channel D) |
| `data/campaign_anchors.yaml` | Per-campaign year floors |
| `data/topic_filters.yaml` | Exclude unrelated research areas |

### 4. Manual review artifacts (commit after your review)

| File | Purpose |
|------|---------|
| `data/campaign_review_overrides.csv` | Final campaign labels for heatmap |
| `data/affiliation_overrides.csv` | Fix missing OpenAlex institution metadata |
| `data/manual_pdf_scan_hits.csv` | Human-verified CLAMPS mentions |
| `data/manual_pdf_scan_misses.csv` | Human-verified false positives |
| `output/clamps_theses_master_list.csv` | Set `manual_flag=y` for accepted theses |

### 5. Thesis discovery (optional but recommended)

- `data/thesis_institutions.yaml` — universities to search (Channel F)
- `data/thesis_repositories.yaml` — IR repos to crawl (Channel H)

---

## Pipeline phases (operational)

| Phase | Scripts | Output |
|-------|---------|--------|
| 1 Discovery | `discover_channels.py`, `discover_thesis_*.py`, `merge_channel_outputs.py` | `clamps_papers_discovered_channels.csv` |
| 2 PDF/HTML scan | `resolve_pdf_urls*.py`, `scan_pdfs.py`, `apply_manual_scan_*.py` | scan logs + mentions |
| 3 Deposits | `build_data_deposits_export.py`, `ensure_mandatory_corpus_inputs.py` | `clamps_data_deposits.csv` |
| 4 Theses | `triage_thesis_repos.py`, `build_theses_master_list.py` + manual review | `clamps_theses_master_list.csv` |
| 5 Corpus | `build_review_corpus.py`, `export_review_corpus_clean.py` | 726-work clean CSV |
| 6 Figures | `plot_review_figures.py` | Fig. 8, S1, Tables X/Y |

See `PIPELINE.md` for exact commands and caveats (AMS cookies, rate limits).

---

## Outputs you should publish

| Artifact | Where | DOI? |
|----------|-------|------|
| Clean corpus CSV | Zenodo | **Yes** (primary data citation) |
| This repository (tagged release) | GitHub + Zenodo | **Yes** (software citation) |
| Binder notebook | GitHub (this repo) | Link from README; cite Zenodo |
| Query inventory / scan logs | Supplement or Zenodo | Optional |

---

## Tests

```bash
python -m pytest tests/ -q
```

---

## Support files

- `PIPELINE.md` — step-by-step reproduction for CLAMPS specifically
- `MANIFEST.md` — file inventory
- `ZENODO.md` — how to mint DOIs
- `CITATION.cff` — citation metadata for GitHub/Zenodo
