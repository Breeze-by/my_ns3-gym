# MR3 P2A V59：初始编码器保持的生产接入与新完整资格链

当前实际闭合：V59 **FAIL**，执行freeze `783aec55353ecb93385ffe305300ab760f9c24fe`、原tool53492真实reap rc1。1EP原生32/32返回；必要角色6PASS/1FAIL/23SKIP，未启动minimum/pilot/final，P2A未完成。旧准备文字保留为历史快照。下一V60只补两处显式profile审计接线，需人工CPU与新freeze完整12EP30角色重新验证。


当前：生产接入、真实CPU构建、最终fresh v3与编排准入已完成，来源冻结已推送且完整资格计划已生成，正在封存执行冻结，尚未启动V59 World、qualification、minimum、pilot或final。P2A未完成。用户已持续委托自主完成，不再请求常规修改或有界工程资源批准。

## 已有依据

[V58完整单场诊断](20261023_mr3_p2a_v58_encoder_hold.md)完成355模拟秒，三机相对45秒时一次固定机身锚点的最大位移约7.56446微米，低于原R=.0078米；实际非零电机纠偏完整记录。它是quick150、原三机物理模型与单一初始zero候选的有限离散观测，不是连续证明、真实rooms/corridors或训练资格。V57 direct-world候选保持失败并排除，未更换生产求解器。

## 本版执行语义

新freeze的`mr3-reach-v1`自动固定`initial-zero-encoder-hold-v1`，由原safety-contract派生；不新增可自由组合的PPO/benchmark profile CLI。launch只向Reach运行时生成SDF的唯一驱动plugin插入明确profile tag；源模型物理字节保持，legacy渲染保持原分支。Supervisor、worker、benchmark、PPO及PLAN/QUAL/所有阶段必须与三机实际配置同profile。

控制只读本地轮q/qdot。首次有真实已消费tagged zero目标后，连续3个34ms轮rim≤.01的样本才一次捕获q_ref；反馈P=1/s、rim截断±.005m/s，再走原配对slew/accel1/torque20。首次成功接收到任意非零目标（包括纯转、尚未消费即被zero覆盖的消息）立即永久退出，到全进程新epoch对象才重新开始。Reset不重置参考或重新arm。无genuine target时不捕获、不纠偏。

APPLIED-v1和存储ACK形状保持；desired仍表示真实body request，applied/written/readback记录实际电机输出。新raw事件完整记录接收锁存、q/qdot/q_ref、计数、servo desired及genuine target join，不把非零输出写成zero。机身姿态仍只用于独立物理观测，不反馈控制；不刷新安全锚点，不扩到运动后的STOP/再次静止，不改R、任务95%、碰撞、时钟、源龄或既有STOP债务。

## 新构建与独立门

实际新驱动构建rc0/116.13177789墙秒，installed ELF2122904B、SHA`df5d9703f23fd206b967eb9408a4504ed3735b9f71a3c31194b60443464139c7`。4个接收锁存gtest通过；首CTest未source ROS setup的失败保留，修入口后同binary执行通过。原六编译源字段加独立第七helper身份、实际编译flags/命令、ELF gzip和loader已封存，见[build manifest](assets/20261023_mr3_p2a_v59_encoder_profile/checks/native_build_v1/build_manifest_v1.json)。其他九个原native ELF与V19原件相同。

新build bridge必须执行实际new-build/current-Git/精确freeze检查，不借旧V15 no-new-build。CPP/CMake及helper的完整来源恢复证明已注册；source和ELF还须在真实新freeze调用strict verifier，当前CPU/构建完成不冒充冻结资格。

独立motor重放已加入receive→consume→34ms actuation完整链，检查一次参考、P/clamp、原common-alpha和精确加速度预算、实际写入/readback/APPLIED join。原drive-v4代数残差界保留，精确segment/预算门没有新增epsilon。62项针对CPU通过；source/build/profile/cadence针对CPU83项通过，原immutable20/34ms数学保留，旧源拒绝与环境入口失败均存档。

统一fresh CPU按完整filesystem Python union（含未tracked模块/tests）封303源、20项改新增源。ROS12模块实际202项通过，40.854571193墙秒、source stable；ns3gym28模块及最终编排准入尚待真实闭合。旧CPU只在当前源码逐字相同处供软件检查信用，改/新增源必须新实际CPU，不使用旧八文件白名单。各组重叠检查不相加为独立样本数。

## 预算与固定出口

承接[V58规范末账](assets/20261023_mr3_p2a_v58_encoder_hold/closure_ledger_v1.json)：累计92217.1876804376018，原C120000/余27782.8123195623982、实费899.40726088全部保留。代理依据持续委托前瞻选择有限工程C150000，入场余57782.8123195623982；这不是用户逐数值批准，也不重置历史账本。见[resource](assets/20261023_mr3_p2a_v59_encoder_profile/resource_v1.json)、[scope](assets/20261023_mr3_p2a_v59_encoder_profile/scope_v1.json)和[authority](assets/20261023_mr3_p2a_v59_encoder_profile/authorization_v1.json)。

