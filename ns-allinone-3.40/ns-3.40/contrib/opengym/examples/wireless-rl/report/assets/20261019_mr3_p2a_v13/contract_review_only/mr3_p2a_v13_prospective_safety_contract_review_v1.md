# V13 失败后的科学契约设计评审稿

状态：**只建议继续 CPU／数学合同设计。现阶段不申请、不执行新 native，不声称新 schema 已就绪、可训练或安全门通过。** 本稿不修改 Git、原门、旧证据、预算或运行配置。任何后续科学契约变更均需用户另批；实施后还须新冻结、前瞻计划、受影响完整重验和独立预算。原 V13 minimum 的 whole-path FAIL 永久保留。

## 已知事实与不能偷换的含义

`MR3_ENV_CONTRACT.md:91–93` 与 `mr3_motion_safety.py:41–50,99–149` 要求同一连续 zero-linear 段从 activation 前最后完整 own odom 锚到实际非零线速度存入／结束，持续平面速度 ≤0.01m/s，**总中心路径** ≤0.0078m；重复批准不刷新预算。V13 的原始位置弦长已经证伪后者。该 FAIL 不是用净位移、滑窗、半径或过滤细小增量可以修复的测量错误。

现有模型已区分条件假设与证据：过去三条静止样本不推出未来静止，采样弦长是连续总路径的下界；tag 存储 ACK 不证明轮指令当刻施加，更不证明身体停车。本稿延续这一区分。

下列量全部保留其原义：每机完整身体包络半径 r=0.25m，几何余量 g=0.02m，通用身体速度界 V=0.30m/s，角速界 1.2rad/s、未观测角加速界 7rad/s²，源龄门 0.5s，本机 rest 范数界 v_r=0.01m/s，20ms 量子，真实执行反应预算 L=0.16s，耦合余量 ε=0.02s，全局停止包络参数 b=0.5m/s²。b 不是每一时刻真实身体都按该减速度减速的已证定理。

原常数关系为：

\[
H=L+V/b+\varepsilon=0.78\mathrm{s},\quad
R=v_rH=0.0078\mathrm{m},
\]

\[
D_{peer}=V(L+\varepsilon)+V^2/(2b)=0.144\mathrm{m}.
\]

0.94s 的零线速度发布资格 =0.16+0.78，配合独立的真实 target 存储时延／零存储历史检查，为过去 0.78s 的零存储旁证服务，不能当作未来 H 的动力学证明。三条后续 fresh rest 样本及 0.10s source-age/gap 门保持独立。

## 方案 A：有限时域 reach tube 与 receding-horizon 归纳

数学上可以构造，但当前还缺关键模型，不能直接把原累计器改成 0.78s 滑窗。

令 T 为当前暂停的物理／ROS 边界，s_i 为当前已选择的几何来源时间 `min(odom,TF)`，a_i=T−s_i。以实际已交付的共同 frame 中估计位置 \(\hat p_i\) 为中心，原运动源龄不确定量为 \(E_i=Va_i\)。这只覆盖有界运动产生的陈旧性，不覆盖任意 SLAM／map→odom 跳变或共同 frame 注册误差；若后者存在，必须另外给出有效误差界，不能借原 0.02m 几何余量或 0.3×age 无声吸收。

对每个候选最终命令 u_i，需构造覆盖“该命令至少执行到下一决策，再在任何证书缺失时执行备份停车”的真实中心 reach tube \(\mathcal R_i(\theta;u_i)\)。对每对机器人、每个未来 θ，要满足：

\[
\operatorname{dist}(\mathcal R_i(\theta),\mathcal R_j(\theta))
\ge 2r+g.
\]

最保守球界形式为：

\[
\|\hat p_i-\hat p_j\|-E_i-E_j-2r-g
\ge Q_i+Q_j,
\]

