# P2C.1 首段探索与返航清道朝向

2026-10-11 P2C.1 v79四原整体FAIL保持：fcbc3f4 forced/rooms原生COMPLETE244.8/297.0，lab/corr原生RALLY300.0/300.2timeout；检测151.5/165.8，集合212.3/175.3，四零接触耗尽FAILED任务期infra、owner-observer0/双图同，24不同子PASS不替代整体FAIL，17+2/917未调用。lab原tb2三清道倒向充电点，corr首tb1探索越过初补能近家窗口，条件观察非任务因果。新未完成普通探索且nativecharge0时首段前缀按原2*radius/0.35m容差+一格对角线截短，完整前沿评分/去返预算不改；清道仅在原可见路径/完整去返/1.8m净空/2-5s源龄通过后按fresh位移朝向，零探索计数，普通相机/finalRALLY保持。2中央改/85其他105纯/native-SLAM-Nav2-SDF保持，1新纯偏好，独立读者绑定原状态/实际普通Future历史/原source与路径预算。2514功能395.40s/259定向37新/四包12.7s/190保护6历史授权54协议/三33源声明及actual DDS/Future四场景两对子PASS；合成endpoint零physical/nativecredit，原4FAIL与math运行失败保留。新v80 clean pushed4→17+2待任务，917未暴露；P2C.1未完成，无P4/ns3/WiFi/RL。报告20261011_p2c_v79_failed_development与20261011_p2c_first_leg_heading_components。

首段截短不会派发充电或在派发时加探索计数；初次补能仍须真实普通Future成功、fresh实际位置落在原2*radius且原可见完整返路/身体净空合格。定向固定条件中，新首段与冻结原算法选择同一完整前沿、相同utility及完整预算；只改当前导航前缀。已有充电、已有普通成功、映射-only、远离近家窗口、过期、无返路、无预算或占体仍按原资格。独立读者拒绝缺失/旧源/伪造计数/改价格与位置，原4次lab清道原图/路线/完整价格逐项保留。

隔离DDS四对照原首段约3.95米、新首段约1.05米，两者每次只在实际Future SUCCESS后加1；清道old0.545/new-1.652rad，同端点同完整预算、真实Future闭合、零普通探索计数。控制地图/模型/时钟、合成ActionServer，无实际Nav2/Gazebo及native充电credit；不作任务、截止期或因果收益保证。所有原失败与报告完整保留。

[JSON](20261011_p2c_first_leg_heading_components.json)
