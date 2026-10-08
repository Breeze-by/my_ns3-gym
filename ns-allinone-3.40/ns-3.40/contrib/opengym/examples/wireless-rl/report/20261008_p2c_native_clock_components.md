# P2C.1 v5 有界原生时钟暂存与能量账本（2026-10-08）

**847功能PASS/1skip、四包5.39秒和172保护/54协议通过，待新推送冻结与完整任务门禁**。v4真实DDS源领先/clock导致的电量冻结原失败保留。新候选用标准heapq暂存原生odom/TF，最多128项、源领先最多原2秒，真实clock成熟后按原源戳处理；不续租、不使用未来数据、不重复结算。超过有界缓存明确正能量失败。组件/source/hash/原stdout/前瞻manifest详见[JSON](20261008_p2c_native_clock_components.json)。

实际ROS/DDS domain209夹具先交付source10.025的odom/TF（TF validity12.025、真实offset2），clock10.0时只能暂存；clock10.1后原source成熟并得到有限预算；source10.125的0.1m运动到clock10.2时仅计一次0.1m+.1s能量，40→39.898；同原样本重放不再扣费。初始缺姿态先停止等待，成熟后在站内且已负担原返航预算时恢复ACTIVE、charge0，避免初始补满。缺姿态/失路30秒停止失败、2秒原姿态源TTL、5秒地图TTL、.35m净空与300s/5s原生门槛保持。

新增每5秒native只读能量账本记录累计距离、计费时间、充电重置增量、原两源戳与暂存项数；不送AP，不加网络控制或数据流。严格读者重建energy=max(0,initial+charge credits-distance×move-idle×time)，检查源不在未来与累计量单调，并拒绝“真值已运动但本地计费为零”的冻结反例。这是仿真模型单位账本，不是实际radio/robot joules或全局安全认证。

109定向/4.15秒后加入账本与启动等待，完整847PASS/1skip（首22.07秒、最终22.52秒）、四包最终5.39秒、source172/54均通过。actual negative disconnected/stale-frame仍独立通过；control完整路径/连通逃离/两前沿算法与f637f64相同，192CPU组件无需无变化重复。新4开发/17正式/两blackout待运行，917未暴露；v1/v2/v4失败、v3partial和accepted P3C.5保持，无P4/ns3/Wi-Fi/RL。
