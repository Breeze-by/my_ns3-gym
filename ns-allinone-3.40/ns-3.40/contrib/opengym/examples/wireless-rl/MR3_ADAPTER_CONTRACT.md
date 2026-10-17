# MR3 理想策略适配契约 v5（P2A.0执行准备）

2026-10-17用户要求继续完成P2A.0。P1A/P1B/P1C已由用户验收，P2A未完成；旧v6停止及全部失败保持，
本次修复以新冻结验证，不启动新pilot，P2B及gateway未开始。
本文记录当前接口；P1B原生矩阵只证明其旧冻结v2，P1C只提供W7环境工程信用。
P2A v3最小链原scalar六项同边界switch归因FAIL保留；v4最小链已完整审计PASS，
pilot在0更新时因源级折扣目标缺陷诊断停止，保留一项peer安全失败及三条前缀。
v5原生已有3次任务成功记录及48次pilot更新，后因20ms终态相位门禁失败自动停止，原完整审计FAIL保留。
v6在af37冻结增加每20tick评价器phase ACK，工程terminal-probe和16决策/4更新最小链已完整审计PASS；
pilot718原生/717返回、0更新，因w0 tb1 SLAM有序SIGINT后karto::Exception/exit -6自动infra停止，
原完整审计八项FAIL保持，无final，三场final-only验证SKIPPED。本次候选/导航接口更新为v5，
不改任务地图评价或机体安全门禁。协议v2只对已严格证明未实际发送的peer停止目标
做detached原W7重放，实际freeze的adapter/protocol/transport/env-auditor四份精确SHA须匹配；
原FAIL和native原件保持，不能将旧v5完整审计改PASS。少量开发成功不证明学习收益、可靠性或网络性能。
任务指标仍由[任务契约](MR3_TASK_CONTRACT.md)约束，学习闭环见[PPO契约](MR3_PPO_CONTRACT.md)。

## 模式与所有权

`execution_mode:=baseline`保留传统控制器；`adapter`由`mr3_adapter`独占全局目标，固定三台，
禁止传统`drive`目标节点。两者共享按用户/ROS域划分的本机文件锁，第二个目标所有者启动即失败。
adapter不导入探索效用、坏点重派或旧目标分配函数；没有策略输入就保持空闲。
它只拥有`NavigateToPose`，不写底盘速度。安全停止与Nav2本地恢复不选择新探索目标。

## 观测与动作

`/mr3/observation`为JSON快照，`epoch/sequence/map_version/candidate_version/digest`
固定该步含义。只使用已交付SLAM地图、估计位姿和实测twist；无Gazebo真值或评价输入。
地图内容摘要与元数据必须配对后才构造观测。状态/地图/回执保留源时间与接收时间、
序号、版本及缺失/年龄字段。SLAM的TF header是scan时间加`.2s`的有效时刻；
额外保存有效时间与扣除声明lead后的测量源时间，不改原TF头；只缓存真正未来的测量源，
不能再次等待前移后的有效时间而人为增加`.2s`滞留。
历史为最多16条已交付位姿；任务剩余时间按300秒上限编码。v3快照另含放行后received local-odom
累计弦长和本epoch唯一accepted-goal计数，分别编码有效/完整性；不把TF回环校正或预热移动累计为参与。
它们是策略可见的估计活动，不替代评价器真值门禁、不新增移动奖励；学习张量schema为v2、robots为71列。

全局图为固定`[-16,16]m`、128×128；三份局部图为各自中心12.8m、64×64。
三个通道表示与原始格正面积相交的占据/自由/未知证据，混合像素可以多通道同时为1，
不冒充可通行概率；范围外填未知。CNN图使用zlib/base64压缩，仅为JSON表示。
原分辨率地图独立决定候选和安全路径，细墙/未知区域不能被降采样抹去。

