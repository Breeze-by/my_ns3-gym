# MR3 P2A V21 原生可行性与容量诊断

**实际闭合：FAIL。冻结 `c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90` 完成两回合/64步原生返回，但第一回合 Runtime 的真实 storage ACK 跨订阅时序不满足现门；无重试、无训练资格。工程末账 `41480.3336378496018 / 52000`，余 `10519.6663621503982` 秒。下方冻结前预声明保留，不能用准备状态覆盖本结果。**

用户在[评估交接](20261020_mr3_p2a_assessment_handoff.md)后指示“好，现在按要求继续执行P2A吧”。本轮在既有 P2A 常规修改、修复、验证授权和 52000 工程墙秒上限内推进一次有界诊断，不申请或推断 60000 扩额，不实施二维环境，不启动 PPO、pilot、final-only、P2B 或 gateway。P2A 未完成；现行完整四阶段/12 回合/30 角色资格与科学门不变。

## 冻结前实施与预声明

复用 benchmark、Supervisor、原生 SLAM/Nav2、reach 执行和 20Hz 激光配置；运行时 ROS 源、ELF、接触/距离/动力学门未改。新增 `--diagnostic-uniform-seed` 只在真实 1000 位合法掩码上随机抽样，每 worker 使用独立 `random.Random(seed + 1000003 * worker_id)`，不排序目标、不额外过滤、不读真值、不调用模型或优化器。与其他工程刺激互斥，真实任务失败/异常后停止后续 reset，保留实际返回及关闭。

固定三台 tb1/tb2/tb3，1 worker，两个 `open:101` 开发回合，各最多 32 决策，总最多 64；动作随机种子 41，ROS domain224，Gazebo port14901。重复开发场景用于观察完整重置与执行，不是未见布局或独立泛化验证。随机动作不等于实际 PPO 输出，不能据此宣称策略可靠。

入场工程末账为 V20 的 `38216.5104974146018 / 52000`，余 `13783.4895025853982` 秒。本轮仅预约 **6500 工程墙秒**，其中 native 上限 3200（含关闭预留180），其余用于独立读者与外部收口，末端预留300；每个只读消费者由既有 owned-child supervisor 在900秒自动中断并真实wait，必要清理尾照实收费。原生采用现有有界RPC/合作式入场与正常关闭，不对不明进程发送信号；这些是预算守卫，不是操作系统最坏时间保证，超额仍按真实费用记录失败。pilot 仍余1870决策/2905.9547395464029秒，三场final-only不动。

两个回合只有在前回合成功或按外部采样上限正常截断时才继续；首次任务/基础设施失败不启动下一回合。不因失败自动重试、扩大活动或重跑完整矩阵。阶段未取得的证据标为缺失/失败，不以 CPU 或旧 PASS 补齐。

## 独立检查与信用

诊断来源单独绑定当前 Git/工作树/声明 SHA、完整执行源码及实际 ELF。原完整资格入口仍调用原 `load_plan/source_check`；共享 native 审计只提取公共主体，原数学谓词不变。本次诊断计划具有不同 schema，始终 `qualification=false`、`training_eligible=false`，不能传给 PPO 解锁。

独立消费者包括：每回合 FIFO/peer/control 和 Information；Cadence 中完整 Runtime；原 native 接触、时钟、命令、scalar、evaluator、观测档案、参与完整性和执行输入检查；实际运行期间的 ELF/PID/maps 观察及关闭复核；真实外层 wait 后的保存进程身份消失检查。基础审计直接复用已完成 FIFO 结果并重新核绑定，避免再次重放；不另跑一份重复 Runtime。诊断不要求工程脚本特有的转向/反转覆盖，不能因此取得原完整资格。

所有实际原生尝试都进发现清单，失败后的部分数据仍需保留。消费者输出存放于 run 目录外；基础审计对整个封闭原件目录做前后字节核对。只有两回合完成、全部已声明检查通过且未超预算时，才能说这次短工程诊断完成；这不证明连续动力学安全、95% RL 成功或长期稳定。

容量分别报告真实原生返回决策数、API/有效时长、含启动/关闭的采集墙时，以及含审计和外部尾的完整活动成本。失败前缀不当作可训练样本；没有优化时报告0更新，不能把合法随机采样速率直接预测为 PPO 长训练吞吐。三台运动与目标接受的实际覆盖单独描述；没有运动证据时不称“移动可行性已通过”。

## 执行入口

