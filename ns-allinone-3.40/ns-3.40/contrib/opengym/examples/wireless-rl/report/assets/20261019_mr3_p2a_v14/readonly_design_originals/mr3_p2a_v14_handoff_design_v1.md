# V14 activation / translation handoff — 只读设计稿

本稿只供数学和隔离 CPU 原型评审，尚非已证明的安全契约或可运行协议。没有修改生产源码、旧 schema、ELF 或 reader，没有运行 native、GPU、正式 consumer。V13 原矩阵 FAIL、minimum FAIL 和旧 reader 的原始含义均保留。逐文件 SHA、具体行段和未闭合前提见同名 JSON。

当前可实现的最小方向是：**把“零线发布资格计时”与“已生效保护的固定 anchor”分开；先有完整二维 generic 过渡/停车覆盖，再发非零线速度；发布后保持 handoff pending，直到实际应用与后续因果源被绑定后才退休旧保护资格。** 非零发布、storage ACK、零发布和 stop ACK 都不是清 anchor 的事件。

## 1. 已证实际时序

1. `mr3_env_worker.py:541–564` 在物理暂停的同一 clock，依次提交 state、peer、motion，消费 motion 本地 topic receipt，再等三台 driver 对精确目标的 storage 回执。`695–746` 在每次物理推进前重新核对这些回执，推进 20 个真实 1ms tick，等真实 /clock 到暂停边界后再 commit 下一边界；`1219–1229` 另有 evaluator 屏障。
2. `motion_safety.py:546–550` 先 `activate()`，然后 `tracker.output(v,clock,seq)`；实际 Twist / tagged target 发布在 `562/567`。`mr3_motion_safety.py:85–91` 在任何 `linear != 0` 时已经清除 active、anchor、path 和样本。因此当前清除甚至早于发布调用，更早于 storage/actuation。`output_completed` 只证明发布及本地最终 Twist topic 回收（`216–259`、`577–585`），不证明底盘响应。
3. driver `OnTarget:769–808` 在锁内验证七字段 tag 后写 target、增加 cmd_seq 并发 status。`mr3_drive_phase.py:59–83` 要求 epoch/robot/sequence/值和 source/actual clock 精确一致；这是真的 **storage**，不是 wheel 或机体切换。
4. `mr3_gazebo_diff_drive.cpp:624–739` 在 `WorldUpdateBegin`（`582–588`）工作：WORLD odom/TF 在 `649–681` 先发布；满足 actuator period 后，`695–726` 才在同一命令锁内选择当前 target、读实际轮 rim、成对限速并 SetParam；`727–736` 的 actuation journal 绑定实际消费 seq、clock、current/desired/applied rim。同 stamp odom 先于该次 actuation，不能称为其机体响应。
5. SDF `594/602` 是 30Hz / 1.0m/s² wheel-rim slew；driver `445` 固定 tagged WORLD odom 为 20ms。30Hz 是 period 条件，不是每个 guard 目标都会被应用。1ms tick 条件下，1/30s 通常在下一 34ms 迭代满足；该最大相位延迟仍须作为受支持执行模型的明确前提，不能直接拿标称频率充当真实上界。
6. 例：相对 t=0 的 target seqA 已 stored，t=20ms seqB 覆盖它，t≈34ms 才首次 actuation；实际可只消费 seqB。**不能等每个/最初非零 seq 都实际应用才允许下一 20ms commit**，否则会引入人为死锁。应允许同一 handoff 的后继 seq，最终绑定实际被消费的那个 seq。
7. worker stop 是独立永久通道：`526–539` 取真正 stop ACK 并等三台零 target storage；`695–708` 在推进前再核；`1453–1478` 的清理失败仍是不合格基础设施出口。`mr3_motion_control.py:192–236` 不让 stop 覆盖成成功 normal ACK。stop/storage-zero 不证明轮、机体或侧滑已经停止。

## 2. 与旧 independent settled reader 的边界

