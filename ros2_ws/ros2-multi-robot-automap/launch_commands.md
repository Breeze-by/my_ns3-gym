# 当前三机器人基线与MR3适配启动命令

新路线为 [MR3](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md)，P0/P1A/P1B已验收，用户于2026-10-16验收P1C并授权P2A；P2B及后续未开始。
默认`execution_mode:=baseline`启动前沿控制器；`adapter`为显式联合动作接口。P2A联合MaskablePPO正在实现与验证；gateway未开始。
所有推荐运行显式固定三台，活动默认已改为三台，保留1–4历史兼容。

## 环境与构建

ROS 使用系统 Python 与 ROS 2 Humble，学习端 `ns3gym` 不用于启动 ROS 节点。
请在未激活 conda、未 source 其他 ROS workspace 的新终端执行：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
export PYTHONNOUSERSITE=1
/usr/bin/python3 /usr/bin/colcon build --symlink-install --allow-overriding nav2_bringup
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1
```

这是历史schema3/普通演示的同主机 ROS 发现 profile；P1A合同模式使用下方明确的
UDP-only配置。两者都不等于正式多主机部署或 ns-3 网络模拟。
切换源码版本需要先评估旧 build/install 的路径/包缓存；必要时移到工作区外备份，
从 underlay 干净重建，保留 log。重新开终端 source，不能认为增量构建已删除旧入口。

## 三台手动演示

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=3 world:=p1c_rooms.world gazebo_seed:=101 \
  enable_gzclient:=true enable_rviz:=false enable_merge_rviz:=false \
  auto_save_map:=false
```

持续建图，Ctrl+C 结束。改为 `world:=my_world.world`、`p1c_open.world` 或
`p1c_corridors.world` 可运行现有其他场景，均是开发/已知场景，不叫未见布局。
看地图时可设置 `enable_gzclient:=false enable_merge_rviz:=true`；`enable_rviz` 只控制
每机器人 RViz，不控制全局 RViz。保持 `enable_drive:=false`，避免另一个速度发布者。

就绪需要三台 action 可发现和每台六个 Nav2 lifecycle 全部 active，不是固定 sleep。
主模式使用 SLAM，三台 Smac2D 的非滚动全局地图均来自实时融合图。轮关节状态由 Gazebo
插件发布，robot_state_publisher 生成 TF。peer_layer 的完整队友机体包络来自观测
odom/TF，不使用真值、不进入 SLAM；任务中源数据失效锁存控制失败并取消目标。
这些实时共享输入**尚未受网络限制**，后续 MR3-P3A 必须消除旁路。

## MR3-P1B理想适配与脚本探针

在已source上述ROS/Gazebo环境的终端使用下方P1A同主机UDP profile。
新模式只启动`mr3_adapter`目标所有者，禁止同时启动control或drive；同ROS域的本机锁
会拒绝第二个所有者。策略输入来自`/mr3/received/map`及交付状态；Nav2全局图为
本机最新图与交付共享图融合的`/tbN/navigation_map`，peer使用交付状态副本。
原生action端点仍位于适配器进程；这不是P3A的DDS隔离或网络gateway。

```bash
MR3_ADAPTER_ID=mr3_p1b_open_$(date +%Y%m%d_%H%M%S)
export ROS_DOMAIN_ID=108 GAZEBO_MASTER_URI=http://127.0.0.1:11901
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_mr3_adapter_probe.py \
  --scene open --seed 101 --run-id $MR3_ADAPTER_ID
/usr/bin/python3 scripts/audit_mr3_adapter_probe.py \
  log/mr3_adapter/$MR3_ADAPTER_ID --require-contact-monitoring
```

脚本自动设置P1A UDP profile，按声明的较长已观测路径验证候选目标、KEEP、WAIT、第二批目标和25秒后终态
闭合；完整95%评价器仅保留原口径监测，主动短停不能当成任务成功。
rooms/corridors分别使用对应`--scene`，推荐域109/110、Gazebo端口11902/11903，逐次运行，
每次新run-id。独立审计读取真实接受/取消/结果和子进程退出，不能只看runner返回值。
脚本显式设置`adapter_probe:=true`，仅允许将评价器以未完成诊断正常结束；默认关闭该服务。
详细信封、频率、租约、观测/候选/掩码和动作字段见
[MR3_ADAPTER_CONTRACT.md](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_ADAPTER_CONTRACT.md)。
冻结`f9928fe`的open/rooms/corridors各seed101严格审计均通过，前三次失败与完整原件见
[P1B报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261015_mr3_p1b.md)。
K8/5秒承诺是本接口版本；P1B异步名义1秒快照在rooms实际有2/3秒间隔。
P1C独立验证stepped 1秒步长/reset/采样，非stepped timer名义频率与跳帧规则不变。
这不证明95%任务或RL有效性；P1B/P1C已验收，P2A正在实施。

