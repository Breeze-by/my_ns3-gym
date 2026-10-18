# ROS component memory — MR3

2026-10-19：P2A.0已验收，P2A仍未完成。V8同冻结`7bbf7ba97e12e3b5db47fb48d7ffa4ccf0740971`两组原生转向诊断共8决策/0策略调用/0优化，刺激与严格关闭均通过；两组4s的最大平面速度约.00229，未复现V7近身/~3s后反例，不能称物理修复。V7原FAIL、V26原父编排中断及所有旧失败保留。工程累计12835.5243178396018/30000墙秒，余17164.4756821603982；pilot余额1870决策/2905.9547395464029墙秒不动，验证不扩额。下一步仅准备真实WORLD odom/对应TF独立50Hz，保持轮执行器30Hz及全部旧门；尚无新修复native信用，P2B/gateway未启动。详见V8报告。

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
