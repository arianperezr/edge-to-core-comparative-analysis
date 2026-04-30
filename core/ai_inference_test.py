#!/usr/bin/env python3
import csv
import os
import platform
import shutil
import signal
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
        proc = subprocess.Popen(
            stress_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"Started I/O stressor (fio), pid={proc.pid}")
        return proc

    if shutil.which("stress-ng"):
        stress_cmd = ["stress-ng", "--hdd", "2", "--hdd-bytes", "512M", "--timeout", "180s"]
        proc = subprocess.Popen(
            stress_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"Started I/O stressor (stress-ng), pid={proc.pid}")
        return proc

    raise RuntimeError("Neither fio nor stress-ng is available for stressed AI inference phase.")


def _stop_stressor(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        print(f"Stressor already exited with return code {proc.returncode}, pid={proc.pid}")
        return

    raw_timeout = os.getenv("STRESSOR_STOP_TIMEOUT", "20")
    try:
        stop_timeout_s = float(raw_timeout)
    except ValueError:
        print(
            f"Warning: invalid STRESSOR_STOP_TIMEOUT={raw_timeout!r}; "
            "falling back to 20.0s"
        )
        stop_timeout_s = 20.0
    if stop_timeout_s < 0:
        print(
            f"Warning: negative STRESSOR_STOP_TIMEOUT={stop_timeout_s}; "
            "using minimum timeout 0.1s"
        )
        stop_timeout_s = 0.1
    elif stop_timeout_s == 0:
        print("Warning: STRESSOR_STOP_TIMEOUT=0; using minimum timeout 0.1s")
        stop_timeout_s = 0.1
    phase_start = time.perf_counter()
    used_process_group = False

    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
        used_process_group = True
        print(f"Stopping stressor pid={proc.pid} via process group SIGTERM (pgid={pgid})")
    except ProcessLookupError:
        # Process may have exited between getpgid()/killpg() and signal delivery.
        print(f"Stressor process group already gone for pid={proc.pid}; assuming exit race during SIGTERM")
        return
    except PermissionError as exc:
        # Permission issues can happen in constrained runtimes; fallback to process signal path.
        if proc.poll() is None:
            print(
                f"Warning: process group SIGTERM denied ({exc}); "
                f"falling back to process SIGTERM for pid={proc.pid}"
            )
            proc.terminate()
        else:
            print(f"Stressor exited before fallback terminate, pid={proc.pid}, rc={proc.returncode}")
            return

    try:
        proc.wait(timeout=stop_timeout_s)
        elapsed = time.perf_counter() - phase_start
        print(f"Stressor exited gracefully in {elapsed:.2f}s, pid={proc.pid}, rc={proc.returncode}")
        return
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - phase_start
        print(
            "Warning: stressor did not stop after "
            f"{elapsed:.2f}s (timeout={stop_timeout_s:.1f}s), escalating to force kill; pid={proc.pid}"
        )

    elapsed_before_kill = time.perf_counter() - phase_start
    remaining_timeout_s = max(0.1, stop_timeout_s - elapsed_before_kill)
    kill_start = time.perf_counter()
    try:
        if used_process_group:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGKILL)
            print(f"Escalation used: process group SIGKILL for pid={proc.pid} (pgid={pgid})")
        else:
            proc.kill()
            print(f"Escalation used: process SIGKILL for pid={proc.pid}")
    except ProcessLookupError:
        print(f"Stressor already exited before force-kill, pid={proc.pid}")
        return

    try:
        proc.wait(timeout=remaining_timeout_s)
        elapsed = time.perf_counter() - kill_start
        print(f"Stressor force-killed and reaped in {elapsed:.2f}s, pid={proc.pid}, rc={proc.returncode}")
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - kill_start
        print(
            "Warning: stressor could not be reaped after SIGKILL "
            f"within {elapsed:.2f}s (remaining budget={remaining_timeout_s:.2f}s), "
            f"pid={proc.pid}. Continuing (best effort cleanup)."
        )


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
        try:
            _stop_stressor(stress_proc)
        except Exception as exc:
            print(f"Warning: stressor cleanup failed but validation will continue: {exc}")
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
