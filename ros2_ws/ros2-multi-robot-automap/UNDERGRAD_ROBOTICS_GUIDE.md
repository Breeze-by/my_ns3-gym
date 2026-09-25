# 本科生机器人任务层上手指南

这份文档给负责机器人算法落地和实机部署的同学使用。你们的工作重点是
ROS 2、Gazebo、SLAM、Nav2、多机器人探索、目标识别、集结、能源管理和真实机器人
部署。通信研究由项目负责人负责；在你们的日常开发和验收中，把无线链路视为**理想链路**：
消息可以到达、没有额外丢包和延迟。

这里的“理想通信”不等于可以绕过通信接口。所有跨机器人或机器人到中央控制器的数据，
仍然要经过项目已经定义好的 gateway。这样你们可以专心优化机器人算法，之后通信侧才能
在不重写任务算法的情况下把理想链路替换成延迟、丢包或真实 ns-3 链路。

## 先回答最关键的问题

你们主要研究 ROS 那部分，但范围比“写几个 ROS 节点”更完整，包含以下闭环：

```text
传感器/执行器 → 定位、SLAM、Nav2、安全控制
      ↓
多机器人地图融合、探索分工、目标检测、集结、充电
      ↓
Gazebo 可重复仿真 → 单机器人实机 → 多机器人实机
      ↓
指标、日志、故障复现和部署文档
```

你们不需要负责 ns-3、Wi-Fi MAC/PHY、空口调度、通信强化学习策略或网络参数标定。
但是需要提供通信侧可以接入的稳定消息接口，并记录任务算法对消息的类型、频率、时效和
内容的要求。

## 1. 项目分工和边界

| 内容 | 本科生机器人组 | 通信研究组 |
| --- | --- | --- |
| ROS 2 节点、launch、参数、TF、Nav2 | 负责 | 使用结果 |
| Gazebo 世界、机器人模型、传感器插件 | 负责 | 不负责 |
| SLAM、地图融合、探索分工和避碰 | 负责 | 不负责 |
| 目标检测、目标跟踪、坐标变换 | 负责 | 不负责 |
| RALLY 集结、充电和本地安全返航 | 负责 | 不负责 |
| 仿真指标、回归测试、实机部署 | 负责 | 关注任务结果 |
| `gateway_mode:=ideal` 下的接口适配 | 负责使用和维护兼容性 | 负责通信模型 |
| 应用层延迟、丢包、重传和消息账本 | 不作为日常算法变量 | 负责 |
| ns-3、Wi-Fi 参数和通信 RL | 不需要研究 | 负责 |

有三条边界必须一直保持：

1. 中央控制只能使用 gateway 送达的地图、位姿、TF、电量和检测消息。
2. 中央控制给机器人发导航目标时，使用 gateway action；不要从中央节点直接调用机器人
   的 Nav2 action。
3. Gazebo 真值只能作为仿真目标检测器或只读评估器的输入，不能让规划器直接读取真值
   坐标、真值地图或真值位姿来代替真实传感器链路。

## 2. 先建立系统心智模型

当前主入口会启动 Gazebo、1–4 台 TurtleBot3、SLAM Toolbox、每台机器人的 Nav2、地图
融合、中央协调器、目标检测器和电池管理器。核心数据流如下：

```text
Gazebo 或真实传感器
  ├─ /tbN/scan, /tbN/odom, /tbN/imu, /tbN/map
  └─ 本地 Nav2、SLAM、电池和安全控制
          │ 候选消息
          ▼
      ideal_gateway                 ← 你们默认使用
          │ GatewayEnvelope
          ├─ /gateway/received/tbN/map
          ├─ /gateway/received/tbN/odom
          ├─ /gateway/received/tbN/tf
          ├─ /gateway/received/tbN/battery_state
          └─ /gateway/received/target_detection
          │
          ├─ merge_map → /merge_map
          ├─ headquarters/control → /task_state, /rally_assignments
          └─ navigation_gateway → /gateway/tbN/navigate_to_pose
                                      │
                                      ▼
                                tbN 的 Nav2
```

