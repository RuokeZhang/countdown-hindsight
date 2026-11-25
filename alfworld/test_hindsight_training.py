"""CPU tests for online hindsight relabeling in verl-agent (hindsight.py + the rollout-loop and trainer patches).

Run on the training machine:
  cd /root/alf/hs && ALFWORLD_DATA=/root/alf/alfworld_data PYTHONPATH=/root/alf/verl-agent /root/alf/venv/bin/python -m unittest test_hindsight_training -v
"""
import os
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np
import torch
from transformers import AutoTokenizer

from agent_system.environments.env_package.alfworld import hindsight
from verl import DataProto

SUBSET_DIR = os.path.expandvars("$ALFWORLD_DATA/train_subset_240")
TOKENIZER = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")
EXPECTED_KIND = {"pick_and_place_simple": "put", "look_at_obj_in_light": "look", "pick_clean_then_place_in_recep": "clean",
                 "pick_heat_then_place_in_recep": "hot", "pick_cool_then_place_in_recep": "cool", "pick_two_obj_and_place": "two"}


def play_expert(game_file):
    import textworld
    import textworld.gym
    from alfworld.agents.environment.alfred_tw_env import AlfredDemangler, AlfredExpert, AlfredInfos
    infos = textworld.EnvInfos(won=True, admissible_commands=True, facts=True, extras=["gamefile", "expert_plan"])
    env_id = textworld.gym.register_games([game_file], infos, batch_size=1, asynchronous=False, max_episode_steps=60,
                                          wrappers=[AlfredDemangler(shuffle=False), AlfredInfos, AlfredExpert("handcoded")])
    env = textworld.gym.make(env_id)
    obs, info = env.reset()
    tracker = hindsight.AchievementTracker(info["facts"][0])
    for _ in range(60):
        action = info["extra.expert_plan"][0][0]
        obs, _, dones, info = env.step([action])
        tracker.update(info["facts"][0], action, obs[0])
        if dones[0]:
            break
    return bool(info["won"][0]), tracker.record()


class TestTracker(unittest.TestCase):
    def test_expert_goal_is_recorded_for_each_task_type(self):
        tasks = [line.strip() for line in open(os.path.join(os.path.dirname(__file__), "train_subset_240.txt"))]
        for task_type, kind in EXPECTED_KIND.items():
            with self.subTest(task_type=task_type):
                for task in [t for t in tasks if t.startswith(task_type)][:5]:
                    won, record = play_expert(os.path.join(SUBSET_DIR, task, "game.tw-pddl"))
                    if won:
                        break
                self.assertTrue(won)
                self.assertIn(kind, {goal[0] for goal in record["goals"]}, record["goals"])
                self.assertTrue(record["trajectory"] and all(isinstance(a, str) and isinstance(f, str) for a, f in record["trajectory"]))


def fact(name, *args):
    return SimpleNamespace(name=name, arguments=[SimpleNamespace(name=a) for a in args])


class TestTrackerRules(unittest.TestCase):
    def test_put_back_is_not_a_put_and_cannot_complete_two(self):
        start = [fact("inreceptacle", "mug 1", "countertop 1"), fact("inreceptacle", "mug 2", "countertop 1"), fact("atlocation", "agent1", "loc 1")]
        tracker = hindsight.AchievementTracker(start)
        held = [fact("inreceptacle", "mug 2", "countertop 1"), fact("holds", "agent1", "mug 1"), fact("atlocation", "agent1", "loc 1")]
        tracker.update(held, "take mug 1 from countertop 1", "You pick up the mug 1 from the countertop 1.")
        tracker.update(start, "move mug 1 to countertop 1", "You move the mug 1 to the countertop 1.")
        self.assertEqual(tracker.record()["goals"], [])

    def test_new_placement_records_goal_and_step(self):
        start = [fact("inreceptacle", "mug 1", "countertop 1"), fact("atlocation", "agent1", "loc 1")]
        tracker = hindsight.AchievementTracker(start)
        held = [fact("holds", "agent1", "mug 1"), fact("atlocation", "agent1", "loc 1")]
        tracker.update(held, "take mug 1 from countertop 1", "You pick up the mug 1 from the countertop 1.")
        tracker.update(held + [fact("ishot", "mug 1")], "heat mug 1 with microwave 1", "You heat the mug 1 using the microwave 1.")
        placed = [fact("inreceptacle", "mug 1", "cabinet 2"), fact("ishot", "mug 1"), fact("atlocation", "agent1", "loc 1")]
        tracker.update(placed, "move mug 1 to cabinet 2", "You move the mug 1 to the cabinet 2.")
        record = tracker.record()
        self.assertEqual(record["goals"], [("hot", "mug", "cabinet"), ("put", "mug", "cabinet")])
        self.assertEqual(dict((tuple(g), step) for g, step in record["goal_steps"]), {("hot", "mug", "cabinet"): 3, ("put", "mug", "cabinet"): 3})

    def test_property_needs_treatment_in_this_episode(self):
        start = [fact("inreceptacle", "mug 1", "countertop 1"), fact("iscool", "mug 1"), fact("atlocation", "agent1", "loc 1")]
        tracker = hindsight.AchievementTracker(start)
        tracker.update([fact("holds", "agent1", "mug 1"), fact("iscool", "mug 1")], "take mug 1 from countertop 1", "You pick up the mug 1.")
        tracker.update([fact("inreceptacle", "mug 1", "cabinet 2"), fact("iscool", "mug 1")], "move mug 1 to cabinet 2", "You move the mug 1 to the cabinet 2.")
        self.assertEqual(tracker.record()["goals"], [("put", "mug", "cabinet")])


