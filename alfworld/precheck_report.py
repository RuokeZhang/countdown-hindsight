"""Summarize precheck episodes.jsonl: overall and per task type.

1. success rate; share of groups (8 episodes of one task) that all failed / are mixed / all succeeded
2. among failed episodes: share with >= 1 achievement expressible as an ALFWorld task template ("full"),
   with only partial achievements ("half"), and with nothing
3. among all-failed groups: whether the 8 episodes' achievement sets are all empty, identical (non-empty), partly different, all different
4. end mode distribution and mean steps
Also writes 10 failed trajectories (at least one per task type) as text.
"""
import argparse
import collections
import json
import random

from precheck import TASK_TYPES


def share(count, total):
    return f"{100 * count / total:.1f}%" if total else "—"


def stats_for(episodes):
    groups = collections.defaultdict(list)
    for episode in episodes:
        groups[episode["group"]].append(episode)
    group_list = list(groups.values())
    failed = [e for e in episodes if not e["won"]]
    all_fail_groups = [g for g in group_list if not any(e["won"] for e in g)]

    def similarity(signature):
        counts = collections.Counter()
        for group in all_fail_groups:
            signatures = {signature(e) for e in group}
            if signatures == {frozenset()}:
                counts["all empty"] += 1
            else:
                counts["identical" if len(signatures) == 1 else ("all different" if len(signatures) == len(group) else "partly different")] += 1
        return counts

    full_only = similarity(lambda e: frozenset(e["full"]))
    full_and_half = similarity(lambda e: frozenset(e["full"]) | frozenset(e["half"]))
    end_modes = collections.Counter(e["end_mode"] for e in episodes)
    return {
        "episodes": len(episodes), "groups": len(group_list),
        "success_rate": share(sum(e["won"] for e in episodes), len(episodes)),
        "all_fail_groups": share(len(all_fail_groups), len(group_list)),
        "mixed_groups": share(sum(any(e["won"] for e in g) and not all(e["won"] for e in g) for g in group_list), len(group_list)),
        "all_success_groups": share(sum(all(e["won"] for e in g) for g in group_list), len(group_list)),
        "failed_episodes": len(failed),
        "failed_with_full": share(sum(bool(e["full"]) for e in failed), len(failed)),
        "failed_half_only": share(sum(not e["full"] and bool(e["half"]) for e in failed), len(failed)),
        "failed_nothing": share(sum(not e["full"] and not e["half"] for e in failed), len(failed)),
        "all_fail_empty_full": share(full_only["all empty"], len(all_fail_groups)),
        "all_fail_identical_full": share(full_only["identical"], len(all_fail_groups)),
        "all_fail_partly_full": share(full_only["partly different"], len(all_fail_groups)),
        "all_fail_all_different_full": share(full_only["all different"], len(all_fail_groups)),
        "all_fail_empty_any": share(full_and_half["all empty"], len(all_fail_groups)),
        "all_fail_identical_any": share(full_and_half["identical"], len(all_fail_groups)),
        "all_fail_partly_any": share(full_and_half["partly different"], len(all_fail_groups)),
        "all_fail_all_different_any": share(full_and_half["all different"], len(all_fail_groups)),
        "end_success": share(end_modes["success"], len(episodes)),
        "end_step_limit": share(end_modes["step_limit"], len(episodes)),
        "end_other": share(end_modes["env_done_without_success"], len(episodes)),
        "mean_steps": f"{sum(e['steps'] for e in episodes) / len(episodes):.1f}",
        "mean_steps_failed": f"{sum(e['steps'] for e in failed) / len(failed):.1f}" if failed else "—",
    }


