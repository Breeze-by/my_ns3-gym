# wireless-rl Codex Memory

Last source/documentation review: 2026-10-01. Behavioral evidence is frozen in
the dated reports and is not automatically evidence for a different HEAD. The
user accepted P1C, P2A, P2B, P2C, P2D, P3A, and P3A.5. The P2C follow-up adds
Gazebo task-region overlays and a live operator status panel. Historical
integration commit `2933c24` was revalidated with two clean runner batches
covering the fixed 10-cell matrix: all 10 episodes are `COMPLETE` with zero
collision events, both manifests report `worktree_dirty=false`, the graph/source
bypass audits pass, and the forced two-robot regression completes two charges.
P3B is accepted only for its deterministic application-layer fault transport,
protocol matrix, ledger, and stale-state semantics. The remaining full-task
fault work is now P3B.5; gateway metrics and default visualization are P3C;
ns-3 packet/clock coupling remains P4A. Earlier `41f63fb`, `c369c7d`, and
`561de99` failures remain historical retained evidence and are not silently
replaced.

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
16. `report/20260928_project_overview_p0_p3b.md` for the beginner-oriented
   end-to-end project background, P0–P3B implementation status, P3B.5/P3C
   planning, evidence, boundaries, and future roadmap.
17. `report/20260928_p3b.md` for the P3B deterministic fault gateway,
   protocol matrix, retained ROS failure, and accepted-scope boundary.
18. `report/20260928_p3b5_plan.md` for the remaining fault-mode task matrix,
   robot freshness safety contract, partial completion, and exit conditions.
19. `report/20260928_p3c_plan.md` for gateway communication metrics,
   real-time curves, default visualization, and data-conservation gates.
20. `report/20260902.md`, `report/20260429.md`, and `log.md` for historical
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

2026-10-01 P3A.6集成门禁通过，用户于2026-10-01验收通过。当前冻结任务栈
`task_stack_frozen_commit=22c95a770a8812452c43fc177e4a00b5c032e6ef`，clean三批次1+7+2覆盖固定十格，
全部COMPLETE、零碰撞/失效/耗尽、零基础设施失败或整格重试。同提交forced303为
190.4 s COMPLETE、tb1/tb2各一次充电、零碰撞/耗尽。127项组件测试、四包构建、
源码审计及十一份通信图回放通过。最大固定最终误差.16194 m、最低电量15.89092；
forced最低8.63739。lab101最长293.4 s，开发种子不是holdout统计证据。
冻结算法包含RPP、射线收益、分层观察点、可视预约航点、最近离通道避让、相关TF限频、
完整集结能量预算及同gateway可靠TTL10 s串行提前充电请求。baec4e8/c08ca65等
所有超时/碰撞/post-start中断保留，不混入当前矩阵。精确命令、manifest和SHA256见
report/20261001_p3a6_freeze.md/.json及log.md。P3B.5是下一检查点，网络/RL未启动；
以后改任务栈必须另开批次重验证。用户报告未修改；临时Git排除已在收尾移除。

- Active boundary: P3A.6 passed; P3B.5 is next, before network/RL work. P3A and
  P3A.5 acceptance applies to their historical task-stack evidence. The historical integration freeze candidate is
  `task_stack_frozen_commit=2933c24`; clean 6+4 runner batches cover all ten
  fixed cells with `COMPLETE` and zero collisions, and the forced-charge
  regression completes two charges. P3B's deterministic application-layer
  fault gateway and protocol matrix are user-accepted. After P3A.6 passes, proceed
  to P3B.5 (fault-mode Gazebo task matrix and safety degradation), followed by P3C
  (gateway metrics and default visualization); P4A remains the later ns-3 bridge.
- Historical P3A.5 evidence is retained at `log/p2d_baseline/p3a5_final_2933c24/`
  (lab/rooms six cells),
  `log/p2d_baseline/p3a5_final_2933c24_corridors_net/` (corridors four cells),
  and `log/p2d_baseline/p3a5_final_2933c24_forced2r/` (forced charge). The
  split is documented because the first runner shell stopped after six cells;
  it does not represent a source or configuration change.
- From P2B onward, only `COMPLETE` is full mission success. If a robot is
  explicitly isolated as failed, the remaining healthy robots may finish with
  `PARTIAL_COMPLETE`; this is a recorded partial result, not a full-success
  episode. The fixed first rally
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
- The accepted P3A.5 evidence audited the central execution chain for direct
  subscriptions to robot maps, odom/TF or raw detection and direct Nav2 action
  calls. Even the ideal baseline traverses the same
  gateway/received-state/local-adapter path, and robot Nav2 global costmaps
  consume gateway-delivered fused maps. Any future regression rejects a batch.
- The prior P3A.5 candidate `41f63fb` reached 9/10; the path-guard commit
  `c369c7d` was rerun on the same 10-cell matrix and reached 8/10, with lab
  seed 202 and rooms seed 303 timing out during `EXPLORE`. Both failures are
  retained. The evidence and next diagnostic rule are in
  `report/20260923_p3a5.md`.
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

