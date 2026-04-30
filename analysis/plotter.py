"""
Convert harness JSON results into Tipping Point graphs.
Reads processed_results.json or perf_run_*.json from results/ (or a given path).
Uses only stdlib + matplotlib (no polars).
"""
import json
import os
import glob
import csv
import math
from pathlib import Path
from collections import defaultdict

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update(
    {
        "figure.dpi": 120,
        "savefig.dpi": 160,
        "axes.titlesize": 14,
        "axes.labelsize": 12,
        "legend.fontsize": 10,
    }
)

def _safe_pct_delta(value: float, ref: float) -> float | None:
    if ref == 0:
        return None
    return ((value - ref) / ref) * 100.0


def _safe_pct_improvement_lower_is_better(value: float, ref: float) -> float | None:
    if ref == 0:
        return None
    return ((ref - value) / ref) * 100.0


def _safe_ratio(value: float, ref: float) -> float | None:
    if ref == 0:
        return None
    return value / ref


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    n = len(vals)
    mid = n // 2
    if n % 2 == 1:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def _ai_arch_display(arch: str) -> str:
    arch_key = (arch or "").strip().lower()
    labels = {
        "aarch64": "Raspberry Pi 5 (aarch64)",
        "arm64": "Raspberry Pi 5 (arm64)",
        "raspberry pi 5": "Raspberry Pi 5 (aarch64)",
        "x86_64": "Consumer Laptop (x86_64)",
        "amd64": "Consumer Laptop (amd64)",
        "consumer laptop": "Consumer Laptop (x86_64)",
        "ppc64le": "IBM Power 10 (ppc64le)",
        "powerpc64le": "IBM Power 10 (powerpc64le)",
        "ibm power10": "IBM Power 10 (ppc64le)",
        "ibm power 10": "IBM Power 10 (ppc64le)",
    }
    return labels.get(arch_key, arch)


def _ms_tick_formatter(value: float, _pos: float) -> str:
    if value >= 1.0:
        return f"{value:.2f}"
    return f"{value:.3f}"


def _arch_sort_key(label: str) -> int:
    l = (label or "").lower()
    if "power" in l:
        return 0
    if "laptop" in l:
        return 1
    if "raspberry" in l or "pi" in l:
        return 2
    return 99


def _arch_color(label: str) -> str:
    l = (label or "").lower()
    if "power" in l:
        return "#4C78A8"
    if "laptop" in l:
        return "#F58518"
    if "raspberry" in l or "pi" in l:
        return "#54A24B"
    return "#9C755F"


def _block_size_sort_key(bs: str) -> tuple[int, int]:
    s = (bs or "").strip().lower()
    if not s:
        return (0, 0)
    unit = s[-1]
    num_str = s[:-1]
    try:
        n = int(num_str)
    except ValueError:
        return (0, 0)
    if unit == "k":
        return (n, 0)
    if unit == "m":
        return (n * 1024, 0)
    if unit == "g":
        return (n * 1024 * 1024, 0)
    return (0, 0)


def load_result_json(path: str) -> dict:
    """Load a single harness result JSON."""
    with open(path, "r") as f:
        return json.load(f)


def find_result_jsons(path: str) -> list[str]:
    """
    Resolve path to a list of JSON paths.
    - If path is a file: return [path] if it's .json
    - If path is a dir: return [processed_results.json] or sorted perf_run_*.json
    """
    p = Path(path)
    if p.is_file():
        return [str(p)] if p.suffix.lower() == ".json" else []
    if not p.is_dir():
        return []
    single = p / "processed_results.json"
    if single.exists():
        return [str(single)]
    return sorted(glob.glob(str(p / "perf_run_*.json")))