`tbN` 表示 `tb1`、`tb2`、`tb3` 或 `tb4`。机器人本地的 `/tbN/scan`、`/tbN/odom` 和
`/tbN/map` 可以由该机器人自己的 SLAM/Nav2 使用；中央协同逻辑不能把这些本地 topic 当作
跨机器人数据的旁路。

任务状态的主流程是：

```text
EXPLORE → FOUND_UNCONFIRMED → FOUND → RALLY → COMPLETE
```

从 P2B 开始，只有 `COMPLETE` 算任务成功。`FOUND` 表示找到目标，覆盖率达到 90% 也只是
过程指标，不等于任务完成。

## 3. 代码地图：从哪里开始读

工作区位于：

```text
/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
```

| 目录或文件 | 作用 | 适合修改的内容 |
| --- | --- | --- |
| `src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py` | 主启动文件 | 新的可配置组件、参数和启动顺序 |
| `src/multi_robot/worlds/` | Gazebo 世界 | 新场景、障碍物、目标和充电区 |
| `src/multi_robot/models/`、`urdf/` | 机器人和传感器模型 | 传感器、底盘、目标模型 |
| `src/multi_robot/params/` | Nav2 参数 | 局部/全局代价图、规划器、控制器 |
| `src/merge_map/merge_map/merge_map.py` | 在线地图融合 | 对齐、融合和合并地图输出 |
| `src/multi_robot_exploration/.../control.py` | 中央探索和任务协调 | 分区、frontier、目标确认、集结调度 |
| `.../target_detector.py` | 目标检测适配 | 仿真检测器、真实视觉检测器的统一输出 |
| `.../battery_manager.py` | 单机器人电量和返航 | 能耗、充电、恢复和安全优先级 |
| `.../task_evaluator.py` | 任务评估和完成门 | 覆盖率、碰撞、集结、超时和失败原因 |
| `.../ideal_gateway.py` | 理想/故障 gateway | 日常使用；改接口前先和负责人协调 |
| `.../navigation_gateway.py` | 导航目标 gateway | 中央目标到本地 Nav2 的适配 |
| `scripts/ros_smoke_test.py` | 单轮自动检查 | 启动、消息、评估和清理 |
| `launch_commands.md` | 命令速查 | 每次修改 launch 参数后同步更新 |
| `user_guide.md` | 详细使用说明 | 遇到启动或 topic 问题先查这里 |

建议阅读顺序是：主 launch → `control.py` → `navigation_gateway.py` → `merge_map.py` →
`target_detector.py` → `battery_manager.py` → `task_evaluator.py`。先理解已有数据流，
再添加算法；不要一开始就重写启动系统。

## 4. 第一次运行

每个新终端先准备环境：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
```

源码有改动时编译：

```bash
colcon build --symlink-install \
  --packages-select multi_robot merge_map multi_robot_exploration
source install/setup.bash
```

先运行两机器人、理想 gateway、只探索建图的基线：

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  world:=my_world.world \
  robot_count:=2 \
  gateway_mode:=ideal \
  enable_gzclient:=true \
  enable_rviz:=false \
  enable_merge_rviz:=true \
  enable_target_detection:=false \
  enable_rally:=false \
  enable_battery:=true \
  gazebo_seed:=101
```

确认以下现象后再开始改代码：

- Gazebo 中有两台机器人，Nav2 都能进入可用状态；
- 每台机器人有自己的 `/tbN/map`，中央有 `/merge_map`；
- `ros2 topic echo /task_state` 能看到任务状态变化；
- RViz 中合并地图持续更新，机器人不会因为中央节点直接控制而绕过 gateway；
- 按 `Ctrl-C` 退出后没有留下需要手工清理的 Gazebo/ROS 进程。

快速查看 topic 和节点：

