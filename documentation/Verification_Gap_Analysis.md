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

## Risk 3: AI Inference Determinism Under I/O Stress

- **Risk statement:** Inference latency can degrade or become unstable when storage pressure is present, masking memory-wall behavior and hypervisor-side scheduling effects.
- **Impact:** Medium-High. This affects confidence in workload stability comparisons across `arm64`, `x86_64`, and `ppc64le`.
- **Implemented mitigations:**
  - Dedicated AI validation harness in `core/ai_inference_test.py` with two phases:
    - Idle: 1,000 inferences baseline
    - Stressed: 1,000 inferences during I/O stress (`fio` with `4M` blocks, fallback `stress-ng`)
  - High-resolution latency timing uses `time.perf_counter()` to reduce clock precision issues in KVM guests.
  - Results are appended to `results/ai_resilience_final.csv` via `run_ai_validation.sh`, using fields:
    - `Architecture`
    - `Test_Type` (`Idle` / `Stressed`)
    - `Average_Latency`
    - `p99_Latency`
    - `Jitter_Delta`
    - `Efficiency_Loss_Pct`
  - AI validation is integrated into `final_run.sh` by default, with explicit controls:
    - `./final_run.sh --ai-only` (AI-only path for missing data backfill)
    - `./final_run.sh --skip-ai` (legacy collection path without AI phase)

## Final Evidence Snapshot (Project Finalized)

Finalized outputs in `analysis/plots/` provide measurable evidence that the above mitigations produced stable, interpretable comparison data:

- `summary_ai.csv`:
  - `ppc64le` (Power10) stress efficiency loss: `+3.8%`
  - `aarch64` (Raspberry Pi 5): `+28.7%`
  - `x86_64` (Consumer Laptop): `+1362.0%`
  - Interpretation: the AI stress harness successfully distinguishes deterministic vs stress-sensitive behavior.
- `summary_reliability.csv`:
  - Power10 MTTR mean/std: `4.9137s / 0.9181s`
  - Consumer Laptop MTTR mean/std: `4.4065s / 0.9982s`
  - Raspberry Pi 5 MTTR mean/std: `5.0818s / 1.2554s`
  - Interpretation: host-clock MTTR controls preserve cross-platform comparability with quantified variance.
- `summary_efficiency.csv` (baseline view):
  - Power10 large-block bandwidth: `2857.5 MiB/s (1M)`, `4379.7 MiB/s (4M)`
  - Power10 p99 latency remains materially lower than Raspberry Pi 5 at large blocks.
  - Interpretation: sustained and scenario-tagged aggregation supports visible tipping-point behavior.
