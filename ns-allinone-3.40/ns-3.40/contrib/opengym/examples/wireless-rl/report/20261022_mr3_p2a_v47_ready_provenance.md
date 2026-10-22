# MR3 P2A V47：启动就绪的两流来源诊断

2026-10-22预声明。[V46](20261022_mr3_p2a_v46_startup_diagnosis.md)已证adapter发布一次initial-input ready（37.92秒）、末三条记录状态新鲜，但worker当时四项ready未保存；原停止CLI全日志0匹配，原V45 FAIL保持。本次继续一次有限描述提取，不重跑活动或裁定科学资格。

[scope](assets/20261022_mr3_p2a_v47_ready_provenance/scope_v1.json)固定读取同一已关闭failedrooms回合的`driver_odometry_receipts.jsonl`（71649012B）与`motion_safety.jsonl`（312731331B），共384380343B；完整SHA/bytes须逐项等于V45库存，前后stat与source必须稳定。总输入512MiB、单行4MiB、输出2MiB，选择200条、每流尾20条；完整事件/标志/故障计数保留，省略明确标识。不读取map/information大流、不重放数学或物理、不启动World/模型/optimizer。

[提取器](assets/20261022_mr3_p2a_v47_ready_provenance/closed_ready_extract_v1.py)统计recorder ready事件、其前后identity/GID标志及首末例；motion按robot统计ready/started/allow、ready变化、decision reason/tracker fault及invalid事件。`message`不输出，`raw_json`仅SHA/字节；worker实际收到哪些ready回调仍是`NOT_RECORDED`。无效schema/epoch/JSON保持有界错误，存在错误时不能由事件0计数推断缺席；valid-schema计数与后续payload错误不是互斥行数分区。

10项纯内存自检已实际PASS、rc0/reap，child0.118299942秒，两个绑定源前后相同，原件读取0、工程费0。[实际wait](assets/20261022_mr3_p2a_v47_ready_provenance/checks/self_check_cpu_v1/actual_wait.json)、[console](assets/20261022_mr3_p2a_v47_ready_provenance/checks/self_check_cpu_v1/console.log)与[测试源码恢复](assets/20261022_mr3_p2a_v47_ready_provenance/checks/self_check_cpu_v1/source_recovery_v1.json)保留。78项outer绑定含全部learner import链、解释ROS源、固定V46 helper、两新脚本、CPU回执/恢复与原库存；scope本身另纳outer wait绑定。人工准备不是已消费原件的结果。

工程入场55718.1502503176018/75000、余19281.8497496823982；本次预约300秒（完整主parent240＋外尾60）。240是实际wait后的PASS费用门，不是未实现的hard-kill承诺；已提交工作始终实际wait/reap，超额仍完整计费并判FAIL，inner不叠加。保留原件/部分输出，不补读/重试旧活动。pilot/final额度及95%/质量/参与/接触/全部安全门保持。

本实现、scope及必要准备新commit/push后，从canonical wireless-rl执行一次：

```text
rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 -B -m report.assets.20261022_mr3_p2a_v47_ready_provenance.run_forensic_v1 --freeze EXACT40
```

[完整parent执行器](assets/20261022_mr3_p2a_v47_ready_provenance/run_forensic_v1.py)先核current/Git/scope一致，独占输出并核两输入库存字节；结束后需外部source/PID/start/费用复核。依据实际记录决定启动/清理修复及必要可观测性，不能凭推测加超时或隐去身份/安全失败。[V48人工提速候选](20261022_mr3_p2a_v48_support_cpu.md)仍禁用；任何接入须相关完整CPU及新冻结资格。P2A未完成，P2B/gateway未开始，用户自主持续授权有效。