其中 Q 必须来自已声明的实际动力学／备份模型，而非过去样本的平均速度或 wheel target。对保留的低速转向候选，只有证明未来完整 H 内的连续范数 ≤v_r，并证明该 H 覆盖下一次判断及真实停车，才有 \(Q_i\le v_rH=R\)；队友仍需原 \(Q_j\le D_{peer}\) 的共同保护／停车义务。原阈值 0.1518m 仅在这些未来条件成立时才可得到。

0.16s 的原文字分解已经包含 20ms gate、请求与执行器等待。新证明必须把“下一决策间隔、stop target 存储、下一次30Hz轮更新、真实身体响应”统一到一条最坏时间线上。若不能证明下一次20ms已被包含，保守 H 应增加到0.80s，低速积分界变为0.008m；不能既增加一个新持有区间又重复使用旧0.78s而少算时间。

安全归纳至少需要以下完整链条：

1. 在 T 发布新命令前，新 tube 包含实际当前状态及 source/frame 不确定集合；不能以未来或未交付队友 raw 刷新集合。
2. T 的既有证书覆盖执行到下一边界及无法续证时的真实备份停车。下一边界若新测量或候选不合格，立即选既有证书中已经覆盖的备份，不能事后才假设一个更强停车界。
3. 新证书合格才拼接新的 tube。证书必须与 epoch、source hashes、决策序号、最终值和真实 tag/storage 水位绑定。旧／新 tube 在实际切换区间重叠，不能仅按发布时刻撤销旧证明。
4. stop 后必须进入一个真实可保持的终端安全集合：精确停止，或有明确空间半径的稳态漂移／保持集合。如果停止后仍可能永久缓慢漂移，有限 H 证明不能推出余下任务安全。

当前三 ACK-before-advance 可保证当前暂停边界三台均已实际存储对应最终目标，且等待时物理不推进。它有助于证书和动作的因果绑定，但不自动给出上述 tube、身体响应或终端集合。`MotionControlPhase` 的永久 stop 通道与 normal ACK 分离是可复用的正确结构，不应让 stop ACK 冒充 normal 资格。暂停仿真也不能被写成真实身体已经停车。

因此，方案 A 的主要新增缺口是未来 low-speed tube、真实停车 tail／终端集合和递归可行性。仅验证每个滑窗内路径小于R，仍允许同一方向小漂移积累数十厘米，不能替代归纳证明。

## 方案 B：固定 anchor 的整段 reach disk

**相对方案 A 更适合先做数学设计，但目前仍是有条件提案。** 它保留整段 immutable anchor、每条原始样本和累计路径诊断，明确把新的条件物理模型改为：

\[
\forall t\in[t_0,\tau_{exit}],\quad
\|p_i^{odom}(t)-A_i^{odom}\|\le R=0.0078\mathrm m,
\quad\|v_{i,xy}(t)\|\le0.01\mathrm{m/s}.
\]

anchor 仍取 activation 前最后完整因果 own odom，frame 固定，绝不按新 TF、新授权、w=0、方向改变或小幅非零内部纠偏重置。累计 path 仍完整单调留存，旧口径超界仍以“旧合同反例”的独立诊断保留；新合同不能把旧 FAIL 改写 PASS。

该假设允许在小 disk 内往返而累计路径大于R。它与原 whole-path 假设不同，需用户明确批准。不能只说“空间半径检查更合理”就自动替换旧门。

### 从当前中心使用 2R 的条件证明

如果当前真实中心 c 和未来真实中心 q 都位于同一个固定 anchor disk，则：

\[
\|q-c\|\le\|q-A\|+\|c-A\|\le2R=0.0156\mathrm m.
\]

等号可以达到：c 位于 anchor 的 −R 一侧，q 位于 +R 一侧。所以沿用原“从当前中心再留R”是不安全的，不能把半径条件直接塞进旧0.1518m计算。

保留原 source-age 扩张、身体包络、几何余量及队友0.144m备份义务，充分条件为：

\[
\underbrace{\|\hat p_i-\hat p_j\|-V(a_i+a_j)-2r-g}_{\text{原body margin}}
\ge2R+D_{peer}=0.1596\mathrm m.
\]