共享候选K=8；v5从每台实际已交付导航图可达的安全目标池分别投影前沿，优先为尚未被代表的机器人
保留一个确定性几何候选，再对剩余项做最远点采样，没有信息增益、奖励或路径效用排名。
被最近安全点遮挡的前沿只在原1m半径内搜索几何可见替代项；不改变地图，不自动派目标。
各台路径和目标使用该台实际导航图，不再要求与全局hub自由格取交集。导航合成按明确来源优先级保留
本机已知格，只从已交付共享图补本机未知；不会按seed/当前位置清点、删本机障碍或吸附起点。
这是对已证own自由/hub占据冲突的版本化信息来源修订，不声称冲突对象身份已证或所有目标都可达。
路径不穿未知、障碍或对角夹缝；路径/实际起点净空仍为`.25+.04=.29m`，原点/分辨率独立换算，
扣除实际起点和目标的格中心偏移。目标还需在对应导航图中容纳`.29+.10=.39m`
完整到达圆盘；已在`.10m`到达容差内的目标不作为该台新探索动作。未知或净空不足的
实际起点明确拒绝并记录，不吸附邻近自由格。缺导航图只KEEP，不回退到其他来源。导航own输入是1Hz任务
采样时本机最新图；actor的own角色是显式上行交付副本。实际`/tbN/navigation_map`与metadata中的
输入/输出SHA配对，不增加地图发送频率。本次理想矩阵必须实证两个own SHA相同，七图归档才能完整重建；
若未来阻断交付导致两者不同，必须另存实际输入，不能外推当前证据。
观测schema为`mr3-observation-v3`，保存路径图来源与源龄。候选截断、各台路径/可达性、
起点安全性和掩码原因均保留。规则版本`mr3-navigation-geometric-staging-v5`及目标/路径半径
写入`candidate_rule`并加入候选哈希；旧审计保留旧schema/哈希口径，旧模型不能直接加载当前接口。
不足8个补无效项，无候选不触发手工规划。

每台动作0–7选候选、8为KEEP、9为WAIT；联合类别为`100*a_tb1+10*a_tb2+a_tb3`，
共1000类。策略观测timer名义周期为1仿真秒；地图内容/元数据未配对或编码仍忙时跳过该次快照，
不使用旧版本伪造新步。P1B v4矩阵的rooms异步观测间隔含2秒和3秒，保留原历史范围。
P1C另在W7 `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`验证显式stepped 1秒训练环境，非stepped timer名义频率与跳帧规则不变；
真实短步/零时长终态按环境契约处理。P1C已于2026-10-16验收并授权P2A。接受后5仿真秒承诺期仅KEEP；终态或安全停止例外。
接受/取消未完成、所有权未知、失效状态只允许KEEP。新目标不得与其他新目标、保留目标
及等待机器人的位置冲突：两个新/保留目标到达圆盘要求`.39+.39=.78m`；
新目标与空闲机器人的实际机体要求`.39+.29=.68m`。继承的KEEP/WAIT所有权不改写；全KEEP始终合法。
KEEP不重发、不续期。WAIT通过取消/终态确认形成停止，adapter不写`cmd_vel`；
底盘最终速度仍由独立安全门检查，取消不被当作即时静止。
快照、候选和掩码必须与动作一起存储；不能用后续地图重解释旧动作。

策略往`/mr3/action`发送JSON，字段为`epoch, observation_sequence,
observation_digest, command_id, created_at, expires_at, action`。
只接受最新快照及未改变的目标所有权；迟到、掩码非法、过期和跨episode命令记录拒绝。
命令id单调，完全重复幂等；复用同id不同内容不能取得新的执行。

## 导航协议

目标id为`epoch:robot:command_id`，保存源观测版本、生成时刻和有效期。
换目标必须先取消旧目标并收到其终态；排队替代目标保留原始TTL，过期后不自动续命。
接受/取消本地RPC期限各10仿真秒，执行期限60仿真秒；超时仍保留未知所有权。
拒绝、abort、非预期取消、租约/RPC超时锁存失败并全队停止，迟到接受仍必须取消。
目标命令TTL为2仿真秒；独立执行租约为2秒，由后端5Hz显式heartbeat续期，
不由KEEP或重复命令隐式续期。协议终态闭合后才发布`/exploration_stopped`。
初始放行与P1A监测就绪握手相同；收到任务停止或安全失败后不再派发。

## 理想交付与后续网络边界

