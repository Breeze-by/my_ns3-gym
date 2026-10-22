# MR3 P2A V42：闭合原件有限诊断与reader环境隔离准备

## 实际闭合：描述性提取PASS（不提供科学资格）

2026-10-22，按预声明入口将`EXACT40`置为 **f96b9801957a80b22bf9096df3691173961ef417** 后执行，driver实际wait/reap rc0。证据仍是V41冻结47224c51c1c525c55093dce26b374d1ccb07eb06的已闭合interface/open101单EP；没有新World、原始物理审计重判或学习。原V41 physics/full FAIL及后继SKIPPED保持。

[提取派生结果](assets/20261022_mr3_p2a_v42_native_diagnosis/closed_execution/extract_v1.json)显示：固定9个文件均完整读完，合计 **517060271B**、原始SHA与V41闭合库存相同，输入stat和源码前后稳定；输出1617条选行、JSON3189288B。**`descriptive_selection_complete=false`**，省略计数为driver_tb2=39、driver_tb3=218、publisher_raw_odom_tb2=102、publisher_raw_odom_tb3=102。不能把输出中的plant/driver/odom窗口说成完整无省略，不能从缺失选行推断“没有发生”。

全任务统计独立累计于完整流式扫描，scope为release≤日志sim clock≤last returned sample clock，不能与有界代表选行混淆。tb3有1602条低层reach判据日志（不是1602次PPO决策），1280次正平移v请求的输出全为0；`linear_brake_preserve_requested_turn`和`reach_transition_envelope`的全记录reason计数分别379/855。此事实定位后续数学核查入口，尚不证明这些拒绝错误或放行后物理安全，也不重裁原停止覆盖FAIL。adapter缺wall/序号、drive/odom缺wall的限制保持，同tick跨文件全序仍不能补造。

[driver summary](assets/20261022_mr3_p2a_v42_native_diagnosis/closed_execution/summary.json)记录完整parent实际wait **27.535294547秒**，[inner actual-wait](assets/20261022_mr3_p2a_v42_native_diagnosis/closed_execution/actual_read_wait/actual_wait.json)为27.31817194秒，后者包含其内不叠加；均在原580内部/600parent及660总预约内。本次独立metadata/source/proc和纯字节封存是bookkeeping，无新科学消费者/实验或新增工程费用。累计 **50041.2338414596018/75000**，余 **24958.7661585403982**；pilot/final未动。

[独立闭合review](assets/20261022_mr3_p2a_v42_native_diagnosis/independent_closed_review_v1.json)PASS：声明scope准确15个源，实际outer绑定16项（另含scope文档），extractor核11项子集；current/f96冻结字节及before/after一致，三保存身份driver/wrapper/extractor均freshgone，Z态仍计存在。未扩大为未记录进程的缺席声明。本独立review只复核metadata、source和/proc，未再次打开原native trace字节；9原件SHA相合依据本次完整first-pass与V41库存。

五份有限输出已逐字复制至[A42 closed_execution](assets/20261022_mr3_p2a_v42_native_diagnosis/closed_execution)，共 **3205464B**；[逐字库存](assets/20261022_mr3_p2a_v42_native_diagnosis/closed_inventory_v1.json)保留原路径、SHA/bytes、canonical SHA及源stat稳定。review PASS仅提供有界提取/来源/身份/末账信用，不提供完整plant窗口、新物理资格、训练准入或P2A完成信用。

下一步本会话继续helper人工CPU和**禁用的同reach cone-support数学候选**；主跑尚未验证，不接生产/重跑matrix，不放宽原数学或任务门。需要先以具体反例证明候选与原reach圆锥约束的关系及边界，再决定新版本/冻结下必要的有界实际验证。用户自主授权有效，不再重复一般批准；P2A未完成。

## system reader隔离修复：人工CPU闭合

实际修复在`audit_reach_preparation.py`将显式exact输入重建交给清除PYTHONPATH/PYTHONHOME的`/usr/bin/python3`子进程，真实wait并严格核schema/episode/freeze/seed/start、完整snapshot/七图/source/input证明；原`audit_seed_inputs`及immutable叶子不改。默认legacy不变，full与PPO仍先走原archive门，再与system replay合取；不能用新子进程绕过原门。

三组实际child命令均为（cwd=wireless-rl）：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m unittest mr3_learning.tests.test_audit_reach_system_replay mr3_learning.tests.test_reach_controlled_dispatch mr3_learning.tests.test_audit_reach_ppo`；由`cpu_bridge_driver_v1.py NAME`封装source recovery与scope=cpu实际wait，NAME按下表顺序独占输出。

人工CPU三次真实结果均保留，不累计重复测试作独立总数：

| 实际组 | 真实结果 | child实际等待 |
|---|---|---|
| [system_bridge_cpu_v1](assets/20261022_mr3_p2a_v42_native_diagnosis/checks/system_bridge_cpu_v1/actual_wait.json) | 27项中一项新fixture的错误消息prefix预期不符，FAIL | 10.022599394s |
| [system_bridge_cpu_v2](assets/20261022_mr3_p2a_v42_native_diagnosis/checks/system_bridge_cpu_v2/actual_wait.json) | 修fixture时IndentationError，FAIL原件保留 | .11785947s |
| [system_bridge_cpu_v3](assets/20261022_mr3_p2a_v42_native_diagnosis/checks/system_bridge_cpu_v3/actual_wait.json) | 修复后27 tests PASS | 10.164193406s |

真实system child对一份**人工**冻结snapshot/七图完整重建通过，记录NumPy1.21.5、SciPy1.8.0；conda parent仍为NumPy2.2.6且无SciPy，没有混装依赖。各组actual-wait、console、source recovery与源码快照完整保存；全为人工CPU，新增工程费0，没有原native trace重验或World。

这项接线修复仍需未来新冻结的完整必要native资格才能给新source信用。本轮27项不改V41 FAIL，不证明停止激励/实际物理问题已解决，不启动PPO或重新矩阵。下一项为禁用cone-support数学helper CPU，尚未验证；原reach/.29及任务/安全门保持。

## 执行前预声明（原文保留）

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
