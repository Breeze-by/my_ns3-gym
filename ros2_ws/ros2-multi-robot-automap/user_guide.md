# 三机器人 ROS 建图导航：当前实现指南

代码核对：2026-10-15，MR3-P1A用户已验收，P1B理想适配验证中；`c9344e1`是历史工程冻结。
新研究契约在 [RESEARCH_PLAN.md](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md)，步骤在
[IMPLEMENTATION_PLAN.md](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/IMPLEMENTATION_PLAN.md)。MR3-P0/P1A已验收，P1C及后续未开始。
默认仍为**传统前沿控制器**；新增互斥的理想策略适配模式，没有导航RL模型、训练环境或通信gateway。
复制运行统一使用 [launch_commands.md](launch_commands.md)，其中全部显式传三台。

## 1. 路径与环境

唯一工作目录：`/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap`。
它是 `Breeze-by/my_ns3-gym` monorepo 的 subtree，不是独立 Git 仓库或 submodule。
旧 `/home/zhuyulab/ros2_ws/` 检出/链接已删除，不使用旧 ros2_humble/multi_robot_autonomous 路径。
从 Git 根提交和推送；ROS 用系统 Python/Humble，学习端 conda 单独进程。

## 2. 当前包与主启动链

| 当前路径 | 职责 |
| --- | --- |
| `src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py` | world、spawn、Nav2、SLAM、融合、就绪、peer、控制、可选评估与关闭 |
| `src/multi_robot/worlds/` | my_world、p1c_open、p1c_rooms、p1c_corridors，均为已知开发场景 |
| `src/multi_robot/models/turtlebot3_waffle/model.sdf` | 真实差速机体/激光/IMU/接触/轮 joint_states；深度相机未启用 |
| `src/slam_toolbox/` | 本机 SLAM 与 map→odom，不以 AMCL 代替本机建图定位 |
| `src/merge_map/merge_map/merge_map.py` | 保守公共 frame 栅格融合 |
| `src/multi_robot_exploration/multi_robot_exploration/control.py` | 当前手工前沿策略与 Nav2 action 所有权 |
| 同包 `nav2_ready_gate.py` / `peer_obstacles.py` / `task_evaluator.py` | 六节点就绪、队友机体输入、隔离任务评估与就绪/停止握手 |
| `mr3_adapter.py` / `mr3_observation.py` / `mr3_protocol.py` | 显式联合动作、几何候选/掩码、稳定目标所有权 |
| `mr3_information.py` / `mr3_transport.py` | 理想交付、后端图和机器人导航图副本；非DDS隔离 |
| `scripts/ros_smoke_test.py` / `run_ideal_baseline.py` / `run_mr3_adapter_probe.py` | 传统检查/矩阵和P1B脚本适配探针 |

主 launch 默认3台，校验保留1–4历史兼容；MR3合同只允许三台，不开展其他数量实验。
当前出生位 tb1=(0,-.45)、tb2=(0,.45)、tb3=(.45,0)，不是旧手册中分散四台的样例。
Nav2 action和各节点数量来自同一个校验后的 robot_count；不通过注释列表启停机器人。
MR3合同和新schema4的原生证据在P1A报告，不能沿用旧90%成绩。

## 3. 当前数据流与可复用边界

每台本机 Gazebo 发布 `/tbN/scan`、`odom`、`imu`、`joint_states`、`collision`；
本机 robot_state_publisher/SLAM 发布 namespaced TF 与 `/tbN/map`。
Nav2 发布 `/tbN/cmd_vel`，差速插件消费速度。`cmd_vel` 不是机器人测得的真实速度。
当前三台 SLAM 地图融合为 `/merge_map`，公共 frame 为 `map`。

手工控制器用融合图及每台观测位姿计算前沿、可达路径/信息增益、历史效用，分配
观察目标、分段到达，并通过 `/tbN/navigate_to_pose` 执行。
Nav2 使用相同实时融合图的 static layer，Smac2D 全局规划和非滚动全局代价图；本地
激光/DWB 负责局部障碍。它不是分散式探索 RL。

地图融合按原点/分辨率处理已知区域与占据冲突，保守优先保留障碍；拒绝不兼容的 frame、
分辨率或旋转方向。共同初始坐标系是已知条件，不宣称实现任意初始相对位姿的地图配准。

peer 组件观察所有机器人的 odom/TF，把队友完整机体包络作为 PointCloud2 发布到
`/tbN/peer_footprints`；全无限量程 LaserScan `/tbN/peer_obstacles` 清理该独立
peer_layer 的旧位置，其他真实障碍层以 max 保留。它不改 SLAM 地图、不发送目标、
不读 Gazebo 真值。任务期间源龄失效会锁存 `/exploration_failure`，阻止派发并取消目标。

网络研究时，本机传感/SLAM/Nav2可继续本地实时工作，但远端融合图、队友位姿、目标和
回执必须遵守真实交付边界。当前这些共享输入仍是实时 ROS 旁路，不能宣称已受 Wi-Fi
影响。adapter模式已通过理想received存储和navigation_map明确逻辑交付边界；
独立action proxy、完整字节及DDS隔离仍属P3A，不能把理想对象交付称为Wi-Fi。

## 4. 关键当前参数（不是未来 RL 默认值）

