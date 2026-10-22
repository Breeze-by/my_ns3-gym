# MR3 P2A V41：登记精确map输出打包来源并继续原生链

## 实际闭合：FAIL（2026-10-22）

唯一活动已在新冻结 `47224c51c1c525c55093dce26b374d1ccb07eb06` 实际执行，driver完整等待后rc1；原准备记录在下方保留。packing来源门的真实preflight已通过，interface原生32条提交/32条正常返回、native rc0，live custody、独立system input及angular均PASS，但尚无完整native资格或P2A学习信用。

| 必需证据 | 实际结果与限制 |
|---|---|
| physics | FAIL：tb1/tb3缺少合格停止证据；tb3任务最大平移速度仅 `0.0005951022668803631m/s`，不能把“几乎未动”计作完整制停验证 |
| full | 真实等待 `603.957455769` 秒后rc1；`full_command.json`记录 `declared result missing`，没有生成full result。主编排对console末尾的核查为 `ModuleNotFoundError: scipy`：conda full调用audit_seed_inputs时导入ROS纯geometry依赖；单独system input reader已PASS。此错误与物理覆盖FAIL分别保留，不安装混合依赖或改审计结果补成功 |
| interface余必需角色 | runtime/information/cadence、FIFO/peer_control、closure按原顺序因前置必需门失败SKIPPED；不能用外部身份absence替代其科学审计 |
| 后续资格/学习 | terminal/reset/deadline、完整qualification及minimum/pilot/final-only validation全部未执行/SKIPPED；0学习、0新optimizer更新，无新final模型或95%验证 |
| 外部身份闭合 | matrix_absence与chain_final_absence均PASS，各自54个保存身份缺席、源码及成员稳定；[最终独立review](assets/20261022_mr3_p2a_v41_packing_gate/independent_closed_review_v1.json)另核包括driver在内的61个保存PID/start身份全部freshgone，原失败保持 |

实际唯一命令，cwd为canonical wireless-rl目录：

```text
PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES=0 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m report.assets.20261022_mr3_p2a_v41_packing_gate.execute_chain_v1 --freeze 47224c51c1c525c55093dce26b374d1ccb07eb06
```

四次完整parent actual-wait分别为preflight `38.263866609`、matrix `1690.452159868`、matrix_absence `1.293211652`、chain_final_absence `1.292744973` 秒，scope-wise union共 **1731.301983102秒**；full/native及inner receipt费用均已包含，不再叠加。工程累计 **50013.6985469126018/75000**，余 **24986.3014530873982**。pilot与validation新增均0；原pilot余1870决策/2905.9547395464029秒及final-only open401/402/403额度保持。20900是事前预约，不是本轮实费，也不是失败后自动应消耗的余额。

原始证据已无损canonical封存：**556份原件/1053103628字节，规范归档88403941字节**；[完整库存](assets/20261022_mr3_p2a_v41_packing_gate/closed_inventory_v1.json)逐项保存原路径、原/规范bytes与SHA、codec、stat稳定及解压后原字节一致证明。JSONL/CSV另存`.rawbytes.gz`、gzip mtime=0；已有原`.gz`仍逐字节保存，未重写原件。缺失的full result如实保持缺失，不能以新环境结果追认本次PASS。

关键原件：[driver summary](assets/20261022_mr3_p2a_v41_packing_gate/closed_execution/tmp/mr3_p2a_reach_v41_driver_v1/summary.json)、[matrix实际wait](assets/20261022_mr3_p2a_v41_packing_gate/closed_execution/tmp/mr3_p2a_reach_v41_matrix_wait/actual_wait.json)、[native32步summary](assets/20261022_mr3_p2a_v41_packing_gate/closed_execution/native/mr3_p2a_reach_v41_interface/benchmark_summary.json)、[physics原FAIL](assets/20261022_mr3_p2a_v41_packing_gate/closed_execution/tmp/mr3_p2a_reach_v41_matrix/interface/physics_result.json)、[full真实命令/无result失败](assets/20261022_mr3_p2a_v41_packing_gate/closed_execution/tmp/mr3_p2a_reach_v41_matrix/interface/full_command.json)、[最终独立关闭/末账review](assets/20261022_mr3_p2a_v41_packing_gate/independent_closed_review_v1.json)。review PASS只证明原FAIL的独立封存、身份和末账，不给予完整资格或训练准入。

首次归档工具将生成的`adapter.jsonl.gz`与已有原同名gzip冲突，[setup failure记录](assets/20261022_mr3_p2a_v41_packing_gate/archive_setup_failure_v1.json)保留；改为`.rawbytes.gz`避免命名冲突后完成封存。原实验结果与原输出没有变化；这是纯字节包装bookkeeping失败，不是新实验/科学消费，新增工程费0。

下一步继续P2A：新声明有界只读取证，正确隔离system reader与conda learner，定位真实平移/探针激励并验证修复；不直接重跑完整matrix，不降停止/物理/95%/质量/参与/接触门。当前失败也不证明RL路线不可行；它明确要求先补有效物理激励及环境接线。用户自主持续授权有效，无需再问一般批准，P2A仍未完成。

## 执行前声明与准备记录（原文保留）

2026-10-22，用户已授权自主持续直到P2A完成，无需重复批准。V40原preflight FAIL/22.442744464工程秒保持；当前已用48282.3965638106018/75000，余26717.6034361893982。新V41预约18000矩阵＋300工程收口＋1800minimum＋800准备/有限诊断，共20900，余5817.6034361893982未预约。原pilot/final初始余额保持，任务与所有数学/物理门不变。

