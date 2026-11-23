"""One rollout step from the initial model on a training parquet (no update): N problems x 8 samples at temperature 1.

Reports the sampling success rate, the share of mixed groups, and the share of responses in all-failed groups that are
hindsight relabel candidates (valid equations whose own value lies in the relabel target range), as arm E defines them.
"""
import argparse
import json

import pandas as pd
from vllm import LLM, SamplingParams

from countdown_grader import grade_countdown
from countdown_hindsight import TARGET_MAX, TARGET_MIN


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train_parquet", required=True)
    parser.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--num_problems", type=int, default=64)
    parser.add_argument("--samples_per_problem", type=int, default=8)
    parser.add_argument("--max_tokens", type=int, default=64)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out_json", required=True)
    args = parser.parse_args()

    frame = pd.read_parquet(args.train_parquet).sample(n=args.num_problems, random_state=args.seed)
    llm = LLM(model=args.model, seed=args.seed, gpu_memory_utilization=0.5)
    sampling = SamplingParams(n=args.samples_per_problem, temperature=1.0, top_p=1.0, max_tokens=args.max_tokens, seed=args.seed)
    outputs = llm.chat([list(prompt) for prompt in frame["prompt"]], sampling)

    total_samples = successes = mixed_groups = all_fail_groups = truncated = 0
    all_fail_responses = all_fail_candidates = 0
    stop_counts = {}
    for extra_info, output in zip(frame["extra_info"], outputs):
        nums, target = list(extra_info["nums"]), int(extra_info["target"])
        grades = [grade_countdown(completion.text, nums, target) for completion in output.outputs]
        truncated += sum(completion.finish_reason == "length" for completion in output.outputs)
        group_successes = sum(grade["success"] for grade in grades)
        total_samples += len(grades)
        successes += group_successes
        for grade in grades:
            stop_counts[grade["stopped_at"] or "success"] = stop_counts.get(grade["stopped_at"] or "success", 0) + 1
        if 0 < group_successes < len(grades):
            mixed_groups += 1
        if group_successes == 0:
            all_fail_groups += 1
            all_fail_responses += len(grades)
            all_fail_candidates += sum(grade["relabelable"] and TARGET_MIN <= grade["final_value"] <= TARGET_MAX for grade in grades)

    report = {
        "train_parquet": args.train_parquet,
        "problems": args.num_problems,
        "samples_per_problem": args.samples_per_problem,
        "max_tokens": args.max_tokens,
        "success_rate": successes / total_samples,
        "mixed_group_rate": mixed_groups / args.num_problems,
        "all_fail_group_rate": all_fail_groups / args.num_problems,
        "relabel_candidate_share_in_all_fail_groups": all_fail_candidates / all_fail_responses if all_fail_responses else None,
        "truncated_rate": truncated / total_samples,
        "stop_stage_shares": {stage: count / total_samples for stage, count in sorted(stop_counts.items())},
    }
    print(json.dumps(report, indent=2))
    with open(args.out_json, "w") as out_file:
        json.dump(report, out_file, indent=2)


if __name__ == "__main__":
    main()
