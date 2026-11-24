"""LLM hindsight relabeling of failed ALFWorld episodes with DeepSeek-V4-Pro, checked against the env state.

For every failed episode of the first --max_groups all-failed groups of the precheck, the model reads the episode text
(the original task, then each executed action with the environment's feedback) and names the most complete ALFWorld task the
agent actually accomplished, in task-template form. The claim is accepted only if the state-based achievements of that
episode contain it (type level, as in relabel_preview.goals_of); hot/cool/clean additionally need the matching
"You heat/cool/clean the <object>" feedback, so a property the object already had at the start does not count.
Every episode of the group is then rescored under each accepted goal.

Credentials: TOPCLOUD_BASE_URL / TOPCLOUD_API_KEY in the environment (OpenAI-compatible endpoint). Cost is not reported
by the endpoint, so token usage is logged and --max_calls bounds the number of episodes (each gets up to 4 attempts).
"""
import argparse
import collections
import concurrent.futures
import gzip
import json
import os
import re
import time
import urllib.error
import urllib.request

from relabel_preview import goals_of, type_of

MODEL = "azure/azure/DeepSeek-V4-Pro"
KINDS = ("put", "clean", "hot", "cool", "two", "look")
PROPERTY_EVENT = {"clean": "clean", "hot": "heat", "cool": "cool"}

PROMPT_V2_RULES = (
    '- The ONLY evidence of a placement is feedback of the form "You move the <object> to the <receptacle>." Walking to, opening or closing a receptacle while holding something is not a placement.\n'
    '- Heating, cooling and cleaning ("You heat/cool/clean the <object> using the <appliance>.") keep the object in the agent\'s hand; they do not put it in the microwave, fridge or sinkbasin. For clean/hot/cool, the placement must come AFTER that feedback.\n')
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


def executed_action(response):
    """The command the env received, as verl-agent's alfworld_projection builds it: lowercased, first <action> to first
    </action>; without both tags the last 30 characters (which the env usually rejects)."""
    text = response.lower()
    start, end = text.find("<action>"), text.find("</action>")
    if start == -1 or end == -1:
        return text[-30:]
    return text[start + len("<action>"):end].strip()


def episode_text(episode):
    lines = [f"Original task: {episode['task_description']}", ""]
    for step, turn in enumerate(episode["trajectory"], 1):
        lines.append(f"Step {step} action: {executed_action(turn['response'])}")
        lines.append(f"Step {step} feedback: {turn['feedback'].strip()}")
    return "\n".join(lines)


PROPERTY_PLACEMENT = re.compile(r"^put (hot|cool|clean) (.+) in (.+)$")


def satisfies(episode, goal):
    """State-based check of a type-level goal; hot/cool/clean also need the property's feedback event ("You heat/cool/
    clean the <instance>") on the very instance that was placed with that property."""
    if goal not in goals_of(episode):
        return False
    kind, obj, target = goal
    if kind not in PROPERTY_EVENT:
        return True
    placed = {match.group(2) for match in map(PROPERTY_PLACEMENT.match, episode["full"])
              if match and match.group(1) == kind and type_of(match.group(2)) == obj and type_of(match.group(3)) == target}
    treated = {event[0] for event in episode["text_events"][PROPERTY_EVENT[kind]]}
    return bool(placed & treated)


def system_prompt(version):
    if version == 2:
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT.replace(PROMPT_V2_RULES, "").replace(' "target" is always required when achieved is true.', "")


