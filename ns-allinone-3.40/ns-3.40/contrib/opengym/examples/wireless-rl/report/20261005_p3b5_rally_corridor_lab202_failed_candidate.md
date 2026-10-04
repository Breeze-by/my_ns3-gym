# P3B.5 v67原始集合失败

2026-10-05 P3B.5 v67原候选FAIL，冻结a7952b59ae9df722eabf3beddc5c159bf4e9a01c；2026-10-04 20:23:16–20:51:34UTC全部owned任务/观察器自然关闭，initial全0、lab101 exit0、lab202任务exit1。8started/8raw、49unrun含剩余8fixed与809，无重试/回填。强制ideal原生COMPLETE211.2s/各charge1/最低16.75387，强制fault300.1s RALLY timeout/各charge1/最低8.48774安全PASS；E0双格预声明FAILED2.0/1.1s且无导航。受控准备两侧均50s内双机到位，两侧各charge1/0接触/最低9.67712、9.59143，断网62–248实际返航path1.22875/1.14257、net1.22331/1.13431、NavEXEC1.22872/1.14254m，严格安全审计PASS；原timeout不计任务成功。首fixed lab101原生243.1s/charge1/最低23.62608；lab202 RALLY timeout300.4s/charge2/最低20.78276，tb1距最终1.41806m、其余两机已到位。八格0接触/0infra/0操作失败，八ledger及八graph PASS、54纯协议PASS。保存AP地图条件回放提示完整高优先未来路线预约拒绝了部分实际body可行短腿；充电preflight需要完全动作排空才能重排，但持续新腿可能使其迟迟不能完成。只读条件几何不是原buffer或任务收益因果证明，待开发修复。809/28091仍从未执行，完整strict PASS报告/图未生成，P3B.5未完成，无ns3/RL。

| original episode | phase / seconds | charges | minimum energy |
|---|---|---:|---:|
| p3b5_v67_zero_ideal_lab2_rally_0678e85373 | FAILED / 2.0 | 0 | 0.00000 |
| p3b5_v67_zero_battery_exhaust_lab_fault | FAILED / 1.1 | 0 | 0.00000 |
| p3b5_v67_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 211.2 | 2 | 16.75387 |
| p3b5_v67_forced_forced_charge_outage_fault | RALLY / 300.1 | 2 | 8.48774 |
| p3b5_v67_returnproof_ideal_forced2_rally_4c7c808f36 | RALLY / 300.1 | 2 | 9.67712 |
| p3b5_v67_returnproof_physical_return_under_blackout_fault | EXPLORE / 300.1 | 2 | 9.59143 |
| p3b5_v67_fixed_lab101_lab_far_northwest_3r_seed101 | COMPLETE / 243.1 | 1 | 23.62608 |
| p3b5_v67_fixed_lab_lab_far_northwest_3r_seed202 | RALLY / 300.4 | 2 | 20.78276 |

Original lab202 tb1 remains1.418m from its final pose, tb2/tb3 errors.003/.009m, each ACTIVE/positive and0contacts. Both tb1/tb2 charged once. Logs show tb1 waits near(-3.67,.19) while tb2 follows a body-masked detour; several conditional AP snapshots offer tb1 a valid known-free leg under actual bodies, but full higher-priority tb2 future approach rejects it. Reconstructed snapshots are not original buffers; do not infer a successful alternative mission. Charging preflight requires total goal quiescence to recompute the approach order, yet new legs keep being admitted as others finish, so it can remain unfinished throughout transit. A current-map route scheduling/drain optimization remains to validate; no lease, clearance, contact, horizon or native threshold relaxed.
