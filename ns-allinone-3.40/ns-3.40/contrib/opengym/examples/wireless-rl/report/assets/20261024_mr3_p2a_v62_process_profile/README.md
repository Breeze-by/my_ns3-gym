# 固定 V62 性能诊断候选

仅一个 open:101、1 worker、8步普通 probe_action 的零学习诊断。固定run `/tmp/mr3_p2a_v62_open101_8step_profile_v1`。不启用32步 preparation_motion_probe/参数readback，不给policy、完整native资格、物理安全或容量信用。现有V48恒等优化已在当前生产，不把它们再次算成新收益。

固定分工：ns3gym Conda Python仅运行benchmark launcher；worker、motion_safety、adapter与ROS prefix全部用`/usr/bin/python3 -B`。三固定进程分别main pstats；仅adapter encode_snapshot和worker ROS-spin两个真实线程入口另取独立pstats，共5份。其它线程与C++内部不分解。cProfile函数耗时含等待，cumulative行重叠；另保存process/thread CPU ns，不能把pstats累计时间当CPU预算或内核成本。

core保留runcall/runpy的SystemExit、异常与默认信号语义；普通dump异常不覆盖target rc。线程仍存活、未观察hook、丢finish或pstats都会诊断FAIL。actualargv与实际临时regular params完整SHA/bytes/只读快照保留，不假称事先预知随机路径，也没有参数readback信用。

仅两个whole-byte可逆源码投影：Supervisor.reset固定worker命令prefix；Worker.__init__固定ROS-spin透明包装及ROS launch prefix/filter。args/kwargs/return/异常与原main、__file__、script sibling sys.path语义保持。实际投影bytes、原source、edits与逆投影证明保存；不能声称执行body逐字未改。源pin承接已闭合C `0ab8d8339368681d657f09814e45a38eae6b2f46`；正式launcher还必须核全部实际生产源属于新的clean/pushed执行freeze。

只读reviewer API：`review_profile_v1.py --freeze HEX --scope A62/scope_v1.json --run /tmp/mr3_p2a_v62_open101_8step_profile_v1 --driver /tmp/mr3_p2a_v62_parent_v1 --output /tmp/mr3_p2a_v62_parent_v1/profile_review_v1.json`。固定正常8返回/close、3真实角色与supervisor saved PID/start关联、5pstats、sourceprojection/params回执。A16 Evidence.visit仅核同原对象PID/start，Z同start仍present，PID-only不补start。当前parent/bootstrap/transport ancestors明确排除runtime absence，不发送信号、不运行科学消费者或读原始telemetry。每pstats32MiB、总128MiB；metadata/params累计64MiB。review最多300墙秒且受complete-parent余量约束，超限partial/FAIL，原件保留。

root独占parent/scope/bootstrap：complete parent1800，native cooperative allocation1500（close120在内），pre/post/review共享余300；全部实际费后判，不承诺硬实时。真实8步不在本候选CPU中执行。

当前/tmp人工CPU v3真实tool96383 reap0，4.556441205s：13 pytest组、15真实child waits，284源before/after/current与快照一致，18保存身份freshgone。包含installed ros2launch CLI→API配置→Executable.prepare真实命令构造（LaunchService替身，不起进程）、真实Conda仅benchmark导入、profile异常/rc/线程、人工closed metadata完整路径与缺profile反例。v1 tool13843的11PASS/3.936702301s原源回执另存attempt_before_benchmark_runtime_v1；v2的13PASS原件仍完整保存在旧candidate目录；v3另核/tmp与canonical位置两种前执行拒绝，只有v3对应最终源码。CPU工程新增0，未执行ROS节点、World、模型、sampler或读取旧raw。

canonical安装后仍须按最终source/spec另封实际CPU（包含固定模块--help/import路径）与新clean/pushed执行freeze；不能把/tmp文件名/源SHA的CPU直接冒成canonical final准入。生产控制数学保持，未知取消因果修复另版本进行。
