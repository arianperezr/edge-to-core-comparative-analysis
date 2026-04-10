#!/bin/bash

# Configuration
ARCH=$(python3 -c "import platform; print(platform.machine())")
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ITERATIONS=${ITERATIONS:-10}
# Using PWD ensures Docker volume mapping is absolute and stable
BASE_DIR=$(pwd)
RESULTS_DIR="results/${ARCH}_${TIMESTAMP}"
mkdir -p "$BASE_DIR/$RESULTS_DIR"

echo "-------------------------------------------------------"
echo "Starting Automated Data Collection for: $ARCH"
echo "Iterations per phase: $ITERATIONS"
echo "Results will be stored in: $BASE_DIR/$RESULTS_DIR"
echo "-------------------------------------------------------"

# 1. PILLAR 1 & 3: PERFORMANCE SWEEP
echo "[Phase 1] Collecting Capability & Efficiency Data..."
for i in $(seq 1 "$ITERATIONS")
do
    echo "  -> Iteration $i/$ITERATIONS (Clean Run)..."
    
    # Run the bench with absolute path volume mapping
    docker run --rm \
        -v "$BASE_DIR/$RESULTS_DIR:/app/results" \
        assurance-harness \
        python3 /app/core/main.py
    
    # Rename only if the file exists (prevents mv errors)
    if [ -f "$BASE_DIR/$RESULTS_DIR/processed_results.json" ]; then
        mv "$BASE_DIR/$RESULTS_DIR/processed_results.json" "$BASE_DIR/$RESULTS_DIR/perf_run_$i.json"
    else
        echo "     Warning: processed_results.json not found for iteration $i"
    fi
done

# 2. PILLAR 2: RELIABILITY SWEEP (SIFI)
echo -e "\n[Phase 2] Collecting Reliability (SIFI) Data..."
for i in $(seq 1 "$ITERATIONS")
do
    echo "  -> Iteration $i/$ITERATIONS (Fault Injection Run)..."
    START_TIME=$(date +%s%N)
    
    # Run with SIFI enabled. We don't expect a JSON here because it crashes.
    docker run --rm \
        -e ENABLE_SIFI=true \
        -v "$BASE_DIR/$RESULTS_DIR:/app/results" \
        assurance-harness \
        python3 /app/core/main.py
    
    # The container exits with code 1 due to sys.exit(1) in main.py
    if [ $? -ne 0 ]; then
        echo "     Fault detected! Measuring recovery..."
        
        # RECOVERY CHECK: Loop until discovery.py returns success
        until docker run --rm assurance-harness python3 /app/core/discovery.py > /dev/null 2>&1; do
            echo -n "."
            sleep 0.5
        done
        
        END_TIME=$(date +%s%N)
        # Calculate MTTR (Mean Time To Recovery)
        MTTR=$(echo "scale=3; ($END_TIME - $START_TIME) / 1000000000" | bc)
        echo -e "\n     Recovery Successful! MTTR: ${MTTR}s"
        echo "$MTTR" >> "$BASE_DIR/$RESULTS_DIR/mttr_data.csv"
    fi
done

echo -e "\n-------------------------------------------------------"
echo "DATA COLLECTION COMPLETE!"
echo "Check $RESULTS_DIR for your JSON and CSV files."
echo "-------------------------------------------------------"