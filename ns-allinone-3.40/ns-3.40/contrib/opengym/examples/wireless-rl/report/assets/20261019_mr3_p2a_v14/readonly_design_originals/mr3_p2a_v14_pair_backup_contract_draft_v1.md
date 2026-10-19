# MR3 V14 pair reach／backup 数学合同独立草稿 v1

**范围：用户已批准安全契约重设计及数学／CPU工作。本稿未修改生产门，未运行 native、GPU 或正式科学 reader，没有新增 native 预算。以下为有明确外部 plant 前提的候选数学合同；不是新 runtime seal、可训练声明或物理 PASS。** 原 V13 whole-path FAIL 不改记。所附独立 CPU 验证设计尚未运行，不含测试结果。

## 1. 目标与最小改变

原不间断 zero-linear 总路径≤R=0.0078m 已被真实低速往返证伪。候选改为固定 anchor 的空间 disk，并为正常运动增加有界残差的有限纵向 sector 与固定 terminal disk。body 仍为每机半径0.25m，保留0.02m余量、0.50m身体任务门、95%/300s、三机、received-only、原速度／角速度／角加速度／停止门。最终门仍只保留 Nav2 原请求、经证明的零线原角请求或全零；不选探索目标、方向或替代路线。

单独将 raw `vy` 限到0.01、把每次target的v=0当身体静止、或只做2R三角不等式，都不构成完整方案。

## 2. 固定常数与条件模型

V=0.30m/s，命令线/角上界0.20/0.8，实际角速界W=1.2rad/s，实际转向加速界7rad/s²；H=0.78s，L=0.16s，D=0.144m，R=0.0078m。D及H保留原**实际完整身体平面停止路径／时间**硬门，不能改名为“理想纵向距离”后容许真实身体走得更远。

物理 point 必须是现有 own odom 中的同一 base_footprint／model-origin 平面中心。新物理证明优先使用已存在、已实际交付的 raw WORLD odom，既不新增 `/model_states` 真值输入，也不读未交付的 peer raw。共同 WORLD provider、同Gazebo实例／epoch、frame、point、source clock 和 payload provenance 须由新合同明确校准。保留所有原 map 门；map与raw分别验算，raw bearing／heading也必须单独证明，不能只用 `min(d_map,d_raw)` 后继续依赖可能跳变的map方向。

令T为暂停决策边界，\(\hat p_i\)为已交付raw源位置，a_i为其保守几何源龄。可继续使用原较旧的 `min(odom,TF)` age，虽对raw WORLD更保守。\(U=V(a_i+a_j)\)；各age均须在[0,0.5s]。若原共同frame不能由WORLD provenance校准，必须另有误差界；0.3×age不覆盖SLAM跳变。

以下 plant 前提尚无普遍物理证明，CPU只能验证“若其成立则几何安全”的蕴含；未来native原件只能提供必要采样和具体反例门，不能升级成无条件动力学定理。

### D：固定 anchor disk

在整个已声明zero-linear物理模式内，immutable odom anchor A不重置，真实中心持续在B(A,R)，且真实平面速度≤0.01m/s。旧累计path、每个source及历史anchor永久保留；旧path反例独立记录。当前真实中心与未来中心均在同盘，故从当前真实位置看的reach buffer为

\[
q_D=2R=0.0156m.
\]

disk资格仍需原发布／三rest／真实存储历史，不能由单条v=0、一个mode字段或storage ACK推断。

### N：有界残差的正常命令及全零备份

每个允许的正常候选必须带一个已提前声明的备份：至迟下一20ms边界不续证就全零。备份从当前T起的**实际完整身体**停止路径≤D，terminal进入时刻τ≤T+H。所有尚可能作用的旧／新target及真实执行器延迟均须包含。

在T到τ之间，以实际身体heading θ(t)定义纵向分解。固定本证书允许的signed longitudinal集合S，令ν(t)等于符号属于S的真实body-forward速度vx(t)，否则ν(t)=0；残差body向量为

\[
r_b(t)=(v_x(t)-\nu(t),\ v_y(t)).
\]

于是物理中心位移恰好为

\[
p(t)-p(T)=\underbrace{\int_T^t\nu(s)h(\theta(s))ds}_{\eta(t)}
+\underbrace{\int_T^tRot(\theta(s))r_b(s)ds}_{e(t)}.
\]

条件要求连续\(\|r_b\|\le0.01m/s\)，所以有限H内\(\|e\|\le0.01H=R\)。它同时覆盖侧滑与不属admitted sign的反向纵向运动；**只查|vy|不足，纵向反转、overshoot不能消失。** ν的符号集合必须在动作前承诺，不可事后跟随样本符号调整以拟合过门。

停止过程中目标v=0不令ν立刻归零。backup继承上一正常运动的S，允许真实尚在制动的forward速度继续形成η；仅在真实terminal接管时才结束有限纵向段。已关闭数据中zero-target仍有约0.16m/s身体瞬态，因此不能把这些样本套disk rest门后称为异常噪声。

