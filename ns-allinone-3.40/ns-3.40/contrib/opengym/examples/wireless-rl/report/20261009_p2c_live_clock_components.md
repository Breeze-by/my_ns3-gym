# P2C.1 v29 中央实时时钟及租约组件 PASS

勘误：该候选在任务前被拒绝，未执行任何原任务。原clock/普通状态/租约组件PASS仍有效，但不涵盖Humble Future动作完成回调，原串行判断过宽。详见[并发勘误](20261009_p2c_v29_concurrency_correction.md)。原版本保留在Git f0fe12c。

v28四原开发FAIL完整保留：强制272.6秒原生完成/两charge且首格严格PASS；rooms220.4秒原生完成但结果写入竞争导致runner1；lab300.3秒RALLY、corridors300.4秒EXPLOREtimeout，corridors末端返航未闭合。没有任务重试或回填。隔离真实DDS复现中央时钟机制：原single worker与只增two workers在0.6秒受控阻塞回调内，外部clock1.1→4.1而AP仍1.1，旧源假定新鲜；只将TimeSource现有clock订阅移到独立互斥回调组并使用two workers，AP完成时4.1，原source1.1过期。普通状态回调三种方案均未并发；原clock best-effort/depth1/唯一订阅保持。这个实验不声称真实CPU耗时、任务收益或无线测量。

新候选在候选生成/预算/路线/最终派发前检查原始source截止，并在提前充电/目标勘察/完整集合计划之后重新验证；过期或clock reset丢弃计算结果，不占用动作owner、不重写源时间。捕获rank/price/dispatch各自时刻，私有证据使用同一明确时刻重算各源年龄，所有预算系数和2/5/60秒TTL保持。旧cohort按原schema读取；新声明必须提供完整price/rank/source/TTL，严格审计同时拒绝未来计算、源后造时与到派发时已过期输入。关闭前停止新准入、取消timer并等待已有executor回调。result reader只对原producer尚未完成JSON作原有deadline内只读轮询，完整错误对象/producer退出/timeout仍FAIL；不改evaluator或任务期时限。

110定向PASS8.10秒；最终1207完整功能PASS90.24秒；四包5.30秒；171保护/4授权/54协议、两manifest、actual DDS clock和camera/survey/quiet/lapsed PASS。原初夹具/参数错误以及1171PASS/36FAIL完整日志保留，修复测试数据且几何断言不变。native battery、TF sampler、launch、observer、native graph全部相对b2字节一致；case参数/物理stimulus/300秒/5秒/关闭grace/安全门限不变。

这是安全时间语义修复，尚不能证明任务300秒通过。新同clean pushed freeze的4开发→17正式/2物理尚待；917未暴露，P3C.5已验收，无P4/ns-3/Wi-Fi/RL。
