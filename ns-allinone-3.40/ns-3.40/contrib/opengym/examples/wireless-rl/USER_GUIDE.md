# wireless-rl 项目指南

最后按代码核对：2026-09-02。

这是当前项目的主要入口。report/20260429.md 和 log.md 记录历史实验，
但环境定义、默认参数和运行行为以当前源码为准。

最终论文目标已经从当前 toy 调度 MDP 明确为“受干扰 Wi-Fi 4 下的多机器人
协同建图、目标搜索、充电和集合任务”。完整研究问题、ROS 2 项目路径、系统
边界、指标、风险和一年路线统一记录在 `RESEARCH_PLAN.md`。该文件是规划，
不是当前已实现功能；重新开始工作时应先阅读它，再阅读本指南。

## 0. 五分钟重新上手

本项目所有 Python 命令都必须在 conda 环境 `ns3gym` 中运行，包括
baseline、DQN 训练/评估和画图脚本。不要直接使用 system Python 或 base 环境。
这里的 Python 通过 `ns3gym` 启动本地 ns-3 `wireless-rl` 可执行文件；
所以从操作流程上说，整个 ns3-gym 实验链路都在激活该 conda 环境后运行。

进入环境和项目目录：

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
```

确认没有进错环境：

```bash
which python
python -c "import ns3gym; print(ns3gym.__file__)"
```

正确路径应分别位于：

```text
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python
/home/zhuyulab/miniconda3/envs/ns3gym/lib/python3.10/site-packages/ns3gym/
```

先跑一个不保存结果的两步 smoke test：

```bash
python test.py \
  --agent greedy \
  --seed 1 \
  --simTime 1 \
  --stepTime 0.5 \
  --no-save \
  --no-plot
```

正常情况下会看到：

- observation space 为 Box(0, 100, (15,), uint64)；
- action space 为 Discrete(5)；
- episode 共 ceil(1 / 0.5) = 2 步；
- Python 自动启动 wireless-rl ns-3 可执行文件。

当前环境在 2026-09-02 实测为 Python 3.10.20、NumPy 2.2.6、
PyTorch 2.11.0+cu128，并可见两张 NVIDIA GeForce RTX 4090。
`--device auto` 会选择 `cuda:0`。导入 ns3gym 时会出现旧版 Gym 的
维护状态警告，但 smoke test 可以正常完成。

用户目录曾存在 `~/.local/lib/python3.10/site-packages/torch 2.12.0+cpu`，
它会遮蔽 conda 环境中的 CUDA PyTorch。现在 `ns3gym` 已配置
`PYTHONNOUSERSITE=1`。如果以后 `torch.cuda.is_available()` 意外变成
`False`，先重新激活环境并检查 `torch.__file__`，不要直接重装 PyTorch：

```bash
conda env config vars set PYTHONNOUSERSITE=1 -n ns3gym
conda deactivate
conda activate ns3gym
echo "$PYTHONNOUSERSITE"
python -c "import torch; print(torch.__file__, torch.__version__, torch.cuda.is_available())"
```

如果 sim.cc 改过，可从 ns-3 根目录只构建本例：

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40
./ns3 build wireless-rl
```

ns3gym 启动仿真时也会按需触发构建，但显式构建更容易发现 C++ 编译错误。

运行完整的最小自动回归检查：

```bash
python check_project.py
```

它会检查 conda/CUDA 环境，在 GPU 上执行一次 DQN forward、backward 和
optimizer step，构建 ns-3，运行两次固定 seed 的短仿真，并比较结果是否完全一致。

## 1. 这个项目到底是什么

这是一个用于验证调度算法和强化学习链路的 toy wireless resource allocation
环境，分为三层：

| 层 | 文件 | 职责 |
|---|---|---|
| ns-3 环境 | sim.cc | 生成抽象 CQI、队列和 delay，执行服务动作并计算 reward |
| baseline/实验编排 | test.py、run_baselines.py、run_multi_seed.py | 运行手工策略，保存单 seed 和多 seed 结果 |
| DQN | dqn_common.py、train_dqn.py、evaluate_dqn.py | 网络、replay buffer、训练、validation checkpoint 和评估 |
| 展示 | plot_dqn_training.py、compare_dqn_with_baselines.py | 生成训练曲线和 DQN/baseline 对比 |

