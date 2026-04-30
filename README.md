# Enterprise ISA Resilience

This repository contains an automated validation harness that compares edge, commodity, and enterprise architectures across three pillars:

- Capability: CPU scaling under load (`stress-ng`)
- Efficiency: I/O behavior across block sizes (`fio`)
- Reliability: MTTR under Software-Implemented Fault Injection (SIFI)

The current implementation is a validation framework for cross-architecture tipping-point behavior, including virtualized enterprise conditions (Power10 on ppc64le in lab-controlled KVM environments).

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
- `sudo apt install -y git docker.io bc python3 python3-venv`
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

6) Optional: install plotting dependencies:

- `python3 -m venv .venv`
- `source .venv/bin/activate`
- `pip install -r analysis/requirements.txt`
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
  `Architecture,Test_Type,Average_Latency,p99_Latency,Jitter_Delta,Efficiency_Loss_Pct`
- Plots: capability, efficiency, reliability PNG files
- Summary tables: `summary_capability.csv`, `summary_efficiency.csv`, `summary_reliability.csv`

