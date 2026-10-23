# MR3 P2A V55：零轮目标的被动物理配对诊断

> 当前：**CLOSED — 实际FAIL，无有效物理结果**。freeze63f5cc107、tool23231真实reap rc1；两CPP均rc-11、wrapper1，缺CPP summary，早期身份已保存。连续parent12.924178319墙秒已收，累计90370.2852481186018/120000、余29629.7147518813982；6主身份与metadata CPU自身2身份分别freshgone，关闭CPU真实wall9.076326329秒/工程0。实际生产`p1c_*.world`为quick150，A55 quick50是诊断设置，不能称生产原配置；下方原准备段和假设均保留为当时快照，实际结果见末尾闭合节。[V56](20261023_mr3_p2a_v56_startup_gdb.md)只对同未改ELF/原quick50 World做一次新范围启动栈诊断，不重跑V55或改判，HOME/ALSA/OpenAL不归因，P2A未完成。

2026-10-23准备快照：尚未执行本活动的World。用户持续委托自主完成P2A；本次只定位真实零目标执行下的机体微漂，不提供完整原生资格、训练或95%任务信用。P2A未完成。

## 已知故障与下一项判别

[V54完整描述](20261023_mr3_p2a_v54_firstfault.md)记录V52 deadline首fault为`tb1 / fixed disk radius exceeded`，commit clock为244.58秒，motion原行1084442。该负载固定发送`888`三机KEEP，不读取策略或候选排名；派生窗口的实际模式是初始HOLD资格后的D，固定anchor在约42.28秒，轮目标为零。窗口最后raw晚于fault commit，不能拿该行冒充精确触发源。既有FAIL、原锚点和R=.0078m保持。

