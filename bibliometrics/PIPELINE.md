# Pipeline reproduction guide

Two paths are supported:

| Path | Time | Requires |
|------|------|----------|
| **A. Quick** (checkpoints → corpus → figures) | ~2 min | `setup.sh` only |
| **B. Full** (OpenAlex discovery → scan → corpus → figures) | days | API access, AMS cookies, manual review |

---

## Path A — Quick reproduction (recommended for verification)

```bash
bash setup.sh
python scripts/ensure_mandatory_corpus_inputs.py
python scripts/build_review_corpus.py
python scripts/export_review_corpus_clean.py
python scripts/plot_review_figures.py
```

Or: `bash verify.sh`

**Expected result:** 726 works; figures in `output/figures/`.

---

## Path B — Full from-scratch pipeline

### Phase 1: OpenAlex discovery

```bash
# Set openalex.mailto in config.yaml first
python scripts/discover_channels.py
python scripts/discover_thesis_openalex.py
python scripts/discover_thesis_repos.py    # slow; may take hours
python scripts/merge_channel_outputs.py
```

**Outputs:** `clamps_papers_discovered_channels.csv`, `clamps_papers_high_confidence_channels.csv`

**Ledger (approximate):**
| Step | Works remaining |
|------|----------------:|
| OpenAlex multi-channel discovery | 6,780 |
| Deduplication | 4,915 |
| Topic exclusions | 4,066 |
| Strict HC gate | 792 |
| Type filter (articles/reports) | 519 |

### Phase 2: PDF/HTML evidence

```bash
python scripts/resolve_pdf_urls.py \
  --input output/clamps_papers_high_confidence_channels.csv \
  --output output/clamps_papers_high_confidence_channels_with_pdfs.csv

python scripts/resolve_pdf_urls_pass2.py

python scripts/build_publications_html_queue.py

python scripts/scan_pdfs.py \
  --input output/clamps_papers_high_confidence_channels_with_pdfs.csv \
  --html-scrape --hybrid-openalex \
  --cookies-file ams_cookies.txt

python scripts/apply_manual_scan_hits.py
python scripts/apply_manual_scan_misses.py
```

**Note:** AMS journals require institutional cookies. OA publishers (Copernicus, ESSD, OSTI)
scan without cookies.

### Phase 3: Data deposits

```bash
python scripts/build_data_deposits_export.py
python scripts/ensure_mandatory_corpus_inputs.py
# Manually validate additional deposits: set work_class=x in clamps_data_deposits.csv
```

**Targets:** 65 seed DOIs (mandatory) + 42 validated discovered deposits = 107 datasets.

### Phase 4: Theses (manual review required)

```bash
python scripts/triage_thesis_repos.py
python scripts/build_theses_master_list.py
# Manual review: flag CLAMPS-related theses with manual_flag=y in master list
# (In this repo, 29 theses are pre-flagged in checkpoints/clamps_theses_master_list.csv)
```

### Phase 5: Corpus assembly

```bash
python scripts/ensure_mandatory_corpus_inputs.py
python scripts/build_review_corpus.py
python scripts/export_review_corpus_clean.py
```

**Merge logic:**
```
519 HC publications
+ 107 datasets (65 seed + 42 validated)
+ 72 ground-truth bypass
+ 28 manual theses
= 726 works (after deduplication)
```

### Phase 6: Figures and tables

```bash
python scripts/plot_review_figures.py
```

**Outputs:**
- Fig. 8 affiliation (gray=all works, gold=articles+reports)
- Fig. 8 work-type stacks
- Supp. Fig. S1 campaign × year heatmap
- Table X (community metrics), Table Y (impact tiers)

---

## Manual review artifacts (committed in `data/`)

These encode human decisions and are required for exact reproduction:

| File | Decisions captured |
|------|-------------------|
| `ground_truth_clamps_papers.csv` | 132 mandatory registry works |
| `clamps_dataset_dois.txt` | 65 seed dataset DOIs |
| `campaign_review_overrides.csv` | 417 campaign label corrections |
| `manual_pdf_scan_hits.csv` | Human-verified CLAMPS mentions |
| `manual_pdf_scan_misses.csv` | Human-verified non-hits |
| `affiliation_overrides.csv` | NWC affiliation fixes |
| `clamps_theses_master_list.csv` (checkpoint) | 29 accepted theses (`manual_flag=y`) |

---

## Discovery channels (reference)

| Channel | Method |
|---------|--------|
| A | Facility identity phrases |
| B | Campaign × instrument compound queries |
| C | Dataset DOI + grant citations |
| D | Author seed bibliographies |
| E | Campaign anchor-paper author groups |
| F | OpenAlex thesis institution search |
| G | Ground-truth DOI registry |
| H | Institutional repository crawl (SHAREOK, etc.) |

Channel definitions: `data/discovery_channels.yaml`

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| OpenAlex 429 rate limit | Increase `openalex_delay` in config.yaml |
| AMS PDF 403 | Add `ams_cookies.txt` from institutional session |
| Missing `clamps_local_scan_log.csv` | `setup.sh` creates empty stub |
| Corpus count ≠ 726 | Ensure checkpoints restored; run `ensure_mandatory_corpus_inputs.py` |
| Playwright errors | `playwright install chromium` |
