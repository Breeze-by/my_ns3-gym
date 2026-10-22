# MR3 P2A V39：精确证书计算提速

2026-10-22，生产恒等优化与人工CPU验证闭合；P2A未完成。工程仍为48259.9538193466018/52000，余3740.0461806533982；75000累计额度和训练负回合新审计仍未批准，pilot/final-only保持。

V37 profile显示主要时间花在精确segment证书，V38禁用候选已通过完整字典恒等与独立oracle检查。本次把相同数学捷径接入生产：闭segment的AABB是它的超集，因此AABB到闭格的距离是segment距离下界；只有该下界严格小于当前capped minimum时才计算完整投影。零长度segment与point距离相等。继续遍历并计数所有原选定非free格，逐格更新point minimum，所有Fraction算术、边界、.29米门及public字段保持。

本次不改观测/候选/掩码/奖励/执行语义、协议FIFO/TTL、训练审计或默认模式。使用[a44冻结旧源码](assets/20261022_mr3_p2a_v39_certificate_kernel/frozen_reference_v1.py)作真实基线，SHA256 `99bd4fdda76a5974d394a2e40177e7cbd5fb12308258c2ee096c5232c568e3cb`；避免用已经优化的生产函数与自身比较。

[本次scope](assets/20261022_mr3_p2a_v39_certificate_kernel/scope_v1.json)只含人工CPU测试及有限微基准，不读原始actor/map/scan/protocol输入，不运行World/回合/学习，工程增量0。CPU结果不提供native、容量、95%或训练资格；旧V37 FAIL保持，随机二维全PASS不是新native前置。

下一步仍是预算批准后新冻结完整native资格→minimum→pilot→final-only；资格与minimum总预约20100工程秒，当前余额不足。负终态训练新审计若拟采用，须另行审阅和新版本，不能由提速继承许可。

## 验证与结果

| 人工CPU组 | 最终结果 | 范围 |
| --- | ---: | --- |
| geometry_cpu_v1 | 354 PASS | 原281项几何/观测/导航＋73项冻结基线、全字段/JSON、独立oracle与快捷分支检查 |
| learner_cpu_v1 | 71 PASS | legacy/v2/point兼容及完整资格、训练准入、policy-chain人工测试 |
| reader_cpu_v2 | 12 PASS | system ROS解释器下的独立native输入读者人工用例 |
| snapshot_cpu_v1 | 9 PASS | ns3gym真实private validator、encoder及原始validator；新增完整可达点接图与摘要/重封攻击 |

最终446项，不重复计首轮reader的12个用例；reader_cpu_v1原失败与源快照完整保留，其12个读者用例通过后，exact_snapshot因系统Python无torch导入失败。只修runner的解释器路由：native读者继续system ROS，快照验证用既有ns3gym；生产与测试内容均未因该错误修改。所有6轮（含微基准与失败）source before/after稳定。[CPU索引](assets/20261022_mr3_p2a_v39_certificate_kernel/checks/index_v1.json)与[126源码版本恢复表](assets/20261022_mr3_p2a_v39_certificate_kernel/checks/source_recovery_index_v1.json)覆盖125路径；唯一双版本为runner环境路由，旧版本字节保存，未改写失败回执。

新增完整人工快照使tb3原seed_cell_body_clearance拒绝、point attachment接受且有真实可达候选，经实际encoder与不可变原validator通过。单独重封whole digest不能隐藏候选摘要变化；结构矛盾由encoder拒绝。完全重封且结构合法的几何伪造不由private validator独立证明，它由相同人工received输入的独立actor重建拒绝；不夸大任何单层校验的职责。

固定微基准128次完整public segment证书，reference/production与production/reference两个顺序各32call：旧源码463339238/466320676ns，生产171110671/170599645ns，合计约2.72倍。四批完整输出SHA均为`5ccf7b151b11626dcc373bf467d10bc1ef1a534f34452ddb178c21c92d92294f`。仅两组人工输入，不声称World/回合/训练速度；详见[原结果](assets/20261022_mr3_p2a_v39_certificate_kernel/checks/microbenchmark_result_v1.json)。

生产只改`_segment_measurements`内部计算，保留所有公有返回字段、计数、窗口遍历与拒绝条件。point helper SHA仍`e55b776c3ec088fe51dfa76ff204b4b135138038502fabc6af01717ed75efc83`；geometry依赖与ENV合同字节保持，ENV SHA仍`baffbf1bffc7fadff80105ec5c5dce3a04c694ce7e7a8f72ca6620d8a7c13a1a`。不能从同输出恒等继承旧原生资格，后续新plan必须绑定优化源码并进行完整新冻结验证。

[下一原生准备清单](assets/20261022_mr3_p2a_v39_certificate_kernel/next_native_preparation_v1.md)记录一个易漏项：`build_plan`只建矩阵，必须另行密封三项`policy_stages` registry；若75000获批，还须修正plan预算依据中旧52000字面并以新末账预约全部20100秒。当前没有新World、optimizer或工程费用；P2A仍未完成。

[独立静态复核](assets/20261022_mr3_p2a_v39_certificate_kernel/independent_review_v1.json)通过：6轮真实回执、console摘要、117个Git原件与9个源码快照（126版本）、生产单函数AST及精确数学证明全部一致；只核人工CPU派生产物/源码身份，没有再次运行测试、World或消费实际原件。
