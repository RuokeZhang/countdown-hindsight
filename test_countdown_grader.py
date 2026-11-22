import unittest

from countdown_grader import grade_countdown


class TestGradeCountdown(unittest.TestCase):
    def test_prompt_example_succeeds(self):
        result = grade_countdown("6 * 4 = 24\n24 / 2 = 12\n12 * 3 = 36", [2, 3, 4, 6], 36)
        self.assertTrue(result["success"])
        self.assertIsNone(result["stopped_at"])
        self.assertEqual(result["final_value"], 36)

    def test_surrounding_whitespace_is_ignored(self):
        result = grade_countdown("\n  44 + 19 = 63 \n63 + 35 = 98\n\n", [44, 19, 35], 98)
        self.assertTrue(result["success"])

    def test_explanation_text_fails_parse(self):
        result = grade_countdown("Here is the solution:\n44 + 19 = 63\n63 + 35 = 98", [44, 19, 35], 98)
        self.assertEqual(result["stopped_at"], "parse")

    def test_unicode_operator_fails_parse(self):
        result = grade_countdown("6 × 4 = 24\n24 / 2 = 12\n12 * 3 = 36", [2, 3, 4, 6], 36)
        self.assertEqual(result["stopped_at"], "parse")

    def test_single_line_expression_fails_parse(self):
        result = grade_countdown("(44 + 19) + 35 = 98", [44, 19, 35], 98)
        self.assertEqual(result["stopped_at"], "parse")

    def test_wrong_line_count_fails_parse(self):
        result = grade_countdown("44 + 19 = 63", [44, 19, 35], 98)
        self.assertEqual(result["stopped_at"], "parse")

    def test_empty_output_fails_parse(self):
        self.assertEqual(grade_countdown("   ", [44, 19, 35], 98)["stopped_at"], "parse")

    def test_wrong_equation_fails_arithmetic(self):
        result = grade_countdown("44 + 19 = 64\n64 + 34 = 98", [44, 19, 35], 98)
        self.assertEqual(result["stopped_at"], "arithmetic")

    def test_non_integer_division_fails_arithmetic(self):
        result = grade_countdown("7 / 2 = 3\n3 + 1 = 4", [7, 2, 1], 4)
        self.assertEqual(result["stopped_at"], "arithmetic")

    def test_division_by_zero_fails_arithmetic(self):
        result = grade_countdown("5 - 5 = 0\n3 / 0 = 0", [5, 5, 3], 0)
        self.assertEqual(result["stopped_at"], "arithmetic")

    def test_negative_intermediate_is_allowed(self):
        result = grade_countdown("19 - 44 = -25\n35 + -25 = 10", [44, 19, 35], 10)
        self.assertTrue(result["success"])

    def test_operand_not_in_pool_fails_usage(self):
        result = grade_countdown("44 + 20 = 64\n64 + 34 = 98", [44, 19, 35], 98)
        self.assertEqual(result["stopped_at"], "usage")

    def test_reusing_a_number_fails_usage(self):
        result = grade_countdown("44 + 44 = 88\n88 + 10 = 98", [44, 19, 35], 98)
        self.assertEqual(result["stopped_at"], "usage")

    def test_duplicate_numbers_can_each_be_used_once(self):
        result = grade_countdown("5 + 5 = 10\n10 * 3 = 30", [5, 5, 3], 30)
        self.assertTrue(result["success"])

    def test_unused_number_fails_usage(self):
        result = grade_countdown("2 + 3 = 5\n5 * 5 = 25\n25 - 1 = 24", [2, 3, 4, 6], 24)
        self.assertEqual(result["stopped_at"], "usage")

    def test_intermediate_result_reused_twice_fails_usage(self):
        result = grade_countdown("2 + 3 = 5\n5 * 5 = 25\n4 + 6 = 10", [2, 3, 4, 6], 10)
        self.assertEqual(result["stopped_at"], "usage")

    def test_wrong_final_value_is_relabelable(self):
        result = grade_countdown("44 + 19 = 63\n63 - 35 = 28", [44, 19, 35], 98)
        self.assertEqual(result["stopped_at"], "target")
        self.assertTrue(result["relabelable"])
        self.assertEqual(result["final_value"], 28)

    def test_final_value_equal_to_initial_number_not_relabelable(self):
        result = grade_countdown("44 - 35 = 9\n19 * 9 = 171\n171 / 9 = 19", [44, 35, 9, 19], 98)
        self.assertEqual(result["stopped_at"], "target")
        self.assertEqual(result["final_value"], 19)
        self.assertFalse(result["relabelable"])

    def test_non_positive_final_value_not_relabelable(self):
        zero_result = grade_countdown("44 - 44 = 0\n0 * 35 = 0", [44, 44, 35], 98)
        negative_result = grade_countdown("19 - 44 = -25\n-25 - 35 = -60", [44, 19, 35], 98)
        self.assertFalse(zero_result["relabelable"])
        self.assertFalse(negative_result["relabelable"])
        self.assertEqual(negative_result["final_value"], -60)


if __name__ == "__main__":
    unittest.main()
