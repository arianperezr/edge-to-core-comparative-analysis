# Graduate Lab Report Template — Final Writeup Structure

## Title Page

**Project Title:** Edge-to-Core Comparative Analysis  
**Course / Program:** [Course Name, Department, University]  
**Student Name:** [Your Name]  
**Student ID:** [ID]  
**Supervisor / Advisor:** [Name]  
**Lab / Research Group:** [Lab Name]  
**Date Submitted:** [YYYY-MM-DD]  
**Version:** [v1.0]

---

## Abstract

Briefly summarize the problem, methodology, platforms, key metrics (capability, efficiency, reliability), and major findings in 150-250 words.

---

## 1. Introduction

### 1.1 Background
- Explain why edge-to-core performance comparison matters.
- Describe practical impact (deployment cost, resilience, latency, throughput).

### 1.2 Problem Statement
- What specific comparison is this project trying to answer?

### 1.3 Objectives
- Objective 1: [e.g., Compare raw throughput across architectures]
- Objective 2: [e.g., Measure I/O efficiency and tail latency]
- Objective 3: [e.g., Quantify recovery behavior using MTTR]

### 1.4 Scope and Limitations
- In-scope: [platforms, workloads, toolchain]
- Out-of-scope: [items not evaluated]

---

## 2. System and Experimental Setup

### 2.1 Hardware Platforms
Document all tested platforms:
- **Edge:** Raspberry Pi 5 (arm64) [or configured edge platform]
- **Commodity:** Consumer laptop / x86_64
- **Enterprise:** IBM Power10 (ppc64le)

For each platform, include:
- CPU model, core/thread count, memory, storage
- OS and kernel version
- Network setup

### 2.2 Software Stack
- Container runtime and orchestration details
- Local execution workflow (`run_lab.sh`, `collect_data.sh`)
- Plotting and summary workflow (`analysis/run_plotter.sh`, matplotlib)
- Benchmark and measurement tools

### 2.3 Multi-Architecture Build/Run Notes
- Docker image(s) and tags tested
- Architecture matrix: amd64, arm64, ppc64le
- Build strategy and verification steps

### 2.4 Workload Description
- Workload type(s): [CPU-bound, I/O-bound, mixed]
- Request profile / block sizes / thread counts
- Number of runs and warmup strategy

---

## 3. Methodology

### 3.1 Experimental Design
- Independent variables: architecture, thread count, block size, etc.
- Dependent variables: ops/sec, bandwidth, p99 latency, MTTR
- Controls: fixed runtime, consistent environment settings

### 3.2 Data Collection Procedure
- How each run is triggered
- Where raw outputs are stored (`results/<run-id>/...`)
- Naming convention for run folders

### 3.3 Reliability and MTTR Measurement
- Define incident/failure trigger
- Define MTTR computation and sampling method
- Note high-resolution timing strategy used in scripts

### 3.4 Statistical Treatment
- Mean, standard deviation, sample size
- Outlier handling policy
- Confidence/uncertainty notes (if applicable)

---

## 4. Results

### 4.1 Capability Results (Throughput)
Include:
- Table/figure references for `summary_capability.csv`
- Per-thread comparison across systems
- Scaling behavior commentary

### 4.2 Efficiency Results (Bandwidth and p99 Latency)
Include:
- Table/figure references for `summary_efficiency.csv`
- Block-size-wise interpretation
- Tail-latency implications

### 4.3 Reliability Results (MTTR)
Include:
- Table/figure references for `summary_reliability.csv` and MTTR samples
- Mean vs variability interpretation

### 4.4 Cross-Platform Comparative Summary
- Consumer laptop vs IBM Power10 key deltas
- Edge vs commodity vs enterprise tradeoff snapshot

### 4.5 AI Stress Sensitivity Results
Include:
- Figure/table references for `plot_ai_resilience.png` and `summary_ai.csv`
- Idle vs stressed latency comparison (average and p99)
- Efficiency loss interpretation by architecture

---

## 5. Discussion

### 5.1 Interpretation of Findings
- Why one platform performed better for specific metrics
- Link behavior to architecture characteristics

### 5.2 Practical Implications
- Recommended platform by use case:
  - Throughput-focused workloads
  - Latency-sensitive workloads
  - Recovery-critical workloads

### 5.3 Threats to Validity
- Internal validity: run-to-run noise, thermal throttling, background processes
- External validity: workload representativeness
- Construct validity: metric definitions and instrumentation limits

---

## 6. Conclusion and Future Work

### 6.1 Conclusion
- Concise answer to research objectives
- Final recommendation grounded in measured evidence

### 6.2 Future Work
- Add more workloads or real-world traces
- Expand architecture set and power measurements
- Add longer-duration resilience tests

---

## 7. Reproducibility Appendix

### 7.1 Environment Manifest
- Commit hash
- Container/image versions
- Exact command set used (`COMMANDS`)

### 7.2 Directory and Data Artifacts
- Point to:
  - Raw run directories in `results/`
  - Derived summaries
  - Plots

### 7.3 Reproduction Steps
1. Prepare environment and dependencies.
2. Run benchmark orchestration.
3. Generate summary CSVs and plots.
4. Verify expected output files.

---

## 8. References

Use a consistent style (APA/IEEE/ACM). Include:
- Benchmark tool documentation
- Architecture/vendor docs
- Related academic work

---

## Optional Tables and Figure Placeholders

### Table A. Platform Specifications
| Platform | Architecture | CPU | RAM | Storage | OS |
|---|---|---|---|---|---|
| Edge | arm64 | [ ] | [ ] | [ ] | [ ] |
| Commodity | amd64 | [ ] | [ ] | [ ] | [ ] |
| Enterprise | ppc64le | [ ] | [ ] | [ ] | [ ] |

### Table B. Capability Summary
| Platform | Threads | Mean ops/sec | Std dev |
|---|---:|---:|---:|
| [ ] | [ ] | [ ] | [ ] |

### Table C. Efficiency Summary
| Platform | Block Size | Mean BW (MiB/s) | Mean p99 Lat (us) |
|---|---|---:|---:|
| [ ] | [ ] | [ ] | [ ] |

### Table D. Reliability Summary
| Platform | MTTR Samples | MTTR Mean (s) | MTTR Std (s) |
|---|---:|---:|---:|
| [ ] | [ ] | [ ] | [ ] |

### Table E. AI Stress Sensitivity Summary
| Architecture | Workload | Idle Avg (ms) | Stressed Avg (ms) | Idle p99 (ms) | Stressed p99 (ms) | Efficiency Loss (%) |
|---|---|---:|---:|---:|---:|---:|
| [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |

---

## Author Checklist (Before Submission)

- [ ] All objectives are answered with data.
- [ ] Figures/tables are cited and discussed in text.
- [ ] Methods are detailed enough for reproduction.
- [ ] Multi-architecture context (amd64, arm64, ppc64le) is included.
- [ ] MTTR analysis includes both mean and variability.
- [ ] Conclusions match evidence and acknowledge limitations.
