# MR3-P2A.0 会话复盘与收口原则

本轮先核实际进程和原件，再读历史结论。接管时工作树干净、冻结为 `92f8bdf5bba1ba245dc53ca0964eef81a7fff938`；文档仍写 source-ready，实际四阶段原生已结束，deadline 的离线审计仍在运行。因此没有重跑原生矩阵，也没有修改运行中的验证代码。

## 当前交付

34个科学必需角色经原回执及同源码只读补验全部通过，P2A.0工程科学门已补齐、待用户验收；索引三组完整等价验证另列，额外deadline有意中止、未得第四组等价信用。原父编排中断保持，P2A未完成。最终结果见[V26报告](20261018_mr3_p2a0_v26_capture.md)。

## 判断

现有证据支持“执行工程与验证流程同时有问题”，不足以认定联合子目标 RL 研究路线已被否定。P2A.0 是训练前工程准备；它不能回答策略可学性和95%可靠性。当前最小闭环是收完同一冻结的已有矩阵、核实退出、保存失败与预算、提交可审阅结果。四阶段只覆盖固定三机、seed101和规定脚本；terminal是注入终态，deadline是300 KEEP。即使全通过，也不能证明95% PPO、连续时域安全、多日稳定或未见布局泛化；后续主瓶颈究竟是可学性、候选/表示还是执行采样工程，现有证据还不能判定。

## 上一轮哪些修复有依据

- V17 的原始横向速度约 .011m/s，确实超过 .01 停车门；命令为零不等于机体已经停住。
- V20–V22逐步把合法近身扫描对应到自身base_collision的射线命中；实际 ODE 库的定向反例证明 RayBox 的精确零/近零判断不一致。修求交有依据，清地图和过滤合法传感器数据没有依据。
- V24两条被选输出只隔20ms仿真时间，却隔约300ms墙钟；同版本源码使用wall timer固定步长积分。V25真实组件对照确认暂停时stock仍输出、fixed停止输出；只改两处timer使用节点时钟，是有针对性的修复。

这些证据支持当前工程修复，不证明所有旧失败都有唯一已证根因。V19的quickstep150组没有任何GOAL，缺少与baseline可比的运动和停车刺激；后续又包含RayBox、timer等变化，不能把完整新配置的通过归因于150一个参数，也不新增隔离对照作为本步出口。

## 哪些地方走偏了

1. 新观察器和编排没有先通过真正入口的小检查，V18文件名、V20/V22解释器、V23初始化阶段的错误接连阻断矩阵；这些与RL无关。
2. V25把多个取证条件压成一个错误且没有逐项after事实，035失败不能事后确定原因。更严格的检查如果没有完整诊断，反而扩大返工。
3. 活动验证器与历史证据混放，动态加载W7和多个旧版本并覆盖函数，版本与源码绑定不断复制。历史需要保留，活动工具不应依赖越来越长的档案链。
4. 当前文档没有跟上实际进度。只读文档会误以为完整矩阵尚未开始，并可能重复运行。

## 已定位的耗时机制

SLAM的TF发布使用墙钟速率。仿真暂停时仍会重复发布同一source；信息与运动观察器对每次回调写完整JSON。deadline的 `information_states.jsonl` 为1,013,618,334字节/1,016,301行，`motion_safety.jsonl` 为1,312,602,030字节/1,057,397行。独立只读尾段抽样中，7162条TF ingress有6845条为ignored_pending_order，约95.6%；这是局部抽样，不外推为全文件比例。

信息审计 `LedgerReplay.expected_latest()` 在每次选择时遍历全部admitted历史，形成selection×累计ingress的成本；`self.raw`还保存所有输入却不再读取。多个审计将整文件解码为Python对象，同时保留多份大列表。reset的正式只读审计约1825秒，其中full约1667秒。这些建立了明确的日志放大与高复杂度审计成本；未做完整profile，不把整个会话耗时唯一归因于TF或这个函数，也不因此降低安全门。原生步进还包含每20ms的多进程屏障往返；不能假定精简日志便能消除全部采样成本。本次deadline有效吞吐约.0559 transition/墙秒，双worker reset约.0741；这是规定工程工作量的实测，不是策略训练吞吐保证。

后续收敛方向应限定为：相同payload按SHA存一份，事件保留顺序、source、receipt、序号、hash及重复原因；流式校验，独立维护有序因果候选，避免每次扫描全前缀；活动验证代码移出report/assets，历史原件仍不可变。不得降采样丢事件、用producer所选引用替代独立oracle，或借重构修改物理与任务门。本轮保持生产冻结和所有原验证谓词不变，仅用独立小替换验证精确索引查询，以便和不可改写的原oracle逐项对照；这是本次收口的有界验证实现，不能继续把运行期覆盖链扩展成下一轮活动工具架构。长期活动工具整理需单独保持相同因果oracle及边界，不能据本步通过省略后续真实检查。

## 本轮交付边界

