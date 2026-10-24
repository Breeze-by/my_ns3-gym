# MR3 P2A V71：masked-cancel完整矩阵资格的软件准备

2026-10-24 V71 masked-cancel软件准备已实际完成、待新执行冻结：新刺激/独立reader已安装，scope True在一切seal前仅作前瞻软件授权；current21 Root50426真reap0/2.201518827秒、21源稳定/两身份gone、ELF同A59，不声称compiler jobs。新fresh ROS212/learner542、入口33及双环境readiness真实PASS；pre-test snapshot xb竞态和首次隐藏CUDA导致device gate FAIL两原件保留，后继未改source/config。真实prepare36700/14.256321161秒与plancheck14624/.470842857秒PASS，新plan1112源/10ELF，12EP30/9probe/authority12要求保持。工程新增0，仍U111365.9618345326018/C180000、余68634.0381654673982，完整47220预约；pilot/final原额和全部旧FAIL保持。下一INDEX逐blob正检查、真实commit/push/clean、exact HEAD正检查后唯一bootstrap；尚无本轮native/资格/学习，capacity/autoPolicy=False，P2A未完成。

新的显式刺激/reader pair为 `mr3-p2a-reach-masked-cancel-v1` / `mr3-reach-reset-masked-cancel-v1`。它在原mask合法取消族中采用显式family/rank调度；GOAL数量、minpath、second_reverse、sum、action排序是新刺激版本，不是控制律等价或物理可用性证明。新masked族取消了旧V3独立的nonapproach工作负载过滤，严格保留原per-robot AND joint masks；这是输入域的显式变化，不复用旧V3资格。nonapproach工作负载过滤不等于原actor mask、安全分离或物理B/R门。原moving .08/path .05、5秒commit、32步/两轮六GOAL、fresh rest/handoff及安全/物理B/R/STOP/95%门保持。

独立reader须从原记录重构interface1+reset8共9个probe EP的真实刺激，并与全部12EP的owned-stream authority、原30科学角色、真实APPLIED及原物理门合取。readiness已真实加载masked helper/profile、独立replayer函数与SOURCE_PATHS闭包；定义加载与CPU证明不替代未来9EP实际重放或原生资格。

| 软件准备活动 | 真实Root tool / rc | 实际child wait秒 | 实际结果 / 绑定数 |
| --- | --- | --- | --- |
| current21增量build | 50426 / 0 | 2.201518827 | 21源稳定，两身份gone，ELF同A59；不推断compiler/link jobs |
| fresh ROS | 35863 / 0 | 51.392758436 | 212PASS，0fail/error/skip；327绑定 |
| fresh learner串行 | 70578 / 0 | 146.381502788 | 542PASS，0fail/error/skip；327绑定 |
| readiness首次 | 30860 / 1 | 7.414518934 | 327源稳定；ROS部分PASS，device gate因Root隐藏CUDA诚实FAIL |
| 双环境readiness v2 | 48224 / 0 | 7.984884747 | 327绑定；system ROS与真实cuda:0两部分PASS |
| entry collect-only | 45048 / 0 | 2.266318039 | 328绑定，只收集新33个case IDs，非测试body信用 |
| 新入口CPU | 52690 / 0 | 9.338504636 | 33PASS，0fail/error/skip；319绑定 |
| prepare | 36700 / 0 | 14.256321161 | 349绑定；真实封plan1112源/10ELF |
| plancheck | 14624 / 0 | .470842857 | 1113绑定；保持12EP/30必要角色及原policy定义 |

Root最初并发提交的learner10951在测试body启动前遭snapshot exclusive `xb` 文件竞态，真实rc1；原异常回执保存在[setup失败](assets/20261024_mr3_p2a_v71_masked_stimulus_qualification/checks/fresh_learner_setup_failure_v1.json)，不能视为542项测试失败或删除。待ROS真实退出后，串行70578在同一source/config下实际通过。随后首次readiness30860因Root继承 `CUDA_VISIBLE_DEVICES=''` 隐藏GPU，ROS JSON已写但device gate拒绝；原[失败wait/console](assets/20261024_mr3_p2a_v71_masked_stimulus_qualification/checks/readiness_cpu_v1/actual_wait.json)与[ROS部分JSON](assets/20261024_mr3_p2a_v71_masked_stimulus_qualification/checks/device_readiness_v1_ros.json)保留。清该环境后用新readiness_cpu_v2输出[device_readiness_v2](assets/20261024_mr3_p2a_v71_masked_stimulus_qualification/checks/device_readiness_v2.json)真实PASS；未改软件源、配置、设备门或使用CPU fallback。