2026-10-04 P3B.5 v43完整57次候选已自然结束，冻结584dadc；最终严格门禁FAIL，尚未完成P3B.5。十固定格原生合格COMPLETE，57次均0接触/0基础设施失败，57份时序账本审计PASS，425组件/四包build/54协议矩阵通过；这些不能代替完整门禁。主强制充电ideal中央297.5s声明COMPLETE，但300.0s截止时success=false、completion_time_sec=null、native_rally_hold_proof=null、termination=timeout，各机器人虽充电一次仍未合格。零注入zero_rally_lab同样RALLY超时，作为稳定性限制保留，不归因于通信损伤。完整原始结果、源/环境/协议/命令/graph/ledger哈希、观察器关闭与严格checker traceback见report/20261004_p3b5_forced_native_hold_failed_candidate.json；全部原格保留，不重跑回填或放宽300s/5s/位速阈值。当前需继续独立开发改进集合能量/时间分配并重新冻结。707此前011786e已暴露，584为同算法基础设施复验；下一次控制算法变化后必须使用预先冻结、真正未暴露的新留出组合，不再把707称为未暴露验证。P3A.6已验收22c95a7历史冻结保持；无ns-3/Wi-Fi/RL实验。

2026-10-04 P3B.5 v55集合分配组件改进：避免ACTIVE观测者返充仍为首位；其后先比较所需充电台数和名义串行行程/返充时间，再比较额外观测者电量余量，最后按minimax/total_path决胜。额外余量不再迫使已满足完整预算的同伴充电或绕行。17相关/427全组件、四包5.24s构建、source审计通过；旧新自由图夹具额外位移8→0m、可避免充电1→0台，低电量观测者保护保留，非仿真因果结果。证据见report/20261004_p3b5_charge_time_assignment_component.json。v43原57失败保留，尚未通过P3B.5；需独立开发回归和新冻结完整矩阵，算法改变后的留出协议使用新未暴露组合，不能重用707声称未暴露验证。

2026-10-04 P3B.5 v55独立开发回归通过，冻结cc21503：force ideal原生COMPLETE297.3s/两机各charge1；zero ideal/fault原生COMPLETE235.6/215.7s/各总charge1；force断网fault RALLY timeout300.3s，但两机各charge1、最低8.307、零碰撞。四原始结果、账本/graph/source/AP快照在report/20261004_p3b5_charge_time_assignment_development.json保留，不回填v43原57失败，开发仍非正式验收。force ideal仅2.7s余量，名义优化不是最坏时限保证。

新正式v56协议在首次运行前改用p3b5_holdout809.world/seed809/fault28091/目标(4.4,-3.4)/3r/E45；这是交错隔断、中央开口、旋转块与柱的新拓扑，静态SDF/visual一致、十box和0.45m净空连通检查通过，尚未运行新场景。707及旧27077首次声明/暴露原样保留为历史，不能称未见测试。主矩阵27case/41unique、同提交十fixed和六安全探针、300s/.35m/.05mps/.1radps/5s、原开发fault17011和已有故障强度保持。新冻结须先检查force ideal真实native保持，再全十fixed，随后含新留出的完整主矩阵；P3B.5尚未完成，无ns3/RL。

2026-10-04 v56冻结前检查：429组件12.92s、四包构建5.29s、source-only3r旁路0违规，27case/41unique清单validate-only通过，未启动Gazebo。runner manifest现在按实际选择case记录seed，不再硬编码707；严格gate新增预声明world/seed/fault及world/control纯bytes SHA验证。native_completion_ok与episode_ok两函数相对cc21503完全相同，300s/.35/.05/.1/5s与安全阈值未放宽。

2026-10-04 P3B.5 v56原候选FAIL，冻结3d079215caacf9e5e31866ca4db236a5cff3236c；14:55:48–15:17:15UTC自然结束，7started/7raw/0接触/0基础设施失败、7账本审计PASS，其余50格未运行。初始force ideal原生COMPLETE273.6s/各charge1、E0双格和双机真实断网返充探针通过；首个固定lab3/101在99.8s进入RALLY、300.4s timeout，2charges、最低20.8966，不能代替完整验收。只读原生诊断见tb2视线无遮挡时朝向转出90度FOV并产生检测间断，原因仍待核验。全部原始失败保留，不回填/重试/放宽300s与原生保持门限。新809/28091从未执行，可在仅开发seed修复后重新冻结控制SHA再首次暴露；初静态文件误把通用采样点标为spawn/charge，原文件保留，另以真实launch三个起点/充电点补查0.45m连通PASS，world未改。证据见report/20261004_p3b5_charge_time_lab101_failed_candidate.json。全部owned owner/观察器/master关闭后才归档，domain222未动；完整strict checker/PASS报告/图未执行，P3B.5仍待完成，无ns-3/RL。

