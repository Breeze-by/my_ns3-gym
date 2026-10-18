# MR3 环境与采样契约 v2（P2A.0准备修订）

2026-10-17用户要求继续完成P2A.0。下列v3快照、v2张量、机器人导航图合成、最终速度门及
`mr3-paired-joint-feedback-drive-v1`及`mr3-drive-target-consumed-v1`实际目标存储相位为本次新接口，
须由新冻结原生矩阵验证；不继承W7或旧P2A的成绩。旧任务指标、reward及20ms评价器相位门禁保持。

本轮P1C验证2026-10-15启动，实际完成时刻见P1C报告。用户于2026-10-16验收P1C并授权P2A；P2A进行中，P2B及后续未开始。
本文件描述已实现环境与验证门禁。W7 `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`完成完整八阶段原生工程矩阵及独立审计，
762项ROS语义和40项conda CPU检查通过；P1C验收范围仍为环境/reset/采样工程。
GPU只保留`b328f84`原model/encoder/probe固定接口3次forward/3次backward、0更新的证据，本次无新GPU调用。
测量和限制见[P1C报告](report/20261015_mr3_p1c.md)。本合同W7规范Git blob保留为审计原件，
当前交付状态文字不反向更改旧证据或已冻结任务定义。
P1C未产生实际策略训练、训练checkpoint、gateway或ns-3闭环；P2A结果另行验证，任务成功仍使用
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

输入快照为`mr3-observation-v3`，张量schema为`mr3-learning-tensors-v2`。
旧v2快照/v1张量及其模型不兼容当前学习入口；历史证据仍按原Git源码/schema重放。
[observation.py](mr3_learning/observation.py)枚举全部列顺序、固定尺度、缺失位与校验规则；
[env.py](mr3_learning/env.py)提供Gymnasium `reset/step`与`Discrete(1000)`。

| Dict键 | shape / dtype | 含义 |
| --- | --- | --- |
| `global_map` | `(3,128,128)` uint8 | 固定32m全局图，occupied/free/unknown二值证据，可重叠 |
| `local_maps` | `(3,3,64,64)` uint8 | 三台各12.8m局部裁剪，顺序tb1/tb2/tb3 |
| `robots` | `(3,71)` float32 | 固定物理尺度的状态、源龄、导航上下文及累计估计活动 |
| `candidates` | `(8,16)` float32 | 几何坐标、清距、前沿数量、三台路径特征及有效位 |
| `history` | `(3,16,4)` float32 | 最多16条已交付估计位姿及源龄/有效位 |
| `task` | `(12,)` float32 | 实际任务时间、剩余时间、地图源龄与缺失/范围位 |
| `action_mask` | `(1000,)` int8 | 保存时的联合动作合法位 |

固定尺度包括坐标16m、路径32m、源龄300s、承诺5s、租约2s；不按当前地图边界或真值归一化。
缺失数值以0和独立有效位表示；超参考尺度值保留并标记越界，不静默clip。
摘要损坏、未来来源时间、非法mask、非有限数值或不匹配的栅格编码均报错。
重放使用原快照/候选/掩码及schema，不能用后续地图重新解释旧动作。

信息桥的`/mr3/received/states`保留同一received record中的原始`odometry`，包含frame和source stamp；
不得以地图位姿或未交付的本地新样本补全活动量。
新增活动字段只使用已交付信息：放行后连续、单调的本机odom平面位置弦长累计，以及本epoch中
唯一accepted-goal计数。map/TF校正不计入路径；重复/乱序源样本不加长度，缺失、同源时间冲突、
frame改变或超过`.5s`间隙使路径完整性失效，并单独编码有效/完整/就绪/越界位。首次放行后样本建立
锚点，不把预热移动补进任务。该状态是估计活动proxy，不替代评价器的真值1m及目标门禁，不另加移动奖励。

机器人自身导航图使用`mr3-own-known-shared-unknown-v1`：保留本机已知free/occupied，
只以最后交付共享图补本机unknown；不按机器人位置清占据或吸附起点。全局hub仍occupied-wins。
候选v5的路径、到达圆盘及前沿都来自与实际`/tbN/navigation_map`字节配对的已交付导航图。
原始own、hub及实际发布的三个navigation地图共七份输入按SHA归档，不用后来的图重算旧候选。

