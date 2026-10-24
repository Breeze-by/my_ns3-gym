# P2A authority 交接与关闭修复

**v3 已完成96步、三机各两轮运动取消与交接，并正常退出；独立刺激、information、cadence/runtime通过。整体诊断仍因FIFO读者遗漏UNBOUND权限记录而FAIL，容量尚未执行。**

用户已授权按[决定性测试建议](20261024_mr3_p2a_decisive_tests.md)执行。本轮先修具体协议链，再做有限行为试验，通过后才执行容量臂。旧失败原件与结论保留。

## 修复范围和验证假设

现行接收 authority 升为 `mr3-owned-stream-authority-v2`，包体与原安全数学不变。旧 v1 科学资格不能转移到 v2。

- 接收端仍逐 normal phase 重建真实停止证据，至多每 80 ms 发布新证据；发送端仅使用年龄不超过原 100 ms 界的 ready，绝不刷新旧证据时间戳。接收端保留原 100 ms/current-witness 检查和 fail-closed 行为。
- 拒绝日志额外保存具体谓词及故障前 owner/state/ready。旧两次 `invalid_authority` 的完整内部状态未记录；缓存 ACK 年龄不是充分根因证明。本轮要用新证据验证这个候选修复，仍可能暴露投递期间证据失效的竞态。
- 任务已经不可逆停止时，真实 native 取消终态可关闭 dispatcher ownership，不再等用于重新授予运动的 normal-stop witness。独立审计必须重建真实 stop 事件、原 owner/revoke/terminal，验证没有改写回执，也没有声称停车证据或允许重新授予。运行中的普通 WAIT 交接仍要求真实新鲜停止证据。
- custody 明确支持固定解释器、完整 `-B -m mr3_learning.decisive_probe --plan /absolute/file.json` 入口，其余源/ELF/进程/原始命令绑定保持。此前未接线的失败不补判。

## 前瞻试验声明

原暖身+两次运动取消候选工作负载、open101/三机/单 worker/最多 96 步保持；原 mask、五秒承诺、v≥0.08、新路径≥0.05、三次新鲜静止和三秒交接不改。live custody、FIFO、information、cadence/runtime、独立刺激、full diagnostic、正常关闭分别报告，任一必需项失败即不派发容量臂。

仅行为臂全部通过后，执行双 worker 各 64 步、open101、uniform legal seed41 的容量臂。这里只测完整采样，尚不包含模型计算，不能独自授予最终 capacity 或 PPO 入场资格。

每臂 native/work 6000 秒和 audit 6000 秒，完整父预约 26000 秒，由代理在用户持续授权和既有 C180000 内前瞻安排。入场 U115431.2861004196018，余64568.7138995803982；连续父实费只收一次，嵌套耗时不相加。pilot 1870决策/2905.9547395464029秒及 final 900决策/9000秒不动。CPU/关闭归档延续工程新增0口径。

开始 native 前必须新源绑定、实际 current21 build、受影响 CPU、真实 commit/push/clean 与 exact freeze 校验；当前尚未执行本轮 World。CPU 首轮 ROS22通过；learner30通过/4失败为旧人工夹具使用过期 ready，原日志已保留。修正夹具后完整受影响组正在真实执行。

## 当前结论

软件候选与验证准备中，尚无修复后的原生通过证据。P2A、capacity、物理与完整资格保持未完成；不自动启动学习。执行结果、具体冻结及实费将在本报告追加。

## 软件准备实际结果

current21 增量 colcon rc0/2.463039182秒、21来源稳定与恢复通过，选定 ELF 与原A59相同，未声称实际 compiler jobs。ROS215通过/55.757127074秒；learner首轮586P3F、后轮587P2F（临时夹具绑定路径在仓库外），最终仅修这两个测试文件后完整40项通过/11.058767160秒，其余生产代码和587个已通过用例对应来源未变。不是宣称新跑一次589全绿；旧失败和各自快照全部保存。新增回归包括新鲜通知、过期通知拒绝、正常交接、停止清理、具体故障谓词与零权限、独立读者拒绝假停车、显式新入口及非法入口拒绝。双环境readiness实际通过/8.436040216秒。

新诊断仅前瞻软件准入，必须仍通过 exact freeze/clean/ELF/原生custody门。准备CPU工程新增0，未给物理或新资格信用。

## 第一轮实际结果（authority v2）

执行冻结 `1f6d2fb7c0330e59de87e676018744a9f6be8fcf`，outer真实rc1；live custody PASS，实际9次返回后task `navigation_failure`。本次tb3重新授予时，发送端最后ready的source为45.06s，grant/接收callback为45.14s，**年龄80ms符合原100ms门限**；接收端前态REVOKED/sequence21/旧owner tb3:1，但当前ready为null，明确拒绝 `grant_without_current_real_stop_evidence`。这证明新鲜通知本身不能消除检查与使用之间的竞态；并不把旧两次缺内部状态的失败补成同一精确证明。[接收端原行](assets/20261024_mr3_p2a_authority_repair/results/receiver_rejection.json)、[发送端原行](assets/20261024_mr3_p2a_authority_repair/results/sender_ready.json)。

