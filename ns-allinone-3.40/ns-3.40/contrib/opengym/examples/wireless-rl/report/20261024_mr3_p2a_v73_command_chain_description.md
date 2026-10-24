# MR3 P2A V73：单 motion 请求到应用链描述的实际闭合

V73固定单流描述实际PASS：执行G `45396954ed2612980859cff4629af1e6a662114c`，Root5969初27397c/终dc2dc7真实reap0。完整输入507221955B/SHA f27397fa…，232887行，parse/semantic/sequence-gap均0；consumer work48.085001603秒，派生输出2554234B/SHA `e467364d394108cd7acb0953663922d4f040cd38ffdb0785bdc66b62fe205c81`。仅描述PASS，V71原生FAIL、original_activity_passed={present:true,value:false}及科学门保持；无新World、轮反馈/plant证明、学习、容量或P2A完成信用。

规范[末账](assets/20261024_mr3_p2a_v73_command_chain_description/closure_ledger_v1.json)6066B/SHA `4211c4b4ed13d26db405b93797fc1ea3a937b705f420f49db8cce2762f34d271`：连续parent52.742855767秒，U112639.6725192646018/C180000/R67360.3274807353982。费用从same-PID bootstrap起点到post-source ended、summary序列化前记录边界，含gaps；consumer wait48.374098953秒与Root工具区间不另加。原300parent/240work软门满足，pilot1870/2905.9547395464029秒、final-only900/9000秒原额保持，工程上限仍为代理依持续委托选择，不声称逐数值用户批准。

26源实际before/after/current-Git与全恢复快照一致；driver2244319/start456045326和consumer2244399/start456045559两保存身份freshgone，nonowned不声称gone。关闭CPU10913初fbfc52/终94ceff真实rc0/7.123449494秒，4执行源before/after/current与恢复一致、own2gone，工程0。主[库存](assets/20261024_mr3_p2a_v73_command_chain_description/closed_inventory_v1.json)42regular4185292B→458027B/0link，全字节恢复、原件不删；仅封存本次parent、RootTool、派生输出及已停写criteria，没有重开507MB原motion、旧两输入、drive CSV、pstats或342库。关闭CPU后继证据另存于[closing_CPU库存](assets/20261024_mr3_p2a_v73_command_chain_description/checks/closing_CPU_v1/inventory_v1.json)，不混入主活动费。原[criteria](assets/20261024_mr3_p2a_v73_command_chain_description/closed_execution_v1/tmp/mr3_p2a_v73_interpretation_criteria_v1/CRITERIA.md.rawbytes.gz)与[派生全文](assets/20261024_mr3_p2a_v73_command_chain_description/closed_execution_v1/tmp/mr3_p2a_v73_command_chain_description_v1.json.rawbytes.gz)按库存条目SHA恢复；此前已有opaque字节读取，不宣称原件从未读取。

派生结果显示两类不同的阻断证据。在precleanup postcommit [44.72,49.72)每机250条控制tick中，raw均可exact join且receiving state为ACTIVE：tb1/2的raw=effective=output linear v均0、w=-.3，reason为reach_clear；tb3的250条raw/effective v均>0，其中237条≥.08，却全部output v=0，223条linear_brake_preserve_requested_turn、27条reach_transition_envelope，记录区域均D。D沿用既有固定anchor圆盘定义，不由标签推断真实物理违界。以上区分收到raw已为0与正effective被Reach拒绝，不确定具体peer，也不把guard定位冒充单一完整根因。规范ledger的root_cause仍为UNKNOWN_PENDING_SEPARATE_DERIVED_ROUTE_REVIEW，原字节不变。

上述有限判读另见[独立derived-only复核](assets/20261024_mr3_p2a_v73_command_chain_description/checks/derived_functional_judgment_v1/REVIEW.md)及其原字段/引用；该复核只读本次派生结果，不重开原科学输入、不改原FAIL，也不代替下一V74准入。

每机353条APPLIED均exact join到Reach/storage且body target.linear_x=0。body target为0不等于双轮命令0，实际转向/过渡仍保留；三机APPLIED rim均值均无≥.08。tb1/2各有一次极小正rim均值，位于cleanup后49.748/49.758秒，约3.54e-5/3.39e-5且bodytarget仍0，不是正向平移plant试验。APPLIED只属原日志接收/应用标签，不充wheel SetParam/readback或机体响应；当前没有正native body target依据，不为此追加读drive。raw goal生成、发布和交付时刻以及上游/具体peer的完整因果仍UNKNOWN。

下一V74只前瞻设计对同固定已闭合motion原件的有界描述，提取tb3 rejected transition checks及own/peer/intent引用；R、.5、B_stop、D、原数学及5秒门保持，不改rank/plant，不重开V71/V73，不直接World。新spec/source闭包/预算/freeze/准入尚待独立声明，不预填已admitted或成功；暂停2+1/1+2与自然成功假设。capacity/autoPolicy=False，P2A未完成。

历史准备快照：下文保留当时原文；其中“尚未执行/新G待封”只代表此前准备时点。

# MR3 P2A V73：单 motion 请求到应用链的有界描述预声明

V73 软件准备已完成，原 motion 描述尚未执行，也没有描述 PASS。Root 在所有 canonical CPU 之前，将固定一输入 spec 前瞻 admitted=True；该准入只授权本次有限描述，不能代替新 freeze、来源核验或实际读取。唯一输入为 V71 库存固定的 motion_safety.jsonl，507221955B/SHA `f27397fad35ca23d6957c6c41121fc548f3f4718ecbbfc90d906ddb064f7cd08`；完整 parent300/work240秒软费门、输出最多4MiB。工程仍 U112586.9296634976018/C180000/R67413.0703365023982，预约300，未新增活动实费；capacity/autoPolicy=False，P2A未完成。

