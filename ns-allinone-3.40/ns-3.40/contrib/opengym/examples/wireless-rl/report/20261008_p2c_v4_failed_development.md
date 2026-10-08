# P2C.1 v4 时钟顺序失败候选（2026-10-08）

**严格开发 FAIL**，冻结 `bc6b44ce9b86d86b2e355f75b3bb8d8f34a87fe9`。首个lab2/303/E18原任务RALLY timeout300.4s、仅tb1充电；其余3开发/17正式/physical未运行，917未暴露，无retry/backfill。owner/observer退出0，gateway/metrics正常退出，但Nav2 lifecycle_manager有SIGTERM→SIGKILL收尾升级，原日志保留，不称所有worker自然退出。源/实际命令/环境/原结果/每SHA、严格traceback和精选gzip见[JSON](20261008_p2c_v4_failed_development.json)。

原生报告零接触、无failed_robots/min16.6752；其中tb2实际Gazebo运动13.570248m，电量却始终18、charge0/return0。这一冻结电量计令能量指标无效，不能作为无耗尽或安全证明。合法native传感器源时间因DDS到达顺序略领先本节点/clock，例如source1998.607、callback1998.582，已有gateway对此暂存0.025秒；v4本地新增处理直接丢弃所有领先样本，导致没有连续odom/TF输入。这是时序处理缺陷，不是通过增大TTL或延长任务可以修复的问题。

新候选按同源时间有界暂存（最多128输入、最多原2秒范围），等真实时钟赶上后按源次序应用；源戳不改、不在未成熟时使用。重复/倒序仍不能重结算，异常未来不替换有效状态。actual DDS先样本后clock夹具复现并验证只结算一次距离/时间费用。原失败仍是失败，后续需要新完整独立cohort。原raw留canonical log/p2c/20261008_p2c_v4/，全原始结果和历史v1/v2/v3保持，无P4/ns3/Wi-Fi/RL。
