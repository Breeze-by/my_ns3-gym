# MR3 P2A V46：失败启动的有限原件诊断

## 实际闭合：有限描述诊断PASS，V45原FAIL保持

执行freeze `8daa902d5fead2def8356cf781d488573d951769`，证据freeze仍为V45 `cace46e08e53b7e89a434e23721db85ac993f6f5`。唯一活动已实际wait/reap rc0；8输入共3101211B，完整SHA/bytes与V45无损库存一致、前后及独立复核lstat稳定；无World/model/optimizer/新科学重放。该PASS只支持本轮提取和来源/费用/关闭一致性，不能覆盖V45 reset/cleanup FAIL、完整资格缺口或P2A未完成。

| 派生事实 | 数值与位置 | 可支持的结论 |
|---|---|---|
| adapter事件 | 完整723行：720 state_update、1 initial_inputs_ready、1 safety_stop、1 task_stopped；task_start=0、parse_error=0 | 有实际adapter ready发布记录，无task release记录 |
| initial-ready | adapter第2行，stamp37.92，schema mr3-initial-inputs-ready-v1 | 发布者的记录成立；不是worker接收/消费回执 |
| 末三state | 第719/720/721行，stamp120.9/121.0/121.1；三次按记录时刻计算fresh=true | 仅说明这些回调记录时刻源龄，不证明timeout时刻或每次maintain的全部ready门 |
| stopCLI | launch完整418行上原停止CLI正则匹配0，identity condition=missing | 原报错本次可确定为missing；没有改正则/执行原helper或改判cleanup |
| launch结尾 | 第417行ordered shutdown向motion_safety-5发SIGINT；第418行sending signal，随后文件结束 | 未记录该次后继exit/native-stop CLI；缺失原因仍未知 |

launch选择最多200项/tail20，23条匹配行未纳选段；完整文件SHA和全行正则计数仍保留，但不能把选段叫完整因果窗口。worker四ready实际值、adapter map/discovery完整历史继续为NOT_RECORDED；不能仅凭initial-ready或末三fresh断定所有worker ready均已收到、启动本应成功或纯粹CPU慢。

### 费用、来源及关闭

完整parent实际等待0.800222553秒；inner0.460828695秒已经包含，不叠加。工程累计55718.1502503176018/75000、余19281.8497496823982；pilot/validation各新增0，原1870/2905.9547395464029及final-only401/402/403额度保持。

[独立闭合review](assets/20261022_mr3_p2a_v46_startup_diagnosis/independent_closed_review_v1.json)PASS/review_errors=[]：75项scope源＋scope本身共76 outer绑定，before/after/current/Git完全一致，7项ROS解释源一致；8输入与V45库存和当前lstat相符，复核没有重读原件。driver/wrapper/extractor三个保存PID/start均freshgone（Z仍计存在），真实argv与时间包含关系相符。review只核metadata/source/Git/proc，不提供科学资格。

[无损库存](assets/20261022_mr3_p2a_v46_startup_diagnosis/closed_inventory_v1.json)及[canonical闭合副本](assets/20261022_mr3_p2a_v46_startup_diagnosis/closed_execution)保留5份派生成果/262691B，逐字SHA/bytes/stat相等；纯包装不重算科学结果/费用。原source/scope/回执未覆盖。

下一步仅对现成driver_odometry_receipts和motion_safety两流作一次有界诊断，区分recorded ready、driver身份/GID无效化和motion故障；先独立人工边界检查及新scope/freeze，不猜因、不加400/420秒门或直接重跑V45。临时CPU优化候选名字不提供任何正式活动信用，后续canonical版本由新声明决定。旧20100整链预约仍大于余额，完整后继链必须另按实际成本前瞻安排；P2A未完成、P2B/gateway未开始。

## 唯一实际命令

cwd=canonical wireless-rl：

```text
rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 -B -m report.assets.20261022_mr3_p2a_v46_startup_diagnosis.run_forensic_v1 --freeze 8daa902d5fead2def8356cf781d488573d951769
```

## 运行前预声明（历史快照）

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