adapter模式的controller和behavior速度统一经过Nav2 smoother及`/motion_safety`最终门，
该门是三个`/tbN/cmd_vel`及`/tbN/mr3_drive/target`的唯一发布者，不选方向或目标。
`cmd_vel`保留Twist输出与本地FIFO核验，实际adapter驱动只订阅带唯一来源标记的target。
完整请求因接近方向被拒绝时，
只在线速度归零、原角速度不变的请求重新通过全部同一几何/源龄/残余移动检查后保留该转向；
状态无效、包络不足或超界不能走此分支。否则保持原请求或全零，每次分量过滤及重验均留证。
命令硬上限为线速度`.20m/s`、角速度`.8rad/s`；三份实际`params/nav2_params_tbN_0.yaml`
中的controller、实际`behavior_server`及smoother共同绑定此上限；通用DWB配置同步线速度和加速度。
V15将导航队友预测速度界独立固定为原`.26m/s`，用于`peer_safety_radius`、
`body_points`障碍cloud和`grid_with_peers`导航栅格；不得再alias命令上限而随降速缩小。
该界恢复原冻结导航几何，不能替代最终保护门的`.30m/s`实测执行模型或原`.50m`任务门。
V14同输入cloud回放已证实原alias的实际几何回归，原FAIL保留，新冻结仍须完整原生重验。
实际三份FollowPath使用已安装Nav2 RotationShimController，primary仍为原DWB：路径前向采样`.30m`，角差启用/退出均`.5rad`，旋转参考`.8rad/s`，角加速度参数`3.2rad/s²`，closed_loop使用本机实测角速度。短路径、变换或旋转检查失败时仍可委托DWB，不承诺所有候选安全可执行或必有平移。Shim不选择探索目标，原critic权重/规划器/goal checker不变。
smoother显式`20Hz/OPEN_LOOP`，线加/减速度参数`±.5m/s²`、角`±3.2rad/s²`；DWB一致。理想指令组合`.5 + (.287/2)*3.2 = .9592m/s²`位于原轮缘`1.0m/s²`预算内；这不证明实测机体、每次墙钟插值或连续制动界。Shim参考`.8`也不保证其每个原始输出不超该值，最终smoother/保护门仍核严格硬界。
Nav2插值恰好高出`.20m/s`或`.8rad/s`一个binary64相邻值时，明确记录原值并规范到上限；
第二个相邻值及更大超界仍拒绝，最终输出严格不超过原上限。
本机原传感、已交付队友状态、源龄、命令超时和任务停止控制放行。近距离的共同制动区域内
禁止朝队友接近，具体常数及计算以版本化纯几何实现为准，不放宽原`.50m`失败门槛。
角速度来自本机原始odom，其未观测加速包络使用`odom_source_stamp`对应源龄和`7rad/s²`界；
位置及yaw不确定性继续使用较旧的`min(odom,TF)`源时间，不能以新odom刷新旧TF的几何时间。
trace分别保存两项source stamp/age。模型依赖实测平面速度`.30m/s`、角速度`1.2rad/s`界；
降低命令上限不能替代完整原始twist向量、源时间、转向响应及停止路程的原生核验。
V13受控normal commit在实际state/peer依赖满足后，核验当前本机源绑定标量与所选raw，以及release后保留历史中source≤commit clock的原始平面/角速度范数；received peer必须有真实raw odometry且v/w/可选标量一致。无raw的本机紧凑状态只作独立重建的平面标量检查，完整角XYZ另由所选/历史raw核验，不把完整odom重复加入actor或每20ms本机状态。超原`.30/1.2`模型界触发永久零与明确`normal_control_model_invalid`负ACK；不发布通用exploration_failure制造任务终态。worker沿现有callback-error/abort_cleanup严格关闭，整次尝试基础设施无效，数据禁止训练。此类normal资格错误不依回调先后归因到任务；真实release/end窗口归属由离线原件核验，不新增终态样本救回支路或改变正常state→peer→motion→storage→evaluator顺序。未来源/预热历史不提前归入任务，后到健康样本不能掩盖保留历史中的因果峰值。raw own非有限值也可能先触发既有settled失败，该分支不承诺重分类任意畸形ROS输入。
轮耦合停止另有`.02s`余量，同时计入`.78s`完整转向/制动时域和双方累计停止reserve；
`.5m/s²`是全局停止包络参数，不声称中心速度每瞬时都以此减速。这是依赖输入/速度/反应/制动界的执行保护，不能保证任意定位跳变或无界迟到下安全。
v9的ideal information发布器以pending队列保留未到当前clock的本机odom，选取最近且source≤clock的已入站样本；不能让future最新样本抹去仍有效的causal缓存而跳过整次发送。256有界队列、冲突/溢出明确失败，并以真实入站/选取账本独立核验。选取及`.5s`有效门以整数纳秒比较：源不得晚于clock，源龄闭区间`[0,500000000]ns`，多1ns仍拒；wire原double源字段保留，无epsilon。修正原double相减将精确`.5s`误判为`.5000000000000001s`的端点错误，与现guard时间规范一致。非受控状态发布仍`.1s`、源龄门仍`.5s`，不借未交付的队友raw状态。`state_audit_path`仅诊断文件，原始入站与选取引用不进入actor、候选、掩码或奖励。该缓存修复不证明跨节点同clock回调总顺序或所有时刻无竞态。

v8增加`mr3-settled-turn-v1`旁证分支，只对原near nonclosing拒绝后的零线速度、原角速度请求生效。own连续最终零线速度publication≥`.94s`，之后三条完整去重own odom的全平面速度≤`.01m/s`、每源age及gap≤`.10s`，才可建立资格；资格起点不得早于任务release；worker初始三台真实stored-zero屏障先于同clock release，不把驱动出生前预热publication计入。实际native连续存储零线速度≥`.78s`及全量160ms时延由独立消费审计另核验。每个原body margin仍含原位置/TF源龄误差和`.02m`余量，并须至少`.1518m`：自身完整零线速度段总漂移预算`.0078m`加队友完整制动`.144m`。

该分支依赖新增条件物理模型：从activation前最后完整own odom锚到下一实际非零线速度存入/结束，持续全平面速度≤`.01m/s`且连续总中心路程≤`.0078m`。重复授权不能刷新整段预算；runtime及独立消费者对原始速度、相邻odom chord速度、整段累计弦长和源完整性作硬检查，违例记真实failure。有限采样弦长是连续路径下界，过去静止样本也不能证明未来，因此这些记录只提供必要采样证据，不授连续或无条件安全定理。publication到actual storage的资格终点须由三ACK-before-advance屏障与独立实际回执绑定，不能提前撤证掩盖违例。全部新增状态只来自本机原odom与自身最终输出历史，不进入actor、候选、掩码或奖励；队友仍只读已交付状态。原unsupported/state/body门、原方向检查及所有任务/物理门保持。

worker在任务放行前等待三台运动输入就绪，并保存图上唯一速度发布者端点、本地actual接收FIFO及
同clock三台输出消费后的ACK。当前Humble的身份范围是`graph_at_callback`，不是逐包MessageInfo
或Gazebo执行器消费确认。另存实际global/local
master costmap完整输出和源头/接收时钟。这些诊断不进入actor，也不冒充planner同刻消费确认。

