# P3B.5 逐条需求复核与独立方向延迟补验

状态：**技术复核 PASS，待用户验收**。本报告按 `IMPLEMENTATION_PLAN.md` 的 P3B.5 文字要求逐条审核。原[20261006报告](20261006_p3b5_gate.md)的57次结果和严格checker PASS保留；发现“独立上下行延迟只有协议测试、没有任务格”后补齐四个TASK case/六个原始episode。完整证据见[JSON](20261007_p3b5_requirement_audit.json)。未进入P3C、ns-3、Wi-Fi或RL。

原任务冻结 `d8d361bfd9d81e0c7a00c428ea66cfac4b3a1a76`；补验实验冻结 `09f15dfbaae7045171c04a2fe963f64240048b02`。两者任务/网关/电池/SLAM/Nav2/评估器源码字节相同；只增加清单、只读审核和文档，不调算法。原57格再次只读严格审核PASS。补验使用开发seed202/101、fault seed17011，未再次运行已暴露的809。

## 逐条要求与证据

| 编号 | 要求 | 结论 | 对应证据 |
|---|---|---|---|
| F01 | 运行前冻结commit/world/目标/机器人/电池/任务/fault/TTL/deadline/retry/queue/horizon/环境 | PASS | 原57 manifest、config、实际命令和源hash；新增09f15df四case逐项冻结；本JSON只读展开原有共享字段 |
| F02 | 每个故障case具有同seed/同配置ideal配对 | PASS | 原27+新增4=31pair；复用ideal明确计数；同提交同环境及task source严格比对 |
| M01 | coverage/target/rally；四world；2/3机器人；开发与独立fault seed分层 | PASS | 原27pair包括my_world/rooms/corridors/首曝809；101/202/303开发seed与fault17011/holdout28091分别保留 |
| M02 | 独立上下行0/10/100%丢包与0/.5/2秒延迟的任务覆盖 | PASS | 原zero/up10/down10/up100/down100；新增四独立方向延迟case真实TASK账本，54协议另列 |
| M03 | 固定burst、独立丢包、TTL、deadline、retry exhausted、duplicate/reorder、queue overflow | PASS | 原对应任务case及实际事件，原54协议/636组件；高损任务失败全部保留 |
| M04 | 检测、地图/pose/TF、探索、集合导航、电池与返航的故障后果 | PASS | detection_loss/map_loss/pose_loss/nav_loss/battery_loss；duplicates_corridors集合阶段导航重试耗尽；forced/controlled blackout实际返充 |
| S01 | 过期地图/pose/TF禁止中央新分配/重规划；已接受安全本地目标有界执行/等待 | PASS | 全部63时序和source leases；原stale wait、navigation deadline；新增2秒uplink下2秒pose/TF TTL过期不产生导航 |
| S02 | 检测未交付不进入RALLY；RALLY目标lease过期不产生新目标驱动决策 | PASS | detection_loss/TTL/up100无RALLY；state_loss_lab与burst_rooms RALLY实际目标过期采样14/28，最大125.7/195.3秒；原严格账本检查及target lease组件 |
| S03 | 无新鲜确认/超过deadline取消停止并可恢复等待，旧命令不无限保持 | PASS | 命令source/deadline校验；无中央上下文的本地0.1秒timer；原local_deadline_cancel实际取消；late accept/cancel-before-goal组件 |
| S04 | 电量/返航/本地碰撞急停及避障优先于网络；断网安全返航 | PASS | ACTIVE以外拒绝中央导航；0.1秒本地deadline；两机器人黑窗内真实Nav2向home运动及各充电一次；RPP本地碰撞检查→controller零速度，软件/config来源明确 |
| S05 | 只以新鲜版本和合法任务阶段恢复；不使用旧消息回滚 | PASS | receiver TTL/严格单调sequence；source stamp不续租；固定任务状态转移表；target重确认与重复charge幂等组件/实际恢复账本 |
| S06 | 单机器人显式失效隔离；健康者继续；PARTIAL不算COMPLETE | PASS | tb3真实FAILED隔离0.1秒；健康两机原生PARTIAL_COMPLETE148.9秒；success=false/TDI1/3；无线静默不伪造physical failure |
| O01 | 每episode任务与按消息类型/方向的账本摘要 | PASS | 本JSON63份任务+账本：终止/失败、stale/deadline、碰撞、电池、充电、最低电量、集合误差、generated/accepted/drop/expiry/retry/queue admissions/overflow |
| T01 | 冻结TDI定义、ideal COMPLETE资格、均值和95%CI及原始指标 | PASS | 原18eligible/5簇；补验4eligible/2簇；合并22eligible/5簇，10000次physical cluster bootstrap seed17011；FOUND/coverage/失败ideal不入TDI |

