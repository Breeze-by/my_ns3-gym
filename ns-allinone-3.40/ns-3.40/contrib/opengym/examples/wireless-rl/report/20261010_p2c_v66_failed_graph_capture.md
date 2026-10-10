# P2C.1 v66 原图采集门禁 FAIL 保留

冻结 `a54ecfbe21fdf12ca5674b6af685748815b23ee4`，首dev_forced2原生COMPLETE241.3秒，检测131.3、RALLY176.5秒，两机各charge1/min16.520507164、零接触耗尽FAILED机器人。原生保持5.5秒/56样本/最大gap.1秒，最大位置误差.025209米。owner/observer0、PID全关闭后修改。原完整strict仍FAIL：monitor_graph_audit读取早期graph.json缺/gateway_metrics而KeyError；原18独立源码冻结分项PASS不能替代整体。余3开发/17正式/2物理与917未调用。

原bypass_audit等待既有central/costmap节点名字齐全后即拍图，未要求指标节点和AP全部正端点完成发现。原早期图中headquarters_control只枚举部分publisher，subscribers/action_clients为空；因此仅检查“未看见禁止端点”不能证明完整拓扑。另由原read-only native observer拍摄的native_graph.json有63节点，metrics完整无控制权限、AP输入/命令与原本地TF绑定齐全。两个图均原证据SHA绑定，不能补造早期缺节点或覆盖它。

未来只改read-only采集契约：早期bypass图另留initial_bypass_graph.json，既有观察者在原steady2秒timer下等完整typed metrics/AP/merge和原native TF/bypass/headless规则，首次合格实际snapshot同时独占写graph.json/native_graph.json。原生/control/SLAM/Nav2/physics/300s/5s/TTL/尝试与全部case刺激逐字保持。原完整FAIL不回填、新同源4→17+2仍必需。

冻结七源码字面、原strict/18审计/两图/私有和native安全账本与所有原raw文件SHA保存，CDR留原路径。一处只读读取猜测不存在scripts/audit_p3a_bypass.py、一次rg指定不存在run_p3c5_live.py，均exit2；随后rg实际src bypass_audit.py及run_p3c5_audit.py确认真实流程，未重跑原任务。无P4/ns-3/Wi-Fi/RL。

[JSON](20261010_p2c_v66_failed_graph_capture.json)
