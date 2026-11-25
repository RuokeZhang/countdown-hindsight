"""Offline check of HPG-style (product over steps) importance weights for our ALFWorld hindsight relabels.

replay: re-plays the precheck episodes (untrained model, 240 tasks x 8) in the env by feeding back the stored
responses, so the prompts are exactly the training prompts. For every all-failed group with an accepted v2 relabel
(LLM claim confirmed by the state tracker in hindsight.py) it picks g' as training does (one anchor per group, rewards
from state goals, all-success groups skipped) and writes, for each of the group's 8 episodes, every turn up to the
goal step (successful copies) or the end (failed copies): the prompt under g, the prompt under g', the response.

score: for each turn, log pi(response | prompt) under g and under g' with one model, over the full response and over
the action tokens only (hindsight.action_token_mask); writes per-turn sums and prints the weight statistics.
"""
import argparse
import collections
import gzip
import json
import math
import os
import random
import sys
import time

VERL_AGENT_DIR = os.environ.get("VERL_AGENT_DIR", "/root/alf/verl-agent")
sys.path.insert(0, VERL_AGENT_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class ReplayWorker:
    """Like precheck.FactsGroupWorker, but tracks goals with hindsight.AchievementTracker (the training tracker)."""

    def __init__(self, base_envs, seeds):
        import textworld
        original_env_infos = textworld.EnvInfos

        def env_infos_with_facts(*args, **kwargs):
            kwargs["facts"] = True
            return original_env_infos(*args, **kwargs)

        textworld.EnvInfos = env_infos_with_facts
        self.envs = []
        for base_env, seed in zip(base_envs, seeds):
            env = base_env.init_env(batch_size=1)
            env.seed(seed)
            self.envs.append(env)
        textworld.EnvInfos = original_env_infos
        self.trackers, self.finished = [], []

    def reset(self):
        from hindsight import AchievementTracker
        results, self.trackers, self.finished = [], [], []
        for env in self.envs:
            obs, infos = env.reset()
            self.trackers.append(AchievementTracker(infos.pop("facts")[0]))
            self.finished.append(False)
            results.append((obs, infos))
        return results

    def step(self, actions):
        results = []
        for index, (env, action) in enumerate(zip(self.envs, actions)):
            obs, scores, dones, infos = env.step([action])
            facts = infos.pop("facts")[0]
            if not self.finished[index]:
                self.trackers[index].update(facts, action, obs[0])
                self.finished[index] = bool(dones[0])
            results.append((obs, scores, dones, infos))
        return results

    def achievements(self):
        return [tracker.record() for tracker in self.trackers]


def replay(args):
    import ray
    from omegaconf import OmegaConf
    from transformers import AutoTokenizer
    import precheck
    from hindsight import goal_instruction
    from agent_system.environments.env_manager import AlfWorldEnvironmentManager
    from agent_system.environments.env_package.alfworld import alfworld_projection

    episodes = [json.loads(line) for line in open(args.episodes)]
    accepted_claims = collections.defaultdict(list)
    for line in open(args.relabels):
        record = json.loads(line)
        if record["status"] == "accepted":
            accepted_claims[record["group"]].append((record["episode_index"], tuple(record["goal"])))
    by_group = collections.defaultdict(list)
    for episode in episodes:
        by_group[episode["group"]].append(episode)
    groups = [g for g in sorted(by_group) if not any(e["won"] for e in by_group[g]) and accepted_claims[g]]
    if args.limit_groups:
        groups = groups[: args.limit_groups]
    selected = [episode for g in groups for episode in by_group[g]]
    assert all(len(by_group[g]) == 8 for g in groups)
    print(f"{len(groups)} all-failed groups with accepted claims, {len(selected)} episodes to replay", flush=True)

    trainer_config = OmegaConf.load(os.path.join(VERL_AGENT_DIR, "verl/trainer/config/ppo_trainer.yaml"))
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    ray.init(num_cpus=32)
    precheck.FactsGroupWorker = ReplayWorker
    games = [os.path.join(args.subset_dir, episode["task"], "game.tw-pddl") for episode in selected]
    config_path = os.path.join(VERL_AGENT_DIR, "agent_system/environments/env_package/alfworld/configs/config_tw.yaml")
    raw_envs = precheck.PrecheckEnvs(config_path, games, 0, 8, 32)
    envs = AlfWorldEnvironmentManager(raw_envs, alfworld_projection, trainer_config)
    observations, _ = envs.reset(kwargs=None)
    assert [envs.tasks[i] for i in range(len(selected))] == [e["task_description"] for e in selected]

    num_envs = len(selected)
    prompts = [[] for _ in range(num_envs)]
    feedback_mismatches = 0
    for step in range(trainer_config.env.max_steps):
        active = [i for i in range(num_envs) if step < len(selected[i]["trajectory"])]
        if not active:
            break
        responses = ["look"] * num_envs
        for i in active:
            prompts[i].append(observations["text"][i])
            responses[i] = selected[i]["trajectory"][step]["response"]
        observations, _, _, _ = envs.step(responses)
        feedback_mismatches += sum(observations["anchor"][i] != selected[i]["trajectory"][step]["feedback"] for i in active)
    records = raw_envs.achievements()
    total_turns = sum(len(e["trajectory"]) for e in selected)
    print(f"replayed {total_turns} turns, feedback mismatches {feedback_mismatches}", flush=True)

    out_turns = gzip.open(os.path.join(args.out_dir, "turns.jsonl.gz"), "wt")
    group_info, kept_turns, missing_task = [], 0, 0
    for group_position, g in enumerate(groups):
        env_ids = list(range(group_position * 8, group_position * 8 + 8))
        state_goals = [{tuple(goal) for goal in records[i]["goals"]} for i in env_ids]
        accepted = [(episode_index, goal) for episode_index, goal in accepted_claims[g] if goal in state_goals[episode_index]]
        if not accepted:
            continue
        anchor, goal = random.Random(f"0:{g}").choice(sorted(accepted))
        rewards = [float(goal in goals) for goals in state_goals]
        if all(rewards):
            continue
        goal_steps = [next((step for gl, step in records[i]["goal_steps"] if tuple(gl) == goal), None) for i in env_ids]
        task = selected[env_ids[0]]["task_description"]
        instruction = goal_instruction(goal)
        group_info.append({"group": g, "goal": list(goal), "anchor": anchor, "rewards": rewards, "goal_steps": goal_steps})
        for position, i in enumerate(env_ids):
            last = goal_steps[position] if rewards[position] else len(prompts[i])
            for step in range(last):
                prompt = tokenizer.apply_chat_template([{"role": "user", "content": prompts[i][step]}], add_generation_prompt=True, tokenize=False)
                if task not in prompt:
                    missing_task += 1
                    continue
                out_turns.write(json.dumps({"group": g, "episode": position, "step": step, "success": rewards[position],
                                            "prompt_g": prompt, "prompt_relabel": prompt.replace(task, instruction),
                                            "response": selected[i]["trajectory"][step]["response"]}) + "\n")
                kept_turns += 1
    out_turns.close()
    json.dump({"groups": group_info, "feedback_mismatches": feedback_mismatches, "replayed_turns": total_turns,
               "kept_turns": kept_turns, "turns_without_task_text": missing_task},
              open(os.path.join(args.out_dir, "replay_info.json"), "w"), indent=1)
    print(f"{len(group_info)} relabeled groups, {kept_turns} turns written, {missing_task} without task text", flush=True)


def score(args):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from hindsight import action_token_mask

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=torch.bfloat16, attn_implementation="flash_attention_2").cuda().eval()
    end_token = tokenizer.convert_tokens_to_ids("<|im_end|>")
    turns = [json.loads(line) for line in gzip.open(os.path.join(args.out_dir, "turns.jsonl.gz"), "rt")]
    sequences = []                       # (turn index, which prompt, prompt ids, response ids)
    for index, turn in enumerate(turns):
        response_ids = tokenizer(turn["response"], add_special_tokens=False)["input_ids"]
        if len(response_ids) < 512:      # generation stopped at the end token, which is part of the sampled response
            response_ids = response_ids + [end_token]
        turn["action_mask"] = action_token_mask(response_ids, tokenizer)
        for which in ("prompt_g", "prompt_relabel"):
            sequences.append((index, which, tokenizer(turn[which], add_special_tokens=False)["input_ids"], response_ids))
    sequences.sort(key=lambda item: len(item[2]) + len(item[3]))
    token_log_probs = {}
    start_time = time.time()
    with torch.no_grad():
        for start in range(0, len(sequences), args.batch_size):
            batch = sequences[start:start + args.batch_size]
            length = max(len(p) + len(r) for _, _, p, r in batch)
            input_ids = torch.full((len(batch), length), tokenizer.pad_token_id, dtype=torch.long)
            attention_mask = torch.zeros((len(batch), length), dtype=torch.long)
            for row, (_, _, prompt_ids, response_ids) in enumerate(batch):
                ids = prompt_ids + response_ids
                input_ids[row, : len(ids)] = torch.tensor(ids)
                attention_mask[row, : len(ids)] = 1
            logits = model(input_ids=input_ids.cuda(), attention_mask=attention_mask.cuda()).logits
            for row, (index, which, prompt_ids, response_ids) in enumerate(batch):
                positions = slice(len(prompt_ids) - 1, len(prompt_ids) + len(response_ids) - 1)
                log_probs = torch.log_softmax(logits[row, positions].float(), dim=-1)
                targets = torch.tensor(response_ids, device=log_probs.device)
                token_log_probs[(index, which)] = log_probs.gather(1, targets[:, None])[:, 0].cpu()
            if start // args.batch_size % 200 == 0:
                print(f"{start}/{len(sequences)} sequences, {time.time() - start_time:.0f}s", flush=True)

    ratio_buckets = collections.Counter()
    out = open(os.path.join(args.out_dir, f"scores_{args.tag}.jsonl"), "w")
    for index, turn in enumerate(turns):
        log_ratio = token_log_probs[(index, "prompt_relabel")] - token_log_probs[(index, "prompt_g")]
        action = torch.tensor(turn["action_mask"], dtype=torch.bool)
        for value in torch.exp(log_ratio[action]).tolist():
            ratio_buckets["below_0.8" if value < 0.8 else "above_1.2" if value > 1.2 else "0.8_to_1.2"] += 1
        out.write(json.dumps({"group": turn["group"], "episode": turn["episode"], "step": turn["step"], "success": turn["success"],
                              "log_ratio_full": log_ratio.sum().item(), "log_ratio_action": log_ratio[action].sum().item(),
                              "action_tokens": int(action.sum()), "response_tokens": len(log_ratio)}) + "\n")
    out.close()
    total = sum(ratio_buckets.values())
    print("action-token ratio buckets:", {k: round(v / total, 3) for k, v in sorted(ratio_buckets.items())})
    summarize(os.path.join(args.out_dir, f"scores_{args.tag}.jsonl"))


