# wireless-rl Codex Memory

Last source/documentation review: 2026-09-23. Behavioral evidence is frozen in
the dated reports and is not automatically evidence for the current HEAD. The
user accepted P1C, P2A, P2B, P2C, and P2D. The P2C follow-up adds
Gazebo task-region overlays and a live operator status panel. P3A is implemented
and awaiting user acceptance; its final evidence contains ten gateway-routed
`COMPLETE`, zero-collision episodes across three fixed world/target/energy scenarios,
plus a two-robot forced-charge regression with two completed charges. Those P3A
results are frozen historical evidence: later HEAD commits changed coordinator,
battery, and clearance behavior, so P3A remains awaiting current-HEAD revalidation
and user acceptance. Current-HEAD P3A.5 revalidation at `41f63fb` passed the
graph/bypass subgate and forced-charge regression, but the formal matrix was
9/10 `COMPLETE`: lab seed 202 failed after episode start during rally. The
failed episode is retained; P3A.5 remains in progress and P3B has not started.
The roadmap review is recorded in `report/20260923_project_review.md`, and the
current run is recorded in `report/20260923_p3a5.md`.

This directory is the active project inside the larger ns-3 workspace. It is a
toy ns3-gym scheduling MDP, not a full Wi-Fi/5G network simulation.

The intended successor task reuses the ROS 2 project in this monorepo at
`/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap` for 2–3 robot collaborative
mapping, object search, charging, and rendezvous. Do not rebuild the robot stack
from scratch or assume that planned integration is already implemented. Read
`RESEARCH_PLAN.md` before proposing architecture or experiments.

## Source Of Truth And Reading Order

Use current code as the source of truth. Read in this order:

1. `RESEARCH_PLAN.md` for the final research goal, scope, architecture,
   evaluation contract, risks, and one-year roadmap. It is a plan, not a
   statement of what the current code already implements.
2. `IMPLEMENTATION_PLAN.md` for engineering checkpoints, exit criteria, and
   the current user-review boundary.
3. The ROS workspace's `launch_commands.md` for current copy-paste launch
   commands, world selection, and parameter names.
4. The ROS workspace's `user_guide.md` for the current task stack, metrics,
   and known limitations.
5. `sim.cc` for the actual environment state transition and reward timing.
6. `test.py` and `run_baselines.py` for baseline semantics and CSV fields.
7. `dqn_common.py`, `train_dqn.py`, and `evaluate_dqn.py` for DQN behavior.
8. `report/20260914_p1b.md`, `report/20260915_p1c.md`,
   `report/20260916_p1c.md`, and `report/20260916_p1c_foundation.md` for the
   ROS engineering checkpoints.
9. `report/20260917_p1c_optimization.md` and
   `report/20260917_p1c_generalization.md` for the final P1C evidence.
10. `report/20260917_p2a.md` for the P2A detector contract and evidence.
11. `report/20260917_roadmap_audit.md` for the revised gates and metric rules.
12. `report/20260917_p2b.md` for the P2B state-machine contract and evidence.
13. `report/20260917_p2c.md` for the P2C energy/charging contract and evidence.
14. `report/20260918_p2c_visualization.md` for the post-acceptance Gazebo
    regions and live status-panel follow-up.
15. `report/20260918_p2d.md` for the P2D runner, schema-v7 metrics, energy
    calibration, failures, and final matrix.
16. `report/20260902.md`, `report/20260429.md`, and `log.md` for historical
   experiment context.

The accepted P1A ROS foundation now has explicit Gazebo seeds, configurable spawn
timeouts, bounded automatic headless smoke checks, and verified 1/2/3-robot
startup. P1A itself proves startup and message flow only; P1B/P1C subsequently
added formal metrics and multi-seed task evidence.

The accepted P1B now provides an evaluator-only Gazebo truth channel, a truth occupancy
grid rasterized from static SDF box collisions, per-robot truth path and visit
masks, search overlap, Nav2 outcomes, base-contact collision events, and one-row
episode CSV/JSON. Its 2026-09-14 one- and two-robot short timeout runs passed.
The current world has one unsupported mesh collision (an SUV outside the lab
walls).

