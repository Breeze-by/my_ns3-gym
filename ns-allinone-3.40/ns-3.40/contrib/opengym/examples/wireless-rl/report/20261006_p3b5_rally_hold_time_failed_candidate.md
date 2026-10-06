# P3B.5 v103原始集合末段保持超时

2026-10-06 P3B.5 v103原候选FAIL，冻结dbed34c0ed708803e131ef00ecff7791e6b3cde3；2026-10-06 05:01:23–05:46:58UTC所有原owner/观察器自然关闭。16started/16raw、41unrun（其余primary/safety含809），无retry/backfill。uniform rmw_fastrtps_cpp/UDPv4真实环境；initial强制ideal原生COMPLETE249.3s/各charge1/最低14.00323，fault300.0s RALLY timeout/各charge1/最低9.23028，仅既定安全PASS。E0双格原生FAILED2.8/.6s/无导航；受控返充两格准备exit0，断网62..248s两机实际路径1.20333/1.14938m、净进展1.19708/1.14094m、EXEC运动1.20330/1.14935m、各charge1，物理返充子门PASS；54纯协议PASS。十固定全部运行，九个原生COMPLETE：lab101260.1、lab202168.4、rooms101/202/303114.8/153.6/177.4、corridors101/202/303194.2/221.9/226.1、双机corridors202175.0s。lab303检测113.9/RALLY116.2、timeout300.4s，tb2/tb3各charge1、最低19.45906、所有终态ACTIVE。终态位置误差均<.1m但原生completion/native proof为null；原中央诊断near298.9s开始保持，299.7s收到tb1角速度.12946rad/s>原.1门限重置，未完成连续5s。16账本因果/TTL/version/决策租约与16图审计PASS，0接触/infra/操作失败，除预声明E0终止外无耗尽或failed机器人；十fixed实际CPU0–79及environment一致，观察器实际RMW/UDP、Nav2模拟时钟/SLAM2s参数保留。19450..56七port/PID/env、全部冻结helper/config/source与17用户资料哈希审核PASS。已关闭AP与路线日志显示观测者让开后继充电机器人的进路后才末段回位；这是诊断证据，不能由离散AP样本证明原生保持或宣称因果加速/最坏时间保证。归档脚本首次把环境大写key误读为小写→KeyError，修正只读归档并保留首错误；未重复任务。报告report/20261006_p3b5_rally_hold_time_failed_candidate.json/.md。300s/.35/.05/.1/5s、poseTF2/mapbattery5/target60/handoff5、body.6/static.35/集合位.45/route1.8阈值与严格checker未放宽；809.world/seed809/fault28091从未执行。完整strict checker/PASS图文未执行，P3B.5未完成，无ns3/WiFi/RL。

| original | phase / seconds | native completion | charges | minimum energy |
|---|---|---:|---:|---:|
| p3b5_v103_zero_ideal_lab2_rally_0678e85373 | FAILED / 2.8 | None | 0 | 0.00000 |
| p3b5_v103_zero_battery_exhaust_lab_fault | FAILED / 0.6 | None | 0 | 0.00000 |
| p3b5_v103_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 249.3 | 249.30000000000018 | 2 | 14.00323 |
| p3b5_v103_forced_forced_charge_outage_fault | RALLY / 300.0 | None | 2 | 9.23028 |
| p3b5_v103_returnproof_ideal_forced2_rally_4c7c808f36 | RALLY / 300.0 | None | 2 | 9.63149 |
| p3b5_v103_returnproof_physical_return_under_blackout_fault | EXPLORE / 300.2 | None | 2 | 9.69863 |
| p3b5_v103_fixed_lab101_lab_far_northwest_3r_seed101 | COMPLETE / 260.1 | 260.0999999999999 | 1 | 18.45185 |
| p3b5_v103_fixed_lab_lab_far_northwest_3r_seed202 | COMPLETE / 168.4 | 168.4000000000001 | 0 | 27.49928 |
| p3b5_v103_fixed_lab_lab_far_northwest_3r_seed303 | RALLY / 300.4 | None | 2 | 19.45906 |
| p3b5_v103_fixed_rooms_rooms_far_northeast_3r_seed101 | COMPLETE / 114.8 | 114.80000000000001 | 0 | 31.37442 |
| p3b5_v103_fixed_rooms_rooms_far_northeast_3r_seed202 | COMPLETE / 153.6 | 153.59999999999997 | 0 | 21.47936 |
| p3b5_v103_fixed_rooms_rooms_far_northeast_3r_seed303 | COMPLETE / 177.4 | 177.39999999999998 | 0 | 18.75361 |
| p3b5_v103_fixed_corridors_corridors_far_west_3r_seed101 | COMPLETE / 194.2 | 194.2 | 0 | 23.64477 |
| p3b5_v103_fixed_corridors_corridors_far_west_3r_seed202 | COMPLETE / 221.9 | 221.9 | 1 | 24.33372 |
| p3b5_v103_fixed_corridors_corridors_far_west_3r_seed303 | COMPLETE / 226.1 | 226.1 | 1 | 24.05715 |
| p3b5_v103_fixed_corridors_corridors_far_west_2r_seed202_crosscheck | COMPLETE / 175.0 | 175.0 | 0 | 23.15565 |

Original lab303 final navigation settles too close to300s; delivered angular speed resets hold near299.7s. Final qualifying instantaneous positions/speeds do not replace continuous5s native hold. Observer route yielding and late charged-peer arrival are recorded conditions, not single-factor causal proof. Keep all originals; develop dispatch/assignment improvement independently.
