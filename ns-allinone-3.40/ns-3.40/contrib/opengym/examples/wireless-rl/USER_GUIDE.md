# wireless-rl 手动实验指南

这份文档记录 `ns3-gym + DQN` 无线资源分配实验的手动运行流程、输出文件和脚本参数。以后修改脚本参数或输出约定时，请同步更新这里。

## 0. 环境和目录

每次运行 Python 脚本前先进入 conda 环境：

```bash
conda activate ns3gym
cd ~/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
```

如果改过 `sim.cc`，需要先在 ns-3 根目录重新编译：

```bash
cd ~/ns3-workspace/ns-allinone-3.40/ns-3.40
./ns3 build
cd contrib/opengym/examples/wireless-rl
```

正式 baseline 和 DQN 评估建议使用多 seed 脚本，不建议用 `test.py --iterations > 1` 做正式实验。原因是 C++ 环境端有全局状态，除非确认 reset 完整重启仿真，否则多 iteration 可能引入状态残留。当前正式链路都是每个 seed 单独启动 ns-3 进程。

## 1. 环境含义

当前状态维度是 15：

```text
[cqi0, queue0, delay0, ..., cqi4, queue4, delay4]
```

动作空间是 `Discrete(5)`，`action=i` 表示服务用户 `i`。

reward：

```text
served - 0.01 * rewardQueue - 0.1 * totalDelay - 5.0 * deadlineMisses
```

注意：

- `delay_i` 是用户级 backlog age，不是逐包 packet delay。
- `deadlineMisses` 是当前 step 仍有积压且 delay 超过 deadline 的用户数，不是累计丢包数。
- `sim.cc` 现在会用 `ceil(simTime / stepTime)` 动态确定 episode 步数。

## 2. 单个 baseline

运行单个 baseline：

```bash
python test.py --agent=delay_aware --seed 1 --simTime 20 --stepTime 0.5
```

输出：

```text
runtime/results/{agent}_seed{seed}.csv
runtime/summaries/{agent}_seed{seed}_summary.csv
runtime/plots/{agent}_seed{seed}_*.svg
```

`test.py` 参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--start` | `1` | 是否由 Python 自动启动 ns-3；一般保持 `1` |
| `--iterations` | `1` | 单进程重复 episode 数；正式实验不建议大于 1 |
| `--agent` | `greedy` | baseline 策略 |
| `--port` | `0` | OpenGym 端口；`0` 表示自动选择空闲端口 |
| `--simTime` | `20.0` | 仿真时长，单位秒 |
| `--stepTime` | `0.5` | 调度 step 间隔，单位秒 |
| `--seed` | `1` | ns-3 random run seed |
| `--outputDir` | `runtime` | 输出目录 |
| `--no-save` | 关闭 | 不保存 CSV 和图 |
| `--no-plot` | 关闭 | 不保存 SVG 图 |

`--agent` 可选值：

```text
random
round_robin
max_cqi
max_queue
max_delay
greedy
delay_aware
```

## 3. 单 seed baseline 对比

运行一个 seed 下的全部 baseline：

```bash
python run_baselines.py --seed 1 --quiet
```

只跑部分 baseline：

```bash
python run_baselines.py --seed 1 --agents greedy,delay_aware,max_delay --quiet
```

输出：

```text
runtime/comparisons/baseline_comparison_seed1.csv
runtime/plots/baseline_comparison_seed1_*.svg
```

`run_baselines.py` 参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--agents` | 全部 baseline | 逗号分隔的 baseline 列表 |
| `--seed` | `1` | ns-3 random run seed |
| `--simTime` | `20.0` | 仿真时长 |
| `--stepTime` | `0.5` | step 间隔 |
| `--iterations` | `1` | 固定要求为 1 |
| `--outputDir` | `runtime` | 输出目录 |
| `--skip-run` | 关闭 | 不重新运行，只读取已有 CSV 重新生成对比 |
| `--no-plot` | 关闭 | 运行 `test.py` 时不生成单 agent 图 |
| `--quiet` | 关闭 | 收起每个 agent 的详细输出 |

## 4. 多 seed baseline 对比

正式 baseline 推荐命令：

