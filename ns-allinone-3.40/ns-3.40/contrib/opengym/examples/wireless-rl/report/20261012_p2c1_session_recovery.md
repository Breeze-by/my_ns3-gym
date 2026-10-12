# P2C.1 长会话独立审查与代码恢复（2026-10-12）

## 结论与授权

P2C.1 完整集成没有验收通过。长会话做了真实的组件开发、来源审计和原生实验，并非零工作；但多次形成“开发格通过、正式格失败、增加针对性规则、重跑开发格”的循环，没有完成同一冻结的完整矩阵，也没有建立新增策略的稳定收益证据。继续把所有局部修补累积在主控制器中，不符合项目原本要求的少量明确假设和对照。

用户要求独立监测；若确认无有效推进则暂停原会话、恢复代码并减少逻辑堆积，并明确选择“恢复到这次长会话开始前，保留已有安全预算修复”。据此恢复到会话元数据记录的 b32c891e0b35558f92ca2244da737a1ecce0bbd2，不恢复到尚含完整返航预算缺口的早期 P3C.5 版本。

这次操作是有备份的维护性恢复，不宣称回退后 P2C.1 成功，也不能证明所有被移出的改动无效。

## 审查依据

- 原会话：01a12147-003f-7912-9e95-89dca962a7f9。线程建立于 2026-10-09 23:27:43（北京时间），恢复前主 turn 约 54.3 小时。
- 会话起点由 state_5.sqlite 只读查询和原 rollout session_meta.git.commit_hash 两处一致确定。
- 恢复前 HEAD：fb400160a5f8532b832eae78df062c10566d67ca（v95）。起点之后共 54 次 Git 提交。
- 独立读取原始 summary/result、完整开发门禁、原生 5 秒保持证明与现行验收契约；不以组件 PASS、中央 COMPLETE 或进程 exit 0 替代完整任务。
- 长会话期间检索到 169 条已结束 summary，来自 54 个不同源码冻结，混合开发、正式与受控探针。它们不能跨版本合并为成功率或统计样本。

## 已确认的进展与反复

| 原版本/批次 | 原任务与严格门禁事实 | 可支持的结论 |
|---|---|---|
| v90 开发 | 四开发 COMPLETE、完整开发门禁 PASS | 当次开发范围通过 |
| v90 正式 | lab101 COMPLETE 263.6s；lab202 FOUND timeout 300.1s | 正式整批未通过 |
| v91 开发 | lab RALLY、corr FOUND 均 300s 超时 | 前述开发通过未形成稳定保持 |
| v92 开发 | 四开发 COMPLETE、完整开发门禁 PASS | 当次开发范围通过 |
| v92 正式 | 同冻结首 lab101 RALLY timeout 300.4s | 正式整批未通过 |
| v93/v94 开发 | lab 分别 EXPLORE/RALLY 超时 | 继续发生集成回退 |
| v95 开发 | forced/lab/rooms/corr COMPLETE 206.0/261.0/250.2/263.1s；完整四格门禁 PASS | 最新候选有局部推进 |
| v95 首正式 | 原生 lab101 COMPLETE 289.8s，有全体原生连续 5 秒保持证明 | 单格结果须保留；其余正式、物理和留出未完成 |

v95 首正式格在审查期间自然闭合，参数、源码和观测没有改动。独立严格审计结果在下方验证记录中。停止后不再启动下一格，未调用格不能标为 FAIL 或 PASS。

现行退出条件仍是同一源码的四开发、17 正式与两受控物理格严格通过，15 非留出和新物理对子通过后才首次运行 917 留出；300 仿真秒、原生保持 5 秒和源 TTL 不放宽。P4/ns-3/Wi-Fi/RL 未开始。

## 代码堆积的具体位置

| 指标 | 会话起点 | 恢复前 v95 | 变化 |
|---|---:|---:|---:|
| control.py 行数 | 7,269 | 9,492 | +2,223（30.6%） |
| control.py 字节 | 356,037 | 500,033 | +143,996 |
| AST FunctionDef 数量（含嵌套） | 188 | 222 | +34 |
| assign_idle_robots 行数 | 543 | 821 | +278 |
| update_mission 行数 | 927 | 957 | +30 |

主要新增包括首次近家补能、前缀继续、奇偶相机优先、未完成视点延续、返航让行/预充、准备批次优先、几何跨回调暂存、集合探查恢复和活动绕路取消。多个规则共同改变同一探索/集合流程；局部夹具与条件快照能验证分支和预算，无法分离完整异步任务中的收益。

全部 542 个变更文件/182 万新增行大部分来自证据报告和展开 JSON，不能把这个数字当运行时代码量。恢复只移出 178 个有变更的代码、测试、清单和活跃规划文件；364 个日期报告/实验记录原样保留并校验哈希。旧测试恢复到与旧实现匹配的版本，新测试和夹具保留在备份分支。

起点控制器本身仍有 7,269 行，是已有技术债；此次不进行新的重构，也不把旧失败改写为通过。

## 暂停、保存与恢复方式

