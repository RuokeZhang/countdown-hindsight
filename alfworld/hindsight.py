"""Online hindsight relabeling for ALFWorld GRPO (copied into verl-agent as
agent_system/environments/env_package/alfworld/hindsight.py).

Per training step, for every group whose 8 episodes all failed:
  1. episodes whose state-based achievements contain at least one ALFWorld task template are sent to the LLM
     (DeepSeek-V4-Pro, prompt v2 of llm_relabel.py), which names the most complete task the episode accomplished;
  2. the claim is accepted only if the state checker confirms it (type level; hot/cool/clean on the placed instance);
  3. one accepted episode is chosen uniformly as the anchor, and its goal g' rescores all 8 episodes of the group.
Episodes without a template achievement are never sent: no LLM claim about them could pass the checker.

Achievements come from TextWorld state facts (AchievementTracker), as in the precheck.
"""
import concurrent.futures
import json
import os
import random
import re
import time
import urllib.error
import urllib.request

LAMP_TYPES = ("desklamp", "floorlamp")
PROPERTIES = (("ishot", "hot"), ("iscool", "cool"), ("isclean", "clean"))
PROPERTY_FEEDBACK = {"hot": re.compile(r"You heat the (.+?) using "), "cool": re.compile(r"You cool the (.+?) using "),
                     "clean": re.compile(r"You clean the (.+?) using ")}
MODEL = "azure/azure/DeepSeek-V4-Pro"
CREDENTIALS_FILE = "/root/.relabel_topcloud.env"


def object_type(name):
    return name.rsplit(" ", 1)[0]


def fact_set(facts):
    return {(fact.name, tuple(arg.name for arg in fact.arguments)) for fact in facts}


class AchievementTracker:
    """Type-level ALFWorld goals one episode achieved, from state facts; frozen once the episode is done.

    goals: ("put", X, R) a placement of an X into an R that is not a put-back into the receptacle it started in;
    ("hot"|"cool"|"clean", X, R) an X placed into an R while having that property, where the property came from a
    heat/cool/clean action on that same instance in this episode; ("two", X, R) two X in an R at the same time right
    after a placement that is not a put-back; ("look", X, L) holding an X while a lamp of type L at the agent's location
    is on.
    """

    def __init__(self, facts):
        self.initial = fact_set(facts)
        self.previous = self.initial
        self.treated = {name: set() for _, name in PROPERTIES}      # instances heated / cooled / cleaned this episode
        self.goals = set()
        self.goal_steps = {}                                        # goal -> number of steps taken when first achieved
        self.trajectory = []                                        # (executed action, feedback)
        self.done = False

    def update(self, facts, action, feedback):
        if self.done:
            return
        self.trajectory.append((action, feedback))
        for name, pattern in PROPERTY_FEEDBACK.items():
            for match in pattern.finditer(feedback):
                self.treated[name].add(match.group(1))
        current = fact_set(facts)
        has = {name: {args[0] for predicate, args in current if predicate == fact} for fact, name in PROPERTIES}
        for predicate, args in current - self.previous:
            if predicate != "inreceptacle":
                continue
            obj, receptacle = args
            put_back = ("inreceptacle", args) in self.initial
            if not put_back:
                self.add_goal(("put", object_type(obj), object_type(receptacle)))
            for _, name in PROPERTIES:
                if obj in has[name] and obj in self.treated[name]:
                    self.add_goal((name, object_type(obj), object_type(receptacle)))
            same_type = {other[0] for p, other in current if p == "inreceptacle" and other[1] == receptacle and object_type(other[0]) == object_type(obj)}
            if len(same_type) >= 2 and not put_back:
                self.add_goal(("two", object_type(obj), object_type(receptacle)))
        holding = {args[1] for predicate, args in current if predicate == "holds"}
        agent_locations = {args[1] for predicate, args in current if predicate == "atlocation"}
        for predicate, args in current:
            if predicate == "istoggled" and object_type(args[0]) in LAMP_TYPES:
                lamp_locations = {other[1] for p, other in current if p == "objectatlocation" and other[0] == args[0]}
                if lamp_locations & agent_locations:
                    for obj in holding:
                        self.add_goal(("look", object_type(obj), object_type(args[0])))
        self.previous = current

    def add_goal(self, goal):
        if goal not in self.goals:
            self.goals.add(goal)
            self.goal_steps[goal] = len(self.trajectory)

    def record(self):
        return {"goals": sorted(self.goals), "goal_steps": [[list(goal), step] for goal, step in sorted(self.goal_steps.items())],
                "trajectory": list(self.trajectory)}


