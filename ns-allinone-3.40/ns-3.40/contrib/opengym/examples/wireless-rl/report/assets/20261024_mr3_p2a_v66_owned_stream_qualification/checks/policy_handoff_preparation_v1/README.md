# V66 矩阵之后的 policy 入口与容量取证准备

2026-10-24，仅只读源码/已闭合派生摘要准备。没有启动 PPO、reader、World、编译或测试，没有读取原始科学流或 pstats，没有修改 canonical 文件。本文件不是准入凭证。**V66 matrix 尚无本文件认可的实际结果，capacity=False，成功值均留空。**

当前规范的 policy 实现是 `mr3_learning/reach_policy_chain.py`、`ppo.py`、`audit_reach_ppo.py`；已只读核对 canonical A66 `prepare_plan_v1.py:339–364` 的 policy registry、`scope_v1.json` 和 Root 宣布实际 plancheck 通过后生成的 `plan_v1.json`。实际读到的 plan 为591116B/SHA `064f2a2ed9b256decdc4a0394494faa5340f49e16430be1bffc751f0c0ded4b0`，1111 source bindings/10 ELF；这只是准备原件 pin，没有 execution freeze 或 matrix 成功含义。A65 registry 只作未改参数的历史交叉核对。**A66 scope 当前明确 `capacity_qualified=False`、`automatic_policy_entry_allowed=False`、`execution_scope=new_same_freeze_full12EP30_matrix_and_qualification_only`**；run_matrix_v1.py:225–245 严格核这些值，不能借 registry 的存在自动运行 policy。

## 先决条件和阶段关系

1. V66 同一 exact40 freeze 下，四 matrix stage 全部真实结束；12 EP、30 必要角色、所有独立 reader、真实 outer wait、保存身份 freshgone、源/库前后及 current-Git 均闭合。保留原 required FAIL / SKIPPED；不能拼旧 freeze 或把旧活动重判。
2. 从 matrix 的真实 outer receipt 生成 qualification；`validate_qualification` 会重建完整证据，不接受手写 passed。接收权限 profile 必须有 12 EP 的独立 authority replay，三机均通过、`raw_generation_known=False`；inner actuation 仍为 `initial-zero-encoder-hold-v1`，compound replay、geometry/intent/固定 R/anchor/STOP 债务均保持。
3. 读取真正关闭后的工程账。minimum 需完整 1800 秒加尚未用完的工程 external reserve，不能降 minimum cap、借 pilot 或按阶段 nested 耗时重复记费。Root 给出的 V66 入场参考为 U109131.3266391666018/C180000/R70868.6733608333982；未来入口必须用实际 matrix 完整关闭后的新账，不能继续使用这个参考余额。
4. 当前 scope 是 matrix/qualification only。**matrix PASS 不把 capacity 变为 True，也不产生自动 policy 权限。** 当前 `reach_policy_chain` 本身没有 capacity-proof CLI/验证器；所以以下 CLI 必须由后继显式 admission 调用，不能绕过 scope 直接执行。最小后继工作是 Root 在明确有界的实际测量报告后作可追溯准入，再调用现有 CLI；不需要新增通用参数/框架，也不恢复 V60 的无容量检查自动循环。
5. 合法的新入口随后依次 minimum → minimum 独立 final absence → pilot → pilot 独立 final absence → validation。任一 required 失败必须关闭、全费、保留原件，后继阶段跳过，不重开同名输出。

若后继对生产/runtime/reader/冻结 plan 的绑定源作改动，不能直接借这次 V66 matrix 资格；须按照真正的新 freeze 重新准入和资格。不能为了新增容量许可直接编辑旧 scope 或旧资格结果。

## A66 已声明的实际入口路径

以下为已安装 registry 的静态路径，不是输出已存在或成功的声明：

| 内容 | 路径 |
|---|---|
| canonical assets / PLAN | `W/report/assets/20261024_mr3_p2a_v66_owned_stream_qualification/plan_v1.json`，W 为本项目 wireless-rl 根 |
| QUAL | `/tmp/mr3_p2a_reach_v66_qualification.json` |
| policy output root | `/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo_reach_v66` |
| stage run directory | 上述 root 下 `mr3_p2a_reach_v66_{minimum,pilot,validation}` |
| stage evidence | `/tmp/mr3_p2a_reach_v66_{minimum,pilot,validation}` |
| main actual wait | `/tmp/mr3_p2a_reach_v66_<stage>_wait/actual_wait.json` |
| independent final absence | `/tmp/mr3_p2a_reach_v66_<stage>_final.json` |
| finalizer actual wait 的既有命名 | `/tmp/mr3_p2a_reach_v66_<stage>_final_wait/actual_wait.json` |
| validation 固定 checkpoint | 上述 policy root 下 `mr3_p2a_reach_v66_pilot/final.zip` |

