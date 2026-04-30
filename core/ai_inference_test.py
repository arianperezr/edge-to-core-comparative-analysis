#!/usr/bin/env python3
import csv
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(np.array(values, dtype=np.float64), pct))


def _mean_jitter_ms(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    arr = np.array(values, dtype=np.float64)
    diffs = np.abs(np.diff(arr))
    return float(np.mean(diffs))


def _run_inference_loop(model: RandomForestClassifier, samples: np.ndarray, iterations: int) -> list[float]:
    latencies_ms: list[float] = []
    sample_count = samples.shape[0]
    for i in range(iterations):
        sample = samples[i % sample_count].reshape(1, -1)
        start = time.perf_counter()
        model.predict(sample)
        end = time.perf_counter()
        latencies_ms.append((end - start) * 1000.0)
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
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def _metrics(latencies_ms: list[float]) -> dict[str, float]:
    return {
        "avg_ms": float(np.mean(np.array(latencies_ms, dtype=np.float64))),
        "p99_ms": _percentile(latencies_ms, 99.0),
        "mean_jitter_ms": _mean_jitter_ms(latencies_ms),
    }


def run_ai_validation() -> None:
    iterations = int(os.getenv("AI_INFER_ITERATIONS", "1000"))
    results_csv = Path(os.getenv("AI_RESULTS_CSV", "results/ai_resilience_final.csv"))

    x, y = make_classification(
        n_samples=4000,
        n_features=24,
        n_informative=16,
        n_redundant=4,
        n_classes=2,
        random_state=42,
    )

    model = RandomForestClassifier(n_estimators=40, random_state=42)
    model.fit(x[:3000], y[:3000])
    infer_samples = x[3000:]

    idle_latencies = _run_inference_loop(model, infer_samples, iterations)
    idle_stats = _metrics(idle_latencies)

    stress_proc = _start_io_stressor()
    try:
        stressed_latencies = _run_inference_loop(model, infer_samples, iterations)
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
            }
        )

    print("AI inference validation complete.")
    print(f"Architecture: {platform.machine()}")
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
