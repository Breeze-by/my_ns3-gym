# P3B.5 v97独立开发FAIL

2026-10-05 P3B.5 v97独立六格开发FAIL，冻结8c0ad72523847e43c7b7457ea2781885c3f24c43；全部原owner/观察器自然关闭后逐项审核。p3b5_v97_dev_fixed_lab101_lab_far_northwest_3r_seed101 PASS/COMPLETE/247.1s/charge1/min18.80650；p3b5_v97_dev_fixed_lab202_lab_far_northwest_3r_seed202 FAIL/RALLY/300.0s/charge1/min19.49767；p3b5_v97_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/211.5s/charge2/min16.22351；p3b5_v97_dev_forced_forced_charge_outage_fault PASS/EXPLORE/300.1s/charge2/min9.00373；p3b5_v97_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/238.4s/charge1/min24.29664；p3b5_v97_dev_zero_zero_rally_lab_fault PASS/COMPLETE/187.5s/charge1/min23.51882。时间审计6/6 PASS、运行图6/6 PASS、原生COMPLETE4/6，参数测量失败0；缺失不推断、各审计独立，不因一项失败跳过其它证据。强制fault仅各机充电/正能量/无碰撞安全子门，未原生完成不计任务成功。保留原交接5s；最终前沿收益过期且另有当前可达/完整预算/实际机体/在途预约/有效可见前缀的替代时，进展中可取消并排空旧腿再正常重选。近到达/无预算或替代/地图过期/本地返航/相机重搜保持原行为。有效检测只指导安全位置的观测朝向，即使目标LOS未知也不授权未知格位移；不续租或虚构未知格，不增加完整任务重试，原地图/电池/poseTF/target TTL、净空/机体/能量/300s与.35/.05/.1/5s原生门槛均不变。所有源/参数/helper/用户17文件hash及四master/PID关闭核验通过，完整源/原始/hash/AP/物理旁录/精确命令见report/20261005_p3b5_fresh_frontier_replan_development.json/.md。共享宿主及启发式预算不提供最坏时限保证，无单因素归因；几何视觉proxy/原生与AP只读取证不参与控制。809/28091从未执行，开发101/202/303不是holdout，本批不是正式57格替代，P3B.5尚未完成，无ns3/RL。

| episode | check | phase / seconds | charges | minimum energy | temporal | graph |
|---|---|---|---:|---:|---|---|
| p3b5_v97_dev_fixed_lab101_lab_far_northwest_3r_seed101 | PASS | COMPLETE / 247.1 | 1 | 18.80650 | PASS | PASS |
| p3b5_v97_dev_fixed_lab202_lab_far_northwest_3r_seed202 | FAIL | RALLY / 300.0 | 1 | 19.49767 | PASS | PASS |
| p3b5_v97_dev_forced_ideal_forced2_rally_86fbb43bc6 | PASS | COMPLETE / 211.5 | 2 | 16.22351 | PASS | PASS |
| p3b5_v97_dev_forced_forced_charge_outage_fault | PASS | EXPLORE / 300.1 | 2 | 9.00373 | PASS | PASS |
| p3b5_v97_dev_zero_ideal_lab2_rally_8d4d5c469d | PASS | COMPLETE / 238.4 | 1 | 24.29664 | PASS | PASS |
| p3b5_v97_dev_zero_zero_rally_lab_fault | PASS | COMPLETE / 187.5 | 1 | 23.51882 | PASS | PASS |
