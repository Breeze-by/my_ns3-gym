# MR3 P2A V62：单环境八步实际进程性能分解

V62 源码、canonical CPU 与 scope 已准备，尚未启动 World，待新的精确提交冻结及真实 push。先测量现有生产行为的成本，再安装取消授权修复；取消候选只在临时目录并行开发。当前 capacity=False、P2A 未完成，自动 pilot/final 入口保持关闭。

## 固定范围与解释边界

只执行一轮 open101、一个环境、三机器人、一个回合、八次普通合法 probe 决策；不启用 32 步 preparation-motion-probe，不使用模型、GPU 推理、优化器或 heldout seeds。原 Reach 数学、物理步长、电机更新、初始编码器保持器、R=.0078、固定 anchor、5 秒承诺、原任务与停止门均保持。V60 的真实停止超限和两 corridors 的取消覆盖缺口继续为 FAIL。

固定诊断包装器分别捕获 motion_safety、adapter、worker 主线程，以及 adapter encoder 和 worker ROS spin 两个已有线程。它保留目标程序的 SystemExit、异常、返回值和参数；worker/supervisor 的有限源码投影与 encoder 包装须保存实际执行字节，并能全字节逆还原到绑定的生产源。执行体包含这些明确的 profiling hooks，不能冒称完全没有源码投影。

benchmark 由现有 ns3gym Python 执行；三类被测 ROS 程序和审查器使用系统 Python。实际 console entrypoint 必须解析到绑定模块的 main；临时 ROS 参数文件保存实际 argv、完整字节快照及 SHA。未进行 Nav2 参数 readback，不补造该信用。

五份 pstats 都需完整读取、绑定 SHA/stat 后才能描述结果。每份最多 32 MiB、总计 128 MiB；小元数据总计 64 MiB。cProfile 时间包含等待，进程与线程的 cumulative 项会重叠，不相加冒充 parent wall。C++、ODE、DDS 内部及其它线程不由这五份 Python profile 分解；profiling 自身也会增加成本。八步结果不证明长回合或完整 auditor/finalizer 容量。

## 真实等待、费用与关闭

新 bootstrap 在 exec 前保存自身 PID/start 及实际观察到的 nonowned 祖先关系；exec 后 driver 核对同一 PID/start。祖先不成为 cleanup 对象，也不声称它们都已退出。只使用保存的完整身份做退出核对，不把 PID-only 字段拼成原身份。

完整 parent 预约 1800 wall-s，包含来源检查、native 实际等待、有限 profile/元数据审查及来源复核；native 合作式 allocation1500 已包含原 close120。原 reset420/step90 及 owned-close 路径保持。审查最多使用 min(240, remaining−60) 秒，余下时间供升级等待和 post-source 共享；这些是合作式安排，完整 1800 是实际全费判定门，不承诺硬实时上界。所有已提交子进程须真实 wait；partial、实际非零 rc、超额与超时均保留，超时后的 rc0 不能抹去原失败。

唯一入场账为 [V61 规范末账](assets/20261024_mr3_p2a_v61_cancel_forensics/closure_ledger_v1.json)，`U108886.5066566616018 / C150000`，余额 `41113.4933433383982`，可覆盖本轮预约。费用从 bootstrap 保存的真实起点计到 driver 完成 post-source/审查检查；嵌套等待不重复加。无法验证完整起点或旧账时明确保留 unknown，不制造累计。pilot1870 决策/2905.9547395464029 秒、final900 决策/9000 秒及三场 open401/402/403 原额不变。

本轮不调用旧活动的执行函数、预算或科学读者。实际 C++ ELF 与绑定来源可复用已保存字节；没有新编译或原生科学资格信用，也不把历史 build 工具的绑定冒称本次重新执行。

## 准备验证与下一步

临时候选 v1/v2/v3 与修订前 fixture 都保留原件。最终私有候选 v3 实际 13 组人工 CPU 通过（15 次真实 toy 子进程等待、284 来源稳定恢复、18 个保存身份 fresh-gone）；parent/bootstrap 的独立 10 项人工 CPU 实际通过，覆盖非零 rc、超时后 rc0、观察异常仍真实等待、坏准入费用、未知起点及失败 bootstrap，真实 wait 为 2.253924557 秒。这些结果不授予 canonical、新 native 或容量信用。

安装后的完整 canonical CPU 已实际通过：工具1554真实 reap rc0，23 PASS、0 fail/error/skip，6.272723873 秒；295 来源 before/after/current 与快照恢复一致，18 次真实 toy/Conda 子进程等待、21 个保存身份 fresh-gone。见[canonical 证明](assets/20261024_mr3_p2a_v62_process_profile/checks/canonical_cpu_v1/proof_v1.json)。本轮在 A62 新文件未提交时绑定实际字节，不冒称已有新的 Git 执行冻结或 native 信用。

私有准备三版、parent 人工 CPU、静态审查与原回执共 1256 regular/49886580B 已[无损封存](assets/20261024_mr3_p2a_v62_process_profile/checks/preparation_history_v1/manifest_v1.json)为17979754B，原件不删；归档工具60699真实 reap0、15.004053126 秒、两个 CPU 身份另 fresh-gone，工程新增0。

[scope](assets/20261024_mr3_p2a_v62_process_profile/scope_v1.json) 已实际 admitted，1051 来源与12个 resolved ELF 已封；producer 工具29523真实 reap0、2.288306556 秒，87项输入 before/after/current 与恢复快照一致、两个 CPU 身份 fresh-gone，工程新增0。这是来源/资源准备，无 World 或新科学资格。新的精确 Git freeze 与真实 push 完成后，才允许一次正式八步测量。真实结束后保留所有原件、partial、真实 rc、完整费用及保存身份观察，再根据实际热点选择等价优化。取消授权修复和 probe-v2 随后独立接线、验证；实际端到端容量通过后，仍需新同 freeze 完整 12EP/30 角色、真实 minimum/pilot 更新和三场 strict95 final，全部满足前 P2A 保持未完成。
