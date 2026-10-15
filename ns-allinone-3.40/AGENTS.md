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
P1B implementation/validation is complete, awaiting user acceptance; freeze
`f9928fe` passed the same-freeze open/rooms/corridors seed101 adapter audits.
See the [P1B report](ns-3.40/contrib/opengym/examples/wireless-rl/report/20261015_mr3_p1b.md).
This is exclusive ideal goal ownership and logical delivered copies, not RL,
training or gateway. K8/5 s describe the interface; they do not prove 95% tasks.
The nominal 1 s timer had 2/3 s rooms snapshot gaps; fixed dt/throughput are P1C gates.
Freeze `5e47802` has 9 effective slots from 10 attempts, including one retained
native infrastructure failure; see the [P1A report](ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_p1a.md).
P1C and later steps remain unstarted; obtain explicit P1B acceptance before P1C.
