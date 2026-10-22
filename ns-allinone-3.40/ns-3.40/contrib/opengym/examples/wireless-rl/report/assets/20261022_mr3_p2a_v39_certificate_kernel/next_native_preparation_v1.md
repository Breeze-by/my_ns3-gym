# V39 后续原生资格与学习入口

本文件是准备清单，**不是运行许可或资格结果**。工程当前累计
48259.9538193466018/52000 秒，余3740.0461806533982秒。累计75000秒仍为
PROPOSED_NOT_APPROVED；若获明确批准，按此末账余26740.0461806533982秒，预约
20100秒后余6640.0461806533982秒。pilot余1870决策/2905.9547395464029秒，
final-only open401/402/403与其原额度保持。没有收到数值上限答复时，不启动本链。

预算批准后，在新冻结上完成以下准备并执行；V37随机二维全PASS不是额外前置。

1. 核对当前源码、ROS安装导入路径、源绑定和动态库身份，生成新的custody binding、
   binary proof、preflight和互不覆盖的输出路径。不能沿用旧冻结的资格结果，不能把
   V39人工CPU或V38法证PASS计为原生信用。
2. 调用`mr3_learning.reach_preparation.build_plan`生成四阶段完整矩阵；所有native
   argv显式使用`--seed-rule exact-point-bridge-v2`和
   `--start-graph-rule point-attachment-3x3-v1`。保留30个mandatory角色、12个回合，
   原阶段上限2400/1200/6500/7900秒、矩阵18000秒不变。新plan重新绑定优化后的
   `mr3_seed_certificate.py`；`mr3_point_graph.py`的e55b…固定pin和环境合同保持。
3. `build_plan`只生成矩阵，**不会自动生成`policy_stages`**。提交前另外密封
   minimum/pilot/validation三项完整registry，按`reach_policy_chain.stage_spec`
   校验全部输出、argv、观察/动作/执行规则和前后继关系。所有策略阶段也必须同时
   显式绑定v2与point模式，不可用原v2/original-seed-cell资格补齐。
4. 如果累计75000获批，更新plan中工程余额与
   `engineering_remaining_basis`。builder现有字面依据仍写Approved 52000；不能只
   把remaining改大、留下相互矛盾的批准记录。顶层scope预约18000矩阵+300外部收口
   +1800 minimum，共20100秒；`validate_plan`自身仅检查18000，不能用它跳过总预约。
5. 运行人工plan/qualification/policy-chain/admission检查，核完整source inventory，
   再提交并推送新freeze。通过入场检查后才执行，运行期间不编辑绑定文件。按实际wait
   区间union记账，完整收口和外部身份核验必须计入，不因主进程结束就省略尾部。
6. 完整新原生资格通过后才进入minimum；minimum通过才进pilot，再按冻结final模型
   进行三场final-only。阶段失败保留，按已声明的停止/不重试规则处理，不补样、改种子、
   混合freeze或放松95%/300秒、质量、三台参与、18接触流及关闭门。

继续使用当前严格训练审计。V38的负回合新审计仅为待审提案；collector接受普通负终态
不代表完整protocol/custody链已准入dispatcher failure。若拟改变这一口径，需要另行
明确批准、版本化实现与新冻结，不能借预算批准或恒等提速激活它。最终任务和物理安全
门始终保持。
