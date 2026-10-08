# P2C.1 v21 有限前沿接续评分

组件PASS，任务门禁仍待新冻结原始批次。v20 forced超时FAIL和全部历史失败保留，不重用旧成功格。新候选仅改变普通探索候选排序：在当前已交付地图中仍有用、距离旧意图≤1.2m、gain>max(200,20%旧gain)、完整能源可负担的接续候选，评分为原adjusted_utility的2倍。其他候选为原评分，收益明显更高的新前沿可以替代旧意图；原成功短前缀记忆、普通失败清理、真正到位清理及充电公平机制保持。

原名义路径效用/近同伴软折扣保留，实际派发仍重新检查完整机体绕行、已接受导航预约、全程往返能源、源TTL与原短腿。排序用名义utility，不能视为真实导航时间预测或全局最优。追加私有group id/size、原排除点、base utility、有限权重和最终score，读者从交付地图重建frontier group/gain/nominal distance，再核验reuse/base/relative factor/weight/score；同时篡改base和score、伪造group/exclusions等坏例拒绝。该旁录不是新增AP观测或无线消息；未保留所有原候选与历史，故不宣称原时刻全局最大选择已证明。

103探索定向PASS13.14s（初102PASS8.91s保留），追加完整图采集检查，完整1048PASS76.93s、四包5.27s、171保护/4授权/54协议与actual AP DDS/domain221 PASS；普通/物理manifest validate-only未启动Gazebo。旧启动图在原required application集合发现后即捕获，未要求native节点。新可选只读observer待全部原生电池消息与完整原required节点/TF端点可见才另存native_graph.json；不延迟任务或更新源时间，原启动图保持。源摘要绑定observer/helper，缺图或未知来源仍FAIL。除assign_idle_robots，70其他中央方法AST、整个native电池、TF入口与launch逐字节保持。保存v20原交付地图的条件夹具中，新评分选择更高收益且完整预算合格的新前沿，旧v18有价值接续夹具仍通过；均非完整原始history/reservation反事实，更不代替任务成功。

需要新clean pushed freeze后先全部4开发；通过后同提交17正式、两原物理远端断网返航，917最后首次暴露。300s/.35m/.05mps/.1radps/5s、所有TTL、SLAM/Nav2、物理模型与旧50/60..250/62..248/1.1m/.5m刺激保持。P3C.5用户已验收，P4/ns-3/Wi-Fi/RL未开始。源码/验证/无损SHA附件见JSON。