| 参数 | 源码默认 | 当前含义 |
| --- | --- | --- |
| `robot_count` | 3 | 保留1–4兼容；MR3合同只允许3 |
| `world` / `gazebo_seed` | my_world.world / 1 | 正式运行显式记录场景、seed |
| `use_sim_time` | true | ROS 使用 Gazebo /clock |
| `enable_drive` | false | 保持关闭，避免重复速度所有权 |
| `enable_gzclient` | true | Gazebo GUI；训练/评估 headless 更合适 |
| `enable_rviz` / `enable_merge_rviz` | false / true | 每台RViz与全局RViz分别控制 |
| `auto_save_map` | true | 正式自动检查关闭，避免不必要保存负载 |
| `spawn_timeout` / `nav2_ready_timeout_sec` | 90 / 300秒 | 启动墙钟保护；六个生命周期及action均需就绪 |
| `exploration_goal_timeout_sec` | 60秒 | 当前目标执行仿真时间上限 |
| `navigation_response_timeout_sec` / `navigation_cancel_timeout_sec` | 10 / 10秒 | 当前 action 接受与取消终态期限 |
| `enable_task_evaluator` | false | 隔离任务评价；schema4与控制器进行任务握手 |
| `evaluation_duration_sec` / `evaluation_coverage_threshold` | 0 / 0 | 需显式设置；0分别表示无有限期限/无覆盖成功终止 |
| `evaluation_contract_path` | 空 | 非空启用MR3 schema4合同，固定95%/300仿真秒；空保留schema3 |
| `stop_on_evaluation_complete` | true | evaluator 退出后有界关闭父 launch 和所属进程 |

标准演示、legacy90%诊断与MR3合同95%检查统一在启动命令页维护，不复制旧二台、四台或过时 fixed sleep。
脚本适配、参数调整会与命令页同提交更新；训练/gateway CLI 在实现验收后才添加。

## 5. 评估器语义与证据限制

评估器不选择探索目标，不发布Nav2导航目标或底盘速度。schema4发布监测就绪与停止请求，
由控制器统一放行、停止派发并取消目标，评估器等待所有权终态闭合。Gazebo
`/gazebo/model_states` 仅给评估真值路径/指标，不进入探索目标选择。
legacy schema3由SDF静态box碰撞在.2m切片生成.05m真值格，应用world state位姿；不支持的几何计数保留。
当前 my_world 有实验室外的SUV mesh限制。估计融合图采样到相同坐标，报告正确自由
覆盖、known覆盖、accuracy和occupied IoU。分母为外接矩形全部真值自由格，尚无独立
任务 ROI/可见性 mask，故不能推导95%一定可达，MR3-P1A先闭合测量定义。

以上为legacy schema3口径。P1A新增schema4严格合同：三开发图完整外墙ROI、.05m正面积
相交真值、.131m名义ray切片、质量/参与/持续监测与终态闭合门禁；保存旧口径对照。
六个真实碰撞体现在各有接触源，18源的源龄/接收龄/中断锁存独立检查，精确过滤正常
轮/脚轮—地面支撑接触。任务从 `/exploration_start` 放行计时，达标后等目标取消终态。
具体合同、开发/留出划分与验收口径见
[任务契约](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_TASK_CONTRACT.md)。

隔离接触夹具v8在冻结`3f24eaa`通过：tb1六部件的真实非支撑接触正例，以及三台共18路
空消息、正常支撑、持续新鲜度和消息序列完整性。沉降窗口后的扫描原点实测约.12925m
（三台.12924–.12926m），与.131m名义值的误差小于2mm；10m光束包络及窗口变化余量
也通过声明的切片/地面检查。详见[夹具原件](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/fixture_v8_pass_result.json)。
这是传感/监测与沉降姿态证据，不代表三台每部件都做过接触正例或95%建图任务已通过。

schema3 成功必须在截止前覆盖达标、接触 topic 记录为零、每台碰撞监测有消息且无控制失败；
schema3只读基体topic，不能证明全机体无非支撑接触；“有消息”也不等于持续新鲜度证明。
P1A合同模式另作完整检查。CSV/JSON原子发布、拒绝覆盖同id。
评估完成默认关闭本轮；父launch退出0不掩盖原生子进程异常。
`trajectory_overlap_ratio` 与旧 `search_overlap_ratio` 是相同中心轨迹格重叠，
不是重复激光覆盖/建图面积。95%时间字段存在，不等于已经达到95%。

历史 [c9344e1工程证据](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261013_p1c_engineering_repair.md)：
三台rooms/corridors、seed101、90%/180秒，60.2/81.9仿真秒达标，基体接触记录为零、干净退出。
旧September多种子P1C/schema2成绩属于旧源码。73组件检查的PASS也不等于MR3整任务。
冻结`5e47802`累计10次尝试含1次保留的原生基础设施失败，得到9个有效单元；完整结果见
[P1A报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_p1a.md)。
P1A已于2026-10-15由用户验收，P1B适配验证中；这些仍是传统开发基线证据，没有导航RL/通信成绩。

## 6. 诊断原则

- 就绪超时：查指定机器人的全部六个 lifecycle、action、TF/map frame 与消息，不能
  加固定两分钟等待或静默减成两台。
- 规划失败：查全局地图是否到达、目标在已知空间的机体可达性、TF时间和窄门；不能
  清空真实障碍或把未知空间改成真值自由空间。
- DWB无有效轨迹：查局部scan、peer包络、机体形状和观测源龄；保留碰撞/失败原件。
- missed rate/采样慢：先看CPU、仿真倍率、GUI、SLAM/Nav2负载，不把4090数量当采样速度。
- 关闭挂起/原生abort：保留每个子进程退出记录，仅清理本轮进程组，不无范围pkill。
- FastDDS响应超时：见命令页官方shm清理；换新run-id复测，不能删除失败或断言普遍修复。
- 版本切换：检查安装路径与旧缓存，在新终端从Humble underlay重建，不复制旧build/install。

新研究的验收次序、RL方法/奖励、gateway无旁路和时钟规则都在共享研究/实施计划。
本文只说明当前实现；历史或上游README的任务步骤不作为当前路线指令。
