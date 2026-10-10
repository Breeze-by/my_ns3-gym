# P2C.1 v60 四原开发整体 FAIL

同冻结 `41f6d86b2ac05712e3bc392e39dd5a1e0f58d4c5`，生产control SHA `e3824ceed94dd3e99e30dbcb4303c4f9ed2075b91994f454c18ccab66c0ec8a1`。四原owner/observer均0关闭后才修改。

|原场景|原生结果/秒|检测/集合秒|charge总数|最低电量|原生goal 成功/取消|原生保持|
|---|---|---|---|---|---|---|
|dev_forced2|COMPLETE 218.9|96.7/133.7|2|15.384717|20 17/3|5.0s/51样本|
|dev_lab101|RALLY 300.1|62.1/94.8|2|21.334932|32 26/5|None|
|dev_rooms202|FAILED 185.9|56.6/None|0|21.577502|17 14/3|None|
|dev_corridors303|COMPLETE 280.9|88.6/106.3|2|25.214837|41 32/9|5.4s/55样本|

forced/corridors完整strict PASS，lab300.1秒RALLY timeout与rooms185.9秒rally_survey_failed:tb2使整体strict FAIL。四格零接触、耗尽、FAILED机器人和原生abort；原任务期/停止后子进程退出分别保留，不把owner0等同全部子进程优雅退出。

rooms原56.6秒发现后目标(5,3)在全部11份原融合图均unknown，原LOS检查导致集合候选为零。原9次真实勘察包含3信息勘察和6后备勘察，全部原次数保持。最初原tb3当前几何可沿已知自由完整机体路径2.421m到达高收益观测位，而旧直视前缀约0.174m，低于原0.35m移动门限；因此原调度转向较远tb1。原tb3全程预算与路径的条件检查只是组件机制，不是原live callback/任务因果反事实。不得修改unknown格、目标LOS、物理/扫描或原尝试次数。18独立子审PASS不替代任务。

lab原62.1秒检测、94.8秒RALLY；有7个普通RALLY派发，但300s内无原生5秒完整保持。17独立子审包括native_return闭合PASS，原rally_proposals读者FAIL。2218.682秒提案生产咨询每机地图选择tb1/tb3/tb2，却没有记录这些地图；旧读者只拿融合图重算，不能支持该顺序。原失败保留，未来新增私有实际咨询图及源戳并绑定原CDR；没有用修正读者回填旧PASS。原源等待还存在，不能将其归因唯一计算方法或声称新提案旁录会解决任务超时。

四原完整结果、first/full strict gate、两完整strict PASS、lab17PASS/1FAIL、rooms18PASS、私有/原生安全账本、诊断与全部原文件SHA压缩归档；大型原CDR/日志保留原目录。17正式、新同冻结物理对子、917均未调用。原300s/5s/TTL/native/Nav2/SLAM/物理保持，P2C.1未完成，无P4/ns-3/Wi-Fi/RL。

[JSON](20261010_p2c_v60_failed_development.json)
