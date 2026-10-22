# MR3 P2A V49：真实启动顺序与故障传播

2026-10-23实际闭合 **PASS**，freeze `14719a72b96cff65b134b7d46ec6d2ccbf84e061`。唯一活动两套环境各rooms101/一步：2/2真实返回、两回合真实外部截断及正常退出；native190.595533179秒，完整父等待**212.565365239秒**（内部212.319052807包含其中，不叠加）。[外部最终review](assets/20261023_mr3_p2a_v49_startup_protocol/independent_closed_review_v1.json) PASS：874源/10ELF、完整wait/source与Git一致；91保存PID/start含原两暂排祖先均freshgone，Z若仍存在将判FAIL。工程累计**55959.6049312316018/75000**、余**19040.3950687683982**，pilot/final-only不动。

独立只读startup日志两机254/294行（159002/183599B），全部解码，pause→全零接管/storage→20ms bootstrap→release顺序完整，release37.0/35.58sim秒时四项均True、真实clock等于physical。两机pause时motion也已True，故本次不提供原生“暂停时False后变True”故障注入信用；该边界只有人工phase回归。startup138.15/135.33墙秒、首step49.79/47.09墙秒，仅两首步，不能推广long-step吞吐。0模型/0优化器/0GPU，本诊断不填充完整科学资格的任何角色或提供95%信用，旧V45FAIL保持。

[完整库存](assets/20261023_mr3_p2a_v49_startup_protocol/closed_inventory_v1.json)已无损归档**271文件/497827640原字节→38177415保存字节，0symlink**，每份原SHA/解码SHA及前后stat/成员集相符，原件保留。完整父等待和console位于[closed execution](assets/20261023_mr3_p2a_v49_startup_protocol/closed_execution/actual_wait/actual_wait.json)。后续启动新V50，而非重开本活动：新fault消息需在PPO build/train前按epoch/schema拒绝，之后新freeze全12EP/30角色→minimum→pilot→final-only，P2A仍未完成。

下文保留执行前的具体实现、首轮失败、CPU与费用声明。

本活动准备完成，尚无 V49 World/native/学习结果。V45 的 startup/cleanup FAIL 保留，V46/V47 的有限描述不能确定 worker 当时实际缺少哪项 ready，也不能把 82.4 秒的故障倒推为 37.92 秒之前的根因。用户已授权自主持续完成 P2A，无需再次一般审批；P2B/gateway 不启动。

新 [启动契约](../MR3_STARTUP_CONTRACT.md) 为显式 Reach 模式固定选择 `received-input-pause-drain-v1`。初始输入、monitor 与 recorder 的真实接收先允许暂停；随后真实全零 takeover/storage 及原有 20ms bootstrap 收齐控制前缀，必须通过精确 motion status、三机 storage 和四项实际 ready 才能请求 snapshot/release。默认 legacy 保持。源龄、原发布序列、图/几何、安全和 95% 任务门均不变。

独立静态检查发现首版“暂停后直接等 motion Bool”会阻断 sim-time timer 的重新计算。此版不执行原生，改用既有真实接管和 bootstrap 推进后再检查；不写造 ready，也不重复相同 clock 的输出。reset 的 420 秒绝对截止从 supervisor 入口计算，扣除创建/发送；启动工作截止还保留 60 秒清理及 5 秒响应，清理阻塞共享剩余时间。首次永久 Reach fault 保留原 reason/clock，并通过现有 failure topic 传播；重复 ingress 仍记原件，真实停止及异常停止路径均须验证。

A48 的两套精确数学候选已在本版本接入各自 producer/独立 reader；cf46 geometry 原字节不变。只复用已验证 exact Q 的不可变根界与恒等整数多项式计算，不共享两方数学或改变安全集合。V48 原先“禁用”是其闭合时事实，本版本须重新通过相关 CPU 和原生资格。

首轮人工 CPU：geometry 597 PASS/2 fixture FAIL（post-release HOLD 缺少真实格式的 anchor/zero target；legacy 字段断言误包含既有 startup_wall_sec），原回执完整保留。learner、reader、snapshot、双环境 readiness 通过。生产顺序/清理修复后的第二轮实际通过：geometry608、learner228、reader12、snapshot9，共857项代码回归；检查器13组人工自检及双环境readiness也通过。各组均已rc0/reap且源前后相等，见[CPU索引](assets/20261023_mr3_p2a_v49_startup_protocol/cpu_validation_index_v1.json)。首轮不拼作最终准入。

另以固定 64 个契约年龄、phi=1.2×(.78+age)，在 0.936–1.536rad 人工域比较冻结基线与候选：12 个计时块全部公共数值 hash 相等。完整生产 pair cold/warm 比例约 1.733/1.104，reader cold trig/direction 约 15.351/8.109；warm trig 变慢，warm direction 仅约 1.028。与其他 CPU 并行、单次短块、baseline 先行，既非实际源龄分布，也非 ENV 吞吐。原 V48 小角域及 cold-sqrt 回归结果保留。见 [v2 结果](assets/20261022_mr3_p2a_v48_support_cpu/contract_angle_result_v2.json) 和 [实际 wait](assets/20261023_mr3_p2a_v49_startup_protocol/checks/contract_angle_cpu_v2/actual_wait.json)。结果中的 production_enabled=False 表示该人工 harness 自身不启用生产；canonical 的 V49 集成状态由本报告及代码确定。

下一次原生仅一次新冻结启动诊断：2 worker，各为三个机器人、rooms101、1 个真实 ENV.step，固定合法均匀输入 seed490101。既有 benchmark native allocation600（含120 close reserve）+外尾120，总预约720工程秒；总额是事后完整等待费用门，不是 OS 硬终止，超额全费并 FAIL。完整接收 journal 有界独立检查及 PID/start 关闭检查随同执行。它不填充完整资格的 12EP/30角色，也不启动 PPO、pilot 或 final-only。874份源/准备输入、10份ELF、argv 和不可重试规则已在 [scope](assets/20261023_mr3_p2a_v49_startup_protocol/startup_scope_v1.json) 封存，待新freeze后执行。

工程入场55747.0395659926018/75000，余19252.9604340073982；当前 CPU/静态工作新增0。pilot 余1870决策/2905.9547395464029秒、final-only三场及95%门不动。原完整20100预约已不可负担；已实现并通过9项人工回归的显式 `bounded-original-workload-v1` 资源预约 profile：默认18000及原分配字节保持，新profile只能小于等于原上限，真实余额、120关闭预留、阶段/总量及原forward-carry均须满足。完整12EP/30角色和科学门保留；尚未声明/执行新完整链。P2A 未完成。

[入口静态review v1](assets/20261023_mr3_p2a_v49_startup_protocol/independent_entry_review_v1.json)发现直接asset脚本导入失败风险；改为canonical W cwd的模块入口，根实际 `-m …run_startup_v1 --help` 导入通过，[v2独立静态review](assets/20261023_mr3_p2a_v49_startup_protocol/independent_entry_review_v2.json) PASS。v1采集源码绑定时入口已修，不能用其绑定复原修前文件；原CPU v2 source snapshot保留修前实际字节。旧CPU没有执行新编排入口，兼容排除精确仅prepare/run/execute三份脚本，它们自身均纳新scope/Git冻结；其余受测runtime/test/helper仍须当前SHA相等。scope封存本身另以真实CPU wait .981559887秒通过，不代表native。
