#!/usr/bin/env bash
# Download ci_c1 plot-ready data when not present locally (Binder / fresh clone).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/data/ci_c1"
MARKER="$DEST/.export_complete"
TARBALL="$ROOT/.cache/ci_c1_data.tar.gz"

# Default: GitHub Release asset (see case_reproduce/data/README.md).
DEFAULT_URL="https://github.com/eeeeelizzzzz/CLAMPS_Resources/releases/download/case-data-v1/ci_c1_data.tar.gz"
URL="${CI_C1_DATA_URL:-$DEFAULT_URL}"

has_case_data() {
  [[ -d "$DEST/tropoe" ]] || return 1
  find "$DEST/tropoe" "$DEST/dlfp" "$DEST/dlvad" -maxdepth 1 \
    \( -name '*.nc' -o -name '*.cdf' \) -print -quit | grep -q .
}

if [[ -f "$MARKER" ]] && has_case_data; then
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
if ! has_case_data; then
  echo "error: tarball extracted but expected NetCDF inputs are missing under $DEST" >&2
  exit 1
fi
echo "Extracted ci_c1 data to $DEST"
