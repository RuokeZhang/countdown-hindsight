import argparse
import glob
import json
import os
import re
from collections import defaultdict

import pandas as pd
import torch
from verl.trainer.ppo.core_algos import compute_grpo_outcome_advantage

from countdown_grader import LINE_PATTERN, grade_countdown

STOP_STAGES = ["parse", "arithmetic", "usage", "target"]
PROMPT_PATTERN = re.compile(r"Using the numbers \[([^\]]*)\], reach the target (\d+)\.")


def load_problem_ids(train_parquet):
    train_frame = pd.read_parquet(train_parquet, columns=["extra_info"])
    return {tuple(sorted(int(n) for n in info["nums"])): int(info["problem_id"]) for info in train_frame["extra_info"]}


def training_reward_from_grade(grade, reward_type):
    if grade["success"]:
        return 1.0
    if reward_type == "validbonus" and grade["stopped_at"] == "target":
        return 0.1
    return 0.0


def has_too_many_lines(output, num_count):
    lines = [line.strip() for line in output.strip().split("\n")]
    return len(lines) > num_count - 1 and all(LINE_PATTERN.match(line) for line in lines)


def load_original_targets(run_dir, step):
    """uid -> original target for groups the hindsight sampler relabeled at this step (empty for other runs)."""
    relabel_path = os.path.join(run_dir, "relabel_log", f"{step}.jsonl")
    if not os.path.exists(relabel_path):
        return {}
    return {row["uid"]: int(row["original_target"]) for row in map(json.loads, open(relabel_path))}


def grade_step(rollout_rows, problem_id_by_multiset, original_target_by_uid, reward_type):
    records = []
    for row in rollout_rows:
        nums_text, target_text = PROMPT_PATTERN.search(row["input"]).groups()
        nums = [int(n) for n in nums_text.split(",")]
        group_id = row["uid"].split("_")[0]
        training_target = int(target_text)
        original_target = original_target_by_uid.get(group_id, training_target)
        grade = grade_countdown(row["output"], nums, original_target)
        training_grade = grade if original_target == training_target else grade_countdown(row["output"], nums, training_target)
        records.append({
            **grade,
            "group_id": group_id,
            "problem_id": problem_id_by_multiset.get(tuple(sorted(nums))),
            "nums": nums,
            "target": original_target,
            "training_target": training_target,
            "relabeled": group_id in original_target_by_uid,
            "output": row["output"],
            "score": float(row["score"]),
            "expected_training_reward": training_reward_from_grade(training_grade, reward_type),
            "too_many_lines": grade["stopped_at"] == "parse" and has_too_many_lines(row["output"], len(nums)),
        })
    group_ids = sorted({r["group_id"] for r in records})
    group_index = {group_id: i for i, group_id in enumerate(group_ids)}
    scores = torch.tensor([[r["score"]] for r in records])
    advantages, _ = compute_grpo_outcome_advantage(
        token_level_rewards=scores,
        response_mask=torch.ones_like(scores),
        index=[group_index[r["group_id"]] for r in records],
        norm_adv_by_std_in_grpo=True,
    )
    for record, advantage in zip(records, advantages[:, 0].tolist()):
        record["advantage"] = advantage
    return records


def summarize_step(records):
    """Success-based metrics use the original target; reward/advantage checks use the actual training score."""
    success_by_group = defaultdict(list)
    training_scores_by_group = defaultdict(list)
    for record in records:
        success_by_group[record["group_id"]].append(float(record["success"]))
        training_scores_by_group[record["group_id"]].append(record["score"])
    failed = [r for r in records if not r["success"]]
    zero_score_groups = {g for g, s in training_scores_by_group.items() if max(s) == 0.0}
    zero_score_advantages = [r["advantage"] for r in records if r["group_id"] in zero_score_groups]
    return {
        "num_samples": len(records),
        "num_groups": len(success_by_group),
        "mean_reward": sum(r["success"] for r in records) / len(records),
        "mean_training_reward": sum(r["score"] for r in records) / len(records),
        "reward_values": sorted({round(r["score"], 6) for r in records}),
        "regraded_matches_reward": all(abs(r["expected_training_reward"] - r["score"]) < 1e-6 for r in records),
        "all_fail_group_rate": sum(max(s) == 0.0 for s in success_by_group.values()) / len(success_by_group),
        "mixed_group_rate": sum(0.0 < sum(s) < len(s) for s in success_by_group.values()) / len(success_by_group),
        "all_success_group_rate": sum(min(s) == 1.0 for s in success_by_group.values()) / len(success_by_group),
        "parse_ok_rate": sum(r["stopped_at"] != "parse" for r in records) / len(records),
        **{f"fail_stop_{stage}": sum(r["stopped_at"] == stage for r in failed) / max(len(failed), 1) for stage in STOP_STAGES},
        "parse_fail_too_many_lines": sum(r["too_many_lines"] for r in records),
        "relabelable_rate_of_failed": sum(r["relabelable"] for r in failed) / max(len(failed), 1),
        "relabeled_groups": len({r["group_id"] for r in records if r["relabeled"]}),
        "max_abs_advantage_in_all_fail_groups": max((abs(a) for a in zero_score_advantages), default=0.0),
        "offline_advantage_max": max(r["advantage"] for r in records),
        "offline_advantage_min": min(r["advantage"] for r in records),
    }


