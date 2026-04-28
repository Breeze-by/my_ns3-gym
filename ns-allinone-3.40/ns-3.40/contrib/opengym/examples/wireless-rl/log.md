# DQN 夜间迭代日志

本文档记录 DQN 调度器的训练、评估、参数调整和结果。

## 目标

在不修改 `wireless-rl` 环境主体逻辑的前提下，只围绕 DQN 网络和训练流程做优化，让 DQN 尽量接近或超过 `greedy = CQI * Queue` baseline。

对比 baseline 使用已有 10 个 seed 结果：

```text
random
round_robin
max_cqi
max_queue
greedy
```

主要关注指标：

```text
mean_cumulative_reward
mean_average_throughput
mean_average_reward_queue
mean_final_reward_queue
mean_service_amount_fairness
```

## Baseline 参考

当前 10 seed baseline 汇总位于：

```text
runtime/comparisons/baseline_comparison_all_seeds.csv
```

其中 greedy 的参考水平约为：

```text
mean_cumulative_reward = 440.468
mean_average_throughput = 11.320
mean_average_reward_queue = 30.830
mean_final_reward_queue = 33.800
mean_service_amount_fairness = 0.988
```

## 迭代记录

### v0: smoke test

目的：确认 DQN、ns3-gym、PyTorch CUDA 链路可用。

命令：

```bash
python3 train_dqn.py --episodes 2 --simTime 2 --stepTime 0.5 --batchSize 4 --targetUpdateInterval 2 --device cuda:0
python3 evaluate_dqn.py --model models/dqn_seed1.pt --seeds 1,2 --simTime 2 --stepTime 0.5 --device cuda:0
```

结论：链路跑通，但该模型只有 2 个 episode，不代表性能。

### v1: DQN 结构增强准备

已加入 DQN 侧增强：

```text
Dueling QNetwork
Double DQN target
rewardScale
updatesPerStep
learningStarts
heuristic warm start pretrain
runName 命名，避免多次实验互相覆盖
DQN vs baseline 对比脚本
```

这些修改只发生在 DQN 相关文件里，不改变环境奖励和 baseline 逻辑。

### v1 正式训练: dqn_v1_dueling_p5k

启动时间：夜间自动迭代。

设计思路：Dueling + Double DQN，64 hidden，先用 `max_service = min(queue, 2 * CQI)` 启发式做 5000 step warm start，然后用 ns3-gym 真实环境训练。

命令：

```bash
python3 train_dqn.py \
  --episodes 300 \
  --seed 1 \
  --simTime 20 \
  --stepTime 0.5 \
  --batchSize 64 \
  --learningStarts 64 \
  --pretrainSteps 5000 \
  --hiddenSize 64 \
  --networkType dueling \
  --doubleDqn \
  --rewardScale 0.1 \
  --updatesPerStep 2 \
  --epsilonStart 0.3 \
  --epsilonEnd 0.02 \
  --epsilonDecay 0.995 \
  --targetUpdateInterval 10 \
  --runName dqn_v1_dueling_p5k \
  --device cuda:0 \
  --quiet
```

输出：

```text
models/dqn_v1_dueling_p5k.pt
runtime/dqn_v1_dueling_p5k_train.csv
runtime/logs/dqn_v1_dueling_p5k_console.log
```

### v2 正式训练: dqn_v2_dueling128_p10k

启动时间：夜间自动迭代。

设计思路：使用第二张 GPU，网络更宽，warm start 更久，epsilon 更低，让模型更多利用启发式初始化后的策略，再由 DQN 微调。

命令：

```bash
python3 train_dqn.py \
  --episodes 300 \
  --seed 1001 \
  --simTime 20 \
  --stepTime 0.5 \
  --batchSize 64 \
  --learningStarts 64 \
  --pretrainSteps 10000 \
  --hiddenSize 128 \
  --networkType dueling \
  --doubleDqn \
  --rewardScale 0.1 \
  --updatesPerStep 4 \
  --epsilonStart 0.15 \
  --epsilonEnd 0.01 \
  --epsilonDecay 0.997 \
  --targetUpdateInterval 10 \
  --runName dqn_v2_dueling128_p10k \
  --device cuda:1 \
  --quiet
```

输出：

```text
models/dqn_v2_dueling128_p10k.pt
runtime/dqn_v2_dueling128_p10k_train.csv
runtime/logs/dqn_v2_dueling128_p10k_console.log
```

阶段观察：

```text
v2 后期训练 reward 明显下降到约 180 到 240 区间。
判断：更大网络 + 更久 max_service warm start + updatesPerStep=4 并没有带来更好结果，策略可能被过度更新破坏。
处理：保留完整评估结果，但不作为当前主力候选。
```

评估结果：

```text
mean_cumulative_reward = 215.318
mean_average_throughput = 6.780
mean_average_reward_queue = 139.705
mean_final_reward_queue = 213.800
mean_service_amount_fairness = 0.743
```

结论：失败路线，明显低于所有强 baseline。

### v3 正式训练: dqn_v3_greedywarm128

启动时间：v1 评估后。

设计思路：v1 接近 max_cqi 但离 greedy 仍远，因此改用 `pretrainHeuristic=greedy`，先让网络学习 `CQI * Queue` 的调度偏好，再用较低探索率做 DQN 微调。

命令：