由于原实际停止总路径≤D，纵向分量弧长\(\int|\nu|\le D\)也成立。它形成signed heading sector的积分reach集合

\[
\mathcal L_i=\{\int\nu h(\theta)dt:\ \theta\in\Theta_i,
\operatorname{sign}\nu\in S_i,\ \int|\nu|dt\le D\}.
\]

该集合应理解为各允许射线的有界积分／凸包，不是仅检查两个endpoint的位置。

τ之后保持全零时，真实中心永久位于固定terminal anchor B(p(τ),R)。terminal anchor的确定必须是预声明的实际causal源／物理水位，不能回看全episode挑最有利一点；三rest样本只能验证必要条件，不能推出永久disk。若anchor不是p(τ)同点，必须再加其实际来源间隙reach，不能塞进R。

故包含有限残差与terminal tail的完整备份reach为

\[
\mathcal K_N=\mathcal L_i\oplus B(R)\oplus B(R)
=\mathcal L_i\oplus B(q_N),\qquad q_N=2R.
\]

这避免不现实的无限总变差要求：残差L1只在有限H内约束，之后允许terminal disk内的持续小幅往返；但仍要求一个明确、可被native反例证伪的有界空间plant模型。

### X：disk→normal handoff

在实际非零轮指令可能作用前，旧disk可相对当前中心移动2R；其后新N备份再有有限残差R和terminal R。首版保守桥为

\[
\mathcal K_X=\mathcal L_i\oplus B(4R),\qquad q_X=4R=0.0312m.
\]

这只是充分上界；它必须与真实handoff状态机证明绑定。发布只进入HANDOFF_PENDING，旧anchor不清、不重锚，所有可能old/new target组合均被桥覆盖。某个实际30Hz actuation事件及严格更晚causal raw watermark匹配后才可结束pending，不能每个50Hz target都等“同seq实际施加”（有些seq会被后继抢占）。缺失actuation证据不产生新锚或资格。

T的当前target在暂停时已由三台真实storage ACK绑定。若T+20ms不续证，下一次轮更新最迟再34ms（1ms tick下30Hz）选择全零，即≤T+54ms<L。**H必须始终从当前T起覆盖整个old/new/backup组合，不从实际actuation重新启动H。** 若该统一globalstop模型不成立，就没有这份桥证书，不能靠加一个空间4R假装解决时间。

首版方向cone可直接保守使用\(W(a_{geometry}+H)\)，W=1.2，覆盖整个桥中的旧转动，继续保留原7rad/s²硬审计。若未来想换成更窄的source-w/request-w/7a模型，需另证真实角响应；新request w=0不证明旧w已消失。

## 3. 对每对机器人完整的几何充分条件

令d=\(\hat p_j-\hat p_i\)。对每个signed cone，要求它对toward-peer方向非接近；可保留原更严的源不确定性条件

\[
\sup_{\theta\in\Theta_i,\sigma\in S_i}\sigma h(\theta)\cdot d\le-U,
\]

j同理对−d。D模式没有纵向分量，不需要凭空给零射线施加−U条件。一个union中每个可能sign／heading都要通过，不能只检查当前请求的单个正向。

满足此条件时，名义纵向增量相对任何初始真实relative vector均不接近。对不满足或未证明方向的端点，保守保留其完整D各向同性纵向reach。由投影及triangle inequality得到充分门：

\[
\|d\|\ge2r+g+U+q_i+q_j+
\sum_{k\in\{i,j\}:\text{方向未证}}D_k.
\]

所有body／source／unsupported／任务门仍独立成立。map与raw各自的bearing、cone、距离独立验算；raw必要条件不因map刚好通过而省略。

mode组合的候选余量（未加body0.50／几何0.02／source U）：

| pair | 两端纵向皆已证非接近时 | 双方均无方向证明的保守值 |
| --- | ---: | ---: |
| D / D | 4R = .0312 | .0312（均无纵向） |
| D / N | 4R = .0312 | D+4R = .1752 |
| N / N | 4R = .0312 | 2D+4R = .3192 |
| D / X | 6R = .0468 | D+6R = .1908 |
| N / X | 6R = .0468 | 2D+6R = .3348 |
| X / X | 8R = .0624 | 2D+8R = .3504 |

原提议的.1596=2R+.144是“单disk+仅有限D停车、不另含terminal tail”的正确有限窗口余量，**不能当成新增N terminal模型的完整全任务证书**。继续保留该数作为旧方案的保守比较不代表它足够接入terminal；本稿按Minkowski和明算，没有少算tail。更紧的actual-stop球界D+R_terminal可作为以后优化，但首版先不优化。

## 4. 共同guard、backup和terminal归纳