```bash
python run_multi_seed.py --seeds 1,2,3,4,5,6,7,8,9,10 --quiet
```

输出：

```text
runtime/comparisons/baseline_comparison_all_seeds.csv
runtime/plots/baseline_comparison_all_seeds_*.svg
```

`run_multi_seed.py` 参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--agents` | 全部 baseline | 逗号分隔的 baseline 列表 |
| `--seeds` | `1,2,3,4,5` | 逗号分隔的 seed 列表 |
| `--simTime` | `20.0` | 仿真时长 |
| `--stepTime` | `0.5` | step 间隔 |
| `--outputDir` | `runtime` | 输出目录 |
| `--skip-run` | 关闭 | 只聚合已有 per-seed CSV |
| `--no-plot` | 关闭 | 运行 per-seed baseline 时不生成单 agent 图 |
| `--quiet` | 关闭 | 收起 per-seed 输出 |

## 5. DQN 训练

快速 smoke test：

```bash
python train_dqn.py --episodes 5 --simTime 2 --stepTime 0.5 --device cuda:0 --runName smoke_test
```

推荐的一版 delay-aware warm start：

```bash
python train_dqn.py \
  --episodes 300 \
  --seed 1 \
  --simTime 20 \
  --stepTime 0.5 \
  --device cuda:0 \
  --quiet \
  --hiddenSize 128 \
  --epsilonDecay 0.99 \
  --pretrainSteps 3000 \
  --pretrainHeuristic delay_aware \
  --runName dqn_delayaware_p3k_h128
```

输出：

```text
models/{runName}.pt
runtime/{runName}_train.csv
```

`train_dqn.py` 参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--episodes` | `300` | 训练 episode 数 |
| `--seed` | `1` | 随机种子；episode 内部使用 `seed + episode` 作为仿真 seed |
| `--simTime` | `20.0` | 每个 episode 的仿真时长 |
| `--stepTime` | `0.5` | step 间隔 |
| `--gamma` | `0.99` | 折扣因子 |
| `--learningRate` | `1e-3` | Adam 学习率 |
| `--batchSize` | `64` | replay buffer 采样 batch 大小 |
| `--bufferSize` | `10000` | replay buffer 容量 |
| `--epsilonStart` | `1.0` | 初始探索率 |
| `--epsilonEnd` | `0.05` | 最低探索率 |
| `--epsilonDecay` | `0.995` | 每个 episode 后的探索率衰减 |
| `--targetUpdateInterval` | `20` | target network 同步间隔 |
| `--hiddenSize` | `64` | Q 网络隐藏层宽度 |
| `--networkType` | `dueling` | 网络类型：`mlp` 或 `dueling` |
| `--doubleDqn` / `--no-doubleDqn` | `--doubleDqn` | 是否使用 Double DQN |
| `--rewardScale` | `0.1` | 训练 target 中的 reward 缩放 |
| `--updatesPerStep` | `1` | 每个环境 step 做几次梯度更新 |
| `--learningStarts` | `64` | buffer 至少多少条经验后开始更新 |
| `--pretrainSteps` | `0` | 启发式监督预训练步数 |
| `--pretrainHeuristic` | `max_service` | 预训练模仿策略 |
| `--runName` | `dqn_seed{seed}` | 输出模型和日志名称 |
| `--device` | `auto` | `auto`、`cpu`、`cuda:0`、`cuda:1` 等 |
| `--outputDir` | `runtime` | 训练日志输出目录 |
| `--modelDir` | `models` | 模型输出目录 |
| `--quiet` | 关闭 | 收起每个 episode 的训练日志 |

`--pretrainHeuristic` 可选值：

```text
max_service
greedy
delay_aware
max_delay
max_queue
max_cqi
```

## 6. DQN 训练曲线

训练后画 SVG 曲线：

```bash
python plot_dqn_training.py --csv runtime/dqn_delayaware_p3k_h128_train.csv --tag dqn_delayaware_p3k_h128
```

输出：

```text
runtime/plots/dqn_delayaware_p3k_h128_total_reward.svg
runtime/plots/dqn_delayaware_p3k_h128_average_total_delay.svg
runtime/plots/dqn_delayaware_p3k_h128_average_deadline_misses.svg
...
```

