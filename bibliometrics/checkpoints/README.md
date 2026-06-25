# Frozen intermediate pipeline outputs

These files capture the pipeline state **after** discovery, PDF/HTML scanning, deposit
classification, and thesis manual review — but **before** the final 726-work collection merge.

They are included so you can reproduce the published collection and figures in minutes without
re-running the multi-day OpenAlex discovery and PDF scan steps.

## Files

| File | Role |
|------|------|
| `clamps_papers_high_confidence_channels_with_pdfs.csv` | 519 HC publications (articles/reports) |
| `clamps_papers_discovered_channels.csv` | Full discovery pool (ground-truth bypass lookup) |
| `clamps_data_deposits.csv` | Validated dataset deposits (`work_class=x`) |
| `clamps_theses_master_list.csv` | Thesis candidates; 29 with `manual_flag=y` in collection |
| `clamps_publications_html_scan_log.csv` | HTML full-text scan results |
| `clamps_publications_html_mentions.csv` | CLAMPS mention snippets from HTML scan |
| `clamps_scan_log.csv` | PDF scan log (supplemental) |
| `clamps_text_mentions.csv` | PDF mention snippets (may be empty; HTML mentions used) |

## Restore

```bash
bash setup.sh          # copies checkpoints → output/
# or manually:
cp checkpoints/*.csv output/
```

## Full from-scratch rebuild

To regenerate these checkpoints, follow `PIPELINE.md` Phase 1–4. That requires:

- OpenAlex API access (`config.yaml` mailto)
- Institutional AMS cookies for paywalled PDFs (`ams_cookies.txt`)
- Playwright for HTML scraping (`playwright install chromium`)
- Manual thesis review loop (Channel H)
