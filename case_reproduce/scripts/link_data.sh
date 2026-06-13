#!/usr/bin/env bash
# Wire data/ci_c1/ into paths expected by code/case_gallery/case_lib.py.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$ROOT/data/ci_c1"
OUT="$ROOT/output/case_gallery"

mkdir -p "$OUT/staged" "$OUT/windoe" "$OUT/pbl_fuzzy" "$OUT/figures" "$ROOT/.matplotlib"

ln -sfn "../../../data/ci_c1" "$OUT/staged/ci_c1"
ln -sfn "../../../data/ci_c1/windoe" "$OUT/windoe/ci_c1"
ln -sfn "../../../data/ci_c1/pbl_fuzzy" "$OUT/pbl_fuzzy/ci_c1"
ln -sfn "../../../data/ci_c1/figure" "$OUT/figures/ci_c1"

echo "Linked ci_c1 under $OUT/"
