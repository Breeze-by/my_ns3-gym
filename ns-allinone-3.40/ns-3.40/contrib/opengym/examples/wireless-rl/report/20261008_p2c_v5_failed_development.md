# P2C.1 v5 启动充电验证失败（2026-10-08）

**FAIL**。原冻结 `0587dcf` 的首个 forced2 在251.1秒原生COMPLETE、两机各charge1、零接触/失败；239 live/protocol/graph/能量与原返回预测通过。然而两机在首批姿态就绪时直接于起点充电，实际返航距离均0、各增加62模型能量。不能把这个结果作为低电量远端返航能力，也不能作为完整P2C门禁。原先单格严格reader PASS保持，新增明确反例审核原样输入FAIL，详见[JSON](20261008_p2c_v5_failed_development.json)。

根因是快速odom回调在下一次安全timer之前直接调用begin_charging，绕过timer中的“已负担初始等待则恢复ACTIVE”判断。v6在统一入口补上相同恢复保护，覆盖时钟领先暂存和clock已成熟/TF先于odom两种实际DDS顺序，保持原源戳/TTL/能量/300s/5s。先前v5合成DDS测试只覆盖timer成熟顺序，不能宣称所有回调入口已验证；本原记录纠正该范围。

所有原owner/observer已关闭、原始SHA与选择性无损gzip保留，未运行其余3开发、17正式、物理blackout和917；没有重试或失败格回填。v1/v2/v4失败、v3partial和accepted P3C.5保持，无P4/ns3/Wi-Fi/RL。
