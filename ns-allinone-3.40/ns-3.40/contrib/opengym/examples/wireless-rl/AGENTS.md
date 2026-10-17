# wireless-rl memory — MR3

2026-10-18: V21_ray冻结099a8eea已自然闭合三机open101普通4step来源诊断，原生219.82827906589955墙秒，39进程exit0、48保存身份消失。三机实际近身回波均命中自身base_collision；原物理因tb1/tb2缺停车刺激保持FAIL，150尚未选用，P2A.0未完成。累计诊断2938.48922518407930/3600墙秒，无PPO或四阶段信用。见[V21](report/20261018_mr3_p2a0_v21_ray.md)。

2026-10-18: V19 freeze72d0465ddd1bbee09af117cfd9d89b7e729f8578 fixed50/150 diagnostic pair closed. Both admission/1ms capture/strict close PASS; baseline original physical PASS, contrast original physical FAIL because all33 snapshots have zero GOAL for every robot and no stopping stimulation. Own maps already retain near-seed100; no occupied clearing or .29 relaxation. 150 not selected, V17 stopping failure unresolved. Native1638.4207719592378sec; V18+V19=2489.3860735194758 of3600 ceiling. 78/78 native exits0; fresh91 PID/start identities gone. No matrix/PPO credit, pilot balance unchanged. See [V19](report/20261018_mr3_p2a0_v19.md).

2026-10-18: V18 freeze85abe391 baseline32/native/original sampled stopping/strict close passed, but root witness rejected actual gzserver-11.10.2 basename. OverallFAIL; formal1ms and iters150 SKIPPED. All39 native exits0,46 saved identities gone,850.965301560238 nativewall charged. V17 physical failure remains unresolved; fix executable entity admission in a fresh freeze, no blind retry or retroactive PASS. See [V18](report/20261018_mr3_p2a0_v18.md). P2A.0 remains incomplete; no PPO/pilot/P2B/gateway.

2026-10-17 continuation (updated2026-10-18 Asia/Shanghai): P2A.0 remains authorized and incomplete. V17 freeze eee6b2f90f697b28a1c20a2af5d1a6d2f044465e passed interface and terminal completely; reset8x32 native/closure and 24 of 26 formal jobs passed, but tb1 real stopping response failed in worker1 open/rooms. Deadline SKIPPED, no retry. All originals preserved; 487 saved PID/start identities absent, 429/429 native processes exited normally. Actual zero commands and applied wheel zeros do not eliminate lateral raw vy about .011m/s; original .01/three-sample/.78s gates remain. Diagnose physics with isolated evidence before a new reviewed clean pushed complete matrix; no cross-freeze PASS. No PPO/P2B/gateway; pilot balance1870 decisions/2905.954739546403 wallsec unchanged. See wireless-rl/report/20261017_mr3_p2a0_v17.md.

Historical first P2A.0 closure (2026-10-17): source freeze f8694025; six native episodes
closed cleanly, terminal audit PASS, reset benchmark/full audit FAIL with one
real peer-envelope task failure. The 300-step deadline was SKIPPED under the
prospective stop rule. P2A.0 exit is unmet; await user review, do not restart
pilot. Shared navigation-map occupied starts are now proved from exact raw maps.

2026-10-17: user authorized P2A continuation and preparation. Current substep
MR3-P2A.0 repairs SLAM ownership teardown, preserves failed collection evidence,
adds versioned received-frontier union and safety diagnostics. No new pilot is
run; its cumulative balance stays 1870 decisions/2905.954739546403 wall seconds.
See [P2A.0 report](report/20261017_mr3_p2a0.md). This substep needs its own user
acceptance before later preparation/training; P2A remains incomplete.

