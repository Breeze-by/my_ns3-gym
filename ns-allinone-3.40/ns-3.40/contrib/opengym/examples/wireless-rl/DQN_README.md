# DQN 调度器 Demo 说明

完整手动实验流程和所有脚本参数见 [USER_GUIDE.md](USER_GUIDE.md)。本文件主要保留 DQN
思路、环境含义和推荐配置。

这个目录里已经接入了一个最小可运行的 DQN 例子，用来学习 `wireless-rl`
这个抽象无线资源分配环境。

你现在的环境可以理解成：

```text
5 个用户共享一个无线资源
每个时隙只能服务 1 个用户
DQN 每一步决定服务哪个用户
```

## 状态和动作

ns-3 每一步给 Python 的状态现在是 15 维：

```text
[cqi0, queue0, delay0,
 cqi1, queue1, delay1,
 cqi2, queue2, delay2,
 cqi3, queue3, delay3,
 cqi4, queue4, delay4]
```

含义是：

```text
cqi_i   用户 i 当前信道质量，范围约 1 到 10
queue_i 用户 i 当前队列长度，范围约 0 到 100
delay_i 用户 i 当前队列已经等待了多久，范围约 0 到 20
```

DQN 训练前会做归一化：

```text
CQI   / 10.0
Queue / 100.0
Delay / 20.0
```

这样做是为了避免队列数值比 CQI 大太多，导致神经网络过度偏向队列。

## 当前环境升级

环境已经从最初的短视 toy 版本升级成更适合 RL 的版本：

```text
状态从 10 维变成 15 维，加入 delay_i
reward 加入 totalDelay 惩罚
reward 加入 deadline miss 惩罚
CQI 从每步独立随机，改成 Markov 相关变化
```

新的 reward 近似为：

```text
reward = served
         - 0.01 * rewardQueue
         - 0.1 * totalDelay
         - 5.0 * deadlineMisses
```

这样 agent 不能只看当前吞吐量，还要考虑哪些用户已经等了很久、哪些用户快要超时。

注意：环境升级后，旧的 10 维模型不能继续作为正式结果使用，需要重新训练。

DQN 网络输出 5 个 Q 值：

```text
[Q(user0), Q(user1), Q(user2), Q(user3), Q(user4)]
```

训练时使用 epsilon-greedy：

```text
以 epsilon 的概率随机探索
以 1 - epsilon 的概率选择 Q 值最大的用户
```

评估时不再探索，直接选择：

```text
action = argmax(Q)
```

## 新增文件

`dqn_common.py`

存放 DQN 公共工具，包括状态归一化、Q 网络、Replay Buffer、动作选择、指标统计。

`train_dqn.py`

负责训练 DQN。它会连接 ns3-gym 环境，和 ns-3 交互，更新 Q 网络，保存模型和训练日志。

`evaluate_dqn.py`

负责测试训练好的 DQN 模型。它会加载 `.pt` 模型，在指定 seed 上评估，并输出和 baseline 一样风格的 summary。

`compare_dqn_with_baselines.py`

负责把 DQN 的多 seed 评估结果和 baseline 汇总到一张表里，并生成对比 SVG 图。

`plot_dqn_training.py`

负责把 DQN 训练 CSV 画成 SVG 曲线，比如 reward、epsilon、throughput、queue、loss。

`log.md`

记录 DQN 夜间迭代过程、参数、失败路线、最佳结果和结论。

`models/`

保存训练得到的模型，例如：

```text
models/dqn_seed1.pt
```

模型文件是运行产物，已经被 Git 忽略。

`runtime/dqn_train_seed*.csv`

DQN 训练曲线。

`runtime/results/dqn_seed*.csv`

DQN 评估时每一步的记录。

`runtime/summaries/dqn_seed*_summary.csv`

DQN 每个 seed 的评估 summary。

`runtime/comparisons/dqn_eval_all_seeds.csv`

DQN 多 seed 评估结果汇总。

## 快速跑通 Demo

先进入 conda 环境和项目目录：

