# MR3 P2A V37：显式实际点到原图的生产模式

2026-10-22：闭合：生产及626人工CPU通过；13e95f29f冻结8步profile完整PASS，三场各64步短探针因corridors导航租约失败提前停止，整体FAIL。无原生/训练信用。P2A未完成；[V36](20261022_mr3_p2a_v36_point_graph.md)已知两帧开发结果只说明新模型值得接入，不能供原生或训练资格。

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

## 冻结运行与闭合

源码冻结 `13e95f29fcc094b19c42fbdeb7d9a76644dee0e9` 已先推送。两活动新符合性各6人工pairs/12full snapshots/36原seed核验/18新attachment核验通过。profile完整8attempt/8return、9actor/27机器人观测attachment审计、性能报告与external final均PASS。profile四舍五入160.05工程秒，仅是instrumented8步、不是长期吞吐。

短probe为119attempt/119return/0step错误、122actor/366次机器人观测attachment审计（不是anchor节点总数）。corridors在54.1仿真时钟、54任务秒触发真实 `navigation_failure`，collector按原规则全局停止；open/rooms的38/27步前缀也没有完成预声明64步外部截断。因此整体collection/audit/description/outer/external final均FAIL，保留原FAIL。external `absence_passed=True`只表示所存进程身份gone，不等于活动PASS。

| 场景101 | 返回步 | 最后估计路径tb1/tb2/tb3（m） | 已接受goal数 | 新attachment接受记录（每机器人） | 原tb3含点格拒绝次数 |
| --- | ---: | --- | --- | ---: | ---: |
| open | 38 | 2.061767/1.058407/1.120983 | 6/6/6 | 39 | 11 |
| rooms | 27 | 0.364946/0.573607/0.477759 | 5/5/5 | 28 | 9 |
| corridors | 54 | 3.139380/2.628002/2.534566 | 8/8/8 | 55 | 3 |

所有保存actor的点接图准入均通过，原tb3含点格失败仍逐次保留，说明该起点阻塞在这些采集样本中已消除；不证明所有20ms状态、任务可达或策略有效。最后代理contact均0；navigation_failure属于collector的unsafe_terminal类别，不能将此直接写成物理碰撞。覆盖/质量/参与未获任务成功，各场时长不同且均未完整，不能与V34/31直接作单因素或任务性能比较。

有限现有描述指出corridors tb3新goal53于52.1创建、原expires54.1，dispatcher requested_at53.3、accepted_at仍空，54.1 lease到期。requested_at不等于endpoint实际收到；KEEP本身不续租，worker已有独立5Hz heartbeat，不能先断言是KEEP漏续租。原IdealTransport全局FIFO及同机器人cancel双回执的队首阻塞是代码候选，已有人工反例；尚未以本次原件证明完整因果链。下一步只做固定时间窗协议法证，核真正generated/received时间，保留TTL/FIFO/频率与旧FAIL；不直接重跑、PPO或改门。

原件[267文件/9,295,067字节清单](assets/20261022_mr3_p2a_v37_point_graph/closed_inventory_v1.json)、[末账与34身份fresh absence](assets/20261022_mr3_p2a_v37_point_graph/closed_metadata_v1.json)、[已有报告派生结果](assets/20261022_mr3_p2a_v37_point_graph/closed_findings_v1.json)、[独立关闭复核](assets/20261022_mr3_p2a_v37_point_graph/independent_closed_review_v1.json)。133绑定来源包括132冻结仓库源/计划及1外部execution driver；driver的actual-receipt SHA绑定与原字节封存单列，不冒称在13冻结中存在。独立复核首版把该retained副本重复计作第134绑定来源，计数错误原版保留，最终报告明确修正；未改任何运行回执/原FAIL。

四outer实际区间union `520.102603214` 秒（profile main159.404680870 + final.650152479；probe main359.366669497 + final.681100368），profile完整端点160.325799130<600、probe360.319167253<1800。累计 `48259.6385161916018/52000`、余 `3740.3614838083982` 秒；pilot与final-only未动，75000提案仍待明确批准。P2A未完成。
