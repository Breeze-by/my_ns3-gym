# P2C.1 v15 原始开发 FAIL

冻结 `4712c019080ed461a7968fc4e1ef53ba57bf2903`。首forced2原EXPLORE timeout300.0s，未发现目标/零充电，最低10.5761481453，零接触/耗尽/机器人失效；owner/observer0自然闭合。其他三开发、17正式、两物理断网与917未执行，没有重试或回填。

122个原生能量快照中110个frame源龄超过2秒，全部对应最近网关已交付源龄≤1秒；native源龄最大23.882秒，原网关frame交付源龄最大0.401秒。tb1/tb2最后第52/31次RETURNING未closed，完整原生返航reader严格FAIL，能量平衡PASS。仅原始输入配对，不是native callback receipt测量，也没有单因素任务因果结论。

v15全TF latest1不满足真实混合TF消费。相关map→odom可能被后续无关odom→body消息替换；该机制由后续混合DDS构造探针检验。不能把先前全相关TF组件PASS当任务PASS。所有原命令/环境/源码/图/账本/live输入/模型实际成本及readerFAIL以无损gzip和双SHA保留，详见JSON。P3C.5已验收，无P4/ns-3/Wi-Fi/RL。
