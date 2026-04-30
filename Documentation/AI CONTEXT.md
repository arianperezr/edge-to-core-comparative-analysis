# AI CONTEXT — COMPLETE REPOSITORY BRIEFING

## 1) Repository Identity

- **Project name:** Edge-to-Core Comparative Analysis
- **Mission focus:** Virtualized Enterprise ISA Resilience
- **Primary objective:** Compare workload behavior across edge, commodity, and enterprise architectures to identify tipping points in capability, efficiency, and resilience.
- **Academic/professional context:** Built to satisfy systems engineering rigor (traceability, risk, verification) and computer engineering rigor (implementation validity, measurement fidelity, reproducibility).

## 2) Core Research Framing

- **Hypothesis:** Enterprise-class architecture (IBM Power10 profile) maintains more deterministic behavior under sustained and concurrent workloads than commodity/edge tiers.
- **Evaluation dimensions:**
  - **Capability** (CPU throughput scaling)
  - **Efficiency** (I/O throughput and tail latency behavior)
  - **Reliability** (MTTR under software-injected faults)
- **Comparative tiers:**
  - **Edge:** Raspberry Pi 5 (`arm64`)
  - **Commodity:** Consumer laptop (`x86_64`)
  - **Enterprise:** IBM Power10 (`ppc64le`)

## 3) Enterprise Baseline Assumptions (Explicit)

For repository-aligned documentation and review:

- `isa`: `ppc64le`
- `virtualization`: `KVM-para`
- `threading_policy`: `SMT1`
- `sockets`: `8`
- **Fairness control assumption:** SMT1 is treated as a per-thread baseline for cross-architecture comparisons.

These values are encoded in `core/discovery.py` for Power10 metadata.

## 4) Current Implementation Boundaries

### Implemented telemetry (default outputs)

- `stress-ng` CPU sweep -> `ops_per_sec`
- `fio` sweep -> `bw_mib_s`, `p99_lat_us`
- SIFI + recovery timing -> MTTR samples in `mttr_data.csv`

### Not currently emitted in default schema

- Hardware perf counters (e.g., L3 cache misses)
- Thermal sensor series
- Direct power telemetry / measured perf-per-watt

## 5) Runtime Architecture

### Container image

- Defined in `testbenches/Dockerfile`
- Base: `ubuntu:22.04`
- Installs: `python3`, `python3-pip`, `fio`, `sysbench`, `stress-ng`, `ca-certificates`
- Entrypoint: `python3 /app/core/main.py`

### Build/run flows

- **Compose flow:** `docker-compose.yml` -> image `edge-to-core/lab:latest`
- **Collection flow:** `collect_data.sh` -> image `assurance-harness`
- These are logically equivalent images built from the same Dockerfile with different tags.

### Multi-architecture targets

- `linux/amd64`
- `linux/arm64`
- `linux/ppc64le`

## 6) Benchmark Orchestration Logic

## 6.1 `core/main.py` behavior

- Discovers platform metadata via `get_arch_details()`
- Reads scenario/profile env vars
- Runs:
  - capability sweep (CPU threads)
  - efficiency sweep (fio block/concurrency dimensions)
- Optional SIFI mode (`ENABLE_SIFI=true`) exits with simulated fault
- Writes `/app/results/processed_results.json`

## 6.2 `collect_data.sh` behavior

- Creates run directory: `results/<arch>_<timestamp>/`
- Supports scenarios:
  - `baseline`
  - `sustained`
  - `io_concurrency`
- For each scenario:
  - **Phase 1:** clean runs -> `perf_run_<scenario>_<n>.json`
  - **Phase 2:** SIFI runs + MTTR measurement
- MTTR timing:
  - Uses **host clock** (`date +%s%N`) for start/end
  - Polls container health via `python3 /app/core/discovery.py`
- MTTR CSV handling:
  - Initializes `mttr_data.csv` with header `scenario,seconds` if missing
  - Appends rows as `<scenario>,<seconds>`

## 7) Data Contracts

### 7.1 JSON output (`processed_results.json` / `perf_run_*.json`)

- Top-level keys:
  - `metadata`
  - `capability_sweep`
  - `efficiency_sweep`

### 7.2 Metadata shape

- Includes discovery data:
  - `isa`
  - `type`
  - `is_enterprise`
  - plus Power10 fields when applicable (`virtualization`, `threading_policy`, `sockets`)
