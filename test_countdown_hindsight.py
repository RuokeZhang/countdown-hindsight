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


class TestRelabelResponsesSplit(unittest.TestCase):
    RESPONSES = TestRelabelResponsesIndividually.RESPONSES

    def test_split_classes_and_rewards(self):
        result = relabel_responses_individually(self.RESPONSES, NUMS, TARGET, 1.0, "0:1:7", split_candidates=True)
        self.assertTrue(result["selected"])
        # Responses 0, 1, 7 are candidates; the rest are fixed by their stage.
        for position in (2,):
            self.assertEqual(result["classes"][position], "negative_parse")
        self.assertEqual(result["classes"][3], "negative_arithmetic")
        self.assertEqual(result["classes"][4], "negative_usage")
        self.assertEqual(result["classes"][5], "untouched")
        self.assertEqual(result["classes"][6], "negative_usage")
        own_values = {0: 28, 1: 60, 7: 28}
        for position, value in own_values.items():
            self.assertIn(result["classes"][position], ("positive", "negative_valid"))
            if result["classes"][position] == "positive":
                self.assertEqual((result["new_targets"][position], result["new_rewards"][position]), (value, 1.0))
            else:
                self.assertEqual((result["new_targets"][position], result["new_rewards"][position]), (None, 0.0))
        for position in (2, 3, 4, 6):
            self.assertEqual((result["new_targets"][position], result["new_rewards"][position]), (None, 0.0))
        self.assertEqual((result["new_targets"][5], result["new_rewards"][5]), (None, None))

    def test_split_is_reproducible_and_depends_on_seed(self):
        first = relabel_responses_individually(self.RESPONSES, NUMS, TARGET, 1.0, "0:1:7", split_candidates=True)
        second = relabel_responses_individually(self.RESPONSES, NUMS, TARGET, 1.0, "0:1:7", split_candidates=True)
        self.assertEqual(first, second)
        patterns = {tuple(relabel_responses_individually(self.RESPONSES, NUMS, TARGET, 1.0, f"0:{step}:7", split_candidates=True)["classes"]) for step in range(40)}
        self.assertGreater(len(patterns), 1)

    def test_split_probability_is_about_half(self):
        candidate = ["44 + 19 = 63\n63 - 35 = 28"] * 8
        positives = sum(relabel_responses_individually(candidate, NUMS, TARGET, 1.0, f"0:{step}:7", split_candidates=True)["classes"].count("positive") for step in range(500))
        self.assertTrue(1800 < positives < 2200, positives)

    def test_group_selection_matches_unsplit_mode(self):
        for step in range(200):
            seed_text = f"0:{step}:7"
            split = relabel_responses_individually(self.RESPONSES, NUMS, TARGET, 0.25, seed_text, split_candidates=True)
            unsplit = relabel_responses_individually(self.RESPONSES, NUMS, TARGET, 0.25, seed_text)
            self.assertEqual(split["selected"], unsplit["selected"])


if __name__ == "__main__":
    unittest.main()