```bash
ros2 topic list | sort
ros2 node list | sort
ros2 topic echo --once /merge_map
ros2 topic echo --once /task_state
```

自动 smoke 用于避免手工观察造成误判：

```bash
python3 scripts/ros_smoke_test.py \
  --world my_world.world \
  --robot-count 2 \
  --gazebo-seed 101 \
  --startup-timeout 300 \
  --message-timeout 90 \
  --shutdown-timeout 60 \
  --evaluation-duration 300 \
  --coverage-threshold 0 \
  --evaluation-wait-timeout 600 \
  --episode-id undergrad_first_run
```

第一次运行失败时，先保存终端输出、world、seed、参数和当前 commit，再改代码。不要只凭
Gazebo 画面判断成功。

## 5. 推荐的开发路线

每个阶段都要保留一个可以重复运行的基线。算法变好之前，先确保旧基线仍能启动和退出。

### 阶段 A：可重复基线

目标是让同一世界、同一机器人数量和同一 `gazebo_seed` 产生可比较的结果。先使用
`my_world.world`、`p1c_rooms.world` 和 `p1c_corridors.world`，开发种子使用 `101`、`202`、
`303`。记录启动时间、任务时间、覆盖率、碰撞数、各机器人路径和最终状态。

交付物：一条可以复制的命令、一次成功的 `COMPLETE` 记录、失败时的原因分类和日志位置。

### 阶段 B：SLAM、地图融合和 Nav2

先单机器人验证传感器、TF、局部代价图和规划；再做两机器人地图融合，最后扩展到三或四
机器人。调整 Nav2 时同时观察：

- TF 是否连续且 frame_id 正确；
- 局部规划器是否会撞墙或在窄通道振荡；
- 合并地图的分辨率、原点和时间戳是否一致；
- 机器人是否会反复探索同一区域；
- 导航目标失败时是否有明确状态，而不是无限等待。

交付物：每个世界至少一组地图截图和指标；关键参数变更说明；单元测试或最小复现用例。

### 阶段 C：多机器人协同探索

可以优化 frontier 选择、区域划分、任务分配、重复覆盖抑制、路径冲突处理和动态重分配。
规划器使用 gateway 送达的数据；没有送达的数据不能假设已经存在。机器人本地安全控制
必须独立工作，中央协调器失去某个机器人的信息时要能超时、降级或重新分配任务。

至少记录：总覆盖率、达到 75/80/90/95% 的时间、最终覆盖率、路径长度、重复覆盖率、
机器人间最小距离、碰撞数和任务完成状态。

### 阶段 D：目标识别和任务状态机

仿真阶段可以使用 `target_detector.py` 的 Gazebo 真值 provider 产生候选检测消息，但中央
控制器只能消费 gateway 送达的检测结果。真实算法接入时，用相同的检测消息语义替换
provider，不要让控制器同时认识两套接口。

至少明确：目标 ID、检测时间、坐标 frame、位置、置信度、观测机器人、重复检测去重规则、
目标消失后的处理和 `FOUND_UNCONFIRMED` 到 `FOUND` 的确认条件。

交付物：仿真真值检测基线、带噪声或遮挡的检测测试、真实相机/深度相机接口说明，以及
误检、漏检和坐标变换错误的日志。

### 阶段 E：RALLY 集结

目标确认后，机器人按独立 staging pose 集结。当前完成门要求每台机器人到达自己的位置，
位置误差不超过约 `0.35 m`，线速度不超过 `0.05 m/s`，角速度不超过 `0.10 rad/s`，并且
连续稳定约 5 秒；具体阈值以当前 evaluator 和 launch 参数为准。

需要处理：路径交叉、目标附近障碍、机器人互相阻挡、某机器人导航失败、重复目标命令和
集结超时。交付物应包括每台机器人轨迹、最终误差、速度曲线、保持时间和失败原因。

### 阶段 F：电量、充电和恢复

