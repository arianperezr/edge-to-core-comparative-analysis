#!/usr/bin/env python3
import csv
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np


def _read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"Warning: invalid {name}={raw!r}; using default {default}")
        return default


def _dense_forward(batch: np.ndarray, w1: np.ndarray, b1: np.ndarray, w2: np.ndarray, b2: np.ndarray) -> np.ndarray:
    x = batch @ w1 + b1
    np.maximum(x, 0, out=x)  # ReLU
    return x @ w2 + b2


def _run_inference_loop(
    samples: np.ndarray,
    w1: np.ndarray,
    b1: np.ndarray,
    w2: np.ndarray,
    b2: np.ndarray,
    iterations: int,
    batch_size: int,
) -> list[float]:
    latencies_ms: list[float] = []
    sample_count = samples.shape[0]
    for i in range(iterations):
        start_idx = (i * batch_size) % sample_count
        end_idx = start_idx + batch_size
        if end_idx <= sample_count:
            batch = samples[start_idx:end_idx]
        else:
            overflow = end_idx - sample_count
            batch = np.vstack((samples[start_idx:], samples[:overflow]))
        start = time.perf_counter()
        _dense_forward(batch, w1, b1, w2, b2)
        end = time.perf_counter()
        # Convert to per-sample latency so runs are comparable across batch sizes.
        latencies_ms.append((end - start) * 1000.0 / batch_size)
    return latencies_ms


