# 本轮12EP/30角色闭合后的容量判断（待填）

只读准备，未调用reader/native或读取raw/pstats/旧342库。当前没有matrix成功或policy容量结论。本表供Root在**本轮实际闭合后**填写，沿用原预算与科学门，不是自动policy入口或新的预算申请。

先填：execution freeze=`__`，PLAN/SHA=`__`，实际qualification12EP/30角色=`__`，真实Root reap/所有submitted child waits=`__`，source/ELF闭合与typed保存身份gone=`__`。V3的9个probe EP独立重放、authority/compound law/Reach/物理/clock及所有原必要角色都必须实际通过。任一FAIL/SKIP/UNKNOWN保留原判，不能启动后继policy。

工程入场只能用本轮完整parent关闭后的真实末账：U=`__`、R=`__`、尚未消耗的工程external300余量e=`__`。不再使用matrix准备时余额，也不把nested wait相加收费。pilot原余额**1870决策/2905.9547395464029秒**、final-only原额**900决策/9000秒**均独立保留；不能挪final额付工程、训练或失败重试。

## 必须取得的实际数字

每项同时填原receipt/output的path、整SHA、freeze/epoch/argv join；仅读已闭合metadata或既有派生摘要，不重跑科学reader。

| 范围 | 要填的数字和边界 |
|---|---|
| 整链/四阶段 | 连续完整parent墙时含gaps；各stage实际wall/derivedcap/native allocation；全部required状态及所有实际wait/rc；external absence/qualification实际支出。 |
| 每个EP/native | 场景/seed/worker并发、真实返回数、Σdt与0-dt数；startup、transition wall、整个EP含shutdown wall；native总端点。整EP减前两项仅标“混合残余”，不能当精确closure。记录forced/failed/remaining/zombie。 |
| 长度/负载可比性 | 本轮最长实际task sim跨度、最长地图/日志体量、实际1/2worker并发与资源采样范围。300step不自动等于300sim秒；32step不能线性推成3个长RL回合。 |
| 科学审计和尾部 | 每个实际full、FIFO leaf/manifest、closure、watcher的wait墙时/rc；native结束→全部审计、源/原件重核与summary结束的实际端点；读字节/文件量。并行耗时不相加冒充关键链，full必须完整，不能只计启动/命中行。 |
| policy特有开销 | 模型coldstart、推理/更新、rollout/checkpoint写出、PPO完整full audit和最终source/artifact绑定的实际开销；外部finalizer的wait及main开始→final结束端点。拆分未计时可UNKNOWN，须有已覆盖它们的完整端点，不能填0。 |

表中matrix/EP数据只支持其实际场景、时长与并发范围；matrix没有模型更新或PPO full audit。不要把CPU/kernel倍速、压缩比或旧profile秒数充当本轮容量。缺少可比的完整端点，后继容量保持UNKNOWN/暂缓；不拿401/402/403做性能调参样本。

## 逐阶段判断，不一次放行三段

| 阶段 | 原完整cap/保留项 | 最小判断 |
|---|---|---|
| minimum | 工程1800；native字面≤1150；内部tail预留500；独立finalizer用工程external余额e。 | 实际工程R≥1800+e；有理由容纳全新16个eligible样本、正真实更新、完整审计/关闭。只记录是否准入此有限阶段，不能承诺pilot/final。 |
| pilot | 原完整2905.9547395464029，内含外部finalizer300；main≤2605.9547395464029；native字面≤2100。当前声明请求64，实际2≤eligible≤64，且不超过原1870余量。 | minimum真实更新与独立final absence已完整通过；结合其实际PPO/full审计成本和本轮并发范围，逐项说明完整pilot能否落在原cap内。仍须正真实更新，64只是请求上限。 |
| final | 原完整9000，内含finalizer300；main≤8700；内部tail预留500；实际native至多**8200−prework**，不是8500全额。 | pilot完整闭合；绑定其最终checkpoint精确SHA和固定物理归一化，同源evaluate且0更新；三open401/402/403各原300step上限、三strict95/质量/参与/安全完整合取。仅短probe或64样本不足以证明3并发长回合及完整full审计能落9000，证据不足就暂缓。 |

源码实际分配：`native=floor_ms(min(native_ceiling, main_cap−实际prework−500))`，必须为正。**500是最低预留，不是审计耗时保证。** 要比较native实际结束后剩余main时间，完整full/FIFO/closure/source绑定是否可容纳，并保留已说明依据的余量；不能把这些审计移到预算外。pilot/final还须实际finalizer≤300、原scope费用与main→final连续端点都≤各自原完整cap；gaps全计，nested不双加。任一超cap/FAIL须排空真实child、全费保留并跳过后继，不降cap或借final余额补洞。

## Root填写的结论

- 本次只判断的阶段=`minimum / pilot / final`；结论=`PENDING / ADMIT_THIS_STAGE / DEFER_CAPACITY_UNKNOWN / REJECT_REQUIRED_FAILURE`。
- 适用的实际证据/负载范围=`__`；native/prework/tail/finalizer完整时间说明=`__`；尚未覆盖部分与余量依据=`__`。
- 实际前账及本阶段funded核对=`__`；同freeze/plan/profile与前驱独立closure/checkpoint绑定=`__`。
- 未授下一阶段自动入口；未改变原余额、科学门或旧FAIL。matrix PASS、描述PASS、native返回完成都不能替代这个逐段判断及各阶段最终真实验收。

容量记录可先留/tmp，在原clean pushed freeze下完成判断再决定后继显式入口；不要为写报告先改变被冻结的plan/source。若实际HEAD/绑定源或plan已经变更，按现有exact-freeze合同重新准备，不回填旧qualification的freeze。此模板不执行现有`stage_evidence`或任何审计。
