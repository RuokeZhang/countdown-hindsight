import argparse
import json
import math
import os
import re

from countdown_grader import grade_countdown

COMPARE_STEPS = [0, 50, 100, 150, 200, 250, 300]
DEGENERATION_STEPS = [0, 25, 50, 100, 150, 200, 250, 300]
DIAGNOSTIC_INTERVALS = [(1, 25), (26, 50), (51, 100), (101, 200), (201, 300)]
DIAGNOSTIC_MEANS = ["logp_diff_success_mean", "logp_diff_success_median", "logp_diff_fail_mean", "logp_diff_fail_median", "logp_abs_diff_small_rate"]
DIAGNOSTIC_COUNTS = ["logp_diff_success_count", "logp_diff_fail_count"]
WINDOW_HALF_WIDTH = 5
PAIRED_STEPS = [100, 150, 200, 250, 300]
MILESTONES = [0.05, 0.10, 0.20]
EARLY_WINDOWS = [(1, 25), (26, 50), (51, 75), (76, 100)]
PROMPT_PATTERN = re.compile(r"Using the numbers \[([^\]]*)\], reach the target (\d+)\.")


def load_jsonl_by_step(path):
    return {row["step"]: row for row in map(json.loads, open(path))}


def window_mean(step_stats, center_step, key):
    """Mean of key over training steps center-4 .. center+5 (steps 1..10 for center 0)."""
    first_step = 1 if center_step == 0 else center_step - WINDOW_HALF_WIDTH + 1
    window = [step_stats[s][key] for s in range(first_step, first_step + 2 * WINDOW_HALF_WIDTH) if s in step_stats and step_stats[s].get(key) is not None]
    return sum(window) / len(window) if window else None


def validation_success_by_prompt(run_dir, step):
    """prompt text -> greedy validation success at this step, or None if the run has no dump for the step."""
    path = os.path.join(run_dir, "validation", f"{step}.jsonl")
    if not os.path.exists(path):
        return None
    success_by_prompt = {}
    for row in map(json.loads, open(path)):
        nums_text, target_text = PROMPT_PATTERN.search(row["input"]).groups()
        success_by_prompt[row["input"]] = grade_countdown(row["output"], [int(n) for n in nums_text.split(",")], int(target_text))["success"]
    return success_by_prompt


def format_percent(value):
    return "—" if value is None else f"{100 * value:.1f}%"


def format_number(value):
    return "—" if value is None else f"{value:.1f}"


