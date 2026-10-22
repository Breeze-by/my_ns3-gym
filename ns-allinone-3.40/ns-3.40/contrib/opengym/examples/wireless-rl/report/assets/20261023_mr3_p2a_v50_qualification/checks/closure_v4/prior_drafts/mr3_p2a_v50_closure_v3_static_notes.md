# V50 关闭/归档 v3 候选边界

v2原文件和额外原字节副本均保留；见 `/tmp/mr3_p2a_v50_closure_v2_independent_preservation.json`。本次仍只改/tmp候选，未读取活动根或/proc，未导入/运行候选、审计器、模型或测试。

v3 reviewer 固定 `cedae11c...18493f` 的原A16源码，按已核原字节compile/exec定义，并额外核其FREEZE Git源。真正执行时，对全部被选原launch.log和过程ledger.jsonl调用原Evidence.consume/finish；identity-bearing raw_json调用原parse/Evidence.visit；合并原同对象PID/start、PID-only和精确launch PID，不跨对象拼对。原始流字节SHA/size与reviewer全程stat/byte binding合取；global launch/PID coverage保持缺start为unknown。普通JSON的观察身份别名仍由既有walker保留，不会用current_start_ticks冒充saved start。

`parent_wait_proof_valid` 是独立保守latch：driver/plan/freeze/schema、summary与ledger、每个phase真实waited/typed returncode和rc内外匹配、source before/after相等及真source receipt、parent/inner时段与费用、wrapper与coordinator PID/start、实际child-parent关系以及phase PASS与原真实rc/errors一致。需要gone的每个parent/pair仍实际查/proc；Z仍present。不能再硬写parents实际waited。此latch必须同时进入preserve-evidence admission和collector前置条件。

整份identity对象含state/parent等观察值，不能拿R/S差异当PID身份变化。v3仅以各原对象自身pid/start_ticks匹配，完整原JSON仍绑定和保存；不从其他对象补缺start。

collector v3 保留同一固定SHA V45 lossless copier，不改压缩数学/数据：同步比较JSON+原launch/ledger身份消费集合；require v3 parent_wait_proof_valid 与exact-A16提取声明；两模式都重查已知parent与原字节稳定性。closed仍要求全部显式saved pairs freshgone、无解析/未绑定PID未知；preserve-evidence只准稳定字节快照，保留原科学/关闭FAIL和unknown，不授完整身份、最终quiescence或P2A信用。

建议root日后在允许时做的最短纯人工边界（此处未执行）：

1. 相同metadata中raw_json含真实pid/start，必须由原A16得到该一对；坏JSON/缺配对保留错误。
2. 原launch.log含process-start PID且无任何saved start，必须global-unbound/unknown；补同对象原saved pair后仅通过global inventory coverage，不能声称PID-only原行得到了补造start。
3. actual_waited=False、内外rc不符、错误source receipt、inner时间越界或ledger不同：parent_wait_proof_valid与preserve admission必须False，即使模拟/proc表示所有PID已消失。
4. 真实非零scientific child rc、source/receipt/父等待均正确：可保留原science FAIL并通过独立metadata/byte preservation；不能改science判定。
5. 相同pid/start但初次R、后次S应仍同一身份；相同pid不同start是PID复用，不能把新start当原start。
6. reviewer与collector必须对同一固定roots的JSON/launch/ledger集合相等；新增launch PID输入不能漏核而归档成closed。

候选尚未提供任何实际关闭、费用或归档结果；只能在整个65081 fully reaped并获root执行指示后使用。

Final source-only tightening: source receipt membership must equal the unchanged frozen driver source/ELF/plan/activity-Python set; cwd and wrapper exit 0/1 must match the actual receipt. Standalone launch/ledger selections use the same predicate as directory selections and the collector. No candidate was invoked.
