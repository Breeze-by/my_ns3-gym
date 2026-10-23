# MR3 P2A V56：一次有界GDB启动SIGSEGV栈诊断

**当前已CLOSED，诊断描述PASS：** 新freeze `9d22290108d3edc8861216eb0505220356de6d32`、tool8209真实reap rc0。成功仅指获得SIGSEGV栈；inferior未自然退出、没有有效物理比较或原生资格。工程实费12.268341836墙秒，累计90382.5535899546018/120000、余29617.4464100453982。末尾实际关闭节及规范末账为当前状态；下方原预声明/待执行/pending字段保留为准备快照，不能用来覆盖已关闭事实。

2026-10-23预声明：root正在封存spec、准确CLI、工具/源码字节和必要CPU证据；尚未新sourcefreeze或正式执行。本次只确定已失败native启动的实际栈，不更换solver、修物理模型或重跑V55双case。P2A未完成，用户持续自主委托保持。

## 入场与配置解释更正

[V55已实际闭合FAIL](20261023_mr3_p2a_v55_passive_plant.md)，freeze `63f5cc107161202a6d610f5fe39f3434b0d7eed9`，tool23231实际rc1。quick50/direct-world两CPP都rc-11、wrapper1，仅early identity存在、CPP summary缺失；没有有效物理数据或solver优劣结论。原连续parent12.924178319墙秒已收费，6主保存身份和后继CPU两身份分别freshgone；原件、pending字段和FAIL不回写。

承接[规范V55末账](assets/20261023_mr3_p2a_v55_passive_plant/closure_ledger_v1.json)：累计 **90370.2852481186018 /120000**，余 **29629.7147518813982**墙秒。本次完整parent另预约 **300**墙秒，预约后余 **29329.7147518813982**。120000仍是代理依据持续委托选择的工程块，不声称用户逐数值批准；pilot1870决策/2905.9547395464029墙秒与open401/402/403三场final-only900决策/9000墙秒保持，新增均0。

生产`p1c_open/rooms/corridors.world`的ODE设置是 **quick150（type=quick、iters=150）**，见[生产open配置](../../../../../../../ros2_ws/ros2-multi-robot-automap/src/multi_robot/worlds/p1c_open.world)及相邻rooms/corridors文件。A55的quick50是诊断生成设置，不能称生产原配置或旧episode exact replay。保留原快照，最新解释以本段为准。`gazebo::loadWorld`已有Init调用，不能在未取得栈时把“再补Init”当成已证实修复；No HOME/ALSA/OpenAL提示同样不能定根因。

## 唯一诊断范围

使用**同一个未修改的A55最终ELF**及原`prepared_worlds_v3/quick50.world`，只在GDB下启动一次以取得SIGSEGV栈，不执行direct-world臂、不作生产solver比较、不补V55样本或将新结果改写旧FAIL。ELF471256B、SHA `b2e154c4b08105c7d37193c8e18df19bb9275542da41924ca06f066b361e7a63`；原buildmanifest、旧源、371条byte-admission链与342链接对象仍作为字节来源。

GDB12.1使用`--batch`和no-init，关闭用户init、auto-load、debuginfod等非必要外部加载/下载；由`timeout`约束120墙秒。driver到150秒对实际观测、同对象PID/start的owned后代作pidfd收尾，180秒为自身wrapper退出兜底，最后实际wait/reap；完整parent300秒仍是费用门，不承诺操作系统硬实时。中断、超时、缺栈或非预期退出均保留partial/真实rc/全费FAIL，不自动重试或扩展输入。

旧A55 byte-admission函数只用于原371链和current/Git/SHA字节核对；不调用A55的`run_case`、不启动旧两臂，也不继承其原entry或1800预约作为本次预算。本次预算/独占输出和工具来源由新V56 spec及准确CLI封存。GDB或wrapper rc0只可能是调试描述成功，不能冒充inferior自然退出、ELF初始化成功或有效物理结果。

## 封存入口与关闭

[root runner](assets/20261023_mr3_p2a_v56_startup_gdb/run_startup_gdb_v1.py)已准备，spec/工具bindings/最终CPU结果及新exact40freeze由root最后封存，当前不预填PASS或哈希。提交推送后，仅以那个精确新freeze执行一次：

```bash
# cwd: wireless-rl；NEW_EXACT40仅是待替换占位符。
rtk proxy /usr/bin/python3 -B report/assets/20261023_mr3_p2a_v56_startup_gdb/run_startup_gdb_v1.py --freeze NEW_EXACT40
```

独占输出`/tmp/mr3_p2a_v56_startup_gdb_v1`及其`actual_wait`、`native`子目录。完整费用从wrapper Popen提交到真实wait并完成post-source核对及owned cleanup，含timeout/GDB/inferior与drain，nested不重复；entry metadata span单列，超额全费FAIL。actual root-tool reap/launch/live祖先、保存同对象身份freshgone（Z算present、不可读不算gone）、来源before/after和不透明原件库存随后封存，后继CPU身份另核，不补PID/start。

