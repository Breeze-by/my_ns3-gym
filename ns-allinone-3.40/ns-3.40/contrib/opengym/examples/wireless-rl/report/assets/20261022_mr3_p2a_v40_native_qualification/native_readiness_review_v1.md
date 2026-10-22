# V40 原生资格准备独立只读审查

2026-10-22。仅阅读当前源码、既有构建证明/配置 JSON、安装路径、ELF 字节及 `readelf -d`。没有导入项目模块，没有执行测试、构建、动态库加载、World/Node、模型、原件输入重放或 Git 修改。本文不是 preflight、live custody、原生资格或 P2A 完成证明。

结论：当前静态安装与原生构建没有发现必须重新编译的项。应新建 V40 binding/plan、完成新冻结实际 CPU preflight，然后直接进入完整原生资格，不增加二维随机全 PASS 前置。任何必要门失败均保留结果并停止后继阶段，不减角色、刷新 TTL 或借用旧资格。

## 资源和阶段门

本轮授权以同目录 [authorization_v1.json](authorization_v1.json) 为依据：工程累计上限 75000，入场已用 48259.9538193466018，余 26740.0461806533982。预约完整矩阵 18000、外部资格/最终关闭/末账 300、fresh minimum 1800，共 20100；预约后工程机动余额 6640.0461806533982。这不重置 pilot 1870 决策/2905.9547395464029 秒，或 final-only 的 open:401/402/403 三场额度。

`mr3_learning/reach_preparation.py:51` 的严格计划门仍要求 normal spawn、无 plant/physics diagnostic、0 GPU/optimizer、四阶段完整顺序及以下固定工作量。阶段节余只按既有 forward allocation 算法向后传递。

| 阶段 | 并发环境/固定 schedule | 声明 steps/实际回合数 | 基础阶段墙秒 | native cap/close reserve | 必需角色数 |
| --- | --- | --- | --- | --- | --- |
| interface | 1 / open:101 | 32 / 1 | 2400 | 1900 / 120 | 9 |
| terminal | 1 / open:101,open:101 | 4 / 2 | 1200 | 850 / 120 | 6 |
| reset | 2 / open:101,open:101,rooms:101,corridors:101 | 32 / 8 | 6500 | 5500 / 120 | 9 |
| deadline | 1 / open:101 | 300 / 1 | 7900 | 6900 / 120 | 6 |

总计 12 个独立 epoch、30 个角色；环境内部始终为 tb1/tb2/tb3。六基础角色为 full/runtime/information/peer_control/cadence/closure，interface/reset 另有 input/angular/physics。per-episode FIFO 叶和 aggregate/manifest 的完整 DAG 不能因“组合角色”省掉。所有正式消费者、watcher、native 子进程均须真实 wait；正式离线审计及关闭尾费属于本次工程实费，不能记作开发 CPU 免费。

`reach_policy_chain.py:88` 还要求计划预封三项 `policy_stages`，不能只调用 `reach_preparation.build_plan` 就认为学习链已准备好：

| 阶段 | 独立准入与固定上限 |
| --- | --- |
| minimum | 新冻结完整资格 + 实际余工程余额准入；seed41、16 eligible decisions、正 optimizer 更新；stage1800/native1150/tail500 |
| pilot | minimum 完整独立 PASS + 实际外尾/前驱 absence；最多1870决策、episode_steps64；stage2905.9547395464029/native2100/tail500；从头训练，不能 resume 旧 checkpoint |
| validation | pilot 完整 PASS、真实 final.zip SHA 与前驱外尾；仅该 final；open401/402/403、每场300、总上限900；stage9000/native8500/tail500、0更新、三场严格任务成功 |

`ppo.py:405` 在创建模型前重新验证同冻结资格、seed/start 两模式；`closed_episode_training_eligibility` 保留模型违例拒收。未实施新的“负终态训练审计”提案，不能由该段 collector 的普通任务负样本许可推导出完整独立审计会接受任意失败。`reach_policy_chain` 没有另设 GPU 余显存/可用性门；V40 CPU preflight 应记录 conda 的 torch/CUDA/version/device availability，固定 `cuda:0`，不做 forward/backward 或 optimizer 探针。资格矩阵 GPU 调用仍为 0。

## 当前磁盘证据

逐文件读取 V19 custody 声明的十项 ELF，均存在、ELF magic 正确、bytes/SHA 与旧构建声明相同；以下是本次静态观测，不是 gzserver/live 进程的加载证明。SHA 为完整 SHA256。