手动提供策略输入时可启动同一模式：

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=3 execution_mode:=adapter mr3_episode_epoch:=unique_episode \
  world:=p1c_open.world gazebo_seed:=101 enable_gzclient:=false \
  enable_rviz:=false enable_merge_rviz:=false auto_save_map:=false
```

无外部`/mr3/action`输入时保持空闲；KEEP不重发目标。正式验证使用脚本内的P1A持续监测，
手动入口未启用评价器，不产生安全或任务成绩。P1C reset/采样工程已验收，P2A训练使用下方独立入口。

## MR3-P1C采样与完整reset入口（2026-10-16已验收）

步进模式明确构造gzserver argv，将每个`-s`与插件路径放在ROS参数终止符之前；
启动日志`MR3_GAZEBO_SERVER_START`记录实际argv、插件和clock配置。baseline保留原启动入口。
stepped worker在暂停前等待adapter的`/mr3/initial_inputs_ready`实际交付确认，
再做原物理相位、drain、快照和seq0绑定；节点出现在graph不能替代该确认。

P1C W7验证的关闭顺序为：真实目标闭合→Nav2原生SHUTDOWN及18节点GetState finalized确认→
最后reward ACK/评价器clean退出→SDK按实际action/PID逐个正常退出ROS进程→Gazebo原生停止。
服务/状态/有序退出回执分别保留，超时或非零退出仍失败；不使用固定sleep代替退出，也不改接触/源序号门禁。
FastDDS保持原依赖，CycloneDDS因官方Humble缺少真实publication_sequence_number未采用。
v6完成记录中的合法2秒TTL浮点误拒及扣分保持原件；W7 `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`
以整数纳秒端点统一命令/租约/承诺/RPC期限，在任务/接触/频率不变下完成全新八阶段与独立命令时间审计。详见[P1C报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261015_mr3_p1c.md)。

先在系统ROS终端按上文重新构建包含步进插件的工作区。学习端另开终端，使用conda，
不source ROS或拼接ROS的PYTHONPATH；supervisor会在独立系统Python子进程重新source规范ROS/Gazebo环境。
以下是已提供的采样入口示例，不授权再次运行既有预算。W7工程证据含762项ROS/40项CPU检查及完整八阶段原生矩阵；
P1C/W7的GPU只保留b328原固定接口3F/3B/0更新范围，P1C本次无新GPU调用。新实验仍须先声明并绑定新推送冻结。

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
unset PYTHONPATH
export PYTHONNOUSERSITE=1
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 \
  --steps 16 --run-id UNIQUE_P1C_1W
```

2/4 worker使用同一入口的`--workers 2`或`--workers 4`及各自唯一run-id；每个worker始终三台，
不是二/四机器人规模实验。默认分别占用从ROS域120和Gazebo端口12001开始的独立编号。
输出位于ROS工作区`log/mr3_learning/<run-id>/`；run-id目录拒绝覆盖。
指标须包括完整startup/reset/closure的有效transition率、仿真倍率、CPU/RAM与GPU资源记录，失败保留。
脚本动作仅施加候选/KEEP/WAIT和取消压力，不是训练策略或性能比较算法。

诊断失败入口默认关闭，仅用于已预声明的P1C终态验证；每轮先3个KEEP步，
分别验证20ms短终态和同边界零时长尾步，不伪造接触或clock。
`training_terminal_probe`默认false，只能与stepped及隔离reward同时启用。

```bash
python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 \
  --steps 4 --terminal-probe --run-id UNIQUE_P1C_TERMINAL \
  --base-domain 144 --base-port 12171
```

本次已保存W7正常矩阵可离线重放；在wireless-rl目录执行，输出必须用新名。此命令不启动原生进程：

