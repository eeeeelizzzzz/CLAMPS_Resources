#!/usr/bin/env bash
# Download ci_c1 plot-ready data when not present locally (Binder / fresh clone).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/data/ci_c1"
MARKER="$DEST/.export_complete"
TARBALL="$ROOT/.cache/ci_c1_data.tar.gz"

# Default: GitHub Release asset (see case_reproduce/data/README.md).
DEFAULT_URL="https://github.com/eeeeelizzzzz/CLAMPS_CaseGallery/releases/download/case-data-v1/ci_c1_data.tar.gz"
URL="${CI_C1_DATA_URL:-$DEFAULT_URL}"

if [[ -f "$MARKER" ]]; then
  echo "ci_c1 data already present at $DEST"
  exit 0
fi

if [[ ! -f "$TARBALL" ]]; then
  mkdir -p "$(dirname "$TARBALL")"
  echo "Downloading ci_c1 data from:"
  echo "  $URL"
  curl -fsSL -L -o "$TARBALL" "$URL"
fi

rm -rf "$DEST"
mkdir -p "$ROOT/data"
tar -xzf "$TARBALL" -C "$ROOT/data"
echo "Extracted ci_c1 data to $DEST"
