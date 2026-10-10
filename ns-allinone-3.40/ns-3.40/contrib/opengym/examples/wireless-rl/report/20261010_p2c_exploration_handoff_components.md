# P2C.1 探索候选几何交接组件 PASS

[v56四原FAIL](20261010_p2c_v56_failed_development.md)保持：forced原生COMPLETE214.8/双charge1并原生5秒保持PASS；lab/rooms未发现且0charge、EXPLORE timeout300.2，corridors RALLY timeout300.2。四零接触耗尽失效、72独立子审不代整体FAIL，owner/observer0关闭，17正式/新物理/917均未调用。

原lab/rooms重复原源lease过期后，完整规划又从头开始。新仅在规划过期时保留各机最多128个候选(x,y)点，按已准确计分点在前、其余原效用上界点随后，去重并剥离价格/路径/Assignment/源授权。它是搜索偏好，不是待发指令。原10秒TARGET_HISTORY仅限制软偏好在准入起点的寿命，不续任何应用数据lease；phase/search/参与集合/目标变更即丢弃。

下一原串行回调重新生成当前map/pose/history候选和完整raw充电lookahead池，再用下一3个偏好点/原1.2m选择每机最多3个当前候选；没有邻近点则选当前top3效用上界。仅当前Assignment进入原准确ray gain、相对/局部/空间偏好、完整身体路、当前和端点contact返路、等待和能源预算、最终2/5/60秒源龄核验，bound不派发。原lease未过期才推进cursor。此过期恢复有意比较子集，不能声称全目录原贪心排序/全局最优或所有选择等价；全raw充电lookahead不截断。原无过期分支六份原输入完整规范化结果逐字一致。

原refuge逐点KDTree净空查询改同一批次查询，原谓词、候选顺序和后续身体/预约资格保持。只1中央assign_idle_robots和1纯rally_yield_pose修改，新增2纯函数，82其他中央/97其他纯/globals/native七类保持；原300s/5s、2-5-60s、0.45端点/0.35路/1.8预约、5m腿/30s原生超时/次数、Nav2/SLAM/扫描/物理不改。

六份原弃置输入绑定24原CDR源图。固定epoch/空缓存/合成端点比较非实时回放。另以相同合成刷新规则重交原几何输入：旧lab中期和rooms中后期四次租约仍过期，新第二次小池用0.268..0.393秒产生当前合格动作；早期无可行方案仍无动作。这不是实际DDS/任务反事实或最坏时限，也不声称恢复时选择与原完整目录一致。prototype与最终生产仅增加两项私有准入元数据，原源码均归档。

真实DDS六场景使用同一价格计数触发clock10→13。旧和新首轮原源10均过期零goal/charge，新仅保存点。新交付13后旧完整池再clock13→16过期；新小池触发1必要充电。资金充足新分支以新gain1200/utility600派1实际NavigateToPose goal并Future闭合；TF仍10、当前地图变全占用、完整预算无法支付三反例均零goal/charge。独立实际派发与完整outbound读者PASS；原充电预约DDS三兼容场景PASS。合成候选/地图/ActionServer不是真实Nav2物理任务，九场景全部owned关闭。

1858功能187.33秒、13新定向、四包6.25秒、190保护6原授权54协议、两声明PASS。先前LRU、distance/veto、local funding proof、segment veto、early body/own proof、mapped lower-bound多种试验收益不稳定/更慢或不足，均未采用。segment通用浮点边界等价未建立；不能据六快照相同推广。初11测试JSON tuple/list断言失败、两临时脚本构建失败及两distance JSON字段覆盖均原样保留；源码归档可以重建。

新v57须同clean pushed源码4开发→17正式+2原物理格；15非留出与新物理全PASS后才首次917。组件PASS不替代完整P2C.1验收，无P4/ns-3/Wi-Fi/RL。[JSON](20261010_p2c_exploration_handoff_components.json)与provenance保存源/临时试验/原输出/失败/声明和SHA，原大型任务输入留在v56目录。
