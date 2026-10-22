# MR3 P2A V37：显式实际点到原图的生产模式

2026-10-22：生产实现及626项人工CPU已通过，尚无V37 World/原生/训练运行结果。P2A未完成；[V36](20261022_mr3_p2a_v36_point_graph.md)已知两帧开发结果只说明新模型值得接入，不能供原生或训练资格。

## 科学变更与实施

显式组合为 `seed_rule=exact-point-bridge-v2`、`start_graph_rule=point-attachment-3x3-v1`。默认 `original-seed-cell` 保持原输出和旧门。实际估计点不snap，仍须唯一canonical含点格raw-free、state/map来源与epoch/future门、完整 `.29m` 点证书。新模式承认含点格centre图门可能失败：保存该FAIL，在固定3×3原图节点中保留所有通过整桥 `.29m` 认证的anchors。

每台机器人独立计算 `min_anchor(bridge_length + original_graph_distance)`；不能把零成本多源最短路与最短桥长分别取最小，不能借用别台虚拟起点。目标投影尾段仍计一次，原 `.39m` 到达圆、frontier/K8/reservation/掩码保持。导航与非导航使用各自新版本，全部证书、规则和路径来源入digest。

代理仅为已经由策略选定的goal选择局部路径入口，沿原无corner-cut图推进；所有20ms平移和名义下一点的续连桥仍独立认证。原生继续派发原策略候选至Nav2，anchor不是新探索目标或额外Nav2 GOAL。固定地图名义几何不能证明定位误差、动态peer、物理跟踪或任务成功。

## 有界验证预声明

见[scope](assets/20261022_mr3_p2a_v37_point_graph/scope_acceptance_v1.json)。先做人工CPU几何、带权图独立oracle、真/旧准入诊断、来源隔离、默认兼容、执行续连、参数/资格/审计接线；通过后提交推送新freeze，才启动一次open101的8步600墙秒profile。完整profile、独立审计和外部关闭通过后，同freeze才允许一次open/rooms/corridors101各64步1800墙秒短探针。两者共预约2400秒，包含各自审计、cleanup和external final，不重试、不补样。

新符合性使用预声明6组人工received-input原起点/新起点成对重建，明确无原生信用；旧模式原6输入符合性逻辑保留。短探针逐actor核张量和完整attachment，关键reset/first/last完整重建。零模型/GPU/policy/optimizer；不改任务门、不做PPO或gateway、不消耗pilot和final-only。

工程开局 `47739.5359129776018/52000`、余 `4260.4640870223982` 秒，扣2400最大预约后仍有 `1860.4640870223982` 秒。75000累计扩额提案未获明确批准。完整原生资格+minimum仍需20100预约，当前余额不足；任何短工程PASS都不能解锁该链。

## 生产实现与CPU结果

已接入原生launch/adapter/supervisor、minimum/pilot/final模式身份、代理Information/navigator/worker/capacity、完整独立输入重建与新符合性。默认新增字段省略；新模式有新候选完整规则、ENV整文逆投影及point helper固定SHA。旧原生diagnostic入口保留旧作用域，不能直接借给新模式。导航帧/registration仍由原Information与archive整payload门保证，几何helper不提供frame或定位证明。

最终相关CPU共626项：281几何/观测/执行、152 ROS接线、12独立原生输入读者、181 learner/资格/consumer。各轮源码before/after稳定。首轮learner181项保留2FAIL/4ERROR（含subtest连带）：新人工top map_version误为字符串、旧mock collect遗漏新start参数；仅修参数/fixture后第二轮181全过。未运行真实原件消费者或World、无policy/GPU/更新，工程增量0。原始回执、日志及所有不同字节源码可恢复位置见[CPU index](assets/20261022_mr3_p2a_v37_point_graph/checks/index_v1.json)与[source recovery](assets/20261022_mr3_p2a_v37_point_graph/checks/source_recovery_v1.json)。

几何人工检查包括独立全anchor闭方格oracle、增广图heap最短路oracle、非最近anchor跨连通分量、桥长不可分开取min、旧seedFalse/新attachmentTrue、own/nav/fused来源隔离与缺失/epoch/future/stale拒绝、续连与handoff/中段障碍/zero deadpoint、旧profile完整输出省略。新符合性12快照独立重建在人工CPU fixture中已过；真实freeze下活动仍须重新运行，mock Git fixture不提供freeze信用。
