# Countdown zero-training baseline

Model `Qwen/Qwen2.5-1.5B-Instruct`, prompt v3, 256 problems each for 3 and 4 nums (seed 0), 8 samples/problem (T=1.0, top_p=1.0) + 1 greedy, max_new_tokens=64.
Dataset target range: [10, 100].

| metric | all | 3 nums | 4 nums |
|---|---|---|---|
| problems | 512 | 256 | 256 |
| sample success rate | 6.0% | 10.3% | 1.7% |
| greedy success rate | 6.4% | 8.6% | 4.3% |
| problems with >=1 success in 8 | 26.8% | 43.8% | 9.8% |
| problems with all 8 failed | 73.2% | 56.2% | 90.2% |
| problems with mixed success/failure | 26.8% | 43.8% | 9.8% |
| format valid rate (sample, passes parse) | 66.5% | 82.2% | 50.9% |
| format valid rate (greedy) | 80.5% | 92.2% | 68.8% |
| failed samples stopped at parse | 35.6% | 19.9% | 50.0% |
| failed samples stopped at arithmetic | 29.1% | 33.6% | 25.0% |
| failed samples stopped at usage | 9.3% | 7.0% | 11.4% |
| failed samples stopped at target | 26.0% | 39.5% | 13.7% |
| failed samples that are relabelable | 23.3% | 36.2% | 11.5% |
| all-fail problems with >=1 relabelable | 72.5% | 88.9% | 62.3% |
| relabelable final value in target range [10, 100] | 51.3% | 51.6% | 50.6% |
| mean output tokens (sample) | 31.6 | 24.3 | 38.9 |
| truncated at 64 tokens (sample) | 6.4% | 2.1% | 10.6% |
| mean output tokens (greedy) | 30.8 | 24.3 | 37.2 |
| truncated (greedy) | 4.3% | 0.8% | 7.8% |

| timing | sampled | greedy | total |
|---|---|---|---|
| generation seconds | 21.2 | 2.0 | 23.2 |
| output tokens | 129357 | 15763 | 145120 |
| output tokens/s | 6098 | 7862 | 6250 |

## Parse-failure patterns (sampled outputs)

| pattern | count | share of parse failures |
|---|---|---|
| decimal number | 414 | 30.2% |
| chained expression (a op b op c = d) | 290 | 21.2% |
| every line well-formed, too many lines | 285 | 20.8% |
| parentheses | 142 | 10.4% |
| no '=' (bare expression, usually cut off) | 74 | 5.4% |
| every line well-formed, too few lines | 70 | 5.1% |
| other (e.g. 'x = y', 'a op b =' cut off, two '=') | 57 | 4.2% |
| empty output / blank line | 30 | 2.2% |
| explanation text / words | 7 | 0.5% |
| unicode operator (× ÷ · −) | 2 | 0.1% |

## Failure examples: stopped at parse (1371 samples)

nums=[67, 71, 30, 28] target=75 final_value=None
```
67 - 30 = 37
37 + 71 = 108
108 - 28 = 80
80 / 30 = 26.6666666667
26.6666
```

nums=[36, 79, 24, 93] target=26 final_value=None
```
24 / 6 = 4
93 - 24 - 79 = -34
-34 + 36 = 2
```

nums=[66, 90, 67] target=89 final_value=None
```
66 - 90 = -24
-24 / 67 = -0.3513698630136986
```

## Failure examples: stopped at arithmetic (1121 samples)

nums=[27, 8, 59] target=94 final_value=None
```
27 * 59 = 1533
1533 - 8 = 1525
```

nums=[5, 39, 61, 20] target=18 final_value=None
```
5 + 39 = 44
44 - 20 = 24
24 / 6 = 18
```

nums=[83, 95, 85, 70] target=75 final_value=None
```
83 - 70 = 13
13 + 85 = 98
98 / 95 = 75
```

## Failure examples: stopped at usage (358 samples)

nums=[69, 16, 76, 3] target=55 final_value=None
```
76 - 16 = 60
60 / 5 = 12
12 * 5 = 60
```

nums=[38, 78, 39, 81] target=62 final_value=None
```
81 - 39 = 42
42 - 78 = -36
-36 + 62 = 26
```

nums=[9, 8, 72, 40] target=23 final_value=None
```
40 / 8 = 5
9 - 5 = 4
4 * 8 = 32
```

## Failure examples: stopped at target (1001 samples)

nums=[29, 24, 72] target=32 final_value=67
```
24 + 72 = 96
96 - 29 = 67
```

nums=[4, 85, 69] target=20 final_value=271
```
4 * 85 = 340
340 - 69 = 271
```

nums=[48, 25, 61, 91] target=32 final_value=-53
```
48 - 25 = 23
61 - 23 = 38
38 - 91 = -53
```
