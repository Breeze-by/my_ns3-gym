# P2C.1 v36 精确准入剪枝组件 PASS

v35冻结7d9709b四个原开发任务整体FAIL：forced200.7s原生COMPLETE、各机器人charge1；lab/rooms EXPLORE timeout300.4/300.3，corridors FOUND timeout300.1、296.2s才检测。四格0接触/耗尽/failed/infra/retry，48独立子门PASS不能替代完整开发成功。原owner/observer自然关闭后才修改，完整原件与严格失败见20261009_p2c_v35_failed_development.md/.json。正式17/物理2/917未调用；旧成功不回填新冻结。

此次用三份精确原ledger弃置行重建完整callback输入，覆盖三机器人混合mapping/visual状态、原地图与本地return grids、source stamps、访问/朝向历史、resume/charge/goals/routes。原固定epoch计算约2.4/3.5/2.4秒，超过原剩余source lease约1.34/1.59/1.41秒；每轮多数昂贵预算最后才因accepted reservation而失败。

新算法保持原稳定贪心顺序和所有硬准入：有实际或临时预留路线时，先生成同body-masked field的原短腿；只在所有当前及未来可能有效前缀都不可用时，才跳过准确gain和完整价格。新增预留只能使第一次冲突向前移动：任一冲突之前仍可能满足原0.75m前缀位移且超过原0.02m位置容差的点都会被保留，故不会因当前终点近乎原地而丢失后续有效前缀。最终仍执行原真实reservation、动态机体、完整body路长/qualified contact return、能量和来源复核。没有预留时沿用原价格流程，保留低电量20候选≤2次完整规划的充电公平性回归。

同field的每条路线均从原escape[0]开始；该点一旦与已有预留冲突，任何候选都无法保留非空前缀，可共用这个不可行证据。不会从真实机器人坐标替代原栅格逃离点。视线布尔结果只在同immutable field内缓存，最多2048条，不保存/简化路径、不续租或保存能量可行决策。原visible-only逐格Bresenham、局部占用veto、全部返回顶点与朝向相同。

测试冻结7d原assign_idle_robots和plan_rally_leg源码与SHA，不以新实现生成期待结果。三份原弃置输入的派发、yaw、相对/多样性偏好、完整储备预算逐项相同；12种随机种子×40条曲线检查false上界在增加任一新预留后仍不会隐藏有效前缀；回环终点反例保留中间有效前缀；8图×24目标逐点路径/朝向与原函数相同，覆盖body与escape。精确布尔memo有界，原充电/真实时钟弃置测试保持。所有私有bound都不进入Nav2、charging forecast或native safety。

| 原弃置输入 | v35中位wall秒 | v36中位wall秒 | 原source剩余秒 |
|---|---|---|---|
| dev_lab101 | 2.38417 | 0.76411 | 1.34400 |
| dev_rooms202 | 3.28726 | 0.65464 | 1.59100 |
| dev_corridors303 | 2.23428 | 0.60396 | 1.40600 |

五轮交错cold/每轮新map和geometry cache，原来源epoch不前进，条件goal sink；不是原history回放或现场callback/最坏时限。初预检查仅None/终点半径检查没有明显普遍改善；任意有效前缀上界及公共起点判断才减少冗余预算。完整保留各原型、首失败检查和中间已通过版本，不只报最快样本。

最终1376功能PASS/86.58s，四包build5.52s，171protected/4既授权/54static与8中央+2native Future注册PASS；七项实际ROS含原clock/Future/视场、普通mapping/visual与两组progressive rally producer-consumer，以及三份原弃置输入的实际中央publisher/独立DDS reader，共三个准确任务witness。源SHA全部绑定；固定原时刻和合成goal sink，无Gazebo/Nav2运动或真实时限保证。v35原48审计细节完全保持，完整strict仍FAIL。

原native battery/action dispatcher/TF/launch/observer/strict reader byte保持；仅control纯plan_rally_leg和assign_idle_robots改变，增加必要前缀上界助手。原300s/5s真实保持、2/5/60s来源TTL、原生储备/能量/SLAM/Nav2/physics/case/真实断网刺激均未改。下一clean pushed freeze先forced原生且每机charge≥1，再其他开发；四格通过才17正式+2物理，917最后首次暴露。P2C.1仍未完成；P3C.5已验收，无P4/ns-3/Wi-Fi/RL。
