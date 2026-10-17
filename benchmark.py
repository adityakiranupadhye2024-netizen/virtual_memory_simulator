"""Run repeatable virtual-memory policy experiments and export per-run CSV data."""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev

from vm_simulator.core import MemorySimulator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seeds",
        default="42,43,44,45,46",
        help="Comma-separated workload seeds (default: 42,43,44,45,46).",
    )
    parser.add_argument("--frames", type=int, default=16, help="Number of physical frames (default: 16).")
    parser.add_argument("--processes", type=int, default=4, help="Number of processes (default: 4).")
    parser.add_argument("--length", type=int, default=400, help="References per process (default: 400).")
    parser.add_argument(
        "--output", default="benchmark_results.csv", help="Output CSV path (default: benchmark_results.csv)."
    )
    args = parser.parse_args()
    try:
        args.seeds = [int(piece.strip()) for piece in args.seeds.split(",") if piece.strip()]
    except ValueError as exc:
        parser.error(f"Seeds must be comma-separated integers: {exc}")
    if not args.seeds:
        parser.error("Provide at least one seed.")
    if args.frames < args.processes or args.processes < 1 or args.frames < 2:
        parser.error("Frames must be at least 2 and at least the number of processes.")
    if args.length < 1:
        parser.error("Length must be at least 1.")
    return args


def main() -> None:
    args = parse_args()
    output_path = Path(args.output)
    rows: list[dict] = []

    for seed in args.seeds:
        for algorithm in MemorySimulator.ALGORITHMS:
            for tlb_enabled in (True, False):
                for adaptive_enabled in (False, True):
                    sim = MemorySimulator(
                        total_frames=args.frames,
                        num_processes=args.processes,
                        algorithm=algorithm,
                        tlb_enabled=tlb_enabled,
                        adaptive_enabled=adaptive_enabled,
                        sequence_length=args.length,
                        seed=seed,
                    )
                    sim.run_to_completion()
                    metrics = sim.metrics()
                    rows.append({
                        "algorithm": algorithm,
                        "tlb_enabled": tlb_enabled,
                        "adaptive_enabled": adaptive_enabled,
                        "processes": len(sim.processes),
                        "physical_frames": sim.total_frames,
                        "references_per_process": args.length,
                        "references": sim.references,
                        "page_faults": sim.page_faults,
                        "overall_page_fault_rate": round(sim.overall_page_fault_rate, 5),
                        "replacements": sim.replacements,
                        "tlb_hits": sim.tlb.hits,
                        "tlb_misses": sim.tlb.misses,
                        "tlb_hit_rate": "" if metrics["tlb_hit_rate"] is None else round(metrics["tlb_hit_rate"], 5),
                        "page_table_accesses": sim.page_table_accesses,
                        "thrashing_detections": sim.thrashing_detections,
                        "adaptive_actions": sim.adaptive_actions,
                        "process_suspensions": sim.process_suspensions,
                        "max_memory_pressure_percent": max(
                            (h["memory_pressure_percent"] for h in sim.history), default=0
                        ),
                        "final_status": metrics["status"],
                        "seed": seed,
                    })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    grouped: dict[tuple[str, bool], list[dict]] = defaultdict(list)
    for row in rows:
        # The page-fault-policy summary uses TLB ON, retaining TLB OFF data in CSV
        # for the separate translation-overhead experiment.
        if row["tlb_enabled"]:
            grouped[(row["algorithm"], row["adaptive_enabled"])].append(row)

    print(f"Saved {len(rows)} controlled runs to {output_path.resolve()}")
    print(f"Seeds: {', '.join(map(str, args.seeds))}; processes: {args.processes}; frames: {args.frames}; refs/process: {args.length}")
    print("Algorithm | Adaptive | Mean faults | Fault rate | Mean replacements | Mean suspensions")
    for algorithm in MemorySimulator.ALGORITHMS:
        for adaptive_enabled in (False, True):
            sample = grouped[(algorithm, adaptive_enabled)]
            print(
                f"{algorithm:8} | {str(adaptive_enabled):8} | "
                f"{mean(float(r['page_faults']) for r in sample):11.1f} | "
                f"{mean(float(r['overall_page_fault_rate']) for r in sample):9.1%} | "
                f"{mean(float(r['replacements']) for r in sample):16.1f} | "
                f"{mean(float(r['process_suspensions']) for r in sample):16.1f}"
            )

    # Display variability to discourage over-interpreting a single workload trace.
    print("\nPage-fault standard deviation across seeds (TLB ON):")
    for algorithm in MemorySimulator.ALGORITHMS:
        for adaptive_enabled in (False, True):
            sample = grouped[(algorithm, adaptive_enabled)]
            faults = [float(r["page_faults"]) for r in sample]
            print(f"  {algorithm:8} adaptive={str(adaptive_enabled):5}: {pstdev(faults):.1f}")


if __name__ == "__main__":
    main()
