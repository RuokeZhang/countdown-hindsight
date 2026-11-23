import copy
import dataclasses
import json
import os
import statistics
import sys
import time
import uuid
import random
from collections import Counter, defaultdict

import torch
import transfer_queue as tq
from tensordict import TensorDict
from transfer_queue import KVBatchMeta
from transformers import AutoConfig
from verl.trainer.ppo.v1.replay_buffer import ReplayBuffer
from verl.utils import hf_tokenizer
from verl.utils.model import compute_position_id_with_mask
from verl.utils.tensordict_utils import list_of_dict_to_tensordict
from verl.utils.tokenizer.continuous_token_wiring import create_continuous_token_builder
from verl.workers.utils.padding import response_from_nested

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from countdown_hindsight import relabel_group, relabel_responses_individually
from run_countdown_baseline import build_prompt

PROMPT_VERSION = "v3"
DIAGNOSTIC_PARTITION = "hindsight_diag"
SMALL_LOGP_DIFF = 0.05
# Bf16 batch-composition noise between the two forwards was at most ~0.3 nats per token; a misaligned forward is far larger.
MAX_CONTROL_TOKEN_DIFF_FOR_ORIG_RATIO = 1.5
PER_SAMPLE_MODES = ("per_sample", "per_sample_split", "per_sample_split_keep_prompt", "per_sample_split_orig_ratio")


