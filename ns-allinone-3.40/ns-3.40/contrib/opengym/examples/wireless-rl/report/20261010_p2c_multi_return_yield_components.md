# P2C.1 同时返航让行组件 PASS

[v57四原FAIL](20261010_p2c_v57_failed_development.md)保持：forced原生COMPLETE266.7/双charge1和rooms140.0/0charge均有native5秒51样本；lab FOUND timeout300.4且tb3第二原生return未闭合，corr RALLY timeout300.2。四零接触耗尽FAILED、70原子审PASS/2原失败及owner/observer0均归档；17正式/新物理/917未调用。

corr原23次清道22 CANCELED/最后1 SUCCEEDED。首276.7秒tb1/tb2均RETURNING/count2、两条完整受保护返路已核验，旧Future/心跳却只豁免名义owner，另一返航机器取消该让行。新准入保存已合格受保护返路对应的native return_count：当前RETURNING绑定当前计数，原ACTIVE申请返航者绑定下一计数；CHARGING同伴不授权下一返航。接受真实Future和电池回调仅对这些既有完整路径/同一周期豁免，计数变化、未覆盖返航、helper自身返航或普通探索仍按原取消。旧格式兼容仍只豁免原单owner，所有新生产准入包含明确周期字段。

原完整返路、0.35m身体出路、1.8m端点和沿路单调离开、当前与端点完整去返预算、最后2/5秒源龄等准入完全保持。新增私有元数据由独立读者从保存原mode/count和重建的全部完整路径重新推导，缺少/多加/改周期均拒绝；没有新增无线应用流、地图操作或改变原身体矩形。只有3中央方法和1新纯谓词，80其他中央/100原纯、globals/native七类、调度/gain/搜索几何/预算/TTL/300s/5s/次数/物理均保持。

真实隔离DDS七场景以原v57首让行地图/位姿/能量、合成刷新源戳和实际ActionServer/Futures重核验准入：旧1goal立即取消；新1goal在两原return周期心跳后保持并SUCCESS且不计普通探索；新周期、未覆盖return、helper自身return各1goal取消；源10在clock13过期与fresh但资金0.1各0goal。真实派发由独立preparation/outbound读者重建，全部Future/线程/节点关闭。原单返航DDS两场景兼容PASS。合成刷新原几何不是原任务回放、真实Nav2运动或任务因果收益证明。

原23清道全部本机/同伴return_maps及原融合源和规划图共184见证，与67原同header键CDR严格绑定；计数是唯一header键数量，不是内容版本数。原保存几何加周期元数据的条件重建PASS，不回填原动作结果。

另修正只读outbound bind_original_maps：每份见证必须在实际同header CDR中独立找到原shape/resolution/origin和完整逐格内容匹配。规划图仍只允许原声明的isolated占用own-cell→0，原尺寸、8邻域及全部改格必须一致，找不到任何一个见证即FAIL；不能用一个版本满足另一不同内容见证。7新重复header反例与原11篡改/路径检查共18 PASS。lab原426格差异版本与完全相同版本同header、同receipt且都早于派发；独立复核31决策/895点/59header PASS，原第一次读者FAIL、native返航未闭合和任务FAIL均保留。gateway因果和应用源龄独立继续核验，此绑定本身不证明唯一内容版本交付，更不证明Nav2按规划点执行或全程地图连通。

1876功能202.93秒、11新周期定向/18outbound读者、39原准备/串行定向、四包14.5秒、190保护6原授权54协议、两声明、7实际DDS+2兼容PASS。初不存在的测试文件、两轮夹具错签名、失败的inline替换、首full ordinary夹具属性失败及诊断NumPy坐标JSON失败均保存；最终生产与运行时SHA一致，没有中间任务调用。

新v58须同clean pushed源码4开发→17正式+2原物理格；15非留出和新物理全PASS后才首次917。组件PASS不代完整P2C.1验收，无P4/ns-3/Wi-Fi/RL。[JSON](20261010_p2c_multi_return_yield_components.json)与provenance保存原输出、初失败、字面源、声明和SHA。
