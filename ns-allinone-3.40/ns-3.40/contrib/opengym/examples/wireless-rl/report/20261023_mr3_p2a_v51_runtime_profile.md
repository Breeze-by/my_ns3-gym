# MR3 P2A V51：单回合独立runtime耗时剖析

## 闭合：完整单回合profile PASS，P2A仍未完成

执行freeze **`41100004d343953cfb2f822a2d3bfb3ef6a4c00e`** 的唯一活动真实退出rc0。旧native证据freeze23e909保持，固定reset worker0首open101回合；原 `audit_episode` 实际1次、target1次、batch dispatch0、partial=False，原必要runtime审计完整PASS。没有新World、训练或资格信用，V50两必要FAIL/阶段超额/停车缺口和未运行阶段不改。

完整outer parent **421.403520124秒 < 840**；nested wrapper421.197357789、guard421.069641491秒不重复收费。工程累计 **70543.1774146986018/75000**，余 **4456.8225853013982**，外部科学消费者0、pilot/final各+0。见[规范末账](assets/20261023_mr3_p2a_v51_runtime_profile/closure_ledger_v1.json)与[原driver summary](assets/20261023_mr3_p2a_v51_runtime_profile/closed_execution/tmp/mr3_single_ep_runtime_profile_v51_driver_v1/summary.json)。

[独立元数据闭合](assets/20261023_mr3_p2a_v51_runtime_profile/closed_execution/closure_tools/mr3_p2a_v51_closed_review_v1.json)PASS：24旧证据源/9执行源及scope与新Git/current一致，5个保存PID/start身份（含活动中实际观察的tool祖先）全部freshgone，Z仍算present；没有跨对象补造start。guard无signal/timeout/残留group，所有实际wait与区间账一致。第一次闭合工具从/tmp直接启动因package路径失败（未读原遥测）已保留；改为从canonical cwd用runpy启动后的实际review通过，不改剖析结果或伪造失败wait。

[规范库存](assets/20261023_mr3_p2a_v51_runtime_profile/closed_inventory_v1.json)：**22原件/362085B → 362008B/0软链**，SHA `c19aab89e2b77b0f3f5c458dd0be1a9a40406d56284465535778238ea1ea55e1`；pstats原字节SHA `315feb4d9d0261b0145b6b5cb13411316b9e258575a7cd072ae5ed5b57cb0001`。原件未删，每个包装反解及源stat/成员集通过；[封存后重哈希](assets/20261023_mr3_p2a_v51_runtime_profile/closed_archive_review_v1.json)通过。

## 已测热点与下一修改

[cProfile完整派生表](assets/20261023_mr3_p2a_v51_runtime_profile/profile_summary_v1.json)记录 **156261242 calls、总self406.841835273秒、process CPU407.069993689秒**。这是一个带cProfile开销的32步旧回合，不代表ENV吞吐、全部八回合或冷盘基准；下表cumulative有重叠，不能相加。

| 路径 | 实测秒 | 含义 |
|---|---:|---|
| 14份Input.read |168.080051580 cumulative|完整读取/严格JSON解析与验证|
| canonical |108.821443606 cumulative|跨解析与核对的序列化，总调用1053784|
| JSON object hook unique |51.618875086 self|7844597次对象hook，逐键检查成本|
| replay_robot related扫描 |51.282523945 self|9074次扫描全declarations|
| 每量子component ACK全扫 |33.712850958 cumulative|4801次筛选consumed|
| independent_pair |39.599337904 cumulative|几何数学，仅为部分成本|

因此先做直接的声明/ACK索引与严格JSON对象构造等价优化，不继续盲改几何阈值。保持重复、乱序、非字符串ID、缺字段、错误先后、完整canonical/nonfinite/depth验证；独立role不共享裁决，不做对象id可变缓存或降采样。先用旧23源和人工正反例验证完整输出/异常一致，再接生产。另已从源码确定现成五文件可描述worker所见五段wall时间；尚未消费它们，不能据静态250推导声称实测或归因DDS/CPU。

