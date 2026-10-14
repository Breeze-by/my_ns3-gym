# 当前 ROS 技术参考与边界

2026-10-14，P1A实施/验证中；`81b2f8b`/`c9344e1`是历史审计/工程冻结。
本文件取代旧分散四台/旧 ros2_humble 路径/过时行号样例；原文可从
[归档索引](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/ARCHIVE_INDEX.json)所列Git对象恢复。
研究路线读 [RESEARCH_PLAN.md](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md)，运行读
[launch_commands.md](launch_commands.md)，概览读 [user_guide.md](user_guide.md)。
以下是当前实际实现；RL/gateway 均未实现。

## 当前源码位置

均相对于 `/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap`：

| 组件 | 源码路径 |
| --- | --- |
| 主建图启动 | `src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py` |
| Nav2 bringup | `src/multi_robot/launch/nav2_bringup/`，配置`src/multi_robot/params/nav2_params_tb1_0.yaml`至tb3 |
| SLAM多机启动 | `src/slam_toolbox/launch/online_async_multirobot_launch.py` |
| 融合 | `src/merge_map/merge_map/merge_map.py` |
| 手工探索 | `src/multi_robot_exploration/multi_robot_exploration/control.py` |
| 就绪/peer/评价 | 同包`nav2_ready_gate.py`、`peer_obstacles.py`、`task_evaluator.py` |
| 模型/世界 | `src/multi_robot/models/turtlebot3_waffle/model.sdf`、`src/multi_robot/worlds/` |
| 运行工具 | `scripts/ros_smoke_test.py`、`scripts/run_ideal_baseline.py` |

## 当前坐标、地图与运动契约

namespaced `/tbN/tf` 和 `/tbN/tf_static`；SLAM估计map→odom，本机odom→base由
底盘/机器人TF链提供。控制器转换观测位姿到公共map，不能把odom数值当map数值。
同一公共初始坐标系是仿真条件，融合不是特征注册/未知坐标系定位。

融合地图frame `map`，发布`/merge_map`；占据冲突保守，分数原点按栅格对齐，拒绝
不兼容frame/分辨率/旋转。三台全局static layer直接用实时融合图；全局图非滚动，
Smac2D规划，本机激光/DWB执行差速速度。模型不支持自由侧移。

`NavigateToPose` 的目标是公共frame下的PoseStamped。当前控制器仍有人工前沿
目标分配/分段/重试；60秒执行、10秒接受/取消期限。待响应/待取消时保留唯一所有权，
握手失效显式`/exploration_failure`，不能无限等待或叠发目标。

## Peer层与真实监测

`peer_obstacles` 观察raw全体odom/TF；机体半径.25m、margin .04m、速度界.26m/s、
反应.55s、最大观测源龄.5s。PointCloud2填充完整包络，清除LaserScan仅清理独立
peer_layer；其他障碍max合并，虚拟peer不进SLAM。它不使用Gazebo真值。
这是理想通信安全输入，后续必须受已交付跨机信息边界约束。

P1A为六个真实碰撞体增加独立20Hz接触源；legacy schema3仍只读基体topic，不能用其
历史零记录证明全机体无碰撞。schema4核查18源持续新鲜度，只精确排除正常轮/脚轮地面
支撑接触；原生覆盖和新鲜度证据以P1A报告为准。
合同模式经C++ `mr3_contact_reducer`逐消息汇总同一碰撞对，原header及首次完整
ContactState几何保留，原18路不变；Python只采用汇总代表样本计数。原发布端与
汇总节点使用reliable/volatile、KEEP_LAST depth100；20Hz和.5秒监测门限不变。
publication sequence缺口/重复/倒退、审计能力缺失或多发布者使任务失败；smoke在
全部原生子进程退出后核查18路完整汇总，不将parent返回0或原生JSON成功单独作PASS。
joint_state插件给真实轮关节；默认建图不再重复启动
虚构零轮位姿的joint_state_publisher。评估器读取真值路径/接触/地图，不选择探索目标、
不发布导航目标或速度；schema4发布任务就绪/停止请求，并等待控制器取消终态闭合。
成功门禁与分母限制见使用指南；监测曾有一条消息不证明整段新鲜。

`.131m`为合同的名义ray切片。隔离夹具v8沉降后的三台扫描原点实测.12924–.12926m，
通过2mm误差及带窗口变化余量的10m光束包络检查。六部件真实接触正例只在tb1执行，
三台18路的空消息、正常支撑、源龄和消息完整性另行全量核查；夹具不提供95%任务成绩。
完整原件及尚在进行的schema4开发矩阵见
[P1A报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_p1a.md)。

## 旧入口与新接口的区分

旧预建图AMCL导航、offline_merge与其他robot_count配置若保留，属于兼容工具，
不是MR3推荐入口；不通过注释机器人列表或复制旧出生位置开展研究。
活动新研究固定三台，活动默认已统一三台；保留兼容入口不增加其他规模研究。

新RL模式需互斥替换全局目标策略，保留协议/安全而无人工探索兜底。
新gateway需隔离后端received store、机器人本地action proxy、共享地图副本/队友状态。
这些是规划，当前没有对应参数/topic/可执行文件。不得用raw融合图、raw跨机TF、
远端action Future或未传输payload旁路，使网络实验继续享有即时信息。
时钟和真实字节分组验证独立于ROS启动；本页不声称现有ns3-gym已实现连接。
