# 当前三机器人基线与MR3适配启动命令

## V53部分取证已关闭，V54新资源版本待冻结

[V53](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261023_mr3_p2a_v53_firstfault.md)实际rc1/partial FAIL：motion固定100万行门停止，首生产故障UNKNOWN；startup仅证实worker自身通用失败回调。完整parent229.413776461墙秒已收费，工程累计90102.9195132536018/120000、余29897.0804867463982，所有旧FAIL和政策余额保持。

当前准备执行[V54资源限定后继版本](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261023_mr3_p2a_v54_firstfault.md)：同两原件/选择规则/旧七解释源，200万行、480秒合作式work、600秒完整parent费用门。21项规范人工CPU实际PASS/.375278637墙秒、18源稳定、两身份gone；候选首轮setup失败保留。只在新commit/push后以exact40freeze执行一次独占输出命令，当前尚未新读raw；没有ROS launch/worker/机体/安全模式变更，也不启动native/PPO。下列V53/V52命令均是已闭合活动的历史准备快照，不得重开。

## V52关闭与V53离线取证

V52原命令已执行FAIL并关闭，禁止重试或覆盖：deadline第204步控制模型负ACK；24/30角色保持原工程结果。当前只执行[V53固定两原件描述](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261023_mr3_p2a_v53_firstfault.md)，无ROS launch/worker/机体/模式变更。新40位执行freeze须先commit/push；具体命令、300秒工程预约和独占输出见该预声明。default baseline与原pilot/final原额保持，P2A未完成。下文V52准备段为执行前快照，不是可重开的活动。

## V52 独立 reset reader 登记与完整资格准备

Reach 的 launch/worker/机体配置保持。新的 `mr3-reach-reset-outward-cancel-v1` 是资格审计工作负载登记，固定原 V17 读者及未改的 V3/V4 物理数学；不是运动/SLAM 模式开关。新完整同冻结资格及学习链使用独占 V52 plan，旧活动命令与原件不可重试或覆盖。准确 CPU/新资格入口、预算和当前尚未执行状态见[V52报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261023_mr3_p2a_v52_qualification.md)。P2A仍未完成，默认baseline保持。

## reach 环境自动启动协议（V49）

当前由 Supervisor 管理的原生 `mr3-reach-v1` reset 自动使用 `received-input-pause-drain-v1`，没有新增 CLI/launch 开关。worker 先实际收到 monitor-ready、有效本 epoch 的 initial-input ACK 和被动 recorder-ready，再启动 step helper、取得真实暂停回执并对齐实际时钟。暂停后先通过原拓扑、三方全零 takeover 和三机真实 storage ACK；既有20ms全零 bootstrap 在新边界完成严格 state→peer→motion commit、ready status 和 storage 屏障后，再等待实际四项 ready 同时成立，最后才进入原 snapshot/release 和 evaluator 屏障。初始 snapshot 前的 motion 输出必须全零。单独 ROS launch 不执行 Supervisor/worker 的私有 reset 握手。

父 reset 的默认420s绝对 monotonic deadline 从入口计时，包含关闭上一轮、worker 创建、导入及 RPC。worker 共用工作截止时间 `min(worker构造早期时刻+400s, 父deadline-65s)`，为原60s失败清理和5s响应留量；两个 ready 阶段不能各用400s，也不增加外部超时。启动失败清理另取 `min(当前时刻+60s, 父deadline-5s)`，各阻塞等待共用实际剩余时间。实际接收、四项变化、阶段和失败快照写入独占 `startup_readiness.jsonl`；本 epoch 的真实 exploration failure 在启动健康检查处失败。legacy 保留旧顺序并省略新增字段。协议、日志语义和边界见[启动契约](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_STARTUP_CONTRACT.md)；这是新版本启动行为，仍需新冻结资格，旧FAIL保持。

## 显式reach几何证书参数（V44）

`mr3_reach_geometry_rule`缺省为`binary-cone-v1`，沿用原二值nonclosing/完整纵向包络判据，旧argv及metadata省略新增字段。显式`mr3_reach_geometry_rule:=cone-support-v2`选择同一Reach集合的连心线投影充分分离证书；仅可与`mr3_safety_contract:=mr3-reach-v1`、三机器人、`execution_mode:=adapter`和`mr3_stepped:=true`组合。未知、重复选择或不支持的profile组合会拒绝。

新选择从reset请求进入worker、launch及motion_safety，三个ReachTracker的当前/拟议证书采用同一值，configuration明确记录实际选择；intent/driver wire、固定锚点、2R/4R、源龄、物理响应和95%门保持。生产日志中的向外区间只作摘要，精确判据使用未取整的有理数。实际资格和学习仍由同一新冻结plan及全部独立门决定，V41原FAIL保持；新增参数本身不提供原生或P2A通过信用。

2026-10-22 V40闭合FAIL：新冻结291b9e32e实际preflight阻止merge_map输出打包未登记的旧native pin冲突；755源/Git/current无漂移。未启动matrix/World/native/PPO，3身份gone，完整parent实费22.442744464（inner包含不叠加）。累计48282.3965638106018/75000、余26717.6034361893982；原FAIL及pilot/final余额保持。用户已授权自主直到P2A完成，不再重复审批；继续显式packing source版本修复/新freeze，P2A未完成。见[V40闭合](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261022_mr3_p2a_v40_native_qualification.md)。

2026-10-22 V40授权续接：用户明确“你一直继续执行就好了，直到把P2A完成，不需要问我是否批准”，授权自主持续完成P2A，不再反复请求一般预算/实施批准。当前工程块75000，入场48259.9538193466018、余26740.0461806533982；完整新native资格+收口+minimum预约20100。V39恒等提速已完成，现准备新冻结完整链；pilot/final初始余额、95%/质量/安全门及旧FAIL保持，P2A仍未完成。见[V40](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261022_mr3_p2a_v40_native_qualification.md)。

2026-10-22 V39闭合：精确segment证书AABB/零长度恒等提速已接生产，446人工CPU通过；冻结a44旧源码逐字段/JSON及独立全格oracle一致，固定128call人工完整证书约2.72倍提速，非World吞吐。首轮system无torch导入FAIL原件保留，环境分离后通过；无新World/学习/工程费。累计48259.9538193466018/52000、余3740.0461806533982；原生资格+minimum须预约20100，75000未批，pilot/final-only及原FAIL保持，P2A未完成。见[V39](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261022_mr3_p2a_v39_certificate_kernel.md)。

2026-10-22 V38闭合：160人工CPU及禁用证书恒等优化通过；a44e1b844冻结一次协议解析935行/102选行，证实tb3新goal续租53.4生成54.1截止时才交付、accept54.5，原V37租约FAIL保留，不刷新TTL/FIFO。2D随机全PASS不是native前置，负样本审计新规则仍仅提案；先恒等提速CPU，再预算批准后原生资格/学习。实费.315303155、5身份gone，累计48259.9538193466018/52000、余3740.0461806533982；75000待答、pilot/final-only不动，P2A未完成。见[V38](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261022_mr3_p2a_v38_protocol_cpu.md)。

2026-10-22 V37闭合：显式point-graph生产/626人工CPU通过；13e95f29f冻结8步profile PASS，三场64步短probe FAIL，119/119/0、122actor/366机器人观测attachment均接受；corridors54秒navigation_failure全局停止，open38/rooms27未完成。原tb3 cell FAIL保留，现先查FIFO/目标租约实际交付，不重跑或改门。267原件/9.30MB、34身份gone；实费520.102603214，累计48259.6385161916018/52000、余3740.3614838083982。75000待答，pilot/final-only不动，P2A未完成。见[V37](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261022_mr3_p2a_v37_point_graph.md)。

2026-10-21 V33闭合：冻结6d16ebdc5的显式exact seed三场101各64步短工程链通过192/192/0、195actor/585证书和20身份gone；功能未解决，tb3每场65/65 pose_not_in_original_seed_cell，tb1几乎不动。规范273原件/11.79MB；实费578.391653362，累计47269.8043977356018/52000，余4730.1956022643982。继续定位精确cell算术与强制中心桥执行先决，新规则须新版本/冻结，不把短工程PASS当P2A；75000提案待答，pilot/final-only不动，P2A未完成。见[V33](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v33_seed_mode.md)。

2026-10-21 V32 CPU：精确point/同seed-centre桥证书禁用原型14项人工通过，保留.29m、unknown/outside、原seed-cell及graph门；未接生产/真实rooms或改V21字节门。两次fixture/launcher失败原件保持，工程新增0。后续先明确新观测/科学版本及必要准入，不能据此PPO/重跑V31；工程仍余5308.5872556263982，pilot/final-only不动，P2A未完成。见[V32](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v32_seed_certificate.md)。


2026-10-21 V31闭合：e7dc690冻结Karto显式模式profile8步与三场各300步完整工程/独立行为PASS；behavior900/900/0、903actor，三场真timeout、任务0/3、0代理unsafe/contact。open质量/参与PASS，rooms/corridors未过；有限原件诊断定位own/navigation起点净空下界.282843<.29导致持续无GOAL，先做精确点/同seed桥证书CPU，不降门/PPO/重跑。1030原件/36保存身份gone，含失败启动及2秒discovery上计共1245.989041707秒；累计46691.4127443736018/52000、余5308.5872556263982。pilot/final-only不动，P2A未完成。见[V31](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v31_karto_behavior.md)。


2026-10-21 V30：Karto薄sensor adapter/显式接线已实现，当前24项人工CPU和consumer80项通过（1跳过），默认endpoint保持；不是SLAM/质量/95%或训练资格。V31将按新scope/freeze执行最多600秒8步profile，完整PASS后才最多3600秒三场长行为，另300秒forensic，总4500工程块；不重开旧活动、不PPO/扩额。当前工程45445.4237026666018/52000、余6554.5762973333982，pilot/final-only不动，P2A未完成。见[V30](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v30_adapter.md)。


## V29 Karto直接CPU接口（已完成，未启用mapper）

已用canonical headers/本地现有库编译运行固定7case探针，未改SDK/ROS build/default。准确reach外层、g++编译与临时ELF运行命令和原件见[报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v29_karto.md)及共享log。仅fixed-grid bookkeeping/API，native AddScan与显式RayTrace量程语义不同，不直接换mapper或跑行为/PPO；已有输出不覆盖/盲重跑。下一步disabled sensor adapter/有限CPU，工程0新增、P2A未完成。

## V28 一致性CPU候选（已完成，未启用）

38项新检查与31组人工三模型比较完成；结构一致性通过，格线占用召回/持续偏差代价使v3仍禁用，不做当前候选正式试跑或PPO。唯一实际CPU入口为 `report/assets/20261021_mr3_p2a_v28_mapping/run_cpu_v1.sh` 经reach actual-wait执行；完整argv/绑定/结果见[报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v28_mapping.md)与共享log，既有输出不覆盖或盲重跑。World/worker/launch默认不变，工程0新增，P2A未完成；下一步先核既有SLAM量测模型复用。

## V27 人工CPU建图候选（已完成，未启用）

本轮新增独立sensor-only mapper-v2与人工比较脚本，未更改World/worker/launch默认。68项检查和14组人工比较完成，但corner、持续偏差及首次hit延迟等反例使候选保持禁用，不据此启动完整行为或PPO。唯一实际CPU命令由 `report/assets/20261021_mr3_p2a_v27_mapping/run_cpu_v1.sh` 通过reach actual-wait执行；准确外层argv、源绑定和输出见[报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v27_mapping.md)与共享log。已有输出仅供复核，不覆盖或盲重跑；无新工程费用或训练/native资格。

## V26 实际几何只读诊断

