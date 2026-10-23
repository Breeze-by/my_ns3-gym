# MR3 P2A V52：reset 显式接线、等价审计提速与新完整资格链

**最新闭合：FAIL。** 24/30 必要角色通过；deadline 第204次动作执行收到控制模型负 ACK，整链已关闭，未启动学习。实费与原始失败见文末“实际闭合”，下一步为 [V53 固定两原件取证](20261023_mr3_p2a_v53_firstfault.md)。

## 准备时历史快照

准备完成，待新commit/push freeze执行；尚未新原生执行或学习。P2A 未完成。用户持续授权自主完成，不再逐次询问常规修复或工程安排；P2B/gateway 未启动。

已应用显式 `mr3-reach-reset-outward-cancel-v1` reader 登记，仅对固定 V17 两份完整源码的唯一 PROBE_VERSION 赋值作声明投影；原件、V3/V4 数学 leaf 和全部物理判据不变。新 preflight 必须真正执行双 load、检查六份 current/plan/Git 源与全源码逆投影并保存 receipt，异常即停止。V50 两入口 FAIL 不改判。

runtime 三处提速由 V51 实测热点支持：按已完整验证的 declaration sequence 保留最后 intent；按 component 延迟建立包含全部重复 ACK 的索引，非字符串 ID 回原扫描；严格 JSON object hook 改用 dict 构造和长度检查。保留原字段触碰/错误先后、完整 canonical/非有限值/深度校验与几何数学，不改变采样、来源年龄或科学门。实际候选10项人工等价检查 PASS；接入后 reset/runtime/index/qualification 共81项 PASS（58.214042114秒），真实 system 模块 help PASS（.11901566秒）。随后新resource v3接入后的23文件集成套件297项全部通过（完整actualwait118.32906101秒、282份源码前后稳定），见[真实wait](assets/20261023_mr3_p2a_v52_qualification/checks/fresh_preparation_cpu_v1/actual_wait.json)及[可恢复源码](assets/20261023_mr3_p2a_v52_qualification/checks/fresh_preparation_cpu_v1_source_recovery.json)。这些都是 CPU，工程费0，不能替代新资格。见[原始CPU及候选字节库存](assets/20261023_mr3_p2a_v52_qualification/preparation_archive_inventory_v1.json)。

runtime 的 source_proof 按传入的新 freeze 对固定源码集合逐字校验，并无旧 runtime 自身 SHA 逃逸；必须用新源码/新 native 的同一冻结，不把旧 V50 回放变成资格。全量审计及 learner 依赖在 ns3gym，ROS/system 独立 reader 保持原环境隔离。

## 前瞻工程资源决策

[资源封存声明](assets/20261023_mr3_p2a_v52_qualification/resource_v1.json)采用新显式 `autonomous-engineering-block-v1`。这是代理依据用户自主持续委托作出的有限工程安排，**不是声称用户明确批准了120000这一数值**。既有52000/75000历史快照和所有实际费用保留；累计从[已关闭V51末账](assets/20261023_mr3_p2a_v51_runtime_profile/closure_ledger_v1.json)70543.1774146986018承接，不清零或退款。新累计上限120000，余额49456.8225853013982。

| 阶段 | 完整parent预约秒 | native预约秒（含原120关闭） |
|---|---:|---:|
| interface |2600|1900|
| terminal |1200|850|
| reset |16000|6500|
| deadline |25200|14000|

矩阵45000＋minimum1800＋外部收口300＋preflight120＝47220，最坏预约后仍余2236.8225853013982。费用只按真实完整 parent 区间 union 收取，nested 不重复；截止后仍排空已提交工作，超额完整收费且资源门 FAIL，不保证操作系统硬实时。

依据是 V50 完整 interface2032.384042887、terminal758.807755841、reset11302.772605716秒；reset native4557.609774705、full6342.154525786、runtime2624.727991544秒（存在并行重叠，不相加为parent）。deadline300步尚未新执行，按32步参考保守外推并为全审计留余量；不声称此推断是实测，也不把三点优化假定成某个 native 加速倍数。旧reset最终cap6301.463804643不足，不能再沿用缩小预约而隐含期待消费者免费。