def _mean_std(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    return mean, variance ** 0.5


def results_to_tables(jsons: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """
    Convert list of result dicts into capability and efficiency tables (list of dicts).
    Multiple runs are aggregated (mean ± std). Returns (cap_data, eff_data, metadata).
    """
    cap_rows = []
    eff_rows = []
    meta = jsons[0].get("metadata", {}) if jsons else {}

    for j in jsons:
        for row in j.get("capability_sweep", []):
            cap_rows.append(row)
        for row in j.get("efficiency_sweep", []):
            eff_rows.append(row)

    cap_data = []
    if cap_rows:
        by_threads = defaultdict(list)
        for r in cap_rows:
            scenario = r.get("scenario", meta.get("benchmark_scenario", "baseline"))
            key = (scenario, r["threads"], r.get("duration_s", 5))
            by_threads[key].append(r["ops_per_sec"])
        for (scenario, threads, duration_s) in sorted(by_threads, key=lambda x: (x[0], x[1])):
            vals = by_threads[(scenario, threads, duration_s)]
            m, s = _mean_std(vals)
            row = {"scenario": scenario, "threads": threads, "duration_s": duration_s, "ops_per_sec": m}
            if len(jsons) > 1:
                row["ops_per_sec_mean"], row["ops_per_sec_std"] = m, s
            else:
                row["ops_per_sec_mean"], row["ops_per_sec_std"] = m, 0.0
            cap_data.append(row)

    eff_data = []
    if eff_rows:
        by_bs = defaultdict(lambda: {"bw": [], "lat": []})
        for r in eff_rows:
            scenario = r.get("scenario", meta.get("benchmark_scenario", "baseline"))
            key = (
                scenario,
                r["block_size"],
                r.get("iodepth", 1),
                r.get("numjobs", 1),
                r.get("rw_pattern", "write"),
                r.get("runtime_s", 5),
            )
            by_bs[key]["bw"].append(r["bw_mib_s"])
            by_bs[key]["lat"].append(r["p99_lat_us"])
        for (scenario, block_size, iodepth, numjobs, rw_pattern, runtime_s) in sorted(
            by_bs.keys(),
            key=lambda x: (x[0], x[1], x[2], x[3], x[4], x[5]),
        ):
            bw_vals = by_bs[(scenario, block_size, iodepth, numjobs, rw_pattern, runtime_s)]["bw"]
            lat_vals = by_bs[(scenario, block_size, iodepth, numjobs, rw_pattern, runtime_s)]["lat"]
            bw_m, bw_s = _mean_std(bw_vals)
            lat_m, lat_s = _mean_std(lat_vals)
            row = {
                "scenario": scenario,
                "block_size": block_size,
                "iodepth": iodepth,
                "numjobs": numjobs,
                "rw_pattern": rw_pattern,
                "runtime_s": runtime_s,
                "bw_mib_s": bw_m,
                "p99_lat_us": lat_m,
                "bw_mib_s_mean": bw_m,
                "bw_mib_s_std": bw_s,
                "p99_lat_us_mean": lat_m,
                "p99_lat_us_std": lat_s,
            }
            eff_data.append(row)

    return cap_data, eff_data, meta


def _arch_label(metadata: dict) -> str:
    """Human-readable label for an architecture (prefer type, fallback to isa)."""
    isa = str(metadata.get("isa", "")).lower()
    isa_labels = {
        "x86_64": "Consumer Laptop",
        "amd64": "Consumer Laptop",
        "arm64": "Raspberry Pi 5",
        "aarch64": "Raspberry Pi 5",
        "ppc64le": "IBM Power10",
        "powerpc64le": "IBM Power10",
        "s390x": "IBM Z Mainframe",
    }
    t = metadata.get("type")
    if t and t != "Unknown":
        return t
    if isa in isa_labels:
        return isa_labels[isa]
    return metadata.get("isa") or "Unknown"


def _reference_dataset_index_from_meta(meta_list: list[dict], preferred: str | None = None) -> int:
    """
    Prefer commodity/laptop reference so percentage labels highlight enterprise uplift.
    Fallback: first dataset.
    """
    if preferred:
        preferred_key = preferred.strip().lower()
        for idx, meta in enumerate(meta_list):
            label = _arch_label(meta).lower()
            isa = str(meta.get("isa", "")).lower()
            if preferred_key in label or preferred_key == isa:
                return idx
            if preferred_key in {"ibm power", "power10", "ppc64le"} and (
                "power" in label or isa in {"ppc64le", "powerpc64le"}
            ):
                return idx

    for idx, meta in enumerate(meta_list):
        label = _arch_label(meta).lower()
        isa = str(meta.get("isa", "")).lower()
        if "laptop" in label or "commodity" in label or isa in {"x86_64", "amd64"}:
            return idx
    return 0


def plot_capability(
    datasets: list[tuple[list[dict], dict]],
    out_path: str | None = None,
) -> None:
    """Plot capability sweep (baseline-only) with percentage gain labels vs reference."""
    if not datasets:
        return
    # Compare apples-to-apples across architectures using the baseline scenario.
    baseline_only: list[tuple[list[dict], dict]] = []
    for cap_data, meta in datasets:
        rows = [r for r in cap_data if r.get("scenario", "baseline") == "baseline"]
        if rows:
            baseline_only.append((rows, meta))
    if baseline_only:
        datasets = baseline_only

    fig, ax = plt.subplots(figsize=(9, 5))
    ref_idx = _reference_dataset_index_from_meta([meta for _, meta in datasets])
    ref_label = _arch_label(datasets[ref_idx][1])
    ref_values: dict[tuple[str, int], float] = {}
    if datasets and datasets[ref_idx][0]:
        for row in datasets[ref_idx][0]:
            ref_values[(row.get("scenario", "baseline"), row["threads"])] = row["ops_per_sec_mean"]

    for cap_data, meta in datasets:
        if not cap_data:
            continue
        by_scenario = defaultdict(list)
        for row in cap_data:
            by_scenario[row.get("scenario", "baseline")].append(row)
        for scenario, rows in sorted(by_scenario.items()):
            label = f"{_arch_label(meta)} [{scenario}]"
            rows = sorted(rows, key=lambda r: r["threads"])
            x = [r["threads"] for r in rows]
            y = [r["ops_per_sec_mean"] for r in rows]
            ax.plot(x, y, marker="o", label=label)

            # Label the laptop points directly so the trend is easy to read.
            if _arch_label(meta) == "Consumer Laptop":
                for r in rows:
                    ax.annotate(
                        f"{r['ops_per_sec_mean']:.0f}",
                        (r["threads"], r["ops_per_sec_mean"]),
                        textcoords="offset points",
                        xytext=(0, 10),
                        ha="center",
                        fontsize=8,
                    )

            is_reference_arch = _arch_label(meta) == ref_label
            if is_reference_arch:
                continue

            for r in rows:
                ref = ref_values.get((scenario, r["threads"]))
                if ref is None:
                    continue
                delta = _safe_pct_delta(r["ops_per_sec_mean"], ref)
                if delta is None:
                    continue
                sign = "+" if delta >= 0 else ""
                ax.annotate(
                    f"{sign}{delta:.1f}%",
                    (r["threads"], r["ops_per_sec_mean"]),
                    textcoords="offset points",
                    xytext=(0, 8),
                    ha="center",
                    fontsize=8,
                )
    ax.set_xlabel("Threads")
    ax.set_ylabel("Bogo ops/s")
    ax.set_title(f"Capability sweep (stress-ng CPU) — % vs {ref_label}")
    ax.legend(loc="best", frameon=True)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
    else:
        plt.show()


def plot_efficiency(
    datasets: list[tuple[list[dict], dict]],
    out_path: str | None = None,
) -> None:
    """Plot efficiency sweep with absolute and tipping-point views."""
    if not datasets:
        return
    # Start with the baseline fio shape so this view stays readable.
    filtered = []
    for eff_data, meta in datasets:
        rows = [
            r
            for r in eff_data
            if r.get("iodepth", 1) == 1 and r.get("numjobs", 1) == 1 and r.get("scenario", "baseline") == "baseline"
        ]
        if rows:
            filtered.append((rows, meta))
    if not filtered:
        filtered = datasets

    # Gather all block sizes across architectures and sort them numerically.
    all_bs = []
    seen_bs = set()
    for eff_data, _ in filtered:
        for r in eff_data:
            bs = r["block_size"]
            if bs not in seen_bs:
                seen_bs.add(bs)
                all_bs.append(bs)
    if not all_bs:
        return
    all_bs = sorted(all_bs, key=_block_size_sort_key)

    n_bs = len(all_bs)
    n_arch = len(filtered)
    bar_width = 0.8 / max(n_arch, 1)
    # Center each architecture's bar within its block-size group.
    offsets = [(i - (n_arch - 1) / 2) * bar_width for i in range(n_arch)]

    fig, (ax_bw, ax_lat, ax_tip) = plt.subplots(3, 1, figsize=(max(8, n_bs * 1.8), 11))
    ref_idx = _reference_dataset_index_from_meta([meta for _, meta in filtered], preferred="ppc64le")
    ref_label = _arch_label(filtered[ref_idx][1])
    ref_by_bs = {}
    if filtered and filtered[ref_idx][0]:
        ref_by_bs = {r["block_size"]: r for r in filtered[ref_idx][0]}

    def by_block_size(eff_data: list[dict]) -> dict[str, dict]:
        return {r["block_size"]: r for r in eff_data}

    for idx, (eff_data, meta) in enumerate(filtered):
        if not eff_data:
            continue
        label = _arch_label(meta)
        by_bs = by_block_size(eff_data)
        y_bw = [by_bs.get(bs, {}).get("bw_mib_s_mean", 0) for bs in all_bs]
        y_lat = [by_bs.get(bs, {}).get("p99_lat_us_mean", 0) for bs in all_bs]
        x = [i + offsets[idx] for i in range(n_bs)]
        bars_bw = ax_bw.bar(x, y_bw, width=bar_width * 0.9, label=label)
        bars_lat = ax_lat.bar(x, y_lat, width=bar_width * 0.9, label=label)

        if label != ref_label:
            for i, bs in enumerate(all_bs):
                ref_row = ref_by_bs.get(bs)
                if not ref_row:
                    continue

                pct_bw = _safe_pct_delta(y_bw[i], ref_row.get("bw_mib_s_mean", 0))
                pct_lat = _safe_pct_improvement_lower_is_better(
                    y_lat[i],
                    ref_row.get("p99_lat_us_mean", 0),
                )
                # Save the full comparison story for the third panel to avoid clutter here.
                if pct_bw is None or pct_lat is None:
                    continue
                ax_bw.annotate(
                    f"{pct_bw:+.0f}%",
                    (bars_bw[i].get_x() + bars_bw[i].get_width() / 2, y_bw[i]),
                    textcoords="offset points",
                    xytext=(0, 4),
                    ha="center",
                    fontsize=8,
                )
                ax_lat.annotate(
                    f"{pct_lat:+.0f}%",
                    (bars_lat[i].get_x() + bars_lat[i].get_width() / 2, y_lat[i]),
                    textcoords="offset points",
                    xytext=(0, 4),
                    ha="center",
                    fontsize=8,
                )
        else:
            # Show IBM Power absolute values so the baseline is obvious at a glance.
            for i in range(len(all_bs)):
                ax_bw.annotate(
                    f"{y_bw[i]:.1f}",
                    (bars_bw[i].get_x() + bars_bw[i].get_width() / 2, y_bw[i]),
                    textcoords="offset points",
                    xytext=(0, 4),
                    ha="center",
                    fontsize=8,
                )
                ax_lat.annotate(
                    f"{y_lat[i]:.1f}",
                    (bars_lat[i].get_x() + bars_lat[i].get_width() / 2, y_lat[i]),
                    textcoords="offset points",
                    xytext=(0, 4),
                    ha="center",
                    fontsize=8,
                )

    ax_bw.set_ylabel("Bandwidth (MiB/s)")
    ax_bw.set_title(f"Efficiency sweep (fio write)\nBandwidth (absolute, log scale, % vs {ref_label})")
    ax_bw.set_xticks(range(n_bs))
    ax_bw.set_xticklabels(all_bs)
    ax_bw.set_yscale("log")
    ax_bw.legend()
    ax_bw.grid(True, alpha=0.3)

    ax_lat.set_xticks(range(n_bs))
    ax_lat.set_xticklabels(all_bs)
    ax_lat.set_ylabel("p99 latency (µs)")
    ax_lat.set_title(f"Efficiency sweep\np99 latency (absolute, log scale, % improvement vs {ref_label})")
    ax_lat.set_yscale("log")
    ax_lat.legend()
    ax_lat.grid(True, alpha=0.3)

    # Third panel: compact tipping-point view relative to IBM Power10.
    tip_summary = []  # (arch_label, worst_p99_ratio_x_vs_ibm, worst_p99_ms)
    ibm_worst_us = None
    by_arch_worst: dict[str, float] = {}
    for eff_data, meta in sorted(filtered, key=lambda t: _arch_sort_key(_arch_label(t[1]))):
        label = _arch_label(meta)
        by_bs = by_block_size(eff_data)
        vals = []
        for bs in all_bs:
            row = by_bs.get(bs)
            if not row:
                continue
            lat_us = row.get("p99_lat_us_mean", 0)
            vals.append(lat_us)
        if not vals:
            continue
        worst_us = max(vals)
        by_arch_worst[label] = worst_us
        if "power" in label.lower():
            ibm_worst_us = worst_us

    if ibm_worst_us is None:
        ibm_worst_us = max(by_arch_worst.values()) if by_arch_worst else 1.0
    for label, worst_us in sorted(by_arch_worst.items(), key=lambda t: _arch_sort_key(t[0])):
        ratio = _safe_ratio(worst_us, ibm_worst_us)
        if ratio is None:
            continue
        tip_summary.append((label, ratio, worst_us / 1000.0))

    labels = [r[0] for r in tip_summary]
    ratios = [r[1] for r in tip_summary]
    worst_ms_vals = [r[2] for r in tip_summary]
    x_tip = list(range(len(labels)))
    clip_cap = max(ratios) if ratios else 1.0
    non_ibm = [r for l, r in zip(labels, ratios) if "power" not in l.lower()]
    if non_ibm:
        med = _median(non_ibm)
        if max(ratios) > med * 1.5 and med > 0:
            clip_cap = med * 1.5
    shown = [min(v, clip_cap) for v in ratios]
    bars = ax_tip.bar(x_tip, shown, color=[_arch_color(l) for l in labels], width=0.6)
    ax_tip.set_xticks(x_tip)
    ax_tip.set_xticklabels(labels, rotation=15, ha="right")
    ax_tip.set_xlabel("Architecture")
    ax_tip.set_ylabel("Worst-case p99 ratio vs IBM Power10 (x)")
    ax_tip.set_title("Tipping-point decision view vs IBM Power10 (lower is better)")
    ax_tip.set_ylim(0, max(shown) * 1.25 if shown else 1.25)
    ax_tip.grid(True, axis="y", alpha=0.3)
    for i, b in enumerate(bars):
        is_ibm = "power" in labels[i].lower()
        if is_ibm:
            lbl = f"{worst_ms_vals[i]:.1f} ms"
        else:
            lbl = f"{worst_ms_vals[i]:.1f} ms\n{ratios[i]:.2f}x vs IBM"
        if ratios[i] > shown[i]:
            lbl += " *"
        ax_tip.annotate(
            lbl,
            (b.get_x() + b.get_width() / 2, shown[i]),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            fontsize=8,
        )
    # Skip extra clip labels to keep this panel clean.

    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
    else:
        plt.show()


def tipping_points(eff_data: list[dict], latency_threshold_us: float = 100_000) -> list[dict]:
    """Identify rows where p99 latency exceeds threshold (e.g. 100ms = 100_000 µs)."""
    return [r for r in eff_data if r["p99_lat_us_mean"] > latency_threshold_us]


def discover_result_paths(parent_dir: str) -> list[str]:
    """
    Given a directory, return all nested dirs that contain:
    - perf_run_*.json / processed_results.json
    - ai_resilience_final.csv
    - mttr_data.csv
    This allows a single 'results' input path to work even with nested arch folders.
    """
    p = Path(parent_dir)
    if not p.is_dir():
        return []
    found_dirs: set[Path] = set()

    # Pull JSON result folders recursively.
    for json_file in p.rglob("perf_run_*.json"):
        found_dirs.add(json_file.parent)
    for json_file in p.rglob("processed_results.json"):
        found_dirs.add(json_file.parent)

    # AI and MTTR files can also live at the architecture root.
    for ai_csv in p.rglob("ai_resilience_final.csv"):
        found_dirs.add(ai_csv.parent)
    for mttr_csv in p.rglob("mttr_data.csv"):
        found_dirs.add(mttr_csv.parent)

    # If a child folder already has results, drop the parent to avoid duplicate traces.
    pruned = []
    for d in sorted(found_dirs):
        if any(other != d and d in other.parents for other in found_dirs):
            continue
        pruned.append(d)
    return [str(d) for d in pruned]


def load_mttr_csv(dir_path: str) -> list[float]:
    """
    Load MTTR samples from mttr_data.csv in the given directory, if present.
    Returns a list of float seconds; empty list if file is missing or unreadable.
    """
    p = Path(dir_path) / "mttr_data.csv"
    if not p.exists():
        return []
    values: list[float] = []
    try:
        with open(p, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if "," in line:
                    parts = line.split(",", 1)
                    value = parts[1].strip()
                else:
                    value = line
                try:
                    values.append(float(value))
                except ValueError:
                    continue
    except OSError:
        return []
    return values


def load_ai_csv(path: str) -> list[dict]:
    """Load AI resilience rows from ai_resilience_final.csv."""
    p = Path(path)
    if p.is_dir():
        p = p / "ai_resilience_final.csv"
    if not p.exists():
        return []
    rows: list[dict] = []
    try:
        with open(p, "r", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                arch = (r.get("Architecture") or "").strip()
                test_type = (r.get("Test_Type") or "").strip()
                if not arch or test_type not in {"Idle", "Stressed"}:
                    continue
                try:
                    rows.append(
                        {
                            "architecture": arch,
                            "workload": (r.get("Workload") or "unknown").strip() or "unknown",
                            "test_type": test_type,
                            "avg_latency_ms": float(r.get("Average_Latency", "0") or 0),
                            "p99_latency_ms": float(r.get("p99_Latency", "0") or 0),
                            "jitter_delta_ms": float(r.get("Jitter_Delta", "0") or 0),
                            "efficiency_loss_pct": float(r.get("Efficiency_Loss_Pct", "0") or 0),
                        }
                    )
                except ValueError:
                    continue
    except OSError:
        return []
    return rows


def load_ai_csv_recursive(path: str) -> list[dict]:
    """Load and combine all ai_resilience_final.csv files under a directory."""
    p = Path(path)
    if not p.is_dir():
        return load_ai_csv(path)
    rows: list[dict] = []
    for ai_csv in sorted(p.rglob("ai_resilience_final.csv")):
        rows.extend(load_ai_csv(str(ai_csv)))
    return rows


def ai_latest_per_arch(ai_rows: list[dict]) -> list[dict]:
    """Aggregate AI metrics per architecture/workload (mean across runs)."""
    by_arch: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(lambda: {"Idle": [], "Stressed": []})
    for row in ai_rows:
        key = (row["architecture"], row.get("workload", "unknown"))
        by_arch[key][row["test_type"]].append(row)

    summary = []
    for (arch, workload), pair in sorted(by_arch.items()):
        idle_rows = pair.get("Idle", [])
        stressed_rows = pair.get("Stressed", [])
        if not idle_rows or not stressed_rows:
            continue
        idle_avg_ms = sum(r["avg_latency_ms"] for r in idle_rows) / len(idle_rows)
        stressed_avg_ms = sum(r["avg_latency_ms"] for r in stressed_rows) / len(stressed_rows)
        idle_p99_ms = sum(r["p99_latency_ms"] for r in idle_rows) / len(idle_rows)
        stressed_p99_ms = sum(r["p99_latency_ms"] for r in stressed_rows) / len(stressed_rows)
        jitter_delta_ms = sum(r["jitter_delta_ms"] for r in stressed_rows) / len(stressed_rows)
        loss_values = [r["efficiency_loss_pct"] for r in stressed_rows]
        efficiency_loss_pct = _median(loss_values)
        slowdown_factor = stressed_avg_ms / idle_avg_ms if idle_avg_ms else 0.0
        absolute_delta_ms = stressed_avg_ms - idle_avg_ms
        summary.append(
            {
                "architecture": arch,
                "workload": workload,
                "idle_avg_ms": idle_avg_ms,
                "stressed_avg_ms": stressed_avg_ms,
                "idle_p99_ms": idle_p99_ms,
                "stressed_p99_ms": stressed_p99_ms,
                "jitter_delta_ms": jitter_delta_ms,
                "efficiency_loss_pct": efficiency_loss_pct,
                "slowdown_factor": slowdown_factor,
                "absolute_delta_ms": absolute_delta_ms,
                "runs": min(len(idle_rows), len(stressed_rows)),
            }
        )
    return summary


def plot_ai_resilience(ai_summary: list[dict], out_path: str | None = None) -> None:
    """Plot AI stress sensitivity metrics by architecture."""
    if not ai_summary:
        return
    ordered = sorted(ai_summary, key=lambda r: r["stressed_avg_ms"])
    archs = [_ai_arch_display(r["architecture"]) for r in ordered]
    arch_ticks = [a.replace(" (", "\n(") for a in archs]
    x = list(range(len(archs)))
    width = 0.35

    fig, (ax_avg, ax_p99, ax_eff) = plt.subplots(
        3,
        1,
        sharex=False,
        figsize=(max(14, len(archs) * 4.0), 12),
        constrained_layout=True,
    )

    idle_avg = [r["idle_avg_ms"] for r in ordered]
    stressed_avg = [r["stressed_avg_ms"] for r in ordered]
    ax_avg.bar([i - width / 2 for i in x], idle_avg, width=width, label="Idle")
    ax_avg.bar([i + width / 2 for i in x], stressed_avg, width=width, label="Stressed")
    ax_avg.set_ylabel("Avg latency (ms)")
    ax_avg.set_title("AI stress sensitivity — Average latency by architecture")
    ax_avg.set_yscale("log")
    ax_avg.grid(True, axis="y", alpha=0.3)
    ax_avg.yaxis.set_major_formatter(FuncFormatter(_ms_tick_formatter))
    ax_avg.set_xticks(x)
    ax_avg.set_xticklabels(arch_ticks, rotation=0, ha="center")
    ax_avg.tick_params(axis="x", labelbottom=True, bottom=True, labeltop=False, top=False, pad=4)
    for i in x:
        ax_avg.annotate(
            f"{idle_avg[i]:.3f} ms",
            (i - width / 2, idle_avg[i]),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=8,
        )
    for i in x:
        pct = _safe_pct_delta(stressed_avg[i], idle_avg[i])
        if pct is None:
            continue
        ax_avg.annotate(
            f"{pct:+.1f}%",
            (i + width / 2, stressed_avg[i]),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            fontsize=8,
        )

    idle_p99 = [r["idle_p99_ms"] for r in ordered]
    stressed_p99 = [r["stressed_p99_ms"] for r in ordered]
    ax_p99.bar([i - width / 2 for i in x], idle_p99, width=width, label="Idle")
    ax_p99.bar([i + width / 2 for i in x], stressed_p99, width=width, label="Stressed")
    ax_p99.set_ylabel("p99 latency (ms)")
    ax_p99.set_title("AI stress sensitivity — p99 latency by architecture")
    ax_p99.set_yscale("log")
    ax_p99.grid(True, axis="y", alpha=0.3)
    ax_p99.yaxis.set_major_formatter(FuncFormatter(_ms_tick_formatter))
    ax_p99.set_xticks(x)
    ax_p99.set_xticklabels(arch_ticks, rotation=0, ha="center")
    ax_p99.tick_params(axis="x", labelbottom=True, bottom=True, labeltop=False, top=False, pad=4)
    for i in x:
        ax_p99.annotate(
            f"{idle_p99[i]:.3f} ms",
            (i - width / 2, idle_p99[i]),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=8,
        )
    for i in x:
        pct = _safe_pct_delta(stressed_p99[i], idle_p99[i])
        if pct is None:
            continue
        ax_p99.annotate(
            f"{pct:+.1f}%",
            (i + width / 2, stressed_p99[i]),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            fontsize=8,
        )

    losses = [r["efficiency_loss_pct"] for r in ordered]
    deltas = [r["absolute_delta_ms"] for r in ordered]
    finite_losses = [v for v in losses if math.isfinite(v)]
    median_loss = sorted(finite_losses)[len(finite_losses) // 2] if finite_losses else 0.0
    max_loss = max(finite_losses) if finite_losses else 0.0
    clip_cap = max_loss
    if max_loss > (median_loss * 3.0) and median_loss > 0:
        clip_cap = median_loss * 3.0
    clipped_losses = [min(v, clip_cap) for v in losses]

    bars = ax_eff.bar(x, clipped_losses, width=0.6)
    ax_eff.set_ylabel("Efficiency loss (%)")
    ax_eff.set_title("AI stress sensitivity — Efficiency loss under stress")
    ax_eff.grid(True, axis="y", alpha=0.3)
    for i, b in enumerate(bars):
        shown = clipped_losses[i]
        actual = losses[i]
        label = f"{actual:.1f}%"
        ax_eff.annotate(
            label,
            (b.get_x() + b.get_width() / 2, shown),
            textcoords="offset points",
            xytext=(0, 4 if shown >= 0 else -12),
            ha="center",
            fontsize=8,
        )

    ax_eff.set_xticks(x)
    ax_eff.set_xticklabels(arch_ticks, rotation=0, ha="center")

    # constrained_layout handles spacing so x tick labels are not clipped.
    if out_path:
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
    else:
        plt.show()


def plot_ai_resilience_split(ai_summary: list[dict], out_dir: str) -> None:
    """Generate separate AI stress sensitivity plots."""
    if not ai_summary:
        return
    os.makedirs(out_dir, exist_ok=True)
    width = 0.35

    ordered_avg = sorted(ai_summary, key=lambda r: r["stressed_avg_ms"])
    archs = [_ai_arch_display(r["architecture"]) for r in ordered_avg]
    x = list(range(len(archs)))
    idle_avg = [r["idle_avg_ms"] for r in ordered_avg]
    stressed_avg = [r["stressed_avg_ms"] for r in ordered_avg]
    fig, ax = plt.subplots(figsize=(max(8, len(archs) * 2.0), 4.8))
    ax.bar([i - width / 2 for i in x], idle_avg, width=width, label="Idle")
    ax.bar([i + width / 2 for i in x], stressed_avg, width=width, label="Stressed")
    ax.set_title("AI stress sensitivity — Average latency")
    ax.set_ylabel("Avg latency (ms)")
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels(archs, rotation=15, ha="right")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    ax.yaxis.set_major_formatter(FuncFormatter(_ms_tick_formatter))
    for i in x:
        pct = _safe_pct_delta(stressed_avg[i], idle_avg[i])
        if pct is None:
            continue
        ax.annotate(
            f"{pct:+.1f}%",
            (i + width / 2, stressed_avg[i]),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            fontsize=8,
        )
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "ai_avg_latency.png"), dpi=160)
    plt.close(fig)

    ordered_p99 = sorted(ai_summary, key=lambda r: r["stressed_p99_ms"])
    archs = [_ai_arch_display(r["architecture"]) for r in ordered_p99]
    x = list(range(len(archs)))
    idle_p99 = [r["idle_p99_ms"] for r in ordered_p99]
    stressed_p99 = [r["stressed_p99_ms"] for r in ordered_p99]
    fig, ax = plt.subplots(figsize=(max(8, len(archs) * 2.0), 4.8))
    ax.bar([i - width / 2 for i in x], idle_p99, width=width, label="Idle")
    ax.bar([i + width / 2 for i in x], stressed_p99, width=width, label="Stressed")
    ax.set_title("AI stress sensitivity — p99 latency")
    ax.set_ylabel("p99 latency (ms)")
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels(archs, rotation=15, ha="right")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    ax.yaxis.set_major_formatter(FuncFormatter(_ms_tick_formatter))
    for i in x:
        pct = _safe_pct_delta(stressed_p99[i], idle_p99[i])
        if pct is None:
            continue
        ax.annotate(
            f"{pct:+.1f}%",
            (i + width / 2, stressed_p99[i]),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            fontsize=8,
        )
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "ai_p99_latency.png"), dpi=160)
    plt.close(fig)

    # Keep percentage-loss view, but clip y-axis for readability and annotate outliers.
    ordered_loss = sorted(ai_summary, key=lambda r: r["efficiency_loss_pct"])
    archs = [_ai_arch_display(r["architecture"]) for r in ordered_loss]
    x = list(range(len(archs)))
    losses = [r["efficiency_loss_pct"] for r in ordered_loss]
    finite_losses = [v for v in losses if math.isfinite(v)]
    median_loss = sorted(finite_losses)[len(finite_losses) // 2] if finite_losses else 0.0
    max_loss = max(finite_losses) if finite_losses else 0.0
    clip_cap = max_loss
    if max_loss > (median_loss * 3.0) and median_loss > 0:
        clip_cap = median_loss * 3.0
    clipped_losses = [min(v, clip_cap) for v in losses]

    fig, ax = plt.subplots(figsize=(max(8, len(archs) * 2.0), 4.8))
    bars = ax.bar(x, clipped_losses, width=0.6)
    ax.set_title("AI stress sensitivity — Efficiency loss %")
    ax.set_ylabel("Efficiency loss (%)")
    ax.set_xticks(x)
    ax.set_xticklabels(archs, rotation=15, ha="right")
    ax.grid(True, axis="y", alpha=0.3)
    for i, b in enumerate(bars):
        shown = clipped_losses[i]
        actual = losses[i]
        label = f"{actual:.1f}%"
        ax.annotate(
            label,
            (b.get_x() + b.get_width() / 2, shown),
            textcoords="offset points",
            xytext=(0, 4 if shown >= 0 else -12),
            ha="center",
            fontsize=8,
        )
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "ai_efficiency_loss_readable.png"), dpi=160)
    plt.close(fig)


