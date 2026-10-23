# MR3 P2A V53：已关闭 V52 的首次控制故障取证

> 当前：**CLOSED — partial FAIL**，非首故障定位成功。执行freeze7f122cfd3实际rc1；motion只读2267972220/2458997272B，`UNKNOWN_PARTIAL_PARSE`保持，startup全读只证实worker通用失败回调。完整parent229.413776461墙秒已收费；累计90102.9195132536018/120000，余29897.0804867463982。4主身份及2后继CPU身份分别freshgone，12小原件无损封存。下方预声明是历史快照，实际结果见末尾闭合节；[V54](20261023_mr3_p2a_v54_firstfault.md)是另立资源/版本范围的新活动，尚待新freeze执行，不补改V53。P2A未完成。

2026-10-23 预声明。用户已授权自主继续至 P2A 完成。本活动仅对已关闭记录作一次有限描述，先确定 `normal_control_model_invalid` 的实际 robot/reason；不回放原审计数学，不启动 World、模型、GPU、optimizer 或 P2B。生产代码和所有科学门保持。P2A 未完成。

## 入场事实与费用

[V52](20261023_mr3_p2a_v52_qualification.md) 的原冻结是 `1fa55bc56d5bb9e230d4b397f962d83b1604b278`。interface 9、terminal 6、reset 9 类必要角色通过；deadline 只有 203 个完整 step 返回，第 204 步在 244.58 s 收到负控制 ACK，随后基础设施失败。六类 deadline 审计未派发，minimum/pilot/final 未启动。旧 FAIL 保持。

本次承接工程累计 `89873.5057367926018 / 120000`，剩余 `30126.4942632073982` 秒；预约完整父 wait 最多 300 秒，预约后 `29826.4942632073982`。120000 是代理依据用户持续委托前瞻选择的工程上限，不声称用户批准过该数值。原 pilot `1870` 决策 / `2905.9547395464029` 秒和三场 final-only 原额保持。本活动两政策账户新增均为零。

V52 的 [7772 原件库存](assets/20261023_mr3_p2a_v52_qualification/closed_inventory_v1.json) 已通过逐字节解码验证，SHA `63efb61cc7b2abaf723b3824399d203a1a0b288465a367110eabcb5ec565ccf7`。Git 中两个大 packed 文件使用 [精确分块映射](assets/20261023_mr3_p2a_v52_qualification/packed_overlay_v1/manifest.json)，原 gzip 与 raw 本地保留；原库存未改。

## 固定输入和选择规则

正式输入仅为 deadline `worker0/episode001_open_101` 的两份原文件。其字节数、整文件 SHA 及库存 SHA 已写入 [spec](assets/20261023_mr3_p2a_v53_firstfault/spec_v1.json)；不允许结果驱动的扩读。

| 输入 | 原字节数 | 目的 |
|---|---:|---|
| `motion_safety.jsonl` | 2458997272 | 首个登记故障类型的 robot/reason、原 clock 与行号 |
| `startup_readiness.jsonl` | 286052 | 既有 exploration-failure callback 的实际接收事实 |

固定 epoch 为 `mr3_p2a_reach_v52_deadline_w0_e1_426a2555`，窗口为 244.48–244.62 s。完整单遍严格解析并哈希：拒绝重复 JSON 键、非有限数（包括 `1e999`）、错误 epoch/schema/序号/时间与来源漂移。保留各登记故障类型按原文件顺序的首次记录，以及固定窗口各 kind/robot/feed 的首尾记录，不按 wall 时间重排。

总输入不超过 3 GiB、每行 8 MiB、每文件 100 万行、最多 256 选择记录、最终输出 2 MiB。consumer 合作式工作截止 240 秒；完整父 wait 300 秒为费用门，超额仍全额收费并 FAIL，不声称硬实时 kill。任何部分读取、坏行或选择遗漏均不供完整结论；未记录与未能证明明确区分。此处的“首次”只指固定文件及登记类型的首条记录，不是全系统因果先后定理。

