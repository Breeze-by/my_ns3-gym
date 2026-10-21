# ROS component memory — MR3

2026-10-21 V26准备：按用户“继续”执行一次三开发场景只读几何审计，最多120工程秒（consumer90），不创建World/Node/episode或训练。几何21/守护10/元数据5项CPU通过；保留原ROI/质量门和全部旧FAIL。入场余6559.4631148643982，pilot/final-only不动；新clean冻结/前检后唯一执行，当前尚未实测。见[V26](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v26_geometry.md)。

2026-10-21 V25 CPU收口：协议117、人工建图7、导航缓存等价21项通过；仅按精确几何输入复用路径场，原scan/pair/源龄与pure源码保持。人工厚box的端点图IoU上限112/697低于.20，另有格线/2mm误差反例；不宣称实际三场不可达。下一步先量化代理质量可达性/逆传感器模型，不直接PPO或重跑V24。本轮无formal/工程新增，仍余6559.4631148643982秒，pilot/final-only不动；P2A未完成。见[V25](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v25_cpu.md)。

2026-10-21 V24闭合FAIL：冻结9b33cf9b6ab491fd5e3b15269adb30d43be1354c实跑三场，544attempt/543verified return/1rooms错误，205/173/165sim秒均未完成任务。协议确认173.1s goal_lease_expired而上次返回仍非终态、次submit才stopped；原FAIL不改/不重跑，post-advance tick分类修复已通过27项CPU，未正式重验，租约/频率/门限保持。含有限故障提取实费1371.868831523秒，累计45440.5368851356018/52000、余6559.4631148643982；20保存身份gone、无训练/原生/pilot/final-only。下一步先接口/代理质量与长步成本，不直接PPO。见[V24](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v24_behavior.md)。

2026-10-20 V23闭合：profile与优化后短容量均PASS；短冻结2e8fcac9439a1a53e3913e45abccdc0b6645825d实跑1/4env、30短EP/240attempt/240verified return、0step错误/30正常关闭，73保存身份gone。含reset/close单env .240650848、四env合计 .610735060步/墙秒；仅8步短容量、无训练/原生资格。V23总实费806.844068675秒，累计44068.6680536126018/52000、余7931.3319463873982；pilot/final-only不动，旧FAIL保留，P2A未完成。见[V23](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_v23_performance.md)。

2026-10-20 V23续接授权：用户“按你的想法继续”，推进新有界性能剖析/提速及短容量：profile最多1EP/8attempt/600秒，优化后一次1/4env短容量最多30EP/240attempt/1800秒，均含审计/外尾，工程仍限52000、入场余8738.1760150623982。旧V22 FAIL不重试/改判；训练、pilot/final-only、原生迁移/gateway/扩额不启动。见[V23预声明](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_v23_performance.md)，先测再优化、每次新freeze。

2026-10-20 V22闭合：冻结`1dc2a1f601693f542479f9b6b7c54c69519b5460`二维符合性6原件+3合成及独立review通过；唯一零更新容量活动284尝试/返回、0step错误，但首场open101未完成、无实际4env，严格时间差与审计verified计数缺陷使完整活动FAIL。旧FAIL不改/不重跑；17保存身份gone，新增1781.490347088秒，累计43261.8239849376018/52000，余8738.1760150623982。pilot/final-only不动，P2A未完成；常规整数时钟/审计信用CPU修复不供新资格，训练/迁移/gateway未启动。见[V22闭合与下一步](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_v22_proxy2d.md)。

2026-10-20 V22授权：用户答复“继续，同意”，已接受二维代理实现、接口符合性和一次零更新容量活动；9000次ENV.step尝试/3600墙秒/最多30回合，1及4env共用上限，0模型/GPU/optimizer，无重试或补样。入场工程余10519.6663621503982/52000，pilot/final-only不动；训练、原生重试/迁移、60000、冻结规则变更和gateway均未授权。见[V22](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_v22_proxy2d.md)。

2026-10-19 V18：同tick因果与reach接收队列修复，140项ROS及有限DDS对照通过；旧完整replay因历史缺ACK保持FAIL。新冻结完整资格待执行，P2A未完成。工程32494.9044856606018/52000，余19505.0955143393982；pilot/验证不扩额。见[V18记录](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261019_mr3_p2a_v18.md)。