该唯一活动已在89a1b0543c5445bb5815162ae4ef07f1f7c728c0完成并闭合，不重跑/复用输出。三场条件上界未排除原.20门，也不证明任务可达；0World/Node/episode/策略，默认launch不变。实际前检/guard/final精确argv和原回执见[V26](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v26_geometry.md)与共享log。工程余6554.5762973333982秒，pilot/final-only未动；下一步sensor-only建图CPU候选，不直接PPO。

## V25 CPU检查已完成

协议/人工质量/缓存等价检查已完成，导航只调整私有几何缓存键；默认launch和参数不变。人工计时不代表ENV长回合吞吐，新源码没有正式资格；不重跑下列历史活动或直接PPO。下一步先核代理地图与原质量门相容性，见[V25](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v25_cpu.md)。工程仍余6559.4631148643982秒，pilot/final-only未动。

## V24 长回合行为诊断已FAIL闭合（历史命令）

本次已在9b33cf9b6ab491fd5e3b15269adb30d43be1354c执行并FAIL关闭：544attempt/543return/1rooms租约边界错误，20保存身份gone，余6559.4631148643982工程秒。以下仅真实历史入口模板，不重试/复用输出或训练；后续post-advance tick只是CPU修复，不提供新冻结资格。每env仍三台，默认native launch不变。详见[V24](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v24_behavior.md)。

```bash
PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES= /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance preflight --kind full_behavior --freeze EXACT40
PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES= /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.reach_execution --scope engineering --output /tmp/mr3_proxy2d_v24_outer --source mr3_learning/proxy2d_performance.py -- /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance execute --kind full_behavior --freeze EXACT40
```

EXACT40当时是9b33cf9b6ab491fd5e3b15269adb30d43be1354c；父进程实际wait后，已用engineering wrapper执行`proxy2d_performance final --kind full_behavior --run RUN --outer OUTER_ACTUAL_WAIT --output NEW_JSON`并计外尾、核保存PID/start均gone。未完成/安全失败不补样或改成任务成功，P2A/原生训练资格保持未完成。

## V23 性能剖析与短容量已闭合（历史命令）

profile冻结caddd853ab8884b3e2fd1018069af2fdc139d3e8、short冻结2e8fcac9439a1a53e3913e45abccdc0b6645825d均已PASS闭合，不可重跑。short实际30个8步EP/240verified返回/0step错误、73保存身份gone，V23合计806.844068675秒，累计44068.6680536126018/52000、余7931.3319463873982。以下仅历史模板；不能复用plan/输出或启动训练。默认profile关闭；学习端canonical wireless-rl/conda ns3gym，system worker/evaluator显式隔离。详见[V23](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_v23_performance.md)。

当时冻结并推送后使用以下入口（EXACT40为各自完整freeze，不能复用旧输出）：

```bash
PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES= /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance preflight --kind profile --freeze EXACT40
PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES= /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.reach_execution --scope engineering --output /tmp/mr3_proxy2d_v23_profile_outer --source mr3_learning/proxy2d_performance.py -- /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance execute --kind profile --freeze EXACT40
```

short实际使用同模板kind=short_capacity、outer=/tmp/mr3_proxy2d_v23_short_outer、EXACT40=2e8fcac9439a1a53e3913e45abccdc0b6645825d。父进程真实wait后，已由engineering wrapper完成`proxy2d_performance final --kind short_capacity --run RUN --outer OUTER_ACTUAL_WAIT --output NEW_JSON`，费用含外尾；有限共享前缀对照另计工程消费者。详细actual argv/源码/回执与完整封存见V23，不可先调用collect绕过符合性。下一正式活动需新的具体范围、冻结与plan，当前PASS只提供短容量，不解锁训练/原生/gateway。

## V22 二维活动已FAIL闭合（历史命令）

本次唯一活动已在1dc2a1f601693f542479f9b6b7c54c69519b5460执行并FAIL闭合，17保存身份gone；下列仅保留历史命令，不是重试入口。V22当时余8738.1760150623982/52000，最新余额以顶部V23为准，pilot/final-only未动。默认原生launch不变。此入口创建system Python无Node代理worker及独立evaluator，学习端仍conda ns3gym，不启动Gazebo/Nav2/ROS graph或训练。固定三机，1/4env共9000 ENV.step尝试、3600秒，包括正式符合性和独立审计；没有native资格信用。计划与入场条件见[V22](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_v22_proxy2d.md)。

仅在当前版本clean commit/push、封存plan前检通过后，由单独actual-wait父进程执行一次，EXACT40是该实际完整freeze；不得直接调用collect绕过符合性。以下为当时模板形态，实际EXACT40为1dc2a1f601693f542479f9b6b7c54c69519b5460；实际argv/结果见V22，当前修复后的源不可冒充该freeze：

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES= /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B \
  -m mr3_learning.proxy2d_activity preflight --freeze EXACT40
PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES= /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B \
  -m mr3_learning.reach_execution --scope engineering --output /tmp/mr3_proxy2d_v22_outer \
  --source mr3_learning/proxy2d_activity.py --source mr3_learning/proxy2d_capacity.py \
  -- /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_activity execute --freeze EXACT40
```

本版本原件输出为ROS树log/mr3_p2a_proxy2d_v22/run_v1；拒绝覆盖/重试。源冻结后不编辑运行/审计文件，所有已提交工作真实wait、末端保存身份独立核对及外部尾费用仍须收口；完成记录进共享log。二维训练、迁移和gateway仍未开始。

## MR3 P2A V21 已闭合诊断（历史命令）

该唯一活动已在冻结c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90执行并FAIL闭合，全部保存身份gone；以下仅保留真实历史命令，不是重试入口。不得复用run/output目录，不因CPU修复直接重跑。本次原预约6500秒，实际3263.823140435秒，1worker、open101两次32步，合法均匀随机，无模型/优化/训练资格。运行参数与停止规则见[V21预声明](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_v21_feasibility.md)。native调用固定在已冻结plan内，失败不直接重跑benchmark。

以下保留当时的模板入口，实际执行时EXACT40已固定为c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90；完整真实argv见V21封存回执。它不适用于当前修复后的源码，也不得作为下一次诊断入口。该次执行的学习侧终端为wireless-rl目录、conda ns3gym、未source ROS，前检后运行期间源码/库/Git/原件保持不变。

```bash
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH
python -m mr3_learning.reach_diagnostic preflight \
  --plan report/assets/20261020_mr3_p2a_v21/predeclared_plan_v1.json \
  --freeze EXACT40 --output /tmp/mr3_p2a_v21_diagnostic_preflight.json
python -m mr3_learning.reach_execution --scope engineering \
  --output /tmp/mr3_p2a_v21_diagnostic_outer \
  --source mr3_learning/reach_diagnostic.py \
  --source mr3_learning/benchmark.py \
  --source mr3_learning/audit_reach_diagnostic.py \
  --source mr3_learning/reach_gates.py \
  -- /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.reach_diagnostic execute \
  --plan /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261020_mr3_p2a_v21/predeclared_plan_v1.json \
  --freeze EXACT40
```

本次执行outer真实wait退出后，已独立运行 `reach_diagnostic final --plan PLAN --outer /tmp/mr3_p2a_v21_diagnostic_outer/actual_wait.json --output NEW_ABSENCE_JSON`，同样保存真实wait并将该外部尾费用加入工程末账。进程全部gone与诊断成功分开报告，不能以absence PASS覆盖原生失败；之后封存原件和准确总账。本入口不能解锁minimum/pilot/验证，60000扩额仍未批准。

2026-10-20 V21当时闭合快照（实时余额/状态见V22）：P2A未完成。V21两次32步合法随机原生返回/关闭完成，但第一回合guard真实storage ACK回调晚于worker推进1.076029ms，Cadence内嵌Runtime失败；保留FAIL且不重试。真实guard屏障修复已有132项CPU通过，未取得修复后原生资格或训练。工程末账41480.3336378496018/52000，余10519.6663621503982；pilot和三final-only不动，60000仍未批准；随后已接受的V22二维实现/符合性/零更新容量见本页顶部，训练/迁移未批准。显式reach为20Hz激光，legacy/base为5Hz。见[V21闭合](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_v21_feasibility.md)及[具体后续提案](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_next_route_proposal.md)。

2026-10-19：P2A.0已验收，P2A未完成。用户已批准V14科学候选并授权生产实现；V15实现显式`mr3-reach-v1`安全模式、真实应用/同源校准回执、完整模式交付及版本化必要审计器，当前完成CPU/编译准备，待新冻结完整原生资格。默认`legacy`保留，旧FAIL不改判；本轮无新native/GPU/pilot/验证，P2B/gateway未启动。见[V15实现与验证](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261019_mr3_p2a_v15.md)和[新契约](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_REACH_CONTRACT.md)。

2026-10-19用户已批准工程累计上限52000墙秒，并授权后续实现/修复直接推进；工程已用32673.5464309836018/52000墙秒，余19326.4535690163982；pilot1870决策/2905.9547395464029墙秒及三场final-only额度未动。旧V13同冻结独立38/38仅有原工程信用，原矩阵/optional/minimum FAIL保留；minimum整轮ineligible、0 eligible/0更新。详见[V13原始结果](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261019_mr3_p2a_v13.md)。

2026-10-18用户已验收P2A.0并要求继续P2A。V7命令为已关闭失败的历史入口，不能重跑；原V26父编排中断保留，P2A未完成。 原V26命令仅供追溯；原生阶段已完成、最后只读审计单独补完，原编排中断不改记PASS。见[V26](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261018_mr3_p2a0_v26_capture.md)和[复盘](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261018_mr3_p2a0_reflection.md)。

新路线为 [MR3](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md)，P0/P1A/P1B已验收，用户于2026-10-16验收P1C并授权P2A；P2B及后续未开始。
默认`execution_mode:=baseline`启动前沿控制器；`adapter`为显式联合动作接口。P2A联合MaskablePPO正在实现与验证；gateway未开始。
所有推荐运行显式固定三台，活动默认已改为三台，保留1–4历史兼容。

新冻结的P2A原生复验由对应版本计划驱动：`mr3_learning.reach_preparation --plan PLAN --freeze EXACT40`
执行四阶段；完整新资格及协调进程退出核验通过后，才由
`mr3_learning.reach_policy_chain --plan PLAN --freeze EXACT40 --qualification RECEIPT --stage minimum`
进入新的最小训练链。后继`pilot`和`validation`分别要求前阶段完整科学审计与外部退出回执。
PPO直接入口新增`--safety-contract mr3-reach-v1 --reach-plan PLAN --reach-qualification RECEIPT`，
两份原件SHA写入metadata；仅有旧PASS或模型文件不能放行。各阶段精确argv、路径、预算及条件以冻结预声明为准，不能绕过watcher和关闭门直接重跑历史命令。

## 环境与构建

ROS 使用系统 Python 与 ROS 2 Humble，学习端 `ns3gym` 不用于启动 ROS 节点。
请在未激活 conda、未 source 其他 ROS workspace 的新终端执行：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
export PYTHONNOUSERSITE=1
/usr/bin/python3 /usr/bin/colcon build --symlink-install --allow-overriding nav2_bringup nav2_velocity_smoother
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1
```

这是历史schema3/普通演示的同主机 ROS 发现 profile；P1A合同模式使用下方明确的
UDP-only配置。两者都不等于正式多主机部署或 ns-3 网络模拟。
切换源码版本需要先评估旧 build/install 的路径/包缓存；必要时移到工作区外备份，
从 underlay 干净重建，保留 log。重新开终端 source，不能认为增量构建已删除旧入口。

## 新安全profile（V15工程准备）