封存计划位于 `assets/20261020_mr3_p2a_v21/predeclared_plan_v1.json`。完成 CPU 检查和 clean commit/push 后，按[当前启动命令](../../../../../../../ros2_ws/ros2-multi-robot-automap/launch_commands.md)的 V21 段执行；命令、freeze、源快照、真实返回与费用由独立 actual-wait 回执及共享 log 保存。任何前检失败都不得启动 native。

本节为冻结前预声明，没有预报原生或审计结果。CPU、实际冻结及最终运行结果随后按真实回执另列；V19 原FAIL、V20开发重放与原末账保持。

组合 CPU 实际通过100项，真实 outer rc0/9.975746618秒，源前后稳定；unittest 内部4.766秒。[actual wait](assets/20261020_mr3_p2a_v21/checks/combined_cpu_v1/actual_wait.json)与[完整console](assets/20261020_mr3_p2a_v21/checks/combined_cpu_v1/console.log)保存实际命令及7份源/测试SHA。覆盖合法随机动作与失败停止、来源/原件稳定、原资格入口保持拒绝、真实wait绑定、负费用拒绝、Z与不可读进程身份，以及旧benchmark/受控执行/训练准入回归。独立审查中发现并修复的absent身份返回None、外层wait绑定及精确费用/额外参数拒绝问题均在这次组合检查之前完成；这些CPU结果不提供原生或训练信用。

[封存计划](assets/20261020_mr3_p2a_v21/predeclared_plan_v1.json) SHA `f2ddefb691944c17a8dfa5ea4d8d1f180fed6868378b41e06aca46ffd2a0eaf8`，绑定445份当前执行/审计/历史必要源与10个实际ELF。计划生成只读核原生ELF，不重构建或改变plant；本轮费用入场仍为V20末账。

## 实际执行与完整闭合

clean/pushed 冻结为 `c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90`。CPU 前检真实 rc0/26.057773539秒，绑定计划、445份源与10个实际ELF；native及各消费者执行期间源前后稳定。完整命令、工作目录、真实PID/start、返回码、单调钟区间及SHA见[外层执行回执](assets/20261020_mr3_p2a_v21/closed_execution/mr3_p2a_v21_diagnostic_outer/actual_wait.json)、[执行汇总](assets/20261020_mr3_p2a_v21/closed_execution/mr3_p2a_v21_diagnostic/summary.json)和共享 [log](../log.md)。

| 实际子进程 | 真实 wait 墙秒 | 结果 |
| --- | ---: | --- |
| native benchmark | 2073.892364923 | rc0，两个完整reset各32步，共64次动作提交/返回 |
| 实时来源 watcher | 2078.301772991 | rc0，与native重叠 |
| FIFO 1 / 2 | 496.724158484 / 502.708009477 | 各rc0/PASS |
| Information 1 / 2 | 479.393231365 / 449.354255872 | 各rc0/PASS |
| native/scalar/观测/输入基础核查 | 325.663984039 | rc0/PASS，封闭原件前后不变 |
| 原生来源关闭复核 | 52.663460966 | rc0/PASS |
| Cadence（含完整Runtime） | 727.869397496 | **rc1/FAIL，未超时、未发中断信号** |

全部已提交子进程已真实wait，检查无跳过。Cadence第二回合及内嵌Runtime通过；第一回合抛出 `ValueError('worker substituted an unreceived storage ACK')`，因此完整诊断明确FAIL。进程正常关闭与部分科学检查通过不覆盖这一失败，不补完整矩阵资格，也不产生可训练样本。全轮0 policy/GPU/optimizer调用，pilot和final-only不动。

[外部收口](assets/20261020_mr3_p2a_v21/closed_execution/mr3_p2a_v21_diagnostic_absence.json)在主outer真实退出之后运行，原109保存身份全部gone，absence通过而diagnostic_passed=false。其自身outer rc0/0.283544031秒；[更晚独立身份复核](assets/20261020_mr3_p2a_v21/later_identity_absence_v1.json)加入已经退出的final helper与child后，共111唯一PID/start全部absent，无不可读身份或同start的Z。该范围不声称覆盖从未保存的任意系统进程。

## ACK失败的最小因果定位

[只读取证](assets/20261020_mr3_p2a_v21/ack_order_forensics_v1.json)保存7条精确原行、1-based行号、行SHA、JSON及整文件inventory引用；没有重跑native或完整reader。唯一违例为第一回合 `tb3`，epoch `uniform_two_episodes_w0_e1_3c77c432`，clock `68980000000`，cmd_seq3059，decision_sequence3231，物理请求q1547。

