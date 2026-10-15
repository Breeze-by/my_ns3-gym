# MR3-P1C 环境与采样契约 v1（原生验证待做）

2026-10-15：P1A/P1B已由用户验收，P1C进行中，P2A及后续未开始。
本文件描述当前源码候选及其待验证要求，不声明原生reset/吞吐或GPU检查通过。
没有实际策略训练、训练checkpoint、gateway或ns-3闭环；任务成功仍使用
[MR3_TASK_CONTRACT.md](MR3_TASK_CONTRACT.md)，不更改95%/300秒、质量、参与、接触或目标闭合门禁。
P1B接口与证据见[适配契约](MR3_ADAPTER_CONTRACT.md)和[P1B报告](report/20261015_mr3_p1b.md)。

## 进程与信息边界

学习端为conda `ns3gym`中的[MR3Env](mr3_learning/env.py)，不导入ROS或真值模块。
[Supervisor](mr3_learning/supervisor.py)通过私有stdin/stdout JSONL pipes控制独立的
[系统ROS worker](../../../../../../ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py)。
epoch与request id绑定每次IPC；日志写独立文件，不能混入协议stdout。IPC不是模拟网络。

策略输入仅为已交付地图、估计位姿、实测速度、导航上下文、几何候选与保存掩码。
P1B的K8+KEEP/WAIT、1000类联合动作、5秒接受后承诺和单一所有权继续适用；无手工目标兜底。
真值SDF/ROI、正确格mask、奖励首格账和真值轨迹只在独立`task_evaluator`进程中使用。
后端、broker和actor不会收到真值数组、正确格indices或真值导航输入；学习IPC只返回标量奖励、
终止标志和标量诊断。Gym info拒绝私有mask/格索引对象；不能把info重新拼进actor观测。

## 固定张量接口

输入快照为`mr3-observation-v2`，张量schema为`mr3-learning-tensors-v1`。
[observation.py](mr3_learning/observation.py)枚举全部列顺序、固定尺度、缺失位与校验规则；
[env.py](mr3_learning/env.py)提供Gymnasium `reset/step`与`Discrete(1000)`。

| Dict键 | shape / dtype | 含义 |
| --- | --- | --- |
| `global_map` | `(3,128,128)` uint8 | 固定32m全局图，occupied/free/unknown二值证据，可重叠 |
| `local_maps` | `(3,3,64,64)` uint8 | 三台各12.8m局部裁剪，顺序tb1/tb2/tb3 |
| `robots` | `(3,64)` float32 | 固定物理尺度的状态、源龄、有效位和导航上下文 |
| `candidates` | `(8,16)` float32 | 几何坐标、清距、前沿数量、三台路径特征及有效位 |
| `history` | `(3,16,4)` float32 | 最多16条已交付估计位姿及源龄/有效位 |
| `task` | `(12,)` float32 | 实际任务时间、剩余时间、地图源龄与缺失/范围位 |
| `action_mask` | `(1000,)` int8 | 保存时的联合动作合法位 |

固定尺度包括坐标16m、路径32m、源龄300s、承诺5s、租约2s；不按当前地图边界或真值归一化。
缺失数值以0和独立有效位表示；超参考尺度值保留并标记越界，不静默clip。
摘要损坏、未来来源时间、非法mask、非有限数值或不匹配的栅格编码均报错。
重放使用原快照/候选/掩码及schema，不能用后续地图重新解释旧动作。

## 本机SDK状态响应等待（v6候选）

同机FastDDS loopback profile只对三台各六个Nav2节点的精确`get_stateReply` writer
增加1墙秒的response-reader匹配/写入有界等待，保留原18个`change_stateReply`的5秒窗口。
Nav2 `get_state`客户端原2秒future超时不变；其预算还包含请求传输和调度，不能推断必有
完整1秒回传余量或保证发现成功。其余默认、request/data/contact端点、DDS transport buffer、
发布频率、SDK版本与任务时钟不变。无自动重试，实际超时仍是infra，旧profile证据不赋予新冻结信用。
这是应用配置的有界等待，不是DDS发现竞态修复声明；新完整原生矩阵待验证。