最终门将同一有界速度写为`/tbN/mr3_drive/target`上的String JSON：schema为
`mr3-drive-target-v1`，恰含`schema,epoch,robot,clock_ns,decision_sequence,linear_x,angular_z`。
source clock为原保护决策时刻，序号为该机单调保护决策序号；不能从后来的值或时间补造。
adapter的局部`libmr3_gazebo_diff_drive.so`以tagged模式订阅该唯一入口，合同算法仍为
`mr3-paired-joint-feedback-drive-v1`。该插件以Gazebo ROS 3.9.0为来源，保留BSD许可及
[来源说明](../../../../../../ros2_ws/ros2-multi-robot-automap/src/multi_robot/vendor/gazebo_ros_diff_drive.PROVENANCE.md)，
不替换系统库。每次实际驱动更新从本机两个轮关节的实测轮缘速度出发，以同一个插值比例朝
最终命令对应的左右轮目标推进，每轮变化不超过`1.0m/s² * sim_dt`；不再累加隐藏轮速指令。
V13 helper以本机受支持long-double构建的向下预算、向上差值区间及始终向内的binary64比例避免有限精度等号误授资格；独立exact Fraction门不放宽，disabled/零dt语义保留。该性质约束施加的轮速参考，不能替代对机体滑移、接触、有限力矩及实际停止响应的验证。
最终速度门仍立即输出原请求、经完整复验的`(0,w)`或全零，不增加其后的另一个策略/速度门。

物理参数保持30Hz驱动更新、`.287m`轮距、`.066m`轮径、`1.0m/s²`轮缘加速度、
`20Nm`力矩和原WORLD里程计；真实1ms物理tick、20ms量子及任务时钟不变。
原`.30m/s`机体平面速度、`1.2rad/s`角速度、`7rad/s²`转向加速度、`.78s/.144m`每机停止响应、
`.50m`队友包络及任务/接触/关闭门禁保持，须在同一冻结原生矩阵独立核验。

驱动在本机mutex内验证tag的epoch/robot、有限硬界、非未来/不回退源clock和严格增加的决策序号，
完成目标存储后在`/tbN/mr3_drive/status`发布`mr3-drive-target-consumed-v1`。
该状态恰含`schema,epoch,robot,clock_ns,decision_sequence,source_clock_ns,cmd_seq,linear_x,angular_z`；
clock为实际回调时的Gazebo世界时刻，source clock及值来自收到的tag，cmd_seq为本机接收序号。
目标及状态均使用reliable/transient-local/depth1；预热期间仍是最新目标语义。

worker按订阅topic核对机器人身份，保存真实状态。初次释放前、每次任务及关闭阶段的正步物理推进前，
要求三台状态与当前暂停physical/ROS clock、保护决策序号和两个速度值完全一致，且仍是各驱动的最新目标。
三台实际回执全部到达并consume后才向step helper发送下一20ms推进请求；等待使用10墙秒保护。
同一暂停边界的已消费cache可复用，不能跨clock、借用未来或历史回执；callback错误、身份冲突或边界改变
阻止推进。初次尚未放行的暂停query与1ms clock对齐保留原例外，必须在放行前完成相同三台目标存储门。
这证明驱动回调已经存储该目标；30Hz轮指令与机体运动由另外的原始证据核验，ACK不保证即时施加或身体停车。

正式原件另存三个`drive_tbN.jsonl`、实际spawn的`drive_model_tbN.sdf`、`drive_targets.jsonl`、
`drive_phase_worker.jsonl`及`drive_topology.json`。驱动schema为`mr3-drive-actuation-v2`，记录
epoch、本机、精确仿真ns、实际库路径及四份编译源摘要（cpp、插件header、paired helper、target合同header）。
`command_received/status_publish`绑定真实tag接收和状态发布，`target_rejected`保留拒绝；
`actuation`绑定该次30Hz更新实际使用的最新cmd_seq/target序号与源clock、两轮实测/目标/施加值、alpha及dt。
worker原件区分`ack_received/ack_consumed/advance_permitted/physics_completed`，保留expected motion、
三台状态、request_id及physical receipt；不能用发布或存储事件补成30Hz执行事件。
图审计要求target唯一发布者为motion_safety，status为该机实际驱动节点，tagged驱动没有cmd_vel订阅旁路。
独立消费者绑定tag原JSON、驱动状态、推进顺序、实际源延迟和加载库SHA；原160ms及物理/任务门保持。
旧`mr3-drive-actuation-v1`及headerless Twist消费仅按其原冻结历史/非tagged兼容范围解释。
缺省audit路径为空时不写驱动原件；正式worker提供路径和epoch，独占创建且写入失败仍为原生失败。

## 本机SDK服务响应等待

原W7配置对三台各六个Nav2节点的精确`get_stateReply` writer
增加1墙秒的response-reader匹配/写入有界等待，保留原18个`change_stateReply`的5秒窗口。
Nav2 `get_state`客户端原2秒future超时不变；其预算还包含请求传输和调度，不能推断必有
完整1秒回传余量或保证发现成功。除下面新增参数回复规则外，其余默认、request/data/contact端点、DDS transport buffer、
发布频率、SDK版本与任务时钟不变。无自动重试，实际超时仍是infra，旧profile证据不赋予新冻结信用。
这是应用配置的有界等待，不是DDS发现竞态修复声明；W7完整矩阵仅提供其实际工程范围。

P2A.0 V14为三台各`controller_server`、`behavior_server`、`velocity_smoother`的九个精确
`get_parametersReply` writer配置1墙秒的可靠匹配/写入等待；无通配、default、service fallback或reader规则。
V13首个参数回复在特定响应reader GUID匹配等待分支超时，早于序列化/write；原九项默认100ms由本机SDK工厂读取证实。
1秒是针对该分支的有限余量，不证明原生可靠性或充分性。参数读回仍为同一暂停release的九节点完整typed核验，
客户端原30秒总墙钟guard及45秒hook不变，无重试、分包、物理推进或丢弃失败。实际超时仍为infra；必须新冻结完整矩阵验证。

## 命令、租约与导航期限的纳秒端点（W7实现）