class TestAddHindsightRows(unittest.TestCase):
    def test_copies_truncation_keys_and_arrays(self):
        from agent_system.multi_turn_rollout.rollout_loop import TrajectoryCollector
        collector = TrajectoryCollector.__new__(TrajectoryCollector)
        collector.tokenizer = TOKENIZER
        task = "put some candle on countertop."
        total, uids = [], ["g0", "g0", "g1", "g1"]
        for env in range(4):
            rows = []
            for turn in range(3):
                row = make_row(f"Your task is to: {task} Step {turn}.", f"<action>act {turn}</action>")
                row.update({"uid": uids[env], "traj_uid": f"t{env}", "active_masks": turn < 3 - (env == 1)})
                rows.append(row)
            total.append(rows)
        rewards = np.zeros(4, dtype=np.float32)
        rewards[2] = 10.0                                            # group g1 is not all-failed
        lengths = np.array([3, 2, 3, 3], dtype=np.float32)
        traj = np.array([f"t{i}" for i in range(4)], dtype=object)
        tools = np.zeros(4, dtype=np.float32)
        envs = SimpleNamespace(tasks=[task] * 4, episode_records=lambda: [{"goals": [], "goal_steps": [], "trajectory": []}] * 4)
        plan = {"g0": {"goal": ("put", "cloth", "drawer"), "instruction": "put a cloth in drawer.", "anchor": 0, "rewards": [1.0, 0.0], "goal_steps": [2, None]}}
        def fake_plan(groups, records, tasks, seed_text, max_workers):
            self.assertEqual(set(groups), {"g0"})                    # only the all-failed group
            return plan, [], {}
        with mock.patch("agent_system.multi_turn_rollout.rollout_loop.plan_relabels", fake_plan):
            new_total, new_rewards, new_lengths, new_traj, new_tools = collector.add_hindsight_rows(total, rewards, lengths, traj, tools, envs, {"seed": 0})
        self.assertEqual(len(new_total), 6)
        success_copy, fail_copy = new_total[4], new_total[5]
        self.assertEqual(len(success_copy), 2)                       # truncated at the goal step
        self.assertEqual(len(fail_copy), 2)                          # only env 1's two active rows
        self.assertEqual(list(new_rewards[4:]), [10.0, 0.0])
        self.assertEqual(list(new_lengths[4:]), [2.0, 2.0])
        self.assertEqual(success_copy[0]["uid"], fail_copy[0]["uid"])
        self.assertNotIn(success_copy[0]["uid"], ("g0", "g1"))
        self.assertEqual(new_traj[4], success_copy[0]["traj_uid"])
        self.assertEqual([r["behavior_row_key"] for r in success_copy], ["t0:0", "t0:1"])
        self.assertTrue(all(r["hindsight"] for r in success_copy) and not any(r["hindsight"] for rows in new_total[:4] for r in rows))
        self.assertIn("put a cloth in drawer.", TOKENIZER.decode(success_copy[0]["prompts"][success_copy[0]["attention_mask"][:64].bool()]))


class TestActorTrainMask(unittest.TestCase):
    def test_masked_kl_keeps_other_tokens_weights(self):
        from verl.trainer.ppo.core_algos import agg_loss
        response_mask = torch.ones(2, 4)
        train_mask = torch.tensor([[1.0, 1.0, 1.0, 1.0], [0.0, 1.0, 0.0, 0.0]])
        kld = torch.ones(2, 4, requires_grad=True)
        agg_loss(loss_mat=kld * train_mask, loss_mask=response_mask, loss_agg_mode="token-mean").backward()
        self.assertTrue(torch.allclose(kld.grad, train_mask / 8))