def plot_reliability(
    datasets: list[tuple[list[float], dict]],
    out_path: str | None = None,
) -> None:
    """
    Plot reliability (SIFI) results as MTTR per architecture with % delta labels.
    """
    if not datasets:
        return

    labels = []
    means = []
    stds = []
    metas = []
    sample_sets = []
    for mttr_samples, meta in datasets:
        if not mttr_samples:
            continue
        label = _arch_label(meta)
        m, s = _mean_std(mttr_samples)
        labels.append(label)
        means.append(m)
        stds.append(s)
        metas.append(meta)
        sample_sets.append(mttr_samples)

    if not labels:
        return

    rows = sorted(zip(labels, means, stds, metas, sample_sets), key=lambda r: _arch_sort_key(r[0]))
    labels = [r[0] for r in rows]
    means = [r[1] for r in rows]
    stds = [r[2] for r in rows]
    metas = [r[3] for r in rows]
    sample_sets = [r[4] for r in rows]

    ref_idx = _reference_dataset_index_from_meta(metas, preferred="ppc64le")
    ref_label = labels[ref_idx]
    ref_mean = means[ref_idx]

    fig, ax = plt.subplots(figsize=(9, 5))
    x = list(range(1, len(labels) + 1))
    vp = ax.violinplot(sample_sets, positions=x, showmeans=False, showmedians=True, showextrema=False)
    for body in vp["bodies"]:
        body.set_alpha(0.4)
    ci95 = [1.96 * (s / (len(sample_sets[i]) ** 0.5)) for i, s in enumerate(stds)]
    ax.errorbar(x, means, yerr=ci95, fmt="o", color="black", capsize=4, label="Mean ±95% CI")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("MTTR (s)")
    ax.set_title(f"Reliability sweep (SIFI) — MTTR distribution and confidence (% vs {ref_label})")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="best")

    for i, label in enumerate(labels):
        if i == ref_idx:
            ax.annotate(
                f"{means[i]:.3f}s",
                (i + 1, means[i]),
                textcoords="offset points",
                xytext=(0, 8),
                ha="center",
                fontsize=11,
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.8, pad=0.3),
            )
            continue
        pct = _safe_pct_improvement_lower_is_better(means[i], ref_mean)
        if pct is None:
            continue
        sign = "+" if pct >= 0 else ""
        ax.annotate(
            f"{sign}{pct:.1f}%",
            (i + 1, means[i]),
            textcoords="offset points",
            xytext=(0, 28),
            ha="center",
            fontsize=12,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.8, pad=0.5),
        )

    # Add explicit seconds labels for non-reference systems.
    for i, label in enumerate(labels):
        if i == ref_idx:
            continue
        ax.annotate(
            f"{means[i]:.3f}s",
            (i + 1, means[i]),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=11,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.8, pad=0.3),
        )
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
    else:
        plt.show()


