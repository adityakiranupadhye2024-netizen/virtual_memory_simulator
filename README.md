# Predictive and Adaptive Virtual Memory Management with Intelligent Thrashing Prevention

A standalone educational OS-lab simulator built with Python, Tkinter, and Matplotlib. It simulates virtual address translation, page replacement, working-set pressure, and adaptive thrashing interventions. It does **not** inspect or modify macOS/Windows memory management.

## Features

- Virtual address translation through a TLB and two-level page table
- FIFO, LRU, Clock, and Optimal page-replacement policies
- Multiple synthetic processes and working-set estimates
- Frame allocation and adaptive frame redistribution
- Rule-based thrashing detection and simulated temporary process suspension
- GUI event log, address inspector, graphs, and CSV export
- Repeatable benchmark script and unit tests

## Requirements

- Python 3.11 or newer recommended
- Tkinter
- Matplotlib

On macOS, verify Tkinter first with `python3 -m tkinter`.

## Setup on macOS

```bash
cd ~/Desktop/virtual_memory_simulator
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Adjust the `cd` path if the project is stored elsewhere.

## Tests and experiments

Run the automated tests:

```bash
python -m unittest discover -s tests -v
```

Run the benchmark with the default configuration:

```bash
python benchmark.py
```

The default benchmark evaluates five seeds (42–46), four replacement algorithms, TLB enabled/disabled, and adaptive management enabled/disabled. This is 80 runs. To use different seeds or settings, run `python benchmark.py --help` and use only options supported by the checked-in script.

The checked-in sample data are generated from synthetic workloads; they are not measurements from a real operating system. The Optimal policy uses future references and is an oracle baseline, not a practical online policy.

## Project documentation

- [Benchmark results and interpretation](EXPERIMENT_RESULTS.md)
- [Architecture diagram (SVG)](docs/architecture_diagram.svg)
- [Architecture source (Graphviz DOT)](docs/architecture.dot)
- [GUI screenshots](docs/screenshots/)

## Limitations

- This is a simulator, not a kernel module or production memory manager.
- Workloads are synthetic and results depend on their seeds and configuration.
- The predictive pressure estimate is a rule-based heuristic, not a trained machine-learning model.
- Process suspension and CPU-utilization effects are simulated.
- Results from one workload should not be generalized to all applications or operating systems.
