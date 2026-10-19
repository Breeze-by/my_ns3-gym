# MR3-P2A：V14 条件安全契约候选

本文件是用户批准重设计方向后的可验收设计，不是当前生产合同、runtime seal、原生资格或训练结果。现行 [环境合同](../../../MR3_ENV_CONTRACT.md) 和 V13 原始 FAIL 保持。隔离 CPU 核没有 ROS、Gazebo、GPU、文件日志控制入口或 native permission；当前生产代码不导入它们。

## 科学语义的改变

现行连续零线速度段的累计中心路径上限 R=.0078m，已被真实低速往返证伪。候选改为同一物理中心、不可刷新 anchor 的空间 disk，并显式增加普通运动的二维残差、停车终端集合和真实执行交接。它不是原门的数值修复；只有另行验收候选、实现新版本并重新资格后才可启用。所有旧累计路径及 FAIL 永久保留。

仍为三机器人、95%/300秒任务、每机半径 .25m、几何余量 .02m、源龄最多 .5s、命令 .20m/s 和 .8rad/s、实际平面速度 .30m/s、实际角速 1.2rad/s、角加速 7rad/s²。原完整机体停车路径 D=.144m、从当前边界起停车时间 H=.78s、反应 L=.16s 独立保留。不得把 D 偷换为仅纵向路径。guard 只放行原 Nav2 请求、经证明的零线原角请求或全零，不产生探索目标、转向或替代路线。

## 有明确外部前提的 reach 模型

R=.01H=.0078m。以下是真实连续机体的候选条件模型；过去的采样、PID稳定或 CPU 测试不证明这些前提未来成立。

| 模式 | 连续条件与从当前中心看的未来集合 |
| --- | --- |
| D：固定 disk | 同一模式内，真实中心始终在固定 B(A,R)，真实平面速度≤.01。当前点与未来点可在盘的两侧，故未来位移必须用 2R，不能用 R。 |
| N：正常及全零备份 | 当前 T 不续证则至迟下一20ms提交全零。全部旧/新target及执行相位包含在从 T 起的 D/H 停车模型内。有限 H 内纵向积分长度≤D，二维残差范数≤.01，停车后保持固定 terminal disk R；reach 为纵向 sector ⊕ B(2R)。 |
| X：D→N桥 | 发布前已承诺完整 bridge。实际应用前旧 disk 可相对当前点移动2R，再加 N 的残差R和terminal R，故为纵向 sector ⊕ B(4R)。H始终从 T 起，不从应用时刻重启。 |

N 的 admitted longitudinal sign 集 S 必须在命令前固定。实际 body vx 的符号属于 S 时令 ν=vx，否则 ν=0；残差为 `(vx−ν,vy)`。停止目标 v=0 仍继承旧 S，不能把尚在制动的 vx 当作已停止，也不能只检查 vy 而漏掉反向 vx。真实正交 body basis 下有 `p(t)−p(T)=∫νh(θ)dt+∫Rot(θ)r_b dt`；第二项在有限 H 内≤R。terminal 之后允许盘内往返，不要求无限时间总变差有限。

terminal 的数学 anchor 是实际确定时刻 τ 的 p(τ)，τ≤T+H；原生实现必须预声明 τ 的选择规则、真实因果来源和固定点，不能回看整回合挑最有利点。若可观测 anchor 与 p(τ)不同，必须显式计入来源间隙 reach，不能塞进 R。NORMAL→新 D 必须独立证明新固定 anchor 的连续 disk 条件，不能仅因它落在旧 terminal disk 内便推导出同半径的新 disk。

初始化使用显式 initial HOLD terminal 条件：release 后只允许全零，原 .94s 连续零线发布、.78s 连续真实零存储、三份100ms内rest源重新从 release 计。D 未取得完整资格前不得旋转。HOLD 的连续物理集合须由新 profile 校准和独立原生必要门支持；三份rest、storage ACK及warmup不能独自证明它。该外部物理假设不能由状态机凭空创建。

## 三对几何充分条件

对每一对、每一帧分别计算：`d = p_j_source − p_i_source`，`U=.30*(age_i+age_j)`。保留原较旧 odom/TF 源龄，两个 age 均为整数纳秒的闭区间 [0,.5s]。每端 q 为 D/N 的2R或 X 的4R。

每个可能 signed-heading cone 都须对 toward-peer 向量满足 `sup direction·d ≤ −U`，才能省略该端的纵向 D；union 中只通过一个 sign 不足。未证明方向时完整保留 D。充分门为：

`|d| ≥ .50 + .02 + U + q_i + q_j + Σ(方向未证明端的 D)`。

证明：省略的纵向增量对包含源不确定性的初始真实相对向量不接近，故其合成不能减小初始距离；其余纵向与全部残差/终端/bridge用三角不等式扣除。三对均成立且每次新证书覆盖真实切换集合，则下一20ms受保护；拒绝续证时上一完整备份覆盖到固定 terminal，不存在依赖后来测量补证的空窗。

map 与 raw WORLD 两套证书分别使用各自距离、bearing、heading cone，最后 AND。raw 证书提供物理共同坐标条件，map 只增加拒绝。方向情形不能混成 `min(distance)` 搭配另一帧的方向折扣。例如 map=.60m且远离、raw=.90m且接近可以各用自己的完整界验算；raw 也只有 .60m 时必须拒绝。SLAM跳变不包含在 `.30*age` 或 .02m 余量里。