P1C now meets the original 90% coverage intent with a shorter evidence-based
time bound and was accepted by the user on 2026-09-17. All robots start inside the same
radius-1 m start/charging region in `my_world.world`; success is 90%
correct-free coverage within 180 simulated seconds. Earlier 75%/300 s results
were symptoms of foundational defects, not an exploration ceiling: the custom
SLAM callback never enabled `map->odom`, AMCL competed with SLAM during mapping,
the coordinator treated odometry as map coordinates, and frontier selection
blocked on a quadratic nearest-frontier loop. After fixing those causes and
using diverse, reachable 0.45 m-clearance observation points, seeds 101/202/303
reached 90% in 141.3/161.4/134.9 seconds, establishing the pre-optimization
baseline. The final shared-map/Smac/staged-navigation controller reaches 90%
with two robots in 98.9/79.6/104.4 seconds (mean 94.3) and with three robots in
78.3/69.8/69.5 seconds (mean 72.5) on seeds 101/202/303. All six final episodes
have zero collisions; maximum search overlap is 0.44%. 95% remains optional.

## Current Handoff Snapshot

- Active boundary: P3A.5 is in progress. The current-HEAD graph/bypass subgate
  passed, but the formal matrix has one retained post-start rally failure, so
  P3A is not accepted and P3B has not started.
- From P2B onward, only `COMPLETE` is mission success. The fixed first rally
  contract is per-robot position error <=0.35 m, linear speed <=0.05 m/s,
  angular speed <=0.10 rad/s, all robots continuously stable for 5 simulated
  seconds. `FOUND` and P1C's 90% coverage are process metrics.
- P2D is now a required integration gate after battery work: at least three
  prevalidated world/target/energy scenarios on seeds 101/202/303 establish the
  full ideal task baseline before any communication impairment.
- The frozen P2D scenarios are lab `(-4,4,40)`, rooms `(5,3,40)`, and corridors
  `(-4.5,-0.5,45)`. Final evidence combines the six lab/rooms episodes in
  `p2d_formal_ideal_energy40_v5` with all four corridors episodes in
  `p2d_formal_corridors_energy45_v6`; all ten are `COMPLETE` with zero
  collisions. Lab seed 202 completed one safety charge. The 40-energy
  two-robot corridors calibration timed out while returning, so the whole
  corridors scenario was frozen at 45 before its final batch.
- P3A.5 must re-audit the current HEAD to ensure the central execution chain has
  no direct subscriptions to robot maps, odom/TF or raw detection and no direct
  Nav2 action calls. Even the ideal baseline must traverse the same
  gateway/received-state/local-adapter path. Robot Nav2 global costmaps must
  consume only gateway-delivered fused maps; any regression rejects the batch.
- The current P3A.5 candidate is commit `41f63fb`: 9/10 formal episodes reached
  `COMPLETE`, zero collisions and zero infrastructure failures; lab seed 202
  timed out in `RALLY` after one safety charge. The evidence and next repair
  rule are in `report/20260923_p3a5.md`.
- P3A implementation uses `multi_robot_interfaces/GatewayEnvelope`, explicit
  per-route sequence/timestamp/ACK/TTL fields, zero-loss queues, gateway-delivered
  received-state topics, and a source/runtime `p3a_forbidden_bypasses.json` audit.
  Formal run `p3a_formal_gateway_3scenes_v2` passed all 10 episodes; the retained
  forced-charge check `p3a_gateway_forced_charge_2r_seed303` completed two charges.
- Formal runs distinguish retained pre-start infrastructure failures from
  post-start task failures; post-start failures cannot be replaced by reruns.
  P7 requires at least 20 paired held-out episodes for primary comparisons.
- P2A adds a visual-only `search_target` marker and an independent detector.
  The default contract is 3.0 m range, 90-degree horizontal field of view,
  static truth-grid line of sight, and three consecutive visible frames.
  Invisible frames reset the per-robot confirmation streak.
