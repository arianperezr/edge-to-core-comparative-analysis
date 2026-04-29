# Verification Gap Analysis

## Purpose

This document captures the highest-priority verification risks identified during PDR hardening and maps each risk to currently implemented mitigations in the repository.

## Risk 1: Hypervisor Jitter / Abstraction Effects

- **Risk statement:** Virtualized enterprise runs can show scheduler-induced noise that is not directly caused by benchmark logic.
- **Impact:** Medium. Can bias throughput/latency interpretation if samples are sparse.
- **Implemented mitigations:**
  - Scenario-driven sustained profile in `collect_data.sh` (longer-duration runs to average scheduling variance).
  - Repeated-run collection (`ITERATIONS`) in `collect_data.sh` to support mean/std-based interpretation in analysis.
  - Scenario-aware aggregation in `analysis/plotter.py` for statistically stronger comparisons.

## Risk 2: Clock Skew in MTTR Measurement

- **Risk statement:** MTTR can be biased if timing crosses unsynchronized clocks between host and containerized tiers.
- **Impact:** Medium. Directly affects reliability metric validity.
- **Implemented mitigations:**
  - MTTR timing uses host timestamps (`date +%s%N`) in `collect_data.sh` for both start and end time.
  - Recovery check remains container-based (`python3 /app/core/discovery.py`), but timing arithmetic is performed on the host clock.
  - `mttr_data.csv` now initializes with a header (`scenario,seconds`) for consistent parsing and auditability.

## Traceability Notes

- **Environment assumptions for enterprise tier** are now explicit in `core/discovery.py` for `ppc64le`:
  - `virtualization: "KVM-para"`
  - `threading_policy: "SMT1"`
  - `sockets: 8`
- These fields flow into benchmark metadata through `core/main.py` (`metadata` merges architecture details from discovery).
