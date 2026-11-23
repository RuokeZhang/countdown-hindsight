# Countdown run comparison

Validation = greedy success on the 512-problem val set. Training columns are means over steps center-4..center+5 (steps 1-10 for step 0), computed against the original target.

| step | run | val all | val 3 nums | val 4 nums | train format valid | too-many-lines fails / step | mixed groups |
|---|---|---|---|---|---|---|---|
| 0 | baseline | 9.0% | 16.0% | 2.0% | 67.9% | 41.1 | 27.7% |
| 0 | A_group_p1 | 9.0% | 16.0% | 2.0% | 63.9% | 57.8 | 29.4% |
| 0 | B_validbonus | 8.8% | 15.6% | 2.0% | 73.9% | 30.3 | 31.6% |
| 0 | C_group_p0.25 | 9.2% | 16.4% | 2.0% | 63.6% | 56.5 | 26.9% |
| 0 | D_per_sample_p0.25 | 9.6% | 16.8% | 2.3% | 69.2% | 43.4 | 32.5% |
| 50 | baseline | 20.9% | 35.5% | 6.2% | 75.1% | 75.7 | 28.0% |
| 50 | A_group_p1 | 16.8% | 28.1% | 5.5% | 84.1% | 56.5 | 9.7% |
| 50 | B_validbonus | 14.1% | 25.0% | 3.1% | 100.0% | 0.0 | 2.7% |
| 50 | C_group_p0.25 | 18.2% | 31.6% | 4.7% | 74.3% | 82.2 | 20.6% |
| 50 | D_per_sample_p0.25 | 17.6% | 31.2% | 3.9% | 99.5% | 0.8 | 14.4% |
| 100 | baseline | 26.8% | 44.5% | 9.0% | 69.6% | 109.4 | 13.6% |
| 100 | A_group_p1 | 23.2% | 39.8% | 6.6% | 76.4% | 94.0 | 11.4% |
| 100 | B_validbonus | 17.0% | 30.5% | 3.5% | 100.0% | 0.0 | 4.2% |
| 100 | C_group_p0.25 | — | — | — | — | — | — |
| 100 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 150 | baseline | 34.0% | 55.1% | 12.9% | 45.8% | 166.4 | 7.8% |
| 150 | A_group_p1 | 28.7% | 48.8% | 8.6% | 67.0% | 100.9 | 4.2% |
| 150 | B_validbonus | 16.0% | 27.0% | 5.1% | 100.0% | 0.0 | 1.9% |
| 150 | C_group_p0.25 | — | — | — | — | — | — |
| 150 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 200 | baseline | 35.5% | 56.6% | 14.5% | 55.3% | 163.8 | 4.1% |
| 200 | A_group_p1 | 29.5% | 49.6% | 9.4% | 82.3% | 68.1 | 2.0% |
| 200 | B_validbonus | 15.0% | 25.4% | 4.7% | 100.0% | 0.2 | 2.0% |
| 200 | C_group_p0.25 | — | — | — | — | — | — |
| 200 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 250 | baseline | 38.9% | 61.7% | 16.0% | 68.8% | 134.4 | 2.7% |
| 250 | A_group_p1 | 31.4% | 53.1% | 9.8% | 70.8% | 114.2 | 3.4% |
| 250 | B_validbonus | 18.2% | 31.6% | 4.7% | 100.0% | 0.0 | 1.7% |
| 250 | C_group_p0.25 | — | — | — | — | — | — |
| 250 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 300 | baseline | 38.5% | 59.8% | 17.2% | 45.2% | 219.6 | 2.0% |
| 300 | A_group_p1 | 36.5% | 60.2% | 12.9% | 51.0% | 136.4 | 3.1% |
| 300 | B_validbonus | 17.0% | 28.5% | 5.5% | 100.0% | 0.0 | 1.9% |
| 300 | C_group_p0.25 | — | — | — | — | — | — |
| 300 | D_per_sample_p0.25 | — | — | — | — | — | — |

## Degeneration signals

Same windows as above. "fail claims target" = share of failed responses whose last line ends in "= <original target>". Hindsight positives/negatives per step: per-sample runs count the samples normalized together in the step's new uid; group runs count reward-1 / reward-0 samples inside rewritten groups.

