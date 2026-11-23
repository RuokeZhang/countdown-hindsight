# Countdown run comparison

Validation = greedy success on the 512-problem val set. Training columns are means over steps center-4..center+5 (steps 1-10 for step 0), computed against the original target.

| step | run | val all | val 3 nums | val 4 nums | train format valid | too-many-lines fails / step | mixed groups |
|---|---|---|---|---|---|---|---|
| 0 | baseline | 9.0% | 16.0% | 2.0% | 67.9% | 41.1 | 27.7% |
| 0 | A_group_p1 | 9.0% | 16.0% | 2.0% | 63.9% | 57.8 | 29.4% |
| 0 | B_validbonus | 8.8% | 15.6% | 2.0% | 73.9% | 30.3 | 31.6% |
| 0 | C_group_p0.25 | 9.2% | 16.4% | 2.0% | 63.6% | 56.5 | 26.9% |
| 0 | D_per_sample_p0.25 | 9.6% | 16.8% | 2.3% | 69.2% | 43.4 | 32.5% |
| 0 | E_split_p0.25 | 9.4% | 16.4% | 2.3% | 68.6% | 42.5 | 26.9% |
| 50 | baseline | 20.9% | 35.5% | 6.2% | 75.1% | 75.7 | 28.0% |
| 50 | A_group_p1 | 16.8% | 28.1% | 5.5% | 84.1% | 56.5 | 9.7% |
| 50 | B_validbonus | 14.1% | 25.0% | 3.1% | 100.0% | 0.0 | 2.7% |
| 50 | C_group_p0.25 | 18.2% | 31.6% | 4.7% | 74.3% | 82.2 | 20.6% |
| 50 | D_per_sample_p0.25 | 17.6% | 31.2% | 3.9% | 99.5% | 0.8 | 14.4% |
| 50 | E_split_p0.25 | 20.5% | 35.2% | 5.9% | 97.6% | 5.1 | 31.1% |
| 100 | baseline | 26.8% | 44.5% | 9.0% | 69.6% | 109.4 | 13.6% |
| 100 | A_group_p1 | 23.2% | 39.8% | 6.6% | 76.4% | 94.0 | 11.4% |
| 100 | B_validbonus | 17.0% | 30.5% | 3.5% | 100.0% | 0.0 | 4.2% |
| 100 | C_group_p0.25 | — | — | — | — | — | — |
| 100 | D_per_sample_p0.25 | 27.7% | 45.3% | 10.2% | 100.0% | 0.2 | 8.1% |
| 100 | E_split_p0.25 | 32.2% | 52.0% | 12.5% | 98.7% | 2.9 | 25.6% |
| 150 | baseline | 34.0% | 55.1% | 12.9% | 45.8% | 166.4 | 7.8% |
| 150 | A_group_p1 | 28.7% | 48.8% | 8.6% | 67.0% | 100.9 | 4.2% |
| 150 | B_validbonus | 16.0% | 27.0% | 5.1% | 100.0% | 0.0 | 1.9% |
| 150 | C_group_p0.25 | — | — | — | — | — | — |
| 150 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 150 | E_split_p0.25 | 39.3% | 62.9% | 15.6% | 98.4% | 2.6 | 16.7% |
| 200 | baseline | 35.5% | 56.6% | 14.5% | 55.3% | 163.8 | 4.1% |
| 200 | A_group_p1 | 29.5% | 49.6% | 9.4% | 82.3% | 68.1 | 2.0% |
| 200 | B_validbonus | 15.0% | 25.4% | 4.7% | 100.0% | 0.2 | 2.0% |
| 200 | C_group_p0.25 | — | — | — | — | — | — |
| 200 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 200 | E_split_p0.25 | 44.5% | 69.5% | 19.5% | 99.8% | 0.2 | 12.2% |
| 250 | baseline | 38.9% | 61.7% | 16.0% | 68.8% | 134.4 | 2.7% |
| 250 | A_group_p1 | 31.4% | 53.1% | 9.8% | 70.8% | 114.2 | 3.4% |
| 250 | B_validbonus | 18.2% | 31.6% | 4.7% | 100.0% | 0.0 | 1.7% |
| 250 | C_group_p0.25 | — | — | — | — | — | — |
| 250 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 250 | E_split_p0.25 | 47.1% | 73.8% | 20.3% | 99.8% | 0.1 | 8.3% |
| 300 | baseline | 38.5% | 59.8% | 17.2% | 45.2% | 219.6 | 2.0% |
| 300 | A_group_p1 | 36.5% | 60.2% | 12.9% | 51.0% | 136.4 | 3.1% |
| 300 | B_validbonus | 17.0% | 28.5% | 5.5% | 100.0% | 0.0 | 1.9% |
| 300 | C_group_p0.25 | — | — | — | — | — | — |
| 300 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 300 | E_split_p0.25 | 47.5% | 74.6% | 20.3% | 99.6% | 0.2 | 6.2% |