V34新增 `mr3_seed_rule:=exact-point-bridge-v2` / learner `--seed-rule exact-point-bridge-v2`，
沿同一supervisor→worker→launch→adapter链传递，二维worker同样显式选择。
它使用精确所在格和新候选版本；局部路径执行只用于二维代理，原生仍保留Nav2。
v1/v2的plan、metadata、snapshot、资格与PPO必须逐层匹配。默认仍为legacy。
本轮仅允许预声明零更新 `seed_probe_v2`；本段不是新的原生资格或训练准入。

V33增加独立的显式观测参数 `mr3_seed_rule:=exact-point-bridge-v1`，默认 `legacy`。
新规则只允许三台、adapter及stepped；学习侧 `Supervisor(seed_rule=...)`、benchmark/PPO
的 `--seed-rule exact-point-bridge-v1` 会传入同一worker/launch/adapter。
新冻结资格计划、minimum、pilot和final必须使用同一参数及新候选版本；旧资格不能混用。
完整科学门和运行预算通过后，才由冻结计划启动，不能自行追加这个参数重跑历史命令。
二维显式 `ProxySupervisor(..., seed_rule="exact-point-bridge-v1")` 仅用于V33预声明短probe，
不等于原生Nav2或训练入口。证书/版本详见[环境契约](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_ENV_CONTRACT.md)。

新增launch参数`mr3_safety_contract`仅接受`legacy`（默认）或`mr3-reach-v1`。
后者只允许`execution_mode:=adapter`、`mr3_stepped:=true`及`robot_count:=3`，由Supervisor/worker
传递到Information、peer和motion；直接launch不能替代worker的20ms暂停、相位及存储屏障。
完整执行模型见[新契约](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_REACH_CONTRACT.md)。

学习侧`Supervisor(..., safety_contract="mr3-reach-v1")`、benchmark与action_trace的
`--safety-contract mr3-reach-v1`为显式工程入口。原旧preparation motion/参数读回组合会在启动前被拒绝；
PPO train/evaluate也拒绝新profile，直至新版完整资格接通并实际通过。默认legacy原入口保持。
下面是后续新冻结/预算预声明后的采集命令形态，本轮未执行，也不提供完整资格或训练信用：

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B \
  -m mr3_learning.action_trace --run-id mr3_reach_v1_fresh_trace \
  --safety-contract mr3-reach-v1 --domain 180 --port 14001
```

两项新版必要只读审计入口为`mr3_learning.audit_reach_information`与
`mr3_learning.audit_reach_runtime`，参数为回合目录及`--output`新文件，可另指定`--freeze`。
它们不能代替完整输入、接触、物理覆盖、peer云/scan、关闭及最终身份消失门；不能把旧38/38转记给新profile。

显式reach从V19起生成真实20Hz激光配置，base/legacy仍5Hz；由同一`mr3_safety_contract`选择，不增加可旁路的手动频率开关。其真实source stamp及每轮双帧证书仍由新冻结完整资格验证。

## 三台手动演示

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=3 world:=p1c_rooms.world gazebo_seed:=101 \
  enable_gzclient:=true enable_rviz:=false enable_merge_rviz:=false \
  auto_save_map:=false
```

持续建图，Ctrl+C 结束。改为 `world:=my_world.world`、`p1c_open.world` 或
`p1c_corridors.world` 可运行现有其他场景，均是开发/已知场景，不叫未见布局。
看地图时可设置 `enable_gzclient:=false enable_merge_rviz:=true`；`enable_rviz` 只控制
每机器人 RViz，不控制全局 RViz。保持 `enable_drive:=false`，避免另一个速度发布者。

就绪需要三台 action 可发现和每台六个 Nav2 lifecycle 全部 active，不是固定 sleep。
主模式使用 SLAM，三台 Smac2D 的非滚动全局地图均来自实时融合图。轮关节状态由 Gazebo
插件发布，robot_state_publisher 生成 TF。peer_layer 的完整队友机体包络来自观测
odom/TF，不使用真值、不进入 SLAM；任务中源数据失效锁存控制失败并取消目标。
这些实时共享输入**尚未受网络限制**，后续 MR3-P3A 必须消除旁路。

## MR3-P1B理想适配与脚本探针

在已source上述ROS/Gazebo环境的终端使用下方P1A同主机UDP profile。
新模式只启动`mr3_adapter`目标所有者，禁止同时启动control或drive；同ROS域的本机锁
会拒绝第二个所有者。策略输入来自`/mr3/received/map`及交付状态；Nav2全局图为
本机最新图与交付共享图融合的`/tbN/navigation_map`，peer使用交付状态副本。
原生action端点仍位于适配器进程；这不是P3A的DDS隔离或网络gateway。

```bash
MR3_ADAPTER_ID=mr3_p1b_open_$(date +%Y%m%d_%H%M%S)
export ROS_DOMAIN_ID=108 GAZEBO_MASTER_URI=http://127.0.0.1:11901
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_mr3_adapter_probe.py \
  --scene open --seed 101 --run-id $MR3_ADAPTER_ID
/usr/bin/python3 scripts/audit_mr3_adapter_probe.py \
  log/mr3_adapter/$MR3_ADAPTER_ID --require-contact-monitoring
```

脚本自动设置P1A UDP profile，按声明的较长已观测路径验证候选目标、KEEP、WAIT、第二批目标和25秒后终态
闭合；完整95%评价器仅保留原口径监测，主动短停不能当成任务成功。
rooms/corridors分别使用对应`--scene`，推荐域109/110、Gazebo端口11902/11903，逐次运行，
每次新run-id。独立审计读取真实接受/取消/结果和子进程退出，不能只看runner返回值。
脚本显式设置`adapter_probe:=true`，仅允许将评价器以未完成诊断正常结束；默认关闭该服务。
详细信封、频率、租约、观测/候选/掩码和动作字段见
[MR3_ADAPTER_CONTRACT.md](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_ADAPTER_CONTRACT.md)。
冻结`f9928fe`的open/rooms/corridors各seed101严格审计均通过，前三次失败与完整原件见
[P1B报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261015_mr3_p1b.md)。
K8/5秒承诺是本接口版本；P1B异步名义1秒快照在rooms实际有2/3秒间隔。
P1C独立验证stepped 1秒步长/reset/采样，非stepped timer名义频率与跳帧规则不变。
这不证明95%任务或RL有效性；P1B/P1C已验收，P2A正在实施。

手动提供策略输入时可启动同一模式：

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=3 execution_mode:=adapter mr3_episode_epoch:=unique_episode \
  world:=p1c_open.world gazebo_seed:=101 enable_gzclient:=false \
  enable_rviz:=false enable_merge_rviz:=false auto_save_map:=false
```

无外部`/mr3/action`输入时保持空闲；KEEP不重发目标。正式验证使用脚本内的P1A持续监测，
手动入口未启用评价器，不产生安全或任务成绩。P1C reset/采样工程已验收，P2A训练使用下方独立入口。

## MR3-P1C采样与完整reset入口（2026-10-16已验收）

步进模式明确构造gzserver argv，将每个`-s`与插件路径放在ROS参数终止符之前；
启动日志`MR3_GAZEBO_SERVER_START`记录实际argv、插件和clock配置。baseline保留原启动入口。
stepped worker在暂停前等待adapter的`/mr3/initial_inputs_ready`实际交付确认，
再做原物理相位、drain、快照和seq0绑定；节点出现在graph不能替代该确认。

P1C W7验证的关闭顺序为：真实目标闭合→Nav2原生SHUTDOWN及18节点GetState finalized确认→
最后reward ACK/评价器clean退出→SDK按实际action/PID逐个正常退出ROS进程→Gazebo原生停止。
服务/状态/有序退出回执分别保留，超时或非零退出仍失败；不使用固定sleep代替退出，也不改接触/源序号门禁。
FastDDS保持原依赖，CycloneDDS因官方Humble缺少真实publication_sequence_number未采用。
v6完成记录中的合法2秒TTL浮点误拒及扣分保持原件；W7 `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`
以整数纳秒端点统一命令/租约/承诺/RPC期限，在任务/接触/频率不变下完成全新八阶段与独立命令时间审计。详见[P1C报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261015_mr3_p1c.md)。

先在系统ROS终端按上文重新构建包含步进插件的工作区。学习端另开终端，使用conda，
不source ROS或拼接ROS的PYTHONPATH；supervisor会在独立系统Python子进程重新source规范ROS/Gazebo环境。
以下是已提供的采样入口示例，不授权再次运行既有预算。W7工程证据含762项ROS/40项CPU检查及完整八阶段原生矩阵；
P1C/W7的GPU只保留b328原固定接口3F/3B/0更新范围，P1C本次无新GPU调用。新实验仍须先声明并绑定新推送冻结。

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
unset PYTHONPATH
export PYTHONNOUSERSITE=1
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 \
  --steps 16 --run-id UNIQUE_P1C_1W
```

2/4 worker使用同一入口的`--workers 2`或`--workers 4`及各自唯一run-id；每个worker始终三台，
不是二/四机器人规模实验。默认分别占用从ROS域120和Gazebo端口12001开始的独立编号。
输出位于ROS工作区`log/mr3_learning/<run-id>/`；run-id目录拒绝覆盖。
指标须包括完整startup/reset/closure的有效transition率、仿真倍率、CPU/RAM与GPU资源记录，失败保留。
脚本动作仅施加候选/KEEP/WAIT和取消压力，不是训练策略或性能比较算法。

诊断失败入口默认关闭，仅用于已预声明的P1C终态验证；每轮先3个KEEP步，
分别验证20ms短终态和同边界零时长尾步，不伪造接触或clock。
`training_terminal_probe`默认false，只能与stepped及隔离reward同时启用。

```bash
python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 \
  --steps 4 --terminal-probe --run-id UNIQUE_P1C_TERMINAL \
  --base-domain 144 --base-port 12171
```

本次已保存W7正常矩阵可离线重放；在wireless-rl目录执行，输出必须用新名。此命令不启动原生进程：

```bash
/usr/bin/python3 -B report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v3.py \
  report/assets/20261015_mr3_p1c/native_v7/workers1 \
  --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --output /tmp/UNIQUE_W7_WORKERS1_PHASE3.json
```

phase3固定绑定原contact task-phase与独立命令时间门禁；scalar reward审计独立列于原件，不由此命令替代。
检查保留的GPU接口结果只读取原JSON，不重复已消耗的3F/3B预算：

```bash
/usr/bin/python3 -m json.tool report/assets/20261015_mr3_p1c/gpu_probe_v2.json
```

原GPU探针在b328固定model/encoder/probe下完成3次forward/3次backward、0 optimizer更新；
它不是训练或W7新增GPU验证。任何新GPU尝试须另立前瞻计划和预算，不能重用原v2计划再执行。
当前Gym/IPC依赖锁定见`mr3_learning/requirements-env.txt`，保留现有CUDA栈，不默认重装环境。
固定1秒step、20ms量子、真实clock相位、seq0首格奖励绑定与外部截断/真实闭合规则见
[环境契约](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_ENV_CONTRACT.md)。
每次实际执行均是需追加共享log的实验，不能把入口存在当成P1C通过。

## MR3-P2A V13 温和转向profile（工程资格38/38，minimum真实FAIL）

