# P2A 决定性测试结果与路线建议

日期：2026-10-24。目的：通过真实执行回答“原约束下是否存在有意义的运动取消机会”和“完整采样是否能在现有预算内完成”。本文承接[停滞分析](20261024_mr3_p2a_stall_analysis.md)，记录本次新增证据。

**结论：建议调整推进顺序，保留现有安全约束与学习目标。先解决 authority 交接和正常关闭，再重新测完整采样容量。当前没有证据证明项目无解，也没有证据允许宣布 P2A 可完成。**

本轮最有价值的变化是：以前怀疑无法同时满足的“满五秒、仍在运动、有新增路径、原 WAIT 合法”，在真实接收记录中同时出现了；随后阻塞执行的是 `invalid_authority`。这个故障又在独立的原有 benchmark 输入下出现。继续盲目更换目标或直接跑完整资格矩阵，优先级已低于修复这条具体协议链。

## 1. 两个问题分别得到了什么答案

| 决定性问题 | 本次结果 | 判断边界 |
| --- | --- | --- |
| 原规则下能否出现合格的运动取消请求？ | **可以出现这些联合接收条件。** tb3 在 accept 满 5.0 秒时，v=0.16845 m/s、新增路径=0.73372 m，active/owned、原 joint/WAIT mask 均 True，并有实际 command 13 / action 539。 | 这是请求条件的存在性证据，**不是**三机各两次取消完成、停车界通过或完整物理资格。 |
| 能否用现有预算稳定完成一批可审计采样？ | **本轮未通过。** 计划双 worker 各 64 步，实际仅返回 29+35=64/128 个样本，两个 episode 均强制清理，独立审计失败。完整父耗时 2074.049093921 秒。 | 34.57 分钟小于 pilot 剩余 48.43 分钟，但这是失败前缀的成本，不能当作完整 128 个合格样本的成功成本。预算是否足以完成成功批次仍未证实。 |

因此，不能再把“所有运动条件根本无法同时成立”当作当前主结论；也不能把某个时间比较字段为 True 当作 capacity PASS。当前版本首先缺少可靠、可审计的采样闭环。

## 2. 行为试验：先自然暖身，再异步运动取消

冻结：`bacd0b59e4aba180dcfb5ff292b572b0e4ba9398`。open101、单 worker、三机、最多 96 步。每机只有一次预先声明的自然完成暖身，随后最多两次正式取消机会；不把提前 SUCCEEDED 的正式机会改称暖身，不重试失败目标。所有动作均通过原 per-robot AND joint mask；保持五秒承诺、v≥0.08、新增 path≥0.05、三次新鲜静止观测和三秒交接要求。

三机暖身均出现自然 SUCCEEDED。tb3 在任务第 7 秒接受后续目标；任务第 12 秒的原始观测给出：

| 字段 | 实际值 |
| --- | --- |
| goal | `feasibility_w0_e1_7ae55b35:tb3:8` |
| accept 后时间 | 5.0 s |
| 接收速度 | 0.16845243687127864 m/s |
| 最早合格完整路径基线 | 0.4886255542033037 m（snapshot sequence 9） |
| 当前累计路径 / 相对基线增量 | 1.222340629195843 / 0.7337150749925392 m |
| active / owned / joint mask / WAIT mask | 全部 True |
| 原始实际命令 | command 13，action 539，即 tb1 GOAL5、tb2 GOAL3、tb3 WAIT |
| 命令 epoch、观测序号、digest 绑定 | 全部相等 |

以上由原始 transitions 独立重算，没有调用刺激程序的判定函数作为答案。[接收谓词计算](assets/20261024_mr3_p2a_decisive_tests/results/qualified_wait_predicates.json)

但该命令后的任务以 `navigation_failure` 提前结束。任务结果记录 `motion_safety / tb1 / invalid_authority`，时刻 50.52 s，恰逢 tb1 暖身后新目标的授权交接。原 worker 保存第 13 条 step，物理只推进 0.02 s；外层刺激程序只收到 12 次返回，之后 step IPC wall guard 过期。worker 最终 rc=-9、`forced_shutdown=true`、`failed_sample=true`。完整父实费 **671.931212850 s（11.20 min）**。[原生 summary](assets/20261024_mr3_p2a_decisive_tests/results/feasibility_native.json)、[故障字段](assets/20261024_mr3_p2a_decisive_tests/results/task_result_reason.json)、[真实等待](assets/20261024_mr3_p2a_decisive_tests/results/first_actual_wait.json)

