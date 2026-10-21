# MR3 P2A V26 实际场景代理地图质量几何审计

本轮已闭合：固定三场的几何消费者、源绑定与收尾均PASS，**三场条件上界都高于原.20门，本检查没有排除任务，也没有证明可达。** 不据人工厚box或本次宽松上界判定RL无解，不据此直接投入PPO。下一步转向V25已复现的端点格线与单次误差覆盖问题，准备仅传感器输入的版本化建图CPU候选；不继续收紧静态上界来代替任务证据。工程实费4.886817531秒，最新余6554.5762973333982秒，P2A未完成。

用户在V25收口后指示“继续”。本轮落实[V25交接](20261021_mr3_p2a_v25_cpu.md)：对原open、rooms、corridors三开发场景做一次有界只读几何诊断，量化端点表面表示与原occupied体积评价的相容性。先完成独立数学复核和人工CPU检查，clean提交推送后绑定新冻结执行；不重新采集V24，也不启动PPO。

入场源码`6e0b7316ac1683bff139311d960f3f58b3f7b376`、工作树干净。工程累计45440.5368851356018/52000，余6559.4631148643982秒，见[V24权威末账v2](assets/20261021_mr3_p2a_v24_behavior/closed_metadata_v2/engineering_accounting_v1.json)；V25没有新增工程费用。pilot余1870决策/2905.9547395464029秒和三场final-only401/402/403不动。

## 固定范围与计费

一次消费者固定读取三份原SDF与三份原任务合同，原.05m格、完整ROI/occupied分母与质量门保持；不选择seed、不调用World、Node、actor、环境步进或历史actor/奖励重放。它只在隔离评价侧输出计数/哈希/条件，不将真值或诊断图送入机器人输入。新工具没有worker/actor调用链。

全活动最多120工程墙秒，消费者最多90秒，另预留受控中断/必要kill/实际wait与核验收尾；主消费者及必要外尾按实际outer区间union计费，不重加嵌套子进程。任何源/输入不一致、不支持几何、异常或超时停止本次，不追加消费者、补场或重试。人工小几何和源码/归档检查是CPU准备，不提供新任务或原生资格。当前余额足够预约，最坏仍余6439.4631148643982秒；不扩52000，不借pilot/final-only。

## 方法与结论边界

将每个box的四条边与原格的闭cell求交，包含格线两侧、角点和保守容差；所有表面union去重。保留外侧、被遮挡、重叠内部等不可观测表面，使支持集合更宽。以其与原truth occupied/ROI交集T除完整occupied格N，得到零量测/位姿误差、无近距裁剪且同格映射的静态表面端点表示的乐观IoU上包络。可能落在truth-free的表面格单列，不能强迫全部进入预测分母制造更低“上界”。

T/N低于原门只排除上述理想化表面模型；当前Gaussian量测与偏置编码器没有确定误差硬界，实际端点可能落在集合外，不能据此声称含噪任务不可能。T/N高于门也不证明95%/质量/参与/300秒或真实导航可达。原生SLAM/Nav2/18路接触及学习收益均不在本诊断信用内。

另列ROI-origin前面子界：只有整个原ROI严格位于面的背侧且留有容差时才排除该面，相等与不确定情况保留；原N不变。它额外假设传感器原点在原ROI内、实体外，当前proxy没有独立保证该条件；若数值没有收紧就如实报告，不将其替代主界或任务证据。

本轮先量化再决定是否需要新的逆传感器模型；不降低.20 IoU/.02 false-free门、不裁ROI、不以真值填充实体内部、不借几何图选择探索目标。生产mapper/evaluator/观测/候选/协议与已有失败保持，实际结果、准确费用及下一步随后追加。

## 准备结果

本节保留执行前状态；实际执行与最终余额以下文为准。

几何21项CPU通过（3.338148882秒）、守护10项mock通过（.286320784秒）、收尾元数据5项通过（.234118018秒），均actual wait/source stable。见[CPU清单](assets/20261021_mr3_p2a_v26_geometry/cpu_preparation_index_v1.json)与[预声明计划](assets/20261021_mr3_p2a_v26_geometry/predeclared_plan_v1.json)。前者没有执行三真实场景；后者绑定20份执行源、原SDF/合同、范围与wrapper。独立数学/源码复核确认条件上包络、来源绑定、固定system ROS模块与真实wait/失败保留口径；正式活动待clean冻结推送及前检。

[预冻结静态检查](assets/20261021_mr3_p2a_v26_geometry/preparation_static_result_v1.json)通过，CPU实际.683550509秒/source stable：20绑定、21/10/5回执与console、原有生产源码/三任务合同未变、476相对链接、log只追加与旧归档/备份分支保持。该检查只核源码/元数据，没有评价实际场景几何。

## 实际结果

冻结`89a1b0543c5445bb5815162ae4ef07f1f7c728c0`在main=origin/main且clean时通过前检（CPU .878233462秒），唯一consumer完成原三场；无重试、无seed采样，原14项source/资产字节稳定。以下为全部真实场景结果，见[原结果](assets/20261021_mr3_p2a_v26_geometry/closed_execution/guard/geometry_result.json)。

