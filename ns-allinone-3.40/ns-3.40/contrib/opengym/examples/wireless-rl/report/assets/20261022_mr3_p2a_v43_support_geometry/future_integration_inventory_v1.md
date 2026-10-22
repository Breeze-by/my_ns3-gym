# V43已闭合后的V44显式cone-support-v2接入清单

2026-10-22更新：root已真实运行support候选与legacy geometry共124人工CPU PASS（5.698039134秒、11源稳定、工程0）；独立逐行数学review PASS/无未解阻断，见同目录independent_math_review_v1.json。用户已授权自主持续完成P2A，下一步V44显式规则接线和新freeze必要原生资格，无需重复一般批准。本清单作者仅只读梳理调用链，未消费原trace或执行World/consumer；本轮CPU/数学不提供plant/native/P2A信用，V41 FAIL及V42选行省略限制保持。

## 必须固定的语义

- 新轴是显式`reach_geometry_rule='cone-support-v2'`，正交于`safety_contract='mr3-reach-v1'`、`seed_rule`、`start_graph_rule`。不能换成seed v3或冒用候选/point-graph版本。
- 缺省规则统一为`binary-cone-v1`，新值为`cone-support-v2`；沿用原pair-certificate v1作为默认。仅旧记录“字段缺失”可解释为v1；新plan声明v2后，任一中间字段/argv漏传必须FAIL，不能以generic reach contract自动认作v2。
- 对未知值、显式None/bool/非str、重复CLI/混用`--x=value`及不支持的safety-contract组合拒绝。v2只允许显式reach profile；保留旧default argv/kwargs/metadata输出字段省略，尤其PPO的`metadata={**vars(args)}`须在v1缺省时删除新增键，不能无意改旧JSON。
- `mr3_reach_geometry.py`保持完整SHA **cf46b49f0740f84511f3d34f9a8eb3e56720744515d9eea1dc81bd8bacb85f0a**，旧`pair_certificate`及disk/normal/transition/Direction不改。新纯module预计`mr3_reach_support.py`，只增加显式v2证书算法；不改Reach集合、D/N=2R/X=4R、年龄/误差/时间界、intent的HOLD/D/X/N/STOP和`mr3-safety-intent-v1`严格字段/含义。
- 如新算法只改善同一集合的充分分离证书，必须用数学/人工CPU证明；不能以名称相同声称数学无变化。独立重放必须独立实现或独立oracle，不能import生产support证书来互相证明。

## 最小完整执行传播

V44三方接口已统一：Python/plan/metadata使用`reach_geometry_rule`（默认`binary-cone-v1`，新值`cone-support-v2`），CLI `--reach-geometry-rule`，launch `mr3_reach_geometry_rule`，Node参数`reach_geometry_rule`。计划构造`build_plan(..., reach_geometry_rule=...)`与native custody binding都必须显式写同rule；v2 binding必含新`mr3_reach_support.py`及独立`mr3_learning/reach_support_replay.py`源码。`runtime.source_proof(..., reach_geometry_rule=...)`由各实际metadata选择，不可落默认。

以下路径以W=wireless-rl、P=ROS `src/multi_robot_exploration/multi_robot_exploration`表示。