1. 向明确识别的原会话发送用户暂停指令；确认任务状态 idle、主 turn interrupted。原会话无 thread_goals 条目，不伪造 goal 状态。
2. 仅暂停 v95 formal 批处理父进程，当前实验子进程继续原样运行；原格结束且 owner/observer/Gazebo 全部退出后终止批处理，避免启动下一格。
3. 创建并推送 backup/p2c1-before-recovery-20261012，指向 fb400160a5f8532b832eae78df062c10566d67ca。Git 历史不重写，恢复作为新的 main 提交。
4. 外部恢复目录保存配置、skill 安装备份、工作树/索引补丁、恢复路径和证据哈希；ignored 原始 ledger/CDR/日志留在原路径。未跟踪的 260929_report 用户资料保持不动。
5. 代码/测试/声明恢复到 b32c891 字节；活跃文档添加恢复事实，历史报告和 log.md 不回退。
6. 通过 Codex 原生 plugin remove 和 marketplace remove 移除 ponytail 插件及市场源，清掉其 hook 信任记录；移出 karpathy-guidelines 安装目录并删除对应 skill lock 条目。清掉全局和项目中的使用指令，保留独立工程判断与必要验证要求。技能备份不在自动发现目录中。

## 验证记录

- 恢复后的 `src/`、`scripts/`、测试、夹具和 manifest 与 b32c891 完全逐字一致；移出 142 个长会话新增文件，恢复其余 36 个变化文件。364 份历史证据逐项 SHA-256 不变。
- 功能回归：1527 PASS；完整 pytest 命令另外有原有 test_flake8/test_pep257 两个 lint FAIL、1 SKIP，耗时201.22s，整体 exit 1。原有 lint 入口从工作区根运行时还扫描了保留日志/build；另在包目录用相同入口重查，两项仍 FAIL（11.50s，8107 flake8 风格诊断，无 undefined-name/syntax 诊断），该范围的源码与 b32c891 相同。记录既有风格债，不把全 suite 标为 PASS，不为凑通过改写旧源码。
- 四包 `colcon build --symlink-install` PASS（4.34s）；安装目录中仅移除一个指向本次已回退 scan_self_filter.hpp 的失效旧链接。
- 原 check_p2c_source.py PASS：171 保护文件、4 个已有安全修复源变化、54 静态协议格；原 native 常量与 Future 串行约束保持。
- 已安装 launch 的 `--show-args` PASS，仅解析参数，没有启动新 Gazebo/ROS 任务。
- v95 原首正式格使用恢复前 fb40016 完整原读者独立审计 PASS，cases=1/full_declared_scope=false；保留4开发完整审计 PASS，明确不替代17正式+两物理的完整门禁。
- 原会话保持 idle/turn interrupted，原 batch/owner/observer/Gazebo 进程均关闭，未启动下一原格或917留出；卸载、配置/指令清理校验通过。
- 两次初始验证错误如实保留：第一条门禁命令未 source ROS/install 导致 import 失败，随后正确环境的原审计通过；恢复命令曾返回仍运行 session 时提前启动测试/构建，run1 收集失败/构建中断均排除，闭合恢复后 run2 作为验证依据。没有为恢复新增一轮任务实验。
- 原始命令、成功/失败输出、逐项证据哈希和 v95 终态归档在 `20261012_p2c1_session_recovery_artifacts/`。技能配置只在外部恢复目录保留，不将可能含私有配置的文件提交到 Git。

实际验证命令（ROS 使用 Humble、仓库 install 和 PYTHONNOUSERSITE=1）：

```bash
/usr/bin/python3 -m pytest -q src/multi_robot_exploration/test scripts/test_*.py
colcon build --symlink-install --packages-select multi_robot multi_robot_exploration merge_map slam_toolbox --allow-overriding slam_toolbox
/usr/bin/python3 scripts/check_p2c_source.py --output log/p2c1_recovery_source1.json
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py --show-args
/usr/bin/python3 scripts/check_p2c_gate.py --run-root log/p2c/20261012_p2c_v95_formal --cases fixed_lab_101 --output log/p2c_v95_formal_fixed_lab_101_recovery_gate1.json
```

pytest 和读者的 PYTHONPATH 包含仓库 scripts；审计最后一条在任何源码恢复前运行。所有输出使用新的路径，不覆盖历史审计。

## 当前研究边界与后续方式

起点已包含完整已知接触区返航路径、源龄预算、原生距离/时间能量账本、失路停止/有界失败和 Future 串行处理；这些基础修复保留。原受控返航对子 PASS 与主 v41 PARTIAL_COMPLETE/失路 FAIL 的历史边界不变。P2C.1B 仍未完成，新恢复提交也没有完整任务信用。

后续如另行恢复研发，应先固定一个可区分的失路或规划迟滞反例，用同冻结的小型对照验证一项机制，再决定是否取回备份中的某项修复。组件优化、条件路线和 CPU 减少不能直接推导任务成功收益。不得继续逐失败无边界叠加效用权重或特殊场景规则。

卸载采用本机 Codex 原生插件命令；插件安装/市场/配置边界参照 [OpenAI 官方插件文档](https://developers.openai.com/plugins/build/plugins)。
