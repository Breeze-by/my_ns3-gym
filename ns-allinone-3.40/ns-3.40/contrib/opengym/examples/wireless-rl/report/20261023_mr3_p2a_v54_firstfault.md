# MR3 P2A V54：固定 FIRSTFAULT 取证的资源限定后继版本

> 当前：**CLOSED — 描述PASS**。执行freeze1d35dda0、tool36067真实reap rc0；完整两流SHA/stat/parse通过，40selected/0drop。首登记故障tb1 / fixed disk radius exceeded（244.58秒）；D为固定anchor圆盘，不是仍在HOLD的判据。完整parent254.441556546墙秒已收费，累计90357.3610697996018/120000、余29642.6389302003982；4主身份及2后继metadata CPU身份分别freshgone。完整实际结果见文末闭合节，下方其余准备/待执行文字是历史快照。下一仅转向固定KEEP故障的零驱动物理诊断，未承诺新scope/solver成功或变更科学门；P2A未完成。

2026-10-23：准备完成，尚未正式读取两份原件；须新commit/push后以exact40执行freeze启动一次独占活动。用户持续委托自主完成P2A有效。规范21项人工CPU已实际PASS，CPU/源码预检查不提供首故障、原生资格或学习信用。P2A未完成。

## 依据与当前账

[V53已真实闭合partial FAIL](20261023_mr3_p2a_v53_firstfault.md)：执行冻结`7f122cfd3c9bbb6f28b57ffaf648be9229c9b1a5`，固定100万行门在第1000001行停止，motion只读2267972220/2458997272B，未取得完整motion SHA，`UNKNOWN_PARTIAL_PARSE`保留。startup完整460行/286052B及整文件SHA通过，仅记录worker自身`infrastructure_failure`广播回调，不能据此证明生产端首fault。原实费229.413776461墙秒与所有FAIL保持。

承接[规范V53末账](assets/20261023_mr3_p2a_v53_firstfault/closure_ledger_v1.json)：累计 **90102.9195132536018 /120000**，余 **29897.0804867463982**墙秒。本次完整parent预约 **600**墙秒，最坏预约后余 **29297.0804867463982**。120000是代理依据用户持续授权选择的有限工程块，`numeric_user_approval_claimed=false`，不声称用户逐数值批准。pilot新增0，原1870决策/2905.9547395464029墙秒保持；final-only新增0，仍open401/402/403三场共900决策/9000墙秒。

## 固定范围与唯一变化

新[spec](assets/20261023_mr3_p2a_v54_firstfault/spec_v1.json)和[scope](assets/20261023_mr3_p2a_v54_firstfault/scope_v1.json)仍只消费原V52 deadline `worker0/episode001_open_101`两文件：

| 原输入 | 整文件字节 | 原SHA256 |
|---|---:|---|
| `motion_safety.jsonl` |2458997272|`d3e0df10ba2f5bafbe46c074d2cdf34653dadc097eee6b7da4582371e2970fc6`|
| `startup_readiness.jsonl` |286052|`c9147ae25628d999b6bdc0e66b6abbc6ebbcf166e2ff3770ba70e4603dc3d4d3`|

两者仍由不可变[V52闭合库存](assets/20261023_mr3_p2a_v52_qualification/closed_inventory_v1.json)绑定。原证据freeze `1fa55bc56d5bb9e230d4b397f962d83b1604b278`、epoch `mr3_p2a_reach_v52_deadline_w0_e1_426a2555`、窗口244.48–244.62秒不变。七份解释源码仍逐字归原Git1fa；执行代码/导入链/配置归未来新exact40freeze。

| 资源门 | V53历史值 | V54新预声明 |
|---|---:|---:|
| 每文件最大行数 |1000000|2000000|
| consumer合作式work墙秒 |240|480|
| 完整parent费用门墙秒 |300|600|

其余总输入3GiB、每行8MiB、最多256选择记录/2MiB输出、严格JSON/epoch/schema/序号/时间校验、原文件顺序首次故障与固定窗口各kind/robot/feed首尾选择均保持；不因V53部分结果拓展输入或选择规则。完整流SHA/stat校验和partial/超限FAIL仍必需，不把未读完计为NOT_RECORDED。[资源版本差异库存](assets/20261023_mr3_p2a_v54_firstfault/resource_only_manifest_v1.json)及[完整patch](assets/20261023_mr3_p2a_v54_firstfault/resource_only_v53_to_v54.patch)记录精确替换，逆替换恢复四份完整V53源/测试字节；没有parser/科学数学/安全优化。

