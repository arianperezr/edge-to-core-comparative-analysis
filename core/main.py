import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

from discovery import get_arch_details


def _parse_csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [token.strip() for token in raw.split(",") if token.strip()]


def _parse_int_csv_env(name: str, default: str) -> list[int]:
    values = []
    for token in _parse_csv_env(name, default):
        try:
            values.append(int(token))
        except ValueError:
            continue
    return values


def _fio_p99_us(io_stats: dict) -> float:
    clat = io_stats.get("clat_ns", {})
    percentiles = clat.get("percentile", {})
    p99 = percentiles.get("99.000000")
    if p99 is None:
        p99 = percentiles.get("99.00", 0)
    return float(p99) / 1000


def _run_capability_sweep(final_results: dict, cpu_counts: list[int], timeout_s: int, scenario_name: str) -> None:
    for count in cpu_counts:
        print(f"Running CPU Stress: {count} threads for {timeout_s}s...", flush=True)
        result = subprocess.run(
            [
                "stress-ng",
                "--cpu",
                str(count),
                "--timeout",
                f"{timeout_s}s",
                "--metrics-brief",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "stress-ng failed "
                f"(threads={count}, timeout_s={timeout_s}): {(result.stderr or '').strip()}"
            )
        out = (result.stdout or "") + (result.stderr or "")
        lines = out.strip().splitlines()
        ops = 0.0
        for line in reversed(lines):
            m = re.search(r"\bcpu\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+([\d.]+)\s+[\d.]+", line)
            if m:
                ops = float(m.group(1))
                break
        final_results["capability_sweep"].append(
            {
                "scenario": scenario_name,
                "threads": count,
                "duration_s": timeout_s,
                "ops_per_sec": ops,
            }
        )


def _run_efficiency_sweep(
    final_results: dict,
    block_sizes: list[str],
    runtime_s: int,
    io_depths: list[int],
    num_jobs: list[int],
    rw_pattern: str,
    fio_size: str,
    scenario_name: str,
) -> None:
    for bs in block_sizes:
        for iodepth in io_depths:
            for jobs in num_jobs:
                print(
                    (
                        "Running fio: "
                        f"bs={bs}, rw={rw_pattern}, iodepth={iodepth}, "
                        f"numjobs={jobs}, runtime={runtime_s}s..."
                    ),
                    flush=True,
                )
                subprocess.run(
                    [
                        "fio",
                        "--name=bench",
                        f"--rw={rw_pattern}",
                        f"--bs={bs}",
                        f"--size={fio_size}",
                        "--ioengine=libaio",
                        "--direct=1",
                        f"--iodepth={iodepth}",
                        f"--numjobs={jobs}",
                        f"--runtime={runtime_s}",
                        "--time_based",
                        "--group_reporting=1",
                        "--output-format=json",
                        "--output=/tmp/fio.json",
                    ],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        "fio failed "
                        f"(bs={bs}, iodepth={iodepth}, numjobs={jobs}, rw={rw_pattern}): "
                        f"{(result.stderr or '').strip()}"
                    )
                fio_out = Path("/tmp/fio.json")
                if not fio_out.exists():
                    raise RuntimeError("fio did not produce expected output file /tmp/fio.json")
                with fio_out.open("r") as f:
                    data = json.load(f)
                jobs_data = data.get("jobs", [])
                if not jobs_data or "write" not in jobs_data[0]:
                    raise RuntimeError("fio output missing expected jobs[0].write section")
                write_data = jobs_data[0]["write"]
                final_results["efficiency_sweep"].append(
                    {
                        "scenario": scenario_name,
                        "rw_pattern": rw_pattern,
                        "block_size": bs,
                        "runtime_s": runtime_s,
                        "iodepth": iodepth,
                        "numjobs": jobs,
                        "bw_mib_s": write_data["bw_bytes"] / (1024 * 1024),
                        "p99_lat_us": _fio_p99_us(write_data),
                    }
                )


def run_validation():
    arch = get_arch_details()
    scenario_name = os.getenv("BENCHMARK_SCENARIO", "baseline")
    cpu_counts = _parse_int_csv_env("CPU_SWEEP_THREADS", "1,2,4,8")
    cpu_timeout_s = int(os.getenv("CPU_SWEEP_DURATION_S", "5"))
    block_sizes = _parse_csv_env("FIO_BLOCK_SIZES", "4k,64k,1M,4M")
    fio_runtime_s = int(os.getenv("FIO_RUNTIME_S", "5"))
    io_depths = _parse_int_csv_env("FIO_IODEPTHS", "1")
    num_jobs = _parse_int_csv_env("FIO_NUMJOBS", "1")
    rw_pattern = os.getenv("FIO_RW", "write")
    fio_size = os.getenv("FIO_SIZE", "128M")
    final_results = {
        "metadata": {
            **arch,
            "benchmark_scenario": scenario_name,
            "benchmark_profile": {
                "cpu_threads": cpu_counts,
                "cpu_duration_s": cpu_timeout_s,
                "fio_block_sizes": block_sizes,
                "fio_runtime_s": fio_runtime_s,
                "fio_iodepths": io_depths,
                "fio_numjobs": num_jobs,
                "fio_rw": rw_pattern,
                "fio_size": fio_size,
            },
        },
        "capability_sweep": [],
        "efficiency_sweep": [],
    }

    print(f"\nTestbench Active: {arch['isa']} ({arch['type']})", flush=True)
    print(f"Scenario: {scenario_name}", flush=True)
    print("-" * 30, flush=True)

    sifi_enabled = os.getenv("ENABLE_SIFI", "false").lower() == "true"
    if sifi_enabled:
        fail_time = random.uniform(2, 5)
        print(f"!!! SIFI ENABLED: System fault in {fail_time:.2f}s !!!")
        time.sleep(fail_time)
        print("CRITICAL FAILURE: Simulated process crash.")
        sys.exit(1)

    _run_capability_sweep(final_results, cpu_counts, cpu_timeout_s, scenario_name)
    _run_efficiency_sweep(
        final_results,
        block_sizes,
        fio_runtime_s,
        io_depths,
        num_jobs,
        rw_pattern,
        fio_size,
        scenario_name,
    )

    output_dir = "/app/results"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    output_path = os.path.join(output_dir, "processed_results.json")
    with open(output_path, "w") as f:
        json.dump(final_results, f, indent=4)

    print("\nVALIDATION COMPLETE.", flush=True)

if __name__ == "__main__":
    run_validation()