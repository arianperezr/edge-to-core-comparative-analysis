#!/usr/bin/env bash
# One-command data-collection wrapper for final benchmark campaigns.
# - No plotting here (analysis is done later on a designated laptop).
# - Runs a quick smoke test first unless SKIP_SMOKE=true.

set -euo pipefail

ITERATIONS="${ITERATIONS:-100}"
SCENARIOS="${SCENARIOS:-baseline,sustained,io_concurrency}"
SMOKE_ITERATIONS="${SMOKE_ITERATIONS:-1}"
SMOKE_SCENARIOS="${SMOKE_SCENARIOS:-baseline}"
SKIP_SMOKE="${SKIP_SMOKE:-false}"
RUN_MODE="${RUN_MODE:-full}"

for arg in "$@"; do
  case "$arg" in
    --ai-only)
      RUN_MODE="ai_only"
      ;;
    --skip-ai)
      RUN_MODE="full_no_ai"
      ;;
    *)
      echo "Unknown argument: $arg"
      echo "Usage: ./final_run.sh [--ai-only] [--skip-ai]"
      exit 1
      ;;
  esac
done

echo "======================================================="
echo "Final Data Collection Wrapper"
echo "ITERATIONS=$ITERATIONS"
echo "SCENARIOS=$SCENARIOS"
echo "SKIP_SMOKE=$SKIP_SMOKE"
echo "RUN_MODE=$RUN_MODE"
echo "======================================================="

if [[ "$RUN_MODE" == "ai_only" ]]; then
  echo
  echo "[1/1] AI inference validation only"
  ./run_ai_validation.sh
  echo
  echo "Collection complete."
  exit 0
fi

if [[ "$SKIP_SMOKE" != "true" ]]; then
  echo
  echo "[1/3] Smoke test collection"
  ITERATIONS="$SMOKE_ITERATIONS" SCENARIOS="$SMOKE_SCENARIOS" ./collect_data.sh
fi

echo
echo "[2/3] Full collection"
ITERATIONS="$ITERATIONS" SCENARIOS="$SCENARIOS" ./collect_data.sh

if [[ "$RUN_MODE" != "full_no_ai" ]]; then
  echo
  echo "[3/3] AI inference validation"
  ./run_ai_validation.sh
fi

echo
echo "Collection complete."
echo "Results are in the newest folder under results/."