因此 source-age 为零时所需中心距离为0.6796m；两方各0.5s时还必须保留0.30m陈旧运动扩张，即0.9796m。未引入任何机器人数量变化、body 缩小或0.50m任务门放宽。圆盘包含全部转向角时，几何部分无需假设转向方向；角速度／加速及通用身体模型门仍必须原样通过。

该证明只在 peer 的原共同保护／反应／停车义务成立时覆盖后续时间。不能把“peer最多0.144m停车”解释为任意 peer 可以一直朝本机运动但永久总路程只有0.144m。仍需在每次共同保护边界重验并保留上一证书已覆盖的 peer 备份路径／终端集合。固定 own disk 的好处是：即使本机 stop 后继续在 disk 内微动，**自身无需再证明一个有限总路径或完全静止的停车 tail**；但并未消除 peer 的停止模型、源龄和连续物理 disk 假设。

### frame 与交接必须补齐

- 推荐先用当前中心的保守2R，不把历史 anchor 映射进 shared frame 来优化余量。anchor 可永久保存在 own odom frame，disk 检查直接在该 frame 中进行，避免把历史 TF 变化变成重锚机会。
- 即使使用2R，原共同 frame 的估计对实际身体位置仍须有效。若 \(G_i(T)\) 是有效刚性 odom→common 变换，\(\|G_iq-G_ic\|=\|q-c\|\) 才给出2R；任意 SLAM jump、各机器人 map 注册偏差和不同时间变换误差不能由0.3×age证明。新合同须明确保留该外部前提／缺口，而非宣称它已被新 disk 自动解决。
- 若以后使用精确 anchor 几何，必须将 immutable odom anchor 与当前 own 点用同一 TF 映射，记录同一 source/hash；不能固定历史 map anchor 后只移动当前点，也不能读未来／未交付 peer TF。该优化当前不推荐进入首版。
- 50Hz sample 的 disk 内点并不证明采样间连续在 disk 内。若只采用原连续速度条件，最多能用 \(v_r\Delta_{source}\) 外插 sweep；0.10s gap 对应1mm。应明确连续 disk 是条件物理假设、样本只作必要核验，或设计包含该 sweep 的更保守空间 tube；不能隐去插值缺口。
- 第一次激活时 last causal anchor 到实际状态已有 source age，须使初始集合落入该 disk，并维持原0.94s发布／三条rest／真实0.78s零存储的资格链。past资格不推出disk全段成立。
- 从 disk 模式退出到合法 translation 前，必须先证明完整 generic／braking envelope 覆盖当前实际状态、侧向速度、残留转动及未来执行；不能只凭原近区 nonclosing 的前向标量方向检查。现有 directional guard 明示依赖 differential-drive/no-side-slip，瞬时 XY 范数合格并不能证明此假设。
- 旧 disk 必须覆盖旧命令的所有实际作用时刻；新 generic envelope 必须在其前提真实成立的时刻接管，且与 tag/storage/30Hz施加／physics 推进有可审核的重叠。发布非零 v 就清 tracker、或以 stored target 已更新就假设机体立刻切换，都存在缺口。做不到原子且有覆盖的交接则拒绝该 translation，不能造0.000001m/s命令清零。

以上连续 disk、共同 frame 误差、peer 备份及 translation 交接都尚未闭合。故本方案当前没有“准入已完成”结论。

## 不改原 whole-path 门，增加 actuator feedback 是否足够

现有执行器已经用每次真实 wheel-joint rim 测量作为 paired common-fraction 的起点。V13 的 applied wheel-pair mean 全为0，实际 wheel 反馈与身体中心仍有残余运动。这说明再把同一 wheel target 写得更“闭环”并不自动给出中心路径上界。

