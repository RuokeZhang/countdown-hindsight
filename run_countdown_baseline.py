import argparse
import json
import os
import random
import re
import time
from collections import Counter

from datasets import load_dataset
from transformers import AutoTokenizer
from vllm import LLM, SamplingParams

from countdown_grader import LINE_PATTERN, grade_countdown

PROMPT_TEMPLATE = """Using the numbers {nums}, reach the target {target}.
Rules:
- Use each number exactly once.
- Only +, -, *, / are allowed.
- Write one equation per line, in the form "a op b = c".
- Each later line may use results from earlier lines.
- The result of the last line must be the target.
- Output only the equations, nothing else.
Example for numbers [2, 3, 4, 6] and target 36:
6 * 4 = 24
24 / 2 = 12
12 * 3 = 36"""

PROMPT_TEMPLATE_V2 = """Using the numbers {nums}, reach the target {target}.
Rules:
- Use each number exactly once.
- Only +, -, *, / are allowed.
- Write exactly {num_lines} lines. Each line has the form "a op b = c" with exactly one operator.
- a and b must each be an unused number from the list or the result of an earlier line.
- All numbers are integers. Division must divide evenly. No decimals, no parentheses.
- The result of the last line must be the target.
- Output only the equations, nothing else.
Example for numbers {example_nums} and target {example_target}:
{example_lines}"""

PROMPT_TEMPLATE_V3 = """Using the numbers {nums}, reach the target {target}.
Rules:
- Use each number exactly once.
- Only +, -, *, / are allowed.
- Write exactly {num_lines} lines, one equation per line, in the form "a op b = c".
- Each later line may use results from earlier lines.
- The result of the last line must be the target.
- Output only the equations, nothing else.
Example for numbers {example_nums} and target {example_target}:
{example_lines}"""

PROMPT_TEMPLATE_V4 = """Using the numbers {nums}, reach the target {target}.
Rules:
- Use each number exactly once.
- Only +, -, *, / are allowed.
- Write exactly {num_lines} lines. Each line has the form "a op b = c" with exactly one operator.
- a and b must each be an unused number from the list or the result of an earlier line.
- All numbers are integers. Division must divide evenly. No decimals, no parentheses, no commas in numbers.
- The result of the last line must be the target.
- Output only the equations, nothing else.
{examples}"""

V2_EXAMPLES_BY_SIZE = {
    3: ([4, 9, 7], 29, "4 * 9 = 36\n36 - 7 = 29"),
    4: ([2, 3, 4, 6], 36, "6 * 4 = 24\n24 / 2 = 12\n12 * 3 = 36"),
}

V4_EXTRA_EXAMPLES_BY_SIZE = {
    3: ([50, 2, 13], 12, "50 / 2 = 25\n25 - 13 = 12"),
    4: ([70, 5, 12, 3], 54, "70 / 5 = 14\n14 * 3 = 42\n42 + 12 = 54"),
}


def build_prompt(problem, prompt_version):
    if prompt_version == "v1":
        return PROMPT_TEMPLATE.format(nums=problem["nums"], target=problem["target"])
    problem_size = len(problem["nums"])
    if prompt_version == "v4":
        examples_text = "\n\n".join(
            f"Example for numbers {example_nums} and target {example_target}:\n{example_lines}"
            for example_nums, example_target, example_lines in (V2_EXAMPLES_BY_SIZE[problem_size], V4_EXTRA_EXAMPLES_BY_SIZE[problem_size])
        )
        return PROMPT_TEMPLATE_V4.format(nums=problem["nums"], target=problem["target"], num_lines=problem_size - 1, examples=examples_text)
    template = PROMPT_TEMPLATE_V2 if prompt_version == "v2" else PROMPT_TEMPLATE_V3
    example_nums, example_target, example_lines = V2_EXAMPLES_BY_SIZE[problem_size]
    return template.format(
        nums=problem["nums"],
        target=problem["target"],
        num_lines=problem_size - 1,
        example_nums=example_nums,
        example_target=example_target,
        example_lines=example_lines,
    )


STOP_STAGES = ["parse", "arithmetic", "usage", "target"]


