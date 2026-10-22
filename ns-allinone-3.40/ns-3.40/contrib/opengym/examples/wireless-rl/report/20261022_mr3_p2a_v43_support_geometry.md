# MR3 P2A V43：禁用support几何候选的数学与CPU收口

2026-10-22。用户已授权自主持续完成P2A，无需重复一般批准。V43为禁用的显式新科学几何候选，人工CPU及独立逐行数学review均通过；**没有生产/native/plant/PPO或95%信用**。V41原FAIL和V42描述提取的选行省略、跨文件时钟限制保持。

[scope](assets/20261022_mr3_p2a_v43_support_geometry/scope_v1.json)以`02ceec45efff1cb4de85779e07abe4d41d530243`为源码基线；新候选在有source recovery/快照的工作树进行人工验证，不把新文件冒称该旧Git冻结已验证。原`mr3_reach_geometry.py`完整SHA仍为`cf46b49f0740f84511f3d34f9a8eb3e56720744515d9eea1dc81bd8bacb85f0a`，旧pair_certificate、默认规则、Reach集合和intent语义逐字保留。

候选[源码](assets/20261022_mr3_p2a_v43_support_geometry/support_prototype_v1.py)与[推导](assets/20261022_mr3_p2a_v43_support_geometry/derivation_v1.md)对同一原Reach集合计算reported-line support的保守上界；96-bit有理根区间、原认证三角界、方向union取max，原外加U和2R/4R reserve保留，raw/map两frame仍分别合取。独立review核准条件充分分离及“旧PASS蕴含新几何PASS”，并明确它不是旧二值规则的恒等替换、精确距离求解器或连续物理模型证明；浮点采样oracle仅用于找实现错误。

## 实际人工结果

| 证据 | 结果 |
|---|---|
| [actual wait](assets/20261022_mr3_p2a_v43_support_geometry/checks/support_geometry_cpu_v1/actual_wait.json) / [原console](assets/20261022_mr3_p2a_v43_support_geometry/checks/support_geometry_cpu_v1/console.log) | support人工反例＋原geometry回归共124 passed；真实child wait5.698039134秒、rc0，11源before/after稳定；工程费0 |
| [source recovery](assets/20261022_mr3_p2a_v43_support_geometry/checks/support_geometry_cpu_v1_source_recovery.json) | 旧Git blobs与新候选/推导/test/runner精确源码快照均可恢复，不覆盖已测试字节 |
| [独立数学review](assets/20261022_mr3_p2a_v43_support_geometry/independent_math_review_v1.json) | PASS，blocking_findings=[]；逐行核root/norm/uncertainty单位、origin/union、相对符号、hard gates、两frame及旧PASS蕴含；未执行测试/consumer或读取原trace |

实际人工child argv（cwd=wireless-rl）：

```text
/usr/bin/bash --noprofile --norc -e -c 'source /opt/ros/humble/setup.bash && source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash && exec /usr/bin/python3 -B -m pytest -q /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261022_mr3_p2a_v43_support_geometry/test_support_prototype_v1.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_reach_geometry.py'
```

完整原argv/等待/来源见actual-wait，不能将124项重复拆成额外独立实验或把5.698秒计为World费用。工程新增0，累计仍 **50041.2338414596018/75000**，余 **24958.7661585403982**；pilot/final-only额度保持。

## 下一步V44的精确边界

用户自主授权有效，继续显式`reach_geometry_rule='cone-support-v2'`生产接线与独立重放；旧默认明确为`binary-cone-v1`，默认argv/kwargs/metadata新增字段省略。新规则正交seed/start_graph，不改cf46旧几何或安全intent schema，不让generic `mr3-reach-v1`静默认领新数学信用。

[完整接入清单](assets/20261022_mr3_p2a_v43_support_geometry/future_integration_inventory_v1.md)重点覆盖plan→四资格stage及minimum/pilot/final→supervisor/reset→worker→真实ROS Node→tracker当前/prospective证书，以及独立runtime reader的allow/component-filter两处pair重放。新module、reader、metadata/config与freeze/source pin必须一致；所有旧物理/来源/关闭/任务门继续必要。人工接线/数学检查完成后，必须以新freeze取得完整原生资格，才可依门继续最小学习/验证；本轮CPU不能跳过该资格或追认V41。

当前候选仍禁用，生产接线是下一活动；尚无新物理运行、正更新、final模型或三场final-only95%任务成功。P2A未完成，P2B/gateway未启动。
