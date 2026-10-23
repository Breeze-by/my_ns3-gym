# MR3 P2A V57：修复启动环境后，quick150 / direct-world 被动物理比较

当前仅准备，未启动World。用户持续自主委托直至P2A完成有效；本活动是新版本诊断，不修改V55旧FAIL或把V56调试成功作为物理证据。

V56真实栈定位到缺失HOME导致Gazebo DiagnosticManager初始化空指针。V57为每次活动创建独占HOME，不复制用户Gazebo配置。生产p1c三场均是quick150；本次两臂使用quick150（150迭代）及direct-world，除solver type外相同。生成场含原三机器人完整物理树和显式安装ground，移除plugin/sensor/visual；它不是旧生产episode重放。

继承V56末账累计90382.5535899546018/120000，余29617.4464100453982；新活动预约1800连续parent墙秒。120000是代理在持续授权下选择的工程块，不声称用户逐数值批准。每臂一次，无自动重试或补样；原生work600秒，outer720秒后仅对自身观测PID/start分阶段INT/TERM/KILL，真实wait/reap，不伪造timeout退出码；超额全费FAIL。pilot/final新增均0。

三机器人同seed101，每场45sim秒settle、一次固定anchor、310秒hold；1ms物理步、34ms配对wheel slew、目标0、accel1、torque20、wheel radius.033，固定R=.0078，不移动锚点，不增加控制器。每物理步观测，CSV每20ms记录。R内/外是描述结果，不决定执行链是否完整；binary64 hypot不是精确Q或连续证明，contact对象累计不是18流安全通过。没有actor、训练、任务或P2A资格信用。

新CPP/generator/build/loader、driver及scope的准确来源与CPU实际回执封存后，提交推送获得新exact40freeze。唯一正式入口：

```bash
# cwd=/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261023_mr3_p2a_v57_passive_plant/run_passive_pair_v1.py --freeze NEW_EXACT40
```

独占输出`/tmp/mr3_p2a_v57_driver_v1`，其中`home`必须新建。完整费用从第一wrapper Popen至最后真实wait，包含两臂间gaps，nested不重复加；source-after核对另记。实际root tool回收、保存身份freshgone和原件库存最后封存。全部失败及partial保留，只有完整比较结果能决定下一步是否更改生产物理版本；原12EP30角色资格、真实minimum/pilot训练和三场冻结策略strict95全部仍必需。

CPU准备实际结果：native编译rc0/50.28348627墙秒；driver6项人工回归rc0/0.299141532墙秒，包含HOME传递与中断后真实wait。ELF471256B、SHA`1d34ab6305ae8600cbfb2155622e8cef783b1f7c3ed496d83e94ffc8d944f9e1`。见[build manifest](assets/20261023_mr3_p2a_v57_passive_plant/checks/build_manifest_v1.json)、[driver实际wait](assets/20261023_mr3_p2a_v57_passive_plant/checks/driver_cpu_v1/actual_wait.json)和[scope](assets/20261023_mr3_p2a_v57_passive_plant/scope_v1.json)。均无World或学习信用；正式freeze由提交后CLI给出。

原生成spec实际CPU rc0/0.181073534秒；compile/generator共4身份freshgone，driver自身2身份另gone。清洁loader实际rc0、342库均匹配build对象；见[loader](assets/20261023_mr3_p2a_v57_passive_plant/checks/ldd_receipt_v1.json)与[编译关闭](assets/20261023_mr3_p2a_v57_passive_plant/checks/freshgone_v1.json)。最初源码逆变换checker的行移除顺序断言失败已保留，候选源未改，修正checker后全源逆变换通过，不作为native重跑。