def make_row(prompt_text, response_text, prompt_length=64, response_length=24):
    prompt_ids = TOKENIZER(prompt_text, add_special_tokens=False)["input_ids"]
    response_ids = TOKENIZER(response_text, add_special_tokens=False)["input_ids"]
    prompts = torch.full((prompt_length,), TOKENIZER.pad_token_id)
    prompts[prompt_length - len(prompt_ids):] = torch.tensor(prompt_ids)
    responses = torch.full((response_length,), TOKENIZER.pad_token_id)
    responses[: len(response_ids)] = torch.tensor(response_ids)
    attention = torch.zeros(prompt_length + response_length, dtype=torch.long)
    attention[prompt_length - len(prompt_ids): prompt_length + len(response_ids)] = 1
    return {"prompts": prompts, "responses": responses, "input_ids": torch.cat([prompts, responses]), "attention_mask": attention,
            "position_ids": torch.clamp(torch.cumsum(attention, 0) - 1, min=0), "raw_prompt": [{"role": "user", "content": prompt_text}],
            "active_masks": True, "traj_uid": "t0", "uid": "g0"}


class TestRelabelRow(unittest.TestCase):
    def setUp(self):
        from agent_system.multi_turn_rollout.rollout_loop import TrajectoryCollector
        self.collector = TrajectoryCollector.__new__(TrajectoryCollector)
        self.collector.tokenizer = TOKENIZER

    def test_prompt_replaced_response_kept_action_mask(self):
        row = make_row("Your task is to: put some candle on countertop. Now act.", "<think>go</think><Action>go to drawer 1</Action>")
        new = self.collector.relabel_row(row, "put some candle on countertop.", "put a cloth in drawer.")
        prompt_mask = new["attention_mask"][:64].bool()
        self.assertEqual(TOKENIZER.decode(new["prompts"][prompt_mask]), "Your task is to: put a cloth in drawer. Now act.")
        self.assertTrue(torch.equal(new["responses"], row["responses"]))
        self.assertTrue(torch.equal(new["attention_mask"][64:], row["attention_mask"][64:]))
        self.assertTrue(torch.equal(new["input_ids"][64:], row["responses"]))
        valid = new["attention_mask"].bool()
        self.assertTrue(torch.equal(new["position_ids"][valid], torch.arange(int(valid.sum()))))
        self.assertEqual(new["raw_prompt"][0]["content"], "Your task is to: put a cloth in drawer. Now act.")
        masked = TOKENIZER.decode(row["responses"][new["action_mask"].bool()])
        self.assertIn("go to drawer 1", masked)
        self.assertNotIn("think", masked.lower())

    def test_missing_task_or_action(self):
        row = make_row("Your task is to: something else.", "no tags at all")
        self.assertIsNone(self.collector.relabel_row(row, "put some candle on countertop.", "put a cloth in drawer."))
        row = make_row("Your task is to: put some candle on countertop.", "no tags at all")
        self.assertEqual(int(self.collector.relabel_row(row, "put some candle on countertop.", "put a cloth in drawer.")["action_mask"].sum()), 0)


class TestBehaviorLogProbs(unittest.TestCase):
    def test_hindsight_rows_take_source_log_probs(self):
        from verl.trainer.ppo.ray_trainer import apply_behavior_log_probs
        old = torch.tensor([[-1.0, -2.0, 0.0], [-0.5, -0.5, -0.5], [-1.0 + np.log(1.5), -2.0, 0.0], [-0.5, -0.5 + np.log(0.5), -0.5]])
        mask = torch.tensor([[1, 1, 0], [1, 1, 1], [1, 1, 0], [0, 1, 1]], dtype=torch.float32)
        batch = DataProto.from_dict(tensors={"old_log_probs": old.clone(), "response_mask": mask},
                                    non_tensors={"hindsight": np.array([False, False, True, True], dtype=object),
                                                 "row_key": np.array(["a:0", "b:0", "c:0", "d:0"], dtype=object),
                                                 "behavior_row_key": np.array(["", "", "a:0", "b:0"], dtype=object)})
        metrics = apply_behavior_log_probs(batch, "behavior")
        self.assertTrue(torch.equal(batch.batch["old_log_probs"][2], old[0]))
        self.assertTrue(torch.equal(batch.batch["old_log_probs"][3], old[1]))
        self.assertTrue(torch.equal(batch.batch["old_log_probs"][:2], old[:2]))
        # trained hindsight tokens: row 2 -> ratios 1.5, 1.0; row 3 -> 0.5, 1.0
        self.assertEqual(metrics["hindsight/trained_tokens"], 4)
        self.assertAlmostEqual(metrics["hindsight/ratio_above_1.2"], 0.25)
        self.assertAlmostEqual(metrics["hindsight/ratio_below_0.8"], 0.25)
        self.assertAlmostEqual(metrics["hindsight/ratio_0.8_to_1.2"], 0.5)

    def test_relabeled_reference_keeps_recomputed(self):
        from verl.trainer.ppo.ray_trainer import apply_behavior_log_probs
        old = torch.tensor([[-1.0], [-3.0]])
        batch = DataProto.from_dict(tensors={"old_log_probs": old.clone(), "response_mask": torch.ones(2, 1)},
                                    non_tensors={"hindsight": np.array([False, True], dtype=object), "row_key": np.array(["a:0", "c:0"], dtype=object),
                                                 "behavior_row_key": np.array(["", "a:0"], dtype=object)})
        apply_behavior_log_probs(batch, "relabeled")
        self.assertTrue(torch.equal(batch.batch["old_log_probs"], old))


