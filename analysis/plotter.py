"""
Convert harness JSON results into Tipping Point graphs.
Reads processed_results.json or perf_run_*.json from results/ (or a given path).
Uses only stdlib + matplotlib (no polars).
"""
import json
import os
import glob
import csv
from pathlib import Path
from collections import defaultdict

import matplotlib.pyplot as plt


def _safe_pct_delta(value: float, ref: float) -> float | None:
    if ref == 0:
        return None
    return ((value - ref) / ref) * 100.0


def _safe_pct_improvement_lower_is_better(value: float, ref: float) -> float | None:
    if ref == 0:
        return None
    return ((ref - value) / ref) * 100.0


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


def _reference_dataset_index_from_meta(meta_list: list[dict]) -> int:
    """
    Prefer commodity/laptop reference so percentage labels highlight enterprise uplift.
    Fallback: first dataset.
    """
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
    """Plot capability sweep with percentage gain labels vs reference."""
    if not datasets:
        return
    fig, ax = plt.subplots()
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
    ax.legend()
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
    """Plot efficiency sweep with percentage deltas vs reference."""
    if not datasets:
        return
    # Keep this plot focused on the baseline/default fio shape for readability.
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

    # Union of block sizes across all archs (preserve order: first arch's order, then any extra)
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

    n_bs = len(all_bs)
    n_arch = len(filtered)
    bar_width = 0.8 / max(n_arch, 1)
    # Offsets so bars are centered per block_size group
    offsets = [(i - (n_arch - 1) / 2) * bar_width for i in range(n_arch)]

    fig, (ax_bw, ax_lat) = plt.subplots(2, 1, sharex=True, figsize=(max(6, n_bs * 1.5), 7))
    ref_idx = _reference_dataset_index_from_meta([meta for _, meta in filtered])
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
        err_bw = [by_bs.get(bs, {}).get("bw_mib_s_std", 0) for bs in all_bs]
        y_lat = [by_bs.get(bs, {}).get("p99_lat_us_mean", 0) for bs in all_bs]
        err_lat = [by_bs.get(bs, {}).get("p99_lat_us_std", 0) for bs in all_bs]
        x = [i + offsets[idx] for i in range(n_bs)]
        bars_bw = ax_bw.bar(x, y_bw, width=bar_width * 0.9, label=label)
        bars_lat = ax_lat.bar(x, y_lat, width=bar_width * 0.9, label=label)

        if label != ref_label:
            for i, bs in enumerate(all_bs):
                ref_row = ref_by_bs.get(bs)
                if not ref_row:
                    continue

                pct_bw = _safe_pct_delta(y_bw[i], ref_row.get("bw_mib_s_mean", 0))
                if pct_bw is not None:
                    sign = "+" if pct_bw >= 0 else ""
                    ax_bw.annotate(
                        f"{sign}{pct_bw:.1f}%",
                        (bars_bw[i].get_x() + bars_bw[i].get_width() / 2, y_bw[i]),
                        textcoords="offset points",
                        xytext=(0, 4),
                        ha="center",
                        fontsize=7,
                        rotation=90,
                    )

                pct_lat = _safe_pct_improvement_lower_is_better(
                    y_lat[i],
                    ref_row.get("p99_lat_us_mean", 0),
                )
                if pct_lat is not None:
                    sign = "+" if pct_lat >= 0 else ""
                    ax_lat.annotate(
                        f"{sign}{pct_lat:.1f}%",
                        (bars_lat[i].get_x() + bars_lat[i].get_width() / 2, y_lat[i]),
                        textcoords="offset points",
                        xytext=(0, 4),
                        ha="center",
                        fontsize=7,
                        rotation=90,
                    )

    ax_bw.set_ylabel("Bandwidth (MiB/s)")
    ax_bw.set_title(f"Efficiency sweep (fio write) — Bandwidth (% vs {ref_label})")
    ax_bw.set_xticks(range(n_bs))
    ax_bw.set_xticklabels(all_bs)
    ax_bw.legend()
    ax_bw.grid(True, alpha=0.3)

    ax_lat.set_xticks(range(n_bs))
    ax_lat.set_xticklabels(all_bs)
    ax_lat.set_xlabel("Block size")
    ax_lat.set_ylabel("p99 latency (µs)")
    ax_lat.set_title(f"Efficiency sweep — p99 latency (% improvement vs {ref_label})")
    ax_lat.legend()
    ax_lat.grid(True, alpha=0.3)

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
    Given a directory, return [parent_dir] plus any subdirs that contain result JSONs,
    so that a single 'results' path can expand to results + results/Power10 + ...
    """
    p = Path(parent_dir)
    if not p.is_dir():
        return []
    paths = []
    if find_result_jsons(str(p)):
        paths.append(str(p))
    for child in sorted(p.iterdir()):
        if child.is_dir() and find_result_jsons(str(child)):
            paths.append(str(child))
    return paths


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
    for mttr_samples, meta in datasets:
        if not mttr_samples:
            continue
        label = _arch_label(meta)
        m, s = _mean_std(mttr_samples)
        labels.append(label)
        means.append(m)
        stds.append(s)
        metas.append(meta)

    if not labels:
        return

    ref_idx = _reference_dataset_index_from_meta(metas)
    ref_label = labels[ref_idx]
    ref_mean = means[ref_idx]

    fig, ax = plt.subplots()
    x = list(range(len(labels)))
    bars = ax.bar(x, means)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("MTTR (s)")
    ax.set_title(f"Reliability sweep (SIFI) — MTTR (% vs {ref_label})")
    ax.grid(True, axis="y", alpha=0.3)

    for i, label in enumerate(labels):
        if i == ref_idx:
            continue
        pct = _safe_pct_improvement_lower_is_better(means[i], ref_mean)
        if pct is None:
            continue
        sign = "+" if pct >= 0 else ""
        ax.annotate(
            f"{sign}{pct:.1f}%",
            (bars[i].get_x() + bars[i].get_width() / 2, means[i]),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            fontsize=8,
        )
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
    else:
        plt.show()


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
    # If single directory: discover subdirs so "results" → results + results/Power10 + ...
    if len(paths) == 1 and Path(paths[0]).is_dir():
        resolved = discover_result_paths(paths[0])
        if resolved:
            paths = resolved
    datasets = []  # (cap_data, eff_data, meta)
    mttr_datasets = []  # (mttr_samples, meta)
    for p in paths:
        json_paths = find_result_jsons(p)
        if not json_paths:
            print(f"No result JSONs at {p}, skipping.")
            continue
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

    if not datasets:
        print("No result JSONs found. Expect processed_results.json or perf_run_*.json")
        return

    save_basename = None
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        save_basename = os.path.join(out_dir, "plot")

    cap_datasets = [(c, m) for c, e, m in datasets if c]
    eff_datasets = [(e, m) for c, e, m in datasets if e]
    rel_datasets = [(mttr, m) for mttr, m in mttr_datasets if mttr]
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
        write_summary_tables(datasets, mttr_datasets, out_dir)
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