冻结`0063aa233ba3008ddcc1eb09ea8068112eea3965`的原矩阵因reset墙秒超额FAIL，原26角色通过；随后同runtime独立reset补4、deadline补8，新的38角色资格通过，原矩阵FAIL不改。fresh16 minimum出现tb3整段累计路径>.0078的真实模型FAIL，整轮ineligible、0更新，49保存身份gone；pilot与验证未启动。原非必需逐回合覆盖FAIL和pooled覆盖PASS仍保留。
V13当时三份活动robot YAML明确统一Shim/DWB/behavior/recovery/smoother双向角上限.3、起转加速1.0；
行为最小角速.15，角减速-3.2、线.20/±.5不变。该轮温和参数profile未改原driver/SDF/轮加速1.0及当时十个ELF；V15后来新增feed并重新build，不能套用本节ELF不变声明。
V13原数学.8命令上界、1.2实测角速、.01 rest speed/.0078累计drift及95%/300秒任务门不放宽；V15显式新profile另依新契约，不重判该轮FAIL。
exact参数reader选择typed部署事实，保留原9live服务及原reader字节；参数读回不替代身体运动、停止和任务门。
准确来源、已完成的8500+100+900续接和minimum失败见[V13](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261019_mr3_p2a_v13.md)。
累计34000已获批准，完整工程收费31596.4775930946018，余2403.5224069053982。最小链失败后不重跑原矩阵/旧run-id、不进入pilot。V13关闭时新模型尚处CPU/math评审；后续V14已获用户接受，V15已实现显式工程入口和CPU/build准备，但完整新资格及原生预算扩额尚未就绪/获批。

## MR3-P2A V9 真实WORLD odometry时序（已关闭历史入口）

V9冻结的adapter驱动曾使用`mr3_odometry_period_ns=20000000`真实发布WORLD odometry及同源TF；该历史参数已由V12固定模式取代，
轮执行器仍原30Hz。非空adapter audit路径同时启动只读`mr3_odometry_recorder`，worker等待三台各odom/驱动TF
实际接收ready；baseline空配置保持旧耦合发布。该默认组件变化须新冻结近身采集及四阶段工程复验，
V9当时未取得新的原生PASS；不作为后来V13状态说明。准确预声明argv与单次preflight/trace/matrix入口见[V9报告执行段](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261019_mr3_p2a_v9.md)。工程刺激默认空，正常矩阵/训练必须清除`MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE`
和plant arm。新入口、真实墙秒截止、38项必需角色及预算见[V9预声明](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261019_mr3_p2a_v9.md)。

## MR3-P2A V8 已关闭原生诊断（历史入口，不重跑）

2026-10-19用户批准累计30000工程墙秒。V8同冻结两臂已完成，刺激VALID/关闭PASS，原V7反例未复现；以下命令仅保留追溯，不重跑已有run-id。V7 FAIL和pilot余额不变。新增`mr3_plant_stimulus_arm`默认空，仅`continuous|pulse`启用固定open101三机稀疏布局与tb3真正smoother工程输入；不要用于正常训练/评估。普通adapter的目标、timer、安全门及出生位置保持原行为。完整预声明、有效性门和预算见[V8报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261019_mr3_p2a_v8.md)。

在conda ns3gym、`PYTHONNOUSERSITE=1`、wireless-rl目录，从新clean+pushed冻结使用单次新run-id：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.plant_probe --arm continuous --run-id mr3_p2a_v8_continuous --physics-config /tmp/mr3_p2a_v8_continuous_physics.json --domain 180 --port 14001
```

config必须预先绑定该run的唯一未来episode路径、当前原生observer库/源码SHA、v2 `observer_only`和原world；不加载旧profile。连续臂完整独立刺激审计与严格关闭通过后才允许pulse arm，准确命令/冻结由本版preflight记录。两arm各1800墙秒，全部实际成本计入累计余额，刺激不足也不重试。诊断结果不代替新冻结完整受影响矩阵、新PPO最小链或95%任务。

## MR3-P2A V7 历史入口（最小链科学门FAIL，pilot/验证SKIP）

2026-10-18已验收P2A.0。V7在8d7f19fc8执行最小链16决策/8更新/702.565秒，但转向模型科学门FAIL；原两份审计保留，pilot及验证未执行。以下仅保留原命令供追溯，不重启旧run-id、不代用工程final。后续代码保护未获新原生信用；2026-10-19用户已批准工程累计30000墙秒，pilot/验证不扩额。
使用下文conda `ns3gym`环境和wireless-rl目录；保留`PYTHONNOUSERSITE=1`、unset PYTHONPATH，ROS子进程仍system Python。
[预声明](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a_v7/predeclared_plan_v7.json)与
[本版结果](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261018_mr3_p2a_v7.md)记录同冻结和所有失败。
不重复V26矩阵，不加载工程模型进pilot。先16/900工程最小链，再fresh pilot；任一基础设施错误停止且不重试。

```bash
python -m mr3_learning.ppo --mode train --workers 1 --schedule open:101 \
  --decisions 16 --episode-steps 16 --wall-seconds 900 --seed 41 \
  --base-domain 180 --base-port 14001 --run-id mr3_p2a_v7_minimal

python -m mr3_learning.ppo --mode train --workers 2 --schedule open:101 \
  --decisions 1870 --episode-steps 64 --wall-seconds 2100 --seed 41 \
  --base-domain 182 --base-port 14011 --run-id mr3_p2a_v7_pilot
```

每个run后对实际目录运行两项只读审计，输出使用新文件名；完整原生/奖励/概率/GAE及收到的地图/活动/执行链均须通过。

```bash
python -m mr3_learning.audit_ppo RUN_DIRECTORY --freeze EXACT40 --output NEW_FULL_AUDIT.json
python -m mr3_learning.audit_policy_inputs RUN_DIRECTORY --freeze EXACT40 --output NEW_INPUT_AUDIT.json
```

64步仅为外部采集截断，不更改95%/300秒任务；关闭后一次bootstrap，不声明完整长回合训练等价或任务成功。
pilot采集软限2100墙秒，原余额2905.9547395464029中的805.9547395464029预留在途请求/关闭/保存；实际总墙秒完整扣费。
只有pilot正常闭合、两项审计通过且本次final.zip有限，才允许原三场完整开发验证（否则SKIP）：

```bash
python -m mr3_learning.ppo --mode evaluate --workers 4 \
  --checkpoint /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v7_pilot/final.zip \
  --schedule open:401,open:402,open:403 --decisions 900 --episode-steps 300 \
  --wall-seconds 9000 --seed 41 --base-domain 186 --base-port 14021 \
  --run-id mr3_p2a_v7_validation
```

验证同样执行上面两项审计；仅本次final、确定性mask-aware、0更新，所有失败保留。未达95%出口停P2A，不进入P2B。

## MR3-P2A.0 第一版历史命令（保留失败，不重跑）

实际在`f8694025`执行：terminal完整审计PASS，reset保留1次真实peer安全失败、3次外部截断，
整体benchmark/完整审计FAIL；deadline命令未执行（SKIPPED）。本步出口未达，停留待复核。
以下保留原预声明命令，不授权自动重跑或执行已跳过的deadline；新修复需新冻结/预声明。

2026-10-17用户授权继续解决P2A并允许前置准备。本轮先验证SLAM生命周期、候选v4、
失败采样保存和安全触发诊断；全部为脚本工程检查，无policy训练/GPU更新。
先按上文系统ROS构建并source当前install；学习端按P1C段激活`ns3gym`并清除`PYTHONPATH`。
只在同一干净已提交推送冻结运行，逐项审计通过才执行下一项；失败停止，不自动重试。
输出与预声明见[P2A.0报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261017_mr3_p2a0.md)。

```bash
MR3_P2A0_FREEZE=$(git rev-parse HEAD)
python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 \
  --steps 4 --terminal-probe --base-domain 180 --base-port 12401 \
  --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 \
  --run-id mr3_p2a0_20261017_terminal
python -m mr3_learning.audit_preparation \
  /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_terminal \
  --freeze "$MR3_P2A0_FREEZE" --output /tmp/mr3_p2a0_terminal_audit.json

python -m mr3_learning.benchmark --workers 2 --schedule open:101,open:101 \
  --steps 16 --base-domain 184 --base-port 12411 \
  --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 \
  --run-id mr3_p2a0_20261017_reset
python -m mr3_learning.audit_preparation \
  /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_reset \
  --freeze "$MR3_P2A0_FREEZE" --output /tmp/mr3_p2a0_reset_audit.json

python -m mr3_learning.benchmark --workers 1 --schedule open:101 \
  --steps 300 --deadline-probe --base-domain 188 --base-port 12421 \
  --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 \
  --run-id mr3_p2a0_20261017_deadline
python -m mr3_learning.audit_preparation \
  /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_deadline \
  --freeze "$MR3_P2A0_FREEZE" --output /tmp/mr3_p2a0_deadline_audit.json
```

源文件/规则/配置由新审计入口精确绑定，旧W7门禁原件不修改。372API/371真实脚本决策为总上限，
工程成本单列，不使用/重置pilot余额。每worker始终三台；300秒KEEP用于截止与关闭验证，
不证明探索或三台参与成功。旧版原件保持；用户随后要求继续完成P2A.0，新版见下节。

## MR3-P2A.0 v12 历史训练前工程命令（失败保留，不重跑）

实际冻结`6b1b4a010835`的interface/terminal全部正式门通过；reset活动、实测速度/持续停止和driver数值门FAIL，deadline跳过。下面命令保留用于追溯；继续修复后新冻结完整重验，不能照此重试旧失败版。

v1至v9失败及原件保留，详见 dated reports。当前导航合成own已知权威/shared补unknown、候选`mr3-navigation-geometric-staging-v5`、快照v3/张量v2及71列活动观测延续。实际速度链为controller/behavior→`cmd_vel_nav`→smoother→`cmd_vel_unguarded`→唯一`motion_safety`→`cmd_vel`。受控每20ms暂停完成state实际发布→peer实际接收/障碍发布→guard实际回收→三台native目标存储后才推进。三机实际Nav2配置和安全门的角速度指令上限均为`.8rad/s`，测量门仍为`1.2rad/s`；精确一ULP规范、完整转向复验及保守停止包络延续。

当前model显式使用本包`libmr3_gazebo_diff_drive.so`，只改轮指令反馈算法，物理参数保持。audit启用时保存实际spawn的三份SDF及drive_tbN.jsonl，不能用未构建的系统插件替代。

系统ROS环境先在canonical ROS目录构建并source当前install：

```bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
/usr/bin/python3 /usr/bin/colcon build --symlink-install \
  --packages-select merge_map multi_robot_exploration multi_robot
source install/setup.bash
```

adapter唯一guard发布tagged target，driver实际存储后回执，worker核对三台exactclock/seq/value；Twist仍观察，baseline显式Twist模式。原paired轮模型、四编译源/库、所有机体门保持。条件静止转向原每个body margin≥.1518m及整段漂移须独立核验。新增显式因果提交修复暂停期间定时发布饥饿，隔离`information_states.jsonl`、`peer_phase.jsonl`和控制账本逐实际callback核验。工程与训练结果审计共用唯一零bootstrap的受限版本入口，不改变真实任务release或原整数物理数学；本轮没有训练信用。

再按P1C段激活conda `ns3gym`，仅在下面wireless-rl目录执行Python入口；ROS子进程仍使用system ROS Python。只在一个干净且已提交推送、完成源码和installed路径核验的冻结运行。interface通过后才开始terminal，再完整reset，最后deadline；每阶段完整审计通过再前进。上限608 API/596脚本动作、18000墙秒，无原生GPU/optimizer；pilot余额不动。真实失败保留并停止该版后续阶段，修复后新冻结/新预声明重验，不拼PASS。详见[v12报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261017_mr3_p2a0_v12.md)。

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
unset PYTHONPATH
export PYTHONNOUSERSITE=1
MR3_P2A0_V12_FREEZE=$(git rev-parse HEAD)
python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_buildproof_preflight.py
python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_launch_stage.py interface "$MR3_P2A0_V12_FREEZE"
python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_audit_stage.py interface "$MR3_P2A0_V12_FREEZE"

python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_launch_stage.py terminal "$MR3_P2A0_V12_FREEZE"
python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_audit_stage.py terminal "$MR3_P2A0_V12_FREEZE"

python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_launch_stage.py reset "$MR3_P2A0_V12_FREEZE"
python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_audit_stage.py reset "$MR3_P2A0_V12_FREEZE"

python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_launch_stage.py deadline "$MR3_P2A0_V12_FREEZE"
python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_audit_stage.py deadline "$MR3_P2A0_V12_FREEZE"

```