ROWS = [
    ("1", "success rate", "success_rate"), ("1", "groups: all failed", "all_fail_groups"), ("1", "groups: mixed", "mixed_groups"),
    ("1", "groups: all succeeded", "all_success_groups"),
    ("2", "failed episodes", "failed_episodes"), ("2", "failed: >= 1 template-expressible achievement", "failed_with_full"),
    ("2", "failed: only partial achievements", "failed_half_only"), ("2", "failed: nothing achieved", "failed_nothing"),
    ("3", "all-failed groups, template achievements: none in all 8", "all_fail_empty_full"),
    ("3", "all-failed groups, template achievements: identical (non-empty)", "all_fail_identical_full"),
    ("3", "all-failed groups, template achievements: partly different", "all_fail_partly_full"),
    ("3", "all-failed groups, template achievements: all different", "all_fail_all_different_full"),
    ("3", "all-failed groups, all achievements incl. partial: none in all 8", "all_fail_empty_any"),
    ("3", "all-failed groups, all achievements incl. partial: identical (non-empty)", "all_fail_identical_any"),
    ("3", "all-failed groups, all achievements incl. partial: partly different", "all_fail_partly_any"),
    ("3", "all-failed groups, all achievements incl. partial: all different", "all_fail_all_different_any"),
    ("4", "end: success", "end_success"), ("4", "end: step limit (50)", "end_step_limit"), ("4", "end: other (env done, not won)", "end_other"),
    ("4", "mean steps (all episodes)", "mean_steps"), ("4", "mean steps (failed episodes)", "mean_steps_failed"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", required=True)
    parser.add_argument("--out_md", required=True)
    parser.add_argument("--out_examples", required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    episodes = [json.loads(line) for line in open(args.episodes)]

    columns = [("all", episodes)] + [(t, [e for e in episodes if e["task_type"] == t]) for t in TASK_TYPES]
    stats = {name: stats_for(rows) for name, rows in columns}
    lines = ["# ALFWorld precheck: untrained Qwen2.5-1.5B-Instruct, 240 tasks x 8 episodes", "",
             "| item | metric | " + " | ".join(name for name, _ in columns) + " |", "|---|---|" + "---|" * len(columns)]
    for item, label, key in ROWS:
        lines.append(f"| {item} | {label} | " + " | ".join(str(stats[name][key]) for name, _ in columns) + " |")

    agreement = collections.Counter()
    for episode in episodes:
        for kind, agrees in episode["text_agrees_with_state"].items():
            agreement[kind] += agrees
    lines += ["", "Achievements are read from the env state facts (placements: inreceptacle facts new vs the previous step; hot/cool/clean/lamp: new vs the initial state). Share of episodes where the "
              "feedback-text parse gives the same event set as the state, per event kind:", "",
              "| " + " | ".join(agreement) + " |", "|" + "---|" * len(agreement),
              "| " + " | ".join(share(agreement[k], len(episodes)) for k in agreement) + " |"]
    full_counts = collections.Counter(a.split(" ")[0] + (" " + a.split(" ")[1] if a.split(" ")[1] in ("hot", "cool", "clean", "two") else "") for e in episodes if not e["won"] for a in e["full"])
    half_counts = collections.Counter(a.split(" ")[0] for e in episodes if not e["won"] for a in e["half"])
    lines += ["", f"Template achievements in failed episodes by kind: {dict(full_counts.most_common())}",
              f"Partial achievements in failed episodes by kind: {dict(half_counts.most_common())}"]
    open(args.out_md, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))

    rng = random.Random(args.seed)
    failed = [e for e in episodes if not e["won"]]
    chosen = [rng.choice([e for e in failed if e["task_type"] == t]) for t in TASK_TYPES if any(e["task_type"] == t for e in failed)]
    remaining = [e for e in failed if e not in chosen]
    chosen += rng.sample(remaining, max(0, 10 - len(chosen)))
    with open(args.out_examples, "w") as out_file:
        for number, episode in enumerate(chosen, 1):
            out_file.write(f"# Failed trajectory {number}: {episode['task_type']} — {episode['task']}\n\n")
            out_file.write(f"Task: {episode['task_description']}\nEnd: {episode['end_mode']} after {episode['steps']} steps\n")
            out_file.write(f"Template achievements: {episode['full']}\nPartial achievements: {episode['half']}\nHolding at end: {episode['holding_at_end']}\n\n")
            for step, turn in enumerate(episode["trajectory"], 1):
                out_file.write(f"## Step {step} (action valid: {turn['action_valid']})\n\nModel output:\n```\n{turn['response']}\n```\nEnvironment feedback:\n```\n{turn['feedback']}\n```\n\n")
    print(f"wrote {len(chosen)} failed trajectories to {args.out_examples}")


if __name__ == "__main__":
    main()