## 执行版本与关闭

[consumer v2](assets/20261023_mr3_p2a_v53_firstfault/firstfault_extract_v2.py) 的 SHA 为 `6276df757a1bdedeb1ad41f439b05f23efc7f5b410107c434b44a13cddebb442`；[runner](assets/20261023_mr3_p2a_v53_firstfault/run_firstfault_v1.py) 为 `88dbd453882ca9895f0a5591bf046edc3d1a743aae528502ae3c86fc624f5a9e`。七份解释源码必须 current == 原 Git `1fa55bc…`；新 consumer、runner、全部导入链及配置必须 current == 新执行 Git。两种冻结分别记录，不能将新 reader 冒充旧冻结的一部分。

[scope](assets/20261023_mr3_p2a_v53_firstfault/scope_v1.json) 封存了 14 份源码、spec/库存与工程预约。正式执行只允许在本次 commit/push 后，以那个完整 40 位新冻结启动：

```bash
# cwd: wireless-rl；NEW_EXACT40 是本次提交推送后的固定执行冻结。
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= /usr/bin/python3 -B report/assets/20261023_mr3_p2a_v53_firstfault/run_firstfault_v1.py --freeze NEW_EXACT40
```

固定独占输出为 `/tmp/mr3_p2a_v53_driver_v1`、其 `forensic_actual_wait` 及 `/tmp/mr3_p2a_v53_firstfault_v1.json`。父区间从提交 `reach_execution` 到真实 wait 返回，包含 wrapper 的源检查、consumer、receipt 和 drain；nested 时间不叠加。无结果、非零退出、超额或源漂移都保留真实费用。随后必须实际回收 driver 并独立核对保存 PID/start，包括后继 CPU 身份，封存取证原件和末账后才能据具体原因修改生产。

## 准备验证与当前状态

v1 的 14 项人工 CPU 原件保留。独立 review 发现输出 fallback 的 hard-cap 缺口；v2 只限制 kind 长度/数量并在超限时生成固定小 FAIL receipt、最终重新检查字节上限。Reach 的实际 schema 保持；最初将 legacy 分支误读为 Reach 的疑点已复核撤回，未据此放宽 schema。

v2 16 项人工解析测试与 runner 5 项回执测试通过，真实 wait `0.360723161` 秒；安装到规范目录后，同 21 项再次通过，真实 wait `0.367003823` 秒，12 源前后相同、两保存身份 fresh gone。见 [CPU 原件库存](assets/20261023_mr3_p2a_v53_firstfault/checks/inventory_v1.json) 与 [独立 review](assets/20261023_mr3_p2a_v53_firstfault/checks/mr3_p2a_v53_firstfault_v2_independent_review_v1.json)。未读取两真实 raw，尚无正式取证结果或新增工程费用。

取证若成功，先按实际 robot/reason 和冻结源码定位、做必要 CPU 修复，再前瞻声明新版本的原生验证与完整资格。不得以该描述、24/30 角色、CPU 或字节归档替代 P2A 的同冻结完整资格、真实策略更新与三场 strict95 出口。

## 实际闭合：部分取证 FAIL，首生产故障仍 UNKNOWN

**本节为最新状态；上文“尚未正式取证/无新增工程费用”是准备时历史快照。** 执行冻结 `7f122cfd3c9bbb6f28b57ffaf648be9229c9b1a5`、原证据冻结 `1fa55bc56d5bb9e230d4b397f962d83b1604b278`。根工具 session74918 已实际 reap、rc1；[真实 root wait](assets/20261023_mr3_p2a_v53_firstfault/closed_execution/closure_tools/mr3_p2a_v53_actual_tool_wait_v1.json)、[driver summary](assets/20261023_mr3_p2a_v53_firstfault/closed_execution/tmp/mr3_p2a_v53_driver_v1/summary.json)及[取证结果](assets/20261023_mr3_p2a_v53_firstfault/closed_execution/closure_tools/mr3_p2a_v53_firstfault_v1.json)均保留实际 FAIL。没有 World、模型或策略更新，P2A 未完成。

