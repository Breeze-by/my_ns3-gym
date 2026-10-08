# P2C.1 v14 四原始开发 FAIL

冻结 `1a30fc76c8a583b1547fbcbf01a980011e8cdaaf`，同源码四原始自然闭合，无重试或回填。

| 原格 | 原生结果 | 时间/s | 充电次数 | 最低电量 |
|---|---|---:|---:|---:|
| forced2 | COMPLETE | 285.2 | 2，各一 | 10.092515 |
| lab101 | COMPLETE | 245.9 | 2 | 24.882625 |
| rooms202 | COMPLETE | 275.7 | 1 | 18.809636 |
| corridors303 | RALLY timeout | 300.4 | 1 | 27.205247 |

四格零接触、耗尽或机器人失效，owner/observer均0。三成功格完整协议/graph/live/预算/能量/私有分配审计PASS；走廊严格任务FAIL。走廊独立能量、AP否决/选择/重选/前瞻审计PASS，native最后一次返航未closed，严格FAIL保留。已有成功不移植到新源码候选。17正式/两断网/917未运行。

走廊目标82.1s发现、86.3s集合。末段tb3记录18次反复暂停/恢复，最后第19次RETURNING未closed；tb1末速0.184783m/s，不能替代原0.05m/s保持。不能只凭位置误差达标称成功。

末段99条原网关frame交付源龄最多0.142s；同一native能量快照时，最近已交付frame源龄约0.04..0.634s，native frame源龄多次2.034..2.235s。原输入与算法路径仍在，提示native20条TF接收队列积压，尚无native callback receipt trace，不能把它当单因素任务收益证明。SLAM原代码每次scan更新原header并由publishTransformLoop保留该scan stamp+原validity offset，本次不改SLAM、不续源戳或放宽TTL。

首只读诊断把网关sender误作robot而输出0frame；原空诊断保留，改正确字段后重读同原文件得到99条。原始SHA、展开命令/环境/config/source、所有成本与源龄证据及无损附件见JSON。P3C.5已验收，无P4/ns-3/Wi-Fi/RL。
