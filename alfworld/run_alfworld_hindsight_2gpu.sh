#!/bin/bash
# Hindsight GRPO on ALFWorld: the baseline script (run_alfworld_grpo_2gpu.sh) unchanged, plus
#   - online relabel of all-failed groups (env.hindsight.*, see hindsight.py): DeepSeek-V4-Pro proposes, the state checker
#     accepts; hindsight rows train only <action> tokens with the original-prompt (behavior) log probs as PPO denominator
#   - rollout speed options measured in speed_test.sh run A (system only: 2 envs per Ray actor, no generation for finished envs)
# Usage: bash run_alfworld_hindsight_2gpu.sh <run_name> <seed> [extra hydra overrides...]
set -euo pipefail
RUN_NAME=$1; SEED=$2; shift 2
RUN_DIR=${RUNS_ROOT:-/root/alf/runs}/${RUN_NAME}
mkdir -p "${RUN_DIR}"
cd "$(dirname "${BASH_SOURCE[0]}")"
bash run_alfworld_grpo_2gpu.sh "${RUN_NAME}" "${SEED}" \
    env.hindsight.enable=True \
    env.hindsight.seed=${SEED} \
    env.hindsight.log_path=${RUN_DIR}/hindsight_log.jsonl \
    env.skip_finished_generation=True \
    env.alfworld.train_envs_per_worker=2 \
    env.alfworld.eval_envs_per_worker=4 "$@"
