# P3B.5 v70原生电池终态测量失败

2026-10-05 P3B.5 v70原候选FAIL，冻结4653c13e6de18b8ad8ade2bc4c734ab76005c9b2；全部owned任务与观察器自然关闭后归档。6started/6raw、51unrun含十fixed/809；p3b5_v70_zero_ideal_lab2_rally_0678e85373 FAILED/1.7s/charge0/min0.00000；p3b5_v70_zero_battery_exhaust_lab_fault FAILED/1.3s/charge0/min0.00000；p3b5_v70_forced_ideal_forced2_rally_86fbb43bc6 COMPLETE/235.2s/charge2/min16.20114；p3b5_v70_forced_forced_charge_outage_fault COMPLETE/300.1s/charge2/min9.92663；p3b5_v70_returnproof_ideal_forced2_rally_4c7c808f36 RALLY/300.1s/charge2/min9.60870；p3b5_v70_returnproof_physical_return_under_blackout_fault EXPLORE/300.1s/charge2/min9.54496。E0 ideal已FAILED1.7s/双机无Nav且中央失败名单完整，但原生评估tb1 battery_message_count0、mode/initial_energy为null，严格E0前置断言拒绝；fault FAILED1.3s双机原生字段完整。独立只读安全观察器收到tb2/tb1 FAILED原生消息于2072.082/2072.282；task evaluator在FAILED后的固定0.5s drain先写终态，快终止可能早于另一路原生电池回调。缺失证据保留为空，不从配置/网关推断0或FAILED、不放宽断言；需有界终态收集回归。无整轮重试/回填，六ledger/graph已审核；报告report/20261005_p3b5_failure_battery_snapshot_failed_candidate.json/.md。809/28091仍从未执行，完整P3B.5未通过，无ns3/RL。

| original | phase / seconds | charges | minimum energy |
|---|---|---:|---:|
| p3b5_v70_zero_ideal_lab2_rally_0678e85373 | FAILED / 1.7 | 0 | 0.00000 |
| p3b5_v70_zero_battery_exhaust_lab_fault | FAILED / 1.3 | 0 | 0.00000 |
| p3b5_v70_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 235.2 | 2 | 16.20114 |
| p3b5_v70_forced_forced_charge_outage_fault | COMPLETE / 300.1 | 2 | 9.92663 |
| p3b5_v70_returnproof_ideal_forced2_rally_4c7c808f36 | RALLY / 300.1 | 2 | 9.60870 |
| p3b5_v70_returnproof_physical_return_under_blackout_fault | EXPLORE / 300.1 | 2 | 9.54496 |

Independent native safety subscriber received both FAILED states. Saved evaluator missed tb1 before its snapshot; callbacks from distinct subscribers are not identical buffers. A bounded evidence drain is to be tested; do not infer missing fields or replace this original result.
