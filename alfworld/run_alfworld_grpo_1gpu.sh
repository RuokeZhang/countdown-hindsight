#!/bin/bash
# GRPO baseline on ALFWorld (text) with verl-agent, one L40S. Starts from verl-agent's examples/grpo_trainer/run_alfworld.sh;
# every setting that differs from it is marked "# changed:".
# Usage: bash run_alfworld_grpo_1gpu.sh <run_name> <seed> [extra hydra overrides...]
set -euo pipefail
RUN_NAME=$1; SEED=$2; shift 2
VERL_AGENT_DIR=${VERL_AGENT_DIR:-/root/alf/verl-agent}
RUN_DIR=${RUNS_ROOT:-/root/alf/runs}/${RUN_NAME}
mkdir -p "${RUN_DIR}"
source /root/alf/venv/bin/activate
export PATH=/root/alf/venv/bin:$PATH
export ALFWORLD_DATA=${ALFWORLD_DATA:-/root/alf/alfworld_data}
# changed: the repo exports VLLM_ATTENTION_BACKEND=XFORMERS; xformers is not installed with vllm 0.11, so vLLM uses its default (FLASH_ATTN)
export RAY_num_server_call_thread=1                    # changed: fewer threads per Ray process (container allows 7680)
export METRICS_JSONL=${RUN_DIR}/metrics.jsonl            # changed: per-step metrics also written to a file
cd "${VERL_AGENT_DIR}"

num_cpus_per_env_worker=0.1
train_data_size=16
val_data_size=274                                        # changed: 128 -> all 140 valid_seen + 134 valid_unseen games, once each
group_size=8

python3 -m examples.data_preprocess.prepare \
    --mode 'text' \
    --train_data_size $train_data_size \
    --val_data_size $val_data_size

python3 -m verl.trainer.main_ppo \
    algorithm.adv_estimator=grpo \
    data.train_files=$HOME/data/verl-agent/text/train.parquet \
    data.val_files=$HOME/data/verl-agent/text/test.parquet \
    data.train_batch_size=$train_data_size \
    data.val_batch_size=$val_data_size \
    data.max_prompt_length=2048 \
    data.max_response_length=512 \
    data.filter_overlong_prompts=True \
    data.truncation='error' \
    data.return_raw_chat=True \
    actor_rollout_ref.model.path=Qwen/Qwen2.5-1.5B-Instruct \
    actor_rollout_ref.actor.optim.lr=1e-6 \
    actor_rollout_ref.model.use_remove_padding=True \
    actor_rollout_ref.actor.ppo_mini_batch_size=256 \
    actor_rollout_ref.actor.ppo_micro_batch_size_per_gpu=4 `# changed: 32 -> 4 (memory only; one GPU)` \
    actor_rollout_ref.actor.use_kl_loss=True \
    actor_rollout_ref.actor.kl_loss_coef=0.01 \
    actor_rollout_ref.actor.kl_loss_type=low_var_kl \
    actor_rollout_ref.model.enable_gradient_checkpointing=True \
    actor_rollout_ref.actor.fsdp_config.param_offload=False \
    actor_rollout_ref.actor.fsdp_config.optimizer_offload=False \
    actor_rollout_ref.rollout.log_prob_micro_batch_size_per_gpu=4 `# changed: 32 -> 4 (memory only)` \
    actor_rollout_ref.rollout.tensor_model_parallel_size=1 `# changed: 2 -> 1 (one GPU)` \
    actor_rollout_ref.rollout.name=vllm \
    actor_rollout_ref.rollout.gpu_memory_utilization=0.3 `# changed: 0.6 -> 0.3, vLLM shares the one GPU with the FSDP actor (memory only)` \
    actor_rollout_ref.rollout.enable_chunked_prefill=False \
    actor_rollout_ref.rollout.enforce_eager=False \
    actor_rollout_ref.rollout.free_cache_engine=False \
    actor_rollout_ref.rollout.val_kwargs.temperature=0.4 \
    actor_rollout_ref.rollout.val_kwargs.do_sample=True \
    actor_rollout_ref.ref.log_prob_micro_batch_size_per_gpu=4 `# changed: 32 -> 4 (memory only)` \
    actor_rollout_ref.ref.fsdp_config.param_offload=True \
    actor_rollout_ref.actor.use_invalid_action_penalty=True \
    actor_rollout_ref.actor.invalid_action_penalty_coef=0.1 \
    algorithm.use_kl_in_reward=False \
    env.env_name=alfworld/AlfredTWEnv \
    env.seed=${SEED} `# changed: 0 -> the run seed` \
    env.max_steps=50 \
    env.rollout.n=$group_size \
    env.resources_per_worker.num_cpus=$num_cpus_per_env_worker \
    env.alfworld.train_data_path=${ALFWORLD_DATA}/train_subset_240 `# changed: train only on the fixed 240-task subset` \
    env.alfworld.eval_dataset=both `# changed: eval_in_distribution only -> valid_seen and valid_unseen` \
    ray_init.num_cpus=32 `# changed: null (all 128) -> 32, fewer idle Ray workers (thread limit)` \
    trainer.critic_warmup=0 \
    trainer.logger=['console'] `# changed: console+wandb -> console (no wandb account)` \
    trainer.project_name='verl_agent_alfworld' \
    trainer.experiment_name=${RUN_NAME} \
    trainer.n_gpus_per_node=1 `# changed: 2 -> 1` \
    trainer.nnodes=1 \
    trainer.save_freq=-1 \
    trainer.test_freq=25 `# changed: 5 -> 25` \
    trainer.total_epochs=100 `# changed: 150 -> 100 (one step per epoch: 16 groups per step)` \
    trainer.val_before_train=True "$@"
