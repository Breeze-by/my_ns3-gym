# P3B.5 v61独立开发失败

2026-10-05 P3B.5 v61独立开发五格FAIL，冻结cf829cf23ae56adb65ca9a54b13b34132cddbd09；2026-10-04 18:18:54–18:31:08UTC所有原owner/观察器自然关闭，lab exit1、force/zero pool exit0。force ideal原生COMPLETE209.8s/各charge1/最低8.79340，zero fault原生COMPLETE160.8s/charge0/最低23.15425。lab3/101检测126.3/RALLY128.4、300.3s timeout/charge1/最低13.98203，tb1/tb2尚RETURNING；zero ideal检测133.7/RALLY143.7、300.0s timeout/各charge1/最低14.29596。force fault300.4s EXPLORE timeout、tb1 charge1/tb2 charge0且末端仅CHARGING3.5s/最低7.38321，未满足各机器人充电安全子门。五格0碰撞/0耗尽/0failed/0infra、五ledger因果/TTL/version/charge消费与决策租约PASS、五graph0旁路，无整轮重试/回填。提前探索充电真实执行，但只在所有可负担任务耗尽才考虑充电，会让已充电同伴连续获任务而饿死idle充电候选；当前驻点成本只计真实observer，其他funded驻点也可能挡charged peer；RALLY名义预算仍无最坏时间保证。报告report/20261005_p3b5_frontier_charge_admission_development.json/.md保留全部原始命令/日志/取证，时间差不作单因素收益。809/28091从未执行，正式57格/PASS图文未启动，P3B.5未完成，无ns3/RL。

| episode | phase / seconds | charges | minimum energy |
|---|---|---:|---:|
| p3b5_v61_dev_fixed_lab101_lab_far_northwest_3r_seed101 | RALLY / 300.3 | 1 | 13.98203 |
| p3b5_v61_dev_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 209.8 | 2 | 8.79340 |
| p3b5_v61_dev_forced_forced_charge_outage_fault | EXPLORE / 300.4 | 1 | 7.38321 |
| p3b5_v61_dev_zero_ideal_lab2_rally_8d4d5c469d | RALLY / 300.0 | 2 | 14.29596 |
| p3b5_v61_dev_zero_zero_rally_lab_fault | COMPLETE / 160.8 | 0 | 23.15425 |

Forced fault tb1 charges once and keeps exploring; tb2 completes zero charges and endsCHARGING after only3.5s at300.4. Existing request_exploration_charge is considered only when no funded admissions exist anywhere and no live exploration exists, so funded work can repeatedly hide a needed idle peer charge. Logs/code establish this admission mechanism; no isolated causal timing claim. Lab detects126.3/RALLY128.4 but ends300.3 with tb1/tb2 RETURNING and tb3 charged/arrived; RALLY path27.006m and allocation/recovery includes a funded non-observer parking in charged-peer corridor. Parking leaf cost currently models only the designated observer body, not other funded peers. Zero ideal detects133.7/RALLY143.7, tb2 early RALLY charge, tb1 later needs a second charge after waiting/body detours; at300s tb1 near changed final and tb2 4.510m away. Nominal whole-rally budgets do not guarantee actual wait/motion. Original data/AP subscriber snapshots are evidence/forensics, not controller truth or exact original buffers. Frontier budget filtering alone does not solve fair charging admission or all parked-peer traffic.
