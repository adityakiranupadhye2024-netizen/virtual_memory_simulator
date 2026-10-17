"""Repeatable multi-pattern virtual-memory experiments with adaptive-policy ablations."""
from __future__ import annotations
import argparse, csv
from collections import defaultdict
from math import sqrt
from pathlib import Path
from statistics import mean, stdev
from vm_simulator.core import MemorySimulator

CONTROL_MODES = {
    "none": (False, False),
    "redistribution_only": (True, False),
    "suspension_only": (False, True),
    "combined": (True, True),
}

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", default="42,43,44,45,46,47,48,49,50,51",
                   help="Comma-separated workload seeds (default: 42 through 51).")
    p.add_argument("--patterns", default=",".join(MemorySimulator.WORKLOAD_PATTERNS),
                   help="Comma-separated patterns: " + ", ".join(MemorySimulator.WORKLOAD_PATTERNS))
    p.add_argument("--frames", type=int, default=16)
    p.add_argument("--processes", type=int, default=4)
    p.add_argument("--length", type=int, default=400)
    p.add_argument("--output", default="benchmark_results.csv")
    p.add_argument("--summary-output", default="benchmark_summary.csv")
    p.add_argument("--paired-output", default="benchmark_paired_summary.csv")
    a = p.parse_args()
    try: a.seeds = [int(x.strip()) for x in a.seeds.split(",") if x.strip()]
    except ValueError as e: p.error(f"Seeds must be comma-separated integers: {e}")
    if not a.seeds: p.error("Provide at least one seed.")
    a.patterns = [x.strip() for x in a.patterns.split(",") if x.strip()]
    unknown = sorted(set(a.patterns) - set(MemorySimulator.WORKLOAD_PATTERNS))
    if not a.patterns or unknown: p.error(f"Unsupported workload patterns: {unknown}")
    if a.frames < a.processes or a.processes < 1 or a.frames < 2: p.error("Frames must be at least 2 and at least the process count.")
    if a.length < 1: p.error("Length must be at least 1.")
    return a

def record_run(sim: MemorySimulator, pattern: str, mode: str, redistribution: bool,
               suspension: bool, tlb_enabled: bool, seed: int, length: int) -> dict:
    m = sim.metrics()
    return {
        "workload_pattern": pattern, "control_mode": mode,
        "frame_redistribution_enabled": redistribution, "process_suspension_enabled": suspension,
        "algorithm": sim.algorithm, "tlb_enabled": tlb_enabled,
        "processes": len(sim.processes), "physical_frames": sim.total_frames,
        "references_per_process": length, "references": sim.references,
        "page_faults": sim.page_faults, "overall_page_fault_rate": round(sim.overall_page_fault_rate, 5),
        "replacements": sim.replacements, "tlb_hits": sim.tlb.hits, "tlb_misses": sim.tlb.misses,
        "tlb_hit_rate": "" if not tlb_enabled else round(sim.tlb_hit_rate or 0.0, 5),
        "page_table_accesses": sim.page_table_accesses, "thrashing_detections": sim.thrashing_detections,
        "adaptive_actions": sim.adaptive_actions, "frame_redistributions": sim.frame_redistributions,
        "process_suspensions": sim.process_suspensions, "simulation_ticks": sim.tick,
        "max_memory_pressure_percent": round(sim.max_memory_pressure_percent, 2),
        "final_status": m["status"], "seed": seed,
    }

def summarize(rows: list[dict], fields: tuple[str, ...], scope: str) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r["tlb_enabled"]:
            groups[tuple(r[f] for f in fields)].append(r)
    result = []
    for key, sample in sorted(groups.items(), key=lambda x: tuple(map(str, x[0]))):
        v = [float(r["page_faults"]) for r in sample]
        sd = stdev(v) if len(v) > 1 else 0.0
        half = 1.96 * sd / sqrt(len(v)) if len(v) > 1 else 0.0
        item = {"scope": scope, **dict(zip(fields, key)), "n": len(v),
                "mean_page_faults": round(mean(v), 3),
                "mean_page_fault_rate": round(mean(float(r["overall_page_fault_rate"]) for r in sample), 5),
                "page_fault_sd": round(sd, 3),
                "ci95_low_normal_approx": round(max(0, mean(v) - half), 3),
                "ci95_high_normal_approx": round(mean(v) + half, 3),
                "mean_replacements": round(mean(float(r["replacements"]) for r in sample), 3),
                "mean_frame_redistributions": round(mean(float(r["frame_redistributions"]) for r in sample), 3),
                "mean_process_suspensions": round(mean(float(r["process_suspensions"]) for r in sample), 3),
                "mean_simulation_ticks": round(mean(float(r["simulation_ticks"]) for r in sample), 3),
                "mean_page_table_accesses": round(mean(float(r["page_table_accesses"]) for r in sample), 3),
                "mean_tlb_hit_rate": round(mean(float(r["tlb_hit_rate"]) for r in sample), 5),
                "mean_max_memory_pressure_percent": round(mean(float(r["max_memory_pressure_percent"]) for r in sample), 3)}
        result.append(item)
    return result

def run_without_history(sim: MemorySimulator, length: int) -> None:
    """Run a benchmark without allocating GUI-style per-reference history rows."""
    limit = length * len(sim.processes) * 4
    for _ in range(limit):
        if sim.is_complete:
            break
        if sim.step() is None:
            break
    if not sim.is_complete:
        raise RuntimeError("A benchmark run failed to finish within the safety limit.")