消息信封含epoch、stream、source、source/generated/received stamp、sequence、version、
完整不可变JSON payload。`ReceivedStore`只能由显式delivery更新，拒绝旧版/跨epoch。
地图为完整快照（含header、几何、每个occupancy值），无增量、无地图传输压缩；
地图重发不刷新传感源龄。非受控状态10Hz、地图/共享图1Hz、回执和租约5Hz；目标/取消即时。
P2A.0 v10的受控stepped状态改为20ms显式提交（有效50Hz），经实际peer接收/障碍发布、guard回收及三台原生storage后才推进；唯一三零启动交接、独立永久zero-stop和callback前缀边界见[环境契约](MR3_ENV_CONTRACT.md)。非受控10Hz及原源龄门保持，无新策略输入。
状态/地图发送队列每源只留最新一项；目标/回执为有界64项可靠顺序队列，溢出报错。
按ROS timer采样的流不再被二次限频；原生action回执最多等待下一5Hz交付槽，
交付等待计入协议期限，不能按原始回调时间回填已超时的回执。

理想信息桥原始订阅只在逻辑edge端读取`tbN/map,odom,tf`。后端图仅融合已交付本地图，
发布`/mr3/received/map`，其融合仍为occupied-wins；每台`/tbN/navigation_map`使用
`mr3-own-known-shared-unknown-v1`。本机已知格是自身导航权威，共享图仅补unknown；本机occupied
不会被其他free覆盖，unknown不会凭空改free，分数格偏移仍保守重采样。地图源时间不因组合刷新。
P2A v3在三台实际`params/nav2_params_tbN_0.yaml`中共同将GoalChecker和DWB的
`xy_goal_tolerance`由`.25m`收紧为`.10m`，yaw仍为3.14；不能将此新参数配置归入历史P1B成绩。
活动`mapper_params_online_multi_async.yaml`的运动阈值改为`.10m/.20rad`，使短子目标能积分扫描；
ROS最短时间节流`.5s`、5s地图更新及Karto/C++实现不改，二者时间参数语义不混用。
peer组件在adapter模式消费交付状态副本，按任务放行启动监测，不读raw action状态；
保留完整机体包络、`.5s`源龄门限及失效停止。未来网络陈旧超过此界会安全停止并报告，
不使用实时远端位姿补洞，也不宣称已经实现自适应失联恢复。

adapter新增最终速度门：controller与behavior均发往`cmd_vel_nav`，smoother输出
`cmd_vel_unguarded`，唯一`motion_safety`发布`cmd_vel`和实际驱动入口`/tbN/mr3_drive/target`。
`cmd_vel`保留本地Twist/FIFO观测，adapter的tagged驱动只订阅target。节点只用own本机odom/TF和已交付peer
state，50Hz检查命令超时、状态源龄、任务放行/停止及共同制动区域；近区只允许完整角速度/制动
时域中不接近队友的请求。接近方向拒绝后，只有`(0,原角速度)`通过同一完整几何/源龄/残余移动核验
才刹停线速度并保留原转向；状态无效、包络不足、超界不能旁路，过滤及重验均写trace；否则全零。
三份实际`params/nav2_params_tbN_0.yaml`和通用配置中的controller、实际`behavior_server`、
smoother共同收紧命令角速度为`.8rad/s`，线速度上限仍为`.26m/s`；smoother保留显式
`20Hz/OPEN_LOOP`，不据其墙钟插值宣称仿真时钟下的物理加速度。恰好比`.26m/s`或`.8rad/s`上限高一个binary64相邻值
的Nav2插值规范到原上限，保留原值/规范元数据；第二个相邻值及更大超界拒绝，最终输出严格有界。
它不替策略选目标/方向，既有peer costmap仍供Nav2避让。
v8对已持续零线速度且三条完整fresh本机odom静止的原转向请求，另允许严格`mr3-settled-turn-v1`总漂移预算检查；每个原body margin须≥`.1518m`，包括自身整段`.0078m`与队友`.144m`。实际存储零线速度历史、原160ms时延及activation至真实下一非零存入的速度/chord/累计漂移须独立硬核验，重复授权不刷新预算；该持续漂移界是明确条件物理模型，过去三样本和有限弦长不是连续未来保证。详细规范在[环境契约](MR3_ENV_CONTRACT.md)，原请求方向、actor/候选/掩码/奖励与任务门保持。