v6实际截止探针暴露两次合法KEEP误拒：254.6→256.6、255.6→257.6的float差值略大于2，
但各端点恢复为整数纳秒后的差恰好2000000000；误拒各产生-0.05真实处罚，原件保留。
同类纯协议反例还包括精确10/60秒超时晚触发、5秒承诺晚释放、2秒租约晚到期和0.2秒心跳漏边界。
W7实现统一复用`mr3_episode.timestamp_ns/elapsed_ns`：分别恢复原端点再比较，不加epsilon，
也不通过改写source stamp或假物理tick消除差异。

命令要求`created_ns <= now_ns < expires_ns`，且`0 < expires_ns-created_ns <= 2000000000`；
真实未来1ns、超限1ns和到期等号仍拒绝。worker/心跳的到期端点先将整数纳秒加2秒再序列化为原秒字段；
dispatcher的租约、待替换目标、5秒承诺及10/60秒期限使用相同端点口径，承诺mask/remaining也一致。
JSON字段、原消息时间、重复命令原payload比较和真实所有权释放规则保留。
这不是放宽2秒/5秒或RPC期限；正数duration若不足可表示的1ns会明确报错，不静默变成零期限。

独立command-time审计须识别合法窗口的`expired_or_invalid_command_time`假拒，以及非法窗口被接受；
其他有实证的导航/掩码拒绝保留。v6主审计PASS仅验证了记录一致，不能证明没有该bug。
修复已在全新推送W7冻结完成完整[v7矩阵](report/assets/20261015_mr3_p1c/predeclared_native_plan_v7.json)与独立命令时间门禁，
具体原件和限制见[P1C报告](report/20261015_mr3_p1c.md)；不将v6结果拼入W7，不改写原失败。

## 真实物理步进与交付水位

已实现并验证的调度器标识为`mr3-physical-20ms-v1`。普通策略step为1000个真实1ms物理tick，即1仿真秒；
每20 tick形成20ms量子，暂停后核对Gazebo迭代数和真实仿真时间回执。
重复request id不得重复推进，跨epoch、错误tick长度、迭代/时间不一致或非暂停回执报错。
实现见[步进契约](../../../../../../ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_step_contract.hpp)。

W7的Gazebo ROS clock已验证配置为50Hz，见
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

暂停不等于回调已经排空。已实现接口通过information drain确认该边界的timer/地图任务处理水位，
记录state sequence、map version、提交/完成作业计数和融合图SHA256；随后请求显式adapter快照。
快照须匹配目标时间、交付状态水位及融合/三台本地图的内容摘要后才编码。
异步编码结束时继续使用启动时冻结的输入和摘要，不把较晚map或metadata拼入旧快照。
source/generated/received时间含义与10Hz状态、1Hz地图、5Hz租约/回执频率不因暂停或drain而改写。
这些ROS/Gazebo边界已由W7原生工程验证，证据见[P1C报告](report/20261015_mr3_p1c.md)；
不提供P4B跨ns-3因果调度信用。

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

W7已验证的关闭协议为`nav2-finalized_then_serial-ros_then_gazebo-v1`，metadata、summary及两端回执使用同一标识。
真实目标闭合后保持物理暂停，依次向tb1/tb2/tb3原生生命周期manager请求SHUTDOWN，
再用GetState确认六节点×三台的18个finalized状态；仅manager返回success不足以证明关闭。
`nav2_shutdown.json`保留实际cleanup clock/wall水位、每个服务响应和状态，而不是将cleanup时间补入任务或奖励。
随后helper关闭、评价器收到最后reward ACK并实际clean退出，launch按实际ProcessStarted的owned action/PID逆序，
逐个正常SIGINT并等对应ProcessExited clean0；全部ROS子进程退出后才原生停止Gazebo。
`MR3_ORDERED_SHUTDOWN`事件序列记录实际身份、信号、退出和阶段墙钟；不能用sleep、丢弃错误或仅父进程0代替。
生命周期拒绝/错误状态、身份不符、非零子退出或阶段墙钟超时仍是基础设施失败，原件保留。
此协议已在W7完整原生工程矩阵中验证；它不宣称修复FastDDS内部listener竞态，保留原18源发布序号审计。

## 完整reset与资源验证

每次reset重建所有ROS/Gazebo/SLAM/Nav2、动作Future、received store、历史、奖励与终态账本，
新epoch、新输出目录；不只重置机器人位姿，不复用上一轮地图/目标/归一化状态。
W7已对同scene/seed重复与跨scene/seed变化进行原生重建和源水位检查，实际估计差异及限制见P1C报告；
新运行版本仍须独立证明，旧快照、消息或IPC响应不能跨epoch应用。
每worker分配独立ROS_DOMAIN_ID、Gazebo master端口、私有pipe和输出根。
监督器记录PID、Linux启动tick、父子关系与session；仅回收身份仍匹配的owned进程，
保留异常退出、强制清理和遗留进程的证据，不使用无范围pkill或覆盖旧run-id。
父子与session判定共用同一次`/proc`快照，记录实际扫描耗时和观测间隔；扫描后50ms等待不是50ms覆盖保证。
已由launch捕获启动并wait为clean exit的唯一Gazebo stop CLI可用完整原生同PID/server退出证明，
不能事后补造Linux start tick；其他launch子进程仍须有原进程身份记录。

学习端从conda `ns3gym`运行，`unset PYTHONPATH`并保持`PYTHONNOUSERSITE=1`。
系统ROS子进程清理继承的conda/ROS路径后重新source规范Humble、当前install和Gazebo，
不在同一解释器混入ROS与学习依赖。依赖锁定见[requirements-env.txt](mr3_learning/requirements-env.txt)。
具体构建、benchmark及GPU探针命令见
[launch_commands.md](../../../../../../ros2_ws/ros2-multi-robot-automap/launch_commands.md)。