原门需要的是 \(\int_{t_0}^{\tau_{exit}}\|v_{xy}(t)\|dt\le R\)，属于 L1／总变差约束。通常 PI／PID 的有界误差或“平均速度接近0”只给出 \(\|v\|\le\epsilon\)，则 T 时间的最坏路径仍为 \(\epsilon T\)。即使没有任何瞬态开销，在300s整段内也需 \(\epsilon\le R/300=0.000026\mathrm{m/s}\)；当前闭合数据的平均路径速度约0.000666m/s，不能据此声称满足。

若能证明 \(\|v(t)\|\le Ke^{-\alpha t}\|e_0\|+d\)，总路径上界为 \(K\|e_0\|/\alpha+dT\)。要获得任意长段固定R，必须消除持续 d 或证明其可积；只靠稳定性、零均值、位置误差有界或轮缘加速参考界都不够。差速执行器也不能对任意侧向接触扰动独立施加横向控制。当前缺少足以证明这些性质的真实接触／有限力矩／侧滑模型。

增加基于 own local odom 的身体速度反馈可以成为工程候选，但须声明它是否使原 zero-linear target 下出现非零 wheel-pair mean；若是，就改变当前 paired drive 合同，需新来源／新冻结及完整受影响重验，不能借 top-level v=0 隐藏新的低层控制。不能借直接强制模型速度／位姿、读取新增真值控制、替换探索目标或制造微小非零 final v 来过门。

有限时长转向后 w=0，也未自动满足原门：原 tracker 的段由 linear=0 定义，w=0不结束它；长时间微小抖动仍可能耗尽总路径。只有可证明的有限总物理运动、真正进入可积误差的rest，或合法translation实际接管才可能保留原门。现有证据不足以给出一个已经可证明、可直接实施的 actuator-feedback 修复。

## 建议的下一步与准入清单

当前明确下一步为：**独立 CPU／math v2 合同原型设计**，候选是固定-anchor disk 的 R=0.0078m 与 2R+0.144=0.1596m保守余量；它是未封版设计，不是新生产schema。优先闭合坐标误差、translation真实storage交接及conditional plant边界，并与有限 tube、维持旧L1门的实际feedback两条备选比较。提交一份明确列出旧／新模型差异的科学合同评审，不先写“schema ready”或申请新 native。关键准入未闭合，不得seal新runtime或启动native。

合同草案须先闭合：

1. 连续物理假设、观测点／frame、来源误差、采样间 sweep 与支持命令集；明确哪些只获必要采样证据。
2. pair reach 集和 backup／终端集合的归纳证明；三机每一对、所有源龄端点和 body 旋转包络均覆盖，peer 信息仍 received-only。
3. activation、永久 anchor、历史完整性、重复授权、停止、source gap、TF变化及合法translation的精确状态机；以实际 storage／actuation／physics 水位证明交接覆盖。
4. 独立 reader 的 provenance 和负例：保留本次 whole-path FAIL；disk 两侧2R尖锐反例；age 0.5s/+1ns；三 ACK 缺失／错误／迟到；frame change／TF jump；瞬时范数与采样弦速度超界；反复转向、零w、非零纠偏均不得重锚；非零translation不得跳过完整接管证明。
5. 用户另批科学合同后才考虑实现；新冻结完整受影响工程矩阵、最小训练链及后续pilot准入不得继承当前38角色或旧模型信用。native应有新前瞻预算／no-retry安排，不能挪用剩余pilot或以批准P2A概括代替预算扩额。

本稿只支持“数学上有条件可构造；当前关键前提不足，先做合同设计”的结论。

来源：`MR3_ENV_CONTRACT.md:64–135`；`mr3_motion_safety.py:20–50,99–235,325–469`；`motion_safety.py:148–162,323–367`；`mr3_motion_control.py:116–253`；`test_paired_wheel_slew.cpp:137–159`（明确仅ideal no-slip wheel-command模型）；`test_settled_turn.py:190–207`（原反向返回仍累计超界的回归）。精确源SHA与原始最低链数据见前一份只读测量合同JSON，不重新执行实验。
