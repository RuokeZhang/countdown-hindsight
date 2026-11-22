import random

from countdown_grader import grade_countdown

TARGET_MIN = 10
TARGET_MAX = 100


def relabel_group(responses, nums, original_target, relabel_probability, random_seed_text):
    """Decide whether to relabel one all-failed group and compute the rewards under the new target.

    A response is a relabel candidate when it passes parse/arithmetic/usage, misses the original
    target, and ends at a positive value that is not one of the given numbers and lies in
    [TARGET_MIN, TARGET_MAX]. The new target is drawn uniformly from the distinct candidate values.
    """
    candidate_values = sorted({
        grade["final_value"]
        for grade in (grade_countdown(response, nums, original_target) for response in responses)
        if grade["relabelable"] and TARGET_MIN <= grade["final_value"] <= TARGET_MAX
    })
    result = {"eligible": bool(candidate_values), "relabeled": False, "candidate_values": candidate_values, "new_target": None, "new_rewards": None}
    if not candidate_values:
        return result

    rng = random.Random(random_seed_text)
    if rng.random() >= relabel_probability:
        return result

    new_target = rng.choice(candidate_values)
    result["relabeled"] = True
    result["new_target"] = new_target
    result["new_rewards"] = [1.0 if grade_countdown(response, nums, new_target)["success"] else 0.0 for response in responses]
    return result


def relabel_responses_individually(responses, nums, original_target, relabel_probability, random_seed_text):
    """Per-sample hindsight for one all-failed group; the group enters with probability relabel_probability.

    Inside an entered group every response gets a class:
    - "positive": a relabel candidate (same condition as relabel_group); its own final value becomes its new target, reward 1.
    - "negative": stopped at parse/arithmetic/usage; prompt unchanged, reward 0.
    - "untouched": everything else (valid arithmetic whose value is not a candidate); left in the original group.
    """
    rng = random.Random(random_seed_text)
    result = {"selected": rng.random() < relabel_probability, "classes": None, "new_targets": None, "new_rewards": None}
    if not result["selected"]:
        return result

    classes, new_targets, new_rewards = [], [], []
    for response in responses:
        grade = grade_countdown(response, nums, original_target)
        if grade["relabelable"] and TARGET_MIN <= grade["final_value"] <= TARGET_MAX:
            classes.append("positive")
            new_targets.append(grade["final_value"])
            new_rewards.append(1.0 if grade_countdown(response, nums, grade["final_value"])["success"] else 0.0)
        elif grade["stopped_at"] in ("parse", "arithmetic", "usage"):
            classes.append("negative")
            new_targets.append(None)
            new_rewards.append(0.0)
        else:
            classes.append("untouched")
            new_targets.append(None)
            new_rewards.append(None)
    result.update(classes=classes, new_targets=new_targets, new_rewards=new_rewards)
    return result
