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

## 原生 footprint 候选：a69f53c

`20261013_p1c_repair_2r_original_v2`：2 机器人、my_world、seed101，schema v3 完整任务 PASS，
124.4 s 达到 91.094% 正确自由覆盖，零接触、监测有效、干净退出，两台都有真实移动和成功目标。
观测准确率 95.125%，总路径 46.781 m。这超过历史两机器人 120 s 速度线，准确率也低于历史
对应格；不能称为旧 P1C 完整性能矩阵重新验收。地图冲突安全修复的任务信用仅限此新原格。

运行结束后补查 plain smoke 的父进程提前正常退出边界：只有评估结果已完整验证时允许
launch 返回 0；未启用评估器的 smoke 提前退出仍判基础设施失败。新增独立回归检查。
后续最终冻结仍需以新的 run-id 运行计划的实际回归，旧原格完整保留。

最后一次完整包检查：62 tests、0 errors、0 failures、2 skips。
最终源码计划独立运行 2r/my_world、3r/rooms、3r/corridors 的 seed101、90%/180s 任务回归，
再做 4r 的 20 秒带评估器启动/运动表征及 plain smoke。20 秒表征的预期 timeout 不获得
完整任务成功信用；用于检查四台实际运动、接触观测与有界退出。全部使用独立 domain/port/run-id。


## 同冻结工程回归：226f11c，完整批次 FAIL

冻结 `226f11c6f40a8587881d0e7badf12c0f43f9cb91` 的五格命令、环境、起止时间、返回码见
[命令原件](assets/20261013_p1c_engineering_repair/226f11c_commands.json)。
原件路径与 SHA256 见 [索引](assets/20261013_p1c_engineering_repair/226f11c_original_index.json)，
四份原生评估 JSON 在同目录跟踪保存；完整 console/launch 日志保留在 ROS `log/`。
所有任务 seed101、覆盖阈值90%，2/3机器人任务期限180仿真秒。

| 格 | 原生终态 | 仿真秒 | 覆盖 | 接触 | runner 返回码 |
|---|---|---:|---:|---:|---:|
| 2r / my_world | coverage_reached | 137.7 | 90.926% | 0 | 0 |
| 3r / rooms | coverage_reached | 73.9 | 90.367% | 0 | 0 |
| 3r / corridors | coverage_reached | 75.8 | 90.080% | 0 | 0 |
| 4r / my_world / 20s运动表征 | collision | 4.6 | 24.556% | 1 | 1 |
| 4r / plain smoke | 基础设施PASS，无任务评估 | — | — | 未评估 | 0 |

前三格接触监测均有效、每台都有移动；覆盖/安全成绩限于各自原生快照，不能与其他候选拼接。
两机器人仍超过历史120s速度线。四机器人在 tb4 靠近停驻 tb2 时发生真实接触，不能把
plain smoke 的启动 PASS 当作安全或完整任务通过。**完整批次 FAIL 保留。**

四机器人日志同时确证两个工程问题：smoke 的 CLI lifecycle 查询超时被误写成 inactive；
原生 planner 实际正在处理目标，该超时本身不能证明 planner 不活跃。原生门控只查
bt_navigator，尚不能表达全部导航组件就绪。另，评估器写出结果后在回调内 shutdown，
没有及时退出，控制器持续派发直到300墙钟秒外部 SIGINT；此时 tb1 SLAM 遭遇
context 无效的 TF timer RCLError 并 abort(-6)。

更正此前“自动关闭通过”的表述：旧 smoke 在读取结果后主动 SIGINT 清理，退出0和无遗留
只能证明外部清理成功，尚未证明评估器驱动的自动关闭。当前后续 smoke 明确等待所属
launch 自行退出，超时即失败；评估器只在退出 spin 后关闭 context。历史原件不改写。

下一候选复用持久 ROS 查询检查全部六个 lifecycle；只使用 odom/TF 构造完整队友机体
避障包络，分别由专用 PointCloud2 标记和 LaserScan 清理独立 peer_layer，并为中央路径
添加同一保守包络；max 合并不清除静态墙体，虚拟数据不进入 SLAM、不用真值、不控制目标。
共享故障在手动/评估模式都停止派发并取消已知目标，迟到接受仍取消；未知所有权不释放。
C++ 仅捕获 context 关闭后的 RCLError，活跃运行的错误继续抛出。
这一候选的机体、速度、膨胀、物理接触、覆盖和任务期限均不放宽；要在新冻结上重新验证。

本轮新增 peer 栅格/点云和评估回调检查：最初69项包检查有1项 E501 格式失败，保留该失败；
修正过长 PointField 构造行后继续完整重跑。组件检查不提供 Gazebo 任务信用。

最终机体/退出修复候选的三包构建 PASS（2min21s），完整包检查70项，0 errors、0 failures、2 skips。
下一冻结先运行四机器人20s运动表征，再在同一源码运行2r原图、3r rooms/corridors和4r plain回归；
默认peer节点/两个costmap层/当前命令已经同步到user_guide与launch_commands。


## TF 接收与子进程退出审计：eb36480，原失败保留

冻结 `eb36480` 的 `20261014_p1c_repair_body_4r_motion`：4台/seed101/my_world，
1.0仿真秒 navigation_failure、零接触、监测有效，尚无有效运动信用。
原生失败理由为 `peer_state_unavailable`；原命令和结果在同目录 `eb36480_*` 附件。
评估器已经自行退出并触发所属 launch 关闭，但两个 planner 被原生 launch 升级到 SIGKILL。
旧 smoke 虽返回0，独立原生日志审计判基础设施关闭 FAIL，不能称干净关闭。
后续 smoke 新增检查原生 abort/升级终止记录，父进程0不掩盖子进程失败。