## Degeneration signals

Same windows as above. "fail claims target" = share of failed responses whose last line ends in "= <original target>". Hindsight positives/negatives per step: per-sample runs count the samples normalized together in the step's new uid; group runs count reward-1 / reward-0 samples inside rewritten groups.

| step | run | entropy | mixed groups | train fail claims target | val fail claims target | hindsight positives / step | hindsight negatives / step |
|---|---|---|---|---|---|---|---|
| 0 | baseline | 0.236 | 27.7% | 37.5% | 32.0% | 0.0 | 0.0 |
| 0 | A_group_p1 | 0.234 | 29.4% | 46.8% | 33.0% | 23.9 | 92.9 |
| 0 | B_validbonus | 0.213 | 31.6% | 25.3% | 32.5% | 0.0 | 0.0 |
| 0 | C_group_p0.25 | 0.243 | 26.9% | 40.8% | 32.7% | 8.4 | 32.4 |
| 0 | D_per_sample_p0.25 | 0.229 | 32.5% | 34.0% | 32.0% | 12.2 | 66.3 |
| 0 | E_split_p0.25 | 0.237 | 26.9% | 36.2% | 33.4% | 7.4 | 77.4 |
| 25 | baseline | 0.117 | 32.2% | 31.7% | — | 0.0 | 0.0 |
| 25 | A_group_p1 | 0.039 | 12.2% | 98.3% | — | 0.0 | 0.0 |
| 25 | B_validbonus | 0.009 | 4.4% | 0.1% | — | 0.0 | 0.0 |
| 25 | C_group_p0.25 | 0.054 | 14.1% | 91.3% | — | 0.8 | 1.6 |
| 25 | D_per_sample_p0.25 | 0.041 | 19.1% | 4.3% | — | 53.8 | 9.9 |
| 25 | E_split_p0.25 | 0.100 | 39.5% | 7.4% | — | 20.5 | 35.8 |
| 50 | baseline | 0.083 | 28.0% | 25.3% | 26.4% | 0.0 | 0.0 |
| 50 | A_group_p1 | 0.032 | 9.7% | 96.8% | 97.9% | 0.0 | 0.0 |
| 50 | B_validbonus | 0.004 | 2.7% | 0.0% | 0.0% | 0.0 | 0.0 |
| 50 | C_group_p0.25 | 0.060 | 20.6% | 87.3% | 87.8% | 0.0 | 0.0 |
| 50 | D_per_sample_p0.25 | 0.019 | 14.4% | 0.3% | 0.2% | 53.9 | 3.8 |
| 50 | E_split_p0.25 | 0.058 | 31.1% | 2.3% | 2.0% | 22.9 | 30.7 |
| 100 | baseline | 0.051 | 13.6% | 28.1% | 25.9% | 0.0 | 0.0 |
| 100 | A_group_p1 | 0.028 | 11.4% | 94.8% | 94.4% | 0.0 | 0.0 |
| 100 | B_validbonus | 0.006 | 4.2% | 0.0% | 0.0% | 0.0 | 0.0 |
| 100 | C_group_p0.25 | — | — | — | — | — | — |
| 100 | D_per_sample_p0.25 | 0.013 | 8.1% | 0.0% | 0.3% | 72.0 | 2.6 |
| 100 | E_split_p0.25 | 0.044 | 25.6% | 0.5% | 0.3% | 26.9 | 27.8 |
| 150 | baseline | 0.052 | 7.8% | 55.3% | 55.9% | 0.0 | 0.0 |
| 150 | A_group_p1 | 0.027 | 4.2% | 79.6% | 81.4% | 0.4 | 1.2 |
| 150 | B_validbonus | 0.004 | 1.9% | 0.0% | 0.0% | 0.0 | 0.0 |
| 150 | C_group_p0.25 | — | — | — | — | — | — |
| 150 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 150 | E_split_p0.25 | 0.029 | 16.7% | 0.9% | 2.3% | 29.5 | 33.8 |
| 200 | baseline | 0.036 | 4.1% | 69.2% | 69.1% | 0.0 | 0.0 |
| 200 | A_group_p1 | 0.008 | 2.0% | 96.3% | 96.1% | 0.6 | 0.2 |
| 200 | B_validbonus | 0.003 | 2.0% | 0.1% | 0.0% | 0.0 | 0.0 |
| 200 | C_group_p0.25 | — | — | — | — | — | — |
| 200 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 200 | E_split_p0.25 | 0.018 | 12.2% | 0.4% | 0.0% | 17.2 | 24.6 |
| 250 | baseline | 0.023 | 2.7% | 86.1% | 85.9% | 0.0 | 0.0 |
| 250 | A_group_p1 | 0.017 | 3.4% | 88.0% | 86.6% | 1.1 | 1.3 |
| 250 | B_validbonus | 0.002 | 1.7% | 0.0% | 0.0% | 0.0 | 0.0 |
| 250 | C_group_p0.25 | — | — | — | — | — | — |
| 250 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 250 | E_split_p0.25 | 0.011 | 8.3% | 0.2% | 0.4% | 29.4 | 27.1 |
| 300 | baseline | 0.032 | 2.0% | 68.1% | 66.3% | 0.0 | 0.0 |
| 300 | A_group_p1 | 0.026 | 3.1% | 50.2% | 56.6% | 0.0 | 0.0 |
| 300 | B_validbonus | 0.002 | 1.9% | 0.0% | 0.0% | 0.0 | 0.0 |
| 300 | C_group_p0.25 | — | — | — | — | — | — |
| 300 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 300 | E_split_p0.25 | 0.011 | 6.2% | 0.1% | 0.7% | 24.6 | 26.8 |

