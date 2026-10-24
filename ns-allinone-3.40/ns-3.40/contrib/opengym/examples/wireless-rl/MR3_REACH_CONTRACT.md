# MR3 reach 安全执行契约 v1

2026-10-19 用户“批准”接受[V14科学候选](report/assets/20261019_mr3_p2a_v14/scientific_contract_candidate_v1.md)
（SHA256 `b1443df121a5ba1af0ff8c55417294bd8fd246fc85463776e1ce022c1752a043`）并授权生产实现。
本文件定义显式 `mr3-reach-v1` profile；默认 `legacy` 保持原 schema/规则。
新 profile 的 CPU/编译准备不提供新冻结原生资格、连续安全、训练或95%任务信用。
当前接线工作见[V44](report/20261022_mr3_p2a_v44_support_native.md)，实际原生资格尚待新冻结验证；所有旧FAIL按原合同保留。

## 条件物理模型与完整余量

固定三台 tb1/tb2/tb3，95%/300s、全机体接触监测、ROI、参与和终态门不变。
每个当前决策时刻 T 的完整机体停车假设为：身体平面速度 ≤.30m/s、角速度 ≤1.2rad/s、
角加速度 ≤7rad/s²，完整停车路径 D=.144m、终端时间 H=.78s，反应时间预算 L=.16s。
命令上界 .20m/s、.8rad/s；几何/模式来源年龄 ≤.5s。标量源样本满足必要条件不能证明连续界。
54ms 的下一20ms边界加最多34ms轮更新，只是 L 的时序必要项，不能代替身体 D/H。

每台模式是一个带固定锚及预声明符号集合 S 的承诺：

| 模式 | 身体必要条件和未来 reach |
| --- | --- |
| HOLD | release 后全零命令，固定release anchor，中心始终在半径 R=.0078m disk，平面速度≤.01m/s；从当前中心看须用2R |
| D | 同一固定 anchor disk R、平面速度≤.01；从当前中心看2R，允许独立审查后的原请求原地转向 |
| X | D→N桥；S 在非零前宣告，覆盖旧 disk 2R及新残差/终端2R，总 buffer 4R，另加有向停车 sector |
| N | S 内的纵向速度 ν，其余二维速度残差在有限全局 H 内范数≤.01；完整身体停车路径仍≤D，τ≤T+H后固定terminal disk R；reach 为有向 sector D 加2R |
| STOP | 永久停止并继承前一模式的 anchor、S、停车/终端责任；不可再次资格或恢复运动 |

D 的完整双帧2R证书通过但拟议X的4R余量不足时，可仅将原请求线速度归零、保留其原角速度；必须保持已交付D、原锚和S为空，不宣告X，也不选择新heading。

S 不允许的纵向速度也计入残差。零命令不是 disk 证明；制动和转向期间继承 N/X 责任。
命令未实际消费、微小非零请求、重复发放资格、同戳 raw、存储ACK都不能重新锚定。
正常 N 只有真正执行过 N 交接、完整全零资格及新的固定锚承诺后才可进入新 D。
旧 X 若未实际线运动，可在更新的全零目标确实应用且有严格更晚 raw 后取消；仍用原 D anchor。

每一对、每个坐标系分别检查距离至少 `.50+.02+U+q_i+q_j+ΣD`，
U=.30乘两端较老几何源龄之和，q 为上述2R/4R。
只有该端所有符号 cone 的支持函数均≤−U，才能省去该端完整 D；否则保留。
cone 半角使用全局 `1.2*(source_age+H)`，不能以旧测得零角速度忽略将来的转动。
map 与同一已交付状态的原始 common-WORLD odom 各自形成完整证书，最后 AND；不跨帧混距离和方向。
共同坐标/真实heading校准及其误差界仍是明确的传感器/物理假设，不能从 metadata 声称已验证。

## 显式几何证书版本（V44）

`reach_geometry_rule`与上述安全profile正交。缺省`binary-cone-v1`逐字保留原
`mr3_reach_geometry.py`及上一节的整D判据；显式`cone-support-v2`只在
`mr3-reach-v1`下有效。未知值或链中选择不一致必须拒绝。新规则沿
plan→benchmark/PPO→Supervisor→reset worker→launch→motion_safety/ReachTracker
传递；episode、监督器、实际motion configuration、资格和三阶段policy必须同值。
旧缺省记录省略新增字段；新plan必须逐跳显式选择，不能用缺字段借新规则信用。

