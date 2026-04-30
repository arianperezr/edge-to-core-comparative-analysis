#!/usr/bin/env bash
set -euo pipefail

RESULTS_CSV="${AI_RESULTS_CSV:-results/ai_resilience_final.csv}"
VENV_DIR="${AI_VENV_DIR:-.venv_ai_validation}"
PY_USER_BASE="${AI_PY_USER_BASE:-.python_user_base}"

echo "======================================================="
echo "AI Inference Validation Runner"
echo "Results CSV: $RESULTS_CSV"
echo "======================================================="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required but not found in PATH."
  exit 1
fi

USE_VENV="true"
if [ ! -x "$VENV_DIR/bin/python" ] || [ ! -x "$VENV_DIR/bin/pip" ]; then
  echo "Creating virtual environment at $VENV_DIR ..."
  if ! python3 -m venv "$VENV_DIR"; then
    echo "Warning: python venv creation failed; falling back to user-site install."
    USE_VENV="false"
  fi
fi

if [ "$USE_VENV" = "true" ] && [ -x "$VENV_DIR/bin/python" ] && [ -x "$VENV_DIR/bin/pip" ]; then
  PYTHON_BIN="$VENV_DIR/bin/python"
  PIP_BIN="$VENV_DIR/bin/pip"
else
  USE_VENV="false"
  PYTHON_BIN="python3"
  PIP_BIN="python3 -m pip"
  PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  PY_USER_SITE="$PY_USER_BASE/lib/python$PY_VER/site-packages"
fi

if ! command -v fio >/dev/null 2>&1 && ! command -v stress-ng >/dev/null 2>&1; then
  echo "Error: either fio or stress-ng is required for stressed inference phase."
  exit 1
fi

if [ "$USE_VENV" = "true" ] && [ -x "$VENV_DIR/bin/python" ]; then
  IMPORT_CHECK_CMD=("$PYTHON_BIN" -c "import numpy, sklearn")
else
  IMPORT_CHECK_CMD=(env PYTHONUSERBASE="$PY_USER_BASE" PYTHONPATH="$PY_USER_SITE:${PYTHONPATH:-}" "$PYTHON_BIN" -c "import numpy, sklearn")
fi

if ! "${IMPORT_CHECK_CMD[@]}" >/dev/null 2>&1; then
  echo "Installing required Python packages (numpy, scikit-learn)..."
  if [ "$USE_VENV" = "true" ] && [ -x "$VENV_DIR/bin/pip" ]; then
    "$VENV_DIR/bin/pip" install numpy scikit-learn
  else
    PYTHONUSERBASE="$PY_USER_BASE" python3 -m pip install --user --break-system-packages --ignore-installed numpy scikit-learn
  fi
fi

mkdir -p "$(dirname "$RESULTS_CSV")"
if [ "$USE_VENV" = "true" ] && [ -x "$VENV_DIR/bin/python" ]; then
  AI_RESULTS_CSV="$RESULTS_CSV" "$PYTHON_BIN" core/ai_inference_test.py
else
  PYTHONUSERBASE="$PY_USER_BASE" PYTHONPATH="$PY_USER_SITE:${PYTHONPATH:-}" AI_RESULTS_CSV="$RESULTS_CSV" "$PYTHON_BIN" core/ai_inference_test.py
fi

echo
echo "AI validation complete. Appended results to $RESULTS_CSV"
