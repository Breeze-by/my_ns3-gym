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

MR3-P0 documentation awaits user acceptance; later steps are unstarted.
