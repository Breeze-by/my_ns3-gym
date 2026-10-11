# P2C.1 v81 原开发 FAIL 保留

冻结 `b9ef25542d498b3a076f8bd350519298a974345b`。完整P2C.1仍FAIL；所有原任务/observer/读者关闭后归档。

dev_forced2：原生success=True/COMPLETE，189.69999999999982秒，检测129.0/集合130.9000000000001，充电2/最低15.219522497292633，接触0/失效[]；strictPASS，24组件PASS，组件错误{}。原任务期/关闭进程日志与全部账本保持。

dev_lab101：原生success=False/FOUND，300.1999999999998秒，检测234.69999999999982/集合None，充电2/最低17.642678836400222，接触0/失效[]；strictFAIL，24组件PASS，组件错误{}。原任务期/关闭进程日志与全部账本保持。

dev_rooms202：原生success=False/EXPLORE，300.1秒，检测None/集合None，充电1/最低30.44628939813171，接触0/失效[]；strictFAIL，23组件PASS，组件错误{'native_return': 'Traceback (most recent call last):\n  File "/tmp/audit_p2c_v81_components.py", line 55, in <module>\n    try:out[name]=check()\n  File "/tmp/audit_p2c_v81_components.py", line 35, in <lambda>\n    \'native_return\':lambda:g.return_audit(directory/\'safety_events.jsonl\',True,True,True,directory/\'navigation_inputs.jsonl.gz\'),\n  File "<frozen frozen v81 gate>", line 229, in return_audit\nAssertionError: (\'unclosed return prediction\', {(\'tb2\', 2)})\n'}。原任务期/关闭进程日志与全部账本保持。

dev_corridors303：原生success=False/RALLY，300.4秒，检测286.9/集合291.9，充电3/最低19.509880463346224，接触0/失效[]；strictFAIL，24组件PASS，组件错误{}。原任务期/关闭进程日志与全部账本保持。

17正式/两物理/917未调用；原300秒/5秒/TTL/物理与native完整去返预算保持，继续依据原失败处理。无P4/ns3/WiFi/RL。

[JSON](20261011_p2c_v81_failed_development.json)