| 原件与行号 | 事件 | wall_monotonic_ns |
| --- | --- | ---: |
| drive_phase_worker.jsonl:14009 | worker实际收到ACK | 4229387098966908 |
| drive_phase_worker.jsonl:14010 | worker实际消费ACK | 4229387124514451 |
| drive_phase_worker.jsonl:14011 | worker允许物理推进 | 4229387130022304 |
| motion_safety.jsonl:215001 | guard实际收到相同ACK | 4229387131098333 |

原生drive_tb3.jsonl:8044–8045确有同epoch/clock/seq及v=0,w=.3目标的接收/发布。ACK确实存在且worker已消费；guard独立订阅回调却晚于推进许可 **1,076,029 ns**。现行 `audit_reach_runtime.py:1030–1033` 明确要求guard对应ingress也早于许可，故原FAIL保留，不能把它直接称为reader误判。`wait_drive_phase`只等待worker自身订阅，与guard的独立订阅没有跨订阅先后保证。正确修复方向是让真实guard的当前三机storage receipt成为现有motion-phase ACK的完成屏障，保持现门，而不是删掉时间比较或加任意sleep。修复后的CPU与资格边界另列于下节。

## 保持原门的真实guard屏障修复（CPU准备）

在上述native及全部reader、outer退出并确认保存身份gone之后，继续既有授权内常规修复。生产仅 `mr3_motion_control.py` 新增17行：v2 `MotionControlPhase.poll_once` 已有完成status且decision序列当前之后，释放现有motion ACK之前，从guard三个reach tracker的真实storage.latest构造现有 `DrivePhaseClient` 并复用 `matching(status)`；核本epoch/robot、source_clock=storage_clock=status.clock、decision序列、有效cmd_seq及实际线/角目标。未收齐则保持pending，错配沿原异常失败路径关闭，不由worker回执或发布记录代替guard收到。

实际回调顺序为 `reach_driver_ingress`原行记录→epoch/graph验证→tracker.receive_storage→control_phase.poll，所以第三份匹配回调才释放现有motion-phase ACK，worker在这之后取得该ACK再执行自己的存储屏障和推进；原reader墙时谓词保留。没有新RPC/schema、sleep、目标重发或tracker历史消费。takeover/STOP先沿原路径立即发零，只有完成ACK等待三机真实存储；legacy不加此门，原超时失败/停车保持。