- The detector now publishes transient `/target_observation` and
  `/target_detection`; the coordinator is the sole `/task_state` publisher.
  On confirmed detection it cancels exploration, assigns distinct known-free
  target-facing poses, and reserves short map paths for at most two concurrent
  robots. Conflicting routes wait and a lower-priority robot yields if live
  positions converge. The fixed 5-second stability window remains required
  before `COMPLETE`.
- Final P2B three-robot seeds 101/202/303 completed in
  134.5/171.9/177.3 simulated seconds with zero collisions and minimum assigned
  separation 1.210/1.221/1.414 m. Maximum final pose error was 0.237 m. The
  two-robot seed-303 cross-check completed in 96.5 seconds with zero collisions.
  Full-task timeout is 300 simulated seconds; details and retained failures are
  in `report/20260917_p2b.md` and `log.md`.
- The follow-up P2B audit added schema-v5 `coverage_at_detection` and made any
  post-start collision authoritative `success=false`. A two-robot check found
  the target at 75.57% coverage and completed at 81.62% with 97.40% observed
  accuracy and zero overlap/collisions, confirming that low coverage is the
  intended stop-on-found behavior. Failed rally actions now retry shorter legs;
  unsafe parallel rally and an over-eager progress watchdog were tested and
  reverted. See `report/20260917_p2b_audit.md`.
- The user-observed serial-rally bottleneck is replaced by conflict-aware
  concurrency: 1.5 m legs reserve 1.2 m-separated map paths, at most two robots
  move concurrently, and live proximity triggers lower-priority yielding.
  Seeds 101/202/303 completed in 131.0/139.2/146.2 seconds with zero collisions.
  Mean `RALLY`-to-`COMPLETE` time fell from the formal serial baseline's 77.6
  seconds to 61.7 seconds. The unrestricted three-way prototype was rejected
  after 18 collision events on seed 101.
- P2C runs one local `battery_manager` per robot. Energy is reduced by odom
  distance and simulated elapsed time; `c_tx=0` until P3 supplies a byte
  ledger. The manager triggers a non-overridable safety-reserve return to the
  robot's distinct spawn/charging pose, requires stationary charging, then
  restores full energy without resetting SLAM or task state. Exhaustion,
  unreachable return, and charge timeout have explicit failure reasons.
- The forced-charge two-robot seed-303 episode used capacity 100, initial
  energy 18, movement cost 1/m, idle cost 0.02/s, margin 5, and 10-second
  charging. Both robots charged once, minimum energy was 6.66, and the mission
  reached `COMPLETE=190.1 s` with zero collisions and zero search overlap.
  Evaluator schema v6 records per-robot energy and charging metrics. See
  `report/20260917_p2c.md` and `log.md`.
- Manual launch now defaults to visual-only Gazebo overlays for the common
  start/charge region, per-robot charger discs, target detection radius, and
  eventual rally poses. A separate Qt panel displays task/activity, Nav2,
  battery, pose, and speed per robot. Battery managers now default on for the
  main manual launch. Headless smoke explicitly sets its requested battery and
  region modes and always disables the panel.
- Final P1C evidence uses seeds 101/202/303, 90% correct-free coverage, and an
  unchanged 180-second hard limit. Two-robot time-to-90 is
  98.9/79.6/104.4 seconds; three-robot time-to-90 is 78.3/69.8/69.5 seconds.
- The controller extracts frontiers and paths from `/merge_map`, assigns
  spatially distinct goals, excludes teammate positions, and stages paths over
  5 m. Nav2 consumes the same merged map with Smac 2D and a complete non-rolling
  global costmap. Local lidar/DWB still performs dynamic obstacle avoidance.
- The readiness gate requires both action discovery and
  `/tbN/bt_navigator=active`; action discovery alone previously admitted a
  stack that rejected every goal.
- Final validation and commit/push details are recorded in `log.md` and
  `report/20260917_p1c_optimization.md`.
