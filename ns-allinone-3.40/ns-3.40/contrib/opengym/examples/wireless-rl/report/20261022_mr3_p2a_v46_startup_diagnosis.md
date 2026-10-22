# MR3 P2A V46：失败启动的有限原件诊断

2026-10-22预声明。用户已授权自主持续完成P2A；本次先定位[V45真实失败](20261022_mr3_p2a_v45_preparation_classification.md)，不修改其结论。当前P2A未完成，生产实现、400/420秒启动门、95%任务及全部安全门保持。

[scope_v1.json](assets/20261022_mr3_p2a_v46_startup_diagnosis/scope_v1.json)只允许一次读取已关闭的V45 reset worker1第三回合rooms101：`launch.log`、`adapter.jsonl`与六份小metadata。逐文件上限合计16MiB，单行1MiB，结果4MiB，选择和省略均显式计数；完整SHA及前后stat必须与V45无损库存一致。不读取motion/information/map大流，不启动World、训练或新科学审计。

已知内层400秒`three-robot delivered-input startup guard expired`、清理`native stop CLI identity is missing or ambiguous`及外层420秒reset RPC超时。诊断复用冻结源码中的原停止CLI正则，区分0/1/多匹配，并读取adapter已记录事件及状态源龄。原件没有保存的worker四项ready布尔、adapter map一致性及Nav2 discovery历史必须报告`NOT_RECORDED`；没有事件不能替代当时回调状态。

[提取器](assets/20261022_mr3_p2a_v46_startup_diagnosis/closed_startup_extract_v1.py)的10项纯内存自检已实际通过，child等待0.107243055秒、源码前后相同，native文件读取0。覆盖停止身份0/1/2、initial-ready有/无、状态源龄正常/缺失/乱序、坏JSON的有界保存及输入字节拒绝；[实际wait](assets/20261022_mr3_p2a_v46_startup_diagnosis/checks/self_check_cpu_v1/actual_wait.json)、[console](assets/20261022_mr3_p2a_v46_startup_diagnosis/checks/self_check_cpu_v1/console.log)和[测试源码恢复](assets/20261022_mr3_p2a_v46_startup_diagnosis/checks/self_check_cpu_v1/source_recovery_v1.json)保留。人工自检不提供原件诊断或原生资格。

工程入场55717.3500277646018/75000、余19282.6499722353982。本活动预约300秒：完整主parent实际wait至多240，外部关闭元数据至多60；嵌套wait不叠加，纯源码/字节保管记账排除。pilot/final额度不动。旧20100完整链预约大于当前余额，后续须先根据实际成本重新声明可行scope。

实现、CPU、scope及闭合原件提交并push后，才在canonical wireless-rl以新40位freeze执行：

```text
rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 -B -m report.assets.20261022_mr3_p2a_v46_startup_diagnosis.run_forensic_v1 --freeze EXACT40
```

[执行器](assets/20261022_mr3_p2a_v46_startup_diagnosis/run_forensic_v1.py)核当前/Git/scope源字节，独占一次输出并实际wait/reap整个外层；输出原件SHA必须逐项等于V45库存。执行后仍须外部核保存PID/start已消失及精确费用，保留失败结果，不补读或重试旧活动。下一步依据此次有限证据修启动/清理或增加必要可观测性，并核运行成本；不能把本诊断当12EP/30角色资格、正更新或最终95%验收。P2B/gateway未开始。
