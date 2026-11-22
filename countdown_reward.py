import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from countdown_grader import grade_countdown


def compute_score(data_source, solution_str, ground_truth, extra_info=None, **kwargs):
    nums = [int(number) for number in extra_info["nums"]]
    grade = grade_countdown(solution_str, nums, int(ground_truth))
    return 1.0 if grade["success"] else 0.0