| role | 当前 SHA256 |
| --- | --- |
| gzserver_executable | 689e61236ef90aeb17099bd9cab70280bc457d18fd3bf37a32b9bae77b1bf9d8 |
| driver | 1cbd0cde998553f840bec7e6f8581d75ea512dfcf5884277b28ea44fea3aa61d |
| observer | 008d68be02b367760049671680e9a63a69d8952705d4b6c1593b56e95c2a6d84 |
| ray_box | 782d388fea8df3646524e54f41d71de5f53480b9d04cc0ea1c453c70e2c1f7d8 |
| ode | a94a424df0b3af9d8a04c58ef1562734cc81728253bcedd25c7705330289c258 |
| smoother_core | fc2a590d2c75b92f7fe12f2adf380dcd8210444f8b601f8b16313c47aae2226f |
| smoother_executable | 2da81a591908de6ad74618c47119c280134246b584e4509751179f15fcfd0dae |
| odometry_recorder_executable | 2b22e115aaf48c1898f51b0bb281d098d74406989f186e885daa554b18c53e0c |
| controller_executable | d8f732a95f19684c9aeb0658a3bb982292729490eced2f17d0fa0e8a619cc55c |
| rotation_shim | ec301e3ef10e7e71dfdfc77d0164dfecfba2408ea0523bb05ebf1983da13fc15 |

driver/observer/ray/recorder 的 6/1/3/2 个 compiled-source SHA 对应当前源码，且全部确实包含于实际 ELF。当前 `multi_robot/CMakeLists.txt` 同原 V15 actual-build source SHA；driver `flags.make` 与 V15 归档逐字相同，六个 SHA 宏及 `-fno-fast-math -ffp-contract=off` 保留。因此可使用 V16 `native_build_evidence_bridge_v3.json` 重新核证原 V15 构建，而不能冒称执行了新构建。

相关磁盘补充：`mr3_gazebo_step` 存在，448392 bytes，SHA `87665ac5b2b4388cc1e8fd38e5dfb3355a38e7bc7a5ef3a014eef495af438dd4`；canonical sync/async slam_toolbox ELF 以及 Karto ELF 均存在，Karto SHA `1848be4216072cad09e74680d9b474ad0908dd9d98ed9c01838d316a76efd80b`。这些补充文件的存在不扩展原十-role custody 的证明范围。二维 `/tmp` Karto thin adapter 不是本次原生必需构建，不应为原生资格重新构建它。

ROS Python 静态路径链为 `install/multi_robot_exploration/lib/python3.10/site-packages/multi-robot-exploration.egg-link` → canonical `build/multi_robot_exploration` → 包目录 symlink → canonical `src/multi_robot_exploration/multi_robot_exploration`。obs/seed_certificate/point_graph/motion_control/adapter/reach_runtime 的 build 路径均解析到当前源字节；console entry shebang 为 `/usr/bin/python3`。当前安装无需仅因新增 pure helper 重装，但仍必须用 source-sealed CPU 命令实际确认 `__file__`/SHA，而非拿静态 symlink 结果代替 import 成功。

driver `readelf -d` 声明 RUNPATH `/opt/ros/humble/lib`；仅检查动态段，没有运行 `ldd`、dlopen 或原生 ELF。实际库选择、参与者 PID/start、参数和停止均由新一轮 live watcher/独立消费者证明。

## 新冻结必须完成的准备

1. 根编写 V40 专用准备器，使用 `reach_preparation.build_plan(..., seed_rule='exact-point-bridge-v2', start_graph_rule='point-attachment-3x3-v1')`；补齐 minimum/pilot/validation 三项 registry。四 native stage、三 policy argv、plan 和 metadata 必须显式同 pair；不能把 default original-start 当 point 模式。
2. 新 custody JSON 使用 `mr3-reach-native-custody-binding-v1`、reach-v1/v2 execution protocol，刷新当前 Python/runtime 源、所有 qualification wrappers 和新 A40 driver/preflight 源 SHA。保留十 binary roles、四组 compiled_sources、原 process/corrector tools 和成功 build receipts。新 binding 自身也写入 plan source_bindings，十 ELF 写入 library_bindings。`source_inventory` 当前完整集合必须被覆盖；不能复用 V19 source SHA。
3. 预算字段写入当前 75000 依据及最新实账，预约完整 20100，保留剩余 pilot/final-only 和 no-retry。`reach_preparation.py:255` 生成说明仍含旧“52000”；根应在 V40 计划构造时替换为真实新依据。V19 prepare main 硬编码旧 V18 账、旧路径和最大余额，**不能直接重跑**；V19 preflight 也固定旧目录/历史准备条件，应写 V40 独立入口，复用当前库 API，不调用旧 main 或再次解压旧原件。
4. 新路径必须 exclusive 且未存在，ROS domains/Gazebo ports 含 reset 的多 worker 偏移均确认无冲突。目录/端口发现为准备；首次 reset/native 不是免费“发现”。不先启动 World 做路径/可用性冒烟。
5. 在 clean/pushed exact40 freeze 下实际 CPU preflight：`source_check(plan,plan_path,freeze)`；`native_custody_reach.verify_binding(ROOT,freeze,binding)`；三个 `stage_spec`；executor/controlled/full/peer/cadence/PPO projections 和 `reach_gates.load_native_gates`；最后再次 source_check。preflight 输出 schema 必须 `mr3-reach-preflight-v1`，passed、exactfreeze、plan SHA 均匹配。历史 build bridge 的 flags、manifest、原 actual wait、当前 ELF/源均须重核；无新 native 信用。
6. 与原生入口有关的受影响人工 CPU 最短集合：conda 的 reach_preparation_entry/reach_qualification/reach_policy_chain/reach_training_admission/audit_reach_ppo/exact_snapshot_validator；system ROS 的 audit_seed_inputs + 原生 seed/start/launch 接线；custody/reach wrapper 源投影。V39 完整证书等价回执可作为原 source 证据，但 source/fixture 有新变时需新回执。system 无 torch，snapshot validator 留 conda，不再复现 reader_v1 的环境误路由。root 统一 source-before/after、console SHA、actual wait，并保留失败。
7. 固定 source 后到所有工程子进程、消费者和外尾退出前不得编辑 production/plan/binding。外层 `reach_execution` 本身没有独立硬终止超时；主阶段仍依赖真实 coordinator deadline/close 管理，不能把它当新的 watchdog 或自动延长矩阵。外部 final 需同时观察 matrix/policy coordinator 与其 outer wrapper，PID/start 相同且 Z 仍算 present；保存所有子身份，fresh absence 不能只观察 ROS descendants。

