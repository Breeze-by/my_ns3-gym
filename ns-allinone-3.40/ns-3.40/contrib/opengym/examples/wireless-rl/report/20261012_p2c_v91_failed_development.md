# P2C.1 v91 四原开发失败保留

冻结 `10272ffcd49a5577e08e70faf244d3a1b8614d02`。完整开发 FAIL 保持，17正式和两物理与917未调用。所有任务、observer、门禁和组件读者退出后归档；不回填、不重跑、不跨版本合并成功率。

dev_forced2：原生COMPLETE/success=True，280.39999999999964秒，检测203.5999999999999/集合206.0，充电2/最低电量10.690056146507905，接触0/失效[]；strict PASS，25组件PASS，owner/observer=0/0，owned关闭。

dev_lab101：原生RALLY/success=False，300.0999999999999秒，检测182.19999999999982/集合185.69999999999982，充电3/最低电量21.39436949340923，接触0/失效[]；strict FAIL，25组件PASS，owner/observer=0/0，owned关闭。

dev_rooms202：原生COMPLETE/success=True，232.6秒，检测166.29999999999998/集合170.99999999999997，充电3/最低电量31.937095824448793，接触0/失效[]；strict PASS，25组件PASS，owner/observer=0/0，owned关闭。

dev_corridors303：原生FOUND/success=False，300.2秒，检测139.3/集合None，充电2/最低电量17.72298402265109，接触0/失效[]；strict FAIL，25组件FAIL，owner/observer=0/0，owned关闭。

原300秒/5秒/TTL/净空/物理与native完整预算保持。下一候选仍需新同源clean pushed四开发->17正式+两物理，917须前置严格通过。无P4/ns3/WiFi/RL，actual airtime/J与容量未测。完整原文件及导航CDR以40MiB分片可无损重组，JSON提供每片和整包SHA256。

[JSON](20261012_p2c_v91_failed_development.json)