上述native入口使用[预声明launcher](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v12/predeclared_plan_v12.json)的精确命令与累计预算，不直接绕过它调用benchmark。`audit_preparation`只是完整门中的一项；interface须补齐full/input/driver/angular/physical/settled/closure及information并新增peer/control精确独立回执；准确清单以本版预声明为准，全部`passed=true`才允许下一stage。各文件名与调用模板在预声明中，真实FAIL或缺件都拒绝继续；不能手写PASS。preflight仅在同一clean+pushed冻结创建新`/tmp`凭据，不覆盖旧凭据。

interface的`--preparation-parameter-review`只读固定、源码绑定的九节点参数脚本；使用原native metadata声明并经canonical profile/Git字节核验的相同loopback UDP配置；reset返回后、首step前物理保持暂停，失败走严格关闭。原件`actual_nav2_parameters.json`保存在episode目录。interface还须通过冻结独立angular消费者及至少一次实际settled-turn触发、完整持续漂移审计；所有阶段driver消费门保持。reset须通过冻结独立物理matrix及所有触发漂移段；规则和脚本SHA见预声明资产。

`--preparation-motion-probe --preparation-probe-version mr3-p2a0-outward-cancel-v3`为32步外部工程输入：GOAL[0,1.5)/[13,15)、WAIT[10,13)/[28,32)，其余KEEP；第二GOAL优先首阶段实际received转向符号的反向合法目标机会，不保证实际反向响应。旧v2仍20步，不能混用。三台每轮均需合法GOAL、原生接受及received路径>.05m，首失败共享标志阻止后续调用而不补造终态。该脚本不是生产探索策略或fallback。terminal/deadline没有95%/参与信用；完成后待用户验收P2A.0。

受控stepped在暂停中以state_phase→peer_phase→motion control→三台storage显式提交，状态有效50Hz；非受控10Hz保持。独立zero-stop同clock更高序号仅三零、不覆normal ACK；启动invalid也走实际cancel/Nav2/native有序关闭。所有原源龄/任务/机体安全门不变。

## MR3-P2A联合MaskablePPO（v6历史命令，本轮不重启pilot）

在上方conda `ns3gym`环境、wireless-rl目录执行；保持`PYTHONNOUSERSITE=1`与ROS解释器隔离。
安装锁定学习依赖不会替换现有CUDA栈：

```bash
python -m pip install -r mr3_learning/requirements-ppo.txt
```

仅在干净、已提交推送的新冻结运行，每次唯一run-id。完整episode闭合之后才更新，掩码随rollout保存；
零时长无动作尾通知归并到此前真实决策，不产生伪actor样本。预算与出口见
[PPO契约](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_PPO_CONTRACT.md)。
当前为v6评价器逐20tick暂停相位ACK修订；原生候选/地图/导航及gamma=lambda=1保持，
不放宽20ms终态检测或任务/安全门禁。每个暂停量子必须等评价器同executor确认精确clock/冻结终态，
不是P3生产端/DDS完整因果时钟证明。下列已执行历史命令与[v6原预声明计划](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261016_mr3_p2a/predeclared_plan_v6.json)一致；前三项已在af37冻结执行，验证项SKIPPED。旧run-id拒绝覆盖，这里不授权重跑。
v5最小链16/4更新完整审计PASS；pilot三round797保存样本/48更新，全16尝试876原生/875返回、
5212.525802815799墙秒，3次原生成功记录及全部失败/前缀保留。最后自动触发终态40ms滞后
超过20ms门禁的基础设施错误，原完整审计FAIL，无final.zip，原声明开发验证SKIPPED，不替换早期权重。
原4096/14400 pilot扣v2的390/1752.957494、v4的242/1051.054936、v5的876/5212.525803，
v6声明时余2588/6383.461767、选2588/6300。实际probe8API/7脚本决策和最小链16决策/4更新审计PASS；
pilot718原生/717返回、3477.507027802989墙秒、0保存round/0更新，tb1 SLAM有序SIGINT后karto::Exception/exit -6，
严格关闭失败且Gazebo stop CLI未启动，表层identity missing；原完整八项FAIL保留，具体SDK throw/stack未知。
无final/checkpoint0000/rollout0000，三场开发验证SKIPPED，不代用早期/其他版本/工程权重。
累计pilot已用2226/约11494.045260453597，余1870/约2905.954739546403；用户确认原累计4096/4小时，
未花不重置、不自动用。本session按无重试infra规则停止P2A，不自动重试/v7或进入P2B。
工程probe/最小链和固定开发验证单列，无额外observer运行。
先terminal-probe的native/scalar/phase-ACK审计PASS，再全新最小链完整审计PASS，才从新权重跑pilot。
phase审计由学习端独立模块重放物理和评价器/worker回执并随完整审计执行，无单独虚构CLI；
保留原20ms/contact/command/scalar/W7门禁及协议v2原FAIL/严格detached重放，scope不扩成all-producer drain。
普通episode上限300步，最后quota/墙时尾段明确外部截断、只bootstrap一次；真实terminated才为无bootstrap MC。
学习seed41与taskseed不同：所有open任务同world/任务几何/固定起点/yaw0，仅Gazebo随机种子变化。

```bash
python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 \
  --steps 4 --terminal-probe --base-domain 156 --base-port 12291 \
  --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo \
  --run-id mr3_p2a_v6_phase_terminal

python -m mr3_learning.ppo --mode train --workers 1 --schedule open:101 \
  --decisions 16 --episode-steps 16 --wall-seconds 900 --seed 41 \
  --base-domain 160 --base-port 12301 --run-id mr3_p2a_v6_minimal

python -m mr3_learning.ppo --mode train --workers 4 --schedule open:101 \
  --decisions 2588 --episode-steps 300 --wall-seconds 6300 --seed 41 \
  --base-domain 164 --base-port 12311 --run-id mr3_p2a_v6_pilot

```

以下是原预声明且未执行的验证命令，因缺final.zip已SKIPPED，不可直接运行：

```bash
python -m mr3_learning.ppo --mode evaluate --workers 4 \
  --checkpoint /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot/final.zip \
  --schedule open:401,open:402,open:403 \
  --decisions 900 --episode-steps 300 --wall-seconds 9000 --seed 41 \
  --base-domain 172 --base-port 12321 --run-id mr3_p2a_v6_validation
```

学习端使用cuda:0（可显式`--device cpu`）；每worker始终三台。
输出为`log/mr3_ppo/<run-id>/`；SB3指标写`sb3_metrics/progress.json`，collector实时状态单独写根`progress.json`。
包含metadata、原生进程/任务原件、张量/掩码rollout、
采样概率、PPO指标、checkpoint和SHA、完整失败/中断。`completed`只表示run的采集/更新闭合，
95%任务成功仍由原生schema4独立判断。本次phase/minimum已PASS但pilot infra失败，不能将工程通过当任务成功；
仅pilot无基础设施错误且有有限final.zip时执行final-only验证，否则SKIP、不替换checkpoint；
本次停在P2A，未接网/进入P2B；[闭合记账](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261016_mr3_p2a/v6_closure_accounting.json)及[预算记录](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261016_mr3_p2a/budget_acceptance_20261016.json)保留全部成本。
v3候选规则为`mr3-per-robot-geometric-staging-v3`，路径机体净空仍为`.29m`，
目标到达圆盘要求`.39m`；各台已交付本地图保留几何代表项，不能用真值或手工目标兜底。
主launch实际读取`src/multi_robot/params/nav2_params_tb1_0.yaml`至`tb3_0.yaml`，
三份GoalChecker和DWB的`xy_goal_tolerance`均为`.10m`，yaw仍3.14；
`params/turtlebot3_params/`内的同名文件不是该launch当前输入。
主launch包含的SLAM入口读取`src/slam_toolbox/config/mapper_params_online_multi_async.yaml`，
运动阈值为`.10m/.20rad`，ROS时间节流`.5s`与地图更新5s不变，C++/Karto实现未改。
这些参数也影响同冻结baseline；历史P1A/P1B/P1C和v1/v2结果不能归入此新执行版本。

## 已有 90% 工程评估（不验收 MR3 的 95% 任务）

```bash
MR3_RUN_ID=mr3_frontier90_$(date +%Y%m%d_%H%M%S)
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=3 world:=p1c_rooms.world gazebo_seed:=101 \
  enable_gzclient:=false enable_rviz:=false enable_merge_rviz:=false \
  auto_save_map:=false enable_task_evaluator:=true \
  evaluation_episode_id:=$MR3_RUN_ID \
  evaluation_output_dir:=/tmp/$MR3_RUN_ID \
  evaluation_duration_sec:=180.0 evaluation_coverage_threshold:=0.90
```

每次使用新 episode id/目录，拒绝覆盖旧结果。schema3 在截止之前达标、接触 topic 记录为零、
每台碰撞监测有消息、无控制失败才成功。schema3只读取 `base_collision`，不能证明
全机体零非支撑接触；其监测门禁也不等于持续新鲜度证明。全机体门禁使用下面的schema4。
评估器完成默认先请求本launch的Gazebo原生停止，等待真实server退出后关闭其余节点；
结果冻结且检查原生子进程，父进程0不能掩盖 abort。
`stop_on_evaluation_complete:=false` 仅用于人工诊断。

把阈值改0.95并不自动完成 MR3-P1A：需先验证任务 ROI、真值几何、质量和95%可达性，
并预声明任务预算/新schema。不要把旧90%/180秒结果、或95%配置本身写成新任务成功。

## MR3-P1A 合同评估与传统开发矩阵

P1A合同模式为schema4，真值/世界哈希、完整ROI、95%/300仿真秒、地图质量、三台参与、
18个组件持续接触监测和导航终态闭合共同决定成功。详细口径见
[MR3_TASK_CONTRACT.md](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_TASK_CONTRACT.md)。
以下为实际已实现入口；原生验证结果仍以P1A报告为准。
合同launch自动启动C++ `mr3_contact_reducer`。18条原始接触消息仍保留，汇总输出为
`/mr3_contacts/tbN/<component>`；只合并同一消息中重复的碰撞对，保留原header和
每对首次完整几何样本，原样本数量保存在state.info。生产20Hz和0.5仿真秒源龄/接收龄
门限不变。原始发布端和汇总节点使用可靠的100条历史，防止启动负载下仅5条历史
被覆盖；该改动是否消除缺口以新冻结原生结果为准。原始消息序列缺口、无法审计或
多个源发布者锁存为失败。runner在任务退出后还核查唯一18路汇总、逐条输入/输出、
完整序列和原生子进程；原生JSON成功不能掩盖基础设施失败。

P1A smoke/baseline在任何ROS命令或初始化之前自动应用下面的同主机UDP-only环境，
并在metadata的 `transport_environment` 记录所选变量和 `profile_sha256`。
手动直接启动合同launch时先在已source上述ROS/Gazebo环境的终端执行：

```bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=0
export FASTRTPS_DEFAULT_PROFILES_FILE="$PWD/src/multi_robot/config/mr3_fastdds_loopback_udp.xml"
export SKIP_DEFAULT_XML=1
unset FASTDDS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML RMW_FASTRTPS_PUBLICATION_MODE
export ROS_DOMAIN_ID=98 GAZEBO_MASTER_URI=http://127.0.0.1:11861
```