旧默认和 bounded profile 保持。prepare、plan_check、preflight、driver 必须使用同一个含 SHA/bytes 的 resource/前账输入，真实 qualification/reach_gates/PPO 再 load_plan 也必须接受合法资源并在模型前拒绝变造。四入口 CPU 准入已完成：第二轮10case全部PASS（16.922094235秒），真实prepare PASS（3.775742432秒）及plan_check PASS（.430606694秒）；[规范plan](assets/20261023_mr3_p2a_v52_qualification/plan_v1.json) SHA `63de7b8d0eacea5d2733d3552fc3abc8b7f408db8717f725c36ff2a4d33f35cc`，933源/10ELF，binding SHA `896b9402f258645f4c23363fc74e3e50a5905b96abc4640bc7cc87401167ddf4`。只执行人工入口边界、实际模块help及源码/ELF元数据，不提供native资格。新双环境真实readiness已PASS（7.385659528秒；system实际loader/逆投影与ns3gym CUDA元数据，不构造模型）。入口fixture首轮4个真实模块help通过，6项因人工binding的binary/support不匹配在setup失败（17.01009387秒）；仅修fixture显式support绑定，保留原[失败wait](assets/20261023_mr3_p2a_v52_qualification/checks/admission_cpu_v1/actual_wait.json)及源码snapshot，新v2输出目录重验，不改生产门。

## 固定科学出口与执行顺序

同一新 freeze 完整12EP/30必要角色 → fresh minimum16、实际 eligible 样本及正 optimizer 更新 → 原余额内 pilot → final.zip 冻结后的 open401/402/403 三指定 final-only、验证零更新且全部 strict95。pilot 仍1870 decisions/2905.9547395464029秒余额，final仍900 decisions/9000秒；本次工程决策不自动扩大二者，不保证64样本或95%结果。

V50 原18PASS/2FAIL/10SKIP、阶段超额以及两 corridors 每回合停车样本不足全部保持。原聚合 physics 判据按完整八回合覆盖，不以可选每回合缺样本制造新PASS，也不把旧parser修复冒充通过；新结果由完整原件及全部独立必要审计裁决。禁用的五流 timing 草稿发现有限值/schema校验缺口，仅9人工CPU通过，未准入/未消费原件，不为此新增诊断活动。

[准备闭合元数据](assets/20261023_mr3_p2a_v52_qualification/checks/closed_cpu_preparation_review_v1.json)核9份真实wait、18个保存PID/start均freshgone（Z仍算present），唯一首轮FAIL明确保留、源before/after及控制台SHA稳定，工程0。下一 AI 接手时先读本报告最新状态及规范 plan/driver 原件；当前无新 native/模型，禁止将准备或 CPU PASS 当作 P2A 完成。后续实跑逐项追加本报告、log.md、末账与身份关闭证据，再 commit/push。

## 实际闭合：完整链 FAIL，来源、费用与无损归档关闭 PASS

**本节为最新状态；上文“待执行/无新native”仅保留为准备时历史快照。** freeze `1fa55bc56d5bb9e230d4b397f962d83b1604b278` 已真实执行并由根工具 session70032 实际 reap，返回码 **1**。P2A 仍未完成，没有模型、minimum、pilot、final 或 optimizer 更新，P2B/gateway 未启动。[真实 driver summary](assets/20261023_mr3_p2a_v52_qualification/closed_execution/tmp/mr3_p2a_reach_v52_driver_v1/summary.json)和[实际 root-tool wait](assets/20261023_mr3_p2a_v52_qualification/closed_execution/closure_tools/mr3_p2a_v52_actual_tool_wait_v1.json)保留原 FAIL。

preflight PASS，完整 parent46.856060022秒（nested45.743779836包含其中）；实际 reset 双 load 六源、runtime23/cadence25 的 current/plan/Git source proof 均通过。interface9、terminal6、reset9 必要角色通过，共 **24/30**；reset 全 stage11294.261598921秒，九项必要审计全部 PASS。原可选 physical_per_episode 的两个 corridors/tb3 有意义停车样本不足 FAIL 原样保留；聚合必要 physics 的 B 取消链覆盖不能被解释为 A 硬零停止证明或连续时间定理。

deadline native 完成 **203 次完整 step 返回**，随后一次请求在244.58仿真秒收到真实 `normal_control_model_invalid` 负 ACK/RPC 错误，第204次返回没有产生，不能补造 transition/reward。任务 release41.3秒，故该控制错误发生于203.28任务秒；不是300秒任务截止或本轮 wall allocation 先到期。现有闭合小元数据尚不能确定底层首故障的 robot/reason。deadline 的六项必要科学审计**未派发**，不能计为六项科学重放 FAIL，也不能计 PASS。matrix 随后停止，minimum/pilot/final 未启动；局部 cleanup PASS 不改原 episode infrastructure_failure/forced shutdown。见[原小元数据说明](assets/20261023_mr3_p2a_v52_qualification/checks/closure_v2/provenance/mr3_p2a_v52_deadline_failure_metadata_note_v1.md)。

