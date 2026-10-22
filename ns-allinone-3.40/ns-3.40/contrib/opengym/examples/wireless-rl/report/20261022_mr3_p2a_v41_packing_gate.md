# MR3 P2A V41：登记精确map输出打包来源并继续原生链

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
