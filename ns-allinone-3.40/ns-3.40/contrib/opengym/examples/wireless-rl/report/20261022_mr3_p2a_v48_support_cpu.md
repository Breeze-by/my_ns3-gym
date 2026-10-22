# MR3 P2A V48：禁用的数学恒等提速候选

2026-10-22人工CPU活动闭合。两套候选仍未接生产；不修改旧cf46 geometry、源龄/安全集合、96位根界或48位显示区间，不提供原生/训练/95%信用。实际执行前的基线与候选字节在[source manifest](assets/20261022_mr3_p2a_v48_support_cpu/source_manifest_v1.json)保留。文件中原V47人工fixture/schema标识明确保留，不冒充已执行的原生活动。

生产候选仅复用required²、dot/cross/h与按已验证exact Q缓存不可变sqrt tuple；原support完整公共dict/canonical JSON/full-frame SHA、异常、字段/mode、输入和返回mutation均作对照。9组人工检查通过，固定14 direction/12pair。独立reader不导入生产数学，只将同43项Taylor/Lagrange界改为整数共同分母/Horner并缓存不可变根界，9组人工检查通过，含76方向与人工map/raw、sign union、年龄/边界、cold/warm错误及256项淘汰。保留旧public trig cache别名行为，未混入入口语义修复。

| 实际人工活动 | 结果 | 完整child等待 | 来源 |
|---|---|---|---|
| production_cpu_v1 | 9组PASS，前后源相同 | 1.612845708s | [wait](assets/20261022_mr3_p2a_v48_support_cpu/checks/production_cpu_v1/actual_wait.json) / [result](assets/20261022_mr3_p2a_v48_support_cpu/production_result_v1.json) |
| reader_cpu_v1 | 9组PASS，前后源相同 | 3.576926018s | [wait](assets/20261022_mr3_p2a_v48_support_cpu/checks/reader_cpu_v1/actual_wait.json) / [result](assets/20261022_mr3_p2a_v48_support_cpu/reader_result_v1.json) |

生产固定两模式各3轮×12公共pair调用，包含完整proof/JSON digest，cProfile下总warm时间203122402→164042842ns（约1.238倍），cold-distinct422371255→398205558ns（约1.061倍）。独立reader的未profile计时：64个cold trig为175790622→8263132ns（约21.27倍），warm sqrt约2.89倍、完整warm direction约1.15倍，cold sqrt时间增加约14.7%。不同计时角色不能相加或当成ENV加速，不能据此认定原生31秒/步或full审计885秒的主要瓶颈已解决。固定原始profile及结果均保留，没有看到结果后调整输入或参数。

[独立review v2](assets/20261022_mr3_p2a_v48_support_cpu/independent_review_v2.json) PASS：12份manifest源、58项source/metadata/profile字节绑定与全部数值hash一致，实际生产仍是原baseline。保留[v1](assets/20261022_mr3_p2a_v48_support_cpu/independent_review_v1.json)及后补解释：reader冷trig64角为(i+1)/257，即约0.00389–0.24903rad，与实际Reach合法0.936–1.536rad及源龄分母不同；21倍不是实际source-age workload测量。两个CPU并行、短块且baseline先行，不提供置信区间或ENV推断。数学恒等验证与性能代表性应分开；后续若验证契约角域，须保留本轮结果并另用固定人工输入和新回执。

两次实际wait均rc0/reap、源稳定；原件/World/模型/optimizer均0，工程新增0，累计仍55718.1502503176018/75000、余19281.8497496823982。当前先继续[V47就绪来源诊断](20261022_mr3_p2a_v47_ready_provenance.md)；必要生产应用须另作源声明、相关全链CPU和新冻结完整资格，不拼旧freeze/改原FAIL。P2A未完成，P2B/gateway未开始。