所有真实initial/final tool对象分别见[Root实际tool回收v1](assets/20261024_mr3_p2a_v71_masked_stimulus_qualification/checks/root_cpu_tool_returns_v1.json)与[v2](assets/20261024_mr3_p2a_v71_masked_stimulus_qualification/checks/root_cpu_tool_returns_v2.json)。以上为各自子wait墙时，不相加计入工程实费。独立current/source恢复及保存身份复核：[独立实际复核](assets/20261024_mr3_p2a_v71_masked_stimulus_qualification/checks/independent_cpu_closure_v1/review_result_v1.json)已PASS：六成功组current SHA/bytes/stat与三份Git blob/快照恢复库存逐条核验、12个保存身份freshgone；失败readiness_v1的327源稳定/另2身份gone，collector328源rc0/另2身份gone。10951在测试body/child启动前失败，没有保存child身份，不补造gone。复核工具48660自身真实reap0/2.065222886秒、1154绑定before/after/current相等、own2身份freshgone，工程0，仅属软件来源/回执关闭，不供科学或容量信用。

Fresh baseline仍是 `f466bcf8a205a348ec7c7e7dbfa0125bd4304c56`，封存326个当前Python/50个changed，filesystem union包含未跟踪runtime/tests、masked producer/replay新测试和非test synthetic helper。源码恢复/current匹配、实际argv及每个声明测试模块的真实非skip JUnit均维持。没有拿旧718或私有测试当成新canonical执行。

私有producer_v2的33项/527条原V3差分、reader_v1的39项及其后发现的reset postmath routing遗漏、reader_v2修正后的40项独立保存；不将33+39+40合成新测试数。其2143个普通原件39692800B→8899053B、0link已无损封存，archive CPU63823真实rc0/6.345148922秒/两源稳定/两身份gone，工程0。见[实现历史与恢复说明](assets/20261024_mr3_p2a_v71_masked_stimulus_qualification/checks/history/implementation_v1/README.md)，包含原v1 blocker和v2 forward修正，不重跑候选或延伸旧source-current范围。

Supervisor实际30319B/SHA `94cf3440f6eb8f89d62e110c4f7bcb10300211adb6b5476a91b0e97c49e79dd5`。新current21严格保留原A59 shell/21输入、六加第七compiled宏、FP flags、实际ELF及恢复archive；[manifest](assets/20261024_mr3_p2a_v71_masked_stimulus_qualification/checks/native_build_v1/build_manifest_v1.json)22909B/SHA `5f98068dfdf01e7ab42fa39afd12cad399bac004f38831693f3a71faf4df2706`，[bridge](assets/20261024_mr3_p2a_v71_masked_stimulus_qualification/native_build_bridge_v1.json)2178B/SHA `89f27de5c2d5492a3ac8cd92e25dbc8430b9d9adc520190d2033b4001b7505a2`。增量colcon/同ELF不推断compiler jobs；Python provenance不冒充ELF编译来源，无新gtest/loader/World或科学资格信用。

[真实计划](assets/20261024_mr3_p2a_v71_masked_stimulus_qualification/plan_v1.json)587001B/SHA `5ea54c3c42d73db419e3fb91e0d26bf7bd3839c4270b904ce2ff6ee54bdb5700`；[native binding](assets/20261024_mr3_p2a_v71_masked_stimulus_qualification/native_custody_binding_v1.json)175219B/SHA `9d2f7f1cf19c215dc766ac607b7ffa44555f2ebd63ca54147952984bb23c627b`。这些绑定未来同freeze12EP30、9probe独立证明与authority12要求，尚不提供其实际结果。

规范前账[V70末账](assets/20261024_mr3_p2a_v70_probe_v3_stimulus_description/closure_ledger_v1.json)6688B/SHA `1b354545c34bc4165fc5f6f128f947c09262a7b2945bebf0f589f066963cee7a`仅为received描述PASS：Root88680rc0、完整parent5.806465998，原activity字段为{present:true,value:false}，V69覆盖FAIL及全部旧科学FAIL保持。仍U111365.9618345326018/C180000/R68634.0381654673982、完整47220预约；C是代理依用户持续委托选择，非数值用户批准。pilot余1870决策/2905.9547395464029秒，final-only原900决策/9000秒与open401/402/403保持，不借用。

下一Root force-stage全部selected regular（含ignored console）→INDEX all-source Git blob正检查→commit→真正push退出→显式clean HEAD==origin→在/tmp作exact HEAD正检查，才唯一启动新bootstrap。新执行freeze尚未产生，不预填。matrix child保持python -m，outer -B和清洁ENV保持；完整parent从same-PID bootstrap至post-source/final-absence含gaps计费，nested/root不叠加。47220为完整软费门，原有限合作式native guard和owned cleanup保持；partial/FAIL/unknown与全部实费保存，canonical source/config/docs/index在活动期间冻结至真实Root reap/source关闭。

本入口不自动minimum/PPO/pilot/final。矩阵通过后也须按本轮实际phase/EP/native/audit/coldstart/finalizer/closure成本作容量准入，才独立决定真实minimum、pilot与三strict95；不线性外推短32步，不借final-only额。用户自主持续委托保持，P2A仍未完成。