2026-10-04 P3B.5 v57朝向保持候选：v56原lab101已归档7cc413c，不回填。网关交付odom朝向与map→odom旋转相加并归一化；当前观测者/guard停在集合位附近后，偏离请求yaw超过交付相机FOV的四分之一时重新开放原final导航腿。要求新鲜target/地图/位姿，ACTIVE、无pending/live与local-return refuge，原网关/能量/机体/在途路线/真实返航/并发保护保持。待执行未来路线优先级不阻止近位朝向校正，实际预约仍保护。448组件PASS14.00s、四包build5.10s、source-only3r audit0违规；证据见report/20261004_p3b5_observer_heading_component.json。v56交付yaw与native相符，物理朝向漂移原因未凭cmd_vel确认；候选修复中央未监测到位后朝向的问题，不能把预测或组件PASS当真实检测/任务通过。需要独立lab101/force303开发与新完整冻结，809尚未暴露，P3B.5未完成。

20261005 P3B.5 v57独立五格开发FAIL，冻结f8297fa，15:53–16:06:36UTC自然结束后归档；lab3/101 RALLY timeout300.3s/1charge/最低20.27738/0碰撞。force ideal/fault原生COMPLETE295.3/299.5s、各两机charge1；zero ideal/fault原生COMPLETE247.5/167.0s、总charge1/0。五账本时序TTL/versions与graph旁路审计通过，五格0接触/0infra，无任务重试。lab最终位置误差小于3.3cm，但原生近末段最长合格窗口3.0s；289.7/298.7s额外朝向腿发出时目标源龄仍1.2s，候选需要限制持续正常检测时的校正，避免干扰保持。原开发失败不回填v56，不放宽300s/.35/.05/.1/5s；809/28091未执行。完整证据见report/20261005_p3b5_observer_heading_development.json；P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v58候选只在目标确认源间断超过现有5秒观测者新鲜度窗口、但60秒目标lease仍有效时考虑停驻朝向校正；继续正常检测时允许安静保持。四分之一相机FOV、交付map-frame yaw、新鲜位姿/地图/目标、ACTIVE、网关导航/完整能量/实际body/route/return/并发保护保持。451组件PASS14.21s、四包build5.15s、source3r0旁路、27case/41unique validate-only；native_completion_ok/episode_ok原样，原300s/.35/.05/.1/5s未改。证据report/20261005_p3b5_observer_confirmation_gap_component.json；原v57五格FAIL已5f50357归档，不回填。809world/seed/fault原样未暴露，预声明更新控制SHA与实际launch静态补查并保留旧原文件标签/两次冻结历史。新完整v58自身按先force原生/E0/真实断网返充→十fixed→完整27/41+六辅助推进，提供新的lab101/force集成验证，无需另称独立开发PASS；总57原任务全部保留、无retry。P3B.5未通过，待完整门禁，无ns3/RL。

2026-10-05 P3B.5 v58原候选FAIL，冻结cf73eebd875d990bd782cef572d09b484b23900a；2026-10-04 16:19:20–16:33:04UTC自然关闭。6started/6raw、0接触/0基础设施失败、6账本与6图审计PASS、54纯协议PASS。强制充电ideal直到242.2s检测、260.2s进入RALLY，300.4s仍有tb1在最终路线中，各charge1、最低8.11062，无原生COMPLETE，不能判通过；force fault300.2s也RALLY timeout。E0双格为预声明FAILED且无导航；controlled remote双格各充电一次/正能量/0接触，关闭后只读严格physical-return审计PASS，证明断网窗口中的实际Nav2返航，并非任务成功。其余51格含全部固定与809未启动；新809/28091仍未暴露，原707不得视为未暴露。只读日志显示返航取消西侧前沿后，充电恢复按即时收益重分配到东侧，再回西侧而造成较晚检测；这是待开发验证的任务接续问题，不是单次运行的因果收益证明。报告见report/20261005_p3b5_confirmation_gap_forced_failed_candidate.json。所有owned owner/观察器/master自然关闭后归档，domain222未动。完整strict checker/PASS报告/图未执行，P3B.5仍未完成，无ns-3/WiFi/RL。

2026-10-05 P3B.5 v59开发组件：充电/同伴返航取消探索动作后保存搜索意图；恢复只优先最新地图中距原前沿≤1.2m、gain>max(200,原20%)且完整往返预算factor≥1的当前候选，继续经过源TTL/动态身体/已接受路线/可见短腿/gateway。旧意图不是旧指令重放；已观测/阻塞/预算不足回退、成功前缀继续意图、抵达或明确FAILED清除。针对20项1.14s PASS后补明确失败清理检查，完整472项13.60s、四包build5.34s、source3r0旁路。原native_completion_ok/episode_ok与300s/.35/.05/.1/5未改。证据report/20261005_p3b5_interrupted_frontier_component.json；原v58六格FAIL已a6830cc归档，809/28091仍未运行。接续为待集成验证启发式，无因果/最坏时间保证；将先冻结独立lab101/forced303/zero303开发，全部自然关闭后才能修改或归档，再重新冻结正式57格。P3B.5尚未完成，无ns-3/RL。