它目前没有真实的 Wi-Fi/5G PHY、MAC、节点、信道传播、数据包或 RB/MCS。
所谓 CQI、到达和服务都是 sim.cc 中的整数随机过程和队列算术。
因此当前结论只能说明“DQN 在这个抽象 MDP 的 reward 上优于手写策略”，
不能直接外推成真实无线系统性能。

## 2. 当前环境定义

### 2.1 状态和动作

固定 5 个用户，每个用户 3 个特征：

```text
[cqi0, queue0, delay0, ..., cqi4, queue4, delay4]
```

- observation dimension：15；
- action space：Discrete(5)；
- action=i：本 step 服务用户 i；
- C++ observation dtype：uint64；
- DQN 输入会转成 float32，并分别除以 10、100、20。

环境常量：

| 量 | 当前值 | 代码语义 |
|---|---:|---|
| 用户数 | 5 | userNum |
| CQI 范围 | 1–10 | 初始均匀采样，之后每步加 {-2,-1,0,1,2} 并截断 |
| 单用户队列上限 | 100 | 每步到达量均匀取整数 0–5 |
| delay 上限 | 20 | 非空队列每次环境更新加 1 |
| deadline | 8 | queue > 0 且 delay > 8 才计 miss |
| service rate | 2 * CQI | 实际服务量为 min(queue, 2 * CQI) |

delay_i 是用户级 backlog age，不是 packet delay。新到达使空队列变为非空时，
该次环境更新就会把 delay 设为 1；只有被选用户服务后队列清空，delay 才立即归零。

### 2.2 一步交互的时序

理解指标时最重要的是以下顺序：

```text
更新 CQI / arrival / delay，形成 s_t
        ↓
Python 收到 observation s_t，选择 action a_t
        ↓
服务被选用户
        ↓
立即记录 rewardQueue / totalDelay / deadlineMisses 并计算 r_t
        ↓
下一次环境更新形成 s_(t+1)
```

reward 是服务后、下一次随机到达前的快照：

```text
served
- 0.01 * rewardQueue
- 0.1  * totalDelay
- 5.0  * deadlineMisses
```

CSV 中两组名字容易混淆：

- rewardQueue、totalDelay、deadlineMisses：计算当前 reward 时的快照；
- currentQueue、currentDelay、currentDeadlineMisses：读取 extra info 时的当前环境值，可能已经包含下一次更新。

训练和正式汇总使用 reward 快照中的 totalDelay、deadlineMisses，队列同时保留
average_reward_queue 和 average_current_queue 两套指标。

### 2.3 episode 和随机种子

episode 步数为 ceil(simTime / stepTime)。

C++ 固定 RngSeedManager::SetSeed(1)，命令行 --seed/simSeed 用作
RngSeedManager::SetRun(simSeed)。

- test.py：使用指定 seed；
- train_dqn.py：第 episode 个训练环境使用 seed + episode；
- validation：反复使用 --evalSeeds 指定的独立 seeds；
- 正式评估：应使用既不参与训练、也不参与 checkpoint 选择的 seeds。

历史推荐模型以 seed 1 训练 300 episodes，因此训练环境 seeds 是 1–300；
validation seeds 1001–1003 与训练独立，但 2026-04-29 表格使用的 evaluation
seeds 1–10 与训练前 10 个 episodes 重叠。该表格不是严格 held-out test。
2026-09-02 已使用全新 seeds 2001–2010 配套重跑 DQN 和全部 baselines；
结果见第 7 节。

不要用 test.py --iterations > 1 做正式实验。该模式复用同一个包含 C++ 全局状态的
环境进程，当前代码没有证明 reset 会完整恢复所有全局变量。正式脚本按 seed 启动新进程。

## 3. Baseline 策略

| agent | 动作规则 |
|---|---|
| random | 使用 Python RNG 均匀选择用户 |
| round_robin | step % 5 |
| max_cqi | 最大 CQI |
| max_queue | 最大 queue |
| max_delay | 最大 delay；全为 0 时退化到 max queue，再退化到 max CQI |
| greedy | 最大 CQI * queue；所有 queue 为 0 时用 max CQI |
| delay_aware | 最大 CQI * queue + 20 * delay；score 全不大于 0 时用 max CQI |

历史实验中 greedy 通常是最强的手工 baseline。DQN 能看到 delay，因此正式比较必须
保留 max_delay 和 delay_aware，不能只与不看 delay 的策略比较。

