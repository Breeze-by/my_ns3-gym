# P2C.1 v33 原优先级惰性核验组件 PASS

v32第一强制原任务在冻结0972下EXPLORE timeout300.0秒，六个实际Nav2 goal、两机各充电一次、零接触/耗尽/failed机器人；strict FAIL、125次原lease弃置（96次预算阶段）完整保留。其余3开发/17正式/2物理/917均未运行。全部owned关闭后才编辑。

新增一个纯heap迭代器，只修改中央assign_idle_robots候选评分执行顺序：原utility和满足当前接续几何/信息门限时的最多2x倍率作上界；原电池完整路线因子、相对同伴旅行因子、历史空间分散因子均不大于1。未评分候选保留上界，已评分候选按真实分数重新入heap；只有其真实分数高于所有未评分上界时才送入原greedy路线核验。原输入索引保留稳定tie顺序。已暂定选择机器人的其他候选不再价格计算（原route循环同样跳过）；每台原始候选全集仍保留给原充电lookahead。未负担候选仍检查可行充电意图，不能因未计算预算而获准行动。

原生成/每次预算/路线/派发都使用真实clock与原source TTL；后续lazy评分过期会撤销先前暂定计划，不留下导航、charge请求或live owner。原完整body/在途预约/已知往返预算保持。非有限上界、非有限分数或超过声明上界直接失败，未核验动作不会yield。诊断candidate_assignments现为已评分数，generated_candidate_assignments为生成总数；不改变实际任务与原native300秒/.35m/.05mps/.1radps/5秒。

十二随机种子的200候选全量惰性顺序与完整稳定排序逐项相同（含tie、跳过、倍率与分数降低）。高优先级早停不计算无用低分候选；分数降低必须先核验竞争上界；非法界失败。实际后期212×253交付map/14相机历史、eligible tb2/pending tb1的五cold固定条件计算中位0.62544→0.31662秒，预算调用90→2，所有导航点/旅行偏好/预算证据相同；这不代表实际callback延迟、任务因果收益或最坏时界。

116定向PASS5.48秒，追加边界与后续过期撤销26PASS1.36秒；最终1280功能PASS73.37秒，四包5.81秒，171保护/4授权/54静态协议/8+2 Future注册、两清单原case和刺激同父版本PASS。实际隔离ROS DDS clock/中央state串行、真实native Future、原视场20数值/79候选/发布消费、camera/survey/quiet/lapsed均绑定最终source PASS。Native battery、共享Future helper、TF sampler、launch、观察器、严格checker/result读者、视场validator相对0972字节不变。只读v32原始十二子门仍PASS、strict任务仍FAIL，不回填。

首helper patch签名不匹配被拒；首中央转换newline索引assert在write前失败；首定向命令拼错test文件pytest exit4无测试。归档首读取错comparison文件名在任何write前失败，改为实际lookup_comparison.json。均为准备错误，无新原任务；修正后完整证据及命令保留。

组件PASS，P2C.1未完成。新4开发→17正式+2物理需要同一clean pushed freeze；首先强制双机真实native完成且各charge≥1。917未暴露；P3C.5已验收，无P4/ns-3/Wi-Fi/RL。
