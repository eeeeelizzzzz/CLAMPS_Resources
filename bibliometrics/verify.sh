#!/usr/bin/env bash
# Quick verification: rebuild corpus + figures from checkpoints and compare to deliverables.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  bash setup.sh
fi
# shellcheck disable=SC1091
source .venv/bin/activate
export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.matplotlib}"
mkdir -p "$MPLCONFIGDIR"

if [[ ! -f config.yaml ]]; then
  cp config.yaml.example config.yaml
fi

echo "==> Building review corpus"
python scripts/ensure_mandatory_corpus_inputs.py
python scripts/build_review_corpus.py
python scripts/export_review_corpus_clean.py

echo "==> Generating figures and tables"
python scripts/plot_review_figures.py --no-archive

echo "==> Comparing to deliverables"
python - <<'PY'
import sys
from pathlib import Path
import pandas as pd

root = Path(".")
errors = []

# Corpus row count
clean = pd.read_csv(root / "output/clamps_review_corpus_clean.csv")
ref = pd.read_csv(root / "deliverables/clamps_review_corpus_clean.csv")
if len(clean) != len(ref):
    errors.append(f"Corpus count: got {len(clean)}, expected {len(ref)}")
elif len(clean) != 726:
    errors.append(f"Corpus count: got {len(clean)}, expected 726")

# Work-type breakdown
for wt, n in ref["work_type"].value_counts().sort_index().items():
    got = (clean["work_type"] == wt).sum()
    if got != n:
        errors.append(f"work_type {wt}: got {got}, expected {n}")

# Key figures exist
figs = [
    "fig08_affiliation_by_year_tier_with_deployments.png",
    "fig08_work_type_by_year_with_deployments.png",
    "supp_fig_s1_campaign_by_year.png",
    "table_x_community_metrics.csv",
    "table_y_impact_metrics.csv",
]
for f in figs:
    if not (root / "output/figures" / f).exists():
        errors.append(f"Missing figure output: {f}")

if errors:
    print("VERIFICATION FAILED:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)

print(f"OK: {len(clean)}-work corpus, figures and tables regenerated successfully.")
PY

echo "Verification complete."
