# MR3 P2A V36：禁用的实际点接图候选

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
