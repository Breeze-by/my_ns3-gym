# MR3 P2A V38：协议定点法证、负样本审计与证书恒等优化CPU

2026-10-22闭合：V37整体短probe FAIL保留；工程累计48259.9538193466018/52000，余3740.0461806533982。P2A未完成，75000待明确批准，pilot/final-only保持。此次没有新World/回合/PPO计划。

V37已审计的122actor/366次机器人起点接图全部接受，仍保留原tb3含点格拒绝。这解决了已采样起点问题，不能把后续corridors54秒的navigation_failure改判为成功。现有test_mr3_protocol已包含全局FIFO/同机器人cancel双回执导致旧expiry不变而延后交付的人工反例，以及及时heartbeat正对照。先用一次固定原件法证识别本次真实链路，不刷新TTL、不改FIFO/频率/失败判据、不重试V37。

法证仅单次解码V37规范corridors101协议日志（23618字节，SHA506e4e491f1a1993b9481f79ef09b1080efdb5de94a7faa5b5906ec69f4ee3e5），最多10000行/8,000,000字节。固定epoch proxy2d_w2_e1_f96a1433；抽52.1–54.3闭窗的全部可靠交付、4个固定goal histories、54.1前每stream/source末交付及首个protocol_failure。保留worker整数clock_ns和envelope各source/generated/received时间，单独算已观测交付延迟；未发现记录不等于未发送，不重建未存队列。新推送freeze下最多30秒main+5cleanup、15external、10buffer，总60工程秒；只消费协议，不读actor/map/scan/真值，不运行仿真或原库重放。

独立CPU工作是禁用证书内核候选：用精确closed segment-AABB到闭格的距离下界，剪去不可能降低当前capped minimum的四角投影；zero-length segment复用point距离。仍计所有原选定非free格，保持完整证书dict/所有计数及阈值、不近似浮点、不删anchor或安全门。先做人工阈值±1e-30、全字典字节等价和独立piecewise oracle；固定小微基准只报本地人工成本，不能当World吞吐。候选不接生产，CPU工程费用0。

另需区分PPO采集器的负样本资格与后续native custody严格门。任何调整训练审计而保留最终95%与物理安全门的方案都先记为PROPOSED_NOT_APPROVED，不能借此直接PPO或继承旧资格。完整原生+minimum仍需20100工程预约，现余额不够。


人工CPU160项通过（候选完整证书/独立oracle与既有protocol共148；协议抽取器12），各轮源码before/after稳定，工程增量0。固定128-call微基准两个相反顺序下，reference32call约.460/.456秒、candidate32call约.168/.168秒，仅是这两组人工kernel输入，不能据此声称World或训练提速。候选仍禁用，生产seed_certificate原字节保持。见[CPU index](assets/20261022_mr3_p2a_v38_protocol_cpu/checks/index_v1.json)。

[负回合审计评估](assets/20261022_mr3_p2a_v38_protocol_cpu/policy_negative_audit_review_v1.md)确认：二维随机short全PASS不是native资格前置门；当前可在预算批准后按现规则做native，但带dispatcher failure的回合会被完整protocol/custody审计拒绝。先保留现门，训练专用新审计版本只为待审提案。不能因随机probe FAIL而无止境改执行语义。

法证范围/入口/源和原件字节见[事前scope](assets/20261022_mr3_p2a_v38_protocol_cpu/scope_acceptance_v1.json)；该scope已在下述冻结执行一次并闭合，不重试。

## 固定协议法证闭合

冻结 `a44e1b844678ece45cfd377ea43e7ed65901cce3` 已先推送。单次有界解析935行/336574解码字节，固定规则保留102行（原行、SHA、JSON及索引），输入/源字节保持；main、外部observer及fresh absence全部PASS。只是提取/来源/关闭PASS，不修改V37原FAIL，也不是队列重放、native或训练资格。

固定tb3新goal53的实际代理记录：

| 记录行 | 事件 | 生成/发出时刻 | 交付/观察时刻 |
| ---: | --- | ---: | ---: |
| 896 | dispatcher send_goal；created52.1、expires/lease54.1 | 53.3 | 53.3 |
| 902 | command send_goal到endpoint | 53.3 | 53.9 |
| 904 | protocol_failure goal_lease_expired | 54.1 | 54.1 |
| 907 | heartbeat | 53.4 | 54.1 |
| 916 | endpoint accept回执 | 53.9 | 54.5 |
| 935 | CANCELED真实terminal | 55.3 | 55.3 |

首个已记录的新goal续租在截止前生成，却在54.1原截止时刻、failure之后才交付；接受回执更晚。不能把本次错误说成未发送heartbeat或KEEP漏续租，也不能刷新原expires来改判。已证实的是交付延迟和既定失效次序；完整未保存队列及每个队首阻塞原因未重建，全局FIFO/cancel双回执解释与源码/人工反例一致，不能假装已完整重放证明。[独立派生记录复核](assets/20261022_mr3_p2a_v38_protocol_cpu/independent_closed_review_v1.json)核每条保留原行SHA/JSON/索引和时间差，不再次解压原流。

[原件清单](assets/20261022_mr3_p2a_v38_protocol_cpu/closed_inventory_v1.json)：6副本/214764字节；[末账](assets/20261022_mr3_p2a_v38_protocol_cpu/closed_metadata_v1.json)：main .220363751 + final .094939404 = union `.315303155`工程秒，完整端点 `.509434203<60`，5保存身份fresh gone。累计 `48259.9538193466018/52000`、余 `3740.0461806533982`；pilot/final-only保持。

[协议时间线与因果边界独立复核](assets/20261022_mr3_p2a_v38_protocol_cpu/protocol_findings_review_v1.md)保留原行号和新旧goal完整身份；仅阅读派生JSON，无新增原件解析。

## 后续决定

继续P2A仍有价值：点接图已接生产并在已采样122actor全通过，剩下需要真实训练/原生证据。停止把二维uniform任务全PASS当作未声明的新前置；不再为同类合法负终态反复修改FIFO、TTL、reward或任务门。当前严格native路线本身可在预算批准后推进，训练负回合新审计若需采用则另行明确批准、实现和新冻结，原资格/最终95%/physical安全门保持。

下一项可直接推进的是已验证的精确证书恒等提速生产化及相关CPU检查，保持全部证书字段/阈值/输入来源/候选/掩码不变，不为此再开二维World活动。随后新冻结原生资格→minimum→pilot→final；完整资格+minimum预约仍20100秒，现有余额不足。已明确请求累计75000墙秒，尚未收到答复；若批准，按当前末账有26740.0461806533982秒，预约20100后余6640.0461806533982秒，原pilot1870决策/2905.9547395464029秒与三场final-only额度不变。