```bash
/usr/bin/python3 -B report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v3.py \
  report/assets/20261015_mr3_p1c/native_v7/workers1 \
  --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --output /tmp/UNIQUE_W7_WORKERS1_PHASE3.json
```

phase3固定绑定原contact task-phase与独立命令时间门禁；scalar reward审计独立列于原件，不由此命令替代。
检查保留的GPU接口结果只读取原JSON，不重复已消耗的3F/3B预算：

```bash
/usr/bin/python3 -m json.tool report/assets/20261015_mr3_p1c/gpu_probe_v2.json
```

原GPU探针在b328固定model/encoder/probe下完成3次forward/3次backward、0 optimizer更新；
它不是训练或W7新增GPU验证。任何新GPU尝试须另立前瞻计划和预算，不能重用原v2计划再执行。
当前Gym/IPC依赖锁定见`mr3_learning/requirements-env.txt`，保留现有CUDA栈，不默认重装环境。
固定1秒step、20ms量子、真实clock相位、seq0首格奖励绑定与外部截断/真实闭合规则见
[环境契约](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_ENV_CONTRACT.md)。
每次实际执行均是需追加共享log的实验，不能把入口存在当成P1C通过。

## MR3-P2A.0 第一版历史命令（保留失败，不重跑）

实际在`f8694025`执行：terminal完整审计PASS，reset保留1次真实peer安全失败、3次外部截断，
整体benchmark/完整审计FAIL；deadline命令未执行（SKIPPED）。本步出口未达，停留待复核。
以下保留原预声明命令，不授权自动重跑或执行已跳过的deadline；新修复需新冻结/预声明。

2026-10-17用户授权继续解决P2A并允许前置准备。本轮先验证SLAM生命周期、候选v4、
失败采样保存和安全触发诊断；全部为脚本工程检查，无policy训练/GPU更新。
先按上文系统ROS构建并source当前install；学习端按P1C段激活`ns3gym`并清除`PYTHONPATH`。
只在同一干净已提交推送冻结运行，逐项审计通过才执行下一项；失败停止，不自动重试。
输出与预声明见[P2A.0报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261017_mr3_p2a0.md)。

```bash
MR3_P2A0_FREEZE=$(git rev-parse HEAD)
python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 \
  --steps 4 --terminal-probe --base-domain 180 --base-port 12401 \
  --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 \
  --run-id mr3_p2a0_20261017_terminal
python -m mr3_learning.audit_preparation \
  /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_terminal \
  --freeze "$MR3_P2A0_FREEZE" --output /tmp/mr3_p2a0_terminal_audit.json

python -m mr3_learning.benchmark --workers 2 --schedule open:101,open:101 \
  --steps 16 --base-domain 184 --base-port 12411 \
  --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 \
  --run-id mr3_p2a0_20261017_reset
python -m mr3_learning.audit_preparation \
  /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_reset \
  --freeze "$MR3_P2A0_FREEZE" --output /tmp/mr3_p2a0_reset_audit.json

python -m mr3_learning.benchmark --workers 1 --schedule open:101 \
  --steps 300 --deadline-probe --base-domain 188 --base-port 12421 \
  --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 \
  --run-id mr3_p2a0_20261017_deadline
python -m mr3_learning.audit_preparation \
  /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_deadline \
  --freeze "$MR3_P2A0_FREEZE" --output /tmp/mr3_p2a0_deadline_audit.json
```

源文件/规则/配置由新审计入口精确绑定，旧W7门禁原件不修改。372API/371真实脚本决策为总上限，
工程成本单列，不使用/重置pilot余额。每worker始终三台；300秒KEEP用于截止与关闭验证，
不证明探索或三台参与成功。旧版原件保持；用户随后要求继续完成P2A.0，新版见下节。

## MR3-P2A.0 v12 当前训练前工程准备

v1至v9失败及原件保留，详见 dated reports。当前导航合成own已知权威/shared补unknown、候选`mr3-navigation-geometric-staging-v5`、快照v3/张量v2及71列活动观测延续。实际速度链为controller/behavior→`cmd_vel_nav`→smoother→`cmd_vel_unguarded`→唯一`motion_safety`→`cmd_vel`。受控每20ms暂停完成state实际发布→peer实际接收/障碍发布→guard实际回收→三台native目标存储后才推进。三机实际Nav2配置和安全门的角速度指令上限均为`.8rad/s`，测量门仍为`1.2rad/s`；精确一ULP规范、完整转向复验及保守停止包络延续。

