# P2A V20：独立审计器性能修复

P2A未完成。用户已授权常规修改、修复与验证直接推进，本版不再请求修改批准。V19原始矩阵、Information中断和所有旧FAIL保留；P2B/gateway未开始。

本版只优化独立离线审计器，不改变ROS执行、SLAM/Nav2、真实20Hz传感器配置、actor输入、奖励、95%/300秒任务、安全余量或科学义务。索引读取已闭合原件，不能给机器人执行提供尚未交付的信息。新reader对旧原件的开发回归不提供新冻结资格，不补齐原V19失败矩阵。

## 原始失败与定位

[V19原结果](20261019_mr3_p2a_v19.md)冻结3631，32/32脚本接口决策和六项已提交独立审计通过，但interface阶段超过2400秒墙限，Information真实-2/2666.069126958秒且结果缺失，后续三阶段及PPO跳过。58个保存进程身份均已gone；完整原件已归档。原Info中断栈在N交接中对历史applied目标反复扫描所有owner、重复canonical完整target。

第一项修复在原publication插入点维护保序多值目标索引，按已验证actuation序列保存完整target键。重复目标、对象引用、真实前缀、严格时间、received-self和全部anchor/sign/lineage判断保留。Information与peer_control中同一完整bundle SHA移出历史循环；空发布历史仍不算该SHA。

| 当时CPU检查 | 实际结果 | 原件 |
| --- | --- | --- |
| 三个既有模块52项 | rc0，15.266555326秒 | [actual wait](assets/20261020_mr3_p2a_v20/checks/information_index_cpu_attempt_v1/actual_wait.json) |
| 新原函数回归首轮6项 | rc0，15.932561681秒 | [actual wait](assets/20261020_mr3_p2a_v20/checks/index_equivalence_cpu_attempt_v1/actual_wait.json) |
| 扩充边界9项 | rc0，17.79671615秒 | [actual wait](assets/20261020_mr3_p2a_v20/checks/index_equivalence_cpu_attempt_v2/actual_wait.json) |
| 两模块整文件逆投影 | rc0，.142309022秒 | [whole-file proof](assets/20261020_mr3_p2a_v20/information_index_projection_result_v1.json) |

上述结果只属于回执中明确绑定的当时源码。旧函数来自完整SHA核验后的Git3631；边界含重复owner先后次序、目标完整编码差异、None HOLD、同clock同wall的row先后、两个真实actuation引用及空历史。反向应用唯一声明patch后，两生产模块完整字节等于原Git blob。后续ACK索引与runtime改动必须另做新检查，不将这组PASS重标。

## 新只读诊断：原件及失败均保留

[104份原件映射](assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/copy_index_v1.json)覆盖完整源快照、输出、profile、actual wait和中断记录，共1,668,023字节；全量copy SHA/bytes及原件before-after一致，原/tmp保留。两个profile helper在创建时误用20261019_mr3_p2a_v20目录，其实际历史路径和argv原样保留。

纯kernel CPU准备真实rc0/31.616835921秒，仅选原第一允许非零X/N decision(record88905)的先前上下文；十段cold1/warm25共.497809188秒。它不能推断整episode性能或供科学资格。[kernel原件](assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/kernel_output/result.json)与[真实wait](assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/kernel_outer/actual_wait.json)均保留。

完整原runtime剖析v1真实outer rc0/137.120663666秒；合作式120秒SIGALRM触发时仍在严格JSON/duplicate-key/canonical装载，original_audit_completed=false，不能称原审计PASS。原.prof有效；原JSON的空ranked_functions/total_calls=0是helper读取已被pstats消费的stats所致，原件不覆盖。[原结果](assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/profile_v1/result.json)、[仅从原.prof离线补充的summary](assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/profile_v1/profile_summary_from_saved_prof_v1.json)和[actual wait](assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/profile_v1_outer/actual_wait.json)分开保存。

core剖析v2真实outer rc1/269.000729653秒、外层四份source bytes稳定。原装载约134.7581秒后core合作式120秒timeout；helper因marshal(code)前后摘要不同判FAIL，source SHA/签名/行号相同，未保存独立code identity/co_code，不推断其运行时原因。FAIL在inputs_after验证前，不能声称全输入after已证明。有效部分.prof显示native_index32.1002秒、ingress_index81.0334秒；TF L924 listcomp已有55次，表明已进入decision循环。[原失败结果](assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/profile_v2/result.json)、[有效profile](assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/profile_v2/original_core_partial.prof)及[真实wait](assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/profile_v2_outer/actual_wait.json)保留；没有修改原数学核。

首轮新Information完整只读回归声明600秒root监督额度，但人工监督延迟，观察到814.868881123秒才对精确owned PID/start发送一次SIGINT；真实outer rc-2/833.533889498秒，全部reader+intent bytes稳定，输出缺失。全833.533889498秒入账，不将600写成硬上限或给回归PASS。新栈落在control dependency完整ACK历史的重复canonical比较。[intent](assets/20261020_mr3_p2a_v20/closed_v19_information_regression_intent_v1.json)、[受控中断记录](assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/information_interrupt/intervention.json)与[实际wait](assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/information_outer/actual_wait.json)保留；这次新reader开发失败与原V19 Information失败是两个不同child，均不改判。

