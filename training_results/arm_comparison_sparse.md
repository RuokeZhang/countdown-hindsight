# Countdown run comparison

Validation = greedy success on the 512-problem val set. Training columns are means over steps center-4..center+5 (steps 1-10 for step 0), computed against the original target.

| step | run | val all | val 3 nums | val 4 nums | train format valid | too-many-lines fails / step | mixed groups |
|---|---|---|---|---|---|---|---|
| 0 | baseline_n5_s0 | 0.0% | — | — | 39.2% | 53.6 | 2.2% |
| 0 | E_split_p1_n5_s0 | 0.2% | — | — | 45.6% | 56.3 | 2.5% |
| 25 | baseline_n5_s0 | 1.4% | — | — | 56.9% | 89.1 | 2.5% |
| 25 | E_split_p1_n5_s0 | 1.8% | — | — | 97.8% | 4.4 | 1.7% |
| 50 | baseline_n5_s0 | 1.4% | — | — | 40.7% | 153.5 | 2.7% |
| 50 | E_split_p1_n5_s0 | 1.8% | — | — | 99.2% | 2.5 | 2.8% |
| 75 | baseline_n5_s0 | 1.4% | — | — | 19.5% | 188.5 | 3.4% |
| 75 | E_split_p1_n5_s0 | 1.8% | — | — | 99.6% | 1.1 | 3.4% |
| 100 | baseline_n5_s0 | 1.4% | — | — | 9.1% | 197.6 | 5.6% |
| 100 | E_split_p1_n5_s0 | 2.3% | — | — | 99.8% | 0.2 | 3.8% |
| 125 | baseline_n5_s0 | — | — | — | — | — | — |
| 125 | E_split_p1_n5_s0 | — | — | — | — | — | — |
| 150 | baseline_n5_s0 | — | — | — | — | — | — |
| 150 | E_split_p1_n5_s0 | — | — | — | — | — | — |
| 175 | baseline_n5_s0 | — | — | — | — | — | — |
| 175 | E_split_p1_n5_s0 | — | — | — | — | — | — |
| 200 | baseline_n5_s0 | — | — | — | — | — | — |
| 200 | E_split_p1_n5_s0 | — | — | — | — | — | — |
| 225 | baseline_n5_s0 | — | — | — | — | — | — |
| 225 | E_split_p1_n5_s0 | — | — | — | — | — | — |
| 250 | baseline_n5_s0 | — | — | — | — | — | — |
| 250 | E_split_p1_n5_s0 | — | — | — | — | — | — |
| 275 | baseline_n5_s0 | — | — | — | — | — | — |
| 275 | E_split_p1_n5_s0 | — | — | — | — | — | — |
| 300 | baseline_n5_s0 | — | — | — | — | — | — |
| 300 | E_split_p1_n5_s0 | — | — | — | — | — | — |

## Degeneration signals

Same windows as above. "fail claims target" = share of failed responses whose last line ends in "= <original target>". Hindsight positives/negatives per step: per-sample runs count the samples normalized together in the step's new uid; group runs count reward-1 / reward-0 samples inside rewritten groups.

| step | run | entropy | mixed groups | train fail claims target | val fail claims target | hindsight positives / step | hindsight negatives / step |
|---|---|---|---|---|---|---|---|
| 0 | baseline_n5_s0 | 0.280 | 2.2% | 25.5% | 17.6% | 0.0 | 0.0 |
| 0 | E_split_p1_n5_s0 | 0.258 | 2.5% | 25.5% | 18.8% | 21.8 | 440.2 |
| 25 | baseline_n5_s0 | 0.155 | 2.5% | 23.7% | 16.8% | 0.0 | 0.0 |
| 25 | E_split_p1_n5_s0 | 0.031 | 1.7% | 0.9% | 0.4% | 125.4 | 187.9 |
| 50 | baseline_n5_s0 | 0.144 | 2.7% | 21.3% | 15.8% | 0.0 | 0.0 |
| 50 | E_split_p1_n5_s0 | 0.030 | 2.8% | 0.1% | 0.0% | 124.5 | 147.2 |
| 100 | baseline_n5_s0 | 0.131 | 5.6% | 21.8% | 19.8% | 0.0 | 0.0 |
| 100 | E_split_p1_n5_s0 | 0.032 | 3.8% | 0.0% | 0.0% | 135.0 | 159.8 |
| 150 | baseline_n5_s0 | — | — | — | — | — | — |
| 150 | E_split_p1_n5_s0 | — | — | — | — | — | — |
| 200 | baseline_n5_s0 | — | — | — | — | — | — |
| 200 | E_split_p1_n5_s0 | — | — | — | — | — | — |
| 250 | baseline_n5_s0 | — | — | — | — | — | — |
| 250 | E_split_p1_n5_s0 | — | — | — | — | — | — |
| 300 | baseline_n5_s0 | — | — | — | — | — | — |
| 300 | E_split_p1_n5_s0 | — | — | — | — | — | — |

## Validation across seeds

