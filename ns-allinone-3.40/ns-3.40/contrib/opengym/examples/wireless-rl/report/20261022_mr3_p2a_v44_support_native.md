# MR3 P2A V44：显式support证书与新冻结完整链

2026-10-22预声明。用户要求自主执行直到P2A完成，不再询问一般修改批准；原V41物理/reader失败与V42描述取证限制保留。V43的124人工检查及独立数学审查只支持条件集合分离结论，本活动必须取得全新的原生、学习和最终任务证据。P2A当前未完成。

## 实际闭合：preflight FAIL，未启动native

唯一活动冻结`8b678c631cb5f7dfc1ba1174882e765d4672ab26`已push；实际driver reaped rc1、completed_stages=[]。preflight回执actual_waited=true、rc1、source_unchanged=true，报`ValueError: current original CPU evidence differs from the frozen plan`；未生成preflight PASS结果，matrix/World/native及minimum/pilot/validation全部未启动，0学习/0optimizer。此次是准备证明分类一致性失败，不是support数学、物理plant或任务失败；下方7次人工准备PASS与首轮fixture失败均保留原结论。

提交后3个新ROS测试进入source_inventory，current_runtime_and_test_sources_checked计数比提交前增3，导致完整proof比较不等；830项计划source及生产SHA没有漂移。保留严格source/CPU准入门，下一V45只修提交前后稳定分类及人工回归，再用新freeze重新准入，不重试或改判本V44。

完整parent实际wait7.010229336秒，inner6.004885052秒包含不重复收费；工程累计50048.2440707956018/75000、余24951.7559292043982，pilot/validation各新增0，原1870决策/2905.9547395464029秒及final-only401/402/403保持。唯一实际输出为/tmp/mr3_p2a_reach_v44_driver_v1与/tmp/mr3_p2a_reach_v44_preflight_wait；[无损库存](assets/20261022_mr3_p2a_v44_support_native/closed_inventory_v1.json)和[canonical副本](assets/20261022_mr3_p2a_v44_support_native/closed_execution)保留5份原件/677367B，源stat稳定、逐项SHA相等，纯包装0工程费。[独立关闭review](assets/20261022_mr3_p2a_v44_support_native/independent_closed_review_v1.json)PASS：841个outer绑定源/ELF before-after/current完全一致，830项repo源＋plan共831项与Git冻结相等；driver/wrapper/child三组保存PID/start均freshgone（Z仍计存在），未虚构未保存父身份。只认可7.010229336秒parent费用，pilot/final为0。本轮无新native资格或P2A信用，用户自主授权继续，P2A未完成。

[首次静态计划review](assets/20261022_mr3_p2a_v44_support_native/final_plan_review.json)因把所有auxiliary job都要求required而误报reset；[纠正版review](assets/20261022_mr3_p2a_v44_support_native/final_plan_review_v2.json)按历史辅助physical_per_episode与必要聚合physics角色关系核查后PASS，源码/计划未为此改变，两个原件均保留。纠正静态审查不等于实际preflight通过，不覆盖本次真实FAIL。

## 准备阶段结果：第二轮人工CPU全部通过

第一轮原件及失败结论如下文保留；两处人工fixture已修复，生产存储屏障、原生冻结来源门及旧cf46几何源码未放宽。第二轮独占v2输出均真实reap、rc0、source_unchanged=true，合计746项人工检查，readiness另计双环境元数据；人工CPU工程费0。

