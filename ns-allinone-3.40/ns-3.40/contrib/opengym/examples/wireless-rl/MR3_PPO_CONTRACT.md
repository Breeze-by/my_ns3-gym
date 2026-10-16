# MR3-P2A 联合 MaskablePPO pilot 契约 v3

2026-10-16：用户验收 P1C 并授权 P2A。P2A 进行中，P2B 及后续未开始。
正式任务沿用 [任务契约](MR3_TASK_CONTRACT.md) 与 [环境契约](MR3_ENV_CONTRACT.md)：
原生 Gazebo、恰好三机器人、95%/300 仿真秒、原地图质量/参与/18 路接触及导航闭合门禁。
本契约不授权二维替代、gateway 或历史候选 500k/72h 配额。

## 模型与学习

固定 `mr3-learning-tensors-v1`；二值地图不除以 255，不使用在线观测或 reward 归一化。
复用 P1C 的全局 CNN、三台共享局部 CNN、状态/候选/历史/任务 MLP，融合为 256 维。
直接输出联合 1000 类 actor 和一个集中式 value；无额外策略 MLP、循环网络或手工目标兜底。
掩码不进入学习编码器，只作用于分布；采样时的候选、张量、掩码和 log probability 一并保存。
真值和 reward diagnostics 仅用于训练目标、离线指标与审计，不拼入 actor/critic 的输入。

学习依赖固定 SB3=2.9.0、sb3-contrib=2.9.0，保留原 Gymnasium1.3.0、PyTorch2.11.0+cu128。
复用成熟 `MaskablePPO.train()`、masked categorical、Adam 与 clipped PPO loss。
学习率 3e-4、gamma=.99/仿真秒、GAE lambda=.95/仿真秒、clip=.2、entropy=.01、
value coefficient=.5、max grad norm=.5、target KL=.03、每 round 最多 4 epochs、minibatch64。
记录实际 optimizer.step 次数与 PPO epoch 数；KL 提前停止不补足更新。

## 完整 episode rollout 与终态

每 round 同一只读策略在 1/2/4 个隔离三机器人环境采样；所有 episode 关闭并核验原生退出后才更新。
不跨 optimizer 更新保留尚未结算的动作，从而避免末步在更新后收到零时长终态通知。

- 普通真实决策为 1 秒；有动作的短终态（包括有效 dt=0、真实物理推进20ms）保留为 actor 样本。
- `action_submitted=false`、完全复用观测的零物理终态通知不产生 actor 样本。核对 epoch、时间、
  奖励序号、观测/候选/交付身份后，将其奖罚直接加到此前真实决策并将此前决策标记为 terminated，
  不另乘 gamma。无此前真实决策或重复结算报错。
- 逐条 `discount=gamma**dt`、`trace=lambda**dt`；terminated bootstrap=0。
  外部 truncated 只 bootstrap 一次真实末观测的 value，GAE 不跨 episode。
- 按完整 episode 展平构造精确长度的 `MaskableDictRolloutBuffer`；保留原采样掩码供 PPO 重评概率。
  最后 singleton minibatch 并入前一批，避免标准优势标准化的单样本标准差产生 NaN。
- 基础设施错误抛出且整 round 不更新；保留所有成功、任务失败、故障前缀和 cleanup 回执，不静默补样本。

## 当前执行修订与预声明范围

v1/v2最小链各完成8真实决策和4次GPU optimizer.step；v1首次文档SHA绑定失败与修正PASS并列保留。
v2 pilot在首个完整round返回前诊断中断：实际390条原生已执行决策、389.10奖励仿真秒、
1752.9574942300096墙秒，0次optimizer更新；388条collector返回与390条原生记录分开。
四条初始策略轨迹均暴露tb3候选饥饿，另有两次真实peer安全失败；两个未完成前缀正常关闭。
这些失败保留，不能将顶层完整round计数0解释成没有采样，也不能复用为v3训练信用。
详见[P2A报告](report/20261016_mr3_p2a.md)。