def sample_problems(dataset, problems_per_size, seed):
    indices_by_size = {3: [], 4: []}
    for index, nums in enumerate(dataset["nums"]):
        indices_by_size[len(nums)].append(index)
    rng = random.Random(seed)
    problems = []
    for size in (3, 4):
        for index in sorted(rng.sample(indices_by_size[size], problems_per_size)):
            row = dataset[index]
            problems.append({"problem_id": len(problems), "dataset_index": index, "nums": row["nums"], "target": row["target"]})
    return problems


def classify_parse_failure(text, num_count):
    lines = [line.strip() for line in text.strip().split("\n")]
    bad_lines = [line for line in lines if not LINE_PATTERN.match(line)]
    if not bad_lines:
        return "every line well-formed, too many lines" if len(lines) > num_count - 1 else "every line well-formed, too few lines"
    first_bad_line = bad_lines[0]
    if first_bad_line == "":
        return "empty output / blank line"
    if re.search(r"[×÷·−]", first_bad_line):
        return "unicode operator (× ÷ · −)"
    if re.search(r"\d\.\s?\d", first_bad_line):
        return "decimal number"
    if "(" in first_bad_line or ")" in first_bad_line:
        return "parentheses"
    if re.search(r"[A-Za-z]", first_bad_line):
        return "explanation text / words"
    if "=" not in first_bad_line:
        return "no '=' (bare expression, usually cut off)"
    if len(re.findall(r"(?<=\d)\s*[+\-*/]", first_bad_line.split("=")[0])) > 1:
        return "chained expression (a op b op c = d)"
    return "other (e.g. 'x = y', 'a op b =' cut off, two '=')"


def build_metrics(problems, sample_records, greedy_records, target_min, target_max):
    samples_by_problem = {}
    for record in sample_records:
        samples_by_problem.setdefault(record["problem_id"], []).append(record)
    greedy_by_problem = {record["problem_id"]: record for record in greedy_records}

    subsets = {"all": problems, "3 nums": [p for p in problems if len(p["nums"]) == 3], "4 nums": [p for p in problems if len(p["nums"]) == 4]}
    metrics = {}
    for subset_name, subset_problems in subsets.items():
        subset_samples = [r for p in subset_problems for r in samples_by_problem[p["problem_id"]]]
        subset_greedy = [greedy_by_problem[p["problem_id"]] for p in subset_problems]
        failed_samples = [r for r in subset_samples if not r["success"]]
        relabelable_samples = [r for r in subset_samples if r["relabelable"]]
        success_counts = [sum(r["success"] for r in samples_by_problem[p["problem_id"]]) for p in subset_problems]
        samples_per_problem = len(samples_by_problem[subset_problems[0]["problem_id"]])
        all_fail_problems = [p for p, count in zip(subset_problems, success_counts) if count == 0]
        stop_counts = Counter(r["stopped_at"] for r in failed_samples)

        metrics[subset_name] = {
            "num_problems": len(subset_problems),
            "num_samples": len(subset_samples),
            "sample_success_rate": sum(r["success"] for r in subset_samples) / len(subset_samples),
            "greedy_success_rate": sum(r["success"] for r in subset_greedy) / len(subset_greedy),
            "problem_any_success_rate": sum(count > 0 for count in success_counts) / len(subset_problems),
            "problem_all_fail_rate": len(all_fail_problems) / len(subset_problems),
            "problem_mixed_rate": sum(0 < count < samples_per_problem for count in success_counts) / len(subset_problems),
            "sample_parse_ok_rate": sum(r["stopped_at"] != "parse" for r in subset_samples) / len(subset_samples),
            "greedy_parse_ok_rate": sum(r["stopped_at"] != "parse" for r in subset_greedy) / len(subset_greedy),
            "failed_samples": len(failed_samples),
            "failure_stop_fraction": {stage: stop_counts[stage] / max(len(failed_samples), 1) for stage in STOP_STAGES},
            "failed_sample_relabelable_rate": len(relabelable_samples) / max(len(failed_samples), 1),
            "all_fail_problems_with_relabelable_rate": sum(
                any(r["relabelable"] for r in samples_by_problem[p["problem_id"]]) for p in all_fail_problems
            ) / max(len(all_fail_problems), 1),
            "relabelable_samples": len(relabelable_samples),
            "relabelable_final_in_target_range_rate": sum(
                target_min <= r["final_value"] <= target_max for r in relabelable_samples
            ) / max(len(relabelable_samples), 1),
            "sample_mean_output_tokens": sum(r["num_output_tokens"] for r in subset_samples) / len(subset_samples),
            "sample_truncated_rate": sum(r["truncated"] for r in subset_samples) / len(subset_samples),
            "greedy_mean_output_tokens": sum(r["num_output_tokens"] for r in subset_greedy) / len(subset_greedy),
            "greedy_truncated_rate": sum(r["truncated"] for r in subset_greedy) / len(subset_greedy),
        }
    return metrics