接着应用新显式reset reader登记、运行26项候选检查并在新preflight真正双load及保存receipt，按实际成本前瞻封存下一有界工程块。新数额须标明代理依据用户持续委托作出的决策，承接旧累计账；pilot/final原额、12EP/30roles与95%/安全门保持。继续直到实际学习和三指定final-only strict95出口完成。

## 原预声明（执行前快照）

准备完成，尚未消费原runtime输入。该活动只定位性能，不提供新native资格、学习或95%信用；V50全部FAIL、真实费用与未运行阶段保留。

固定原证据freeze `23e909380b470039bd5680cf2d07710dca71097e`，只取reset worker0的 `episode001_open_101`，epoch `mr3_p2a_reach_v50_reset_w0_e1_58c70a39`。调用原 `audit_reach_runtime.audit_episode(EP, expected_freeze=...)` **恰好一次**，无prewarm、retry或worker集合自动扩展。14份完整逻辑输入及实际编码SHA取V50规范库存；24份旧证据源与旧Git逐字相等，另封9份实际执行源和system Python ELF，scope本身再由新执行Git freeze完整绑定。见[scope](assets/20261023_mr3_p2a_v51_runtime_profile/scope_v1.json)及[准入记录](assets/20261023_mr3_p2a_v51_runtime_profile/scope_admission_v1.json)。

工程入场70121.7738945746018/75000、余额4878.2261054253982。[预算](assets/20261023_mr3_p2a_v51_runtime_profile/budget_admission_v1.json)预约 **900秒＝完整parent主840＋外尾60**，最坏funding后仍余3978.2261054253982；实际仅按完整parent wait及真实提交外尾收费，nested guard/reader不叠加，预留不虚报消费。pilot/final不动。

内部从guard入口起810秒工作截止，TERM10秒/KILL5秒，预留清理；中断、partial、超840或原审计失败均FAIL并完整收费。父TERM/INT只记录，任何wait异常都继续真实wait，不能未reap就退出；OS不可中断I/O可超额，不承诺硬实时。pstats缺失或partial也保留。cProfile会扰动耗时，不声称冷盘或World吞吐。

[人工lifecycle CPU](assets/20261023_mr3_p2a_v51_runtime_profile/checks/lifecycle_cpu_v1/mr3_profile_lifecycle_selfcheck_v1/result.json)6组/4真实owned toy进程全部PASS；包含真实10秒TERM→KILL、清理中重复TERM/INT、wait异常后真实wait、无效scope不启动child及末信号rc1。实际wait10.420628302秒，源前后相等，工程0；旧v1未reap缺口、v2末信号窗口及草稿原件保留。[guard模块help](assets/20261023_mr3_p2a_v51_runtime_profile/checks/installed_guard_help_v1/actual_wait.json)与[driver模块help](assets/20261023_mr3_p2a_v51_runtime_profile/checks/installed_driver_help_v1/actual_wait.json)均实际PASS，无原reader导入或消费。[最终静态review](assets/20261023_mr3_p2a_v51_runtime_profile/preparation_archive/mr3_p2a_single_ep_runtime_profile_v3_driver_independent_review_v1.json)无新阻断。

新执行freeze为包含本计划的实际commit/push。唯一固定入口是本package的 `run_profile_v1 --freeze EXACT40`，cwd为wireless-rl、system Python、清理ROS/conda路径并禁用户site/CUDA；driver保存真实argv和两层receipt，固定 `/tmp/mr3_single_ep_runtime_profile_v51_driver_v1` 与 `/tmp/mr3_single_ep_runtime_profile_v51_work_v1` 独占输出。必须等实际工具退出后，再做driver/outer/guard/child原保存身份freshgone和来源/字节封存；driver PASS不替代该关闭。

完成后依据pstats确定恒等缓存/索引优化，保留全输入、重复/乱序/错误语义和原判据，再实施显式reset接线与真实入口CPU。按实测成本制定新的完整同freeze资格/学习工程块；在用户持续委托下自主规划，不把旧75000账改成“原已批准更大金额”，不自动扩大pilot/final，P2A未完成。
