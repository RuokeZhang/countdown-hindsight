# Countdown：零样本评测 + GRPO baseline（binary reward）

## 文件

| 文件 | 作用 |
|---|---|
| `countdown_grader.py` | 判分器（parse → arithmetic → usage → target），零样本评测和训练共用 |
| `test_countdown_grader.py` | 判分器单测：`python3 -m unittest test_countdown_grader -v` |
| `run_countdown_baseline.py` | 零样本评测（vLLM），以及 prompt v1–v4 的定义（`build_prompt`） |
| `prepare_countdown_data.py` | 生成 verl 用的 train/val parquet（prompt v3） |
| `countdown_reward.py` | verl 自定义 reward：四步全过记 1.0，否则 0.0 |
| `countdown_reward_validbonus.py` | B 组 reward：四步全过 1.0，过了 parse/arithmetic/usage 但没中目标 0.1，否则 0.0 |
| `countdown_hindsight.py` | 全失败组的改写逻辑（候选值、按 p 决定是否改写、新目标下重新判分） |
| `countdown_hindsight_sampler.py` | A 组用的 `custom_sampler`：在 TQ 里原地改写 prompt/reward，附带 logprob 诊断 |
| `test_countdown_hindsight.py`、`test_countdown_hindsight_sampler.py` | 改写逻辑单测：`python3 -m unittest test_countdown_hindsight -v`；TQ 集成测试需要在训练机上跑 |
| `train_countdown_grpo.sh` | GRPO 训练启动脚本（`--seed`、`--lr`、`--reward binary\|validbonus`、`--sampler none\|hindsight\|hindsight_per_sample\|hindsight_per_sample_split`、`--relabel_p`） |
| `countdown_rollout_stats.py` | 离线统计：每步 reward、组统计、格式合法率、止步分布、耗时、验证成功率（hindsight run 按原始目标统计） |
| `countdown_compare_runs.py` | 多个 run 的对比表、退化指标表（熵、混合组、失败回答里"最后一行等于目标数"的占比、每步改写正负样本数），加上 logprob 诊断的区间表 |
| `HINDSIGHT_NOTES.md` | verl 训练主循环里 hindsight 插入点的调研 |
| `SMOKE_TEST.md` | 冒烟测试结果汇总（结果文件在 `smoke_results/`） |
| `results*/` | 零样本评测结果（prompt v1–v4） |
| `training_results/grpo_binary_seed0/` | 400 步 GRPO baseline 的指标、每步统计、验证集输出（不含 rollout 原文和 checkpoint） |
| `training_results/grpo_hindsight_p1_seed0/` | A 组（hindsight，p=1）300 步，另有 `relabel_log/`（每条改写样本和 logprob 诊断） |
| `training_results/grpo_validbonus_seed0/` | B 组（合法格式 +0.1）300 步 |
| `training_results/grpo_hindsight_p0.25_seed0/` | C 组（整组改写，p=0.25），只跑到第 50 步（第 51–56 步的原始数据只在 OSS 的 results tar 里，`rollouts_after_step50/`，不计入统计） |
| `training_results/three_arm_comparison.md` | 三组对比表 |
| `training_results/grpo_hindsight_per_sample_p0.25_seed0/` | D 组（逐条改写：候选改成自己的值记 1，parse/arithmetic/usage 失败记 0，两者放进每步一个新 uid 统一归一化；p=0.25），跑到第 100 步停止；`relabel_log/advantages/` 是每条样本实际的 advantage |
| `training_results/arm_comparison_baseline_A_B_C_D.md` | 五组对比表（C 到第 50 步，D 到第 100 步） |

完整 rollout 和全部 checkpoint 在 Aliyun OSS：`oss://ruoke-h200-export/countdown-grpo-20261122/`（us-west-1）。checkpoint 是 `tar` 后按 4GB 切分的，恢复方法：`cat global_step_N.tar.part_* | tar -xf -`，校验文件为 `checkpoints/checkpoint_parts.md5`。

## 环境（单卡 L40S 48GB，Ubuntu 22.04，驱动支持 CUDA 13）