电池管理器是每台机器人的本地安全组件。总部不能覆盖安全返航；机器人充电后要保留已知
地图和任务状态，并能恢复任务。先用低初始能量强制触发一次充电，再验证多机器人同时
返航时的充电位冲突。

至少测量：返航触发能量、到达充电位能量、充电时长、恢复后的任务进度、耗尽次数、碰撞数
和完成状态。建议从已有的 `battery_initial_energy:=18` 强制充电 smoke 开始，不要一开始
改动整个电池模型。

### 阶段 G：仿真到实机

按以下顺序迁移：

1. Gazebo 中使用真实传感器 topic 结构，先关闭对规划器不可见的真值输入。
2. 单台真实 TurtleBot3：校准激光、里程计、TF、速度限制和急停。
3. 两台真实机器人：先做静态地图导航，再做局部探索，最后做多机器人协同。
4. 接入真实相机/深度相机或 AprilTag/ArUco 等目标识别方案，比较仿真和实机误差。
5. 在实验室固定场景做多次重复运行，记录电量、温度、CPU、网络连接和人工接管次数。

实机阶段仍可先把通信视为理想任务条件，但不能把 Gazebo 真值、仿真时间或仿真模型路径
留在控制链路中。任何急停、障碍物安全停、通信超时和电量保护都要能由机器人本地触发。

## 6. 理想 gateway 下的接口规则

日常开发统一显式设置：

```text
gateway_mode:=ideal
```

这表示当前任务实验不研究延迟、丢包和重传；它不表示删除 gateway。请遵守下面的规则：

- 中央地图融合订阅 `/gateway/received/tbN/map`，不要直接订阅 `/tbN/map`；
- 中央状态使用 `/gateway/received/tbN/odom`、`/tf`、`/battery_state` 和
  `/target_detection`；
- 中央导航目标发布到 `/gateway/tbN/navigate_to_pose`；机器人本地 Nav2 再由
  `navigation_gateway` 转换；
- 保留消息中的机器人 ID、消息 ID/序号、源时间戳、frame_id、任务模式和版本字段；
- 新增字段要向后兼容，修改字段类型、topic 或 action 前先记录接口变更；
- 不要用全局变量、文件拷贝或 Gazebo service 把地图、位姿或目标坐标直接塞给中央规划器；
- 需要查看真值时，把它接到 evaluator 或单独的 debug 节点，不要接到任务决策路径。

你们可以优化消息生产者和任务算法，但要让同一套消息在 `gateway_mode:=ideal` 和未来的
故障/通信模式下都能被消费。通信侧需要知道每类消息的发送频率、平均和最大 payload、
允许的年龄、是否允许丢失、是否需要顺序和重复处理方式。

## 7. 指标和验收方式

每轮实验至少写下：代码 commit、world、机器人数量、Gazebo seed、初始电量、目标坐标、
关键算法参数、运行时长、最终任务状态和日志目录。建议统一保存 JSON/CSV，不要只保存截图。

| 类别 | 最少指标 |
| --- | --- |
| 建图 | 合并地图覆盖率、地图尺寸/分辨率、完成时间、地图一致性 |
| 探索 | 75/80/90/95% 覆盖时间、最终覆盖率、路径长度、重复覆盖率 |
| 导航安全 | 碰撞数、最小机器人间距、规划失败次数、急停次数 |
| 目标识别 | 首次发现时间、确认时间、精度/召回率、坐标误差、误检/漏检 |
| 集结 | 每台机器人的位置/姿态误差、速度、稳定保持时间、超时原因 |
| 电量 | 能量曲线、返航触发、充电次数/时长、耗尽次数、任务恢复结果 |
| 任务 | `COMPLETE`、失败状态、总时长和失败原因 |

验收时优先看 `COMPLETE`、零碰撞和可复现性。`FOUND`、90% 覆盖率、某个漂亮的 RViz
画面都不能单独替代完整任务验收。

## 8. 测试分层