新增加自动owned-child监督helper，超时对单一verified PID/start用pidfd发送SIGINT并真实wait，不signal进程组；必要清理尾仍计入外层实费。[CPU正常/超时两个fixture](assets/20261020_mr3_p2a_v20/checks/bounded_helper_cpu_attempt_v1/actual_wait.json)实际rc0/1.187485926秒/source stable，分别核正常rc0和超时真实-2、wait及gone；不以fixture替代科学或完整原件重放。

## 当前边界

截至上述三个正式诊断闭合，V20工程实费1239.655282817秒；加V19末账36483.3647801256018，为37723.0200629426018/52000，余14276.9799370573982。CPU单元/源投影/纯kernel/归档不作native费，nested/并行child不再双扣。后续完整新reader回归仍须按真实outer ns另入账。

该余额不足当前严格声明的18000秒新四阶段矩阵。本版未启动新矩阵、minimum、PPO、pilot或final-only验证；没有缩减12回合/30角色、降低预留、借用pilot或自动扩大累计上限。pilot1870决策/2905.9547395464029秒与三场final-only保持。


## 最终源码与完整重放

最终Information追加完整ACK多值索引，按原publisher-list位置和原对象保留重复payload；只在原control dependency门按原短路顺序懒编码。尚未因果的ACK不供信用，后来变eligible且位于cached match之前的旧行仍先审；nondecreasing query wall来自原prefix逐行校验。其余PeerReplay、received bundle、anchor/sign/received-self和全部数学门保持原规则。原ACK草稿22项PASS及完整source快照见[CPU wait](assets/20261020_mr3_p2a_v20/checks/ack_draft_cpu_attempt_v1/actual_wait.json)，仅是草稿原scope，随后实际apply后另作组合验证。

Runtime将native命令latest查找、raw callback计数及raw/calib/applied完整因果前缀改为严格索引；number每次先做原type/finite校验，再用typed=True/4096缓存纯Fraction转换。TF保持callback arrival严格早于decision、header不晚于clock+.2的二维选择，同header取最后prior callback；clock回退、乱序header及未使用坏尾均保留原语义。初稿会提前触发无关坏acttime的静态反例已在apply前修复，旧未执行草稿仍保留；真实v2首次normal-ready先执行完整原actuation检查成功后再建索引，STOP/nonready保留原循环和错误顺序。

最终八模块组合131项PASS，真实rc0/77.574838239秒、102源before-after稳定。新Information/runtime模块各22项，对照3631旧函数/完整旧runtime，覆盖完整编码/重复引用/迟到、缺失、future、同clock、clock回退和缓存拒绝门。[组合实际wait与源码快照](assets/20261020_mr3_p2a_v20/checks/combined_reader_cpu_attempt_v1/actual_wait.json)保留完整命令和每一实际源版本。没有修改旧tests以放宽判断。

最终[完整三文件逆投影](assets/20261020_mr3_p2a_v20/reader_optimization_projection_result_v2.json)真实rc0/.355942296秒；[manifest](assets/20261020_mr3_p2a_v20/reader_optimization_projection_manifest_v2.json)绑定组合patch SHA3cc61a8b24ed422ac2c1db7311d9fc613ff0417b36076008ff3c00f637894491。反向后完整字节等于Git3631，35个既有数学/Inputs/source_proof/wholeaudit定义含decorator原文及AST相同。源码SHA：Information f17c6fd76c4a1682ba36bd084548f74c46fd3151da14a3084c6613d984c6e495，peer_control29f074ecf0d704b4f484ccc1c0c990b0bdf7223e04ffbd44e4af887b038c989f，runtime4f6505f686945927641431a7cc64ee42e1fa5219b9d5f5144c82118fb96d88fa。[独立静态review](assets/20261020_mr3_p2a_v20/independent_reader_review_v1.json)的当时70个新增links/数学原文/闭合账检查也保留原观察版本，不改为最终未观察工作已通过。

Runtime完整闭合V19开发重放通过，真实外层rc0/339.708353551秒；[actual wait](assets/20261020_mr3_p2a_v20/closed_regressions/runtime_regression_v1/outer/actual_wait.json)、[自动owned-child wait](assets/20261020_mr3_p2a_v20/closed_regressions/runtime_regression_v1/child/actual_wait.json)和[完整结果](assets/20261020_mr3_p2a_v20/closed_regressions/runtime_regression_v1/result.json)原字节保存。无超时或信号；核心结果、全部13份artifact_proof逐字段等于原V19 runtime通过叶，Inputs.close及全部原数学检查真实执行，所有源和原件SHA/stat前后一致。这不是同条件性能倍数实验，原V19消费者并行，不能仅凭两个墙秒推断纯代码加速比例。

生产source_proof仍严格要求current==declared freeze，所以新runtime直接冒用旧freeze会被拒。仅本次[独立harness](assets/20261020_mr3_p2a_v20/closed_v19_runtime_regression_v1.py)在内存投影reader这一条检查，先核完整candidate patch逆投影等于原Git，再标注reader current_equals_freeze=false/diagnostic_candidate_sha256/qualification=false；其余原source==Git3631、native compiled source/feed检查、原完整loader/核心/Inputs.close不动。结果明确artifact freeze不是candidate freeze，不用本开发PASS补原V19失败或新资格。

Runtime闭合后账为38062.7284164936018/52000，余13937.2715835063982。最后Information完整重放在独立新outer进行，600秒自动监督；本段编写时尚未闭合，不预报其rc、耗时或PASS，随后真实结果另列。