完整工程拟预约47220=matrix45000＋minimum1800＋preflight120＋外尾300。原pilot剩1870决策/2905.9547395464029墙秒，三场final-only open401/402/403共900决策/9000墙秒，均无新消耗。新actuation方程是显式版本；`acceptance_gates_unchanged`仅指原任务/质量/安全阈值、时钟及12EP30角色合取，不声称新内环是旧方程恒等。

最终仍须同一freeze完整12EP/30必要角色→fresh minimum16个eligible决策与真实正优化更新→pilot实际eligible、正更新及固定final.zip/normalization→同checkpoint三场strict95全部通过、validation0更新，以及所有来源/审计/关闭条件。旧FAIL不改判、不拼接旧24/30 PASS，不重开旧活动。任何必要失败保留原件和真实全费并停止后继。

## 下一AI或续接的具体顺序

1. 等所有writer停止后完成两组fresh CPU及最终11项编排准入，逐组核实际wait/JUnit/source/recovery/保存身份关闭。
2. 封新source/build证据，commit/push；以准确新freeze真实调用build bridge、native custody、所有projected loaders/readiness。源码/plan生成阶段若失败，保留CPU原件，修复后新封源；不能给未跑的native信用。
3. 通过`prepare_plan_v1`生成独占V59 binding/plan，复核完整source inventory、三policy profile和47220预约；plan/code再冻结提交推送后才一次执行`execute_chain_v1 --freeze EXACT40`。准确CLI由最终plan与执行声明封存，不在本准备文档填假freeze。
4. 按真实parent区间union入engineering/pilot/final各账，所有writer实际wait后再归档/freshgone；不把CPU或短工程PASS写成P2A完成。

初始zero-only不解决所有运动后长时间静止漂移；本版是否足够完成P2A需实际资格和学习验证。尚无已验证探索策略，也无P2B/gateway工作。

## 统一CPU第二版实际结果

fresh v2两个环境均已实际wait/reap：ROS202项/38.504274032墙秒、ns3gym411项/126.860394636墙秒，0失败/0跳过，303源前后相同。见[ROS回执](assets/20261023_mr3_p2a_v59_encoder_profile/checks/fresh_ros_cpu_v2/actual_wait.json)、[learner回执](assets/20261023_mr3_p2a_v59_encoder_profile/checks/fresh_learner_cpu_v2/actual_wait.json)、[JUnit及保存身份关闭](assets/20261023_mr3_p2a_v59_encoder_profile/checks/fresh_cpu_postreap_v2.json)。当前相对baseline有21个改/新增Python源，只有当前字节的v2供最终准备信用。

初轮ROS202通过、learner409通过/1失败；唯一失败为人工positive计划未注册新profile，生产门正确拒绝。只补全该fixture及副作用前拒错反例，最短模块11项通过，未改生产规则。旧spec、旧源码、失败JUnit/actual wait均保留。第二版首次group入口在seal进程尚未结束时被拒，pytest/World均未启动；实际等seal rc0后再提交新独占group，顺序记录保留，未改门。两版共8份实际保存CPU身份均freshgone。

最终编排11项准入仍待单独真实封存；此前并行写入导致source-drift的两轮开发结果不供最终资格。所有准备结果均没有新World/训练/P2A信用。后续精确sourcefreeze/newbuild实际loader仍须通过。

最终编排准入已实际11项PASS/18.775484301墙秒，295源before/after相同，spec/实际argv/JUnit/wait/recovery已再次严格验证，2保存身份gone。见[最终准入](assets/20261023_mr3_p2a_v59_encoder_profile/checks/admission_verified_v1.json)和[关闭](assets/20261023_mr3_p2a_v59_encoder_profile/checks/admission_postreap_v1.json)。此前两轮开发入口与source-drift拒绝保留。当前全部代码writer已停止；下一步commit/push source/build证据，再用真实精确freeze验证新桥/loader，生成plan后再次封存执行。正式V59 World、资格或学习仍为0。

## EOF清理后的当前来源检查

提交检查发现prepare/preflight两文件各多一个EOF空行，仅去掉这两个LF。它们实际包含在303份封存源码中，因此v2保留原历史PASS，不给新字节信用。旧spec、两旧源码、旧准入证据均无损保存在checks下的独占attempt目录。fresh v3以同一b6af48基线重封：ROS202项/40.593820366墙秒、learner411项/133.691170848墙秒，actual wait均rc0、来源前后相同。编排准入新一轮11项/20.202614774墙秒、295源稳定；该实际源集合不含fresh spec JSON，重封后逐项当前字节仍一致，严格分类验证通过。后续生产源码若变化，仍须更新对应证据；这些结果没有World、资格或学习信用。