v3将执行契约明确修订为`mr3-per-robot-geometric-staging-v3`：每台已交付本地图的可达几何池
先保证代表项，再做共享K8最远点采样；不引入真值、收益排序、手工目标选择或不安全起点吸附。
路径仍要求`.25+.04=.29m`净空；目标需在融合图及该台本地图中容纳`.29+.10=.39m`
完整到达圆盘。新目标之间最少`.78m`，新目标与空闲实际机体最少`.68m`；全KEEP始终合法。
候选规则和半径写入`candidate_rule`并参与`candidate_version`哈希，审计按明确版本核对。
活动SLAM YAML只将`minimum_travel_distance/heading`从`.5m/.5rad`改为`.10m/.20rad`，
使短子目标位移能触发地图积分；ROS时间节流`.5s`、地图更新5s及C++/Karto实现不变。
实际tb1/tb2/tb3 Nav2配置的GoalChecker和DWB位置容差均由`.25m`收紧至`.10m`，yaw保持3.14。
这属于新冻结的执行参数变化，P1B/P1C及v1/v2原件仍只证明原冻结，不转记为v3证据。
300秒/95%、质量、三台参与、18路接触健康、peer包络及导航所有权门禁均不放宽。

[v3前瞻计划](report/assets/20261016_mr3_p2a/predeclared_plan_v3.json)在原生运行前绑定同一新提交推送冻结；
计划中的`SOURCE_FREEZE_FROM_METADATA`由各运行metadata记录实际SHA，不猜测尚未产生的提交。
先完成CPU/静态检查和原生最小更新链：1 worker、open101、学习seed41、16真实决策、
外部16步截断、900墙秒，最多4 epochs。它验证采样/更新/checkpoint及新执行接口，不能证明95%。
最小链及独立原生/policy审计未通过则先诊断、新冻结，不启动pilot；所有尝试保留。

之后以全新初始权重执行单训练seed41的v3 pilot：4 workers，每个仍为tb1/tb2/tb3，固定open101，
最多3706真实决策或12600墙秒采样截止（先到即停），普通episode上限300步，不载入v2 checkpoint。
预算沿用原4096决策/14400墙秒：扣除v2实际390决策及1752.9574942300096墙秒，
决策余量3706，墙时余量12647.04250576999秒，v3保守取12600秒，不扩展原pilot预算。
最小工程链与固定开发验证分别记账；原生安全取消/退出及已开始round的最后一次更新收尾
仍按原声明单列实际额外墙时，不混入任务300仿真秒。

v3 pilot完成后冻结final checkpoint，在open401/open402/open403各运行一轮开发验证，
总上限900决策、9000墙秒，最多4 workers、确定性mask-aware推理、0 optimizer更新。
只使用最终checkpoint，不从验证episode反馈选checkpoint或调参。
这些均为开发已见布局，不称未见泛化；rooms/corridors与姿态变化在固定布局学习诊断后再预声明。

本轮无自动重试。真实任务失败计入；基础设施故障终止run，保留前缀与已有checkpoint。
如未达到95%任务/安全/学习出口，明确P2A未完成，诊断表示、候选、采样与奖励，停在本步。
不因短预算或有optimizer更新就宣布P2A验收通过，也不进入P2B或接网。

## 证据

入口 `python -m mr3_learning.ppo`；命令见 [ROS启动页](../../../../../../ros2_ws/ros2-multi-robot-automap/launch_commands.md)。
每次运行需干净已提交且推送的freeze、新run-id；metadata记录完整命令、版本、seed与预算。
中断后另外记录collector已返回、原生已执行和完整round已纳入学习的计数，保留所有差额和错误；
关闭时仅结算奖励但没有提交动作的记录不能充当actor样本。中断分类与原始错误并存。
保存native原件、startup/reset/closure、采样时张量/掩码/动作/value/log_prob/GAE/return、
逐次checkpoint及SHA、熵/KL/value loss/梯度、覆盖/时间/任务失败/切换/安全介入。
资源数据包含全host活动，不冒充独占进程归因。
原生门禁与独立离线审计分开；每次尝试追加 [log.md](log.md)，选定原件归档后提供用户验收。

技术依据：[MaskablePPO官方接口](https://sb3-contrib.readthedocs.io/en/master/modules/ppo_mask.html)、
[SB3特征编码器](https://stable-baselines3.readthedocs.io/en/master/guide/custom_policy.html)、
[Gymnasium终止/截断](https://gymnasium.farama.org/tutorials/gymnasium_basics/handling_time_limits/)。