当前model显式使用本包`libmr3_gazebo_diff_drive.so`，只改轮指令反馈算法，物理参数保持。audit启用时保存实际spawn的三份SDF及drive_tbN.jsonl，不能用未构建的系统插件替代。

系统ROS环境先在canonical ROS目录构建并source当前install：

```bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
/usr/bin/python3 /usr/bin/colcon build --symlink-install \
  --packages-select merge_map multi_robot_exploration multi_robot
source install/setup.bash
```

adapter唯一guard发布tagged target，driver实际存储后回执，worker核对三台exactclock/seq/value；Twist仍观察，baseline显式Twist模式。原paired轮模型、四编译源/库、所有机体门保持。条件静止转向原每个body margin≥.1518m及整段漂移须独立核验。新增显式因果提交修复暂停期间定时发布饥饿，隔离`information_states.jsonl`、`peer_phase.jsonl`和控制账本逐实际callback核验。工程与训练结果审计共用唯一零bootstrap的受限版本入口，不改变真实任务release或原整数物理数学；本轮没有训练信用。

再按P1C段激活conda `ns3gym`，仅在下面wireless-rl目录执行Python入口；ROS子进程仍使用system ROS Python。只在一个干净且已提交推送、完成源码和installed路径核验的冻结运行。interface通过后才开始terminal，再完整reset，最后deadline；每阶段完整审计通过再前进。上限608 API/596脚本动作、18000墙秒，无原生GPU/optimizer；pilot余额不动。真实失败保留并停止该版后续阶段，修复后新冻结/新预声明重验，不拼PASS。详见[v12报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261017_mr3_p2a0_v12.md)。

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
unset PYTHONPATH
export PYTHONNOUSERSITE=1
MR3_P2A0_V12_FREEZE=$(git rev-parse HEAD)
python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_buildproof_preflight.py
python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_launch_stage.py interface "$MR3_P2A0_V12_FREEZE"
python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_audit_stage.py interface "$MR3_P2A0_V12_FREEZE"

python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_launch_stage.py terminal "$MR3_P2A0_V12_FREEZE"
python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_audit_stage.py terminal "$MR3_P2A0_V12_FREEZE"

python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_launch_stage.py reset "$MR3_P2A0_V12_FREEZE"
python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_audit_stage.py reset "$MR3_P2A0_V12_FREEZE"

python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_launch_stage.py deadline "$MR3_P2A0_V12_FREEZE"
python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_audit_stage.py deadline "$MR3_P2A0_V12_FREEZE"

