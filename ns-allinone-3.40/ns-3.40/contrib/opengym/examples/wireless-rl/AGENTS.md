# wireless-rl Codex Memory

Last verified against source, local 1/2/3-robot headless smoke tests, P1B
evaluator tests, and the P1C ideal baseline awaiting user review: 2026-09-16.

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
3. `USER_GUIDE.md` for the current mental model, commands, metrics, historical
   best result, and known limitations.
4. `sim.cc` for the actual environment state transition and reward timing.
5. `test.py` and `run_baselines.py` for baseline semantics and CSV fields.
6. `dqn_common.py`, `train_dqn.py`, and `evaluate_dqn.py` for DQN behavior.
7. `report/20260914_p1b.md`, `report/20260915_p1c.md`,
   `report/20260916_p1c.md`, and `report/20260916_p1c_foundation.md` for the
   ROS engineering checkpoints.
8. `report/20260902.md`, `report/20260429.md`, and `log.md` for historical
   experiment context.

The accepted P1A ROS foundation now has explicit Gazebo seeds, configurable spawn
timeouts, bounded automatic headless smoke checks, and verified 1/2/3-robot
startup. This proves startup and message flow only; task completion,
cross-seed reproducibility, and formal completion metrics remain for P1C.

The accepted P1B now provides an evaluator-only Gazebo truth channel, a truth occupancy
grid rasterized from static SDF box collisions, per-robot truth path and visit
masks, search overlap, Nav2 outcomes, base-contact collision events, and one-row
episode CSV/JSON. Its 2026-09-14 one- and two-robot short timeout runs passed.
The current world has one unsupported mesh collision (an SUV outside the lab
walls).

P1C now meets the original 90% coverage intent with a shorter evidence-based
time bound and is waiting for user review. Two robots start inside the same
radius-1 m start/charging region in `my_world.world`; success is 90%
correct-free coverage within 180 simulated seconds. Earlier 75%/300 s results
were symptoms of foundational defects, not an exploration ceiling: the custom
SLAM callback never enabled `map->odom`, AMCL competed with SLAM during mapping,
the coordinator treated odometry as map coordinates, and frontier selection
blocked on a quadratic nearest-frontier loop. After fixing those causes and
using diverse, reachable 0.45 m-clearance observation points, seeds 101/202/303
reached 90% in 141.3/161.4/134.9 seconds and finished at
93.87%/93.90%/93.88%, with zero collisions and zero search overlap. Do not
proceed to P2 until the user accepts P1C; 95% remains a higher milestone.

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
