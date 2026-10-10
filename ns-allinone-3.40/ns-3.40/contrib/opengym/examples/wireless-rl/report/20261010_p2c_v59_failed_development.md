# P2C.1 v59 四原开发整体 FAIL

同冻结 `978c8dda8102a155dd7c282988ad18787c0ab36b`，生产control SHA `e284836b14d0520979ca8c0b44dc30e03f137066b101f4ae84f18fbc6d3f4956`。四个原任务均owner/observer0、owned进程关闭后才修改源码。

|原场景|原生结果/秒|检测/集合秒|charge总数|最低电量|原生goal 成功/取消|原生保持|
|---|---|---|---|---|---|---|
|dev_forced2|COMPLETE 230.0|73.2/98.5|2|9.412376|20 17/3|6.0s/61样本|
|dev_lab101|RALLY 300.0|174.4/185.6|3|17.787580|43 37/6|None|
|dev_rooms202|COMPLETE 206.5|88.7/103.4|1|23.176166|25 21/4|5.0s/51样本|
|dev_corridors303|COMPLETE 224.9|79.8/85.6|2|28.650176|24 18/6|5.0s/51样本|

forced首严格gate PASS；rooms/corridors也由四场景严格gate完成全部子审并PASS。lab300.0秒RALLY timeout导致整体严格FAIL，三机各charge1、全部原native return周期已闭合，另18独立子审PASS不能替代任务完成。四格零接触、耗尽、真实机器人FAILED及原生abort；任务期和停止后清理退出由原summary分别保存，不以外层0宣称所有子进程优雅关闭。

lab原检测174.4秒，RALLY185.6秒。原4观察者handoff等待和6次“Draining rally legs to release an ahead robot's approach”，而原private ledger没有普通rally导航派发；观察者随后失去5秒健康确认并返充，60秒目标lease到期，原合法当前姿态盲扫描/当前地图前沿重获取未在300秒内完成。普通集合的未来优先级阻塞可触发map-safe重排，但旧分支只重置preflight后返回；常规真正重算要求无不就绪/充电机器人，观察者保留角色且资金不足使该条件长期不成立。拟修复只在无central accepted/pending RALLY腿时保存已有计算的未来顺序，并留到下个回调重查原完整准入。原输入条件推导不是精确回调重放，也不能据此断定新完整任务必完成。

原chosen地图和位置的条件排序中，未就绪观察者被原energy-ready排序放到最后，全局inversions仍可能保持2；这不等于修复全部冲突或一般死锁自由。验证重点是就绪同伴相对顺序与实际当前身体/返路/能量/源龄准入。

四原完整结果、first/full gate、三完整strict PASS、lab18子审、私有/原生安全账本、原timeline与条件几何、全部原文件SHA归档。原CDR及大型日志仍在原目录。17正式、新同冻结物理对子、917均未调用。原300s/5s/TTL/native/SLAM/Nav2/物理保持，P2C.1仍未完成，无P4/ns-3/Wi-Fi/RL。

[JSON](20261010_p2c_v59_failed_development.json)