系统ROS Python最短相关组合真实 [v2 wait](assets/20261020_mr3_p2a_v21/checks/guard_storage_barrier_cpu_v2/actual_wait.json) rc0/**132 PASS**，pytest内部7.64秒、真实outer9.439727408秒，源码前后稳定；[完整console](assets/20261020_mr3_p2a_v21/checks/guard_storage_barrier_cpu_v2/console.log)保留。覆盖worker先收而guard后收、缺任一机、错epoch/robot/clock/sourceclock/decision/目标/类型/坏cmd_seq、重复旧ACK、STOP/takeover、legacy和原wall timeout零停车，未自行推进物理时钟。

首轮 [v1 wait](assets/20261020_mr3_p2a_v21/checks/guard_storage_barrier_cpu_v1/actual_wait.json) rc1/11.345561775秒，115通过/17个新fixture失败；原因是新fake clock缺 `.now()`，只修fixture后在不同v2目录复测，原console/回执未覆盖。最初CPU入场检查还曾误匹配自身shell文本而拒绝提交测试，未启动pytest，原失败说明及修正后的精确argv检查一并保留。这些是CPU准备问题，不补造native尝试或工程费用。

修复属于**本轮原生闭合之后的新运行时源码**，不是c38e3e8原生执行的代码；旧FAIL不改判，CPU PASS不证明DDS/物理链修复已原生通过。本次不启动第三回合或新矩阵/PPO，后续native须新冻结及具体范围/预算，现行完整资格门仍有效。

## 三机参与、任务与容量

[描述性核对](assets/20261020_mr3_p2a_v21/diagnostic_findings_v1.json)逐回合绑定小原件SHA。两回合分别有reset+32次API step，总66条API记录（其中64 step）；每回合奖励时间32.0秒、step物理时间32.0秒，关闭尾后evaluator为32.2秒。两者都按 `external_sampler_limit` 截断，并非完整300秒任务。

| 项目 | 回合1 | 回合2 |
| --- | ---: | ---: |
| correct-free coverage | 74.121245% | 73.046197% |
| tb1/tb2/tb3路径（m） | .015443 / 2.098155 / .007109 | .015166 / 1.523410 / .091113 |
| 只有一个合法联合动作的step | 22/32 | 13/32 |
| 实际888 KEEP动作 | 22/32 | 15/32 |
| 地图质量 / 三机参与 / 95%成功 | 均false | 均false |

18路接触监测全程fresh/active、event0、ever_unhealthy=false；最终导航协议closed=true、pending0、navigation_failure=false。共35个目标全部cancel，0 succeeded、0 aborted；目标接受不能代替三机运动。所有Nav2生命周期finalized，launch/worker正常关闭，无forced cleanup或残余owned/zombie。这里尤其不能用最后step中尚未关闭的reward快照，误报最终导航未闭合；也不能用最终关闭通过掩盖tb1/tb3参与不足。

含启动关闭的native实际速率为 `64/2073.892364923 = 0.03085984648117` 返回step/墙秒（约111.10/小时）；含审计与外部尾的本轮产出率为 `64/3263.823140435 = 0.01960890564416`（约70.59/小时）。分母、启动成本和原件均保留，不线性外推多worker或长PPO。35/64步没有多个合法选择，37/64实际KEEP，且完整诊断FAIL、training_eligible=false，所以这不是合格训练吞吐，也没有证明三机持续运动或任何学习收益。

## 精确工程末账与下一步边界

[末账](assets/20261020_mr3_p2a_v21/engineering_accounting_v1.json)按真实单调钟区间union：主outer `3263.539596404` + 不重叠的final outer `.283544031` = **3263.823140435秒**。九份native/watcher/reader command wait均完全位于主outer内，不重复加收。CPU前检、单元检查、有限取证和封存不冒充原生或审计运行信用。

累计 `38216.5104974146018 + 3263.823140435 = 41480.3336378496018 / 52000`，余 **10519.6663621503982**。pilot仍1870决策/2905.9547395464029秒，open401/402/403三场final-only未动。原60000上限提案仍未批准；按本轮末账即使采用也只余18519.6663621503982，低于完整20100预约，缺1580.3336378496018。旧提案的数值准入结论已失效，不自动增加总额或另借pilot。

本轮一次诊断按预声明终止，无第三回合、失败重采或完整矩阵。现有授权内继续做具体ACK屏障修复和CPU验证；不因修复完成擅自认定原生资格。下一路线的可审阅范围见[后续路线候选](20261020_mr3_p2a_next_route_proposal.md)，二维仍须单独接受，PPO完整准入与95%出口不改。

## 原件封存与恢复

全部1033份原生文件、2,041,262,832字节原件保留在原目录，并封存为三份按顺序拼接的 `assets/20261020_mr3_p2a_v21/native.tar.xz.part0001` 至 `part0003`。完整archive及各part SHA、tar/xz真实返回、1033成员逐字节解压核对和原件前后稳定性见[封存验证](assets/20261020_mr3_p2a_v21/archive_verification_v1.json)及[原件清单](assets/20261020_mr3_p2a_v21/native_inventory_v1.json)。所有消费者输出、真实wait/console、前检、absence按原字节复制到closed_execution，见[复制索引](assets/20261020_mr3_p2a_v21/auxiliary_copy_index_v1.json)。

恢复时在新空目录中按part0001→0003拼接后经xz解压、tar提取；归档相对根是 `uniform_two_episodes` 的内容，禁止覆盖原件目录。恢复后按inventory逐项核SHA。`seal_results_v1.py`和`summarize_closed_v1.py`保存本次封存及描述性核算方法，不运行simulator、不提供资格，封存脚本拒绝覆盖已有archive。

最终有限静态封存检查：[actual wait](assets/20261020_mr3_p2a_v21/checks/closure_static_v1/actual_wait.json)真实CPU rc0/1.682505902秒，检查源前后稳定；[结果](assets/20261020_mr3_p2a_v21/closed_integrity_v1.json)核三part/拼接SHA、53份复制与原件、1033清单、精确末账、原FAIL/132 CPU及失败首轮保留、JSON/Python语法、新增文档链接和log仅追加。它不重复解压或正式科学reader，不新增工程费；报告本段只追加该实际检查结果，不将静态PASS作为原生资格。
