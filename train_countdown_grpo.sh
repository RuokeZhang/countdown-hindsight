#!/bin/bash
# Usage: bash train_countdown_grpo.sh --seed 0 --lr 1e-6 --total_steps 400 --run_name grpo_seed0 [extra hydra overrides...]
#   --reward binary|validbonus   reward function (default binary = baseline)
#   --sampler none|hindsight     hindsight relabels all-failed groups in place (default none = baseline)
#   --relabel_p P                relabel probability for --sampler hindsight (default 1.0)
set -euo pipefail

SEED=0
LR=1e-6
TOTAL_STEPS=400
SAVE_FREQ=50
TEST_FREQ=50
RUN_NAME=""
REWARD=binary
SAMPLER=none
RELABEL_P=1.0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --seed) SEED="$2"; shift 2 ;;
        --lr) LR="$2"; shift 2 ;;
        --total_steps) TOTAL_STEPS="$2"; shift 2 ;;
        --save_freq) SAVE_FREQ="$2"; shift 2 ;;
        --test_freq) TEST_FREQ="$2"; shift 2 ;;
        --run_name) RUN_NAME="$2"; shift 2 ;;
        --reward) REWARD="$2"; shift 2 ;;
        --sampler) SAMPLER="$2"; shift 2 ;;
        --relabel_p) RELABEL_P="$2"; shift 2 ;;
        *) break ;;
    esac
done
if [[ "${REWARD}" == binary && "${SAMPLER}" == none ]]; then
    RUN_NAME=${RUN_NAME:-grpo_binary_seed${SEED}_lr${LR}}
else
    RUN_NAME=${RUN_NAME:-grpo_${REWARD}_${SAMPLER}_seed${SEED}_lr${LR}}
fi
MODEL_PATH=Qwen/Qwen2.5-1.5B-Instruct

CODE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
VERL_DIR=${VERL_DIR:-/root/work/verl}
DATA_DIR=${DATA_DIR:-/root/work/data/countdown_v3}
RUN_DIR=${RUNS_ROOT:-/root/work/runs}/${RUN_NAME}
mkdir -p "${RUN_DIR}"

case "${REWARD}" in
    binary) REWARD_FILE=${CODE_DIR}/countdown_reward.py ;;
    validbonus) REWARD_FILE=${CODE_DIR}/countdown_reward_validbonus.py ;;
    *) echo "unknown --reward ${REWARD}" >&2; exit 1 ;;
esac
MODE_ARGS=()
case "${SAMPLER}" in
    none) ;;
    hindsight)
        # Relabeled samples get a new prompt, so their rollout log probs would be stale; disable them for every sample.
        MODE_ARGS=(
            trainer.v1.sampler.custom_sampler.path=${CODE_DIR}/countdown_hindsight_sampler.py
            trainer.v1.sampler.custom_sampler.name=HindsightRelabelReplayBuffer
            +trainer.v1.sampler.sampler_kwargs.seed=${SEED}
            +trainer.v1.sampler.sampler_kwargs.relabel_probability=${RELABEL_P}
            +trainer.v1.sampler.sampler_kwargs.relabel_log_dir=${RUN_DIR}/relabel_log
            +trainer.v1.sampler.sampler_kwargs.model_path=${MODEL_PATH}
            +trainer.v1.sampler.sampler_kwargs.logprob_diagnostic=True
            actor_rollout_ref.rollout.calculate_log_probs=False
            algorithm.rollout_correction.bypass_mode=False
        )
        ;;
    *) echo "unknown --sampler ${SAMPLER}" >&2; exit 1 ;;
esac

export PATH=${VERL_DIR}/.venv/bin:${PATH}
# The file logger opens its output with "wb", so each launch (including resumes) gets its own metrics file.
export VERL_FILE_LOGGER_PATH=${RUN_DIR}/metrics_$(date +%Y%m%d_%H%M%S).jsonl

python -m verl.trainer.main_ppo \
    algorithm.adv_estimator=grpo \
    algorithm.norm_adv_by_std_in_grpo=True \
    algorithm.use_kl_in_reward=False \
    data.train_files=${DATA_DIR}/train.parquet \
    data.val_files=${DATA_DIR}/val.parquet \
    data.train_batch_size=64 \
    data.max_prompt_length=256 \
    data.max_response_length=64 \
    data.filter_overlong_prompts=True \
    data.truncation=error \
    data.shuffle=True \
    data.seed=${SEED} \
    actor_rollout_ref.model.path=${MODEL_PATH} \
    actor_rollout_ref.model.use_remove_padding=False \
    +actor_rollout_ref.model.override_config.attn_implementation=sdpa \
    actor_rollout_ref.model.enable_gradient_checkpointing=True \
    actor_rollout_ref.actor.optim.lr=${LR} \
    actor_rollout_ref.actor.ppo_mini_batch_size=64 \
    actor_rollout_ref.actor.ppo_epochs=1 \
    actor_rollout_ref.actor.ppo_micro_batch_size_per_gpu=16 \
    actor_rollout_ref.actor.use_kl_loss=False \
    actor_rollout_ref.actor.entropy_coeff=0 \
    actor_rollout_ref.actor.data_loader_seed=${SEED} \
    actor_rollout_ref.actor.fsdp_config.seed=${SEED} \
    actor_rollout_ref.actor.fsdp_config.param_offload=False \
    actor_rollout_ref.actor.fsdp_config.optimizer_offload=False \
    actor_rollout_ref.rollout.name=vllm \
    actor_rollout_ref.rollout.tensor_model_parallel_size=1 \
    actor_rollout_ref.rollout.gpu_memory_utilization=0.3 \
    actor_rollout_ref.rollout.n=8 \
    actor_rollout_ref.rollout.temperature=1.0 \
    actor_rollout_ref.rollout.top_p=1.0 \
    actor_rollout_ref.rollout.seed=${SEED} \
    actor_rollout_ref.rollout.log_prob_micro_batch_size_per_gpu=16 \
    actor_rollout_ref.rollout.val_kwargs.do_sample=False \
    actor_rollout_ref.rollout.val_kwargs.temperature=0 \
    actor_rollout_ref.rollout.val_kwargs.n=1 \
    reward.custom_reward_function.path=${REWARD_FILE} \
    reward.custom_reward_function.name=compute_score \
    trainer.logger='["console","file"]' \
    trainer.project_name=countdown_grpo \
    trainer.experiment_name=${RUN_NAME} \
    trainer.n_gpus_per_node=1 \
    trainer.nnodes=1 \
    trainer.total_training_steps=${TOTAL_STEPS} \
    trainer.save_freq=${SAVE_FREQ} \
    trainer.test_freq=${TEST_FREQ} \
    trainer.val_before_train=True \
    trainer.resume_mode=auto \
    trainer.critic_warmup=0 \
    trainer.default_local_dir=${RUN_DIR}/checkpoints \
    trainer.rollout_data_dir=${RUN_DIR}/rollouts \
    trainer.validation_data_dir=${RUN_DIR}/validation \
    "${MODE_ARGS[@]+"${MODE_ARGS[@]}"}" \
    "$@" 2>&1 | tee -a "${RUN_DIR}/train.log"
