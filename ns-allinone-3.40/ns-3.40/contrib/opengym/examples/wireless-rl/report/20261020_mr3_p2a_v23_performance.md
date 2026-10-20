# MR3 P2A V23 性能剖析与短容量

本轮已闭合：性能剖析、等价map打包优化和新冻结短容量均完成。固定1/4env共30个8步回合、240次尝试全部独立验证通过，73个短活动保存身份已gone。**继续保留二维采样路线，但下一步先检查完整时长任务行为，再决定训练投入；P2A仍未完成。** 工程最终余额7931.3319463873982秒；完整事实和下一AI操作边界见下文“短容量实际结果与后续路线”。

用户在V22闭合后答复“按你的想法继续”，授权推进已提出的性能剖析/提速路线；本次[范围记录](assets/20261020_mr3_p2a_v23_performance/scope_acceptance_v1.json)将执行限定为一次新短profile、基于测量的等价优化，以及一次新冻结的短1/4env容量。V22旧FAIL、无实际四环境、仅前缀验证及原件不变；本轮不重跑旧run、不训练、不消费pilot/final-only、不启动原生/gateway或扩额。

入场43261.8239849376018/52000，余8738.1760150623982秒。本轮分别最多600秒profile及1800秒short activity，二者总预约2400秒，最坏仍余6338.1760150623982；每项独立审计、性能数据消费者和外部尾均计入自身真实engineering区间union，nested不重复收费。纯stub/CPU准备与封存不提供正式或原生信用。

## 两次新活动的预声明

profile仅1env/open101/seed101，随机动作seed41，在真实前序mask上均匀choice、最多8次attempt/1EP；MR3Env max_steps=8，第8次真实外部截断并完成取消/result尾。显式cProfile仅此活动启用，worker/evaluator分别保存pstats，保留非零退出/异常；不得把受剖析开销影响的速率当无剖析容量，不把两进程等待或嵌套函数累计时间相加。profile全活动600秒：conformity60、独立review20、collection240、独立audit120、profile report40、external120为阶段最大预约；每阶段仍先留180秒合作清理尾及120秒external，时间不足SKIP/FAIL，不能用max1强行入场。

profile通过当轮源绑定/6条原件+3合成/独立review/完整本EP因果审计和真实关闭后，才按实测热点选择简单优化。任何真实安全、时钟、IPC或forced close问题均停止新增活动，不以capacity补profile失败。不做新的PPO或95%准入主张。

优化后short activity另freeze、clean commit/push及当轮符合性，1env与4env各跑固定open/rooms/corridors×101/103，每worker六EP、每EP最多8步，共最多30EP/240attempt；每env为三机器人。group1与group4分别400/800秒的collection窗口，另留audit300/external120及准入清理尾；总活动1800秒，sourcecheck/关闭超尾照实收费。global collection按实际collector启动+1200秒，两个组仍共享240计数和绝对活动截止，不让前组耗尽后组时间。预算窗口用尽正常关闭可继续后组，完整性保留FAIL；任何真实执行/安全异常全局停止，不重试、补cell或增加seed。

所有新活动只有当全预声明cell、动作/输入/tensor/奖励时间/关闭/source和verified覆盖通过才PASS；profile只给单场短工程剖析信用，short只给固定短容量描述，不将8步外部截断当300秒/95%任务或长期训练可靠性。原门限、频率、扫描/地图分辨率、随机流、received-only与独立truth评价保持。

## 准备状态

以下为活动启动前的准备快照；正式结果已追加于下文。当时尚未启动正式profile或新容量。剖析helper的12项dummy/stub CPU、Supervisor profile开关12项和worker/helper组合29项已通过，完整命令/源前后SHA/wait/console见assets checks；重复覆盖不累计独立项。预算/短规范审计和活动末账CPU准备完成后再freeze。具体实测、优化依据、正式结果与精确末账随后追加。

准备检查已完成：短规格/原审计组合34项与活动末账10项CPU通过，分别真实37.892244021/.653239656秒；支持正常提前终态不补样、错误停止、独立group窗口和raw/verified区分。所有检查源稳定，见[CPU清单](assets/20261020_mr3_p2a_v23_performance/cpu_preparation_index_v1.json)。本轮未改原_duration谓词、原频率/奖励/路径/真值边界；此处不预报正式PASS。


## 剖析实际闭合与优化依据

