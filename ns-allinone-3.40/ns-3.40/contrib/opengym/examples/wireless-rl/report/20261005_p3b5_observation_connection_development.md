# P3B.5 v94独立开发FAIL

2026-10-05 P3B.5 v94独立六格开发FAIL，冻结9b513fab47c445e1da44bb0304cc77bb301a3000；全部原owner/观察器自然关闭后逐项审核。p3b5_v94_dev_fixed_lab101_lab_far_northwest_3r_seed101 FAIL/RALLY/300.0s/charge3/min21.04333；p3b5_v94_dev_fixed_lab202_lab_far_northwest_3r_seed202 PASS/COMPLETE/280.3s/charge2/min25.82174；p3b5_v94_dev_forced_ideal_forced2_rally_86fbb43bc6 FAIL/RALLY/300.3s/charge2/min15.92234；p3b5_v94_dev_forced_forced_charge_outage_fault PASS/RALLY/300.1s/charge2/min10.36649；p3b5_v94_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/226.3s/charge1/min18.72230；p3b5_v94_dev_zero_zero_rally_lab_fault FAIL/FAILED/213.1s/charge0/min17.41613。时间审计6/6 PASS、运行图6/6 PASS、原生COMPLETE2/6，参数测量失败0；缺失不推断、各审计独立，不因一项失败跳过其它证据。强制fault仅各机充电/正能量/无碰撞安全子门，未原生完成不计任务成功。恢复既定观测交接5s；待行观测者对准有效交付目标、调查腿可见时朝向目标，分配受阻复用实际射线收益前沿绕行调查连接区域；不续租或虚构未知格，不增加完整任务重试，原地图/电池/poseTF/target TTL、净空/机体/能量/300s与.35/.05/.1/5s原生门槛均不变。所有源/参数/helper/用户17文件hash及四master/PID关闭核验通过，完整源/原始/hash/AP/物理旁录/精确命令见report/20261005_p3b5_observation_connection_development.json/.md。共享宿主及启发式预算不提供最坏时限保证，无单因素归因；几何视觉proxy/原生与AP只读取证不参与控制。809/28091从未执行，开发101/202/303不是holdout，本批不是正式57格替代，P3B.5尚未完成，无ns3/RL。

| episode | check | phase / seconds | charges | minimum energy | temporal | graph |
|---|---|---|---:|---:|---|---|
| p3b5_v94_dev_fixed_lab101_lab_far_northwest_3r_seed101 | FAIL | RALLY / 300.0 | 3 | 21.04333 | PASS | PASS |
| p3b5_v94_dev_fixed_lab202_lab_far_northwest_3r_seed202 | PASS | COMPLETE / 280.3 | 2 | 25.82174 | PASS | PASS |
| p3b5_v94_dev_forced_ideal_forced2_rally_86fbb43bc6 | FAIL | RALLY / 300.3 | 2 | 15.92234 | PASS | PASS |
| p3b5_v94_dev_forced_forced_charge_outage_fault | PASS | RALLY / 300.1 | 2 | 10.36649 | PASS | PASS |
| p3b5_v94_dev_zero_ideal_lab2_rally_8d4d5c469d | PASS | COMPLETE / 226.3 | 1 | 18.72230 | PASS | PASS |
| p3b5_v94_dev_zero_zero_rally_lab_fault | FAIL | FAILED / 213.1 | 0 | 17.41613 | PASS | PASS |