minimum/pilot/validation 声明 base domain 分别212/214/218，base port分别15801/15811/15821；从最终plan读取而非重新选择。实际执行前核 exclusive HOME 和这些端口/domain 以及输出目录的归属与空闲情况；当前 readonly准备没有运行端口检查或创建它们。

## 固定采集与预算

| 项目 | minimum | pilot | validation / final |
|---|---|---|---|
| 模式 | fresh train，seed41 | fresh train，seed41；不加载 minimum checkpoint | evaluate，只加载 pilot 的 `final.zip` |
| 请求 | 16 总决策、episode cap16、1 worker、open101 | 64 总决策上限、episode cap64、2 workers、open101 | 总上限900、episode cap300、open401/402/403 各一次、声明最多4 workers |
| 实际计数门 | 必须恰16 eligible，正 optimizer updates | 2≤eligible≤64，正 optimizer updates；64 是请求上限，不能预称实际取得64 | schedule 完整、恰3 EP、三场 strict success、optimizer updates=0 |
| 原完整 wall cap | 1800 | 2905.9547395464029 | 9000 |
| 外部 finalizer 预留 | 工程 external300 的剩余共用部分 | 原本阶段内300 | 原本阶段内300 |
| main cap | 1800 | 2605.9547395464029 | 8700 |
| native 字面 ceiling | 1150 | 2100 | 8500 |
| 扣前耗时前可分配 native ceiling | 1150 | 2100 | **8200** |
| 内部 tail 最低预留 | 500 | 500 | 500 |

`native_budget` 实际分配为 `floor_ms(min(native_ceiling, main_cap - elapsed_before_native - 500))`。500 是预留，不是审计一定能在500内完成的证明。完整 main 包括入场 source/qualification/predecessor 核验、watcher、native/PPO、正常关闭、所有科学审计、完整原件和 policy artifacts 绑定、source/raw 重核及 summary；outer wait 还包括解释器等外层开销。超过 cap 仍排空已提交 children，保留全费并 FAIL，不能把 finalizer 或审计挪到工程以绕过 pilot/final cap。

原累计 pilot 总额4096决策/14400秒，已用2226决策/11494.0452604535971秒，剩 **1870/2905.9547395464029**；本版只请求其中64，不重置历史。final 原额9000独立保持。工程47220预约的构成为 matrix45000 + preflight120 + minimum1800 + external300；当前 matrix-only scope 不表示 minimum 已实际获准或执行。

采集代码按剩余总决策在 active workers 间分配，所以 pilot 首轮是32+32，而不是64+64；final 三个 schedule 项首轮实际只会构造3个环境，即使 `--workers 4`。三场提前真实成功时，实际决策可少于900；不能补到900或把 timeout 当成功。minimum 不从旧16样本/旧V7更新复用，pilot 不从 minimum 续训；当前门只允许 validation 带 `--checkpoint`。

## checkpoint、归一化和最终成功门

policy 输出与 evidence 输出分开：plan 的 `policy_stages[stage].run_directory` 保存 `metadata.json`、`summary.json`、`initial.zip`、`final.zip`、`checkpoint_*.zip`、`rollout_*.npz/json`、`resources.json`；`output_directory` 保存 coordinator `summary.json`、ledger、native/watcher/完整 full/FIFO/closure 回执。目录必须不存在，不能覆盖或重试。

validation 必须逐字绑定 pilot 独立 final-absence receipt 中的 final checkpoint SHA，并限定路径为该 pilot 的 `run_directory/final.zip`。不能选中间 checkpoint、最好成绩、minimum final 或另一 run。推理 deterministic；实际 input checkpoint SHA 前后相等，initial/final policy 参数 SHA 相等，真实 optimizer step hook=0，离线 reader 重新加载 initial/final/input 三者逐参数等同。训练则要真实更新、非零参数变化、有限 metrics、原 collecting-checkpoint action/log-prob/value replay、rollout/variable-dt GAE/terminal bootstrap 全部通过。

“冻结归一化”在现实现中是 **同源固定物理 tensor scales**，不是另有可学习的 VecNormalize 状态文件。`observation.py` 的 `mr3-learning-tensors-v2`/`mr3-observation-v3`、6 navigation phases、binary maps、缺失 valid flags、固定 scales 由同 freeze source 绑定；`metadata.normalization` 必须保持 `frozen physical tensor scales only`。不能用只有该字符串的 metadata 代替实际 tensor/原始 snapshot 独立重构和源一致证明。validation 不收集更新 normalization statistics，也不改变观测 schema、阈值或 crop。