本次唯一输入读取错误是 motion 达到封存的每文件100万行上限：读到第1000001行时停止，已读2267972220/2458997272字节，未读后缀保留；没有整 motion SHA，也不能声称全流无故障。`first_runtime_fault_status=UNKNOWN_PARTIAL_PARSE`，不能把窗口空选择/尚未找到 runtime fault 当作全流 NOT_RECORDED。240秒合作式工作门未到期，未修改上限或在同一活动补读。

startup 完整460行/286052字节，整文件 SHA与封存输入一致，源stat稳定。实际记录了一条本epoch、244.58秒的 `exploration_failure_received`，receipt中component为 `mr3_environment_worker`、reason为 `infrastructure_failure`；这是 worker 自身故障广播的接收记录，不能据此证明 motion 生产端首故障的 robot/reason或其广播接收。原结果保留该行的真实字段、行号和raw-line SHA，完整科学重放未运行。

### 完整 wall 账与关闭

工程费按 wrapper 提交至真实 parent wait 返回的整数纳秒区间 `[4476710920209333,4476940333985794]` 收取 **229.413776461墙秒**。nested consumer wait229.144047167墙秒包含其中，不另相加；300秒 parent 费用门未超。原累计89873.5057367926018，现为 **90102.9195132536018 /120000**，余额 **29897.0804867463982**。120000仍为代理在持续委托下的资源决策，`numeric_user_approval_claimed=false`。pilot/final新增均0，原1870决策/2905.9547395464029墙秒及open401/402/403三场final-only900决策/9000墙秒保持。见[规范归一化末账](assets/20261023_mr3_p2a_v53_firstfault/closure_ledger_v1.json)。

[独立小元数据关闭核对](assets/20261023_mr3_p2a_v53_firstfault/checks/closed_metadata_review_v1.json) PASS：14份执行源码及spec/scope/库存current==执行Git，7份解释源码亦逐字等于原证据Git；outer17份source-before/after及consumer源码字典稳定。driver原失败路径的 `source_after=[]` 与 `PENDING_EXTERNAL_DRIVER_FRESH_GONE` 原样保留，由本次外部证明补足关闭，不重写原件。actual root wait精确绑定launch/live SHA；driver、wrapper、consumer及运行时实际观测的祖先共4个同对象PID/start全部freshgone，Z仍算present、不可读不算gone，不跨对象补start。

关闭核对本身是metadata-only CPU scope，**实际wall25.119514753秒**、工程费0（不是CPU处理器用时），14个绑定输入前后稳定；其两个保存身份在真实工具reap后[另行freshgone](assets/20261023_mr3_p2a_v53_firstfault/checks/closed_metadata_cpu_postreap_v1.json)，没有并入主4身份。核对只读小元数据、源码/Git对象及`/proc`，没有重新读取或复制motion/startup两份raw，也未重跑consumer。[实际wait](assets/20261023_mr3_p2a_v53_firstfault/checks/closed_metadata_cpu_v1/actual_wait.json)保留真实返回及完整控制台。

[闭合库存](assets/20261023_mr3_p2a_v53_firstfault/closed_inventory_v1.json)逐字保存12份小原件（driver完整七文件prefix、取证结果、root launch/live/wait及本次metadata helper），0 symlink；原大输入仍由不可变V52库存/分块证明承接，不重复封存。库存SHA和字节数由规范末账绑定，归档/费用/身份关闭PASS不修改本次描述FAIL。

下一步若继续同一问题，必须另立显式版本和有界资源范围，使完整motion读取可在预声明上限内完成；不在V53补样、改原scope或将partial结果拼成整流结论。保留固定输入、epoch、选择规则、科学门与本次实费；在真实producer首故障得到证据前，不据通用literal选择生产修复，不启动PPO或重跑资格矩阵。
