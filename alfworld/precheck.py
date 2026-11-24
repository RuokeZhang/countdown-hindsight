"""Pre-check without training: the untrained model plays every task of the 240-task subset 8 times.

Prompts, action parsing and history come from verl-agent's AlfWorldEnvironmentManager (same as training); generation
uses the training rollout settings (temperature 1.0, top_p 1.0, top_k -1, up to 512 response tokens, 50 env steps).
For every episode the env workers record what was actually achieved, read from the TextWorld state facts
(holds / inreceptacle / ishot / iscool / isclean / istoggled), and separately parsed from the feedback text as a
cross-check. Outputs episodes.jsonl (one row per episode, with the trajectory) in --out_dir.
"""
import argparse
import copy
import json
import os
import re
import sys
import time

import ray

VERL_AGENT_DIR = os.environ.get("VERL_AGENT_DIR", "/root/alf/verl-agent")
sys.path.insert(0, VERL_AGENT_DIR)

TASK_TYPES = ["pick_and_place_simple", "look_at_obj_in_light", "pick_clean_then_place_in_recep",
              "pick_heat_then_place_in_recep", "pick_cool_then_place_in_recep", "pick_two_obj_and_place"]
LAMP_TYPES = ("desklamp", "floorlamp")
TEXT_EVENT_PATTERNS = {
    "put": re.compile(r"You move the (.+?) to the (.+?)\."),
    "hold": re.compile(r"You pick up the (.+?) from the "),
    "heat": re.compile(r"You heat the (.+?) using "),
    "cool": re.compile(r"You cool the (.+?) using "),
    "clean": re.compile(r"You clean the (.+?) using "),
    "toggle": re.compile(r"You turn on the (.+?)\."),
}


def object_type(name):
    return name.rsplit(" ", 1)[0]


class AchievementTracker:
    """Achievements of one episode from state facts, frozen once the episode is done.

    A placement is an inreceptacle fact that is new relative to the previous step (so putting an object back where it
    started counts); properties (hot/cool/clean) are those the object has at that moment, unioned over placements.
    """

    def __init__(self, facts):
        self.initial = {(fact.name, tuple(arg.name for arg in fact.arguments)) for fact in facts}
        self.previous = self.initial
        self.placements = {}          # (object, receptacle) -> set of properties the object had when placed there
        self.two_placed = set()       # (object type, receptacle) with two objects of that type in it at the same time
        self.heated, self.cooled, self.cleaned = set(), set(), set()
        self.held, self.toggled_lamps, self.examined_in_light = set(), set(), set()
        self.holding = []
        self.text_events = {kind: set() for kind in TEXT_EVENT_PATTERNS}

    def update(self, facts, feedback):
        current = {(fact.name, tuple(arg.name for arg in fact.arguments)) for fact in facts}
        properties = {name: {args[0] for name_, args in current if name_ == name} for name in ("ishot", "iscool", "isclean")}
        self.holding = sorted(args[1] for name, args in current if name == "holds")
        self.held.update(self.holding)
        for name, args in current - self.previous:
            if name == "inreceptacle":
                obj, receptacle = args
                self.placements.setdefault(args, set()).update(p for p in ("ishot", "iscool", "isclean") if obj in properties[p])
                same_type_inside = {other[0] for n, other in current if n == "inreceptacle" and other[1] == receptacle and object_type(other[0]) == object_type(obj)}
                if len(same_type_inside) >= 2:
                    self.two_placed.add((object_type(obj), receptacle))
        for name, args in current - self.initial:
            if name == "ishot":
                self.heated.add(args[0])
            elif name == "iscool":
                self.cooled.add(args[0])
            elif name == "isclean":
                self.cleaned.add(args[0])
            elif name == "istoggled" and object_type(args[0]) in LAMP_TYPES:
                self.toggled_lamps.add(args[0])
        self.previous = current
        agent_locations = {args[1] for name, args in current if name == "atlocation"}
        for name, args in current:
            if name == "istoggled" and object_type(args[0]) in LAMP_TYPES:
                lamp_locations = {other_args[1] for other_name, other_args in current if other_name == "objectatlocation" and other_args[0] == args[0]}
                if lamp_locations & agent_locations:
                    self.examined_in_light.update((held_object, args[0]) for held_object in self.holding)
        for kind, pattern in TEXT_EVENT_PATTERNS.items():
            for match in pattern.finditer(feedback):
                if kind != "toggle" or object_type(match.group(1)) in LAMP_TYPES:
                    self.text_events[kind].add(match.groups())

    def summary(self):
        full, half = [], []
        property_words = {"ishot": "hot", "iscool": "cool", "isclean": "clean"}
        for (obj, receptacle), props in sorted(self.placements.items()):
            full.append(f"put {obj} in {receptacle}")
            full += [f"put {property_words[p]} {obj} in {receptacle}" for p in sorted(props)]
        full += [f"put two {obj_type} in {receptacle}" for obj_type, receptacle in sorted(self.two_placed)]
        full += [f"examine {obj} with {lamp}" for obj, lamp in sorted(self.examined_in_light)]
        half += [f"hold {obj}" for obj in sorted(self.held)]
        for verb, prop, objects in (("heat", "ishot", self.heated), ("cool", "iscool", self.cooled), ("clean", "isclean", self.cleaned)):
            placed_with_property = {obj for (obj, _), props in self.placements.items() if prop in props}
            half += [f"{verb} {obj}" for obj in sorted(objects) if obj not in placed_with_property]
        examined_lamps = {lamp for _, lamp in self.examined_in_light}
        half += [f"turn on {lamp}" for lamp in sorted(self.toggled_lamps - examined_lamps)]
        state_events = {
            "put": {(obj, receptacle) for obj, receptacle in self.placements},
            "hold": {(obj,) for obj in self.held},
            "heat": {(obj,) for obj in self.heated}, "cool": {(obj,) for obj in self.cooled},
            "clean": {(obj,) for obj in self.cleaned}, "toggle": {(lamp,) for lamp in self.toggled_lamps},
        }
        text_agrees = {kind: sorted(map(list, self.text_events[kind])) == sorted(map(list, state_events[kind])) for kind in TEXT_EVENT_PATTERNS}
        return {"full": full, "half": half, "holding_at_end": self.holding, "text_agrees_with_state": text_agrees,
                "text_events": {kind: sorted(map(list, events)) for kind, events in self.text_events.items()}}