V53部分吞吐只提供完整读取耗时的粗略外推，不是新全读实测或600秒内成功保证。本次为新的前瞻有界活动，不重开V53目录、补读后缀或改旧费用/判词。

## 已有人工验证

候选21项人工fixture实际PASS，完整wait **0.170796105墙秒**；见[候选回执](assets/20261023_mr3_p2a_v54_firstfault/checks/candidate_cpu_v2/actual_wait.json)。最初候选命令support源码路径错误，在测试Popen前setup失败、没有actualwait；其[实际setup错误原件](assets/20261023_mr3_p2a_v54_firstfault/checks/candidate_cpu_v1_setup_failure/setup_failure.json)和控制台保留，只修命令，不掩盖失败。

规范安装后同21项真实PASS、rc0，完整wait **0.375278637墙秒**，18个执行/配置/支持源before==after，两个保存身份在实际reap后[freshgone](assets/20261023_mr3_p2a_v54_firstfault/checks/canonical_cpu_v1/freshgone_v1.json)；[规范actualwait](assets/20261023_mr3_p2a_v54_firstfault/checks/canonical_cpu_v1/actual_wait.json)保留完整argv/控制台SHA。均为小BytesIO人工fixture，无原件消费，工程费0。[预提交源码核对](assets/20261023_mr3_p2a_v54_firstfault/checks/precommit_sources_v1.json)核14份声明源、七旧Git解释源及规范spec绑定；新执行Git的完整逐字校验须在未来freeze上实际完成。

## 唯一正式入口与收口

正式版本为[consumer v3](assets/20261023_mr3_p2a_v54_firstfault/firstfault_extract_v3.py)，SHA `1ea8f8bf37f6bbd147ac18652e6825ab34cf384c624c5d84635de6dd3a4fbc0c`；[runner](assets/20261023_mr3_p2a_v54_firstfault/run_firstfault_v1.py) SHA `240d04ed93fc75c2dd1603e9f2078a061ee80bba96edb578acf1094851decf0a`。须先提交推送，再将`NEW_EXACT40`替换为本次唯一40位执行freeze；此占位符不是已获准运行的实际值：

```bash
# cwd: wireless-rl；只在新commit/push后执行一次。
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= /usr/bin/python3 -B report/assets/20261023_mr3_p2a_v54_firstfault/run_firstfault_v1.py --freeze NEW_EXACT40
```

独占输出`/tmp/mr3_p2a_v54_driver_v1`、其`forensic_actual_wait`与`/tmp/mr3_p2a_v54_firstfault_v1.json`；不覆盖旧V53。费用按wrapper Popen提交至完整parent真实wait返回墙秒区间收取，nested不重复；entry/post metadata span单列。work门合作式，600秒是费用门，不声称操作系统硬实时kill；超额/部分/错误均保留全费FAIL，不自动重试或扩读。

实际工具reap后单独绑定root wait/launch/live祖先证明，fresh核同对象保存PID/start（Z算present、不可读不算gone），封存小结果/driverprefix/原件绑定和末账。若全读后只得NOT_RECORDED也应如实报告，不能猜producer首故障。只有真实具体robot/reason证据才能引导原因对应的修复与CPU验证；不据描述PASS跳过同freeze完整12EP30角色、minimum真实策略更新、原额pilot与三场strict95出口。当前无World/native/模型/GPU/optimizer或P2B活动。

## 实际闭合：完整固定输入描述 PASS，首登记控制故障已记录

**本节为最新状态；上文“尚未正式读取/待新freeze”保留为准备时历史快照。** 执行freeze `1d35dda0d9f1ae8c0fc7a692132fccec29b00282`，原证据仍为V52 `1fa55bc56d5bb9e230d4b397f962d83b1604b278`；根工具36067已真实reap、rc0。实际driver与consumer均PASS、errors为空，全部选定输入与原件绑定通过；[真实结果](assets/20261023_mr3_p2a_v54_firstfault/closed_execution/closure_tools/mr3_p2a_v54_firstfault_v1.json)和[driver原件](assets/20261023_mr3_p2a_v54_firstfault/closed_execution/tmp/mr3_p2a_v54_driver_v1/summary.json)完整保存。

