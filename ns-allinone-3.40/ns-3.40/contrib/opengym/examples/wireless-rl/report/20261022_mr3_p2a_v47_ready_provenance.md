# MR3 P2A V47：启动就绪的两流来源诊断

## 实际闭合：两流描述诊断PASS，启动根因未被完整定位

执行freeze `deb2b5a8d46ab6ec9cd6a3eb897c8ff0bf75ba0c`，原证据freeze仍为V45 `cace46e08e53b7e89a434e23721db85ac993f6f5`。本活动实际wait/reap rc0，固定两流共384380343B完整SHA/bytes与V45库存一致，前后及独立复核lstat稳定；无新World/native/model/optimizer或数学重放。提取/来源/费用/关闭PASS不覆盖V45 startup/cleanup/reset FAIL，也不提供12EP/30角色资格、学习或最终任务信用。P2A未完成。

| 完整派生计数 | 实际结果 | 解释边界 |
|---|---|---|
| recorder | 35926行/0解析错误；configuration1、odom17962、tf17962、ready1 | 第350行ready事件clock2.58秒；所有已记录identity_match/GID_stable均True，未见false |
| motion | 122485行/0解析错误；reach_decision12723 | 每机4241决策记录，started=False、allow=False；不是任务release或策略样本 |
| motion ready | 每机False3050、True1191；False→True169、True→False169 | 生产者决策时的ready变化；不是worker Bool接收历史 |
| 首invalid ingress | motion第79596行，sim82.4秒，tb3；calibration publication stream gap/regression | 这是已记录的首条invalid ingress，不能倒推为37.92秒前启动阻塞原因 |
| invalid原因 | calibration publication gap/regression1363行；raw source cadence gap/regression2723行 | 4086条接收拒绝记录；标签本身未定位producer、transport或consumer哪层根因 |
| reach_model_failure | 9252条 | 可能重复记录已锁定故障，不能写成9252次独立首故障 |
| 选择范围 | 14357候选、实际200、省略14157；每流另有有界tail/首末例 | 完整计数保留，选段不代表全部时序因果窗口；message不输出、raw_json仅SHA/bytes |

结合V46 adapter在37.92秒发布initial-ready及本次recorder在2.58秒记录ready，只能确认各生产者的记录。worker当时monitor/initial-input/motion/recorder四项实际收到的bool与合取状态仍为NOT_RECORDED。82.4秒晚期故障不能倒因成37.92秒以前原因；也不能凭motion出现True即宣称worker启动本应成功。原400/420秒守卫、序列/源龄/健康和资格门均保持。

### 费用、来源和关闭

完整parent实际wait28.889315675秒，inner28.566096096秒已包含不叠加；工程累计55747.0395659926018/75000、余19252.9604340073982。pilot/validation各新增0，原1870/2905.9547395464029与final-only401/402/403额度未动。

[独立闭合review](assets/20261022_mr3_p2a_v47_ready_provenance/independent_closed_review_v1.json)PASS/review_errors=[]：78项scope源＋scope本身共79 outer绑定before/after/current/Git相等；6项解释来源（self、固定V46 helper、V45库存、recorder、motion、runtime）匹配。两输入与V45库存SHA/bytes及当前lstat一致，复核未重读raw或运行新consumer。driver/wrapper/extractor三保存PID/start均freshgone（Z仍计存在），实际argv/时间包含关系及费用相符。

[无损库存](assets/20261022_mr3_p2a_v47_ready_provenance/closed_inventory_v1.json)与[canonical副本](assets/20261022_mr3_p2a_v47_ready_provenance/closed_execution)保留5份派生成果/314747B，逐字SHA/bytes/stat一致，纯包装不重算科学结果或费用；不覆盖原source/scope/CPU/回执或原V45失败。本活动无新科学资格，独立review PASS只认可元数据/来源/费用/关闭一致性。

### 下一步

优先增加真实worker四ready及其接收/合取转变的有限日志，在startup等待时及时传播已经发生的硬健康故障；分清初始未就绪和82.4秒后模型失效，不再等待到400秒才只得到总超时。随后依据必要实际序列/来源证据定位producer发布、传输/队列与consumer接收时序的根因，保持连续性/源龄和真实物理门；不以跳序、忽略错误、提高守卫或筛掉失败来取得资格。

