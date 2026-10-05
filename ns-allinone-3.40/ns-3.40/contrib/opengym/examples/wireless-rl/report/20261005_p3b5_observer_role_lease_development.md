# P3B.5 v91独立开发FAIL

2026-10-05 P3B.5 v91独立六格开发FAIL，冻结2d1a1b8204811aa54ba2557bdbb3b277bb97476e；所有原owner/观察器自然关闭后审核归档。p3b5_v91_dev_fixed_lab101_lab_far_northwest_3r_seed101 FAIL/RALLY/300.2s/charge2/min18.31056；p3b5_v91_dev_fixed_lab202_lab_far_northwest_3r_seed202 FAIL/FAILED/180.7s/charge0/min29.75193；p3b5_v91_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/233.0s/charge2/min10.58555；p3b5_v91_dev_forced_forced_charge_outage_fault PASS/RALLY/300.4s/charge2/min10.83913；p3b5_v91_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/196.2s/charge1/min21.57276；p3b5_v91_dev_zero_zero_rally_lab_fault PASS/COMPLETE/198.8s/charge1/min21.89806。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_observer_role_lease_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。原target60s租约内保护最后观测者角色，只有真实同伴确认才移交；心跳5s/其他源TTL不变，控制只用交付输入，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与历史候选不同，无单因素消融，不把较早发现或较短完成时间归因于角色保护，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。 六格真实参数响应齐全且正确，所有原ledger/graph审核通过；无source/helper/用户资料改动，无任务重试。lab101角色保护实际保持到确认缺口超过24s但仍RALLY timeout300.3；原生旁录tb2静止距target2.167m、yaw2.454、target方向1.592，误差约.862rad>FOV半角.785，实际朝向恢复缺失，不续租或推断仍可见。lab202在180.7s因insufficient_rally_poses FAILED、0charge/min29.75193，无物理失败机器人；三原AP末期条件回放各18候选，tb2可达16而tb1/tb3与home仅达2，原图与现有自回波规划副本均无完整三机分配。单纯候选数量不能保证连通；需调查连接区域，而不是放宽净空/穿未知格。AP回放不是原内部buffer或反事实任务，原生只读取证不反馈控制，不宣称角色修改已解决任务。

| episode | check | phase / seconds | charges | minimum energy |
|---|---|---|---:|---:|
| p3b5_v91_dev_fixed_lab101_lab_far_northwest_3r_seed101 | FAIL | RALLY / 300.2 | 2 | 18.31056 |
| p3b5_v91_dev_fixed_lab202_lab_far_northwest_3r_seed202 | FAIL | FAILED / 180.7 | 0 | 29.75193 |
| p3b5_v91_dev_forced_ideal_forced2_rally_86fbb43bc6 | PASS | COMPLETE / 233.0 | 2 | 10.58555 |
| p3b5_v91_dev_forced_forced_charge_outage_fault | PASS | RALLY / 300.4 | 2 | 10.83913 |
| p3b5_v91_dev_zero_ideal_lab2_rally_8d4d5c469d | PASS | COMPLETE / 196.2 | 1 | 21.57276 |
| p3b5_v91_dev_zero_zero_rally_lab_fault | PASS | COMPLETE / 198.8 | 1 | 21.89806 |

Independent originals, no formal backfill or counterfactual causal claim. Detector is Gazebo geometric visibility proxy, not image recognition. Native evaluator/physics only read-only evidence; native truth never enters mission control. Nominal serial energy/time/parking costs remain heuristics.