XML关闭内建transport，仅启用白名单为127.0.0.1的UDPv4；没有更改socket缓冲或
UDP transport的默认发送阻塞方式。`ROS_LOCALHOST_ONLY=0` 由显式loopback白名单约束通信范围，
`SKIP_DEFAULT_XML=1` 只阻止工作目录的默认XML覆盖显式profile，仍加载上方指定文件。
legacy入口不会自动改为此环境；重新打开终端并使用前面的历史profile可复现其原环境。
P1A第六版冻结时另为三台各六个Nav2节点的 `change_state` 响应writer配置精确命名profile：
`rr/tbN/NODE/change_stateReply`，共18项；NODE为 `controller_server`、`planner_server`、
`behavior_server`、`bt_navigator`、`waypoint_follower`、`velocity_smoother`。
只将这些response writer的reliability `max_blocking_time` 从默认100ms改为5墙秒，
为启动时响应writer等待对应reader匹配提供有界窗口，也约束这些writer的DDS写入阻塞；
它不按ROS仿真时钟计时。没有新增Nav2 transition重试，也没有改变其无超时future等待；
reader匹配为何延迟、客户端为何可能一直等待的根因仍未解决。
profile只绑定这些命名writer，不随启动阶段结束而撤销；不设置默认writer、service-wide
fallback或reader配置；P1A原冻结的contact/control、get_state及request writer保持原有QoS。
P1C W7保留同三台六节点的18个精确`rr/tbN/NODE/get_stateReply`配置1墙秒
匹配/写入等待（默认100ms），低于安装版Nav2 `get_state`客户端原2墙秒超时，后者不变。
新增规则不改变request/data/contact端点、频率或任务门槛；实际失败仍按infra保留，不自动重试。
这是有界发现等待的应用配置，不宣称修复DDS内部发现竞态；W7完整矩阵仅提供其实际工程范围。
P1A旧报告/原件仍只对应其冻结18项change_state规则，不能赋予新配置结果信用。
`RMW_FASTRTPS_USE_QOS_FROM_XML` 继续unset，ROS端点QoS转换仍保留该max-blocking字段。
静态SDK/RMW验证另列为
[证据](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/lifecycle_reply_qos_v6_static_proof.json)，
不代表实际启动已通过；配置是否改善响应问题仍以新冻结
原生结果为准，不宣称已证明SHM或abort根因。300墙秒启动、300仿真秒任务、95%及
.5仿真秒接触健康门禁均不变，控制策略与物理参数未改。

```bash
MR3_BATCH_ID=mr3_p1a_rooms_$(date +%Y%m%d_%H%M%S)
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_ideal_baseline.py \
  --world p1c_rooms.world --robot-count 3 --seeds 101 202 303 \
  --task-contract src/multi_robot/config/mr3_p1a/rooms.json \
  --startup-timeout 300 --evaluation-wait-timeout 900 --run-id $MR3_BATCH_ID
```

open/corridors使用对应world与 `open.json` / `corridors.json`，每次新run-id。
评估器等待有效正ROS仿真时钟，再一次建立18路接触订阅；此后收到的所有放行前
接触保留，18路持续新鲜且无非支撑接触才可放行。这不覆盖订阅建立之前的每个历史
触碰。未来消息先按当前时钟排水，真正未来队列超过256条立即失败并记录诊断；
不改源时间戳或.5秒门限。任务提前结束时，runner优先读取原生JSON并审计退出，
不继续等待已经消失的topic。300墙秒约束Nav2/ROS就绪，后续时钟/监测等待仍由
900墙秒评估保护约束。
P1A第六版按rooms、corridors、open逐场景串行执行，每场景内部也串行重启三种子。
第六版计划使用独立ROS域98/99/100与Gazebo端口11861/11862/11863；保持所有任务与墙钟保护门限。
这用于减少并发启动压力，不表示一次Nav2响应超时的根因已经确定。精确预声明见
[native plan](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/predeclared_native_plan.json)。
冻结`5e47802`累计10次尝试含1次保留的原生基础设施失败，得到9个有效单元；结果见
[P1A报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_p1a.md)。
合同确定任务300仿真秒，300/900墙秒分别是启动/基础设施保护，不能当成延长任务。
参数与合同显式冲突会拒绝。任务t0为控制器仿真时间放行；启动预热地图单列，达标后的
取消闭合计入任务截止。合同模式不接受两/四台、schema3或曾中断的监测作为成功。
`my_world`暂不提供95%合同；validation/test/confirmation布局本步不运行。

默认 `stop_on_evaluation_complete:=true` 时，评估器退出后launch向记录的owned
gzserver环境（包括实际 `GAZEBO_MASTER_URI`）执行
`gz topic -p /gazebo/server/control -m "stop: true"`。
必须同时观察同一启动action、PID和进程名的server退出0及stop CLI退出0，才关闭其余节点；
两者可任意先后，CLI退出0不等于server已停止。10墙秒仍未收到任一必要退出事件则输出
`MR3_GAZEBO_NATIVE_STOP_ERROR` 并兜底关闭；CLI失败或server非零退出也保留错误标记和
真实子进程退出码。runner把该标记判为基础设施失败，即使之后CLI/server退出0；
SIGABRT等真实失败不会被屏蔽。有效任务失败或无效JSON也先等待同一原生关闭流程，
然后保留原失败结果。该关闭保护不改变300仿真秒任务预算。
`stop_on_evaluation_complete:=false` 不发出原生stop请求，供人工诊断。

## 当前自动检查与传统批量入口

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/ros_smoke_test.py \
  --robot-count 3 --world p1c_rooms.world --gazebo-seed 101 --startup-timeout 300

MR3_BATCH_ID=mr3_frontier90_batch_$(date +%Y%m%d_%H%M%S)
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_ideal_baseline.py \
  --world p1c_rooms.world --robot-count 3 --seeds 101 202 303 \
  --duration 180 --coverage-threshold 0.90 --startup-timeout 300 \
  --evaluation-wait-timeout 360 --run-id $MR3_BATCH_ID
```

这只是可执行示例，本轮未执行。smoke 是启动/消息/关闭检查，任务结果另列。
runner 对任务或基础设施失败返回非零；启动保护是墙钟，任务预算是仿真时间。
所有正式检查也属于实验，必须追加共享 [log.md](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/log.md)，包括失败、冻结提交、
完整命令、seed、环境、原件路径和结论，不自动覆盖或继承旧 run-id。

Nav2 接受/取消终态默认期限为10仿真秒，对应
`navigation_response_timeout_sec` / `navigation_cancel_timeout_sec`；当前目标上限
`exploration_goal_timeout_sec:=60.0`。这不是未来 Wi-Fi 命令 TTL 的现成实现。

## 故障诊断和证据

先确认生命周期、TF/map frame、最新 scan/odom、原生日志和自己的残留进程。
若原生日志显示 FastDDS 生命周期响应发送超时，停止本次实验后可用安装的官方工具
清理失效共享内存；工具会检查锁并保留在用资源：

```bash
/usr/bin/python3 /opt/ros/humble/tools/fastdds/fastdds.py shm clean
```

不使用无范围 pkill 或手工删除所有 DDS 段。清理后新 run-id 复测，原失败保持。
该工具不是已证明的所有时序故障修复方法。

运行源码 `c9344e1` 的最近三机器人90%工程结果为 rooms60.2s、corridors81.9s，seed101，
180仿真秒上限、基体接触记录为零、原生干净退出；未重跑完整多种子矩阵或95%任务。
详见 [工程修复报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261013_p1c_engineering_repair.md)。

## MR3-P2A.0 v13 已关闭失败的工程准备

V13冻结`1cfe74b4ad32`在首个参数服务响应reader匹配超时处FAIL，1reset/0step；后三stage均SKIP。下列保留原声明，不自动重跑。V12失败原件保留。V13实际三份参数启用Rotation Shim→原DWB；命令线速度.20、角.8，DWB与smoother线加减速度±.5/角±3.2。通用配置保持DWB但同步命令与加速度。WORLD里程计、SDF、实测.30/1.2、停止.78秒/.144米、任务95%/300秒/参与及接触门均不放宽。fullnorm模型不符的normal commit返回明确负ACK，沿原abort_cleanup清理，数据禁止训练；不改正常state→peer→motion→storage→evaluator顺序。

先按上文system ROS环境构建实际库（本版helper与target header已变，必须重新configure以嵌入4源码摘要）：

```bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
/usr/bin/python3 /usr/bin/colcon build --symlink-install --allow-overriding nav2_bringup --packages-select multi_robot multi_robot_exploration --cmake-force-configure --cmake-args -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
source install/setup.bash
```

再按P1C段进入conda ns3gym，仅在wireless-rl调用下列入口；ROS child仍system Python。源码、实际新库、独立回执与预声明全部钉住、通过离线检查并clean commit/push后才能启动。源码离线准入已打开；实际40位冻结仅由推送后的preflight解析，不能把CPU检查当作原生通过。仅同一个freeze逐stage全部mandatory通过才可下一stage，首FAIL停止后续；预算608API/596动作/18000原生墙秒，不启动PPO/GPU/optimizer或pilot。

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export MR3_P2A0_V13_FREEZE="$(git rev-parse HEAD)"
python report/assets/20261017_mr3_p2a0_v13/independent/mr3_p2a0_v13_buildproof_preflight.py
/usr/bin/python3 report/assets/20261017_mr3_p2a0_v13/independent/mr3_p2a0_v13_cross_stage_mapping_monitor_v1.py --freeze "$MR3_P2A0_V13_FREEZE" > /tmp/mr3_p2a0_v13_cross_stage_mapping_console.log 2>&1 &
python report/assets/20261017_mr3_p2a0_v13/independent/mr3_p2a0_v13_launch_stage.py interface "$MR3_P2A0_V13_FREEZE"
python report/assets/20261017_mr3_p2a0_v13/independent/mr3_p2a0_v13_audit_stage.py interface "$MR3_P2A0_V13_FREEZE"
python report/assets/20261017_mr3_p2a0_v13/independent/mr3_p2a0_v13_launch_stage.py terminal "$MR3_P2A0_V13_FREEZE"
python report/assets/20261017_mr3_p2a0_v13/independent/mr3_p2a0_v13_audit_stage.py terminal "$MR3_P2A0_V13_FREEZE"
python report/assets/20261017_mr3_p2a0_v13/independent/mr3_p2a0_v13_launch_stage.py reset "$MR3_P2A0_V13_FREEZE"
python report/assets/20261017_mr3_p2a0_v13/independent/mr3_p2a0_v13_audit_stage.py reset "$MR3_P2A0_V13_FREEZE"
python report/assets/20261017_mr3_p2a0_v13/independent/mr3_p2a0_v13_launch_stage.py deadline "$MR3_P2A0_V13_FREEZE"
python report/assets/20261017_mr3_p2a0_v13/independent/mr3_p2a0_v13_audit_stage.py deadline "$MR3_P2A0_V13_FREEZE"
```

上面的每一个audit入口包括完整原门和独立consumer，不直接绕过launcher调用benchmark。新drive v6先完整调用旧V5/V4严格数学/源/时延/停止验证，再附加最终guard、target与native实用值的精确.20/.8硬界。参数readback仍在首次动作前对9实际节点只读查询；插件映射原件证明实际加载身份，均不能代替身体运动/停止核验。脚本v3仅外部工程刺激，不是探索fallback。结果及限制见[V13报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261017_mr3_p2a0_v13.md)。完成本步后待用户验收，不自动训练。

## MR3-P2A.0 V14 已关闭失败的参数服务修复

