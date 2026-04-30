#!/usr/bin/env bash
set -euo pipefail

RESULTS_CSV="${AI_RESULTS_CSV:-results/ai_resilience_final.csv}"
PY_USER_BASE="${AI_PY_USER_BASE:-.python_user_base}"
AI_REPEATS="${AI_REPEATS:-100}"
AI_INFER_ITERATIONS="${AI_INFER_ITERATIONS:-1000}"

echo "======================================================="
echo "AI Inference Validation Runner"
echo "Results CSV: $RESULTS_CSV"
echo "AI_REPEATS: $AI_REPEATS"
echo "AI_INFER_ITERATIONS: $AI_INFER_ITERATIONS"
echo "======================================================="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required but not found in PATH."
  exit 1
fi

PYTHON_BIN="python3"
PIP_BIN="python3 -m pip"
PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_USER_SITE="$PY_USER_BASE/lib/python$PY_VER/site-packages"

if ! command -v fio >/dev/null 2>&1 && ! command -v stress-ng >/dev/null 2>&1; then
  echo "Error: either fio or stress-ng is required for stressed inference phase."
  exit 1
fi

IMPORT_CHECK_CMD=(env PYTHONUSERBASE="$PY_USER_BASE" PYTHONPATH="$PY_USER_SITE:${PYTHONPATH:-}" "$PYTHON_BIN" -c "import numpy")

if ! "${IMPORT_CHECK_CMD[@]}" >/dev/null 2>&1; then
  echo "Installing required Python packages (numpy)..."
  PYTHONUSERBASE="$PY_USER_BASE" python3 -m pip install --user --break-system-packages --ignore-installed numpy
fi

mkdir -p "$(dirname "$RESULTS_CSV")"
for i in $(seq 1 "$AI_REPEATS"); do
  echo
  echo "[AI Run $i/$AI_REPEATS]"
  PYTHONUSERBASE="$PY_USER_BASE" PYTHONPATH="$PY_USER_SITE:${PYTHONPATH:-}" AI_RESULTS_CSV="$RESULTS_CSV" AI_INFER_ITERATIONS="$AI_INFER_ITERATIONS" "$PYTHON_BIN" core/ai_inference_test.py
done

echo
echo "AI validation complete. Appended results to $RESULTS_CSV"