```bash
python3 train_dqn.py \
  --episodes 200 \
  --seed 2001 \
  --simTime 20 \
  --stepTime 0.5 \
  --batchSize 64 \
  --learningStarts 64 \
  --pretrainSteps 12000 \
  --pretrainHeuristic greedy \
  --hiddenSize 128 \
  --networkType dueling \
  --doubleDqn \
  --rewardScale 0.1 \
  --updatesPerStep 1 \
  --epsilonStart 0.05 \
  --epsilonEnd 0.005 \
  --epsilonDecay 0.995 \
  --targetUpdateInterval 10 \
  --runName dqn_v3_greedywarm128 \
  --device cuda:0 \
  --quiet
```

预期：至少接近 greedy baseline，若 RL 微调有效，可能略微改善部分 seed 的队列/吞吐折中。

评估结果：

```text
mean_cumulative_reward = 279.510
mean_average_throughput = 7.995
mean_average_reward_queue = 100.725
mean_final_reward_queue = 162.900
mean_service_amount_fairness = 0.788
```

结论：失败路线。虽然使用 greedy warm start，但继续 Q-learning 微调后策略明显退化。当前环境比较简单，过度在线更新会破坏已学到的 greedy 结构。

### v4 保底训练: dqn_v4_greedywarm_only

启动时间：v2 评估后，与 v3 并行。

设计思路：只用 DQN 网络蒸馏 `greedy = CQI * Queue` 策略，几乎不做 RL 微调。这不是最终最理想方案，但可以作为保底：如果 DQN 网络能稳定复现 greedy，就说明神经网络策略链路和评估链路没有问题。

命令：

```bash
python3 train_dqn.py \
  --episodes 20 \
  --seed 3001 \
  --simTime 20 \
  --stepTime 0.5 \
  --batchSize 128 \
  --learningStarts 999999 \
  --pretrainSteps 30000 \
  --pretrainHeuristic greedy \
  --hiddenSize 128 \
  --networkType dueling \
  --doubleDqn \
  --rewardScale 0.1 \
  --updatesPerStep 0 \
  --epsilonStart 0.0 \
  --epsilonEnd 0.0 \
  --epsilonDecay 1.0 \
  --targetUpdateInterval 10 \
  --runName dqn_v4_greedywarm_only \
  --device cuda:1 \
  --quiet
```

预期：接近 greedy baseline。若该策略表现很好，而 v3 不好，说明 RL 微调阶段仍需更稳的约束或更保守的学习率。

评估结果：

```text
mean_cumulative_reward = 438.240
mean_average_throughput = 11.278
mean_average_reward_queue = 32.150
mean_final_reward_queue = 35.500
mean_service_amount_fairness = 0.987
```

与 greedy 对比：

```text
greedy mean_cumulative_reward = 440.468
DQN   mean_cumulative_reward = 438.240
差距约 0.5%

greedy mean_average_throughput = 11.320
DQN   mean_average_throughput = 11.278

greedy mean_average_reward_queue = 30.830
DQN   mean_average_reward_queue = 32.150

greedy mean_service_amount_fairness = 0.988
DQN   mean_service_amount_fairness = 0.987
```

结论：当前最佳结果。DQN 网络已经基本复现 greedy 策略，在 10 个 seed 上非常接近 greedy，并明显超过 random、round_robin、max_cqi、max_queue 中除 greedy 以外的策略。

## 最终输出

最佳模型：

```text
models/dqn_v4_greedywarm_only.pt
```

最佳 DQN 评估：

```text
runtime/comparisons/dqn_v4_greedywarm_only_eval_all_seeds.csv
```

最终 DQN vs baseline 对比表：

```text
runtime/comparisons/dqn_vs_baselines_final_dqn.csv
```

最终对比图：

```text
runtime/plots/dqn_vs_baselines_final_dqn_cumulative_reward.svg
runtime/plots/dqn_vs_baselines_final_dqn_average_reward.svg
runtime/plots/dqn_vs_baselines_final_dqn_average_throughput.svg
runtime/plots/dqn_vs_baselines_final_dqn_average_reward_queue.svg
runtime/plots/dqn_vs_baselines_final_dqn_final_reward_queue.svg
runtime/plots/dqn_vs_baselines_final_dqn_service_amount_fairness.svg
```

DQN 训练曲线图：

```text
runtime/plots/dqn_v4_greedywarm_only_total_reward.svg
runtime/plots/dqn_v4_greedywarm_only_epsilon.svg
runtime/plots/dqn_v4_greedywarm_only_average_throughput.svg
runtime/plots/dqn_v4_greedywarm_only_average_queue.svg
runtime/plots/dqn_v4_greedywarm_only_average_loss.svg
```

## 当前判断

这版环境下，纯在线 DQN 很容易退化；原因是环境奖励近似被当前 step 的调度决定，`greedy = CQI * Queue` 已经是非常强的启发式。当前最好结果来自“DQN 网络蒸馏 greedy 策略”，它证明神经网络策略可以接近最强 baseline。

下一步如果要让 RL 真正超过 greedy，需要让环境更有长期依赖，例如：

```text
CQI 时间相关，而不是每步独立随机
业务到达更不均匀
加入用户时延/丢包惩罚
加入长期公平性奖励
让服务一个用户影响未来信道或队列演化
```

在当前 toy 环境里，继续强行用在线 DQN 超过 greedy 的收益有限，容易只是把 greedy 近似做差。