- Cross-map validation adds `p1c_open.world`, `p1c_rooms.world`, and
  `p1c_corridors.world`. Three robots reached 90% on seeds 101/202/303 in all
  nine episodes; the worst time was 75.5 seconds, all had zero collisions,
  minimum accuracy was 97.47%, and maximum overlap was 1.91%. A two-robot
  hardest-case check took 85.5 seconds with zero collisions. Details are in
  `report/20260917_p1c_generalization.md`.
- The launch, smoke tool, and baseline runner accept a world filename. The
  default remains `my_world.world`; no exploration, Nav2, truth, sensor, speed,
  safety, or scoring rule changed for generalization validation.
- No ROS/Gazebo experiment process was running when this handoff was written.
- The worktree intentionally still contains user-owned report changes:
  deleted `report/20260914.md` and untracked `report/20260914_p1a.md`. Do not
  restore, stage, rename, or commit them unless the user asks.

For a manual two-robot Gazebo demonstration, use `enable_merge_rviz:=false` to
avoid running both heavy visual frontends. Successful startup prints:

```text
All 2 Nav2 stacks are active.
Nav2 ready; starting cooperative exploration.
```

If the gate times out, diagnose the named robot's lifecycle and TF chain; do
not restore a long fixed delay or silently run with only one robot.

Do not treat the dated report as current configuration. Do not overwrite it
when current code changes; write a new dated report for a new research stage.

## Environment And First Check

**Mandatory:** run every project Python command from the conda environment
`ns3gym` at `/home/zhuyulab/miniconda3/envs/ns3gym`. This includes
`test.py`, all baseline runners, DQN training/evaluation, and plotting scripts.
Do not use the base conda environment or the system Python. The Python process
in this environment imports `ns3gym` and launches the local ns-3
`wireless-rl` executable.

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
python test.py --agent greedy --seed 1 --simTime 1 --stepTime 0.5 --no-save --no-plot
```

The 2026-09-02 environment has Python 3.10.20, NumPy 2.2.6, CUDA PyTorch
2.11.0+cu128, and two NVIDIA GeForce RTX 4090 GPUs. Prefer `--device auto`,
which selects `cuda:0`. The old Gym maintenance warning is present, but the
smoke test succeeds.

The user-site package `~/.local/lib/python3.10/site-packages/torch
2.12.0+cpu` can shadow the correct conda CUDA build. The conda environment is
configured with `PYTHONNOUSERSITE=1`; preserve this setting. If CUDA
unexpectedly becomes unavailable, reactivate the environment and check
`torch.__file__` before reinstalling anything.

Restore the setting if the conda environment metadata is lost:

```bash
conda env config vars set PYTHONNOUSERSITE=1 -n ns3gym
conda deactivate
conda activate ns3gym
```

Before diagnosing import, Gym, PyTorch, or ns3-gym failures, verify:

```bash
which python
python -c "import ns3gym; print(ns3gym.__file__)"
python -c "import torch; print(torch.__file__, torch.__version__, torch.cuda.is_available())"
```

`which python` must resolve under
`/home/zhuyulab/miniconda3/envs/ns3gym/bin/`.

Run the automated regression check after source or environment changes:

```bash
python check_project.py
```

It requires CUDA and checks the conda environment, a DQN GPU
forward/backward step, the ns-3 build, a short simulation, and fixed-seed
reproducibility.

If `sim.cc` changes:

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40
./ns3 build wireless-rl
```

ns3-gym uses local ZMQ ports. Tool sandboxes may require permission for a smoke
test even though the project itself does not use external network access.

## Current Environment Contract

- 5 users; observation dimension 15.
- Observation: `[cqi0, queue0, delay0, ..., cqi4, queue4, delay4]`.
- Action `i` serves user `i`.
- CQI is bounded 1–10 and changes by a random integer in -2..2 per step.
- Arrival is a random integer 0–5 per user per step; queue is capped at 100.
- Service is `min(queue_i, 2 * cqi_i)`.
- Delay is capped per-user backlog age, not packet delay.
- A miss is a currently backlogged user with `delay > 8`, not a packet drop.
- Episode length is `ceil(simTime / stepTime)`.