- Includes benchmark profile:
  - `benchmark_scenario`
  - thread/runtime/block/concurrency config

### 7.3 MTTR CSV

- Preferred format: `scenario,seconds`
- Legacy parsing compatibility exists in analysis for rows without scenario tag.

## 8) Analysis Pipeline

### 8.1 `analysis/plotter.py` capabilities

- Loads one or many result directories/files
- Aggregates repeated runs by scenario/workload keys
- Computes:
  - mean
  - standard deviation
- Produces:
  - `plot_capability.png`
  - `plot_efficiency.png`
  - `plot_reliability.png`
  - `summary_capability.csv`
  - `summary_efficiency.csv`
  - `summary_reliability.csv`

### 8.2 Plot behavior notes

- Capability/efficiency/reliability plots include percentage-delta annotations relative to a selected reference architecture.
- Full statistical variability is preserved in summary CSVs.

## 9) Repository Map (High-Value Files)

- `README.md` -> project summary, workflow commands, output expectations
- `docker-compose.yml` -> compose build/run and multi-arch platform targets
- `run_lab.sh` -> quick single-pass run wrapper
- `collect_data.sh` -> scenario-driven repeated data collection + MTTR
- `core/main.py` -> benchmark execution and result writing
- `core/discovery.py` -> architecture classification and enterprise assumptions
- `analysis/plotter.py` -> aggregation, plotting, summary CSV generation
- `analysis/run_plotter.sh` -> user-site-safe plot runner
- `testbenches/Dockerfile` -> container definition
- `Documentation/Project Overview` -> mission/scope/workflow summary
- `Documentation/Repository-File-Guide.txt` -> file-by-file guide
- `Documentation/Graphs Overview.txt` -> graph interpretation guide
- `Documentation/Verification_Gap_Analysis.md` -> risk-to-mitigation traceability
- `Documentation/Graduate-Lab-Report-Template.md` -> final report scaffolding

## 10) Verification and Risk Traceability

Key explicit risks and implemented controls:

- **Hypervisor jitter / abstraction effects**
  - Mitigations: sustained profile + repeated sampling + aggregated analysis
- **Clock skew in MTTR comparison**
  - Mitigations: host-clock MTTR timing (`date +%s%N`) and structured CSV output

See `Documentation/Verification_Gap_Analysis.md` for consolidated mapping.

## 11) Reproducibility Workflow

1. Build/run quick pass:
   - `./run_lab.sh`
2. Collect repeated scenario data:
   - `./collect_data.sh`
3. Generate plots and summary tables:
   - `./analysis/run_plotter.sh results -o analysis/plots --no-show`

Expected artifacts:

- `results/<arch>_<timestamp>/perf_run_<scenario>_<n>.json`
- `results/<arch>_<timestamp>/mttr_data.csv`
- Plot PNGs + summary CSVs in chosen output directory

## 12) Reviewer Guidance (for External AI)

When reviewing this project, evaluate along two axes:

- **Systems engineering rigor**
  - requirement/verification traceability
  - explicit assumptions and risk controls
  - reproducibility and acceptance gates
- **Computer engineering rigor**
  - measurement validity across architectures
  - scenario realism (`baseline`, `sustained`, `io_concurrency`)
  - resilience characterization via MTTR and variability

Do not assume unimplemented telemetry (perf counters, thermal series, real power sensors) unless added to code and output contracts.

## 13) Maintenance Gate (Update This File If Any Trigger Occurs)

Update this AI context immediately when any of the following changes:

1. `core/main.py` output schema or env var handling
2. `collect_data.sh` scenario logic, MTTR method, or CSV format
3. `core/discovery.py` architecture mappings/metadata keys
4. `analysis/plotter.py` aggregation semantics or output files
5. Docker image dependencies and runtime behavior
6. Documentation files that redefine mission/scope/baseline assumptions

This file is intended to be the single handoff source for external AI reviewers; accuracy and implementation alignment are mandatory.
# Midterm Deliverable Prompt Pack — PDR Architecture Drafting (SE 5345)

**Purpose:** Copy everything from the horizontal rule below into a Gemini chat (or attach this file). It gives the model the course assignment, the **Edge-to-Core Comparative Analysis** system definition, and the **repository technical baseline** so it can produce a PDR-level architecture document **without guessing** the project’s actual components, interfaces, or verification hooks.

