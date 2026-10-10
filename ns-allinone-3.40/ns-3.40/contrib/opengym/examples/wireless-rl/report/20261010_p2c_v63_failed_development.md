# P2C.1 v63 四原开发整体 FAIL

同冻结 `b488cd5ecd16f6061e19f6b8f47755fd055e51a8`，四原27软件/仪器digest一致，owner/observer均0且PID不存在后才修改。

|场景|原生结果/秒|检测/集合秒|charge总数|最低电量|原生保持|strict|
|---|---|---|---|---|---|---|
|dev_forced2|COMPLETE 156.5|88.7/100.7|2|16.714836|5.0s/51样本|PASS|
|dev_lab101|COMPLETE 234.5|72.6/76.1|2|28.592891|5.5s/56样本|PASS|
|dev_rooms202|COMPLETE 209.2|118.6/123.7|1|19.751141|5.4s/55样本|PASS|
|dev_corridors303|RALLY 300.0|181.6/210.0|3|22.014091|None|FAIL|

corridors18原独立子审PASS不能替代300s原生RALLY timeout。原6次return全部闭合，4条完整前缀与8个原local/fused CDR绑定PASS，三机各charge1；旧v62未闭合return及漏源两问题未在这轮重现，但不可据此归因唯一修改。四格零接触/耗尽/FAILED，原任务期与停止后子进程状态原样保留。

原检测181.6秒，RALLY210.0；赋值几何原clock311.8、完成314.1、交接接纳338.4。原当前接纳快照的tb2/tb1/tb3顺序可重新证明三条完整body/local approach。五条件冷样本中位完整排列1.204秒、只复证既有串行顺序.227秒；不是原live回放或最坏时限，不能将原26.6秒延迟唯一归因排序。未来保留过期尝试的几何顺序为偏好，并在当前交付图/身体/源期限内重新证明完整路线，失败仍原搜索；不复用旧预算或续源戳，实际普通派发仍走完整能量/hold/返回门槛。

原晚段TB3在永久blocker恢复中被改派正式final(-4.52,2.08)，旧代码只清blocker的return_yield关联，未清waiting beneficiary的旧关联/yield/probe。原410.9与428.2真实导航旁录仍标为local_return_yield，晚hold诊断allACTIVE且yield_targets仍tb2/tb3。它保留visible-only短腿和目标/集合能量例外，原读者未检查这个意图转换，所以18原PASS完整保留，未来新增角色/改派旁录与读者约束。该机制并不证明独自修复就完成任务；原TB3末距final3.366m，TB2尚在临时refuge且final误差.494m，只有新原任务能验证完整收敛。

完整gate、three原strict PASS、18原组件、原私有/安全账本、四份冻结字面源、全部原文件SHA和条件诊断压缩归档，大型CDR/log留原目录。17正式、新同冻结物理对子、917未调用。原300s/5s/TTL/净空/能源/次数/Nav2/SLAM/物理保持。P2C.1未完成，无P4/ns-3/Wi-Fi/RL。

[JSON](20261010_p2c_v63_failed_development.json)