| 输入 | 实际完整行数 | 实际完整字节 | 完整SHA/stat/parse |
|---|---:|---:|---|
| motion |1086363|2458997272|全部PASS，0解析错误|
| startup |460|286052|全部PASS，0解析错误|

实际选择40条、dropped0、声明规则选择完整；本次只做原记录描述，没有重放Reach/物理数学。首次登记runtime fault是motion原第 **1084442** 行、`record_sequence=1084442`、kind=`normal_control_model_invalid`：tb1，reason=`fixed disk radius exceeded`，`commit_clock_ns=244580000000`、原sim244.58秒。该原行SHA `8edeee4a5c8470cf687a569f44675882bcc661f8b4a837f933a24552c407908c` 与完整payload保留；“首次”仍仅指固定原文件及登记故障类型的原序首条，不是全系统因果先后定理。startup实际首callback仍是worker自身通用infrastructure_failure接收，不能变成motion首fault广播到达证明。

该具体记录提供下一步定位控制/校准/模型路径的依据；它本身不证明真实机体违反物理界，也不直接决定应放宽或改哪项门。V52资格FAIL与V53partial FAIL、UNKNOWN和两次实际费用原样保留，不能把两版本拼成一次完整审计或P2A通过。

### 实际完整wall末账与身份

完整parent区间`[4477944797377143,4478199238933689]`为 **254.441556546墙秒**，nested child 254.052367673墙秒包含其中、不另叠加；600秒费用门未超。承接90102.9195132536018，现累计 **90357.3610697996018 /120000**、余 **29642.6389302003982**墙秒。120000仍为代理依据持续授权选择，`numeric_user_approval_claimed=false`。pilot/final新增均0，原1870决策/2905.9547395464029墙秒与open401/402/403三场final-only900决策/9000墙秒保持；无World/native新运行、模型、GPU或optimizer更新。见[规范末账](assets/20261023_mr3_p2a_v54_firstfault/closure_ledger_v1.json)。

[独立metadata关闭](assets/20261023_mr3_p2a_v54_firstfault/checks/closed_metadata_review_v1.json)核14执行源及spec/scope/库存current==执行Git、七解释源==原1fa；outer17绑定与consumer before/after稳定，driver本身before==after。root实际wait绑定launch/live原SHA；driver、wrapper、consumer及运行时实观祖先4个同对象PID/start均freshgone，Z仍算present、不可读不能算gone，不跨对象补start。driver原`PENDING_EXTERNAL_DRIVER_FRESH_GONE`字段保留，由本次外部证明完成关闭，不改原件。

原live观察的辅助`actual_tool_program_argument`误取sys.argv索引2，保存成`--freeze`。原字节不改；root依据真实工具调用另写[绑定三原件SHA的更正说明](assets/20261023_mr3_p2a_v54_firstfault/closed_execution/closure_tools/mr3_p2a_v54_live_argv_field_correction_v1.json)。实际entry/summary完整argv与launch去掉Python `-B`后的argv逐项相同，均指规范绝对runner；错位辅助字段不作程序或身份来源证明，也没有更改/补造任何PID/start。

关闭核对自身是metadata-only CPU范围，真实wall **17.468819143秒**、rc0、15绑定输入前后稳定、工程0；其两个保存身份在工具真实reap后[另行freshgone](assets/20261023_mr3_p2a_v54_firstfault/checks/closed_metadata_cpu_postreap_v1.json)，不并入主4身份。[实际wait及完整控制台](assets/20261023_mr3_p2a_v54_firstfault/checks/closed_metadata_cpu_v1/actual_wait.json)保留。这是墙钟实耗，不是CPU处理器用时。

[闭合库存](assets/20261023_mr3_p2a_v54_firstfault/closed_inventory_v1.json)逐字封存 **13份小原件/167712B/0 symlink**（完整driver七文件prefix、取证结果、root wait/launch/live、更正说明及实际metadata helper）。原两raw仍承接不可变V52库存/分块证明；本次metadata关闭没有再读或复制两raw，没有重跑consumer或完整性审计。

下一步围绕已记录的tb1固定disk模型故障作原因对应的源码定位、人工CPU验证与新版本有界验证，不机械重跑整资格矩阵或直接PPO；原同freeze完整12EP30角色、真实策略更新及三场strict95出口仍全部保持。描述和关闭PASS不等于技术P2A完成。