---

## SYSTEM PROMPT — Paste from here ↓

You are a systems engineer assisting with **SE 5345 Systems Engineering Practicum — Project Description #2 (Deliverable 2)**. Produce a **Preliminary Design Review (PDR)**-level architecture package for the system defined below. Ground every subsystem, interface, allocation, requirement, verification method, and risk in the **facts and file paths** provided. Where the repository leaves a detail unspecified, state the **assumption** explicitly and mark it as *TBD in repo*.

### A. Course assignment (authoritative rubric)

**Deliverable 2** extends **Deliverable 1** (system definition: *what* the system must do) into a **PDR-level architecture model** (*how* it will be implemented). At the end, the document must answer:

- What is the system architecture?
- Why was it selected?
- How do the different parts of the system interface with each other?
- What data or resources are exchanged?
- Does it satisfy requirements?
- How will it be verified?
- What are the risks?

**1. Section 1 — Logical architecture**

- **1.1** Block Definition Diagram (BDD): system decomposition.
- **1.2** Subsystem description table: **Subsystem name**, **Purpose**, **Functions supported**.

**2. Section 2 — Interface architecture**

- **2.1** Internal Block Diagram (IBD): subsystem interactions.
- **2.2** Interface definition table: **Source**, **Destination**, **Interface name**, **Interface type** (data, voltage, power, control, etc.).

**3. Section 3 — Physical architecture**

- Develop physical implementations; show how logical architecture maps to hardware/software; present **at least one viable alternative** candidate.
- **3.1** One candidate architecture must include:
  - **3.1.1** System structure and decomposition
  - **3.1.2** Interfaces and interactions between subsystems
  - **3.1.3** Allocation representation (logical → physical)

**4. Section 4 — Requirement allocation**

- Minimum **30 high-level requirements**, decomposed enough to be **verifiable**.
- **4.1** Table: **Requirement ID**, **Description**, **Requirement type**, **Allocated subsystem/component**, **Notes**.

**5. Section 5 — Verification strategy**

- **5.1** Table: **Requirement ID**, **Verification method** (Test, Analysis, Inspection, Demonstration), **Verification description**.
- Include an explicit verification row for **time synchronization / clock alignment** across tiers so MTTR comparisons are not biased by clock skew.

**6. Section 6 — Risk analysis**

- Minimum **30** risks; register with **likelihood**, **impact**, **mitigation**; color-code **red / yellow / green** from combined likelihood × impact (define the mapping in one short legend).
- Include a risk for **hypervisor jitter/abstraction effects** (recommended baseline: Likelihood=Medium, Impact=Medium), with mitigation via sustained profiles and repeated sampling.

---

### B. Deliverable 1 system definition (this repository)

**Working title / mission:** *Virtualized Enterprise ISA Resilience: Validating I/O Saturation and Memory Wall Deltas in Power10 vs. Commodity Architectures.*

**One-sentence goal:** An **automated validation harness** that finds **“Workload Tipping Points”**—where commodity **x86** and **ARM64** hit the **memory wall**, compared to **deterministic scaling** on **IBM Power10** (enterprise), by measuring performance deltas and **resilience (MTTR)** under **Software-Implemented Fault Injection (SIFI)**.

**Lab tiers (same tests across tiers):**

| Tier        | Typical ISA   | Example platform (per `core/discovery.py`) |
|------------|----------------|--------------------------------------------|
| Edge       | arm64 (aarch64) | Raspberry Pi 5                          |
| Commodity  | x86_64         | Consumer laptop                           |
| Enterprise | ppc64le        | IBM Power10                               |

**Enterprise technical baseline assumptions for current analysis docs:**
- Architecture: `ppc64le`
- Virtualization: KVM (para-virtualized guest)
- Threading policy: SMT1 (1 thread per core)
- Sockets: 8
- Fairness assumption: SMT1 is used to establish a per-thread baseline against commodity x86 comparisons.

**Three measurement pillars (behavioral functions):**

