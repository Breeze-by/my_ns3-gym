# P1C 工程修复记录

日期：2026-10-13。基线：`main@99cf3a6`，原路线保留在 `p2c1/global-mission-20261012@8fe1495`。
本轮只修工程缺陷；`RESEARCH_PLAN.md`、`IMPLEMENTATION_PLAN.md` 的研究路线不作修改，
等待用户另行提供新路线。历史实验原件与成绩保持原版本身份。

## 修复内容

- lifecycle 精确检查 active 状态，避免把 inactive 当成 active，重复检查所有相关节点。
- schema v3 先检查任务期限和安全，再判覆盖成功；缺接触监测或导航握手失败不能成功。
  CSV/JSON 完整发布且不覆盖原件，批量 runner 对任务失败返回非零。
- 评估器退出默认关闭其所属 launch。未启用评估器的手动建图仍由 Ctrl+C 结束。
- Nav2 接受/取消/终态响应有显式期限；未知所有权不释放，迟到目标取消，旧回调不清理新任务。
- 地图融合保守保留占据冲突，按实际重叠面积处理小数偏移；拒绝旋转或不同 frame。
  Dijkstra 禁止切过受阻拐角，缺分段路径不回退为未经验证的长目标。
- 四机器人使用一致的融合图/Smac/非滚动配置；出生点统一在共同区域；非法数量直接拒绝。
- 模型资源使用安装包路径，修正依赖声明；旧 build/install 移到仓库外后干净构建。
- `trajectory_overlap_ratio` 明确为中心轨迹栅格重叠；保留 `search_overlap_ratio` 兼容字段。
  本轮不实现重复激光覆盖指标，也不定义未来 RL 的观测、动作或奖励。
- 更新实际运行指南与交接状态，新增统一 launch 命令。研究目标、算法路线和阶段计划等待后续指示。

## 验证与证据边界

回退后只读审查的旧 19 单元测试通过，但未覆盖本轮发现的边界缺陷。修复中的新增回归测试
曾有一项测试夹具误依赖已安装包路径，已改成源码资源夹具；测试失败不是有效 Gazebo 任务。

干净构建命令：

```bash
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
export PYTHONNOUSERSITE=1 CMAKE_BUILD_PARALLEL_LEVEL=4
/usr/bin/python3 /usr/bin/colcon build --symlink-install --parallel-workers 4 \
  --allow-overriding nav2_bringup --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
```

六包干净构建通过。旧构建安装备份位于
`/home/zhuyulab/.cache/ns3-workspace/ros-build-before-p1c-hardening-20261013/`；实验 `log/` 没有移动或删除。
后续正式运行使用新的 run-id 和推送冻结提交；实际结果在本报告与共享 `log.md` 追加，
不预先宣称完整 P1C 矩阵通过，不把历史结果计入本次修复。

完整 Python 包检查通过：61 tests、0 errors、0 failures、2 版权检查 skips。
安装审计确认零失效符号链接、无旧接口包，探索包仅有 control/task_evaluator/nav2_ready_gate
三个入口；模型资源全部可解析，实际安装 launch 参数检查通过。

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /usr/bin/colcon test --packages-select merge_map multi_robot_exploration \
  --event-handlers console_direct+ --return-code-on-test-failure
/usr/bin/python3 /usr/bin/colcon test-result --verbose
```

首次包检查的两项格式失败（嵌套函数空行、D213 docstring）已修正，完整重跑通过。
下一阶段在推送冻结上运行 2 机器人原地图、3 机器人 rooms/corridors 的 seed101 工程回归，
以及 4 机器人基础 smoke；全部结果，包括失败/中断，单独保留。

## 首次实际回归：9b2dd5e，保留 FAIL

`20261013_p1c_repair_2r_original_v1`：2 机器人、my_world、seed101，180.0 秒 timeout，
正确自由覆盖 54.365%，零接触、监测有效，基础设施 PASS，完整任务 FAIL。
tb1 路径仅 0.222 m、0 个成功目标；tb2 路径 8.725 m、6 个成功目标。

只读原地图/代价图旁录 `readonly_map_probe.json` 确认：tb1 私有图在实际当前位置为 free，
tb2 的图在 tb1 同一位置为 occupied，融合图和 tb1 全局代价图均为 occupied。
原生 Smac 持续报 Starting point in lethal space。该结果是本次保守融合暴露的本机起点问题，
不能恢复 free 优先来掩盖真实障碍冲突。

后续候选启用 Humble Nav2 原生静态层 `footprint_clearing_enabled`，仅清理该机器人的当前
真实 footprint 下的代价；融合图仍保守，轮廓外占据证据、未知区、原半径、膨胀和期限不变。
已核对本机安装的 static_layer.hpp 中原生接口；新候选须推送后以新 run-id 独立验证。