def load_logged_metrics(run_dir):
    logged_by_step = {}
    for path in sorted(glob.glob(os.path.join(run_dir, "metrics_*.jsonl"))):
        for line in open(path):
            entry = json.loads(line)
            logged_by_step.setdefault(entry["step"], {}).update(entry["data"])
    return logged_by_step


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run_dir", required=True)
    parser.add_argument("--train_parquet", default="/root/work/data/countdown_v3/train.parquet")
    parser.add_argument("--reward_type", choices=["binary", "validbonus"], default="binary")
    args = parser.parse_args()

    problem_id_by_multiset = load_problem_ids(args.train_parquet)
    logged_by_step = load_logged_metrics(args.run_dir)
    rollout_paths = [p for p in glob.glob(os.path.join(args.run_dir, "rollouts", "*.jsonl")) if re.fullmatch(r"\d+\.jsonl", os.path.basename(p))]
    rollout_paths.sort(key=lambda p: int(os.path.basename(p).split(".")[0]))

    step_summaries = []
    for path in rollout_paths:
        step = int(os.path.basename(path).split(".")[0])
        records = grade_step([json.loads(line) for line in open(path)], problem_id_by_multiset, load_original_targets(args.run_dir, step), args.reward_type)
        logged = logged_by_step.get(step, {})
        summary = {
            "step": step,
            **summarize_step(records),
            "logged_advantage_max": logged.get("critic/advantages/max"),
            "logged_advantage_min": logged.get("critic/advantages/min"),
            "logged_score_mean": logged.get("critic/score/mean"),
            "entropy": logged.get("actor/entropy"),
            "response_length_mean": logged.get("response_length/mean"),
            "pg_loss": logged.get("actor/pg_loss"),
            "grad_norm": logged.get("actor/grad_norm"),
            "timing_rollout_s": logged.get("timing_s/gen"),
            "timing_old_log_prob_s": logged.get("timing_s/old_log_prob"),
            "timing_update_actor_s": logged.get("timing_s/update_actor"),
            "timing_update_weights_s": logged.get("timing_s/update_weights"),
            "timing_step_s": logged.get("timing_s/step"),
            "timing_logprob_diagnostic_s": logged.get("hindsight/diagnostic_seconds"),
            **{key: value for key, value in logged.items() if key.startswith("hindsight/")},
            "problem_ids": sorted({r["problem_id"] for r in records}),
        }
        step_summaries.append(summary)
        with open(os.path.join(args.run_dir, "rollouts", f"{step}.graded.jsonl"), "w") as graded_file:
            for record in records:
                graded_file.write(json.dumps(record) + "\n")

    validation_rows = []
    for step, logged in sorted(logged_by_step.items()):
        three = logged.get("val-core/countdown_3/acc/mean@1")
        four = logged.get("val-core/countdown_4/acc/mean@1")
        if three is not None and four is not None:
            validation_rows.append({"step": step, "val_greedy_success_all": (three + four) / 2, "val_greedy_success_3": three, "val_greedy_success_4": four})

    with open(os.path.join(args.run_dir, "step_stats.jsonl"), "w") as stats_file:
        for summary in step_summaries:
            stats_file.write(json.dumps(summary) + "\n")
    with open(os.path.join(args.run_dir, "validation_stats.jsonl"), "w") as validation_file:
        for row in validation_rows:
            validation_file.write(json.dumps(row) + "\n")

    columns = ["step", "mean_reward", "all_fail_group_rate", "mixed_group_rate", "parse_ok_rate"] + [f"fail_stop_{s}" for s in STOP_STAGES] + ["entropy", "timing_rollout_s", "timing_update_actor_s", "timing_step_s"]
    print(pd.DataFrame(step_summaries)[columns].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    if validation_rows:
        print(pd.DataFrame(validation_rows).to_string(index=False, float_format=lambda v: f"{v:.4f}"))


if __name__ == "__main__":
    main()