```

上述native入口使用[预声明launcher](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v12/predeclared_plan_v12.json)的精确命令与累计预算，不直接绕过它调用benchmark。`audit_preparation`只是完整门中的一项；interface须补齐full/input/driver/angular/physical/settled/closure及information并新增peer/control精确独立回执；准确清单以本版预声明为准，全部`passed=true`才允许下一stage。各文件名与调用模板在预声明中，真实FAIL或缺件都拒绝继续；不能手写PASS。preflight仅在同一clean+pushed冻结创建新`/tmp`凭据，不覆盖旧凭据。

interface的`--preparation-parameter-review`只读固定、源码绑定的九节点参数脚本；使用原native metadata声明并经canonical profile/Git字节核验的相同loopback UDP配置；reset返回后、首step前物理保持暂停，失败走严格关闭。原件`actual_nav2_parameters.json`保存在episode目录。interface还须通过冻结独立angular消费者及至少一次实际settled-turn触发、完整持续漂移审计；所有阶段driver消费门保持。reset须通过冻结独立物理matrix及所有触发漂移段；规则和脚本SHA见预声明资产。

`--preparation-motion-probe --preparation-probe-version mr3-p2a0-outward-cancel-v3`为32步外部工程输入：GOAL[0,1.5)/[13,15)、WAIT[10,13)/[28,32)，其余KEEP；第二GOAL优先首阶段实际received转向符号的反向合法目标机会，不保证实际反向响应。旧v2仍20步，不能混用。三台每轮均需合法GOAL、原生接受及received路径>.05m，首失败共享标志阻止后续调用而不补造终态。该脚本不是生产探索策略或fallback。terminal/deadline没有95%/参与信用；完成后待用户验收P2A.0。

受控stepped在暂停中以state_phase→peer_phase→motion control→三台storage显式提交，状态有效50Hz；非受控10Hz保持。独立zero-stop同clock更高序号仅三零、不覆normal ACK；启动invalid也走实际cancel/Nav2/native有序关闭。所有原源龄/任务/机体安全门不变。

## MR3-P2A联合MaskablePPO（v6历史命令，本轮不重启pilot）

在上方conda `ns3gym`环境、wireless-rl目录执行；保持`PYTHONNOUSERSITE=1`与ROS解释器隔离。
安装锁定学习依赖不会替换现有CUDA栈：

```bash
python -m pip install -r mr3_learning/requirements-ppo.txt
```

仅在干净、已提交推送的新冻结运行，每次唯一run-id。完整episode闭合之后才更新，掩码随rollout保存；
零时长无动作尾通知归并到此前真实决策，不产生伪actor样本。预算与出口见
[PPO契约](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_PPO_CONTRACT.md)。
当前为v6评价器逐20tick暂停相位ACK修订；原生候选/地图/导航及gamma=lambda=1保持，
不放宽20ms终态检测或任务/安全门禁。每个暂停量子必须等评价器同executor确认精确clock/冻结终态，
不是P3生产端/DDS完整因果时钟证明。下列已执行历史命令与[v6原预声明计划](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261016_mr3_p2a/predeclared_plan_v6.json)一致；前三项已在af37冻结执行，验证项SKIPPED。旧run-id拒绝覆盖，这里不授权重跑。
v5最小链16/4更新完整审计PASS；pilot三round797保存样本/48更新，全16尝试876原生/875返回、
5212.525802815799墙秒，3次原生成功记录及全部失败/前缀保留。最后自动触发终态40ms滞后
超过20ms门禁的基础设施错误，原完整审计FAIL，无final.zip，原声明开发验证SKIPPED，不替换早期权重。
原4096/14400 pilot扣v2的390/1752.957494、v4的242/1051.054936、v5的876/5212.525803，
v6声明时余2588/6383.461767、选2588/6300。实际probe8API/7脚本决策和最小链16决策/4更新审计PASS；
pilot718原生/717返回、3477.507027802989墙秒、0保存round/0更新，tb1 SLAM有序SIGINT后karto::Exception/exit -6，
严格关闭失败且Gazebo stop CLI未启动，表层identity missing；原完整八项FAIL保留，具体SDK throw/stack未知。
无final/checkpoint0000/rollout0000，三场开发验证SKIPPED，不代用早期/其他版本/工程权重。
累计pilot已用2226/约11494.045260453597，余1870/约2905.954739546403；用户确认原累计4096/4小时，
未花不重置、不自动用。本session按无重试infra规则停止P2A，不自动重试/v7或进入P2B。
工程probe/最小链和固定开发验证单列，无额外observer运行。
先terminal-probe的native/scalar/phase-ACK审计PASS，再全新最小链完整审计PASS，才从新权重跑pilot。
phase审计由学习端独立模块重放物理和评价器/worker回执并随完整审计执行，无单独虚构CLI；
保留原20ms/contact/command/scalar/W7门禁及协议v2原FAIL/严格detached重放，scope不扩成all-producer drain。
普通episode上限300步，最后quota/墙时尾段明确外部截断、只bootstrap一次；真实terminated才为无bootstrap MC。
学习seed41与taskseed不同：所有open任务同world/任务几何/固定起点/yaw0，仅Gazebo随机种子变化。

```bash
python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 \
  --steps 4 --terminal-probe --base-domain 156 --base-port 12291 \
  --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo \
  --run-id mr3_p2a_v6_phase_terminal

python -m mr3_learning.ppo --mode train --workers 1 --schedule open:101 \
  --decisions 16 --episode-steps 16 --wall-seconds 900 --seed 41 \
  --base-domain 160 --base-port 12301 --run-id mr3_p2a_v6_minimal

python -m mr3_learning.ppo --mode train --workers 4 --schedule open:101 \
  --decisions 2588 --episode-steps 300 --wall-seconds 6300 --seed 41 \
  --base-domain 164 --base-port 12311 --run-id mr3_p2a_v6_pilot