def plot_capability_per_arch(datasets: list[tuple[list[dict], dict]], out_dir: str) -> None:
    """Generate one capability plot per architecture."""
    os.makedirs(out_dir, exist_ok=True)
    for cap_data, meta in datasets:
        if not cap_data:
            continue
        by_scenario = defaultdict(list)
        for row in cap_data:
            by_scenario[row.get("scenario", "baseline")].append(row)

        fig, ax = plt.subplots(figsize=(8, 5))
        for scenario, rows in sorted(by_scenario.items()):
            rows = sorted(rows, key=lambda r: r["threads"])
            x = [r["threads"] for r in rows]
            y = [r["ops_per_sec_mean"] for r in rows]
            ax.plot(x, y, marker="o", label=scenario)
        arch = _arch_label(meta)
        ax.set_title(f"Capability sweep — {arch}")
        ax.set_xlabel("Threads")
        ax.set_ylabel("Bogo ops/s")
        ax.legend(loc="best")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        safe_arch = arch.lower().replace(" ", "_")
        fig.savefig(os.path.join(out_dir, f"capability_{safe_arch}.png"), dpi=160)
        plt.close(fig)


def plot_efficiency_per_arch(datasets: list[tuple[list[dict], dict]], out_dir: str) -> None:
    """Generate one efficiency plot (bandwidth + p99) per architecture."""
    os.makedirs(out_dir, exist_ok=True)
    for eff_data, meta in datasets:
        if not eff_data:
            continue
        rows = [
            r
            for r in eff_data
            if r.get("iodepth", 1) == 1 and r.get("numjobs", 1) == 1 and r.get("scenario", "baseline") == "baseline"
        ] or eff_data
        rows = sorted(rows, key=lambda r: r["block_size"])
        blocks = [r["block_size"] for r in rows]
        bw = [r["bw_mib_s_mean"] for r in rows]
        lat = [r["p99_lat_us_mean"] for r in rows]

        fig, (ax_bw, ax_lat) = plt.subplots(2, 1, sharex=True, figsize=(9, 7))
        ax_bw.bar(blocks, bw, color="#4C78A8")
        ax_bw.set_ylabel("Bandwidth (MiB/s)")
        ax_bw.set_title(f"Efficiency bandwidth — {_arch_label(meta)}")
        ax_bw.grid(True, axis="y", alpha=0.3)

        ax_lat.bar(blocks, lat, color="#F58518")
        ax_lat.set_ylabel("p99 latency (µs)")
        ax_lat.set_title(f"Efficiency p99 latency — {_arch_label(meta)}")
        ax_lat.set_xlabel("Block size")
        ax_lat.grid(True, axis="y", alpha=0.3)
        fig.tight_layout()
        safe_arch = _arch_label(meta).lower().replace(" ", "_")
        fig.savefig(os.path.join(out_dir, f"efficiency_{safe_arch}.png"), dpi=160)
        plt.close(fig)


