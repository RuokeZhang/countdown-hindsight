import unittest

from countdown_hindsight import relabel_group, relabel_responses_individually

NUMS = [44, 19, 35]
TARGET = 98


class TestRelabelGroup(unittest.TestCase):
    def test_no_relabelable_response_skips_group(self):
        responses = ["Sure: 44 + 19", "44 + 19 = 64\n64 + 34 = 98", "44 + 20 = 64\n64 + 34 = 98", "19 - 44 = -25\n-25 - 35 = -60"]
        result = relabel_group(responses, NUMS, TARGET, 1.0, "0:1:uid")
        self.assertFalse(result["eligible"])
        self.assertFalse(result["relabeled"])
        self.assertIsNone(result["new_target"])
        self.assertIsNone(result["new_rewards"])

    def test_multiple_distinct_values_picks_one_of_them_and_rewards_match(self):
        responses = ["44 + 19 = 63\n63 - 35 = 28", "44 - 19 = 25\n25 + 35 = 60", "Sure: 44 + 19", "44 - 19 = 25\n25 + 35 = 60"]
        result = relabel_group(responses, NUMS, TARGET, 1.0, "0:1:uid")
        self.assertTrue(result["relabeled"])
        self.assertEqual(result["candidate_values"], [28, 60])
        self.assertIn(result["new_target"], [28, 60])
        expected = {28: [1.0, 0.0, 0.0, 0.0], 60: [0.0, 1.0, 0.0, 1.0]}[result["new_target"]]
        self.assertEqual(result["new_rewards"], expected)

    def test_both_values_get_chosen_across_seeds(self):
        responses = ["44 + 19 = 63\n63 - 35 = 28", "44 - 19 = 25\n25 + 35 = 60"]
        chosen = {relabel_group(responses, NUMS, TARGET, 1.0, f"0:{step}:uid")["new_target"] for step in range(50)}
        self.assertEqual(chosen, {28, 60})

    def test_values_outside_target_range_are_not_candidates(self):
        responses = ["44 * 19 = 836\n836 + 35 = 871", "44 - 35 = 9\n9 - 19 = -10", "44 + 35 = 79\n79 / 19 = 4"]
        result = relabel_group(responses, NUMS, TARGET, 1.0, "0:1:uid")
        self.assertFalse(result["eligible"])
        mixed = relabel_group(responses + ["44 + 19 = 63\n63 - 35 = 28"], NUMS, TARGET, 1.0, "0:1:uid")
        self.assertEqual(mixed["candidate_values"], [28])
        self.assertEqual(mixed["new_rewards"], [0.0, 0.0, 0.0, 1.0])

    def test_value_equal_to_an_input_number_is_not_a_candidate(self):
        result = relabel_group(["44 + 35 = 79\n79 - 44 = 35"], [44, 35, 44], 98, 1.0, "0:1:uid")
        self.assertFalse(result["eligible"])

    def test_several_responses_with_same_value_all_get_reward(self):
        responses = ["44 + 19 = 63\n63 - 35 = 28", "19 + 44 = 63\n63 - 35 = 28", "44 - 35 = 9\n9 + 19 = 28", "44 + 19 = 64\n64 - 35 = 29"]
        result = relabel_group(responses, NUMS, TARGET, 1.0, "0:1:uid")
        self.assertEqual(result["candidate_values"], [28])
        self.assertEqual(result["new_target"], 28)
        self.assertEqual(result["new_rewards"], [1.0, 1.0, 1.0, 0.0])

    def test_same_seed_text_is_reproducible(self):
        responses = ["44 + 19 = 63\n63 - 35 = 28", "44 - 19 = 25\n25 + 35 = 60"]
        first = relabel_group(responses, NUMS, TARGET, 1.0, "0:7:abc")
        second = relabel_group(responses, NUMS, TARGET, 1.0, "0:7:abc")
        self.assertEqual(first, second)

    def test_probability_zero_never_relabels(self):
        result = relabel_group(["44 + 19 = 63\n63 - 35 = 28"], NUMS, TARGET, 0.0, "0:1:uid")
        self.assertTrue(result["eligible"])
        self.assertFalse(result["relabeled"])


class TestRelabelResponsesIndividually(unittest.TestCase):
    RESPONSES = [
        "44 + 19 = 63\n63 - 35 = 28",    # candidate -> positive, target 28
        "44 - 19 = 25\n25 + 35 = 60",    # candidate -> positive, target 60
        "Sure: 44 + 19",                 # parse failure -> negative
        "44 + 19 = 64\n64 + 34 = 98",    # wrong arithmetic claiming the target -> negative
        "44 + 19 = 63\n63 + 19 = 82",    # number reused -> usage failure -> negative
        "44 * 19 = 836\n836 + 35 = 871", # valid but value above TARGET_MAX -> untouched
        "44 + 35 = 79\n79 - 44 = 35",    # usage failure (44 used twice) -> negative
        "44 - 35 = 9\n9 + 19 = 28",      # candidate -> positive, target 28
    ]

    def test_classes_targets_and_rewards(self):
        result = relabel_responses_individually(self.RESPONSES, NUMS, TARGET, 1.0, "0:1:7")
        self.assertTrue(result["selected"])
        self.assertEqual(result["classes"], ["positive", "positive", "negative", "negative", "negative", "untouched", "negative", "positive"])
        self.assertEqual(result["new_targets"], [28, 60, None, None, None, None, None, 28])
        self.assertEqual(result["new_rewards"], [1.0, 1.0, 0.0, 0.0, 0.0, None, 0.0, 1.0])

    def test_value_equal_to_input_number_or_nonpositive_is_untouched(self):
        result = relabel_responses_individually(["44 - 35 = 9\n19 - 9 = 10", "19 - 44 = -25\n-25 + 35 = 10", "44 + 35 = 79\n79 - 60 = 19"], [44, 19, 35], TARGET, 1.0, "0:1:7")
        # 19 - 9 = 10: uses 19 and 9 (result) -> candidate value 10 (in range); the others fail arithmetic/usage.
        self.assertEqual(result["classes"][0], "positive")
        self.assertEqual(result["new_targets"][0], 10)
        self.assertEqual(result["classes"][2], "negative")
        equal_to_input = relabel_responses_individually(["44 + 35 = 79\n79 - 44 = 35"], [44, 35, 44], 98, 1.0, "0:1:7")
        self.assertEqual(equal_to_input["classes"], ["untouched"])

    def test_probability_zero_never_selects(self):
        result = relabel_responses_individually(self.RESPONSES, NUMS, TARGET, 0.0, "0:1:7")
        self.assertFalse(result["selected"])
        self.assertIsNone(result["classes"])

    def test_probability_selects_about_p_of_groups(self):
        selected = sum(relabel_responses_individually(self.RESPONSES, NUMS, TARGET, 0.25, f"0:{step}:7")["selected"] for step in range(2000))
        self.assertTrue(400 < selected < 600, selected)


if __name__ == "__main__":
    unittest.main()
