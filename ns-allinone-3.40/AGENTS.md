# ns-allinone component memory

2026-10-23 V52准备：显式reset reader登记与runtime声明/ACK索引、严格JSON构造等价优化已接入；候选10项、初轮81项、新resource v3集成297项人工CPU通过，原数学/物理/95%及12EP/30角色保持，尚无新native/学习。代理按用户自主持续委托前瞻选择工程累计120000（非声称数值user批准），从原账70543.1774146986018承接、余49456.8225853013982，预约47220；pilot/final原额不动。四入口10case与真实prepare/plan_check已通过，933源/10ELF待新冻结执行，旧FAIL保持，P2A未完成。 见[V52](ns-3.40/contrib/opengym/examples/wireless-rl/report/20261023_mr3_p2a_v52_qualification.md)。

2026-10-23 V51闭合PASS：freeze41100004固定旧V50单open回合原runtime审计1次完整PASS/无batch，parent421.403520124秒；24旧证据源/9执行源与Git一致、5保存身份freshgone，22原件362085B无损封存362008B。实际热点为JSON解析/规范化及重复声明/ACK全扫，非单纯几何；先等价索引/严格JSON构造CPU，再显式reset接线与原生阶段wall分解。累计70543.1774146986018/75000、余4456.8225853013982，pilot/final不动，无新资格/学习/95%信用，P2A未完成。 见[V51闭合](ns-3.40/contrib/opengym/examples/wireless-rl/report/20261023_mr3_p2a_v51_runtime_profile.md)。

2026-10-23 V51准备：固定V50 reset首open回合的一次独立runtime profile，14输入/24旧证据源/9执行源封存，6组真实toy生命周期CPU及guard/driver模块help PASS；尚未原件消费。预约840主＋60尾＝900工程秒可funded，先实测再恒等优化/显式reset登记与新完整资格。用户持续委托保持，后续有界工程块按实测自主规划、诚实保留旧账及pilot/final原额；P2A未完成。 见[V51](ns-3.40/contrib/opengym/examples/wireless-rl/report/20261023_mr3_p2a_v51_runtime_profile.md)。

2026-10-23 V50闭合FAIL：freeze23e909380真实reap rc1；11EP/296原生返回，30必要角色18PASS/2FAIL/10SKIP。reset input/runtime/full PASS，angular/physics旧probe入口拒绝、阶段11302.772605716>最终cap6301.463804643；可选两corridors停车证据缺口保留。deadline/minimum/pilot/final未启、0学习。911源/10ELF一致、545保存pair freshgone；5070原件10224871773B无损封存855260558B/0软链。工程parent union14162.168963343，累计70121.7738945746018/75000、余4878.2261054253982，pilot/final不动，P2A未完成。 见[V50闭合](ns-3.40/contrib/opengym/examples/wireless-rl/report/20261023_mr3_p2a_v50_qualification.md)。

2026-10-20交接入口：[P2A评估与后续交接](ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_assessment_handoff.md)。以下2026-10-18状态保留原时点含义，当前P2A.0已验收、P2A未完成，以根/无线组件活动计划及V20末账为准。用户本次仅要求保存评估；二维路线、验收规则调整和60000扩额尚未批准，先形成有界可行性/容量方案，不直接启动新训练。

2026-10-18: P2A.0工程科学门已补验通过，待用户验收；原V26父编排中断保留，P2A未完成，未启动PPO。 源码冻结`92f8bdf5bba1ba245dc53ca0964eef81a7fff938`；同冻结四阶段/12回合、34必需科学角色全部通过，最后一个information只读消费者在原父进程组消失后单独补完；原ledger/未知返回码/缺失最终回执不补造。 原生468/468正常退出，枚举元数据中543个保存PID/start均gone。 reset非必需逐回合停车覆盖FAIL及所有旧FAIL保留，原合并覆盖门通过。 工程累计11420.856789876707/18000墙秒，pilot余额1870决策/2905.954739546403墙秒未用。 详见共享V26报告与20261018_mr3_p2a0_reflection.md；验收前不进入训练或后续步骤。

This tree contains ns-3.40 and ns3-gym within the single Git repository
`/home/zhuyulab/ns3-workspace`. Do not scan the whole framework unless needed.

First read the root AGENTS.md, then
`ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md`,
`IMPLEMENTATION_PLAN.md` and `AGENTS.md`.

The active route is MR3: exactly three robots, navigation RL under ideal
communication first, then frozen-policy gateway/ns-3 Wi-Fi effects. Current
`wireless-rl/sim.cc` is historical five-user toy scheduling; no robot policy or
ROS gateway is implemented there. Do not let its old DQN or report next steps
replace the active roadmap. The ROS workspace is in the same repository.

MR3-P0 was accepted by the user on 2026-10-14; P1A was accepted on 2026-10-15.
P1B was accepted by the user on 2026-10-15; freeze
`f9928fe` passed the same-freeze open/rooms/corridors seed101 adapter audits.
See the [P1B report](ns-3.40/contrib/opengym/examples/wireless-rl/report/20261015_mr3_p1b.md).
This is exclusive ideal goal ownership and logical delivered copies, not a
trained policy or gateway. K8/5 s do not prove 95% tasks. P1C's
fixed-step Gymnasium/IPC, full reset and isolated rewards are implemented and
validated at W7 `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; see
[environment contract](ns-3.40/contrib/opengym/examples/wireless-rl/MR3_ENV_CONTRACT.md).
The P1B asynchronous 1 s timer had 2/3 s rooms gaps. P1C independently validates
stepped 1 s transitions/reset/1-2-4-worker sampling; the non-stepped timer nominal cadence and skip rules are unchanged.
Its engineering checks include 762 ROS and 40 conda CPU tests. Retain only the original
`b328f84` fixed-interface GPU 3-forward/3-backward/0-update proof for P1C. P2A now has an eight-decision engineering checkpoint
(seed17, four GPU optimizer steps), without 95% task credit.
Freeze `5e47802` has 9 effective slots from 10 attempts, including one retained
native infrastructure failure; see the [P1A report](ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_p1a.md).
The user accepted P1C and authorized P2A's joint MaskablePPO minimum training/validation loop on 2026-10-16.
P2A is in progress; P2B and later remain unstarted. The separate 2D option and candidate
500k/72h per-run budget are not accepted. Short sampling does not prove multi-day stability.
