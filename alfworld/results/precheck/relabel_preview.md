# Relabel preview on the precheck episodes (untrained model, 240 groups x 8)

## Variant `lfh`

- selected groups: 239 of 240
- anchor achieved no template goal (no relabel): 187 (78.2%)
- relabeled groups: 52
- under the hindsight goal: all episodes succeed 0.0%, mixed (carries signal) 100.0%
- episodes succeeding under the hindsight goal (per group, anchor included): {1: 26, 2: 11, 3: 4, 4: 3, 5: 6, 6: 1, 7: 1}
- hindsight goal kind: {'put': 36, 'cool': 7, 'look': 4, 'two': 2, 'hot': 2, 'clean': 1}; same kind as the group's original task: 17.3%
- hindsight rows with nonzero advantage: 416; of these also with nonzero original advantage: 120; opposite signs: 50 (41.7%)

Examples (original task -> hindsight goal; per-episode original / hindsight success):

- `put a candle in cart.` -> `put a cloth in drawer`: [0, 0, 1, 0, 1, 1, 1, 1] / [0, 1, 0, 0, 0, 0, 0, 0]
- `put a candle in drawer.` -> `put a spraybottle in drawer`: [0, 0, 0, 0, 0, 0, 1, 1] / [0, 0, 0, 1, 0, 0, 0, 0]
- `put a keychain in safe.` -> `look at keychain under the desklamp`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 1, 0, 0, 0, 1, 0, 0]
- `put a toiletpaper in toiletpaperhanger.` -> `put two toiletpaper in drawer`: [1, 0, 1, 0, 1, 0, 1, 1] / [0, 1, 0, 0, 0, 0, 0, 0]
- `put a watch in coffeetable.` -> `put a laptop in armchair`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 0, 0, 0, 0, 0, 0, 1]
- `look at pencil under the desklamp.` -> `look at pen under the desklamp`: [0, 1, 0, 1, 1, 0, 1, 1] / [1, 0, 0, 0, 1, 0, 0, 0]
- `examine the statue with the desklamp.` -> `look at keychain under the desklamp`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 0, 0, 0, 0, 1, 0, 0]
- `clean some bowl and put it in fridge.` -> `put a cool bowl in fridge`: [0, 0, 0, 0, 0, 0, 1, 0] / [0, 0, 0, 1, 0, 0, 1, 0]

## Variant `dead`

- selected groups: 174 of 240
- anchor achieved no template goal (no relabel): 137 (78.7%)
- relabeled groups: 37
- under the hindsight goal: all episodes succeed 0.0%, mixed (carries signal) 100.0%
- episodes succeeding under the hindsight goal (per group, anchor included): {1: 17, 2: 8, 3: 3, 4: 3, 5: 4, 6: 1, 7: 1}
- hindsight goal kind: {'put': 27, 'look': 3, 'cool': 3, 'hot': 2, 'two': 1, 'clean': 1}; same kind as the group's original task: 10.8%
- hindsight rows with nonzero advantage: 296; of these also with nonzero original advantage: 0; opposite signs: 0 (—)

Examples (original task -> hindsight goal; per-episode original / hindsight success):

- `put a keychain in safe.` -> `look at keychain under the desklamp`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 1, 0, 0, 0, 1, 0, 0]
- `put a watch in coffeetable.` -> `put a laptop in armchair`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 0, 0, 0, 0, 0, 0, 1]
- `examine the statue with the desklamp.` -> `look at keychain under the desklamp`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 0, 0, 0, 0, 1, 0, 0]
- `clean some cloth and put it in countertop.` -> `put a cloth in countertop`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 1, 0, 0, 1, 1, 0, 0]
- `put a clean cup in microwave.` -> `put a cup in countertop`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 0, 0, 0, 0, 1, 0, 1]
- `put a clean mug in coffeemachine.` -> `put a bowl in sinkbasin`: [0, 0, 0, 0, 0, 0, 0, 0] / [1, 0, 0, 0, 0, 0, 0, 0]
- `put a clean pan in countertop.` -> `put a pan in countertop`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 0, 1, 0, 0, 0, 0, 1]
- `clean some soapbar and put it in cabinet.` -> `put a soapbottle in cabinet`: [0, 0, 0, 0, 0, 0, 0, 0] / [0, 0, 0, 0, 0, 0, 1, 0]
