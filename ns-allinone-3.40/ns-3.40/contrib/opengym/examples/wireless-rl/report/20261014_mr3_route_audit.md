# 2026-10-14 MR3 路线审计与方法依据

类型：代码阅读、文献调研与文档规划，**无新增仿真、训练或性能结果**。
代码审计基点：`81b2f8b9c2a36f0a8c5278e04fae66dc06859180`；该点运行源码与
`c9344e10f4a0788f96fd70371c5ea033e0fc5268` 相同。
研究契约见 [RESEARCH_PLAN.md](../RESEARCH_PLAN.md)，状态见
[IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md)。新路线 MR3-P0 待用户验收。

## 用户方向的具体化

固定三机器人，先用一个 RL 网络联合选择探索动作，保留融合与导航能力；理想通信下
达到可靠的 95% 联合建图，再冻结策略并用 ns-3 Wi-Fi 承载真实上下行数据。
本轮路线终点是该冻结策略的网络影响测量；通信优化和实机部署以后另定。

这是集中式 RL 全局规划问题，不能因为有三台机器人就默认改成分散 MAPPO。
首版采用稳定的目标选择而非直接速度：学习的是协同探索决策，Nav2 执行运动。
维护 action 接受/取消/终态的协议状态是必要工程能力，不是继续用手写策略决定探索。
下面的方案和参数是本项目的工程判断，**不是文献已证明本项目有效**。

## 当前代码审计

ROS 源码路径均相对于
`/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap`。

| 文件/模块 | 阅读到的事实 | 路线要求与处理时机 |
| --- | --- | --- |
| `src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py` | 主 launch 默认数量 2，校验 1–4；SLAM/导航/融合/peer/evaluator 同数量；自动评估退出 | 文档当前命令显式传 3；P1A 再改活动默认和验证矩阵，不假称源码已三台专用 |
| `src/multi_robot_exploration/multi_robot_exploration/control.py` | 根据融合图的前沿、路径、信息增益和历史人工评分分配目标，分段导航与失败处理 | RL 模式替换评分与重派；P1B 隔离纯几何/导航协议能力，旧控制保留为互斥基线 |
| `src/merge_map/merge_map/merge_map.py` | 对齐公共 frame 栅格，保守占据冲突、处理分数原点；拒绝不兼容地图 | 复用融合核心；不是任意相对位姿配准；P3A 后只融合交付的机器人地图 |
| `src/multi_robot/params/nav2_params_tb1_0.yaml` 至 `tb3` | 全局 static layer 直接读 `/merge_map`，Smac2D、非滚动全局图 | 如果只让 RL 输入受网影响，Nav2 仍持有即时全局图；P1B 定义副本，P3A 消除此旁路 |
| `src/multi_robot_exploration/multi_robot_exploration/peer_obstacles.py` | 直接读每台 odom/TF；队友完整机体包络进入独立 peer_layer；不进 SLAM | 跨机器人安全信息也要交付；不能接网后借 raw 全体位姿维持即时安全 |
| 同上 | 机体半径 .25m、安全 margin .04m，速度界 .26m/s，反应 .55s，数据失效 .5s；任务期失效锁存 `/exploration_failure` | 网络陈旧可能导致停止而不是碰撞；P1B/P3A 验证陈旧/租约策略，保留真实安全条件，不直接放宽门限 |
| `task_evaluator.py:load_truth_grid` | 静态 SDF box collision、saved world state、.05m 栅格、.2m 切片；mesh 等存在未支持情况 | P1A 审计可测任务区域和几何；当前未声明 ROI/可见性 mask |
| `task_evaluator.py:compare_occupancy_grid` | 分母是外接矩形内所有真值自由格；估计图投到同一真值格；并非“已探索格占当前地图的95%” | 存在区域定义风险，不能从90%推导95%可达；P1A 冻结任务分母，禁止事后缩小 |
| evaluator 的成功门禁 | schema3 截止优先、零接触、collision monitor message_count>0、无控制失败 | message_count 不是持续新鲜度；P1A 验证整任务有效监测；不改旧原件为新 schema 成绩 |
| evaluator 重叠字段 | `trajectory_overlap_ratio` 与 `search_overlap_ratio` 同值，是机器人中心轨迹格重复 | 不能拿它当重复扫描/建图面积，需另定义传感可见统计 |
| `scripts/ros_smoke_test.py` 与 `run_ideal_baseline.py` | 基础设施/任务结论分开，检查原生子进程，有界关闭与非零失败返回 | 复用自动化结构，三台固定；训练 reset 必须隔离进程、地图与动作状态 |
| `wireless-rl/sim.cc`、`train_dqn.py` 等 | 独立五用户 toy 调度环境，CQI/backlog age reward，非 ROS 导航和非真实 Wi-Fi 分组 | 保留历史工具链；不能复用其 observation/action/checkpoint 当新策略 |