P1C validation started 2026-10-15; actual closure time is in the P1C report. The active contract is [RESEARCH_PLAN.md](RESEARCH_PLAN.md),
then [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Follow root AGENTS.md.
MR3-P0 was explicitly accepted on 2026-10-14; MR3-P1A was accepted on 2026-10-15 and the user authorized P1B.
P1B was accepted by the user on 2026-10-15. The user accepted P1C and authorized P2A's
joint MaskablePPO minimum training/validation loop on 2026-10-16. P2A is in progress;
P2B and later remain unstarted. The separate 2D option and candidate 500k/72h per-run
budget are not accepted; gateway work is not authorized.
The implemented environment contract is [MR3_ENV_CONTRACT.md](MR3_ENV_CONTRACT.md).
This route replaces the old search/charging/rally/communication-scheduler plan.

## Task and source of truth

Exactly three robots. First learn centralized joint exploration subgoals under
ideal communication, retain local SLAM/Nav2 and conservative fusion, prove a
95% task; then freeze the policy and its interfaces and route actual application
bytes through gateway and ns-3 Wi-Fi (one AP, three STA). Stop at measured
network effects; remedies, hardware, other team sizes and target/charging/rally
are out of scope. Detailed method decisions live in the plan and
[route audit](report/20261014_mr3_route_audit.md), not in historical report instructions.

Default baseline retains handcrafted ROS frontier allocation; the mutually
exclusive adapter owns stable goals and consumes logical ideal-delivery copies.
P2A has separate eight-decision engineering checkpoints (seed17/41, four GPU steps each).
The v2 pilot diagnostic interruption retains 390 native decisions, zero updates and
two peer-safety failures. The v4 16-decision native/reward/policy chain passed with
four GPU updates; its pilot diagnostic stop retains another 242 native decisions,
zero updates and one genuine peer-safety failure. V5 corrects the finite-horizon
objective to gamma=lambda=1 while retaining external-truncation bootstrap.
Its pilot retained 48 optimizer steps/797 saved samples before a genuine 40ms
terminal-detection infrastructure failure; three strict successes remain
descriptive sampling outcomes. No final checkpoint exists and final-only
validation was skipped. V6 `af37b2a` adds an evaluator exact-clock/terminal ACK at each20ms boundary;
its two-episode terminal probe and16-decision/four-update minimum pass the
independent gates. Its pilot preserves718 native decisions/zero updates before
a genuine SLAM Karto abort(-6) during controlled shutdown. All167 saved process
identities and its parent are gone; no final.zip exists, so final-only validation
is skipped. The session stops in P2A under the no-retry rule. User-approved
cumulative pilot4096decisions/14400wall seconds has charged2226/11494.045260453597,
leaving1870/2905.954739546403 unused without automatic retry. There is no
frozen-policy reliability or95% P2A acceptance credit; no validated robot policy or ROS/ns-3 gateway exists. P1C implements Gymnasium
tensors/IPC, full process rebuild, explicit stepping and isolated first-correct-cell rewards.
W7 `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a` has the complete eight-stage engineering matrix and independent audits,
762 ROS semantic and 40 conda CPU checks. The unchanged `b328f84` GPU interface probe
retains its original 3-forward/3-backward/0-update scope; P1C itself performed no
policy training. P2A GPU evidence is separately versioned above. Freeze `f9928fe`
passed all three same-freeze open/rooms/corridors seed101 adapter audits; see the
[P1B report](report/20261015_mr3_p1b.md). K8/5 s are this interface version,
not 95% task evidence. The P1B asynchronous nominal 1 s timer had 2/3 s rooms gaps;
P1C supplies separate stepped 1 s/reset/1-2-4-worker evidence. The non-stepped timer nominal cadence and skip rules are unchanged. P1A launch/check defaults are three;
1–4 compatibility remains.
MR3 evaluation uses an explicit hash-bound 95%/300s schema4 task contract. Plans are
not implemented features. P1A includes 18-stream body contact/freshness audit
and 9 effective slots at freeze `5e47802` from 10 attempts, including one
retained native infrastructure failure; see the [P1A report](report/20261014_mr3_p1a.md).
Historical runtime freeze `c9344e1` has only 90% three-robot
rooms/corridors seed101 engineering credit, not a new 95% or multi-seed result.
Its evidence remains in [repair report](report/20261013_p1c_engineering_repair.md).

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

ROS nodes run system ROS2 Humble Python, not conda. The learning environment
uses explicit IPC; do not merge interpreters via PYTHONPATH. Two GPUs help the
learner but do not establish Gazebo sampling speed. Worker isolation/reset and throughput are measured in MR3-P1C; short engineering
runs do not establish multi-day training stability. New Gymnasium/algorithm dependencies must be
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
  Adapter mode uses logical received map/state copies; baseline retains raw
  shared Nav2 map and all-peer odom/TF. P3A must still prove byte transport,
  DDS/process isolation and absence of bypasses; ideal objects do not prove this.
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