def write_summary_tables(
    datasets: list[tuple[list[dict], list[dict], dict]],
    mttr_datasets: list[tuple[list[float], dict]],
    out_dir: str,
) -> None:
    """
    Write report-friendly CSV summary tables for capability, efficiency, and reliability.
    """
    os.makedirs(out_dir, exist_ok=True)

    cap_path = os.path.join(out_dir, "summary_capability.csv")
    with open(cap_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["architecture", "scenario", "duration_s", "threads", "ops_per_sec_mean", "ops_per_sec_std"],
        )
        writer.writeheader()
        for cap_data, _, meta in datasets:
            arch = _arch_label(meta)
            for row in cap_data:
                writer.writerow(
                    {
                        "architecture": arch,
                        "scenario": row.get("scenario"),
                        "duration_s": row.get("duration_s", 5),
                        "threads": row.get("threads"),
                        "ops_per_sec_mean": row.get("ops_per_sec_mean"),
                        "ops_per_sec_std": row.get("ops_per_sec_std"),
                    }
                )

    eff_path = os.path.join(out_dir, "summary_efficiency.csv")
    with open(eff_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "architecture",
                "scenario",
                "block_size",
                "iodepth",
                "numjobs",
                "rw_pattern",
                "runtime_s",
                "bw_mib_s_mean",
                "bw_mib_s_std",
                "p99_lat_us_mean",
                "p99_lat_us_std",
            ],
        )
        writer.writeheader()
        for _, eff_data, meta in datasets:
            arch = _arch_label(meta)
            for row in eff_data:
                writer.writerow(
                    {
                        "architecture": arch,
                        "scenario": row.get("scenario"),
                        "block_size": row.get("block_size"),
                        "iodepth": row.get("iodepth", 1),
                        "numjobs": row.get("numjobs", 1),
                        "rw_pattern": row.get("rw_pattern", "write"),
                        "runtime_s": row.get("runtime_s", 5),
                        "bw_mib_s_mean": row.get("bw_mib_s_mean"),
                        "bw_mib_s_std": row.get("bw_mib_s_std"),
                        "p99_lat_us_mean": row.get("p99_lat_us_mean"),
                        "p99_lat_us_std": row.get("p99_lat_us_std"),
                    }
                )

    rel_path = os.path.join(out_dir, "summary_reliability.csv")
    with open(rel_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["architecture", "mttr_samples", "mttr_mean_s", "mttr_std_s"],
        )
        writer.writeheader()
        for mttr_samples, meta in mttr_datasets:
            if not mttr_samples:
                continue
            m, s = _mean_std(mttr_samples)
            writer.writerow(
                {
                    "architecture": _arch_label(meta),
                    "mttr_samples": len(mttr_samples),
                    "mttr_mean_s": m,
                    "mttr_std_s": s,
                }
            )