V23 map打包性能修订只将两处ROS OccupancyGrid.data赋值改为直接array('b')，但V40的reach版本登记漏该文件，旧immutable pin拒绝是正确行为。本版显式plan profile `mr3-occupancy-int8-array-v1`，仅承认当前/freeze/plan精确e4cf897d2c22e70f89d9293efc00f44dd4bf1eb01624713735e08afdee0cbfcc；三literal完整inverse必须恢复旧76c3d2c604f38f61116be1f39263472f9074b4f69fe7a0428b532da977530078，再在private reader登记这一pin。没有删原核验谓词、修改immutable audit_ppo或merge_map算法；未声明profile及legacy原锁保留。

重新密封全部当前源码CPU、完整plan/source/custody与各policy registry，使用新/tmp和ROS/log v41路径，不复用V40资格或覆盖失败。显式v2＋point观测、30必要角色/12回合、policy外尾300与全部95%/质量/参与/18接触安全门保持；新freeze通过preflight后才World，再资格→minimum→pilot→final。P2A未完成。

## 实际准备结果

五组当前源 CPU 全部通过：geometry 384（含真实 ROS map packing/序列化等价30项）、native reader 12、learner 95（含新来源门18项）、完整 snapshot validator 9，共500项；system ROS 与 ns3gym CUDA 就绪仅检查导入/设备元数据，另计而不冒充策略 forward/backward。随后 plan 生成及 plan_check 通过：55项既有回归与上表有交叠，另26项新准备 fixture，不将55重复叠成独立总量。七份 actual-wait 全 PASS、来源前后稳定；本轮人工 CPU 工程费为0，无新 World/native episode、GPU优化或资格信用。

| 实际组 | 结果 | 原件 |
|---|---|---|
| geometry_cpu_v1 | 384 passed | [console](assets/20261022_mr3_p2a_v41_packing_gate/checks/geometry_cpu_v1/console.log) |
| reader_cpu_v1 | 12 tests OK | [console](assets/20261022_mr3_p2a_v41_packing_gate/checks/reader_cpu_v1/console.log) |
| learner_cpu_v1 | 95 tests OK | [console](assets/20261022_mr3_p2a_v41_packing_gate/checks/learner_cpu_v1/console.log) |
| snapshot_cpu_v1 | 9 tests OK | [console](assets/20261022_mr3_p2a_v41_packing_gate/checks/snapshot_cpu_v1/console.log) |
| readiness_cpu_v1 | ROS/learner/both metadata PASS | [console](assets/20261022_mr3_p2a_v41_packing_gate/checks/readiness_cpu_v1/console.log) |
| prepare_plan_cpu_v1 | plan/source/custody生成 PASS | [console](assets/20261022_mr3_p2a_v41_packing_gate/checks/prepare_plan_cpu_v1/console.log) |
| plan_check_cpu_v1 | 55回归＋26新fixture PASS | [console](assets/20261022_mr3_p2a_v41_packing_gate/checks/plan_check_cpu_v1/console.log) |

上述实际入口在 canonical wireless-rl 目录为：

```text
rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 -B report/assets/20261022_mr3_p2a_v41_packing_gate/cpu_driver_v1.py NAME
```

NAME 为表中实际组名；各 child 完整 argv、解释器、源码字节与真实 wait 见对应原件。它们是本轮已完成记录，不能覆盖原输出重跑来补成功。

[plan_v1.json](assets/20261022_mr3_p2a_v41_packing_gate/plan_v1.json) 211855字节，SHA256 `85c7146999279ce6981c885544c08faa12577722f5f17b8460dc946c2d0a9742`；[native custody binding](assets/20261022_mr3_p2a_v41_packing_gate/native_custody_binding_v1.json) 128956字节，SHA256 `5ea491d674c78f25a7a3c6f2336f3390f25912ca110e418ccb217ed486d2e93c`。两者必须随最终源 commit/push 密封；当前不填尚未产生的新冻结 SHA，也不把静态准备称作真实 preflight PASS。

## 下一次完整链与计费门

新 freeze 唯一完整链入口为 ns3gym：

```text
PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES=0 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m report.assets.20261022_mr3_p2a_v41_packing_gate.execute_chain_v1 --freeze EXACT40
```

`EXACT40` 必须换成完成 commit/push 后的真实40位 SHA；这段是即将执行的预声明形态，尚未声称启动。先真实来源/ELF/reader preflight，再同冻结完整资格30角色/12回合及外部退出核验，才进minimum→pilot→final；同一链闭合前不改绑定源、plan或中途commit。任一必需门/费用门失败阻断后继，原件不改判；若继续修复，另建具体新版本活动。

minimum仍16有效决策/真实正更新；pilot从零、open101、最多1870决策及2905.9547395464029秒；final仅同一pilot final.zip、open401/402/403、900决策/9000秒上限且零更新、三场全部严格成功。pilot/final各在原CAP内预留300外部收口，主deadline2605.9547395464029/8700、内部500不借用，native ceilings1150/2100/8500不增。minimum外尾与资格/完整链身份检查共用工程300；外部真实parent-wait union及完整端点必须在所属额度内，不把finalizer自身未来费用写成已证明。当前余额仍为48282.3965638106018/75000、余26717.6034361893982，20900是预约不是实费；P2A未完成，尚无新学习或95%出口。
