# wireless-rl memory — MR3

Updated 2026-10-14. The active contract is [RESEARCH_PLAN.md](RESEARCH_PLAN.md),
then [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Follow root AGENTS.md.
MR3-P0 was explicitly accepted on 2026-10-14; MR3-P1A is in implementation/validation.
Do not start P1B, training or gateway work before P1A user acceptance.
This route replaces the old search/charging/rally/communication-scheduler plan.

## Task and source of truth

Exactly three robots. First learn centralized joint exploration subgoals under
ideal communication, retain local SLAM/Nav2 and conservative fusion, prove a
95% task; then freeze the policy and its interfaces and route actual application
bytes through gateway and ns-3 Wi-Fi (one AP, three STA). Stop at measured
network effects; remedies, hardware, other team sizes and target/charging/rally
are out of scope. Detailed method decisions live in the plan and
[route audit](report/20261014_mr3_route_audit.md), not in historical report instructions.

Current `main` still uses handcrafted ROS frontier allocation. No robot RL,
training environment or ROS/ns-3 gateway exists. P1A launch/check defaults are three; 1–4 compatibility remains.
MR3 evaluation uses an explicit hash-bound 95%/300s schema4 task contract. Plans are
not implemented features. Runtime freeze `c9344e1` has only 90% three-robot
rooms/corridors seed101 engineering credit, not a new 95% or multi-seed result.
Canonical evidence: [repair report](report/20261013_p1c_engineering_repair.md).

The actual ROS workspace is:
`/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap`.
Read its `user_guide.md` and `launch_commands.md` for current commands.
The Git root is `/home/zhuyulab/ns3-workspace`, origin is `Breeze-by/my_ns3-gym`.
Original route backup: `p2c1/global-mission-20261012@8fe1495`, not active work.

Current code is the implementation authority. [report/README.md](report/README.md)
separates current engineering, route audit and historical evidence. Old P1C/P2C
and toy DQN results cannot count as MR3 acceptance. Do not read historical
“next steps” as instructions. User acceptance is required after each MR3 substep,
not after running every old branch of the project.

## Learning, ROS and ns-3 environment boundaries

Wireless-rl Python commands must use conda `ns3gym`:

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
export PYTHONNOUSERSITE=1
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
```

Check before diagnosing imports/CUDA; this does not launch a simulation:

```bash
which python
python -c "import ns3gym; print(ns3gym.__file__)"
python -c "import torch; print(torch.__file__, torch.__version__, torch.cuda.is_available())"
```

Python must resolve under `/home/zhuyulab/miniconda3/envs/ns3gym/bin/`.
Historical environment checks (2026-09-02) saw Python3.10.20, NumPy2.2.6,
PyTorch2.11.0+cu128 and two RTX4090. Verify versions at implementation time;
these are not a fresh hardware probe. User-site CPU torch previously shadowed
CUDA torch; preserve PYTHONNOUSERSITE instead of reinstalling blindly.

ROS nodes run system ROS2 Humble Python, not conda. A future learning adapter
uses explicit IPC; do not merge interpreters via PYTHONPATH. Two GPUs help the
learner but do not establish Gazebo sampling speed. Worker isolation/reset and
throughput are MR3-P1C gates. New Gymnasium/algorithm dependencies must be
version-pinned and checked independently of the legacy Gym/ns3-gym API.

## Legacy toy toolchain (only when specifically needed)

[USER_GUIDE.md](USER_GUIDE.md) now describes only the historical scheduling toy.
Its state is 5 users x `(CQI, queue, backlog age)`, action serves one user,
15 inputs/5 actions. Service/arrival and reward are implemented in `sim.cc`;
backlog age is not packet delay, misses are not packet drops, and this is not a
Wi-Fi PHY/MAC simulation. Retained toy weights cannot initialize a robot policy.

For explicit toy maintenance, keep reward/current-state snapshots distinct,
baseline semantics aligned across `test.py` and `run_baselines.py`, and old
checkpoints incompatible when state/action shape changes. Use a new ns-3
process per formal seed; globals make multi-iteration reset unproven. Keep
training, validation and final test seeds disjoint. Historical held-out seeds
2001–2010 establish only this toy; all exact data remain in dated reports.

If toy `sim.cc` changes, build from the ns-3 root in the conda environment:

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40
./ns3 build wireless-rl
```

`check_project.py` includes a build and simulator run; run it only for relevant
implementation/environment changes, not as an automatic response to document
work. Every simulator check is an experiment requiring the shared log.

## Required engineering and evidence rules

- RL decides exploration; a protocol/safety adapter must not silently call
  handcrafted goal scoring, bad-target reallocation or truth-based masks.
- Preserve stable goal IDs, acceptance/cancel/result ownership and source ages.
  Current raw shared Nav2 map and all-peer odom/TF are explicit gateway bypasses
  to remove under the planned contract, not exceptions for safety.
- Preserve genuine contacts, truth/model boundaries and fixed measurement ROI.
  No held-out tuning, changing time/safety gates after failure or cross-freeze matrices.
- Append all training/evaluation/baseline/ablation/smoke/simulator attempts,
  including failures, to [log.md](log.md), with commands/freeze/seeds/outputs.
- Keep plans/guides concise current contracts. Date reports, retain immutable
  original assets, and record archival/supersession in [ARCHIVE_INDEX.json](report/ARCHIVE_INDEX.json).
- Generated runtime, ROS build/install/log, bags, maps, weights and pycache are
  ignored by default. Only deliberately selected evidence enters Git.
- Verify the change, diff-check, dry-run staging, commit and push to origin in
  the same session. Update ROS launch_commands.md if run modes/commands change.
