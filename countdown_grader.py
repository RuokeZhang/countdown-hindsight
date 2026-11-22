import re
from collections import Counter

LINE_PATTERN = re.compile(r"^(-?\d+)\s*([+\-*/])\s*(-?\d+)\s*=\s*(-?\d+)$")


def grade_countdown(output_text, nums, target):
    """Return dict with success, stopped_at (parse/arithmetic/usage/target or None), final_value, relabelable."""
    result = {"success": False, "stopped_at": None, "final_value": None, "relabelable": False}

    lines = [line.strip() for line in output_text.strip().split("\n")]
    parsed_lines = []
    for line in lines:
        match = LINE_PATTERN.match(line)
        if match is None:
            result["stopped_at"] = "parse"
            return result
        left, operator, right, claimed = match.groups()
        parsed_lines.append((int(left), operator, int(right), int(claimed)))
    if len(parsed_lines) != len(nums) - 1:
        result["stopped_at"] = "parse"
        return result

    for left, operator, right, claimed in parsed_lines:
        if operator == "+":
            correct = left + right == claimed
        elif operator == "-":
            correct = left - right == claimed
        elif operator == "*":
            correct = left * right == claimed
        else:
            correct = right != 0 and left % right == 0 and left // right == claimed
        if not correct:
            result["stopped_at"] = "arithmetic"
            return result

    number_pool = Counter(nums)
    for left, operator, right, claimed in parsed_lines:
        for operand in (left, right):
            if number_pool[operand] == 0:
                result["stopped_at"] = "usage"
                return result
            number_pool[operand] -= 1
        number_pool[claimed] += 1
    remaining_numbers = list(number_pool.elements())
    if len(remaining_numbers) != 1:
        result["stopped_at"] = "usage"
        return result

    final_value = remaining_numbers[0]
    result["final_value"] = final_value
    if final_value == target:
        result["success"] = True
        return result

    result["stopped_at"] = "target"
    result["relabelable"] = final_value > 0 and final_value not in nums
    return result
