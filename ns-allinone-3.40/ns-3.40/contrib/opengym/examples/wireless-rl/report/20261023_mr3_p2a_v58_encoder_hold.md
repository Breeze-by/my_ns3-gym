# MR3 P2A V58：初始静止阶段的本地轮编码器保持候选

**当前已实际闭合，执行/取样描述PASS：** freeze`b6af48cfe88b73a633d0e7552b88c3489900391a`、root tool23554真实reap rc0，355000步/355模拟秒完整；三机固定body anchor最大位移约7.56446e-6m，低于原R=.0078。只对本次隔离候选取样有效，没有生产资格、连续证明、训练或95%任务信用。完整parent899.40726088墙秒已收，累计92217.1876804376018/120000、余27782.8123195623982。实际关闭节为当前状态，下方预声明/尚未World/待freeze文字保留为准备快照。

2026-10-23预声明与CPU准备已完成。helper12组、driver最终6组及真实native编译通过，source/spec/实际回执已封存于末节；待新exact40freeze提交推送后一次正式诊断。本版尚未World或生产应用，CPU不提供物理或P2A信用。用户持续自主委托保持，P2A未完成。

## 依据与边界

[V57实际闭合FAIL](20261023_mr3_p2a_v57_passive_plant.md)：quick150在600墙秒合作式上限处只完成235.631模拟秒，其三机已观测固定锚点位移约7.35mm，不能证明完整310秒hold；direct-world完整355模拟秒却出现4.09–5.78m位移，已排除该生产候选。原失败、部分观测和费用全部保持。

本版针对轮轴位置误差设计一个新的有限内环。它只读取本机轮编码器q、qdot与body desired(v,w)，不把WorldPose送入控制。编码器位置稳定也不保证机身不滑移，原固定机身圆盘仍须由实际物理观测检查；不能从这个控制方程推出R安全。

## 唯一候选控制律

profile暂定`initial-zero-encoder-hold-v1`。仅在该epoch首次任意非零body request之前允许启用；第一次非零v或w（包括纯转）永久退出，到新epoch对象才重新开始。连续三个实际34ms更新均满足request v=w=0且两轮实测rim速度绝对值≤.01m/s，才一次捕获q_ref。重复zero、decision、时间推进或后续测量不刷新参考。

保持分支固定P增益1/s（名义1秒时间常数），每轮rim反馈为`.033*(q_ref-q)`，先截断到±.005m/s，再经过原`limit_paired_wheel_speeds(current_rim, servo_desired, 1, dt)`。未捕获和已退出分支按原配对slew处理body request。该版不加积分，不unwrap/snap编码器值，不调用SetPosition、姿态/机体速度写入或固定关节。输入有限性及状态提交行为由CPU检查；q原API的连续性和物理适用性仍待实际验证。

实际纠偏可产生正、负非零电机命令，必须逐次记录q/qdot/q_ref、参考捕获次数、servo目标、slew输出、实际写入/读回与armed状态；不得将它标作zero-wheel或隐藏在原actual-command字段内。它是新的actuation方程，不能借用旧`measured_joint_rim_paired_common_fraction_v1`恒等证明、STOP符号债务或V15“no-new-build”桥作新资格。当前候选不扩到首次运动之后的STOP/再次静止场景，也不承担探索决策。

## 后继有界诊断预约

承接[V57规范末账](assets/20261023_mr3_p2a_v57_passive_plant/closure_ledger_v1.json)：工程累计 **91317.7804195576018/120000**墙秒，余 **28682.2195804423982**。为新版本单臂活动预约完整parent **2100**墙秒，预约后余 **26582.2195804423982**。120000是代理依据持续委托选择的有限工程块，未声称用户逐数值批准。pilot/final新增均0，原余额和用途保持。

待CPU、真实build/加载对象、source/spec及新freeze封存后，只执行一个quick150场、三机器人tb1/tb2/tb3、seed101。仍为45模拟秒settle＋310秒hold，355000个1ms物理步、34ms电机更新、torque20、accel1、wheel radius.033、一次固定机身anchor及R=.0078。WorldPose仅用于隔离的机身观测，不回馈servo；不换solver、不扫描参数、不移动安全anchor。该场不是旧V57补样或生产episode重放。

V57的实测速率不足以在600墙秒完成本目标，因此本版前瞻声明native合作式work上限1500墙秒、outer1800秒后仅对实际观测的owned PID/start分阶段收尾，并真实wait/reap；完整parent仍限2100，不宣称操作系统硬实时。超时、丢证据、命令不符或原物理门失败均保留partial/全费失败，无自动重试。完整费用按实际parent区间计，nested不重复；最终准确外尾口径随scope封存。

拟入口（当前占位，尚不能执行）：

```bash
# cwd=/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261023_mr3_p2a_v58_encoder_hold/run_passive_pair_v1.py --freeze NEW_EXACT40
```

独占输出拟为`/tmp/mr3_p2a_v58_driver_v1`，HOME必须新建；最终环境由scope/真实submission完整记录。先做CPU及静态来源检查，再commit/push取得精确freeze，随后才可一次诊断。原件、actual root-tool回收、保存身份freshgone、无损库存和费用闭合后才解释结果。

本活动没有原生资格、模型、optimizer或95%任务信用。即使机身观测完整落在R内，后续仍须明确生产新actuation/真实build与独立执行方程门，再完成同freeze的12EP30角色资格、实际minimum/pilot学习和三场冻结策略strict95验证。原任务/质量/安全门及历史FAIL保持，P2B/gateway未启动。

## 封存前实际准备结果