class TestPlanRelabels(unittest.TestCase):
    def test_only_checker_accepted_claims_become_anchors(self):
        goal = ("put", "cloth", "drawer")
        records = [{"goals": [goal], "goal_steps": [[list(goal), 4]], "trajectory": [("go", "ok")]}, {"goals": [], "goal_steps": [], "trajectory": []},
                   {"goals": [goal, ("put", "mug", "desk")], "goal_steps": [[list(goal), 2], [["put", "mug", "desk"], 5]], "trajectory": [("go", "ok")]},
                   {"goals": [("put", "mug", "desk")], "goal_steps": [[["put", "mug", "desk"], 7]], "trajectory": [("go", "ok")]}]
        claims = {0: {"achieved": True, "kind": "put", "object": "cloth", "target": "drawer"},
                  2: {"achieved": True, "kind": "put", "object": "spoon", "target": "drawer"},       # not in state: rejected
                  3: {"achieved": True, "kind": "put", "object": "mug", "target": "desk"}}
        tasks = ["task a"] * 4
        texts = {}
        def ask(base, key, text, timeout):
            return claims[texts[text]], {"prompt_tokens": 10, "completion_tokens": 2}
        for env in (0, 2, 3):
            records[env]["trajectory"] = [(f"action {env}", "ok")]
            texts[hindsight.episode_text(tasks[env], records[env]["trajectory"])] = env
        with mock.patch.object(hindsight, "ask_llm", ask), mock.patch.object(hindsight, "load_credentials", return_value=("http://x", "k")):
            plans, log, metrics = hindsight.plan_relabels({"g": [0, 1, 2, 3]}, records, tasks, seed_text="s")
        self.assertEqual(metrics["hindsight/llm_calls"], 3)                 # env 1 has no state goal: never sent
        self.assertEqual(metrics["hindsight/claims_accepted"], 2)
        self.assertEqual(metrics["hindsight/claims_rejected"], 1)
        plan = plans["g"]
        self.assertIn(plan["anchor"], (0, 3))
        expected = {goal: ([1.0, 0.0, 1.0, 0.0], [4, None, 2, None]), ("put", "mug", "desk"): ([0.0, 0.0, 1.0, 1.0], [None, None, 5, 7])}[tuple(plan["goal"])]
        self.assertEqual(plan["rewards"], expected[0])
        self.assertEqual(plan["goal_steps"], expected[1])
        self.assertEqual(plan["instruction"], hindsight.goal_instruction(plan["goal"]))

    def test_all_success_relabel_is_dropped(self):
        goal = ("put", "cloth", "drawer")
        records = [{"goals": [goal], "goal_steps": [[list(goal), 1]], "trajectory": [(f"a{i}", "ok")]} for i in range(2)]
        claim = {"achieved": True, "kind": "put", "object": "cloth", "target": "drawer"}
        with mock.patch.object(hindsight, "ask_llm", lambda *a: (claim, {})), mock.patch.object(hindsight, "load_credentials", return_value=("http://x", "k")):
            plans, _, metrics = hindsight.plan_relabels({"g": [0, 1]}, records, ["t", "t"], seed_text="s")
        self.assertEqual(plans, {})
        self.assertEqual(metrics["hindsight/relabel_all_success_groups"], 1)