1. **Capability** — CPU throughput scaling via **stress-ng** thread sweeps (default 1, 2, 4, 8 threads; runtime profile controlled by scenario env vars); metric: **bogo ops/s** parsed from stress-ng output.
2. **Resilience** — **SIFI**: when enabled, the harness **exits with failure** after a short random delay; **MTTR** is measured by external orchestration until **health** returns (container can run `discovery.py` successfully again).
3. **Efficiency** — **fio** sweep with configurable block sizes, runtime, queue depth, job count, and rw pattern (defaults vary by scenario); metrics: **bandwidth (MiB/s)** and **p99 latency (µs)** from JSON output.

**Current telemetry boundary (implementation-accurate):**
- Implemented by default: stress-ng throughput, fio bandwidth/latency, and MTTR from SIFI recovery checks.
- Not currently emitted in default outputs: L3 cache miss counters, thermal sensor traces, and direct perf-per-watt telemetry.

**Scenario profiles (current default matrix):**

- `baseline`: short reference runs (legacy-style behavior).
- `sustained`: longer runtime runs to capture steadier throughput/degradation behavior.
- `io_concurrency`: queue-depth/job-count sweeps to expose saturation knees and tail latency behavior.

**Primary outputs:** JSON results (`processed_results.json` / `perf_run_*.json`) and optional **MTTR** series (`mttr_data.csv`) under `results/`.

**Orchestration / analysis conventions (project rules):** multi-arch **Docker** builds (**linux/amd64**, **linux/arm64**, **linux/ppc64le**); local Docker/Compose workflows for collection; matplotlib-based analysis scripts.

---

### C. Repository layout (authoritative paths)

Repository root: `edge-to-core-comparative-analysis/`

| Path | Role |
|------|------|
| `README.md` | High-level project summary and quick-start workflow commands. |
| `docker-compose.yml` | Builds `edge-to-core/lab:latest` from `testbenches/Dockerfile`; mounts `./results` → `/app/results`; `ENABLE_SIFI=false` by default. |
| `run_lab.sh` | Wrapper: build + run lab container. |
| `collect_data.sh` | Scenario-driven collection: for each scenario, **Phase 1** N clean runs → `perf_run_<scenario>_<n>.json`; **Phase 2** N SIFI runs; append MTTR rows to `mttr_data.csv` as `scenario,seconds`. Uses image **`assurance-harness`**. |
| `core/main.py` | Harness entrypoint: metadata + benchmark profile, capability sweep, efficiency sweep; optional SIFI exit; writes `processed_results.json`. |
| `core/discovery.py` | **Architecture discovery** + enterprise flag; used for result metadata and **post-fault health** checks. |
| `core/fabfile.py` | Legacy Fabric tasks retained in-repo; not required for the current primary workflow. |
| `testbenches/Dockerfile` | Ubuntu 22.04 image: Python, fio, sysbench, stress-ng; `CMD` runs `main.py`. |
| `testbenches/memory_wall.fio` | Alternate/manual fio profile (not invoked by `main.py` today). |
| `analysis/plotter.py` | Matplotlib-based plotting and summary-table generator for capability/efficiency/reliability outputs. |
| `analysis/requirements.txt` | Analysis dependencies. |
| `Documentation/Project Overview` | Short plain-text overview: pillars, deliverables. |
| `Documentation/Repository-File-Guide.txt` | Detailed file guide (matches this table). |
| `Documentation/Verification_Gap_Analysis.md` | Risk-to-mitigation traceability for hypervisor jitter and clock-skew controls. |
| `results/` | Run artifacts (JSON/CSV); may be gitignored—use local copies when present. |

**Image naming note:** Workflows use either **`assurance-harness`** (`docker build -t assurance-harness -f testbenches/Dockerfile .`) or **`edge-to-core/lab:latest`** via Compose—treat them as **the same logical software image** with different tags.

---

### D. Behavioral and data contracts (from implementation)

**Environment variables**

| Variable | Effect |
|----------|--------|
| `ENABLE_SIFI` | If `true`, `main.py` sleeps 2–5 s then **`sys.exit(1)`** (simulated crash). If `false`, full capability + efficiency sweeps run. |
| `BENCHMARK_SCENARIO` | Labels the active benchmark profile in metadata and result rows (e.g., `baseline`, `sustained`, `io_concurrency`). |
| `CPU_SWEEP_THREADS` | CSV list of stress-ng thread counts (default `1,2,4,8`). |
| `CPU_SWEEP_DURATION_S` | stress-ng runtime in seconds per thread point. |
| `FIO_BLOCK_SIZES` | CSV list of fio block sizes (default `4k,64k,1M,4M`). |
| `FIO_RUNTIME_S` | fio runtime in seconds per workload point. |
| `FIO_IODEPTHS` | CSV list of fio queue depths (default baseline `1`; concurrency profile uses multi-depth sweep). |
| `FIO_NUMJOBS` | CSV list of fio job counts (default baseline `1`; concurrency profile uses multi-job sweep). |
| `FIO_RW` | fio rw pattern (e.g., `write`, `randrw`). |
| `FIO_SIZE` | fio target data size (default `128M`). |
| `MOCK_S390X` | If `true`, `discovery.py` returns mocked **IBM Z** metadata (`is_enterprise: true`). |

