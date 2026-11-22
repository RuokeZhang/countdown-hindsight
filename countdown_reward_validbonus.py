import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from countdown_grader import grade_countdown

VALID_BUT_WRONG_TARGET_REWARD = 0.1


def compute_score(data_source, solution_str, ground_truth, extra_info=None, **kwargs):
    nums = [int(number) for number in extra_info["nums"]]
    grade = grade_countdown(solution_str, nums, int(ground_truth))
    if grade["success"]:
        score = 1.0
    elif grade["stopped_at"] == "target":
        score = VALID_BUT_WRONG_TARGET_REWARD
    else:
        score = 0.0
    # "acc" makes verl report val-core/<data_source>/acc as the four-step success rate rather than the shaped score.
    return {"score": score, "acc": 1.0 if grade["success"] else 0.0}