Mean over the seeds that have reached the step; per-seed values in seed order (— = not reached yet).

| step | arm | seeds | mean all | mean 3 nums | mean 4 nums | per-seed all |
|---|---|---|---|---|---|---|
| 0 | baseline_n5 | 1 | 0.0% | — | — | 0.0% |
| 0 | E_split_p1_n5 | 1 | 0.2% | — | — | 0.2% |
| 25 | baseline_n5 | 1 | 1.4% | — | — | 1.4% |
| 25 | E_split_p1_n5 | 1 | 1.8% | — | — | 1.8% |
| 50 | baseline_n5 | 1 | 1.4% | — | — | 1.4% |
| 50 | E_split_p1_n5 | 1 | 1.8% | — | — | 1.8% |
| 75 | baseline_n5 | 1 | 1.4% | — | — | 1.4% |
| 75 | E_split_p1_n5 | 1 | 1.8% | — | — | 1.8% |
| 100 | baseline_n5 | 1 | 1.4% | — | — | 1.4% |
| 100 | E_split_p1_n5 | 1 | 2.3% | — | — | 2.3% |
| 125 | baseline_n5 | 0 | — | — | — | — |
| 125 | E_split_p1_n5 | 0 | — | — | — | — |
| 150 | baseline_n5 | 0 | — | — | — | — |
| 150 | E_split_p1_n5 | 0 | — | — | — | — |
| 175 | baseline_n5 | 0 | — | — | — | — |
| 175 | E_split_p1_n5 | 0 | — | — | — | — |
| 200 | baseline_n5 | 0 | — | — | — | — |
| 200 | E_split_p1_n5 | 0 | — | — | — | — |
| 225 | baseline_n5 | 0 | — | — | — | — |
| 225 | E_split_p1_n5 | 0 | — | — | — | — |
| 250 | baseline_n5 | 0 | — | — | — | — |
| 250 | E_split_p1_n5 | 0 | — | — | — | — |
| 275 | baseline_n5 | 0 | — | — | — | — |
| 275 | E_split_p1_n5 | 0 | — | — | — | — |
| 300 | baseline_n5 | 0 | — | — | — | — |
| 300 | E_split_p1_n5 | 0 | — | — | — | — |

## Problem-by-problem validation: E_split_p1_n5 vs baseline_n5 (same seed)

Counts over the 512 validation problems. only E_split_p1_n5 = E_split_p1_n5 solves it and baseline_n5 does not.

| step | seed | only E_split_p1_n5 | only baseline_n5 | both | neither |
|---|---|---|---|---|---|
| 100 | 0 | 8 | 3 | 4 | 497 |

## First validation step reaching a success level

Earliest validated step whose greedy val success is at least the level (— = never reached among the validated steps).

| run | last validated step | first step >= 5% | first step >= 10% | first step >= 20% |
|---|---|---|---|---|
| baseline_n5_s0 | 100 | — | — | — |
| E_split_p1_n5_s0 | 100 | — | — | — |

## First 100 steps: mixed groups and hindsight samples

Means over every training step in the interval. Hindsight positives/negatives per step as in the degeneration table.

| steps | run | mixed groups | hindsight positives / step | hindsight negatives / step |
|---|---|---|---|---|
| 1-25 | baseline_n5_s0 | 2.2% | 0.0 | 0.0 |
| 1-25 | E_split_p1_n5_s0 | 2.7% | 61.7 | 331.8 |
| 26-50 | baseline_n5_s0 | 3.8% | 0.0 | 0.0 |
| 26-50 | E_split_p1_n5_s0 | 2.6% | 129.2 | 160.8 |
| 51-75 | baseline_n5_s0 | 3.2% | 0.0 | 0.0 |
| 51-75 | E_split_p1_n5_s0 | 3.5% | 131.2 | 146.5 |
| 76-100 | baseline_n5_s0 | 3.8% | 0.0 | 0.0 |
| 76-100 | E_split_p1_n5_s0 | 3.4% | 139.6 | 155.2 |

## Per-sample-split runs: pooled samples per step by class

Window means as above. negative_valid = valid relabel candidate kept on its original prompt with reward 0.

| step | run | positive | negative_valid | negative_parse | negative_arithmetic | negative_usage |
|---|---|---|---|---|---|---|
| 0 | E_split_p1_n5_s0 | 21.8 | 24.1 | 272.2 | 89.0 | 54.9 |
| 25 | E_split_p1_n5_s0 | 125.4 | 123.5 | 11.2 | 48.8 | 4.4 |
| 50 | E_split_p1_n5_s0 | 124.5 | 124.3 | 4.1 | 16.1 | 2.7 |
| 100 | E_split_p1_n5_s0 | 135.0 | 149.6 | 0.8 | 6.6 | 2.8 |
| 150 | E_split_p1_n5_s0 | — | — | — | — | — |
| 200 | E_split_p1_n5_s0 | — | — | — | — | — |
| 250 | E_split_p1_n5_s0 | — | — | — | — | — |
| 300 | E_split_p1_n5_s0 | — | — | — | — | — |