Reward is captured after service and before the next arrival:

```text
served - 0.01 * rewardQueue - 0.1 * totalDelay - 5.0 * deadlineMisses
```

Do not conflate reward snapshot fields (`rewardQueue`, `totalDelay`,
`deadlineMisses`) with current-state fields (`currentQueue`, `currentDelay`,
`currentDeadlineMisses`). Formal summaries use the reward snapshot delay and
miss fields.

## Experiment Contract

Baseline agents must stay aligned between `test.py` and the `BASELINES` list in
`run_baselines.py`:

```text
random round_robin max_cqi max_queue max_delay greedy delay_aware
```

Use a new ns-3 process per seed. Do not use `test.py --iterations > 1` for
formal results because the C++ environment uses globals and reset completeness
has not been established.

Training seeds are `seed + episode`. Validation seeds select `_best.pt`; final
evaluation seeds must be separate from training and validation. Baseline and
DQN comparisons require identical evaluation seeds, `simTime`, and `stepTime`;
`compare_dqn_with_baselines.py` does not validate this for the caller.

## Historical Result To Preserve

The best retained 2026-04-29 checkpoint is:

```text
models/dqn_exp06_evalselect_p5k_h256_best.pt
```

It is a 15-input, 5-action, hidden-256 dueling Double DQN with a 5000-step
`delay_aware` synthetic warm start. It was selected at zero-based episode 249
using validation seeds 1001–1003. On evaluation seeds 1–10 it beat `greedy` on
reward, backlog-age delay, and deadline misses, while losing some throughput
and fairness. Exact numbers are in `USER_GUIDE.md` and `report/20260429.md`.

Important: training used simulation seeds 1–300, so the historical evaluation
seeds 1–10 overlap training. The result is not a held-out generalization test.
This issue has now been addressed by rerunning the checkpoint and all baselines
on fresh seeds 2001–2010. DQN beat `greedy` on cumulative reward, backlog-age
delay, and deadline misses on all 10 seeds. Aggregate DQN versus `greedy`:

| Metric | DQN | Greedy |
|---|---:|---:|
| reward | -128.586 | -284.997 |
| throughput | 9.8200 | 10.1275 |
| reward queue | 69.9400 | 64.6425 |
| total delay | 35.9775 | 46.8100 |
| misses | 1.7475 | 2.3850 |
| fairness | 0.9460 | 0.9791 |

See `report/20260902.md`. This remains evidence for the current toy MDP only.
The main research limitation is the environment model, not the lack of more RL
algorithms.

## Change Discipline

- Keep changes small and code-driven; do not add architecture for hypothetical
  future protocols.
- Do not change environment or reward semantics during DQN-only work.
- If state shape or normalization changes, update `sim.cc`, `test.py`, and
  `dqn_common.py` together and treat existing checkpoints as incompatible.
- If reward timing or metric meaning changes, update `USER_GUIDE.md` and write a
  new dated report; preserve historical reports.
- Run the shortest relevant smoke test after code changes. Use multi-seed runs
  for research claims.
- Append every training, evaluation, baseline sweep, ablation, and formal
  smoke/regression run to `log.md` in the same work session. Include failed or
  interrupted runs, exact commands, seeds, parameters, outputs, and conclusions.
  Updating the log is part of completing the experiment, not optional cleanup.
- Generated files under `runtime/`, `models/*.pt`, and `__pycache__/` are ignored
  and should not be committed unless explicitly requested.
- Before any commit, use `git add -n .` and confirm only intended source/docs or
  selected report assets are included.
- The repository root is `/home/zhuyulab/ns3-workspace`; ns-3 and ROS 2 are in
  the same monorepo. After a verified modification, commit it and push the
  current branch to `origin` in the same work session unless the user explicitly
  says not to.
