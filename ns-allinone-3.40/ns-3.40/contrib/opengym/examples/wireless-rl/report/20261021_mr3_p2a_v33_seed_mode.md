# MR3 P2A V33 显式精确起点规则与继续执行

P2A仍未完成。用户要求持续处理直至达到P2A；本轮先将V32人工证书接入显式生产模式，消除V31定位的保守起点假阴性，再检查真实行动入口。最终必须回到原生Gazebo中的联合学习策略及原定final-only三场严格成功；二维短链不提供该资格。

新参数是`seed_rule=exact-point-bridge-v1`，默认`legacy`保留。新规则只替换`seed_pose_body_clearance`分支的保守下界，使用估计位姿及实际交付图，认证点和到同一原seed中心的整段桥。原cell归属、free/graph gate、`.29m`、unknown/outside、状态/map来源、目标到达圆盘等保持；没有找邻居seed、清占据、真值填图或手工探索兜底。具体版本与字段见[环境契约](../MR3_ENV_CONTRACT.md)。

生产CPU首轮113项通过：局部Fraction内核对独立全图分段二次距离oracle、原保守假阴性、桥中段不安全、阈值两侧及上游拒绝门。实际wait/source不变见[首轮CPU回执](assets/20261021_mr3_p2a_v33_seed_mode/checks/seed_observation_cpu_v1/actual_wait.json)。独立符合性11项测试首次1 error：future-map夹具试图编码为合法actor，原encoder正确拒绝未来来源；保留[失败回执](assets/20261021_mr3_p2a_v33_seed_mode/checks/conformity_cpu_v1/actual_wait.json)。修正测试预期后11项通过，见[v2回执](assets/20261021_mr3_p2a_v33_seed_mode/checks/conformity_cpu_v2/actual_wait.json)。均为人工CPU，工程新增0。

新二维v2符合性保持原V21六输入选择及旧v1逐字门：current-legacy必须与旧原件snapshot/张量逐字兼容；exact同六输入另存新输出，并由独立consumer重建。新mask不能称旧native输出或执行信用。每条exact actor仅复算三机seed证书与来源；原有reset/first/last完整候选重建及全部tensor、随机动作、计时和闭合检查保持，避免为900条重复构造完整候选造成无效成本。

本轮[事前scope](assets/20261021_mr3_p2a_v33_seed_mode/scope_acceptance_v1.json)限一个新冻结、一次零更新短验证：open/rooms/corridors各seed101、各64步，总192次尝试、1800工程墙秒含独立审计和外部关闭；采集900秒，符合性/独立review各120秒，原件审计270秒、描述30秒，另120外尾/180清理预约。保留全部错误/中断，无补样或重试。使用V30已构建Karto thin adapter的同一ELF/构建来源，当前Python源码重新绑定；它仍非完整SLAM/原生Nav2或训练资格。

当前工程46691.4127443736018/52000，余5308.5872556263982。已提交[累计75000墙秒的具体提案](20261021_mr3_p2a_v33_budget_proposal.md)供用户决定，**提案尚非批准**。现行完整新冻结资格及minimum仍需20100秒预约，不能用当前余额启动或静默删审计角色；普通实现及余额内短验证继续。pilot余额1870决策/2905.9547395464029墙秒、final-only open401/402/403及原900步/9000秒上限保持。

接下来按当前source freeze执行短probe并保存关闭/费用/结果，再据实际行动入口决定修复。若新冻结原生资格完整通过，才进行minimum→pilot→final；checkpoint保存、单次训练成功或二维95%均不足P2A验收。全部旧FAIL保持，P2B/gateway不启动。

生产接线检查已收口：学习侧139项、原生received-input reader 9项、实际不可变`audit_ppo`/current candidate rule/W7 validator联合4项均通过。ROS全套295项中，首轮5项因本次信息桥`_raster`返回值漏接失败；修正后294项通过，剩余一项新fixture误传空robot列表，被既有三机器人硬门正确拒绝。修正为三个显式无效状态后，信息桥文件12项全部通过。导航旧21项等价检查、新22项桥/直线提议及全部几何观测在该完整套中通过；未改三机门或production物理门。

学习侧首次133项运行中，新native reader人工fixture被错误放进不含SciPy的conda，另有protocol SHA多写前导0；随后9项system重放测试暴露fixture回滚整个`sys.modules`破坏SciPy类缓存。已分别使用原有系统环境、修正64位SHA、将fixture隔离限于项目namespace；没有安装依赖或改变production距离数学。所有原失败console/实际wait及匹配SHA的旧源码快照保留。新审计入口另加4项关闭/来源异常/trace被替换后不得借verified-prefix的检查通过；本轮所有这些CPU均0工程费用。

原生reader的七图是归档原始交付字节；机器人部分从snapshot的normalized充分字段自洽重建，不能称恢复全部原始kwargs，Information/activity/协议门仍独立必要。缺失navigation必须反演为`{}`；每个exact input任务严格绑定自己的episode/output，不得用另一个同冻结回合代替。独立reader自身、archive helper、worker、supervisor和五份纯源共9项冻结绑定均须一致。旧协议审计使用完整原源码私有副本，仅版本化adapter来源pin，原数学保持；新环境文档两块插入逆投影须恢复整份旧文档，随后继续旧规范门。

二维执行仅在回退期间朝同一seed中心转向或直行；每个20ms平移提议还须通过同一`.29m` closed-cell整段几何。原scalar bound恢复后回旧lookahead，激光`.40m`、同伴及源龄否决保持。它是估计几何下的proxy局部执行，不是原生Nav2跟踪或物理安全证明。[唯一短probe计划](assets/20261021_mr3_p2a_v33_seed_mode/seed_probe_plan_v1.json)已按当前完整源码、scope和原ELF构建来源绑定；执行须使用干净且已推送的完整40位freeze。