每个有效commit必须同时具备：源／坐标／完整性证据、per-robot模式及其实际交付承诺、覆盖当前真实状态不确定集合的reach证书、全部三对的几何充分门、共同全零备份义务和target/storage绑定。不能从peer raw v=0推出disk mode，也不能把worker知道的三storage ACK当成local gate已收到peer模式信息；当前received states没有mode字段，因此未来信息合同必须显式扩展并保留真实交付记录。

设T_k证书成立。当前最终命令最多执行一个20ms量子；下一边界：

1. 新证书完整通过，且其初始集合包含实际可能状态，才原子接管并保持旧／新handoff覆盖。
2. 新证书不完整或拒绝，则执行T_k已覆盖的共同全零备份。每个端点的名义纵向段到≤T_k+H停止，有限残差与terminal disk均在旧reach内。因此上一证书覆盖停止之后的全部余下时间，不要求凭新测量拼凑一个未承诺的停车模型。
3. 若实际发生plant／source／身份违例，则原件明确hard FAIL、禁止数据进入learner；物理暂停／进程关闭是实验处置，不是证明这些物理前提仍成立。

新命令改变未来轨迹并不要求旧证书继续覆盖所有新轨迹；要求在真实切换前，新证书已经覆盖实际初始集合及切换区间。尚未闭合的handoff不允许被微小非零v或publishing event跳过。每次mode和所有后继pending target均需先建立bridge，不能先动作后解释。

本归纳只覆盖受声明plant模型控制的三个机器人、已校准同WORLD odom、当前理想通信和受控20ms执行。它不自动提供未来gateway／丢包／真实硬件信用，也不证明95%任务可达或policy学习有效。

## 5. 近队形不是纯各向同性deadlock

纯isotropic N/N需要中心距至少.8392m（fresh），会拒绝当前最近约.6364m出生距，因此不能把这个“总拒绝也安全”的核包装成可训练。

方向tube可以存在合法translation：tb1与其两个peer的bearing相差45°，非接近方向楔宽135°。在D模式原地转向使自身heading约向西南后，global W×(.02+.78)=.96rad的双边cone宽约110°，可严格包含在该135°楔内；其D→X扰动对最近D peer为6R=.0468，加0.52和0.012源扩张仍小于.6364。tb2有对称的西北可行cone。tb3初始正东在该宽cone下可能被拒绝；这正是需要保留的真实约束。

这只是控制可行性的数学存在性fixture，guard不生成或推荐这些heading／探索目标。实际方向仍必须来自原Nav2请求，未来RL是否产生可行子目标、能否完成95%，仍未测试。

## 6. 可观测necessary审计与明确外部前提

必要原件应记录：predeclared mode与signed cone、完整raw body XY／angular向量、源／frame、实际已交付peer mode/state、每个残差分解ν/r、所有raw相邻chord、finite stop身份／窗口／全body path、固定terminal／D anchor及每条anchor距离、所有历史累计path、真实tag/storage/actuation/physics水位。不得过滤峰值或在模式切换时删除样本。

0.01残差norm需检查反向vx与vy合成，而不只vy；target0的制动期仍使用前一signed longitudinal模型。raw twist和chord各自是必要证据，积分的采样近似不是连续界的定理。0.10s source gap内若仅依赖连续0.01界，最多仍有1mm插值sweep；若不采用连续disk假设，必须把该sweep显式加进空间tube，不能暗藏。

需要先写明而不能从CPU推导的外部条件：真实norm及角cone；从T起≤H／≤D的完整备份响应；整个有限H连续残差norm≤0.01（含反向/overshoot）；stop后固定terminal disk；zero-linear转向固定disk；raw WORLD坐标及point校准；三台共同备份执行／模式交付；handoff所有old/new命令与物理水位覆盖。任一不可支持则候选合同不准入，不能用PID稳定、wheel target、平均值或原38角色替代。

## 7. 纯CPU验证设计（尚未执行）

独立设计脚本 `/tmp/mr3_p2a_v14_pair_safety_cpu_design_v1.py` 仅导入隔离的 `reach_geometry_v1.py`，无ROS、native、GPU、实验日志reader。它应以synthetic exact-Fraction fixtures验证：

- binary64保持exact、bool／nonfinite／future／stale拒绝；exact阈值与少1个有理增量的拒绝。
- D/N/X的2R/2R/4R buffer及上述Minkowski和；.1596遗漏terminal反例。
- nonclosing support对完整signed-cone union；raw bearing与map bearing相反时不能凭距离cap通过。
- 近队形西南／西北X与D的几何存在性，及tb3宽cone正东应拒绝；验证不是全拒绝核。
- 缺calibration／legacy-hard gate始终拒绝；任何accepted均 `mathematical_geometry_only=true,native_admission=false`。
- 残差合成：wrong-sign vx不能消失，v=0 backup的forward制动不能被误当disk；R=.01×H与独立terminal R的和不能被省略。

这些测试即使全部通过，也只验证代码实现了给定集合的几何蕴含。没有模式交付、连续plant、handoff和新冻结准入证据，不得写“新schema ready”“可以启动训练”。