```

以下是原预声明且未执行的验证命令，因缺final.zip已SKIPPED，不可直接运行：

```bash
python -m mr3_learning.ppo --mode evaluate --workers 4 \
  --checkpoint /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot/final.zip \
  --schedule open:401,open:402,open:403 \
  --decisions 900 --episode-steps 300 --wall-seconds 9000 --seed 41 \
  --base-domain 172 --base-port 12321 --run-id mr3_p2a_v6_validation
```

学习端使用cuda:0（可显式`--device cpu`）；每worker始终三台。
输出为`log/mr3_ppo/<run-id>/`；SB3指标写`sb3_metrics/progress.json`，collector实时状态单独写根`progress.json`。
包含metadata、原生进程/任务原件、张量/掩码rollout、
采样概率、PPO指标、checkpoint和SHA、完整失败/中断。`completed`只表示run的采集/更新闭合，
95%任务成功仍由原生schema4独立判断。本次phase/minimum已PASS但pilot infra失败，不能将工程通过当任务成功；
仅pilot无基础设施错误且有有限final.zip时执行final-only验证，否则SKIP、不替换checkpoint；
本次停在P2A，未接网/进入P2B；[闭合记账](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261016_mr3_p2a/v6_closure_accounting.json)及[预算记录](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261016_mr3_p2a/budget_acceptance_20261016.json)保留全部成本。
v3候选规则为`mr3-per-robot-geometric-staging-v3`，路径机体净空仍为`.29m`，
目标到达圆盘要求`.39m`；各台已交付本地图保留几何代表项，不能用真值或手工目标兜底。
主launch实际读取`src/multi_robot/params/nav2_params_tb1_0.yaml`至`tb3_0.yaml`，
三份GoalChecker和DWB的`xy_goal_tolerance`均为`.10m`，yaw仍3.14；
`params/turtlebot3_params/`内的同名文件不是该launch当前输入。
主launch包含的SLAM入口读取`src/slam_toolbox/config/mapper_params_online_multi_async.yaml`，
运动阈值为`.10m/.20rad`，ROS时间节流`.5s`与地图更新5s不变，C++/Karto实现未改。
这些参数也影响同冻结baseline；历史P1A/P1B/P1C和v1/v2结果不能归入此新执行版本。

## 已有 90% 工程评估（不验收 MR3 的 95% 任务）

```bash
MR3_RUN_ID=mr3_frontier90_$(date +%Y%m%d_%H%M%S)
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=3 world:=p1c_rooms.world gazebo_seed:=101 \
  enable_gzclient:=false enable_rviz:=false enable_merge_rviz:=false \
  auto_save_map:=false enable_task_evaluator:=true \
  evaluation_episode_id:=$MR3_RUN_ID \
  evaluation_output_dir:=/tmp/$MR3_RUN_ID \
  evaluation_duration_sec:=180.0 evaluation_coverage_threshold:=0.90
