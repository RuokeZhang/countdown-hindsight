import argparse
import os
import random

import pandas as pd
from datasets import load_dataset
from transformers import AutoTokenizer

from run_countdown_baseline import build_prompt, sample_problems

PROMPT_VERSION = "v3"


def to_verl_row(dataset_index, nums, target, split):
    problem = {"nums": nums, "target": target}
    return {
        "data_source": f"countdown_{len(nums)}",
        "prompt": [{"role": "user", "content": build_prompt(problem, PROMPT_VERSION)}],
        "ability": "math",
        "reward_model": {"style": "rule", "ground_truth": target},
        "extra_info": {
            "problem_id": dataset_index,
            "nums": nums,
            "target": target,
            "num_count": len(nums),
            "split": split,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="Jiayi-Pan/Countdown-Tasks-3to4")
    parser.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--val_per_size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--zero_shot_seed", type=int, default=0)
    parser.add_argument("--zero_shot_per_size", type=int, default=256)
    parser.add_argument("--out_dir", default="data/countdown_v3")
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    dataset = load_dataset(args.dataset, split="train")
    all_nums, all_targets = list(dataset["nums"]), list(dataset["target"])

    first_index_by_multiset = {}
    for dataset_index, nums in enumerate(all_nums):
        first_index_by_multiset.setdefault(tuple(sorted(nums)), dataset_index)
    print(f"{len(all_nums)} rows, {len(first_index_by_multiset)} unique number multisets")

    zero_shot_problems = sample_problems(dataset, args.zero_shot_per_size, args.zero_shot_seed)
    zero_shot_multisets = {tuple(sorted(p["nums"])) for p in zero_shot_problems}

    rng = random.Random(args.seed)
    val_indices, train_indices = [], []
    for size in (3, 4):
        multisets = sorted(m for m in first_index_by_multiset if len(m) == size)
        rng.shuffle(multisets)
        val_candidates = [m for m in multisets if m not in zero_shot_multisets]
        val_multisets = set(val_candidates[: args.val_per_size])
        val_indices += [first_index_by_multiset[m] for m in val_candidates[: args.val_per_size]]
        train_indices.append([first_index_by_multiset[m] for m in multisets if m not in val_multisets])
    train_per_size = min(len(indices) for indices in train_indices)
    train_indices = train_indices[0][:train_per_size] + train_indices[1][:train_per_size]
    rng.shuffle(train_indices)

    train_multisets = {tuple(sorted(all_nums[i])) for i in train_indices}
    val_multisets = {tuple(sorted(all_nums[i])) for i in val_indices}
    assert not train_multisets & val_multisets
    assert not val_multisets & zero_shot_multisets
    zero_shot_in_train = len(train_multisets & zero_shot_multisets)

    for split, indices in (("train", train_indices), ("val", val_indices)):
        rows = [to_verl_row(i, list(all_nums[i]), all_targets[i], split) for i in indices]
        pd.DataFrame(rows).to_parquet(os.path.join(args.out_dir, f"{split}.parquet"))
        size_counts = pd.Series([len(all_nums[i]) for i in indices]).value_counts().to_dict()
        print(f"{split}: {len(rows)} rows, by num count {size_counts}")
    print(f"zero-shot multisets: in val 0, in train {zero_shot_in_train}")

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    prompt_lengths = [
        len(tokenizer(tokenizer.apply_chat_template(to_verl_row(i, list(all_nums[i]), all_targets[i], "")["prompt"], tokenize=False, add_generation_prompt=True), add_special_tokens=False)["input_ids"])
        for i in val_indices + train_indices[:2000]
    ]
    print(f"prompt tokens (val + first 2000 train): min {min(prompt_lengths)} max {max(prompt_lengths)}")


if __name__ == "__main__":
    main()