profile冻结`caddd853ab8884b3e2fd1018069af2fdc139d3e8`clean/pushed前检后执行，主outer真实rc0/69.60772768秒，外部final rc0/.53091343秒；完整活动PASS，8attempt/8return/8action与return verified，真实第8步external_sampler_limit。无重试/补样/模型。原native六条/三合成与独立review通过，profile只给单场短工程信用。

worker main profile总self45.593059415秒；_known_line112491calls自身12.0495秒，update_maps累计18.5024秒，build_snapshot累计15.4901秒，OccupancyGrid.data setter333calls累计9.9811秒，两逐元素genexpr各约955万次。evaluator main44.3843秒中43.0804秒为poll等待。以上函数累计/进程区间重叠，不能相加作互斥占比；cProfile仅包main入口，module初始导入及主outer还包括其他阶段。见[性能消费者原件](assets/20261020_mr3_p2a_v23_performance/profile_closed/closed_execution/aux/profile_summary.json)。

本轮优先消除实测ROS map setter重复Python校验：merge_maps/navigation已验证[-1,100]的int16输出转int8 bytes与stdlib array('b')；worker int8本机map同样独占复制打包，其他dtype保留原list分支；restore_message仅OccupancyGrid.data、exact list且每项exact int/bool进入array fastpath，OverflowError回原setter，其他Python类型/其他消息递归保持。原几何/栅格融合、数据/shape/旋转/范围错误、频率/随机流/独立评价/received年龄及payload/digest不变。_known_line与原候选构造源码保持字节，未改观察/动作/门限或放宽旧原件准入。

merge最终30项CPU通过，另独立改前源码×新源码32次小图全消息字段、signed data bytes与双边CDR roundtrip等价；局部100次setter中位旧48.175335ms、新.323835ms，只反映这段打包，不代表整步/训练倍数。restore/information/merge/proxy信息组合102项CPU通过（真实3.810323824秒）；worker打包19项通过（真实2.680710161秒）。精确回执在checks/map_packing_cpu_v2、restore_packing_cpu_v1、worker_packing_cpu_v3。首次merge fixture假设未改消息反复CDR全bytes固定，受未初始化padding影响失败，v1保留；worker v2误将wire反序列化直接等于原Python .05高精度值，原ROS float32同样量化，2fail保留。最终比较原新完整字段、数据bytes和双边CDR往返，并未给CDR padding或float32精度作新资格豁免。

profile主+external两个不重叠真实outer union **70.13864111秒**，累计 **43331.9626260476018/52000**，余 **8668.0373739523982**；14个保存身份均已gone。52份/2,678,544 bytes完整原件已封存并全成员SHA验证，原件前后不变，见[profile manifest](assets/20261020_mr3_p2a_v23_performance/profile_closed/archive_manifest_v1.json)和[中账](assets/20261020_mr3_p2a_v23_performance/profile_metadata/engineering_accounting_v1.json)。CPU封存不重放正式consumer；pilot/final-only不动。

profile收口时，下一次short_capacity已按本轮授权预声明：优化后另冻结、无cProfile、group1/4固定短矩阵，最多240attempt/1800秒，实际结果随后追加；不是训练或300秒任务验证。


## 短容量实际结果与后续路线

short冻结`2e8fcac9439a1a53e3913e45abccdc0b6645825d`，当时main=origin/main、clean，110份绑定源码与plan均通过入场/末端校验；无cProfile。六条native历史输入与三合成的当轮符合性、独立review及全部短矩阵独立因果审计均PASS。其信用仍限保存输入的接口符合性与本轮二维执行，不提供新原生资格。

| 采集组 | 实际短回合 | attempt/return/verified return | 含reset/close墙秒 | 原始及verified返回速率（步/墙秒） |
| --- | ---: | ---: | ---: | ---: |
| 1env | 6 | 48/48/48 | 199.459093428 | 0.24065084812654514 |
| 4env | 24 | 192/192/192 | 314.375271233 | 0.6107350595578452（四环境合计） |

每worker固定open/rooms/corridors×101/103、每env三机器人；动作RNG base41，各组env_id使用41+1000003×env_id并跨本worker六回合连续使用；240个global ticket连续唯一，240个动作及uniform抽样、270份actor记录和240个返回全部验证。30回合均在第8次真实external_sampler_limit截断并完成正常取消/result/关闭尾，0step_error、无补样/重试。单组速率包含该组启动、重置、关闭，不包含之后的独立审计；全主活动含符合性、全部采集/审计及源核验735.849491694秒，不能拿受剖析profile或不同长回合V22作整步提速倍数对照。