## Validation across seeds

Mean over the seeds that have reached the step; per-seed values in seed order (— = not reached yet).

| step | arm | seeds | mean all | mean 3 nums | mean 4 nums | per-seed all |
|---|---|---|---|---|---|---|
| 0 | baseline | 1 | 9.0% | 16.0% | 2.0% | 9.0%, —, — |
| 0 | E | 1 | 9.4% | 16.4% | 2.3% | 9.4%, —, — |
| 50 | baseline | 1 | 20.9% | 35.5% | 6.2% | 20.9%, —, — |
| 50 | E | 1 | 20.5% | 35.2% | 5.9% | 20.5%, —, — |
| 100 | baseline | 1 | 26.8% | 44.5% | 9.0% | 26.8%, —, — |
| 100 | E | 1 | 32.2% | 52.0% | 12.5% | 32.2%, —, — |
| 150 | baseline | 1 | 34.0% | 55.1% | 12.9% | 34.0%, —, — |
| 150 | E | 1 | 39.3% | 62.9% | 15.6% | 39.3%, —, — |
| 200 | baseline | 1 | 35.5% | 56.6% | 14.5% | 35.5%, —, — |
| 200 | E | 1 | 44.5% | 69.5% | 19.5% | 44.5%, —, — |
| 250 | baseline | 1 | 38.9% | 61.7% | 16.0% | 38.9%, —, — |
| 250 | E | 1 | 47.1% | 73.8% | 20.3% | 47.1%, —, — |
| 300 | baseline | 1 | 38.5% | 59.8% | 17.2% | 38.5%, —, — |
| 300 | E | 1 | 47.5% | 74.6% | 20.3% | 47.5%, —, — |