另有我新增测试入口的接线遗漏：live custody 原白名单只支持 benchmark/PPO/action_trace，未支持 decisive_probe。该臂 capture FAIL，原定审计 SKIPPED，**不能获得完整原生或取消资格信用**。原失败没有补判，也没有重跑。后续已增加启动前同一白名单检查；新增刺激入口在完成正式 custody 接线前会被拒绝。

## 3. 成本试验：使用原有 benchmark 独立执行

第一臂结束后，先逐一检查其保存的 48 个 PID/start 身份不存在，再执行尚未启动的容量臂。冻结：`0649f057c38410a14761c5c98a13bd3f496bc1d2`。控制、物理、authority 实现及实际 ELF 与第一臂相同；新增的是有界接续父脚本和证据声明。

使用原有 benchmark、双 worker、各一个 open101、各最多 64 步，uniform legal 输入 seed41，保持现行 exact-point/point-attachment/cone-support、owned authority 与 initial encoder profile。没有模型调用、优化器更新或学习。

| 项目 | 实际结果 |
| --- | --- |
| cold reset | worker0 137.756 s；worker1 135.478 s，并发，不相加收费 |
| 成功返回的 step | worker0 29；worker1 35；共 64/128 |
| 原始 worker step 行 | worker0 30，其中末行仅推进 0.02 s；worker1 35 |
| 首个故障 | worker0 的 tb2 在 66.12 s / task 29 s 报 `motion_safety: invalid_authority`，继而 navigation_failure、step IPC 超时 |
| 另一 worker | 完成在途 RPC 后按原 benchmark 规则退出，不补造样本 |
| 关闭 | 两 worker 均 rc=-9、forced_shutdown/failed_sample=True；没有正常完成 summary |
| native 命令实际等待 | 1297.614420271 s |
| live custody capture | PASS；不等于原生任务、退出资格或物理 PASS |
| FIFO / information | 各两项 FAIL：缺少 episode `summary.json` |
| cadence/runtime | FAIL，697.483329343 s：worker0 保留 `reach_model_failure`，worker1 为 `unclosed deferred terminal tail` |
| closure review | FAIL：native launcher 未真实返回 0 |
| full diagnostic | 因缺少 PASS 的 FIFO 结果而 SKIPPED |
| 连续完整外父实费 | **2074.049093921 s（34.57 min）** |

[benchmark 原件](assets/20261024_mr3_p2a_decisive_tests/results/capacity_native.json)、[父结果及各角色回执](assets/20261024_mr3_p2a_decisive_tests/results/capacity_parent.json)、[真实完整等待](assets/20261024_mr3_p2a_decisive_tests/results/capacity_actual_wait.json)、[cadence/runtime](assets/20261024_mr3_p2a_decisive_tests/results/capacity_cadence.json)

原 summary 的 `valid_transitions=64` 表示实际返回计数，不表示 64 个已获科学资格的训练样本。`fits_existing_pilot_wall_budget=true` 只比较失败前缀的墙时；同一父结果的 `diagnostic_passed=false`，`capacity_qualified=false` 保持。没有完整成功批次，不能线性外推成功训练或三场 300 步验证费用，也不能据此保证增加预算就能学会。

## 4. 故障已缩小到哪一层

**已确认：** 两种输入方式、两个不同机器人，都在真实运行中出现 authority 故障；第二项使用原有 benchmark，故障不依赖新增 decisive_probe 入口。两臂也都暴露了失败后的响应/关闭链问题。这是具体软件协议与执行可靠性问题的证据，不是安全公式不存在可行解的证明。

**有证据的候选解释：** adapter 在 `poll_authority_handoff` 中依据缓存 `authority_ready` 非空发送 grant；接收端还检查当前停止证据及其 100 ms 时效。第一次 tb1 失败 grant 前，最后匹配 ready ACK 年龄约 2.20 s；第二次 tb2 为 0.96 s。[第一次发送端字段](assets/20261024_mr3_p2a_decisive_tests/results/authority_cached_ready_description.json)、[接收回调原行](assets/20261024_mr3_p2a_decisive_tests/results/authority_callbacks_description_v2.json)、[第二次字段](assets/20261024_mr3_p2a_decisive_tests/results/capacity_authority_description.json)

**仍不能下的结论：** ACK 年龄本身不是唯一根因证明。第一次 tb3 后续 grant 的缓存 ACK 年龄约 2.42 s，却被接受；接收端内部证据可能在继续刷新。`invalid_authority` 又合并了多种校验异常，因此精确失败谓词、当时接收端 ready/witness 状态及完整因果链仍待专门核实。不要把缓存 ACK 重新打时间戳、放宽 100 ms 条件或伪造 ready 当作修复。