真实阶段wait：conformity12.799853446秒、review.869791539秒、collection514.334642721秒、audit206.482445868秒，均rc0且未超各自预声明时限。独立审计读取真实保存输入并复核，不用producer PASS替代；见[原审计摘要](assets/20261020_mr3_p2a_v23_performance/short_closed/closed_execution/aux/independent_audit.json)与[活动结果](assets/20261020_mr3_p2a_v23_performance/short_closed/closed_execution/aux/activity_result.json)。

主活动闭合后，只对预先指定的两run共有open101/group1/worker0的reset+8return比较已验证tensor_proofs（dtype/shape/原始byte SHA）、动作和reward/dt/physical_dt/终态/reason：9行逐项一致。只读取已有证明与trace记录，不重编码actor或创建World；不能据此证明所有输入通用等价、连续动力学或训练收益。该工程消费者实际.337749651秒，结果见[有限前缀对照](assets/20261020_mr3_p2a_v23_performance/short_closed/closed_execution/aux/mr3_proxy2d_v23_pair_v1.json)。原新map CPU字段/data bytes/双边CDR证据与原错误门仍需一并理解。

外部final实际.51818622秒，连同main与有限对照三个outer区间union **736.705427565秒**；profile另70.13864111，本轮合计 **806.844068675秒**。累计 **44068.6680536126018/52000**、余 **7931.3319463873982**。嵌套阶段/四worker并行区间不重复计费；外部进程真实wait后的73个保存PID/start均gone（同PID不同start不混淆，僵尸视为仍在），无不可读项；见[最终账](assets/20261020_mr3_p2a_v23_performance/short_metadata/engineering_accounting_v1.json)及[身份核对](assets/20261020_mr3_p2a_v23_performance/short_metadata/saved_process_absence_v1.json)。pilot余1870决策/2905.9547395464029秒、三场final-only401/402/403均未动；policy/GPU/optimizer全0。

598份/16,310,889 bytes原件完整封存，单分片13,206,468 bytes，SHA256 `791a6116237973276af8caf724b809bddf4e13e370fa2eda9910f73c1115da45`；16份辅助原件复制亦核字节，原件封存前后不变。见[manifest](assets/20261020_mr3_p2a_v23_performance/short_closed/archive_manifest_v1.json)。封存和账目静态核查为CPU归档，不重复执行正式审计/模拟，不提供新资格。

给下一位AI的操作顺序：

1. 先读本节、最终账和评估交接顶部；两次V23活动均已关闭，不要复用输出、重跑矩阵或再次请求已授权常规修复批准。当前生产源码保持short冻结的110份绑定字节，后续报告提交不是另一次正式资格freeze。旧V21/V22等FAIL保留。
2. 用源码和本轮摘要具体化一次后续**完整时长行为检查**的范围，先回答实际移动/停止/重置、地图质量、合法候选、停滞/安全终态和随地图增长的每步成本；必须保持三机/received-only/原95%任务与真值隔离。8秒短回合不回答300秒任务或学习效果；随机动作未达95%也不能单独否定RL可学性。
3. 先给出固定场景/seed、回合与attempt总限、全活动墙限、审计/关闭预约、计费归属和失败即停规则。新增正式活动和二维训练范围需先具体记录并依用户实际授权执行，不能把本轮容量PASS解释为批准大训练或未接受的500k/72h。
4. 当前profile的_known_line仍是热点，本轮未改其原候选源码；不要为了速度绕过native纯构造字节门、降低分辨率/频率、加入truth/手工探索或猴子补丁。仅在新测量证明有必要时继续等价优化，不为增加工程PASS而重复矩阵。
5. 完整任务行为和可负担吞吐成立后，再提出独立二维最小学习试验，比较未训练策略和学习趋势并保留所有失败；训练额度、原生迁移/必要微调及正式95%验收各自独立。现有完整原生资格20100秒预约大于余7931.33秒；不得启动旧矩阵、原生PPO、gateway或自行扩52000。P2A出口保持未完成。

最终[静态核查](assets/20261020_mr3_p2a_v23_performance/closed_static_result_v1.json)通过：原件/封存/辅助copies字节、110绑定源、87保存身份与账目、461相对链接和历史记录均一致，CPU真实1.499108469秒，无新模拟或正式重放。
