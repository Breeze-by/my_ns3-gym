# MR3 P2A V55：零轮目标的被动物理配对诊断

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