v2仍使用完全相同的Reach集合、源龄U、D/H/R、heading cone、2R/4R、双frame、
intent承诺和硬门，仅用固定报告分离线的support上界代替每端二值保留整D。
在每个frame取δ=右中心−左中心，d=|δ|>0，n=δ/d；每个origin-containing
sector的纵向支持上界为h，多个允许符号/heading形成union，故取max。
若 `d²≥(.50+.02+U+q_left+q_right+h_left(n)+h_right(−n))²`，
则在所声明Reach集合和原物理/来源前提下足以分离。raw和map独立计算后AND。
这是充分条件，不声称所有安全情况都能放行，也不单靠公式证明真实plant满足Reach。

每个axis a仅在dot(a,δ)<0且cone可严格证明acute时使用投影上界
`H=dot*cos_lower+abs(cross)*sin_upper`；保守比值
`clamp((H+U*|a|_upper)/(|a|_lower*d_lower),0,1)`乘该Reach的实际L。
分子≤0先取0，旧robust nonclosing成立则保留其精确0；其他情况保留完整L。
外层U保持完整，额外方向项也保留在比值内，不能错写成无量纲项直接加米。
根号通过96bit dyadic的整数isqrt给出有理上下界，零/不正lower不能作分母；
没有libm/epsilon准入。生产proof保留历史调用键`geometric_necessary`作为许可bool，
新schema明确其含义为这个充分证书，保留逐端/逐frame结论、日志用向外有理区间及完整精确frame的canonical SHA。日志区间仅压缩记录，不参与准入；独立reader从完整交付输入和冻结源重新计算，不能把生产summary当oracle。

[禁用原型及独立推导](report/20261022_mr3_p2a_v43_support_geometry.md)只提供人工
条件数学检查；生产新源仍必须在新freeze完成完整原生角色、独立重放、物理/接触和
训练/最终95%验收，不能替旧FAIL改判。actor、候选、种子、reward和intent wire不变。

## 来源cadence配置

V19显式reach研究配置`mr3-reach-lidar-20hz-v1`只将生成SDF内`hls_lfcd_lds`真实采样率由5Hz改为20Hz；base/legacy仍5Hz，360 beam、噪声与碰撞/驱动参数保持。扫描和TF保留真实来源时间，不重戳、不减年龄U或放松双帧证书。更高cadence改变SLAM/地图与actor观测分布，须单独冻结并完整重验，不复用旧资格。20Hz只声明该仿真配置，不声称实体传感器可达。配置20Hz不证明持续实际到达或连续物理界；原每次来源、几何及关闭门仍必要。

## 实际交付和应用链

launch 仅在 adapter、stepped、三台时接受 `mr3_safety_contract:=mr3-reach-v1`。
Supervisor/worker/node 明确记录 profile；state/peer/motion 相位使用 v2，legacy v1 严格拒绝新字段。
每轮先冻结同一三机 received bundle，再完成全部三台准入，之后才发布目标。
任一机器人出现模型矛盾，三台该轮均输出全零，并进入永久停止；故障不能递归产生半轮输出。

真实 topic：

- `/{robot}/mr3/safety_intent`：唯一 motion_safety 发布 `mr3-safety-intent-v1`，含 epoch/robot/intent_sequence/source、模式、固定锚、S、lineage、原目标。
- `/{robot}/mr3_drive/odometry_calibration`：原生 WORLD producer 发布 `mr3-odom-calibration-v1`，绑定同源完整原 odometry、实际 float32 c/s 和转换合同；没有新增 ModelStates/world velocity。
- `/{robot}/mr3_drive/applied`：原生 `mr3-drive-applied-v1`，在同次真实物理更新的全部 SetParam 成功返回后发布；绑定实际 target/cmd_seq、actuation_sequence、source/dt 及全部轮对输入/输出。它证明写入调用成功，不能证明未来身体响应。

原七字段 `mr3-drive-target-v1`、九字段 `mr3-drive-target-consumed-v1` 存储ACK及原轮更新数学保留。
每20ms原三个真实存储屏障继续存在；应用更新为34ms，不假称每个50Hz目标都被轮更新消费。
实际注册的兼容后继可以完成 X→N；严格更晚 raw 才能退休旧责任，同戳原始样本先于应用检查。

