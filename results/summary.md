# Countdown zero-training baseline

Model `Qwen/Qwen2.5-1.5B-Instruct`, 256 problems each for 3 and 4 nums (seed 0), 8 samples/problem (T=1.0, top_p=1.0) + 1 greedy, max_new_tokens=64.
Dataset target range: [10, 100].

| metric | all | 3 nums | 4 nums |
|---|---|---|---|
| problems | 512 | 256 | 256 |
| sample success rate | 4.3% | 7.2% | 1.4% |
| greedy success rate | 9.4% | 14.8% | 3.9% |
| problems with >=1 success in 8 | 22.5% | 34.8% | 10.2% |
| problems with all 8 failed | 77.5% | 65.2% | 89.8% |
| problems with mixed success/failure | 22.5% | 34.8% | 10.2% |
| format valid rate (sample, passes parse) | 32.3% | 34.3% | 30.3% |
| format valid rate (greedy) | 54.9% | 55.9% | 53.9% |
| failed samples stopped at parse | 70.8% | 70.8% | 70.7% |
| failed samples stopped at arithmetic | 8.8% | 8.5% | 9.1% |
| failed samples stopped at usage | 5.1% | 3.5% | 6.7% |
| failed samples stopped at target | 15.3% | 17.2% | 13.5% |
| failed samples that are relabelable | 12.1% | 12.6% | 11.6% |
| all-fail problems with >=1 relabelable | 57.9% | 55.7% | 59.6% |
| relabelable final value in target range [10, 100] | 53.4% | 56.5% | 50.2% |
| mean output tokens (sample) | 35.6 | 29.9 | 41.2 |
| truncated at 64 tokens (sample) | 12.4% | 6.3% | 18.4% |
| mean output tokens (greedy) | 34.2 | 29.0 | 39.4 |
| truncated (greedy) | 11.9% | 7.8% | 16.0% |

| timing | sampled | greedy | total |
|---|---|---|---|
| generation seconds | 23.0 | 2.5 | 25.5 |
| output tokens | 145782 | 17508 | 163290 |
| output tokens/s | 6330 | 7027 | 6398 |

## Parse-failure patterns (sampled outputs)

| pattern | count | share of parse failures |
|---|---|---|
| every line well-formed, too many lines | 959 | 34.6% |
| chained expression (a op b op c = d) | 695 | 25.1% |
| decimal number | 513 | 18.5% |
| every line well-formed, too few lines | 179 | 6.5% |
| no '=' (bare expression, usually cut off) | 133 | 4.8% |
| explanation text / words | 117 | 4.2% |
| parentheses | 94 | 3.4% |
| other (e.g. 'x = y', 'a op b =' cut off, two '=') | 74 | 2.7% |
| empty output / blank line | 9 | 0.3% |

## Failure examples: stopped at parse (2773 samples)

nums=[78, 21, 3, 98] target=83 final_value=None
```
78 - 21 = 57
57 / 98 = 1.075449906
1.075449906 * 78 = 83
```

nums=[86, 29, 92, 50] target=40 final_value=None
```
86 + 50 = 136
136 - 29 = 107
```

nums=[3, 78, 44] target=37 final_value=None
```
3 * 78 - 44 = 37
```

## Failure examples: stopped at arithmetic (346 samples)

nums=[4, 78, 23] target=59 final_value=None
```
4 * 78 = 292
292 - 23 = 269
```

nums=[14, 66, 70, 77] target=59 final_value=None
```
77 / 7 = 11
11 * 6 = 66
66 - 1 = 59
```

nums=[45, 89, 2, 9] target=42 final_value=None
```
45 + 89 = 134
134 / 2 = 67
67 - 4 = 42
```

## Failure examples: stopped at usage (201 samples)

nums=[9, 56, 59, 74] target=21 final_value=None
```
2 * 9 = 18
18 + 59 = 77
77 - 56 = 21
```

nums=[48, 13, 8, 73] target=79 final_value=None
```
48 - 13 = 35
35 / 5 = 7
7 * 73 = 511
```

nums=[44, 74, 66, 65] target=46 final_value=None
```
66 - 44 = 22
22 - 6 = 16
16 * 65 = 1040
```

## Failure examples: stopped at target (599 samples)

nums=[71, 24, 72, 58] target=83 final_value=81
```
71 + 24 = 95
95 - 72 = 23
23 + 58 = 81
```

nums=[72, 29, 43, 8] target=18 final_value=8
```
72 - 29 = 43
43 / 43 = 1
1 * 8 = 8
```

nums=[26, 19, 34, 21] target=20 final_value=-6
```
26 - 19 = 7
21 + 7 = 28
28 - 34 = -6
```