def call_model(base, key, episode, max_tokens, prompt_version):
    request = {"model": MODEL, "max_tokens": max_tokens, "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": system_prompt(prompt_version)}, {"role": "user", "content": episode_text(episode)}]}
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "hindsight-relabel/1.0"}
    for attempt in range(4):
        try:
            started = time.time()
            response = json.load(urllib.request.urlopen(urllib.request.Request(base + "/chat/completions", data=json.dumps(request).encode(), headers=headers), timeout=180))
            content = response["choices"][0]["message"].get("content") or ""
            return {"raw": content, "parsed": json.loads(content), "usage": response.get("usage", {}), "seconds": time.time() - started}
        except Exception as error:  # dropped connection, bad JSON, 429 or 5xx: retried; other 4xx: recorded as an error row at once
            last_error = repr(error)[:300]
            http_code = error.code if isinstance(error, urllib.error.HTTPError) else None
            if http_code is not None and 400 <= http_code < 500 and http_code != 429:
                break
            if attempt < 3:
                time.sleep((30 if http_code == 429 else 5) * (attempt + 1))
    return {"raw": None, "parsed": None, "error": last_error, "usage": {}, "seconds": None}


def verdict(episode, result):
    if result.get("error"):
        return None, "error"
    parsed = result["parsed"]
    if not isinstance(parsed, dict) or not parsed.get("achieved"):
        return None, "none"
    kind, obj, target = parsed.get("kind"), parsed.get("object"), parsed.get("target")
    if kind not in KINDS or not isinstance(obj, str) or not isinstance(target, str):
        return None, "malformed"
    goal = (kind, obj.strip().lower(), target.strip().lower())
    return goal, ("accepted" if satisfies(episode, goal) else "rejected")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", required=True)
    parser.add_argument("--out", required=True, help="jsonl, one row per relabeled episode")
    parser.add_argument("--max_groups", type=int, default=60)
    parser.add_argument("--max_calls", type=int, default=500)
    parser.add_argument("--max_tokens", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--prompt_version", type=int, choices=[1, 2], default=2, help="1 = first run's prompt (without the two placement rules)")
    args = parser.parse_args()
    base, key = os.environ["TOPCLOUD_BASE_URL"].rstrip("/"), os.environ["TOPCLOUD_API_KEY"]

    groups = collections.defaultdict(list)
    for line in gzip.open(args.episodes, "rt"):
        episode = json.loads(line)
        groups[episode["group"]].append(episode)
    dead_groups = [g for _, g in sorted(groups.items()) if not any(e["won"] for e in g)][: args.max_groups]
    jobs = [(group[0]["group"], index, episode) for group in dead_groups for index, episode in enumerate(group)][: args.max_calls]
    print(f"{len(dead_groups)} all-failed groups, {len(jobs)} episodes to relabel")

    done = set()
    if os.path.exists(args.out):
        with open(args.out, "rb") as existing:
            content = existing.read()
        if content and not content.endswith(b"\n"):    # drop the half-written last line of a killed run before appending
            with open(args.out, "wb") as existing:
                existing.write(content[: content.rfind(b"\n") + 1])
        for line in open(args.out):
            row = json.loads(line)
            if row.get("prompt_version", 1) != args.prompt_version:
                raise SystemExit(f"{args.out} holds prompt version {row.get('prompt_version', 1)} rows; use another --out")
            if row["status"] != "error":                # errored episodes are retried on resume
                done.add((row["group"], row["episode_index"]))
    with open(args.out, "a") as out_file, concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(call_model, base, key, episode, args.max_tokens, args.prompt_version): (group_id, index, episode)
                   for group_id, index, episode in jobs if (group_id, index) not in done}
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            group_id, index, episode = futures[future]
            result = future.result()
            goal, status = verdict(episode, result)
            group = groups[group_id]
            out_file.write(json.dumps({
                "group": group_id, "episode_index": index, "prompt_version": args.prompt_version, "task": episode["task"], "task_type": episode["task_type"],
                "task_description": episode["task_description"], "llm": result["parsed"], "llm_raw": result["raw"],
                "error": result.get("error"), "usage": result["usage"], "seconds": result["seconds"],
                "goal": list(goal) if goal else None, "status": status,
                "state_goals": sorted(map(list, goals_of(episode))),
                "rescored": [satisfies(e, goal) for e in group] if status == "accepted" else None,
            }) + "\n")
            out_file.flush()
            if count % 20 == 0:
                print(f"{count}/{len(futures)} done", flush=True)


if __name__ == "__main__":
    main()
