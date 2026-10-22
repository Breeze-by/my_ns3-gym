# MR3 P2A V36：禁用的实际点接图候选

**40项人工CPU和唯一两帧/六机开发计算闭合PASS；六机均可接图，tb3原格仍false但得到2/4条安全桥。尚未接生产，P2A未完成。**

P2A未完成。依据[V35实际取证](20261022_mr3_p2a_v35_grid_liveness.md)，安全的估计点不一定能安全桥接本格中心；继续要求含点格本身必须是图节点不能解决该初始拒绝。本轮先检验一个独立、禁用的新起点模型，不改生产默认，不启动训练。

## 科学定义

`mr3-point-graph-attachment-3x3-disabled-v1`保留未吸附的received estimated XY。唯一canonical格必须inbounds/raw0，实际点必须通过精确.29m closed-square证书。随后固定枚举canonical周围3×3（裁到图内、不扩圈），只考虑原native_traversable节点；对每个实际点→exact centre整段再做原.29m证书，保留全部合格anchors，按row/col固定顺序输出。没有选择最近一个、探索goal、motion command或写图。

它**替代原含点格准入前提**；原格及centre图数据不改，不能说整个旧可达性模型没变。原含点格可false，新attachment可true，两事实须分别报告。0 anchor继续拒绝，不代表连续空间无路。unknown、非零和outside阻塞/.29阈值保持，真实地图误差、定位/跟踪、peer、scan、物理安全仍未证明。

[禁用代码](assets/20261022_mr3_p2a_v36_point_graph/point_graph_v1.py)及[人工oracle测试](assets/20261022_mr3_p2a_v36_point_graph/test_point_graph_v1.py)无生产调用。27项人工CPU已通过：独立full-grid piecewise-quadratic距离oracle核完整anchor集合；原格false但邻节点安全、原格true但桥中段不安全、无anchor、unknown/outside、canonical二进制边界、严格3×3、输入不变、精确长度、.29等号及两侧等均覆盖。actual-wait 2.294315069秒、源前后稳定，工程0。重放入口13项人工检查亦通过（含actual canonical纯源加载、不读取证据），actual-wait1.565565462秒；合计40项，见[索引](assets/20261022_mr3_p2a_v36_point_graph/checks/index_v1.json)。

## 有限开发重放边界

接下来仅可在新scope/clean pushed freeze下，使用V35已经暴露的固定两份rooms101输入（reset=首次拒绝、last），每份三机各用自己的received navigation map和estimated XY，共6次primitive调用；不解码其他输入、不重读trace、不构造actor/World/episode/奖励/命令。先核原压缩与canonical SHA、元数据及新旧freeze来源，再保留全部6结果；0 anchor是有效负结果，计算闭合与attachment accepted分别报告。

这是已知失败开发样本的局部可用性检查，不是无偏泛化、95%任务、策略可学性或原生资格。成本包括全图验证/EDT和最多9条局部Fraction桥，不能称常数成本或ENV吞吐。[事前scope](assets/20261022_mr3_p2a_v36_point_graph/scope_acceptance_v1.json)总预约60工程秒含外部关闭：main30、cleanup5、external15、buffer10；当前47737.7117251386018/52000、余4262.2882748613982，pilot/final-only不动，75000仍待答。

## 生产前必须解决的条件

若原型及有限重放支持继续，再单独声明新的模式组合：保留v2 canonical `seed_rule`，新增 `start_graph_rule=point-attachment-3x3-v1`，给导航和非导航候选分别新完整版本字典。旧默认分支和旧FAIL保持；新观测保留原seed-cell拒绝及独立attachment结果，不伪造robot_seed_traversable=true。没有anchor时路径全inf，但收到的有效图不应谎报missing。

起点到目标的代价必须为 `min_a[真实桥长(point,a)+原图路径长(a,target)]`，再保留一次目标投影尾段；新模式不再叠加旧seed_offset。全部anchor按目标分别竞争，不能先zero-cost min_only再加最短桥；其他机器人的虚拟点不得成为可借节点。

二维局部执行按策略已给goal的该式选择anchor，沿该attachment和对应原route认证执行段，不强制先精确到centre；到anchor不是新的策略goal/导航终态。每个20ms名义proposal既要满足point→proposal整段.29，还应保留至少一个同目标连接：proposal canonical仍与所选anchor相差≤1，原anchor仍trav/goal-field有限，proposal→同anchor整桥.29。这在固定图/目标且下一点恰等于名义proposal时证明连接不丢失；不证明估计漂移、地图更新、真实plant跟踪或任务成功。

native仍向Nav2发送策略选定的原候选goal，attachment不能变成手工探索兜底或额外Nav2 goal。新模式须逐层绑定launch/worker/supervisor、完整actor输入与快照、qualification/minimum/pilot/final及独立重放。生产接入和完整20100秒原生资格+minimum准入是后续工作，本轮disabled原型不替代这些门。

## 同冻结唯一开发重放实际闭合

新源冻结`49c468e993738a12fe67abde68becaf039e6d991`已clean/pushed后执行一次；原数据evidence7816cced7、原固定选择source47dd6774e。只解码seq1/129两份已知输入，每份三机按自己的navigation map/estimated XY配对，总6计算，保留全部38 anchors。未读取trace、没有actor/World/路径场或运动命令。见[完整原件](assets/20261022_mr3_p2a_v36_point_graph/closed_inventory_v1.json)、[结果摘要](assets/20261022_mr3_p2a_v36_point_graph/closed_findings_v1.json)、[独立静态复核](assets/20261022_mr3_p2a_v36_point_graph/independent_closed_review_v1.json)。

| actor序列 | tb1/tb2/tb3 anchor数 | tb3原含点格 | tb3合格原图节点 |
| --- | --- | --- | --- |
| reset 1 | 8 / 6 / 2 | [101,150], 原trav=false | [101,151], [102,151] |
| last 129 | 9 / 9 / 4 | [106,152], 原trav=false | [105,152], [105,153], [106,153], [107,153] |

这提供本轮新模型在已知拒绝位置上的局部可用性证据，支持继续生产版本设计；并未证明候选/掩码正确、能执行目标、地图质量、95%任务、泛化或学习结果。特别是两帧都已暴露且无active goal，没有回放/选择目标，不能把六个attachment接受率当episode成功率。

source/input前后SHA稳定；main1.730547980秒、final outer0.093639859秒，union1.824187839秒，完整端点2.017525952秒<60，5身份fresh gone（Z按present）。当前累计47739.5359129776018/52000、余4260.4640870223982，见[末账](assets/20261022_mr3_p2a_v36_point_graph/closed_metadata_v1.json)。CPU仍0工程费用，内嵌phase不重复记费，pilot/final-only不动。

下一步按上述条件实现独立显式start_graph_rule的新生产版本、严格输入/候选/计划与审计绑定及CPU。尚不自动运行PPO/完整原生资格。若CPU通过，最多600秒8步profile及1800秒三场64步短probe可分别新freeze/scope在当前余额内提出；这不是重试V34，也不先把新生产版本记为功能已解决。75000工程提案仍待答，20100完整原生资格+minimum不具当前余额准入。