```bash
conda activate ns3gym
cd ~/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
```

先跑一个很短的训练测试：

```bash
python3 train_dqn.py --episodes 5 --simTime 2 --stepTime 0.5 --device cuda:0
```

这个命令的目的不是训练出好模型，而是确认 DQN 和 ns3-gym 链路能正常工作。

成功后会生成：

```text
models/dqn_seed1.pt
runtime/dqn_train_seed1.csv
```

然后评估这个模型：

```bash
python3 evaluate_dqn.py --model models/dqn_seed1.pt --seeds 1,2 --simTime 2 --stepTime 0.5 --device cuda:0
```

成功后会生成：

```text
runtime/results/dqn_seed1.csv
runtime/results/dqn_seed2.csv
runtime/summaries/dqn_seed1_summary.csv
runtime/summaries/dqn_seed2_summary.csv
runtime/comparisons/dqn_eval_all_seeds.csv
```

## 正式训练建议

短 demo 跑通后，可以做第一版正式训练：

```bash
python3 train_dqn.py --episodes 300 --seed 1 --device cuda:0
```

训练完成后评估：

```bash
python3 evaluate_dqn.py --model models/dqn_seed1.pt --seeds 1,2,3,4,5 --device cuda:0
```

如果你想用第二张 GPU：

```bash
python3 train_dqn.py --episodes 300 --seed 1 --device cuda:1
```

## 当前推荐配置

目前这个目录里效果最好的 checkpoint 是一版带有 `delay_aware` 预热的
`dueling + double DQN`。推荐你优先复现这一版：

```bash
python3 train_dqn.py \
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

python3 evaluate_dqn.py \
  --model models/dqn_delayaware_p3k_h128.pt \
  --agentName dqn_delayaware_p3k_h128 \
  --seeds 1,2,3,4,5 \
  --simTime 20 \
  --stepTime 0.5 \
  --device cuda:0
```

当前最佳模型文件：

```text
models/dqn_delayaware_p3k_h128.pt
```

当前最佳 5-seed 汇总结果：

```text
runtime/comparisons/dqn_delayaware_p3k_h128_eval_all_seeds.csv
```

## 怎么看训练结果

训练日志在：

```text
runtime/dqn_train_seed1.csv
```

重点看这些列：

`total_reward`

每个 episode 的总收益。整体上最好逐渐变高，但不会严格单调上升，因为环境里的 CQI 和业务到达是随机的。

`average_reward`

每一步平均 reward。

`epsilon`

探索概率。它会从 `epsilonStart` 开始，逐渐衰减到 `epsilonEnd`。

`average_throughput`

每一步平均传输了多少数据。

`average_queue`

每一步动作执行后的平均队列积压。越低通常越好。

`average_loss`

DQN 的训练损失。它不一定单调下降，只要没有爆炸成很大的异常值，一开始不用太紧张。

## 旧模型兼容性

如果你在 `models/` 里看到更早的 `dqn_v1_*` 到 `dqn_v4_*` 模型，不要直接拿来
评估当前环境。它们对应的是更早的 10 维状态版本，现在环境已经升级到 15 维，
旧模型无法直接加载。

## 常用参数

`--episodes`

训练 episode 数。建议先用 `5` 或 `50` 测试，再用 `300` 做第一版实验。

`--simTime`

每个 episode 的仿真时间。默认是 `20` 秒。

`--stepTime`

环境 step 间隔。默认是 `0.5` 秒，所以 `simTime=20` 大约有 40 个决策步。

`--learningRate`

Adam 学习率。默认是 `1e-3`。

`--batchSize`

Replay Buffer 每次采样多少条经验。默认是 `64`。

`--bufferSize`

Replay Buffer 最大容量。默认是 `10000`。

`--epsilonStart`

初始探索概率。默认是 `1.0`，也就是一开始几乎全随机。

`--epsilonEnd`

最终最低探索概率。默认是 `0.05`。

`--epsilonDecay`

每个 episode 后 epsilon 乘上的衰减系数。默认是 `0.995`。

`--targetUpdateInterval`

