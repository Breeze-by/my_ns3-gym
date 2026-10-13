# wireless-rl Codex Memory

2026-10-13 中断恢复继续P2C.1：原 `9bb2c2c` 四开发严格PASS，15非留出部分门禁仍有5FAIL，两物理安全PASS；signed-energy读者修复已推送 `d54ccd3`，旧FAIL保持。新global观测/依赖/任务排序候选验证中，无新任务信用，917未运行。实现与证据见[单一累计报告](report/20261012_p2c1_global_mission.md)，仍须同冻结四开发→17正式+两物理，不能混拼历史版本。

2026-10-12 用户授权接手 P2C.1 全局工作。长会话继续暂停，恢复基线 `b32c891` 的安全预算/本地返航/能量/Future 契约保留；当前独立分支 `p2c1/global-mission-20261012` 使用全局规划工作线程和统一导航所有权，选择性取回有原扫描证据的 SLAM 自体回波修复。新候选须以同一推送冻结完成四开发、17 正式和两物理，组件检查不计任务信用。详细实现与新原件结果集中在 `report/20261012_p2c1_global_mission.md` 和实验 log，不能把历史 v95 PASS 算到本轮。P2C.1B 仍未完成，917 留出未调用，无 ROS/ns-3 Wi-Fi 联合实验。

v95 四开发与首正式 lab101 的单格 PASS 属于已回退版本的历史结果，不是当前源码的完整任务信用。当前判断见 [恢复审查](report/20261012_p2c1_session_recovery.md) 和 [补强评审](report/20261009_p2c_strengthening_review.md)。

2026-10-12 按用户要求清理：已回退长会话的逐候选报告和大型附件移出当前工作树，完整原件保存在 `backup/project-before-report-cleanup-20261012`；失败、超时及原始账本保留。文件位置与 Git 对象见 [归档索引](report/ARCHIVE_INDEX.json)。详细时间线集中在 `log.md` 与日期报告中，不再复制进每份规划、指南和 AGENTS.md。

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

## Current Task Contract

- Historical P1/P2 and P3A–P3C.5 acceptances belong to their dated freezes; P2C.1 is a separate unfinished strengthening gate. Current P2C.1B requires a new same-source four-development, seventeen-formal and two-physical matrix; physical characterization alone does not establish full mission success.
- Full success requires all originally required robots at distinct rally poses with error <=0.35 m, linear speed <=0.05 m/s and angular speed <=0.10 rad/s continuously for 5 simulated seconds, within the original 300-second horizon. Explicit robot isolation produces PARTIAL_COMPLETE, with success=false.
- Central control consumes gateway-delivered maps, pose/TF, battery and detection; never add direct raw robot-state or Nav2 bypasses. Robot-local safety return may use its own sensors and native Nav2.
- Return admission uses a complete qualified known-map route to a charging contact region, source age, waiting/recovery and reaction reserve. Unavailable or stale geometry is not a finite straight-line budget. Charging preserves maps and mission state; c_tx=0 is an abstract-energy assumption, not measured radio joules.
- Preserve existing source TTLs (pose/TF 2 seconds, maps/battery 5 seconds and target-confirmation contract), protocol fields, observer separation and native completion criteria. New data delivery does not renew an old source timestamp.
- Headless and manual launch use the canonical ROS workspace; readiness requires action discovery and bt_navigator ACTIVE for every requested robot. Do not replace readiness with a fixed sleep or silently omit a robot.
- Distinguish pre-start infrastructure failures, post-start task failures and shutdown failures. Keep every original failure and use fresh run IDs; never mix algorithm freezes or backfill unsuccessful cells.
- Planning documents are intent. Current code and dated source-bound evidence establish implementation and experimental claims. Historical P1/P2/P3 milestones and retained failures are indexed in the project README and experiment log.

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