2026-10-19：P2A.0已验收，P2A未完成。用户已批准V14科学候选并授权生产实现；V15实现显式`mr3-reach-v1`安全模式、真实应用/同源校准回执、完整模式交付及版本化必要审计器，当前完成CPU/编译准备，待新冻结完整原生资格。默认`legacy`保留，旧FAIL不改判；本轮无新native/GPU/pilot/验证，P2B/gateway未启动。见[V15实现与验证](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261019_mr3_p2a_v15.md)和[新契约](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_REACH_CONTRACT.md)。

2026-10-19用户已批准工程累计上限52000墙秒，并授权后续实现/修复直接推进；工程已用32494.9044856606018/52000墙秒，余19505.0955143393982；pilot1870决策/2905.9547395464029墙秒及三场final-only额度未动。旧V13同冻结独立38/38仅有原工程信用，原矩阵/optional/minimum FAIL保留；minimum整轮ineligible、0 eligible/0更新。详见[V13原始结果](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261019_mr3_p2a_v13.md)。

Follow `/home/zhuyulab/ns3-workspace/AGENTS.md`. Read the shared
`ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md`
and `IMPLEMENTATION_PLAN.md` before research decisions. Current executable
commands are in `launch_commands.md`, actual behavior in `user_guide.md`.

Fixed research team: tb1/tb2/tb3. First centralized joint RL exploration with
stable subgoals and local SLAM/Nav2; later frozen-policy gateway/ns-3 Wi-Fi.
No target search, charging, rally, other robot counts or hardware roadmap.
MR3-P0 was accepted by the user on 2026-10-14; P1A was accepted on 2026-10-15.
P1B was accepted by the user on 2026-10-15; `f9928fe`
passed same-freeze open/rooms/corridors seed101 scripted adapter audits. See the
[P1B report](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261015_mr3_p1b.md).
Freeze `5e47802` has 9 effective slots from 10 attempts, including one retained
native infrastructure failure; see the [P1A report](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_p1a.md).
The user accepted P1C and authorized P2A's joint MaskablePPO minimum training/validation loop on 2026-10-16.
The user accepted P2A.0 and explicitly authorized continuing P2A on 2026-10-18.
P2A is in progress and incomplete; P2B and later remain unstarted. The bounded 2D implementation/conformity/zero-update capacity scope was accepted on 2026-10-20; 2D training and the candidate 500k/72h quota remain unaccepted; gateway work is not authorized. K8/5 s describe the interface version,
not a 95% task proof. The nominal 1 s snapshot timer had 2/3 s rooms gaps;
P1C provides separate W7 stepped fixed-dt/reset/1-2-4-worker engineering evidence.
The non-stepped timer nominal cadence and skip rules remain unchanged. See the
[environment contract](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_ENV_CONTRACT.md).

Active launch/check defaults are three; 1–4 compatibility remains without
new non-three research runs. Explicit MR3 contracts select schema4 evaluation.
Default baseline launches handcrafted control; the mutually exclusive adapter
owns stable goals with logical ideal-delivery copies and no exploration fallback.
P1C implements and validates a fixed-step environment and sampling CLI, not a trained RL
policy or gateway. Historical reports are evidence, not instructions.

Use system ROS2 Humble Python, preserving PYTHONNOUSERSITE=1; learner conda is
separate. Keep canonical workspace paths, clean owned-process shutdown and
native failure evidence. Do not copy old build/install caches into this tree.

P1B verified ownership/KEEP/commit and ideal navigation copies; P1C independently validates
complete process reset and fixed physical stepping at W7 `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`.
Its checks include 762 ROS semantic and 40 conda CPU tests, plus the full eight-stage engineering matrix.
Retain only the original b328 GPU 3-forward/3-backward/0-update interface scope.
Short runs do not prove multi-day stability, 95% RL success or a DDS internal-race repair.
Before networking audit raw
baseline shared inputs, ideal same-process/DDS delivery, action callbacks and truth leakage. Robot
local sensing stays local; cross-robot information obeys actual delivery.
Source ages, physical footprint, contacts and task deadlines cannot be relaxed
to hide failures. Do not introduce a hidden handcrafted exploration fallback.

Every completed change is verified, committed and pushed in-session. Launch
commands/defaults change with launch_commands.md in the same commit. Append
all simulator/training/evaluation attempts, including failures, to the shared
wireless-rl/log.md. After each MR3 substep wait for the user's acceptance.