| 组 | 实际结果 | child实际等待 | 原始回执/console |
|---|---|---|---|
| geometry_cpu_v2 | 523 PASS | 47.51967478s | [actual_wait](assets/20261022_mr3_p2a_v44_support_native/checks/geometry_cpu_v2/actual_wait.json) / [console](assets/20261022_mr3_p2a_v44_support_native/checks/geometry_cpu_v2/console.log) |
| learner_cpu_v2 | 202 PASS | 60.411545013s | [actual_wait](assets/20261022_mr3_p2a_v44_support_native/checks/learner_cpu_v2/actual_wait.json) / [console](assets/20261022_mr3_p2a_v44_support_native/checks/learner_cpu_v2/console.log) |
| reader_cpu_v2 | 12 PASS | 4.281579034s | [actual_wait](assets/20261022_mr3_p2a_v44_support_native/checks/reader_cpu_v2/actual_wait.json) / [console](assets/20261022_mr3_p2a_v44_support_native/checks/reader_cpu_v2/console.log) |
| snapshot_cpu_v2 | 9 PASS | 9.289128831s | [actual_wait](assets/20261022_mr3_p2a_v44_support_native/checks/snapshot_cpu_v2/actual_wait.json) / [console](assets/20261022_mr3_p2a_v44_support_native/checks/snapshot_cpu_v2/console.log) |
| readiness_cpu_v2 | system ROS/conda learner双环境PASS，未创建Node/model | 7.951573978s | [actual_wait](assets/20261022_mr3_p2a_v44_support_native/checks/readiness_cpu_v2/actual_wait.json) / [console](assets/20261022_mr3_p2a_v44_support_native/checks/readiness_cpu_v2/console.log) |

[CPU索引](assets/20261022_mr3_p2a_v44_support_native/cpu_validation_index_v1.json)绑定本轮证据。真实system子进程用当前必要源码建立临时隔离Git冻结，人工1snapshot/7map完整重建通过，并实际拒绝副本supervisor字节篡改；仍执行原reader全部source匹配和固定pointgraph helper pin。system NumPy1.21.5/SciPy1.8.0，conda未混装SciPy；该人工冻结不是任何正式native证据。

[独立几何/接线审查](assets/20261022_mr3_p2a_v44_support_native/independent_geometry_integration_review_v1.json)PASS；[入口审查](assets/20261022_mr3_p2a_v44_support_native/independent_entry_review_v1.json)的passed_static_review=true是预v2路径别名/当时源码的静态审查，不能称其全部SHA仍与最终准备树一致。后续v2实际CPU提供各自锁定源的验证，plan准入已由下方两份实际回执独立完成，新freeze仍待封存。当前未启动V44 World/native/PPO，工程仍50041.2338414596018/75000、余24958.7661585403982，预约20900；P2A未完成。

## 计划准备与封存检查

[prepare_plan_cpu_v1](assets/20261022_mr3_p2a_v44_support_native/checks/prepare_plan_cpu_v1/actual_wait.json)真实PASS，child2.206919836秒，生成830 source/10 ELF/3 policy；[plan_check_cpu_v1](assets/20261022_mr3_p2a_v44_support_native/checks/plan_check_cpu_v1/actual_wait.json)真实PASS，child.365967683秒，核四native stage/12EP/30必要角色及minimum/pilot/validation全部显式cone-support-v2。两组source稳定，连同上方五组共7次准备actual wait均PASS；没有World/native/训练信用，工程费0。

| 封存输入 | 字节数 | SHA256 |
|---|---|---|
| [plan_v1.json](assets/20261022_mr3_p2a_v44_support_native/plan_v1.json) | 226638 | `2a799060f541620072a3fdf16cb530c71d6664992c8b9a9d1f280795fdc2e75f` |
| [native_custody_binding_v1.json](assets/20261022_mr3_p2a_v44_support_native/native_custody_binding_v1.json) | 129741 | `3457393d7f9b9917cfafa1f332628414e77c41f92e3bc91385da3cd7c9153150` |

计划含全部必要当前生产/测试来源；actual custody binding绑定必需生产来源和ELF，不要求无关测试源码角色。准备证明不复用旧native结果；下一步待本活动新commit/push精确freeze后才执行真实preflight及条件完整链。

## 实施与一致性

