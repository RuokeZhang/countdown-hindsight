# 冒烟测试汇总（2026-11-22，单卡 L40S 46GB，verl 0.9.1）

## 运行命令

```bash
bash train_countdown_grpo.sh --seed 0 --total_steps 5 --save_freq 5 --test_freq 5 --run_name smoke_seed0        # 主冒烟：5 步
bash train_countdown_grpo.sh --seed 0 --total_steps 6 --save_freq 5 --test_freq 5 --run_name smoke_seed0        # 续训：从 step 5 接着跑 step 6
bash train_countdown_grpo.sh --seed 0 --total_steps 3 --save_freq -1 --test_freq -1 --run_name smoke_seed0_repeat trainer.val_before_train=False   # 同 seed 重跑
python countdown_rollout_stats.py --run_dir /root/work/runs/smoke_seed0
```

结果文件拷回本地 `smoke_results/`，不含 checkpoint。

## 检查项

| 检查 | 结果 |
|---|---|
| 能正常产出 rollout | 通过。每步 512 条（64 组 × 8），已落盘 `rollouts/<step>.jsonl` |
| reward 只有 0 和 1 | 通过。每步 reward 取值集合都是 {0.0, 1.0}。离线用同一个判分器重判原文，结果和训练时的 reward 完全一致 |
| 全失败组的 advantage 为 0 | 通过。每步全失败组里 \|advantage\| 的最大值都是 0.0 |
| advantage 与训练实际一致 | 通过。用 verl 的 `compute_grpo_outcome_advantage` 对落盘分数重算，6 步的 max/min 与训练日志里的 `critic/advantages/max/min` 完全相同 |
| loss 和梯度范数是有限值 | 通过。pg_loss 在 0.0065–0.0137 之间，grad_norm 在 0.64–1.13 之间（clip 阈值 1.0） |
| checkpoint 能存 | 通过。`global_step_5` 约 19GB，保存耗时 25.7 s |
| checkpoint 能读 | 通过。日志显示加载了 model、optimizer、rng、lr_scheduler，从 step 6 继续跑完，`latest_checkpointed_iteration.txt`=6 |
| 验证能跑通 | 通过。step 0、5、6 都完成了验证（每次约 5.5 s） |
| 同 seed 数据顺序可复现 | 通过。重跑前 3 步抽到的 64 个题目 id 与第一次完全相同 |

## 每步统计（smoke_seed0，step 6 是续训跑出来的）

| step | 平均 reward | 全失败组 | 混合组 | 格式合法 | 失败止步 parse / arith / usage / target | rollout s | old_logprob s | update s | 整步 s |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.043 | 84.4% | 15.6% | 56.4% | 45 / 25 / 9 / 20% | 4.3 | 12.3 | 26.2 | 44.6 |
| 2 | 0.047 | 73.4% | 26.6% | 63.9% | 38 / 32 / 8 / 23% | 4.3 | 12.2 | 24.4 | 42.6 |
| 3 | 0.090 | 70.3% | 29.7% | 67.4% | 36 / 25 / 9 / 31% | 4.3 | 10.4 | 25.0 | 41.4 |
| 4 | 0.107 | 67.2% | 31.2% | 67.2% | 37 / 30 / 9 / 24% | 4.3 | 10.8 | 24.6 | 41.4 |
| 5 | 0.088 | 75.0% | 25.0% | 63.7% | 40 / 25 / 9 / 26% | 4.3 | 10.7 | 24.0 | 66.3（含存盘和验证） |
| 6 | 0.094 | 68.8% | 29.7% | 66.4% | 37 / 23 / 13 / 28% | 4.3 | — | 24.0 | 66.9（含存盘和验证） |

"update" 是 `timing_s/update_actor`。每步另有约 0.8 s 用于把权重同步到 vLLM。

验证集贪心成功率：

| step | 总体 | 3 个数 | 4 个数 |
|---|---|---|---|
| 0 | 9.18% | 16.02% | 2.34% |
| 5 | 12.89% | 21.09% | 4.69% |
| 6 | 12.50% | 21.88% | 3.12% |

注：显存溢出的那次运行里，step 0 验证结果是 16.41% / 1.95%。说明即使是贪心解码，vLLM 也有少量批次相关的不确定性，大约 ±1 题 / 256。

## 第 1 步的 3 条 rollout 原文

1. 混合组（组内 reward = [0,0,0,1,1,0,0,0]），nums=[35, 1, 66, 18]，target=82，**reward 1.0，advantage +1.6202**

```
35 + 66 = 101
101 - 18 = 83
83 - 1 = 82
```

2. 同一个混合组，**reward 0.0，advantage −0.5401**，止步于 usage（35 用了两次）

```
35 + 1 = 36
36 - 18 = 18
18 * 35 = 630
```

3. 全失败组（8 条全是 0），nums=[3, 3, 82, 12]，target=76，**reward 0.0，advantage 0.0000**，止步于 parse

```
3 * 82 - 3 = 76
76 / 12 = 6.3333...
6.3333... * 3 = 76
```

验算：2/8 成功的组，均值为 0.25，无偏标准差为 0.4629，所以 (1−0.25)/0.4629 = 1.620，(0−0.25)/0.4629 = −0.540。

## 显存

- 训练端（PyTorch）：`max_memory_allocated` 28.8GB，`max_memory_reserved` 36.3GB。
- 整卡峰值（nvidia-smi 每秒采样，包括 vLLM）：**40.9GB / 46GB**。
- 第一次用 `log_prob_micro_batch_size_per_gpu=64` 时，在 step 2 计算 old log prob 时显存溢出：fp32 logits 一次要 8.3GB，而第 1 步更新后 Adam 状态已经占了约 12GB。
- 把两个 micro batch 都降到 16 后不再溢出。这个改动只影响前向 / 反向时每次处理多少条，每步仍然是 512 条做一次优化器更新。

## 400 步估算

- 稳态每步约 42 s，400 步约 4.7 h。
- 加上 8 次验证、8 次存盘和启动开销（启动约 5 min，主要花在过滤长 prompt 和加载 vLLM），合计约 **4.9 h**。
- 按 $0.628/h 算，约 $3.1。
- 8 个 checkpoint 约 152GB，磁盘还剩 241GB。

## 已知的无害报错

训练结束退出进程时，会出现 `RuntimeError: DataLoader worker ... is killed by signal: Killed` 这条 traceback。它发生在最终验证和存盘都完成之后，是进程退出时 DataLoader 子进程被杀掉导致的，不影响结果。
