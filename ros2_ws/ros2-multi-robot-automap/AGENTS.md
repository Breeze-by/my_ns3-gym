# ROS component memory — MR3

2026-10-19：P2A.0已验收，P2A未完成。V13运行时冻结`0063aa233ba3008ddcc1eb09ea8068112eea3965`完成独立26+4+8=38/38工程资格，原矩阵时间FAIL及optional覆盖FAIL保留。fresh16 minimum随后因tb3整段累计路径.007800136333791129>.0078m而真实FAIL；瞬时速度未越.01，整轮ineligible，eligible训练决策/API记录/优化更新均0，49保存PID/start均gone。pilot与三场final-only未启动，P2B/gateway未启动。

用户已批准工程累计34000墙秒，当前31596.4775930946018、余2403.5224069053982；pilot1870决策/2905.9547395464029墙秒及验证额度未动。安全/任务/源龄/接触门不变，无新native重试。下一步仅有安全契约CPU/math重设计评审，坐标/连续模型/真实执行交接未闭合，不能seal或启动native。见[V13完整结果](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261019_mr3_p2a_v13.md)。

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
P2A is in progress and incomplete; P2B and later remain unstarted. The separate 2D option and candidate
500k/72h per-run budget are not accepted; gateway work is not authorized. K8/5 s describe the interface version,
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
