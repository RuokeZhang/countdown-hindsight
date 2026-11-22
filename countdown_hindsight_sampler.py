import copy
import dataclasses
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict

import torch
import transfer_queue as tq
from transfer_queue import KVBatchMeta
from transformers import AutoConfig
from verl.trainer.ppo.v1.replay_buffer import ReplayBuffer
from verl.utils import hf_tokenizer
from verl.utils.model import compute_position_id_with_mask
from verl.utils.tensordict_utils import list_of_dict_to_tensordict
from verl.utils.tokenizer.continuous_token_wiring import create_continuous_token_builder
from verl.workers.utils.padding import response_from_nested

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from countdown_hindsight import relabel_group
from run_countdown_baseline import build_prompt

PROMPT_VERSION = "v3"
DIAGNOSTIC_PARTITION = "hindsight_diag"
SMALL_LOGP_DIFF = 0.05


class HindsightRelabelReplayBuffer(ReplayBuffer):
    """Sync replay buffer that relabels all-failed Countdown groups in place before the PPO update.

    sampler_kwargs: seed, relabel_probability, relabel_log_dir, model_path, logprob_diagnostic.

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
        self.logprob_diagnostic = bool(self.sampler_kwargs.get("logprob_diagnostic", False))
        self.pending_diagnostic = None
        self.pending_log_rows = None
        if self.logprob_diagnostic:
            self._install_logprob_diagnostic()

    def _install_logprob_diagnostic(self):
        # The sampler is built inside PPOTrainer.__init__; actor_rollout_wg only exists after trainer.init(), so it is
        # looked up when the diagnostic runs.
        trainer = getattr(self.refill_fn, "__self__", None)
        if trainer is None or not hasattr(trainer, "_compute_old_log_prob") or not hasattr(trainer, "config"):
            raise RuntimeError("logprob_diagnostic needs refill_fn to be a bound method of the verl PPOTrainer")
        self.trainer = trainer
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
        relabel_indices = [i for uid in relabeled_uids for i in indices_by_uid[uid]]
        new_tags = [dict(tag) for tag in batch.tags]
        log_rows = []

        if relabel_indices:
            relabel_keys = [keys[i] for i in relabel_indices]
            full_data = tq.kv_batch_get(keys=relabel_keys, partition_id=batch.partition_id)
            new_samples, original_samples = [], []
            for local_index, batch_index in enumerate(relabel_indices):
                sample = self._copy_sample(full_data[local_index])
                original_samples.append(self._copy_sample(full_data[local_index]))
                uid = uids[batch_index]
                decision, nums, original_target = decisions[uid]
                new_target = decision["new_target"]
                new_reward = decision["new_rewards"][indices_by_uid[uid].index(batch_index)]

                original_prompt_ids = self._build_prompt_ids(list(sample["raw_prompt"]))
                if not torch.equal(original_prompt_ids, sample["prompts"]):
                    raise RuntimeError(f"Rebuilt original prompt does not match rollout prompt for key {keys[batch_index]}")

                new_messages = [{"role": "user", "content": build_prompt({"nums": nums, "target": new_target}, PROMPT_VERSION)}]
                new_prompt_ids = self._build_prompt_ids(new_messages)
                responses = sample["responses"]
                input_ids = torch.cat([new_prompt_ids, responses], dim=0)
                attention_mask = torch.ones_like(input_ids, dtype=torch.int64)
                position_ids = compute_position_id_with_mask(attention_mask.unsqueeze(0)).squeeze(0).to(sample["position_ids"].dtype)
                rm_scores = torch.zeros_like(sample["rm_scores"])
                rm_scores[-1] = new_reward

                sample["prompts"] = new_prompt_ids
                sample["input_ids"] = input_ids
                sample["position_ids"] = position_ids
                if "attention_mask" in sample:
                    sample["attention_mask"] = attention_mask
                sample["rm_scores"] = rm_scores
                sample["raw_prompt"] = new_messages
                sample["reward_model"] = {**sample["reward_model"], "ground_truth": new_target}
                sample["extra_info"] = {**sample["extra_info"], "target": new_target}
                if "reward_extra_info" in sample.get("extra_fields", {}):
                    sample["extra_fields"]["reward_extra_info"]["acc"] = new_reward
                new_samples.append(sample)

                tag = new_tags[batch_index]
                tag["prompt_len"] = int(new_prompt_ids.size(0))
                tag["seq_len"] = int(new_prompt_ids.size(0) + responses.size(0))
                assert tag["response_len"] == int(responses.size(0))

            tq.kv_batch_put(
                keys=relabel_keys,
                partition_id=batch.partition_id,
                fields=list_of_dict_to_tensordict(new_samples),
                tags=[new_tags[i] for i in relabel_indices],
            )

            stored = tq.kv_batch_get(keys=relabel_keys, partition_id=batch.partition_id, select_fields=["input_ids", "rm_scores"])
            for stored_input_ids, stored_rm_scores, sample in zip(stored["input_ids"].unbind(0), stored["rm_scores"].unbind(0), new_samples):
                if not torch.equal(stored_input_ids, sample["input_ids"]) or not torch.equal(stored_rm_scores, sample["rm_scores"]):
                    raise RuntimeError("Relabeled sample read back from TransferQueue differs from what was written")

            for uid in relabeled_uids:
                decision, nums, original_target = decisions[uid]
                log_rows.append({
                    "step": global_steps,
                    "uid": uid,
                    "nums": nums,
                    "original_target": original_target,
                    "new_target": decision["new_target"],
                    "candidate_values": decision["candidate_values"],
                    "responses": [response_texts[i] for i in indices_by_uid[uid]],
                    "original_rewards": [scores[i] for i in indices_by_uid[uid]],
                    "new_rewards": decision["new_rewards"],
                })

        control_keys, control_count = [], 0
        if self.logprob_diagnostic and relabel_indices:
            relabeled_key_set = set(relabel_keys)
            control_count = self.log_prob_micro_batch_size - len(relabel_indices) % self.log_prob_micro_batch_size
            control_keys = [key for key in keys if key not in relabeled_key_set][:control_count]
        if self.logprob_diagnostic and relabel_indices and len(control_keys) == control_count:
            control_data = tq.kv_batch_get(keys=control_keys, partition_id=batch.partition_id)
            control_samples = [self._copy_sample(control_data[i]) for i in range(len(control_keys))]
            self.pending_diagnostic = {
                "step": global_steps,
                "partition_id": batch.partition_id,
                "real_keys": relabel_keys + control_keys,
                "num_relabeled": len(relabel_keys),
                "samples": original_samples + control_samples,
                "tags": [batch.tags[i] for i in relabel_indices] + [batch.tags[keys.index(key)] for key in control_keys],
                "new_rewards": [decisions[uids[i]][0]["new_rewards"][indices_by_uid[uids[i]].index(i)] for i in relabel_indices],
            }
            self.pending_log_rows = log_rows
        else:
            self._write_relabel_log(global_steps, log_rows)

        ones_per_group = Counter(int(sum(row["new_rewards"])) for row in log_rows)
        metrics = {
            "hindsight/num_samples": len(keys),
            "hindsight/all_fail_groups": all_fail_groups,
            "hindsight/eligible_groups": len(decisions),
            "hindsight/relabeled_groups": len(relabeled_uids),
            "hindsight/relabeled_samples": len(relabel_indices),
            "hindsight/relabeled_all_success_groups": ones_per_group[8],
            "hindsight/new_reward_ones_mean": sum(sum(row["new_rewards"]) for row in log_rows) / max(len(log_rows), 1),
        }
        for ones in range(1, 9):
            metrics[f"hindsight/relabeled_groups_with_{ones}_ones"] = ones_per_group[ones]
        with open(os.path.join(self.relabel_log_dir, "summary.jsonl"), "a") as summary_file:
            summary_file.write(json.dumps({"step": global_steps, **metrics}) + "\n")

        return dataclasses.replace(batch, tags=new_tags), metrics

    def _write_relabel_log(self, global_steps, log_rows):
        with open(os.path.join(self.relabel_log_dir, f"{global_steps}.jsonl"), "w") as log_file:
            for row in log_rows:
                log_file.write(json.dumps(row) + "\n")

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
        group_start = 0
        for row in log_rows:
            group_slice = slice(group_start, group_start + len(row["responses"]))
            group_start += len(row["responses"])
            row["logp_new"] = logp_new[group_slice]
            row["logp_orig"] = logp_orig[group_slice]
            row["logp_diff"] = diffs[group_slice]
            row["response_tokens"] = response_tokens[:num_relabeled][group_slice]
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
        metrics.update(diagnostic_metrics)
        with open(os.path.join(self.relabel_log_dir, "diagnostic_summary.jsonl"), "a") as summary_file:
            strict_json_metrics = {key: (None if isinstance(value, float) and value != value else value) for key, value in diagnostic_metrics.items()}
            summary_file.write(json.dumps({"step": step, **strict_json_metrics}) + "\n")
