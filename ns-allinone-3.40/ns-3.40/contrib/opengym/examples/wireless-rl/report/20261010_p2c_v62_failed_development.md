# P2C.1 v62 四原开发整体 FAIL

同冻结 `df0f3fc3911dfc513369c7650de1237d817effa1`，四原owner/observer均0退出且PID不存在后才修改。

|场景|原生结果/秒|检测/集合秒|charge总数|最低电量|原生保持|strict|
|---|---|---|---|---|---|---|
|dev_forced2|COMPLETE 242.1|144.6/147.4|2|7.888501|10.4s/105样本|PASS|
|dev_lab101|COMPLETE 193.8|106.4/121.5|1|20.004397|5.0s/51样本|PASS|
|dev_rooms202|COMPLETE 158.8|60.9/79.7|1|25.097257|5.5s/56样本|PASS|
|dev_corridors303|RALLY 300.0|156.5/160.2|2|24.025428|None|FAIL|

forced/lab/rooms完整strict PASS不能替代corridors失败。四格零接触、耗尽和FAILED机器人，原任务期和停止后子进程状态保留；owner0不代表所有子进程无清理退出。corridors16独立子审PASS，native_return因tb1第2次返航未闭合FAIL，rally_proposals因原288.2秒记录缺tb2/pose_state及tb2/frame_state FAIL。tb2正在返航仍用于身体避让/顺序，原默认input_robot_names排除了其位姿/TF记录；未来必须核验全部原参与身体源，不能仅补字段而接受过期几何。

tb1原第2次返航首段完整返路7.212m，直视目标2.277m；随后完整返路4.883/4.762m，而直视目标降为.183/.026m，后四次约.027m。七原decision map严格复算均escape_vertices=1，短目标来自普通直视前缀。原返路仍有约4.76m完整已知contact路径；新的至多5m完整曲线前缀在七份原图上均通过原.35m连续净空。此为条件几何，不能证明Nav2实际沿各顶点执行或单独解释集合超时。原Nav2 xy_tol为.02m；初“膨胀逃离导致短段”解释已撤回，也不采用.25m成功无运动猜测。

四原结果、first/full strict读者、三完整PASS、16PASS/2FAIL、原私有/原生安全账本、诊断、冻结字面control/native/gate及全部原文件SHA归档，大型CDR/日志保留原目录。17正式、新同冻结两原物理、917均未调用。原300s/5s/TTL/native能量/次数/Nav2/SLAM/物理保持，P2C.1未完成，无P4/ns-3/Wi-Fi/RL。

[JSON](20261010_p2c_v62_failed_development.json)
