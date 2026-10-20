# MR3 P2A V24 完整时长二维行为诊断

本轮已FAIL闭合：544次尝试、543次真实返回、1次rooms执行错误导致三场全局停止，均未完成300秒任务。发现目标租约到期被迟到一个控制边界识别的接口缺陷；原租约/FIFO/失败保持，已完成27项CPU边界分类修复，尚无修复后正式重验。**目前不建议直接投入二维PPO；先收口该接口缺口，并处理长回合成本与代理任务可达性。** 最新工程余6559.4631148643982秒，pilot/final-only未动。下文先保留原预声明，实测结果及下一AI步骤在末节。

用户在V23结果后指示“继续执行吧”，续接完整时长任务行为检查。本次只做一次新的有界零训练诊断，固定三机器人与原300秒任务，核长回合的移动、目标执行、地图质量、候选/停滞和步耗时增长。V23的30个8步回合不提供本次长行为或策略资格；旧FAIL全部保留。

入场工程44068.6680536126018/52000，余7931.3319463873982秒；本次最多3600秒，最坏余4331.3319463873982。pilot余1870决策/2905.9547395464029秒及三场final-only401/402/403不动。具体授权解释和停止规则见[范围记录](assets/20261021_mr3_p2a_v24_behavior/scope_acceptance_v1.json)。

## 固定执行范围

三个代理环境并发，每env仍tb1/tb2/tb3：env0只做open101、env1只做rooms101、env2只做corridors101，各一回合，不是每env都跑三场。每EP最多300次ENV.step，全活动最多3EP/900attempt，失败尝试也收费计数。动作只在真实前序合法mask上均匀随机，独立流seed=41+1000003×env_id；不创建策略、GPU或optimizer。真实提前合格coverage或原300秒timeout终止；max_steps300外截断不能冒充任务完整终态。随机未达95%不能单独证明RL不可学。

采集独立窗口2100秒；当轮符合性60、独立review20、完整trace审计950、行为报告100秒为阶段上限，外部尾120及每阶段180秒合作清理先留后入场。阶段上限合计3230秒，余370秒处理源核验、清理和外尾；不足时压缩/跳过并保留FAIL，不强行入场。真实异常全局停止新步进、等待已发在途请求及所属进程真实退出，不补样、重试或换seed；达到墙限的未完成回合如实记录。

准备完成后先clean commit/push冻结，重新运行六条历史native保存输入与三合成的接口符合性及独立review，再允许唯一新采集。绑定完整当前执行/审计源码、场景/任务和本范围；原source-proof纯构造、_duration、95%/地图质量/参与/真值边界不变。source变动不拼冻结。

## 行为指标与结果解释

复用本轮trace、保存actor输入、private evaluator原请求/响应、protocol、backend和真实关闭原件；隔离system Python消费者按原评价/奖励规则复算，不向actor新增truth。输出每场最终覆盖/quality/participation与三机path/goals/contact、候选与合法动作、停滞及前中后段步耗时，明确raw/verified/未完成范围。完整工程证据PASS与proxy_task_success分别报告；任何二维结果仍没有原生SLAM/Nav2/DDS/18路接触或95%策略资格。

本轮不做训练、原生重试/迁移、完整旧矩阵、gateway或预算扩额。实测结果与精确union费用在活动关闭后追加，并更新评估交接、操作入口及共享log。

## 准备验证

首项61条组合CPU/stub/人工snapshot检查通过，真实80.466307479秒、源码稳定。含900人工返回与903 actor记录的长终态fixture及错误反例；不创建World或重放历史实验。回执见[准备检查](assets/20261021_mr3_p2a_v24_behavior/checks/activity_capacity_cpu_v1/actual_wait.json)，不计作新环境样本或工程实验。独立行为消费者仍在准备，正式活动尚未开始。

后补入场账/context一致性、报告跳过及pidfd异常所属子进程回收24项CPU通过（.723031392秒），独立行为消费者11项system ROS CPU通过（5.634405988秒、0skip），含真实ProxyReward小数组而无World/Node。完整回执均在本轮assets checks；重复覆盖不累计为独立总数。

