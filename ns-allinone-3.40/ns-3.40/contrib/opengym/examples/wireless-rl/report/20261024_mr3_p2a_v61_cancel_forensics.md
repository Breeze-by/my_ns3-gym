# MR3 P2A V61：固定取消窗口的有限原件取证预声明

V61 尚未读取原件流，也未取得取证、根因、原生资格或学习结果。canonical consumer 已封为 v4，最终 10 项人工 CPU 实际通过；本次执行冻结仍待 commit/push，当前工作区不能据 admitted=True 直接执行。P2A 未完成，当前 capacity=False，禁止自动进入 pilot/final。

## 前序事实与本轮目标

[V60](20261023_mr3_p2a_v60_reader_registration.md) 在证据执行冻结 `935b466bd076002afdfe161b55a508938de2a8b0` 下实际 FAIL，30 必要角色为 19 PASS / 1 FAIL / 10 SKIP。reset 的 tb2 首次取消存在真实停止界违反，另两例缺合格取消刺激/证据；两类问题分别保留，根因仍 UNKNOWN。V60 关闭提交 `1d016b318a1a7afefbec7ad4c3b395b1cd7fbe54` 已实际推送，工具 2130 真实返回 0。

本轮仅对固定五份已闭合原件提取两段取消窗口，区分原请求、guard 输出、native receive/store、实际电机/APPLIED 与 odometry；保留原行、原事件身份与各源时钟标签。描述完整性不等于因果解释，更不等于重裁 V60 的停止结论或取得完整 12 EP / 30 角色资格。

证据生成源为上述旧冻结 E；V61 consumer、解释源、spec、scope 及执行来源必须在新的执行冻结下封存，实际 `--freeze` 指向本次新 source commit。二者用途分开，不能将旧 E 冒称 V61 execution freeze，也不能用旧 CPU 对新修订源码授予执行信用。

## 固定输入、选择与上限

五个输入为既定 adapter、motion、tb2 drive、tb2 odometry 和 launch 流，均为 plain / identity，总原件字节数 `523777922`。原路径、逐文件完整 SHA/bytes 与关闭来源以本活动的 [extraction spec](assets/20261024_mr3_p2a_v61_cancel_forensics/extraction_spec_v1.json) 和 [scope](assets/20261024_mr3_p2a_v61_cancel_forensics/scope_v1.json) 最终封存字节为准。原件不改写、不删除。

固定 actor 为原 V60 reset worker1/episode002 的 tb2，episode/epoch 沿用原证据身份。主窗口为 `[42.6, 46.1]` sim-s，对照窗口为 `[54.6, 55.6]` sim-s；不同源时钟不伪装成同一 wall 顺序，对照成功不覆盖首次失败。命令、guard、APPLIED 等被选 actuation 的精确依赖未恢复时，必须保留不完整状态，不能仅凭 nested cmd_seq 宣称因果已核实。

| 资源项 | 本轮固定上限 |
| --- | --- |
| 完整 parent / consumer work | 660 / 480 wall-s |
| 总 encoded / decoded 输入 | 各 1 GiB |
| 单行 / 每文件行数 | 8 MiB / 2,000,000 行 |
| selected / 所选 raw 字节 | 12,000 条 / 24 MiB |
| 总输出 | 64 MiB |

输入完整消费、解析、SHA/bytes、稳定 stat、窗口边界与依赖恢复按最终 spec 检验；遇上限、解析错误或依赖缺失如实保留 partial/INCOMPLETE，不补读重裁旧活动。完整 parent 包含来源核验、实际等待与 owned 清理；nested 子等待不重复加费。不启动 World、训练或策略验证。

## canonical 源码与真实 CPU 记录

canonical 已完成两轮各 8 项人工 CPU：第一轮工具 36263 真实 rc0、`.712938518` wall-s；第二轮工具 78387 真实 rc0、`.655878763` wall-s。每轮 32 个来源前后稳定、两个保存 CPU 身份 fresh-gone，绑定字节可恢复。见[第一轮原证明](assets/20261024_mr3_p2a_v61_cancel_forensics/checks/artificial_cpu_v1/proof_v1.json)、[第一轮真实等待](assets/20261024_mr3_p2a_v61_cancel_forensics/checks/artificial_cpu_v1/actual_wait.json)、[第二轮原证明](assets/20261024_mr3_p2a_v61_cancel_forensics/checks/artificial_cpu_v2/proof_v1.json)及[第二轮真实等待](assets/20261024_mr3_p2a_v61_cancel_forensics/checks/artificial_cpu_v2/actual_wait.json)。这些检查只绑定旧 consumer `860b69…`，未读取五原件流；旧 8 项结果与快照继续保留。

最终 active consumer 为 [cancel_window_extract_v4.py](assets/20261024_mr3_p2a_v61_cancel_forensics/cancel_window_extract_v4.py)，`43207` B、SHA256 `293fd84735171ba977d826d920b6f22bf80a50e6f15671e2aa0f64e0aeb7dac0`。parent 的 CONSUMER 已指向 `_v4`，spec/scope 同步绑定，runtime 来源仍为 25 项。原 v3 作为 baseline 保留，旧两轮 8 项 CPU 的源码和证明未改。

本次修订针对窗口边界 actuation 的精确 command/guard/APPLIED 依赖：原 checker、scanner、provenance 与 helpers 逐字保留，仅 Selection/main 接入固定 drive-first 与 exactrefs。索引和 selected 共用原有的计数/原行字节两项上限，overflow 仍为 INCOMPLETE；不增加原件读取遍数，不改变固定窗口。baseline 已有 first-nonzero latch 分支，本轮不把它描述为旧缺陷或新增修复。

最终 canonical CPU v3 工具 44521 已真实 reap rc0：10 PASS、0 fail/error/skip，`.788136087` wall-s；34 个来源 before/after/current 相等且逐字恢复，两个保存 CPU 身份 fresh-gone。见[最终 10 项证明](assets/20261024_mr3_p2a_v61_cancel_forensics/checks/artificial_cpu_v3/proof_v1.json)。其中包含两个 scan 集成 case；这些均为人工 CPU，不代表五原件流已经读取。

当前 extraction spec 为 `10496` B、SHA256 `85fdee1964caf7f969d8541bf053e4e43c48d7a1f89eafd1e9271e1fe61ce9a2`。admitted=True 不代替新 commit/push、source/current/Git 一致与干净工作区要求。实际取证仍未执行，本报告不预填取证结果或本轮实际费用。

## 连续账与后续边界

唯一入场账为 [V60 规范末账](assets/20261023_mr3_p2a_v60_reader_registration/closure_ledger_v1.json)：`U108848.4042410476018 / C150000`，余额 `41151.5957589523982`；本轮完整工程预约 660 wall-s。150000 仍为代理依据用户持续委托选择，非逐数值用户批准；旧费不重置，pilot/final 原总额不动。

最终源码和 10 项 CPU 已闭合；root 实际提交推送本次 source/spec/scope 并通过来源准入后，才可在新执行冻结下进行一次有界原件消费。失败保留原件、真实 rc、partial 与完整费用。下一路线仍为：固定取消因果窗 → 诊断真实取消并修复、验证有效 probe → 短 native/审计性能分解与等价提速实测 → 容量 gate → 新同 freeze 完整 12 EP / 30 角色 → 真实学习及三场 strict95。取证结果本身不放行后继链，原停止界、R、固定 anchor、实际非零电机披露和 95% 门均保持。