class HindsightRelabelReplayBuffer(ReplayBuffer):
    """Sync replay buffer that relabels all-failed Countdown groups in place before the PPO update.

    sampler_kwargs: seed, relabel_probability, relabel_log_dir, model_path, logprob_diagnostic, relabel_mode, advantage_log.

    relabel_mode "group" (arms A/C) rewrites a whole all-failed group to one new target. relabel_mode "per_sample" (arm D)
    gives each relabel candidate its own value as target (reward 1), keeps parse/arithmetic/usage failures on their
    original prompt (reward 0), and moves both into one new uid per step so GRPO normalizes them together; the other
    responses stay in their original all-zero group (advantage 0). relabel_mode "per_sample_split" (arm E) is per_sample
    except that each candidate is relabeled (reward 1) or kept on its original prompt as a negative (reward 0) with
    probability 0.5 each. "per_sample_split_keep_prompt" (arm F) is per_sample_split but positives keep their original
    prompt (reward 1 all the same). "per_sample_split_orig_ratio" (arm G) is per_sample_split but, for relabeled positives,
    old_log_probs (the PPO ratio denominator) is replaced by the per-token log probs under the ORIGINAL prompt taken from
    the diagnostic forward; it therefore requires logprob_diagnostic.

    With logprob_diagnostic, the trainer instance's _compute_old_log_prob is wrapped (the trainer is reached through
    refill_fn, a bound method of it). After verl computes old_log_probs for the whole batch, the wrapper runs one extra
    actor forward on the relabeled samples with their ORIGINAL prompts (plus unmodified control samples, which must
    reproduce their own old_log_probs), in a separate TransferQueue partition. The result is only logged.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seed = int(self.sampler_kwargs["seed"])
        self.relabel_probability = float(self.sampler_kwargs["relabel_probability"])
        self.relabel_log_dir = self.sampler_kwargs["relabel_log_dir"]
        model_path = self.sampler_kwargs["model_path"]
        os.makedirs(self.relabel_log_dir, exist_ok=True)
        self.tokenizer = hf_tokenizer(model_path)
        self.prompt_builder = create_continuous_token_builder(
            self.tokenizer,
            hf_model_type=AutoConfig.from_pretrained(model_path).model_type,
            chat_template_kwargs={},
            mm_processor_kwargs={},
            processor=None,
        )
        self.relabel_mode = self.sampler_kwargs.get("relabel_mode", "group")
        if self.relabel_mode not in ("group",) + PER_SAMPLE_MODES:
            raise ValueError(f"unknown relabel_mode {self.relabel_mode}")
        self.logprob_diagnostic = bool(self.sampler_kwargs.get("logprob_diagnostic", False))
        self.advantage_log = bool(self.sampler_kwargs.get("advantage_log", False))
        self.pending_diagnostic = None
        self.pending_log_rows = None
        self.last_train_step = None
        if self.relabel_mode == "per_sample_split_orig_ratio" and not self.logprob_diagnostic:
            raise ValueError("per_sample_split_orig_ratio takes the original-prompt log probs from the logprob diagnostic")
        if self.logprob_diagnostic or self.advantage_log:
            # The sampler is built inside PPOTrainer.__init__ (refill_fn is a bound method of it); actor_rollout_wg only
            # exists after trainer.init(), so it is looked up when the diagnostic runs.
            self.trainer = getattr(self.refill_fn, "__self__", None)
            if self.trainer is None or not hasattr(self.trainer, "_compute_old_log_prob") or not hasattr(self.trainer, "config"):
                raise RuntimeError("logprob_diagnostic/advantage_log need refill_fn to be a bound method of the verl PPOTrainer")
        if self.logprob_diagnostic:
            self._install_logprob_diagnostic()
        if self.advantage_log:
            self._install_advantage_log()

    def _install_advantage_log(self):
        """Log every sample's advantage after verl computes it (logging only, used to check the GRPO grouping)."""
        trainer = self.trainer
        compute_advantage = trainer._compute_advantage

        def compute_advantage_then_log(batch, metrics):
            output_batch = compute_advantage(batch, metrics)
            # verl stores advantages as a response-only nested tensor (response_to_nested), one row per sample.
            data = tq.kv_batch_get(keys=batch.keys, partition_id=batch.partition_id, select_fields=["uid", "advantages"])
            os.makedirs(os.path.join(self.relabel_log_dir, "advantages"), exist_ok=True)
            with open(os.path.join(self.relabel_log_dir, "advantages", f"{self.last_train_step}.jsonl"), "w") as log_file:
                for key, uid, values in zip(batch.keys, list(data["uid"]), data["advantages"].unbind(0)):
                    log_file.write(json.dumps({"key": key, "uid": uid, "advantage": float(values[0]), "token_spread": float(values.max() - values.min())}) + "\n")
            return output_batch

        trainer._compute_advantage = compute_advantage_then_log

    def _install_logprob_diagnostic(self):
        trainer = self.trainer
        self.log_prob_micro_batch_size = int(trainer.config.actor_rollout_ref.rollout.log_prob_micro_batch_size_per_gpu)
        compute_old_log_prob = trainer._compute_old_log_prob

        def compute_old_log_prob_then_diagnose(batch, metrics):
            output_batch = compute_old_log_prob(batch, metrics)
            # verl set calculate_entropy/compute_loss/temperature on the INPUT batch's extra_info for its forward.
            self._run_logprob_diagnostic(copy.deepcopy(batch.extra_info), metrics)
            return output_batch

        trainer._compute_old_log_prob = compute_old_log_prob_then_diagnose

    def sample(self, global_steps: int, partition_id: str, batch_size: int) -> tuple[KVBatchMeta, dict]:
        batch, metrics = super().sample(global_steps=global_steps, partition_id=partition_id, batch_size=batch_size)
        if partition_id == "val":
            return batch, metrics
        batch, relabel_metrics = self._relabel_batch(batch, global_steps)
        metrics.update(relabel_metrics)
        return batch, metrics

    @staticmethod
    def _copy_sample(source):
        sample = {}
        for field_name in source.keys():
            value = source[field_name]
            sample[field_name] = value.clone() if isinstance(value, torch.Tensor) else copy.deepcopy(value)
        return sample

    def _build_prompt_ids(self, messages):
        return torch.tensor(self.prompt_builder.build_initial_tokens(messages), dtype=torch.int64)

    def _relabel_batch(self, batch: KVBatchMeta, global_steps: int) -> tuple[KVBatchMeta, dict]:
        keys = list(batch.keys)
        summary = tq.kv_batch_get(keys=keys, partition_id=batch.partition_id, select_fields=["uid", "rm_scores", "responses", "extra_info"])
        # Non-tensor columns come back as tensordict LinkedList (no .tolist()); verl uses list(...) the same way.
        uids = list(summary["uid"])
        extra_infos = list(summary["extra_info"])
        scores = [float(score.sum()) for score in summary["rm_scores"].unbind(0)]
        response_texts = [self.tokenizer.decode(ids, skip_special_tokens=True) for ids in summary["responses"].unbind(0)]

        indices_by_uid = defaultdict(list)
        for index, uid in enumerate(uids):
            indices_by_uid[uid].append(index)

        if self.relabel_mode == "group":
            plan, log_rows, metrics = self._plan_group_relabel(keys, uids, scores, response_texts, extra_infos, indices_by_uid, global_steps)
        else:
            plan, log_rows, metrics = self._plan_per_sample_relabel(keys, uids, scores, response_texts, extra_infos, indices_by_uid, global_steps)

        # plan: batch index -> (new_target or None to keep the prompt, new_reward, new_uid or None to keep the uid)
        relabel_indices = sorted(plan)
        new_tags = [dict(tag) for tag in batch.tags]
        prompt_changed_indices = [i for i in relabel_indices if plan[i][0] is not None]
        original_samples_by_index = {}

        if relabel_indices:
            relabel_keys = [keys[i] for i in relabel_indices]
            full_data = tq.kv_batch_get(keys=relabel_keys, partition_id=batch.partition_id)
            new_samples = []
            for local_index, batch_index in enumerate(relabel_indices):
                sample = self._copy_sample(full_data[local_index])
                new_target, new_reward, new_uid = plan[batch_index]
                nums = [int(n) for n in extra_infos[batch_index]["nums"]]

                original_prompt_ids = self._build_prompt_ids(list(sample["raw_prompt"]))
                if not torch.equal(original_prompt_ids, sample["prompts"]):
                    raise RuntimeError(f"Rebuilt original prompt does not match rollout prompt for key {keys[batch_index]}")

                if new_target is not None:
                    original_samples_by_index[batch_index] = self._copy_sample(full_data[local_index])
                    new_messages = [{"role": "user", "content": build_prompt({"nums": nums, "target": new_target}, PROMPT_VERSION)}]
                    new_prompt_ids = self._build_prompt_ids(new_messages)
                    responses = sample["responses"]
                    input_ids = torch.cat([new_prompt_ids, responses], dim=0)
                    attention_mask = torch.ones_like(input_ids, dtype=torch.int64)
                    position_ids = compute_position_id_with_mask(attention_mask.unsqueeze(0)).squeeze(0).to(sample["position_ids"].dtype)
                    sample["prompts"] = new_prompt_ids
                    sample["input_ids"] = input_ids
                    sample["position_ids"] = position_ids
                    if "attention_mask" in sample:
                        sample["attention_mask"] = attention_mask
                    sample["raw_prompt"] = new_messages
                    sample["reward_model"] = {**sample["reward_model"], "ground_truth": new_target}
                    sample["extra_info"] = {**sample["extra_info"], "target": new_target}

                    tag = new_tags[batch_index]
                    tag["prompt_len"] = int(new_prompt_ids.size(0))
                    tag["seq_len"] = int(new_prompt_ids.size(0) + responses.size(0))
                    assert tag["response_len"] == int(responses.size(0))

                rm_scores = torch.zeros_like(sample["rm_scores"])
                rm_scores[-1] = new_reward
                sample["rm_scores"] = rm_scores
                if "reward_extra_info" in sample.get("extra_fields", {}):
                    sample["extra_fields"]["reward_extra_info"]["acc"] = new_reward
                if new_uid is not None:
                    sample["uid"] = new_uid
                new_samples.append(sample)

            tq.kv_batch_put(
                keys=relabel_keys,
                partition_id=batch.partition_id,
                fields=list_of_dict_to_tensordict(new_samples),
                tags=[new_tags[i] for i in relabel_indices],
            )

            stored = tq.kv_batch_get(keys=relabel_keys, partition_id=batch.partition_id, select_fields=["input_ids", "rm_scores", "uid"])
            for stored_input_ids, stored_rm_scores, stored_uid, sample in zip(stored["input_ids"].unbind(0), stored["rm_scores"].unbind(0), list(stored["uid"]), new_samples):
                if not torch.equal(stored_input_ids, sample["input_ids"]) or not torch.equal(stored_rm_scores, sample["rm_scores"]) or stored_uid != sample["uid"]:
                    raise RuntimeError("Relabeled sample read back from TransferQueue differs from what was written")

        # The diagnostic re-scores, under the ORIGINAL prompt, every sample whose prompt was changed.
        control_keys, control_count = [], 0
        if self.logprob_diagnostic and prompt_changed_indices:
            changed_key_set = {keys[i] for i in prompt_changed_indices}
            control_count = self.log_prob_micro_batch_size - len(prompt_changed_indices) % self.log_prob_micro_batch_size
            control_keys = [key for key in keys if key not in changed_key_set][:control_count]
        if self.relabel_mode == "per_sample_split_orig_ratio" and prompt_changed_indices and len(control_keys) != control_count:
            raise RuntimeError("orig_ratio needs the diagnostic forward but there are not enough control samples")
        if self.logprob_diagnostic and prompt_changed_indices and len(control_keys) == control_count:
            control_data = tq.kv_batch_get(keys=control_keys, partition_id=batch.partition_id)
            control_samples = [self._copy_sample(control_data[i]) for i in range(len(control_keys))]
            self.pending_diagnostic = {
                "step": global_steps,
                "partition_id": batch.partition_id,
                "real_keys": [keys[i] for i in prompt_changed_indices] + control_keys,
                "num_relabeled": len(prompt_changed_indices),
                "samples": [original_samples_by_index[i] for i in prompt_changed_indices] + control_samples,
                "tags": [batch.tags[i] for i in prompt_changed_indices] + [batch.tags[keys.index(key)] for key in control_keys],
                "new_rewards": [plan[i][1] for i in prompt_changed_indices],
                "batch_keys": keys,
            }
            self.pending_log_rows = log_rows
        else:
            self._write_relabel_log(global_steps, log_rows)

        self.last_train_step = global_steps
        with open(os.path.join(self.relabel_log_dir, "summary.jsonl"), "a") as summary_file:
            summary_file.write(json.dumps({"step": global_steps, **metrics}) + "\n")

        return dataclasses.replace(batch, tags=new_tags), metrics

    def _plan_group_relabel(self, keys, uids, scores, response_texts, extra_infos, indices_by_uid, global_steps):
        decisions = {}
        all_fail_groups = 0
        for uid, indices in indices_by_uid.items():
            if any(scores[i] != 0.0 for i in indices):
                continue
            all_fail_groups += 1
            extra_info = extra_infos[indices[0]]
            nums = [int(n) for n in extra_info["nums"]]
            # uid is a fresh uuid4 every run, so the dataset problem_id (unique within a batch) keys the randomness instead.
            random_seed_text = f"{self.seed}:{global_steps}:{int(extra_info['problem_id'])}"
            decision = relabel_group([response_texts[i] for i in indices], nums, int(extra_info["target"]), self.relabel_probability, random_seed_text)
            if decision["eligible"]:
                decisions[uid] = (decision, nums, int(extra_info["target"]))

        relabeled_uids = [uid for uid, (decision, _, _) in decisions.items() if decision["relabeled"]]
        plan, log_rows = {}, []
        for uid in relabeled_uids:
            decision, nums, original_target = decisions[uid]
            for position, batch_index in enumerate(indices_by_uid[uid]):
                plan[batch_index] = (decision["new_target"], decision["new_rewards"][position], None)
            log_rows.append({
                "step": global_steps,
                "uid": uid,
                "keys": [keys[i] for i in indices_by_uid[uid]],
                "nums": nums,
                "original_target": original_target,
                "new_target": decision["new_target"],
                "candidate_values": decision["candidate_values"],
                "responses": [response_texts[i] for i in indices_by_uid[uid]],
                "original_rewards": [scores[i] for i in indices_by_uid[uid]],
                "new_rewards": decision["new_rewards"],
            })

        ones_per_group = Counter(int(sum(row["new_rewards"])) for row in log_rows)
        metrics = {
            "hindsight/num_samples": len(keys),
            "hindsight/all_fail_groups": all_fail_groups,
            "hindsight/eligible_groups": len(decisions),
            "hindsight/relabeled_groups": len(relabeled_uids),
            "hindsight/relabeled_samples": len(plan),
            "hindsight/relabeled_all_success_groups": ones_per_group[8],
            "hindsight/new_reward_ones_mean": sum(sum(row["new_rewards"]) for row in log_rows) / max(len(log_rows), 1),
        }
        for ones in range(1, 9):
            metrics[f"hindsight/relabeled_groups_with_{ones}_ones"] = ones_per_group[ones]
        return plan, log_rows, metrics

    def _plan_per_sample_relabel(self, keys, uids, scores, response_texts, extra_infos, indices_by_uid, global_steps):
        all_fail_groups = 0
        log_rows = []
        for uid, indices in indices_by_uid.items():
            if any(scores[i] != 0.0 for i in indices):
                continue
            all_fail_groups += 1
            extra_info = extra_infos[indices[0]]
            nums = [int(n) for n in extra_info["nums"]]
            original_target = int(extra_info["target"])
            random_seed_text = f"{self.seed}:{global_steps}:{int(extra_info['problem_id'])}"
            decision = relabel_responses_individually(
                [response_texts[i] for i in indices], nums, original_target, self.relabel_probability, random_seed_text,
                split_candidates=self.relabel_mode.startswith("per_sample_split"),
            )
            if not decision["selected"]:
                continue
            log_rows.append({
                "step": global_steps,
                "uid": uid,
                "keys": [keys[i] for i in indices],
                "nums": nums,
                "original_target": original_target,
                "responses": [response_texts[i] for i in indices],
                "original_rewards": [scores[i] for i in indices],
                "relabel_mode": self.relabel_mode,
                "classes": decision["classes"],
                "new_targets": decision["new_targets"],
                "new_rewards": decision["new_rewards"],
            })

        key_index = {key: i for i, key in enumerate(keys)}
        pooled = [(key_index[key], cls, target, reward) for row in log_rows for key, cls, target, reward in zip(row["keys"], row["classes"], row["new_targets"], row["new_rewards"]) if cls != "untouched"]
        positives = sum(cls == "positive" for _, cls, _, _ in pooled)
        negatives = len(pooled) - positives
        # Without a positive there is nothing to learn from (and verl treats a one-sample group as mean 0, std 1).
        pool_built = positives >= 1 and len(pooled) >= 2
        pool_uid = str(uuid.UUID(int=random.Random(f"{self.seed}:{global_steps}:pool").getrandbits(128), version=4)) if pool_built else None
        assert pool_uid is None or ("_" not in pool_uid and pool_uid not in indices_by_uid)

        plan = {}
        keep_prompt = self.relabel_mode == "per_sample_split_keep_prompt"
        if pool_built:
            for batch_index, cls, target, reward in pooled:
                plan[batch_index] = (None if keep_prompt else target, reward, pool_uid)
        for row in log_rows:
            row["pool_built"] = pool_built
            row["prompt_rewritten"] = not keep_prompt
            row["training_uids"] = [pool_uid if (pool_built and cls != "untouched") else row["uid"] for cls in row["classes"]]

        metrics = {
            "hindsight/num_samples": len(keys),
            "hindsight/all_fail_groups": all_fail_groups,
            "hindsight/selected_groups": len(log_rows),
            "hindsight/pool_built": int(pool_built),
            "hindsight/pooled_positive_samples": positives if pool_built else 0,
            "hindsight/pooled_negative_samples": negatives if pool_built else 0,
            "hindsight/untouched_samples_in_selected_groups": sum(cls == "untouched" for row in log_rows for cls in row["classes"]),
            "hindsight/selected_groups_with_positive": sum("positive" in row["classes"] for row in log_rows),
        }
        if self.relabel_mode.startswith("per_sample_split"):
            for cls in ("positive", "negative_valid", "negative_parse", "negative_arithmetic", "negative_usage"):
                metrics[f"hindsight/pooled_{cls}_samples"] = sum(c == cls for _, c, _, _ in pooled) if pool_built else 0
        return plan, log_rows, metrics

    def _write_relabel_log(self, global_steps, log_rows):
        with open(os.path.join(self.relabel_log_dir, f"{global_steps}.jsonl"), "w") as log_file:
            for row in log_rows:
                log_file.write(json.dumps(row) + "\n")

    @staticmethod
    def _replace_positive_old_log_probs(pending, shadow_log_probs, real_data):
        """Arm G: use the original-prompt per-token log probs as old_log_probs of the relabeled positives.

        real_keys[:num_relabeled] are exactly the prompt-changed samples (the positives); the rest are controls. Every other
        sample in the batch is left untouched, which is checked by reading the whole batch's old_log_probs before and after.
        """
        num_relabeled = pending["num_relabeled"]
        positive_keys = pending["real_keys"][:num_relabeled]
        new_prompt_rows = [row.clone() for row in real_data["old_log_probs"].unbind(0)[:num_relabeled]]
        original_prompt_rows = [row.to(new_prompt_rows[0].dtype).clone() for row in shadow_log_probs.unbind(0)[:num_relabeled]]
        masks = [mask.bool() for mask in real_data["response_mask"].unbind(0)[:num_relabeled]]
        ratios = torch.cat([torch.exp(new - original)[mask] for new, original, mask in zip(new_prompt_rows, original_prompt_rows, masks)])

        all_keys = list(pending["batch_keys"])
        before = tq.kv_batch_get(keys=all_keys, partition_id=pending["partition_id"], select_fields=["old_log_probs"])["old_log_probs"].unbind(0)
        before = [row.clone() for row in before]
        replacement = torch.nested.as_nested_tensor(original_prompt_rows, layout=torch.jagged)
        tq.kv_batch_put(keys=positive_keys, partition_id=pending["partition_id"], fields=TensorDict({"old_log_probs": replacement}, batch_size=num_relabeled))
        after = tq.kv_batch_get(keys=all_keys, partition_id=pending["partition_id"], select_fields=["old_log_probs"])["old_log_probs"].unbind(0)

        positive_key_set = set(positive_keys)
        changed_keys = {key for key, old_row, new_row in zip(all_keys, before, after) if not torch.equal(old_row, new_row)}
        max_abs_error = max(float((after[all_keys.index(key)] - row).abs().max()) for key, row in zip(positive_keys, original_prompt_rows))
        if not changed_keys <= positive_key_set or max_abs_error != 0.0:
            raise RuntimeError(f"orig_ratio write-back failed: changed non-positive keys {changed_keys - positive_key_set}, max error {max_abs_error}")
        return {
            "hindsight/orig_ratio_positive_tokens": int(ratios.numel()),
            "hindsight/orig_ratio_below_0.8_token_rate": float((ratios < 0.8).float().mean()),
            "hindsight/orig_ratio_0.8_to_1.2_token_rate": float(((ratios >= 0.8) & (ratios <= 1.2)).float().mean()),
            "hindsight/orig_ratio_above_1.2_token_rate": float((ratios > 1.2).float().mean()),
            "hindsight/orig_ratio_replaced_samples": len(positive_keys),
            "hindsight/orig_ratio_changed_samples": len(changed_keys),
            "hindsight/orig_ratio_unchanged_other_samples": len(all_keys) - len(changed_keys),
            "hindsight/orig_ratio_writeback_max_abs_error": max_abs_error,
        }

    @staticmethod
    def _masked_sums(log_probs, response_mask):
        return [float((lp * mask).sum()) for lp, mask in zip(log_probs.unbind(0), response_mask.unbind(0))]

    def _run_logprob_diagnostic(self, forward_extra_info: dict, metrics: dict) -> None:
        pending, self.pending_diagnostic = self.pending_diagnostic, None
        if pending is None:
            return
        start_time = time.time()
        step = pending["step"]
        shadow_keys = [f"hsdiag{step}n{i}_{i}_0" for i in range(len(pending["samples"]))]
        shadow_samples = []
        for shadow_key, sample in zip(shadow_keys, pending["samples"]):
            sample = dict(sample)
            sample["uid"] = shadow_key.split("_")[0]
            shadow_samples.append(sample)
        tq.kv_batch_put(keys=shadow_keys, partition_id=DIAGNOSTIC_PARTITION, fields=list_of_dict_to_tensordict(shadow_samples), tags=pending["tags"])
        shadow_meta = KVBatchMeta(partition_id=DIAGNOSTIC_PARTITION, keys=shadow_keys, tags=pending["tags"], extra_info=forward_extra_info)
        output = self.trainer.actor_rollout_wg.compute_log_prob(shadow_meta)
        assert len(output) == len(shadow_keys)
        shadow_data = tq.kv_batch_get(keys=shadow_keys, partition_id=DIAGNOSTIC_PARTITION, select_fields=["log_probs", "response_mask"])
        shadow_log_probs = response_from_nested(shadow_data["log_probs"], shadow_data["response_mask"])
        shadow_sums = self._masked_sums(shadow_log_probs, shadow_data["response_mask"])
        tq.kv_clear(keys=shadow_keys, partition_id=DIAGNOSTIC_PARTITION)

        real_data = tq.kv_batch_get(keys=pending["real_keys"], partition_id=pending["partition_id"], select_fields=["old_log_probs", "response_mask"])
        real_sums = self._masked_sums(real_data["old_log_probs"], real_data["response_mask"])
        response_tokens = [int(mask.sum()) for mask in real_data["response_mask"].unbind(0)]

        num_relabeled = pending["num_relabeled"]
        control_token_diffs = [
            float((shadow - real).abs().max())
            for shadow, real in zip(shadow_log_probs.unbind(0)[num_relabeled:], real_data["old_log_probs"].unbind(0)[num_relabeled:])
        ]
        control_sum_diffs = [abs(s - r) for s, r in zip(shadow_sums[num_relabeled:], real_sums[num_relabeled:])]

        logp_new, logp_orig = real_sums[:num_relabeled], shadow_sums[:num_relabeled]
        diffs = [new - orig for new, orig in zip(logp_new, logp_orig)]
        new_rewards = pending["new_rewards"]
        success_diffs = [d for d, reward in zip(diffs, new_rewards) if reward == 1.0]
        fail_diffs = [d for d, reward in zip(diffs, new_rewards) if reward == 0.0]

        log_rows = self.pending_log_rows
        self.pending_log_rows = None
        diagnosed = {key: (new, orig, diff, tokens) for key, new, orig, diff, tokens in zip(pending["real_keys"][:num_relabeled], logp_new, logp_orig, diffs, response_tokens[:num_relabeled])}
        for row in log_rows:
            values = [diagnosed.get(key, (None, None, None, None)) for key in row["keys"]]
            row["logp_new"], row["logp_orig"], row["logp_diff"], row["response_tokens"] = (list(column) for column in zip(*values))
        self._write_relabel_log(step, log_rows)

        diagnostic_metrics = {
            "hindsight/logp_diff_success_mean": statistics.mean(success_diffs) if success_diffs else float("nan"),
            "hindsight/logp_diff_success_median": statistics.median(success_diffs) if success_diffs else float("nan"),
            "hindsight/logp_diff_success_count": len(success_diffs),
            "hindsight/logp_diff_fail_mean": statistics.mean(fail_diffs) if fail_diffs else float("nan"),
            "hindsight/logp_diff_fail_median": statistics.median(fail_diffs) if fail_diffs else float("nan"),
            "hindsight/logp_diff_fail_count": len(fail_diffs),
            "hindsight/logp_abs_diff_small_rate": sum(abs(d) < SMALL_LOGP_DIFF for d in diffs) / len(diffs),
            "hindsight/control_logp_sum_max_abs_diff": max(control_sum_diffs),
            "hindsight/control_logp_token_max_abs_diff": max(control_token_diffs),
            "hindsight/control_samples": len(control_sum_diffs),
            "hindsight/diagnostic_seconds": time.time() - start_time,
        }
        if self.relabel_mode == "per_sample_split_orig_ratio":
            if max(control_token_diffs) > MAX_CONTROL_TOKEN_DIFF_FOR_ORIG_RATIO:
                raise RuntimeError(f"orig_ratio: control samples disagree by {max(control_token_diffs)} nats per token; refusing to replace old_log_probs")
            diagnostic_metrics.update(self._replace_positive_old_log_probs(pending, shadow_log_probs, real_data))
        metrics.update(diagnostic_metrics)
        with open(os.path.join(self.relabel_log_dir, "diagnostic_summary.jsonl"), "a") as summary_file:
            strict_json_metrics = {key: (None if isinstance(value, float) and value != value else value) for key, value in diagnostic_metrics.items()}
            summary_file.write(json.dumps({"step": step, **strict_json_metrics}) + "\n")
