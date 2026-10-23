# MR3 P2A V56：一次有界GDB启动SIGSEGV栈诊断

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
