# MR3 P2A V35：rooms 残余停滞的有限归因

**有限取证闭合PASS：reset即原格门拒绝，实际点安全而同中心桥不安全；当前同seed中心路线存在表示缺口。P2A未完成。**

P2A未完成。[V34](20261022_mr3_p2a_v34_seed_v2.md)的唯一三场64步短探针已闭合，tb1和部分tb3运动恢复，但rooms tb3只有0.220832m、1个accepted goal，59/65记录被原seed_cell_body_clearance门拒绝。当前只做有界归因，保留真实失败，不延长300步或直接PPO。

## 本次改动与CPU

V34闭合后修复v2公共fused API的缺图/空图路径：零shape不调用strict canonical helper，保持原KEEP、无候选与pose_outside_received_map诊断。legacy/v1及非空图数学不变。两个fresh-state缺图反例加既有观测/v2共99项CPU通过。有限取证脚本的固定选择、130事件上限、输入SHA/路径、反例分类等12项人工CPU通过；外部观察者对真实live saved identity拒绝及reaped identity允许的2项人工CPU通过。合计113项，均无World/原件重放，工程新增0，actual-wait及源绑定见[索引](assets/20261022_mr3_p2a_v35_grid_liveness/checks/index_v1.json)。

## 事前有限取证

[scope](assets/20261022_mr3_p2a_v35_grid_liveness/scope_acceptance_v1.json)限定rooms101的已封存V34 trace，最多130 events（含close），只解码reset、首次tb3格净空拒绝、最后actor共最多3份输入；选择重合去重，不补样。所有65原件先按SHA绑定，但不解码其余62份。只计算received地图、估计状态与已选goal的canonical cell、原格/图门、独立点与桥、原lookahead及名义proposal条件。geometry-only结果不得覆盖原格拒绝。原件没有20ms命令/scan，不能唯一归因scan/pair停机，也不能补造实际运动。

单次新冻结、无重试，总工程预约60秒含外部关闭：main30秒、最多5秒超时清理、外部15秒及10秒截止余量。无World/新episode/训练/GPU，原生/任务资格false。入场47735.8935792376018/52000，余4264.1064207623982秒，最大预约后仍可负担；实际按main和final outer单调钟union上计。pilot/final-only不动，75000提案仍待答，20100完整原生资格+minimum预约不受此小诊断替代。

## 路线判断边界

只读代码审查发现：v2整段和20ms提议可满足raw闭格几何净空，却经过原cell-centre graph不接受的格；下一quantum的起点门会拒绝。它是可构造的执行/图一致性反例，尚不能据此认定真实rooms的唯一根因。若证据支持，优先研究局部执行保留原图与已选路径的约束，继续保持.29m和原任务门。

均匀格的精确square-centre dilation虽可在一般分辨率改善EDT下界，但在当前.05m/.29m组合下两者unsafe offset集合相同，不能把它当当前rooms修复。点安全与所在格中心安全也不同；不以更精确centre图替代执行路径约束。此处是数学/源码推导，实际三帧结果随后追加。

## 唯一实际取证闭合

新源冻结`47dd6774e478bb714e1844e0056f2301269896a3`已clean/pushed后执行唯一诊断。main1.726117935秒、final outer0.092027966秒，union1.818145901秒；两端点2.052657422秒，含0.234511521秒间隙，低于60秒预约。前后源与绑定原件SHA稳定，5保存PID/start均fresh gone（Z按present），无新World/episode/GPU/optimizer。见[原件清单](assets/20261022_mr3_p2a_v35_grid_liveness/closed_inventory_v1.json)、[末账/身份](assets/20261022_mr3_p2a_v35_grid_liveness/closed_metadata_v1.json)及[实际发现](assets/20261022_mr3_p2a_v35_grid_liveness/closed_findings_v1.json)。

130 events完整读取；首次tb3格拒绝就是reset，因此固定三个角色去重为两份输入，未补样。

| 角色/序列 | canonical cell | 原cell lower bound m | 实际点 .29证书 | 同中心整桥 .29证书 | active goal/累计接受数 |
| --- | --- | --- | --- | --- | --- |
| reset兼首次拒绝 / 1 | [101,150] | .2848008728123151 | PASS | FAIL | 无 / 0 |
| last / 129 | [106,152] | .28087242695751063 | PASS | FAIL | 无 / 1 |

两格raw值均0、原traversable均false；重算cell与下界等于原snapshot字段。独立点证书只证明达到.29门（其距离为阈值封顶，不宣称全局精确最小值）；geometry-only整桥平方最小值约.08125，确实低于(.29)^2=.0841，不能以移向本格中心作安全修复。该结果没有覆盖未保存的实际20ms轨迹/scan/peer命令。

**路线调整：停止把本次初始rooms拒绝只归因于shortcut或EDT精度。** reset尚无goal，故不能由后来shortcut导致初始失败；该静态反例仍是执行契约的另一问题。[数学/源码讨论](assets/20261022_mr3_p2a_v35_grid_liveness/graph_reasoning_v1.md)说明当前.05/.29的centre布尔图也不能靠精确dilation获得不同集合。此前“保留原含点格的graph门且只桥接该格中心”的路线不足以覆盖这些已观测安全点。

下一步先禁用CPU原型：将未吸附的实际received estimated point作为virtual start，只允许其inbounds/raw0/精确点.29通过；在固定3×3局部邻域内，对原图节点逐条做完整.29桥认证，保留全部合格anchor，不选择探索goal、不命令运动、不改图。它明确替代旧的“含点格本身必须是图节点”的前提，属于新科学版本，不能声称旧seed-cell gate未变；threshold、unknown/outside阻塞、目标/参与/95%任务与真值隔离不动。原型通过也不自动接生产或取得原生/训练资格，之后须声明新的观测/候选/执行版本及完整准入。

累计47737.7117251386018/52000，余4262.2882748613982秒，pilot/final-only不变。75000提案仍待答；当前不能联合预约20100秒新原生资格+minimum。保留V34/V35原件和全部原FAIL，不重跑本活动。