V14冻结`aa16d6541ef54a9c676e78367ba8a8b13c2589b9`已执行interface32步，九参数与严格关闭通过，peer/control实际几何回归及停止覆盖FAIL，后三stage SKIP。下列为已执行声明，不自动重跑。须解耦导航peer bound与command cap并修外部取消刺激，再用新冻结完整矩阵。V13完整失败原件已在60f932ed保留。V14仅为三台各controller/behavior/smoother的精确get_parametersReply writer增加1秒匹配/写入等待；旧36规则、30秒client总guard、45秒hook与原任务/身体/停止门保持。实际模型/驱动/运动源码与a014库没有变更，不为XML再次编译驱动；canonical source profile由新ROS child启动加载，成功CPU解析不等于原生应用证明。

以下命令仅在源码/离线核验完成、plan ready、clean commit/push与actual exact40 preflight后运行；root计划ready仍必须实际clean-pushed preflight才准入。先按上文进入conda ns3gym，ROS child仍system Python。四stage逐项全部mandatory通过才前进，任何FAIL保留、后续SKIP，不同freeze不拼接，608API/596动作/18000原生墙秒不变。PPO/GPU/pilot/P2B/gateway不启动。

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export MR3_P2A0_V14_FREEZE="$(git rev-parse HEAD)"
python report/assets/20261017_mr3_p2a0_v14/independent/mr3_p2a0_v14_buildproof_preflight.py
/usr/bin/python3 report/assets/20261017_mr3_p2a0_v14/independent/mr3_p2a0_v14_cross_stage_mapping_monitor_v1.py --freeze "$MR3_P2A0_V14_FREEZE" > /tmp/mr3_p2a0_v14_cross_stage_mapping_console.log 2>&1 &
python report/assets/20261017_mr3_p2a0_v14/independent/mr3_p2a0_v14_launch_stage.py interface "$MR3_P2A0_V14_FREEZE"
python report/assets/20261017_mr3_p2a0_v14/independent/mr3_p2a0_v14_audit_stage.py interface "$MR3_P2A0_V14_FREEZE"
python report/assets/20261017_mr3_p2a0_v14/independent/mr3_p2a0_v14_launch_stage.py terminal "$MR3_P2A0_V14_FREEZE"
python report/assets/20261017_mr3_p2a0_v14/independent/mr3_p2a0_v14_audit_stage.py terminal "$MR3_P2A0_V14_FREEZE"
python report/assets/20261017_mr3_p2a0_v14/independent/mr3_p2a0_v14_launch_stage.py reset "$MR3_P2A0_V14_FREEZE"
python report/assets/20261017_mr3_p2a0_v14/independent/mr3_p2a0_v14_audit_stage.py reset "$MR3_P2A0_V14_FREEZE"
python report/assets/20261017_mr3_p2a0_v14/independent/mr3_p2a0_v14_launch_stage.py deadline "$MR3_P2A0_V14_FREEZE"
python report/assets/20261017_mr3_p2a0_v14/independent/mr3_p2a0_v14_audit_stage.py deadline "$MR3_P2A0_V14_FREEZE"
```

只读mapping wrapper与Shim reader仍复用原A13字节；V14 closure的显式binaryproof路径adapter先核旧SHA，只在review时切换13→14并finally还原，actual argv/typed base/maps门不变。[报告与预声明](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261017_mr3_p2a0_v14.md)记录所有失败和原件；完成全矩阵及证据commit/push后等用户P2A.0验收。

## MR3-P2A.0 V15 完整准备矩阵（已关闭失败）

V14失败原件已封存于f7376d02。V15导航peer预测界独立为原`.26`，命令仍`.20/.8`；V4/32外部刺激只读received snapshot和原mask，在运动且WAIT合法时取消，实际step返回并绑定command后才锁存，保留5秒承诺。初次WAIT至少3秒且fresh idle/received速度代理合格后才准第二GOAL；原raw物理、A/B分报、角速度/接触/实际关闭门保持。旧V2/V3可复现，无生产探索兜底。代码及离线回归不能替代同冻结原生通过。

以下保留实际V15入口供复核；冻结17ef3cb212aa已在interface活动/停止覆盖门FAIL并关闭，terminal/reset/deadline SKIP，禁止重跑该冻结。原实际串行父编排按以下原生入口及其完整审计执行；每阶段全部mandatory通过才允许下一阶段，真实失败保留并跳过后续，不自动同版重试。被动mapping观察器只读实际进程并随父编排ledger自然结束。预算仍608 API/596动作/18000原生墙秒，无原生GPU/PPO/pilot。

```bash
# cwd: wireless-rl；先按P1C段激活conda ns3gym并保持PYTHONNOUSERSITE=1
unset PYTHONPATH
export PYTHONDONTWRITEBYTECODE=1
export MR3_P2A0_V15_FREEZE="$(git rev-parse HEAD)"
python report/assets/20261017_mr3_p2a0_v15/independent/mr3_p2a0_v15_buildproof_preflight.py
/usr/bin/python3 report/assets/20261017_mr3_p2a0_v15/independent/mr3_p2a0_v15_cross_stage_mapping_monitor_v1.py --freeze "$MR3_P2A0_V15_FREEZE" > /tmp/mr3_p2a0_v15_cross_stage_mapping_console.log 2>&1 &
python report/assets/20261017_mr3_p2a0_v15/independent/mr3_p2a0_v15_launch_stage.py interface "$MR3_P2A0_V15_FREEZE"
python report/assets/20261017_mr3_p2a0_v15/independent/mr3_p2a0_v15_audit_stage.py interface "$MR3_P2A0_V15_FREEZE"
python report/assets/20261017_mr3_p2a0_v15/independent/mr3_p2a0_v15_launch_stage.py terminal "$MR3_P2A0_V15_FREEZE"
python report/assets/20261017_mr3_p2a0_v15/independent/mr3_p2a0_v15_audit_stage.py terminal "$MR3_P2A0_V15_FREEZE"
python report/assets/20261017_mr3_p2a0_v15/independent/mr3_p2a0_v15_launch_stage.py reset "$MR3_P2A0_V15_FREEZE"
python report/assets/20261017_mr3_p2a0_v15/independent/mr3_p2a0_v15_audit_stage.py reset "$MR3_P2A0_V15_FREEZE"
python report/assets/20261017_mr3_p2a0_v15/independent/mr3_p2a0_v15_launch_stage.py deadline "$MR3_P2A0_V15_FREEZE"
python report/assets/20261017_mr3_p2a0_v15/independent/mr3_p2a0_v15_audit_stage.py deadline "$MR3_P2A0_V15_FREEZE"
```

新reset包装器仅识别V4/32工作量，归一化版本与文案后AST仍为A8；原physical2516/angular7a472数学、八轮/33条API记录及原pool/活动门不变。原A13 Shim观察/reader及实际a014库复用，V15只在review期间将binaryproof路径13→15并finally恢复。实际命令、失败、限制和结果见[V15报告与预声明](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261017_mr3_p2a0_v15.md)。完成本步并提交推送证据后等待用户验收，不自动启动PPO/P2B/gateway。


## MR3-P2A.0 V16 完整准备矩阵（已关闭失败）

V15失败闭包55da440保持。V5/32仅在V4生命周期及原joint合法子集中筛除直线接近队友的新GOAL，KEEP/WAIT与原5秒承诺、运动取消、3秒首WAIT和typed返回记账保持。原V4默认/旧V2/V3可复现；这是外部工程刺激，无生产探索兜底。两reset包装器只变精确V5 metadata；原每机A或B停止信用、每机一转向段/总体正负/至少一机双向及全部bounds/contacts/严格关闭门保持。

以下保留V16实际入口供复核；冻结ebe7d51b已因interface的tb1制停覆盖FAIL关闭，后三阶段SKIP，禁止重跑该冻结。原串行父编排按下列入口执行；各阶段所有mandatory收齐并PASS才准下一阶段，失败保留并SKIP后续，不同版重试或拼接PASS。被动mapping观察器只读实际进程。预算仍608API/596动作/18000原生墙秒，无PPO/pilot。

```bash
# cwd: wireless-rl；先按P1C段激活conda ns3gym并保持PYTHONNOUSERSITE=1
unset PYTHONPATH
export PYTHONDONTWRITEBYTECODE=1
export MR3_P2A0_V16_FREEZE="$(git rev-parse HEAD)"
python report/assets/20261017_mr3_p2a0_v16/independent/mr3_p2a0_v16_buildproof_preflight.py
/usr/bin/python3 report/assets/20261017_mr3_p2a0_v16/independent/mr3_p2a0_v16_cross_stage_mapping_monitor_v1.py --freeze "$MR3_P2A0_V16_FREEZE" > /tmp/mr3_p2a0_v16_cross_stage_mapping_console.log 2>&1 &
python report/assets/20261017_mr3_p2a0_v16/independent/mr3_p2a0_v16_launch_stage.py interface "$MR3_P2A0_V16_FREEZE"
python report/assets/20261017_mr3_p2a0_v16/independent/mr3_p2a0_v16_audit_stage.py interface "$MR3_P2A0_V16_FREEZE"
python report/assets/20261017_mr3_p2a0_v16/independent/mr3_p2a0_v16_launch_stage.py terminal "$MR3_P2A0_V16_FREEZE"
python report/assets/20261017_mr3_p2a0_v16/independent/mr3_p2a0_v16_audit_stage.py terminal "$MR3_P2A0_V16_FREEZE"
python report/assets/20261017_mr3_p2a0_v16/independent/mr3_p2a0_v16_launch_stage.py reset "$MR3_P2A0_V16_FREEZE"
python report/assets/20261017_mr3_p2a0_v16/independent/mr3_p2a0_v16_audit_stage.py reset "$MR3_P2A0_V16_FREEZE"
python report/assets/20261017_mr3_p2a0_v16/independent/mr3_p2a0_v16_launch_stage.py deadline "$MR3_P2A0_V16_FREEZE"
python report/assets/20261017_mr3_p2a0_v16/independent/mr3_p2a0_v16_audit_stage.py deadline "$MR3_P2A0_V16_FREEZE"
```

原A13实际九参数reader、Shim观察及a014库保持；V16 closure只在核旧SHA后暂时切binaryproof路径13→16并finally还原。准确冻结、原件、所有FAIL及限制见[V16报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261017_mr3_p2a0_v16.md)。完整准备证据提交推送后等待用户P2A.0验收，不自动启动训练/P2B/gateway。


## MR3-P2A.0 V17 完整准备矩阵（已关闭失败，不重跑）

V16失败原件已封存db6410f。外部V6/32增晚目标机会，真实elapsed换算整数ns按[15e9,26e9)分类，保持旧V4/V5默认及原early排名；late只在原joint/lifecycle+V5非接近合法subset用旧outward排序。seed.29/路径/actor mask、5秒承诺、首WAIT3秒及moving/typed实际提交门不变。正常整数25秒最后新GOAL、30秒才可WAIT、32秒前剩2秒只是设计机会，仍须原raw物理/角向/接触/关闭门。没有生产探索兜底。

实际冻结eee6b2f9已完成interface/terminal PASS；reset物理停车FAIL，deadline SKIP，所有进程自然关闭。以下命令只保留原执行入口，不重跑该失败版。新修复须另立冻结和预声明。原串行父编排依次调用以下入口；各阶段全mandatory结束并PASS才准下一阶段，FAIL保留并SKIP后续，不同版重试或拼接PASS。被动mapping观察器只读实际进程。预算仍608API/596动作/18000原生墙秒，无PPO/pilot。

```bash
# cwd: wireless-rl；先按P1C段激活conda ns3gym并保持PYTHONNOUSERSITE=1
unset PYTHONPATH
export PYTHONDONTWRITEBYTECODE=1
export MR3_P2A0_V17_FREEZE="$(git rev-parse HEAD)"
python report/assets/20261017_mr3_p2a0_v17/independent/mr3_p2a0_v17_buildproof_preflight.py
/usr/bin/python3 report/assets/20261017_mr3_p2a0_v17/independent/mr3_p2a0_v17_cross_stage_mapping_monitor_v1.py --freeze "$MR3_P2A0_V17_FREEZE" > /tmp/mr3_p2a0_v17_cross_stage_mapping_console.log 2>&1 &
python report/assets/20261017_mr3_p2a0_v17/independent/mr3_p2a0_v17_launch_stage.py interface "$MR3_P2A0_V17_FREEZE"
python report/assets/20261017_mr3_p2a0_v17/independent/mr3_p2a0_v17_audit_stage.py interface "$MR3_P2A0_V17_FREEZE"
python report/assets/20261017_mr3_p2a0_v17/independent/mr3_p2a0_v17_launch_stage.py terminal "$MR3_P2A0_V17_FREEZE"
python report/assets/20261017_mr3_p2a0_v17/independent/mr3_p2a0_v17_audit_stage.py terminal "$MR3_P2A0_V17_FREEZE"
python report/assets/20261017_mr3_p2a0_v17/independent/mr3_p2a0_v17_launch_stage.py reset "$MR3_P2A0_V17_FREEZE"
python report/assets/20261017_mr3_p2a0_v17/independent/mr3_p2a0_v17_audit_stage.py reset "$MR3_P2A0_V17_FREEZE"
python report/assets/20261017_mr3_p2a0_v17/independent/mr3_p2a0_v17_launch_stage.py deadline "$MR3_P2A0_V17_FREEZE"
python report/assets/20261017_mr3_p2a0_v17/independent/mr3_p2a0_v17_audit_stage.py deadline "$MR3_P2A0_V17_FREEZE"
```

原A13九参数reader、Shim观察及a014库复用；closure只在核旧SHA后暂改binaryproof路径13→17并finally还原。两A17 reset wrapper只变V6/32元数据，raw7a472/2516数学与原pool保持。实际结果/限制见[V17报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261017_mr3_p2a0_v17.md)。完整准备证据提交推送后等待用户验收，不自动启动训练/P2B/gateway。

## P2A.0 V18 隔离停车物理诊断（历史FAIL，不重跑）

V17真实停车响应失败原件保持。V18冻结85abe391实际baseline32与原停车/关闭PASS，但root可执行文件名准入FAIL，
正式1ms consumer及iters150均SKIP，整体FAIL。以下原命令仅保留，不重跑；修复后另立新冻结。
原计划为三机open101两次串行32步物理归因，
先baseline原50 iterations，再显式150；各1800墙秒、总3600，最多2reset/64step/66API。
默认运行不加载诊断库。仅由已审核预声明入口逐命令注入
`MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE`，不要全局export。源码/安装库需先完成系统ROS构建、
清洁提交推送和exact40准入，runner拒绝既有输出及盲重试。

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python \
  report/assets/20261018_mr3_p2a0_v18/independent/mr3_p2a0_v18_preflight_v1.py
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 \
  report/assets/20261018_mr3_p2a0_v18/independent/mr3_p2a0_v18_run_diagnostics_v1.py EXACT40
```

