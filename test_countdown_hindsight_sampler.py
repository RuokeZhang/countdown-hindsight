"""Integration test of HindsightRelabelReplayBuffer._relabel_batch against a real (local) TransferQueue.

Needs the verl environment (ray, transfer_queue, verl). Run on the training machine when no training job is running:
    /root/work/verl/.venv/bin/python -m unittest test_countdown_hindsight_sampler -v
"""

import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import ray
import torch
import transfer_queue as tq
from tensordict import TensorDict
from transfer_queue import KVBatchMeta
from verl.utils.model import compute_position_id_with_mask
from verl.utils.tensordict_utils import list_of_dict_to_tensordict

from countdown_hindsight_sampler import HindsightRelabelReplayBuffer
from verl.trainer.ppo.v1.replay_buffer import ReplayBuffer
from run_countdown_baseline import build_prompt

MODEL_PATH = "Qwen/Qwen2.5-1.5B-Instruct"
NUMS = [44, 19, 35]
TARGET = 98
GROUPS = {
    "relabelme": ["44 + 19 = 63\n63 - 35 = 28", "44 - 19 = 25\n25 + 35 = 60", "Sure", "44 - 19 = 25\n25 + 35 = 60", "44 + 19 = 64\n64 + 34 = 98", "x", "44 * 19 = 836\n836 + 35 = 871", "19 + 44 = 63\n63 - 35 = 28"],
    "mixed": ["44 + 19 = 63\n63 + 35 = 98"] + ["44 + 19 = 63\n63 - 35 = 28"] * 7,
    "nocandidate": ["Sure"] * 8,
}


def fake_log_probs(length):
    return torch.full((length,), -0.25) - 0.001 * torch.arange(length, dtype=torch.float32)


class FakeActorGroup:
    """Stands in for actor_rollout_wg: writes deterministic per-position log probs over prompt+response."""

    def compute_log_prob(self, meta):
        data = tq.kv_batch_get(keys=meta.keys, partition_id=meta.partition_id, select_fields=["input_ids"])
        rows = [fake_log_probs(ids.numel()) for ids in data["input_ids"].unbind(0)]
        tq.kv_batch_put(keys=meta.keys, partition_id=meta.partition_id, fields=TensorDict({"log_probs": torch.nested.as_nested_tensor(rows, layout=torch.jagged)}, batch_size=len(rows)))
        return list(meta.keys)


class FakeTrainer:
    def __init__(self):
        self.config = SimpleNamespace(actor_rollout_ref=SimpleNamespace(rollout=SimpleNamespace(log_prob_micro_batch_size_per_gpu=4)))
        self.actor_rollout_wg = FakeActorGroup()

    def _compute_old_log_prob(self, batch, metrics):
        return batch

    def _compute_advantage(self, batch, metrics):
        return batch

    def refill(self):
        pass


