"""Fixed ALFWorld training subset: 40 random tasks per task type (240 total) from the train split.

Candidates use the same filter as verl-agent's AlfredTWEnv.collect_game_files (has traj_data.json and game.tw-pddl,
no 'movable'/'Sliced' in the path, solvable), so every listed task is one the training env can load.
Writes the list (paths relative to json_2.1.1/train) and builds a directory that mirrors only those tasks, with the
two files the env reads symlinked, to use as the env's data_path.
"""
import argparse
import json
import os
import random

TASK_TYPES = ["pick_and_place_simple", "look_at_obj_in_light", "pick_clean_then_place_in_recep",
              "pick_heat_then_place_in_recep", "pick_cool_then_place_in_recep", "pick_two_obj_and_place"]


def solvable_train_tasks(train_dir):
    tasks_by_type = {task_type: [] for task_type in TASK_TYPES}
    for root, _, files in os.walk(train_dir):
        if "traj_data.json" not in files or "movable" in root or "Sliced" in root:
            continue
        game_path = os.path.join(root, "game.tw-pddl")
        if not os.path.exists(game_path):
            continue
        task_type = json.load(open(os.path.join(root, "traj_data.json")))["task_type"]
        if task_type in tasks_by_type and json.load(open(game_path)).get("solvable"):
            tasks_by_type[task_type].append(os.path.relpath(root, train_dir))
    return {task_type: sorted(tasks) for task_type, tasks in tasks_by_type.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--alfworld_data", default=os.environ.get("ALFWORLD_DATA"))
    parser.add_argument("--per_type", type=int, default=40)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out_list", required=True)
    parser.add_argument("--out_dir", required=True, help="mirror directory used as the env's dataset.data_path")
    args = parser.parse_args()

    train_dir = os.path.join(args.alfworld_data, "json_2.1.1", "train")
    tasks_by_type = solvable_train_tasks(train_dir)
    rng = random.Random(args.seed)
    chosen = []
    for task_type in TASK_TYPES:
        print(f"{task_type}: {len(tasks_by_type[task_type])} solvable train tasks")
        chosen += sorted(rng.sample(tasks_by_type[task_type], args.per_type))

    with open(args.out_list, "w") as list_file:
        list_file.write("\n".join(chosen) + "\n")
    for task in chosen:
        os.makedirs(os.path.join(args.out_dir, task), exist_ok=False)
        for file_name in ("traj_data.json", "game.tw-pddl"):
            os.symlink(os.path.join(train_dir, task, file_name), os.path.join(args.out_dir, task, file_name))
    print(f"wrote {len(chosen)} tasks to {args.out_list} and {args.out_dir}")


if __name__ == "__main__":
    main()