已生成[本轮计划](assets/20261021_mr3_p2a_v24_behavior/full_behavior_plan_v1.json)，绑定112份源码/场景/范围；[预冻结静态检查](assets/20261021_mr3_p2a_v24_behavior/preparation_static_result_v1.json)通过（2.211512485秒），原纯actor/episode/_duration字节和460相对链接保持。完整[CPU准备清单](assets/20261021_mr3_p2a_v24_behavior/cpu_preparation_index_v1.json)包含各actual-wait与source SHA；正式执行待clean冻结推送及前检。

冻结前必要读者修正已通过12项system ROS CPU（5.522226466秒、0skip）：同clock内accept按实际观测边界计数，提前coverage必须实际关闭于300秒之前。执行器/actor/奖励/任务门未变；旧11CPU源码/回执与未执行pre_review计划均保留。当前计划已重建，最新[准备清单v2](assets/20261021_mr3_p2a_v24_behavior/cpu_preparation_index_v2.json)及[static v2](assets/20261021_mr3_p2a_v24_behavior/preparation_static_result_v2.json)替代v1的当前准备适用性，旧结果保留其原源码范围。

## 实际结果与继续判断

冻结`9b33cf9b6ab491fd5e3b15269adb30d43be1354c`通过clean/pushed前检，当轮符合性与独立review PASS；collector、完整接口审计与行为报告均FAIL，未超各phase时限、没有重试。544次动作及uniform抽样、546份actor记录和543次返回完成各自既定校验；因果失败保留为1次step_error，不产生训练资格。详见[活动结果](assets/20261021_mr3_p2a_v24_behavior/closed_run/closed_execution/aux/activity_result.json)、[原审计](assets/20261021_mr3_p2a_v24_behavior/closed_run/closed_execution/aux/independent_audit.json)和[行为报告](assets/20261021_mr3_p2a_v24_behavior/closed_run/closed_execution/aux/behavior_report.json)。

| 场景 | attempt/return/error | 最后实际任务秒 | 正确自由覆盖 | occupied IoU | 质量/参与 | 前/中/后段平均step墙秒 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| open101 | 205/205/0 | 205 | 86.2800% | .150593 | FAIL/PASS | 3.239/6.079/8.661 |
| rooms101 | 174/173/1 | 173 | 71.0143% | .136699 | FAIL/PASS | 5.195/4.410/11.553 |
| corridors101 | 165/165/0 | 165 | 42.1582% | .117160 | FAIL/PASS | 3.609/9.354/9.407 |

rooms抛出`masked action rejected by original dispatcher: stopped`后全局停止，另两场是因同组故障关闭，不是其任务已失败至300秒。三场均无完整任务终态、无95%成功；代理接触计数0，原生18流监测/动力学仍无信用。三机实际参与均通过，但最长全机无中心平移分别28/62/25仿真秒（允许旋转）。三场IoU均低原.20门；rooms false-free约.021859也超过.02门。没有降低质量门，随机未达标及未跑满本轮也不足以判断RL不可学。

collector实际1242.136169728秒、audit68.347750972秒、behavior report44.5844279秒；全主outer1370.575677101秒。已保存响应的独立评价/奖励复算全部一致，无replay error；这只验证已有数据，不补造终态或把全活动改为PASS。608份/31,996,063bytes原件全封存，单分片26,290,008bytes，SHA256 `db44fe8b530a2d4522511f0f5a8b6a3a7f9229ab637aa657fa4d0c68b32f6876`，13份aux copies及全成员字节通过；见[封存manifest](assets/20261021_mr3_p2a_v24_behavior/closed_run/archive_manifest_v1.json)。

有限故障提取只读本轮协议/trace，计入原工程预约（.743226624秒），无新World/actor/奖励重放。原件确认：tb3命令172的租约在173.1秒过期，接收ACK虽172.9秒生成，却173.5秒才交付；173.1秒最后返回仍非终态，下一步submit先tick才发现stopped。它不是60秒执行超时。该提取的[输入与结果](assets/20261021_mr3_p2a_v24_behavior/failure_diagnostic/mr3_proxy2d_v24_failure_extract.json)与exact脚本/outer已保留，证明真实租约失败与检测分类缺口分别存在。