## 四个新增任务case

0.5秒采用走廊2机器人/seed202/E45，2秒采用房间3机器人/seed101/E40；capacity100、同原充电与安全参数。每个场景的两方向共用一个同配置ideal，不把共用ideal计为两次独立运行。四case在运行前逐项声明，上下行另一方向延迟为0，丢包为0。

| 故障case | 同配置ideal | fault原始结果 | 完成时间增量 | TDI |
|---|---|---|---|---|
| uplink_delay05_corridors2 | 176.8 s COMPLETE | 252.9 s COMPLETE | +76.1 s | 0 |
| downlink_delay05_corridors2 | 176.8 s COMPLETE | 181.4 s COMPLETE | +4.6 s | 0 |
| uplink_delay2_rooms3 | 150.2 s COMPLETE | 300.0 s timeout，0导航 | 无完成时间 | 1 |
| downlink_delay2_rooms3 | 150.2 s COMPLETE | 175.9 s COMPLETE | +25.7 s | 0 |

六个原始运行零碰撞、零耗尽/物理失效、零基础设施/操作失败，全部自然关闭，未重试或回填。0.5秒上行格实际充电一次；其余五格没有充电。最低电量22.34。2秒上行格的pose/TF在2秒TTL到期后被丢弃，中央保持等待且未产生Nav2目标，直到原300秒时限结束；不降低TTL或延长任务来制造完成。

四个实际方向的交付延迟均逐attempt核验：0.5秒上行6524、下行533次；2秒上行2509、下行1191次交付。源时刻/发送/交付的仿真时间因果和源TTL/版本检查通过。2秒上行仍有map/battery交付，不能把“部分消息可交付”当作pose/TF可用。

## TDI 与全部原始输出

| 统计范围 | eligible episode-pair | 物理配置簇 | TDI均值 | 95% CI |
|---|---:|---:|---:|---|
| 原27pair | 18 | 5 | 0.685185 | [0.487179, 0.823529] |
| 新增4pair | 4 | 2 | 0.250000 | [0.000000, 0.500000] |
| 合计31pair | 22 | 5 | 0.606061 | [0.384615, 0.800000] |

仅ideal原生COMPLETE的rally pair纳入TDI；fault完整完成为0、健康2/原需3的PARTIAL为1/3、失败/超时为1。原E0与0.3秒deadline的失败ideal明确排除，三个target与四个coverage pair只计过程指标。CI为10000次physical-cell cluster percentile bootstrap，seed17011；共用ideal和同物理配置相关性按簇处理，属于固定矩阵描述，不是最终未见总体泛化或P7统计结论。

合计**63个原始episode＝原57＋新增6**，**31个故障配对case＝原27＋新增4**。JSON含每格终止/失败、COMPLETE/PARTIAL/FAILED/timeout/no_data、stale与navigation_deadline事件、碰撞、电池失败、充电、最低电量、集合误差和原生保持证明；按消息类型/方向输出generated/accepted/dropped/expired/retry与queue admissions/overflow。每pair保留实际完成时间增量（未完成为null）、覆盖率/能量增量、应用PDR与AoI/时延增量，未交付的AoI不填零。十个固定ideal也补齐同口径的只读账本摘要。