旧 `mr3_independent_settled_turn_v3.py:249–303` 独立检查 .94s 零线发布、.78s actual stored-zero、三份 100ms 内的 raw rest 源、完整平面速度、peer margin，并绑定原 publication/storage。`304–318` 的首 grant 固定 source anchor，但一旦发布非零 v 即在历史 replay 清除它；`323–328` 的 interval end 则取首 nonzero **storage**，不是 actual actuation。`331–352` 检查至该端点/最终 physics 的全段 raw chord、.01 和累计 .0078，并要求末源新鲜。

这不闭合 storage→actuation→body response 交接，也不证明采样间连续路径上界。旧 reader 自己在 `367` 明确说明 chord 只是连续路径的采样下界。新固定 disk 的径向约束不是旧累计 path 条件的重命名：必须有新的前瞻数学契约/身份、独立重建与受影响审计，不能修改旧 reader 或用新门把 V13 改记 PASS。

## 3. 连续覆盖义务

命令 .20m/s / .8rad/s、完整机体 .30m/s / 1.2rad/s、原源龄 .5s、rest .01m/s、三源 100ms 和 .94/.78s 必要门均不在此稿中调宽；新 disk 与 handoff 是新的前瞻对象，不能暗换旧数值或旧累计路径契约。

记旧保护 disk 为 `D(a,R)`，`R=.0078m`，anchor 含 epoch、原始 odom frame/pose/source/ingress seq/hash 和 common-frame lift 的具体 TF。重复 grant/零输出不得移动 a。若以当前/延迟源点 p_s 计算旧 pair 几何，且 `p_s,p_future ∈ D(a,R)`，则只由三角不等式得到 `|p_future-p_s|≤2R=.0156m`，不能仍把未来位移只算 R；直接以 a 计算则必须同时处理 anchor→共同 frame 和源龄误差。旧 .50m 双机体、.02m margin、完整源龄不应静默删除或重复抵消。

拟发布非零 target 之前，必须已经有 generic bridge `B_i(τ)`：从**整个**当前可达位置/二维速度/轮状态集合开始，包含旧 target 残留、新 target、所有允许的 storage/actuation 相位与机体响应延迟；也包含到期/缺数据/stop 的 backup。不能把当时观测点视为精确当前静止状态，或把轮指令线段等同为机体速度线段。

对每个允许推进区间及其 backup，真实中心必须始终落入预先证明的覆盖集；各机器人集合的所有允许组合必须保持机体加原几何余量分离。handoff 期间不得有从“旧 zero 前提已可能失效”到“新 generic 证据后来到达”之间的空窗。可把不确定切换时刻下的 old/generic reachable union 用一个保守 generic bridge 包住；**不是假称旧 disk 前提在 nonzero storage 后仍成立**。不确定时期 anchor 保留为尚未结清的历史责任，生效覆盖明确标记为 bridge。

完整平面速度范数检查不能建立 no-side-slip。当前 `guard_motion:412–427` 只按 `v`、own `v` 的符号及 heading interval 计算 near-field 方向，阈值还忽略 `|v|≤1e-4`；driver WORLD odom `904–907` 实际保存非零 body-y 测量。仅把 `.30` 范数检查留下、继续丢掉 y 并不闭合 generic safety。

保留 translation 的两层候选：

- 空间充分的情形，可用完整二维的 isotropic reachable/backup tube，让原 Nav2 translation 原值通过。若采用旧单机 `.30*(.16+.02)+.30²/(2*.5)=.144m` 停车 reserve，必须先证明它约束**整个平面机体运动**，不只轮 rim 或 forward 分量；full-speed bound 本身不能推出有限停车半径。
- near-field 想保留“远离 peer 的合法平移”，必须对二维速度集合、非零 lateral 分量、heading/TF 不确定度、angular/linear 耦合和未来演化计算 support/nonclosing 条件。瞬时 `v_y` 小不是未来侧滑有界的证明。无该模型时不能沿用 forward-sign 结论，也不能把所有 translation 默默禁止后称可用性已保留。应明确哪些请求有证书、哪些暂拒，并给可行平移的 CPU witness。