```

每次使用新 episode id/目录，拒绝覆盖旧结果。schema3 在截止之前达标、接触 topic 记录为零、
每台碰撞监测有消息、无控制失败才成功。schema3只读取 `base_collision`，不能证明
全机体零非支撑接触；其监测门禁也不等于持续新鲜度证明。全机体门禁使用下面的schema4。
评估器完成默认先请求本launch的Gazebo原生停止，等待真实server退出后关闭其余节点；
结果冻结且检查原生子进程，父进程0不能掩盖 abort。
`stop_on_evaluation_complete:=false` 仅用于人工诊断。

把阈值改0.95并不自动完成 MR3-P1A：需先验证任务 ROI、真值几何、质量和95%可达性，
并预声明任务预算/新schema。不要把旧90%/180秒结果、或95%配置本身写成新任务成功。

## MR3-P1A 合同评估与传统开发矩阵

P1A合同模式为schema4，真值/世界哈希、完整ROI、95%/300仿真秒、地图质量、三台参与、
18个组件持续接触监测和导航终态闭合共同决定成功。详细口径见
[MR3_TASK_CONTRACT.md](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_TASK_CONTRACT.md)。
以下为实际已实现入口；原生验证结果仍以P1A报告为准。
合同launch自动启动C++ `mr3_contact_reducer`。18条原始接触消息仍保留，汇总输出为
`/mr3_contacts/tbN/<component>`；只合并同一消息中重复的碰撞对，保留原header和
每对首次完整几何样本，原样本数量保存在state.info。生产20Hz和0.5仿真秒源龄/接收龄
门限不变。原始发布端和汇总节点使用可靠的100条历史，防止启动负载下仅5条历史
被覆盖；该改动是否消除缺口以新冻结原生结果为准。原始消息序列缺口、无法审计或
多个源发布者锁存为失败。runner在任务退出后还核查唯一18路汇总、逐条输入/输出、
完整序列和原生子进程；原生JSON成功不能掩盖基础设施失败。

P1A smoke/baseline在任何ROS命令或初始化之前自动应用下面的同主机UDP-only环境，
并在metadata的 `transport_environment` 记录所选变量和 `profile_sha256`。
手动直接启动合同launch时先在已source上述ROS/Gazebo环境的终端执行：

```bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=0
export FASTRTPS_DEFAULT_PROFILES_FILE="$PWD/src/multi_robot/config/mr3_fastdds_loopback_udp.xml"
export SKIP_DEFAULT_XML=1
unset FASTDDS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML RMW_FASTRTPS_PUBLICATION_MODE
export ROS_DOMAIN_ID=98 GAZEBO_MASTER_URI=http://127.0.0.1:11861
```

XML关闭内建transport，仅启用白名单为127.0.0.1的UDPv4；没有更改socket缓冲或
UDP transport的默认发送阻塞方式。`ROS_LOCALHOST_ONLY=0` 由显式loopback白名单约束通信范围，
`SKIP_DEFAULT_XML=1` 只阻止工作目录的默认XML覆盖显式profile，仍加载上方指定文件。
legacy入口不会自动改为此环境；重新打开终端并使用前面的历史profile可复现其原环境。
P1A第六版冻结时另为三台各六个Nav2节点的 `change_state` 响应writer配置精确命名profile：
`rr/tbN/NODE/change_stateReply`，共18项；NODE为 `controller_server`、`planner_server`、
`behavior_server`、`bt_navigator`、`waypoint_follower`、`velocity_smoother`。
只将这些response writer的reliability `max_blocking_time` 从默认100ms改为5墙秒，
为启动时响应writer等待对应reader匹配提供有界窗口，也约束这些writer的DDS写入阻塞；
它不按ROS仿真时钟计时。没有新增Nav2 transition重试，也没有改变其无超时future等待；
reader匹配为何延迟、客户端为何可能一直等待的根因仍未解决。
profile只绑定这些命名writer，不随启动阶段结束而撤销；不设置默认writer、service-wide
fallback或reader配置；P1A原冻结的contact/control、get_state及request writer保持原有QoS。
P1C W7保留同三台六节点的18个精确`rr/tbN/NODE/get_stateReply`配置1墙秒
匹配/写入等待（默认100ms），低于安装版Nav2 `get_state`客户端原2墙秒超时，后者不变。
新增规则不改变request/data/contact端点、频率或任务门槛；实际失败仍按infra保留，不自动重试。
这是有界发现等待的应用配置，不宣称修复DDS内部发现竞态；W7完整矩阵仅提供其实际工程范围。
P1A旧报告/原件仍只对应其冻结18项change_state规则，不能赋予新配置结果信用。
`RMW_FASTRTPS_USE_QOS_FROM_XML` 继续unset，ROS端点QoS转换仍保留该max-blocking字段。
静态SDK/RMW验证另列为
[证据](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/lifecycle_reply_qos_v6_static_proof.json)，
不代表实际启动已通过；配置是否改善响应问题仍以新冻结
原生结果为准，不宣称已证明SHM或abort根因。300墙秒启动、300仿真秒任务、95%及
.5仿真秒接触健康门禁均不变，控制策略与物理参数未改。

```bash
MR3_BATCH_ID=mr3_p1a_rooms_$(date +%Y%m%d_%H%M%S)
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_ideal_baseline.py \
  --world p1c_rooms.world --robot-count 3 --seeds 101 202 303 \
  --task-contract src/multi_robot/config/mr3_p1a/rooms.json \
  --startup-timeout 300 --evaluation-wait-timeout 900 --run-id $MR3_BATCH_ID