| 现文件/入口 | 未来最小改动/核验责任 |
|---|---|
| `W/mr3_learning/supervisor.py` validators与argv readers | 一个严格规则验证/唯一CLI提取接口；Supervisor构造参数保存规则，reset IPC显式传v2；`supervisor_metadata.json`显式记录v2。旧缺省省略新增字段。不要用环境变量偷偷切换。 |
| `W/mr3_learning/reach_preparation.py::build_plan/validate_plan/_qualification_evidence` | 新plan显式rule；四stage benchmark argv逐一等于plan；新helper及独立数学reader进入source inventory，worker/supervisor metadata也必须相同。qualification绑定该rule/新freeze，不能借原v1 PASS。 |
| 未来新活动`prepare_plan/preflight` | 生成四个qualification stage及完整minimum/pilot/validation三policy registry的显式argv；预检实际load新source-custody路径；不得修改已冻结A41/A42脚本/plan补信用。 |
| `W/mr3_learning/reach_policy_chain.py::stage_spec/check_native_result/stage_evidence` | 三policy argv、PPO run metadata、计划、资格及每EP都同rule；predecessor/final checkpoint仍严格同链；不能minimum漏传v1、pilot/final却取v2信用。费用/roles/最终95%门不变。 |
| `W/mr3_learning/benchmark.py` CLI/collection/worker task | 增新CLI严格验证；实际传给Supervisor；benchmark summary及attempt metadata绑定v2。参数review/terminal/deadline/reset入口不能漏。 |
| `W/mr3_learning/ppo.py` CLI/admission/metadata/Supervisor创建 | 资格plan与arg一致；train/evaluate均显式传；metadata默认省略。训练/验证仍只用同一pilot final.zip、不改样本/optimizer/95%语义。 |
| `ros2.../scripts/mr3_env_worker.py::Worker.__init__/launch/reset metadata` | 严格读取reset request，v2写`metadata.json`，launch命令附`mr3_reach_geometry_rule:=cone-support-v2`。实际worker metadata不能只抄outer宣称。 |
| `ros2.../src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py` | 声明/解析新launch参数，验证其与safety profile组合，传给真正`motion_safety` Node；不要错传仅给adapter而guard仍默认。现motion_safety Node在约725行，safety args约559/1314。 |
| `P/motion_safety.py::__init__` | 读取并严格验证ROS参数；同一epoch三个`ReachTracker`全部取该值；`configuration`日志只有v2时附rule，记录有效选择以供独立reader绑定。只改配置元数据，不向intent wire塞新字段。 |
| `P/mr3_reach_runtime.py::ReachTracker/pair_checks/decide` | tracker固定rule、不可中途热切。`pair_checks`缺省调用原函数，v2调用新support。**当前检查(约435)和D→X prospective检查(约479)都传同rule**；不能只修一侧。保留当前D证书/拒绝X证书各自真实proof及线性刹车分量语义。 |
| 新`P/mr3_reach_support.py` | 保留old Reach对象和输入几何，新增独立版本化证书标记/规则；unknown/outside/fresh/两frame/.29等原先独立门不得被support结果替代。v1不得悄悄调用新helper改变旧输出。 |

`mr3_learning/env.py`当前只包装Supervisor并转发step，不拥有reach几何数学；若不新增reset options覆写，通常无需再造一层规则。`mr3_adapter.py`和observation/candidate/encoder也不拥有这对reach证书；此改变无需无意义重发seed/candidate/intent schema。任何尚未支持v2的proxy/诊断入口应拒绝显式新值，不能忽略后当旧默认提供资格。

## 旧数学门中真正需要显式新版本的地方

1. **生产调用者**：`mr3_reach_runtime.py:95 pair_checks`当前无条件调用旧`pair_certificate`。`ReachTracker.decide`既检查当前真实Reach，又检查D→X拟议Reach；两者须同一新规则。不能修改cf46几何文件或吞掉不允许的转向/符号/锚点债务。
2. **独立原生重放**：`W/mr3_learning/audit_reach_runtime.py:308 independent_pair`当前自己重建raw/map两frame和旧nonclosing+整D额外reserve判据。不是生产函数的动态import。其调用在约**363** `admitted_command`线性刹车分量合取，以及约**981** `_audit_records`对实际allow的合取。只把新module加进source SHA而不显式更新这两处的rule dispatch，会让新允许运动仍被旧数学正确拒绝；反之全局改旧函数会污染v1语义。
3. 这个reader的`state_geometry`/intent/校准/source age/实际驱动/20ms cadence/关闭等共同必要门继续原样合取。仅pair证书的数学分支按显式rule选择；新独立计算不得调用生产support当oracle。可增加独立learner侧support helper，但也必须冻结自体和依赖。
4. `ingress_index`约533目前只核motion configuration的generic CONTRACT/controlled/robots，**不核reach_geometry_rule**；新模式必须把episode metadata、supervisor/benchmark/PPO身份、有效motion configuration和独立分支互相绑定。只在episode metadata写cone-support而guard实际v1，不应获得v2信用。
5. `audit_episode`约1062先读metadata再`source_proof`，`audit_episode_set`约1115核同freeze/epoch与generic profile；两入口都要拒绝unknown/mixed rule，run中混入v1/v2不能靠generic `mr3-reach-v1`通过。返回报告在v2时显式写实际rule。

## 资格、custody和source pin不能漏的链