## 真实物理步进与交付水位

候选调度器标识为`mr3-physical-20ms-v1`。普通策略step为1000个真实1ms物理tick，即1仿真秒；
每20 tick形成20ms量子，暂停后核对Gazebo迭代数和真实仿真时间回执。
重复request id不得重复推进，跨epoch、错误tick长度、迭代/时间不一致或非暂停回执报错。
实现见[步进契约](../../../../../../ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_step_contract.hpp)。

Gazebo ROS clock候选配置为50Hz，见
[mr3_step_clock.yaml](../../../../../../ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/mr3_step_clock.yaml)。
暂停前必须先收到adapter的可靠transient-local一次性`/mr3/initial_inputs_ready`：
schema为`mr3-initial-inputs-ready-v1`，包含epoch、实际stamp、已交付state序号、融合图摘要及各状态/地图源水位。
该确认仅在三台状态新鲜、融合/三份本地图与metadata配对、monitor及Nav2就绪后发布；
不产生observation、目标、任务release或奖励，也不改10Hz状态频率/QoS/源时间。
节点出现在ROS graph不等于它已收到首个volatile状态。worker核对确认的epoch/时间/序号，
暂停后继续使用原drain与精确快照屏障，不能用确认替代后续水位检查。
首次放行前按真实`/clock`发布相位与Gazebo回执对齐；必要的1ms预热tick是真实物理推进，
不计策略transition或奖励。不能假定相位为绝对时间整20ms，也不能补发/改写`/clock`或传感源时间来对齐。
每量子须确认ROS时钟到达同一暂停边界；未来时钟、越过边界或停钟均显式失败。

暂停不等于回调已经排空。候选接口通过information drain确认该边界的timer/地图任务处理水位，
记录state sequence、map version、提交/完成作业计数和融合图SHA256；随后请求显式adapter快照。
快照须匹配目标时间、交付状态水位及融合/三台本地图的内容摘要后才编码。
异步编码结束时继续使用启动时冻结的输入和摘要，不把较晚map或metadata拼入旧快照。
source/generated/received时间含义与10Hz状态、1Hz地图、5Hz租约/回执频率不因暂停或drain而改写。
这些ROS/Gazebo边界仍须原生验证，不提供P4B跨ns-3因果调度信用。

普通step的实际`dt`必须为1秒，不能把P1B的2/3秒观测间隔伪装成固定步长。
若任务终态发生在最后一个量子内，奖励使用评价器原冻结`effective_step_end`与实际短步`dt`；
worker记录物理结束时刻与检测余差，要求余差不超过20ms，不能把余差加进奖励时间或任务成功预算。
超过界限是基础设施/时间契约错误，不能悄悄丢掉该transition或宣称固定dt通过。

评价器以可靠transient-local `/mr3/task_terminal`仅发布
`epoch,end_sim_time_sec,termination_reason`三项冻结标量，先于文件I/O；broker不再轮询评价真值文件。
adapter与broker等待真实clock到达notice结束水位，adapter随后真实安全停止并允许末端快照。
step快照可预先声明`allow_terminal=true`，但只有实际收到该notice才启用终态freshness/monitor例外；
普通取消闭合和外部截断不能开启例外，融合图与实际drain状态序号仍须配对。

若notice恰在上一正常sample已返回的同一物理边界T到达，下一step不发送新动作、不推进物理、
不请求新快照或刷新来源；用新reward序号结算`start=end=T`的真实终态，原保存snapshot逐字复用。
此唯一零时长例外必须`terminated=true,truncated=false,dt=physical_dt=0`，
info显式记录`terminal_observation_reused=true,action_submitted=false,bootstrap=0`。
零有效时长的任务终态不支付新增coverage；评价器仍保留冻结终态地图与当前正确格数诊断，终态奖罚只结算一次。
旧快照不能用于其他step，不能在终态seal后重复结算；notice早于上一已返回边界为基础设施归因错误。

