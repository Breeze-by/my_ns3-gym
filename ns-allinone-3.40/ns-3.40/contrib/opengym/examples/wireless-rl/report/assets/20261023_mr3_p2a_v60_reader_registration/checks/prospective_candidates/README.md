# P2A 后继接续入口

V60 已实际失败并完成关闭。当前资格为 19 PASS / 1 FAIL / 10 SKIP，未启动 minimum、pilot 或 final；容量 gate 为 False。用户已授权自主持续完成 P2A，无需重复询问一般实施批准。先读[规范末账](../../closure_ledger_v1.json)与[V60实际报告](../../../../20261023_mr3_p2a_v60_reader_registration.md)。

以下代码都是未安装候选。其人工 CPU 只证明对应人工场景，不能当成 canonical、native、可达、学习或容量证据。原件完整保存在[opaque包](prospective_candidates_v1.tar.gz)，整包 SHA256 为 `90d75622c78bec832e4b78e9c9aa2bcb79f0a56ae998a1e65f862b3a1951c852`。先核[清单](manifest_v1.json)，按 `original_path → archive_member` 找到成员，在空目录恢复或单独读取。包内没有链接/hardlink header，不会自动安装 `.py`。

| 候选原路径（包内位于 `payload/tmp/`） | 用途与限制 |
| --- | --- |
| `mr3_p2a_v60_cancel_causality_static_v1` | 取消静态链、固定窗、v2描述器及7项人工CPU。原3.031秒FAIL不动。更早345f私有draft未保存的缺口已如实登记。 |
| `mr3_p2a_v61_original_path_v3_review` | 在v2上只补原路径强等，优先采用SHA `860b69ca4bf755da4af411f6f7a8ccb870329ee6f8f96c9d5254c26da072ee1e` 的v3 consumer。它未执行旧7case，需新相关CPU。 |
| `mr3_p2a_v61_run_cancel_forensics_draft_v1.py`、`mr3_p2a_v61_cancel_scope_pending_v1.json`及parent说明 | V61完整parent660秒/work480秒草稿，ENTRY只读真实V60末账，nested不加。scope/spec仍未准入。选v3后同步parent的consumer文件名和spec SHA。 |
| `mr3_p2a_outward_cancel_v2_shadow_v1`、`mr3_p2a_outward_cancel_probe_review_v1` | 显式probe-v2、真实GoalDispatcher/mask人工回归及完整接线清单。1.45m仅名义刺激筛选；保留5s承诺、32步、最多6GOAL，实际owned/moving/legal WAIT与匹配CANCELED分开。不能替代真实停车迟延修复。 |
| `mr3_p2a_fixed_process_profile_candidate_v1` | 固定motion/adapter/worker三角色main和encoder/ROS两个线程的profiler及最小接线。core保留真实SystemExit/异常；不是直接`-m cProfile`。14toy和3接线case已通过，真实ROS prefix/filter、loaded paths和8step native尚未验证。普通8step probe不冒称32step preparation/readback。 |
| `mr3_p2a_v60_policy_capacity_source_review_v1` | 原minimum/pilot/final cap与已闭合成本。当前无容量资格；V48/V39优化已在当前源，不再计新收益。8step profile也不是最终容量证明。 |
| `mr3_p2a_same_activity_audit_reuse_source_review_v1`、`mr3_p2a_exact_seed_materialization_shadow_v1` | 仅同活动exact-seed辅助fact复用。先统一-B/env，严格绑定真实origin wait/源码/原件闭包；当前V60旧结果缺新seal，不能复用。PPO无对应叶时显式not-applicable而实际调用原helper；坏资格叶不得偷偷fallback。原archive、30角色和其它数学检查保留。v1目录漏洞及v2真实10项人工CPU均保留。 |

立即下一步只做 V61：

1. 从不可变V60库存选择 `worker1/episode002_open_101` 的五份**原始仍保留regular encoded文件**：adapter、motion_safety、tb2 drive、tb2 odometry、launch log；原件若本来是.gz就绑定该原始.gz。`item.path == inventory.original_path`，不使用重压canonical wrapper或临时换来源。
2. 固定epoch `mr3_p2a_reach_v60_reset_w1_e2_d678c4be`，主窗[42.6,46.1]s、明确对照窗[54.6,55.6]s。原42.86s取消起点、.78s/.144m、eligibility、R=.0078、anchor及旧FAIL不改。49.86s后继goal仅作已声明上下文。
3. 原件整encoded SHA/bytes、完整decoded SHA/bytes、parse/行数/输出/总work成本均封入新spec。gzip若没有事前decoded SHA，可明确缺省但必须全解码验证；不能为填预pin先额外读raw。
4. 将选定consumer/parent/spec/scope及必要解释源安装到新的A61目录。解释源必须同时等于旧E；新程序/spec/scope/库存/末账须匹配新的精确Git freeze与当前字节。补最短相关CPU后commit/push并等真实完成，再单次运行。不得直接运行/tmp草稿或绕过admitted=False。
5. 等真实parent/工具退出，保留partial/真实rc/完整费和所有原件；据实际raw request→guard→store/APPLIED→odom分段选择修复。既有unstamped Twist/UUID缺失就报告UNKNOWN，不能制造跨进程wall总序或把desired0叫motor0。

随后才整合诊断所得取消修复、probe-v2和性能改进。probe与seed-only patch都改 `reach_preparation.py` / `audit_reach_preparation.py`，必须按冲突清单合并，不能整文件覆盖。profiler绑定的是E源；若底层源已更新，重新绑定并验证唯一透明hook。先做有界8step性能分解，再验证恒等优化与完整native/audit容量；可在原9000秒内前瞻重分配native/audit预留，不能扩大pilot/final余额或更改科学门。

容量未通过时，新driver的pilot/final自动入口必须保持关闭。容量通过后仍须新同freeze完整12EP/30角色、真实minimum与pilot正更新/固定checkpoint，以及open401/402/403同checkpoint零更新strict95验证和最终来源/退出核验。全部满足前，P2A保持未完成；P2B/gateway不启动。
