# P3B.5 v58失败候选

2026-10-05 P3B.5 v58原候选FAIL，冻结cf73eebd875d990bd782cef572d09b484b23900a；2026-10-04 16:19:20–16:33:04UTC自然关闭。6started/6raw、0接触/0基础设施失败、6账本与6图审计PASS、54纯协议PASS。强制充电ideal直到242.2s检测、260.2s进入RALLY，300.4s仍有tb1在最终路线中，各charge1、最低8.11062，无原生COMPLETE，不能判通过；force fault300.2s也RALLY timeout。E0双格为预声明FAILED且无导航；controlled remote双格各充电一次/正能量/0接触，关闭后只读严格physical-return审计PASS，证明断网窗口中的实际Nav2返航，并非任务成功。其余51格含全部固定与809未启动；新809/28091仍未暴露，原707不得视为未暴露。只读日志显示返航取消西侧前沿后，充电恢复按即时收益重分配到东侧，再回西侧而造成较晚检测；这是待开发验证的任务接续问题，不是单次运行的因果收益证明。报告见report/20261005_p3b5_confirmation_gap_forced_failed_candidate.json。所有owned owner/观察器/master自然关闭后归档，domain222未动。完整strict checker/PASS报告/图未执行，P3B.5仍未完成，无ns-3/WiFi/RL。

| 原始 episode | phase / elapsed(s) | charges | 最低能量 |
|---|---|---:|---:|
| p3b5_v58_zero_ideal_lab2_rally_0678e85373 | FAILED / 1.8 | 0 | 0.00000 |
| p3b5_v58_zero_battery_exhaust_lab_fault | FAILED / 1.8 | 0 | 0.00000 |
| p3b5_v58_forced_ideal_forced2_rally_86fbb43bc6 | RALLY / 300.4 | 2 | 8.11062 |
| p3b5_v58_forced_forced_charge_outage_fault | RALLY / 300.2 | 2 | 7.01518 |
| p3b5_v58_returnproof_ideal_forced2_rally_4c7c808f36 | RALLY / 300.2 | 2 | 9.54092 |
| p3b5_v58_returnproof_physical_return_under_blackout_fault | EXPLORE / 300.3 | 2 | 9.65034 |

断网返航只读证明：tb1: offset172.7s,home1.98534m,path1.17401m,net1.16880m,Nav2EXEC1.17397m; tb2: offset171.2s,home2.01065m,path1.17720m,net1.16953m,Nav2EXEC1.17717m。