本次只描述收到态39.72秒 GOAL 至49.72秒 cleanup，并观察至51.72秒首见 CANCELED 的命令链。原始生成/交付时刻仍 UNKNOWN，不合成跨进程 wall 顺序。区分 raw 请求→authority effective→Reach→native storage/APPLIED 各层记录；后两者不能充作 wheel-write/readback 或 plant 因果。没有 drive CSV、旧 summary/transitions 两输入、新 World 或物理重审。此前 motion 已作 opaque hash/copy/恢复，本次准备未语义读取它，不能宣称原件字节从未读取。

证据 G 为 `b3707dcf258c832f35ef60f47a5dc8dc52296629`（V71 Root65935rc1）；前账 G 为 `74c8f710114bac3c2c91a5a1df8ebc6c63ec7637`（V72 Root64500rc0，仅描述 PASS）。新执行 G 尚待 commit/push、显式 clean HEAD==origin 与 exact Git blob 检查，不预填。前账 [A72 ledger](assets/20261024_mr3_p2a_v72_masked_stimulus_description/closure_ledger_v1.json)6593B/SHA `cd620cc88978991f6de366f281e8ce458f07379552abad59ba3886f3319078ab` 保持；original_activity_passed 仍为 `{present:true,value:false}`，V71 原生 FAIL 不改。输入路径/stat、epoch、A71库存799822B/SHA2cdf667a…及恢复包装见 [固定引用](assets/20261024_mr3_p2a_v72_masked_stimulus_description/checks/v73_fixed_inputs_v1.json)3110B/SHA `dc76a9a1b401df01c1cc41b9d957898a0c5b7a8c6f27950c4cb043a5133ed9f9`。

canonical CPU Root17796 真实 reap0，17项（consumer13+parent4）全部通过，实际 child wait4.140205043秒；97绑定源 before/after/current 与全恢复快照一致，2保存 CPU PID/start freshgone。见 [实际回执](assets/20261024_mr3_p2a_v73_command_chain_description/checks/canonical_CPU_postreap_proof_v1.json)。独立 bounded metadata/source 复核亦真实通过：direct chunk32441e rc0/.216206044秒，206绑定稳定、own2gone，确认上述97源恢复与 runtime26 exact；它没有重跑测试、consumer main、旧342库或 World。见 [独立复核](assets/20261024_mr3_p2a_v73_command_chain_description/checks/independent_CPU_review_v1/review_v1.json)。这些都是软件准备证明，工程新增0，不是507MB实际消费或科学资格。

最终 [consumer](assets/20261024_mr3_p2a_v73_command_chain_description/describe_motion_chain_v1.py)39230B/SHA `77d6c905f6b96466cf2405e9590e86ec1e0e68059bbd8b691772a2032eff38bf`；[admitted spec](assets/20261024_mr3_p2a_v73_command_chain_description/description_spec_v1.json)8586B/SHA `8c4127429391d39e4c077c4326b61913b36aacd8dbd9fcba2accd06172217512`；[parent](assets/20261024_mr3_p2a_v73_command_chain_description/run_description_v1.py)21016B/SHA `8ffbe87dc8ef5e44de9e3615f74a93a7d5f69dc3083d2db5e5d13311a3e15915`。[runtime manifest](assets/20261024_mr3_p2a_v73_command_chain_description/source_blob_manifest_v1.json)5057B/SHA `9aa770fd3950ac18ae6b04556f5a4270c38406e9bf6d764f9195f186ff22e513` 固定20解释源+consumer21，再加 spec/parent/库存/前账/固定引用，自然为26；原 motion 不进入 source hash union。执行时仍须该26源的新 G/current 与恢复快照、完整输入 SHA/stat、严格解析和输出门实际通过；缺依赖、未知字段、partial 与真实 rc 均保留，不能补造或只凭源相等报描述 PASS。

七个已停写私有候选/派生审阅根，289 regular/5136148B，无损封存为1286661B、0link，并全字节恢复及原件前后 stat/membership核验；原件保留，见 [历史库存](assets/20261024_mr3_p2a_v73_command_chain_description/checks/candidate_history_v1/inventory_v1.json)。原 consumer12→13、parent0→4 分轮保留，不叠加成新判据或代替 canonical17；三份派生路由审阅只保存原字节。归档 CPU15200 真实 rc0/1.224805289秒，两执行源 before/after/current/恢复一致、own2gone，工程0，无原 motion 读取或科学信用。

下一步由 Root force-stage 全部 selected regular（含 ignored console），核 INDEX→commit→真实 push→显式 clean HEAD==origin→exact HEAD blob，然后按 parent 独立一次读取。完整费从 same-PID bootstrap 经实际 consumer wait、gaps、post-source 至 final summary 一次结算；300/240是合作式软门，超额全费 FAIL，nested/root不叠加。活动期间 source/config/docs/index 保持冻结，Root真实 reap 与保存身份退出后再关闭。

暂停2+1/1+2路由和直接 World，不以短goal自然成功、Reach必然压0、plant坏或只是没转完作为已证前提。V72收到样本仅表明 t5–10 signed v范围[-.0003998413467885009,+.0009048234214563353]m/s，w有转，速度与新path谓词未满足；原生因果仍未知。先完成这次有限链路描述，再依实际证据决定最小后继修复。pilot1870/2905.9547395464029秒、final-only900/9000秒与三open401/402/403原额不借用；安全分离/B/R/STOP/质量/95%及全部历史 FAIL 保持，无学习、容量或P2A完成信用。C与本有界工程预约由代理依用户持续委托前瞻选择，不声称逐数值用户批准。