| step | run | entropy | mixed groups | train fail claims target | val fail claims target | hindsight positives / step | hindsight negatives / step |
|---|---|---|---|---|---|---|---|
| 0 | baseline | 0.236 | 27.7% | 37.5% | 32.0% | 0.0 | 0.0 |
| 0 | A_group_p1 | 0.234 | 29.4% | 46.8% | 33.0% | 23.9 | 92.9 |
| 0 | B_validbonus | 0.213 | 31.6% | 25.3% | 32.5% | 0.0 | 0.0 |
| 0 | C_group_p0.25 | 0.243 | 26.9% | 40.8% | 32.7% | 8.4 | 32.4 |
| 0 | D_per_sample_p0.25 | 0.229 | 32.5% | 34.0% | 32.0% | 12.2 | 66.3 |
| 25 | baseline | 0.117 | 32.2% | 31.7% | — | 0.0 | 0.0 |
| 25 | A_group_p1 | 0.039 | 12.2% | 98.3% | — | 0.0 | 0.0 |
| 25 | B_validbonus | 0.009 | 4.4% | 0.1% | — | 0.0 | 0.0 |
| 25 | C_group_p0.25 | 0.054 | 14.1% | 91.3% | — | 0.8 | 1.6 |
| 25 | D_per_sample_p0.25 | 0.041 | 19.1% | 4.3% | — | 53.8 | 9.9 |
| 50 | baseline | 0.083 | 28.0% | 25.3% | 26.4% | 0.0 | 0.0 |
| 50 | A_group_p1 | 0.032 | 9.7% | 96.8% | 97.9% | 0.0 | 0.0 |
| 50 | B_validbonus | 0.004 | 2.7% | 0.0% | 0.0% | 0.0 | 0.0 |
| 50 | C_group_p0.25 | 0.060 | 20.6% | 87.3% | 87.8% | 0.0 | 0.0 |
| 50 | D_per_sample_p0.25 | 0.019 | 14.4% | 0.3% | 0.2% | 53.9 | 3.8 |
| 100 | baseline | 0.051 | 13.6% | 28.1% | 25.9% | 0.0 | 0.0 |
| 100 | A_group_p1 | 0.028 | 11.4% | 94.8% | 94.4% | 0.0 | 0.0 |
| 100 | B_validbonus | 0.006 | 4.2% | 0.0% | 0.0% | 0.0 | 0.0 |
| 100 | C_group_p0.25 | — | — | — | — | — | — |
| 100 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 150 | baseline | 0.052 | 7.8% | 55.3% | 55.9% | 0.0 | 0.0 |
| 150 | A_group_p1 | 0.027 | 4.2% | 79.6% | 81.4% | 0.4 | 1.2 |
| 150 | B_validbonus | 0.004 | 1.9% | 0.0% | 0.0% | 0.0 | 0.0 |
| 150 | C_group_p0.25 | — | — | — | — | — | — |
| 150 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 200 | baseline | 0.036 | 4.1% | 69.2% | 69.1% | 0.0 | 0.0 |
| 200 | A_group_p1 | 0.008 | 2.0% | 96.3% | 96.1% | 0.6 | 0.2 |
| 200 | B_validbonus | 0.003 | 2.0% | 0.1% | 0.0% | 0.0 | 0.0 |
| 200 | C_group_p0.25 | — | — | — | — | — | — |
| 200 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 250 | baseline | 0.023 | 2.7% | 86.1% | 85.9% | 0.0 | 0.0 |
| 250 | A_group_p1 | 0.017 | 3.4% | 88.0% | 86.6% | 1.1 | 1.3 |
| 250 | B_validbonus | 0.002 | 1.7% | 0.0% | 0.0% | 0.0 | 0.0 |
| 250 | C_group_p0.25 | — | — | — | — | — | — |
| 250 | D_per_sample_p0.25 | — | — | — | — | — | — |
| 300 | baseline | 0.032 | 2.0% | 68.1% | 66.3% | 0.0 | 0.0 |
| 300 | A_group_p1 | 0.026 | 3.1% | 50.2% | 56.6% | 0.0 | 0.0 |
| 300 | B_validbonus | 0.002 | 1.9% | 0.0% | 0.0% | 0.0 | 0.0 |
| 300 | C_group_p0.25 | — | — | — | — | — | — |
| 300 | D_per_sample_p0.25 | — | — | — | — | — | — |

## Hindsight log-prob diagnostic (A_group_p1): logp_new - logp_orig (sum over response tokens)

Per-step summaries averaged over the steps in each interval (steps with no relabeled sample of a kind are skipped); counts are totals.

| steps | diff mean (new-target success) | diff median (success) | diff mean (new-target fail) | diff median (fail) | share \|diff\| < 0.05 | success samples | fail samples |
|---|---|---|---|---|---|---|---|
| 1-25 | 1.077 | 1.055 | -14.778 | -14.062 | 1.1% | 262.0 | 1018.0 |
| 26-50 | — | — | — | — | — | 0 | 0 |
| 51-100 | -1.096 | -1.080 | -42.371 | -44.289 | 0.0% | 21.0 | 19.0 |
| 101-200 | -0.392 | -0.392 | -66.060 | -65.420 | 0.0% | 38.0 | 42.0 |
| 201-300 | 0.873 | 0.873 | -81.661 | -80.313 | 50.0% | 52.0 | 28.0 |

## Hindsight log-prob diagnostic (C_group_p0.25): logp_new - logp_orig (sum over response tokens)

Per-step summaries averaged over the steps in each interval (steps with no relabeled sample of a kind are skipped); counts are totals.

| steps | diff mean (new-target success) | diff median (success) | diff mean (new-target fail) | diff median (fail) | share \|diff\| < 0.05 | success samples | fail samples |
|---|---|---|---|---|---|---|---|
| 1-25 | 0.375 | 0.333 | -16.604 | -16.027 | 1.2% | 143.0 | 505.0 |
| 26-50 | — | — | — | — | — | 0 | 0 |
| 51-100 | — | — | — | — | — | 0 | 0 |
| 101-200 | — | — | — | — | — | 0 | 0 |
| 201-300 | — | — | — | — | — | 0 | 0 |

## Hindsight log-prob diagnostic (D_per_sample_p0.25): logp_new - logp_orig (sum over response tokens)

Per-step summaries averaged over the steps in each interval (steps with no relabeled sample of a kind are skipped); counts are totals.

| steps | diff mean (new-target success) | diff median (success) | diff mean (new-target fail) | diff median (fail) | share \|diff\| < 0.05 | success samples | fail samples |
|---|---|---|---|---|---|---|---|
| 1-25 | -0.015 | 0.100 | — | — | 7.4% | 705.0 | 0.0 |
| 26-50 | -0.847 | -0.248 | — | — | 37.1% | 1257.0 | 0.0 |
| 51-100 | -0.621 | -0.089 | — | — | 39.2% | 1880.0 | 0.0 |
| 101-200 | — | — | — | — | — | 0 | 0 |
| 201-300 | — | — | — | — | — | 0 | 0 |
