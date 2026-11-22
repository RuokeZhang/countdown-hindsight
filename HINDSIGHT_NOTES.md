# verl 0.9.1 中插入 hindsight relabel 的位置（调研，未改代码）

源码基于 GitHub tag `v0.9.1`。下文路径相对于 `verl/` 包目录。

## 1. 实际运行的是哪个训练循环

- 默认配置 `trainer.use_v1=true`。`trainer/main_ppo.py:183` 走 `TaskRunnerV1`，`trainer.v1.trainer_mode=sync` 对应 `PPOTrainerSync`（`trainer/ppo/v1/trainer_sync.py:24`）。
- 主循环是 `trainer/ppo/v1/trainer_base.py` 里的 `PPOTrainer.fit`（:426）→ `step`（:547）→ `_step_once`（:576）。
- 旧的 `trainer/ppo/ray_trainer.py` 里的 `RayPPOTrainer.fit` 已标记为 deprecated，不会走到。
- v1 里的 batch 不是 DataProto，而是 `KVBatchMeta`，只存 key 和 tag。每条轨迹的变长 tensor 存在 TransferQueue（TQ）里，key 格式为 `{uid}_{session}_{index}`。

## 2. 每步的执行顺序（`_step_once`，trainer_base.py:576-626）

1. **gen**（:579-588）：`replay_buffer.sample(...)` 一直阻塞到凑齐 `train_batch_size` 组。
   - 生成和 reward 在这之前已经完成：agent loop 每生成完一条，就异步调用 reward 函数（`experimental/agent_loop/agent_loop.py:967-1029`）。
   - 分数写进 `rm_scores`，即最后一个 token 位置上的值。
2. **reward**（:591-593）：只有共置 reward model 时才走这里。我们用规则函数，这一步跳过。
3. **balance**（:596）：`_balance_batch` 把 batch 补齐到 `lcm(dp, ppo_mini_batch_size*n)` 的整数倍，再按 `seq_len` 重排。
4. **old_log_prob**（:599-600）：`_compute_old_log_prob`（:1649）。
   - 默认 `bypass_mode=false`，由 actor 用当前权重重新计算 `old_log_probs`。
   - 打开 `bypass_mode` 时，直接用 rollout 的 log prob。
5. ref（:603），只在开了 KL 时执行；values（:608），只在有 critic 时执行。
6. **adv**（:613）：`_compute_advantage`（:1758）调用 `compute_advantage_for_multi_trajectories`（`v1/utils.py:148-217`）。按 `uid` 分组，用 `core_algos.compute_grpo_outcome_advantage`（:267-330）计算 GRPO advantage。
7. **update_actor**（:622）。

## 3. 插入点

- **"reward 已算完、advantage 和策略更新之前"的位置**：`_step_once` 里 :593（sample 和可选的 reward 之后）与 :596（`_balance_batch`）之间。这时 `rm_scores` 已经在 TQ 里。
- **旧策略 log prob 在插入点之后计算**（:600）。所以在这里追加的样本：
  - 会自动由 actor 按**新 prompt** 重算 `old_log_probs`，不用自己处理。
  - 前提是不能开 `bypass_mode`，因为 rollout 的 log prob 是以旧 prompt 为条件算的。
- **不改 verl 源码的两种接入方式**：
  - **自定义 sampler（推荐）**：设置 `trainer.v1.sampler.custom_sampler.{path,name}`，由 :159-199 按路径加载。
    - 写一个 `ReplayBuffer` 子类：先 `super().sample()`，再把 relabel 样本写进 TQ，最后返回扩展后的 `KVBatchMeta`。
    - `partition_id=="val"` 时不能 relabel，因为验证也会调用 `sample`（:1091）。
  - **自定义 trainer**：`@register_trainer("hindsight")` 注册一个 `PPOTrainerSync` 的子类，在 `_step_once` 的这个位置插入逻辑。
    - 需要保证模块在 `TaskRunnerV1` 所在进程里、`get_trainer_cls` 调用之前就被 import，所以要多一层入口包装。

## 4. 追加一批"换 prompt、回复不变、reward 重算"的样本时需要改什么

参照 `trainer/ppo/padding_utils.py:72-200`（`construct_minimal_padding_template` / `upsample_batch_to_divisible_size`）。它做的事情正好是：复制样本 → 改 tensor → `tq.kv_batch_put` → 扩展 `KVBatchMeta`。

- **TQ value 字段**：每条样本是一维、不补 padding 的 tensor，写入位置见 `v1/agent_loop_tq.py:183-203`。
  - `prompts`：换成新 prompt 的 token。生成方式要和 rollout 一致，见 `single_turn_agent_loop.py:41-60`（chat template）。
  - `responses`、`response_mask`、`loss_mask`：保持原样。
  - `input_ids = cat(prompts, responses)`；`position_ids` 按新长度重新生成。
  - `rm_scores`：长度等于 response 长度，新的分数放在最后一位。
  - `rollout_log_probs`：已经过期。可以删掉，或者在 :600 之后用重算的 `old_log_probs` 覆盖；也可以关掉 `rollout.calculate_log_probs`。否则会污染 `rollout_corr/*` 这类诊断指标。
  - 数据集字段：`reward_model.ground_truth` 改成新 target；`extra_info` 改成新 target；还有 `raw_prompt`、`data_source`、`index` 等。
- **tag**：`seq_len`、`prompt_len`、`response_len`、`min_global_steps`、`max_global_steps`、`global_steps`、`status` 都必须有。
  - 缺 `min/max_global_steps` 时，:1912 会直接 KeyError。
  - 带 `is_padding` 的行不计入指标。
- **key 和分组**：
  - key 必须是 `{uid}_{session}_{index}`，`v1/utils.py:183` 有 assert 检查。uid 里不能含 `_`，因为 ReplayBuffer 用 `split("_")[0]` 取 uid。
  - GRPO 分组看的是 value 字段里的 `uid`（:1766）。relabel 样本要用**新 uid**，例如 `{uid}-hs`，否则会和原组一起做归一化。
  - **注意**：只有 1 条样本的组，mean=0、std=1，advantage 等于原始 reward 而不是 0。见 `core_algos.py:317`。
- **batch 大小和更新次数**：
  - 运行时没有"batch 必须等于 train_batch_size*n"的 assert，balance 阶段会补齐到整数倍。
  - 但 `mini_batch_size = ppo_mini_batch_size*n` 是固定的（:1844-1867）。batch 变大以后，一个 step 里会做**多次**优化器更新，而不是一次更大的更新。
  - 如果要保持"每个 batch 更新一次"，需要在自定义 trainer 里同时改 `_update_actor` 的 mini batch 大小和 `_get_required_batch_multiple`。
- **清理**：每步结束时 `tq.kv_clear(batch.keys)`（:525）只会清理 `KVBatchMeta` 里登记过的 key，所以追加的 key 必须加进返回的 meta。

## 5. 和 baseline 相关的事实

- 全失败组的 advantage = (0−0)/(0+1e-6)，正好等于 0，见 `core_algos.py:326`。
- v1 训练路径**不会**把 reward 函数返回 dict 里的额外字段写进训练指标，也不会写进 rollout 落盘文件（`{step}.jsonl` 只有 `input/output/gts/score/step/uid`）。这些字段只出现在验证集的指标和落盘里。所以止步步骤这类统计由离线脚本 `countdown_rollout_stats.py` 来做。