新增显式`reach_geometry_rule=cone-support-v2`，缺省`binary-cone-v1`保持原算法与输出；原geometry完整SHA cf46b49f0740f84511f3d34f9a8eb3e56720744515d9eea1dc81bd8bacb85f0a不改。新生产helper复用已测数学，独立reader另行实现；当前/prospective两次生产检查与allow/component-filter两处重放均按同一显式选择。plan、全部原生/三阶段policy argv、实际worker/Node配置、metadata、source/custody和资格必须一致。

固定三机器人；保留原Reach集合、D/H/R、误差、源龄、两frame、硬门、物理/接触、95%/300秒与参与/质量条件；不改actor、候选、reward、intent wire或加入手工探索兜底。具体数学见[契约](../MR3_REACH_CONTRACT.md)和[V43](20261022_mr3_p2a_v43_support_geometry.md)。

## 一次新活动及预算

[scope](assets/20261022_mr3_p2a_v44_support_native/scope_v1.json)和[预算](assets/20261022_mr3_p2a_v44_support_native/budget_acceptance_v1.json)以入场工程50041.2338414596018/75000、余24958.7661585403982为准；完整资格18000、工程外尾300、minimum1800，共20100，准备/有限取证另800，总预约20900；未预约余4058.7661585403982。只记实际完整parent wait，嵌套子回执不重复收费，所有失败也保留和收费。

一次同freeze四stage/12EP/30必要角色完整原生资格通过并完成真实退出核验后，才执行16样本minimum与正更新；minimum全部独立门通过后才pilot，取得合格final.zip后才三场final-only open401/402/403。pilot仍限1870决策/2905.9547395464029秒，final-only总900决策/9000秒；每场仍需严格95%任务成功。它们的完整主程序和外尾费都各记原scope，不能挪入工程。所有stage和源在运行前封存；链闭合前不改源或中途commit。

[prepare_plan_v1.py](assets/20261022_mr3_p2a_v44_support_native/prepare_plan_v1.py)仅封存来源/ELF与活动计划；[execute_chain_v1.py](assets/20261022_mr3_p2a_v44_support_native/execute_chain_v1.py)真实wait全部已提交子进程、保留失败、条件放行并收口身份/实际费用。既有输出不得覆盖；原活动不重试/补样。ELF只能在原编译源和完整字节完全相同时复用，旧原生结果不复用。

## 第一轮人工CPU（原件保留，尚未全部通过）

五组均在`99e4273bb5037fce47fe09a406565b81e5375622`基线的未提交实现树执行；新源精确快照与before/after记录保存在[checks](assets/20261022_mr3_p2a_v44_support_native/checks)。每组都真实wait、source_unchanged=true，人工CPU工程费0。

| 组 | 结果 | child实际等待 |
|---|---|---|
| geometry_cpu_v1 | 517 PASS/6 FAIL，共523；旧motion phase fixture的ReachGuard缺少现有storage barrier所需reach字段 | 49.935390431s |
| learner_cpu_v1 | 202项中1 FAIL；人工system replay仍用旧472冻结，新supervisor源被正确拒绝 | 58.064545459s |
| reader_cpu_v1 | 12 PASS | 4.592227215s |
| snapshot_cpu_v1 | 9 PASS | 9.146108383s |
| readiness_cpu_v1 | ROS/learner canonical imports及cuda元数据PASS，未建model/Node | 9.647735107s |

两处fixture须修复后以新的独占v2输出重新验证；生产存储屏障及冻结来源门不放宽，失败原件不覆盖。独立source/数学接线审查无阻断，仍不能用人工CPU替新原生资格。工程及pilot/final余额未动。

## 本次唯一实际入口（已闭合FAIL）

cwd=canonical wireless-rl；以下活动已按新freeze实际执行，preflight失败后退出。

```text
rtk proxy env PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES=0 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m report.assets.20261022_mr3_p2a_v44_support_native.execute_chain_v1 --freeze 8b678c631cb5f7dfc1ba1174882e765d4672ab26
```

实际preflight失败和费用如顶部闭合段所列；未启动World/native/optimizer或产生任务结果。人工准备检查成功不提供原生信用；后续须新V45活动的完整独立准入。P2B/gateway未开始。