### 能复用什么，不能直接称已经完成什么

SLAM、公共坐标系地图融合、Nav2、传感器、碰撞原件和自动评估基础可复用。
深度相机目前未启用；首版用已有激光地图，不预设新增 RGB/语义模型。
旧预建图 AMCL 入口和旧位置样例不是新路线的定位条件；以当前 SLAM/TF 为准。

最新三台 rooms/corridors seed101 工程任务分别 60.2/81.9 仿真秒达到90%，零接触、自动
干净退出；共73组件检查无错误/失败、2跳过。它们仅说明修复基线可用。
95% 三台 my_world、跨布局/多种子 RL、训练 reset、gateway、Wi-Fi 任务均未验证。
具体成功和所有先前失败只引用 [工程报告](20261013_p1c_engineering_repair.md)，不复制旧
September 的最好单格作为最新源码成绩。

## 关键方案选择与替代方案

### 1. 选择学习子目标，而非从底盘速度开始

地图→联合稳定目标→Nav2 符合当前系统可复用边界，也便于区分探索策略与局部控制。
NeuralCoMapping 的机器人—前沿关系学习，比无约束目标坐标回归更贴近当前前沿导航框架。
本项目首版只采用该思想，先用小 CNN/MLP 联合类别输出，不直接引入完整 mGNN/Sinkhorn。

候选 K=8，加 KEEP/WAIT，联合动作1000类，对固定三台可直接使用 masked Discrete
PPO 和同接口 DQN。这样避免 MultiDiscrete 的独立头难以表达联合目标冲突，也避免为
仅三台过早实现自回归采样/分布。候选池按空间几何代表性而不是手工效用排名产生，
K 的损失/截断和所有掩码均需在 P1B 可观测；无合法目标时网络可 WAIT，不触发旧 planner。

连续 SAC/TD3 可以学局部子目标偏移，但会增加未知区域/可行性投影等区别，不作为
算法纯对照；直接速度还需要局部雷达、高频差速动作、独占 cmd_vel 与更强采样工程。
DDPG 和 MAPPO 保留文献定位，不要求机械跑遍算法名字。

### 2. 决策同步不等于机器人动作必须同步

三台可在同一1秒观测快照联合决策，但各自 Nav2 目标异步执行，未到换目标条件的
机器人输出 KEEP。不能每个训练 step 都强制取消三台，也不能等待最慢机器人完成
再允许任何台选择下一个目标。ACE 的工作提醒动作时长和异步执行会改变效率定义。

首版固定策略步长便于复用库；奖励的时间项按仿真 dt。若以后事件驱动，则必须验证
SMDP 折扣/优势，不能直接把变时长轨迹喂固定 gamma 的 PPO。
任务目标是仿真任务 T95，不是动作数，也不是墙钟 GPU 算得快。

### 3. 覆盖、质量、安全必须在训练之前定义

无 ROI 的 truth_free 分母以及 unsupported geometry 是当前95%任务定义的主要风险，
尚不能凭代码断言某张图95%一定不可达。先做几何/可达/可见诊断与原生任务证据。
主要自由格覆盖之外，错误自由标记、occupied IoU、接触和监测源龄共同防止把墙画成
自由空间或停掉安全传感器来得到漂亮覆盖率。

奖励隔离真值、首次正确格去重、有限截止含剩余时间；成功以当前地图而非累计奖励为准。
T_max=300、周期1s、承诺5s、K8 是预先给出的工程起点，不是已验收门限。
P1A/P1B 锁定后，正式测试不能逐格改预算或目标接口。