取消关闭修复在这次实际失败路径生效：terminal step真实返回，error/cleanup_error均null，worker rc0、forced_shutdown=false、failed_sample=false；实际episode summary存在、launch rc0、cleanup22.682590798秒，Nav2生命周期与finalize正常闭合。`failed_sample=false`只表示没有基础设施异常，**不能把navigation_failure任务算成功或合格样本**。[native](assets/20261024_mr3_p2a_authority_repair/results/native.json)、[episode](assets/20261024_mr3_p2a_authority_repair/results/episode.json)。原生collector因工作负载未完成返回1，原closure角色仍FAIL，未改判。

独立FIFO和cadence/runtime保留真实reach_model_failure；stimulus报incomplete workload，full因FIFO失败跳过。还发现诊断入口的两个接线缺口：summary未带geometry profile，information读者未登记authority日志事件。后继会补明确版本字段和信息角色的事件登记，authority本身仍必须由独立FIFO/runtime完整重建，不删除故障或降低门限。容量臂没有派发，P2A/capacity/科学资格均保持未完成。

完整外父实际715.993225406秒（native内部407.876233882秒；不相加），U变为116147.2793258256018/C180000，余63852.7206741743982；pilot/final未动。[末账](assets/20261024_mr3_p2a_authority_repair/closure_ledger.json)。1161来源current/Git及恢复通过、54个已保存运行身份fresh absent；253普通原件462037582B与源码快照无损归档约69284560B，未删除原件。关闭归档CPU实际rc0/106.524877881秒，两个CPU身份另gone、工程新增0。[库存](assets/20261024_mr3_p2a_authority_repair/closed_inventory.json)。

下一 authority v3 候选先在私有目录准备：合法grant仅登记PENDING零权限；原控制阶段以当前真实witness原子激活并设置实际raw callback floor。等待期间续约仍受原两秒租约、取消与过期均不能激活；不改原STOP/B/R/5s/95%。私有3项人工CPU通过只供候选检查，生产尚未安装；必须新来源/受影响测试/冻结后再运行有限验证。

## 第二轮前瞻范围（authority v3）

承接第一轮真实失败，v3现已安装：合法请求PENDING零权限，控制阶段以当前真实停止证据原子激活，并设置实际最新raw callback floor；PENDING续约仍零权限，撤销与过期禁止激活。原停止谓词和所有物理/五秒/95%门保持。独立重放要求完整激活ACK及原始证据。诊断summary补齐明确profile字段，information角色登记显式authority事件但不替代独立authority验证。

沿用先行为、后容量的两臂及完整父26000秒预约，入场 U116147.2793258256018/C180000、余63852.7206741743982。当前尚无v3原生结果；须通过新的受影响CPU、build/readiness、来源封存与exact freeze。此前所有失败保持，不把私有候选测试视为原生证据。

## 第二轮软件准备实际结果

完整ROS218P/59.128570779秒、learner612P/167.511980496秒；随后只增加两个测试文件，生产实现未变，完整相关文件ROS15P/22.437206149秒、独立44P/6.239707632秒。新增验证覆盖真实激活回执到adapter、伪owner/伪witness/非法floor/错误ACTIVE接收态拒绝，以及独立原始停止证据重建、过期租约和缺证据拒绝。新增人工夹具首轮跳号1F/43P保留，修正为完整实际回调序列后44P；不是重跑所有830项。readiness首轮参数all不合法rc2保留，后继both双环境rc0/8.547587696秒。current21实际build rc0/2.383893262秒，21来源前后及恢复稳定、ELF同A59，不声称编译job。各CPU来源、原件和保存身份fresh absence见[准备核验](assets/20261024_mr3_p2a_authority_activation/checks/preparation_verification.json)。

scope现为前瞻原生准入，仍必须运行时新freeze/clean/来源/ELF门；尚未运行v3 World。工程新增0，U116147.2793258256018与pilot/final原额保持。

## v3首次准入失败与forward

冻结3af8a615f在World前被来源范围门拒绝：prepare时新测试文件尚未tracked，提交后source_inventory新增此文件。原arms=[]、完整来源验证未完成；只有外父5源前后稳定，不能称完整范围通过。真实外父rc1/0.516007944秒，累计116147.7953337696018，余63852.2046662303982；四原件与已保存身份absence见[准入闭合](assets/20261024_mr3_p2a_authority_activation/admission_failure_v1/closure.json)。

