#!/usr/bin/env bash
# Run the plotter with system python.
# Usage: from repo root, ./analysis/run_plotter.sh [path] [-o out_dir] [--no-show]

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

python3 -c "import matplotlib" >/dev/null 2>&1 || {
  echo "Error: matplotlib not available in system python."
  echo "Install python3-matplotlib and retry."
  exit 1
}
exec python3 "$REPO_ROOT/analysis/plotter.py" "$@"
