# Countdown zero-training baseline

Model `Qwen/Qwen2.5-1.5B-Instruct`, prompt v2, 256 problems each for 3 and 4 nums (seed 0), 8 samples/problem (T=1.0, top_p=1.0) + 1 greedy, max_new_tokens=64.
Dataset target range: [10, 100].

| metric | all | 3 nums | 4 nums |
|---|---|---|---|
| problems | 512 | 256 | 256 |
| sample success rate | 3.4% | 5.7% | 1.1% |
| greedy success rate | 2.9% | 3.1% | 2.7% |
| problems with >=1 success in 8 | 16.2% | 25.4% | 7.0% |
| problems with all 8 failed | 83.8% | 74.6% | 93.0% |
| problems with mixed success/failure | 16.2% | 25.4% | 7.0% |
| format valid rate (sample, passes parse) | 67.5% | 80.4% | 54.6% |
| format valid rate (greedy) | 78.3% | 88.7% | 68.0% |
| failed samples stopped at parse | 33.6% | 20.8% | 45.9% |
| failed samples stopped at arithmetic | 37.6% | 45.2% | 30.3% |
| failed samples stopped at usage | 7.9% | 5.4% | 10.3% |
| failed samples stopped at target | 20.8% | 28.5% | 13.5% |
| failed samples that are relabelable | 18.9% | 27.1% | 11.0% |
| all-fail problems with >=1 relabelable | 68.1% | 82.2% | 56.7% |
| relabelable final value in target range [10, 100] | 35.4% | 31.7% | 44.1% |
| mean output tokens (sample) | 32.8 | 26.6 | 39.0 |
| truncated at 64 tokens (sample) | 7.2% | 3.2% | 11.1% |
| mean output tokens (greedy) | 32.1 | 26.0 | 38.2 |
| truncated (greedy) | 5.1% | 1.2% | 9.0% |

| timing | sampled | greedy | total |
|---|---|---|---|
| generation seconds | 23.0 | 2.2 | 25.2 |
| output tokens | 134206 | 16421 | 150627 |
| output tokens/s | 5832 | 7372 | 5968 |

## Parse-failure patterns (sampled outputs)

| pattern | count | share of parse failures |
|---|---|---|
| decimal number | 512 | 38.5% |
| every line well-formed, too many lines | 285 | 21.4% |
| every line well-formed, too few lines | 110 | 8.3% |
| chained expression (a op b op c = d) | 89 | 6.7% |
| no '=' (bare expression, usually cut off) | 74 | 5.6% |
| other (e.g. 'x = y', 'a op b =' cut off, two '=') | 69 | 5.2% |
| parentheses | 62 | 4.7% |
| unicode operator (× ÷ · −) | 62 | 4.7% |
| empty output / blank line | 59 | 4.4% |
| explanation text / words | 9 | 0.7% |

## Failure examples: stopped at parse (1331 samples)

nums=[67, 71, 30, 28] target=75 final_value=None
```
67 - 28 = 39
39 - 2 \* 30 = -19
-19 * -1 = 19
19 * 3 = 75
```

nums=[47, 78, 75, 17] target=61 final_value=None
```
47 + 78 = 125
125 - 75 = 50
50 / 17 = 2.9411764705882354
```

nums=[66, 90, 67] target=89 final_value=None
```
66 * 90 = 5,940
5,940 - 67 = 8,873
```

## Failure examples: stopped at arithmetic (1487 samples)

nums=[10, 30, 95] target=92 final_value=None
```
10 * 9 = 90
90 - 30 = 92
```

nums=[20, 64, 12, 61] target=16 final_value=None
```
20 * 64 = 1280
1280 / 61 = 21
21 - 6 = 15
```

nums=[66, 2, 52, 2] target=94 final_value=None
```
66 - 2 = 64
64 - 12 = 52
52 / 2 = 94
```

## Failure examples: stopped at usage (314 samples)

nums=[27, 60, 74, 83] target=42 final_value=None
```
83 - 60 = 23
27 * 23 = 621
621 / 27 = 23
```

nums=[86, 29, 92, 50] target=40 final_value=None
```
86 - 29 = 57
57 - 29 = 28
28 + 92 = 120
```

nums=[4, 9, 4, 67] target=60 final_value=None
```
4 * 9 = 36
36 - 4 = 32
32 + 4 = 36
```

## Failure examples: stopped at target (824 samples)

nums=[64, 15, 6] target=85 final_value=369
```
64 * 6 = 384
384 - 15 = 369
```

nums=[13, 79, 26, 97] target=16 final_value=572
```
26 + 97 = 123
123 - 79 = 44
44 * 13 = 572
```

nums=[41, 20, 34] target=27 final_value=55
```
41 - 20 = 21
21 + 34 = 55
```
