# 禁用的单EP原runtime profiler候选

system Python实际resolved ELF也按scope固定bytes/SHA，在父进程前后及子进程import前核定。它是单列二进制绑定，不伪称来自Git；子进程另保存真实interpreter路径/版本。

仅准备了候选文本、静态AST与源字节索引。没有导入/执行reader或候选，没有读取任何native原件、profile、测试、World、GPU或模型；仓库未改。`scope_TEMPLATE_NOT_ADMITTED.json`含null余额/epoch/输入SHA，**必定不能入场**，不得把它直接用于执行。

三个拟canonical文件：`profile_common_v1.py`、`runtime_child_v1.py`、`profile_guard_v1.py`。应由root在V50实际整链wait/reap、费用结算、身份/原件关闭完成后，移入一个新report package、实际CPU检查、完善scope后新freeze。新包名称不在候选中写死，guard从自身`__package__`生成固定同包child入口，不接受任意reader/EP/命令行。

**双freeze兼容性已静态确认。** 原`audit_reach_runtime.source_proof`429–445仅对23个明确源核current bytes等于`git show 23e9093:path`，并核两wire literal；没有HEAD==23、clean/status gate。因此新文档/profiler提交可成为另一个execution freeze，只要这23源逐字不变。guard加强为这23源及docstring-only `mr3_learning.__init__`同时匹配Git23、未来Git和current；其自身3源及完整scope匹配未来Git，且HEAD必须等于未来freeze。不会修改/投影原audit或冒充旧执行源。

固定EP只为V50冻结计划的reset worker0/episode001_open_101，无择优、替代或retry。guard按14个原logical artifact选择规则核完整encoded bytes/sha/stat，并要求它们等于已闭合canonical inventory的original_sha256/original_bytes；不把rawbytes.gz归档目录传给reader、不解压mapblobs。元数据核真实epoch/原freeze/seed/point/support；完整API内部仍自行核decoded SHA/source/nativefeed，所有原数学和缓存均保持。

child仅在fresh system Python进程中调用**一次**：

```python
runtime.audit_episode(FIXED_EP, expected_freeze=ORIGINAL_23_FREEZE)
```

不调用自动RUN CLI、audit/audit_episode_set，不调用source_proof作预热。前置hash会温OS cache，不能称冷盘benchmark。cProfile只覆盖原函数调用；所有hash/import/Git/序列化/actualwait仍在父收费区间内。保留完整原runtime结果、raw pstats、top40 self/cumulative、function/callcounts、childwall/processCPU/peakRSS KiB、所有源/输入ref。检查target count=1且RUN-dispatch count=0；无新原生/任务/学习/P2A资格信用。

**900秒只是未来预约，当前尚未余额准入。** 必须用V50全部实费及外尾结算后的真实余额编制一个新`mr3-runtime-profile-budget-admission-v1` JSON（used+remaining=75000、remaining>=900、reservation=900），绑定该JSON并封进scope。禁止借pilot/final-only、重置余额或自动扩大配额。当前模板没有这些事实。

主parent840内预留30秒guard收尾：entry+810绝对monotonic workdeadline触发owned session TERM，10秒不退出发KILL，随后5秒仍没reap则继续真实wait并明确超额FAIL。child可把TERM变成专用异常，在finally尝试dump partial pstats，但超时永远FAIL；早期signal/kill/异常可能没有有效pstats，原空/partial文件必须保留。若内核阻塞IO或reap无法及时返回，不能承诺硬墙时上限；全部实际超额完整计费FAIL，不放弃reap/伪造rc。source/hash循环检查剩余时间，Git子检查各最多10秒。

调用最终canonical module的示意（**现在不能运行**）：

```text
/usr/bin/python3 -B -m report.assets.NEW_PACKAGE.profile_guard_v1 --scope /CANONICAL/SEALED/scope_v1.json --execution-freeze EXACT_FUTURE_40 --output /tmp/mr3_single_ep_runtime_profile_v1
```

root仍应以现有`reach_execution --scope engineering --source ... -- <上述命令>`保存外部完整actualwait，并从最外parent计算主840而不是只相信guard嵌套用时；另≤60秒外尾fresh-check guard/outer/child saved PID-start与owned group、source/input/output refs及总900/真实余额。原guard自己的模块import/receipt写入不应从费用中漏掉。嵌套child时间不重复相加。任何主/总额超额均FAIL且全费。

guard的输入关闭前置当前采用V50 closed reviewer的字段：parent_coordinators_actual_waited_and_fresh_gone/closed_archive_eligible/bound_inputs_stable/metadata_membership_stable均True。若V50最终使用其他已声明schema或只达到preserve-evidence/unknown，root必须如实处理前置不满足，不直接改布尔；该候选不会靠忽略未知身份取得closed信用。单EP profile也不修原科学FAIL。

应用前必要的人工CPU（未运行）：mock Popen正常/异常/预检查过期；TERM后真实rc与partial；TERM10→KILL→actualwait；无法reap继续wait/FAIL；无epoch/输入SHA/14文件之一/23源之一/futureseal缺失拒绝；错EP/RUN拒绝；budget<900拒绝；两个freeze文档变化允许但任何被核源变化拒绝；单次dummy target/no RUN/warmup；新输出拒覆盖。应只用dummy math/toy files，不提前消费本EP。模板A26 owned-child guard与reach_execution仅提供真实wait/close模式；没有给候选授予现成测试信用。
