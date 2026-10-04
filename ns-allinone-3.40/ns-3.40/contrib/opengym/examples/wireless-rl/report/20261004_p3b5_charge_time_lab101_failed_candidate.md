# P3B.5 v56失败候选

2026-10-04 P3B.5 v56原候选FAIL，冻结3d079215caacf9e5e31866ca4db236a5cff3236c；14:55:48–15:17:15UTC自然结束，7started/7raw/0接触/0基础设施失败、7账本审计PASS，其余50格未运行。初始force ideal原生COMPLETE273.6s/各charge1、E0双格和双机真实断网返充探针通过；首个固定lab3/101在99.8s进入RALLY、300.4s timeout，2charges、最低20.8966，不能代替完整验收。只读原生诊断见tb2视线无遮挡时朝向转出90度FOV并产生检测间断，原因仍待核验。全部原始失败保留，不回填/重试/放宽300s与原生保持门限。新809/28091从未执行，可在仅开发seed修复后重新冻结控制SHA再首次暴露；初静态文件误把通用采样点标为spawn/charge，原文件保留，另以真实launch三个起点/充电点补查0.45m连通PASS，world未改。证据见report/20261004_p3b5_charge_time_lab101_failed_candidate.json。全部owned owner/观察器/master关闭后才归档，domain222未动；完整strict checker/PASS报告/图未执行，P3B.5仍待完成，无ns-3/RL。

| episode | phase / elapsed(s) | success | charges | minimum energy |
|---|---|---:|---:|---:|
| p3b5_v56_zero_ideal_lab2_rally_0678e85373 | FAILED / 0.8 | False | 0 | 0.00000 |
| p3b5_v56_zero_battery_exhaust_lab_fault | FAILED / 1.8 | False | 0 | 0.00000 |
| p3b5_v56_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 273.6 | True | 2 | 6.63120 |
| p3b5_v56_forced_forced_charge_outage_fault | EXPLORE / 300.1 | False | 2 | 8.14450 |
| p3b5_v56_returnproof_ideal_forced2_rally_4c7c808f36 | EXPLORE / 300.2 | False | 2 | 9.69955 |
| p3b5_v56_returnproof_physical_return_under_blackout_fault | EXPLORE / 300.0 | False | 2 | 9.61204 |
| p3b5_v56_fixed_lab101_lab_far_northwest_3r_seed101 | RALLY / 300.4 | False | 2 | 20.89659 |

lab/101在300.4s尚未完成，观察者tb2无返充、最低能量正；native yaw偏离目标视野是只读观测，尚不证明具体控制原因。新809未暴露，原707已暴露。后续需开发修复并重新冻结完整批次。