Information 真订阅 intent/calibration；RPC 只声明 expected refs，不创造 ingress。
选中的 `{intent,calibration}` 必须与原始 odom 在同一 state envelope、同一 send/delivery 和完整 bundle 中交付。
表 SHA 是 canonical `{tb1:safety,tb2:safety,tb3:safety}`，每条机器人引用也绑定 safety SHA。
peer/motion 均实际接收完整同 bundle，再核对原始内容、来源、引用和表 SHA；只比 digest 标签不够。
V19另修复状态bundle消费时遗漏transform：仅reach保留同一实际交付envelope内完整原TF字段，转向cone从它计算；不以本机raw TF替补远端字段。legacy序列化仍按原规则移除该字段。独立交付reader对实际源/选择/envelope/side publication/bundle逐内容重建并取合取。
输出 status 的 intent_refs 是本轮新发布的三条承诺，table SHA 是本轮实际消费的上一份表，二者不得混为一物。

Humble 此安装的 callback 没有 MessageInfo。唯一发布者检查诚实标为 `graph_at_callback`，
记录 node/namespace/type/GID；不称 packet 身份认证、三网络端点、P3隔离或字节网络实现。

## 启动、历史和停车责任

release 先重新检查当前完整原始源的 rest/模型，固定 release anchor；未取得资格前仅全零。
资格要求 release 后连续全零发布≥.94s、真实全零存储≥.78s、实际全零应用和三个新鲜rest源。
当前工程实现采用全零（包括角速度）的保守资格；不借预热，不把资格缩短成只看当前零速度。
20ms原始/校准流和34ms应用流必须完整；缺回调则等待，矛盾/序列或时序洞则永久故障。
原始 ingress、坏源及其后tail、固定anchor历史、完整弦长与原累计路径诊断保留。

完整H/D停车责任在非零实际应用后就存在，即使严格更晚raw尚未到达。
全零发布建立责任时保留最近实际执行目标的原始 T（可比最后准入 T 更早，属于保守检查）。
之后旧非零目标在途的重复应用不能重启 H。新非零 publication/storage 也不能清旧 terminal；
只有新目标实际应用加严格更晚 raw 才能退休旧责任。零目标、task end、最后physics及cleanup tail分别保留。
原始弦长和采样metric只能作为必要下界/样本门，不得称连续路径上界。

## 同源数值与学习边界

producer 保持原 float yaw/cosf/sinf/body conversion。c²+s²并非精确1。
使用实际 c/s 和 IEEE32/64、RN、无FMA、无DAZ/FTZ 的声明前提，精确有理区间处理转换误差；
不以 epsilon 放宽 .01，也不根据 quaternion 重造 trig 系数。原生线程只检查浮点环境，不暗改环境。
物理heading与校准系数的实际关系仍需新冻结的独立校准/来源和物理角色验证。

safety 为执行 sidecar。actor维度、候选、mask、地图和reward定义不因它增加；三台本机guard仅取自己的raw，
同伴几何和模式仅取实际交付 bundle。无手工方向/目标兜底、无真值控制输入。
PPO入口仅在同freeze、同显式规则的完整原生资格及前驱学习审计通过时放行；当前尚无新规则资格，不能借旧38角色或旧模型进入。


## 2026-10-24 receiving authority v2 修复契约

本次用户授权执行修复路线。现行 `mr3-owned-stream-authority-v2` 保持全部原停止谓词和 100 ms 接收证据门；真实 witness 最多每80 ms重新发布，发送 grant/运行中取消终态使用≤100 ms证据。任务已不可逆停止时，仅释放真实 native terminal 的 ownership，不要求能再次授予运动的 witness；独立事件明确不供 normal-stop/物理资格。故障仍 fail-closed，日志保存具体拒绝谓词与前态。完整原生资格必须新冻结重新验证，详见[修复报告](report/20261024_mr3_p2a_authority_repair.md)。

## 2026-10-24 receiving authority v3 原子激活契约

v2 实测证明发送 ready 年龄80ms仍可能在接收时失去当前停止证据。现行 `mr3-owned-stream-authority-v3` 因而把合法 grant 登记为 PENDING，保持零权限；只在正常控制阶段重建原真实停止 witness 后原子转 ACTIVE，并以实际最新 raw callback sequence 设置 floor。既有回调不能取得新 owner 权限，严格更晚真实回调才可进入原 Reach。PENDING 续约不激活，原2秒租约、撤销和过期约束不变；非法包及重叠 owner 仍 fail-closed。独立读者必须逐原事件重建 PENDING→ACTIVE、原 witness 与 floor，并要求对应 activation ACK。原停止谓词、100ms证据界、STOP/B/R/5秒/95%不变。information 角色只检验自身信息边界，不能代替 FIFO/runtime 的完整 authority 重放。
