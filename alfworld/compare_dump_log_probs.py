"""Diagnostic: recompute with HF the log probs that training (FSDP) stored for hindsight rows and their source rows
(dump written by apply_behavior_log_probs when HINDSIGHT_DUMP is set), on exactly the same token ids, and compare the
pi(a | o, g') / pi(a | o, g) ratio buckets over the hindsight action tokens."""
import argparse
import random

import torch
from transformers import AutoModelForCausalLM


def buckets(ratio):
    return {"below_0.8": round(float((ratio < 0.8).float().mean()), 3),
            "0.8_to_1.2": round(float(((ratio >= 0.8) & (ratio <= 1.2)).float().mean()), 3),
            "above_1.2": round(float((ratio > 1.2).float().mean()), 3)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", default="/root/alf/hindsight_dump.pt")
    parser.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--sample", type=int, default=400)
    args = parser.parse_args()
    dump = torch.load(args.dump)
    num_hindsight = dump["num_hindsight"]
    response_length = dump["responses"].shape[1]
    mask = dump["hindsight_mask"]
    old = dump["old_log_probs"]
    training_ratio = torch.exp(old[:num_hindsight] - old[num_hindsight:])
    print(f"{num_hindsight} hindsight rows, {int(mask.sum())} action tokens")
    response_attention = dump["attention_mask"][:, -response_length:]
    print("hindsight rows whose response attention equals the action mask:", int((response_attention[:num_hindsight] == mask.long()).all(1).sum()))
    print("training (FSDP) ratio buckets, all rows:", buckets(training_ratio[mask]))

    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16, attn_implementation="flash_attention_2").cuda().eval()
    sample = sorted(random.Random(0).sample(range(num_hindsight), min(args.sample, num_hindsight)))
    hf_log_probs = {}
    with torch.no_grad():
        for row in sample + [num_hindsight + i for i in sample]:
            # full context: prompt + the whole response (the source row's response attention gives the response length)
            source = row if row >= num_hindsight else num_hindsight + row
            response_valid = int(dump["attention_mask"][source, -response_length:].sum())
            prompt_ids = dump["input_ids"][row, :-response_length][dump["attention_mask"][row, :-response_length].bool()]
            ids = torch.cat([prompt_ids, dump["responses"][row, :response_valid]])
            prompt_valid = len(prompt_ids)
            logits = model(input_ids=ids[None].cuda()).logits[0, prompt_valid - 1: len(ids) - 1].float()
            values = torch.log_softmax(logits, dim=-1).gather(1, ids[prompt_valid:, None].cuda())[:, 0].cpu()
            hf_log_probs[row] = torch.zeros(response_length)
            hf_log_probs[row][:response_valid] = values
    sample_mask = mask[sample]
    hf_ratio = torch.stack([torch.exp(hf_log_probs[i] - hf_log_probs[num_hindsight + i]) for i in sample])
    print(f"sample of {len(sample)} rows, {int(sample_mask.sum())} action tokens")
    print("  training (FSDP) ratio buckets:", buckets(training_ratio[sample][sample_mask]))
    print("  HF recomputed ratio buckets:  ", buckets(hf_ratio[sample_mask]))
    for name, rows in (("hindsight rows", sample), ("source rows", [num_hindsight + i for i in sample])):
        difference = torch.cat([(hf_log_probs[r] - old[r])[mask[i]] for r, i in zip(rows, sample)]).abs()
        print(f"  |HF - FSDP| log prob on action tokens, {name}: mean {difference.mean():.4f}, 99% {difference.quantile(0.99):.4f}, max {difference.max():.4f}")


if __name__ == "__main__":
    main()