建议每次提交按下面的顺序验证：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
colcon test --packages-select multi_robot_exploration merge_map
colcon test-result --verbose
```

然后运行一个两机器人理想 gateway smoke；算法有明显变化时，再运行三个固定 seed。单元
测试优先覆盖纯函数、状态机、检测去重、stale 消息、超时和电池边界；集成 smoke 覆盖
启动、topic、Nav2、地图融合和退出清理。

通信故障矩阵属于通信组的测试范围。你们不需要把 10% 丢包或 2 秒延迟作为普通算法调参
条件，但修改消息接口或超时逻辑时要和通信组共同跑一次对应回归。

## 9. 仿真与实机的分工建议

可以把本科生工作拆成以下可独立验收的项目：

1. **地图和导航**：完成单机 SLAM、地图融合、Nav2 参数和安全停。
2. **协同探索**：完成 frontier/区域分配、重分配、避碰和覆盖率优化。
3. **目标识别**：完成仿真 provider、真实传感器 detector、目标确认和坐标变换。
4. **集结任务**：完成 staging pose、路径冲突处理、稳定保持和完成门。
5. **电量和恢复**：完成返航、充电、状态保持和任务恢复。
6. **部署与评估**：完成 launch、参数管理、日志、自动 smoke、实机脚本和安全检查。

每个小组都必须提供：接口说明、启动命令、最小复现、指标结果、已知限制和交接说明。
小组之间通过 ROS topic/action 和参数文件协作，不要通过未记录的全局变量或临时脚本耦合。

## 10. 交给通信研究组的交接材料

当一个机器人算法版本准备交给通信侧时，提交一页接口表，至少包括：

- 消息或 action 名称、生产者、消费者和方向；
- ROS 类型、字段含义、单位、frame_id、机器人 ID 和版本；
- 产生时间、发送频率、平均/最大 payload 大小；
- 可以接受的最大消息年龄、是否需要顺序、重复消息如何处理；
- 消息丢失或延迟时任务应当如何降级；
- `gateway_mode:=ideal` 下的基线结果；
- 一次成功和一次失败的日志、seed、world、参数和 commit。

这样通信侧可以把同一条应用消息接入故障 gateway 或 ns-3，而不需要改动探索、检测、集结
和充电算法。若通信实验发现任务算法确实需要新的优先级或超时语义，两组共同修改接口，
并同时更新测试、`launch_commands.md` 和本指南。

## 11. Git 和协作规则

- 只在本仓库的 canonical path 工作，不要使用旧的 `/home/zhuyulab/ros2_ws/` 副本。
- 不要提交 `build/`、`install/`、`log/`、Gazebo 运行输出、rosbag 或临时地图。
- 修改 launch 参数、默认组件或推荐命令时，同一提交更新 `launch_commands.md`。
- 提交前运行相关测试、`git diff --check`，并用 `git add -n .` 检查没有误加运行产物。
- 每个提交保持一个主题，例如“改进 frontier 分配”或“接入真实目标 detector”，不要把
  无关的格式化和大批生成文件混进来。
- 修改 `ideal_gateway.py`、`navigation_gateway.py`、消息字段或中央 topic 前，先和通信组
  对齐；这些文件是双方的接口边界。

## 12. 完成定义

一个功能可以交付时，应该同时满足：

- 有明确的 ROS topic/action、参数和 frame 说明；
- 有至少一个单元测试或最小复现；
- 在 `gateway_mode:=ideal` 下能用固定 world/seed 重复运行；
- 不绕过 gateway，不把 Gazebo 真值接入控制决策；
- 有成功、超时、导航失败和退出清理路径；
- 指标和失败原因可从日志读取；
- 相关启动命令和参数文档已更新；
- 仿真到实机需要的传感器、TF、速度限制、安全停和人工接管步骤已写明。

## 相关资料

- [启动命令速查](launch_commands.md)
- [完整使用说明](user_guide.md)
- [ROS 2 项目 README](README.md)
- [研究总计划](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md)
- [工程实现计划](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/IMPLEMENTATION_PLAN.md)
