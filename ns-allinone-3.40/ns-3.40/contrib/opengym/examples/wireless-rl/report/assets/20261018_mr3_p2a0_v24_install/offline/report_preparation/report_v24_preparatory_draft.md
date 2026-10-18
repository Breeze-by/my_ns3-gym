# MR3-P2A.0 V24：安装生命周期修正准备记录

**状态：准备阶段；尚无 V24 新原生矩阵、PPO/GPU 调用或任务 API。** 实际 SDK 测量、安装源码修正、canonical 构建及有限 CPU 审计已完成；最终计划/bindings、clean commit/push、source/ELF准入和完整同冻结四阶段仍待完成。本文不授 P2A.0 或策略95%出口信用。

## 原失败与必要修正

V23 源 `9160543e32ca49a56dfd05eaa0df3ccb6d25f89e` 在 reset 返回前失败，gzserver `-6`、真实 forced cleanup、零有效 transitions、后续三阶段 SKIP 全部保留。现场仅记录联合安装 guard 异常，未打印逐条件值；不能把新的 SDK 读数当作旧失败分支或唯一根因。

独立源码检查确认：Gazebo11.10.2 的 `World::Load` 发出同步 `worldCreated` 时，`WorldPrivate::iterations` 尚未初始化；`World::Init` 才赋零。旧 corrector 在该阶段读取 `Iterations()` 的做法无效。撤回此前“created意味着已初始化的iteration0”推断，旧材料保持原字节。[独立源码审查](assets/20261018_mr3_p2a0_v24_install/offline/independent_source_review/review_v1.json)

其他替代解释同样澄清：`create_world` 先登记 world 再调用 Load；“created时world还未注册”的源顺序推断不成立。`SystemPlugin::Init` 又发生在创建 world 前，不能盲挪过去做依赖实际ODE world的安装。`Running()` 返回 `!stop`，构造器设置 `stop=false`，所以 preInit 的实际值 true 合法，不应要求 false。

V24 只替 created 回调块：corrector `f82646c8434b77c42f585ac1828eda84640bac873f70cc7de6848cfbd6493473`（14395B）；块外全字节恢复 b165。slab core `d556dda5…`、header `c619442d…`、hot callback、CAS/dSet/进程生命周期顺序不改。声明的初始单world/no-sensor路径仍在首次物理与sensor更新前安装，不泛化为任意插件/live-reload线程安全保证。

## 实际阶段记录与单次SDK

installed 必须真实绑定 phase `world_created_during_load_before_world_init`；`world_iterations=null`、`world_iterations_available=false`、reason=`counter_initialized_only_in_World_Init`，绝不填0。`world_clock_ns=0`、load_completed=false、sensors_initialized=false、model_sensor_count=0，lookup/physics/nativeODE实际可用、type=ode、failed_preconditions=[]；Running只要求实际typed bool。保留原native quickstep150/step.001读回。失败先记实际定义字段及失败列表，再维持真实失败。

只执行一次授权 SDK create/load/init/fini：compile exit0/37.52403453504667wall；run exit0/2.1119531956501305wall。created实测RunningTrue/loadedFalse/sensorsFalse/150/.001且iteration不可用；仅afterInit读取0。末记录Run/Step/ROS/robotspawn各0。该SDK程序没有加载实际corrector插件，不是V23重执行、物理运动/停车或完整原生任务证明。[SDK handoff](assets/20261018_mr3_p2a0_v24_install/offline/sdk/handoff_v1.json)、[manifest](assets/20261018_mr3_p2a0_v24_install/offline/sdk/manifest_v1.json)、[完整源码/argv/环境/原输出](assets/20261018_mr3_p2a0_v24_install/offline/sdk/originals.tar.gz)

初次syntax01 **FAIL**：exit1/27.221719437278807wall，外部Gazebo/ODE `-I`头的write-strings/deprecated警告被-Werror提升。syntax02只把外部SDK include改成-isystem，同f826源码自身严格选项不变，exit0/27.285107973963022wall。原FAIL/stderr保留，不重标PASS；未产生SO。