只有实际栈和完整来源可引导下一新版本修复，当前不宣称已定位SIGSEGV、更不改变原12EP30角色/95%/质量/安全或P2A学习出口。无learner/optimizer/P2B活动，V55原活动不重跑。

## 封存前CPU证据

GDB flags-only CPU实际rc0，墙秒0.187747703，未包含`run`、inferior或World；来源前后相同，2保存身份freshgone。见[实际wait](assets/20261023_mr3_p2a_v56_startup_gdb/checks/gdb_flags_cpu_v1/actual_wait.json)和[freshgone](assets/20261023_mr3_p2a_v56_startup_gdb/checks/gdb_flags_cpu_v1/freshgone_v1.json)。当时driver快照随receipt保留；后续仅强化实际wait成功、来源对应和命令rc检查，最终AST与help另作静态核对，不复用CPU运行成native资格。准确CLI由spec和新freeze绑定。


## 实际执行与关闭（2026-10-23）

新exact freeze为`9d22290108d3edc8861216eb0505220356de6d32`，root tool8209已真实reap rc0；driver/wrapper/debugger命令均实际返回0，原`inferior_SIGSEGV_observed=true`、`backtrace_observed=true`与`inferior_natural_exit_claimed=false`一并保留。取得栈是本次唯一诊断PASS，不是inferior正常结束、World初始化成功或有效被动物理结果；不重裁V55两臂FAIL，也不提供native/训练信用。

主线程实际路径为`__strlen_evex → gazebo::util::DiagnosticManager构造 → World::Init → init_world → gazebo::loadWorld → main`。[本机字节与真实栈定位证明](assets/20261023_mr3_p2a_v56_startup_gdb/checks/home_null_rootcause_v1/evidence/proof_v1.json)显示HOME字符串、getEnv返回值直接送入无空检查的strlen，返回地址与本次GDB frame1相符；这是缺HOME的启动环境故障，发生于runWorld/本次控制anchor回调之前，不能解释solver/drift性能。该独立静态CPU实际wall0.113990578秒、工程0，其2身份另freshgone；没有运行修复后World。

实际从wrapper Popen至真实wait并完成post-source核对/owned cleanup的完整parent为 **12.268341836墙秒**，原nested debugger wait4.523455087秒包含在内不相加。承接90370.2852481186018，累计 **90382.5535899546018 /120000**，余 **29617.4464100453982**。原300预约未超，不把未用预约计为消费。120000仍为代理在持续授权下选定的有界工程块，`numeric_user_approval_claimed=false`；pilot1870决策/2905.9547395464029墙秒与final-only open401/402/403共900决策/9000墙秒不变，本次新增全部0。

[关闭metadata核对](assets/20261023_mr3_p2a_v56_startup_gdb/checks/closed_metadata_review_v1.json)保留root actual-tool wait、launch、活体祖先与entry/summary/actual wait同对象绑定，6个主保存PID/start均freshgone（同start的Z算present、不可读拒绝）。timeout在Popen初次身份保存后改变自身group：保留两次实际group观测，只对原PID/start/parent/session绑定相同对象，不伪造不变group。376条原source before/after相等，关闭新核34个非库源、30个repo current-Git与旧1fa的10源子集；342库只对原实际wait/封存manifest metadata及resolved别名，不重新读取342对象或复制系统库。

[不透明原件库存](assets/20261023_mr3_p2a_v56_startup_gdb/closed_inventory_v1.json)有 **12文件、原586647B、规范516957B、0link**，JSON逐字保留、文本仅无损gzip，含原prefix8文件及rootwait/launch/live/helper4文件。无V52 raw重读、无CSV/轨迹语义重放、无新native/GDB执行；原driver pending字段不回写。原件位于[closed_execution](assets/20261023_mr3_p2a_v56_startup_gdb/closed_execution)，每个gzip的decoded SHA/bytes在库存中等于原字节，可据此无损恢复。

关闭CPU v1实际rc1/0.511946006墙秒：ldd别名拼写与实际resolved source路径比较拒绝，未开始归档，原失败脚本/回执保留；v2仅按同对象resolved路径比较metadata后真实rc0/**26.171658586墙秒**，16绑定源前后稳定、工程新增0。[两轮CPU postreap记录](assets/20261023_mr3_p2a_v56_startup_gdb/checks/closure_cpu_postreap_v1.json)分别核4个自身保存身份freshgone，无需再运行旧consumer。[规范末账](assets/20261023_mr3_p2a_v56_startup_gdb/closure_ledger_v1.json)可由下一活动直接承接。

下一步为[root准备的V57](20261023_mr3_p2a_v57_passive_plant.md)：独占有效HOME、实际生产配置基线quick150与direct-world的新有界两臂；不是旧V55重试/改判。此处不预填V57结果、solver优劣或安全/95%资格；12EP30角色、完整科学门及旧FAIL保持，P2A未完成。