class FactsGroupWorker:
    """Ray actor with several single-game ALFWorld envs that also request state facts and track achievements."""

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
        results, self.trackers, self.finished = [], [], []
        for env in self.envs:
            obs, infos = env.reset()
            self.trackers.append(AchievementTracker(infos.pop("facts")[0]))
            self.finished.append(False)
            infos["observation_text"] = obs
            results.append((obs, infos))
        return results

    def step(self, actions):
        results = []
        for index, (env, action) in enumerate(zip(self.envs, actions)):
            obs, scores, dones, infos = env.step([action])
            facts = infos.pop("facts")[0]
            if not self.finished[index]:
                self.trackers[index].update(facts, obs[0])
                self.finished[index] = bool(dones[0])
            infos["observation_text"] = obs
            results.append((obs, scores, dones, infos))
        return results

    def achievements(self):
        return [tracker.summary() for tracker in self.trackers]


class PrecheckEnvs:
    """Same interface as verl-agent's AlfworldEnvs; env i plays games[i] (each task repeated group_n times in a row)."""

    def __init__(self, config_path, games, seed, group_n, envs_per_worker):
        from agent_system.environments.env_package.alfworld.envs import load_config_file, compute_reward
        from agent_system.environments.env_package.alfworld.alfworld.agents.environment import get_environment
        self.compute_reward = compute_reward
        config = load_config_file(config_path)
        base_env = get_environment(config["env"]["type"])(config, train_eval="train")
        base_envs = []
        for game in games:
            single_game_env = copy.copy(base_env)
            single_game_env.game_files, single_game_env.num_games = [game], 1
            base_envs.append(single_game_env)
        self.num_processes = len(games)
        worker_cls = ray.remote(num_cpus=0.1)(FactsGroupWorker)
        self.workers, self.worker_sizes = [], []
        for start in range(0, self.num_processes, envs_per_worker):
            indices = list(range(start, min(start + envs_per_worker, self.num_processes)))
            self.workers.append(worker_cls.remote([base_envs[i] for i in indices], [seed + i // group_n for i in indices]))
            self.worker_sizes.append(len(indices))
        self.prev_admissible_commands = [None] * self.num_processes

    def _unpack(self, info):
        return {key: value[0] for key, value in info.items()}

    def reset(self):
        results = [r for worker_results in ray.get([w.reset.remote() for w in self.workers]) for r in worker_results]
        text_obs, infos = [], []
        for i, (obs, info) in enumerate(results):
            info = self._unpack(info)
            text_obs.append(obs[0])
            self.prev_admissible_commands[i] = info["admissible_commands"]
            infos.append(info)
        return text_obs, None, infos

    def step(self, actions):
        futures, start = [], 0
        for worker, size in zip(self.workers, self.worker_sizes):
            futures.append(worker.step.remote(actions[start:start + size]))
            start += size
        results = [r for worker_results in ray.get(futures) for r in worker_results]
        text_obs, rewards, dones, infos = [], [], [], []
        for i, (obs, scores, done, info) in enumerate(results):
            info = self._unpack(info)
            text_obs.append(obs[0])
            dones.append(done[0])
            self.prev_admissible_commands[i] = info["admissible_commands"]
            rewards.append(self.compute_reward(info))
            infos.append(info)
        return text_obs, None, rewards, dones, infos

    @property
    def get_admissible_commands(self):
        return self.prev_admissible_commands

    def achievements(self):
        return [a for worker_results in ray.get([w.achievements.remote() for w in self.workers]) for a in worker_results]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset_dir", default=os.path.expandvars("$ALFWORLD_DATA/train_subset_240"))
    parser.add_argument("--subset_list", required=True)
    parser.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--group_n", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--envs_per_worker", type=int, default=64)
    parser.add_argument("--limit_tasks", type=int, default=0, help="only the first N tasks (for a quick test)")
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()

    from omegaconf import OmegaConf
    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams
    from agent_system.environments.env_manager import AlfWorldEnvironmentManager
    from agent_system.environments.env_package.alfworld import alfworld_projection

    trainer_config = OmegaConf.load(os.path.join(VERL_AGENT_DIR, "verl/trainer/config/ppo_trainer.yaml"))
    max_steps = trainer_config.env.max_steps                     # 50, as in the training script
    max_prompt_length, max_response_length = 2048, 512           # training script values
    rollout = trainer_config.actor_rollout_ref.rollout
    # No per-request seed: vLLM would give every request the same generator, so the 8 identical prompts of a group would
    # sample identical outputs. LLM(seed=...) seeds the engine once, as in training.
    sampling = SamplingParams(temperature=rollout.temperature, top_p=rollout.top_p, top_k=rollout.top_k, max_tokens=max_response_length)
    print(f"sampling: temperature {rollout.temperature} top_p {rollout.top_p} top_k {rollout.top_k} max_tokens {max_response_length}; max_steps {max_steps}; history_length {trainer_config.env.history_length}")

    tasks = [line.strip() for line in open(args.subset_list) if line.strip()]
    if args.limit_tasks:
        tasks = tasks[: args.limit_tasks]
    games = [os.path.join(args.subset_dir, task, "game.tw-pddl") for task in tasks for _ in range(args.group_n)]
    os.makedirs(args.out_dir, exist_ok=True)

    ray.init(num_cpus=32)
    config_path = os.path.join(VERL_AGENT_DIR, "agent_system/environments/env_package/alfworld/configs/config_tw.yaml")
    raw_envs = PrecheckEnvs(config_path, games, args.seed, args.group_n, args.envs_per_worker)
    envs = AlfWorldEnvironmentManager(raw_envs, alfworld_projection, trainer_config)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    llm = LLM(model=args.model, seed=args.seed, gpu_memory_utilization=0.85, max_model_len=max_prompt_length + max_response_length)

    num_envs = len(games)
    observations, _ = envs.reset(kwargs=None)
    done = [False] * num_envs
    won = [False] * num_envs
    steps_taken = [0] * num_envs
    trajectories = [[] for _ in range(num_envs)]
    overlong_prompts = 0
    start_time = time.time()
    for step in range(max_steps):
        active = [i for i in range(num_envs) if not done[i]]
        if not active:
            break
        prompts = [tokenizer.apply_chat_template([{"role": "user", "content": observations["text"][i]}], add_generation_prompt=True, tokenize=False) for i in active]
        overlong_prompts += sum(len(tokenizer(prompt, add_special_tokens=False)["input_ids"]) > max_prompt_length for prompt in prompts)
        outputs = llm.generate(prompts, sampling, use_tqdm=False)
        responses = ["look"] * num_envs                      # finished envs: placeholder, their results are ignored
        for i, output in zip(active, outputs):
            responses[i] = output.outputs[0].text
        next_observations, rewards, dones, infos = envs.step(list(responses))
        for i in active:
            trajectories[i].append({"response": responses[i], "action_valid": int(infos[i]["is_action_valid"]), "feedback": next_observations["anchor"][i]})
            steps_taken[i] += 1
            won[i] = bool(infos[i]["won"])
            done[i] = bool(dones[i])
        observations = next_observations
        print(f"step {step + 1}: active {len(active)}, finished {sum(done)}, won {sum(won)}, elapsed {time.time() - start_time:.0f}s", flush=True)

    achievements = raw_envs.achievements()
    with open(os.path.join(args.out_dir, "episodes.jsonl"), "w") as out_file:
        for i, game in enumerate(games):
            task = tasks[i // args.group_n]
            end_mode = "success" if won[i] else ("step_limit" if steps_taken[i] >= max_steps else "env_done_without_success")
            out_file.write(json.dumps({
                "task": task, "task_type": next(t for t in TASK_TYPES if task.startswith(t)), "group": i // args.group_n,
                "task_description": envs.tasks[i], "won": won[i], "steps": steps_taken[i], "end_mode": end_mode,
                **achievements[i], "trajectory": trajectories[i],
            }) + "\n")
    json.dump({"episodes": num_envs, "overlong_prompts": overlong_prompts, "seconds": time.time() - start_time,
               "sampling": {"temperature": rollout.temperature, "top_p": rollout.top_p, "top_k": rollout.top_k, "max_tokens": max_response_length},
               "max_steps": max_steps, "history_length": trainer_config.env.history_length},
              open(os.path.join(args.out_dir, "run_info.json"), "w"), indent=2)
    print("done", num_envs, "episodes")


if __name__ == "__main__":
    main()
