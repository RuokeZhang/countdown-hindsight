# ALFWorld precheck: untrained Qwen2.5-1.5B-Instruct, 240 tasks x 8 episodes

| item | metric | all | pick_and_place_simple | look_at_obj_in_light | pick_clean_then_place_in_recep | pick_heat_then_place_in_recep | pick_cool_then_place_in_recep | pick_two_obj_and_place |
|---|---|---|---|---|---|---|---|---|
| 1 | success rate | 7.7% | 21.6% | 4.4% | 9.1% | 3.1% | 7.2% | 0.6% |
| 1 | groups: all failed | 72.5% | 40.0% | 87.5% | 72.5% | 77.5% | 62.5% | 95.0% |
| 1 | groups: mixed | 27.5% | 60.0% | 12.5% | 27.5% | 22.5% | 37.5% | 5.0% |
| 1 | groups: all succeeded | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| 2 | failed episodes | 1773 | 251 | 306 | 291 | 310 | 297 | 318 |
| 2 | failed: >= 1 template-expressible achievement | 28.1% | 15.9% | 8.2% | 39.9% | 36.8% | 29.0% | 36.8% |
| 2 | failed: only partial achievements | 45.5% | 47.8% | 45.1% | 35.7% | 54.8% | 52.9% | 37.1% |
| 2 | failed: nothing achieved | 26.4% | 36.3% | 46.7% | 24.4% | 8.4% | 18.2% | 26.1% |
| 3 | all-failed groups, template achievements: none in all 8 | 24.7% | 43.8% | 54.3% | 10.3% | 0.0% | 28.0% | 18.4% |
| 3 | all-failed groups, template achievements: identical (non-empty) | 0.6% | 0.0% | 0.0% | 3.4% | 0.0% | 0.0% | 0.0% |
| 3 | all-failed groups, template achievements: partly different | 74.7% | 56.2% | 45.7% | 86.2% | 100.0% | 72.0% | 81.6% |
| 3 | all-failed groups, template achievements: all different | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| 3 | all-failed groups, all achievements incl. partial: none in all 8 | 2.9% | 12.5% | 2.9% | 0.0% | 0.0% | 4.0% | 2.6% |
| 3 | all-failed groups, all achievements incl. partial: identical (non-empty) | 0.6% | 0.0% | 2.9% | 0.0% | 0.0% | 0.0% | 0.0% |
| 3 | all-failed groups, all achievements incl. partial: partly different | 87.4% | 87.5% | 94.3% | 93.1% | 77.4% | 84.0% | 86.8% |
| 3 | all-failed groups, all achievements incl. partial: all different | 9.2% | 0.0% | 0.0% | 6.9% | 22.6% | 12.0% | 10.5% |
| 4 | end: success | 7.7% | 21.6% | 4.4% | 9.1% | 3.1% | 7.2% | 0.6% |
| 4 | end: step limit (50) | 92.3% | 78.4% | 95.6% | 90.9% | 96.9% | 92.8% | 99.4% |
| 4 | end: other (env done, not won) | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| 4 | mean steps (all episodes) | 48.5 | 45.4 | 49.0 | 48.5 | 49.3 | 48.7 | 49.9 |
| 4 | mean steps (failed episodes) | 50.0 | 50.0 | 50.0 | 50.0 | 50.0 | 50.0 | 50.0 |

Achievements are read from the env state facts (placements: inreceptacle facts new vs the previous step; hot/cool/clean/lamp: new vs the initial state). Share of episodes where the feedback-text parse gives the same event set as the state, per event kind:

| put | hold | heat | cool | clean | toggle |
|---|---|---|---|---|---|
| 99.3% | 100.0% | 100.0% | 97.7% | 100.0% | 100.0% |

Template achievements in failed episodes by kind: {'put': 371, 'put two': 176, 'put cool': 82, 'examine': 29, 'put hot': 21, 'put clean': 20}
Partial achievements in failed episodes by kind: {'hold': 1546, 'cool': 108, 'heat': 50, 'clean': 42, 'turn': 33}
