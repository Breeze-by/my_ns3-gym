# MR3 P2A V54：固定 FIRSTFAULT 取证的资源限定后继版本

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