### 4. 不夸大双 4090 的采样收益

网络反向传播可以用 CUDA，SLAM/Nav2/Gazebo 与 reset 多半需要 CPU/进程吞吐量测。
先测每个三机器人 worker 的有效 transition 和真实资源，再定并发/总样本预算。
快速二维预训练仅在实测需要时启用，真实 ROS/Gazebo 正式测试不可替代。
并行 worker 与独立训练 seed 是两种概念，不把多环境采样当作多次独立训练。

### 5. 冻结策略接网需要冻结“整套接口”，不只一个 pt 文件

输入年龄/缺失、发送频率、观测尺度、候选/掩码、KEEP/租约、导航地图副本及 peer 信息规则必须
从理想阶段就存在。冻结权重、归一化和执行参数后，网络只改变应用信息何时能交付。

当前三条明显旁路是：后端 raw 状态/地图订阅；每台 Nav2 直接读实时融合图；peer
组件直接读全部队友位姿。导航回执/取消 Future 还有隐性下行/上行通道。
因此 gateway 必须是双向、包含共享导航图和队友状态的真实字节交付边界。
只在 RL 输入前加 sleep，或只传 dummy Packet 后取实时 ROS 内容，不算 ns-3 接入。

本地本机 SLAM 和激光仍实时，属于正确的机器人自治。评估器的完整本地图副本只用于
C_physical 因果诊断，后端不能读；Gazebo 真值给无线传播位置也不能“补新”后端状态。

### 6. 接网的两个独立困难：数据因果与仿真时钟

序列化、分片、地图版本、目标幂等与 TTL 的错误，会混入网络退化结论；先做断链和
确定性故障夹具，再跑真实 Wi-Fi。目标稳定和本地安全可能使受限网络主要表现为
停顿/超时而非碰撞，不能规定实验一定出现碰撞或显著变慢。

ns-3 自己的事件钟与 ROS `/clock` 不天然同步。其 RealTime scheduler 对齐墙钟，
当前 Gazebo 可变仿真倍率下不能不加验证就用于因果任务比较。
优先验证物理多步/事件分段屏障，量化 ROS 回调与耦合量子误差；实现困难是独立门禁，
不在文档中声称已经有 Gazebo/ns-3 lockstep 服务。

## 参考文献与核查结论

核查日期：2026-10-14。以下为直接论文、作者项目或官方工具文档；这些结论用于设计，
不是对本项目的性能背书。范围是相关方法与工程契约调研，不声称穷尽全部文献。