## 实际执行接口（此审查未执行）

从 W 目录运行学习侧 conda 命令，`PYTHONNOUSERSITE=1`，不继承 ROS `PYTHONPATH`；ROS 子进程由 Supervisor 的已有 clean environment + canonical setup 流程生成。下面 `PLAN/FREEZE/QUALIFICATION/OUTER` 代表 V40 预封路径，不是旧 V19 输出。root 的 source-sealed wrapper 必须包含全部实际 source 参数与外部关闭 observer。

```text
conda-python -B -m mr3_learning.reach_execution --scope cpu --output NEW_PREFLIGHT_OUTER --source ... -- conda-python -B A40/preflight_v1.py --plan PLAN --freeze FREEZE --output PREFLIGHT
conda-python -B -m mr3_learning.native_custody_reach verify --binding BINDING --freeze FREEZE --output NEW_BINDING_CHECK
conda-python -B -m mr3_learning.reach_execution --scope engineering --output NEW_MATRIX_OUTER --source ... -- conda-python -B -m mr3_learning.reach_preparation --plan PLAN --freeze FREEZE
conda-python -B -m mr3_learning.reach_preparation --plan PLAN --freeze FREEZE --qualify MATRIX_OUTER/actual_wait.json --output QUALIFICATION
conda-python -B -m mr3_learning.reach_policy_chain --plan PLAN --freeze FREEZE --qualification QUALIFICATION --stage minimum
conda-python -B -m mr3_learning.reach_policy_chain --plan PLAN --freeze FREEZE --stage minimum --finalize-outer-wait MINIMUM_OUTER/actual_wait.json --output MINIMUM_FINAL
```

这里 `conda-python` 的确切路径是 `/home/zhuyulab/miniconda3/envs/ns3gym/bin/python`。这些是接口模板，`--source ...` 和大写路径须由根展开成预封实参；V40 `preflight_v1.py` 当时尚未生成，不表示已有可执行入口。调用 learner/native gate 会依赖 torch，应使用 conda-python；system ROS imports 应作为干净 ROS 子命令独立记录，不能把两边的 sys.path 拼接。`native_custody_reach verify` 不依赖 live ROS，也可使用 system Python，cwd W。

matrix 的 `--qualify` 只有 coordinator 与 outer 已退出且完整30角色/12epoch/所有消费者与源字节核查通过才会成功；该原件读取本身须计入已预约外尾。minimum/pilot/validation 均通过 scope 对应的 actual-wait wrapper 调用，finalize 后再独立外层 observer 确认全部保存身份 gone。pilot/validation 的 CLI 仅替换 stage 与对应预封前驱路径，不能省掉 predecessor/final checkpoint 核查。

`audit_reach_ppo.audit_episode_conjunction` → current `audit_reach_preparation` 的 exact archives wrapper → `audit_seed_inputs.audit_episode`，已接上七 received maps、完整 snapshot 和当前冻结 pure source 重建；private snapshot validator 负责结构/digest/encoder 门，不单独充当几何 oracle。此链应在 preflight/人工 fixture 验证，正式数据仍由既有完整独立审计执行。

本轮只读结论不承诺矩阵会 PASS、采样性能或策略可学性。V21 ACK、V37 FIFO/租约以及所有历史 FAIL 仍属原冻结，不改判；P2A 仍须实际完整原生资格、minimum、保留额度内 pilot、final-only 严格任务证据。