def format_entropy(value):
    return "—" if value is None else f"{value:.3f}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs="+", required=True, help="name=run_dir pairs")
    parser.add_argument("--out", required=True)
    parser.add_argument("--diagnostic_runs", nargs="*", default=[], help="name=run_dir pairs of hindsight runs for the log-prob table")
    parser.add_argument("--seed_groups", nargs="*", default=[], help="arm=run_dir_seed0,run_dir_seed1,... for the multi-seed validation table")
    parser.add_argument("--paired_groups", nargs=2, default=None, metavar=("ARM", "REFERENCE"), help="two --seed_groups arms compared problem by problem, seed by seed")
    parser.add_argument("--compare_steps", type=int, nargs="+", default=COMPARE_STEPS, help="validation steps shown in the main and multi-seed tables")
    parser.add_argument("--paired_steps", type=int, nargs="+", default=PAIRED_STEPS)
    parser.add_argument("--milestones", action="store_true", help="add first-step-to-5/10/20%% validation and first-100-steps signal tables")
    args = parser.parse_args()

    runs = [run.split("=", 1) for run in args.runs]
    loaded = {name: (load_jsonl_by_step(os.path.join(run_dir, "validation_stats.jsonl")), load_jsonl_by_step(os.path.join(run_dir, "step_stats.jsonl"))) for name, run_dir in runs}

    lines = [
        "# Countdown run comparison",
        "",
        f"Validation = greedy success on the 512-problem val set. Training columns are means over steps center-{WINDOW_HALF_WIDTH - 1}..center+{WINDOW_HALF_WIDTH} (steps 1-10 for step 0), computed against the original target.",
        "",
        "| step | run | val all | val 3 nums | val 4 nums | train format valid | too-many-lines fails / step | mixed groups |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for step in args.compare_steps:
        for name, _ in runs:
            validation, step_stats = loaded[name]
            val = validation.get(step, {})
            lines.append(
                f"| {step} | {name} | {format_percent(val.get('val_greedy_success_all'))} | {format_percent(val.get('val_greedy_success_3'))} | "
                f"{format_percent(val.get('val_greedy_success_4'))} | {format_percent(window_mean(step_stats, step, 'parse_ok_rate'))} | "
                f"{format_number(window_mean(step_stats, step, 'parse_fail_too_many_lines'))} | {format_percent(window_mean(step_stats, step, 'mixed_group_rate'))} |"
            )
    lines += [
        "",
        "## Degeneration signals",
        "",
        "Same windows as above. \"fail claims target\" = share of failed responses whose last line ends in \"= <original target>\". "
        "Hindsight positives/negatives per step: per-sample runs count the samples normalized together in the step's new uid; "
        "group runs count reward-1 / reward-0 samples inside rewritten groups.",
        "",
        "| step | run | entropy | mixed groups | train fail claims target | val fail claims target | hindsight positives / step | hindsight negatives / step |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for step in DEGENERATION_STEPS:
        for name, _ in runs:
            validation, step_stats = loaded[name]
            lines.append(
                f"| {step} | {name} | {format_entropy(window_mean(step_stats, step, 'entropy'))} | {format_percent(window_mean(step_stats, step, 'mixed_group_rate'))} | "
                f"{format_percent(window_mean(step_stats, step, 'fail_claims_target_rate'))} | {format_percent(validation.get(step, {}).get('val_fail_claims_target_rate'))} | "
                f"{format_number(window_mean(step_stats, step, 'hindsight_positive_samples'))} | {format_number(window_mean(step_stats, step, 'hindsight_negative_samples'))} |"
            )
    seed_groups = {name: dirs.split(",") for name, dirs in (group.split("=", 1) for group in args.seed_groups)}
    if seed_groups:
        lines += [
            "",
            "## Validation across seeds",
            "",
            "Mean over the seeds that have reached the step; per-seed values in seed order (— = not reached yet).",
            "",
            "| step | arm | seeds | mean all | mean 3 nums | mean 4 nums | per-seed all |",
            "|---|---|---|---|---|---|---|",
        ]
        for step in args.compare_steps:
            for name, dirs in seed_groups.items():
                rows = [load_jsonl_by_step(os.path.join(d, "validation_stats.jsonl")).get(step) if os.path.exists(os.path.join(d, "validation_stats.jsonl")) else None for d in dirs]
                present = [row for row in rows if row]
                means = [sum(row[key] for row in present) / len(present) if present and all(key in row for row in present) else None for key in ("val_greedy_success_all", "val_greedy_success_3", "val_greedy_success_4")]
                per_seed = ", ".join(format_percent(row["val_greedy_success_all"]) if row else "—" for row in rows)
                lines.append(f"| {step} | {name} | {len(present)} | " + " | ".join(format_percent(m) for m in means) + f" | {per_seed} |")
    if args.paired_groups:
        arm, reference = args.paired_groups
        lines += [
            "",
            f"## Problem-by-problem validation: {arm} vs {reference} (same seed)",
            "",
            f"Counts over the 512 validation problems. only {arm} = {arm} solves it and {reference} does not.",
            "",
            f"| step | seed | only {arm} | only {reference} | both | neither |",
            "|---|---|---|---|---|---|",
        ]
        for step in args.paired_steps:
            for seed_index, (arm_dir, reference_dir) in enumerate(zip(seed_groups[arm], seed_groups[reference])):
                arm_success, reference_success = validation_success_by_prompt(arm_dir, step), validation_success_by_prompt(reference_dir, step)
                if arm_success is None or reference_success is None:
                    continue
                assert arm_success.keys() == reference_success.keys(), "validation sets differ"
                only_arm = sum(arm_success[p] and not reference_success[p] for p in arm_success)
                only_reference = sum(reference_success[p] and not arm_success[p] for p in arm_success)
                both = sum(arm_success[p] and reference_success[p] for p in arm_success)
                lines.append(f"| {step} | {seed_index} | {only_arm} | {only_reference} | {both} | {len(arm_success) - only_arm - only_reference - both} |")
    if args.milestones:
        lines += [
            "",
            "## First validation step reaching a success level",
            "",
            "Earliest validated step whose greedy val success is at least the level (— = never reached among the validated steps).",
            "",
            "| run | last validated step | " + " | ".join(f"first step >= {100 * level:.0f}%" for level in MILESTONES) + " |",
            "|---|---|" + "---|" * len(MILESTONES),
        ]
        for name, _ in runs:
            validation = loaded[name][0]
            first_steps = [next((step for step in sorted(validation) if validation[step]["val_greedy_success_all"] >= level), None) for level in MILESTONES]
            lines.append(f"| {name} | {max(validation) if validation else '—'} | " + " | ".join("—" if step is None else str(step) for step in first_steps) + " |")
        lines += [
            "",
            "## First 100 steps: mixed groups and hindsight samples",
            "",
            "Means over every training step in the interval. Hindsight positives/negatives per step as in the degeneration table.",
            "",
            "| steps | run | mixed groups | hindsight positives / step | hindsight negatives / step |",
            "|---|---|---|---|---|",
        ]
        for first_step, last_step in EARLY_WINDOWS:
            for name, _ in runs:
                step_stats = loaded[name][1]
                interval_mean = lambda key: (lambda values: sum(values) / len(values) if values else None)([step_stats[s][key] for s in range(first_step, last_step + 1) if s in step_stats and step_stats[s].get(key) is not None])
                lines.append(f"| {first_step}-{last_step} | {name} | {format_percent(interval_mean('mixed_group_rate'))} | {format_number(interval_mean('hindsight_positive_samples'))} | {format_number(interval_mean('hindsight_negative_samples'))} |")
    split_classes = ["positive", "negative_valid", "negative_parse", "negative_arithmetic", "negative_usage"]
    split_runs = [name for name, _ in runs if any("hindsight_negative_valid_samples" in row for row in loaded[name][1].values())]
    if split_runs:
        lines += [
            "",
            "## Per-sample-split runs: pooled samples per step by class",
            "",
            "Window means as above. negative_valid = valid relabel candidate kept on its original prompt with reward 0.",
            "",
            "| step | run | " + " | ".join(split_classes) + " |",
            "|---|---|" + "---|" * len(split_classes),
        ]
        for step in DEGENERATION_STEPS:
            for name in split_runs:
                step_stats = loaded[name][1]
                lines.append(f"| {step} | {name} | " + " | ".join(format_number(window_mean(step_stats, step, f"hindsight_{cls}_samples")) for cls in split_classes) + " |")
    for diagnostic_name, diagnostic_dir in (run.split("=", 1) for run in args.diagnostic_runs):
        step_stats = load_jsonl_by_step(os.path.join(diagnostic_dir, "step_stats.jsonl"))
        lines += [
            "",
            f"## Hindsight log-prob diagnostic ({diagnostic_name}): logp_new - logp_orig (sum over response tokens)",
            "",
            "Per-step summaries averaged over the steps in each interval (steps with no relabeled sample of a kind are skipped); counts are totals.",
            "",
            "| steps | diff mean (new-target success) | diff median (success) | diff mean (new-target fail) | diff median (fail) | share \\|diff\\| < 0.05 | success samples | fail samples |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for first_step, last_step in DIAGNOSTIC_INTERVALS:
            rows = [step_stats[s] for s in range(first_step, last_step + 1) if s in step_stats and f"hindsight/{DIAGNOSTIC_COUNTS[0]}" in step_stats[s]]
            means = []
            for key in DIAGNOSTIC_MEANS:
                values = [row[f"hindsight/{key}"] for row in rows if row.get(f"hindsight/{key}") is not None and not math.isnan(row[f"hindsight/{key}"])]
                means.append(sum(values) / len(values) if values else None)
            counts = [sum(row[f"hindsight/{key}"] for row in rows) for key in DIAGNOSTIC_COUNTS]
            formatted = [format_percent(value) if key == "logp_abs_diff_small_rate" else ("—" if value is None else f"{value:.3f}") for key, value in zip(DIAGNOSTIC_MEANS, means)]
            lines.append(f"| {first_step}-{last_step} | " + " | ".join(formatted) + f" | {counts[0]} | {counts[1]} |")

    with open(args.out, "w") as out_file:
        out_file.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