未来P2A消费方不能把每次API返回都当成一次已执行决策。`action_submitted=false`的零时长
终态只结算真实终态奖罚，不得对`requested_action`建立actor训练样本；其终态收益仍须影响此前
真实决策，且不能因额外API记录多乘一次时间折扣。仅设置bootstrap=0或只屏蔽actor loss并不充分。
P2A须预声明并测试collector归并或无动作事件的return/GAE规则，区分API记录数、真实决策数和
仿真秒；确有执行动作的末端短步不能一律丢弃。本步没有实现rollout或验证现成PPO可直接消费。

## 独立奖励与初始化

原P1A真值采样函数与比较器共用同一坐标/阈值逻辑，不另建分母或真值重采样规则。
`task_evaluator`在放行时建立provisional首格账并发布可靠transient `/mr3/reward_ready`，
包含epoch、start_sim_time和初始图摘要。学习端reset必须完成一次seq0绑定：

```json
{"epoch":"EPISODE","sequence":0,"step_start":80.0,"step_end":80.0,"expected_map_sha256":"FIRST_SNAPSHOT_MAP_SHA256"}
```

seq0通过`/mr3/reward_request`发送，选择评价进程本地有界交付缓存中的相同地图，
核查接收时间不晚于reset水位，一次性绑定首actor快照并返回零奖励及`reset_bound=true`。
普通step从sequence1开始；重复seq0同payload幂等，不同内容或已推进后重绑均拒绝。
预热已正确自由格不获奖励，epoch/完整进程reset才创建新账。

后续账本按冻结真值格首次正确free记账；重传、重复上传、未知/自由翻转、地图回退和回环不能重复付奖。
终态仍检查当前地图，历史已奖励面积不替代95%、质量或参与条件。
初始权重为coverage10、时间1、contact20、switch .01、reject .05、success10、failure20；
总coverage奖励至多10，失败罚项大于其上界，真实接触和任务失败罚项可同时发生。
switch/reject来自实际`/mr3/events`，contact来自既有全机体monitor，不能信任学习端自报罚次数。

普通奖励请求包含epoch、sequence、step_start/end及actor快照的`expected_map_sha256`，
必须与评价器当前地图配对；已更晚且不同的图明确失败，不拿future图计算过去奖励。
真正尚未到达的clock/map请求最多等待5墙秒，暂停时仍能处理交付与墙钟保护。
响应只含标量reward、分项/计数增量、质量诊断和地图接收水位/摘要；原OccupancyGrid没有source version时
明确标记缺失，不把本地接收序号伪装成源版本。

任务已终止后，评价器冻结地图A，末端drain可能得到仅供诊断的actor图B。
此时奖励只使用A与原终态，响应记录`map_pairing_scope=terminal_evaluator_frozen_before_drain`、
expected actor摘要与实际评价摘要；绝不按B补coverage或改原成功。
该例外只用于`terminated`最后短步，普通step及需要bootstrap的外部截断仍要求严格配对。

## 终态、截断与关闭

任务自身300秒截止为失败`terminated`，且优先于同刻成功或采样截断；质量/参与、18源持续监测、
零真实非支撑接触和导航闭合仍使用原门禁。基础设施异常由worker抛出并单列，
不伪造正常成功、有效next observation或可训练transition。
截止、奖励连续性与时长比较先把各原端点恢复为整数纳秒再相减；不对浮点差值加容差，
避免212.06到512.06被误算为略少于300秒，不延长任务期限。

采样器外部截止为`truncated`，不加任务失败罚项，并立即seal账本；之后不能再推进奖励。
worker随后发布真实停止请求，继续以20 tick量子推进到所有已知目标取消/终态闭合，
完成下述Nav2生命周期屏障并关闭helper后，再向`/mr3/training_finalize`发送`epoch, ack_sequence, reason=external_truncation`。
评价器保留未完成的`training_external_truncation`诊断；cleanup时间单列、不补奖励，原任务门禁不改。
任务自身已finalize时发送`reason=task_terminal`确认最后奖励响应。
该ACK等待使用独立90墙秒保护，不能延长300仿真秒成功期限；未知所有权不能凭timeout释放。