JSON的 `resolved_case_manifests` 从**原先已冻结**的命令、各自pool manifest与源hash展开31个case的参数；它是共享字段的只读展开，不冒称事后重新预注册。环境分别保留原pool CPU亲和性，新增两个pool均0–79；每个ideal/fault pair使用相同commit、配置和环境。

## 本地安全与实现边界

本地RETURNING/CHARGING/FAILED拒绝中央导航，导航命令源TTL/deadline与0.1秒本地取消timer不依赖中央context；迟到目标接受后也必须取消。正常恢复仍按接收源时刻、严格版本和合法任务阶段执行，不把无线静默推断为机器人物理失效。原单tb3故障隔离0.1秒、两健康机原生PARTIAL_COMPLETE148.9秒/`success=false`保留。原受控断网窗口内两个机器人都有实际Nav2 EXEC运动并各充电一次，仍作为安全证据，不计任务完成。

碰撞急停采用已有机器人本地Nav2 RPP的footprint/costmap预测检查：预测危险时拒绝速度，controller发布零速度，不经过故障gateway。当前安装Nav2 1.1.20的[RPP实现](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_regulated_pure_pursuit_controller/src/regulated_pure_pursuit_controller.cpp#L332)和[controller停止实现](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_controller/src/controller_server.cpp#L449)对应已启用的配置；机体覆盖、碰撞检查和仿真时钟组件通过。ContactsState用于评估碰撞，不把63格零接触说成实体碰撞传感器/硬件急停认证。

原state_loss_lab与burst_rooms在RALLY后确实发生目标lease过期，分别14/28个诊断采样，最大源龄125.7/195.3秒。严格账本拒绝过期目标驱动的新任务决策；安全返航和使用当前位置/新鲜地图的重新确认动作保留，不续租旧目标。

## 只读审核修正与复现

新增checker首次把未发现目标格的 `null` 坐标与冻结目标比较而FAIL；[原始trace和六格SHA](20261007_p3b5_directional_delay_initial_audit.json)保留。修正仅把**配置目标**绑定到实际CLI，并要求尚未发现时观测坐标仍为null；错误配置/伪造检测反例被拒绝。未改变任务栈、数据、TDI/native/安全门槛。31项runner/新checker检查、22项freshness/版本/导航检查、1项机体/RPP检查，共54项通过；原636组件证据保留。

预声明的队列参数为0，原注释误写“unbounded”。实际冻结gateway把0解析为默认4096，overflow case为1，ideal为4096；这不是改变队列配置。[原始预声明快照](20261007_p3b5_directional_delay_frozen/p3b5_directional_delay_manifest.json)和其SHA保留，当前清单只修正说明文字；JSON逐case同时记录参数值和有效容量。队列摘要为准入/溢出次数，队列占用曲线留待P3C。

Humble/install环境下的精确补验审核命令：

```bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
/usr/bin/python3 scripts/check_p3b5_directional_delay.py \
  --base /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261006_p3b5_gate.json \
  --config /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261007_p3b5_directional_delay_frozen/p3b5_directional_delay_manifest.json \
  --summaries log/p3b5/p3b5_directional_delay_20261007_corridors/summary.json \
    log/p3b5/p3b5_directional_delay_20261007_rooms/summary.json \
  --output /tmp/p3b5_directional_delay_reaudit.json
```

两master19700/19701、domain180–182/200–202及所有owned任务/观察器已关闭；域222未操作，17份用户资料SHA不变。六份实际Nav2 sim-clock与SLAM2秒参数旁录完整。原lab303仅5.2秒余量，预算仍不保证最坏任务时限；809已暴露，后续控制修改需要新的未见留出。技术完成后仍等待用户验收，再进入下一检查点。