## 4. 当前 DQN

默认训练配置不是历史最佳配置。代码默认值是：

- 两层 hidden MLP，每层 64；默认 dueling head；
- Double DQN 默认开启；
- replay buffer 10000，batch size 64；
- Adam，learning rate 1e-3；
- gamma 0.99，reward scale 0.1；
- epsilon 从 1.0 开始，每 episode 乘 0.995，最低 0.05；
- 每 20 episodes 同步 target network；
- gradient norm clip 为 10；
- synthetic heuristic pretraining 默认关闭；
- validation checkpoint selection 默认关闭。

可选 warm start 会随机生成符合状态范围的 synthetic states，用指定 heuristic 产生标签，
先做监督分类。它不是从真实 rollout 收集 demonstration。

开启 --evalInterval N 后，训练每 N 个 episode 以及最后一个 episode 在
--evalSeeds 上进行 greedy-Q validation。_best.pt 按 validation seeds 的
mean cumulative reward 选择；普通 .pt 始终保存最后一个训练状态。

## 5. 常用工作流

### 5.1 单个 baseline

```bash
python test.py --agent delay_aware --seed 1 --simTime 20 --stepTime 0.5
```

主要参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| --start | 1 | 是否由 Python 启动 ns-3；一般保持 1 |
| --iterations | 1 | 单进程 episode 数；正式实验保持 1 |
| --agent | greedy | baseline 策略 |
| --port | 0 | start=1 时由 ns3gym 选择空闲端口 |
| --simTime | 20.0 | 仿真时长 |
| --stepTime | 0.5 | 调度间隔 |
| --seed | 1 | ns-3 run number 和 Python action RNG seed |
| --outputDir | runtime | 输出根目录 |
| --no-save | 关闭 | 不写 CSV，也不画图 |
| --no-plot | 关闭 | 写 CSV，但不画 SVG |

### 5.2 正式 baseline 对比

单 seed：

```bash
python run_baselines.py --seed 1 --quiet
```

多 seed：

```bash
python run_multi_seed.py --seeds 1,2,3,4,5,6,7,8,9,10 --quiet
```

只重新聚合已有结果时使用 --skip-run。run_baselines.py 强制
--iterations 1；run_multi_seed.py 会为每个 seed 启动一次前者。

### 5.3 DQN 训练

DQN smoke test：

```bash
python train_dqn.py \
  --episodes 2 \
  --simTime 1 \
  --stepTime 0.5 \
  --device auto \
  --runName smoke_test
```

复现历史推荐训练配置：

```bash
python train_dqn.py \
  --episodes 300 \
  --seed 1 \
  --simTime 20 \
  --stepTime 0.5 \
  --device auto \
  --quiet \
  --hiddenSize 256 \
  --learningRate 5e-4 \
  --epsilonStart 0.2 \
  --epsilonEnd 0.01 \
  --epsilonDecay 0.995 \
  --pretrainSteps 5000 \
  --pretrainHeuristic delay_aware \
  --evalInterval 25 \
  --evalSeeds 1001,1002,1003 \
  --runName dqn_exp06_evalselect_p5k_h256
```

训练输出：

```text
models/{runName}.pt
models/{runName}_best.pt       # 仅开启 validation 且至少评估一次时
runtime/{runName}_train.csv
```

### 5.4 训练曲线

```bash
python plot_dqn_training.py \
  --csv runtime/dqn_exp06_evalselect_p5k_h256_train.csv \
  --tag dqn_exp06_evalselect_p5k_h256
```

### 5.5 DQN 多 seed 评估

```bash
python evaluate_dqn.py \
  --model models/dqn_exp06_evalselect_p5k_h256_best.pt \
  --agentName dqn_exp06_evalselect_p5k_h256_best_heldout \
  --seeds 2001,2002,2003,2004,2005,2006,2007,2008,2009,2010 \
  --simTime 20 \
  --stepTime 0.5 \
  --device auto \
  --outputDir runtime/heldout_2001_2010
```

评估使用 greedy Q action，不含 epsilon exploration。

### 5.6 DQN 与 baseline 合并对比

先确保 baseline 和 DQN 使用完全相同的 evaluation seeds、simTime 和
stepTime，然后运行：