| 场景 | box数 | 原occupied格N | 表面包络中可能正确格T | 条件IoU上包络T/N | 不在该包络中的原occupied格 |
| --- | ---: | ---: | ---: | ---: | ---: |
| open | 8 | 5964 | 2328 | .3903420523 | 3636 |
| rooms | 14 | 6176 | 2992 | .4844559585 | 3184 |
| corridors | 8 | 5296 | 2720 | .5135951662 | 2576 |

三者均未低于原.20门，不能得出实际场景结构性不可能；它们包含外侧/遮挡面及格线相邻格，也不能得出可达。ROI-origin变体完全同值，只说明这项保守过滤未收紧本次结果，不是其原点假设已验证或第二份独立支持。N−T只是该条件模型下不在表面包络中的原格，不能称实际含噪模型的物理不可观测体积。

open的厚实体比薄墙占更多原occupied：两个1.2m方块各有92/576格落在其自身表面包络，旋转bar各176/646；rooms柜体各80/392，但许多.2m薄墙的自身表面包络约为其solid格的一半，corridors主要也是薄墙。它们解释宽松上界的差异；分障碍有重叠，不能相加替代全场union。可落在truth-free的表面支持格分别1060/1916/1732，只是可选支持，不是实际/必然误占，也不是V24的false-free；不得改用N+这些格作乐观IoU分母。

## 费用与完整闭合

主outer实际4.793615429秒，独立final元数据/源/身份核验.093202102秒，均rc0、actual wait/source stable。两区间不重叠，union **4.886817531秒**；首main启动至末final结束跨度6.183447779秒，小于120秒预约，内层guard/consumer不重复收费。累计 **45445.4237026666018/52000**，余 **6554.5762973333982秒**，见[权威末账](assets/20261021_mr3_p2a_v26_geometry/closed_metadata/engineering_accounting_v1.json)。pilot1870决策/2905.9547395464029秒、三场final-only401/402/403均未动。

[final原核验](assets/20261021_mr3_p2a_v26_geometry/closed_execution/final.json)通过；进一步fresh /proc核5个工程身份及2个CPU前检身份，全7原PID/start已gone，无不可读或僵尸，见[保存身份核对](assets/20261021_mr3_p2a_v26_geometry/closed_metadata/saved_process_absence_v1.json)。13份原控制/结果/console文件完整逐字节复制，原件未改，见[副本索引](assets/20261021_mr3_p2a_v26_geometry/evidence_copy_index_v1.json)；复制/末账CPU .093460805秒，不重算几何、不计新工程费。

本轮0World/Node/episode/ENV.step/actor/奖励重放/GPU/optimizer/native，只有一次预声明真实几何消费者。PASS只表示该条件计算、来源和关闭完成；没有95%/300秒、实际图质量、SLAM/Nav2/18路接触、策略学习或新完整资格。V24全部FAIL和543个原返回保持。

## 下一位AI的操作顺序

1. 读本轮结果和权威末账；不要重跑V26、给宽松几何上界附加任务资格，或重新启动V24。保留三机、原95%/300秒、全部质量门、received-only、租约/FIFO与原生准入。
2. 不再通过继续收紧静态上界积累PASS。针对V25已证明的量测缺陷，具体化最小sensor-only mapper-v2 CPU候选：命中恰落格线时只按ray与数值规则定格；用有界hit/free证据、未知态/迟滞取代最后一次直接覆盖。参数和更新规则在人工比较前固定，保留v1对照及全部失败，不猜实体厚度、不读truth选格或填内部。
3. 证据累计必须按真实新scan消费。现`_last_ray_cells`端点格相同即skip只适用于幂等写图；新scan同端点仍是新证据，同scan重复调用不能重复投票。至少核4面/旋转/角点、±量测误差、max-range不造hit、同scan hit/free冲突、重复scan幂等及一致free清除ghost；同时报告false-positive、false-free、accuracy与自由覆盖代价，不能只追IoU。
4. 常规CPU候选实现/验证已有授权，可直接推进。明确候选收益和代价后，再另立新范围/冻结做一次有界完整行为和长步成本检查；CPU、静态上界及局部计时都不能替代完整任务或直接解锁二维PPO。原生迁移/资格仍需自身条件与预算。
5. 工程余6554.5762973333982秒，原完整native资格20100秒预约仍不具备；pilot/final-only不动。P2A未完成，P2B/gateway未开始。

最终[闭合静态检查](assets/20261021_mr3_p2a_v26_geometry/closed_static_result_v1.json)通过（CPU .686888544秒/source stable，[真实回执](assets/20261021_mr3_p2a_v26_geometry/checks/closed_static_cpu_v1/actual_wait.json)）：13原件/副本字节、20冻结绑定和14消费者绑定、精确union与余额、7保存身份、505相对链接，以及运行源/旧证据/旧归档/备份不变和log只追加均核对；没有重算几何或新增任务信用。
