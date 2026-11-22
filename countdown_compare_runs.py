import argparse
import json
import math
import os

COMPARE_STEPS = [0, 50, 100, 150, 200, 250, 300]
DIAGNOSTIC_INTERVALS = [(1, 25), (26, 50), (51, 100), (101, 200), (201, 300)]
DIAGNOSTIC_MEANS = ["logp_diff_success_mean", "logp_diff_success_median", "logp_diff_fail_mean", "logp_diff_fail_median", "logp_abs_diff_small_rate"]
DIAGNOSTIC_COUNTS = ["logp_diff_success_count", "logp_diff_fail_count"]
WINDOW_HALF_WIDTH = 5


def load_jsonl_by_step(path):
    return {row["step"]: row for row in map(json.loads, open(path))}


def window_mean(step_stats, center_step, key):
    """Mean of key over training steps center-4 .. center+5 (steps 1..10 for center 0)."""
    first_step = 1 if center_step == 0 else center_step - WINDOW_HALF_WIDTH + 1
    window = [step_stats[s][key] for s in range(first_step, first_step + 2 * WINDOW_HALF_WIDTH) if s in step_stats]
    return sum(window) / len(window) if window else None


def format_percent(value):
    return "—" if value is None else f"{100 * value:.1f}%"


def format_number(value):
    return "—" if value is None else f"{value:.1f}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs="+", required=True, help="name=run_dir pairs")
    parser.add_argument("--out", required=True)
    parser.add_argument("--diagnostic_run", default=None, help="run_dir of the hindsight run for the log-prob table")
    args = parser.parse_args()

    runs = [run.split("=", 1) for run in args.runs]
    loaded = {name: (load_jsonl_by_step(os.path.join(run_dir, "validation_stats.jsonl")), load_jsonl_by_step(os.path.join(run_dir, "step_stats.jsonl"))) for name, run_dir in runs}

    lines = [
        "# Countdown: baseline vs hindsight vs valid-bonus",
        "",
        f"Validation = greedy success on the 512-problem val set. Training columns are means over steps center-{WINDOW_HALF_WIDTH - 1}..center+{WINDOW_HALF_WIDTH} (steps 1-10 for step 0), computed against the original target.",
        "",
        "| step | run | val all | val 3 nums | val 4 nums | train format valid | too-many-lines fails / step | mixed groups |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for step in COMPARE_STEPS:
        for name, _ in runs:
            validation, step_stats = loaded[name]
            val = validation.get(step, {})
            lines.append(
                f"| {step} | {name} | {format_percent(val.get('val_greedy_success_all'))} | {format_percent(val.get('val_greedy_success_3'))} | "
                f"{format_percent(val.get('val_greedy_success_4'))} | {format_percent(window_mean(step_stats, step, 'parse_ok_rate'))} | "
                f"{format_number(window_mean(step_stats, step, 'parse_fail_too_many_lines'))} | {format_percent(window_mean(step_stats, step, 'mixed_group_rate'))} |"
            )
    if args.diagnostic_run:
        step_stats = load_jsonl_by_step(os.path.join(args.diagnostic_run, "step_stats.jsonl"))
        lines += [
            "",
            "## Hindsight log-prob diagnostic: logp_new - logp_orig (sum over response tokens)",
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