## 实际构建与有限审计

canonical构建整体exit0/59.77381576690823wall，含colcon、actual SO factory（不Load）、ldd-r和实际链接的纯CPU几何probe。无world/物理步进/ROS init/DDS/训练。[构建原始命令与回执](assets/20261018_mr3_p2a0_v24_install/binary/canonical_build_receipt_v1.json)

| 原件 | SHA256 / bytes |
| --- | --- |
| actual installed ELF | `782d388fea8df3646524e54f41d71de5f53480b9d04cc0ea1c453c70e2c1f7d8` /398080 |
| lossless gzip | `41c1ae6ad5fd1c80a220ecde90328271e2f4e0668d4d240beb44bc0dce67abed` /129776 |
| binary receipt | `84bbd6bd4b5a8802222dfff9ef8f5a741b89a5d670b71170f46e9a8ae67b4ac8` /7954 |
| canonical build receipt | `6ee8d2739a62d4432122b47aface5abbbc56242737528e2284c03696fd6b7ef6` /17467 |

[actual custody](assets/20261018_mr3_p2a0_v24_install/binary/receipt_v1.json)、[归档库](assets/20261018_mr3_p2a0_v24_install/binary/libmr3_ray_box_corrector.so.gz)。receipt沿用既有schema；actualODE `a94a424d…`和原四库drive `a014f2c6…`/stop observer `9a1d76b0…`/profile `09321ea6…`/ray observer `b7613813…`前后字节不变。

根执行原canonical `test_audit_ppo` 单模块16PASS/.503test/5.608815073035657wall，源before==after；该原回执精确钉auditor `e128e90b…`/ENV `27dfaf84…`/test `43e13e59…`。其后只收窄ENV“因此失败”的过强因果措辞并更新3个常量，函数不变：最终ENV `cc467064ab66e04507ed4d4e805a4e23cdf09b3716fd85517ebb34fe7b2de521`、auditor `f1e0be60d35db3677fb9194341c1ae4133a5c74ed7199056fe18f7e797f40416`。新增2项最终ENV正例/repinned坏prefix拒绝检查PASS/.018284440971910954wall。没有把原16回执改成最终措辞的重跑；新冻结前检仍待实际执行。

## 原门与计费

原34 mandatory、12EP、最多608API/596脚本动作保持：interface1×32；terminal2×最多4；reset2worker×4回合×32；deadline1×300。原wall分配1800/1800/6400/8000，总18000；真实失败保留且后续SKIP，不自动重试。

原任务95%、18路接触/新鲜度、strict close、received-only activity/accept/path、reward真值隔离和actor/候选/mask/SLAM接口保持；命令.20/.8、实测全平面.30/全角速1.2/采样角加速7、原rest .01/3sample/.78/.144及160ms执行门不改。reset停车池仍为每机跨8回合至少一个合格A **或** B；每次实际bound violation/missing-rest不能靠池覆盖抵销，也不新增每EP AAND B。interface角刺激仍每机一sign-span、总体双sign、至少一机双向；reset只要求8回合sampled bounds。

V22+V23原启动32.34240595437586wall，本SDK compile+run保守另计39.6359877306968，根台账累计 **71.97839368507266/18000s**，余 **17928.02160631492734s**。构建/其他CPU时间另列，不伪计为有效reset/API；V24新任务API仍0。失败计费不清零。

## 待完成项

- **PENDING**：CI最终source/admission/ENV/auditor/matrix bindings与精确计划SHA（预计210binding，未在本草稿授已冻结信用）。
- **PENDING**：新clean commit/push、实际782d ELF与Git/worktree宏/归档身份、正确conda learner entry的真实准入。
- **PENDING**：同一新freeze完整interface→terminal→reset→deadline，原mandatory、每EP loaded corrector/ODE maps、installed/callback ledger、真实原生运动/停车与严格退出全部闭合。

未来四阶段即使通过，也仅是P2A后续训练接口准备，不能直接认定策略95%可靠性或授权P2B。
