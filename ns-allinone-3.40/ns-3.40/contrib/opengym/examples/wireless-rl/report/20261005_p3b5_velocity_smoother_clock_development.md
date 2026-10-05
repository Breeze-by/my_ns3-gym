# P3B.5 v85独立开发FAIL

2026-10-05 P3B.5 v85独立六格开发FAIL，冻结14c4c416d7cd30eb958b20a528e660bebf4b6943；所有原owner/观察器自然关闭后审核归档。p3b5_v85_dev_fixed_lab101_lab_far_northwest_3r_seed101 PASS/COMPLETE/174.1s/charge1/min22.64706；p3b5_v85_dev_fixed_lab202_lab_far_northwest_3r_seed202 PASS/COMPLETE/247.0s/charge2/min23.44580；p3b5_v85_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/189.7s/charge2/min15.51925；p3b5_v85_dev_forced_forced_charge_outage_fault PASS/COMPLETE/296.8s/charge2/min9.89349；p3b5_v85_dev_zero_ideal_lab2_rally_8d4d5c469d FAIL/EXPLORE/300.3s/charge1/min3.21880；p3b5_v85_dev_zero_zero_rally_lab_fault PASS/COMPLETE/202.3s/charge1/min21.89626。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_velocity_smoother_clock_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。Nav2平滑器命令超时仿真时钟只用交付输入，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与历史候选不同，无单因素消融，不把较早发现或较短完成时间归因于Nav2平滑器时钟，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。 lab202原参数只返回五项true，缺/tb3/controller_server，测量FAIL且不推断第六项。原冻结审核器未改；新关闭后只读归档器将缺响应列为测量失败并完整保留六任务。失败zero ideal原ledger有27条过期输入诊断，个人地图源龄超过5s时融合地图/pose/TF/电池仍新鲜；实际overlay地图周期5s恰等于TTL5s，缺交付余量。此为确认的配置冲突，尚不能证明加快更新就能完成任务或解决返航停滞。

| episode | check | phase / seconds | charges | minimum energy |
|---|---|---|---:|---:|
| p3b5_v85_dev_fixed_lab101_lab_far_northwest_3r_seed101 | PASS | COMPLETE / 174.1 | 1 | 22.64706 |
| p3b5_v85_dev_fixed_lab202_lab_far_northwest_3r_seed202 | PASS | COMPLETE / 247.0 | 2 | 23.44580 |
| p3b5_v85_dev_forced_ideal_forced2_rally_86fbb43bc6 | PASS | COMPLETE / 189.7 | 2 | 15.51925 |
| p3b5_v85_dev_forced_forced_charge_outage_fault | PASS | COMPLETE / 296.8 | 2 | 9.89349 |
| p3b5_v85_dev_zero_ideal_lab2_rally_8d4d5c469d | FAIL | EXPLORE / 300.3 | 1 | 3.21880 |
| p3b5_v85_dev_zero_zero_rally_lab_fault | PASS | COMPLETE / 202.3 | 1 | 21.89626 |

lab101 six original parameter responses are true; lab202 retains only five true responses, missing /tb3/controller_server. No sixth response is inferred. The original frozen archive checker is unchanged; a new post-closure read-only checker records this as an apparatus failure while retaining all six task outcomes.

Independent originals, no formal backfill or counterfactual causal claim. Detector is Gazebo geometric visibility proxy, not image recognition. Native evaluator/physics only read-only evidence; native truth never enters mission control. Nominal serial energy/time/parking costs remain heuristics.
