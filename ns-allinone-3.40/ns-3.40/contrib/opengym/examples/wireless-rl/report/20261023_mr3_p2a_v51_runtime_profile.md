# MR3 P2A V51：单回合独立runtime耗时剖析

准备完成，尚未消费原runtime输入。该活动只定位性能，不提供新native资格、学习或95%信用；V50全部FAIL、真实费用与未运行阶段保留。

固定原证据freeze `23e909380b470039bd5680cf2d07710dca71097e`，只取reset worker0的 `episode001_open_101`，epoch `mr3_p2a_reach_v50_reset_w0_e1_58c70a39`。调用原 `audit_reach_runtime.audit_episode(EP, expected_freeze=...)` **恰好一次**，无prewarm、retry或worker集合自动扩展。14份完整逻辑输入及实际编码SHA取V50规范库存；24份旧证据源与旧Git逐字相等，另封9份实际执行源和system Python ELF，scope本身再由新执行Git freeze完整绑定。见[scope](assets/20261023_mr3_p2a_v51_runtime_profile/scope_v1.json)及[准入记录](assets/20261023_mr3_p2a_v51_runtime_profile/scope_admission_v1.json)。

工程入场70121.7738945746018/75000、余额4878.2261054253982。[预算](assets/20261023_mr3_p2a_v51_runtime_profile/budget_admission_v1.json)预约 **900秒＝完整parent主840＋外尾60**，最坏funding后仍余3978.2261054253982；实际仅按完整parent wait及真实提交外尾收费，nested guard/reader不叠加，预留不虚报消费。pilot/final不动。

内部从guard入口起810秒工作截止，TERM10秒/KILL5秒，预留清理；中断、partial、超840或原审计失败均FAIL并完整收费。父TERM/INT只记录，任何wait异常都继续真实wait，不能未reap就退出；OS不可中断I/O可超额，不承诺硬实时。pstats缺失或partial也保留。cProfile会扰动耗时，不声称冷盘或World吞吐。

[人工lifecycle CPU](assets/20261023_mr3_p2a_v51_runtime_profile/checks/lifecycle_cpu_v1/mr3_profile_lifecycle_selfcheck_v1/result.json)6组/4真实owned toy进程全部PASS；包含真实10秒TERM→KILL、清理中重复TERM/INT、wait异常后真实wait、无效scope不启动child及末信号rc1。实际wait10.420628302秒，源前后相等，工程0；旧v1未reap缺口、v2末信号窗口及草稿原件保留。[guard模块help](assets/20261023_mr3_p2a_v51_runtime_profile/checks/installed_guard_help_v1/actual_wait.json)与[driver模块help](assets/20261023_mr3_p2a_v51_runtime_profile/checks/installed_driver_help_v1/actual_wait.json)均实际PASS，无原reader导入或消费。[最终静态review](assets/20261023_mr3_p2a_v51_runtime_profile/preparation_archive/mr3_p2a_single_ep_runtime_profile_v3_driver_independent_review_v1.json)无新阻断。

新执行freeze为包含本计划的实际commit/push。唯一固定入口是本package的 `run_profile_v1 --freeze EXACT40`，cwd为wireless-rl、system Python、清理ROS/conda路径并禁用户site/CUDA；driver保存真实argv和两层receipt，固定 `/tmp/mr3_single_ep_runtime_profile_v51_driver_v1` 与 `/tmp/mr3_single_ep_runtime_profile_v51_work_v1` 独占输出。必须等实际工具退出后，再做driver/outer/guard/child原保存身份freshgone和来源/字节封存；driver PASS不替代该关闭。

完成后依据pstats确定恒等缓存/索引优化，保留全输入、重复/乱序/错误语义和原判据，再实施显式reset接线与真实入口CPU。按实测成本制定新的完整同freeze资格/学习工程块；在用户持续委托下自主规划，不把旧75000账改成“原已批准更大金额”，不自动扩大pilot/final，P2A未完成。