## 实际计划准备

源码/真实build证据已提交并推送`ec63e5946b35adce394b7b2b425ebd03169daa96`，真实tool73425回收rc0后才执行依赖步骤。prepare实际tool97772回收rc0，生成[plan](assets/20261023_mr3_p2a_v59_encoder_profile/plan_v1.json)（SHA c69aa1c222cfa8963202468df7bd114e8d23368c85436ad35d0ac83457b9679e）及[binding](assets/20261023_mr3_p2a_v59_encoder_profile/native_custody_binding_v1.json)（SHA 501de8e6caadaa8c362e351149d23e436a1a845a285484041f55d7a2c1ff63d7），1015来源/10ELF。实际plan_check通过12EP/30必要角色、三policy接线和47220预约；ROS/learner CUDA实际就绪检查均通过。见[工具观测](assets/20261023_mr3_p2a_v59_encoder_profile/checks/preparation_tool_observations_v1.json)。

下一步将这些生成物提交推送为最终执行freeze B，要求HEAD=origin/main=B且工作区干净；对B实际调用严格native binding verifier，成功后才一次运行execute_chain_v1 --freeze B。完整链自己的preflight输出尚未占用，World/PPO仍未启动。CLI与root活身份在启动时保存到独占/tmp记录，所有writer结束后再入库，防止运行中污染严格来源工作区。工程、pilot及final实际账均未因准备CPU改变。

## V59实际闭合 FAIL

正式preflight PASS/62.55259715墙秒。interface原生1EP32/32有效返回，native实际wait1160.371180768墙秒/rc0；angular、physics、input、runtime（含三机新compound motor）、information、cadence六必要角色PASS。full role FAIL；fifo_001为required、role=None的子命令rc1，使peer_control/fifo_manifest未派发，closure role亦SKIPPED。完整30必要角色为6PASS/1FAIL/23SKIP；terminal/reset/deadline及minimum/pilot/final均未启动，0优化更新，不拼接旧24/30或给本回合资格信用。

full原始错误为新Reach SDF whole-byte inverse与原5Hz模型不相等，以及controlled inputs缺完整motion replay。静态源码核对定位：真实launch新增的唯一`mr3_actuation_profile`标签未进入sensor逆投影登记；peer reader旧kind白名单缺`initial_encoder_configuration`与`initial_encoder_receive`，其原始错误为native driver complete identity/record prefix。controlled-motion错误依赖peer失败而生；这些来源定位不改判V59，也不宣称未来组合必定通过。准备检查遗漏了公共入口新profile接线，V60将补公共入口正负回归，保留完整原字节及旧分支，不删新事件、不伪装zero、不改控制/物理阈值。

原root tool53492真实reap1之后，67份明确保存运行/root PID+start身份freshgone；两预存Codex transport祖先按启动前声明为nonowned，不纳入gone。PID-only原始未知start状态仍保留，不从另一对象构造原始身份，不声称未记录writer全部不存在。metadata CPU真实4.178548118秒、collector CPU真实131.630549137秒均rc0，各2保存身份另gone；1015源current/Git与10ELF一致。

578 regular原件1111648531B无损封存为97838145B，0链接、无超64MiB原件wrapper、不需分块。见[规范库存](assets/20261023_mr3_p2a_v59_encoder_profile/closed_inventory_v1.json)、[metadata review](assets/20261023_mr3_p2a_v59_encoder_profile/closed_execution/closure_tools/mr3_p2a_v59_closed_metadata_review_v1.json)、[关闭CPU原件库存](assets/20261023_mr3_p2a_v59_encoder_profile/checks/closed_cpu_v1/inventory_v1.json)。全保留partial/失败/实际非零motor输出；未重跑旧科学读者或原活动。

实际工程按四个完整phase-parent区间union收费：preflight62.55259715＋matrix2033.384699001＋matrix_absence1.765363467＋chain_final_absence1.768951836＝2099.471611454秒；nested与整个root wall不重加，记账gaps按预声明不计费。累计94316.6592918916018/150000、余55683.3407081083982；C150000仍为代理依持续委托选定，非用户逐数值批准。pilot1870决策/2905.9547395464029秒、final-only900决策/9000秒和三open401/402/403保持原余额。规范[末账](assets/20261023_mr3_p2a_v59_encoder_profile/closure_ledger_v1.json)。

下一步：保存本轮C提交后，V60安装已在/tmp人工验证的sensor与peer显式profile登记候选，统一公共入口CPU、当前源恢复及新精确freeze，再完整同freeze12EP/30角色→fresh minimum16真实正更新→pilot实际正更新及固定checkpoint→三场strict95/零验证更新；本次缺失资格不由旧数据补做。R=.0078、一次body anchor、实际非零命令披露、原95%/质量/接触/时钟/源龄门保持，P2B/gateway未启动。