无法给出新的完整 bridge 时，保持当前保护下的 zero-line（可仅保留已被同一完整 disk/peer 检查允许的原请求 w）；不发明转向或探索目标。若连 zero backup 也未被覆盖，应失败/保持物理暂停并按已声明清理协议关闭，而非把输出零当安全证明。

## 4. 最小状态机（保护状态与 qualification 计时分离）

| 状态 | 进入及可推进条件 | 不得发生的操作 |
|---|---|---|
| GENERIC_PROTECTED | 当前完整 generic/backup 已闭合；非零或零请求都按完整模型审 | 未证 generic 就靠名称进入 normal；借此丢失残留 lateral velocity |
| ZERO_QUALIFYING | 保持 generic/旧覆盖；另计 publication-zero / storage-zero / applied-zero 历史，保留原 .94/.78/三源必要门 | 仅计时/三样本就宣称未来 disk 连续不变性；warmup 冒充 release 后历史 |
| DISK_ACTIVE | 唯一资格通过；固定 a；给定连续 disk/速度/源间隙/坐标前提成立 | 重复 grant、零输出、零 stop、新 decision seq 造成重锚 |
| HANDOFF_PENDING | **发布前** generic bridge 已覆盖全旧状态集合和 backup；随后 publication/storage/actuation 分层记账 | publication 或 storage 单独清 a；等原 seq 必须被应用；尚无 bridge 却先发非零 |
| GENERIC_PROTECTED（交接完成） | 实际 actuation 消费 handoff 链内某个已绑定 seq；其后严格更晚/有明确 phase 顺序的 causal raw 和整段 bridge 包含关系成立 | 用同 stamp pre-actuation odom充当 post-response；把存储 ACK 改名为应用 ACK |
| STOPPING | 永久 stop，旧/bridge/generic backup 继续覆盖；真实零 publication/storage/actuation/rest 分开 | stop ACK 清 anchor/责任；从停止状态恢复 normal；缺 ACK 补造成功 |
| FAULT/CLOSED | 记录 model/protocol/coverage 具体失败；只允许已覆盖的 stop/有限清理，保留实际 wait 与最终 physics 端点 | 清空状态消除违例、把缺源当静止、用进程 gone 代替此前机体安全 |

`zero_qualification_since` 可以因 nonzero publication 正常失效；native-zero qualification 可以因 nonzero storage 失效。但这两种计时失效均**不能清旧 active anchor**。旧 anchor 退休后也留不可变历史记录；新的 a 只能由完整 generic 接管之后的新零线资格（或真正新 epoch/full rebuild）产生。

微小非零（包括 subnormal）、正负交替、发后被 stop/后继 seq 抢占的 nonzero 都不能直接重锚。不设任意 epsilon 作为清除/重锚通道。若任何幅度的请求确实完成了完整 generic 覆盖与实际接管，再满足全部新资格，重锚可以合法；安全依据是覆盖链，非人为最小位移阈值。

HANDOFF_PENDING 允许在已闭合且未过期的 bridge 下推进有限下一 20ms，并允许已注册后继 seq 携带新 clock/真实 state-peer 依赖与续接证书。它不要求所有 seq 被应用，也不能每次用新观测/seq 丢掉旧可达集合。stop 若在首次 nonzero actuation 前覆盖该链，应取消候选并保留原 anchor；不能获得一次虚构的 generic 接管资格。

## 5. actual evidence 与因果端点

原 target parser `mr3_drive_target.hpp:42–47` 严格只接七字段；原 storage status client 也严格字段集合。不要把 mode/anchor 直接塞入原 tag 或污染当前 schema。CPU 原型可将 mode/anchor/bridge 作为独立 sidecar，绑定 `(epoch,robot,clock,decision_seq,v,w)`、真实 target bytes/hash、依赖 receipts 和模式版本；旧 tuple 原样保留。