本轮描述没有将 APPLIED/body target 当作双轮实际零值、wheel readback 或连续 plant 证明；也没有重判 V60/V71 等旧 FAIL。

## 5. 建议调整的推进顺序

1. **优先定位并修复 authority 交接。** 保留具体失败谓词、旧/新 owner、当前 stop witness 与时间关系；验证自然完成、主动取消、证据失效、延迟 ACK、新 goal 等交接。发送端不能把历史 ready 当作永久授权依据，接收端仍执行原真实停止门。
2. **修复失败后的正常关闭。** 针对 navigation_failure → terminal drain → RPC 返回 → worker shutdown 的链条做有限回归，消除这次 IPC 超时和强制 -9；不能仅靠增大超时掩盖故障。
3. **继续有限的行为测试，再进入完整资格。** 本轮暖身后确实出现较长合法目标与运动 WAIT 条件，值得保留为候选工作负载。先让一次实际运动取消及后续重新授予正常闭合，再验证三机各两次及原停车界。所有原安全门、五秒承诺和独立审计保持。
4. **用完整成功批次重新判断容量，再决定训练安排。** 要包含 reset、采样、正常关闭、完整独立审计和模型计算；若实测无法在明确预算内完成，再优化采样/日志/审计实现或重新制定预算。完整同冻结资格、minimum、pilot 和三场 strict95 仍是独立出口。

这次不支持直接换掉安全数学、降低 95% 标准、把失败样本算作资格、或因短任务能运行就切入 PPO。也不支持因为上述工程故障就宣布项目不可解决。**建议保留研究目标，把下一轮投入收敛到可复现的 authority 与关闭故障上。**

## 6. 费用、原件与工具限制

两项新增工程父费用只各计一次：671.931212850 + 2074.049093921 = **2745.980306771 s**。承接 U112685.3057936486018，现为 **U115431.2861004196018 / C180000**，余 **64568.7138995803982 s**。native、watcher、审计与外父重叠时间不叠加；并行的有限描述工作包含在接续父期间。pilot 1870 决策 / 2905.9547395464029 s、final 900 决策 / 9000 s 均未动用。原 26000 秒诊断预约内仅接续容量臂，未扩额。[费用账](assets/20261024_mr3_p2a_decisive_tests/closure_ledger.json)

关闭时核对 1120 个来源与执行 Git 字节，10 个选定 ELF 保持；150 个已保存运行/审计身份 fresh absent，非所有外部进程不存在的声明。1448 个闭合普通原件共 2,972,755,967 B，加源码恢复快照，无损保存约 272.60 MB；所有恢复字节逐一核验，大件按 32 MiB 分块，原始文件未删除。关闭/归档 CPU 返回 0、200.885952904 s，按既有规则工程新增 0，其两个身份另行检查退出。[来源关闭](assets/20261024_mr3_p2a_decisive_tests/checks/closure/source_closure.json)、[保存身份](assets/20261024_mr3_p2a_decisive_tests/checks/closure/saved_absence.json)、[完整库存及恢复关系](assets/20261024_mr3_p2a_decisive_tests/closed_inventory.json)

软件准备最终 63 passed / 1 deselected；旧 fixture 缺当前 authority 字段的问题已在旧 HEAD 读者复现，排除说明保留，未降低生产门。执行完成并封存后，补了启动前 native 模块白名单检查和 reader 纳秒比较：64 passed / 1 deselected。后者处理真实日志中 `27.999999999999993` 这类表示误差，仍拒绝真正的节拍偏差。后继 CPU 结果不补发旧 native 信用，也没有再次启动 World。[准备 CPU](assets/20261024_mr3_p2a_decisive_tests/cpu_preparation_v2/actual_wait.json)、[后继 CPU](assets/20261024_mr3_p2a_decisive_tests/cpu_post_v1/actual_wait.json)

第一项 custody 接线遗漏、首次描述器因空格字面过滤得到零行、早期准备/fixture 失败均保留记录。描述器改用真实紧凑 JSON token 后，单次完整流选出 124 条原 authority 回调/拒绝行，未把首轮零匹配说成“没有 authority 事件”。执行原冻结源码已封存；后继测试工具修改不改原结果。P2A、科学资格和 capacity 均未完成，自动 pilot/final 仍禁止。
