# V35 讨论输入：原 centre 图与 v2 shortcut 的数学边界

本文仅依据 V34 源码及人工几何推导；未读取、重放或消费真实 rooms 原件，未运行测试、World 或实验，未修改生产代码。它不能证明 V34 rooms tb3 停滞的实际原因。原生 actor 仍为 `exact-point-bridge-v2`，本文不创建 seed v3。

参照源码：

- `ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_observation.py`：`native_traversable`、`_seed_diagnostics`、`_path_distances`。
- 同目录 `mr3_proxy2d_navigation.py`：`_lookahead_cells`、`_exact_goal_velocity`、`_exact_waypoint_velocity`、`target_velocity`。
- 同目录 `mr3_proxy2d_world.py`：当前代理 `RESOLUTION=.05`；这里只读其定义，没有实例化 World。

## 1. 精确 closed-square centre 图的一般公式成立

假设地图是均匀、轴对齐、同分辨率的正方形格，任意非零值（包括 unknown）及地图外部均 blocked；物体位置为格中心，要求距离 blocked closed square 至少 `R=29/100 m`。

若 blocked 格相对待判中心的整数偏移为 `(dr,dc)`，精确平方距离为

```
d_square² = res² / 4 * (
    max(2*abs(dr)-1, 0)² + max(2*abs(dc)-1, 0)²
)
```

将严格满足 `d_square² < R²` 的 offset 置入对称、奇数边长、中心锚定的 Boolean footprint，随后对 `raw_grid != 0` 做一次 `binary_dilation(..., iterations=1, border_value=1, origin=0)`，所得 unsafe mask 的补集即为这个模型下精确的 `centre distance >= R` 图。阈值等号应接受，不能将 `<` 写成 `<=`。`border_value=1` 使外部格视为 blocked，等价于地图外部连续区域不可进入。

footprint 的范围必须覆盖所有可能 unsafe offset；例如每轴取 `K=ceil(R/res+1/2)` 并精确计算内部 predicate 即足够。Fraction 仅用于 footprint 的生成，后续 Boolean dilation 无需对每格运行 Fraction。不得用浮点距离、epsilon、圆形近似 footprint、默认 4 邻域 structure 或 `iterations=0` 替代该定义。

此方法在一般分辨率确实可能修正保守误拒。例如 `res=.1`、offset `(3,2)`：旧下界 `sqrt(13)*.1-.1/sqrt(2) ≈ .2898444 < .29`，精确距离 `sqrt(.25²+.15²) ≈ .2915476 > .29`。

## 2. 但当前 `.05/.29` 的 centre Boolean 图不会改变

令 `a=abs(dr)`、`b=abs(dc)`，先按精确 `res=1/20`、`R=29/100` 推导。旧 EDT 减半格对角线的 unsafe predicate 为

```
sqrt(a²+b²) - 1/sqrt(2) < 5.8
等价于 a²+b² < (5.8+1/sqrt(2))² ≈ 42.34243866
```

新 closed-square predicate 为

```
max(a-.5,0)² + max(b-.5,0)² < 33.64
```

两者对全部整数 offset 得到同一个有限集合：

| a | 旧门 unsafe 的最大 b | 精确门 unsafe 的最大 b |
|---:|---:|---:|
| 0 | 6 | 6 |
| 1 | 6 | 6 |
| 2 | 6 | 6 |
| 3 | 5 | 5 |
| 4 | 5 | 5 |
| 5 | 4 | 4 |
| 6 | 2 | 2 |
| >=7 | 无 | 无 |

负号和交换行列由对称性覆盖。任意地图的 unsafe mask 都是各 blocked 格对应 offset 集合的并集；集合相同，因此图相同，包括外部 blocked 格带来的边界拒绝。实际 binary64 `.05` 与 `1/20` 的差异远小于该集合到阈值的间隔，不是格线 ULP 等号问题：旧最近 unsafe/safe 壳的下界约 `.284801/.300055`，精确对应最近 unsafe/safe 距离约 `.285044/.302076`。

