# P3B.5 v91审计更正

2026-10-05 P3B.5 v91归档审计更正：此前734bc85“所有原ledger/graph审核通过”错误，后置核验KeyError(temporal_audit)后仍继续提交；现分别审计六原始格，未修改原checker/ledger/helper。lab101时间审计FAIL，首个observer_handoff_wait在2243.282使用2234.082确认、年龄9.2s，违反原5s交接门槛；其余五时间审计PASS，六运行图独立PASS，三个原生COMPLETE、两fixed任务失败及forced fault安全结果不变。原JSON/失败audit/原始物理旁录/hash/提交保留，report/20261005_p3b5_observer_role_lease_audit_correction.json/.md明确取代旧“六时间通过”结论。全部原owner/观察器/四master已关闭，原源/配置/helper/用户17文件及raw hash一致。v90角色保护60s未满足既定5s门槛，不能进入正式验收；后续恢复5s并修复实际朝向/连接调查，绝不放宽checker、TTL、能量、净空或原生完成条件。未重跑、回填或执行809/28091，P3B.5尚未完成，无ns3/RL。

- p3b5_v91_dev_fixed_lab101_lab_far_northwest_3r_seed101: temporal FAIL, graph PASS, native FAIL
- p3b5_v91_dev_fixed_lab202_lab_far_northwest_3r_seed202: temporal PASS, graph PASS, native FAIL
- p3b5_v91_dev_forced_ideal_forced2_rally_86fbb43bc6: temporal PASS, graph PASS, native PASS
- p3b5_v91_dev_forced_forced_charge_outage_fault: temporal PASS, graph PASS, native FAIL
- p3b5_v91_dev_zero_ideal_lab2_rally_8d4d5c469d: temporal PASS, graph PASS, native PASS
- p3b5_v91_dev_zero_zero_rally_lab_fault: temporal PASS, graph PASS, native PASS