## Problem-by-problem validation: E vs baseline (same seed)

Counts over the 512 validation problems. only E = E solves it and baseline does not.

| step | seed | only E | only baseline | both | neither |
|---|---|---|---|---|---|
| 100 | 0 | 53 | 25 | 112 | 322 |
| 150 | 0 | 51 | 24 | 150 | 287 |
| 200 | 0 | 63 | 17 | 165 | 267 |
| 250 | 0 | 51 | 9 | 190 | 262 |
| 300 | 0 | 57 | 11 | 186 | 258 |

## Per-sample-split runs: pooled samples per step by class

Window means as above. negative_valid = valid relabel candidate kept on its original prompt with reward 0.

| step | run | positive | negative_valid | negative_parse | negative_arithmetic | negative_usage |
|---|---|---|---|---|---|---|
| 0 | E_split_p0.25 | 7.4 | 6.8 | 35.2 | 26.3 | 9.1 |
| 25 | E_split_p0.25 | 20.5 | 15.6 | 10.6 | 5.6 | 4.0 |
| 50 | E_split_p0.25 | 22.9 | 22.7 | 2.6 | 3.7 | 1.7 |
| 100 | E_split_p0.25 | 26.9 | 24.7 | 1.0 | 1.1 | 1.0 |
| 150 | E_split_p0.25 | 29.5 | 30.2 | 0.8 | 0.0 | 2.8 |
| 200 | E_split_p0.25 | 17.2 | 20.4 | 0.2 | 1.4 | 2.6 |
| 250 | E_split_p0.25 | 29.4 | 26.1 | 0.2 | 0.0 | 0.8 |
| 300 | E_split_p0.25 | 24.6 | 26.8 | 0.0 | 0.0 | 0.0 |

## Hindsight log-prob diagnostic (D_per_sample_p0.25): logp_new - logp_orig (sum over response tokens)

Per-step summaries averaged over the steps in each interval (steps with no relabeled sample of a kind are skipped); counts are totals.

| steps | diff mean (new-target success) | diff median (success) | diff mean (new-target fail) | diff median (fail) | share \|diff\| < 0.05 | success samples | fail samples |
|---|---|---|---|---|---|---|---|
| 1-25 | -0.015 | 0.100 | — | — | 7.4% | 705.0 | 0.0 |
| 26-50 | -0.847 | -0.248 | — | — | 37.1% | 1257.0 | 0.0 |
| 51-100 | -0.788 | -0.120 | — | — | 39.8% | 3013.0 | 0.0 |
| 101-200 | — | — | — | — | — | 0 | 0 |
| 201-300 | — | — | — | — | — | 0 | 0 |

## Hindsight log-prob diagnostic (E_split_p0.25): logp_new - logp_orig (sum over response tokens)

Per-step summaries averaged over the steps in each interval (steps with no relabeled sample of a kind are skipped); counts are totals.

| steps | diff mean (new-target success) | diff median (success) | diff mean (new-target fail) | diff median (fail) | share \|diff\| < 0.05 | success samples | fail samples |
|---|---|---|---|---|---|---|---|
| 1-25 | -0.055 | -0.044 | — | — | 7.9% | 290.0 | 0.0 |
| 26-50 | -0.239 | 0.047 | — | — | 15.6% | 512.0 | 0.0 |
| 51-100 | -0.580 | -0.133 | — | — | 25.2% | 1382.0 | 0.0 |
| 101-200 | -0.711 | -0.142 | — | — | 31.5% | 2593.0 | 0.0 |
| 201-300 | -0.451 | -0.010 | — | — | 50.7% | 2543.0 | 0.0 |
