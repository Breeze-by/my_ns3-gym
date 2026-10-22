# MR3 P2A V40：新冻结原生资格与最小学习链

2026-10-22开始准备。用户直接回应75000工程额度问题：“你一直继续执行就好了，直到把P2A完成，不需要问我是否批准”。据此自主持续执行P2A，不再就一般预算/实施步骤反复询问批准；当前采用累计75000工程墙秒的有界块并完整记账，不降低95%任务、质量、参与、安全或审计门。P2B/gateway不启动。

[本次授权](assets/20261022_mr3_p2a_v40_native_qualification/authorization_v1.json)：入场已用48259.9538193466018，当前余26740.0461806533982秒；完整新原生资格18000＋外部收口300＋minimum1800，共预约20100秒，余6640.0461806533982秒给其他必要有界准备/故障诊断。pilot初始仍余1870决策/2905.9547395464029秒，final-only初始open401/402/403和原额度保持。

V39已完成精确证书生产恒等提速和446项人工CPU。新的生产字节需要新的完整source/binary/custody绑定、明确point模式、同冻结资格，不能继承旧通过。V37二维随机probe FAIL保留，它的全PASS不是native前置。继续用现有严格审计；训练负回合新版本如确有必要，先形成可审阅的科学有效方案并新冻结，不能用提速或预算授权改判既有失败。

准备新plan：所有native与minimum/pilot/final argv同时显式exact-point-bridge-v2和point-attachment-3x3-v1，四阶段30 mandatory角色/12回合及原墙秒上限保持；完整policy_stages三registry、不可覆盖输出、源/动态库身份、外部实际wait/关闭及实际区间union费用全部密封。当前只准备，尚未启动新World或PPO；后续结果逐项追加。

冻结前补齐费用边界：pilot与validation外部finalizer归所属phase，各从原CAP内事前留300秒，主deadline相应2605.9547395464029/8700，内部500尾不减，native ceilings不增。minimum外尾仍归工程300共享预留。最终driver按完整parent实际wait区间union扣费，包含wrapper前后开销，nested inner不重复相加；缺失/失败回执也保留实际费用，失败仍做外部身份收口。没有改变任务或科学门。

## 冻结前准备通过

当前源码主CPU452项通过（geometry354、native输入读者12、learner77含6项新外尾用例、snapshot9），实际ROS导入与RTX4090 CUDA metadata通过。实际plan通过55项准入回归及20项新人工fixture；55与主组部分重复，不相加为独特样本。[CPU索引](assets/20261022_mr3_p2a_v40_native_qualification/checks/index_v1.json)保留全部失败：readiness_v1的模块路径错误、三个actual-wait提交前的并行快照setup竞争、plan_check_v1缺pytest；分别用canonical learner路径、atomic link、ns3gym pytest8.4.2纠正。旧源与回执保持，无World或学习，工程新增0。

[完整plan](assets/20261022_mr3_p2a_v40_native_qualification/plan_v1.json) SHA `7b3cd679a88adbab02d20a34acba91e7697916ba91f9c65b728bd91098515a0b`，755source/10ELF；[binding](assets/20261022_mr3_p2a_v40_native_qualification/native_custody_binding_v1.json) SHA `09fa39c6e2f6d51cab5e0ddc4ca068dd0d6498237b93d4bca0cb8855762fc06f`。[plan独立复核](assets/20261022_mr3_p2a_v40_native_qualification/plan_independent_review_v1.json)与[入口复核](assets/20261022_mr3_p2a_v40_native_qualification/entry_independent_review_v1.json)PASS。没有必须重编译的项；新freeze实际preflight/完整科学矩阵仍须通过。

唯一入口在wireless-rl：`PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES=0 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m report.assets.20261022_mr3_p2a_v40_native_qualification.execute_chain_v1 --freeze EXACT40`。EXACT40取本次clean/pushed完整Git SHA。所有阶段与policy registry已密封，整链闭合前不改源码、plan、文档或commit。原生矩阵/tmp/mr3_p2a_reach_v40_matrix及ROS/log/mr3_p2a_reach_v40，driver记录/tmp/mr3_p2a_reach_v40_driver_v1；policy路径/条件完整见plan。全部提交工作实际wait/闭合，错误也记费用，不同freeze不拼资格、不在本活动重试覆盖。结束后另核driver与wrapper保存身份gone，仍不以当前准备宣称P2A成功。