verl **0.9.1**（GitHub tag `v0.9.1`），按仓库自带的 `uv.lock` 安装：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh && export PATH=$HOME/.local/bin:$PATH
mkdir -p /root/work && cd /root/work
git clone --branch v0.9.1 --depth 1 https://github.com/volcengine/verl.git && cd verl
uv python install 3.12
UV_PYTHON=3.12 uv sync --frozen --extra fsdp --extra vllm --no-install-package flash-attn
uv pip install --python .venv/bin/python datasets pandas pyarrow
```

装出来的版本：vllm 0.24.0、torch 2.11.0+cu130、transformers 5.9.0。

**为什么不装 flash-attn**：`uv.lock` 引用的 flash-attn 2.8.3（torch 2.11）轮子已经从 verl-wheelhouse 删除（404），wheelhouse 现在只剩 torch 2.13 / cu132 的构建。所以：
- 训练端注意力改用 PyTorch SDPA（`+actor_rollout_ref.model.override_config.attn_implementation=sdpa`），并设置 `use_remove_padding=False`。
- verl 的 padding 工具在没有 flash-attn 时会自动退回 torch 实现（`utils/attention_utils.py:71`）。
- vLLM 用的是它自带的 flash-attn，rollout 不受影响。

代码放在 `/root/work/countdown/`。下面的命令都在这个目录下、用 `/root/work/verl/.venv/bin/python` 执行。

## 运行

```bash
# 1. 数据（seed 0；输出到 /root/work/data/countdown_v3/{train,val}.parquet）
python prepare_countdown_data.py --out_dir /root/work/data/countdown_v3

# 2. 训练（默认 400 步、每 50 步验证和存 checkpoint；用同一个 run_name 重跑会自动从最新 checkpoint 续训）
bash train_countdown_grpo.sh --seed 0 --lr 1e-6 --run_name grpo_binary_seed0