def quantiles(values, points=(0.05, 0.25, 0.5, 0.75, 0.95)):
    ordered = sorted(values)
    return [round(ordered[min(len(ordered) - 1, int(p * len(ordered)))], 2) for p in points]


def summarize(path):
    rows = [json.loads(line) for line in open(path)]
    episodes = collections.defaultdict(list)
    for row in rows:
        episodes[(row["group"], row["episode"])].append(row)
    for kind in ("action", "full"):
        key = f"log_ratio_{kind}"
        print(f"\n== ratio over {kind} tokens ==")
        print("per-turn log ratio quantiles (5/25/50/75/95%):", quantiles([r[key] for r in rows]))
        final = {}
        decision_weights = []
        for episode_key, turns in episodes.items():
            cumulative = 0.0
            for turn in sorted(turns, key=lambda r: r["step"]):
                cumulative += turn[key]
                decision_weights.append(cumulative)
            final[episode_key] = (cumulative, turns[0]["success"], len(turns))
        for label, selected in (("successful copies", [v for v in final.values() if v[1]]), ("failed copies", [v for v in final.values() if not v[1]])):
            logs = [v[0] for v in selected]
            print(f"{label}: {len(selected)} episodes, mean turns {sum(v[2] for v in selected) / len(selected):.1f}; "
                  f"log10 of product weight quantiles (5/25/50/75/95%): {quantiles([x / math.log(10) for x in logs])}; "
                  f"weight < 0.01: {sum(x < math.log(0.01) for x in logs) / len(logs):.1%}, > 100: {sum(x > math.log(100) for x in logs) / len(logs):.1%}")
        print(f"per-decision weights (prefix products over all turns): in [0.5, 2]: {sum(abs(x) <= math.log(2) for x in decision_weights) / len(decision_weights):.1%}, "
              f"< 0.01: {sum(x < math.log(0.01) for x in decision_weights) / len(decision_weights):.1%}, > 100: {sum(x > math.log(100) for x in decision_weights) / len(decision_weights):.1%}")
        group_ess, top_share = [], []
        for g in {k[0] for k in final}:
            logs = [final[k][0] for k in final if k[0] == g]
            peak = max(logs)
            weights = [math.exp(x - peak) for x in logs]
            group_ess.append(sum(weights) ** 2 / sum(w * w for w in weights))
            top_share.append(max(weights) / sum(weights))
        print(f"self-normalized ESS per group of 8 (episode weights): mean {sum(group_ess) / len(group_ess):.2f}, quantiles {quantiles(group_ess)}; "
              f"largest episode's share of the group weight: median {quantiles(top_share)[2]}")
        positives = [v[0] for v in final.values() if v[1]]
        peak = max(positives)
        weights = [math.exp(x - peak) for x in positives]
        print(f"self-normalized ESS over all {len(positives)} successful copies: {sum(weights) ** 2 / sum(w * w for w in weights):.1f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["replay", "score", "summarize"])
    parser.add_argument("--episodes", default="/root/alf/precheck/episodes.jsonl")
    parser.add_argument("--relabels", default="/root/alf/precheck/llm_relabel_prompt_v2.jsonl")
    parser.add_argument("--subset_dir", default=os.path.expandvars("$ALFWORLD_DATA/train_subset_240"))
    parser.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--tag", default="base")
    parser.add_argument("--batch_size", type=int, default=8)
    parser.add_argument("--limit_groups", type=int, default=0)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    if args.phase == "replay":
        replay(args)
    elif args.phase == "score":
        score(args)
    else:
        summarize(os.path.join(args.out_dir, f"scores_{args.tag}.jsonl"))


if __name__ == "__main__":
    main()
