#!/bin/bash
# On the 2x A100 box: precheck test (2 tasks) -> 1-step GRPO smoke -> full precheck + report -> baseline seed 0 -> seed 1.
# Stops at the first failing stage. Status lines go to /root/alf/chain.status.
set -uo pipefail
HS=/root/alf/hs
STATUS=/root/alf/chain.status
export ALFWORLD_DATA=/root/alf/alfworld_data PATH=/root/alf/venv/bin:$PATH VERL_AGENT_DIR=/root/alf/verl-agent
log() { echo "$1 $(date -u +%Y-%m-%dT%H:%M:%S)" >> $STATUS; }
run_stage() {
    local name=$1; shift
    log "START $name: $*"
    "$@" > /root/alf/$name.log 2>&1
    local code=$?
    log "EXIT $name $code"
    if [ $code != 0 ]; then log "STOP_AT $name"; exit 1; fi
}
cd $HS
run_stage precheck_test python precheck.py --subset_list train_subset_240.txt --limit_tasks 2 --out_dir /root/alf/precheck_test
run_stage smoke env RUNS_ROOT=/root/alf/smoke_runs bash run_alfworld_grpo_2gpu.sh smoke_2gpu 0 trainer.total_epochs=1 trainer.val_before_train=False trainer.test_freq=-1
ray stop --force > /dev/null 2>&1
run_stage precheck python precheck.py --subset_list train_subset_240.txt --out_dir /root/alf/precheck
run_stage precheck_report python precheck_report.py --episodes /root/alf/precheck/episodes.jsonl --out_md /root/alf/precheck/precheck_summary.md --out_examples /root/alf/precheck/failed_trajectories.md
ray stop --force > /dev/null 2>&1
run_stage baseline_seed0 bash run_alfworld_grpo_2gpu.sh grpo_alfworld_seed0 0
ray stop --force > /dev/null 2>&1
run_stage baseline_seed1 bash run_alfworld_grpo_2gpu.sh grpo_alfworld_seed1 1
log CHAIN_DONE