def write_ai_summary_table(ai_summary: list[dict], out_dir: str) -> None:
    if not ai_summary:
        return
    ai_path = os.path.join(out_dir, "summary_ai.csv")
    with open(ai_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "architecture",
                "workload",
                "runs",
                "idle_avg_ms",
                "stressed_avg_ms",
                "idle_p99_ms",
                "stressed_p99_ms",
                "jitter_delta_ms",
                "efficiency_loss_pct",
                "slowdown_factor",
                "absolute_delta_ms",
            ],
        )
        writer.writeheader()
        for row in ai_summary:
            writer.writerow(row)


def analyze_and_plot(
    paths: list[str] | None = None,
    path: str | None = None,
    out_dir: str | None = None,
    show: bool = True,
) -> None:
    """
    Load JSON result(s) from one or more paths. Each path can be a file or directory.
    If a single directory is given, subdirs containing result JSONs are included.
    Plots all architectures on the same capability and efficiency graphs.
    """
    if paths is None:
        paths = [path or "results"]
    root_path_for_aux = paths[0] if len(paths) == 1 else None
    # If single directory: discover subdirs so "results" → results + results/Power10 + ...
    if len(paths) == 1 and Path(paths[0]).is_dir():
        resolved = discover_result_paths(paths[0])
        if resolved:
            paths = resolved
    datasets = []  # (cap_data, eff_data, meta)
    mttr_datasets = []  # (mttr_samples, meta)
    ai_rows_all = []
    for p in paths:
        json_paths = find_result_jsons(p)
        if json_paths:
            data = [load_result_json(f) for f in json_paths]
            cap_data, eff_data, meta = results_to_tables(data)
            label = _arch_label(meta)
            print(f"Loaded {len(json_paths)} run(s) for {label} from {p}")
            tipping = tipping_points(eff_data, latency_threshold_us=100_000)
            if tipping:
                print(f"  Tipping points (p99 > 100 ms): {[r['block_size'] for r in tipping]}")
            datasets.append((cap_data, eff_data, meta))
            mttr = load_mttr_csv(p)
            if mttr:
                m, s = _mean_std(mttr)
                print(f"  SIFI MTTR samples: n={len(mttr)}, mean={m:.3f}s, std={s:.3f}s")
                mttr_datasets.append((mttr, meta))
        else:
            print(f"No result JSONs at {p}, skipping JSON plots for this path.")

        ai_rows = load_ai_csv(p)
        if ai_rows:
            ai_rows_all.extend(ai_rows)

    # Pick up AI CSVs recursively in case root-level discovery was pruned.
    if root_path_for_aux and Path(root_path_for_aux).is_dir():
        ai_rows = load_ai_csv_recursive(root_path_for_aux)
        if ai_rows:
            ai_rows_all.extend(ai_rows)

    ai_summary = ai_latest_per_arch(ai_rows_all)

    if not datasets and not ai_summary:
        print("No result JSONs or AI CSV found. Expect perf_run_*.json and/or ai_resilience_final.csv")
        return

    save_basename = None
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        save_basename = os.path.join(out_dir, "plot")

    cap_datasets = [(c, m) for c, e, m in datasets if c]
    eff_datasets = [(e, m) for c, e, m in datasets if e]
    rel_datasets = [(mttr, m) for mttr, m in mttr_datasets if mttr]
    if ai_summary:
        plot_ai_resilience(
            ai_summary,
            out_path=f"{save_basename}_ai_resilience.png" if save_basename else None,
        )
    if cap_datasets:
        plot_capability(
            cap_datasets,
            out_path=f"{save_basename}_capability.png" if save_basename else None,
        )
    if eff_datasets:
        plot_efficiency(
            eff_datasets,
            out_path=f"{save_basename}_efficiency.png" if save_basename else None,
        )
    if rel_datasets:
        plot_reliability(
            rel_datasets,
            out_path=f"{save_basename}_reliability.png" if save_basename else None,
        )
    if out_dir:
        if datasets:
            write_summary_tables(datasets, mttr_datasets, out_dir)
            detail_dir = os.path.join(out_dir, "detail")
            plot_capability_per_arch(cap_datasets, detail_dir)
            plot_efficiency_per_arch(eff_datasets, detail_dir)
        write_ai_summary_table(ai_summary, out_dir)
        plot_ai_resilience_split(ai_summary, os.path.join(out_dir, "detail"))
        print(f"Summary tables saved under {out_dir}/")

    if save_basename and (cap_datasets or eff_datasets):
        print(f"Plots saved under {out_dir}/")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Plot harness JSON results. Pass one or more paths; all are combined on the same graphs.",
    )
    parser.add_argument(
        "path",
        nargs="*",
        default=["results"],
        help="Path(s) to results dir(s) or .json file(s). Single dir auto-includes subdirs (e.g. results + results/Power10).",
    )
    parser.add_argument(
        "-o", "--out-dir",
        default=None,
        help="Directory to save plot images (default: show only)",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open interactive plots (useful when saving only)",
    )
    args = parser.parse_args()
    analyze_and_plot(paths=args.path if args.path else ["results"], out_dir=args.out_dir, show=not args.no_show)
