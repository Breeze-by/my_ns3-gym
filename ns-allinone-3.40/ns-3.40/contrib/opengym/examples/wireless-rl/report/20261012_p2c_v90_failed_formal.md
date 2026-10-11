# P2C.1 v90 开发四原通过、正式第二原格失败保留

冻结 `ad5f32e17f00b8d14c8a1fa4ee45d9947cb022aa`。原四开发完整门禁 PASS，目标信息勘察实际执行两次。正式 lab101 原生 COMPLETE/严格 PASS；第二原格 lab202 在299.7秒检测目标，300.1秒截止仍 FOUND，严格 FAIL。任务仍未完成，全部原始结果保持，不回填、不重跑。所有任务、observer、门禁和组件读者退出后归档。

development/dev_forced2：原生COMPLETE/success=True，187.30000000000018秒，检测125.0/集合139.60000000000036，充电2/最低电量11.856158570852667，接触0/失效[]；strict PASS，owner/observer=0/0，owned关闭。

development/dev_lab101：原生COMPLETE/success=True，291.10000000000036秒，检测208.5/集合222.9000000000001，充电3/最低电量30.00177918484532，接触0/失效[]；strict PASS，owner/observer=0/0，owned关闭。

development/dev_rooms202：原生COMPLETE/success=True，265.70000000000005秒，检测146.9/集合194.70000000000002，充电2/最低电量25.44423225664827，接触0/失效[]；strict PASS，owner/observer=0/0，owned关闭。

development/dev_corridors303：原生COMPLETE/success=True，274.0秒，检测154.20000000000002/集合160.20000000000002，充电3/最低电量29.366345710797724，接触0/失效[]；strict PASS，owner/observer=0/0，owned关闭。

formal/fixed_lab_101：原生COMPLETE/success=True，263.60000000000036秒，检测153.0/集合158.5，充电3/最低电量17.88647019636039，接触0/失效[]；strict PASS，owner/observer=0/0，owned关闭。

formal/fixed_lab_202：原生FOUND/success=False，300.0999999999999秒，检测299.6999999999998/集合None，充电3/最低电量20.433589135421652，接触0/失效[]；strict FAIL，owner/observer=0/0，owned关闭。

失败 lab202 的25组件读者PASS，包括38探索/21实际朝向补查/32过期计划弃置。46原生Nav2目标41成功/5取消/0abort。任务期零子进程非零退出，停止后lifecycle_manager退出-9原样保持。补能完成不替代任务成功；现有计数不证明延迟的因果。

余15正式（含两917留出）/两物理未调用。原300秒/5秒/TTL/净空/物理与native完整预算保持。下一候选需新同源clean pushed四开发→17正式+两物理；917仍须前置完整通过。无P4/ns3/WiFi/RL。完整原文件及导航CDR以40MiB分片可无损重组，JSON提供每片和整包SHA256。

[JSON](20261012_p2c_v90_failed_formal.json)
