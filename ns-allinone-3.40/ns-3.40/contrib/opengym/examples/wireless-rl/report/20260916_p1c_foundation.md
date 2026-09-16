# ROS 2 P1C 协同探索基础修复与 90% 基线报告

日期：2026-09-16

## 结论

P1C 在不修改 world、真值栅格、覆盖率定义和成功规则的前提下，已从缺陷修复前的
75%–80% 平台提升到稳定超过 90%。当前建议验收条件为：2 台机器人、理想通信、
`my_world.world`、正确自由空间覆盖率 90%、180 仿真秒上限。

最终 seeds 101/202/303 均达到 90%，180 秒终值为 93.87%/93.90%/93.88%。三轮均
零碰撞、零搜索重叠；51 个在截止前结束的导航目标中 50 个成功、1 个取消、0 个 abort。
这说明此前达不到 90% 不是地图不可探索，也不是应当降低评价门槛，而是定位、启动、
探索调度和目标安全性存在可修复的基础问题。

## 根因

1. 自定义 `multirobot_slam_toolbox` 的 laser callback 没有保存 `scan_header`。地图仍能
   更新，但 TF 发布线程因时间戳始终为 0 而不发布 `map→odom`。
2. 建图 launch 同时无条件启动 AMCL。AMCL 暂时掩盖了 SLAM TF 缺失，又与 SLAM 形成
   两个 `map→odom` 来源；运行时曾观测到 odom 位置约 `(-0.15,-2.79)`，TF 地图位置却约
   `(4.7,3.7)`。
3. 探索控制器直接把 `/tbN/odom` 当作 map 坐标做 Dijkstra，因而会把断开的前沿误判为
   可达；Navfn 的连续失败是结果，不是首要根因。
4. 每个前沿组只保留一个目标，多机器人在一个大前沿上无法从不同方向并行推进。
5. 最近前沿搜索对“候选栅格 × 整组前沿点”做 Python 二次循环，初始大前沿会阻塞控制器
   约 30 秒。
6. nested `ros2 launch merge_map` 在 smoke 退出后会遗留 publisher；最多观测到三个
   `/merge_map` publisher，后续 episode 会消费旧地图。
7. 0.35 m 目标净空对 Waffle 的边缘/狭窄区域偏小，长 episode 后会出现 Navfn 无路径或
   DWB no-progress。

## 修复

- SLAM callback 恢复 scan header，建图模式禁止 AMCL，只由 SLAM 发布 `map→odom`。
- 控制器订阅每台机器人的 `/tbN/tf`，先把 odom 位置转换到 map 坐标，再在该机器人的
  本地 SLAM 地图上验证已知自由空间连通性。
- 中央协调器为每个前沿保留多个相距至少 1.2 m 的安全观察点，用 `/merge_map` 的未知
  栅格信息增益统一评分；一次为所有 idle 机器人选择互不冲突的目标。
- 候选生成改为从前沿点枚举 0.8 m 有限邻域，避免全图二次搜索；允许在已验证连通时执行
  最长 12 m 的跨区任务。
- 最终观察点要求 0.45 m 障碍净空，路径连通判断使用 0.23 m 净空；Nav2 使用 A*、允许
  穿过 unknown，最终目标仍必须位于已知自由栅格。
- `merge_map` 按分辨率和世界原点对齐各 OccupancyGrid，以向量化 NumPy 合并；unknown
  仅在无人观测时保留，冲突 free 优先以清理动态机器人残影。frame 固定为 `map`，topic
  固定为 `/merge_map`。主 launch 直接拥有节点，退出时不遗留子进程。
- Nav2 在 spawn 后 10 秒开始并按机器人错峰 45 秒；删除当前探索行为树不使用的
  `smoother_server`，保留 `velocity_smoother`，降低 lifecycle 转换超时。

## 迭代证据

固定 seed 101 的代表性演进如下。所有覆盖率都是 evaluator 的
`correct_free_coverage_ratio`，没有改变评价逻辑。

| 版本 | 时长 | 覆盖率 | 路径 | 导航结果 | 结论 |
|---|---:|---:|---:|---:|---|
| v8 | 120 s | 62.15% | 10.66 m | 5/5 success | TF/AMCL 修复后导航正确，但单候选导致串行等待 |
| v9 | 120 s | 69.83% | 8.62 m | 7/7 success | 同组多观察点有效，但硬领地规则让 idle 机器人等待 |
| v10 | 120 s | 71.58% | 16.70 m | 8 success，1 active | 删除硬领地后路径翻倍 |
| v12 | 120 s | 73.42% | 18.50 m | 11/11 success | 前沿计算优化后持续调度；末期受 6 m 任务半径限制 |
| v13 | 180 s | 75.51% | 23.68 m | 14 success，3 cancel | 12 m 跨区有效，但边缘目标净空不足 |
| v14 | 180 s | 93.87% | 36.46 m | 17 success，2 active | 0.45 m 安全观察点消除边缘卡死并达到目标 |

## 三种子结果

命令形式：

```bash
python3 scripts/ros_smoke_test.py \
  --robot-count 2 --gazebo-seed SEED \
  --evaluation-duration 180 --evaluation-wait-timeout 270 \
  --episode-id p1c_coop_v14_safe_targets_seedSEED
```

| Seed | 180 s 覆盖率 | 到 90% | 路径 | success/cancel/abort | 碰撞 | 重叠 |
|---:|---:|---:|---:|---:|---:|---:|
| 101 | 93.87% | 141.3 s | 36.46 m | 17/0/0 | 0 | 0 |
| 202 | 93.90% | 161.4 s | 43.08 m | 17/1/0 | 0 | 0 |
| 303 | 93.88% | 134.9 s | 42.87 m | 16/0/0 | 0 | 0 |
| 平均 | 93.88% | 145.9 s | 40.81 m | — | 0 | 0 |

`nav_goal_count` 总计 56，其中 50 success、1 cancel、0 abort，另 5 个在 180 秒截止时仍
active；因此已结束目标成功率为 98.0%。平均 observed accuracy 为 97.12%。

## 验收口径与限制

- 600 秒不再必要：最慢 seed 在 161.4 秒达到 90%，180 秒保留约 18.6 秒余量。
- 当前证据支持 90%/180 秒，不支持声称稳定达到 95%；三轮均未在截止前达到 95%。
- 当前地图已知冲突采用 free 优先，适合清除动态机器人残影，但 occupied IoU 仍只有
  0.24–0.28；后续若研究墙体精度，应引入时间衰减/置信度融合，而不是改变覆盖率真值。
- 当前仍是 ideal/unlimited communication：中央节点直接读取所有地图、TF 和里程计。
  只有在用户验收 P1C 后，才进入目标检测、状态机和通信因果闭环。
