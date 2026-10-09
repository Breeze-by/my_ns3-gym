# P2C.1 v40 分阶段同伴预算排序界组件 PASS

v39冻结10860f4首forced原任务RALLY timeout300.4s，检测279.8/RALLY295.9s；双机各charge1、最低7.95590、零接触/耗尽/failed/任务期infra/retry。267 live与12独立审计PASS不能抵消任务失败；其余3dev/17formal/2physical/917未调用，全部原数据见20261009_p2c_v39_failed_development.md/.json。

这次先比较八个计算候选：空间历史折扣界、完全安全末段veto复用、距离场LRU、提前航段界、最后并发槽的精确前缀检查、同伴预算界、分阶段同伴界、同伴加历史组合界。前五个在两份原输入上没有稳定实质收益，未合入；LRU的cold样本无命中，不代表所有warm场景都无用。组合历史没有证明优于较简洁的同伴界方案，未合入。所有源码/输入/失败/样本保留，首prototype缩进解析错误发生在任何计算/任务前并保留。

采用有顺序的精确branch-and-bound：先用单条完整本地已知接触返路证明同伴资金，再解原精确gain，最后原全部预算/相对距离/空间偏好定价。自己的local返路是qualified候选之一，距离上界不小于所有qualified候选的最小距离；按原最大合法map5s/pose2s源龄定价，严格energy>upper时该同伴在本冻结租约内必能通过原名义预算。仅用这样已证明的同伴子集计算relative_travel_factor上界；未证明、不新鲜、缺本地图/完整返路或无效状态一律保留中性1，不丢候选。原已知全返路/原真实body路线完整预算、充电公平/全部池与lookahead、原stable greedy并列顺序与来源弃置保护均执行。这个upper budget从不进入实际命令或native能量许可。

八组准确历史AP输入各5次交错cold对照，全部实际选择/朝向/充电意图/预算/source epoch一致。v39两个中位.9409→.7397/1.4841→1.3858wall秒，v35corridors.6022→.5249；v35lab.7636→.8287、rooms.6671→.6919，v36三个低电量输入.8732/.8792/.8819→.8894/.9000/.9203，计算退化明确保留。该算法不是普遍加速保证，sim剩余来源时间不能直接与wall样本等同；prototype采用独立globals，部分临时计数wrapper被绕过，因此不把prototype调用计数当作跨算法成本证据。

新34checks与既有相关127PASS39.83s；完整1462PASS121.52s；追加来源在资金证明中到期仍撤销全部临时命令的检查后，35专门检查PASS6.97s，独立合计1463。验证12随机稳定排序/并列、8地图×16合法源龄下本地预算证明覆盖全部qualified最小返路、无效/未负担/本地unknown但融合可负担回退、可写地图改变重建、每级不得扩大上界、第二级拒绝不定价以及原弃置输入实际等价。四包build5.63s，171保护/4原授权变化/54static、8中央+2native Future注册PASS。

实际两个coordinator原fresh checks/选择/发布/序列化Future注册与独立DDS receiver：准确原地图均一致，3真实决策请求/3接收witness各自完整travel/预算/源龄审计PASS，frozen39选择完全相同；仅动作客户端是pending合成Future，无Nav2运动或Gazebo任务。实际独立DDS时钟/互斥普通状态/序列化action检查PASS，来源过期未被阻塞状态回调掩盖。源码仅lazy_priority_candidates、assign_idle_robots变化和新增local_peer_funded_for_lease；其余class方法/native/clock/TF/action/Nav2/SLAM/物理字节不变。原300s/.35/.05/.1/5s与2/5/60s TTL未放宽。

新clean pushed freeze先forced完整native及每机charge≥1，再另3dev；all4过才同freeze17formal+2physical，917最后首次暴露。组件改善仍未证明任务成功或真实最坏完成；P2C.1尚未完成，P3C.5已验收，无P4/ns-3/Wi-Fi/RL。
