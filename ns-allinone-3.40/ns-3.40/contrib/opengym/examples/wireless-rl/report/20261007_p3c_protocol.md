# P3C 实现与验证协议

用户于2026-10-07验收P3B.5并授权完成P3C，同时新增实时通信故障控台。本协议在新任务运行前写入；当前为实现中，不声明实验通过。

范围：复用现有GatewayEnvelope、固定故障模型、账本及Qt依赖。默认启动独立只读指标进程和GUI监控；headless关闭GUI但继续输出同一指标。配置控台通过独立原子配置服务调整上/下行丢包、延迟、重复、乱序、ACK等待、有限重试、队列容量、类别丢弃和blackout，不发布任务/Nav2/电池/速度指令。模式和实际配置有版本、生效仿真时间及曲线标注；在途attempt保留发送时配置，后续attempt使用新配置，队列不清空、源时间不续租。启动seed和全部任务TTL/deadline/原生保持/安全门限不可通过控台修改。

指标定义：逻辑消息与attempt分开；ACK及外部导航消息以首次enqueue作为生成证据，明确区分显式generated与推断generated。独立报告唯一transport交付和receiver accepted；goodput使用有效accepted payload，attempt PDR使用已结算发送尝试，避免跨窗口排队使PDR超过1。无交付时AoI未知；freshness从源时间及原TTL计算，缺信息不填零。延迟使用源/准入/发送/交付时间，低样本p95/p99保留null与样本数。所有曲线使用仿真时间、元数据和配置版本。

验证顺序：

1. 组件验证：守恒、ACK/重试/重复/乱序/TTL/溢出、无交付AoI、低样本分位、配置原子拒绝及在途语义；原54协议矩阵与任务组件回归。
2. 只读回放已验收P3B.5原始ideal、10%、100%、TTL、overflow及partial任务，保留原结果/hash；生成逐类CSV、JSON、事件及同seed对比图、TDI/RMST。原始数据不重跑或回填。
3. 冻结clean/pushed实现后运行新的Gazebo实时配置实验：零损起始→独立上行丢包→下行延迟→全断→恢复，实际配置服务ACK、账本、曲线和安全/任务事件同步。保留全部真实任务结果，不要求强故障人为成功。
4. GUI实际渲染、文件回放与headless同源比较、运行图与源码只读/无旁路审核；新ideal任务及强制充电回归确认监控未引入控制语义变化。所有owner自然结束并关闭后才编辑源或归档。

正式新实验仍为300s、.35m/.05mps/.1radps/5s；控制/battery/evaluator/Nav2/SLAM/world字节与已验收基线比较。101/202/303为集成seed，809已暴露。P3C曲线是应用层消息敏感性，不能称作Wi-Fi PHY/MAC性能；P3C完成后提交验收，P3C.5/P4不在本次范围。
