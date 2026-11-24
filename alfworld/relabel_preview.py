"""Offline relabel preview on the precheck episodes (untrained model, 240 tasks x 8): what would hindsight relabeling produce?

Goals are ALFWorld task templates at the type level, built from an episode's template achievements (state facts):
  put a X in R / put a hot|cool|clean X in R / put two X in R / look at X under the lamp.
An episode satisfies a goal if one of its achievements matches it at the type level (any instance of X and of R).

Two variants, both relabeling one uniformly chosen failed anchor episode per selected group with one goal drawn uniformly
from the anchor's distinct type-level goals, and rescoring every episode of the group under that goal:
  lfh  - groups whose mean original reward is below 0.8 (LfH gate eta); original and hindsight rows are both trained
  dead - only all-failed groups; their original advantages are zero, so only hindsight rows carry gradient
"""
import argparse
import collections
import gzip
import json
import random
import statistics

TASK_TYPES = ["pick_and_place_simple", "look_at_obj_in_light", "pick_clean_then_place_in_recep",
              "pick_heat_then_place_in_recep", "pick_cool_then_place_in_recep", "pick_two_obj_and_place"]
PROPERTY_WORDS = ("hot", "cool", "clean")
GOAL_KIND_OF_TASK_TYPE = {"pick_and_place_simple": "put", "look_at_obj_in_light": "look", "pick_clean_then_place_in_recep": "clean",
                          "pick_heat_then_place_in_recep": "hot", "pick_cool_then_place_in_recep": "cool", "pick_two_obj_and_place": "two"}


def type_of(name):
    return name.rsplit(" ", 1)[0]


def goals_of(episode):
    """Type-level goals an episode achieved, as tuples (kind, object type, receptacle or lamp type)."""
    goals = set()
    for achievement in episode["full"]:
        words = achievement.split(" ")
        if words[0] == "examine":                       # examine <obj> <n> with <lamp> <n>
            with_index = words.index("with")
            goals.add(("look", type_of(" ".join(words[1:with_index])), type_of(" ".join(words[with_index + 1:]))))
        elif words[1] == "two":                         # put two <type> in <recep> <n>
            in_index = words.index("in")
            goals.add(("two", " ".join(words[2:in_index]), type_of(" ".join(words[in_index + 1:]))))
        elif words[1] in PROPERTY_WORDS:                # put hot <obj> <n> in <recep> <n>
            in_index = words.index("in")
            goals.add((words[1], type_of(" ".join(words[2:in_index])), type_of(" ".join(words[in_index + 1:]))))
        else:                                           # put <obj> <n> in <recep> <n>
            in_index = words.index("in")
            goals.add(("put", type_of(" ".join(words[1:in_index])), type_of(" ".join(words[in_index + 1:]))))
    return goals


def goal_text(goal):
    kind, obj, target = goal
    if kind == "look":
        return f"look at {obj} under the {target}"
    if kind == "two":
        return f"put two {obj} in {target}"
    return f"put a {kind + ' ' if kind in PROPERTY_WORDS else ''}{obj} in {target}"


def grpo_advantages(rewards):
    mean = statistics.mean(rewards)
    std = statistics.stdev(rewards) if len(rewards) > 1 else 0.0
    return [(r - mean) / (std + 1e-6) for r in rewards]


def preview(groups, variant, seed):
    stats = collections.Counter()
    hindsight_success_counts = collections.Counter()
    goal_kinds = collections.Counter()
    examples = []
    for group_id, episodes in sorted(groups.items()):
        original = [float(e["won"]) for e in episodes]
        selected = sum(original) / len(original) < 0.8 if variant == "lfh" else not any(original)
        if not selected:
            continue
        stats["selected_groups"] += 1
        failed = [e for e in episodes if not e["won"]]
        rng = random.Random(f"{seed}:{group_id}")
        anchor = rng.choice(failed)
        candidates = sorted(goals_of(anchor))
        if not candidates:
            stats["anchor_without_goal"] += 1
            continue
        goal = rng.choice(candidates)
        goal_kinds[goal[0]] += 1
        hindsight = [float(goal in goals_of(e)) for e in episodes]
        successes = int(sum(hindsight))
        hindsight_success_counts[successes] += 1
        stats["relabeled_groups"] += 1
        stats["hindsight_all_success"] += successes == len(episodes)
        stats["hindsight_mixed"] += 0 < successes < len(episodes)
        stats["goal_equals_original_task_type"] += goal[0] == GOAL_KIND_OF_TASK_TYPE[episodes[0]["task_type"]]
        if 0 < successes < len(episodes):
            original_adv = grpo_advantages(original) if 0 < sum(original) < len(original) else [0.0] * len(original)
            hindsight_adv = grpo_advantages(hindsight)
            for o, h, won in zip(original_adv, hindsight_adv, original):
                stats["hindsight_rows_with_signal"] += 1
                if o != 0.0:
                    stats["rows_with_both_signals"] += 1
                    stats["sign_conflicts"] += (o > 0) != (h > 0)
        if len(examples) < 8:
            examples.append({"task": episodes[0]["task_description"], "goal": goal_text(goal), "original": original, "hindsight": hindsight})
    return stats, hindsight_success_counts, goal_kinds, examples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", required=True)
    parser.add_argument("--out_md", required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    opener = gzip.open if args.episodes.endswith(".gz") else open
    groups = collections.defaultdict(list)
    for line in opener(args.episodes, "rt"):
        episode = json.loads(line)
        groups[episode["group"]].append(episode)

    lines = [f"# Relabel preview on the precheck episodes (untrained model, {len(groups)} groups x {len(next(iter(groups.values())))})", ""]
    for variant in ("lfh", "dead"):
        stats, success_counts, goal_kinds, examples = preview(groups, variant, args.seed)
        relabeled = stats["relabeled_groups"]
        def pct(count, total):
            return f"{100 * count / total:.1f}%" if total else "—"
        lines += [f"## Variant `{variant}`", "",
                  f"- selected groups: {stats['selected_groups']} of {len(groups)}",
                  f"- anchor achieved no template goal (no relabel): {stats['anchor_without_goal']} ({pct(stats['anchor_without_goal'], stats['selected_groups'])})",
                  f"- relabeled groups: {relabeled}",
                  f"- under the hindsight goal: all episodes succeed {pct(stats['hindsight_all_success'], relabeled)}, mixed (carries signal) {pct(stats['hindsight_mixed'], relabeled)}",
                  f"- episodes succeeding under the hindsight goal (per group, anchor included): {dict(sorted(success_counts.items()))}",
                  f"- hindsight goal kind: {dict(goal_kinds.most_common())}; same kind as the group's original task: {pct(stats['goal_equals_original_task_type'], relabeled)}",
                  f"- hindsight rows with nonzero advantage: {stats['hindsight_rows_with_signal']}; of these also with nonzero original advantage: {stats['rows_with_both_signals']}; "
                  f"opposite signs: {stats['sign_conflicts']} ({pct(stats['sign_conflicts'], stats['rows_with_both_signals'])})", "",
                  "Examples (original task -> hindsight goal; per-episode original / hindsight success):", ""]
        lines += [f"- `{e['task']}` -> `{e['goal']}`: {[int(x) for x in e['original']]} / {[int(x) for x in e['hindsight']]}" for e in examples]
        lines.append("")
    open(args.out_md, "w").write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
