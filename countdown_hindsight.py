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