helper的12组CPU实际rc0/1.96319775墙秒；首轮模块入口导入FAIL/.228416829原件保留，修入口后没有改候选参数。见[helper实际wait](assets/20261023_mr3_p2a_v58_encoder_hold/checks/helper_cpu_v2/actual_wait.json)、[helper证据](assets/20261023_mr3_p2a_v58_encoder_hold/checks/helper_candidate_v1.json)。这里的request是`update`实际输入，尚未实现ROS接收/覆盖语义；未来生产若成功接收到首非零目标，即须锁存退出，不能只等34ms消费而漏掉被zero覆盖的非零消息。本次只有zero输入的独立诊断不提供这项接收语义资格。

native generator实际rc0/.137421507墙秒、compiler rc0/52.375035399墙秒；4保存CPU身份gone。ELF494528B，SHA`0f911c2a0d163e66bb32656944732a74a760511aff49b606bf947b6517e118e6`；342 clean-loader对象字节稳定。单quick150世界逐字保留A57原输入，SHA`5cac66c22e0281de6c424aa517147cb33fffd818e4df7240a60c8a3cc2527298`。见[build manifest](assets/20261023_mr3_p2a_v58_encoder_hold/checks/build_manifest_v1.json)。未执行ELF main/World。

driver6组人工回归三轮实际rc0（.319194718/.329905909/.391277212墙秒），仅末轮绑定最终driver；前轮源码快照、实际回执和各自关闭证据保留，不累计成18项独立检查。末轮覆盖真实非零servo记录可被接纳、重复capture被拒、partial实际rc和无重试/完整费用；见[最终实际wait](assets/20261023_mr3_p2a_v58_encoder_hold/checks/driver_cpu_v3/actual_wait.json)及[freshgone](assets/20261023_mr3_p2a_v58_encoder_hold/checks/driver_cpu_postreap_v3.json)。静态接线核对通过，body pose不进入servo，固定body anchor仍只捕获一次。

[scope](assets/20261023_mr3_p2a_v58_encoder_hold/scope_v1.json)已准备，准确freeze由commit/push后的唯一正式CLI绑定。运行环境保留独占HOME，并显式`ALSOFT_DRIVERS=null`选无输出音频后端以避免无关音频自动启动；这不改变物理配置。依据[OpenAL Soft环境文档](https://github.com/kcat/openal-soft/blob/master/docs/env-vars.txt)及[1.19.1 null后端源码](https://github.com/kcat/openal-soft/blob/openal-soft-1.19.1/Alc/backends/null.c)，本机1.19.1 ELF同时具有对应环境键和No Output后端标记。完整实际环境写入submission，不以此宣称所有外部daemon不存在。

## 实际执行与关闭

原准确CLI（活动已关闭，不再运行）：

```bash
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261023_mr3_p2a_v58_encoder_hold/run_passive_pair_v1.py --freeze b6af48cfe88b73a633d0e7552b88c3489900391a
```

CPP/engineering wrapper/root均实际rc0；355000个1ms步完成355模拟秒，45秒一次机身anchor之后310001次观测覆盖完整310秒hold。tb1/tb2/tb3最大固定anchor位移为7.564460922440505e-6 / 7.564460921095306e-6 / 7.564460923987289e-6米；最大平移速度约6.58461348e-5m/s。每机10441次真实motor更新、q_ref捕获一次；最大实际写入电机目标约.00126813934rad/s，是已披露的非零纠偏，不能称zero-wheel。机身anchor未刷新，helper只读本机编码器。上述量是binary64/1ms取样描述，不是精确Q连续证明、任务/18流安全通过或生产资格。

启动次序存在一项透明记录：本地exact Git已提交，但native提交先于观察到push RPC真实reap；push随后实际rc0。未声称push回收先于启动，原[push观察收据](assets/20261023_mr3_p2a_v58_encoder_hold/closed_execution/closure_tools/mr3_p2a_v58_push_tool_actual_wait_v1.json)完整保留，活动不重跑或补写顺序。

连续parent实费**899.40726088**墙秒（native内部893.582203956包含其中，不另加），累计**92217.1876804376018/120000**、余**27782.8123195623982**；numeric_user_approval_claimed=false，pilot/final新增0。372原源before/after稳定，关闭时核20新代码/28 repo current-Git、old10及30非库字节；342库只匹配原完整receipt/manifest，不重读。仅4份实际保存main身份freshgone，不补身份或宣称所有外部daemon不存在。

20 regular原件35601348B无损封存为9623421B、0链接，含body/motor CSV原始字节；没有重算CSV语义。关闭metadata CPU实际tool68165 reap rc0，25.947314682墙秒、16源before/after相等、工程新增0；自身2份保存身份另freshgone。见[库存](assets/20261023_mr3_p2a_v58_encoder_hold/closed_inventory_v1.json)、[metadata关闭](assets/20261023_mr3_p2a_v58_encoder_hold/checks/closed_metadata_review_v1.json)、[CPU实际wait](assets/20261023_mr3_p2a_v58_encoder_hold/checks/closed_metadata_cpu_v1/actual_wait.json)、[CPU freshgone](assets/20261023_mr3_p2a_v58_encoder_hold/checks/closure_cpu_postreap_v1.json)及[规范末账](assets/20261023_mr3_p2a_v58_encoder_hold/closure_ledger_v1.json)。原driver pending字段和全部历史FAIL保持。

下一S59才实施生产新profile、接收首非零立即锁存、真实newbuild/第7helper宏与ELF来源，以及独立compound-law/cadence严格门；本次候选不借旧V15 no-new-build或旧paired-slew恒等信用。代理依据持续委托选择后继有限工程累计块150000，从本次真实账92217.1876804376018承接、余57782.8123195623982，拟完整链预约47220，具体scope在实现/CPU后封存；150000不是逐数值用户批准，未重置旧账或pilot/final。只有新同freeze完整12EP30角色、实际minimum/pilot学习和三场冻结策略strict95全通过才完成P2A。