`plot_dqn_training.py` 参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--csv` | 必填 | `train_dqn.py` 生成的训练 CSV |
| `--tag` | CSV 文件名 | 输出图名前缀 |
| `--outputDir` | `runtime/plots` | SVG 输出目录 |

## 7. DQN 多 seed 评估

评估已有模型：

```bash
python evaluate_dqn.py \
  --model models/dqn_delayaware_p3k_h128.pt \
  --agentName dqn_delayaware_p3k_h128 \
  --seeds 1,2,3,4,5,6,7,8,9,10 \
  --simTime 20 \
  --stepTime 0.5 \
  --device cuda:0
```

输出：

```text
runtime/results/{agentName}_seed{seed}.csv
runtime/summaries/{agentName}_seed{seed}_summary.csv
runtime/comparisons/{agentName}_eval_all_seeds.csv
```

`evaluate_dqn.py` 参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--model` | `models/dqn_seed1.pt` | 要加载的 `.pt` 模型 |
| `--seeds` | `1` | 逗号分隔的评估 seed |
| `--agentName` | `dqn` | 输出 CSV 中使用的 agent 名称 |
| `--simTime` | `20.0` | 仿真时长 |
| `--stepTime` | `0.5` | step 间隔 |
| `--device` | `auto` | 推理设备 |
| `--outputDir` | `runtime` | 输出目录 |

## 8. DQN vs baseline

先确保已经有：

```text
runtime/comparisons/baseline_comparison_all_seeds.csv
runtime/comparisons/{agentName}_eval_all_seeds.csv
```

合并对比：

```bash
python compare_dqn_with_baselines.py \
  --baselineCsv runtime/comparisons/baseline_comparison_all_seeds.csv \
  --dqnCsv runtime/comparisons/dqn_delayaware_p3k_h128_eval_all_seeds.csv \
  --tag dqn_delayaware_p3k_h128
```

输出：

```text
runtime/comparisons/dqn_vs_baselines_dqn_delayaware_p3k_h128.csv
runtime/plots/dqn_vs_baselines_dqn_delayaware_p3k_h128_*.svg
```

`compare_dqn_with_baselines.py` 参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--baselineCsv` | `runtime/comparisons/baseline_comparison_all_seeds.csv` | baseline 多 seed 汇总 |
| `--dqnCsv` | `runtime/comparisons/dqn_eval_all_seeds.csv` | DQN 多 seed 汇总 |
| `--outputDir` | `runtime` | 输出目录 |
| `--tag` | DQN agent 名称 | 输出文件标签 |

## 9. 重点指标怎么读

高优先级指标：

- `mean_cumulative_reward`：综合 reward，越高越好。
- `mean_average_total_delay`：平均用户级 backlog age 总和，越低越好。
- `mean_average_deadline_misses`：平均持续超 deadline 用户数，越低越好。
- `mean_average_throughput`：平均吞吐，越高越好。
- `mean_average_reward_queue`：动作服务后的队列积压，越低越好。
- `mean_service_amount_fairness`：Jain fairness，越接近 1 越公平。

当前 reward 权重会明显惩罚 deadline miss。如果 DQN reward 更高但 throughput 较低，通常表示它牺牲了一部分吞吐来换低时延；这在低时延调度目标下可以接受，但需要在报告里说明 trade-off。

## 10. 常见微调方向

如果 `deadlineMisses` 长期接近 0：

- deadline 可能太宽。
- arrival 可能太轻。
- delay/deadline 指标区分度不足。

如果 `deadlineMisses` 长期很大：

- deadline 可能太紧。
- arrival 可能太重。
- deadline penalty 可能过强，学习会比较困难。

如果 DQN 吞吐太低：

- 降低 deadline penalty 或 delay penalty。
- 减小 `delay_aware` 预训练里的 delay 倾向。
- 对比 `greedy`、`delay_aware` 和 DQN 的 throughput/delay trade-off。

如果训练不稳定：

- 试 `--learningRate 5e-4`。
- 增大 `--bufferSize`。
- 增大 `--targetUpdateInterval`。
- 保持 `--rewardScale 0.1` 或更小。
- 先用 `--pretrainSteps 3000 --pretrainHeuristic delay_aware` 做 warm start。
