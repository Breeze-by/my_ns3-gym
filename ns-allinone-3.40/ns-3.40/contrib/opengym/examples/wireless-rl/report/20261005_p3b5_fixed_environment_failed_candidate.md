# P3B.5 v79固定实验环境汇总失败

2026-10-05 P3B.5 v79原始批次验收FAIL，冻结c4c943ffc5dcecc7252f1eaba2f52dd7ce7f016d；2026-10-05 00:22:25至01:06:49UTC全部owned任务与观察器自然关闭。16started/16raw、41unrun，未重试/回填；809.world/seed809/fault28091仍从未执行。initial强制ideal原生COMPLETE220.3s/两机各charge1；fault RALLY timeout300.3s/各charge1/最低9.49659，仅安全子门PASS。E0双格FAILED1.9/2.6s、实际原生电量0、无导航；受控断网返充strict物理子门与54协议PASS。两机在守护窗口从距home1.959/2.008m开始，真实路径1.165/1.227m、净进展1.151/1.218m、Nav2 EXEC运动1.165/1.226m，各实际充电一次。全部十个固定原任务均满足未修改的episode_ok/native5秒保持，完成时间165.6至256.5s，零碰撞/耗尽/失效；但原fixed_ideal_batches继承same_candidate要求environment完全相同，而预声明world池CPU0–19/20–39/40–59不同，汇总AssertionError: environment，不能判全门禁PASS。其余环境字段一致，原manifest与失败helper全部保留，没有归一化/重写结果。16账本TTL/version及16通信图旁路审计PASS，0接触/0基础设施失败/0操作失败；实际17550..56七port/PID/env关闭及全部原helper/config/source/17用户资料哈希PASS，foreign222/master11345未动。修正下一批实验装置为全部固定world同一CPU亲和性并在首次任务前断言一致，保持严格checker/算法/任务300s/.35/.05/.1/5s/原故障与能量参数。报告report/20261005_p3b5_fixed_environment_failed_candidate.json/.md。完整strict checker/PASS图文未执行，P3B.5尚未通过，无ns3/WiFi/RL。

| original | phase / seconds | native completion | charges | minimum energy |
|---|---|---:|---:|---:|
| p3b5_v79_zero_ideal_lab2_rally_0678e85373 | FAILED / 1.9 | None | 0 | 0.00000 |
| p3b5_v79_zero_battery_exhaust_lab_fault | FAILED / 2.6 | None | 0 | 0.00000 |
| p3b5_v79_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 220.3 | 220.30000000000018 | 2 | 14.78344 |
| p3b5_v79_forced_forced_charge_outage_fault | RALLY / 300.3 | None | 2 | 9.49659 |
| p3b5_v79_returnproof_ideal_forced2_rally_4c7c808f36 | RALLY / 300.4 | None | 2 | 9.72399 |
| p3b5_v79_returnproof_physical_return_under_blackout_fault | EXPLORE / 300.4 | None | 2 | 9.70381 |
| p3b5_v79_fixed_lab101_lab_far_northwest_3r_seed101 | COMPLETE / 220.7 | 220.70000000000027 | 1 | 22.80208 |
| p3b5_v79_fixed_lab_lab_far_northwest_3r_seed202 | COMPLETE / 213.7 | 213.69999999999982 | 1 | 23.98456 |
| p3b5_v79_fixed_lab_lab_far_northwest_3r_seed303 | COMPLETE / 175.8 | 175.80000000000018 | 1 | 22.62811 |
| p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed101 | COMPLETE / 173.9 | 173.89999999999998 | 0 | 19.73693 |
| p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed202 | COMPLETE / 169.0 | 169.0 | 1 | 21.41084 |
| p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed303 | COMPLETE / 165.6 | 165.59999999999997 | 0 | 19.51113 |
| p3b5_v79_fixed_corridors_corridors_far_west_3r_seed101 | COMPLETE / 194.9 | 194.89999999999998 | 0 | 22.59217 |
| p3b5_v79_fixed_corridors_corridors_far_west_3r_seed202 | COMPLETE / 198.2 | 198.20000000000002 | 0 | 22.16069 |
| p3b5_v79_fixed_corridors_corridors_far_west_3r_seed303 | COMPLETE / 193.8 | 193.79999999999998 | 0 | 21.56430 |
| p3b5_v79_fixed_corridors_corridors_far_west_2r_seed202_crosscheck | COMPLETE / 256.5 | 256.5 | 1 | 26.01681 |

All ten raw fixed tasks pass strict native completion. The unchanged aggregator rejected only cpu_affinity equality. Preserve this original failed candidate; no post-hoc normalization or resuming/backfilling its41 unrun cells. New prospective full57 cohort uses identical fixed CPU affinity. Task core source bytes and thresholds remain unchanged.