所以，不能预期只把当前 `.05/.29` centre 图换成上述 dilation，就能解除 rooms 的 `seed_cell_body_clearance`。V31 高层报告中的 `.282843` 还是 centre 下界再扣 pose offset 后的 pose 下界；该报告明确原 seed cell 本身可以过门，不能把它改述为 centre 误拒。

## 3. v2 shortcut 可进入下一步不准作起点的格

当前代码只要求起点 cell 和 lookahead 节点通过原 traversable/field 门；选中的 shortcut 整段及实际 20ms proposal 只检查 raw blocked-square 净空。它们没有要求途经的 canonical cells 仍在原图中。下一次 `target_velocity` 又会先查 `traversable[current_cell]`，故存在执行闭环不一致。

以下为人工反例，未执行。此段有限小数先指精确十进制有理数，故可给出精确最小平方距离；binary64 实现应另用人工 fixture 验证，不将下述数学推导伪称为运行结果。各关键净空离 `.29` 有毫米级间隔，未依赖等号或 ULP 边界：

- 地图：`81x81`、`res=.05`、origin `(-1,-1)`，其余全 free，仅 `[0,.05] x [0,.05]` 为 blocked，即格 `(20,20)`。
- 起点 `S=(.325,.175)`，canonical cell `(23,26)`；策略已给目标 `G=(.375,-.425)`，cell `(11,27)`。
- 起点旧 centre 下界约 `.300055 > .29`；目标约 `.534732 > .39`，不会因原 body/target centre 门失败。
- 原无切角下降 route 的前五节点为 `(23,27),(22,27),(21,27),(20,27),(19,27)`；其中心为 `(.375,.175/.125/.075/.025/-.025)`，全部 traversable。
- v2 最远 shortcut 的终点为 `W=(.375,-.025)`。整段 `S→W` 距 blocked square 的最小平方距离是 `2401/27200`，距离大于 `.297 > .29`，因此可通过现有精确几何证书。
- 该线段先进入格 `C=[.30,.35) x [.10,.15)`，即 `(22,26)`。C 的中心 `(.325,.125)` 旧 clearance 下界约 `.280872 < .29`，其真实 centre 距离也仅 `sqrt(.275²+.075²) ≈ .285044 < .29`。所以 C 在旧图和精确 centre 图中都不 traversable。
- 初始 yaw 指向 W，名义 `v=.12,w=0`，固定 20ms 推进约 11 次后即可进入 C；此时离策略目标仍远于 `.10` arrival 门。下次起点检查拒绝，尽管已经走过的线段保持几何安全。

因此“point/segment 安全”与“其 containing cell 的 centre 属于原图”是不同谓词。换成精确 centre 图也不会消除这个一般问题。

## 4. 如果实际诊断支持，再声明独立的 proxy 执行规则

可保持原 native actor v2、candidate graph、任务门及 `.29` 不变，仅前瞻声明独立 `proxy_execution_rule`。最小可证目标是：固定收到地图下，名义局部命令不自行离开原 traversable 图及其合法 route。

候选整段和每个实际 proposal 都需精确枚举沿途 canonical cell 区间，要求全部 traversable、field 有限，并保持原 diagonal 双侧格检查。先沿已有 route 相邻节点执行；保留长 shortcut 时也须通过该图约束。只验端点、只验 lookahead 节点或只验整段几何净空均不足。原几何证书、scan/pair/freshness 门继续合取，不搜索新策略目标。

人工验证至少应覆盖：上述几何安全/图不兼容反例、合法 route 正例、连续多 quantum、yaw 容差使 proposal 偏离已验证整段、格角/格线归属、同 seed 中心桥，以及 legacy/v1/v2 原输出不变的边界。

这只证明固定地图下的名义命令性质。独立 encoder bias 会使估计轨迹偏离名义直线，原地转向也可能产生估计 XY 漂移；收到的新地图也可能令当前格失效。不能借此声称真实估计起点必然可用，更不能借实际失配绕过原图门。实际三帧诊断应先区分名义 proposal 跨图、估计运动偏离、地图更新三种来源，再决定是否实现。
