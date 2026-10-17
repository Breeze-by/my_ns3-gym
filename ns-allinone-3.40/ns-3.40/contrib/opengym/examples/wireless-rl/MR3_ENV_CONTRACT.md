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

## 本机SDK状态响应等待（W7已验证配置）

同机FastDDS loopback profile只对三台各六个Nav2节点的精确`get_stateReply` writer
增加1墙秒的response-reader匹配/写入有界等待，保留原18个`change_stateReply`的5秒窗口。
Nav2 `get_state`客户端原2秒future超时不变；其预算还包含请求传输和调度，不能推断必有
完整1秒回传余量或保证发现成功。其余默认、request/data/contact端点、DDS transport buffer、
发布频率、SDK版本与任务时钟不变。无自动重试，实际超时仍是infra，旧profile证据不赋予新冻结信用。
这是应用配置的有界等待，不是DDS发现竞态修复声明；W7完整矩阵仅提供其实际工程范围。

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


## P2A.0 v10 显式受控执行阶段（待同冻结原生验证）

在`mr3_stepped=true`时，启动实际旧零输出/三存储ACK后接管timer，再真实推进20ticks到新clock；每一物理边界暂停，完成state_phase→peer_phase→motion control→三台driver存储→evaluator相位后再推进。三阶段共用epoch/request_id/target_time_ns且成功normal必须clock完全相等。状态节点取消周期state发布，选择自身实际causal入站、真实发布bundle及side消息；受控有效状态节拍改为50Hz，warmup/非stepped原10Hz保持。peer必须实际收到匹配SHA、sequence和publication开始后callback的六side及main bundle，才能真实发布障碍并ACK；guard必须实际收到两份ACK及main bundle、own causal输入，唯一正常输出并回收后ACK。墙超时10秒使本轮invalid，不推进仿真/修改源时间。诊断引用、raw ingress与协议ACK不进入actor/奖励。

normal回执同clock不可覆；独立`phase_kind=stop`只能永久三零、ready=false，可在相同clock用更高seq，单独`/motion_safety/stop_status`及控制ACK，不授几何/缺输入安全信用。终止或取消需真实通知，随后每次20ticks关闭推进仍等真实零存储。真实terminal可取消pending state commit；仅排空可复用最后真实水位原引用且保留源时间，不能再发布新state或LIVE推进。未返回reset的基础设施失败以隔离abort begin→真实cancel/zero/Nav2/helper/navigation_closed→finalize→原有序native关闭，不产生reward/伪造transition；正常sealed评价器规则不变。新的peer/control/information独立原件审计与所有旧任务/物理门均必需，详见[本版报告](report/20261017_mr3_p2a0_v10.md)。

阶段ACK绑定各节点实际callback前缀，不构成跨进程原子事务。worker已实际处理stop或主动发stop请求后不得再用normal推进或恢复；guard一旦stop，新输出只能为零。guard发出但DDS尚在途的窗口保留原最多20ms终态排空和完整160ms驱动/机体反应门；源stop与旧normal permit的窗口另作诊断，不声称零延迟跨进程封闭。

工程与策略结果审计共用受限bootstrap审计入口：仅精确v1元数据、唯一实际三零交接、三takeover、实际回收/原生存储以及完整控制账本均成立时，原W7物理审计的setup→受控量子切换参数取bootstrap起点T0；输入仍为全部原始receipts，原整数/连续/量子数学不改。真实任务release仍为交接终点T1，奖励/接触/终态等继续使用T1。legacy保留原release调用，未知协议拒绝，每次调用后还原原审计函数；工程fixture的capacity排除不进入策略审计。本轮只验证接线，无新采样/优化或策略效果信用。