### 实际末账与身份

四个完整工程 parent 区间互不重叠，sum=union；native、watcher、reader nested 时间不另叠加，driver bookkeeping gap 不伪算为 child wait。

| 完整 parent | 实际秒 |
|---|---:|
| preflight |46.856060022|
| matrix |19273.355286664|
| matrix_absence |5.030591601|
| chain_final_absence |5.086383807|
| 合计 union |**19330.328322094**|

承接 V51 累计70543.1774146986018，现为 **89873.5057367926018 /120000**，余额 **30126.4942632073982**。120000仍是代理依据用户持续授权作出的前瞻工程块，`numeric_user_approval_claimed=false`，不是用户逐数值批准；旧账与旧 FAIL 不清零。pilot/final 新增费用均0，原1870 decisions/2905.9547395464029秒和三场 open401/402/403 final-only900 decisions/9000秒保持。见[规范 closure ledger](assets/20261023_mr3_p2a_v52_qualification/closure_ledger_v1.json)。

[实际独立闭合 review](assets/20261023_mr3_p2a_v52_qualification/closed_execution/closure_tools/mr3_p2a_v52_independent_closed_review_v2.json)的 metadata/source/process 结论 PASS、scientific activity 结论仍 FAIL：933源/10ELF 与原 plan/Git 相符，611个保存 PID/start 全部 freshgone；按原 A16 同对象身份/全局覆盖规则，global unbound 与 identity parse errors 均为空。原 PID-only occurrence 保留，不跨对象拼 start，不声称未记录进程不存在。

后继 review、collector、overlay 及相应人工 CPU 的六份完整 wait/console/源码绑定另封存：[CPU 证据](assets/20261023_mr3_p2a_v52_qualification/checks/closure_v2/closed_cpu_evidence_v1.json)。独立 fresh 核12个后继CPU身份，未并入主611。新 static-only seal rc0、0.638006453秒、六源稳定，其两个身份在实际工具 reap 后[单独 freshgone](assets/20261023_mr3_p2a_v52_qualification/checks/closure_v2/seal_cpu_postreap_v1.json)。这些有限 metadata/archive CPU 工程费0，不重跑科学 reader。reviewer 首稿 critical-ref latch 缺口及 overlay 人工v1的3 FAIL/2 ERROR 原件保留；后继8项 tool-wait、9项 overlay 人工检查通过，不修改原失败。

### 无损封存与 Git 分片表示

实际 collector rc0、1721.014750639 CPU scope实际wait墙秒，保存 **7772 文件 /15628170281 原字节 /1293834289 packed canonical字节 /0 symlink**；policy root 原本未创建。不可变 [V1 inventory](assets/20261023_mr3_p2a_v52_qualification/closed_inventory_v1.json) SHA `63efb61cc7b2abaf723b3824399d203a1a0b288465a367110eabcb5ec565ccf7` 保留原 gzip/解码字节证明与全部原 PASS/FAIL。

实际 overlay rc0、20.440347567 CPU scope实际wait墙秒，仅将两个超过64MiB的既有 packed gzip 按字节拆为六份，每份≤67108864B；逐份与完整连接 SHA均校验，不解压/重压/重放。原 packed 保留本地，只有其两条精确路径被 ignore；分片与不可变 V1 inventory 一起纳入 Git。[最终 manifest](assets/20261023_mr3_p2a_v52_qualification/packed_overlay_v1/manifest.json) SHA `0b5d73736e9560982ca6234cb49e59d589de21e83d40ddeff3ead1abcb6104ad` 保存 offset/index、每份 SHA、完整 gzip SHA及原 raw SHA 的映射。[恢复说明及工具](assets/20261023_mr3_p2a_v52_qualification/checks/closure_v2/README.md)给出 exclusive 输出与完整 SHA校验命令；本节所述 canonical字节指标是V1逻辑表示，不是本地同时保留原 gzip/分片后的磁盘用量。

下一步先对固定已闭合原件作一次另行封存范围的有限**首控制故障取证**，识别真实 producer first-fault 与接收链，再按原因修复、CPU验证和新freeze。不能只据通用错误名选根因、放宽95%/质量/安全/12EP30角色，或在修复前启动PPO/机械重跑完整矩阵。剩余30126.4942632073982秒已不足原47220整链预约，后继资源须按实际问题另作有界安排，不借用pilot/final额度。归档和metadata关闭PASS不代表技术P2A完成。
