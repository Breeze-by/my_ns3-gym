# P2C.1 v94 四原开发失败保留

冻结 `ee3845aebb86cb0615d856e34c7301432646b9e7`。完整开发 FAIL 保持，17正式和两物理与917未调用。所有任务、observer、门禁和组件读者退出后归档；不回填、不重跑、不跨版本合并成功率。

dev_forced2：原生COMPLETE/success=True，274.7999999999997秒，检测206.29999999999973/集合208.19999999999982，充电2/最低电量15.160929538918113，接触0/失效[]；strict PASS，25组件PASS，owner/observer=0/0，owned关闭。

dev_lab101：原生RALLY/success=False，300.2999999999997秒，检测214.79999999999973/集合218.0，充电3/最低电量23.675425694856333，接触0/失效[]；strict FAIL，25组件PASS，owner/observer=0/0，owned关闭。

dev_rooms202：原生COMPLETE/success=True，130.0秒，检测63.39999999999998/集合75.89999999999998，充电1/最低电量25.481472726809137，接触0/失效[]；strict PASS，25组件PASS，owner/observer=0/0，owned关闭。

dev_corridors303：原生COMPLETE/success=True，258.5秒，检测159.39999999999998/集合162.5，充电3/最低电量37.07191879362349，接触0/失效[]；strict PASS，25组件PASS，owner/observer=0/0，owned关闭。

原300秒/5秒/TTL/净空/物理与native完整预算保持。下一候选仍需新同源clean pushed四开发->17正式+两物理，917须前置严格通过。无P4/ns3/WiFi/RL，actual airtime/J与容量未测。完整原文件及导航CDR以40MiB分片可无损重组，JSON提供每片和整包SHA256。

[JSON](20261012_p2c_v94_failed_development.json)
