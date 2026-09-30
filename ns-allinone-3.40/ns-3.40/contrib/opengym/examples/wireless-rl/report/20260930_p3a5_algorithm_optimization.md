# P3A.5 后续算法优化记录

日期：2026-09-30
代码提交：`d340ba3`
状态：优化候选，尚未重新冻结 `task_stack_frozen_commit`

## 目标与问题

本轮继续处理 P3A.5 的探索和充电协同问题。当前故障的直接原因是：探索目标规划只在部分条件下保留其他机器人的位置约束；一个目标完成后，原有的初始信息增益会被清除，停驻机器人可能不再被当作动态障碍物。这样规划出的路径可能把机器人送进被另一台机器人占据的窄通道，导致探索碰撞或后续集合路线无法重规划。

本轮没有改变 COMPLETE 判定、网关通信边界或网络/RL 接口，只调整探索路线准入和电池返航期间的派发时序。

## 算法改动

- 在实际调用 `plan_rally_leg()` 时，把其他参与机器人的当前位置作为动态障碍物，并使用现有的 `PATH_CLEARANCE_M` 检查整条路线，而不是只检查候选点。
- 继续限制同一时刻只有一条新的探索路线处于派发状态。地图更新是异步的，单路线可以避免机器人在两次地图更新之间互相封锁；已有集合路线仍使用原有的路线保留逻辑。
- 任一机器人处于 `RETURNING` 时，不再派发新的探索路线；启用全局电池暂停时，只有所有机器人回到 `ACTIVE` 后才允许继续派发集合路线。
- 增加两个回归测试：窄通道被停驻机器人封锁时必须拒绝路线；前一个目标完成后，新的探索路线仍必须避开停驻机器人。

## 自动验证

在 ROS 2 Humble 环境执行：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
/usr/bin/python3 -m pytest -q \
  src/multi_robot_exploration/test/test_control.py \
  src/multi_robot_exploration/test/test_gateway.py \
  src/multi_robot_exploration/test/test_battery_manager.py \
  src/multi_robot_exploration/test/test_task_evaluator.py \
  src/multi_robot_exploration/test/test_fault_model.py
colcon build --symlink-install --packages-select \
  multi_robot_interfaces multi_robot_exploration merge_map multi_robot
python3 -m py_compile \
  src/multi_robot_exploration/multi_robot_exploration/control.py
```

结果：`80 passed`，4 个 ROS 包构建通过，Python 语法检查通过，`git diff --check` 通过。

## Gazebo 证据

### 定向三机器人回归：通过

命令使用 `my_world.world`、seed 101、初始能量 40、目标 `(-4, 4)`、全局电池暂停和单路线派发。完整输出在：
`ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a6_safe_candidates_lab101/`。

结果文件为 `p3a6_safe_candidates_lab101.json`：

- `success=true`，`task_phase=COMPLETE`，`termination_reason=task_complete`；
- 198.7 s 完成，89.9 s 发现目标，98.5 s 进入集合；
- `collision_events=0`，总充电 0 次，最低能量 20.51；
- 三台机器人都保持 `ACTIVE`，集合位置误差均小于 0.21 m。

这是对停驻位置避让修复的定向证据，不替代固定十格 P2D/P3A 矩阵。

### 强制充电回归：未通过，但充电闭环有效

命令使用 `my_world.world`、seed 303、两台机器人、初始能量 18、目标检测、强制充电和全局电池暂停。完整输出在：
`ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a6_forced_charge_parked_fix_seed303/`。

结果文件为 `p3a6_forced_charge_parked_fix_seed303.json`：

- 300.2 s 超时，仍在 `EXPLORE`，未发现目标，不能计作 `COMPLETE`；
- 两台机器人各完成 1 次返航和充电，共 2 次充电；
- `collision_events=0`，最低能量 9.288；
- 两台机器人均恢复为 `ACTIVE`，说明返航、充电和任务恢复链路工作，但探索路线在本时限内没有覆盖目标位置。

### 并行探索试验：中断

曾将探索路线并发上限临时改为 2，运行三机器人 seed 101 试验。日志显示两条路线可以被准入，之后 tb2 触发返航并完成充电，但 tb3 长时间等待安全路线；评估窗口结束前进程被中断，没有生成 episode JSON。因此并行版本没有进入最终提交，当前提交仍使用单路线策略。原始日志保留在：
`ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a6_parallel_lab101/`。

## 结论与下一步

`d340ba3` 解决了一个明确的探索碰撞根因，并在三机器人定向回归中得到 `COMPLETE`/零碰撞结果；`9025b38` 又把长返航改为短段重规划，使强制充电回归完成两次充电并找到目标。由于目标发现较晚，严格 RALLY `COMPLETE` 仍未通过，固定矩阵也尚未重新执行。因此当前不能宣称 P3A.5 新优化已冻结，也不能进入 ns-3 时间/数据包耦合或 RL 训练。下一步应针对 seed 303 的目标区集合起点和剩余时间做小范围诊断，再决定是否扩大正式矩阵。

## 后续返航短段修复（`9025b38`）

上一轮诊断发现，电池管理器虽然注释说明使用短腿返航，但实际把 `max_distance_m` 设为无穷大，一次性把整段返航交给 Nav2。tb2 在长返航段反复报告 `Failed to make progress`，最终触发 `battery_return_unreachable`。本次把返航规划改为使用 `MAX_NAVIGATION_LEG_M` 的短段；每个短段成功后重新基于最新地图规划下一段。

组件验证仍为 `80 passed`，4 个 ROS 包构建通过。新的两机器人 seed 303 回归输出在：
`ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a6_short_return_forced303/`。

结果文件 `p3a6_short_return_forced303.json`：

- 两台机器人各完成 1 次返航和充电，共 2 次充电；
- `collision_events=0`，最低能量 8.214，最终两台均为 `ACTIVE`；
- 目标在 256.3 s 被确认，随后进入 RALLY（267.6 s）；
- 300.1 s 时仍在 RALLY，未完成集合，`success=false`；
- 失败原因已不再是电池返航不可达，而是目标发现过晚后剩余集合时间不足，且首个集合目标曾被 Nav2 报告起点处于 lethal space。

因此短段返航修复有效，但严格强制充电 `COMPLETE` 门禁仍未通过。
