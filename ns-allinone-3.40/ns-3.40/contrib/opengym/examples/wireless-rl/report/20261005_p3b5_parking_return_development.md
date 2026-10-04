# P3B.5 v60独立开发失败

2026-10-05 P3B.5 v60独立开发五格FAIL，冻结79a3b05b5101418cd99dd8cb7cd6d4630c0eb823；2026-10-04 17:39:47–17:52:26UTC三个owner全部exit0、原观察器自然关闭。lab3/101原生COMPLETE198.5s/charge0/最低23.35519；force ideal原生COMPLETE214.8s/各charge1/最低8.91814，force fault300.1s RALLY timeout/各charge1/最低8.03192，安全子门通过但非任务成功。zero ideal283.8s检测/291.2s RALLY、300.0s timeout/各charge1/最低4.03001；zero fault原生COMPLETE271.6s/总charge1/最低21.73648。五格0碰撞/0耗尽/0failed/0infra、五ledger TTL/version与graph旁路PASS；原生阈值未改，无重试/回填。前沿接续/驻点绕行成本/返航watchdog尚不能解决晚发现；只读日志证实远端不够完整任务预算的探索fallback与返航先于迟到的西北发现，watchdog有一次真实取消，但不作单因素因果或最坏时保证。完整报告report/20261005_p3b5_parking_return_development.json/.md。809/28091从未执行，正式57格/PASS图文未启动，P3B.5仍未完成，无ns3/RL。

| episode | phase / seconds | charges | minimum energy |
|---|---|---:|---:|
| p3b5_v60_dev_fixed_lab101_lab_far_northwest_3r_seed101 | COMPLETE / 198.5 | 0 | 23.35519 |
| p3b5_v60_dev_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 214.8 | 2 | 8.91814 |
| p3b5_v60_dev_forced_forced_charge_outage_fault | RALLY / 300.1 | 2 | 8.03192 |
| p3b5_v60_dev_zero_ideal_lab2_rally_8d4d5c469d | RALLY / 300.0 | 2 | 4.03001 |
| p3b5_v60_dev_zero_zero_rally_lab_fault | COMPLETE / 271.6 | 1 | 21.73648 |

Zero ideal detects283.8s/RALLY291.2s, so peer final error3.67768m at300s is late discovery, not failed native hold alone. Before discovery both execute unfunded long frontier fallback: tb2 west path9.13m utility19, tb1 west11.47m utility7.8; repeated local prefixes/reassignments precede reserve-triggered returns. Local tb2 watchdog really cancels no-waypoint-progress return once and replans; all five originals stay positive, which is observed safety, not a worst-case guarantee or single-factor causal proof. Both charge once in zero ideal and resume current funded west frontier, but discovery remains too late. Lab native198.5/charge0 versus prior timeout/charge2 is an asynchronous multi-change result, not isolated parking benefit. Forced fault detects253.4/RALLY262.9 and is nonCOMPLETE300.1, while its positive/every-robot-charge safety subgate passes. All failures and original start/finish/commands retained; no809 exposure.