最终费用union **1371.868831523秒**，累计 **45440.5368851356018/52000**，余 **6559.4631148643982**；权威[最终账v2](assets/20261021_mr3_p2a_v24_behavior/closed_metadata_v2/engineering_accounting_v1.json)含main、external和有限提取，nested/三worker并行不重加。原中账closed_metadata保留未含提取的18身份快照，最终[20保存身份核对](assets/20261021_mr3_p2a_v24_behavior/closed_metadata_v2/saved_process_absence_v1.json)全gone、0不可读/僵尸。pilot余1870决策/2905.9547395464029秒，final-only401/402/403未动。

## 下一位AI的操作顺序

本轮原完整活动已停止且全部闭合。`complete_declared_cells_per_worker=true`仅表示三个指定目录已有数据；`final_metrics`仅表示最后保存边界；错误文本中的“eight-step ceiling”是旧通用字符串，本轮实限300。均不能解释成完整任务PASS。故障在collection约1242秒触发，尚未耗尽2100秒窗口，不能归因为预算不足。

1. 先读权威末账v2和故障提取，检查当前worker的CPU修复状态。新修复在每20ms实际推进后先tick协议，再更新状态/查询隔离评价器，使真实lease/执行失败在当前物理区间终止并取消关闭；它不解决租约失败本身、不刷新pending目标原TTL。保留本次FAIL，不重开旧run或给旧样本补终态；当前修复源码与正式9b冻结不同。
2. 优先纯CPU检查pending GOAL切换保留原expiry、可靠FIFO/cadence及心跳/迟到ACK因果。复现本次173.1到期、173.5才接受的模式，分清策略可避免的任务失败与接口不一致。不得用延长2秒TTL/60秒执行界、跳队列/加真值/静默KEEP或手工探索兜底消除FAIL。
3. 再审代理模型与原质量门的相容性、导航停滞和计算热点。末端质量FAIL只属于中断前缀；须用可解释的几何/映射与候选证据判断95%/质量任务是否可达，不能凭随机失败否定学习，也不能降低IoU/false-free门。原纯候选源码保持，任何优化应先有测量和等价证据，不通过猴子补丁绕过source-proof。
4. 上述修复及模型/性能方案具体化后，才另拟一次新冻结的有界长回合闭合或二维最小学习方案，列清样本/更新/全活动费用和失败停止规则。不要自动加回合或重跑V24。当前三场末段每步8.7–11.6秒，不支持直接放大训练；CPU通过不提供新完整长行为或策略资格。
5. 工程尚余6559.4631148643982秒，原完整native资格预约20100仍不具备；pilot/final-only未动。原生迁移/正式95%验收和二维学习分别需各自资格与预算；P2A未完成、P2B及gateway未开始。

## 边界检测修复的CPU结果

当前生产worker仅在`world.advance()`后增加`dispatcher.tick(self.now)`，然后才更新接收状态和查询隔离终态。原2秒TTL、60秒执行期限、FIFO/5Hz回执与心跳、候选/mask、奖励和截止优先均不变；真实租约/执行故障在当前正时长物理区间返回，原取消/result尾仍排除于奖励端点。它不使过期目标重新有效，也不解决此前未到达目标的原因。

27项system ROS CPU/stub通过，真实2.911973945秒、source stable；包括实际原dispatcher/IdealTransport配人工20ms时钟、lease/60秒边界、API中间/末量子、迟到accept队列、真实取消/result尾及300秒优先。没有创建ProxyWorld、ROS Node或新episode。见[CPU原回执](assets/20261021_mr3_p2a_v24_behavior/checks/worker_boundary_cpu_v1/actual_wait.json)。未重跑V24、未给新源码正式或训练资格；旧冻结原件及FAIL保持。

闭合静态检查通过（CPU 1.898351381秒，source stable）：608原件及13份aux字节、额外故障提取副本、三outer精确union与20身份gone、544/543/1原FAIL、111份其余绑定源码不变、worker全模块AST仅新增推进后tick、489相对链接、log只追加及备份分支均核对。见[静态结果](assets/20261021_mr3_p2a_v24_behavior/closed_static_result_v1.json)和[真实回执](assets/20261021_mr3_p2a_v24_behavior/checks/closed_static_cpu_v1/actual_wait.json)；未重放正式消费者，不计新工程实验费。
