"""ALFWorld's hand-coded expert solves one subset task of each type; the tracker must record that task's goal.

Run on the training machine: cd /root/alf/hs && ALFWORLD_DATA=/root/alf/alfworld_data /root/alf/venv/bin/python -m unittest test_precheck_tracker -v
"""
import os
import unittest

import textworld
import textworld.gym
from alfworld.agents.environment.alfred_tw_env import AlfredDemangler, AlfredExpert, AlfredInfos

from precheck import TASK_TYPES, AchievementTracker

SUBSET_DIR = os.path.expandvars("$ALFWORLD_DATA/train_subset_240")
EXPECTED_KIND = {
    "pick_and_place_simple": "put ", "look_at_obj_in_light": "examine ", "pick_clean_then_place_in_recep": "put clean ",
    "pick_heat_then_place_in_recep": "put hot ", "pick_cool_then_place_in_recep": "put cool ", "pick_two_obj_and_place": "put two ",
}


def play_expert(game_file):
    infos = textworld.EnvInfos(won=True, admissible_commands=True, facts=True, extras=["gamefile", "expert_plan"])
    env_id = textworld.gym.register_games([game_file], infos, batch_size=1, asynchronous=False, max_episode_steps=60,
                                          wrappers=[AlfredDemangler(shuffle=False), AlfredInfos, AlfredExpert("handcoded")])
    env = textworld.gym.make(env_id)
    obs, info = env.reset()
    tracker = AchievementTracker(info["facts"][0])
    for _ in range(60):
        obs, _, dones, info = env.step([info["extra.expert_plan"][0][0]])
        tracker.update(info["facts"][0], obs[0])
        if dones[0]:
            break
    return bool(info["won"][0]), tracker.summary()


class TestTrackerOnExpertEpisodes(unittest.TestCase):
    def test_expert_goal_is_recorded_for_each_task_type(self):
        tasks = [line.strip() for line in open(os.path.join(os.path.dirname(__file__), "train_subset_240.txt"))]
        for task_type in TASK_TYPES:
            with self.subTest(task_type=task_type):
                # the hand-coded expert occasionally fails a task; use the first of this type's tasks it solves
                for task in [t for t in tasks if t.startswith(task_type)][:5]:
                    won, summary = play_expert(os.path.join(SUBSET_DIR, task, "game.tw-pddl"))
                    if won:
                        break
                print(task_type, won, summary["full"], summary["text_agrees_with_state"])
                self.assertTrue(won)
                self.assertTrue(any(a.startswith(EXPECTED_KIND[task_type]) for a in summary["full"]), summary["full"])
                self.assertTrue(summary["text_agrees_with_state"]["put"] and summary["text_agrees_with_state"]["hold"])


if __name__ == "__main__":
    unittest.main()