新完整余量（不含 .52+U）为 D/D .0312；D/N .0312或 .1752；N/N .0312或 .3192；D/X .0468或 .1908；N/X .0468或 .3348；X/X .0624或 .3504。第二个数为缺方向证明时保留所有纵向项。历史 .1596 是单 disk 加有限停车的比较值，遗漏新增 terminal tail，不能当完整新合同。

纯各向同性 N/N 要求 fresh 中心距 .8392m，会拒绝约 .6364m 的初始近队形。独立 CPU fixture 给出原队形 tb1 西南/tb2 西北 heading 的可行方向 tube，tb3 初始宽 cone 向东仍拒绝。它只证明存在合法原 Nav2 请求，不让 guard 选择这些方向，不证明 RL 会学到或达到95%。首版 cone 使用全局 `1.2*(older_geometry_age+H)`，覆盖旧角速和整个 bridge；实际来源的 heading 校准角误差须另加，不能从 H 中扣除。当前可行性 fixture 明确以零校准角误差为条件。不得以新请求 w=0 推断旧转动消失。

## 坐标与数值前提

只使用本机 causal odom 和**同一实际已交付 peer state envelope**内的完整 raw odometry；不新增 peer raw 订阅，不让 actor/candidate/mask/Nav2读取真值，不引入 `/model_states` 或spawn坐标校正。当前 WORLD producer 的原始 pose 是 Model::WorldPose，没有每机初始原点扣除。共同 Gazebo实例/epoch、source/ELF/SDF、frame和中心点需显式绑定；相同字符串 `odom` 不是校准证明。此条件不推广到有漂移的编码器或硬件里程计。

现 producer 以 float yaw、cosf/sinf 转换 body twist，c²+s² 不精确等于1。普通 `.01` body norm 不能直接当严格 WORLD norm。隔离 [metric核](cpu/calibration_metric_v1.py) 接收未来真实同源 metadata 的实际 c/s，在明确 IEEE64 RN 条件下给每分量舍入区间，再用 `A Aᵀ=(c²+s²)I` 的物理 metric 检查残差；不发明 epsilon，不从另一次 sin/cos 重算猜原系数。实际物理 heading 与此归一化 basis 的误差仍须进入 cone 校准。CPU helper 不证明 metadata 已存在、编译器满足数值前提或连续物理界成立。

连续 disk 是明确 plant 假设；50Hz点都在盘内只是必要条件。若后续不用连续 disk 假设而改靠速度插值，必须将最多 `.01*source_gap`（100ms时1mm）的 sweep另加进 reach。不能把采样 chord 当连续总路径上界；有限H的残差、完整D/H、末源到最后physics/cleanup的尾部也须独立审计。

## 实际模式交付和执行交接

1. 保存原七字段 `mr3-drive-target-v1`，mode/anchor/reach放独立版本化 sidecar，绑定 epoch、robot、clock、decision seq、实际 target bytes/hash 和 source/phase identities。
2. D→N 首版在 T 先发布真实全零与不可变 X intent；Information 的真实订阅回收后，下一 state envelope 才能携带该 intent。现 state→peer→motion 屏障在实际 peer phase 消费同一冻结 bundle 后，才允许非零。worker知道intent或三台storage ACK不代表peer guard已收到模式。
3. 当前三逻辑 guard 共享理想 bundle，不是三条网络ACK，亦无P3/字节隔离信用；后续网络阶段必须传实际模式字节。
4. 发布及storage仅进入 pending。30Hz执行器会跳过被后继覆盖的50Hz目标，允许同一handoff的合法后继seq。旧anchor保留，直到某个真实实际消费target身份的 actuation receipt及严格更晚 causal raw均绑定，才可X→N。相同stamp odom在OnUpdate内先于wheel应用，不能作post-response。
5. 选择新增本机 typed actuation receipt：只在原OnUpdate实际wheel写入后发布既有消费身份与时序，不从审计JSON文件读取在线控制事实，不把stored回执改名为applied。须有完整连续序号、≤34ms间隙和物理末水位。暂停等回执不推进仿真；下一20ms再加最迟34ms应用，共54ms<L，但完整D/H仍须从当前T统一成立。
6. future raw/actuation保留不可变 ingress，按真实physics及两个已证明完整水位排序drain，同stamp先raw后actuation。首坏源、后续tail和累计path诊断全保留；FAULT吸收，不得继续提升安全水位。原始归属必须有typed epoch/robot，opaque hash不是归属证明。
7. 普通NORMAL→全零可在旧完整backup保护下重新资格；永久stop不可恢复。微小非零、重复grant、零w、storage覆盖或stop不清anchor、不造成自动重锚。新anchor只在完整实际接管及全新资格后产生，历史anchor不可变。

## 原生准入和后续边界

隔离 CPU 只验证数学蕴含和协议状态转换；所有输出 `native_admission=false`。新物理假设、连续尾部、实际source/receipt/metadata接线仍需生产实现与新冻结原生反例检查。旧38科学角色不能继承到新合同，旧 FAIL不能以新 reader重判PASS。

后续实现范围已具体化：版本化 scientific profile、真实 mode/intent subscriber 与同envelope交付、typed native applied receipt、velocity metric/calibration、完整独立新reader及原门并列保存。观测维数、候选/掩码/策略/reward不因安全metadata变化。实现与CPU/编译检查完成后再封实际source/ELF、完整受影响四阶段资格和最小训练链。

本轮无新增 native/GPU，工程仍已用31596.4775930946018/34000、余2403.5224069053982；pilot1870决策/2905.9547395464029墙秒与三场final-only额度不动。这里不申请或创建新运行配额。只有获验收的新合同及明确后续原生预算，才可能进入新原生资格；P2A、pilot/final模型和95%验证仍未完成。