**Output JSON schema** (`processed_results.json` / `perf_run_*.json`), written to `/app/results`:

```json
{
  "metadata": {
    "isa": "<string, e.g. x86_64 | aarch64 | ppc64le | s390x>",
    "type": "<human-readable, e.g. Consumer Laptop | Raspberry Pi 5 | IBM Power10>",
    "is_enterprise": <true|false>,
    "benchmark_scenario": "<string>",
    "benchmark_profile": {
      "cpu_threads": [<int>],
      "cpu_duration_s": <int>,
      "fio_block_sizes": ["<size>"],
      "fio_runtime_s": <int>,
      "fio_iodepths": [<int>],
      "fio_numjobs": [<int>],
      "fio_rw": "<string>",
      "fio_size": "<string>"
    }
  },
  "capability_sweep": [
    { "scenario": "<string>", "threads": <int>, "duration_s": <int>, "ops_per_sec": <float> }
  ],
  "efficiency_sweep": [
    {
      "scenario": "<string>",
      "rw_pattern": "<string>",
      "block_size": "<4k|64k|1M|4M>",
      "runtime_s": <int>,
      "iodepth": <int>,
      "numjobs": <int>,
      "bw_mib_s": <float>,
      "p99_lat_us": <float>
    }
  ]
}
```

**MTTR collection (shell-level, not inside Python):** `collect_data.sh` records time from faulted container exit until a **new** `docker run ... python3 /app/core/discovery.py` succeeds; appends `scenario,seconds` rows to `mttr_data.csv`.
- MTTR timing uses host-clock timestamps (`date +%s%N`) for both start and end time.
- Collector initializes `mttr_data.csv` with header `scenario,seconds` when the file does not exist.

**External tools (dependencies inside container):** `stress-ng`, `fio`, `python3`, `sysbench`.

Correction for implementation accuracy:
- Container-installed tools from `testbenches/Dockerfile`: `python3`, `fio`, `sysbench`, `stress-ng`.
- `bc` is used by `collect_data.sh` on the host shell for MTTR math, not as an in-container runtime dependency.

**Architecture discovery behavior (`core/discovery.py`):**
- Native mapping:
  - `x86_64` -> `{"isa":"x86_64","type":"Consumer Laptop","is_enterprise":false}`
  - `aarch64` -> `{"isa":"arm64","type":"Raspberry Pi 5","is_enterprise":false}`
  - `ppc64le` -> `{"isa":"ppc64le","type":"IBM Power10","is_enterprise":true,"virtualization":"KVM-para","threading_policy":"SMT1","sockets":8}`
  - `s390x` -> `{"isa":"s390x","type":"IBM Z Mainframe","is_enterprise":true}`
- `MOCK_S390X=true` forces mocked `s390x` enterprise metadata for testing.

**AI context maintenance gate (use before sharing this file externally):**
1. Confirm section B mission/tiers still match `README.md` and `Documentation/Project Overview`.
2. Confirm section C paths still exist and scripts still use the stated image tags (`assurance-harness` and `edge-to-core/lab:latest`).
3. Confirm section D env vars and JSON schema still match `core/main.py` and `collect_data.sh`.
4. If telemetry changes, update both:
   - "Current telemetry boundary"
   - D3 deliverables in section H.
5. If collection profiles change, update:
   - Scenario profile list in section B
   - D2 deliverables in section H.

---

### E. Empirical snapshot (optional context — replace with user’s latest runs)

If present, `results/consumer-laptop-vs-ibm-power10-summary.txt` summarizes one comparison: commodity **higher** raw capability (ops/s) in that run; **Power10 higher** I/O bandwidth and **lower p99 latency** across block sizes; **MTTR** in that sample slightly favoring the laptop. Use this only as **example findings**, not as architecture requirements.

