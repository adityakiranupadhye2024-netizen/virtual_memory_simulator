# Expanded Benchmark Results and Interpretation

## 1. Experimental objective

The expanded experiment checks the behavior of the simulator under multiple memory-reference patterns and separates the impact of frame redistribution from temporary process suspension. A second paired experiment checks the effect of enabling the translation lookaside buffer (TLB).

## 2. Methodology

All runs use the same parameters unless the variable under test changes:

| Parameter | Setting |
|---|---|
| Processes | 4 |
| Physical frames | 16 |
| References per process | 400 |
| References per completed run | 1,600 |
| Page size | 256 bytes |
| Virtual pages per process | 64 |
| TLB capacity | 8 entries |
| Workload seeds | 42 through 51 (10 seeds) |
| Workload patterns | 5 |
| Replacement policies | FIFO, LRU, Clock, Optimal |

The main ablation uses TLB enabled and four control modes: **none**, **redistribution only**, **suspension only**, and **combined**. The design includes 10 seeds x 5 workload patterns x 4 replacement policies x 4 adaptive modes = 800 runs. A matched TLB check adds 200 no-adaptation baseline runs with TLB disabled, for 1,000 recorded runs in total.

Workload patterns:

| Pattern | Reference behavior represented |
|---|---|
| \`phase_locality\` | Mostly accesses a small region, then shifts to another region over phases. |
| \`uniform_random\` | Uniform random references over all 64 virtual pages. |
| \`sequential_scan\` | Repeated scans through all 64 pages in order. |
| \`bursty_hotset\` | Bursts over a small hot set mixed with occasional broad random accesses. |
| \`alternating_hotsets\` | Alternates between two disjoint 8-page regions. |

The same seed and pattern are used for matched comparisons. Each row in \`benchmark_results.csv\` is one run. \`benchmark_summary.csv\` groups results and includes sample standard deviations and a normal-approximation 95% interval. \`benchmark_paired_summary.csv\` calculates the difference against the baseline for the same pattern, seed, and policy. Confidence intervals are descriptive and approximate, not a substitute for broader validation on real workload traces.

## 3. Main ablation results

The table shows means across 50 matched pattern-seed combinations for each algorithm and adaptive mode. Each run completes 1,600 references.

| Policy | No adaptation | Redistribution only | Suspension only | Combined | Combined reduction by ratio of means |
|---|---:|---:|---:|---:|---:|
| FIFO | 1,199.8 | 1,206.7 | 1,199.8 | 965.8 | 19.5% |
| LRU | 1,193.1 | 1,201.9 | 1,193.1 | 963.6 | 19.2% |
| Clock | 1,197.5 | 1,205.5 | 1,197.5 | 964.2 | 19.5% |
| Optimal* | 953.4 | 974.2 | 953.4 | 843.6 | 11.5% |

\`Optimal*\` knows the future references generated for a process; it is included as an oracle comparison and is not an implementable online replacement policy.

For LRU, the paired analysis found an average per-run page-fault reduction of **22.3%** for the combined mode, with an approximate 95% normal interval of **18.6% to 26.0%** across the 50 pattern-seed pairs. This paired mean percentage differs from the 19.2% ratio-of-means calculation in the table because the two calculations aggregate percentages differently.

## 4. What the ablation reveals

- **Redistribution only:** mean faults increased slightly for all four algorithms in the pooled set. Changing allocation can evict pages and incur new faults; redistribution should not be assumed to improve every workload.
- **Suspension only:** page-fault totals are identical to the no-adaptation baseline in this model. In the isolated ablation, a suspended process keeps its frame allocation, so the other processes do not gain its frames. This result exposes a limitation of testing suspension without reclamation/reallocation.
- **Combined:** suspension and redistribution coordinate; the suspended process's frames can be reallocated to active processes. The combined mode lowered pooled mean faults for all four policies in this experiment.
- **Workload matters:** the policy is not universally effective. A repeated sequential scan generated 1,600 faults under LRU in every mode (one fault per reference), so the combined controller did not help that pattern.

## 5. LRU results by workload pattern

| Workload | Baseline mean faults | Combined mean faults | Reduction by ratio of means |
|---|---:|---:|---:|
| Phase locality | 1,026.1 | 676.3 | 34.1% |
| Uniform random | 1,498.3 | 1,272.7 | 15.1% |
| Sequential scan | 1,600.0 | 1,600.0 | 0.0% |
| Bursty hot set | 966.5 | 680.0 | 29.6% |
| Alternating hot sets | 874.5 | 589.2 | 32.6% |

The plot \`docs/figures/lru_workload_effects.png\` shows the percentage change for each ablation mode relative to baseline. A negative result means more faults than baseline.

## 6. TLB comparison

The paired baseline experiment has 200 TLB-on runs and 200 matched TLB-off runs (5 patterns x 10 seeds x 4 replacement policies). Mean page-table accesses per run were:

| Setting | Mean page-table accesses per run |
|---|---:|
| TLB enabled | 2,450.2 |
| TLB disabled | 2,856.6 |

The TLB-enabled run used **14.2% fewer simulated page-table accesses** on average. The mean TLB hit rate across the TLB-on baseline rows was 12.7%. The paired validation found **zero page-fault mismatches across all 200 pairs**, as expected: the TLB caches translations but does not change page residency or the replacement policy.

## 7. Interpretation and limitations

These experiments use synthetic traces, fixed frame capacity, and rule-based thresholds. The values are simulator outputs, not real operating-system measurements. The run-level and summary CSVs are included so the calculations can be inspected or reproduced with \`python benchmark.py\`.

The isolated suspension mode intentionally leaves frame ownership unchanged to separate it from redistribution. That is useful for ablation, but it does not represent a production OS reclaiming a suspended process's memory. CPU utilization shown by the GUI is a heuristic proxy, not sampled CPU usage. The pressure value is estimated from the working-set demand and frame capacity, not a host OS metric. Optimal replacement is an oracle because it uses future references.

For follow-up research, consider a reclamation-enabled suspension model, longer and externally collected workload traces, additional seeds, threshold sensitivity experiments, process completion-time metrics, and a statistical method planned before the experiment. Do not infer that the policy will reduce page faults on every workload from these results.
