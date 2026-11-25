# ALFWorld (text) GRPO baseline and hindsight relabel, verl-agent

Model Qwen/Qwen2.5-1.5B-Instruct; verl-agent commit `20bd331` plus `verl_agent_changes.patch`; vllm 0.11.0, torch
2.8.0+cu128, transformers 4.57.3, flash-attn 2.8.3; 2x A100 SXM4 80GB (Vast). Environment setup: `setup_env.sh`.

## GRPO baseline, seed 0 (100 steps, 16 groups x 8 episodes per step)

Validation: every valid_seen (140) and valid_unseen (134) game once, temperature 0.4 (repo default).

| step | all | valid_seen | valid_unseen |
|---|---|---|---|
| 0 | 5.5% | 7.9% | 3.0% |
| 25 | 13.9% | 17.1% | 10.4% |
| 50 | 31.8% | 38.6% | 24.6% |
| 75 | 34.3% | 39.3% | 29.1% |
| 100 | 47.8% | 50.7% | 44.8% |

Per-step metrics (training success, all-fail / mixed / all-success group shares, entropy, step time, per-split and
per-task-type validation): `results/grpo_alfworld_seed0/metrics.jsonl`. Seed 1 was not run (dropped by request).

Command (on the training box, in `/root/alf/hs`, `ALFWORLD_DATA=/root/alf/alfworld_data`):

    bash run_alfworld_grpo_2gpu.sh grpo_alfworld_seed0 0

Every setting that differs from verl-agent's `examples/grpo_trainer/run_alfworld.sh` is marked `# changed:` in
`run_alfworld_grpo_2gpu.sh` (240-task training subset, both validation splits once each, test_freq 25, 100 steps,
run seed, console logging, no XFORMERS, Ray thread settings).

## Files

| file | what |
|---|---|
| `train_subset_240.txt`, `make_train_subset.py` | the fixed training subset: 40 solvable train tasks per type, seed 0 |
| `verl_agent_changes.patch` | our changes to verl-agent: several envs per Ray actor, eval over both splits, group-outcome metrics, metrics JSONL, optional speed options (`env.skip_finished_generation`, `env.alfworld.train_envs_per_worker`) |
| `run_alfworld_grpo_2gpu.sh`, `run_chain.sh` | baseline launch script; precheck -> smoke -> baseline chain |
| `precheck.py`, `precheck_report.py`, `test_precheck_tracker.py` | untrained-model precheck (240 tasks x 8), achievements from TextWorld state facts; report; expert test |
| `results/precheck/` | precheck summary, 10 failed trajectories, all 1920 episodes (`episodes.jsonl.gz`) |
| `relabel_preview.py` | offline relabel simulation from state achievements (LfH gate vs all-failed groups) |
| `llm_relabel.py`, `results/precheck/llm_relabel_prompt_v*.jsonl` | DeepSeek-V4-Pro relabel of every failed episode in all-failed groups, checked by the state checker (v1 had an action-extraction bug; v2 is the reference) |
| `build_relabel_viewer.py` | viewer: https://alfworld-hindsight-relabel.jaade1107.workers.dev |
| `compare_dump_log_probs.py` | diagnostic that found the hindsight attention bug (see below): recomputes with HF the old log probs training stored for hindsight rows |
| `hpg_weight_check.py`, `results/hpg_weight_check/` | offline check of HPG product-over-steps importance weights: replays the precheck episodes (prompts identical, 0 feedback mismatches), scores every turn under g and g' with the base model and the hindsight step-50 checkpoint |
| `speed_test.sh`, `results/speed_test/` | 3-step timing of the speed options (A: 2 envs per actor + skip finished generation + ref not offloaded; B: A + vLLM TP 1) |

Tests (training box): `cd /root/alf/hs && ALFWORLD_DATA=/root/alf/alfworld_data /root/alf/venv/bin/python -m unittest test_precheck_tracker -v`

## Hindsight run 1 (`grpo_alfworld_hindsight_seed0`, stopped at step 50): invalid

Validation 17.2% at step 25 (baseline 13.9%), 15.7% at step 50 (baseline 31.8%). Two bugs in that code, fixed since:

- `compute_response_mask` returns a view of `attention_mask`; masking the hindsight rows' non-action tokens in place
  also removed their thought tokens from the model input (all 2938 dumped hindsight rows), so old/ref log probs and the
  update saw the action right after the prompt. With the full context the action-token ratio pi(a|o,g')/pi(a|o,g) is
  in [0.8, 1.2] for 95% of tokens; training had logged 65%.
- Hindsight rows were appended at the end and kept there by `_balance_batch`, so about 14 of each step's ~38 optimizer
  steps used only hindsight rows.

Current code: rows shuffled before balancing; loss = L_orig + lambda * min(L_H, c) (lambda 0.1, `env.hindsight.loss_coef`;
c = 0.85 quantile of micro-batch L_H over the first 5 steps with hindsight rows); as many optimizer steps per training
step as the original rows alone would give. 2-step smoke: ratio in [0.8, 1.2] 95%, KL 0.004, clipfrac 0.011 / 0.03
(original / hindsight), response length 93.
