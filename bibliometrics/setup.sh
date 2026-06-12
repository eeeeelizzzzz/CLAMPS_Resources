#!/usr/bin/env bash
# Initialize the bibliometrics repo for reproduction.
# Run from the bibliometrics/ directory root.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "==> CLAMPS bibliometric pipeline setup"

# Config
if [[ ! -f config.yaml ]]; then
  cp config.yaml.example config.yaml
  echo "Created config.yaml from config.yaml.example"
  echo "  Edit config.yaml and set openalex.mailto before running discovery."
else
  echo "config.yaml already exists"
fi

# Virtual environment
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  echo "Created .venv"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
echo "Python dependencies installed"

# Restore pipeline checkpoints into output/
mkdir -p output/review_metrics
CHECKPOINTS=(
  clamps_papers_high_confidence_channels_with_pdfs.csv
  clamps_papers_discovered_channels.csv
  clamps_data_deposits.csv
  clamps_theses_master_list.csv
  clamps_publications_html_scan_log.csv
  clamps_publications_html_mentions.csv
  clamps_scan_log.csv
  clamps_text_mentions.csv
)
for f in "${CHECKPOINTS[@]}"; do
  if [[ -f "checkpoints/$f" ]]; then
    cp "checkpoints/$f" "output/$f"
  fi
done

# Empty local scan log stub (optional; not used in published results)
if [[ ! -f output/clamps_local_scan_log.csv ]]; then
  echo "openalex_id,doi,status,mention_count,matched_terms,match_strength,error" > output/clamps_local_scan_log.csv
fi

echo ""
echo "Checkpoints restored to output/"
echo ""
echo "Quick reproduction (corpus + figures):"
echo "  source .venv/bin/activate"
echo "  python scripts/ensure_mandatory_corpus_inputs.py"
echo "  python scripts/build_review_corpus.py"
echo "  python scripts/export_review_corpus_clean.py"
echo "  python scripts/plot_review_figures.py"
echo ""
echo "Or run: bash verify.sh"
