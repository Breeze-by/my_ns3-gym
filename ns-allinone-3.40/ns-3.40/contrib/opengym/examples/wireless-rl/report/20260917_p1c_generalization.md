# P1C 跨地图泛化验收

日期：2026-09-17

## 结论

P1C 不再只由 `my_world.world` 支撑。项目新增三张面积同量级、拓扑不同且未参与算法调参的
静态地图，并在不修改探索控制器、Nav2 参数、真值栅格、90% 覆盖定义、机器人速度、lidar
或碰撞统计的前提下，完成 3 机器人 3 地图 × 3 seeds 的正式验证。

九轮全部达到 90%，最坏 `time_to_90` 为 75.5 秒，低于 3 机器人的 90 秒验收线；全部零碰撞，
最低观测准确率 97.47%，最大搜索重叠 1.91%。额外在最难地图/最坏 seed 上运行两机器人，
`time_to_90=85.5` 秒，低于 120 秒线且零碰撞。因此没有证据支持继续修改探索算法。

这些结果证明当前实现不是只对一张地图坐标过拟合，并覆盖三类代表性室内几何；它不构成对
任意尺寸、不可通行、动态或低于机器人净空地图的数学保证。更大规模随机地图、动态障碍和
分布外场景仍属于后续 P7 泛化研究。

## 新地图与固定契约

| World | 几何重点 | 正确自由面积 |
|---|---|---:|
| `p1c_open.world` | 开放空间、离散箱体和斜置长障碍 | 109.94 m² |
| `p1c_rooms.world` | 多房间、门洞、遮挡和室内家具 | 129.40 m² |
| `p1c_corridors.world` | 长绕行、交替出口和支路走廊 | 121.40 m² |

原 `my_world.world` 的正确自由面积约 130.84 m²。三张新地图都满足：真值只含 evaluator
已支持的 box collision、自由空间全连通、三台机器人共同出生区净空至少 0.45 m。

所有有效 episode 固定：

- 3 机器人，seeds 101/202/303；
- 90% correct-free coverage，180 仿真秒硬上限；
- 3 机器人 90 秒、2 机器人 120 秒速度验收线；
- 原速度、lidar、SLAM、Nav2、安全距离、碰撞与覆盖定义；
- 每个 episode 使用独立 ROS/Gazebo 进程。

## 三机器人结果

| World | Seed | time90 | 终止覆盖率 | 准确率 | 总路径 | 碰撞 | 重叠 |
|---|---:|---:|---:|---:|---:|---:|---:|
| open | 101 | 40.8 s | 90.01% | 98.50% | 21.060 m | 0 | 0% |
| open | 202 | 31.3 s | 91.91% | 98.10% | 16.539 m | 0 | 0% |
| open | 303 | 32.2 s | 90.87% | 98.39% | 17.194 m | 0 | 0% |
| rooms | 101 | 60.0 s | 95.25% | 97.48% | 29.836 m | 0 | 0% |
| rooms | 202 | 74.4 s | 90.13% | 98.02% | 31.102 m | 0 | 0.58% |
| rooms | 303 | 45.1 s | 90.99% | 97.89% | 23.784 m | 0 | 0% |
| corridors | 101 | 70.4 s | 93.97% | 97.87% | 37.930 m | 0 | 0.71% |
| corridors | 202 | 75.5 s | 92.15% | 97.59% | 43.569 m | 0 | 0.60% |
| corridors | 303 | 71.5 s | 92.56% | 97.69% | 42.116 m | 0 | 1.91% |

每轮三台机器人均有实质路径。最难的 corridors/seed 202 中三台路径分别为
14.455/14.640/14.474 m，不存在单台机器人完成任务的假协作。

地图参数化完成后另跑默认 `my_world.world`、3 机器人 seed 101 回归：`time_to_90=79.2 s`，
终止覆盖率 91.07%，总路径 37.267 m，零碰撞、零重叠，仍满足原 90 秒线。

## 两机器人交叉验证

在 `p1c_corridors.world`、seed 202 上，两机器人达到 90% 用时 85.5 秒，终止覆盖率
90.23%，准确率 97.74%，总路径 30.941 m，零碰撞、零重叠。两台路径分别为
16.391/14.550 m。

## 工程改动

主 launch、headless smoke 和 serial baseline runner 新增 world 文件参数；默认仍为
`my_world.world`。runner 会拒绝目录穿越和不存在的 world，结果 metadata 记录实际地图。
地图静态测试验证 evaluator 支持、全连通和出生区净空。

探索控制器和导航规则没有修改。唯一运行时修复是让 conda 中启动的 smoke runner 为 ROS
子进程优先使用系统 Python；否则 `spawn_entity.py` 会错误使用缺少 ROS 系统 `lxml` 的 conda
解释器。smoke 同时把已有 `--startup-timeout` 传给 launch 内部 readiness gate，仍要求每台
`bt_navigator=active`，没有绕过门控。

## 失败与无效轮次

- 首次 open/seed 101：三台 `spawn_entity.py` 因 conda Python 缺少 `lxml` 退出；没有有效
  episode，修复 ROS 子进程解释器后重跑通过。
- 首次 rooms/seed 101：tb2 的 `bt_navigator` 未在 launch 默认 180 秒内保持 active，gate
  正确阻止控制器和 evaluator 启动；贯通 240 秒诊断上限后重跑通过。

两次都属于 evaluator 未开始前的基础设施失败，保留原始 launch log，未混入任务成功率。

## 复现入口

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
source /opt/ros/humble/setup.bash
source /usr/share/gazebo/setup.sh
source install/setup.bash
export TURTLEBOT3_MODEL=waffle
PYTHONNOUSERSITE=1 python scripts/run_ideal_baseline.py \
  --world p1c_corridors.world \
  --seeds 101 202 303 --robot-count 3 \
  --duration 180 --coverage-threshold 0.90 \
  --startup-timeout 240 --evaluation-wait-timeout 330 \
  --message-timeout 90 --shutdown-timeout 60 \
  --run-id <unique-run-id>
```

运行输出位于忽略目录 `ros2_ws/ros2-multi-robot-automap/log/ideal_baseline/`，正式命令、
失败和结论同时追加到 `wireless-rl/log.md`。