def goal_instruction(goal):
    kind, obj, target = goal
    if kind == "look":
        return f"look at {obj} under the {target}."
    if kind == "two":
        return f"put two {obj} in {target}."
    if kind == "put":
        return f"put a {obj} in {target}."
    return f"put a {kind} {obj} in {target}."


SYSTEM_PROMPT = """You relabel ALFWorld household episodes for hindsight learning. You get one episode: the original task, then every step's action and the environment's feedback.

Name the single most complete task the agent ACTUALLY accomplished, as one ALFWorld task of exactly one of these kinds:
- put: "put a <object> in/on <receptacle>" - the agent placed an object of that type into/onto a receptacle of that type
- clean: "put a clean <object> in/on <receptacle>" - the object was cleaned at a sinkbasin during the episode, then placed
- hot: "put a hot <object> in/on <receptacle>" - the object was heated with a microwave during the episode, then placed
- cool: "put a cool <object> in/on <receptacle>" - the object was cooled with a fridge during the episode, then placed
- two: "put two <object> in/on <receptacle>" - two objects of that type were in that receptacle at the same time after a placement (one may have been there already)
- look: "look at <object> under the <lamp>" - the agent held the object while a desklamp/floorlamp at its location was turned on
Rules:
- Use object and receptacle TYPES without numbers (e.g. "mug", "countertop", "desklamp"). "target" is always required when achieved is true.
- Only count what the feedback shows actually happened. "Nothing happens." means the action failed.
- The ONLY evidence of a placement is feedback of the form "You move the <object> to the <receptacle>." Walking to, opening or closing a receptacle while holding something is not a placement.
- Heating, cooling and cleaning ("You heat/cool/clean the <object> using the <appliance>.") keep the object in the agent's hand; they do not put it in the microwave, fridge or sinkbasin. For clean/hot/cool, the placement must come AFTER that feedback.
- Picking an object up alone does not count. Putting an object back into the receptacle it was taken from does not count as "put" (but can count for clean/hot/cool).
- The original task is irrelevant; describe what was done, not what was asked.
- Prefer the most complete kind (clean/hot/cool/two/look over plain put). If several of the same kind, pick the last one done.
- If nothing qualifies, set achieved to false.
Return only a JSON object: {"achieved": true|false, "kind": "<one of put|clean|hot|cool|two|look, or null>", "object": "<type or null>", "target": "<receptacle or lamp type, or null>", "instruction": "<the task sentence, or null>", "evidence_steps": [<step numbers>], "reason": "<one sentence>"}"""


def episode_text(task_description, trajectory):
    lines = [f"Original task: {task_description}", ""]
    for step, (action, feedback) in enumerate(trajectory, 1):
        lines.append(f"Step {step} action: {action}")
        lines.append(f"Step {step} feedback: {feedback.strip()}")
    return "\n".join(lines)


def load_credentials():
    values = dict(os.environ)
    if os.path.exists(CREDENTIALS_FILE):
        for line in open(CREDENTIALS_FILE):
            if "=" in line:
                key, value = line.strip().split("=", 1)
                values.setdefault(key, value)
    return values["TOPCLOUD_BASE_URL"].rstrip("/"), values["TOPCLOUD_API_KEY"]


def ask_llm(base, key, text, timeout, attempts=2):
    """The parsed JSON claim, or None after attempts failures (counted by the caller as an LLM error)."""
    request = {"model": MODEL, "max_tokens": 2000, "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}]}
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "hindsight-relabel/1.0"}
    for attempt in range(attempts):
        try:
            response = json.load(urllib.request.urlopen(urllib.request.Request(base + "/chat/completions", data=json.dumps(request).encode(), headers=headers), timeout=timeout))
            return json.loads(response["choices"][0]["message"].get("content") or ""), response.get("usage", {})
        except Exception as error:  # 429 / 5xx / dropped connection / bad JSON: retry; other 4xx: give up
            code = error.code if isinstance(error, urllib.error.HTTPError) else None
            if code is not None and 400 <= code < 500 and code != 429:
                break
            if attempt + 1 < attempts:
                time.sleep((20 if code == 429 else 3) * (attempt + 1))
    return None, {}


