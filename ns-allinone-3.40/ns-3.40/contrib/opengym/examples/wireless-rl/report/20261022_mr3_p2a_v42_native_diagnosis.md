# MR3 P2A V42：闭合原件有限诊断与reader环境隔离准备

2026-10-22预声明。用户已授权本会话自主持续完成P2A，不再询问一般实施/有限预算批准；P2A尚未完成。[V41](20261022_mr3_p2a_v41_packing_gate.md)原interface32/32与局部PASS、physics停止覆盖FAIL、conda full缺scipy的rc1/无result、后继全部SKIPPED及61保存身份freshgone均保持。本轮不把描述性取证或新CPU修复追认为V41通过。

## 当前准备及证据边界

[scope_v1.json](assets/20261022_mr3_p2a_v42_native_diagnosis/scope_v1.json)、[固定提取器](assets/20261022_mr3_p2a_v42_native_diagnosis/closed_native_extract_v1.py)与[实际wait launcher](assets/20261022_mr3_p2a_v42_native_diagnosis/run_forensic_v1.py)已建立；15项source绑定、语法和路径静态准备通过。当前system reader/conda learner隔离修复正在人工CPU准备，尚未测试，也未重新消费原trace；不能写“修复通过”或新增原生资格。

只读取V41已闭合的interface/open101单EP、reset＋32实际step，证据冻结仍为 **47224c51c1c525c55093dce26b374d1ccb07eb06**；完整原字节来源由[V41闭合库存](assets/20261022_mr3_p2a_v41_packing_gate/closed_inventory_v1.json)及其SHA锁定。提取执行使用本次新源码freeze，须待修复CPU完成后同commit/push确定；旧证据冻结与新执行冻结不能混称。

## 固定有限范围与费用

- 文件固定9个：transitions、adapter、motion_safety各一，以及tb1/tb2/tb3的drive和odometry各三；单次流式读取，合计输入≤1GiB，不扩大episode/场景或解map/blob。
- 最多2200条选行、完整输出≤4MiB；保留原行号、原有时间戳与缺失字段。不能补造wall时钟或从跨文件同tick记录推断完整因果全序；提取不重新裁决物理/任务成功，不给科学资格。
- reader内部≤580秒，完整parent实际wait≤600秒，外部收口另预留60秒，共660秒。来自原800准备块扣preflight38.263866609秒后余761.736133391秒，块内还余101.736133391秒；没有新扩额。
- 入场工程累计50013.6985469126018/75000，余24986.3014530873982。这里只记预约，不提前填写实费；主实际完整wrapper wait与外尾分别保留，嵌套receipt不重复收费，失败也记实际费用。
- 0 World、0新回合、0GPU优化/学习，无P2B/gateway；pilot1870决策/2905.9547395464029秒及final-only401/402/403额度保持。

## 新freeze后的唯一实际入口（尚未执行）

cwd为canonical wireless-rl目录：

```text
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -m report.assets.20261022_mr3_p2a_v42_native_diagnosis.run_forensic_v1 --freeze EXACT40
```

`EXACT40`替换为本次源码/CPU/文档同commit并push后的精确40位SHA。launcher要求scope中source与当前Git冻结字节一致，唯一新输出prefix `/tmp/mr3_p2a_v42_native_diagnosis`，不覆盖V41或重用旧结果。运行与完整外部身份/费用闭合前，不改已绑定源或中途commit。

必须等主实际wait、9原件完整SHA与stat稳定、输出边界、最终driver/consumer身份及外尾真实费用全部核完再写实际结论；一个进程不能证明自身最终关闭或未来费用。输出截断/缺件/超限必须保留不完整状态，不能加读或补样自动变成PASS。

本次先用有限事实区分导航/控制请求、gate拒绝、真实平移与停止激励覆盖，再决定最小必要修复及新冻结验证。正确隔离system reader与conda learner不等于物理问题已修复；不直接重跑完整matrix、不改原95%/300秒、质量、参与、18接触或停止/物理/FIFO/TTL门。最终训练与final-only三场严格任务成功仍独立必要，P2A未完成。