```bash
python run_multi_seed.py \
  --seeds 2001,2002,2003,2004,2005,2006,2007,2008,2009,2010 \
  --outputDir runtime/heldout_2001_2010 \
  --quiet \
  --no-plot

python compare_dqn_with_baselines.py \
  --baselineCsv runtime/heldout_2001_2010/comparisons/baseline_comparison_all_seeds.csv \
  --dqnCsv runtime/heldout_2001_2010/comparisons/dqn_exp06_evalselect_p5k_h256_best_heldout_eval_all_seeds.csv \
  --outputDir runtime/heldout_2001_2010 \
  --tag dqn_exp06_evalselect_p5k_h256_best_heldout
```

这个脚本只合并 CSV 并画图，不检查两边 seeds 或仿真参数是否一致，调用者必须自己确认。

## 6. 输出和指标

```text
runtime/results/       每 step 结果
runtime/summaries/     单 agent、单 seed summary
runtime/comparisons/   单 seed 或多 seed 聚合比较
runtime/plots/         SVG 图
runtime/command_logs/  手工保存的历史命令输出
models/                PyTorch checkpoints
```

正式结果优先看：

| 指标 | 方向 | 含义 |
|---|---|---|
| mean_cumulative_reward | 越高越好 | 每个 episode reward 总和的 seed 均值 |
| mean_average_throughput | 越高越好 | 每 step 实际服务量的 seed 均值 |
| mean_average_reward_queue | 越低越好 | reward 快照中总队列的 seed 均值 |
| mean_average_total_delay | 越低越好 | reward 快照中 5 个 backlog age 之和的 seed 均值 |
| mean_average_deadline_misses | 越低越好 | 每 step 持续超时用户数的 seed 均值 |
| mean_service_amount_fairness | 越接近 1 越公平 | 按各用户累计 served amount 计算 Jain fairness |

多 seed 的 std_* 使用 sample standard deviation，即 NumPy ddof=1；
只有一个 seed 时记为 0。

## 7. 当前结果

### 7.1 2026-09-02 held-out 复测

历史最佳 checkpoint 已在全新 seeds 2001–2010 上与全部 baselines 重新比较。
这些 seeds 不属于训练 seeds 1–300 或 validation seeds 1001–1003。

| Agent | Reward | Throughput | Reward queue | Total delay | Misses | Fairness |
|---|---:|---:|---:|---:|---:|---:|
| random | -518.758 | 8.1400 | 105.4950 | 56.2900 | 2.8850 | 0.9240 |
| round_robin | -437.580 | 8.8950 | 86.9000 | 53.5300 | 2.7225 | 0.9476 |
| max_cqi | -530.368 | 6.6450 | 136.4450 | 51.3975 | 2.6800 | 0.7117 |
| max_queue | -630.028 | 8.2950 | 92.4700 | 64.3350 | 3.3375 | 0.9816 |
| max_delay | -523.314 | 7.0225 | 126.2100 | 51.6825 | 2.7350 | 0.8318 |
| greedy | -284.997 | 10.1275 | 64.6425 | 46.8100 | 2.3850 | 0.9791 |
| delay_aware | -322.693 | 9.4600 | 77.4325 | 46.6550 | 2.4175 | 0.9772 |
| DQN best held-out | **-128.586** | 9.8200 | 69.9400 | **35.9775** | **1.7475** | 0.9460 |

DQN 相对 strongest baseline `greedy`：

- cumulative reward 平均提高 156.411，10/10 seeds 胜出；
- total delay 平均降低 10.8325，10/10 seeds 胜出；
- deadline misses 平均降低 0.6375，10/10 seeds 胜出；
- throughput 平均低 0.3075，reward queue 高 5.2975，fairness 低 0.0331。

paired reward difference 的 95% t interval 约为 [108.054, 204.768]。
核心 DQN 优势在 held-out seeds 上仍然存在。完整方法和逐项解释见
`report/20260902.md`。

结果文件：

```text
runtime/heldout_2001_2010/comparisons/baseline_comparison_all_seeds.csv
runtime/heldout_2001_2010/comparisons/dqn_exp06_evalselect_p5k_h256_best_heldout_eval_all_seeds.csv
runtime/heldout_2001_2010/comparisons/dqn_vs_baselines_dqn_exp06_evalselect_p5k_h256_best_heldout.csv
```

### 7.2 2026-04-29 历史结果

下列结果来自 2026-04-29 的 10-seed 实验，不是 2026-09-02 重新训练的结果。
本地 checkpoint 和对应 CSV 仍然存在，并已核对 metadata：

