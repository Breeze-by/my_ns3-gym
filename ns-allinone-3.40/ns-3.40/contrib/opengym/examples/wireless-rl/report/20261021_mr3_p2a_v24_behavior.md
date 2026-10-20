# MR3 P2A V24 完整时长二维行为诊断

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
