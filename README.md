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
- Plots: capability, efficiency, reliability PNG files
- Summary tables: `summary_capability.csv`, `summary_efficiency.csv`, `summary_reliability.csv`