[V48禁用CPU候选](20261022_mr3_p2a_v48_support_cpu.md)有各自人工范围，不能据此代替本次因果缺口、证明新native或承诺PPO已可行。完整继任scope须据实测成本重订，原20100预约仍大于当前余额；用户自主完成P2A授权保持，P2B/gateway未开始。

## 唯一实际命令

cwd=canonical wireless-rl：

```text
rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 -B -m report.assets.20261022_mr3_p2a_v47_ready_provenance.run_forensic_v1 --freeze deb2b5a8d46ab6ec9cd6a3eb897c8ff0bf75ba0c
```

## 运行前预声明（历史快照）

2026-10-22预声明。[V46](20261022_mr3_p2a_v46_startup_diagnosis.md)已证adapter发布一次initial-input ready（37.92秒）、末三条记录状态新鲜，但worker当时四项ready未保存；原停止CLI全日志0匹配，原V45 FAIL保持。本次继续一次有限描述提取，不重跑活动或裁定科学资格。

[scope](assets/20261022_mr3_p2a_v47_ready_provenance/scope_v1.json)固定读取同一已关闭failedrooms回合的`driver_odometry_receipts.jsonl`（71649012B）与`motion_safety.jsonl`（312731331B），共384380343B；完整SHA/bytes须逐项等于V45库存，前后stat与source必须稳定。总输入512MiB、单行4MiB、输出2MiB，选择200条、每流尾20条；完整事件/标志/故障计数保留，省略明确标识。不读取map/information大流、不重放数学或物理、不启动World/模型/optimizer。

[提取器](assets/20261022_mr3_p2a_v47_ready_provenance/closed_ready_extract_v1.py)统计recorder ready事件、其前后identity/GID标志及首末例；motion按robot统计ready/started/allow、ready变化、decision reason/tracker fault及invalid事件。`message`不输出，`raw_json`仅SHA/字节；worker实际收到哪些ready回调仍是`NOT_RECORDED`。无效schema/epoch/JSON保持有界错误，存在错误时不能由事件0计数推断缺席；valid-schema计数与后续payload错误不是互斥行数分区。

10项纯内存自检已实际PASS、rc0/reap，child0.118299942秒，两个绑定源前后相同，原件读取0、工程费0。[实际wait](assets/20261022_mr3_p2a_v47_ready_provenance/checks/self_check_cpu_v1/actual_wait.json)、[console](assets/20261022_mr3_p2a_v47_ready_provenance/checks/self_check_cpu_v1/console.log)与[测试源码恢复](assets/20261022_mr3_p2a_v47_ready_provenance/checks/self_check_cpu_v1/source_recovery_v1.json)保留。78项outer绑定含全部learner import链、解释ROS源、固定V46 helper、两新脚本、CPU回执/恢复与原库存；scope本身另纳outer wait绑定。人工准备不是已消费原件的结果。

工程入场55718.1502503176018/75000、余19281.8497496823982；本次预约300秒（完整主parent240＋外尾60）。240是实际wait后的PASS费用门，不是未实现的hard-kill承诺；已提交工作始终实际wait/reap，超额仍完整计费并判FAIL，inner不叠加。保留原件/部分输出，不补读/重试旧活动。pilot/final额度及95%/质量/参与/接触/全部安全门保持。

本实现、scope及必要准备新commit/push后，从canonical wireless-rl执行一次：

```text
rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 -B -m report.assets.20261022_mr3_p2a_v47_ready_provenance.run_forensic_v1 --freeze EXACT40
```

[完整parent执行器](assets/20261022_mr3_p2a_v47_ready_provenance/run_forensic_v1.py)先核current/Git/scope一致，独占输出并核两输入库存字节；结束后需外部source/PID/start/费用复核。依据实际记录决定启动/清理修复及必要可观测性，不能凭推测加超时或隐去身份/安全失败。[V48人工提速候选](20261022_mr3_p2a_v48_support_cpu.md)仍禁用；任何接入须相关完整CPU及新冻结资格。P2A未完成，P2B/gateway未开始，用户自主持续授权有效。
