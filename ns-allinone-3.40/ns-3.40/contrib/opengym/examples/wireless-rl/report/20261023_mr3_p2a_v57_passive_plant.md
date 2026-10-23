# MR3 P2A V57：修复启动环境后，quick150 / direct-world 被动物理比较

**当前已CLOSED FAIL。** freeze `71cb6b18090d8e140048b0ab69fe7c81d9a365ea`，root tool92392真实reap rc1。quick150仅完成235.631sim秒后合作式600秒上限partial；direct-world执行完成355sim秒但固定anchor位移达4.09–5.78m，物理候选失败，禁止据此接生产。实际连续parent935.226829603墙秒，累计91317.7804195576018/120000、余28682.2195804423982。以下原准备内容及原driver pending字段原样保留；本页末尾实际关闭节和规范末账为当前结果。

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


## 实际结果与关闭（2026-10-23）

唯一执行freeze为`71cb6b18090d8e140048b0ab69fe7c81d9a365ea`，root tool92392实际reap rc1。两CPP均真实返回并shutdown，无自动重试；原pair `passed=false`、顶层`errors=[]`及两臂实际状态同时保留。独占HOME已使两臂进入物理步进，不能把修复启动当作模型/控制或物理候选通过。

| 臂 | CPP / wrapper实际rc | 完成窗口 | 执行结论 | 固定anchor结果 |
| --- | --- | --- | --- | --- |
| quick150 | 1 / 1 | 235631步、235.631sim秒；仅190.631秒post-anchor | PARTIAL_OR_FAIL，实际合作式600秒上限，shutdown600.116527557墙秒 | 三机max约.0073513646204m；只在该部分窗口内未观察到超R，不能当完整310秒hold通过 |
| direct-world | 0 / 0 | 355000步、355sim秒，含310秒hold | COMPLETE / execution_passed=true | 三机全部超R，物理候选严重失败，不能接生产 |

| direct-world机器人 | 最大anchor位移(m) | 最大平移速度(m/s) | 首次超R时钟(sim秒) |
| --- | --- | --- | --- |
| tb1 | 4.092486164689881 | 3.607078686419674 | 45.784 |
| tb2 | 4.4155389088244865 | 3.7882919503566215 | 45.032 |
| tb3 | 5.779568440772417 | 3.6041915890845906 | 46.094 |

上表仅读取预声明CPP已有summary聚合，未重解释CSV或增加新物理reader。`desired_body_target=[0,0]`和`desired_wheel_rim_target=[0,0]`是目标；配对feedback slew可能输出非零命令，不能隐去或把目标0写成“所有实际驱动命令始终0”。完整CSV原字节保留。R仍为.0078m、45秒只取一次固定anchor，没有为了结果刷新anchor/扩大R；binary64 1ms sampled hypot不是精确Q或连续安全证明，contact累计不是18stream资格。direct-world完成仅是执行协议完整，与物理候选可用性分开；本结果不支持direct solver生产路线。

### 实际费用、来源和身份

完整连续pair parent为 **935.226829603墙秒**：quick150 case parent605.740176299 + gap.025355993 + direct-world case parent329.461297311。按预声明从第一wrapper Popen至最后真实wait，nested CPP与关闭CPU不相加；entry/post-source metadata分别保存，没有改写原费用口径。承接90382.5535899546018，累计 **91317.7804195576018 /120000**，余 **28682.2195804423982**；未用1800预约不当作实费。120000仍是代理依持续委托选定的工程块，`numeric_user_approval_claimed=false`；pilot1870决策/2905.9547395464029墙秒与final-only open401/402/403共900决策/9000墙秒全部不动，本次policy/model/optimizer新增0。

[关闭metadata](assets/20261023_mr3_p2a_v57_passive_plant/checks/closed_metadata_review_v1.json)绑定实际root wait、launch、活体祖先和CPP/wrapper同对象身份，6份实际保存的main PID/start均freshgone（同start的Z算present，不可读拒绝）；不补缺失PID/start，也不宣称未记录的外部daemon全部退出。372条原source before/after稳定；关闭新核30非库源、28repo current-Git、old1fa的10源子集。342库仅匹配原稳定receipt与封存manifest metadata及resolved别名，未重复读取库对象。

[库存](assets/20261023_mr3_p2a_v57_passive_plant/closed_inventory_v1.json)保存 **28份regular原件、原32763601B、规范12859498B**，JSON逐字、CSV/log仅opaque无损gzip；不重算轨迹、控制或奖励。[closed_execution](assets/20261023_mr3_p2a_v57_passive_plant/closed_execution)另含[1条符号链接记录](assets/20261023_mr3_p2a_v57_passive_plant/closed_execution/symlink_records_v1.json)：私有HOME中的Pulse runtime链接只存lstat和原readlink字面目标，不跟随或复制外部target，不把链接算成regular原件。恢复regular文件时按库存decoded SHA/bytes核验；若恢复该链接，按link记录创建原字面target即可，外部target内容不属于本库存。

关闭CPU首轮实际rc1/**18.815633349墙秒**，因发现Pulse目录符号链接在归档前拒绝；原脚本/console/wait保留。后轮只增加上述不跟随的literal链接记录后实际rc0/**28.583849962墙秒**，16源前后稳定、工程新增0。[CPU postreap](assets/20261023_mr3_p2a_v57_passive_plant/checks/closure_cpu_postreap_v1.json)分别记录两轮自身4身份freshgone。没有重复运行World/native/科学consumer，没有改写原driver pending。[规范末账](assets/20261023_mr3_p2a_v57_passive_plant/closure_ledger_v1.json)可供下一活动直接承接。

### 下一步边界

停止direct solver生产路线；下一仅对本地轮编码器zero-hold的有限servo做源代码/数学静态评估。此时没有新科学版本、生产应用或新native准入，不把该候选当现门恒等替换。不得改R、刷新固定anchor、隐藏非零命令或机械重跑旧矩阵；任何后续实际活动另用清楚的新版本/scope/freeze。V52资格FAIL、V55启动FAIL、V57partial/物理失败及实费全部保留，12EP30角色/95%/安全门和pilot/final原额不变，P2A未完成。