本次验证矩阵为1/2/4个并行worker，**每个worker始终三台机器人**。测量完整startup/reset/closure、
每墙秒有效transition、仿真倍率、CPU/RAM、GPU使用和进程残留；宿主资源包含其他活动时须说明归因限制。
GPU探针仅做固定接口forward/backward且无optimizer step，不是策略训练。
`--terminal-probe`是明确的诊断失败实验：仅显式`training_terminal_probe=true`时允许
私有worker向评价器`/mr3/diagnostic_failure`发送绑定epoch/目标真实水位的固定诊断原因。
评价器等真实clock精确到该水位后走原控制失败门禁；不修改contact数据、健康阈值或物理时间。
它验证20ms短终态与同边界零时长尾步，不提供碰撞、策略、95%或网络成功信用；默认关闭。
所有原生/GPU尝试先预声明新推送冻结，失败与重试保留并追加共享log；本文件给接口约束，数值结果见P1C报告。
短工程采样不证明多日稳定或95%任务成功。真实短步和零时长终态的rollout、时间折扣及GAE处理
必须在P2A明确验证，不能把本接口完成当成标准PPO可直接使用的证明。
用户已于2026-10-16验收P1C并授权P2A；P2A须独立实现和验证上述消费方规则，不能追认P1C为策略训练证据。

P2A.0的`mr3-p2a0-outward-cancel-v4`是显式32步外部工程刺激，不供生产探索或训练兜底。
保留初始`[0,1.5)`与第二次`[13,15)`合法GOAL窗口及v3 received反向bearing/outward排名；
已交付状态须fresh/valid、目标active/owned且有接受记录、线速度至少`.08m/s`、
本phase received路径增量至少`.05m`，并且原per-robot及joint mask均允许WAIT，才请求运动中取消。
`[10,13)`及`[28,32)`为有限WAIT截止窗口；WAIT被掩码禁止时只合法KEEP并保存missing，不越过5秒承诺。
只有实际step返回且command的epoch/观测序号/digest/action/正整数command_id全部绑定后，才锁存已提交WAIT；
显式action_submitted非bool拒绝，False不计提交。第二GOAL还要求本机首阶段成功WAIT至少3秒、
fresh且导航idle、received线速度绝对值至多`.01m/s`；缺WAIT记录不发第二GOAL。该速度只作选择代理，
不代替独立raw完整平面速度、三连续rest样本、.78秒/.144米及实际cancel闭合的原物理门。
旧v2/v3行为保持，未知版本及错误步数仍拒绝；工程capacity资格适配不提供历史P1C吞吐信用。


V16新增`mr3-p2a0-outward-cancel-v5`，复用V4的32步、两GOAL窗口、取消条件和实际返回记账。
仅对外部工程新GOAL增加筛选：本快照三机位置均fresh/valid且有限，每个所选目标相对每个队友的
直线outward margin均有限且不小于0；重合、零分母及运算溢出/下溢拒绝该GOAL。KEEP/WAIT保持。
筛选后沿用原GOAL数量、反向机会、outward、path及action id排名；原snapshot和actor joint mask不变。
V5诊断的max_legal_goal_components只指工程筛选子集，另存原/过滤后合法动作数，不代表actor候选可用性。
该筛选不保证Nav2瞬时路径、运动中cone或以后队友位置的安全；原guard与全部独立活动/物理门仍决定信用。
原角覆盖要求每机至少一有效方向段、三机总体正负、至少一机先后反向，不添加每机双向要求。
V4默认行为与旧V2/V3保持；新reset包装器只识别精确V5/32，原8轮/33API和raw物理/角向数学不改。


V17新增`mr3-p2a0-outward-cancel-v6`，仅在外部刺激中增加已接收候选的晚目标机会。
旧初始及`[13,15)`窗口仍原V3排名，V6另外将`round(task_elapsed_sec*1e9)`按整数纳秒
与`[15e9,26e9)`比较；晚窗口直接沿用原outward几何排名，真实elapsed原样保留，不伪造V3输入时间。
整数端点避免`46.12-20.12`得到略小于26而错在第26秒派新GOAL；V4/V5默认窗口和诊断保持。
晚GOAL仍要求原mask/V5非接近筛选、首WAIT至少3秒、fresh idle及received静止代理，
active目标、缺首WAIT或不满足恢复条件时保持原合法KEEP/WAIT。原`.08m/s`、phase路径`.05m`运动取消条件、
5秒承诺、28秒WAIT截止及真实step返回typed command锁存均不变。正常1秒输入最新新GOAL在25秒，
最早30秒可合法WAIT，至32秒剩2秒只是测量机会，不能替代原`.78s/.144m`和连续raw rest样本。
每机器人seed净空`.29m`及候选/actor mask不改；候选不合法时只等待。原V2/V3/V4/V5均可复现，
V6只作32步工程刺激，不提供生产探索兜底、原生运动/停车或策略效果信用。


## P2A.0 v10 显式受控执行阶段（待同冻结原生验证）

在`mr3_stepped=true`时，启动实际旧零输出/三存储ACK后接管timer，再真实推进20ticks到新clock；每一物理边界暂停，完成state_phase→peer_phase→motion control→三台driver存储→evaluator相位后再推进。三阶段共用epoch/request_id/target_time_ns且成功normal必须clock完全相等。状态节点取消周期state发布，选择自身实际causal入站、真实发布bundle及side消息；受控有效状态节拍改为50Hz，warmup/非stepped原10Hz保持。peer必须实际收到匹配SHA、sequence和publication开始后callback的六side及main bundle，才能真实发布障碍并ACK；guard必须实际收到两份ACK及main bundle、own causal输入，唯一正常输出并回收后ACK。墙超时10秒使本轮invalid，不推进仿真/修改源时间。诊断引用、raw ingress与协议ACK不进入actor/奖励。

