# MR3 P2A V64：实际热点的等价优化

V63 的两份失败启动 profile 已完成有限描述；根因仍 UNKNOWN，P2A 尚未完成。本轮把两处有测量依据的优化接入实际 Python 源码，原数学、物理、时间门和记录内容保持。没有新 World、资格、学习或容量信用。

## 修改与依据

`ReachTracker` 的 raw/calibration/applied/publication 字典只接纳单调递增新身份，同身份仅允许原内容重复；因此最大 key 等于最后插入 key。查询直接取末键，保留全部原件。`DrivePhaseClient.receive` 保证 cmd_seq 严格递增，consume 仅保序删除；实际执行的新旧存储检查可以逆序，遇到不大于当前 cmd_seq 时停止，较旧记录不可能满足原谓词。异常、同钟的新存储和所有原历史保留。

`MotionSafety.record` 先对原 payload 严格 JSON 编码；成功时直接保存原字节，出现 ValueError 才执行原 nonfinite→None 的递归处理。序号、sim/wall 时钟各一次采样和原 payload 均保留。等价范围是生产 schema 的普通、有限深度 dict/list/tuple 标量树；不宣称任意自定义 Python 容器、并发突变或异常混合对象的通用等价。

实际安装文件与已测试候选逐字相同，见 [安装绑定](assets/20261024_mr3_p2a_v64_equivalent_hotspots/installation_v1.json)。底层 C++、encoder profile、R=.0078、固定 anchor、一次性 servo 永久 disarm、原 10 秒相位 guard 均不变。authority 修复仍是独立未安装候选。

## 已做验证

| 检查 | 实际结果 | 限制 |
| --- | --- | --- |
| 原 Reach 测试与原版/候选实际类差分 | 58 PASS，tool23256 rc0，82.440813439秒 | 人工输入，无物理信用 |
| record 原方法/候选 AST 方法的字节、序号、异常及非有限值比较 | 21 PASS，tool9522 rc0，0.666653817秒 | 原 huge-int fixture 自动命名导致的 collection FAIL 原件另存 |
| canonical 路径、真实 ROS 消息类型、原运动安全与 Reach 交付测试 | 112 PASS，tool6051 rc0，23.187448483秒 | 137 来源前后稳定，两个保存身份 fresh-gone；无 ROS 图/World |
| 固定人工 latest-target `_applied`，每轮1000调用 | 256记录约2.7倍，4096记录约98倍 | 只测该 kernel；原记录/结果相同 |
| 固定人工 finite record，每轮2000调用 | 三轮约3.00/3.00/2.74倍 | 字节数/SHA/序号完全相同；digest sink，不是磁盘吞吐 |

canonical 首轮缺 merge_map 搜索路径而 collection FAIL（tool21575，rc1，child2.019878675秒）保持；第二轮仅补真实模块目录并保存实际环境，生产代码未因该失败修改。各实际 wait、源快照和保存身份退出证据连同失败版本完整封存，不将准备失败改判 PASS。见 [canonical 检查证明](assets/20261024_mr3_p2a_v64_equivalent_hotspots/canonical_cpu_proof_v1.json)及 checks 下的历史包。

局部倍速不能相乘或外推为整套仿真的倍速，旧 V62/V60 FAIL 不改。人工 CPU 工程新增0；承接 [V63 实际末账](assets/20261024_mr3_p2a_v63_profile_description/closure_ledger_v2.json)：U109074.2448783686018/C150000，余额40925.7551216313982。pilot 1870 decisions/2905.9547395464029秒与 final-only 900 decisions/9000秒原额保持。

## 下一位执行者

1. 完成 owned-stream authority 的 ROS 回调、独立审计器、custody/plan 与 PPO pre-update 接线，再做统一 source-bound CPU。其 profile 为 `mr3-owned-stream-authority-v1`，独立于原 encoder profile。真实取消必须在原合法取消时钟立即派发，raw 非零不得伪造为零；逐条已验证 APPLIED 锁存曾经运动，不能只看同步后的最后状态。
2. 将 authority 的 motion_safety 改动合到本轮新源，避免整文件覆盖 record 快路径；runtime 五处优化保留。保留快速 terminal-before-logical-accept 与发布异常仍附 native cancel done callback 的回归。
3. 合并已封存 outward-cancel-v2 有效刺激及同活动 exact-seed-only 辅助事实接线，保持32步、5秒承诺、12EP/30必要角色、原停车/安全/95%门。
4. 新精确 freeze 下先有界原生验证并实测整套 native+完整独立审计+收口容量。capacity=False 时禁止自动 pilot/final。实测成本不足时前瞻制定有界工程块，承接全部实费，不扩 pilot/final 原总额。
5. 全部同 freeze 资格、minimum/pilot 真实正更新与三指定 final-only strict95 真正通过后，才能宣称 P2A 完成。P2B/gateway 不启动。
