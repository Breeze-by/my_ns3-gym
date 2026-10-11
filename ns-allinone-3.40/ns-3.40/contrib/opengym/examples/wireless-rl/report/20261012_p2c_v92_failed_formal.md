# P2C.1 v92 四开发通过、正式首格失败保留

冻结 `b851a57148cc3a506750e8258e60a31f9712a610`。四个开发原任务原生COMPLETE并通过完整canonical门禁；条件目标信息勘察实际执行两次。正式首格lab101在266.6秒检测、270.8秒进入RALLY，300.4秒截止仍未完成原生保持，严格FAIL。全部owner、observer、门禁及组件读者关闭后归档，原结果不回填、不重跑。

development/dev_forced2：原生COMPLETE/success=True，231.29999999999973秒，检测164.0/集合166.0，充电2/最低电量9.586591999715303，接触0/失效[]；strict PASS，owner/observer=0/0，owned关闭。

development/dev_lab101：原生COMPLETE/success=True，243.79999999999973秒，检测135.9000000000001/集合149.29999999999973，充电3/最低电量19.806481080111034，接触0/失效[]；strict PASS，owner/observer=0/0，owned关闭。

development/dev_rooms202：原生COMPLETE/success=True，168.09999999999997秒，检测92.09999999999997/集合110.39999999999998，充电2/最低电量21.83366980813214，接触0/失效[]；strict PASS，owner/observer=0/0，owned关闭。

development/dev_corridors303：原生COMPLETE/success=True，201.20000000000002秒，检测110.30000000000001/集合113.6，充电1/最低电量27.853715226018853，接触0/失效[]；strict PASS，owner/observer=0/0，owned关闭。

formal/fixed_lab_101：原生RALLY/success=False，300.4000000000001秒，检测266.60000000000036/集合270.8000000000002，充电3/最低电量24.050929287673206，接触0/失效[]；strict FAIL，owner/observer=0/0，owned关闭。

四开发完整PASS不代替正式首格FAIL。晚检测与剩余集合时间是原始观测描述；原因仍需读原始搜索输入、导航和native可见性证据。任务期与清理退出、完整源龄、原预算及返回预测均按原记录保留。

余16正式（含两917）/两物理未调用；原300秒/5秒/TTL/净空/物理/native预算保持。下一候选仍须新同源clean pushed四开发→17正式+两物理，917仍须前置严格通过。无P4/ns3/WiFi/RL。五任务全部原文件及导航CDR以40MiB分片可无损重组，JSON提供每片和整包SHA256。

[JSON](20261012_p2c_v92_failed_formal.json)