normal回执同clock不可覆；独立`phase_kind=stop`只能永久三零、ready=false，可在相同clock用更高seq，单独`/motion_safety/stop_status`及控制ACK，不授几何/缺输入安全信用。终止或取消需真实通知，随后每次20ticks关闭推进仍等真实零存储。真实terminal可取消pending state commit；仅排空可复用最后真实水位原引用且保留源时间，不能再发布新state或LIVE推进。未返回reset的基础设施失败以隔离abort begin→真实cancel/zero/Nav2/helper/navigation_closed→finalize→原有序native关闭，不产生reward/伪造transition；正常sealed评价器规则不变。新的peer/control/information独立原件审计与所有旧任务/物理门均必需，详见[本版报告](report/20261017_mr3_p2a0_v10.md)。

阶段ACK绑定各节点实际callback前缀，不构成跨进程原子事务。worker已实际处理stop或主动发stop请求后不得再用normal推进或恢复；guard一旦stop，新输出只能为零。guard发出但DDS尚在途的窗口保留原最多20ms终态排空和完整160ms驱动/机体反应门；源stop与旧normal permit的窗口另作诊断，不声称零延迟跨进程封闭。

工程与策略结果审计共用受限bootstrap审计入口：仅精确v1元数据、唯一实际三零交接、三takeover、实际回收/原生存储以及完整控制账本均成立时，原W7物理审计的setup→受控量子切换参数取bootstrap起点T0；输入仍为全部原始receipts，原整数/连续/量子数学不改。真实任务release仍为交接终点T1，奖励/接触/终态等继续使用T1。legacy保留原release调用，未知协议拒绝，每次调用后还原原审计函数；工程fixture的capacity排除不进入策略审计。本轮只验证接线，无新采样/优化或策略效果信用。

## P2A.0 显式隔离物理诊断（V18，尚无验收信用）

默认不加载观测或物理配置插件。仅在事前声明的单次命令中设置
`MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE`，launch严格核对三机器人stepped adapter、
唯一run/首episode、场景、seed、有限整数采集窗口和两个已构建库的路径/SHA，
生成绑定实际epoch的独占JSON。gzserver消费该绑定；actor、候选、mask、reward和
原world/model几何字节保持原契约。未设置该变量时，默认gzserver参数和生成模型与旧版逐字相同。

独立ModelPlugin仅向隔离文件记录1ms求解前后配对状态、原点/CoG速度、轮关节和
实际保留的接触数据；空接触列表不证明没有支撑接触。它不发布消息、不调用物理setter，
其同步读回/JSON/I/O有墙时开销。独立SystemPlugin在首个实际1ms更新边界记录
ODE原生数值与配置缓存：baseline不调用setter；iters150仅调用一次iterations50→150，
其余读回字段须保持。缓存solver类型不冒充私有求解函数指针证明。新库与原a014驱动
分别保留源码宏、构建产物、真实加载路径及owned PID/start/maps证明。

原30Hz里程计、.78秒/.144米停车、全平面速度≤.01连续3个唯一源样本、任务/安全门、
1ms物理步与20ms策略边界均不变。新增1ms积分/有限差分只用于归因，不能代替原停车门。
两次固定三机open101/32步诊断最多66条API记录、3600原生墙秒，0训练/0更新，
不计四阶段矩阵或95%任务信用；实际失败全部保留。修复之后仍须另立新冻结，完整重验四阶段。

## P2A.0 研究 world 的显式 QuickStep 执行配置

本执行修订仅在`p1c_open.world`、`p1c_rooms.world`、`p1c_corridors.world`中，
增加唯一审核过的`ode/solver`块，显式指定`type=quick`及`iters=150`。
SOR、CFM、ERP、接触参数、重力及其他物理配置保持原值；模型、碰撞体、场景几何不变。
对应`mr3_p1a/open.json`、`rooms.json`、`corridors.json`仅更新单个`world_sha256`，
使任务加载、真值栅格、scene审计、reward reset和evaluation继续绑定所选实际world的完整文件SHA。
任务loader仍只使用这一实际world身份；不以旧geometry摘要代替实际world来源，
不通过运行时物理setter绕过world配置或审计。

六个修订文件的完整新SHA如下，路径相对ROS工程根：

| 文件 | 完整新SHA256 |
| --- | --- |
| `src/multi_robot/worlds/p1c_open.world` | `ed3fcd526d7367e8e0eb5245c365ba60631a6f4a6d725c64134221217ddc4846` |
| `src/multi_robot/worlds/p1c_rooms.world` | `92ac7dff82bdf03b9f1ce3e9f075a3f59ca07df23c2f89fca654b3f423742768` |
| `src/multi_robot/worlds/p1c_corridors.world` | `7e15f3ba716fd2f6cdc55310ab3064e61c8d0d34c4f8cba79a964260a8dac051` |
| `src/multi_robot/config/mr3_p1a/open.json` | `e4a3c25374bb482a0104530f1765f17b807377e0a5c85bc42d6645a63bfc5487` |
| `src/multi_robot/config/mr3_p1a/rooms.json` | `c4ddca59d8b955f5410a0e639736263c750d6e819a864020c3e4e6da783a811e` |
| `src/multi_robot/config/mr3_p1a/corridors.json` | `44cc8593cf69206a36b3a7bf82b2008957d5454caaa040dc4b3ac815e1b778a6` |

这六份执行/元数据原件与W7原字节不同。受限审计仅对白名单中这六个固定路径，
同时核验声明冻结Git对象、当前文件及上述固定新SHA，再作逐字投影：
三个world移除唯一固定新增的`ode/solver/type=quick/iters=150`块后必须完全恢复
`TASK_BASE_FREEZE`的原world；三个JSON仅将对应实际新world SHA替回该场景原W7 world SHA，
必须完全恢复原JSON。任务JSON的新world SHA须来自独立验证的对应实际world，不能由调用者自证。
其他machine/config文件仍要求与原W7逐字相同。审计回执分别保留实际新SHA、
物理配置或world-SHA元数据修订类别、原W7来源与投影SHA，不将新文件记为原始W7字节。
旧SDF、任务JSON、sourcepack、失败、诊断及各冻结结果均保留，不改写或追认其范围。

