# ns-allinone component memory

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
`b328f84` fixed-interface GPU 3-forward/3-backward/0-update proof; no policy training has begun.
Freeze `5e47802` has 9 effective slots from 10 attempts, including one retained
native infrastructure failure; see the [P1A report](ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_p1a.md).
The user accepted P1C and authorized P2A's joint MaskablePPO minimum training/validation loop on 2026-10-16.
P2A is in progress; P2B and later remain unstarted. The separate 2D option and candidate
500k/72h per-run budget are not accepted. Short sampling does not prove multi-day stability.
