# Countdown: baseline vs hindsight vs valid-bonus

Validation = greedy success on the 512-problem val set. Training columns are means over steps center-4..center+5 (steps 1-10 for step 0), computed against the original target.

| step | run | val all | val 3 nums | val 4 nums | train format valid | too-many-lines fails / step | mixed groups |
|---|---|---|---|---|---|---|---|
| 0 | baseline | 9.0% | 16.0% | 2.0% | 67.9% | 41.1 | 27.7% |
| 0 | hindsight | 9.0% | 16.0% | 2.0% | 63.9% | 57.8 | 29.4% |
| 0 | validbonus | 8.8% | 15.6% | 2.0% | 73.9% | 30.3 | 31.6% |
| 50 | baseline | 20.9% | 35.5% | 6.2% | 75.1% | 75.7 | 28.0% |
| 50 | hindsight | 16.8% | 28.1% | 5.5% | 84.1% | 56.5 | 9.7% |
| 50 | validbonus | 14.1% | 25.0% | 3.1% | 100.0% | 0.0 | 2.7% |
| 100 | baseline | 26.8% | 44.5% | 9.0% | 69.6% | 109.4 | 13.6% |
| 100 | hindsight | 23.2% | 39.8% | 6.6% | 76.4% | 94.0 | 11.4% |
| 100 | validbonus | 17.0% | 30.5% | 3.5% | 100.0% | 0.0 | 4.2% |
| 150 | baseline | 34.0% | 55.1% | 12.9% | 45.8% | 166.4 | 7.8% |
| 150 | hindsight | 28.7% | 48.8% | 8.6% | 67.0% | 100.9 | 4.2% |
| 150 | validbonus | 16.0% | 27.0% | 5.1% | 100.0% | 0.0 | 1.9% |
| 200 | baseline | 35.5% | 56.6% | 14.5% | 55.3% | 163.8 | 4.1% |
| 200 | hindsight | 29.5% | 49.6% | 9.4% | 82.3% | 68.1 | 2.0% |
| 200 | validbonus | 15.0% | 25.4% | 4.7% | 100.0% | 0.2 | 2.0% |
| 250 | baseline | 38.9% | 61.7% | 16.0% | 68.8% | 134.4 | 2.7% |
| 250 | hindsight | 31.4% | 53.1% | 9.8% | 70.8% | 114.2 | 3.4% |
| 250 | validbonus | 18.2% | 31.6% | 4.7% | 100.0% | 0.0 | 1.7% |
| 300 | baseline | 38.5% | 59.8% | 17.2% | 45.2% | 219.6 | 2.0% |
| 300 | hindsight | 36.5% | 60.2% | 12.9% | 51.0% | 136.4 | 3.1% |
| 300 | validbonus | 17.0% | 28.5% | 5.5% | 100.0% | 0.0 | 1.9% |

## Hindsight log-prob diagnostic: logp_new - logp_orig (sum over response tokens)

Per-step summaries averaged over the steps in each interval (steps with no relabeled sample of a kind are skipped); counts are totals.

| steps | diff mean (new-target success) | diff median (success) | diff mean (new-target fail) | diff median (fail) | share \|diff\| < 0.05 | success samples | fail samples |
|---|---|---|---|---|---|---|---|
| 1-25 | 1.077 | 1.055 | -14.778 | -14.062 | 1.1% | 262.0 | 1018.0 |
| 26-50 | — | — | — | — | — | 0 | 0 |
| 51-100 | -1.096 | -1.080 | -42.371 | -44.289 | 0.0% | 21.0 | 19.0 |
| 101-200 | -0.392 | -0.392 | -66.060 | -65.420 | 0.0% | 38.0 | 42.0 |
| 201-300 | 0.873 | 0.873 | -81.661 | -80.313 | 50.0% | 52.0 | 28.0 |