SDFormat9.7的每场景43项schema字段归一化对照只允许迭代数`50→150`不同；
43项是schema字段数，包含可选及非活动引擎分支，不是43次测试，也不是实际native参数读回。
静态几何、ROI和真值mask一致性只证明任务定义保持，不能证明求解收敛、机体响应或运行稳定性。
完整新冻结须保留实际world路径/SHA、任务JSON SHA、Gazebo命令及二进制来源，
并按事前声明的实际参数核验范围解释生效证据；不把缓存solver标签冒充私有执行函数指针证明。

物理步`1ms`、受控量子`20ms`、实测全平面速度界`.30m/s`、完整角速度范数界`1.2rad/s`、
原角加速度界`7rad/s²`、停车响应`.78s`与路程`.144m`、全平面速度≤`.01m/s`的
连续`3`条唯一raw源样本均不变；积分、位姿差分或更高求解迭代数不能替代这些原门。
任务仍为三机`95%`覆盖、`300s`期限、每机至少`1m`参与及原目标要求，
保留`18`路持续机体接触监测、零真实非支撑接触、`.50m`队友安全包络、原地图质量与导航闭合门。
原`a014`驱动及目标存储协议、actor、候选/掩码、observation/tensor schema、reward和评价器数学不变。

本执行修订本身不授予原生矩阵、95%任务或策略信用。应用后须另立干净推送的新source freeze，
在同一冻结下完成原interface、terminal、reset、deadline四阶段及全部独立门禁；
不得将旧矩阵或隔离对照结果拼接为新矩阵，也不因此启动PPO或重置累计训练余额。

## P2A.0 native Ray×Box 碰撞执行修订

该执行候选保留原模型尺寸、惯量、轮组、碰撞体、激光量程、噪声与传感器外参，
只修正 Gazebo 所用 ODE 的 Ray×Box 碰撞查询中近乎平行分量的 slab 判定。
新独立 SystemPlugin `libmr3_ray_box_corrector.so` 通过公开
`dSetColliderOverride(dRayClass,dBoxClass,callback)` 安装审核过的固定回调，
不修改其他 shape pair、接触动力学、控制器、driver、SLAM、地图融合、候选、动作掩码或奖励。
不得以删除射线、自体过滤、清除已有 occupied、减小 `.29m` 候选净空或放宽安全门代替源级修正。
此段是待新冻结逐项核验的执行要求，不把源码提案或 CPU 几何反例写成原生验收结果。

插件只由显式 MR3 任务入口接入，位于 gzserver 的 ROS 参数分隔符之前；
应在正确研究 world 的 ODE 已初始化、time/iteration 均为零且首个研究传感器尚未执行之前安装一次。
实际安装时机、唯一次数、epoch、库类型、实际解析的库路径和源码身份必须由实际 native ledger 保留。
源代码、header、CMake/launch 接线、新实际 ELF、build commands 和归档字节需对应同一审核冻结；
原 Gazebo 可执行体、原 ODE 库、原 driver 和 Shim 的既有来源检查仍继续，
新增 actual `/proc` 映射须绑定每个 episode 自己的 owned gzserver PID/start/epoch 与祖链。
仅有文件名、字符串、GetParameters 或旧 driver 的相同 SHA，不能证明修正回调实际被研究进程使用。
安装原件还必须只读取得实际 ODE world 的 `native_ode_quickstep_iterations=150` 整数及
`physics_max_step_size_sec=.001`，二者与事前配置一致；缓存 SDF 标签不能替代这项实际读回。
不得将诊断-only SensorPlugin 或运行时物理 profile setter 混入正式四阶段命令。

原 CMake/launch 的受限执行修订须同时验证固定 Git 原件、实际冻结 Git 对象、worktree 与新 SHA。
按审核的固定增量移除新回调接线和已有 opt-in 诊断声明后，必须逐字恢复原规范 source；
回执区分实际执行 SHA、规范来源 SHA 与逆投影，不将新源码标记为原始字节。
共享 current auditor 的这项精确分派必须同时用于正式审计和预检，不能只在启动前临时改内存 pin。
除明确列入的新 source/binary 与固定六 world/task 文件外，其余冻结源和所有原数值门保持。

`iters=150` 是针对前次制停证据失败所选的单一工程候选，不因隔离静止诊断而视为修复已验。
原 `1ms` 物理步、`20ms` 受控量子、`.20m/s` 命令上限、`.8rad/s` 命令角速上限、
实测 `.30m/s` 全平面速度界、`1.2rad/s` 完整角范数、`7rad/s²` 样本角加速度界、
`.78s` 制停期限、`.144m` 路程和 `.01m/s` 下连续 `3` 条唯一源样本均保持原门。
完整 interface32、terminal 两 episode、reset 两 worker 共八 episode32、deadline300 必须在新同一冻结下重做。
interface 仍要求原角向覆盖和每机 A 或 B 制停信用；reset 仍按八 episode 逐机 A 或 B 合并，
任一实际 eligible 的超界、非休止或源错误不能被其他 episode 信用冲销；reset 原角向 sampled-bounds 范围不变。
四阶段原 608 API、596 脚本决策、18000 wall-second 工程上限与失败后保留原件并跳过后续阶段不变。
本工程候选不授予 `95%` 三机建图、有效分工、PPO 学习或冻结策略可靠性信用，不重置学习余额。


## P2A.0 Ray×Box 安装阶段与计数可用性更正

本修订保留上述规范与全部数值门。先前版本在 `WorldCreated` 回调中读取
`World::Iterations()` 并要求零，是错误的生命周期测量：对应 Gazebo 11.10.2
源码在 `World::Load` 期间发出创建事件，而迭代计数直到后续 `World::Init`
才初始化。V23 在该联合前置检查处失败；原日志未记录各分项值，具体失败
分支未观测。本次源码审查独立确认了提前读取未初始化计数的缺陷。V23 的
configuration-only 原件、进程异常、强制失败样本清理及全部正式 FAIL 均保留，
不追认为安装成功或迭代数实测。

