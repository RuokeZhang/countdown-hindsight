#!/bin/bash
# Speed test: 3 training steps each, no validation. A = system-only optimizations with TP=2; B = A + vLLM TP=1 (one engine per GPU).
export ALFWORLD_DATA=/root/alf/alfworld_data PATH=/root/alf/venv/bin:$PATH
STATUS=/root/alf/speed.status
cd /root/alf/hs
COMMON="trainer.total_epochs=3 trainer.val_before_train=False trainer.test_freq=-1 env.skip_finished_generation=True env.alfworld.train_envs_per_worker=2 env.alfworld.eval_envs_per_worker=4 actor_rollout_ref.ref.fsdp_config.param_offload=False"
echo "START A $(date -u +%H:%M:%S)" >> $STATUS
RUNS_ROOT=/root/alf/speed_runs bash run_alfworld_grpo_2gpu.sh speed_A 0 $COMMON > /root/alf/speed_A.log 2>&1
echo "EXIT A $? $(date -u +%H:%M:%S)" >> $STATUS
ray stop --force > /dev/null 2>&1
echo "START B $(date -u +%H:%M:%S)" >> $STATUS
RUNS_ROOT=/root/alf/speed_runs bash run_alfworld_grpo_2gpu.sh speed_B 0 $COMMON actor_rollout_ref.rollout.tensor_model_parallel_size=1 > /root/alf/speed_B.log 2>&1
echo "EXIT B $? $(date -u +%H:%M:%S)" >> $STATUS