```text
models/dqn_exp06_evalselect_p5k_h256_best.pt
runtime/comparisons/dqn_exp06_evalselect_p5k_h256_best_eval_all_seeds.csv
runtime/comparisons/dqn_vs_baselines_dqn_exp06_evalselect_p5k_h256_best.csv
```

checkpoint 信息：dueling Double DQN、hidden size 256、300 episodes、
5000-step delay_aware warm start；每 25 episodes 在 seeds 1001–1003 上选择，
最佳 checkpoint 来自 zero-based episode 249，validation mean reward 为
-71.463334。

历史 evaluation seeds 1–10：

| Agent | Reward | Throughput | Reward queue | Total delay | Misses | Fairness |
|---|---:|---:|---:|---:|---:|---:|
| random | -486.868 | 7.7850 | 103.6950 | 52.6975 | 2.7300 | 0.8888 |
| round_robin | -408.080 | 8.6550 | 86.4250 | 50.9275 | 2.5800 | 0.9438 |
| max_cqi | -529.182 | 6.3450 | 143.4300 | 50.5275 | 2.6175 | 0.6843 |
| max_queue | -641.642 | 7.7250 | 100.2550 | 63.5100 | 3.2825 | 0.9771 |
| max_delay | -550.375 | 6.7925 | 127.6375 | 53.5050 | 2.7850 | 0.7978 |
| greedy | -278.111 | 9.6525 | 70.4775 | 45.5050 | 2.2700 | 0.9531 |
| delay_aware | -361.319 | 9.2350 | 80.7225 | 48.7325 | 2.5175 | 0.9567 |
| DQN best | -105.792 | 9.3250 | 73.8050 | 34.4425 | 1.5575 | 0.8974 |

在这组与训练重叠的 seeds 上，DQN 相比 greedy 明显降低 delay 和 misses，并取得更高
cumulative reward；代价是吞吐约低 3.4%，fairness 也更低。这是有价值的训练结果，
但因为 evaluation seeds 1–10 已在训练中出现，不能把表格当作 held-out 泛化结论。
即使在新 seeds 上复现，也仍只能证明当前 toy MDP，不能直接证明真实无线协议性能。

## 8. 已知边界和下一步决策

当前最重要的模型边界：

- 没有 packet-level queue、arrival timestamp 或 packet deadline；
- miss 是“当前仍超时的用户数”，不是新发生违约数、累计丢包数或 packet violation；
- 5 个用户和归一化上限在 C++、baseline、DQN 代码中分别硬编码；
- reward 没有 fairness 项，因此 DQN 降低公平性是可预期的；
- 历史 evaluation seeds 1–10 与训练 seeds 1–300 重叠；该问题已通过
  seeds 2001–2010 的 held-out 复测解决；
- 旧的 10-dimensional CQI + Queue checkpoints 与当前 15-dimensional 网络不兼容；
- `check_project.py` 已自动化 conda/CUDA 检查、build、短 smoke test 和固定 seed
  可重复性比较，但还没有覆盖完整训练收敛或统计性实验回归。

如果恢复研究，先决定研究问题，再改代码。最自然的下一阶段是把抽象用户 backlog age
升级为 packet-level queue，明确 arrival time、packet delay、deadline violation 和 drop
语义；在完成这一步前，不建议继续堆 PPO、Rainbow、PER 等算法，因为环境真实性是当前
主要瓶颈。

## 9. 修改时的同步清单

- 每次训练、评估、baseline sweep、ablation 或正式 smoke/regression 运行后，
  必须在同一工作会话追加 `log.md`。失败和中断的实验也要记录；至少包含日期、
  目的、代码状态、完整命令、模型、seeds、关键参数、输出路径、结果和结论。
- 改 observation、用户数或归一化范围：同步 sim.cc、test.py、dqn_common.py，
  并将旧 checkpoint 标记为不兼容。
- 改 baseline：同步 test.py 的 action rule、run_baselines.py 的 BASELINES，
  检查 run_multi_seed.py 和图表颜色/标签。
- 改 reward 或指标时序：同步本文、CSV 字段解释和新报告，不要覆盖历史报告。
- 正式对比：baseline 与 DQN 必须使用相同 evaluation seeds、simTime、stepTime。
- 不提交 runtime/ 生成物和 models/*.pt，除非明确要求。
