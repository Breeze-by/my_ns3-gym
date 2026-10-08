# P2C.1 v20 本地 TF 前置筛选组件

组件PASS，完整任务门禁仍待新原始批次。v19完整四原批次两任务完成、实验室任务失败、走廊晚检测超时；这些FAIL和所有原输入保持，不重用成功格回填新候选。

既有机器人端tf_ingress_sampler新增/robot/battery/source_tf本地输出，只提取原map→odom，保留所有原相关transform及其源时间，包括重复/乱序/异常未来样本，交由完全不变的原生电池逻辑核验。原生订阅由launch remap到该本地输出；仍在网关损伤之前，断网不会关闭本地感知。原20/odom10/fused1队列、两个executor/串行状态组、2s/5s/128未来heap与完整能源/返航/充电函数逐字节不变。新增本地DDS转发不是AP可用观测或模型无线数据包；它也不是隐藏当前队列输入。

原始混合TF入口BestEffort缓存5→100，在机体突发期间先保留相关样本，仍按原源时间判过期。它可能改变通信模型之前的源可用性和实际轨迹/应用负载，不能声称真实新旧负载或时间完全相同；未来每个baseline必须共享冻结。原gateway/source_tf的observe分支除了新增本地publish外AST完全相同，相同输入序列（重复/乱序/未来）下原AP输出序列化字节一致；原gateway候选节流/生成器/协议/损伤参数不变。

实际DDS/domain218先尝试仅native rawTF改BestEffort20，紧密30body突发中未保留当前TF，FAIL保留；恢复native字节后，raw入口5前置筛选在1ms间隔压力下PASS，但同零间隔突发FAIL，不能将不同刺激作同等改进证明。最终入口100在相同30body零间隔突发PASS，native source50、可靠raw参考仅48；原过期输入不可预算、机体TF不续租、异常未来60不能阻挡随后有效53、TF不改距离计费/能量39.94/原odom3s。该兼容性参考是构造反例，不追溯证明v19实际publisher QoS根因，也不是硬件或任意突发可靠性保证。

源审计扩大唯一必要的第四文件tf_ingress_sampler，171其他源码/模型保持；原四任务常量与54协议格保持。33定向PASS1.52s，预检1035PASS71.96s，最终1035PASS72.37s、四包5.22s、actual AP DDS/domain221与两manifest validate-onlyPASS。新graph审计要求native订阅本地筛选输出、生产者绑定同机器人原TF及原AP输出、其他机器人/AP均不可消费native通道，六坏绑定反例及历史raw原scope保留。原physical刺激/50/60..250/62..248/.5m/1.1m/300s不变；4开发先全通过，再17正式与两物理，917未暴露。P3C.5已验收，无P4/ns-3/Wi-Fi/RL。完整失败/源码/当前PASS/SHA/无损附件见JSON。
