# P3B.5 v101原生启动失败原候选

2026-10-06 P3B.5 v101正式原候选FAIL，冻结0fff5eb4ed3b57e1f60a9f7a6e8d1ecdabac1b93；04:30:04–04:43:13UTC全部原owner/观察器自然关闭。5attempted/4native-started/4raw，1强制ideal启动600s超时且episode_started=false/无原生结果、图和安全trace；52not-invoked含全部十fixed及809（53未进入原生评估）。不把summary缺结果行计为raw或启动，不推断该格碰撞/电量。原force fault未调用；E0双格原生FAILED2.1/1.9s且无导航；controlled-return双格EXPLORE timeout300.3/300.1s，各机器人charge1、最低9.70732/9.56846，仅安全子门。实际fault黑障62..248s两机返航路径1.21190/1.16494m、净回home进展1.20063/1.15387m、Nav2 EXEC运动1.21188/1.16491m，关闭后原strict physical-return审核PASS。54纯协议/5账本因果TTL版本与决策租约PASS，4图0旁路，1图缺失；四raw0接触，1infra/操作失败。原网关观察器exit0；附加AP因无result被owner SIGINT后重复rclpy.shutdown报错exit1，最终metadata未写完整，原traceback与部分数据保留。原tb2 SLAM只到stack-size输出、未Ceres/Lidar初始化，tb2 planner lifecycle异步请求失败；只读/proc五线程均futex、没有已观察到UDP等待线程，不能据此证明SHM/DDS根因。实际19350..56七端口/PIDs/master环境后代关闭、全部冻结source/config/helper与17用户资料哈希通过；原600s启动/300s任务及原生5s等阈值未放宽，无整轮重试/回填。准备helper第一次在push未完成时被clean-pushed guard拒绝、未创建helper/未启动任务；卡住SSH push仅终止已核验自有git/ssh，随后IPv4 bounded push成功，再首次启动本批；全部记录保留。归档第一次读取缺失result字段KeyError（原summary确无该键），修正仅只读归档器用get，任务没有重启。809.world/seed809/fault28091从未执行；完整strict gate/PASS图文未执行，P3B.5仍未完成，无ns3/WiFi/RL。证据report/20261006_p3b5_native_startup_failed_candidate.json/.md；下一候选只在全部关闭后前瞻验证原生启动环境，不能把当前缺失结果修补为成功。

| original | native phase / seconds | charges | minimum energy |
|---|---|---:|---:|
| p3b5_v101_forced_ideal_forced2_rally_86fbb43bc6 | absent; native evaluation not started | unknown | unknown |
| p3b5_v101_zero_ideal_lab2_rally_0678e85373 | FAILED / 2.1 | 0 | 0.00000 |
| p3b5_v101_zero_battery_exhaust_lab_fault | FAILED / 1.9 | 0 | 0.00000 |
| p3b5_v101_returnproof_ideal_forced2_rally_4c7c808f36 | EXPLORE / 300.3 | 2 | 9.70732 |
| p3b5_v101_returnproof_physical_return_under_blackout_fault | EXPLORE / 300.1 | 2 | 9.56846 |