class TestHindsightSamplerTransferQueue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ray.init(num_cpus=4, include_dashboard=False)
        tq.init()
        cls.log_dir = tempfile.mkdtemp()
        cls.sampler = HindsightRelabelReplayBuffer(
            trainer_mode="sync",
            trainer_config={},
            max_off_policy_threshold=None,
            max_off_policy_strategy="drop",
            sampler_kwargs={"seed": 0, "relabel_probability": 1.0, "relabel_log_dir": cls.log_dir, "model_path": MODEL_PATH},
            refill_fn=None,
        )
        cls.tokenizer = cls.sampler.tokenizer
        cls.per_sample_log_dir = tempfile.mkdtemp()
        cls.per_sample_sampler = HindsightRelabelReplayBuffer(
            trainer_mode="sync",
            trainer_config={},
            max_off_policy_threshold=None,
            max_off_policy_strategy="drop",
            sampler_kwargs={"seed": 0, "relabel_probability": 1.0, "relabel_log_dir": cls.per_sample_log_dir, "model_path": MODEL_PATH, "relabel_mode": "per_sample"},
            refill_fn=None,
        )
        cls.keep_prompt_log_dir = tempfile.mkdtemp()
        cls.keep_prompt_sampler = HindsightRelabelReplayBuffer(
            trainer_mode="sync",
            trainer_config={},
            max_off_policy_threshold=None,
            max_off_policy_strategy="drop",
            sampler_kwargs={"seed": 0, "relabel_probability": 1.0, "relabel_log_dir": cls.keep_prompt_log_dir, "model_path": MODEL_PATH, "relabel_mode": "per_sample_split_keep_prompt"},
            refill_fn=None,
        )
        cls.orig_ratio_log_dir = tempfile.mkdtemp()
        cls.orig_ratio_sampler = HindsightRelabelReplayBuffer(
            trainer_mode="sync",
            trainer_config={},
            max_off_policy_threshold=None,
            max_off_policy_strategy="drop",
            sampler_kwargs={"seed": 0, "relabel_probability": 1.0, "relabel_log_dir": cls.orig_ratio_log_dir, "model_path": MODEL_PATH, "relabel_mode": "per_sample_split_orig_ratio", "logprob_diagnostic": True},
            refill_fn=FakeTrainer().refill,
        )
        cls.split_log_dir = tempfile.mkdtemp()
        cls.split_sampler = HindsightRelabelReplayBuffer(
            trainer_mode="sync",
            trainer_config={},
            max_off_policy_threshold=None,
            max_off_policy_strategy="drop",
            sampler_kwargs={"seed": 0, "relabel_probability": 1.0, "relabel_log_dir": cls.split_log_dir, "model_path": MODEL_PATH, "relabel_mode": "per_sample_split"},
            refill_fn=None,
        )

    @classmethod
    def tearDownClass(cls):
        ray.shutdown()

    def _make_sample(self, uid, session_id, response_text, score):
        messages = [{"role": "user", "content": build_prompt({"nums": NUMS, "target": TARGET}, "v3")}]
        prompts = self.sampler._build_prompt_ids(messages)
        responses = torch.tensor(self.tokenizer.encode(response_text, add_special_tokens=False) + [self.tokenizer.convert_tokens_to_ids("<|im_end|>")], dtype=torch.int64)
        input_ids = torch.cat([prompts, responses])
        rm_scores = torch.zeros(responses.size(0), dtype=torch.float32)
        rm_scores[-1] = score
        sample = {
            "prompts": prompts,
            "responses": responses,
            "response_mask": torch.ones_like(responses),
            "loss_mask": torch.ones_like(responses),
            "input_ids": input_ids,
            "position_ids": compute_position_id_with_mask(torch.ones_like(input_ids).unsqueeze(0)).squeeze(0),
            "rm_scores": rm_scores,
            "num_turns": 2,
            "extra_fields": {"reward_extra_info": {"acc": score}, "min_global_steps": 1, "max_global_steps": 1},
            "uid": uid,
            "session_id": session_id,
            "raw_prompt": messages,
            "data_source": "countdown_3",
            "reward_model": {"style": "rule", "ground_truth": TARGET},
            "extra_info": {"problem_id": 7, "nums": NUMS, "target": TARGET, "num_count": 3, "split": "train"},
            "global_steps": 1,
        }
        tag = {"status": "success", "prompt_len": prompts.size(0), "response_len": responses.size(0), "seq_len": input_ids.size(0), "global_steps": 1, "min_global_steps": 1, "max_global_steps": 1}
        return sample, tag

    def test_relabel_in_place(self):
        keys, samples, tags = [], [], []
        for uid, responses in GROUPS.items():
            for session_id, response_text in enumerate(responses):
                score = 1.0 if (uid == "mixed" and session_id == 0) else 0.0
                sample, tag = self._make_sample(uid, session_id, response_text, score)
                keys.append(f"{uid}_{session_id}_0")
                samples.append(sample)
                tags.append(tag)
        tq.kv_batch_put(keys=keys, partition_id="train", fields=list_of_dict_to_tensordict(samples), tags=tags)

        relabeled_batch, metrics = self.sampler._relabel_batch(KVBatchMeta(partition_id="train", keys=keys, tags=tags), global_steps=1)
        self.assertEqual(relabeled_batch.keys, keys)
        self.assertEqual(metrics["hindsight/num_samples"], 24)
        self.assertEqual(metrics["hindsight/all_fail_groups"], 2)
        self.assertEqual(metrics["hindsight/eligible_groups"], 1)
        self.assertEqual(metrics["hindsight/relabeled_groups"], 1)

        log_row = json.loads(open(os.path.join(self.log_dir, "1.jsonl")).readline())
        new_target = log_row["new_target"]
        self.assertIn(new_target, [28, 60])
        expected_rewards = {28: [1, 0, 0, 0, 0, 0, 0, 1], 60: [0, 1, 0, 1, 0, 0, 0, 0]}[new_target]
        self.assertEqual(log_row["new_rewards"], [float(r) for r in expected_rewards])
        self.assertEqual(log_row["original_target"], TARGET)

        stored = tq.kv_batch_get(keys=keys, partition_id="train")
        expected_new_prompt = self.sampler._build_prompt_ids([{"role": "user", "content": build_prompt({"nums": NUMS, "target": new_target}, "v3")}])
        for index, key in enumerate(keys):
            row = stored[index]
            original = samples[index]
            self.assertEqual(row["uid"], original["uid"])
            self.assertTrue(torch.equal(row["responses"], original["responses"]))
            self.assertTrue(torch.equal(row["response_mask"], original["response_mask"]))
            self.assertTrue(torch.equal(row["loss_mask"], original["loss_mask"]))
            if key.startswith("relabelme_"):
                session_id = int(key.split("_")[1])
                self.assertTrue(torch.equal(row["prompts"], expected_new_prompt))
                self.assertTrue(torch.equal(row["input_ids"], torch.cat([expected_new_prompt, original["responses"]])))
                self.assertTrue(torch.equal(row["position_ids"], torch.arange(row["input_ids"].size(0))))
                self.assertEqual(float(row["rm_scores"].sum()), float(expected_rewards[session_id]))
                self.assertEqual(float(row["rm_scores"][-1]), float(expected_rewards[session_id]))
                self.assertEqual(row["reward_model"]["ground_truth"], new_target)
                self.assertEqual(row["extra_info"]["target"], new_target)
                self.assertEqual(row["raw_prompt"][0]["content"], build_prompt({"nums": NUMS, "target": new_target}, "v3"))
                decoded = self.tokenizer.decode(row["input_ids"], skip_special_tokens=True)
                self.assertIn(f"reach the target {new_target}.", decoded)
                self.assertTrue(decoded.endswith(self.tokenizer.decode(original["responses"], skip_special_tokens=True)))
                self.assertEqual(relabeled_batch.tags[index]["prompt_len"], expected_new_prompt.size(0))
                self.assertEqual(relabeled_batch.tags[index]["seq_len"], expected_new_prompt.size(0) + original["responses"].size(0))
            else:
                for field_name in ("prompts", "input_ids", "position_ids", "rm_scores"):
                    self.assertTrue(torch.equal(row[field_name], original[field_name]), field_name)
                self.assertEqual(row["reward_model"]["ground_truth"], TARGET)
                self.assertEqual(relabeled_batch.tags[index], tags[index])


    def _put_groups(self, groups):
        keys, samples, tags = [], [], []
        for uid, responses in groups.items():
            for session_id, response_text in enumerate(responses):
                score = 1.0 if (uid in ("psmixed", "spmixed", "kpmixed", "ormixed") and session_id == 0) else 0.0
                sample, tag = self._make_sample(uid, session_id, response_text, score)
                keys.append(f"{uid}_{session_id}_0")
                samples.append(sample)
                tags.append(tag)
        tq.kv_batch_put(keys=keys, partition_id="train", fields=list_of_dict_to_tensordict(samples), tags=tags)
        return keys, samples, tags

    def test_per_sample_relabel(self):
        groups = {"psrelabel": GROUPS["relabelme"], "psmixed": GROUPS["mixed"], "psnone": GROUPS["nocandidate"]}
        keys, samples, tags = self._put_groups(groups)
        relabeled_batch, metrics = self.per_sample_sampler._relabel_batch(KVBatchMeta(partition_id="train", keys=keys, tags=tags), global_steps=3)
        self.assertEqual(relabeled_batch.keys, keys)
        self.assertEqual(metrics["hindsight/all_fail_groups"], 2)
        self.assertEqual(metrics["hindsight/selected_groups"], 2)
        self.assertEqual(metrics["hindsight/pool_built"], 1)

        # relabelme: 28, 60, parse, 60, fake 98, parse, 871 (out of range), 28
        expected_classes = ["positive", "positive", "negative", "positive", "negative", "negative", "untouched", "positive"]
        expected_targets = [28, 60, None, 60, None, None, None, 28]
        self.assertEqual(metrics["hindsight/pooled_positive_samples"], 4)
        self.assertEqual(metrics["hindsight/pooled_negative_samples"], 3 + 8)
        self.assertEqual(metrics["hindsight/untouched_samples_in_selected_groups"], 1)

        log_rows = {row["uid"]: row for row in map(json.loads, open(os.path.join(self.per_sample_log_dir, "3.jsonl")))}
        self.assertEqual(set(log_rows), {"psrelabel", "psnone"})
        self.assertEqual(log_rows["psrelabel"]["classes"], expected_classes)
        self.assertEqual(log_rows["psnone"]["classes"], ["negative"] * 8)

        stored = tq.kv_batch_get(keys=keys, partition_id="train")
        pool_uids = set()
        for index, key in enumerate(keys):
            row, original = stored[index], samples[index]
            group, session_id = key.split("_")[0], int(key.split("_")[1])
            self.assertTrue(torch.equal(row["responses"], original["responses"]))
            self.assertTrue(torch.equal(row["response_mask"], original["response_mask"]))
            if group == "psmixed":
                for field_name in ("prompts", "input_ids", "position_ids", "rm_scores"):
                    self.assertTrue(torch.equal(row[field_name], original[field_name]), field_name)
                self.assertEqual(row["uid"], "psmixed")
                self.assertEqual(relabeled_batch.tags[index], tags[index])
                continue
            cls = expected_classes[session_id] if group == "psrelabel" else "negative"
            if cls == "untouched":
                self.assertEqual(row["uid"], group)
                self.assertTrue(torch.equal(row["input_ids"], original["input_ids"]))
                self.assertEqual(float(row["rm_scores"].sum()), 0.0)
                continue
            pool_uids.add(row["uid"])
            self.assertNotIn("_", row["uid"])
            if cls == "positive":
                new_target = expected_targets[session_id]
                expected_prompt = self.sampler._build_prompt_ids([{"role": "user", "content": build_prompt({"nums": NUMS, "target": new_target}, "v3")}])
                self.assertTrue(torch.equal(row["prompts"], expected_prompt))
                self.assertTrue(torch.equal(row["input_ids"], torch.cat([expected_prompt, original["responses"]])))
                self.assertEqual(float(row["rm_scores"][-1]), 1.0)
                self.assertEqual(float(row["rm_scores"].sum()), 1.0)
                self.assertEqual(row["extra_info"]["target"], new_target)
                self.assertEqual(row["reward_model"]["ground_truth"], new_target)
                self.assertEqual(relabeled_batch.tags[index]["prompt_len"], expected_prompt.size(0))
            else:
                for field_name in ("prompts", "input_ids", "position_ids"):
                    self.assertTrue(torch.equal(row[field_name], original[field_name]), field_name)
                self.assertEqual(float(row["rm_scores"].sum()), 0.0)
                self.assertEqual(row["extra_info"]["target"], TARGET)
                self.assertEqual(relabeled_batch.tags[index], tags[index])
        self.assertEqual(len(pool_uids), 1)
        self.assertNotIn(pool_uids.pop(), groups)

    def test_per_sample_without_positive_builds_no_pool(self):
        keys, samples, tags = self._put_groups({"psonlybad": ["Sure"] * 8})
        _, metrics = self.per_sample_sampler._relabel_batch(KVBatchMeta(partition_id="train", keys=keys, tags=tags), global_steps=4)
        self.assertEqual(metrics["hindsight/pool_built"], 0)
        stored = tq.kv_batch_get(keys=keys, partition_id="train")
        for index in range(len(keys)):
            self.assertEqual(stored[index]["uid"], "psonlybad")
            self.assertTrue(torch.equal(stored[index]["input_ids"], samples[index]["input_ids"]))

    def test_per_sample_split_relabel(self):
        keys, samples, tags = self._put_groups({"sprelabel": GROUPS["relabelme"], "spmixed": GROUPS["mixed"]})
        relabeled_batch, metrics = self.split_sampler._relabel_batch(KVBatchMeta(partition_id="train", keys=keys, tags=tags), global_steps=6)
        row = json.loads(open(os.path.join(self.split_log_dir, "6.jsonl")).readline())
        candidates = {0: 28, 1: 60, 3: 60, 7: 28}
        fixed = {2: "negative_parse", 4: "negative_arithmetic", 5: "negative_parse", 6: "untouched"}
        for position, cls in fixed.items():
            self.assertEqual(row["classes"][position], cls)
        for position in candidates:
            self.assertIn(row["classes"][position], ("positive", "negative_valid"))
        counts = {cls: row["classes"].count(cls) for cls in ("positive", "negative_valid", "negative_parse", "negative_arithmetic", "negative_usage")}
        for cls, count in counts.items():
            self.assertEqual(metrics[f"hindsight/pooled_{cls}_samples"], count if metrics["hindsight/pool_built"] else 0)

        stored = tq.kv_batch_get(keys=keys, partition_id="train")
        pool_uids = set()
        for index, key in enumerate(keys):
            stored_row, original = stored[index], samples[index]
            group, position = key.split("_")[0], int(key.split("_")[1])
            if group == "spmixed":
                for field_name in ("prompts", "input_ids", "position_ids", "rm_scores"):
                    self.assertTrue(torch.equal(stored_row[field_name], original[field_name]), field_name)
                self.assertEqual(stored_row["uid"], "spmixed")
                continue
            cls = row["classes"][position]
            if cls == "untouched":
                self.assertEqual(stored_row["uid"], group)
                continue
            if not metrics["hindsight/pool_built"]:
                continue
            pool_uids.add(stored_row["uid"])
            if cls == "positive":
                self.assertEqual(stored_row["extra_info"]["target"], candidates[position])
                self.assertEqual(float(stored_row["rm_scores"].sum()), 1.0)
            else:
                self.assertTrue(torch.equal(stored_row["input_ids"], original["input_ids"]))
                self.assertEqual(stored_row["extra_info"]["target"], TARGET)
                self.assertEqual(float(stored_row["rm_scores"].sum()), 0.0)
        self.assertLessEqual(len(pool_uids), 1)

    def test_keep_prompt_matches_split_classes_and_keeps_prompts(self):
        split_keys, _, split_tags = self._put_groups({"kpsplitref": GROUPS["relabelme"]})
        self.split_sampler._relabel_batch(KVBatchMeta(partition_id="train", keys=split_keys, tags=split_tags), global_steps=9)
        keys, samples, tags = self._put_groups({"kprelabel": GROUPS["relabelme"], "kpmixed": GROUPS["mixed"]})
        relabeled_batch, metrics = self.keep_prompt_sampler._relabel_batch(KVBatchMeta(partition_id="train", keys=keys, tags=tags), global_steps=9)
        split_row = json.loads(open(os.path.join(self.split_log_dir, "9.jsonl")).readline())
        row = json.loads(open(os.path.join(self.keep_prompt_log_dir, "9.jsonl")).readline())
        # Same seed, step, problem_id and response order -> the same selection and the same 50/50 split as arm E.
        self.assertEqual(row["classes"], split_row["classes"])
        self.assertFalse(row["prompt_rewritten"])
        self.assertTrue(metrics["hindsight/pool_built"])
        stored = tq.kv_batch_get(keys=keys, partition_id="train")
        pool_uids = set()
        for index, key in enumerate(keys):
            stored_row, original = stored[index], samples[index]
            group, position = key.split("_")[0], int(key.split("_")[1])
            for field_name in ("prompts", "input_ids", "position_ids", "responses"):
                self.assertTrue(torch.equal(stored_row[field_name], original[field_name]), field_name)
            self.assertEqual(stored_row["extra_info"]["target"], TARGET)
            self.assertEqual(relabeled_batch.tags[index], tags[index])
            if group == "kpmixed":
                self.assertEqual(stored_row["uid"], "kpmixed")
                self.assertTrue(torch.equal(stored_row["rm_scores"], original["rm_scores"]))
                continue
            cls = row["classes"][position]
            if cls == "untouched":
                self.assertEqual(stored_row["uid"], group)
                continue
            pool_uids.add(stored_row["uid"])
            self.assertEqual(float(stored_row["rm_scores"].sum()), 1.0 if cls == "positive" else 0.0)
            self.assertEqual(float(stored_row["rm_scores"][-1]), 1.0 if cls == "positive" else 0.0)
        self.assertEqual(len(pool_uids), 1)
        self.assertIn("positive", row["classes"])

    def test_orig_ratio_replaces_only_positive_denominators(self):
        keys, samples, tags = [], [], []
        for uid, responses in {"orrelabel": GROUPS["relabelme"], "ormixed": GROUPS["mixed"], "ornone": GROUPS["nocandidate"]}.items():
            for session_id, response_text in enumerate(responses):
                score = 1.0 if (uid == "ormixed" and session_id == 0) else 0.0
                sample, tag = self._make_sample(uid, session_id, response_text, score)
                sample["old_log_probs"] = torch.full((sample["responses"].size(0),), -1.0)
                keys.append(f"{uid}_{session_id}_0")
                samples.append(sample)
                tags.append(tag)
        tq.kv_batch_put(keys=keys, partition_id="train", fields=list_of_dict_to_tensordict(samples), tags=tags)
        self.orig_ratio_sampler._relabel_batch(KVBatchMeta(partition_id="train", keys=keys, tags=tags), global_steps=11)
        metrics = {}
        # The stored old_log_probs (-1.0) deliberately differ from the fake actor's (~-0.25) so replaced rows are recognizable;
        # that also makes the controls disagree by ~0.6 nats per token, so the guard is relaxed here.
        with mock.patch("countdown_hindsight_sampler.MAX_CONTROL_TOKEN_MEAN_ABS_DIFF_FOR_ORIG_RATIO", 1.0):
            self.orig_ratio_sampler._run_logprob_diagnostic({}, metrics)
        row = json.loads(open(os.path.join(self.orig_ratio_log_dir, "11.jsonl")).readline())
        positive_keys = [key for key, cls in zip(row["keys"], row["classes"]) if cls == "positive"]
        self.assertTrue(positive_keys)
        self.assertEqual(metrics["hindsight/orig_ratio_replaced_samples"], len(positive_keys))
        self.assertEqual(metrics["hindsight/orig_ratio_changed_samples"], len(positive_keys))
        self.assertEqual(metrics["hindsight/orig_ratio_writeback_max_abs_error"], 0.0)
        stored = tq.kv_batch_get(keys=keys, partition_id="train", select_fields=["old_log_probs"])["old_log_probs"].unbind(0)
        for index, key in enumerate(keys):
            response_length = samples[index]["responses"].size(0)
            if key in positive_keys:
                # The original-prompt forward predicts response token t from position prompt_length + t - 1.
                prompt_length = samples[index]["prompts"].size(0)
                expected = fake_log_probs(prompt_length + response_length)[prompt_length - 1 : prompt_length + response_length - 1]
                self.assertTrue(torch.equal(stored[index], expected), key)
            else:
                self.assertTrue(torch.equal(stored[index], torch.full((response_length,), -1.0)), key)

    def test_validation_batch_is_not_relabeled(self):
        val_batch = KVBatchMeta(partition_id="val", keys=["v_0_0"], tags=[{}])
        for sampler in (self.sampler, self.per_sample_sampler, self.split_sampler, self.keep_prompt_sampler, self.orig_ratio_sampler):
            with mock.patch.object(ReplayBuffer, "sample", return_value=(val_batch, {})), mock.patch.object(sampler, "_relabel_batch", side_effect=AssertionError("val relabeled")):
                batch, metrics = sampler.sample(global_steps=5, partition_id="val", batch_size=1)
            self.assertIs(batch, val_batch)
            self.assertEqual(metrics, {})


if __name__ == "__main__":
    unittest.main()
