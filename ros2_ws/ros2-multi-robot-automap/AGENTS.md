# ROS component memory — MR3

2026-10-17 continuation: P2A.0 remains authorized and incomplete. V16 clean pushed freezeebe7d51b completed interface32, strict closure and9 mandatory gates, but physical stopping coverage FAIL for tb1; terminal/reset/deadline SKIP. Full/input activity and angular gates pass; tb1 only has20-80ms prior linear segments and no meaningful A/B. Actual original GOAL masks are absent in the13-15s second window and return at22s; investigate candidate availability and bounded late stimulus before new freeze. Preserve original task/body/stop gates and all FAILs, complete one new reviewed clean pushed full four-stage matrix. No PPO/P2B/gateway; pilot balance1870 decisions/2905.954739546403 wallsec unchanged. See wireless-rl/report/20261017_mr3_p2a0_v16.md.

Historical first P2A.0 closure (2026-10-17): source freeze f8694025; six native episodes
closed cleanly, terminal audit PASS, reset benchmark/full audit FAIL with one
real peer-envelope task failure. The 300-step deadline was SKIPPED under the
prospective stop rule. P2A.0 exit is unmet; await user review, do not restart
pilot. Shared navigation-map occupied starts are now proved from exact raw maps.

2026-10-17: user authorized P2A continuation/preparation. Current substep is
MR3-P2A.0, with no new pilot: repair SLAM teardown ownership, retain failed
collection evidence, version the received-frontier union and add safety input
diagnostics. See shared `report/20261017_mr3_p2a0.md`; user acceptance of this
substep precedes later preparation/training. P2A remains incomplete.

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
P2A is in progress; P2B and later remain unstarted. The separate 2D option and candidate
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
