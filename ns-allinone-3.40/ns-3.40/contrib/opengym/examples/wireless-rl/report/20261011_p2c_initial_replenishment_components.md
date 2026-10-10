# P2C.1 一次近充电区初始补能组件

组件PASS，完整P2C.1未完成。原v70同a383cda四格：forced COMPLETE247.4/rooms COMPLETE251.9完整strictPASS；lab RALLY300.3/corridors EXPLORE300.3timeout，整体strictFAIL保留。四格零接触/耗尽/FAILED，各20子审PASS，owner-observer0关闭、完整双图一致。17正式/两物理/917未调用。

新策略仅用于完整对象任务。机器人必须先有至少一个真实普通探索成功、native charge_count恰为整数0、当前电量低于原capacity×charge_target_fraction，且原近充电区.35m到2×charge_radius范围内，当前完整去返成本仍充足、容量能资助当前候选、保守local/fused机体路线可达原接触区。它以原充电目标为一次策略触发阈值；原实际候选去返成本单独保存，不能把80阈值称为物理任务消耗。

原request_exploration_charge继续先等待实际动作排空、完整1.8m返路清道，再按当前源重新预算/重查派发。原电池节点与消息类型保持；payload reason显式标为initial_near_home_replenishment，全部字节仍入账。补能后charge_count≥1恢复原四分之一/两前沿机会与缺电规则。无工作、spawn、未知接触路、过期/未来源、活动/返充/充电同伴、已充电、纯建图均不能据此获得新策略授权。

52新检查含七份原始近充电区快照与冻结旧budget函数对照，普通成功/清道区别、完整成本与阈值分离、当前/过期再预算及独立读者反例。旧14几何回归明确限定为已有一次充电后的条件，未虚称新策略与原初始充电决策相同。最终全功能2167检查303.36秒；四包symlink6.96秒、190保护/6历史授权/54协议、三31源声明PASS。只2中央方法修改，84方法/103纯函数AST与11原生/SLAM/observer/command源保持；门禁与owner各仅原check_one/main变化，cases/物理刺激/300s/5s/原TTL保持。

新私有读者绑定普通命令与成功回执、原生充电计数历史、当前完整去返成本、原接触曲线和原完整清道。四原118命令均在原2秒窗口内匹配最近且唯一的私有来源；计数按实际成功发生时间，跨主题记录顺序不能把未来结果变成既有工作，重复/清道/失败/缺命令/歧义来源不能增加证明。

实际隔离DDS：旧/新控制器各完成一次合成普通ActionServer/Future成功；无工作拒绝、clock11→14原源过期拒绝、实际新源14消费通过。旧版0请求/0原生充电credit，新版1策略请求，原生BatteryManager通过受控合成pose运动及真实Future完成1次credit，模型加入41.57131483926619单位能量、模型计程1.4513148392661783m；之后charge_count1的新请求被拒绝。全部节点/线程/Future关闭。保留实际map/odom/TF/请求CDR和native账本；零Gazebo或真实Nav2运动，不是物理补能/任务回放/因果时长收益。

首夹具非探索字段KeyError、错误用generated导致0快照、严格同头戳匹配的原0.1秒差拒绝，以及临时scope参考路径误替换FAIL均保留，分别修正证据夹具/来源匹配，不回填原任务。原v70全部失败与原账本独立归档。

新v71须同clean-pushed冻结4开发→17正式+2物理全严格验证；917未暴露。P2C.1未完成，无P4/ns-3/Wi-Fi/RL，actual airtime/J未测。

[JSON](20261011_p2c_initial_replenishment_components.json)