v5关闭候选协议为`nav2-finalized_then_serial-ros_then_gazebo-v1`，metadata、summary及两端回执使用同一标识。
真实目标闭合后保持物理暂停，依次向tb1/tb2/tb3原生生命周期manager请求SHUTDOWN，
再用GetState确认六节点×三台的18个finalized状态；仅manager返回success不足以证明关闭。
`nav2_shutdown.json`保留实际cleanup clock/wall水位、每个服务响应和状态，而不是将cleanup时间补入任务或奖励。
随后helper关闭、评价器收到最后reward ACK并实际clean退出，launch按实际ProcessStarted的owned action/PID逆序，
逐个正常SIGINT并等对应ProcessExited clean0；全部ROS子进程退出后才原生停止Gazebo。
`MR3_ORDERED_SHUTDOWN`事件序列记录实际身份、信号、退出和阶段墙钟；不能用sleep、丢弃错误或仅父进程0代替。
生命周期拒绝/错误状态、身份不符、非零子退出或阶段墙钟超时仍是基础设施失败，原件保留。
此协议有待新冻结完整原生验证；它不宣称修复FastDDS内部listener竞态，保留原18源发布序号审计。

## 完整reset与资源验证

每次reset重建所有ROS/Gazebo/SLAM/Nav2、动作Future、received store、历史、奖励与终态账本，
新epoch、新输出目录；不只重置机器人位姿，不复用上一轮地图/目标/归一化状态。
同scene/seed重复与跨seed变化须原生证明；旧快照、消息或IPC响应不能跨epoch应用。
每worker分配独立ROS_DOMAIN_ID、Gazebo master端口、私有pipe和输出根。
监督器记录PID、Linux启动tick、父子关系与session；仅回收身份仍匹配的owned进程，
保留异常退出、强制清理和遗留进程的证据，不使用无范围pkill或覆盖旧run-id。
父子与session判定共用同一次`/proc`快照，记录实际扫描耗时和观测间隔；扫描后50ms等待不是50ms覆盖保证。
已由launch捕获启动并wait为clean exit的唯一Gazebo stop CLI可用完整原生同PID/server退出证明，
不能事后补造Linux start tick；其他launch子进程仍须有原进程身份记录。

学习端从conda `ns3gym`运行，`unset PYTHONPATH`并保持`PYTHONNOUSERSITE=1`。
系统ROS子进程清理继承的conda/ROS路径后重新source规范Humble、当前install和Gazebo，
不在同一解释器混入ROS与学习依赖。依赖候选锁定见[requirements-env.txt](mr3_learning/requirements-env.txt)。
具体构建、benchmark及GPU探针命令见
[launch_commands.md](../../../../../../ros2_ws/ros2-multi-robot-automap/launch_commands.md)。

待验证矩阵为1/2/4个并行worker，**每个worker始终三台机器人**。测量完整startup/reset/closure、
每墙秒有效transition、仿真倍率、CPU/RAM、GPU使用和进程残留；宿主资源包含其他活动时须说明归因限制。
GPU探针仅做固定接口forward/backward且无optimizer step，不是策略训练。
`--terminal-probe`是明确的诊断失败实验：仅显式`training_terminal_probe=true`时允许
私有worker向评价器`/mr3/diagnostic_failure`发送绑定epoch/目标真实水位的固定诊断原因。
评价器等真实clock精确到该水位后走原控制失败门禁；不修改contact数据、健康阈值或物理时间。
它验证20ms短终态与同边界零时长尾步，不提供碰撞、策略、95%或网络成功信用；默认关闭。
所有原生/GPU尝试先预声明新推送冻结，失败与重试保留并追加共享log；本文件没有测量结果或PASS声明。
完成上述门禁并提交推送后仍需用户验收P1C，才能进入P2A。
