"""Generate repeatable charts and a raster architecture image from checked-in project data."""
from __future__ import annotations

import csv
import gzip
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
FIGS = DOCS / "figures"
FIGS.mkdir(parents=True, exist_ok=True)


def read_runs() -> list[dict]:
    csv_path = ROOT / "benchmark_results.csv"
    compressed_path = ROOT / "benchmark_results.csv.gz"
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    if compressed_path.exists():
        with gzip.open(compressed_path, "rt", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    raise FileNotFoundError("Expected benchmark_results.csv or benchmark_results.csv.gz at project root.")


def save_both(fig, stem: str) -> None:
    fig.tight_layout()
    fig.savefig(FIGS / f"{stem}.png", dpi=160, bbox_inches="tight", facecolor="white")
    fig.savefig(FIGS / f"{stem}.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    rows = read_runs()
    main_runs = [r for r in rows if r["tlb_enabled"].lower() == "true"]
    algorithms = ["FIFO", "LRU", "Clock", "Optimal"]
    modes = ["none", "redistribution_only", "suspension_only", "combined"]
    labels = {
        "none": "No adaptation",
        "redistribution_only": "Redistribution only",
        "suspension_only": "Suspension only",
        "combined": "Combined",
    }
    series_values = {
        (alg, mode): statistics.mean(
            int(r["page_faults"]) for r in main_runs
            if r["algorithm"] == alg and r["control_mode"] == mode
        )
        for alg in algorithms for mode in modes
    }

    fig, ax = plt.subplots(figsize=(10.4, 5.8))
    width = 0.19
    for j, mode in enumerate(modes):
        ax.bar(
            [i + (j - 1.5) * width for i in range(len(algorithms))],
            [series_values[(alg, mode)] for alg in algorithms],
            width=width, label=labels[mode],
        )
    ax.set_xticks(range(len(algorithms)), algorithms)
    ax.set_ylabel("Mean page faults per 1,600 references")
    ax.set_title("Adaptive-policy ablation across synthetic workloads and seeds")
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    ax.legend(ncol=2, frameon=False)
    save_both(fig, "overall_ablation_results")

    patterns = [
        "phase_locality", "uniform_random", "sequential_scan",
        "bursty_hotset", "alternating_hotsets",
    ]
    pattern_labels = [
        "Phase locality", "Uniform random", "Sequential scan",
        "Bursty hot set", "Alternating hot sets",
    ]
    baseline = {
        pat: statistics.mean(
            int(r["page_faults"]) for r in main_runs
            if r["workload_pattern"] == pat and r["algorithm"] == "LRU" and r["control_mode"] == "none"
        ) for pat in patterns
    }
    fig, ax = plt.subplots(figsize=(11, 5.9))
    for j, mode in enumerate(modes):
        vals = []
        for pat in patterns:
            variant = statistics.mean(
                int(r["page_faults"]) for r in main_runs
                if r["workload_pattern"] == pat and r["algorithm"] == "LRU" and r["control_mode"] == mode
            )
            vals.append(100 * (baseline[pat] - variant) / baseline[pat] if baseline[pat] else 0)
        ax.bar(
            [i + (j - 1.5) * width for i in range(len(patterns))],
            vals, width=width, label=labels[mode],
        )
    ax.axhline(0, color="#555555", linewidth=0.8)
    ax.set_xticks(range(len(patterns)), pattern_labels, rotation=12, ha="right")
    ax.set_ylabel("Page-fault reduction vs baseline (%)")
    ax.set_title("LRU intervention effects by workload pattern")
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    ax.legend(ncol=2, frameon=False)
    save_both(fig, "lru_workload_effects")

    tlb_on = [
        int(r["page_table_accesses"]) for r in rows
        if r["control_mode"] == "none" and r["tlb_enabled"].lower() == "true"
    ]
    tlb_off = [
        int(r["page_table_accesses"]) for r in rows
        if r["control_mode"] == "none_tlb_off_check"
    ]
    if not tlb_off:
        raise ValueError("The checked-in experiment must include paired TLB-off baseline records.")
    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    vals = [statistics.mean(tlb_on), statistics.mean(tlb_off)]
    bars = ax.bar([0, 1], vals, width=0.55)
    ax.set_xticks([0, 1], ["TLB enabled", "TLB disabled"])
    ax.set_ylabel("Mean page-table accesses per run")
    ax.set_title("TLB effect on translation overhead")
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(), f"{val:,.1f}", ha="center", va="bottom")
    reduction = 100 * (1 - vals[0] / vals[1]) if vals[1] else 0
    ax.text(0.5, 0.93, f"{reduction:.1f}% fewer page-table accesses with TLB", ha="center", transform=ax.transAxes)
    save_both(fig, "tlb_effect")
    print(f"Generated figure files under {FIGS}")

if __name__ == "__main__":
    main()
