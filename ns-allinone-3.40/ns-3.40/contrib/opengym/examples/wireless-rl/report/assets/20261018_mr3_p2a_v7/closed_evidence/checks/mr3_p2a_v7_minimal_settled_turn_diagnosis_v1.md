# V7最小链首回合 settled-turn 只读诊断

冻结 `8d7f19fc8225eae0ccdc6609b828ee8e832f7c93`；原件目录 `/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v7_minimal/native/round0000/worker0/episode001_open_101`。未运行native或完整审计、未发信号、未改仓库。正式两门仍由主代理执行，pilot不启动。完整逐行原件、数字、SHA与提案见 [mr3_p2a_v7_minimal_settled_turn_diagnosis_v1.json](/tmp/mr3_p2a_v7_minimal_settled_turn_diagnosis_v1.json)。

首因是tb3真实native机体速度违反原settled-turn条件模型，不能归为map/TF跳变。`motion_safety.jsonl:70968` 的原始own odom输入1482、源54.155秒，vx=0.019766829596618123、vy=0.004178201595048607，平面速度 **0.02020358683181293m/s > .01m/s**；紧接record70969记录 `active settled turn drift bound exceeded`。原odom规范字节SHA为 `6395f6d4ebf11b6ad3eefbed0bab2ad0b9df8643ecf333810cc7b4acf4dde6e4`。该速度由WORLD里程计直接取模型WorldLinearVel并旋转到机体坐标，不通过融合图/TF位移差分求得。

`motion_safety.jsonl:58001` 在51.08秒激活，之前publication零线速度起点49.94秒。native drive在51.08至54.155秒共154条实际收取target均线速度零；最新证明的累计弦长0.005674432986632134m小于.0078m，首次触发是速度条件。`drive_tb3.jsonl:6512-6517` 保留54.12秒[0,0]制动、54.14秒[0,.8]恢复、54.155秒实际轮写入；后续6518在54.16秒收取安全零target。轮命令不等于机体响应，制动/重启导致漂移的因果尚未证明。

纠正早期即时推测：54.12秒的零输出record70882发生在源54.121秒odom入站record70900之前；不能用future latest解释该次空证书。此前三条源为54.019/54.053/54.087秒，最老源age=101ms，确实超过原100ms门。因此该次拒绝符合原规则，不能靠延长窗口、保持旧授权或重置漂移预算“修复”。

本回合真实返回navigation_failure终态：8个决策，末步有效.22秒、物理.24秒；失败reward=-19.83890552360084。worker返回0且未强杀，evaluation的collision_events=0、collision_monitoring_fresh=true。现存motion consumer第647-648行仍无条件拒绝模型失败；真实终态和无接触不补回工程/模型信用。

下一步仅为可审阅提案，未经执行不称修好：

1. 先对原始到达前缀、causal own-state选择和三样本资格作短只读一致性复核，保持100ms、.94s/.78s与全部raw速度/弦长检查。若没有真实不一致，不在此理由上修改certificate。
2. 预声明同冻结、相同三机器人初始/peer/settling条件的原生配对工程对照：原[0,.8]/零切换与持续[0,.8]请求。保留原guard、20ms因果链及所有真实drive ACK；guard若不能实现连续对照，保留为不完整对照，不旁路放行。全量记录本机raw odom、stored targets、轮执行、18路接触与资格历史。
3. 唯一候选修复限于确有证据的causal certificate/state前缀一致性，保留全raw故障监测和全部原门；同新冻结两对照native通过以前不称修好。若需改drive，另立真实执行、plant模型/制动/源时延/二进制来源门，再复验受影响工程与最小PPO链。

.01m/s、.0078m、.50m、95%/300秒、原传感器和交付因果边界均不改变。原工程余额 **6579.143210123293墙秒**，历史完整四阶段 **10051.210844483227墙秒**，差额 **3472.067634359934墙秒**，原余额不足；历史时长不是新预算或保证，不自动扩额或挪用pilot/验证额度。

源文件均核对Git冻结字节与当前工作树相同：

| 源角色 | SHA256 |
| --- | --- |
| tracker | `06ca6ece92ca49072df9eedbdd5396148ca2e09d4f2560204448e460e3e73ae7` |
| guard | `63d3a59e48cf34180308a494761bc467214fc30ea36b1017dd13e9bd33aa03fc` |
| drive | `09f741ee154d620fb3d62f8473853929231093fd8cc0b9a4be62b535b514dc05` |
| paired_actuation | `dca3dbaf01251cf7ffe167f1dabb23a45b4fc95d6ad317dcc3290ff50ecf9a1b` |
| motion_consumer | `5254fcc83ea9c36fb38cd2b300b77390d23d6633be8c04a1f4a6915f4d893359` |
| environment_contract | `41feac9a6d76adb839a615d7703e78e1b1c9f2ce22d55aba805387643536380e` |