角速度原测量来自own odom，其pending-turn预测使用`odom_source_stamp`对应源龄及`7rad/s²`界；
几何位置/yaw仍使用较旧的`min(odom,TF)`源时间，两项source stamp/age分别留证。
实测平面速度`.30m/s`、角速度`1.2rad/s`界保持；`.8rad/s`命令上限不能证明身体实测满足此界，
仍须以完整原始twist向量、响应及停止路程核验。`.02s`轮耦合余量继续同时计入`.78s`时域和
共同停止reserve；`.5m/s²`描述全局停止包络，不是每瞬时中心速度的物理最低减速度。
输入/输出、使用的源时间和几何判据写入独立trace，worker核对图上唯一发布者、本地actual值FIFO
及同clock三台输出消费后ACK；`graph_at_callback`不是逐包MessageInfo或Gazebo执行器消费确认。
保护依赖有限速度/源龄/反应/制动界，不对任意定位跳变作绝对安全承诺；`.50m`任务失败门槛保持。

执行算法为`mr3-paired-joint-feedback-drive-v1`：最终门同值的有界tagged目标交给局部
`libmr3_gazebo_diff_drive.so`，从本机实测左右轮关节轮缘速度共同插值到命令目标；
每轮步长受`max_wheel_acceleration * sim_dt`约束，两轮共享同一比例，不累加隐藏指令。
插件来自Gazebo ROS 3.9.0，保留BSD许可、独立namespace/class及
[来源说明](../../../../../../ros2_ws/ros2-multi-robot-automap/src/multi_robot/vendor/gazebo_ros_diff_drive.PROVENANCE.md)，
系统插件保持原件。轮速反馈是本机传感；继承的WORLD里程计仍只用于输出计算，不进入轮执行决策。
30Hz、`.287m`轮距、`.066m`轮径、`1.0m/s²`轮缘加速度、`20Nm`力矩、WORLD里程计及
1ms物理tick/20ms量子保持。施加参考的共同插值性质不等于机体响应证明；
`.30m/s`、`1.2rad/s`、`7rad/s²`、每机`.78s/.144m`停止响应及原任务/接触/关闭门禁仍须同冻结原生核验。

实际目标为String JSON `mr3-drive-target-v1`，字段为
`schema,epoch,robot,clock_ns,decision_sequence,linear_x,angular_z`；绑定原guard源时刻/序号与同值输出。
驱动mutex内拒绝错误epoch/robot、非有限/超界值、未来/回退clock及旧决策序号，成功存储后在
`/tbN/mr3_drive/status`发布`mr3-drive-target-consumed-v1`，字段为
`schema,epoch,robot,clock_ns,decision_sequence,source_clock_ns,cmd_seq,linear_x,angular_z`。
actual clock为Gazebo实际回调时刻，source clock保留tag原时刻。target/status均为
reliable/transient-local/depth1，预热保留最新目标语义；tagged模式不创建cmd_vel订阅。

worker在初次放行前及任务/关闭的每次20ms推进前，必须真实收到三台与同暂停physical/ROS clock、
guard序号及两个速度值完全匹配的最新目标存储状态，并在10墙秒保护内consume后才发送物理请求。
订阅topic绑定robot，旧/未来/错target或不完整三台状态不能借用；callback错误和边界改变阻止推进。
同暂停边界可复用已消费cache，跨边界须新回执。初始未放行时query/1ms clock对齐仍按原路线进行，
完成后放行也须经过三台状态门。该ACK确认真实目标存储，30Hz施加、物理响应及停车仍独立验证。

正式保存实际spawn的`drive_model_tbN.sdf`与`drive_tbN.jsonl`，后者schema为
`mr3-drive-actuation-v2`，保存实际库/四份编译来源SHA、`command_received/status_publish/target_rejected`
及真实30Hz `actuation`；绑定cmd_seq、target决策序号/源clock、两轮实测/目标/施加值、alpha及dt。
另存保护层`drive_targets.jsonl`原tag JSON、worker的`drive_phase_worker.jsonl`
（ack_received/ack_consumed/advance_permitted/physics_completed）及实际target/status图端点。
独立核对tag、真实回执、物理推进顺序、整段源延迟和库SHA，原160ms、物理及任务门不变。
旧trace v1和headerless Twist只按原冻结的历史/非tagged兼容范围解释。
原motion同clock ACK仍只证明发布与本地topic接收，不能升级成轮施加或机体停车证明。
驱动原件只供独立工程核验，不进入actor或产生目标/探索兜底。

