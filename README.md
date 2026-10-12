# Multi-Robot Task-Oriented Wi-Fi RL

This monorepo combines ns-3/ns3-gym reinforcement learning with a ROS 2
multi-robot mapping and navigation task.

## Repository layout

```text
ns-allinone-3.40/ns-3.40/
  ns-3.40, ns3-gym, and the current wireless-rl experiments

ros2_ws/ros2-multi-robot-automap/
  ROS 2 Humble + Gazebo multi-robot SLAM, exploration, and navigation
```

The long-term goal is to study task-oriented Wi-Fi 4 communication for 2–3
robots that collaboratively map an unknown environment, search for an object,
return to charge when necessary, and rendezvous at the detected object.

Start with the
[`RESEARCH_PLAN.md`](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md),
then read the component guides:

- [`wireless-rl/USER_GUIDE.md`](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/USER_GUIDE.md)
- [`ros2-multi-robot-automap/user_guide.md`](ros2_ws/ros2-multi-robot-automap/user_guide.md)

Generated ns-3 outputs, checkpoints, ROS build/install/log directories, maps,
bags, and local environments are intentionally not versioned.

## 当前状态与报告入口

当前运行代码保持为 `b32c891` 的内容，长会话已暂停。P3C.5 的历史工程范围已验收；P2C.1 完整集成仍未完成，917 留出未运行。请从当前规划和指南进入，逐候选记录集中在实验日志与日期报告中。

| 内容 | 入口 |
|---|---|
| 项目概览、系统边界 | [项目概览](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20260928_project_overview_p0_p3b.md) |
| 当前工程检查点 | [实施计划](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/IMPLEMENTATION_PLAN.md) |
| P2C/P2D 历史验收 | [电池与充电](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20260917_p2c.md)、[完整理想任务](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20260918_p2d.md) |
| P3B.5/P3C 历史验收 | [需求审计](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261007_p3b5_requirement_audit.md)、[指标与控台](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261007_p3c_gate.md) |
| P3C.5 历史验收 | [应用负载审计](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261007_p3c5_gate.md) |
| P2C.1 现状与恢复 | [安全补强评审](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261009_p2c_strengthening_review.md)、[长会话审查与恢复](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261012_p2c1_session_recovery.md) |
| 五十四小时任务复盘 | [工作内容、实际成果与 54 个版本清单](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261012_p2c1_long_session_retrospective.md) |
| 完整实验时间线 | [实验日志](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/log.md) |

## 2026-10-12 资料整理

已从当前工作树删除 363 个已回退长会话的报告/附件，以及 6 份经 SHA-256 核验与归档分片一致的本地压缩副本，移除约 2.48 GiB。六份常读文档删除重复候选历史，保留当前状态、研究目标、验收条件、环境和实际使用方法。

完整原件保存在已推送的 `backup/project-before-report-cleanup-20261012`（整理前提交 `a48c9b4`），清理路径、字节数和 Git 对象见[归档索引](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/ARCHIVE_INDEX.json)。可用 `git show <归档分支>:<索引中的路径>` 读取旧报告；大型分片按索引顺序恢复后核对原 SHA-256。

原始任务账本、原生导航/安全记录、已验收阶段的报告、当前安全修复、测试夹具、模型、build/install 和 `260929_report/` 个人资料均保留。历史报告只支持对应冻结，不能据其推导当前任务通过。Git 历史仍保留归档，因此本次整理缩减当前文件和重复资料，不重写历史。

