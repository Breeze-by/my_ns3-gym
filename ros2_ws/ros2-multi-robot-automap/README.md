# 三机器人联合建图导航：ROS 组件

本组件在 `/home/zhuyulab/ns3-workspace` 单一仓库内，使用 ROS2 Humble、Gazebo Classic、
TurtleBot3 Waffle、slam_toolbox、保守地图融合与 Nav2。当前仍由传统前沿控制器选择目标。
新路线固定 tb1/tb2/tb3，拟由集中式 RL 策略联合选择稳定子目标，再冻结策略接 ns-3 Wi-Fi；
**导航 RL 和 gateway 尚未实现**。MR3-P0已验收；P1A待用户验收，P1B及后续未开始。

先读 [研究计划](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md)和[检查点](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/IMPLEMENTATION_PLAN.md)，
实际运行读 [launch_commands.md](launch_commands.md)，代码/话题说明读
[user_guide.md](user_guide.md)和[Technical_Manual.md](Technical_Manual.md)。

```text
src/multi_robot/               模型、场景、主 launch、每台 Nav2 参数
src/slam_toolbox/              当前 SLAM 实现
src/merge_map/                 公共 frame 栅格融合
src/multi_robot_exploration/   当前手工控制、peer避障、就绪门控、评估器
scripts/                      有界 smoke 与传统理想基线 runner
```

当前主 launch 默认三台，保留1–4兼容；MR3研究命令显式 `robot_count:=3`。
三台默认与严格schema4合同已在 MR3-P1A实施；不通过注释机器人列表、运行二/四/六台或
旧 AMCL 预建图 launch 来实现研究场景。融合假设已知公共坐标系，不解决任意初始地图配准。

历史`c9344e1`的三台rooms/corridors seed101仅有90%工程回归。新隔离接触夹具v8已验证
tb1六部件真实接触正例与三台18路持续监测；它不代表95%建图成功。schema4开发矩阵
在冻结`5e47802`得到9个有效单元，累计10次尝试含1次保留的原生基础设施失败；
P1A待用户验收，导航RL、训练和通信尚未实现。
[P1A当前证据](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_p1a.md)、
[工程原件](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261013_p1c_engineering_repair.md)与
[报告索引](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/README.md)保留旧结果和失败，不自动成为 MR3 信用。

ROS 使用系统 Python 与 canonical workspace；学习端 conda 环境另行隔离。
具体环境、构建、三台演示/评估及故障诊断统一在当前指南，不照搬旧独立检出路径。
每次源码/命令修改同步文档、验证、提交推送；实验追加共享 wireless-rl/log.md。
上游软件包自带 README 描述依赖本身，不是本项目的研究路线或验收状态。
