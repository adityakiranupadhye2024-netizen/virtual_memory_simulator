# Predictive and Adaptive Virtual Memory Management with Intelligent Thrashing Prevention

A standalone operating-system laboratory simulator built with Python, Tkinter, and Matplotlib. It runs on macOS and Windows and **does not modify or inspect the host operating system's real memory management**.

## Features

- Virtual address → TLB → two-level page table → physical frame translation
- 256-byte pages and 64 virtual pages (two page-table levels with 8 entries per level)
- Read-only virtual-address inspector showing VPN, offset, L1/L2 indices, translation source, and physical address when resident
- TLB enabled/disabled comparison, hit-rate accounting, and page-table-walk measurement
- FIFO, LRU, Clock, and Optimal page replacement
- Multiple synthetic processes with locality-based reference streams
- Per-process frame allocation, page-fault statistics, working-set estimates, and frame table
- Dynamic frame redistribution based on working-set demand
- Predictive pressure estimate based on recent working-set trends
- Thrashing detection using recent page-fault frequency and working-set pressure
- Adaptive demonstration response: frame redistribution and temporary process suspension
- Performance plots, event log, CSV history export, and multi-seed benchmark script

**Interpretation note:** CPU utilization is a simulated proxy for useful work under page-fault overhead. Memory pressure is estimated from working-set demand and frame capacity. Neither value is a live reading from macOS/Windows. The Optimal policy uses future references from the generated sequence and is included as a theoretical benchmark, not as a practical online policy.

## Requirements

- Python 3.11 or newer recommended
- Tkinter
- Matplotlib

On macOS, use a Python distribution that includes Tkinter. If `python3 -m tkinter` fails, the python.org macOS installer is a reliable option for getting a Tk-enabled Python installation.

## Setup on macOS

Open Terminal and navigate to the folder where you extracted this project. If it is on your Desktop:

```bash
cd ~/Desktop/virtual_memory_simulator
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

To check Tkinter before installing dependencies:

```bash
python3 -m tkinter
```

A small Tk demo window should appear. Close it to continue. If the project folder is somewhere else, change the first `cd` command to match that location.

## First GUI demonstration

1. Keep the defaults: 4 processes, 16 physical frames, LRU, TLB ON, and Adaptive control ON.
2. Click **Run Batch** to watch the counters, per-process table, physical-frame table, event log, and graphs update.
3. Click **Run to End** to finish all generated memory-reference streams.
4. Change the replacement algorithm to FIFO, Clock, or Optimal, click **Reset**, and run again for a comparable experiment.
5. Turn **TLB enabled** off, click **Reset**, and compare TLB statistics and page-table accesses. Page faults should remain the same for the same policy, seed, and workload.
6. Turn **Adaptive control** off, click **Reset**, and compare the baseline run with adaptive control enabled.
7. Use **Virtual Address Translation Inspector** to inspect a process and a virtual address between 0 and 16383. It is read-only and does not change simulation counters. If the page is not resident, it reports that a page fault would be required.
8. Use **Export CSV** to save history for reports.

## Run tests

With the virtual environment active:

```bash
python -m unittest discover -s tests -v
```

## Run benchmark experiments

```bash
python benchmark.py
```

By default, the benchmark runs 5 seeds × 4 replacement algorithms × 2 TLB settings × 2 adaptive settings (80 runs) and writes `benchmark_results.csv`. Example with different parameters:

```bash
python benchmark.py --seeds 10,11,12 --frames 24 --processes 4 --length 600
```

Keep seeds and workload parameters identical when comparing policies. The sample results and interpretation are documented in [`EXPERIMENT_RESULTS.md`](EXPERIMENT_RESULTS.md). They are synthetic simulator results, not claims about behavior on a real operating system.

## Git/GitHub setup

From the project folder:

```bash
git init
git add .
git commit -m "Build virtual memory simulator MVP"
```

Create an empty repository on GitHub, then use GitHub's displayed instructions to add the remote and push your branch. Do not commit `.venv/`.

## Implementation stages

1. **Core simulation:** address translation, TLB, multi-level page table, page faults, replacement algorithms, and baseline statistics.
2. **Memory analysis:** working sets, per-process statistics, graphs, event log, and CSV export.
3. **Adaptive management:** frame redistribution, pressure forecasting, thrashing detection, and process suspension.
4. **Benchmarking:** controlled seeds, algorithm comparisons, TLB on/off comparisons, and adaptive on/off comparisons.
5. **Recommended extensions:** more workload patterns, more seeds, confidence intervals, configurable thresholds, and ablation experiments to isolate the effects of each adaptive intervention.

## Project structure

```text
virtual_memory_simulator/
├── main.py
├── requirements.txt
├── README.md
├── EXPERIMENT_RESULTS.md
├── benchmark.py
├── benchmark_results.csv
├── vm_simulator/
│   ├── __init__.py
│   ├── core.py       # simulation, address translation, policies, adaptation
│   └── gui.py        # Tkinter interface, plots, event log, CSV export
└── tests/
    └── test_core.py
```
