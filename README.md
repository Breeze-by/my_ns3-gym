# MR3：三机器人 RL 联合建图与 Wi-Fi 网络影响

当前研究路线（2026-10-15）：固定三台机器人，先以集中式 RL 联合选择稳定探索子目标，
保留各机器人 SLAM/Nav2 与地图融合；理想通信任务达到可靠的95%覆盖后，冻结策略，
通过 gateway 将上下行真实应用数据送入 ns-3 Wi-Fi，评估任务表现。通信优化和实机部署
以后另定。MR3-P0已验收，P1A待用户验收；P1B及后续未开始。

当前代码仍是传统前沿控制器的建图导航系统，尚无三机器人导航 RL 或 ROS/ns-3 gateway。
P1A已实现固定ROI的95%任务契约、18路全机体接触监测和导航终态闭合。冻结`5e47802`
累计10次尝试保留1次原生关闭基础设施失败，经事前预声明的同冻结补测得到9个有效单元：
6次严格成功、3次peer包络安全失败；SDK关闭崩溃尚未证明根治。这是传统开发基线证据。
详见[P1A报告](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_p1a.md)。

## 从这里开始

- [研究契约与方法](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md)
- [逐步研发与验收状态](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/IMPLEMENTATION_PLAN.md)
- [代码/文献路线审计](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_route_audit.md)
- [当前 ROS 使用指南](ros2_ws/ros2-multi-robot-automap/user_guide.md)与[可执行启动命令](ros2_ws/ros2-multi-robot-automap/launch_commands.md)
- [报告与证据适用范围](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/README.md)
- [旧 toy 调度工具指南](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/USER_GUIDE.md)（不是新导航策略入口）

## 仓库

唯一 Git 根 `/home/zhuyulab/ns3-workspace`，origin 为 `Breeze-by/my_ns3-gym`。
ROS 源码以 git subtree 合入，不是 submodule：

```text
ros2_ws/ros2-multi-robot-automap/     ROS 2 Humble / Gazebo / SLAM / Nav2
ns-allinone-3.40/ns-3.40/            ns-3.40 / ns3-gym / wireless-rl
```

`main` 是回退修复后的活动版本；`p2c1/global-mission-20261012@8fe1495` 是原路线最新
完整版备份。仅维护这两条本地/远程分支，不改备份，不把旧搜索/充电/集合/通信调度研究
带回新路线。旧计划与报告的恢复位置在归档索引，历史失败保持原义。

每个 MR3 子步骤完成检查与提交推送后给用户验收，确认后才进入下一步。规划不等于
功能已实现；实际行为看源码，性能结论看同冻结版本的原件，不跨版本拼接成绩。
