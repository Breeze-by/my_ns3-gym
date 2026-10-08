# P2C.1 v19 四原始开发 FAIL

冻结 `79f211323ade3e949f91ad3896e727beeeef7522`。forced2原生COMPLETE225.2s/两机各charge1，rooms202原生COMPLETE258.6s；lab101在181.5s原生任务FAILED，原因rally_survey_failed:tb2，三机无原生电池FAILED；corridors303在299.6s才检测到目标，未进入RALLY，timeout300.4s，总charge1。先前过程评论误称走廊为集合超时，在此明确纠正，原始数据保持。四格均零接触/耗尽/机器人失效，owner/observer0自然关闭；无任务重试/回填或阈值放宽。新17正式/两物理与917未调用。

严格四格门禁FAIL，forced与rooms的原始PASS同时保留。独立只读原输入审核四格的返航/能量/前瞻/AP否决/失败与成功分配/探索路径全部PASS；84返航触发全部closed、83pose预算、541能量样本、58实际探索/26接续/6相对距离折扣、12真实两前沿前瞻决定。全部native返航均零map路径重建/零local腿，三次charger-return发生于接触区；不充当远端断网返航证明。

lab第三机37个5s旁录中10个TF源龄>2s、最大2.712s、中位1.8675s，同刻网关源龄最大0.536s。第三机72次短缺路返航/恢复反复暂停目标区域survey；这是原记录相关现象，不能把survey失败或跨async时间差作单因素因果证明。其他三格没有旁录TF过期。原图没有publisher QoS，不能追溯声称QoS是确定根因。

首次只读辅助脚本把普通task-state字符串误按JSON解析，原trace/脚本保留；仅辅助TF样本抽取跳过非JSON普通字符串，再审核完全不变原文件，任务FAIL不变。一次push未结束的CLI调用被冻结校验在创建目录/启动子进程前拒绝，不是Gazebo原任务或重试。原命令/环境/图/地图/账本/live/native模型与SHA无损归档见JSON。P3C.5已验收，无P4/ns-3/Wi-Fi/RL。
