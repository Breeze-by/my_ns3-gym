# P2C.1 v83 原开发 FAIL 保留

冻结 `25f45dc9778c3227c24c77ee0a2c6110a611f575`。完整P2C.1仍FAIL；所有原任务/observer/读者关闭后归档。

dev_forced2：原生success=True/COMPLETE，215.29999999999973秒，检测149.5999999999999/集合152.0，充电2/最低15.091204571185639，接触0/失效[]；strictFAIL，23组件PASS，组件错误{'initial_replenishment': 'Traceback (most recent call last):\n  File "/tmp/audit_p2c_v83_components.py", line 55, in <module>\n    try:out[name]=check()\n  File "/tmp/audit_p2c_v83_components.py", line 31, in <lambda>\n    \'initial_replenishment\':lambda:initial_replenishment_audit(ledger,True,directory/\'safety_events.jsonl\',True,directory/\'navigation_inputs.jsonl.gz\',True,True,True,True,True,True),\n  File "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/p2c_initial_replenishment.py", line 59, in initial_replenishment_audit\n    reservation_waits = audit_first_window_reservation_waits(window_waits, native, require_reservation_wait)\n  File "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/p2c_initial_replenishment.py", line 156, in audit_first_window_reservation_waits\n    assert any(row == state for row in native[e[\'robot\']]), \'wait lacks original native battery source\'\nAssertionError: wait lacks original native battery source\n'}。原任务期/关闭进程日志与全部账本保持。

17正式/两物理/917未调用；原300秒/5秒/TTL/物理与native完整去返预算保持，继续依据原失败处理。无P4/ns3/WiFi/RL。

[JSON](20261011_p2c_v83_failed_development.json)