forward只更改入口输出/清单/末账，复用逐源相等的v3核心、实际current21 build及CPU证明。新包 `20261024_mr3_p2a_authority_activation_forward`，新exclusive `/tmp/mr3_p2a_authority_activation_forward_v1` 与外父 `/tmp/mr3_authority_activation_forward_root_v1`；26000预约、两臂及全部科学门不变。旧清单与失败原样保留；新清单须在INDEX与新HEAD对当前必需inventory做包含检查后继续。

## v3实际原生与独立审计结果

执行冻结 `5d070c33d1c5d0aa785d444797b3ede80cbc1535`，真实外父rc1。原生96/96返回、collector rc0，三机自然暖身SUCCEEDED后各完成两轮运动WAIT取消、CANCELED回执、三次新鲜静止与三秒交接。独立stimulus读者通过，不以producer输出当oracle。六次取消前接收速度0.168291879–0.199835656 m/s、新路径0.724688927–0.760927329 m；原v≥.08、newpath≥.05、5秒及其余安全门未放宽。[独立刺激原结果](assets/20261024_mr3_p2a_authority_activation_forward/results/stimulus_result.json)。

正常退出已实证：worker/launch均rc0、forced_shutdown=false、failed_sample=false、remaining owned/zombie为空；本次为external_truncation的完整固定96步结束，不是P2A完成。[原生结果](assets/20261024_mr3_p2a_authority_activation_forward/results/native.json)、[关闭原件](assets/20261024_mr3_p2a_authority_activation_forward/results/shutdown.json)。

| 本轮检查 | 真实结果 | 范围 |
|---|---|---|
| native / live custody | PASS / PASS | 真实执行与现场来源 |
| 独立stimulus | PASS | 六次运动取消、真实接收生命周期 |
| information | PASS | 信息边界及完整原始记录 |
| cadence/runtime | PASS | 原控制节拍与运行时重放，不扩成连续物理或完整资格 |
| FIFO | FAIL | peer decision missing independently reconstructed authority permission |
| full diagnostic | SKIPPED | 缺通过的FIFO前置叶 |
| closure角色 | FAIL | FIFO/phase leaf failed；不重判为进程异常 |
| capacity | 未派发 | 原两臂条件未满足 |

FIFO失败已通过源码和人工回归定位：replay_motion在UNBOUND分支验证了严格零权限，却未把该决策存入供后续全流查询的decision_permissions；后续FIFO检查找不到它。私有候选只保留这些已独立验证的权限条目，并严格校验序号；同一两项人工测试原版2F/候选2P，错误ACTIVE/owner/非零输出仍拒绝。候选尚未安装，不把本轮FIFO原FAIL改成PASS。

原生完整2948.696478093秒，96步调用合计约2806.545028791秒，中位28.9288370135秒/步（末步包含终态边界）；FIFO2394.675349601秒、information2185.000587447秒、cadence1116.573110112秒，后两项并行，不能相加计费。完整连续外父实际7614.152750209秒，累计123761.9480839786018/C180000，余56238.0519160213982；pilot/final原额保持。[末账](assets/20261024_mr3_p2a_authority_activation_forward/closure_ledger.json)。

1178绑定来源current/Git及原字节恢复通过，54保存运行身份fresh absent；1358普通原件共2889913160B无损封存274899718B，原件仍保留。关闭归档CPU实际rc0/265.401453636秒，两个CPU身份另gone、工程新增0。[完整库存](assets/20261024_mr3_p2a_authority_activation_forward/closed_inventory.json)。

## 据此调整下一项诊断

协议链已有本次真实行为、独立刺激及运行时正证据，暂未发现必须改变原安全数学的依据；但完整科学资格仍未取得。当前应安装已复现的FIFO读者修复，经新的CPU/来源检查后，以新冻结单独测双worker×64步完整采样成本。这个新活动是回答容量问题的独立工程试验，不把本轮总体FAIL当作入场资格，不合并不同freeze为同freeze资格，不进入PPO。保持全部原物理、安全、动作mask和95%要求；如果新试验失败，按真实失败与成本继续判断。

## 独立容量试验软件准备实际完成

读者修复已安装，仅新增保存已验证UNBOUND权限及严格序号检查，控制/物理源码未改。新完整learner615P/177.886293034秒、双环境readiness rc0/10.285743741秒；来源前后/current相等、快照恢复及保存CPU身份fresh absent。21原实际构建输入逐字节相等，显式复用A3真实构建，不声称新build/compiler jobs。

新 `mr3-p2a-capacity-after-activation-v4` scope只运行双worker各64步、open101、uniform legal seed41容量臂。每臂native/audit各6000秒准入软门、完整连续父26000秒预约，实际超额仍完整记录；由代理依持续授权前瞻选择，非数值用户批准。入场U123761.9480839786018/C180000，余56238.0519160213982，pilot/final原额保持。旧96步诊断总体FAIL保持；本次是新的独立工程问题，不借旧PASS组成同freeze资格。仍须新commit/push/clean和完整来源/ELF门，当前尚无本次容量World结果。
