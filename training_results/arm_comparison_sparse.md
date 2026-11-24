# Countdown run comparison

Validation = greedy success on the 512-problem val set. Training columns are means over steps center-4..center+5 (steps 1-10 for step 0), computed against the original target.

| step | run | val all | val 3 nums | val 4 nums | train format valid | too-many-lines fails / step | mixed groups |
|---|---|---|---|---|---|---|---|
| 0 | baseline_n5_s0 | 0.0% | — | — | 39.2% | 53.6 | 2.2% |
| 25 | baseline_n5_s0 | 1.4% | — | — | 56.9% | 89.1 | 2.5% |
| 50 | baseline_n5_s0 | 1.4% | — | — | 40.7% | 153.5 | 2.7% |
| 75 | baseline_n5_s0 | 1.4% | — | — | 19.5% | 188.5 | 3.4% |
| 100 | baseline_n5_s0 | 1.4% | — | — | 9.1% | 197.6 | 5.6% |
| 125 | baseline_n5_s0 | — | — | — | — | — | — |
| 150 | baseline_n5_s0 | — | — | — | — | — | — |
| 175 | baseline_n5_s0 | — | — | — | — | — | — |
| 200 | baseline_n5_s0 | — | — | — | — | — | — |
| 225 | baseline_n5_s0 | — | — | — | — | — | — |
| 250 | baseline_n5_s0 | — | — | — | — | — | — |
| 275 | baseline_n5_s0 | — | — | — | — | — | — |
| 300 | baseline_n5_s0 | — | — | — | — | — | — |

## Degeneration signals

Same windows as above. "fail claims target" = share of failed responses whose last line ends in "= <original target>". Hindsight positives/negatives per step: per-sample runs count the samples normalized together in the step's new uid; group runs count reward-1 / reward-0 samples inside rewritten groups.

| step | run | entropy | mixed groups | train fail claims target | val fail claims target | hindsight positives / step | hindsight negatives / step |
|---|---|---|---|---|---|---|---|
| 0 | baseline_n5_s0 | 0.280 | 2.2% | 25.5% | 17.6% | 0.0 | 0.0 |
| 25 | baseline_n5_s0 | 0.155 | 2.5% | 23.7% | 16.8% | 0.0 | 0.0 |
| 50 | baseline_n5_s0 | 0.144 | 2.7% | 21.3% | 15.8% | 0.0 | 0.0 |
| 100 | baseline_n5_s0 | 0.131 | 5.6% | 21.8% | 19.8% | 0.0 | 0.0 |
| 150 | baseline_n5_s0 | — | — | — | — | — | — |
| 200 | baseline_n5_s0 | — | — | — | — | — | — |
| 250 | baseline_n5_s0 | — | — | — | — | — | — |
| 300 | baseline_n5_s0 | — | — | — | — | — | — |

## First validation step reaching a success level

Earliest validated step whose greedy val success is at least the level (— = never reached among the validated steps).

| run | last validated step | first step >= 5% | first step >= 10% | first step >= 20% |
|---|---|---|---|---|
| baseline_n5_s0 | 100 | — | — | — |

## First 100 steps: mixed groups and hindsight samples

Means over every training step in the interval. Hindsight positives/negatives per step as in the degeneration table.

| steps | run | mixed groups | hindsight positives / step | hindsight negatives / step |
|---|---|---|---|---|
| 1-25 | baseline_n5_s0 | 2.2% | 0.0 | 0.0 |
| 26-50 | baseline_n5_s0 | 3.8% | 0.0 | 0.0 |
| 51-75 | baseline_n5_s0 | 3.2% | 0.0 | 0.0 |
| 76-100 | baseline_n5_s0 | 3.8% | 0.0 | 0.0 |