EXACT40必须是预检相同、干净且已推送的实际HEAD；清除学习端PYTHONPATH。两次原始物理门
及1ms观测独立审计全部保留，baseline物理FAIL可作为有效诊断结果比较，基础设施/覆盖/来源
核验失败则后一次SKIP。无PPO、pilot、GPU更新、四阶段或95%任务信用；之后完整矩阵另立新冻结。


## P2A.0 V19：实体准入修复与固定物理对照

V18整体FAIL已封存，不重跑。V19只修独立工具的Gazebo可执行实体/SHA检查；原ROS源码、a014驱动及两诊断库
保持，无需重构建。新三机open101/V6/32固定baseline域154/端口13361、iters150域156/13371；
各1374.5原生墙秒，总2749.0，保留V18已用850.965301560238。全部原物理/停车/任务门不变。
先完成独立复核、clean commit/push与actual exact40预检；诊断环境仅由runner逐命令注入，不全局export。

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python \
  report/assets/20261018_mr3_p2a0_v19/independent/mr3_p2a0_v19_preflight_v1.py
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -u \
  report/assets/20261018_mr3_p2a0_v19/independent/mr3_p2a0_v19_run_diagnostics_v1.py EXACT40
```

EXACT40与实际预检必须相同。固定两个新run仅尝试一次；加载/原生/配置/逐毫秒覆盖/关闭FAIL则后续SKIP，
正确捕获的原物理FAIL仍保留并可比较。不据结果挑样，不用旧PASS拼接，活动期间不改源/库/Git。
这是隔离归因，不是四阶段矩阵或P2A.0通过；之后有依据修复再新冻结完整重验，待用户验收后训练。
详见[V19报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261018_mr3_p2a0_v19.md)。


## MR3-P2A.0 V24 历史失败命令（不重跑）

以下在wireless-rl目录执行；须新代码提交推送、工作树干净并完成源码审查。
先以固定Conda运行真实完整预检：

```bash
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_buildproof_preflight.py
```

通过后将EXACT40替换为本次完整冻结SHA；先启动只读monitor并确认START，再另终端启动唯一parent。

```bash
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_cross_stage_mapping_monitor_v1.py --freeze EXACT40
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_run_matrix_v1.py EXACT40
```

benchmark/完整审计仍由绑定源码使用固定Conda，parent和ROS读者使用系统Python。
新domain198/200/202+203/206、port13701/13711/13721+22/13731；原四阶段/34门/12episode/608 API/596脚本决策保持。
工程18000墙秒累计先扣71.97839368507266，所有native和必需消费者及monitor自然结束前不改源码、库或Git。
失败保留并跳过后续stage，不在同冻结重试。此命令用于训练前工程验收；P2A.0证据提交推送并获用户验收后才进入训练。
原启动/物理/任务门及pilot余额不变，见[V24报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261018_mr3_p2a0_v24_install.md)。


## MR3-P2A.0 V25 历史节点时钟命令（已关闭失败，不重跑）

从官方1.1.20导入的 `src/nav2_velocity_smoother` 由正常 ament overlay 选择。
完整构建须允许覆盖此包；仅构建该包的命令如下（本次已执行，不作为矩阵重试命令）：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
export PYTHONNOUSERSITE=1
/usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select nav2_velocity_smoother --allow-overriding nav2_bringup nav2_velocity_smoother --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DBUILD_TESTING=OFF
source install/setup.bash
```

实际package/launch executable/ldd已核为canonical新库。组件对照只验证timer机制；
随后同冻结实际interface32完成，但新取证035 FAIL，后三阶段SKIP；不能由本构建或局部PASS授予P2A.0完成信用。


以下为已执行的V25历史绑定入口，freeze579f7ad2；本版失败已封存，不再执行。
在wireless-rl目录执行实际学习侧前检：

```bash
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
env -u PYTHONPATH /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261018_mr3_p2a0_v25_smoother/independent/mr3_p2a0_v25_buildproof_preflight.py
```

前检PASS后，在独立终端先启动只读watcher；保存的START回执出现后，在另一个终端
启动唯一parent。两处使用同一clean pushed exact40（下例从HEAD取得）：

```bash
MR3_V25_FREEZE=$(git rev-parse HEAD)
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v25_smoother/independent/mr3_p2a0_v25_cross_stage_mapping_monitor_v1.py --freeze "$MR3_V25_FREEZE"
```

```bash
MR3_V25_FREEZE=$(git rev-parse HEAD)
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v25_smoother/independent/mr3_p2a0_v25_run_matrix_v1.py "$MR3_V25_FREEZE"
```

parent串行执行interface32、terminal2、reset双worker共8x32、deadline300KEEP，原34门
逐stage全部drain；首FAIL阻止后续，累计工程墙秒不重置。源/库/Git须保持到原生、正式
reader和watcher全部自然结束及原件封存。P2A.0实际PASS并获用户验收后才进入训练。


## MR3-P2A.0 V26 历史工程入口（原生已完成，审计补完；不重跑）

以下保留实际冻结92f8bdf5的历史入口。原生四阶段已完成，父编排在离线审计期间中断；最后一个只读消费者另名补验，详见V26报告。不要再次执行这些原生命令。

```bash
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261018_mr3_p2a0_v26_capture/independent/mr3_p2a0_v26_buildproof_preflight.py
```

实际前检PASS后，先在独立终端启动watcher，保存START后在另一终端启动唯一parent：

```bash
MR3_V26_FREEZE=92f8bdf5bba1ba245dc53ca0964eef81a7fff938
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v26_capture/independent/mr3_p2a0_v26_cross_stage_mapping_monitor_v1.py --freeze "$MR3_V26_FREEZE"
```

```bash
MR3_V26_FREEZE=92f8bdf5bba1ba245dc53ca0964eef81a7fff938
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v26_capture/independent/mr3_p2a0_v26_run_matrix_v1.py "$MR3_V26_FREEZE"
```

原四stage、12episode、608API/596脚本动作、34门及额外必需FIFO均保持，累计工程18000墙秒
携带1369.6459453934804；先FAIL后续SKIP。所有native、已提交reader及watcher关闭并封存前
source/bin/Git不变。本次工程科学门补验通过，原编排中断保持；无PPO/pilot/P2B/gateway，仍待用户验收后才进入后续训练。

## V31 已闭合活动入口（历史命令，禁止重试）

V31已在e7dc6903c0bb4c2fe09f0eb07266f46c9d259022闭合，profile/behavior输出已封存，下列仅为历史命令，不能再次执行或复用输出。V30显式mode不改变默认endpoint。新activity自动依次执行符合性、独立review、收集、独立审计与profile/行为报告；不能直接collect绕过准入。两个plan和native_manifest封存后，clean commit/push，EXACT40取该完整freeze：

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_karto_activity preflight --kind karto_profile --freeze EXACT40
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.reach_execution --scope engineering --output /tmp/mr3_p2a_v31_profile_outer --source mr3_learning/proxy2d_karto_activity.py -- /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_karto_activity execute --kind karto_profile --freeze EXACT40
```

随后同actual-wait工程wrapper封装`proxy2d_karto_activity final --kind karto_profile --run ROS_ROOT/log/mr3_p2a_proxy2d_v31/karto_profile_v1 --outer /tmp/mr3_p2a_v31_profile_outer/actual_wait.json --output /tmp/mr3_p2a_v31_profile_final.json`。只有完整PASS，才用新kind=karto_behavior、新outer=/tmp/mr3_p2a_v31_behavior_outer，并同时提供`--profile-outer /tmp/mr3_p2a_v31_profile_outer/actual_wait.json --profile-final /tmp/mr3_p2a_v31_profile_final.json --profile-final-outer /tmp/mr3_p2a_v31_profile_final_outer/actual_wait.json`执行preflight/execute。每项一次，无重试；actualargv/freeze/失败及union费用在报告收口，不训练/PPO或迁移原生。

## V37 显式点到原图起点模式（待新冻结验证）

默认 `mr3_start_graph_rule:=original-seed-cell` 保留原起点准入。新模式须与seed v2成对：
在既有MR3 adapter启动命令附加 `mr3_seed_rule:=exact-point-bridge-v2 mr3_start_graph_rule:=point-attachment-3x3-v1`。
原生仍向Nav2派发策略选定的候选，attachment不是额外导航目标。此入口当前仅完成实现/CPU准备，
不是原生资格或训练推荐；只按V37冻结计划执行有界代理profile/短探针。
