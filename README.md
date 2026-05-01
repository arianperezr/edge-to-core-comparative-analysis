# Cross-Architecture System Validation: Edge-to-Core Performance, Reliability, and AI Workload Resilience

This repository contains an automated validation harness that compares edge, commodity, and enterprise architectures across four pillars:

- **Capability:** CPU scaling under load (`stress-ng`)
- **Efficiency:** I/O behavior across block sizes (`fio`)
- **Reliability:** mean time to recovery (MTTR) under Software-Implemented Fault Injection (SIFI)
- **AI workload resilience:** inference stress testing for a matrix-heavy dense MLP—baseline vs concurrent storage stress—to compare average and p99 latency, jitter, and efficiency loss across tiers

AI inference validation is implemented in `core/ai_inference_test.py`, driven by `run_ai_validation.sh`, and runs by default as the last phase of `./final_run.sh` (use `--skip-ai` or `--ai-only` to change that).

The harness targets cross-architecture tipping-point behavior, including virtualized enterprise conditions (Power10 on `ppc64le` in lab-controlled KVM environments).

The current target lab tiers are:

- Edge: Raspberry Pi 5 (`arm64`)
- Commodity: consumer laptop (`x86_64`)
- Enterprise: IBM Power10 (`ppc64le`)


## One-Command Run (Recommended)

- `./final_run.sh`
- `./final_run.sh --ai-only` (run only AI inference validation; skip prior benchmark suites)
- `./final_run.sh --skip-ai` (run smoke + full collection without AI phase)

## Fresh Install Setup

Use these commands on a new machine before the first benchmark run.

1) Install base dependencies (Debian/Ubuntu):

- `sudo apt update`
- `sudo apt install -y git docker.io bc python3`
- `sudo usermod -aG docker "$USER"` (log out/in once after this)

2) Clone and enter the project:

- `git clone <your-repo-url>`
- `cd edge-to-core-comparative-analysis`

3) Build the benchmark image:

- `docker build -t assurance-harness -f testbenches/Dockerfile .`

4) Run a quick smoke test:

- `ITERATIONS=1 SCENARIOS=baseline ./collect_data.sh`

5) Run a full campaign:

- `ITERATIONS=10 SCENARIOS=baseline,sustained,io_concurrency ./collect_data.sh`
- or simply `./final_run.sh` (includes smoke + full collection, and AI validation by default)
- AI-only rerun for missing data: `./run_ai_validation.sh`
- AI workload tuning (matrix-heavy dense MLP): `AI_BATCH_SIZE=64 AI_INFER_ITERATIONS=1000 ./run_ai_validation.sh`

6) Optional: install plotting dependencies:

- `python3 -m pip install --user --break-system-packages -r analysis/requirements.txt`
- `./analysis/run_plotter.sh results -o analysis/plots --no-show`


## Enterprise Tier Baseline Assumptions

For repeatability of comparative analysis, the enterprise tier documentation assumes:

- Architecture: `ppc64le`
- Virtualization: KVM para-virtualized guest
- Threading policy: SMT1 (1 thread per core)
- Sockets: 8
- Rationale: SMT1 provides a cleaner per-thread comparison baseline relative to commodity x86 measurements.

## Outputs

- Per-run JSON: `processed_results.json` or `perf_run_*.json`
- SIFI recovery series: `mttr_data.csv` (scenario-tagged as `scenario,seconds`)
- AI resilience CSV: `results/ai_resilience_final.csv` with
  `Architecture,Test_Type,Average_Latency,p99_Latency,Jitter_Delta,Efficiency_Loss_Pct,Workload`
- Plots: capability, efficiency, reliability, and AI resilience PNG files
- Summary tables: `summary_capability.csv`, `summary_efficiency.csv`, `summary_reliability.csv`, `summary_ai.csv`

## Finalized Results Snapshot

The repository now includes finalized comparative outputs in `analysis/plots/`.

- Canonical figures:
  - `analysis/plots/plot_capability.png`
  - `analysis/plots/plot_efficiency.png`
  - `analysis/plots/plot_reliability.png`
  - `analysis/plots/plot_ai_resilience.png`
- Canonical summary tables:
  - `analysis/plots/summary_capability.csv`
  - `analysis/plots/summary_efficiency.csv`
  - `analysis/plots/summary_reliability.csv`
  - `analysis/plots/summary_ai.csv`

### Final Findings (Condensed)

- **Capability (stress-ng, baseline):**
  - Consumer Laptop leads raw throughput and scales to `11050.95` bogo ops/s at 8 threads.
  - IBM Power10 scales near-linearly to `4617.09` bogo ops/s at 8 threads.
  - Raspberry Pi 5 reaches `610.11` at 4 threads and declines to `573.43` at 8 threads (early saturation).
- **Efficiency (fio write, baseline):**
  - IBM Power10 provides the best combined profile for large blocks:
    - `4379.74 MiB/s` at `4M` and `2857.52 MiB/s` at `1M`
    - lower p99 tails than Raspberry Pi 5 by two orders of magnitude at large blocks.
  - Consumer Laptop is second in bandwidth, but with materially higher p99 tails at large blocks.
  - Raspberry Pi 5 shows severe p99 latency inflation at `1M`/`4M` despite modest bandwidth.
- **Reliability (SIFI MTTR):**
  - Consumer Laptop has the fastest mean MTTR (`4.4065s`).
  - IBM Power10 mean MTTR is `4.9137s` with the tightest variance (`std 0.9181s`).
  - Raspberry Pi 5 has highest MTTR mean (`5.0818s`) and highest variance (`std 1.2554s`).
- **AI stress sensitivity (dense MLP):**
  - Power10: `+3.8%` efficiency loss (most stable under stress).
  - Raspberry Pi 5: `+28.7%` efficiency loss.
  - Consumer Laptop: `+1362.0%` efficiency loss with large tail-latency expansion under stress.

