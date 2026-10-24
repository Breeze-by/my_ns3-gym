# P2A authority 交接与关闭修复

**第一轮原生结果：交接修复尚未通过；失败后的正常返回与关闭在本次真实故障中通过。精确竞态已定位，下一版改为接收端控制阶段激活。**

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