```

open/corridors使用对应world与 `open.json` / `corridors.json`，每次新run-id。
评估器等待有效正ROS仿真时钟，再一次建立18路接触订阅；此后收到的所有放行前
接触保留，18路持续新鲜且无非支撑接触才可放行。这不覆盖订阅建立之前的每个历史
触碰。未来消息先按当前时钟排水，真正未来队列超过256条立即失败并记录诊断；
不改源时间戳或.5秒门限。任务提前结束时，runner优先读取原生JSON并审计退出，
不继续等待已经消失的topic。300墙秒约束Nav2/ROS就绪，后续时钟/监测等待仍由
900墙秒评估保护约束。
P1A第六版按rooms、corridors、open逐场景串行执行，每场景内部也串行重启三种子。
第六版计划使用独立ROS域98/99/100与Gazebo端口11861/11862/11863；保持所有任务与墙钟保护门限。
这用于减少并发启动压力，不表示一次Nav2响应超时的根因已经确定。精确预声明见
[native plan](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/predeclared_native_plan.json)。
冻结`5e47802`累计10次尝试含1次保留的原生基础设施失败，得到9个有效单元；结果见
[P1A报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_p1a.md)。
合同确定任务300仿真秒，300/900墙秒分别是启动/基础设施保护，不能当成延长任务。
参数与合同显式冲突会拒绝。任务t0为控制器仿真时间放行；启动预热地图单列，达标后的
取消闭合计入任务截止。合同模式不接受两/四台、schema3或曾中断的监测作为成功。
`my_world`暂不提供95%合同；validation/test/confirmation布局本步不运行。

默认 `stop_on_evaluation_complete:=true` 时，评估器退出后launch向记录的owned
gzserver环境（包括实际 `GAZEBO_MASTER_URI`）执行
`gz topic -p /gazebo/server/control -m "stop: true"`。
必须同时观察同一启动action、PID和进程名的server退出0及stop CLI退出0，才关闭其余节点；
两者可任意先后，CLI退出0不等于server已停止。10墙秒仍未收到任一必要退出事件则输出
`MR3_GAZEBO_NATIVE_STOP_ERROR` 并兜底关闭；CLI失败或server非零退出也保留错误标记和
真实子进程退出码。runner把该标记判为基础设施失败，即使之后CLI/server退出0；
SIGABRT等真实失败不会被屏蔽。有效任务失败或无效JSON也先等待同一原生关闭流程，
然后保留原失败结果。该关闭保护不改变300仿真秒任务预算。
`stop_on_evaluation_complete:=false` 不发出原生stop请求，供人工诊断。

## 当前自动检查与传统批量入口

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/ros_smoke_test.py \
  --robot-count 3 --world p1c_rooms.world --gazebo-seed 101 --startup-timeout 300

MR3_BATCH_ID=mr3_frontier90_batch_$(date +%Y%m%d_%H%M%S)
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_ideal_baseline.py \
  --world p1c_rooms.world --robot-count 3 --seeds 101 202 303 \
  --duration 180 --coverage-threshold 0.90 --startup-timeout 300 \
  --evaluation-wait-timeout 360 --run-id $MR3_BATCH_ID
```

这只是可执行示例，本轮未执行。smoke 是启动/消息/关闭检查，任务结果另列。
runner 对任务或基础设施失败返回非零；启动保护是墙钟，任务预算是仿真时间。
所有正式检查也属于实验，必须追加共享 [log.md](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/log.md)，包括失败、冻结提交、
完整命令、seed、环境、原件路径和结论，不自动覆盖或继承旧 run-id。

Nav2 接受/取消终态默认期限为10仿真秒，对应
`navigation_response_timeout_sec` / `navigation_cancel_timeout_sec`；当前目标上限
`exploration_goal_timeout_sec:=60.0`。这不是未来 Wi-Fi 命令 TTL 的现成实现。

## 故障诊断和证据

先确认生命周期、TF/map frame、最新 scan/odom、原生日志和自己的残留进程。
若原生日志显示 FastDDS 生命周期响应发送超时，停止本次实验后可用安装的官方工具
清理失效共享内存；工具会检查锁并保留在用资源：

```bash
/usr/bin/python3 /opt/ros/humble/tools/fastdds/fastdds.py shm clean
```

不使用无范围 pkill 或手工删除所有 DDS 段。清理后新 run-id 复测，原失败保持。
该工具不是已证明的所有时序故障修复方法。

运行源码 `c9344e1` 的最近三机器人90%工程结果为 rooms60.2s、corridors81.9s，seed101，
180仿真秒上限、基体接触记录为零、原生干净退出；未重跑完整多种子矩阵或95%任务。
详见 [工程修复报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261013_p1c_engineering_repair.md)。
