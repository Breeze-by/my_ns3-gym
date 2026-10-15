@/home/zhuyulab/.codex/RTK.md

# Codex Monorepo Memory — MR3

## Canonical checkout and components

The only Git root is `/home/zhuyulab/ns3-workspace`. Both components belong to
this same working tree and the same `origin` (`Breeze-by/my_ns3-gym`):

- `ros2_ws/ros2-multi-robot-automap/`: ROS 2 Humble, Gazebo Classic, TurtleBot3,
  SLAM, Nav2 and collaborative mapping.
- `ns-allinone-3.40/ns-3.40/`: ns-3.40, ns3-gym and the historical wireless-rl
  toy scheduling environment; the future MR3 gateway/network component.

The ROS tree was imported using git subtree on 2026-09-02. It is not a
submodule/nested repository. The former standalone checkout and compatibility
symlink under `/home/zhuyulab/ros2_ws/` were removed; use canonical paths only.

## Read first and authority

Before research or architecture decisions read, in order:

1. `ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md`.
2. The adjacent `IMPLEMENTATION_PLAN.md` for the current acceptance boundary.
3. The adjacent `AGENTS.md` for component/environment/evidence rules.
4. `ros2_ws/ros2-multi-robot-automap/user_guide.md` and `launch_commands.md` for
   actual current ROS behavior and executable commands.
5. `wireless-rl/report/20261014_mr3_route_audit.md` and `report/README.md` as needed.

Current code determines implemented behavior. Plans describe intended work;
dated reports and native artifacts establish results only for their original
source/contract. Historical reports, archived plans and upstream READMEs do not
set the active research route. Avoid repeating detailed chronology in guides.

## Active route and user acceptance

The user's 2026-10-14 direction supersedes the earlier research route:

- Exactly **three robots**, tb1/tb2/tb3; no new 2/4/5-robot research matrices.
- First replace hand-coded global exploration decisions with a centralized
  joint RL policy. Retain SLAM/map fusion and local Nav2; start with stable
  subgoals, not unrestricted velocity or a hand-planner fallback.
- Establish a reliable **95%** mapping task under ideal communication, then
  freeze weights, normalization, observation/action and execution contracts.
- Route application uplink/downlink bytes through gateway and genuine ns-3
  Wi-Fi (1 AP + 3 STA). Received-only maps/states/goals/ACKs must causally govern
  the backend and remote shared information used by robot navigation/safety.
- No target search, charging, rally, learned communication scheduling or
  hardware work. Network remedies and deployment are outside this roadmap.

New checkpoints are namespaced **MR3-P0 … MR3-P5**, with individual substep
acceptance. Complete and verify each substep, commit/push, present evidence,
and wait for the user's explicit acceptance before the next substep.
Old P1C/P2C acceptance or PASS cannot be reused as MR3 credit.

Current boundary: **MR3-P0 accepted on 2026-10-14; MR3-P1A accepted by the user on 2026-10-15; MR3-P1B in progress**.
P1A implementation and validation are complete as of 2026-10-15. The user explicitly authorized P1B on 2026-10-15. P1B implements the ideal
observation/goal adapter; P1C and later remain unstarted. No training or gateway
work is authorized by P1B.

## Current implementation and evidence

`main` was restored from P1C `99cf3a6` and repaired. Pre-route document commit
is `81b2f8b`; historical repair freeze is `c9344e1`. P1A changes the active launch and check defaults to three, retaining 1–4
compatibility without new non-three research runs. Use the explicit MR3 task
contract for 95% schema4 evaluation; legacy schema3 remains diagnostic only.

The source still uses a handcrafted frontier controller, common-frame
conservative map fusion and Nav2. No three-robot RL policy or ROS/ns-3 gateway
exists. Historical five-user/15-input/5-action toy DQN is a separate task.
P1A now measures all six actual body collisions per robot (18 streams), with
continuous freshness, raw publication-sequence audit and navigation terminal
closure. Freeze `5e47802` has 9 effective scene/seed slots: 6 strict successes
and 3 peer-envelope safety failures. All 10 attempts retain one native shutdown
infrastructure failure; a prospectively declared same-freeze replay fills its
slot without proving the SDK crash fixed. See the
[P1A report](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_p1a.md)
and shared `log.md`. The historical
`c9344e1` rooms/corridors seed101 90% evidence and base-only zero-contact records
retain their original scope; they do not supply MR3 credit.

The explicit ROI/95% contract, scene audits and sustained contact monitoring
are implemented for P1A validation. RL goal ownership, complete episode reset,
removal of raw shared-map/peer-pose bypasses, actual payload transport and
causal simulation clocks remain later scheduled gates.

## Engineering judgment

Use independent engineering judgment, simple direct solutions, existing code
and mature dependencies. Preserve correctness, data safety and research
validity; do not limit necessary analysis or validation to save tokens.
User requirements take precedence over repository preferences. Keep scope
focused. The two removed coding-guideline skills must not be reinstalled,
invoked, or used as constraints (user preference 2026-10-12).

Do not hide a hand-coded exploration policy behind the RL adapter, expose truth
to actor/candidates/masks/safety, loosen failed task gates, cherry-pick seeds,
or assemble a matrix across different code freezes. Ground truth is permitted
only for isolated evaluation/training reward and network propagation position.
Local own sensors remain local; cross-robot information must respect delivery.

## Environments

Wireless-rl/ns3-gym Python uses conda `ns3gym`, preserving
`PYTHONNOUSERSITE=1`; see nested instructions. ROS nodes use system ROS Python:

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
export PYTHONNOUSERSITE=1
/usr/bin/python3 /usr/bin/colcon build --symlink-install --allow-overriding nav2_bringup
source install/setup.bash
```

Do not copy old ROS build/install/log directories or mix conda and ROS Python
through ad hoc PYTHONPATH. Colcon absolute-path caches must be regenerated at
the canonical location when needed. Preserve evidence logs; only stop owned
process groups. Separate wall-clock startup guards from sim-time task budgets.

## Git, push and experiment discipline

Only `main` and original-route backup `p2c1/global-mission-20261012` are maintained.
The backup's latest complete state is `8fe1495`; leave it untouched unless the
user requests otherwise. Do not create extra archival branches, force-push or
rewrite shared history. Both components stay together on each feature branch.

Every completed modification must be committed and pushed to `origin` in the
same session unless explicitly instructed otherwise. Before every commit:

1. Run the shortest relevant checks; documentation-only changes need static
   links/consistency/evidence checks, not simulator or training runs.
2. Run `git diff --check` from the Git root.
3. Run `git add -n .`; exclude accidental build/runtime/log/bag/map/checkpoint
   artifacts. Selected canonical research evidence may be intentionally tracked.
4. Commit focused changes and push the current branch.

Whenever a launch argument, default component, recommended mode or copy/paste
launch command changes, update ROS `launch_commands.md` in the same commit.
Every training, evaluation, baseline, ablation, formal smoke, simulator or
hardware experiment is appended, including failures/interruptions, in the
same session to:

`ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/log.md`.

Record exact command, freeze, seeds, parameters, outputs and conclusion. Keep
one canonical evidence set. Do not relabel old failures or rewrite experiment
history; archive/supersession locations belong in `report/ARCHIVE_INDEX.json`.
