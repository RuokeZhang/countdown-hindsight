# Countdown zero-training baseline

Model `Qwen/Qwen2.5-1.5B-Instruct`, prompt v4, 256 problems each for 3 and 4 nums (seed 0), 8 samples/problem (T=1.0, top_p=1.0) + 1 greedy, max_new_tokens=64.
Dataset target range: [10, 100].

| metric | all | 3 nums | 4 nums |
|---|---|---|---|
| problems | 512 | 256 | 256 |
| sample success rate | 3.9% | 7.0% | 0.8% |
| greedy success rate | 4.5% | 5.9% | 3.1% |
| problems with >=1 success in 8 | 18.2% | 31.2% | 5.1% |
| problems with all 8 failed | 81.8% | 68.8% | 94.9% |
| problems with mixed success/failure | 18.0% | 30.9% | 5.1% |
| format valid rate (sample, passes parse) | 73.3% | 89.0% | 57.5% |
| format valid rate (greedy) | 78.5% | 94.1% | 62.9% |
| failed samples stopped at parse | 27.8% | 11.8% | 42.8% |
| failed samples stopped at arithmetic | 29.6% | 35.8% | 23.7% |
| failed samples stopped at usage | 14.5% | 7.9% | 20.7% |
| failed samples stopped at target | 28.1% | 44.5% | 12.7% |
| failed samples that are relabelable | 26.1% | 42.2% | 11.1% |
| all-fail problems with >=1 relabelable | 70.2% | 91.5% | 54.7% |
| relabelable final value in target range [10, 100] | 38.7% | 36.4% | 47.1% |
| mean output tokens (sample) | 31.4 | 24.3 | 38.6 |
| truncated at 64 tokens (sample) | 6.4% | 0.6% | 12.2% |
| mean output tokens (greedy) | 31.4 | 24.5 | 38.3 |
| truncated (greedy) | 4.7% | 0.4% | 9.0% |

| timing | sampled | greedy | total |
|---|---|---|---|
| generation seconds | 26.4 | 2.2 | 28.6 |
| output tokens | 128743 | 16092 | 144835 |
| output tokens/s | 4882 | 7283 | 5068 |

## Parse-failure patterns (sampled outputs)

| pattern | count | share of parse failures |
|---|---|---|
| decimal number | 445 | 40.6% |
| every line well-formed, too many lines | 171 | 15.6% |
| every line well-formed, too few lines | 130 | 11.9% |
| empty output / blank line | 113 | 10.3% |
| chained expression (a op b op c = d) | 68 | 6.2% |
| parentheses | 56 | 5.1% |
| other (e.g. 'x = y', 'a op b =' cut off, two '=') | 54 | 4.9% |
| no '=' (bare expression, usually cut off) | 51 | 4.7% |
| explanation text / words | 7 | 0.6% |

## Failure examples: stopped at parse (1095 samples)

nums=[79, 55, 11, 15] target=44 final_value=None
```
79 - 55 = 24
24 + 11 = 35
35 + 15 = 50
50 - 6 = 44
```

nums=[22, 67, 66, 92] target=75 final_value=None
```
92 - 22 = 70
70 + 66 = 136
136 / 92 = 1.5
```

nums=[89, 77, 87] target=75 final_value=None
```
89 - 77 = 12
12 * 77 / 89 = 75
```

## Failure examples: stopped at arithmetic (1164 samples)

nums=[13, 12, 67] target=66 final_value=None
```
13 * 67 = 871
871 - 12 = 66
```

nums=[85, 29, 30, 34] target=50 final_value=None
```
85 - 29 = 56
56 - 30 = -4
-4 + 34 = 30
```

nums=[4, 9, 4, 67] target=60 final_value=None
```
9 * 67 = 603
4 * 67 = 268
603 - 268 = 60
```

## Failure examples: stopped at usage (572 samples)

nums=[64, 64, 61, 52] target=15 final_value=None
```
64 + 64 = 128
128 / 2 = 64
64 - 52 = 12
```

nums=[76, 85, 55, 74] target=70 final_value=None
```
55 - 85 = -30
-30 * 76 = -2280
-2280 / 10 = -228
```

nums=[83, 95, 85, 70] target=75 final_value=None
```
85 + 83 = 168
168 / 2 = 84
84 - 95 = -11
```

## Failure examples: stopped at target (1106 samples)

nums=[5, 52, 39] target=86 final_value=221
```
5 * 52 = 260
260 - 39 = 221
```

nums=[35, 9, 63] target=89 final_value=245
```
63 / 9 = 7
7 * 35 = 245
```

nums=[10, 77, 50, 33] target=88 final_value=60
```
33 + 50 = 83
83 - 77 = 6
6 * 10 = 60
```