class TestTokenMeanWeights(unittest.TestCase):
    def test_short_and_long_rows_get_equal_per_token_weight(self):
        """verl's token-mean: a 4-token row's tokens weigh the same as a 400-token row's (no per-row normalization)."""
        from verl.trainer.ppo.core_algos import agg_loss
        mask = torch.zeros(2, 400)
        mask[0, :4] = 1
        mask[1, :] = 1
        loss_mat = torch.zeros(2, 400, requires_grad=True)
        agg_loss(loss_mat=loss_mat, loss_mask=mask, loss_agg_mode="token-mean").backward()
        weights = loss_mat.grad[mask.bool()]
        self.assertTrue(torch.allclose(weights, torch.full_like(weights, 1 / 404)))


class TestHindsightMasks(unittest.TestCase):
    def test_attention_kept_action_masked_and_rows_spread(self):
        from verl.trainer.ppo.ray_trainer import apply_hindsight_masks, compute_response_mask
        num_original, num_hindsight, prompt_length, response_length = 96, 48, 3, 6
        rows = num_original + num_hindsight
        attention_mask = torch.ones(rows, prompt_length + response_length, dtype=torch.long)
        action_mask = torch.zeros(rows, response_length)
        action_mask[:, 4:] = 1
        is_hindsight = np.array([False] * num_original + [True] * num_hindsight, dtype=object)
        batch = DataProto.from_dict(tensors={"attention_mask": attention_mask.clone(), "responses": torch.zeros(rows, response_length, dtype=torch.long),
                                             "action_mask": action_mask},
                                    non_tensors={"hindsight": is_hindsight, "row_key": np.array([str(i) for i in range(rows)], dtype=object)})
        batch.batch["response_mask"] = compute_response_mask(batch)      # a view of attention_mask
        apply_hindsight_masks(batch, action_only_mask=True, shuffle_seed=0)
        self.assertTrue(torch.equal(batch.batch["attention_mask"], attention_mask))   # thought tokens stay in the input
        flags = batch.non_tensor_batch["hindsight"].astype(bool)
        self.assertTrue(torch.equal(batch.batch["hindsight_flag"], torch.from_numpy(flags).float()))
        self.assertTrue(torch.equal(batch.batch["response_mask"][flags], action_mask[:num_hindsight].long()))
        self.assertTrue(torch.equal(batch.batch["response_mask"][~flags], torch.ones(num_original, response_length, dtype=torch.long)))
        self.assertTrue(torch.equal(batch.batch["token_train_mask"], batch.batch["response_mask"]))
        self.assertNotEqual([int(k) for k in batch.non_tensor_batch["row_key"]], list(range(rows)))
        for start in range(0, rows, 16):       # every mini-batch of 16 rows mixes original and hindsight rows
            self.assertTrue(0 < flags[start:start + 16].sum() < 16)


class TestHindsightLossTerm(unittest.TestCase):
    def test_equal_weight_per_hindsight_token_across_micro_batches(self):
        from verl.workers.actor.dp_actor import hindsight_loss_term
        short_tokens = torch.zeros(4, requires_grad=True)
        long_tokens = torch.zeros(400, requires_grad=True)
        total = (hindsight_loss_term(short_tokens.mean(), 4, 404, 0.1, None)
                 + hindsight_loss_term(long_tokens.mean(), 400, 404, 0.1, None))
        total.backward()
        self.assertTrue(torch.allclose(short_tokens.grad, torch.full((4,), 0.1 / 404)))
        self.assertTrue(torch.allclose(long_tokens.grad, torch.full((400,), 0.1 / 404)))

    def test_cap_drops_the_gradient(self):
        from verl.workers.actor.dp_actor import hindsight_loss_term
        tokens = torch.full((4,), 2.0, requires_grad=True)
        hindsight_loss_term(tokens.mean(), 4, 4, 0.1, cap=1.0).backward()
        self.assertTrue(torch.equal(tokens.grad, torch.zeros(4)))
        tokens.grad = None
        hindsight_loss_term(tokens.mean(), 4, 4, 0.1, cap=3.0).backward()
        self.assertTrue(torch.allclose(tokens.grad, torch.full((4,), 0.1 / 4)))

    def test_near_equal_sizes(self):
        from verl.workers.actor.dp_actor import near_equal_sizes
        for num_rows, num_parts in ((4500, 24), (193, 7), (9, 5), (3, 8)):
            sizes = near_equal_sizes(num_rows, num_parts)
            self.assertEqual(len(sizes), min(num_rows, num_parts))
            self.assertEqual(sum(sizes), num_rows)
            self.assertLessEqual(max(sizes) - min(sizes), 1)
        self.assertEqual([len(part) for part in torch.arange(9).split(near_equal_sizes(9, 5))], [2, 2, 2, 2, 1])


if __name__ == "__main__":
    unittest.main()
