"""
Convert harness JSON results into Tipping Point graphs.
Reads processed_results.json or perf_run_*.json from results/ (or a given path).
Uses only stdlib + matplotlib (no polars).
"""
import json
import os
import glob
from pathlib import Path
from collections import defaultdict

import matplotlib.pyplot as plt


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
            by_threads[r["threads"]].append(r["ops_per_sec"])
        for threads in sorted(by_threads):
            vals = by_threads[threads]
            m, s = _mean_std(vals)
            row = {"threads": threads, "ops_per_sec": m}
            if len(jsons) > 1:
                row["ops_per_sec_mean"], row["ops_per_sec_std"] = m, s
            else:
                row["ops_per_sec_mean"], row["ops_per_sec_std"] = m, 0.0
            cap_data.append(row)

    eff_data = []
    if eff_rows:
        by_bs = defaultdict(lambda: {"bw": [], "lat": []})
        for r in eff_rows:
            key = r["block_size"]
            by_bs[key]["bw"].append(r["bw_mib_s"])
            by_bs[key]["lat"].append(r["p99_lat_us"])
        # Preserve block_size order (first occurrence)
        seen = []
        for r in eff_rows:
            bs = r["block_size"]
            if bs not in seen:
                seen.append(bs)
        for block_size in seen:
            bw_vals = by_bs[block_size]["bw"]
            lat_vals = by_bs[block_size]["lat"]
            bw_m, bw_s = _mean_std(bw_vals)
            lat_m, lat_s = _mean_std(lat_vals)
            row = {
                "block_size": block_size,
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
    t = metadata.get("type")
    if t and t != "Unknown":
        return t
    return metadata.get("isa") or "Unknown"


def plot_capability(
    datasets: list[tuple[list[dict], dict]],
    out_path: str | None = None,
) -> None:
    """Plot capability sweep: threads vs ops/s (Pillar 1), one line per architecture."""
    if not datasets:
        return
    fig, ax = plt.subplots()
    for cap_data, meta in datasets:
        if not cap_data:
            continue
        label = _arch_label(meta)
        x = [r["threads"] for r in cap_data]
        y = [r["ops_per_sec_mean"] for r in cap_data]
        err = [r["ops_per_sec_std"] for r in cap_data]
        if any(err):
            ax.errorbar(x, y, yerr=err, marker="o", capsize=4, label=label)
        else:
            ax.plot(x, y, marker="o", label=label)
    ax.set_xlabel("Threads")
    ax.set_ylabel("Bogo ops/s")
    ax.set_title("Capability sweep (stress-ng CPU)")
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
    """Plot efficiency sweep: block size vs bandwidth and p99 latency, grouped by architecture."""
    if not datasets:
        return
    # Union of block sizes across all archs (preserve order: first arch's order, then any extra)
    all_bs = []
    seen_bs = set()
    for eff_data, _ in datasets:
        for r in eff_data:
            bs = r["block_size"]
            if bs not in seen_bs:
                seen_bs.add(bs)
                all_bs.append(bs)
    if not all_bs:
        return

    n_bs = len(all_bs)
    n_arch = len(datasets)
    bar_width = 0.8 / max(n_arch, 1)
    # Offsets so bars are centered per block_size group
    offsets = [(i - (n_arch - 1) / 2) * bar_width for i in range(n_arch)]

    fig, (ax_bw, ax_lat) = plt.subplots(2, 1, sharex=True, figsize=(max(6, n_bs * 1.5), 7))

    def by_block_size(eff_data: list[dict]) -> dict[str, dict]:
        return {r["block_size"]: r for r in eff_data}

    for idx, (eff_data, meta) in enumerate(datasets):
        if not eff_data:
            continue
        label = _arch_label(meta)
        by_bs = by_block_size(eff_data)
        y_bw = [by_bs.get(bs, {}).get("bw_mib_s_mean", 0) for bs in all_bs]
        err_bw = [by_bs.get(bs, {}).get("bw_mib_s_std", 0) for bs in all_bs]
        y_lat = [by_bs.get(bs, {}).get("p99_lat_us_mean", 0) for bs in all_bs]
        err_lat = [by_bs.get(bs, {}).get("p99_lat_us_std", 0) for bs in all_bs]
        x = [i + offsets[idx] for i in range(n_bs)]
        ax_bw.bar(x, y_bw, width=bar_width * 0.9, label=label, yerr=err_bw if any(err_bw) else None, capsize=2)
        ax_lat.bar(x, y_lat, width=bar_width * 0.9, label=label, yerr=err_lat if any(err_lat) else None, capsize=2)

    ax_bw.set_ylabel("Bandwidth (MiB/s)")
    ax_bw.set_title("Efficiency sweep (fio write) — Bandwidth")
    ax_bw.set_xticks(range(n_bs))
    ax_bw.set_xticklabels(all_bs)
    ax_bw.legend()
    ax_bw.grid(True, alpha=0.3)

    ax_lat.set_xticks(range(n_bs))
    ax_lat.set_xticklabels(all_bs)
    ax_lat.set_xlabel("Block size")
    ax_lat.set_ylabel("p99 latency (µs)")
    ax_lat.set_title("Efficiency sweep — p99 latency")
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
                try:
                    values.append(float(line))
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
    Plot reliability (SIFI) results as MTTR (Mean Time To Recovery) per architecture.
    Each architecture becomes a bar with mean ± std error bars.
    """
    if not datasets:
        return

    labels = []
    means = []
    stds = []
    for mttr_samples, meta in datasets:
        if not mttr_samples:
            continue
        label = _arch_label(meta)
        m, s = _mean_std(mttr_samples)
        labels.append(label)
        means.append(m)
        stds.append(s)

    if not labels:
        return

    fig, ax = plt.subplots()
    x = list(range(len(labels)))
    ax.bar(x, means, yerr=stds if any(stds) else None, capsize=4)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("MTTR (s)")
    ax.set_title("Reliability sweep (SIFI) — Mean Time To Recovery")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
    else:
        plt.show()


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