def main() -> None:
    a = parse_args()
    raw = []
    total = len(a.seeds) * len(a.patterns) * len(MemorySimulator.ALGORITHMS) * len(CONTROL_MODES)
    done = 0
    for pattern in a.patterns:
        for seed in a.seeds:
            for algorithm in MemorySimulator.ALGORITHMS:
                for mode, (redist, suspend) in CONTROL_MODES.items():
                    sim = MemorySimulator(total_frames=a.frames, num_processes=a.processes,
                        algorithm=algorithm, tlb_enabled=True, adaptive_enabled=True,
                        frame_redistribution_enabled=redist, process_suspension_enabled=suspend,
                        sequence_length=a.length, seed=seed, workload_pattern=pattern, record_history=False)
                    run_without_history(sim, a.length)
                    raw.append(record_run(sim, pattern, mode, redist, suspend, True, seed, a.length))
                    done += 1
                    if done % 50 == 0 or done == total: print(f"Main ablation: {done}/{total} runs", flush=True)
    # Paired baseline runs with TLB off isolate translation-caching overhead.
    tlb_off = []
    for pattern in a.patterns:
        for seed in a.seeds:
            for algorithm in MemorySimulator.ALGORITHMS:
                sim = MemorySimulator(total_frames=a.frames, num_processes=a.processes,
                    algorithm=algorithm, tlb_enabled=False, adaptive_enabled=True,
                    frame_redistribution_enabled=False, process_suspension_enabled=False,
                    sequence_length=a.length, seed=seed, workload_pattern=pattern, record_history=False)
                run_without_history(sim, a.length)
                tlb_off.append(record_run(sim, pattern, "none_tlb_off_check", False, False, False, seed, a.length))
    rows = raw + tlb_off
    out = Path(a.output); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    summaries = summarize(rows, ("workload_pattern", "algorithm", "control_mode"), "per_workload")
    summaries += summarize(rows, ("algorithm", "control_mode"), "all_workloads_pooled")
    sout = Path(a.summary_output); sout.parent.mkdir(parents=True, exist_ok=True)
    with sout.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summaries[0])); w.writeheader(); w.writerows(summaries)
    print(f"Saved {len(rows)} run records to {out.resolve()}")
    print(f"Saved {len(summaries)} grouped summaries to {sout.resolve()}")
    print(f"Seeds: {a.seeds}; patterns: {a.patterns}; processes={a.processes}; frames={a.frames}; refs/process={a.length}")
    pooled = [r for r in summaries if r["scope"] == "all_workloads_pooled"]
    print("\nTLB-on mean page faults pooled across patterns and seeds:")
    print("Algorithm | Control mode        | Mean faults | Fault rate | Frame redistrib. | Suspensions")
    for alg in MemorySimulator.ALGORITHMS:
        for mode in CONTROL_MODES:
            r = next(x for x in pooled if x["algorithm"] == alg and x["control_mode"] == mode)
            print(f"{alg:8} | {mode:19} | {r['mean_page_faults']:11.1f} | {r['mean_page_fault_rate']:9.1%} | {r['mean_frame_redistributions']:16.2f} | {r['mean_process_suspensions']:11.2f}")
    on = {(r["workload_pattern"], r["seed"], r["algorithm"]): r["page_faults"] for r in raw if r["control_mode"] == "none"}
    mismatches = sum(on[(r["workload_pattern"], r["seed"], r["algorithm"])] != r["page_faults"] for r in tlb_off)
    print(f"\nPaired TLB validation: {mismatches} page-fault mismatches across {len(tlb_off)} pairs.")

    # Paired policy-effect analysis: every variant is matched to the baseline
    # with the same workload pattern, seed, and replacement algorithm.
    baseline = {(r["workload_pattern"], r["seed"], r["algorithm"]): int(r["page_faults"])
                for r in raw if r["control_mode"] == "none"}
    paired_rows = []
    for alg in MemorySimulator.ALGORITHMS:
        for mode in ("redistribution_only", "suspension_only", "combined"):
            matched = []
            for r in raw:
                if r["algorithm"] != alg or r["control_mode"] != mode:
                    continue
                b = baseline[(r["workload_pattern"], r["seed"], alg)]
                v = int(r["page_faults"])
                matched.append((r["workload_pattern"], b, v, b-v, 100*(b-v)/b if b else 0.0))
            for scope in ["all_workloads"] + list(a.patterns):
                sample = matched if scope == "all_workloads" else [x for x in matched if x[0] == scope]
                diffs = [x[3] for x in sample]
                pcts = [x[4] for x in sample]
                sd_pct = stdev(pcts) if len(pcts) > 1 else 0.0
                half = 1.96 * sd_pct / sqrt(len(pcts)) if len(pcts) > 1 else 0.0
                paired_rows.append({
                    "algorithm": alg, "control_mode": mode, "scope": scope, "n_pairs": len(sample),
                    "mean_baseline_faults": round(mean(x[1] for x in sample), 3),
                    "mean_variant_faults": round(mean(x[2] for x in sample), 3),
                    "mean_fault_reduction": round(mean(diffs), 3),
                    "mean_percent_reduction": round(mean(pcts), 3),
                    "percent_reduction_sd": round(sd_pct, 3),
                    "ci95_low_normal_approx": round(mean(pcts)-half, 3),
                    "ci95_high_normal_approx": round(mean(pcts)+half, 3),
                })
    paired_path = Path(a.paired_output); paired_path.parent.mkdir(parents=True, exist_ok=True)
    with paired_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(paired_rows[0])); w.writeheader(); w.writerows(paired_rows)
    print(f"Saved {len(paired_rows)} paired effect summaries to {paired_path.resolve()}")

if __name__ == "__main__": main()