| 来源 | 核查内容 | 对本项目的启发/限制 |
| --- | --- | --- |
| [Active Neural SLAM，ICLR 2020](https://www.cs.cmu.edu/afs/cs/user/dchaplot/www/projects/neural-slam.html)；[论文](https://arxiv.org/abs/2004.05155) | 学习全局目标与规划模块分层 | 复用经典 SLAM/Nav2；不是照搬其 RGB 学习式 SLAM；出版为 ICLR2020 |
| [NeuralCoMapping，CVPR2022](https://arxiv.org/abs/2203.16319)；[全文](https://arxiv.org/html/2203.16319v1) | 学习机器人/前沿关联，以地图覆盖增量和时间项训练全局策略，规划周期内保留目标 | 最接近联合主动建图；不继承它的传感器、碰撞表现、带宽与完成时间 |
| [PPO](https://arxiv.org/abs/1707.06347) | on-policy clipped surrogate 更新 | 主线易与合法动作掩码结合；不保证三机器人最优或最省样本 |
| [Invalid Action Masking](https://arxiv.org/abs/2006.14171) | 策略梯度中合法动作掩码的方法依据 | 保存同一快照的掩码，评估也必须一致；掩码不能充当手工策略 |
| [MaskablePPO 官方文档](https://sb3-contrib.readthedocs.io/en/master/modules/ppo_mask.html) | Discrete/Dict/并行支持；无直接 recurrent 支持；专用评估入口 | 首版 joint Discrete 和前馈编码可复用；worker 内实现 mask；版本在实施时锁定 |
| [DQN](https://arxiv.org/abs/1312.5602) | 离散动作值学习 | 做同接口对照；旧 toy checkpoint 维度与语义均不适用 |
| [DDPG](https://arxiv.org/abs/1509.02971) | 连续动作 deterministic actor-critic | 可理解用户举例，但不是首轮必须追加的算法 |
| [TD3](https://arxiv.org/abs/1802.09477) | 双 critic/延迟策略更新处理 actor-critic 估计误差 | 连续目标接口有需要时考虑，不预言胜出 |
| [SAC](https://arxiv.org/abs/1801.01290) | off-policy、最大熵随机 actor 的连续控制 | 样本复用候选；连续接口比较不能声称只换算法 |
| [MAPPO，NeurIPS2022 D&B](https://arxiv.org/abs/2103.01955) | PPO 在合作多智能体基准上的强基线 | 集中式三台联合 actor 不自动叫 MAPPO；不据游戏结果宣称机器人性能 |
| [ACE，AAMAS2023](https://arxiv.org/abs/2301.03398)；[作者项目](https://sites.google.com/view/ace-aamas) | 异步决策和动作延迟影响真实探索时间 | 保留异步 Nav2 目标；不在理想阶段提前加入网络适应训练改变研究顺序 |
| [Gymnasium 时间限制](https://gymnasium.farama.org/tutorials/gymnasium_basics/handling_time_limits/) | 有限任务终止与外部截断的 bootstrap 不同 | 明确 T_max 属于任务失败，观测剩余时间；训练采样截断另外处理 |
| [Statistical Precipice，NeurIPS2021](https://arxiv.org/abs/2108.13264) | 少量独立 run 的区间估计与稳健统计 | 多训练 seed、未见布局、失败计入、配对区间；不能挑最好单曲线 |
| [ns3-gym 原论文](https://arxiv.org/abs/1810.03943)；[官方发布](https://www.nsnam.org/news/2018/12/07/ns3-gym-app.html) | 为 ns-3 提供 Gym 交互框架 | 现有工具链经验可用，不自动提供 ROS gateway 或 Wi-Fi 数据交付 |
| [ns-3 RealTime 官方手册](https://www.nsnam.org/docs/manual/html/realtime.html) | 对齐外部墙钟，存在 BestEffort/HardLimit 行为 | 不等同于与 Gazebo `/clock` 锁步；用本地3.40源码核对版本 |
| [Nav2 Humble NavigateToPose](https://api.nav2.org/actions/humble/navigatetopose.html) | PoseStamped 目标和异步导航反馈 | 子目标接口复用，跨网络 action proxy 保留接受/取消/终态所有权 |

NeuralCoMapping 全文有一处把 PPO 称作 off-policy；本计划依 PPO 原论文将其归类为
on-policy，不继承该表述。其报告的跨机器人数量泛化不属于本项目的固定三台要求。

本地 ns-3.40 精确模型依据还包括
[Wi-Fi 模型说明](../../../../../src/wifi/doc/source/wifi-design.rst)、
[Wi-Fi 使用说明](../../../../../src/wifi/doc/source/wifi-user.rst) 和
[RealTime 手册源文件](../../../../../doc/manual/source/realtime.rst)。
本轮访问发布版网站的部分3.40 Wi-Fi页面失败，因此版本相关实现以仓库原始文档与源码
为准，不拿其他旧版网页默认参数冒充3.40。上述阅读不代表已构建或运行新 Wi-Fi 场景。

## 文档去冲突与保留策略

活动入口统一使用 MR3；旧计划/旧技术手册全文通过切换前 Git 对象与
[ARCHIVE_INDEX.json](ARCHIVE_INDEX.json) 可恢复。报告原有数据与 assets 不删除，
每份历史报告添加适用范围提示，原始内容 SHA256 在索引保留；工程修复报告继续是
当前传统基线的事实依据。shared log 原文不重写，只追加路线切换记录。

保留 `main` 与 `p2c1/global-mission-20261012` 两条分支；不修改原路线备份。
不建立额外分支、不重写历史。未来 AI 先读新计划/检查点/AGENTS，再按报告索引查证，
不能从历史报告的“下一步”或旧 toy 指南发起目标检测、充电、集合或通信调度研究。

## 本轮文档验证（不产生实验信用）

检查本地链接、Markdown代码围栏、当前命令的bash语法（不执行）、launch/CLI参数
与三台数量、12个MR3步骤/未开始状态；校验24份切换前Git对象哈希、10份原报告正文、
历史log条目保留和原路线备份不变。校验产物见
[document_checks.json](assets/20261014_mr3_route_audit/document_checks.json)。
初次CLI检查器误把同一代码块的两条命令参数合并；修正检查器后通过，无需修改项目接口。
追加附录时一次临时写入命令遇到heredoc分隔符冲突，已修正并重新静态核对范围。
本轮未运行Gazebo/ns-3、训练或性能评估。后续源码改变后，此P0静态检查不充当功能测试。

下面保留本轮只读核对脚本，便于从报告恢复临时文件并复核；脚本只写本报告验证receipt，
不修改运行源码，不启动模拟器。复现命令（从Git根执行）：

```bash
rtk proxy python3 - <<'PY'
from pathlib import Path
report = Path('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_route_audit.md').read_text()
code = report.split('<!-- MR3_DOCUMENT_CHECK_BEGIN -->\n```python\n', 1)[1].split('\n```', 1)[0] + '\n'
Path('/tmp/mr3_document_check.py').write_text(code)
PY
rtk proxy python3 /tmp/mr3_document_check.py
```

<!-- MR3_DOCUMENT_CHECK_BEGIN -->
```python
from pathlib import Path
import ast, datetime, hashlib, json, re, subprocess

root = Path('/home/zhuyulab/ns3-workspace')
b = root/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ros = root/'ros2_ws/ros2-multi-robot-automap'
receipt = b/'report/assets/20261014_mr3_route_audit/document_checks.json'
pre = '81b2f8b9c2a36f0a8c5278e04fae66dc06859180'
backup = '8fe1495b6624cd9136f3ce160acaa274428e54ae'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=root)

def sha(data):
    return hashlib.sha256(data).hexdigest()

changed = set(git('diff', pre, '--name-only').decode().splitlines())
changed |= set(git('ls-files', '--others', '--exclude-standard').decode().splitlines())
receipt_rel = str(receipt.relative_to(root))
changed.add(receipt_rel)
allowed_json = {str((b/'report/ARCHIVE_INDEX.json').relative_to(root)), receipt_rel}
assert all(p.endswith('.md') or p in allowed_json for p in changed), changed
assert not any('/report/assets/' in p and p != receipt_rel for p in changed)

local_links = 0
markdown_count = 0
for rel in sorted(changed):
    p = root/rel
    if p.suffix != '.md':
        continue
    markdown_count += 1
    text = p.read_text()
    assert len(re.findall(r'^```(?:[A-Za-z0-9_+-]+)?[ \t]*$', text, re.M)) % 2 == 0, rel
    for target in re.findall(r'(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)', text):
        if '://' in target or target.startswith('#'):
            continue
        target = target.split('#')[0].strip('<>')
        if not target:
            continue
        resolved = Path(target) if target.startswith('/') else p.parent/target
        assert resolved.exists(), (rel, target)
        local_links += 1

idx = json.loads((b/'report/ARCHIVE_INDEX.json').read_text())
assert idx['pre_route_commit'] == pre
assert idx['original_route_backup']['commit'] == backup
assert git('rev-parse', 'p2c1/global-mission-20261012').decode().strip() == backup
assert git('rev-parse', 'origin/p2c1/global-mission-20261012').decode().strip() == backup
assert set(git('for-each-ref','--format=%(refname:short)','refs/heads').decode().splitlines()) == {'main', 'p2c1/global-mission-20261012'}
report_bodies = 0
for item in idx['files']:
    original = git('show', pre+':'+item['path'])
    assert sha(original) == item['sha256'], item['path']
    current = (root/item['path']).read_bytes()
    if '/report/' in item['path']:
        assert current.split(b'\n\n',1)[1] == original, item['path']
        report_bodies += 1
    if item['path'].endswith('/log.md'):
        marker = b'## Logging rule\n'
        assert current[current.index(marker):].startswith(original[original.index(marker):])

plan = (b/'IMPLEMENTATION_PLAN.md').read_text()
expected = ['MR3-P0','MR3-P1A','MR3-P1B','MR3-P1C','MR3-P2A','MR3-P2B','MR3-P2C','MR3-P3A','MR3-P3B','MR3-P4A','MR3-P4B','MR3-P5']
assert re.findall(r'^### (MR3-P\w+)[：:]',plan,re.M) == expected
for checkpoint in expected[1:]:
    assert re.search(r'\| '+checkpoint+r' \|[^\n]+\| 未开始 \|',plan)
assert re.search(r'\| MR3-P0 \|[^\n]+\| 文档已交付，待用户验收 \|',plan)

launch_src = ros/'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py'
tree = ast.parse(launch_src.read_text())
launch_args = set()
robot_default = None
for node in ast.walk(tree):
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='DeclareLaunchArgument' and node.args and isinstance(node.args[0],ast.Constant):
        name = node.args[0].value
        launch_args.add(name)
        if name=='robot_count':
            robot_default = next(kw.value.value for kw in node.keywords if kw.arg=='default_value')
launch_args |= {'navigation_response_timeout_sec','navigation_cancel_timeout_sec'}
assert robot_default == '2', robot_default
cmds = (ros/'launch_commands.md').read_text()
used_args = set(re.findall(r'\b([a-z][a-z0-9_]*):=',cmds))
assert used_args <= launch_args, used_args-launch_args
robot_values = re.findall(r'\brobot_count:=(\d+)',cmds)
assert robot_values and set(robot_values)=={'3'}
assert re.findall(r'--robot-count\s+(\d+)',cmds)==['3','3']

def declared_cli(name):
    tree = ast.parse((ros/'scripts'/name).read_text())
    return {arg.value for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='add_argument' for arg in n.args if isinstance(arg,ast.Constant) and isinstance(arg.value,str) and arg.value.startswith('--')}
blocks = re.findall(r'```bash\n(.*?)```',cmds,re.S)
checked_shell = 0
for block in blocks:
    result = subprocess.run(['bash','-n'],input=block,text=True,capture_output=True)
    assert result.returncode == 0, result.stderr
    checked_shell += 1
    for name in ['ros_smoke_test.py','run_ideal_baseline.py']:
        if name in block:
            tail = block.split('scripts/'+name,1)[1].split('\n\n',1)[0]
            flags = set(re.findall(r'--[a-z][a-z-]+',tail))
            assert flags <= declared_cli(name), (name, flags-declared_cli(name))

hashes = {rel: sha((root/rel).read_bytes()) for rel in sorted(changed) if rel != receipt_rel}
result = {
    'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'type':'documentation_static_validation_not_a_simulator_or_training_experiment',
    'pre_route_commit':pre,
    'runtime_source_unchanged_from':'c9344e10f4a0788f96fd70371c5ea033e0fc5268',
    'command':'rtk proxy python3 /tmp/mr3_document_check.py',
    'checker_sha256':sha(Path(__file__).read_bytes()),
    'checks':{
        'documentation_only_scope':True,'runtime_config_weights_and_original_assets_unchanged':True,
        'local_markdown_links':local_links,'markdown_files':markdown_count,
        'balanced_fences':True,'archival_git_object_hashes':len(idx['files']),
        'original_report_bodies_unchanged':report_bodies,'historical_log_entries_unchanged':True,
        'mr3_checkpoints_and_pending_acceptance':len(expected),
        'bash_blocks_syntax_only_not_executed':checked_shell,
        'launch_and_cli_flags_match_source':True,'recommended_robot_counts_exactly_three':True,
        'source_launch_default_still_two_documented_honestly':True,
        'original_route_backup_unchanged_and_two_local_branches':True
    },
    'file_sha256':hashes,
    'simulator_runs':0,'training_runs':0,'new_task_performance_claims':0,
    'result':'PASS'
}
receipt.parent.mkdir(parents=True,exist_ok=True)
receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='file_sha256'},ensure_ascii=False,indent=2))
```
