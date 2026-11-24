# Relabel preview on the precheck episodes (untrained model, 240 groups x 8)

## Variant `lfh`

- selected groups: 239 of 240
- anchor achieved no template goal (no relabel): 174 (72.8%)
- relabeled groups: 65
- under the hindsight goal: all episodes succeed 3.1%, mixed (carries signal) 96.9%
- episodes succeeding under the hindsight goal (per group, anchor included): {1: 31, 2: 11, 3: 5, 4: 4, 5: 5, 6: 3, 7: 4, 8: 2}
- hindsight goal kind: {'put': 35, 'two': 19, 'cool': 6, 'look': 3, 'clean': 1, 'hot': 1}; same kind as the group's original task: 16.9%
- hindsight rows with nonzero advantage: 504; of these also with nonzero original advantage: 136; opposite signs: 63 (46.3%)

Examples (original task -> hindsight goal; per-episode original / hindsight success):

- `put some butterknife on sidetable.` -> `put two potato in sidetable`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 0, 0, 0, 0, 1, 0, 0]
- `put a candle in cart.` -> `put a cloth in drawer`: [0, 0, 1, 0, 1, 1, 1, 1] / [0, 1, 0, 0, 0, 0, 0, 0]
- `put some candle on countertop.` -> `put two cloth in countertop`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 0, 0, 0, 1, 1, 0, 0]
- `put a candle in drawer.` -> `put a spraybottle in drawer`: [0, 0, 0, 0, 0, 0, 1, 1] / [0, 0, 0, 1, 0, 0, 0, 0]
- `put some creditcard on desk.` -> `put two alarmclock in desk`: [0, 0, 0, 0, 0, 0, 0, 1] / [0, 0, 0, 1, 0, 0, 0, 0]
- `put a keychain in safe.` -> `look at keychain under the desklamp`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 1, 0, 0, 0, 1, 0, 0]
- `put a soapbottle in toilet.` -> `put two spraybottle in toilet`: [0, 0, 0, 0, 0, 0, 0, 0] / [1, 0, 0, 0, 0, 1, 1, 1]
- `put a toiletpaper in toiletpaperhanger.` -> `put two toiletpaper in drawer`: [1, 0, 1, 0, 1, 0, 1, 1] / [0, 1, 0, 0, 0, 0, 0, 0]

## Variant `dead`

- selected groups: 174 of 240
- anchor achieved no template goal (no relabel): 127 (73.0%)
- relabeled groups: 47
- under the hindsight goal: all episodes succeed 2.1%, mixed (carries signal) 97.9%
- episodes succeeding under the hindsight goal (per group, anchor included): {1: 21, 2: 9, 3: 3, 4: 4, 5: 3, 6: 3, 7: 3, 8: 1}
- hindsight goal kind: {'put': 26, 'two': 14, 'look': 3, 'cool': 2, 'clean': 1, 'hot': 1}; same kind as the group's original task: 14.9%
- hindsight rows with nonzero advantage: 368; of these also with nonzero original advantage: 0; opposite signs: 0 (—)

Examples (original task -> hindsight goal; per-episode original / hindsight success):

- `put some butterknife on sidetable.` -> `put two potato in sidetable`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 0, 0, 0, 0, 1, 0, 0]
- `put some candle on countertop.` -> `put two cloth in countertop`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 0, 0, 0, 1, 1, 0, 0]
- `put a keychain in safe.` -> `look at keychain under the desklamp`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 1, 0, 0, 0, 1, 0, 0]
- `put a soapbottle in toilet.` -> `put two spraybottle in toilet`: [0, 0, 0, 0, 0, 0, 0, 0] / [1, 0, 0, 0, 0, 1, 1, 1]
- `put a watch in coffeetable.` -> `put a laptop in armchair`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 0, 0, 0, 0, 0, 0, 1]
- `look at pillow under the desklamp.` -> `put two pillow in bed`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 0, 0, 0, 0, 0, 1, 0]
- `examine the statue with the desklamp.` -> `look at keychain under the desklamp`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 0, 0, 0, 0, 1, 0, 0]
- `clean some cloth and put it in countertop.` -> `put a cloth in countertop`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 1, 0, 0, 1, 1, 0, 0]