实际 applied endpoint 可由现有 native actuation journal（driver `727–736/818–825`，已记录/flush）重建；现阶段该 journal **没有等价的在线 actuation ACK**。未来若由 worker 在暂停处只读该本地 journal，必须先闭合文件/PID/source 身份、连续记录水位、完整行、实际消费 seq、入 guard/worker 的 causal receipt 与超时语义，不能把任意 JSON 文件当 native 应用事实。也可另立只读 native feed，但这是后续版本的具体实现决策，本稿未实现。

未来源到达时先校验并保留 immutable ingress，然后按 `source_ns≤真实已提交 clock/physical watermark` 才推进安全状态与失败归属。当前 tracker `107–109` 注释虽说保留 future，但 `138–149` 已更新路径/可能失败；应将 future 暂存和 causal drain 分开。完整 drain 必须处理所有尚未审计的 causal 样本，不能只挑最新好样本；bounded history 溢出/未知丢样不得静默丢弃。equal-source same-bytes 不重复计数，冲突或回退单独报告。

每次 sample→当前边界→下一量子/backup 的尾部仍是连续模型义务。末份 raw 距离端点≤100ms 只是必要新鲜度，不能把它当端点真实位置/零速。物理切换同 stamp 的 odom 与 actuation 还要按 native phase/record order 区分；没有顺序证明时要求 raw source 严格晚于应用端点。任务终态与 cleanup attribution 分开，但实际 physics 仍在推进时保护责任不能因 terminal notice 结束。最终无新样本不得凭 stop ACK/进程消失填补最后路径。

anchor 坐标不能靠最新 TF 反复搬动：`state_payload:154–166` 将原始 odom 经当次 map→odom TF 组合，guard `323–357` 还允许 TF header 的既有 .2s validity lead。应保存锚定时 TF/odom 的真实 source 与规范化 frame，冻结 lift 或显式扩大其随时间误差；TF validity lead 不是未来信息已可用。若 SLAM/map→odom 可无界跳变，固定 disk 与 generic common-frame pair 证明都不成立，此前提尚未闭合。

## 6. 隔离 CPU 原型应覆盖的反例（本稿未执行）

1. DISK_ACTIVE→nonzero published、storage 缺失：anchor 不变、无 physics permission。
2. seqA stored 后被 seqB/stop 抢占、A 从未 actuation：不死锁、不虚构应用/重锚。
3. 同 clock normal 与永久 stop 交错：真实 stop 身份永久锁存，不可回退为 normal 成功。
4. `nextafter(0,+∞)`、交替 ±tiny v、重复 grants/zeros：无清 anchor 或新 anchor 漏洞。
5. old disk 边界上的 outward residual velocity / lateral-only velocity：三份 rest 样本不自动证明不变性。
6. 当前 `v_x=0,v_y≠0` 朝 peer、或 source 后发生侧滑：forward-sign 放行必须被拒或由完整二维证书覆盖。
7. future raw 先到、clock 后到；future 违例不污染早先 causal 决策，但到达水位后不得跳过。
8. same-source 相同/冲突、乱序、gap、history overflow：完整来源保持或明确失败。
9. 同 stamp pre-actuation odom 与 actuation：不能签发 post-response 交接完成。
10. 三份健康样本之间/末样本之后的 outward excursion：采样 chord/源龄不能冒充连续 disk 证明。
11. TF 更新/跳变与坐标旋转、反向平移及正常合法侧向测量：anchor 不被重投搬移，二维 reach 不漏项。
12. 从整个 `D(a,R)` 而非当前 singleton 初始化 generic；在 source-based 几何中检查 R→2R 差异。
13. far/near 有明确合法 translation witness 与拒绝 witness；状态机不能通过永久只出零“通过”可用性评审。

待 root 综合的硬前提：连续 fixed-disk 不变性；完整二维 generic+backup 的轮→机体/侧滑模型；旧/新覆盖集合包含与 pair 联合不变性；共同坐标及 TF 误差；actual actuation 事实的可信在线/离线边界；source/末量子连续尾部；有条件可行平移及无死锁。以上任何一项未闭合，均只停留 math/CPU，不 seal、不新增 native。