三场每场都需原 evaluator 的 `success=True`、`correct_free_coverage_ratio>=.95`、`elapsed_sim_time_sec<300`、`map_quality_pass=True`、`robot_participation_pass=True`、零真实 contact、fresh collision monitoring、closed navigation protocol。open 冻结合同质量阈值为 observed accuracy≥.95、occupied IoU≥.20、false-free ratio≤.02；每台累计 path≥1m 且 accepted goal count≥1。必须复核实际 evaluator 合同、原 independent safety/scalar/contact/18路监测、真实 cadence/input/runtime/FIFO/authority/compound law 等全部合取；reward 高或没有前沿不能替代成功。strict95 是覆盖率门，三开发 seeds 的3/3结果不是95%统计可靠性或未见场景泛化；P2B/gateway 未由此自动授权。

## 要从 V66 实际输出取得的容量数据

只从**闭合的** metadata/receipt 提取；正在增长或未实际 tool-reap 的文件不能填最终值。先核每个 child receipt 的 output SHA 与被读 JSON 整 SHA 一致，且 source/freeze/argv/path/epoch join 成立。以下是提取表，不是新的 reader 或 cache。

| 数据 | 真实位置 / JSON 字段 | 用途与限制 |
|---|---|---|
| matrix 完整 fee、closing、所有角色 | Root driver summary 的真实 `actual_parent_seconds`/`actual_waits`，`plan.output_directory/summary.json` 的 stages/status/skipped、all_submitted_children_waited、charged_wall_seconds | 连续父区间含 gaps；nested 只分解，不再次加费。完整费用以实际关闭 ledger 为准。 |
| 单 stage 和各 job wall | `<matrix output>/<stage>/stage.json`: wall_seconds、effective_stage_wall_cap_seconds、budget_allocation、native/watcher/audits；每个 subprocess_waited child 的 started_wall_monotonic_ns/ended_wall_monotonic_ns/wall_seconds | runtime/full/input/cadence/physics/FIFO/closing 必须各留完整真实 wait。并行 reader 不把 duration 相加当父费；另算实际审计 endpoint 和最长关键链。 |
| native 总量及 EP 结构 | declared native receipt/output 指向的 `benchmark_summary.json`: wall_sec_including_all_attempts、valid_transitions、workers_results | 1/2 worker reset 与 final3 worker 不同；不能把 sum(EP wall) 当并行总墙时。 |
| 启动/推进/正常关闭拆分 | workers_results[].episodes[]: scene、seed、epoch、transitions、dt_values、startup_wall_sec、transition_wall_sec、wall_sec_including_startup_and_closure、terminated/truncated/reason；workers_results[].shutdown_receipts | `sum(dt_values)` 是实际 task sim 秒；推进 wall/task 秒与 startup 分列。残余=整EP−startup−transition，不能把残余全归关闭。零 dt terminal 另保留，不能以 transitions 直接冒 sim 秒。 |
| 长任务实际样本 | deadline stage 原 open101/300-step probe 的上述 fields，完整 deadline native + 全部 audit waits | 可显示同 freeze 的300 task秒推进/日志规模/审计实际量；不同 stimulus、1 vs3 workers、RL推理/地图和资源竞争仍不同，不能凭线性外推保证 final。 |
| 审计 I/O 与保全量 | 完整 reader 原 report 的 file bindings（bytes/SHA）、actual receipt output/console size、最终 closed inventory；原 archive/qualification artifact 的实际 wall | 不读 raw 求新指标；不要用小 source/helper CPU 或 gzip 压缩比推断全 reader 容量。source/hash/最终重核也占实际时间。 |
| 主机资源/争用 | native `resources.json` 及实际 metadata 中 worker数/CPU/设备/版本，actual observer/watcher identity | 记录峰值和采样范围；稀疏采样不是完整资源上界，不猜测被采样间隙。 |
| policy 真正完整阶段 | `<policy output>/summary.json`: started/ended_wall_monotonic_ns、wall_seconds、native_budget_allocation、native/watcher/audits、skipped/errors/scientific_result；外层 actual_wait；独立 final-absence 与其实际 outer wait | 要包含模型初始化/inference/updates/checkpoint和每EP完整审计/finalizer，matrix不含这部分的完整实测。 |

`observations_template_v1.json` 留出了这些结果与来源 pins。填数据本身不设 capacity=True。应先比较实际 native budget 可用量、启动/推进/关闭、全部 audit+raw/source重核、外尾300和整体 endpoint 剩余量。说明负载/worker并发/长任务/无profile扰动的可比范围；V66若只是短样本可比不足，容量仍 UNKNOWN/False。不得拿401/402/403反复作性能调参样本。