每隔多少个 episode 把 policy network 同步到 target network。默认是 `20`。

`--hiddenSize`

神经网络隐藏层宽度。默认是 `64`。

`--networkType`

网络结构。当前支持：

```text
mlp
dueling
```

`dueling` 会把状态价值和动作优势分开估计，通常比普通 MLP 更稳一点。

`--doubleDqn` / `--no-doubleDqn`

是否使用 Double DQN target。默认开启。

`--rewardScale`

训练时对 reward 做缩放。默认是 `0.1`，目的是让 Q 值目标更平稳。

`--updatesPerStep`

每和 ns-3 交互一步，做几次 replay buffer 更新。

`--learningStarts`

Replay Buffer 至少积累多少条经验后才开始更新 DQN。

`--pretrainSteps`

在进入 ns3-gym 在线训练前，先用合成状态做多少步启发式预训练。

`--pretrainHeuristic`

预训练模仿哪个启发式策略。当前支持：

```text
max_service
greedy
delay_aware
max_delay
max_queue
max_cqi
```

其中 `delay_aware` 会同时看 `CQI * Queue` 和 delay，更适合升级后的环境。

`--device`

训练设备，可以是：

```text
auto
cpu
cuda:0
cuda:1
```

## 怎么调整实验

想让网络稍微大一点：

```bash
python3 train_dqn.py --hiddenSize 128 --episodes 300 --device cuda:0
```

想训练更久：

```bash
python3 train_dqn.py --episodes 1000 --epsilonDecay 0.997 --device cuda:0
```

想减少探索，让它更快进入利用阶段：

```bash
python3 train_dqn.py --epsilonDecay 0.99 --device cuda:0
```

想保持更久探索：

```bash
python3 train_dqn.py --epsilonDecay 0.999 --device cuda:0
```

## 当前阶段的目标

第一版 DQN 不要一开始就要求超过 `greedy`。

因为当前环境比较简单：

```text
serviceRate = CQI * 2
reward = throughput - 0.01 * queue
```

在这种设计下，`greedy = CQI * Queue` 本身可能已经非常强。

第一阶段更合理的目标是：

```text
DQN 明显好于 random
DQN 接近或超过 round_robin
DQN 尽量接近 max_queue / max_cqi / greedy
```

如果 DQN 能稳定接近 greedy，说明 DQN 和 ns3-gym 的训练链路已经成功。

## 旧环境最佳结果

下面结果来自旧的 10 维环境，只用于历史参考。

旧环境最佳模型是：

```text
models/dqn_v4_greedywarm_only.pt
```

它使用 `greedy` 作为 warm start 目标，让 DQN 网络学习 `CQI * Queue`
调度策略，然后在 10 个 seed 上评估。

最终对比结果在：

```text
runtime/comparisons/dqn_vs_baselines_final_dqn.csv
```

最终对比图在：

```text
runtime/plots/dqn_vs_baselines_final_dqn_cumulative_reward.svg
runtime/plots/dqn_vs_baselines_final_dqn_average_throughput.svg
runtime/plots/dqn_vs_baselines_final_dqn_average_reward_queue.svg
runtime/plots/dqn_vs_baselines_final_dqn_final_reward_queue.svg
runtime/plots/dqn_vs_baselines_final_dqn_service_amount_fairness.svg
```

关键结果：

```text
greedy mean_cumulative_reward = 440.468
DQN    mean_cumulative_reward = 438.240
```

DQN 非常接近 greedy，差距大约 0.5%。这说明 DQN 策略链路是成功的。

但升级到 15 维 delay/deadline 环境后，需要重新跑 baseline 和 DQN：

```bash
python3 run_multi_seed.py --seeds 1,2,3,4,5,6,7,8,9,10
python3 train_dqn.py --episodes 300 --pretrainHeuristic delay_aware --seed 1 --device cuda:0
python3 evaluate_dqn.py --model models/dqn_seed1.pt --seeds 1,2,3,4,5 --device cuda:0
```

更详细的过程记录在：

```text
log.md
```