第一次只读旁录在该四机器人任务已经关闭后启动，输出空对象，没有诊断信用。
随后2r只读诊断脚本第一次在 `use_sim_time` 重复 declare 时失败，尚未启动仿真，保留失败。
修正旁录脚本后，`20261014_p1c_repair_body_2r_peer_diagnostic_v2` 使用相同冻结源码、
seed101、2r/my_world、15墙钟秒 dwell，smoke返回0；这只是原问题的诊断，不提供任务完成信用。

只读节点同时订阅每台同一TF话题的depth1/depth20，并旁录odom、clock、peer PointCloud2，
没有发布。98个一秒间隔样本保留原件与SHA256，所选原样本和旁录源码已跟踪。
在倒数第二个样本，仿真clock2075.382，depth1的map->odom源龄为tb1 2.404s、tb2 10.802s；
depth20分别为-0.197s/-0.199s（SLAM原生0.2s未来时间容差），odom新鲜。
队友点云停在2002.972/2002.980，确证depth1混合TF接收没有维持新鲜完整数据。

下一候选将peer TF订阅与现有control一致设为depth20，源龄上限0.5s不变；
只修传输接收队列，没有放宽安全、物理或任务门限。必须独立以新run-id验证。

TF depth / native child audit candidate: Python package build PASS3.70s; complete package checks71 tests, 0 errors/failures, 2 skips. Next pushed freeze predeclares4r20s motion, 2r original/3r rooms/3r corridors seed10190%180s, then4r plain. All new IDs, exact argv/env/output and native outcomes recorded; no source changes during simulations.


## 四机器人完整运动与退出检查：8b3aa2d，退出 FAIL 保留

`20261014_p1c_repair_fresh_4r_motion`，同原20s/seed101/my_world条件：四台路径分别
3.350/2.981/3.782/3.440m，总13.553m，均有实际导航目标，零接触、全部监测有效，
无协议/peer数据故障。20.0s原生timeout，覆盖50.996%，符合预声明的短时表征目的，
不提供完整任务完成信用。新增peer层能持续更新，TF接收故障未复现。

评估器自动退出，Nav2/SLAM/Gazebo均正常关闭，但tb3独立joint_state_publisher在SIGINT时
发生rclpy take_message RuntimeError并退出1。新smoke原生日志检查返回1，故基础设施关闭
仍FAIL；批次在此中止，当前冻结尚未运行随后2r/3r/4r plain，不补入旧格。
命令、原JSON、原件路径/SHA256在同目录8b3aa2d附件，失败原件保持。

当前SDF已经用 `libgazebo_ros_joint_state_publisher.so` 以30Hz提供左右轮真实状态；URDF
只有这两个非fixed关节。下一候选移除主建图launch的重复默认值joint_state_publisher，
保留Gazebo真实关节与robot_state_publisher；启动smoke要求每台收到左右轮数据，新增
SDF插件覆盖URDF所有活动关节的回归。其他Nav2/SLAM/探索/物理/门限均不改变。
这既消除重复状态源，也修复实际退出崩溃；必须在新的同一冻结重跑全部工程格。

Single native joint-state candidate: mapping package build PASS4.02s; complete package checks72 tests, 0 errors/failures, 2 skips. Predeclared next pushed freeze4r20s motion, 2r original/3r rooms/3r corridors seed10190%180s, then4r plain; new IDs/source/env/outcomes, no source changes during runs.


## 6838ef8 单机启动失败与环境恢复，原 FAIL 保留

`20261014_p1c_repair_verified_4r_motion`：300墙钟秒启动期限失败，没有评估结果、没有任务信用，
随后各格未运行。所有机器人左右轮真实joint_states已接收，tb1/3/4的六组件已active；
tb2 waypoint_follower原生WARN明确报告change_state响应发送超时，已转inactive但lifecycle
manager没有拿到响应，velocity_smoother停unconfigured，故整套未active。门控正确阻止探索。
这不是关节源删除造成的缺数据结论；原件确证的是中间件服务响应失败。
外部SIGINT同时暴露门控未捕获KeyboardInterrupt，manager等待响应最终被SIGKILL。

命令、原件SHA256和批次驱动源码以 `6838ef8_*` 保存；额外只读
`ROS_DOMAIN_ID=189 ros2 topic info /tb1/joint_states --verbose` 看到一个原生publisher。
共享内存仍有61.465GiB可用，不能声称内存容量耗尽。官方安装工具检查锁后清理了
1115个失效segment和139个失效port，保留3个在用segment/3个在用port，返回0；
前后计数与精确命令在 `6838ef8_dds_cleanup.json`。清理尚不能单独证明服务超时的因果。

下一候选保证被中断/关闭的readiness返回失败，处理KeyboardInterrupt/ExternalShutdownException；
当前所有Gazebo/ROS/RViz同主机的回归明确使用ROS_LOCALHOST_ONLY=1与相同FastRTPS，
新命令同步到launch_commands。源代码、物理/接触/覆盖/时间门限不以环境失败放宽。
将在新的同一推送冻结使用独立run-id/domain/port运行全部五个原预声明工程格。

Readiness-close candidate: build PASS3.25s; complete package checks73 tests, 0 errors/failures, 2 skips. Next source freeze predeclares same five engineering cases on single-host ROS_LOCALHOST_ONLY=1 / rmw_fastrtps_cpp after official zombie cleanup, with newIDs/domains and no source mutation during runs.
