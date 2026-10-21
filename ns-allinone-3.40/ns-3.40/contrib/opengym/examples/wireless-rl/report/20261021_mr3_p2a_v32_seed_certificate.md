# MR3 P2A V32 禁用的精确起点/桥证书CPU原型

**14个人工CPU检查通过，原型保持禁用；没有修改生产观测、掩码、导航或默认mapper。** V31已经完整跑完三场300秒工程链，任务0/3；有限原件诊断指出own/navigation给rooms起点约.282843m保守下界，小于原.29m。这里将下一科学候选做成可审阅代码，不能据人工PASS称实际rooms已修复。

[事前计划v1](assets/20261021_mr3_p2a_v32_seed_certificate/predeclared_plan_v1.json)只允许人工图CPU、最多4096格，没有World/scene/原件回放/SDK/actor/GPU/PPO或工程消费。复用原mr3_reach_geometry.exact/point及Fraction；新增[原型](assets/20261021_mr3_p2a_v32_seed_certificate/seed_certificate.py)只接受received-grid模型、原estimated XY、原seed cell及调用方已计算的原seed_cell_traversable。阈值精确29/100m，略严于binary64(.29)，不减margin；unknown/非零cell的整块闭square和map exterior均阻挡。

证书检查估计点到所有阻挡物的最短距，以及估计点→**同一原seed-centre整条线段**的最短距。使用有理slab交叉判定、端点到矩形/角点到线段的精确平方距，展示float不参与决定。原seed-cell门False仍拒绝，pose不在原cell仍拒绝，没有换seed、snap、图改写或清占据。调用方的freshness/epoch/source与原cell归属/图门仍须在未来保留；本原型信任其输入，不独立重验这些条件。

[人工测试](assets/20261021_mr3_p2a_v32_seed_certificate/test_seed_certificate.py)包括：41²人工图中原cell已traversable、原pose下界.2828427124失败，而精确point/bridge均≥.29；真正point不足/unknown/nonfree仍失败；闭角点/相切；两端点距离都≥.29但桥中段距离²=.083205<.0841必须拒绝；地图外/闭边界/近边界、不同seed不snap、原cell门False保持拒绝和非法数值。人工正例只证明这种假阴性确实可能，不是V31九份真实图的证书或修复证明。

首次运行13pass/1fail：人工numpy.float64 offset被复用exact()的严格builtin float/int/Fraction输入门拒绝，原candidate算法未错判距离。原测试源码和rc1回执保留；仅将fixture值显式转builtin float（同binary64数值）后，第二启动因我将canonical setup路径漏写ros2_ws而在收集前rc2，亦完整保留。[v2](assets/20261021_mr3_p2a_v32_seed_certificate/predeclared_plan_v2.json)/[v3](assets/20261021_mr3_p2a_v32_seed_certificate/predeclared_plan_v3.json)事前记录这两项修订；第三启动使用正确canonical路径及bash -e，14pass/rc0/实际wait/source稳定，outer2.148375849秒。前两次outer3.074038672、1.720518848秒；全部为纯CPU，不产生工程费用或任务信用。

独立只读数学审查未见实质错误，确认桥中段检查、outside四闭半平面、non-free整块square与原cell gate必要。当前全格Fraction枚举/4096格上限只适合人工CPU，不能直接扩大上限塞进World；真实模式需可审计的局部空间界/性能设计，保留原state/map/seed-cell图门，只针对seed_pose_body_clearance分支提出新证书版本。

后续具体工作：先设计显式版本和原观测兼容/必要资格，不删除或绕过proxy2d_conformity对V21纯源逐字门；新seed/candidate/mask资格属于科学规则变更，不能称纯性能修复或继承V31资格。当前证书只约束数值received-grid，不证明physical pose、传感/跟踪误差或原生安全。不得用它放行原seed_cell_body_clearance拒绝、自动找邻居/手工兜底，亦未证明coverage/quality已恢复。完成版本与CPU准备后再声明新的有限验证；不重跑V31、启动PPO、迁移native或扩预算。

工程仍46691.4127443736018/52000，余5308.5872556263982秒；pilot1870/2905.9547395464029和final-only401/402/403不动。P2A仍未完成，常规实现/CPU可继续直接推进；二维训练和原生资格仍不能从本原型解锁。