def write_summary(path, metrics, timing, target_min, target_max, sample_records, args):
    def percent(value):
        return f"{100 * value:.1f}%"

    subset_names = list(metrics)
    rows = [
        ("problems", lambda m: str(m["num_problems"])),
        ("sample success rate", lambda m: percent(m["sample_success_rate"])),
        ("greedy success rate", lambda m: percent(m["greedy_success_rate"])),
        (f"problems with >=1 success in {args.samples_per_problem}", lambda m: percent(m["problem_any_success_rate"])),
        (f"problems with all {args.samples_per_problem} failed", lambda m: percent(m["problem_all_fail_rate"])),
        ("problems with mixed success/failure", lambda m: percent(m["problem_mixed_rate"])),
        ("format valid rate (sample, passes parse)", lambda m: percent(m["sample_parse_ok_rate"])),
        ("format valid rate (greedy)", lambda m: percent(m["greedy_parse_ok_rate"])),
    ]
    rows += [(f"failed samples stopped at {stage}", lambda m, stage=stage: percent(m["failure_stop_fraction"][stage])) for stage in STOP_STAGES]
    rows += [
        ("failed samples that are relabelable", lambda m: percent(m["failed_sample_relabelable_rate"])),
        ("all-fail problems with >=1 relabelable", lambda m: percent(m["all_fail_problems_with_relabelable_rate"])),
        (f"relabelable final value in target range [{target_min}, {target_max}]", lambda m: percent(m["relabelable_final_in_target_range_rate"])),
        ("mean output tokens (sample)", lambda m: f"{m['sample_mean_output_tokens']:.1f}"),
        (f"truncated at {args.max_new_tokens} tokens (sample)", lambda m: percent(m["sample_truncated_rate"])),
        ("mean output tokens (greedy)", lambda m: f"{m['greedy_mean_output_tokens']:.1f}"),
        ("truncated (greedy)", lambda m: percent(m["greedy_truncated_rate"])),
    ]

    lines = [
        "# Countdown zero-training baseline",
        "",
        f"Model `{args.model}`, prompt {args.prompt_version}, {args.problems_per_size} problems each for 3 and 4 nums (seed {args.seed}), "
        f"{args.samples_per_problem} samples/problem (T=1.0, top_p=1.0) + 1 greedy, max_new_tokens={args.max_new_tokens}.",
        f"Dataset target range: [{target_min}, {target_max}].",
        "",
        "| metric | " + " | ".join(subset_names) + " |",
        "|---|" + "---|" * len(subset_names),
    ]
    for row_name, format_value in rows:
        lines.append(f"| {row_name} | " + " | ".join(format_value(metrics[name]) for name in subset_names) + " |")
    lines += [
        "",
        "| timing | sampled | greedy | total |",
        "|---|---|---|---|",
        f"| generation seconds | {timing['sample_seconds']:.1f} | {timing['greedy_seconds']:.1f} | {timing['total_seconds']:.1f} |",
        f"| output tokens | {timing['sample_tokens']} | {timing['greedy_tokens']} | {timing['total_tokens']} |",
        f"| output tokens/s | {timing['sample_tokens'] / timing['sample_seconds']:.0f} | "
        f"{timing['greedy_tokens'] / timing['greedy_seconds']:.0f} | {timing['total_tokens'] / timing['total_seconds']:.0f} |",
        "",
        "## Parse-failure patterns (sampled outputs)",
        "",
        "| pattern | count | share of parse failures |",
        "|---|---|---|",
    ]
    parse_failures = [r for r in sample_records if r["stopped_at"] == "parse"]
    pattern_counts = Counter(classify_parse_failure(r["output"], len(r["nums"])) for r in parse_failures)
    for pattern, count in pattern_counts.most_common():
        lines.append(f"| {pattern} | {count} | {percent(count / len(parse_failures))} |")

    rng = random.Random(args.seed)
    for stage in STOP_STAGES:
        stage_records = [r for r in sample_records if r["stopped_at"] == stage]
        lines += ["", f"## Failure examples: stopped at {stage} ({len(stage_records)} samples)"]
        for record in rng.sample(stage_records, min(3, len(stage_records))):
            lines += ["", f"nums={record['nums']} target={record['target']} final_value={record['final_value']}", "```", record["output"], "```"]
    with open(path, "w") as summary_file:
        summary_file.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--dataset", default="Jiayi-Pan/Countdown-Tasks-3to4")
    parser.add_argument("--problems_per_size", type=int, default=256)
    parser.add_argument("--samples_per_problem", type=int, default=8)
    parser.add_argument("--max_new_tokens", type=int, default=64)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--prompt_version", choices=["v1", "v2", "v3", "v4"], default="v2")
    parser.add_argument("--gpu_memory_utilization", type=float, default=0.5)
    parser.add_argument("--out_dir", default="results")
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    dataset = load_dataset(args.dataset, split="train")
    print(dataset)
    for row in dataset.select(range(3)):
        print(row)
    all_targets = dataset["target"]
    target_min, target_max = min(all_targets), max(all_targets)
    print(f"target range over {len(all_targets)} rows: [{target_min}, {target_max}]")
    problems = sample_problems(dataset, args.problems_per_size, args.seed)

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    prompts = [
        tokenizer.apply_chat_template(
            [{"role": "user", "content": build_prompt(p, args.prompt_version)}],
            tokenize=False,
            add_generation_prompt=True,
        )
        for p in problems
    ]
    print("example prompt:\n" + prompts[0])

    llm = LLM(model=args.model, seed=args.seed, gpu_memory_utilization=args.gpu_memory_utilization, max_model_len=1024)
    sample_params = SamplingParams(n=args.samples_per_problem, temperature=1.0, top_p=1.0, max_tokens=args.max_new_tokens, seed=args.seed)
    greedy_params = SamplingParams(n=1, temperature=0.0, max_tokens=args.max_new_tokens)

    start_time = time.time()
    sample_outputs = llm.generate(prompts, sample_params)
    sample_seconds = time.time() - start_time
    start_time = time.time()
    greedy_outputs = llm.generate(prompts, greedy_params)
    greedy_seconds = time.time() - start_time

    sample_records, greedy_records = [], []
    for decode_mode, request_outputs, records in (("sample", sample_outputs, sample_records), ("greedy", greedy_outputs, greedy_records)):
        for problem, request_output in zip(problems, request_outputs):
            for sample_index, completion in enumerate(request_output.outputs):
                grade = grade_countdown(completion.text, problem["nums"], problem["target"])
                records.append({
                    **problem,
                    "decode": decode_mode,
                    "sample_index": sample_index,
                    "output": completion.text,
                    "num_output_tokens": len(completion.token_ids),
                    "truncated": completion.finish_reason == "length",
                    **grade,
                })

    with open(os.path.join(args.out_dir, "raw.jsonl"), "w") as raw_file:
        for record in sample_records + greedy_records:
            raw_file.write(json.dumps(record) + "\n")

    sample_tokens = sum(r["num_output_tokens"] for r in sample_records)
    greedy_tokens = sum(r["num_output_tokens"] for r in greedy_records)
    timing = {
        "sample_seconds": sample_seconds,
        "greedy_seconds": greedy_seconds,
        "total_seconds": sample_seconds + greedy_seconds,
        "sample_tokens": sample_tokens,
        "greedy_tokens": greedy_tokens,
        "total_tokens": sample_tokens + greedy_tokens,
    }
    metrics = build_metrics(problems, sample_records, greedy_records, target_min, target_max)
    with open(os.path.join(args.out_dir, "metrics.json"), "w") as metrics_file:
        json.dump({"metrics": metrics, "timing": timing, "target_min": target_min, "target_max": target_max, "args": vars(args)}, metrics_file, indent=2)
    write_summary(os.path.join(args.out_dir, "summary.md"), metrics, timing, target_min, target_max, sample_records, args)
    print(open(os.path.join(args.out_dir, "summary.md")).read())


if __name__ == "__main__":
    main()