V60 闭合派生容量复核曾测 interface32task秒：native1142.750379943、完整stage2053.863667255、full895.529903519；reset open短前缀推进约31–32 wall秒/task秒。只是旧 E 的历史风险参考，不能当 V66 测量，也不能把 full>500 自动裁成未来PPO所需时长的定理。V63 派生摘要来自失败 startup partial main profile：motion self149.642740049、iterencode10.797169716、deepcopy cum15.053442151、strict_json cum9.093808096；这些帮助定位 V64等价提速，**没有任何 task throughput 或长链 capacity 信用**。不重复计旧kernel倍速。

## 供后继准入后的命令模板（本次未执行）

在最终 frozen plan 写明的新 scope 准许后，Root 使用现有 actual-wait 方式逐阶段提交并真实 tool wait，保存 launcher/child PID+start_ticks、actual returncode、source recovery/sourcebeforeafter/current、freshgone。所有 shell 变量必须由真实 V66（或明确后继新活动）的 sealed plan 填，成功字段不能手写。当前不运行整条链，也不运行 V60 execute_chain。

```bash
# 仅展示入口；FREEZE/PLAN/QUAL/WAIT/FINAL/FINAL_WAIT 必须是实际已封的新活动值。
PY=/home/zhuyulab/miniconda3/envs/ns3gym/bin/python
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES=0
unset PYTHONPATH PYTHONHOME
export ALSOFT_DRIVERS=null
# HOME 复用本新活动已声明的独占HOME，不能指回旧活动或漏掉它。
# SOURCE_FLAGS 为 --source <exact-path> 的数组：plan source_bindings、全部实际 library_bindings、
# frozen PLAN、对应 canonical wrappers；依最终冻结清单生成，不能只绑定协调器。

STAGE=minimum  # 后续分别为 pilot、validation；每次先完成前驱独立闭合和容量/余额准入。
SCOPE=engineering  # pilot→pilot，validation→validation
"$PY" -B -m mr3_learning.reach_execution --scope "$SCOPE" \
  --output "$WAIT" "${SOURCE_FLAGS[@]}" -- \
  "$PY" -m mr3_learning.reach_policy_chain \
  --plan "$PLAN" --freeze "$FREEZE" --qualification "$QUAL" --stage "$STAGE"
# 上一个外层工具必须实际 reap，校验 WAIT/actual_wait.json，随后单独运行 external finalizer：
"$PY" -B -m mr3_learning.reach_execution --scope "$SCOPE" \
  --output "$FINAL_WAIT" "${SOURCE_FLAGS[@]}" -- \
  "$PY" -m mr3_learning.reach_policy_chain --plan "$PLAN" --freeze "$FREEZE" \
  --stage "$STAGE" --finalize-outer-wait "$WAIT/actual_wait.json" --output "$FINAL"
```

注意协调器 **child argv 必须是 `[learner_python, '-m', 'mr3_learning.reach_policy_chain', ...]`**，native PPO plan 也固定 `[learner_python, '-m', 'mr3_learning.ppo', ...]`；当前 exactargv gate 不接受在 child 中插入 `-B`。`-B` 放 outer wrapper，child 无bytecode由环境保证。上述模板不能直接替代 parent 连续计费/关闭脚本：outer receipt 只含 inner child wait，tool/wrapper开销、main→final gaps 与连续 endpoint 必须由 Root真实父区间另存，不能伪造实际 wait。

main 独立 final absence 的 `passed=True` 仍不包括外部 finalizer 自己费用。pilot/final 要另核：finalizer实际≤300、main+final scope interval union≤原总cap、从 main真实开始至 final真实结束的 endpoint≤原总cap，费用不挪工程。minimum 的 finalizer与matrix absence/qualification共用工程external300余额。前驱 `previous_stage_summary/outer_wait/final_absence` 三个 exact paths 已由 frozen registry 固定，不能临时换文件。validation checkpoint也由 registry固定；无需手拼一次直接ppo命令绕过gate。

## 交接时应看到的最小闭合包

每个 policy stage：实际 parent/tool receipt+保存身份、原 coordinator/native/watcher/每个审计完整回执与 output SHA、source recovery+beforeafter/current/Git、全部 EP 原件库存与归档、checkpoint/rollout 完整库存、外部 final absence 和其真实 outer wait、父费用/原余额结算。最终独立 review 应能重建 qualification、前驱链、真实更新、固定 checkpoint/norm、三场strict95与原安全/质量全部合取；不得以 `completed` 或 `overall_claim=False` 的中间 summary 代替总验收。

目前 observed freeze、matrix资格、capacity证据、minimum更新、pilot final SHA、final三个成功值均为未知。本准备文档只能减少入口查找工作，不能授予科学信用。
