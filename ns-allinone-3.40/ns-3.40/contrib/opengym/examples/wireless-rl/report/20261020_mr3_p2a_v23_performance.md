# MR3 P2A V23 性能剖析与短容量

用户在V22闭合后答复“按你的想法继续”，授权推进已提出的性能剖析/提速路线；本次[范围记录](assets/20261020_mr3_p2a_v23_performance/scope_acceptance_v1.json)将执行限定为一次新短profile、基于测量的等价优化，以及一次新冻结的短1/4env容量。V22旧FAIL、无实际四环境、仅前缀验证及原件不变；本轮不重跑旧run、不训练、不消费pilot/final-only、不启动原生/gateway或扩额。

入场43261.8239849376018/52000，余8738.1760150623982秒。本轮分别最多600秒profile及1800秒short activity，二者总预约2400秒，最坏仍余6338.1760150623982；每项独立审计、性能数据消费者和外部尾均计入自身真实engineering区间union，nested不重复收费。纯stub/CPU准备与封存不提供正式或原生信用。

## 两次新活动的预声明

profile仅1env/open101/seed101，随机动作seed41，在真实前序mask上均匀choice、最多8次attempt/1EP；MR3Env max_steps=8，第8次真实外部截断并完成取消/result尾。显式cProfile仅此活动启用，worker/evaluator分别保存pstats，保留非零退出/异常；不得把受剖析开销影响的速率当无剖析容量，不把两进程等待或嵌套函数累计时间相加。profile全活动600秒：conformity60、独立review20、collection240、独立audit120、profile report40、external120为阶段最大预约；每阶段仍先留180秒合作清理尾及120秒external，时间不足SKIP/FAIL，不能用max1强行入场。

profile通过当轮源绑定/6条原件+3合成/独立review/完整本EP因果审计和真实关闭后，才按实测热点选择简单优化。任何真实安全、时钟、IPC或forced close问题均停止新增活动，不以capacity补profile失败。不做新的PPO或95%准入主张。

优化后short activity另freeze、clean commit/push及当轮符合性，1env与4env各跑固定open/rooms/corridors×101/103，每worker六EP、每EP最多8步，共最多30EP/240attempt；每env为三机器人。group1与group4分别400/800秒的collection窗口，另留audit300/external120及准入清理尾；总活动1800秒，sourcecheck/关闭超尾照实收费。global collection按实际collector启动+1200秒，两个组仍共享240计数和绝对活动截止，不让前组耗尽后组时间。预算窗口用尽正常关闭可继续后组，完整性保留FAIL；任何真实执行/安全异常全局停止，不重试、补cell或增加seed。

所有新活动只有当全预声明cell、动作/输入/tensor/奖励时间/关闭/source和verified覆盖通过才PASS；profile只给单场短工程剖析信用，short只给固定短容量描述，不将8步外部截断当300秒/95%任务或长期训练可靠性。原门限、频率、扫描/地图分辨率、随机流、received-only与独立truth评价保持。

## 准备状态

尚未启动正式profile或新容量。剖析helper的12项dummy/stub CPU、Supervisor profile开关12项和worker/helper组合29项已通过，完整命令/源前后SHA/wait/console见assets checks；重复覆盖不累计独立项。预算/短规范审计和活动末账CPU准备完成后再freeze。具体实测、优化依据、正式结果与精确末账随后追加。

准备检查已完成：短规格/原审计组合34项与活动末账10项CPU通过，分别真实37.892244021/.653239656秒；支持正常提前终态不补样、错误停止、独立group窗口和raw/verified区分。所有检查源稳定，见[CPU清单](assets/20261020_mr3_p2a_v23_performance/cpu_preparation_index_v1.json)。本轮未改原_duration谓词、原频率/奖励/路径/真值边界；此处不预报正式PASS。
