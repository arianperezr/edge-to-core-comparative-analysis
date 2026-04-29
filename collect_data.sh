#!/bin/bash
set -u

# Configuration
ARCH=$(python3 -c "import platform; print(platform.machine())")
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ITERATIONS=${ITERATIONS:-10}
SCENARIOS=${SCENARIOS:-baseline,sustained,io_concurrency}
IMAGE_NAME=${IMAGE_NAME:-assurance-harness}
# Using PWD ensures Docker volume mapping is absolute and stable
BASE_DIR=$(pwd)
RESULTS_DIR="results/${ARCH}_${TIMESTAMP}"
mkdir -p "$BASE_DIR/$RESULTS_DIR"
MTTR_FILE="$BASE_DIR/$RESULTS_DIR/mttr_data.csv"

echo "-------------------------------------------------------"
echo "Starting Automated Data Collection for: $ARCH"
echo "Iterations per phase: $ITERATIONS"
echo "Scenarios: $SCENARIOS"
echo "Results will be stored in: $BASE_DIR/$RESULTS_DIR"
echo "-------------------------------------------------------"

if ! command -v docker >/dev/null 2>&1; then
    echo "Error: docker is required but was not found in PATH."
    exit 1
fi

if ! command -v bc >/dev/null 2>&1; then
    echo "Error: bc is required for MTTR math. Install it and retry."
    exit 1
fi

if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    echo "Docker image '$IMAGE_NAME' not found. Building it now..."
    docker build -t "$IMAGE_NAME" -f testbenches/Dockerfile .
fi

# Ensure MTTR CSV has a header when first created.
if [ ! -f "$MTTR_FILE" ]; then
    echo "scenario,seconds" > "$MTTR_FILE"
fi

configure_scenario() {
    local scenario="$1"
    case "$scenario" in
        baseline)
            export BENCHMARK_SCENARIO="baseline"
            export CPU_SWEEP_DURATION_S="${CPU_SWEEP_DURATION_S:-5}"
            export FIO_RUNTIME_S="${FIO_RUNTIME_S:-5}"
            export FIO_IODEPTHS="${FIO_IODEPTHS:-1}"
            export FIO_NUMJOBS="${FIO_NUMJOBS:-1}"
            export FIO_RW="${FIO_RW:-write}"
            ;;
        sustained)
            export BENCHMARK_SCENARIO="sustained"
            export CPU_SWEEP_DURATION_S="${CPU_SWEEP_DURATION_S:-60}"
            export FIO_RUNTIME_S="${FIO_RUNTIME_S:-60}"
            export FIO_IODEPTHS="${FIO_IODEPTHS:-8}"
            export FIO_NUMJOBS="${FIO_NUMJOBS:-4}"
            export FIO_RW="${FIO_RW:-randrw}"
            ;;
        io_concurrency)
            export BENCHMARK_SCENARIO="io_concurrency"
            export CPU_SWEEP_DURATION_S="${CPU_SWEEP_DURATION_S:-15}"
            export FIO_RUNTIME_S="${FIO_RUNTIME_S:-30}"
            export FIO_IODEPTHS="${FIO_IODEPTHS:-1,8,32,64}"
            export FIO_NUMJOBS="${FIO_NUMJOBS:-1,4,8}"
            export FIO_RW="${FIO_RW:-randrw}"
            ;;
        *)
            echo "Unknown scenario '$scenario'. Skipping."
            return 1
            ;;
    esac
    return 0
}

run_scenario() {
    local scenario="$1"

    echo -e "\n[Scenario: $scenario] Collecting Capability & Efficiency Data..."
    for i in $(seq 1 "$ITERATIONS")
    do
        echo "  -> Iteration $i/$ITERATIONS (Clean Run)..."

        if ! docker run --rm \
            -e BENCHMARK_SCENARIO="$BENCHMARK_SCENARIO" \
            -e CPU_SWEEP_DURATION_S="$CPU_SWEEP_DURATION_S" \
            -e FIO_RUNTIME_S="$FIO_RUNTIME_S" \
            -e FIO_IODEPTHS="$FIO_IODEPTHS" \
            -e FIO_NUMJOBS="$FIO_NUMJOBS" \
            -e FIO_RW="$FIO_RW" \
            -v "$BASE_DIR/$RESULTS_DIR:/app/results" \
            "$IMAGE_NAME" \
            python3 /app/core/main.py; then
            echo "     Error: clean run failed for scenario '$scenario', iteration $i."
            exit 1
        fi

        if [ -f "$BASE_DIR/$RESULTS_DIR/processed_results.json" ]; then
            mv "$BASE_DIR/$RESULTS_DIR/processed_results.json" "$BASE_DIR/$RESULTS_DIR/perf_run_${scenario}_$i.json"
        else
            echo "     Warning: processed_results.json not found for iteration $i"
        fi
    done

    echo -e "\n[Scenario: $scenario] Collecting Reliability (SIFI) Data..."
    for i in $(seq 1 "$ITERATIONS")
    do
        echo "  -> Iteration $i/$ITERATIONS (Fault Injection Run)..."
        START_TIME=$(date +%s%N)

        docker run --rm \
            -e BENCHMARK_SCENARIO="$BENCHMARK_SCENARIO" \
            -e CPU_SWEEP_DURATION_S="$CPU_SWEEP_DURATION_S" \
            -e FIO_RUNTIME_S="$FIO_RUNTIME_S" \
            -e FIO_IODEPTHS="$FIO_IODEPTHS" \
            -e FIO_NUMJOBS="$FIO_NUMJOBS" \
            -e FIO_RW="$FIO_RW" \
            -e ENABLE_SIFI=true \
            -v "$BASE_DIR/$RESULTS_DIR:/app/results" \
            "$IMAGE_NAME" \
            python3 /app/core/main.py

        if [ $? -ne 0 ]; then
            echo "     Fault detected! Measuring recovery..."
            until docker run --rm "$IMAGE_NAME" python3 /app/core/discovery.py > /dev/null 2>&1; do
                echo -n "."
                sleep 0.5
            done

            END_TIME=$(date +%s%N)
            MTTR=$(echo "scale=3; ($END_TIME - $START_TIME) / 1000000000" | bc)
            echo -e "\n     Recovery Successful! MTTR: ${MTTR}s"
            echo "${scenario},$MTTR" >> "$MTTR_FILE"
        fi
    done
}

IFS=',' read -ra SCENARIO_LIST <<< "$SCENARIOS"
for scenario in "${SCENARIO_LIST[@]}"
do
    scenario=$(echo "$scenario" | xargs)
    [ -z "$scenario" ] && continue
    if configure_scenario "$scenario"; then
        run_scenario "$scenario"
    fi
done

echo -e "\n-------------------------------------------------------"
echo "DATA COLLECTION COMPLETE!"
echo "Check $RESULTS_DIR for your JSON and CSV files."
echo "-------------------------------------------------------"