# 3. 离线统计（每步统计和验证成功率，写到 run 目录下的 step_stats.jsonl / validation_stats.jsonl）
python countdown_rollout_stats.py --run_dir /root/work/runs/grpo_binary_seed0
```

每个 run 目录（`/root/work/runs/<run_name>/`）里有：
- `metrics_<时间戳>.jsonl`：verl 的 file logger 输出，每启动一次新建一个文件，因为它用 `wb` 打开、会覆盖旧文件。
- `rollouts/<step>.jsonl`：每步 512 条 rollout 原文。
- `validation/`：验证集输出。
- `checkpoints/`：checkpoint。
- `train.log`：训练日志。

## 数据切分

- 按数字 multiset 去重：490,364 条原始数据去重后剩 358,636 个组合，每个组合保留第一次出现的那道题。
- 验证集：3 个数和 4 个数各 256 道，从**不在**零样本 512 题里的组合中抽取。
- 训练集：剩下的组合里 3 个数和 4 个数各取 118,377 道（数量取两者中较小的），再打乱。
- train 和 val 的组合不重叠，脚本里有 assert 检查。零样本那 512 题里有 389 个组合落在训练集里。
- `data_source` 设为 `countdown_3` / `countdown_4`，因此 verl 会自动按数字个数分开报告验证指标。
- `extra_info` 包含 `problem_id`（原数据集行号）、`nums`、`target`、`num_count`、`split`。

## 训练配置和 verl 实际键名

| 意图 | 用到的配置键 / 说明 |
|---|---|
| GRPO，组内减均值、除标准差 | `algorithm.adv_estimator=grpo`，`algorithm.norm_adv_by_std_in_grpo=True`。全相同的组 advantage = 0/(0+1e-6) = 0 |
| 每步 64 题 × 8 条 | `data.train_batch_size=64`，`actor_rollout_ref.rollout.n=8` |
| 每个 batch 只更新一次 | `actor.ppo_mini_batch_size=64`（以题目数为单位，乘 n 后是 512，即整个 batch），`actor.ppo_epochs=1`。`ppo_micro_batch_size_per_gpu=16`（`log_prob_micro_batch_size_per_gpu` 也是 16，64 会在第 2 步 OOM）只是梯度累积的切分，不增加更新次数 |
| 不加 KL、不要 critic、entropy 为 0 | `actor.use_kl_loss=False`，`algorithm.use_kl_in_reward=False`（因此不会创建 ref 模型），`actor.entropy_coeff=0`。GRPO 不创建 critic |
| AdamW，学习率 1e-6 | `actor.optim.lr`。其余用 verl 默认值：AdamW，betas (0.9, 0.999)，weight_decay 0.01，学习率恒定、无 warmup，grad clip 1.0 |
| bf16 全参数训练 | FSDP 默认 `fsdp_config.dtype=bfloat16`（前向和反向用 bf16 计算），`model_dtype=fp32`（主权重和优化器状态用 fp32）。没有用 LoRA |
| 采样 | `rollout.temperature=1.0`，`rollout.top_p=1.0`，`data.max_response_length=64` |
| prompt 长度 | v3 prompt 实测 157–178 token，所以设 `data.max_prompt_length=256` |
| 每 50 步用贪心解码验证 | `trainer.test_freq=50`，`rollout.val_kwargs.{do_sample=False, temperature=0, n=1}`，`trainer.val_before_train=True` |
| 每 50 步存 checkpoint，可续训 | `trainer.save_freq=50`，`trainer.resume_mode=auto`，`trainer.default_local_dir=<run>/checkpoints`。全部保留，每个约 18GB |
| vLLM 和训练共用一张卡 | `rollout.gpu_memory_utilization=0.3`，`rollout.tensor_model_parallel_size=1`。训练阶段 vLLM 会 sleep，释放 KV cache |
| 本地日志 | `trainer.logger=["console","file"]`，`VERL_FILE_LOGGER_PATH` |

## 随机种子（`--seed`）

| 影响 | 由什么控制 | 启动脚本里的设置 |
|---|---|---|
| 数据顺序 | `data.seed`：训练 sampler 的 `torch.Generator().manual_seed`（`trainer/ppo/utils.py:157`） | `data.seed=$SEED` |
| 采样 | `rollout.seed`：vLLM 引擎 seed（`vllm_async_server.py:343`）。没开 `rollout.full_determinism` 时没有逐请求的 seed，结果还取决于调度顺序，所以采样**不能逐条复现** | `rollout.seed=$SEED` |
| 模型初始化 | 从预训练权重加载，没有随机初始化的部分（没有 critic，也没有新加的 head） | — |
| 其他 | `actor.fsdp_config.seed` 只在 `full_determinism=True` 时生效；`actor.data_loader_seed` 只在 `actor.shuffle=True` 时生效（默认关闭） | 也设成 `$SEED`，保持一致 |

## Reward 和日志

- reward 通过 `reward.custom_reward_function.path/name` 接入。注意：顶层的 `custom_reward_function` 在 v1 的 `main_ppo` 里不生效。
- verl 调用 reward 函数时传入 `(data_source, solution_str, ground_truth, extra_info)`，其中 `solution_str` 是去掉特殊 token 后的回复文本。
- reward 函数可以返回 dict（`score` 加额外字段），但 v1 训练路径**不会**把额外字段写进训练指标或 rollout 落盘，只会出现在验证指标和验证落盘里。验证还会对每个额外字段求均值，字符串字段会出错。
- 所以 reward 只返回 0.0/1.0。止步步骤、最终结果值和组统计，由 `countdown_rollout_stats.py` 从 `rollouts/<step>.jsonl` 里的原文重新判分得到。
- 每步耗时来自 verl 记录的指标：`timing_s/gen`（rollout，含异步 reward）、`timing_s/old_log_prob`、`timing_s/update_actor`、`timing_s/update_weights`、`timing_s/step`。
- 验证成功率：`val-core/countdown_{3,4}/acc/mean@1`。总体成功率取两者的平均（两边题数相同）。

## 三组对比（seed 0，完整表见 `training_results/three_arm_comparison.md`）

验证集贪心成功率（512 题）：

| step | baseline | A：hindsight p=1 | B：合法格式 +0.1 |
|---|---|---|---|
| 0 | 9.0% | 9.0% | 8.8% |
| 50 | 20.9% | 16.8% | 14.1% |
| 100 | 26.8% | 23.2% | 17.0% |
| 150 | 34.0% | 28.7% | 16.0% |
| 200 | 35.5% | 29.5% | 15.0% |
| 250 | 38.9% | 31.4% | 18.2% |
| 300 | 38.5% | 36.5% | 17.0% |

- **A**：前 20 步每步改写约 15 组，之后模型开始"算式随便写、最后一行硬写成目标数"（全失败组里 target 阶段的失败从第 5 步的 67 条降到第 18 步的 0 条，arithmetic 阶段的失败升到第 30 步的 360 条），于是没有可改写的候选，第 21 步以后一次改写都没有。第 50 步熵 0.034（baseline 0.08），混合组 9.7%（baseline 28%）。推测原因：改写组里只有"算式对且等于新目标"的正样本和"不等于新目标"的负样本，没有"写了新目标但算式是假的"负样本，所以分不清"算出目标"和"抄目标"。
- **B**：第 50 步左右格式合法率到 100%，熵 0.003，模型稳定输出"合法但不对"的式子拿 0.1，几乎所有组 reward 相同，学习停滞。
- logprob 诊断（第 1–25 步）：改写后成功的样本在新 prompt 下的 log 概率之和比原 prompt 高 1.1 nats，改写后失败的样本低 14.8 nats。