| 当前文件 | 需要保持/新增 |
|---|---|
| `audit_reach_runtime.py::SOURCES/source_proof`（约28/410） | 当前固定源包括旧geometry/runtime/guard/worker/launch/reader自体；v2再显式绑定新生产support和独立support reader。核Gitfreeze==current bytes及完整依赖，不仅检查含有字符串。v1历史路径不要求其冻结中不存在的新helper。 |
| `native_custody_reach.py::REQUIRED_SOURCES/build_binding/verify_binding`（约67起） | 新plan/binding覆盖真正加载的support源与独立reader；原driver/recorder/observer等ELF及其编译源证明不变。纯Python数学变化本身不需要假造新的C++编译证据。新helper仅放repo却未入binding不可供资格。 |
| `reach_gates.py::load_native_gates/_load_versioned_native_gates`（约204/220） | public plan route和separate diagnostic route均显式传规则；source proof及dispatch报告绑定v2。保留原immutable pins和现packing whole-source inverse。默认不扩generic REVISED_RUNTIME跳过其他源锁。 |
| `reach_gates.py`旧geometry额外依赖门（约319） | exact seed证书仍依赖旧geometry；**cf46旧文件保留就无需放宽此门**。新support是额外依赖，不拿新SHA替代旧geometry的有效性。 |
| `reach_preparation.py::source_inventory/source_check/_qualification_evidence` | source_inventory含tracked ROS执行源及所有learner.py，但仍要显式require新helper，避免untracked/缺件或只有registry宣称。闭合qualification必须绑定实际输出的rule及新源。 |
| `audit_reach_preparation.py::audit_directory/load_impl/audit_archives` | plan/每EP rule一致，旧完整gate+独立runtime的v2选择真正到达；system exact seed replay仍是原snapshot/七图必要合取，不因新runtime规则跳过它。 |
| `audit_reach_ppo.py::admission/audit_episode_conjunction` | PPO run/资格plan/每attempt相同rule；其`runtime_drive`调用进入新独立分支，其余information/peer/FIFO/archive/activity/input合取不删。 |
| `audit_reach_cadence.py::source_proof` | 当前直接调runtime.source_proof（约85），如新增kwonly规则须让单EP/RUN都传实际rule；别落回v1来源证明。数学cadence不改。 |
| `audit_reach_information.py`、`audit_reach_peer_control.py`、`audit_reach_controlled_physics.py` | 原wire/intent/接收/FIFO/物理方程无需改；但若其EP/RUN共享metadata入口接收规则，必须核合法一致并保留新源绑定。不能为新geometry删generic旧身份门。 |
| `audit_seed_inputs.py`、`mr3_seed_certificate.py`纯loader | 旧输入重建本身不使用新pair证书，仍应保留旧geometry依赖/原数学。仅当实际新增lazy依赖才扩pure inventory；不要为axis命名而无故改snapshot/候选或wire schema。 |

新增科学说明应在`MR3_REACH_CONTRACT.md`明确这个足够分离算法版本仍针对原Reach集合。若实际修改ENV文档，新完整SHA与唯一新块的whole-document inverse也必须在reach_gates显式登记，恢复当前整文；不能为了文案删旧ENV pin。同步`launch_commands.md`任何新增launch参数/推荐用法。

## V44接线的最短人工检查（尚未执行）

- 独立数学反例/oracle：保留旧v1结果逐字段；新support确实覆盖同Reach集合、两frame/年龄/残差/严格边界，拒绝NaN/unknown/缺证据；不能只测试有利旋转方向。
- 实际人工tracker与真正独立runtime reader同case：v2安全新接受、v1保持原拒绝；伪造rule/来源/配置、偷改Reach或intent全拒。要覆盖`independent_pair`两个callsite和D→X/current两次生产证书。
- 从新plan到真正launch Node/Tracker的人工argv/metadata fixture；缺/错/重复rule、资格与pilot/final混配、worker漏传/guard默认均拒；default输出/旧cert和cf46源字节相等。
- 真正source-custody gate loader人工集成：包括新module缺件/改字节、独立helper缺pin、旧ENV/packing pin未变。不能只mock source gate证明新资格。

V43人工数学/CPU已闭合，当前生产尚未启用；按已授权的V44计划完成显式接线、独立reader/source与人工检查后，以新freeze取得完整必要原生资格。不能凭这份清单或124CPU跳过资格、启动PPO或改变预算、95%/安全门。
