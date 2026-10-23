# Predictive and Adaptive Virtual Memory Management with Intelligent Thrashing Prevention

An educational operating-systems simulator built with Python, Tkinter, and Matplotlib. It models virtual address translation, TLB caching, two-level page tables, page replacement, working-set demand, thrashing detection, and adaptive memory-management actions.

**Safety and scope:** this project is a standalone simulation. It does not inspect or modify macOS/Windows/Linux kernel memory, real page tables, CPU utilization, or running processes. Any CPU-utilization, pressure, suspension, and intervention values shown by the dashboard are simulated values.

## Features

- 256-byte pages and 64 virtual pages per process, represented with a two-level page table (8 entries per level).
- TLB with LRU behavior; compare enabled and disabled translation caching.
- FIFO, LRU, Clock, and Optimal replacement policies.
- Five repeatable workload patterns: \`phase_locality\`, \`uniform_random\`, \`sequential_scan\`, \`bursty_hotset\`, and \`alternating_hotsets\`.
- Working-set estimation based on the recent reference window and a trend-based pressure forecast.
- Thrashing detection using rolling page-fault rate and estimated working-set demand.
- Adaptive frame redistribution and temporary process suspension; benchmark switches let each mechanism be measured independently.
- Tkinter dashboard with process/frame tables, an address translation inspector, event log, fault-rate and pressure charts, and CSV history export.
- Reproducible multi-seed benchmark with run-level results, grouped summaries, paired ablation comparisons, and TLB validation.

## Requirements

- Python 3.11 or newer recommended
- Tkinter (usually bundled with a Tk-enabled Python distribution)
- Matplotlib

On macOS, verify Tkinter first:

\`\`\`bash
python3 -m tkinter
\`\`\`

A small Tk window should appear. If it does not, install/use a Python distribution with Tk support.

## Setup on macOS

\`\`\`bash
cd ~/Desktop/virtual_memory_simulator
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
\`\`\`

Change the first \`cd\` command if you extracted the folder somewhere else.

## GUI demonstration

1. Keep the defaults: 4 processes, 16 frames, LRU, TLB enabled, and adaptive control enabled.
2. Click **Run Batch** to advance the simulation, then **Run to End** to finish every process's reference stream.
3. Change FIFO / LRU / Clock / Optimal, click **Reset**, and rerun for a comparable demonstration.
4. Toggle **TLB enabled**, reset, and compare page-table access counts. The TLB should change translation-cache statistics, but it should not change page-fault counts when the workload and replacement policy are otherwise identical.
5. Toggle **Adaptive control**, reset, and compare the baseline with the combined intervention.
6. Use the read-only virtual-address inspector for a process and an address between 0 and 16383.
7. Click **Export CSV** to save the run's history.

## Tests

\`\`\`bash
python -m unittest discover -s tests -v
\`\`\`

The suite covers page-table behavior, TLB caching, replacement algorithms, frame-allocation invariants, address inspection, independent adaptive switches, and all five workload patterns.

## Expanded benchmark experiments

Run:

\`\`\`bash
python benchmark.py
\`\`\`

Default settings:

- 10 seeds: 42 through 51
- 5 workload patterns
- 4 replacement algorithms
- 4 adaptive modes: none, redistribution only, suspension only, and combined
- 4 processes, 16 frames, and 400 references per process (1,600 references per run)
- 800 main runs with TLB enabled, plus 200 paired baseline runs with TLB disabled
- **1,000 total run records**

The benchmark writes:

- \`benchmark_results.csv\` - row for every individual run
- \`benchmark_summary.csv\` - means, standard deviations, and approximate 95% confidence intervals
- \`benchmark_paired_summary.csv\` - each adaptive mode matched against its baseline on the same pattern, seed, and replacement policy

Example with a smaller custom run:

\`\`\`bash
python benchmark.py --seeds 42,43 --patterns phase_locality,uniform_random --length 200
\`\`\`

The five workload patterns are synthetic. The results demonstrate behavior in this simulator; they are not universal performance claims about real operating systems. \`Optimal\` can inspect the future sequence and is an oracle benchmark, not a realistic online policy.

## Experimental highlights

In the default 1,000-run experiment, the combined policy reduced pooled mean faults from 1,193.1 to 963.6 for LRU (19.2% by ratio of means; 22.3% mean paired reduction across runs). The improvement depended on workload: the sequential scan produced no reduction, while phase-locality and alternating-hotset workloads improved more. Frame redistribution alone slightly increased mean faults in this implementation, and suspension alone left page-fault counts unchanged because frames remain assigned to the suspended process in that isolated ablation. See [\`EXPERIMENT_RESULTS.md\`](EXPERIMENT_RESULTS.md) for methodology, tables, confidence intervals, and caveats.

## Submission files included in this folder

- [Expanded experiment methodology and results](EXPERIMENT_RESULTS.md)
- [Architecture Graphviz source](docs/architecture.dot)
- Benchmark figures: [overall ablation](docs/figures/overall_ablation_results.svg), [workload effects](docs/figures/lru_workload_effects.svg), [TLB effect](docs/figures/tlb_effect.svg)
- Run-level data: \`benchmark_results.csv\`; grouped results: \`benchmark_summary.csv\`; paired ablation data: \`benchmark_paired_summary.csv\`

## Project structure

\`\`\`text
virtual_memory_simulator/
├── main.py
├── requirements.txt
├── README.md
├── EXPERIMENT_RESULTS.md
├── benchmark.py
├── benchmark_results.csv
├── benchmark_summary.csv
├── benchmark_paired_summary.csv
├── vm_simulator/
│   ├── core.py
│   └── gui.py
├── tests/
└── docs/
    ├── architecture.dot
    ├── generate_figures.py
    └── figures/
\`\`\`