新候选继续在实际研究 world 的创建/加载阶段、ODE 已可读且首物理/传感器执行
之前安装唯一 Ray×Box 回调。安装门须使用该阶段已有定义的运行、加载、传感器
初始化状态与零仿真时钟，并核对尚无研究传感器。`World::Running()` 的实际
布尔值只记录，其 `!stop` 语义不表示此阶段物理线程已运行，不能强制其为 false。
精确字段和固定新 source/ELF 身份必须在新冻结前声明。此时不可读的迭代计数明确记录为 null、availability=false，
不得伪造零或将 null 投影为旧 actual-zero 证据。实际 ODE QuickStep 150 与
max-step .001 的原只读核验仍必要；源级生命周期条件的可用性说明不能代替它们。

这只是错误测量接线与固定执行来源身份的修订，不改变 collider 数学、world/task
几何或六文件投影、actor/SLAM/地图/候选/掩码、原 34 项正式门及原 1ms/20ms、
.30/.01/连续三样本、.78s/.144m、A 或 B 与角向门。完整四阶段仍须在新的干净
推送冻结下重新完成。原 18000 墙秒累计保留：V22 entry .24578428314998746 秒，
V23 实际启动尝试 32.096621671225876 秒，合计 32.34240595437586 秒，
另依事前会计要求累计有限 SDK 生命周期验证的实际编译 37.52403453504667 秒
与单次执行 2.1119531956501305 秒，累计为 71.97839368507266 秒，
新版本开局余额为 17928.021606314927 秒。SDK 只 create/load/init/fini，不 Run/Step
或启动 ROS；它是生命周期可用性证据，不是完整矩阵或新插件安装的原生 PASS。
不重置工程或学习预算。


## P2A.0 V25：Nav2 平滑器使用节点时钟

V24 的真实输入链显示，仿真时间只前进 20ms 时，原 Humble 平滑器可在墙钟上
执行多个回调，OPEN_LOOP 输出因此累计多次名义加速度增量。V25 在 canonical
ROS workspace 覆盖官方 `nav2_velocity_smoother` 1.1.20（上游 commit
`a097086719c88f781aa59788eca29ac6ca5e56db`）。仅在激活和动态修改频率的
两处，以 `rclcpp::create_timer` 和节点 `get_clock()` 替换 wall timer，并增加
对应头文件。其他官方源码、算法、参数、话题、生命周期和依赖保持原字节。
包内 `MR3_PROVENANCE.md` 说明来源，Apache 2.0 许可证随包保留。

`use_sim_time=true` 时，两个 timer 均跟随仿真时钟；仿真暂停期间不得累计平滑
输出。现有 OPEN_LOOP、20Hz、线速度 .20、角速度 .8、线加速度 .5、角加速度
3.2 及其减速度配置保持。每个回调仍按原频率计算增量；此修复不把量化回调
解释为任意短时间间隔内的连续加速度保证。

实际覆盖包核心库 SHA256 为
`ceedf1b35cc501e9caa655c5b0a66f538395893664ec683a6290760f37d60b52`；
实际 standalone executable 为
`0a5bf913f698dc0f43f57bd06a3f87d35a06e1b8366709576084b4afca5d6c5a`。
启动仍通过 package/executable 的正常 ament overlay 解析。源码、官方差异、构建、
压缩库原件及逐 episode 三台实际进程的 executable/core-library 映射须通过固定
独立准入；不能仅凭 install 中有文件或预先添加库路径授予原生信用。

原任务、奖励、候选和掩码不变。95%/300s、三台参与、18 路接触新鲜度、.50m
队友包络、实测完整平面 .30m/s、完整角速 1.2rad/s、采样角加速度 7rad/s²、
.78s/.144m 停车、完整平面静止 .01m/s 与三个唯一新鲜样本等门全部保持。
组件 stock/fixed 对照只验证计时机制；P2A.0 仍须在新冻结完整通过原四阶段和
全部正式独立审计，不拼接历史 PASS，不构成 PPO 或 95% 策略成功证明。


## P2A V9：真实 WORLD odometry 与同源 TF 独立 50Hz

本次修订仅适用于带 MR3 协议标签的 adapter 驱动：`mr3_odometry_period_ns=20000000`
使 WORLD odometry 和同一测量时刻的 odom→base_footprint TF 每 20 个真实 1ms tick 发布。
未设置该字段的 baseline 保持旧耦合发布。轮目标计算、paired joint-feedback helper、
30Hz 更新判据、轮 TF、轮距/轮径/力矩/加速度及真实物理推进保持原实现。
这修复旧 34ms 实际采样下三份最新唯一源在部分 20ms 边界跨度达 101ms 的资格空洞；
100ms 源龄与三样本要求均保持。丢包、滞后、未来源和真实速度越界仍须拒绝，不能重标时间或复用过期授权。

驱动将实际 WORLD 测量和实际 publish/sendTransform 调用另记 `odometry_tbN.jsonl`；
原 `drive_tbN.jsonl` 的行种类、序号及执行器证明不增加合成事件。
独立 C++ `mr3_odometry_recorder` 以 rclcpp MessageInfo 取得实际收到的包 GID，记录完整
Odometry/选中的驱动 TF、真实端点图与接收时钟；同一个 TF topic 上允许其他合法发布者，
但每个所选包必须匹配唯一真实驱动端点。三台 odom/驱动 TF 六流实际到达才发布 recorder ready，
worker 在真实 reset release 前等待该条件。该只读记录器不证明 Nav2 接收，也不参与 actor/奖励。
新 cadence 审计补充原 34 项科学角色，逐个真实发布/收到源、全消息、20ms cadence 和原 34ms
执行器时序核验。新的原生冻结矩阵通过前，不追认旧工程 PASS，不宣称 V7 反例已修复。