这些edge/backend对象目前同进程/同DDS域，action endpoint仍在适配器内部。
逻辑交付夹具不等于P3A的进程/订阅隔离、完整线协议或黑断测试；这些仍按计划留待P3A。
P1C已测量本接口采样工程成本，P2A按已声明1秒决策/20tick相位契约执行；完整策略出口未达，不能在模型冻结后为接网改执行架构。

## P1B历史预声明与证据范围

离线测试覆盖几何/掩码/确定性回放、无真值、所有权/拒绝/迟到/过期/租约与取消终态、
交付缓存和地图副本、启动模式互斥。原生矩阵为open/rooms/corridors各seed101，
每次独立重启三台，按同一推送冻结串行执行。v3预声明脚本先最大化合法候选动作数，
再选择较长的已观测路径以施加取消压力；随后KEEP，7秒后WAIT，15秒后再次选候选，
25秒后主动请求停止并检查终态闭合。观测编码和信息桥地图处理各用一个CPU worker；
地图最多保留一个运行任务和一个最新待处理任务，1Hz采样不变，源时间不因处理/重发刷新。
导航副本组合使用该次采样的最新本机图与最后交付共享图；完成后按真实交付时刻发布。ROS回调持续处理
交付、心跳和终态。显式`adapter_probe:=true`提供评价器诊断结束服务，写入
`adapter_probe_shutdown`未完成记录，再由launch执行原生关闭；正常任务不启用该服务。
此脚本是适配测试输入，不作为RL或用于性能比较的算法。
注入同命令重复、跨epoch、过期及承诺期内非法WAIT，并审计执行次数。

原生门禁为三台各至少一次接受，KEEP不重发，承诺期无自主换目标，真实取消/终态闭合，
无重复目标，已保存快照摘要/动作可回放，持续监测与原生进程退出可解释。
既有95%评价器保留原指标；短探针主动停止产生的未完成评价不能标为任务成功。
所有失败/基础设施异常保留；修代码后使用新冻结重跑整套矩阵，不跨冻结拼接。
最终运行冻结为`f9928fe97f4081c3f331ba1407aa18a9fc14a602`，三单元严格审计通过；
完整结果、三次保留失败及边界见[P1B报告](report/20261015_mr3_p1b.md)。
K8/名义1秒/5秒承诺是本次已测试接口版本；候选在保守本地图条件下仍可能大量不可用，
P1B矩阵不证明候选足以完成95%任务，也不提供训练吞吐与固定dt信用。P1B已由用户验收；
完整reset、stepped固定步长及1/2/4 worker采样由P1C的W7独立证据提供。
P1C已于2026-10-16由用户验收；短工程矩阵不证明多日训练稳定。
P2A v2 pilot的tb3候选饥饿与两次peer安全失败保留在[P2A报告](report/20261016_mr3_p2a.md)，
是本次v3执行修订的诊断依据。v3的16秒最小链三台均实际到达目标并更新地图几何，
但不证明300秒候选充分性或95%任务；原scalar审计失败保留。
v4候选/SLAM/Nav2及安全门禁不改，日志隔离/离线switch归因已在v4最小链验证；v6只补评价器消费相位，
不复用P1B/P1C或旧pilot成绩，详见[PPO契约](MR3_PPO_CONTRACT.md)。

V6闭合及预算见[记账](report/assets/20261016_mr3_p2a/v6_closure_accounting.json)。
有限前缀CPU复核发现部分机器人零合法GOAL或合法但未选，不能将所有静止归为actor拒选。
P2A.0首冻结已合入v4前沿union，但新原图证明其仍不能修复导航起点占据冲突，且reset捕获真实peer失败；
旧完整FAIL与跳过deadline保持。本次v5须在新冻结完整准备矩阵验证，原.29路径/.39到达圆盘、
未知拒绝和所有权门禁不变，不提供导航起点清障或吸附兜底。