def claimed_goal(claim):
    if not isinstance(claim, dict) or not claim.get("achieved"):
        return None
    kind, obj, target = claim.get("kind"), claim.get("object"), claim.get("target")
    if kind not in ("put", "clean", "hot", "cool", "two", "look") or not isinstance(obj, str) or not isinstance(target, str):
        return None
    return (kind, obj.strip().lower(), target.strip().lower())


def plan_relabels(groups, records, task_descriptions, seed_text, max_workers=48, timeout=60, deadline=240):
    """groups: {uid: [env indices]} of all-failed groups. Returns (plans, log, metrics); plans maps uid to
    {"goal", "instruction", "anchor", "rewards", "goal_steps"} for groups whose relabel gives a mixed reward vector.
    LLM calls that have not finished within deadline seconds are abandoned (those episodes are not relabeled)."""
    base, key = load_credentials()
    jobs = [(uid, env) for uid, envs in groups.items() for env in envs if records[env]["goals"]]
    claims, usage = {}, {"prompt_tokens": 0, "completion_tokens": 0, "llm_errors": 0, "llm_timeouts": 0}
    pool = concurrent.futures.ThreadPoolExecutor(max_workers)
    futures = {pool.submit(ask_llm, base, key, episode_text(task_descriptions[env], records[env]["trajectory"]), timeout): (uid, env) for uid, env in jobs}
    finished, unfinished = concurrent.futures.wait(futures, timeout=deadline)
    pool.shutdown(wait=False, cancel_futures=True)
    usage["llm_timeouts"] = len(unfinished)
    for future in finished:
        uid, env = futures[future]
        claim, call_usage = future.result()
        usage["llm_errors"] += claim is None
        usage["prompt_tokens"] += call_usage.get("prompt_tokens", 0)
        usage["completion_tokens"] += call_usage.get("completion_tokens", 0)
        claims[env] = claim
    plans, log = {}, []
    accepted_count = rejected_count = all_success = 0
    for uid, envs in groups.items():
        accepted = []
        for env in envs:
            if env not in claims:
                continue
            goal = claimed_goal(claims[env])
            ok = goal is not None and tuple(goal) in {tuple(g) for g in records[env]["goals"]}
            accepted_count += ok
            rejected_count += goal is not None and not ok
            if ok:
                accepted.append((env, goal))
        entry = {"uid": uid, "envs": envs, "task": task_descriptions[envs[0]],
                 "claims": {env: claims[env] for env in envs if env in claims}, "accepted": [[env, list(goal)] for env, goal in accepted]}
        if accepted:
            anchor, goal = random.Random(f"{seed_text}:{min(envs)}").choice(accepted)   # group position, not the random uid
            rewards = [float(tuple(goal) in {tuple(g) for g in records[env]["goals"]}) for env in envs]
            # for an episode that achieved g', the step at which it first did (the env would have ended the episode there)
            goal_steps = [next((step for g, step in records[env]["goal_steps"] if tuple(g) == tuple(goal)), None) for env in envs]
            entry.update({"anchor": anchor, "goal": list(goal), "rewards": rewards, "goal_steps": goal_steps})
            if all(rewards):
                all_success += 1
            else:
                plans[uid] = {"goal": goal, "instruction": goal_instruction(goal), "anchor": anchor, "rewards": rewards, "goal_steps": goal_steps}
        log.append(entry)
    metrics = {
        "hindsight/dead_groups": len(groups), "hindsight/llm_calls": len(jobs), "hindsight/llm_errors": usage["llm_errors"],
        "hindsight/llm_timeouts": usage["llm_timeouts"],
        "hindsight/claims_accepted": accepted_count, "hindsight/claims_rejected": rejected_count,
        "hindsight/relabeled_groups": len(plans), "hindsight/relabel_all_success_groups": all_success,
        "hindsight/llm_prompt_tokens": usage["prompt_tokens"], "hindsight/llm_completion_tokens": usage["completion_tokens"],
    }
    return plans, log, metrics


def action_token_mask(response_ids, tokenizer):
    """1 for response tokens that overlap the first <action>...</action> span (case-insensitive), else 0."""
    pieces = [tokenizer.decode([token]) for token in response_ids]
    text = "".join(pieces).lower()
    start, end = text.find("<action>"), text.find("</action>")
    if start == -1 or end == -1:
        return [0] * len(pieces)
    end += len("</action>")
    mask, position = [], 0
    for piece in pieces:
        mask.append(int(position < end and position + len(piece) > start))
        position += len(piece)
    return mask