零轮目标与固定机体位置是不同的物理事实。本活动仅比较两个预先固定的求解器：ODE `quick`的50次迭代与ODE `world`直接求解。Gazebo说明两者分别使用迭代法和直接法；这支持一次隔离比较，不能预先证明本次漂移由求解器导致或直接法必定消除漂移。[Gazebo物理参数说明](https://classic.gazebosim.org/tutorials?tut=physics_params)、[SDFormat 1.7参数定义](https://sdformat.org/spec/1.7/physics/)。

## 有限范围与账

承接[V54规范末账](assets/20261023_mr3_p2a_v54_firstfault/closure_ledger_v1.json)：工程累计90357.3610697996018/120000，余29642.6389302003982墙秒。本活动完整两case parent预约1800墙秒，预约后余27842.6389302003982。120000为代理依持续委托选择的有限工程块，不声称用户数值批准。pilot/final新增均为0，原余额保持。

两个case各一次、顺序执行，不重试；每个case原生工作合作式上限600墙秒。完整parent费用包含实际提交、两case等待、间隙、排空与收尾；超限、错误或partial保留全费及原件。1800为完整费用门，不声称操作系统硬实时保证。

每个case只放置三台canonical TurtleBot3 waffle机体，初姿分别为tb1(0,-.45,.01)、tb2(0,.45,.01)、tb3(.45,0,.01)，rpy均零、同seed101。保留机体质量、惯量、碰撞、关节、重力、摩擦及1ms物理步；复用现双轮限速helper，以34ms执行周期、20Nm最大扭矩和1m/s²轮沿加速度，真实写入零轮目标。不设置机体pose/velocity、不焊接关节、不增加纠偏控制。

先settle45模拟秒，再固定各机锚点并观察310模拟秒，逐物理步统计最大位移、首R越界源时刻及实际运动指标，另存有限间隔样本。两arm除求解器及标识外保持物理输入相同。将实时更新率设为0只改变墙时节流，物理步仍为1ms。

诊断明确使用固定的已安装ground_plane源字节，并记录来源；不冒称V52历史URI解析路径已被封存。移除非物理plugin/sensor/visual并保留剩余物理树的证明须在入场前完成。该无ROS、无SLAM/Nav2/策略、无任务障碍的隔离World不等于旧episode重放，不证明三场建图、安全资格或任何actor性能。

## 入场与结果解释

实际运行前须完成最短相关准备检查和真实编译，封存C++、生成器、driver、模型/helper/ground源、生成World、编译命令及ELF身份；提交推送后以新的exact40执行freeze绑定。当前尚未声明这些准备已通过。

程序完整执行、来源/参数/时钟/收尾合格与机体是否留在R内分别记录。baseline越界是应当如实保留的测量结果，不能靠将它标为消费者失败掩盖；完整描述PASS也不等于物理条件PASS。若候选改善，先以显式新plant版本接入，再完成同freeze完整12EP/30必要角色、minimum真实更新、原额pilot及三场冻结策略strict95验证。若未改善，依据具体记录继续定位，不移动锚点、放宽R、替换KEEP负载或改旧结果。


## 准备实际结果（正式World前）

[规范scope](assets/20261023_mr3_p2a_v55_passive_plant/scope_v1.json)已在实际编译/人工检查后准入；[最终生成spec](assets/20261023_mr3_p2a_v55_passive_plant/prepared_worlds_v3/spec_v1.json)和[真实构建manifest](assets/20261023_mr3_p2a_v55_passive_plant/checks/build_manifest_v2.json)绑定最终源与ELF。19份执行/解释/机体源码、其中10份原Git1fa源将逐新exact40/current/old核对；342份动态链接依赖按解析后的实际对象绑定，不把系统库或/tmp ELF冒充Git文件。

前三版准备各有真实CPU编译PASS：51.086935907、50.734880339、47.164755331墙秒；仅末轮CPP/ELF用于正式活动。前两轮源码、构建回执及字节原件保留。第二版补首末UpdateEnd时钟与每机310001个保护观测；第三版显式调用PhysicsEngine::SetSeed(101)，与Ignition随机源回读分开，不声称已有ODE内部种子回读。最终ELF471256B、SHA `b2e154c4b08105c7d37193c8e18df19bb9275542da41924ca06f066b361e7a63`，原始压缩字节可复原。

两轮同6项纯人工driver fixture均真实PASS，完整wait .32403286/.292878378墙秒；[后轮actualwait](assets/20261023_mr3_p2a_v55_passive_plant/checks/driver_cpu_v2/actual_wait.json)与[清洁环境动态加载器--list](assets/20261023_mr3_p2a_v55_passive_plant/checks/loader_cpu_v1/actual_wait.json)（.068962845墙秒）保留真实argv/source before-after/rc。加载器不进入应用main，不运行World。后轮只加强Popen后立即记录owned身份、规范系统Python/cwd入口及学习模型字段命名。对应已保存身份分别在真实reap后freshgone；生成器spec仅有PID的字段不补造start。

第一次构建manifest元数据helper的whole-stat比较断言失败、实际rc1原样记录于[失败说明](assets/20261023_mr3_p2a_v55_passive_plant/checks/build_manifest_metadata_attempt_v1.json)；未保存具体差字段，不能事后宣称已证实是某一stat字段导致。后续按dev/ino/size/mode/mtime/ctime及真实源码/ELF SHA核对完成，没有把该失败改判，也没有额外World。

半径指标是每1ms Gazebo binary64位置经std::hypot计算的描述量；不是原runtime精确Q门重放或连续界证明。接触表是逐步接触对象计数，不是18路unsafe事件率。程序还要求首UpdateEnd为1ms、末为355秒、累计355000物理步及310001个锚后观测，避免漏最后物理步仍声称完成。

正式唯一命令仍须提交推送后将下列新exact40替换为该冻结；输出prefix独占，两个case各一次：

```bash
# cwd: wireless-rl；NEW_EXACT40是尚待提交推送的执行版本。
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261023_mr3_p2a_v55_passive_plant/run_passive_pair_v1.py --freeze NEW_EXACT40
```

每case超过720墙秒或收到中断时只对已绑定的自身CPP请求INT，10秒后TERM、再10秒后KILL，并等待原wrapper真实返回；不信号端口上的其他进程、不杜撰退出码。连续两case的费用区间包括中间检查，不将两个nested wait相加。实际root工具退出及保存身份freshgone须另行封存。当前仍无本活动World结果，也无新学习或P2A完成信用。


最终运行环境补充：最初loader虽rc0，但清洁环境选中了两份system urdfdom库，和构建时实际解析的两份ROS同SONAME库不同；[对象比对失败](assets/20261023_mr3_p2a_v55_passive_plant/checks/loader_binding_attempt_v1.json)原样保留。driver现明确指定现有ROS native库目录LD_LIBRARY_PATH，未设置PYTHONPATH或启动ROS节点。[最终loader](assets/20261023_mr3_p2a_v55_passive_plant/checks/loader_cpu_v2/actual_wait.json)真实PASS/.061848255墙秒，[342个对象与SHA完全相等](assets/20261023_mr3_p2a_v55_passive_plant/checks/loader_object_binding_v2.json)。仅环境一行变更后的同6项driver CPU再次真实PASS/.293310886墙秒，最新两组保存身份均实际freshgone；此前准入scope草稿移入准备原件，最终规范scope重建绑定当前driver，末轮构建manifest与ELF保持。正式ELF gzip为`native/passive_plant_v3.elf.gz`，另一个v1 gzip仅为第二轮构建的保留原件。

## 实际闭合：两臂CPP均rc-11，物理诊断FAIL

**本节为最新状态；上方准备/尚未World文字保留为执行前快照。** 执行freeze `63f5cc107161202a6d610f5fe39f3434b0d7eed9`、原生产证据freeze `1fa55bc56d5bb9e230d4b397f962d83b1604b278`。root tool23231已真实reap、rc1；[实际root wait](assets/20261023_mr3_p2a_v55_passive_plant/closed_execution/closure_tools/mr3_p2a_v55_actual_tool_wait_v1.json)与[driver原summary](assets/20261023_mr3_p2a_v55_passive_plant/closed_execution/tmp/mr3_p2a_v55_driver_v1/summary.json)保持FAIL。

| 实际arm | CPP真实rc | wrapper真实rc | 原CPP summary | 有效物理结果 |
|---|---:|---:|---|---|
| quick50 |-11|1|缺失，早期identity已保存|无|
| direct-world |-11|1|缺失，早期identity已保存|无|

两臂均已实际提交和真实wait，未重试；rc-11对应SIGSEGV。每臂保留原`closed case receipt: FileNotFoundError`、`actual_CPP_summary=null`，不能补造355000步、anchor、R比较、seed调用完成、solver成功或实际World加载完成。driver顶层`errors=[]`仅是原结构，整体`passed=false`与两臂错误均保留，不能将空顶层errors误读为执行成功。没有获得样本CSV或任何有效物理测量。

两份原console只有`No HOME defined. Will not log`以及ALSA/OpenAL默认音频设备失败等提示。这些是关闭时保存的输出事实，**不能据此判定SIGSEGV根因**；本次未做gdb或额外日志取证，也不以初始化崩溃为物理模型、quick/world优劣或安全界的结论。

### 连续parent实际费用与关闭

完整连续pair区间`[4480864950596286,4480877874774605]`收取 **12.924178319墙秒**。两case parent分别6.450256977和6.455060348秒；其和12.905317325只是nested参考，连续pair额外包含0.018860994秒臂间gap，不用nested sum替代收费。所有CPP/nested wrapper时间不另加；1800秒费用门未超。

承接90357.3610697996018，现累计 **90370.2852481186018 /120000**、余 **29629.7147518813982**墙秒。120000仍是代理依据持续委托选择的工程块，`numeric_user_approval_claimed=false`；pilot/final新增均0，原1870决策/2905.9547395464029墙秒及open401/402/403三场final-only900决策/9000墙秒保持。无learner模型或optimizer更新，原12EP30角色/95%/质量/安全门和旧FAIL保持。见[规范末账](assets/20261023_mr3_p2a_v55_passive_plant/closure_ledger_v1.json)。

[独立小元数据/来源关闭](assets/20261023_mr3_p2a_v55_passive_plant/checks/closed_metadata_review_v1.json)PASS：371完整source-before/after稳定，19份repo源current==本次Git，旧10份production/model/header/drive是其中子集且同原1fa，342封存链接对象字节一致；不把旧子集重复加总，也不把预期链接对象数当成崩溃CPP已记录的实际加载集合。配置、生成world、spec、buildmanifest/实际compile receipt与ELF/gzip关联保持原封存。没有复制342系统库。

root wait精确绑定launch/live SHA，实际entry/summary完整argv与launch除去Python `-B`后相等，live观察程序参数正确。主保存身份为 **6**：driver、运行时实观祖先、两wrapper与两CPP；早期identity/实际wait/监测记录逐同对象PID/start一致，6个均freshgone，Z算present、不可读不算gone，不跨对象补start。原driver `PENDING_EXTERNAL_ROOT_TOOL_REAP_AND_FRESH_GONE`字段不回写，由外部关闭证明补足。

本次source/metadata/不透明归档是CPU范围，真实wall **9.076326329秒**、rc0、17绑定输入前后稳定、工程费0；其两个保存身份在实际工具reap后[单独freshgone](assets/20261023_mr3_p2a_v55_passive_plant/checks/closed_metadata_cpu_postreap_v1.json)，不混入主6身份。[实际wait与完整console](assets/20261023_mr3_p2a_v55_passive_plant/checks/closed_metadata_cpu_v1/actual_wait.json)保留，wall不是CPU处理器用时。

[闭合库存](assets/20261023_mr3_p2a_v55_passive_plant/closed_inventory_v1.json)以原V45不透明archive函数逐字封存 **22文件/1262790原字节/1262742规范字节/0 symlink**；JSON/代码原样，console按mtime0 gzip并解码SHA验证。没有解释CSV、重读V52 raw、再运行CPP/World、读取其他实验原件或重做完整性/物理审计。原件保持本地，缺失CPP summary不补造。

下一仅定位本次native初始化SIGSEGV，再按实际原因准备新版本修复和有界验证；V55原活动不重跑/覆盖。当前没有有效物理结果，未证实quick50或world方案可用，也未提供原生资格或学习信用。P2A未完成。