全部科学必需角色的真实原回执及披露的补验回执均已完成并通过核验，运行报告已记录真实结果、reset非必需逐回合物理FAIL、同冻结合并覆盖门、PID/start退出与全部预算。只将实际通过的准备出口标为待用户验收；不启动PPO，不把脚本矩阵说成95%策略或连续动力学安全证明。


## 本轮接管后发现的原编排中断

接管时原deadline审计仍在运行；其full、drive、peer、control、settled-turn、FIFO和来源闭包七项先后真实return0/PASS。约在原命令启动四小时的边界，整个父进程组消失，原ledger停在deadline audit child_spawned，没有原最终capture、aggregate和information结果。当前会话没有向该原父组发送终止信号；后续可选索引reader的单次SIGTERM另列；时刻吻合只能支持外层限制的推测，具体信号/原因未知，kernel journal无记录也不能排除OOM。

为避免再采样同一矩阵，本轮以原f736源码声明并执行只读information补充，使用全新输出。原f736补充真实returncode=0/PASS、2909.4306966429576墙秒、signals_sent=0；输出SHA`4254219b07e635517652daf723b146f53c7f362ab5541da57f9c4468e1fb29e9`。该补充自然返回0/PASS、signals_sent=0，是选定缺失科学角色；wrapper从工具stdin执行，没有伪称存在的原始源码文件。另外完成等价索引reader验证，只替expected_latest，保留所有科学谓词与完整输入；57648次逐查询参考max对照及interface/terminal/reset三组完整报告deep equality通过（含8次reset回合）。额外deadline索引尝试有意中止：root以保存PID/start=3915500/405102066核对后通过pidfd发送一次SIGTERM；实际executor wait返回-15，630.2861267556436墙秒，passed=false、输出仍缺失、源末SHA不变。这是intentionally_stopped/incomplete，不获得第四组等价信用，不影响已自然PASS的原f736科学角色。索引验证不替代已通过的原f736补验，也没有新native信用。原七项deadline PASS不重跑，原ledger、原FAIL及缺失final不补造；按原34个科学角色核验原回执和同源码选定补验。原编排永久记INTERRUPTED、返回码unknown。科学证据补齐与原父进程成功是两个不同结论。实际argv、PID/start、wait、源SHA、输出SHA和输入绑定由独立收据保存，实际override来源在V26结果报告公开。


## 核查入口

[原停车失败](20261017_mr3_p2a0_v17.md), [实际ODE反例](20261018_mr3_p2a0_v22_ray_box.md), [平滑器归因及范围](20261018_mr3_p2a0_v24_install.md), [组件对照与V25失败](20261018_mr3_p2a0_v25_smoother.md), [本轮完整原件与恢复结果](20261018_mr3_p2a0_v26_capture.md)。

- [TF发布循环](../../../../../../../ros2_ws/ros2-multi-robot-automap/src/slam_toolbox/src/slam_toolbox_common.cpp)。
- [信息入口与记录](../../../../../../../ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_information.py)。
- [运动观察记录](../../../../../../../ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py)。
- [原独立信息回放](assets/20261017_mr3_p2a0_v9/independent/mr3_independent_information_v1.py)。
- [当前受控信息消费者](assets/20261017_mr3_p2a0_v10/independent/mr3_independent_information_v2.py)。


## 停止额外验证与二次复杂度诊断

额外deadline索引尝试有意中止：root以保存PID/start=3915500/405102066核对后通过pidfd发送一次SIGTERM；实际executor wait返回-15，630.2861267556436墙秒，passed=false、输出仍缺失、源末SHA不变。这是intentionally_stopped/incomplete，不获得第四组等价信用，不影响已自然PASS的原f736科学角色。

原A9:350的cycle时钟谓词每次遍历self.selections历史；原deadline有46302次selection，按有效完成记录及该循环可推导约1071914451次key迭代。这是静态复杂度分析，不是运行期profile。原科学消费者已完整PASS，继续拉长同一语义的可选回放不再是出口需要；不追加第二项优化或新native。


## 下一步的采样预算约束

P2A.0通过不等于现有pilot余量足够支撑默认采集。当前训练器默认episode_steps=300，先等待collect_episodes完成本轮回合，再构造buffer并调用model.train（[训练器](../mr3_learning/ppo.py)）。本次300 KEEP工程回合实测5368.246922858991墙秒，已大于剩余pilot的2905.954739546403墙秒；这直接说明“默认再开一个300步回合即可取得新更新”缺乏预算依据。策略可能提前终止，PPO推断及行为也不同，不能据KEEP脚本断言训练必定超时或恰好零更新，更不能把脚本吞吐直接当学习性能。

因此后续应先明确剩余预算能闭合的采集/更新安排及其证据，再申请进入相应训练步骤；保留失败round不训练、真实20ms因果链和原任务门，不自动扩预算、缩短95%任务或改回手工探索。本段是由现有代码与原件推导的交接约束，不增加本次P2A.0出口门、不运行新pilot，也不提前断言表示或RL路线可学/不可学。