def _start_io_stressor() -> subprocess.Popen | None:
    if shutil.which("fio"):
        stress_cmd = [
            "fio",
            "--name=ai_stress",
            "--rw=randrw",
            "--bs=4M",
            "--size=512M",
            "--ioengine=libaio",
            "--direct=1",
            "--iodepth=8",
            "--numjobs=2",
            "--runtime=180",
            "--time_based",
            "--group_reporting=1",
        ]
        return subprocess.Popen(stress_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if shutil.which("stress-ng"):
        stress_cmd = ["stress-ng", "--hdd", "2", "--hdd-bytes", "512M", "--timeout", "180s"]
        return subprocess.Popen(stress_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    raise RuntimeError("Neither fio nor stress-ng is available for stressed AI inference phase.")


def _stop_stressor(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return

    total_timeout_s = _read_float_env("STRESSOR_STOP_TIMEOUT", 20.0)
    if total_timeout_s <= 0:
        total_timeout_s = 1.0

    # Split timeout budget so force-kill always has some headroom.
    force_kill_share = _read_float_env("STRESSOR_FORCE_KILL_SHARE", 0.25)
    if force_kill_share < 0.05:
        force_kill_share = 0.05
    if force_kill_share > 0.90:
        force_kill_share = 0.90

    force_kill_timeout_s = max(0.1, total_timeout_s * force_kill_share)
    graceful_timeout_s = max(0.1, total_timeout_s - force_kill_timeout_s)

    proc.terminate()
    try:
        proc.wait(timeout=graceful_timeout_s)
        return
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=force_kill_timeout_s)
        except subprocess.TimeoutExpired:
            print(
                "Warning: stressor did not exit after SIGTERM/SIGKILL "
                f"(graceful_timeout_s={graceful_timeout_s:.2f}, "
                f"force_kill_timeout_s={force_kill_timeout_s:.2f}). Continuing."
            )


def _metrics(latencies_ms: list[float]) -> dict[str, float]:
    arr = np.array(latencies_ms, dtype=np.float64)
    if arr.size == 0:
        return {"avg_ms": 0.0, "p99_ms": 0.0, "mean_jitter_ms": 0.0}
    return {
        "avg_ms": float(np.mean(arr)),
        "p99_ms": float(np.percentile(arr, 99.0)),
        "mean_jitter_ms": float(np.mean(np.abs(np.diff(arr)))) if arr.size > 1 else 0.0,
    }


def run_ai_validation() -> None:
    iterations = int(os.getenv("AI_INFER_ITERATIONS", "1000"))
    batch_size = int(os.getenv("AI_BATCH_SIZE", "64"))
    input_dim = int(os.getenv("AI_INPUT_DIM", "1024"))
    hidden_dim = int(os.getenv("AI_HIDDEN_DIM", "2048"))
    output_dim = int(os.getenv("AI_OUTPUT_DIM", "512"))
    sample_count = int(os.getenv("AI_SAMPLE_COUNT", "4096"))
    results_csv = Path(os.getenv("AI_RESULTS_CSV", "results/ai_resilience_final.csv"))

    rng = np.random.default_rng(42)
    infer_samples = rng.standard_normal((sample_count, input_dim), dtype=np.float32)
    w1 = rng.standard_normal((input_dim, hidden_dim), dtype=np.float32) * np.float32(0.02)
    b1 = rng.standard_normal((hidden_dim,), dtype=np.float32) * np.float32(0.02)
    w2 = rng.standard_normal((hidden_dim, output_dim), dtype=np.float32) * np.float32(0.02)
    b2 = rng.standard_normal((output_dim,), dtype=np.float32) * np.float32(0.02)

    idle_latencies = _run_inference_loop(infer_samples, w1, b1, w2, b2, iterations, batch_size)
    idle_stats = _metrics(idle_latencies)

    stress_proc = _start_io_stressor()
    try:
        stressed_latencies = _run_inference_loop(infer_samples, w1, b1, w2, b2, iterations, batch_size)
    finally:
        _stop_stressor(stress_proc)
    stressed_stats = _metrics(stressed_latencies)

    idle_avg = idle_stats["avg_ms"]
    stressed_avg = stressed_stats["avg_ms"]
    efficiency_loss_pct = ((stressed_avg - idle_avg) / idle_avg * 100.0) if idle_avg else 0.0
    jitter_delta_ms = stressed_stats["mean_jitter_ms"] - idle_stats["mean_jitter_ms"]

    results_csv.parent.mkdir(parents=True, exist_ok=True)
    file_exists = results_csv.exists()
    with results_csv.open("a", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Architecture",
                "Test_Type",
                "Average_Latency",
                "p99_Latency",
                "Jitter_Delta",
                "Efficiency_Loss_Pct",
                "Workload",
            ],
        )
        if not file_exists:
            writer.writeheader()
        arch = platform.machine()
        writer.writerow(
            {
                "Architecture": arch,
                "Test_Type": "Idle",
                "Average_Latency": f"{idle_stats['avg_ms']:.6f}",
                "p99_Latency": f"{idle_stats['p99_ms']:.6f}",
                "Jitter_Delta": "0.000000",
                "Efficiency_Loss_Pct": "0.000000",
                "Workload": "dense_mlp",
            }
        )
        writer.writerow(
            {
                "Architecture": arch,
                "Test_Type": "Stressed",
                "Average_Latency": f"{stressed_stats['avg_ms']:.6f}",
                "p99_Latency": f"{stressed_stats['p99_ms']:.6f}",
                "Jitter_Delta": f"{jitter_delta_ms:.6f}",
                "Efficiency_Loss_Pct": f"{efficiency_loss_pct:.6f}",
                "Workload": "dense_mlp",
            }
        )

    print("AI inference validation complete.")
    print(f"Architecture: {platform.machine()}")
    print(f"Workload: dense_mlp (batch_size={batch_size}, dims={input_dim}->{hidden_dim}->{output_dim})")
    print(f"Idle avg/p99 latency (ms): {idle_stats['avg_ms']:.6f}/{idle_stats['p99_ms']:.6f}")
    print(
        "Stressed avg/p99 latency (ms): "
        f"{stressed_stats['avg_ms']:.6f}/{stressed_stats['p99_ms']:.6f}"
    )
    print(f"Mean jitter delta (ms): {jitter_delta_ms:.6f}")
    print(f"Efficiency loss (%): {efficiency_loss_pct:.6f}")
    print(f"Appended CSV row set: {results_csv}")


if __name__ == "__main__":
    run_ai_validation()