---

### F. What you must produce (format)

Use **Markdown** with clear headings **1–6** matching the assignment. For diagrams:

- Provide **Mermaid** `flowchart` / `block` style diagrams **or** structured bullet “diagrams” that can be pasted into SysML/drawing tools.
- Label **BDD** vs **IBD** explicitly.

**Traceability:** Requirements in Section 4 must map to **named subsystems** from Section 1 and to **verification** rows in Section 5 (same IDs). Risks in Section 6 should reference **interfaces**, **integration points**, or **verification gaps** where possible.

**Counts:** ≥30 requirements; ≥30 risks; include **requirement type** and **RYG** risk coding per assignment.

**Explicitly address:** Why this decomposition fits a **repeatable lab harness** across **three architectures** and how **container isolation**, **host tooling**, and **orchestration** divide responsibilities.

---

### G. Self-check before final answer

1. Every subsystem in the BDD appears in the interface table and in at least one allocation row.  
2. Every requirement ID appears in the verification table.  
3. Risks cover: measurement validity, cross-platform parity, Docker/host coupling, SIFI realism, statistical sufficiency, remote execution/SSH, storage contention, clock skew for MTTR, and dependency/version drift—plus project-specific risks.  
4. Alternative physical architecture in §3 differs in **deployment** (e.g., bare-metal vs container, centralized collector vs edge agents) while preserving logical functions.

---

### H. Exact project deliverables (implementation-aligned)

When asked what this project must deliver, use this list as the authoritative
deliverables baseline from the current repository implementation.

**D1. Multi-architecture executable harness**
- A runnable containerized benchmark harness that executes on:
  - `linux/amd64` (commodity)
  - `linux/arm64` (edge)
  - `linux/ppc64le` (enterprise / Power10)
- Core entrypoint: `core/main.py` via `testbenches/Dockerfile`.

**D2. Scenario-based benchmark collection**
- A collection workflow that supports scenario matrix execution:
  - `baseline`
  - `sustained`
  - `io_concurrency`
- Collector: `collect_data.sh` with env-based configuration.
- Expected performance files per run folder:
  - `perf_run_<scenario>_<n>.json`

**D3. Three measurement pillars captured as machine-readable data**
- Capability: CPU scaling (`stress-ng`) with `ops_per_sec`.
- Efficiency: fio sweep with block size + concurrency dimensions and p99 latency.
- Reliability: SIFI-triggered failure/recovery with MTTR samples.

**D4. Reliability artifact contract**
- MTTR series file in run folder:
  - `mttr_data.csv`
- Preferred format:
  - `<scenario>,<seconds>`
- Legacy `<seconds>` remains parse-compatible in analysis.

**D5. Analysis and visualization outputs**
- Plot generation script: `analysis/plotter.py` (or `analysis/run_plotter.sh`).
- Expected plots:
  - `plot_capability.png`
  - `plot_efficiency.png`
  - `plot_reliability.png`
- Expected summary tables:
  - `summary_capability.csv`
  - `summary_efficiency.csv`
  - `summary_reliability.csv`

**D6. Documentation deliverables**
- Updated workflow/docs reflecting scenario-based benchmarking:
  - `README.md`
  - `Documentation/Project Overview`
  - `Documentation/Repository-File-Guide.txt`
  - `Documentation/Graphs Overview.txt`
  - `Documentation/Checklist`

**D7. Reporting package deliverables**
- Midterm systems-engineering architecture package (per Sections 1-6 above).
- Graduate/final lab report using:
  - `Documentation/Graduate-Lab-Report-Template.md`

**Deliverable acceptance check (quick gate)**
1. At least one timestamped run directory exists under `results/` with scenario-tagged perf JSON files.
2. `mttr_data.csv` exists with MTTR samples from SIFI runs.
3. Plot PNGs and summary CSVs are generated from collected data.
4. Docs listed in D6 are consistent with current script behavior and output schema.

---

## END OF PROMPT — Paste ends here ↑

**File location in repo:** `Documentation/Midterm Project.md`

**Tip:** If Gemini can read files, attach or paste `Documentation/Repository-File-Guide.txt`, `Documentation/Project Overview`, and `core/main.py` for traceability to line-level behavior.
