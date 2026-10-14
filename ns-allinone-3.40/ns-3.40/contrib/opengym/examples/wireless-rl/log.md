# Shared Experiment and Development Log

> 本文件按日期保留toy/ROS/旧路线/MR3的历史，不是当前研究指令。活动契约是
> [MR3研究计划](RESEARCH_PLAN.md)与[实施检查点](IMPLEMENTATION_PLAN.md)。
> 历史P编号、门限、PASS和“下一步”不转记新验收；失败/原件保持原义。

## Logging rule

Append an entry for every training run, evaluation, baseline sweep, ablation,
or formal smoke/regression run. Record it in the same work session, including
failed or interrupted experiments. Each entry must contain:

- date and purpose;
- code commit or a note that the worktree is dirty;
- exact command;
- model/checkpoint;
- training, validation, and evaluation seeds where applicable;
- important parameters;
- output paths;
- result and conclusion.

Never rewrite an older experiment to match newer code; append a correction or a
new dated entry instead.

## 2026-09-02 Project recovery check

No new training experiment was run. The current source, local environment,
retained checkpoint metadata, and historical aggregate CSVs were audited after
the project had been idle for several months.

Verified:

- the conda environment `ns3gym` still exists;
- a two-step `greedy` smoke test completes with the current 15-dimensional
  observation and 5-action environment;
- the conda environment contains CUDA PyTorch 2.11.0+cu128 and can use both RTX
  4090 GPUs; a user-site CPU PyTorch had shadowed it, so the environment was
  configured with `PYTHONNOUSERSITE=1`;
- `models/dqn_exp06_evalselect_p5k_h256_best.pt` and its evaluation CSV remain
  present;
- the checkpoint metadata matches the recorded 2026-04-29 configuration and
  identifies zero-based episode 249 as the best validation checkpoint;
- the historical evaluation seeds 1–10 overlap the training seeds 1–300, so
  that table is not a held-out generalization result;
- the source-level environment and metric semantics are now documented in
  `USER_GUIDE.md`; the dated 2026-04-29 report remains an unchanged historical
  snapshot.

The main conclusion is unchanged: the current result is promising for the toy
MDP, while packet-level traffic and realistic wireless behavior remain the
largest missing research step.

### GPU environment repair and regression validation

Commands:

```bash
conda env config vars set PYTHONNOUSERSITE=1 -n ns3gym
conda deactivate
conda activate ns3gym
python check_project.py

python train_dqn.py \
  --episodes 1 \
  --simTime 2 \
  --stepTime 0.5 \
  --batchSize 2 \
  --learningStarts 2 \
  --bufferSize 16 \
  --device auto \
  --runName gpu_smoke \
  --outputDir /tmp/wireless-rl-gpu-smoke/runtime \
  --modelDir /tmp/wireless-rl-gpu-smoke/models
```

Results:

- `check_project.py` passed the CUDA forward/backward, ns-3 build, two-step
  smoke, and fixed-seed reproducibility checks;
- `train_dqn.py` reported `Device: cuda:0`, completed four environment
  steps and gradient updates, and saved its temporary checkpoint and CSV under
  `/tmp/wireless-rl-gpu-smoke/`;
- this was an infrastructure smoke run, not a research training result.

### Held-out retest

Worktree note: documentation and `check_project.py` changes were uncommitted;
environment, reward, baseline, DQN, and checkpoint code were unchanged.

The retained best checkpoint and all seven baselines were rerun on fresh seeds
2001–2010 with identical `simTime=20` and `stepTime=0.5`.

Commands:

```bash
python run_multi_seed.py \
  --seeds 2001,2002,2003,2004,2005,2006,2007,2008,2009,2010 \
  --simTime 20 \
  --stepTime 0.5 \
  --outputDir runtime/heldout_2001_2010 \
  --quiet \
  --no-plot

python evaluate_dqn.py \
  --model models/dqn_exp06_evalselect_p5k_h256_best.pt \
  --agentName dqn_exp06_evalselect_p5k_h256_best_heldout \
  --seeds 2001,2002,2003,2004,2005,2006,2007,2008,2009,2010 \
  --simTime 20 \
  --stepTime 0.5 \
  --device auto \
  --outputDir runtime/heldout_2001_2010

python compare_dqn_with_baselines.py \
  --baselineCsv runtime/heldout_2001_2010/comparisons/baseline_comparison_all_seeds.csv \
  --dqnCsv runtime/heldout_2001_2010/comparisons/dqn_exp06_evalselect_p5k_h256_best_heldout_eval_all_seeds.csv \
  --outputDir runtime/heldout_2001_2010 \
  --tag dqn_exp06_evalselect_p5k_h256_best_heldout
```

Output paths:

```text
runtime/heldout_2001_2010/comparisons/baseline_comparison_all_seeds.csv
runtime/heldout_2001_2010/comparisons/dqn_exp06_evalselect_p5k_h256_best_heldout_eval_all_seeds.csv
runtime/heldout_2001_2010/comparisons/dqn_vs_baselines_dqn_exp06_evalselect_p5k_h256_best_heldout.csv
report/20260902.md
```

- DQN mean cumulative reward: -128.586
- greedy mean cumulative reward: -284.997
- paired DQN-minus-greedy reward difference: +156.411
- DQN reward wins: 10/10 seeds
- DQN total-delay wins: 10/10 seeds
- DQN deadline-miss wins: 10/10 seeds

DQN retains its low-delay reward advantage, while giving up about 3% throughput,
higher reward queue, and some fairness. Full results are in
`report/20260902.md`.

## 2026-04-28

### Step 1: Baseline refresh

Command:

```bash
conda run -n ns3gym python3 run_multi_seed.py --seeds 1,2,3,4,5 --simTime 20 --stepTime 0.5 --quiet
```

Five-seed aggregate baseline summary from `runtime/comparisons/baseline_comparison_all_seeds.csv`:

| Agent | Mean cumulative reward | Mean average throughput | Mean average reward queue | Fairness |
| --- | ---: | ---: | ---: | ---: |
| `greedy` | -314.698 | 9.575 | 69.545 | 0.952 |
| `round_robin` | -446.262 | 8.540 | 88.905 | 0.962 |
| `random` | -480.968 | 7.700 | 101.970 | 0.913 |
| `max_cqi` | -504.940 | 6.760 | 141.800 | 0.750 |
| `max_queue` | -728.888 | 7.615 | 100.670 | 0.976 |

Current target for DQN:

- clearly beat `random`
- beat or approach `round_robin`
- ideally move toward `greedy`, which is the strongest current baseline

### Step 2: First 15-dim DQN run

Command:

```bash
conda run -n ns3gym python3 train_dqn.py --episodes 300 --seed 1 --simTime 20 --stepTime 0.5 --device cuda:0 --quiet
conda run -n ns3gym python3 evaluate_dqn.py --model models/dqn_seed1.pt --agentName dqn_seed1 --seeds 1,2,3,4,5 --simTime 20 --stepTime 0.5 --device cuda:0
```

Observed aggregate result from `runtime/comparisons/dqn_seed1_eval_all_seeds.csv`:

| Agent | Mean cumulative reward | Mean average throughput | Mean average reward queue | Mean average total delay | Mean average deadline misses | Fairness |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `dqn_seed1` | -209.778 | 7.950 | 89.995 | 36.695 | 1.725 | 0.770 |

Comparison against baselines:

- much better than `greedy` on mean cumulative reward: `-209.778` vs `-314.698`
- much lower mean delay than `greedy`: `36.695` vs `47.470`
- much lower mean deadline misses than `greedy`: `1.725` vs `2.400`
- worse fairness than `greedy`, so the model is likely learning a more aggressive priority policy

Conclusion:

- The current 15-dim DQN is already producing a clear gain on the environment objective.
- Next iteration should focus on improving stability and trying to keep the reward advantage while reducing variance and maybe recovering some fairness.

### Step 3: Delay-aware warm start

Command:

```bash
conda run -n ns3gym python3 train_dqn.py \
  --episodes 300 \
  --seed 1 \
  --simTime 20 \
  --stepTime 0.5 \
  --device cuda:0 \
  --quiet \
  --hiddenSize 128 \
  --epsilonDecay 0.99 \
  --pretrainSteps 3000 \
  --pretrainHeuristic delay_aware \
  --runName dqn_delayaware_p3k_h128

conda run -n ns3gym python3 evaluate_dqn.py \
  --model models/dqn_delayaware_p3k_h128.pt \
  --agentName dqn_delayaware_p3k_h128 \
  --seeds 1,2,3,4,5 \
  --simTime 20 \
  --stepTime 0.5 \
  --device cuda:0
```

Observed aggregate result from `runtime/comparisons/dqn_delayaware_p3k_h128_eval_all_seeds.csv`:

| Agent | Mean cumulative reward | Mean average throughput | Mean average reward queue | Mean average total delay | Mean average deadline misses | Fairness |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `dqn_delayaware_p3k_h128` | -167.700 | 8.230 | 88.400 | 34.635 | 1.615 | 0.813 |

Comparison against the previous DQN:

- better mean cumulative reward: `-167.700` vs `-209.778`
- better mean delay: `34.635` vs `36.695`
- better mean deadline misses: `1.615` vs `1.725`
- slightly better fairness: `0.813` vs `0.770`

Comparison against the best baseline (`greedy`):

- much better mean cumulative reward: `-167.700` vs `-314.698`
- lower mean total delay: `34.635` vs `47.470`
- lower mean deadline misses: `1.615` vs `2.400`
- fairness is lower than `greedy`, but still improved over the first DQN run

Interpretation:

- The tuned DQN is clearly optimizing the full reward better than the hand-made baselines.
- It is trading some queue control for a larger reduction in delay and deadline misses, which fits the current reward design.

### Compatibility note

Older checkpoints such as `dqn_v1_*` to `dqn_v4_*` were trained on the older
10-dimensional state space and cannot be loaded into the current 15-dimensional
`CQI + Queue + Delay` environment.

### Current best checkpoint

Best model in the current workspace:

```text
models/dqn_delayaware_p3k_h128.pt
```

Best evaluation summary:

```text
runtime/comparisons/dqn_delayaware_p3k_h128_eval_all_seeds.csv
```

## 2026-09-02 Monorepo Migration Validation

Code state before validation:

```text
58ffbcc  validated wireless-rl baseline, regression check, and research plan
c531eae  ROS 2 project imported under ros2_ws/ with git subtree --squash
branch: integration/ros2-monorepo
```

The former standalone ROS repository was clean at commit `9f3702b` before the
import. Its source is now tracked inside the same Git repository as ns-3 at:

```text
/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
```

### ns-3/GPU regression

Exact command:

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
python check_project.py
```

Result: passed. PyTorch `2.11.0+cu128` loaded from the `ns3gym` environment,
the NVIDIA GeForce RTX 4090 DQN forward/backward check passed, `wireless-rl`
built successfully, and the two seed-4242 smoke runs produced byte-identical
CSV and summary files. Temporary outputs were written under `/tmp` and removed
by the check.

### Clean ROS 2 build from the monorepo path

Exact command:

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
colcon list
colcon build --symlink-install --packages-select \
  nav2_bringup slam_toolbox multi_robot merge_map multi_robot_exploration
```

Result: all five selected packages finished successfully in 2 minutes 45
seconds. Colcon warned that the local modified `nav2_bringup` overrides the
Humble underlay package; this is expected for the imported project. The new
`build/`, `install/`, and `log/` directories are ignored and were not staged.

### ROS 2 one-robot headless smoke, attempt 1

Exact command:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
timeout --signal=INT --kill-after=15s 70s ros2 launch multi_robot \
  gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=1 enable_gzclient:=false enable_rviz:=false \
  enable_merge_rviz:=false
```

Additional live checks:

```bash
ros2 topic list
ros2 lifecycle get /tb1/controller_server
ros2 lifecycle get /tb1/planner_server
timeout 8s ros2 topic hz /tb1/scan --window 3
```

Result: partial failure. The entity appeared and `/tb1/scan`, `/tb1/map`,
`/tb1/odom`, `/tb1/cmd_vel`, `/tb1/imu`, and `/merge_map` were present.
Controller and planner were `active`; scan rate was about 5 Hz. However,
`spawn_entity.py` timed out just as the initially cold Gazebo process finished
creating `tb1`, returned exit code 1, and the first navigation goal was rejected.
There was no explicit simulator seed, so this is a startup smoke rather than a
formal reproducibility experiment.

### ROS 2 one-robot headless smoke, warm retry

Exact command:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
timeout --signal=INT --kill-after=15s 50s ros2 launch multi_robot \
  gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=1 enable_gzclient:=false enable_rviz:=false \
  enable_merge_rviz:=false
```

Result: functional startup passed. `tb1` spawned cleanly, SLAM registered the
lidar, headquarters assigned frontiers, and the robot reached its first goal
before receiving a second. The intentional timeout then exposed existing
shutdown problems: `map_saver_cli` ran after `/merge_map` was stopping,
`rclpy.shutdown()` was called twice, and Gazebo required termination escalation.
These teardown errors and the cold-start spawn timeout are recorded follow-up
issues; neither indicates a path or colcon-cache failure caused by the monorepo
migration.

### Migration conclusion

- ns-3 kept its canonical path and passed its full automated regression.
- ROS 2 rebuilt from a clean cache at its new canonical path and ran the core
  Gazebo/SLAM/Nav2/exploration chain.
- The old standalone checkout was renamed, not deleted, to
  `/home/zhuyulab/ros2_ws/ros2-multi-robot-automap.standalone-backup-20260902`.
- `/home/zhuyulab/ros2_ws/ros2-multi-robot-automap` is now a compatibility
  symlink to the monorepo, preventing old local commands from using a second
  source tree.
- Follow-up work should fix clean shutdown and cold-start spawn timing before
  treating the ROS launch as an automated pass/fail regression.

### Standalone checkout cleanup

After the monorepo migration and validation, the user requested removal of the
old local ROS checkout. On 2026-09-02:

- The compatibility symlink
  `/home/zhuyulab/ros2_ws/ros2-multi-robot-automap` was removed with `unlink`.
- The pre-migration standalone checkout
  `/home/zhuyulab/ros2_ws/ros2-multi-robot-automap.standalone-backup-20260902`
  was moved to the system trash with `gio trash`. It remains recoverable until
  the trash is emptied.
- The canonical, Git-tracked ROS source remains
  `/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap`.
- Removal of the former `Breeze-by/ros_mutirobot_nav` GitHub repository is
  user-managed and was not performed by the agent.

## 2026-04-29 DQN Optimization Summary

Baseline command:

```bash
python run_multi_seed.py --seeds 1,2,3,4,5,6,7,8,9,10 --quiet
```

Best DQN command:

```bash
python train_dqn.py \
  --episodes 300 \
  --seed 1 \
  --simTime 20 \
  --stepTime 0.5 \
  --device cuda:0 \
  --quiet \
  --hiddenSize 256 \
  --learningRate 5e-4 \
  --epsilonStart 0.2 \
  --epsilonEnd 0.01 \
  --epsilonDecay 0.995 \
  --pretrainSteps 5000 \
  --pretrainHeuristic delay_aware \
  --evalInterval 25 \
  --evalSeeds 1001,1002,1003 \
  --runName dqn_exp06_evalselect_p5k_h256
```

Best checkpoint:

```text
models/dqn_exp06_evalselect_p5k_h256_best.pt
```

10-seed evaluation summary:

| Agent | Mean cumulative reward | Mean throughput | Mean reward queue | Mean total delay | Mean deadline misses | Fairness |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `greedy` | -278.111 | 9.6525 | 70.4775 | 45.5050 | 2.2700 | 0.9531 |
| `delay_aware` | -361.319 | 9.2350 | 80.7225 | 48.7325 | 2.5175 | 0.9567 |
| `max_delay` | -550.375 | 6.7925 | 127.6375 | 53.5050 | 2.7850 | 0.7978 |
| `dqn_exp06_evalselect_p5k_h256_best` | -105.792 | 9.3250 | 73.8050 | 34.4425 | 1.5575 | 0.8974 |

Notes:

- The useful code change was DQN-only validation checkpoint selection in `train_dqn.py`.
- A 500-episode validation-selected run did not improve over the 300-episode run.
- The best model improves reward, delay, and deadline misses over `greedy`, while giving up some fairness and a small amount of throughput.

## 2026-09-14 ROS 2 P1A headless smoke

Purpose: turn the existing ROS 2 Gazebo/SLAM/Nav2/map-merge/exploration startup
into a seeded, bounded, automatic smoke gate before implementing task metrics.

Code state: base commit `d45d88b` plus the uncommitted P0/P1A source and
documentation changes that are committed together with this entry. No model or
checkpoint applies. Gazebo seed was 1 for every run.

Build command:

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
colcon build --symlink-install --packages-select multi_robot merge_map multi_robot_exploration
```

Result: all three selected packages built successfully.

The first one-robot run used:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
python3 scripts/ros_smoke_test.py --robot-count 1 --gazebo-seed 1 \
  --startup-timeout 180 --shutdown-timeout 45
```

Result: failed. The topics appeared, but one five-second lifecycle query timed
out and the initial checker treated that single query as a terminal failure.
The launched process group was cleaned up. Output:
`log/smoke/robots1_seed1_20260914-172800.log`.

The checker was changed to keep polling after an individual lifecycle timeout.
The one-robot run then passed; output:
`log/smoke/robots1_seed1_20260914-172903.log`. Headquarters was subsequently
changed from a nested `ros2 run` process to a native launch `Node`, and the same
command passed again with clean headquarters exit. Final output:
`log/smoke/robots1_seed1_20260914-173031.log`.

Two-robot command:

```bash
python3 scripts/ros_smoke_test.py --robot-count 2 --gazebo-seed 1 \
  --startup-timeout 240 --shutdown-timeout 60
```

Result: passed. Output:
`log/smoke/robots2_seed1_20260914-173107.log`.

Three-robot command:

```bash
python3 scripts/ros_smoke_test.py --robot-count 3 --gazebo-seed 1 \
  --startup-timeout 300 --shutdown-timeout 75
```

Result: passed. Output:
`log/smoke/robots3_seed1_20260914-173259.log`.

Every final pass found `/merge_map` plus each robot's `/cmd_vel`, `/map`,
`/odom`, and `/scan`; observed active Nav2 controller/planner lifecycle nodes;
received lidar and merged-map messages; survived the dwell interval; and exited
within the configured shutdown timeout without leaked Gazebo/ROS processes.

Conclusion: P1A startup and bounded shutdown are ready for user review. This is
not a task-completion, cross-seed reproducibility, or network-coupling result.
Those claims require the P1B evaluator, P1C ideal-communication experiments,
and later explicit communication checkpoints.

## 2026-09-14 ROS 2 P1B evaluator

Purpose: add an evaluator-only Gazebo truth path and write bounded episode
metrics without changing frontier or Nav2 control.

Code state: base commit `bbfade1` plus the P1B worktree changes committed with
this entry. No RL model applies. Generated files are under ignored ROS `log/`
directories.

Targeted test command:

```bash
source /opt/ros/humble/setup.bash
PYTHONPATH=src/multi_robot_exploration:$PYTHONPATH \
  python3 -m pytest -q \
  src/multi_robot_exploration/test/test_task_evaluator.py
```

Result: 3 passed in 0.45 seconds. The tests cover SDF state-pose/height-slice
rasterization, occupancy metrics with unknown cells, and the research-plan
overlap formula.

Build command:

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select multi_robot multi_robot_exploration
```

Result: both packages built successfully.

First evaluator smoke command:

```bash
python3 scripts/ros_smoke_test.py --robot-count 1 --gazebo-seed 11 \
  --startup-timeout 180 --shutdown-timeout 45 \
  --evaluation-duration 10 --evaluation-wait-timeout 180
```

Result: failed. `task_evaluator` attempted to assign rclpy's read-only
`subscriptions` property and exited with `AttributeError`; the outer check
reported the missing result and cleaned the launch. Output:
`log/smoke/robots1_seed11_20260914-195452.log`.

After renaming the member to `input_subscriptions` and adding early evaluator
exit detection, the following one-robot command passed:

```bash
python3 scripts/ros_smoke_test.py --robot-count 1 --gazebo-seed 12 \
  --startup-timeout 180 --shutdown-timeout 45 \
  --evaluation-duration 10 --evaluation-wait-timeout 180
```

Result: 10.0 simulated seconds, 3 merged maps, 122 model states, 236 contact
messages, 0.668 m truth path, no teleport jump, one successful Nav2 goal, no
collision, and 0.1092 correct-free coverage. Outputs:
`log/smoke/robots1_seed12_20260914-195943.log` and
`log/evaluation/smoke_robots1_seed12_20260914-195943.{json,csv}`.

Two-robot command:

```bash
python3 scripts/ros_smoke_test.py --robot-count 2 --gazebo-seed 13 \
  --startup-timeout 240 --shutdown-timeout 60 \
  --evaluation-duration 10 --evaluation-wait-timeout 240
```

Result: 10.3 simulated seconds, 5 merged maps, 172 model states, 340/275
contact messages, 1.089 m total truth path, no teleport jump, no collision,
0.1644 correct-free coverage, and zero search overlap in this short window.
Both issued Nav2 goals were still active at timeout. Outputs:
`log/smoke/robots2_seed13_20260914-200108.log` and
`log/evaluation/smoke_robots2_seed13_20260914-200108.{json,csv}`.

After adding truth/map metadata and start/end simulation timestamps to the
schema, a final one-robot regression used:

```bash
python3 scripts/ros_smoke_test.py --robot-count 1 --gazebo-seed 14 \
  --startup-timeout 180 --shutdown-timeout 45 \
  --evaluation-duration 5 --evaluation-wait-timeout 180
```

Result: passed; output:
`log/evaluation/smoke_robots1_seed14_20260914-200531.{json,csv}`.

Conclusion: P1B is ready for user review. The SDF truth grid includes 25 static
box collisions at lidar height. One SUV mesh collision outside the laboratory
walls is not rasterized and is explicitly reported as unsupported. Task
completion remains undefined, so timeout smoke results correctly keep
`success=false`; P1C must define the ideal-communication completion contract.

## 2026-09-14–15 ROS 2 P1C ideal-communication engineering round

Purpose: implement the user-approved P1C contract (`my_world.world`, two
robots in the common start/charging region, 90% correct-free coverage success,
600 simulated-second timeout), run multiple seeds, and repair the existing
frontier baseline until either the exit condition passed or a concrete design
decision required user review.

Code state: base commit `38f14bb` plus the P1C worktree changes documented in
`report/20260915_p1c.md`. No RL checkpoint applies. All generated ROS outputs
below are ignored by Git. Gazebo seed does not make ROS scheduling, SLAM, or
Nav2 completely deterministic.

The repeated directed command form was:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
PYTHONNOUSERSITE=1 python3 scripts/ros_smoke_test.py \
  --robot-count 2 --gazebo-seed SEED --goal-timeout 60 \
  --startup-timeout STARTUP --shutdown-timeout 60 \
  --evaluation-duration DURATION --coverage-threshold 0.9 \
  --evaluation-wait-timeout WAIT --episode-id EPISODE
```

Unless a row says otherwise, `SEED=101`, `STARTUP=240`, and the launch log is
under `ros2_ws/ros2-multi-robot-automap/log/smoke/`. `shutdown` results mean
the evaluator preserved a partial result during an intentionally interrupted
or infrastructure-failed launch; they are not valid strategy samples.

| Episode/run id | Duration / wait | Result and conclusion |
|---|---:|---|
| `p1c_short_seed21` | 30 / 240, seed 21 | PASS infrastructure; timeout, coverage 0.5490, path 10.634 m, zero collision. Fixed starts were correct. |
| `p1c_release_target_seed101` | 180 / 480 | FAIL startup: tb2 planner did not become active. Partial shutdown output was not used. |
| `p1c_spawn_order_seed101` | 180 / 480 | FAIL startup: first attempt to couple each spawn with its own Nav2 left tb1 planner inactive; reverted. |
| `p1c_navigation_only_seed101` | 180 / 480 | FAIL startup: direct navigation include lacked effective namespaced parameters (`No critics defined`); reverted. |
| `p1c_namespaced_nav_seed101` | 120 / 420 | FAIL startup/lifecycle after namespacing direct navigation. Partial coverage 0.0409, no valid goals. |
| `p1c_delayed_control_seed101` / `p1c_staggered_nav_seed101` | 180 / 480 | FAIL startup/lifecycle in direct-navigation variants; partial coverage about 0.0405/0.0402, no goals. |
| `p1c_proven_bringup_seed101` | 180 / 480 | Proven bringup restored, but evaluator started at clock 0 then timed out after the clock jump; invalid elapsed 2061.282 s, coverage 0.0404. Added clock gate. |
| `p1c_clock_gate_seed101` | 180 / 480 | PASS infrastructure; elapsed 180.3 s, coverage 0.7651, path 44.404 m, 2/6 goals succeeded, 3 canceled. |
| `p1c_goal_timeout_seed101` | 180 / 480 | PASS; coverage 0.7836, path 43.578 m, 5/9 goals succeeded, 2 canceled; cancellation occurred at 60 simulated seconds as designed. |
| `p1c_local_map_seed101` | 180 / 480 | PASS; coverage 0.8393, path 54.696 m, 2/7 succeeded, 3 canceled; no `off the global costmap` message after per-robot map selection. |
| `p1c_frontier_fallback_seed101` | 180 / 480 | PASS; coverage 0.7382, path 39.935 m, 5/10 succeeded. Group fallback increased goal supply but short-run coverage was stochastic. |
| `p1c_frontier_fallback_seed101_600` | 600 / 1200 | Interrupted after lifecycle/action-server diagnosis; partial shutdown at 166.1 s, coverage 0.6456. Not a strategy result. |
| `p1c_frontier_fallback_seed101_600_retry1` | 600 / 1200 | FAIL startup/inactive Nav2; partial shutdown at 170.0 s, coverage 0.6677. Not a strategy result. |
| `p1c_ready_gate_seed101` | 180 / 600, startup 300 | PASS after adding bt_navigator gate; coverage 0.7258, path 36.376 m, 15/17 succeeded, 1 canceled. High goal success exposed repeated successful-target oscillation. |
| `p1c_visited_history_seed101` | 180 / 600, startup 300 | FAIL startup because tb2 bt_navigator never became active; partial evaluator result was not used. |
| `p1c_no_amcl_seed101` | 180 / 480 | FAIL: experimental navigation-only bringup left both planners inactive and all goals rejected. The AMCL-suppression change was reverted. |
| `p1c_delayed_ready_visited_seed101` | 180 / 600, startup 300 | PASS; coverage 0.7377, path 45.557 m, 13/16 succeeded, 1 canceled. Successful target history removed A↔B revisits and targets continued outward. |
| `p1c_visited_history_seed101_600` | 600 / 1200, startup 300 | PASS infrastructure but task timeout: coverage 0.7873, path 100.571 m, 25/31 goals succeeded, 5 canceled, 0 collisions. This is the latest valid candidate result. |

The serial batch command form was:

```bash
PYTHONNOUSERSITE=1 python3 scripts/run_ideal_baseline.py \
  --seeds 101 102 103 --robot-count 2 \
  --duration 600 --coverage-threshold 0.9 \
  --goal-timeout 60 --run-id RUN_ID
```

Early batches before the goal-timeout option used the same command without
`--goal-timeout 60`. Every batch summary contains the complete child command
for every seed under its `command` field.

| Run id | Result |
|---|---|
| `p1c_ideal_20260914` | 0/3 valid episodes: all three child launches produced evaluator files but the first smoke implementation used transient node discovery and returned infrastructure failures. Failure preserved; checker changed to inspect evaluator death in the launch log. |
| `p1c_ideal_20260914_retry1` | seed 101/103 timed out at 0.8654/0.8863; seed 102 infrastructure failed. Robot end poses showed escape through the south outer doorway. |
| `p1c_ideal_20260914_retry2` | After closing the door, 3/3 infrastructure PASS and 0/3 success. Coverage 0.7864/0.8682/0.7801; paths 137.696/95.995/51.970 m; no escape. |
| `p1c_ideal_20260914_retry3` | After 60 s goal cancellation, 3/3 infrastructure PASS and 0/3 success. Coverage 0.8311/0.7759/0.7406; paths 57.330/69.058/63.218 m. Failed goals still leaked reservations. |
| `p1c_ideal_20260914_retry4` | After reservation release and clock/startup fixes, 3/3 infrastructure PASS and 0/3 success. Coverage 0.7856/0.7575/0.7647; paths 63.674/60.919/32.745 m; success goals 2/11, 3/8, 2/6. This is the complete formal three-seed comparison. |
| `p1c_ideal_20260915_local_map` | Intentionally interrupted during seed 102 after seed 101 proved local-only frontier exhaustion. Seed 101 infrastructure PASS but timed out at coverage 0.7418, path 37.610 m, 3/6 goals succeeded. Summary was preserved incrementally. |

Other checks and failures:

```bash
source /opt/ros/humble/setup.bash
PYTHONNOUSERSITE=1 colcon build --symlink-install \
  --packages-select multi_robot multi_robot_exploration
source install/setup.bash
PYTHONNOUSERSITE=1 python3 -m pytest \
  src/multi_robot_exploration/test/test_control.py \
  src/multi_robot_exploration/test/test_task_evaluator.py -q
```

Final relevant result: build passed and 4 tests passed. The first pytest call
failed collection with `ModuleNotFoundError` because `install/setup.bash` had
not been sourced; the exact corrected command above then passed.

`ros2 action list --no-daemon` was tried as a stricter gate and failed because
Humble does not support that option. Plain `ros2 action list` returned stale
daemon graph data after process cleanup, so the experimental action-list gate
was removed. The lifecycle gate remains the source of truth.

`jq` was attempted for read-only JSON aggregation and failed because it is not
installed. Python's standard `json` module was then used read-only; no runtime
file was changed.

Truth/parser and final code checks during the round:

- the closed world rasterizes 26 box collisions and reports one unsupported
  mesh outside the task area;
- selected Python syntax checks passed;
- task evaluator tests passed (3/3), and after the frontier regression test was
  added the combined focused suite passed (4/4);
- repeated `multi_robot`/`multi_robot_exploration` symlink builds passed;
- valid final runs reported zero collisions and no teleport jumps.

Conclusion: the P1C infrastructure and measurement contract are reproducible,
but the 90%/600 s exit condition is not met. The current blocker is safe global
task handoff after one robot's local frontier supply is exhausted. Recommended
next round: local frontier first; on exhaustion, propose a merged-map frontier
and require that robot's Nav2 `ComputePathToPose` to return a path before sending
`NavigateToPose`. Do not lower 90% or lengthen 600 s without user approval.

## 2026-09-16 ROS 2 P1C optimization and threshold revision

Purpose: continue P1C without changing the world, truth metric, robot count,
frontier definition, or task logic; test algorithmic ways to exceed the prior
baseline, replace the overly long 600 s episode with an evidence-based bound,
and record failed approaches as well as the final result.

Code state: base commit `23fb48e` plus the worktree changes committed with this
entry. The pre-existing deletion of `report/20260914.md` and untracked
`report/20260914_p1a.md` were not touched or included. No RL checkpoint applies.

Focused validation used:

```bash
source /opt/ros/humble/setup.bash
PYTHONNOUSERSITE=1 colcon build --symlink-install \
  --packages-select multi_robot merge_map multi_robot_exploration
source install/setup.bash
PYTHONNOUSERSITE=1 python3 -m pytest \
  src/multi_robot_exploration/test/test_control.py \
  src/multi_robot_exploration/test/test_task_evaluator.py -q
```

Builds passed throughout. The final focused suite passed 5 tests; the added
regression proves `fGroups` does not discard valid groups after the eighth.

### Directed attempts

The common directed command form was:

```bash
PYTHONNOUSERSITE=1 python3 scripts/ros_smoke_test.py \
  --robot-count 2 --gazebo-seed 101 --goal-timeout GOAL_TIMEOUT \
  --startup-timeout 300 --shutdown-timeout 60 \
  --evaluation-duration DURATION --coverage-threshold 0.9 \
  --evaluation-wait-timeout WAIT --episode-id EPISODE
```

| Episode | Changed method | Result |
|---|---|---|
| `p1c_shared_map_seed101_180` | merged map for control/Nav2, goal timeout 45, 180 s | Infrastructure FAIL before evaluation: `/merge_map` wait timed out at 30 s. |
| `p1c_shared_map_seed101_180_retry1` | same, message timeout 60 | Infrastructure FAIL: frame id was also used as output topic, so the map was published as `/map`; no strategy result. |
| `p1c_shared_map_seed101_180_retry2` | decoupled frame/topic experimentally, message timeout 45 | PASS infrastructure, timeout at 72.70%, 46.67 m, 2/9 goals succeeded, 6 canceled. Dynamic merged-map navigation was worse and was reverted. |
| `p1c_reachable_frontier_seed101_180` | local known-free Dijkstra connectivity, goal timeout 45 | PASS, timeout at 71.42%, 15.41 m, 1/2 goals succeeded. Odom/map mismatch starved targets; reverted. |
| `p1c_path_precheck_seed101_180` | Nav2 `ComputePathToPose` before navigation, goal timeout 45 | PASS, timeout at 73.61%, 37.51 m, 13/17 goals succeeded. Precheck rejected no candidate and did not improve coverage; reverted. |
| `p1c_all_frontiers_seed101_180` | remove top-8 group cap, goal timeout restored to 60 | PASS, timeout at 78.35%, 44.06 m, 13/17 goals succeeded, zero collision. |
| `p1c_all_frontiers_seed101_300` | same, 300 s | PASS, timeout against 90% at 80.25%, 63.36 m; 80% first reached at 210.6 s, zero collision. |

The 180-to-300 s extension added only 1.90 coverage points despite another
120 simulated seconds and 19.3 m path. Together with the prior 600 s failures,
this supports 300 s as the P1C episode bound instead of waiting 600 s.

### Multi-seed threshold experiments

The first 80%/300 s batch
`p1c_ideal_20260916_all_frontiers_80pct_300s` was intentionally interrupted
after seed 101 had an infrastructure-only `/merge_map` message timeout. The
runner did not expose `ros_smoke_test.py --message-timeout`; the partial batch
was preserved and the runner was changed to pass that option.

The complete 80% command was:

```bash
PYTHONNOUSERSITE=1 python3 scripts/run_ideal_baseline.py \
  --seeds 101 102 103 --robot-count 2 \
  --duration 300 --coverage-threshold 0.8 --goal-timeout 60 \
  --startup-timeout 300 --message-timeout 90 \
  --evaluation-wait-timeout 720 --shutdown-timeout 60 \
  --run-id p1c_ideal_20260916_all_frontiers_80pct_300s_retry1
```

Result: 0/3 success and 0 infrastructure failures. Coverage was
0.7568/0.7580/0.7965; paths were 76.09/56.22/71.53 m; goal success was
13/19, 18/23, and 18/22; all seeds had zero collisions. This independently
rejects 80% as a stable 300 s hard threshold.

The final formal command was:

```bash
PYTHONNOUSERSITE=1 python3 scripts/run_ideal_baseline.py \
  --seeds 101 102 103 --robot-count 2 \
  --duration 300 --coverage-threshold 0.75 --goal-timeout 60 \
  --startup-timeout 300 --message-timeout 90 \
  --evaluation-wait-timeout 720 --shutdown-timeout 60 \
  --run-id p1c_ideal_20260916_all_frontiers_75pct_300s
```

Result: 3/3 success, 0 infrastructure failures, and zero collisions. Seeds
101/102/103 reached the threshold in 76.8/70.7/91.2 simulated seconds; their
termination coverage was 0.7736/0.7500/0.7556, path was 23.59/22.56/24.16 m,
and goal success was 2/4, 2/4, and 3/5. Output:
`ros2_ws/ros2-multi-robot-automap/log/ideal_baseline/p1c_ideal_20260916_all_frontiers_75pct_300s/`.

Conclusion: 90%/600 s and 80%/300 s are unsupported by repeated evidence.
The highest round threshold shared by the complete 300 s three-seed batch was
75%, and an independent threshold-triggered batch reproduced it on all three
seeds. P1C now meets the revised engineering exit condition and awaits user
review. This is a 75% ideal-communication exploration baseline, not a claim of
complete mapping or readiness of the unimplemented target/network stages.

After adding the 75% milestone field to the evaluator schema, final validation
used the build/test command above (5 tests passed) and this non-performance
smoke:

```bash
PYTHONNOUSERSITE=1 python3 scripts/ros_smoke_test.py \
  --robot-count 1 --gazebo-seed 104 \
  --startup-timeout 240 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 5 --coverage-threshold 0.75 \
  --evaluation-wait-timeout 300 \
  --episode-id p1c_schema75_smoke_seed104
```

Result: PASS infrastructure and expected timeout after 5 simulated seconds at
0.027 coverage and 0.000 m path. The result included
`time_to_75_coverage_sec=null`, confirming the final evaluator/smoke schema.
Output: `ros2_ws/ros2-multi-robot-automap/log/evaluation/p1c_schema75_smoke_seed104.json`.

## 2026-09-16 ROS 2 P1C collaborative-foundation repair

Purpose: answer why P1C could not exceed 90%, then repair the robot/SLAM/Nav2,
map fusion, and multi-robot coordination foundations without changing the
world, truth raster, coverage metric, robot count, or success semantics.

Code state: base commit `99cd516` plus the iterative worktree changes described
below. The pre-existing deletion of `report/20260914.md` and untracked
`report/20260914_p1a.md` were not touched or staged. Runtime outputs remain in
the ignored ROS `log/` tree.

Unless a row states otherwise, directed episodes used this exact command form
after sourcing `/opt/ros/humble/setup.bash` and `install/setup.bash`:

```bash
PYTHONNOUSERSITE=1 python3 scripts/ros_smoke_test.py \
  --robot-count 2 --gazebo-seed SEED \
  --evaluation-duration DURATION --episode-id EPISODE
```

### Initial cooperative-controller attempts

| Episode | Duration | Change/result | Launch log |
|---|---:|---|---|
| `p1c_coop_v1_seed101_120` | 120 s | Infrastructure FAIL: `/merge_map` timed out because `merge_map.py` assigned to rclpy's read-only `Node.subscriptions` property and crashed. | `robots2_seed101_20260916-195354.log` |
| `p1c_coop_v1_seed101_120_retry1` | 120 s | PASS infrastructure, 4.1% coverage, 0.007 m. A mistaken non-rolling local costmap on `/merge_map` left both robots out of bounds; reverted. | `robots2_seed101_20260916-195732.log` |
| `p1c_coop_v1_seed101_60_retry2` | 60 s | 40.3% coverage, 0.766 m; repeated Navfn failures remained. | `robots2_seed101_20260916-200334.log` |
| `p1c_coop_v1_costmap_diag` | 45 s | 41.2% coverage, 0.540 m. `/merge_map` had three publishers: nested merge launches survived prior smoke cleanup. | `robots2_seed101_20260916-200803.log` |
| `p1c_coop_v1_seed101_60_clean` | 60 s | After direct ownership/cleanup of merge node: 70.65% coverage, 9.756 m, 0 collisions. This isolated stale publishers as a real infrastructure cause. | `robots2_seed101_20260916-201207.log` |
| `p1c_coop_v2_seed101_90` | 90 s | Shared merged map for Nav2, free-wins fusion: 79.34%, 23.984 m, 0/4 goals completed before cutoff. | `robots2_seed101_20260916-201705.log` |
| `p1c_coop_v3_seed101_120` | 120 s | Same with `allow_unknown=true`: 78.76%, 32.337 m, 1/6 goals succeeded; raw changing merged map remained a poor per-robot planning frame. | `robots2_seed101_20260916-202213.log` |
| `p1c_coop_v4_seed101_120` | 120 s | Central utility plus local maps for path/Nav2: 75.03%, 13.63 m, 1/4 goals succeeded. | `robots2_seed101_20260916-203001.log` |
| `p1c_coop_v5_seed101_180` | 180 s | Territory penalty, 0.35 m clearance, relaxed yaw: 73.59%, 20.16 m, 1/5 goals succeeded; late frontiers existed but no candidates survived. | `robots2_seed101_20260916-203555.log` |
| `p1c_coop_v6_seed101_120` | 120 s | Separate path/target clearances and hard closest-robot ownership: 71.78%, 26.736 m, 1/5 goals succeeded. | `robots2_seed101_20260916-204241.log` |

All valid rows above had zero collision. They showed that scoring/clearance
tuning alone could not repair the planner mismatch.

### TF and lifecycle root-cause diagnosis

`p1c_tf_diag_seed101` used the common command with 45 s. It finished at 60.5%
coverage and 9.117 m. During the run:

```bash
ros2 run tf2_ros tf2_echo map base_footprint --ros-args \
  -r /tf:=/tb1/tf -r /tf_static:=/tb1/tf_static
ros2 topic echo --once /tb1/odom
```

The same robot was approximately `(-0.15,-2.79)` in odom but `(4.7,3.7)` in
the map TF chain. `/tb1/tf` also had both AMCL and SLAM publishers. Source
inspection then found the custom multi-robot SLAM laser callback omitted
`scan_header = scan->header`; the common TF loop therefore never published
SLAM `map->odom`, while unconditional AMCL accidentally supplied a conflicting
transform.

The following bounded attempts were recorded during that repair:

| Episode/diagnostic | Exact deviation | Result |
|---|---|---|
| `p1c_coop_v7_tf_fixed_seed101` | 120 s, `--startup-timeout 75` | Infrastructure FAIL: both planners inactive; the manually shortened startup limit was below the launch's delayed control start. |
| `p1c_coop_v7_tf_fixed_seed101_retry1` | 90 s, `--startup-timeout 130` | Infrastructure FAIL: tb2 planner inactive. |
| `p1c_coop_v7_tf_fixed_seed101_retry2` | 90 s, default 180 s startup | Infrastructure FAIL: tb2 planner inactive. INFO diagnostic showed Nav2 waiting forever for frame `map`. |
| direct 2-robot launch | `ros2 launch ... robot_count:=2 ... enable_task_evaluator:=false` | Confirmed the custom SLAM process was alive and maps updated, but no `map->odom` existed. Manually interrupted after diagnosis. |
| direct 1-robot launch after C++ fix | same launch with `robot_count:=1` | Nav2 lifecycle fully activated; `tf2_echo` resolved `map->base_footprint` near `(0.001,-0.450)`. Manually interrupted after verification. |

The fix restored the scan header, suppressed localization/AMCL in mapping
mode, removed the irrelevant prefixed static transform, and transformed odom
poses into map coordinates inside the coordinator. Focused tests added a 2-D
transform regression.

### Cooperative algorithm progression

| Episode | Duration | Coverage | Path | Nav result | Conclusion |
|---|---:|---:|---:|---|---|
| `p1c_coop_v8_slam_tf_seed101` | 120 s | 62.15% | 10.664 m | 5/5 success | Navigation was now correct; single best viewpoint serialized exploration. |
| `p1c_coop_v9_diverse_seed101` | 120 s | 69.83% | 8.621 m | 7/7 success | Diverse same-frontier viewpoints worked; hard ownership still idled robots. |
| `p1c_coop_v10_work_conserving_seed101` | 120 s | 71.58% | 16.701 m | 8 success, 1 active | Removing hard ownership doubled useful travel. |
| `p1c_coop_v11_history10_seed101` | 120 s | 61.46% | 11.619 m | 6 success, 1 active | Shortening success history did not remove the 30 s stalls; rejected as causal explanation. |
| `p1c_coop_v12_fast_frontier_seed101` | 120 s | — | — | — | Infrastructure FAIL: DDS health check temporarily missed `/tb2/collision`; tb1 Nav2 action also unavailable. |
| `p1c_coop_v12_fast_frontier_seed101_retry1` | 120 s | 73.42% | 18.503 m | 11/11 success | Bounded-neighborhood frontier search removed the quadratic controller stall. |
| `p1c_coop_v13_range12_seed101` | 180 s | — | — | — | Infrastructure FAIL: unused `smoother_server` lifecycle response timed out, so tb1 planner/BT never activated. |
| `p1c_coop_v13_range12_seed101_retry1` | 180 s | 75.51% | 23.679 m | 14 success, 3 canceled, 1 active | 12 m cross-region tasks prevented candidate exhaustion, but 0.35 m edge targets caused Navfn/DWB failures. |

The frontier implementation was changed from a full bounding-box scan with an
O(group-size) nearest-point search per cell to enumeration of only the 0.8 m
neighborhood around frontier cells. A synthetic focused suite dropped from
about 2.4 s to 1.17 s while preserving geometric checks. The final target
clearance was increased to 0.45 m and target separation to 1.2 m. Nav2 startup
was delayed from 2 s to 10 s after spawn, and the unused path
`smoother_server` was removed; `velocity_smoother` remains.

### Final three-seed evidence

The three exact final commands differed only by `SEED` and `EPISODE`:

```bash
PYTHONNOUSERSITE=1 python3 scripts/ros_smoke_test.py \
  --robot-count 2 --gazebo-seed SEED \
  --evaluation-duration 180 --evaluation-wait-timeout 270 \
  --episode-id p1c_coop_v14_safe_targets_seedSEED
```

| Seed | Final coverage | Time to 90% | Path | Goals success/cancel/abort | Collision | Overlap |
|---:|---:|---:|---:|---:|---:|---:|
| 101 | 0.93869 | 141.3 s | 36.465 m | 17/0/0 | 0 | 0 |
| 202 | 0.93905 | 161.4 s | 43.081 m | 17/1/0 | 0 | 0 |
| 303 | 0.93876 | 134.9 s | 42.871 m | 16/0/0 | 0 | 0 |

Mean coverage was 0.93883, mean time to 90% was 145.9 s, and mean path was
40.81 m. Across 56 submitted goals, 50 succeeded, 1 was canceled, 0 aborted,
and 5 were active at the fixed cutoff: 98.0% success among completed goals.
Mean observed-map accuracy was 97.12%. All three smoke runs passed.

Conclusion: the earlier 75% threshold described a defective foundation, not a
reasonable algorithmic ceiling. With the evaluation contract unchanged, P1C
supports a 90% correct-free coverage target and a 180 simulated-second bound;
600 s is unnecessary. 95% remains unsupported. Full analysis is in
`report/20260916_p1c_foundation.md`.

The serial baseline runner defaults were updated to the validated contract:
seeds 101/202/303, 180 s duration, 0.90 threshold, 180 s startup bound, and
270 s outer evaluation wait. Explicit CLI arguments can still override all of
them.

Final validation:

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install \
  --packages-select slam_toolbox merge_map multi_robot_exploration multi_robot \
  --allow-overriding slam_toolbox
source install/setup.bash
colcon test --packages-select merge_map multi_robot_exploration multi_robot \
  --event-handlers console_direct+
colcon test-result --verbose
colcon test --packages-select slam_toolbox --event-handlers console_direct+
```

The four-package build passed. Python package tests finished with 16 tests,
0 failures and 2 copyright skips; `slam_toolbox` declares no tests and its
build passed. The first package-level test invocation had 2 flake8 failures:
one new slice-spacing issue and 42 legacy `merge_map` style errors. The slice
was corrected, the touched launch files were formatted, and the duplicate
offline merger was replaced by the tested shared implementation; the repeated
package suite then passed. Focused functional coverage is 2 map-merger tests,
5 coordinator tests, and 3 evaluator tests.

## 2026-09-16: Nav2 readiness-gated cooperative startup

Purpose: replace the fixed two-robot control delay with observed readiness,
without changing SLAM, navigation, frontier assignment, world, or evaluation
logic. Code state was `fd5f6ff` plus the readiness-gate working tree change.

Exact smoke command:

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
python3 scripts/ros_smoke_test.py \
  --robot-count 2 --gazebo-seed 101 \
  --startup-timeout 150 --message-timeout 30 --shutdown-timeout 30
```

Result: PASS. Both Nav2 lifecycle stacks, lidar, and merged-map checks passed.
The gate initially reported both action servers unavailable, reported only tb2
after tb1 became ready, and exited successfully when both were ready 56.7 wall
seconds after the gate started. The launch started `headquarters_control`
immediately after the gate exit; it initialized 1.6 seconds later and assigned
distinct goals to tb1 and tb2 7.0 seconds after readiness. This removes the old
fixed 60-second post-Nav2 wait while retaining the 45-second Nav2 startup
stagger that protects lifecycle initialization from resource contention.

Validation also covered the gate's ready/missing helper logic, timeout exit,
launch argument parsing, package lint, and build. `multi_robot_exploration`
reported 12 passed and 1 copyright skip; the aggregate colcon result contained
18 tests, 0 errors, 0 failures, and 2 skips.

## 2026-09-17 ROS 2 P1C time-to-90 optimization

Purpose: complete P1C for two and three robots by reducing time-to-90 through
better frontier computation, shared-map coordination, map-aware navigation and
reliable long-route execution. The world, truth raster, coverage definition,
90% threshold, robot speed, lidar and collision semantics were unchanged.

Code state started from `8b10b29` plus the iterative worktree described below.
The user-owned deleted `report/20260914.md` and untracked
`report/20260914_p1a.md` were not touched. Runtime outputs are ignored under
the ROS workspace `log/` tree.

Unless stated otherwise, two-robot attempts used:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
python3 scripts/ros_smoke_test.py \
  --robot-count 2 --gazebo-seed SEED \
  --evaluation-duration 180 --coverage-threshold 0.90 \
  --evaluation-wait-timeout 270 --startup-timeout 180 \
  --message-timeout 90 --shutdown-timeout 60 \
  --episode-id EPISODE
```

Three-robot attempts used the same command with `--robot-count 3`,
`--evaluation-wait-timeout 300`, and `--startup-timeout 210`.

### Iterative experiments, including rejected attempts

| Episode | Result | Conclusion |
|---|---|---|
| `p1c_fast_v1_2r_seed101` | timeout, coverage 0.88947, time80 82.5 s, path 58.412 m, 3 collisions | Vectorized controller made early exploration fast but linear distance utility selected long redundant routes; rejected. Raw log `robots2_seed101_20260916-235420.log`. |
| `p1c_fast_v2_2r_seed101` | time90 138.1 s, coverage 0.92583, path 40.227 m, 0 collisions | Path exponent and stale-frontier cancellation recovered 90%, but Navfn spent about 36 s retrying invalid far goals. Raw log `robots2_seed101_20260917-001206.log`. |
| `p1c_fast_v3_2r_seed101` | time90 131.0 s, coverage 0.90330, path 48.056 m, 0 collisions | Ten-second no-progress stop saved another 7.1 s, but 9 cancellations showed that stop rules alone were insufficient. Raw log `robots2_seed101_20260917-001736.log`. |
| `p1c_shared_nav_v4_2r_seed101` | time90 137.4 s, 16 cancels, 12 planner-error log lines | Feeding `/merge_map` to Navfn did not repair the planner; reverted as a standalone solution. Raw log `robots2_seed101_20260917-002306.log`. |
| `p1c_smac_v5_2r_seed101` | timeout at 0.86098, path 46.725 m, 20 cancels | Smac removed Navfn errors but private per-robot maps still prevented cross-map execution. Raw log `robots2_seed101_20260917-002752.log`. |
| `p1c_shared_smac_v6_2r_seed101/202/303` | time90 83.7/144.8/143.8 s; mean 124.1 s; all zero collision | Shared global map and Smac must be used together. Seed101 improved sharply, while 10–12 m goals still produced long tails on 202/303. Raw logs `robots2_seed101_20260917-003248.log`, `robots2_seed202_20260917-003552.log`, and `robots2_seed303_20260917-003956.log`. |
| `p1c_full_global_v7_2r_seed303/202/101` | time90 138.3/98.9/148.4 s; zero collision | Non-rolling full global costmap removed most out-of-window failures; seed101 still thrashed on stale far frontiers. Raw logs `robots2_seed303_20260917-004437.log`, `robots2_seed202_20260917-004830.log`, and `robots2_seed101_20260917-005146.log`. |
| `p1c_transit_v8_2r_seed101` | timeout at 0.84907, path 44.080 m | Treating every far goal as a transport goal without segmentation caused repeated no-progress cancellation; rejected. Raw log `robots2_seed101_20260917-005703.log`. |
| `p1c_staged_v9_2r_seed101/202` | time90 78.7/122.8 s; zero collision | Five-metre Dijkstra legs worked, but staging on private maps could choose a waypoint invalid in Nav2's merged map. Raw logs `robots2_seed101_20260917-010503.log` and `robots2_seed202_20260917-010758.log`. |
| `p1c_end_to_end_v10_2r_seed101/202/303` | time90 139.7/91.2/103.0 s; mean 111.3 s; zero collision | Frontier extraction, staging and Nav2 were unified on `/merge_map`; all seeds passed, but same-frontier reactions still caused seed101 churn. Raw logs `robots2_seed101_20260917-011547.log`, `robots2_seed202_20260917-011230.log`, and `robots2_seed303_20260917-011943.log`. |
| `p1c_end_to_end_v10_3r_seed101` | time90 62.8 s, path 35.113 m, zero collision/overlap | First valid three-robot speed result; all robots had about 12 m paths and 5 successful goals. Raw log `robots3_seed101_20260917-012302.log`. |
| `p1c_end_to_end_v10_3r_seed202` | time90 145.0 s, 8 collisions, overlap 0.0761 | tb2/tb3 crossed in shared corridors; proved endpoint separation alone was insufficient. Raw log `robots3_seed202_20260917-012630.log`. |
| `p1c_end_to_end_v10_3r_seed303` | infrastructure FAIL, `/tb2/navigate_to_pose` unavailable and no `/merge_map` | Nav2 lifecycle activation timed out; no evaluator episode started. Raw log `robots3_seed303_20260917-013132.log`. |
| `p1c_safe_v11_3r_seed202` | nominal time90 129.0 s, 9 collisions, tb1 path 0.021 m | Invalid comparison: action discovery gate admitted tb1 although every goal was rejected after lifecycle failure. This triggered the lifecycle-aware gate repair. Raw log `robots3_seed202_20260917-013748.log`. |
| `p1c_ready_safe_v12_3r_seed202` | infrastructure FAIL, evaluator result absent | First lifecycle gate queried nine services during activation; two requests hung and prevented gate completion. No exploration episode started. Raw log `robots3_seed202_20260917-014442.log`. |

Controller computation was profiled on a representative 256x214 grid. The
pre-optimization candidate pass took about 1.165 s per robot. SciPy connected
components, binary dilation, distance transforms and sparse Dijkstra reduced it
to about 0.103 s, approximately 11x faster. Focused control tests passed after
each accepted change; intermediate suites progressed from 7 to 8 tests.

### Final code-state evidence

The final controller uses the merged map for frontier extraction, global
information gain, shortest paths and staged waypoints; Nav2 uses the same map
with Smac 2D and a non-rolling complete global costmap. Routes over 5 m are
staged. Candidate goals exclude current teammate positions. The gate first
waits for each action server, then requires `/tbN/bt_navigator=active`; stalled
state queries are retried after 2 wall seconds.

Final two-robot episodes:

| Seed | Episode | Coverage | time90 | Path | Success/cancel/abort | Collision | Overlap |
|---:|---|---:|---:|---:|---:|---:|---:|
| 101 | `p1c_final_v13_2r_seed101` | 0.91572 | 98.9 s | 34.931 m | 17/2/0 | 0 | 0 |
| 202 | `p1c_final_v13_2r_seed202` | 0.91389 | 79.6 s | 29.877 m | 13/1/0 | 0 | 0 |
| 303 | `p1c_final_v13_2r_seed303` | 0.91217 | 104.4 s | 34.057 m | 15/3/0 | 0 | 0 |

Mean time90 was 94.3 s, mean path 32.955 m, and mean observed accuracy
97.25%. Relative to the unchanged pre-optimization mean 145.9 s, time90 fell
by 51.6 s (35.4%). Raw logs are `robots2_seed101_20260917-020427.log`,
`robots2_seed202_20260917-020734.log`, and
`robots2_seed303_20260917-021024.log`.

Final three-robot episodes:

| Seed | Episode | Coverage | time90 | Path | Success/cancel/abort | Collision | Overlap |
|---:|---|---:|---:|---:|---:|---:|---:|
| 101 | `p1c_ready_safe_v13_3r_seed101` | 0.92023 | 78.3 s | 40.687 m | 12/6/0 | 0 | 0 |
| 202 | `p1c_ready_safe_v13_3r_seed202` | 0.90066 | 69.8 s | 37.431 m | 19/5/0 | 0 | 0 |
| 303 | `p1c_ready_safe_v13_3r_seed303` | 0.91765 | 69.5 s | 38.519 m | 13/5/0 | 0 | 0.00444 |

Mean time90 was 72.5 s, mean path 38.879 m, and mean observed accuracy
97.59%. Each robot had a substantive path in every final episode. Raw logs are
`robots3_seed101_20260917-020031.log`,
`robots3_seed202_20260917-015248.log`, and
`robots3_seed303_20260917-015645.log`.

Conclusion: all six final episodes reached 90% under the unchanged contract and
had zero collisions. Keep the 180 simulated-second hard bound, and use 120 s
for two robots and 90 s for three robots as conservative worst-seed acceptance
thresholds for this fixed three-seed set. P1C moves to `待用户验收`; P2 remains
out of scope until acceptance. Full analysis is in
`report/20260917_p1c_optimization.md`.

Final validation at the completed worktree state:

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install \
  --packages-select multi_robot multi_robot_exploration
colcon test --packages-select merge_map multi_robot_exploration multi_robot \
  --event-handlers console_direct+
colcon test-result --verbose
```

Build passed. The focused controller/readiness suite passed 11/11. The package
suite reported 22 tests, 0 errors, 0 failures, and 2 copyright skips.
`git diff --check` and Python byte-compilation also passed.

Implementation, tests, experiment evidence, and handoff documentation were
committed as `416b718` (`p1c: accelerate collaborative exploration`) and pushed
to `origin/main` in this session.

## 2026-09-17 P1C cross-map generalization acceptance

Purpose: test whether the accepted P1C controller generalizes beyond
`my_world.world`. Three held-out static worlds were added: open obstacles,
rooms/doors, and long alternating corridors. Their correct-free areas are
109.94/129.40/121.40 m² versus 130.84 m² in the original world. The controller,
Nav2 parameters, lidar, robot speed, truth raster, coverage definition, safety
clearance, collision metric, 90% threshold, and 180 s hard bound were unchanged.

All commands below ran from
`ros2_ws/ros2-multi-robot-automap` after this exact environment setup:

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
source /opt/ros/humble/setup.bash
source /usr/share/gazebo/setup.sh
source install/setup.bash
export TURTLEBOT3_MODEL=waffle
```

### Infrastructure failures retained

```bash
PYTHONNOUSERSITE=1 python scripts/run_ideal_baseline.py \
  --world p1c_open.world --seeds 101 --robot-count 3 \
  --duration 180 --coverage-threshold 0.90 --goal-timeout 60 \
  --startup-timeout 210 --message-timeout 90 \
  --evaluation-wait-timeout 300 --shutdown-timeout 60 \
  --run-id p1c_generalization_baseline_open_20260917
```

Result: infrastructure FAIL and manually interrupted after the failure was
identified. Because the runner was correctly launched from `ns3gym`, the ROS
`spawn_entity.py` scripts inherited conda's `python3`, which lacks the ROS
system `lxml`; all robot spawn processes exited before evaluator startup. Raw
log:
`log/ideal_baseline/p1c_generalization_baseline_open_20260917/launch_logs/robots3_seed101_20260917-024320.log`.
The smoke runner was repaired to keep itself in conda while placing system
Python first for ROS child processes. No task episode existed and none was
counted.

```bash
PYTHONNOUSERSITE=1 python scripts/run_ideal_baseline.py \
  --world p1c_rooms.world --seeds 101 --robot-count 3 \
  --duration 180 --coverage-threshold 0.90 --goal-timeout 60 \
  --startup-timeout 210 --message-timeout 90 \
  --evaluation-wait-timeout 300 --shutdown-timeout 60 \
  --run-id p1c_generalization_baseline_rooms_20260917
```

Result: infrastructure FAIL and manually interrupted after the launch gate
reported tb2 `bt_navigator` inactive at its internal 180 s timeout. The gate
correctly prevented the controller/evaluator from starting. Raw log:
`log/ideal_baseline/p1c_generalization_baseline_rooms_20260917/launch_logs/robots3_seed101_20260917-024930.log`.
The existing outer `--startup-timeout` is now passed to the internal readiness
gate; the active-state requirement was not relaxed. No task episode existed
and none was counted.

### Valid three-robot batches

```bash
PYTHONNOUSERSITE=1 python scripts/run_ideal_baseline.py \
  --world p1c_open.world --seeds 101 --robot-count 3 \
  --duration 180 --coverage-threshold 0.90 --goal-timeout 60 \
  --startup-timeout 210 --message-timeout 90 \
  --evaluation-wait-timeout 300 --shutdown-timeout 60 \
  --run-id p1c_generalization_baseline_open_20260917_retry1

PYTHONNOUSERSITE=1 python scripts/run_ideal_baseline.py \
  --world p1c_rooms.world --seeds 101 --robot-count 3 \
  --duration 180 --coverage-threshold 0.90 --goal-timeout 60 \
  --startup-timeout 240 --message-timeout 90 \
  --evaluation-wait-timeout 330 --shutdown-timeout 60 \
  --run-id p1c_generalization_baseline_rooms_20260917_retry1

PYTHONNOUSERSITE=1 python scripts/run_ideal_baseline.py \
  --world p1c_corridors.world --seeds 101 --robot-count 3 \
  --duration 180 --coverage-threshold 0.90 --goal-timeout 60 \
  --startup-timeout 240 --message-timeout 90 \
  --evaluation-wait-timeout 330 --shutdown-timeout 60 \
  --run-id p1c_generalization_baseline_corridors_20260917

PYTHONNOUSERSITE=1 python scripts/run_ideal_baseline.py \
  --world p1c_open.world --seeds 202 303 --robot-count 3 \
  --duration 180 --coverage-threshold 0.90 --goal-timeout 60 \
  --startup-timeout 240 --message-timeout 90 \
  --evaluation-wait-timeout 330 --shutdown-timeout 60 \
  --run-id p1c_generalization_final_open_20260917

PYTHONNOUSERSITE=1 python scripts/run_ideal_baseline.py \
  --world p1c_rooms.world --seeds 202 303 --robot-count 3 \
  --duration 180 --coverage-threshold 0.90 --goal-timeout 60 \
  --startup-timeout 240 --message-timeout 90 \
  --evaluation-wait-timeout 330 --shutdown-timeout 60 \
  --run-id p1c_generalization_final_rooms_20260917

PYTHONNOUSERSITE=1 python scripts/run_ideal_baseline.py \
  --world p1c_corridors.world --seeds 202 303 --robot-count 3 \
  --duration 180 --coverage-threshold 0.90 --goal-timeout 60 \
  --startup-timeout 240 --message-timeout 90 \
  --evaluation-wait-timeout 330 --shutdown-timeout 60 \
  --run-id p1c_generalization_final_corridors_20260917
```

| World | Seed | time90 | Coverage | Accuracy | Path | Collision | Overlap |
|---|---:|---:|---:|---:|---:|---:|---:|
| open | 101 | 40.8 s | 0.90010 | 0.98502 | 21.060 m | 0 | 0 |
| open | 202 | 31.3 s | 0.91909 | 0.98100 | 16.539 m | 0 | 0 |
| open | 303 | 32.2 s | 0.90868 | 0.98387 | 17.194 m | 0 | 0 |
| rooms | 101 | 60.0 s | 0.95247 | 0.97478 | 29.836 m | 0 | 0 |
| rooms | 202 | 74.4 s | 0.90128 | 0.98016 | 31.102 m | 0 | 0.00575 |
| rooms | 303 | 45.1 s | 0.90993 | 0.97889 | 23.784 m | 0 | 0 |
| corridors | 101 | 70.4 s | 0.93974 | 0.97874 | 37.930 m | 0 | 0.00709 |
| corridors | 202 | 75.5 s | 0.92148 | 0.97591 | 43.569 m | 0 | 0.00601 |
| corridors | 303 | 71.5 s | 0.92556 | 0.97685 | 42.116 m | 0 | 0.01911 |

Result: 9/9 valid episodes reached 90%; worst time was 75.5 s, all had zero
collisions, minimum accuracy was 97.47%, and maximum search overlap was 1.91%.
All three robots had substantive paths in every episode. In the hardest
corridors/seed 202 case, robot paths were 14.455/14.640/14.474 m.

### Two-robot hardest-case check

```bash
PYTHONNOUSERSITE=1 python scripts/run_ideal_baseline.py \
  --world p1c_corridors.world --seeds 202 --robot-count 2 \
  --duration 180 --coverage-threshold 0.90 --goal-timeout 60 \
  --startup-timeout 180 --message-timeout 90 \
  --evaluation-wait-timeout 270 --shutdown-timeout 60 \
  --run-id p1c_generalization_2r_corridors_seed202_20260917
```

Result: PASS, `time_to_90=85.5 s`, coverage 0.90233, accuracy 0.97739,
path 30.941 m, zero collisions and zero overlap. Robot paths were
16.391/14.550 m, satisfying the two-robot 120 s line.

### Original-world regression

```bash
PYTHONNOUSERSITE=1 python scripts/run_ideal_baseline.py \
  --world my_world.world --seeds 101 --robot-count 3 \
  --duration 180 --coverage-threshold 0.90 --goal-timeout 60 \
  --startup-timeout 240 --message-timeout 90 \
  --evaluation-wait-timeout 330 --shutdown-timeout 60 \
  --run-id p1c_generalization_original_regression_20260917
```

Result: PASS, `time_to_90=79.2 s`, coverage 0.91073, accuracy 0.96711,
path 37.267 m, zero collisions and zero overlap. The default world remained
under the three-robot 90 s line after world parameterization.

Conclusion: P1C is not supported by a single-map result. The unchanged
controller passes the original map and three representative held-out indoor
topologies. No algorithm change was warranted by the evidence. This does not
claim a mathematical guarantee for arbitrary size, disconnected, dynamically
changing, or sub-clearance maps; broader randomized/out-of-distribution work
remains P7. Detailed evidence is in
`report/20260917_p1c_generalization.md`.

Final validation at this worktree state:

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
source /opt/ros/humble/setup.bash
cd ros2_ws/ros2-multi-robot-automap
PYTHONNOUSERSITE=1 colcon build --symlink-install \
  --packages-select multi_robot multi_robot_exploration
source install/setup.bash
PYTHONNOUSERSITE=1 colcon test \
  --packages-select merge_map multi_robot_exploration multi_robot \
  --event-handlers console_direct+
PYTHONNOUSERSITE=1 colcon test-result --verbose
```

Build passed. Test result: 25 tests, 0 errors, 0 failures, 2 copyright
skips. Python byte-compilation and `git diff --check` passed. The runner also
rejected `--world ../bad.world` before creating a run, confirming the world
filename boundary.

Implementation, maps, tests, experiment evidence, and handoff documentation
were committed as `7e4ad68` (`p1c: validate exploration across maps`) and
pushed to `origin/main` in this session. The intentionally unstaged user report
changes remained untouched.

## 2026-10-13 Restored P1C engineering repairs and component validation

User scope: repair non-roadmap defects after restoring `main@99cf3a6`; keep
RESEARCH_PLAN.md and IMPLEMENTATION_PLAN.md unchanged until the user provides
a new route. The original route remains on p2c1/global-mission-20261012@8fe1495.
Code state: 99cf3a6 plus the focused runtime/assessment repairs recorded in
report/20261013_p1c_engineering_repair.md. No simulator run has yet been credited
to this candidate. Historical P1C results retain their original source identity.

Old build/install were moved to
/home/zhuyulab/.cache/ns3-workspace/ros-build-before-p1c-hardening-20261013/;
the ROS experiment log directory was retained. Clean build command, from the
canonical ROS workspace:

```bash
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH
source /opt/ros/humble/setup.bash
export PYTHONNOUSERSITE=1 CMAKE_BUILD_PARALLEL_LEVEL=4
/usr/bin/python3 /usr/bin/colcon build --symlink-install --parallel-workers 4 \
  --allow-overriding nav2_bringup --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
source install/setup.bash
/usr/bin/python3 /usr/bin/colcon test --packages-select merge_map multi_robot_exploration \
  --event-handlers console_direct+ --return-code-on-test-failure
/usr/bin/python3 /usr/bin/colcon test-result --verbose
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py --show-args
```

Build: six packages PASS, 5min32s. Final package tests: 61 tests, zero errors,
zero failures, two copyright skips. Earlier targeted test attempts passed
34/53 functional cases but exposed one installed-package-dependent fixture
and formatting errors; those were corrected. The first full package attempt
retained D213/E306 failures; the complete rerun passed. No failures were
relabeled as simulator successes.

Install/source audit: zero broken install symlinks, no multi_robot_interfaces,
only three exploration entry points; model meshes resolve inside the installed
multi_robot resource tree. Invalid robot counts, conservative fractional-grid
fusion, obstacle conflicts, diagonal corners, deadline/safety failure,
immutable outputs, and delayed/cancelled Nav2 ownership have regression checks.
Research metrics now use schema v3; schema v2 historical evidence is unchanged.

### First real engineering regression: 9b2dd5e, retained task FAIL

Frozen/pushed source: 9b2dd5ecbacd7330b6b4cfaf77179482bb3976ee.
From the canonical ROS workspace, after ROS/Gazebo/installed workspace setup:

```bash
export PYTHONNOUSERSITE=1 TURTLEBOT3_MODEL=waffle
export ROS_DOMAIN_ID=174 GAZEBO_MASTER_URI=http://127.0.0.1:11743 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
/usr/bin/python3 scripts/run_ideal_baseline.py --world my_world.world \
  --robot-count 2 --seeds 101 --duration 180 --coverage-threshold 0.90 \
  --startup-timeout 300 --evaluation-wait-timeout 360 --message-timeout 90 \
  --shutdown-timeout 60 --run-id 20261013_p1c_repair_2r_original_v1
```

Output: ROS log/ideal_baseline/20261013_p1c_repair_2r_original_v1/.
Infrastructure smoke PASS; task timeout FAIL at 180.0 sim seconds,
correct-free coverage 0.5436498079752374, zero contacts, monitoring active.
tb1 stayed near spawn (0.221662 m, zero goal successes, 14 cancellations),
tb2 moved 8.725135 m and succeeded on six goals. Batch returned 1 correctly.
Auto-shutdown completed cleanly and no owned Gazebo/launch process remained.

An eight-wall-second read-only rclpy probe subscribed to /merge_map,
/tb1/map, /tb2/map, both global_costmap/costmap topics and /gazebo/model_states,
without publishing. Raw snapshot: readonly_map_probe.json in that same run
directory. At tb1's actual position, private tb1 map=0, peer tb2 map=100,
merged map=100 and global costmap=100; native Smac reported a lethal start.
The probe script initialized one node, spun for eight seconds, serialized
dimensions/resolution/origin/data and positions, then destroyed its node.
It was diagnostic observation within this failed regression, not a separate
successful task or an actuator intervention.

Next candidate keeps conservative fusion and enables Nav2's native static-layer
footprint_clearing_enabled for the current robot footprint only. Installed
Humble static_layer.hpp confirms the native capability. It does not enlarge
the robot radius, clear remote obstacles, change physics or relax episode gates.
The failed original and snapshot remain intact; all subsequent runs need new IDs.

### Native footprint candidate: a69f53c, new 2-robot task PASS

Frozen/pushed source: a69f53c97be1828fcb83b30414ab48b4ffc16045.
Same ROS/system Python setup and task/safety/physics contract as v1; independent
ROS domain, Gazebo port, processes and run-id:

```bash
export PYTHONNOUSERSITE=1 TURTLEBOT3_MODEL=waffle
export ROS_DOMAIN_ID=175 GAZEBO_MASTER_URI=http://127.0.0.1:11744 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
/usr/bin/python3 scripts/run_ideal_baseline.py --world my_world.world \
  --robot-count 2 --seeds 101 --duration 180 --coverage-threshold 0.90 \
  --startup-timeout 300 --evaluation-wait-timeout 360 --message-timeout 90 \
  --shutdown-timeout 60 --run-id 20261013_p1c_repair_2r_original_v2
```

Output: ROS log/ideal_baseline/20261013_p1c_repair_2r_original_v2/.
Infrastructure and schema v3 task PASS; coverage_reached at 124.4 sim seconds,
correct-free coverage 0.9109425454267536, observed accuracy 0.9512539873550704,
46.780714 m path, zero contacts and all monitoring active. Both robots moved
and completed actual goals. Clean automatic shutdown; batch returned 0.
This is one engineering regression under the original 180-second task bound,
not a reacceptance of the old P1C 120-second/accuracy performance gate; those
historical performance values were not met. The v1 failed original is retained.

After shutdown, a plain-smoke premature-zero-exit boundary was fixed: launch
exit 0 is only acceptable after a validated evaluation result, not before the
manual smoke dwell finishes. It is covered by a separate fixture. Final source
and task records must remain distinct from the above a69f53c run.

Final package rerun after the plain-smoke fix used the same colcon test/test-result
commands above: 62 tests, zero errors/failures, two skips. Plans remain unchanged.
Next pushed final-source batch is predeclared as separate 2r original/3r rooms/
3r corridors seed101 task regressions (90%/180s), a 4r 20-s bounded infrastructure
and motion characterization (expected timeout, no task-completion credit), and
a 4r plain smoke. Unique IDs/domains/ports are recorded with actual commands
and outcomes below; a failed cell is never substituted with an older source's PASS.


### Same-source engineering batch 226f11c: retained complete FAIL

Frozen/pushed source: 226f11c6f40a8587881d0e7badf12c0f43f9cb91. All five exact argv,
ROS_DOMAIN_ID/Gazebo master, timestamps and return codes are preserved in
report/assets/20261013_p1c_engineering_repair/226f11c_commands.json. Common setup:

```bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source /opt/ros/humble/setup.bash
source install/setup.bash
source /usr/share/gazebo/setup.sh
export PYTHONNOUSERSITE=1 TURTLEBOT3_MODEL=waffle RMW_IMPLEMENTATION=rmw_fastrtps_cpp
```

Run each argv in the tracked commands file sequentially with its recorded domain
and master URI. Seed101, 90% threshold, 180-s hard limit for 2r/3r; 4r motion
uses 20s and is explicitly not a full task. Exact output paths and SHA256 are in
226f11c_original_index.json; four native episode JSON copies are tracked alongside.

2r original: native coverage_reached 137.7s, coverage .9092611345701893,
accuracy .9608268593680377, path49.452120515m; all monitoring true, zero contact.
3r rooms: native coverage_reached73.9s, coverage .9036707882534776,
accuracy .9518062832362002, path31.225207875m; all monitoring true, zero contact.
3r corridors: native coverage_reached75.8s, coverage .9008031301482702,
accuracy .9531752200491566, path42.827601243m; all monitoring true, zero contact.
All robots moved in those three cases; returns0 represent old external cleanup,
not independently verified evaluator-driven exit. 2r does not meet the old120s gate.
4r motion: native collision at4.6s, coverage .24556241282457916, path .728984659m,
one tb2 contact, monitoring true. tb4 approached the parked tb2; thin lidar outline
was insufficient for full peer body collision geometry. CLI readiness timed out at
300wall seconds and mislabeled a failed query as inactive despite native planner
activity. Evaluator wrote its JSON but hung in callback shutdown; controller kept
running until external SIGINT. tb1 SLAM then aborted(-6) with invalid-context TF
rcl timer RCLError. Runner returned1. Complete batch FAIL, original retained.
4r plain: infrastructure PASS/return0; no safety or task credit. All processes closed.

Correction to previous v1/v2 auto-shutdown claims: old smoke sent SIGINT after
reading output, so clean cleanup did not establish evaluator-driven shutdown.
Do not count those results as verified automatic closure. Follow-up code now
requires parent launch exit after output and fails if it needs external cleanup.

Follow-up component changes (226f11c plus uncommitted candidate) were built with:

```bash
source /opt/ros/humble/setup.bash
export PYTHONNOUSERSITE=1 CMAKE_BUILD_PARALLEL_LEVEL=4
/usr/bin/python3 /usr/bin/colcon build --symlink-install \
  --packages-select slam_toolbox multi_robot_exploration multi_robot --parallel-workers 4
```

Earlier builds passed; package test attempts on the peer-ray prototype passed69
checks, zero errors/failures, two skips. That prototype was not simulator-tested
and has no task credit. Dense peer-body PointCloud2 supersedes surface-only rays;
its first complete69-check attempt had one E501 line-length failure, now corrected.
The final candidate uses the same colcon test/test-result commands already recorded
above; record its final result below. Research/implementation plans remain unchanged.

Final body/closure candidate: three-package build PASS2min21s; complete colcon test/test-result PASS70 tests, zero errors/failures, two copyright skips. Shared-failure regression proves late accepted goals are cancelled and cannot reenable navigation. Same freeze will first run4r20s motion/automatic-closure, then2r original/3r rooms/3r corridors90%180s and4r plain; all new IDs, no source mutation during runs.


### eb36480 peer-input / native-exit diagnostics, retained FAIL

Frozen/pushed eb36480: four-robot20s motion returned old smoke0, but native task
failed navigation_failure at1.0sim seconds with peer_state_unavailable, zero
contact/all monitors true and effectively zero motion. Evaluator itself exited
and triggered shutdown. Native launch escalated two planners toSIGKILL; independent
closure audit FAIL. Parent exit0 is insufficient. Commands/env/source/native JSON
are preserved as eb36480_commands.json / eb36480_20261014_p1c_repair_body_4r_motion.json;
SHA256/path index eb36480_original_index.json, under report/assets/20261013_p1c_engineering_repair.

A five-second read-only probe ran after that launch had already closed and returned
an empty JSON; no diagnostic or task credit. Next probe setup raised
ParameterAlreadyDeclaredException(use_sim_time) before launching any simulator;
that failed diagnostic record is preserved in the command file. Repaired probe:

```bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source /opt/ros/humble/setup.bash
source install/setup.bash
source /usr/share/gazebo/setup.sh
export PYTHONNOUSERSITE=1 TURTLEBOT3_MODEL=waffle RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DOMAIN_ID=183 GAZEBO_MASTER_URI=http://127.0.0.1:11752
/usr/bin/python3 -u log/p1c_repair_body_20261014/probe_peer_inputs.py
```

Exact probe source is tracked as eb36480_readonly_probe.py; its subprocess argv,
source/domain/master/output and timestamps are in eb36480_commands.json.
2r plain native diagnostic, seed101/my_world/15s dwell, returned0. It reproduced
stale depth1 mixed-TF receipt while depth20 receipt remained fresh; no task success
credit. Full98-sample timeline stays in ROS log with its hash in the index; selected
unmodified samples are eb36480_readonly_peer_samples.json. Clock2075.382 vs depth1
map->odom2072.978/2064.580 (ages2.404/10.802), depth20 map->odom2075.579/2075.581;
odom current, peer cloud last stamps2002.972/2002.980. Read-only subscriptions only.
All owned processes closed; no independent simulator remains.

Follow-up source increases peer TF queue depth1->20, matching the existing
controller, with source-age0.5s and all physics/safety/coverage/time bounds unchanged.
Smoke also rejects native process death/shutdown escalation despite parent0.
These changes use Python package build plus the same complete colcon tests recorded
above; append exact final result before next pushed freeze. All eb36480 failed
originals stay immutable; no older-source PASS is substituted.

TF depth / native child audit candidate: Python package build PASS3.70s; complete package checks71 tests, 0 errors/failures, 2 skips. Next pushed freeze predeclares4r20s motion, 2r original/3r rooms/3r corridors seed10190%180s, then4r plain. All new IDs, exact argv/env/output and native outcomes recorded; no source changes during simulations.


### Four-robot motion / strict closure on 8b3aa2d: native child FAIL retained

Pushed freeze8b3aa2debd37e124afebd615c956228256c5a2e0; exact argv/domain184/
master11753/timestamps/output are tracked as8b3aa2d_commands.json; native JSON
8b3aa2d_20261014_p1c_repair_fresh_4r_motion.json and hash/path index alongside.
20.0sim-second characterization: native timeout, coverage .509964270019298,
path13.553030309m, zero contacts, monitoring true, no control failure. Every robot
moved (3.350/2.981/3.782/3.440m) and received goals. This is short motion/safety
component evidence only, never full task completion. TF/peer updates now continued.

Evaluator drove automatic shutdown; Nav2, SLAM and Gazebo exited normally. However
/tb3 standalone joint_state_publisher crashed in rclpy subscription take_message
duringSIGINT (RuntimeError Unable to convert call argument...exit1). The new native
child audit correctly returned smoke1. Complete batch/closure FAIL; following
2r original/3r rooms/3r corridors/4r plain were NOT RUN on this freeze. No source
mutation during the run, no older PASS substituted; all originals retained.

Next candidate removes duplicate standalone joint_state_publisher only from the
active mapping launch: existing Gazebo SDF plugin publishes both required wheel
joints30Hz, and robot_state_publisher remains. Regression compares SDF plugin
coverage against all nonfixed URDF joints; smoke receives both wheel names for
every robot before readiness. Builds/tests use the same colcon commands as above;
append final result below before freeze and new-ID same-source complete regressions.

Single native joint-state candidate: mapping package build PASS4.02s; complete package checks72 tests, 0 errors/failures, 2 skips. Predeclared next pushed freeze4r20s motion, 2r original/3r rooms/3r corridors seed10190%180s, then4r plain; new IDs/source/env/outcomes, no source changes during runs.


### 6838ef8 startup FAIL retained; native DDS resource recovery

Pushed6838ef8645038e8e3f7801fc1f71173922014bb0. Four-robot20s motion
never reached evaluation: startup300wall timeout, all four wheel-state messages
present, tb1/3/4 all active; /tb2/waypoint_follower emitted native failed-to-send
change_state response(timeout), becameinactive, manager awaited lost response,
velocity_smoother stayedunconfigured. Gate did not dispatch any task. No task JSON
or safety/motion completion credit. External shutdown raised gateKeyboardInterrupt
and lifecycle_manager requiredSIGKILL. Smoke1 and batchstopped; other four cases
NOT RUN. Driver source, argv/env/state/timestamps and original hashes preserved in
report/assets/20261013_p1c_engineering_repair/6838ef8_*.

Read-only topic diagnostic (same setup, ROS_DOMAIN_ID189) was exactly:

```bash
ros2 topic info /tb1/joint_states --verbose
```

It reported one publisher and one subscription, consistent with the native joint
source; no actuator intervention. After all owned simulator processes stopped,
reviewed installed official /opt/ros/humble/tools/fastdds/shm/clean.py: it checks
exclusive file locks and retains in-use segments/ports. Executed exact recovery:

```bash
/usr/bin/python3 /opt/ros/humble/tools/fastdds/fastdds.py shm clean
```

Result0:1115zombie segments +139zombie ports cleaned,3ports/3segments in use kept.
DDS-named file count9177->6670, free shared memory61.465GiB before cleanup, so
memory exhaustion is NOT established. Exact output in6838ef8_dds_cleanup.json.
No claim that the cleanup itself proves lost-response root causality. Native
fastdds wrapper lacks shebang (direct execution Execformaterror); systemPython
entry above invokes the installed official implementation successfully.

Follow-up catches readiness interruption and returnsfailure even if ROS context
closes; regression ensures context-close cannot implysuccess. Current single-host
Gazebo/ROS/RViz commands explicitly setROS_LOCALHOST_ONLY=1, consistentRMW/domain.
Plans/physics/coverage/safety/task limits unchanged. Next pushed freeze uses new
IDs and domains for all five original engineering cases; its middleware/local
setting is recorded so it cannot be mixed with older failed environments.

Readiness-close candidate: build PASS3.25s; complete package checks73 tests, 0 errors/failures, 2 skips. Next source freeze predeclares same five engineering cases on single-host ROS_LOCALHOST_ONLY=1 / rmw_fastrtps_cpp after official zombie cleanup, with newIDs/domains and no source mutation during runs.


### Final same-source engineering regressions: c9344e1, five PASS

Pushed runtime freeze:c9344e10f4a0788f96fd70371c5ea033e0fc5268. Clean workingtree at
start, no source mutation throughout sequential runs. Exact commands, per-case
domain194–198/master11763–11767, local/RMW environment, timestamps, source and
returncodes are in report/assets/20261013_p1c_engineering_repair/c9344e1_commands.json.
Exact batch source is c9344e1_batch_driver.py. Invocation from canonical ROS root:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
source /usr/share/gazebo/setup.sh
export PYTHONNOUSERSITE=1 TURTLEBOT3_MODEL=waffle RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1
/usr/bin/python3 -u log/p1c_local_batch.py
```

All seed101; unique processes/domains/ports/runids. Four native JSONs are tracked,
all raw logs/CSV/JSON retained at indexed paths, SHA256 c9344e1_original_index.json.
Engineering credit is explicitly separated in c9344e1_engineering_summary.json.
- 4r20s motion: smoke0, expected native timeout20.2s (no full task completion),
  coverage.48208724229512584, accuracy.9387827569064697, zero contact/monitoringtrue,
  no control failure. Four true paths2.956/3.064/3.599/2.983m, total12.602431210m.
- 2r my_world180s task: native coverage_reached133.3s, coverage.9060511683894759,
  accuracy.9598378704912602, path48.227614458m; task/smoke0, zero contacts/monitors
  valid. Both moved. Exceeds historical120s speed, no old performance reacceptance.
- 3r rooms180s task: native coverage_reached60.2s, coverage.914064914992272,
  accuracy.9582618527760449, path32.732144185m; task/smoke0, zero/monitoringvalid.
- 3r corridors180s task: native coverage_reached81.9s, coverage.906342668863262,
  accuracy.9505184081455268, path43.592509059m; task/smoke0, zero/monitoringvalid.
- 4r plain5-wall-second dwell: smoke0, all four actual wheel states and six-node
  activation confirmed, clean manual SIGINT closure; no safety/task credit.

Native log audit confirms every owned child cleanly closed with no abort or
SIGTERM/SIGKILL escalation; no owned domain174–198 simulator/task process remained.
Four-robot short-run timeout is not coverage-success; all gates and failure originals
are preserved. Cleanup + local-only profile did not reproduce lost responses in
this batch; it is not a universal middleware reliability proof. Task accuracies
also remain below corresponding historical values, and full multi-seed matrix
has not been rerun. Engineering verification scope is fulfilled, roadmap pending.

Final component results73 checks/zeroerrors/zerofailures/twoskips remain from the
same runtime source. Closing changes affect only documentation/receipts; runtime
files unchanged fromc9344e1, both research/implementation plans byte-identical to
99cf3a6. Original-route backup branch8fe1495 stays untouched.

## 2026-10-14 MR3 route audit and documentation transition (no new experiment)

- User direction: exactly three robots; first centralized joint RL exploration
  with stable subgoals and local SLAM/Nav2/map fusion under ideal communication;
  then freeze policy and interface contracts, route actual uplink/downlink bytes
  through gateway/ns-3 Wi-Fi and measure network effects. No target search,
  charging, rally, other team-size study, communications optimizer or hardware roadmap.
- Code/read-only baseline: main@81b2f8b9c2a36f0a8c5278e04fae66dc06859180,
  runtime unchanged from c9344e10f4a0788f96fd70371c5ea033e0fc5268.
  Original-route backup p2c1/global-mission-20261012@8fe1495b6624cd9136f3ce160acaa274428e54ae
  remains untouched. No weights/config/source change, simulator or training run.
- Primary-paper/official-document research and source audit are centralized in
  report/20261014_mr3_route_audit.md. Decisions: goal-based joint MaskablePPO,
  same-action DQN comparison, optional SAC/TD3 continuous-goal method; reward
  tied to correct-free coverage/time/safety; explicit ROI/95% feasibility,
  reset/throughput, Nav2 shared-map/peer-state bypasses, serialized payload and
  simulation-clock causality gates.
- New checkpoint namespace MR3-P0…MR3-P5 supersedes old route instructions.
  This session delivers P0 documentation for user acceptance; no P1A work or
  retrospective acceptance of historical P1C/task results. Future substeps each
  require separate user acceptance after verified, committed/pushed delivery.
- Updated root/component memories, research and implementation plans, repository
  entry points, ROS guide/technical reference/three-robot commands, scoped legacy
  toy guide/models/runtime. Added report README and ARCHIVE_INDEX.json.
  All ten existing report bodies retain original hashes after scope banners;
  original assets unchanged. Superseded text is recoverable at the pre-route Git
  object; old failures are not removed or relabeled.
- Validation commands (static only, not simulator experiments):

```bash
rtk proxy python3 /tmp/mr3_document_check.py
rtk git diff --check
rtk git add -n .
```

- Static check script verifies local links/fences, shell syntax without execution,
  current launch/CLI arguments and explicit three-robot recommendation, MR3
  checkpoint completeness/status, pre-route Git/SHA256 archival records,
  unchanged report bodies/log chronology, and documentation-only change scope.
  Exact static checker source is preserved in the route-audit report appendix.
  Canonical validation receipt:
  report/assets/20261014_mr3_route_audit/document_checks.json.
- Scientific status: current traditional baseline still has only the already
  logged c9344e1 three-robot rooms/corridors seed101 90% engineering results.
  No 95% task, navigation RL, gateway or ns-3 mission credit added this session.
  Later optimization/deployment awaits a separate user direction.

## 2026-10-14 MR3 correction review (static only, no new experiment)

- User request: assess current project and route; correct real gaps without
  inventing changes. Review base main@57edcb6, runtime remains c9344e1.
- Retained the three-robot centralized subgoal RL then frozen-policy Wi-Fi route.
  Corrected three evidence/contract gaps: existing zero-contact records cover
  only base_collision; formal-test-driven repairs require exposed-set demotion
  and fresh held-out confirmation for independent generalization; P4B final
  clock must be shared by every P5 branch and revalidate ideal equivalence.
- XML parsing confirms six physical collision bodies and one contact sensor
  watching base_collision. This is source evidence, not a collision experiment.
  Whole-body non-support coverage and normal support exclusions are P1A gates.
  Historical zero-contact wording retains the narrower sensor meaning; no
  native result, report body or prior receipt was rewritten.
- Updated research/implementation contracts, current ROS evidence wording,
  root memory, report index and clarification record. Details and limitations:
  report/20261014_mr3_correction_review.md.
- Static validation: `rtk proxy python3 /tmp/mr3_correction_check.py`,
  `rtk git diff --check`, and `rtk git add -n .`. Checker source and receipt:
  report/assets/20261014_mr3_correction_review/correction_checks.json.
- No runtime/config/weights or launch commands changed; no simulator, smoke,
  training or evaluation run. MR3-P0 still awaits user acceptance; no later
  substep started and no new task/safety/network performance credit claimed.

## 2026-10-14 MR3-P1A authorization, implementation and native predeclaration

- User explicitly accepted P0 after the correction review and authorized P1A.
  Only P1A is active; no P1B/RL/training/gateway work begins this session.
- Three-robot active defaults; strict hash-bound full outer-wall ROI/schema4;
  .131m SDF ray height and matching active URDF; .05m positive-area box truth;
  95%/300sim-second deadline; accuracy>=.95, occupied IoU>=.20, false-free/all
  truth occupied<=.02; each true task path>=1m and >=1goal. These are declared
  before any new simulation, not selected after MR3 failures. Old schema3 stays
  separate. my_world SUV mesh is explicitly unsupported for this strict task.
- Six real contact components per robot, exact normal support-pair filtering,
  .5sim-second source/receipt age and gap latching; shared controller release,
  stop new goals, cancel accepted or late-accepted ownership, await terminal
  closure within10sim seconds and before task deadline. Truth remains isolated
  from exploration/candidates/safety.
- Static geometry: three development layouts connected/spawn safe, ideal
  continuous-laser visibility lower bound1.0 (not native task success). Nine
  validation/test/confirmation layouts generated/hash-frozen, static checked
  only, zero policy/simulator runs. Split/training-budget method in protocol.json.
- Verification: canonical system ROS Python/build succeeded. First direct
  pytest omitted overlay and failed import; after sourcing install a legacy
  fake lacked new task_contract field, and initial integrated lint failed.
  Old test fixture and lint corrected; second integrated check preceded all
  delegated style edits, remaining lint repaired. Final colcon test:182checks,
  0errors/0failures/2skips (180passes), no simulation. Exact JUnit/receipts in
  report/assets/20261014_mr3_p1a/.

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select multi_robot multi_robot_exploration
/usr/bin/python3 /usr/bin/colcon test --packages-select multi_robot_exploration merge_map --event-handlers console_cohesion+
/usr/bin/python3 scripts/audit_mr3_geometry.py --output /tmp/mr3_p1a_geometry_initial.json
/usr/bin/python3 scripts/generate_mr3_worlds.py --check
```

- Native predeclaration: predeclared_native_plan.json, generated before running.
  First isolated3robot contact fixture (all18sources, ground support, six
  intentional component contacts, settled ray height), then same-source
  development task matrix rooms/corridors/open x101/202/303. Every run is
  independent and has a uniqueid/output; all failures/interruptions retained.
  Start only after candidate commit/push; record exact freeze at invocation.
  No final/native PASS is claimed at predeclaration.

### MR3-P1A native contact fixture attempt mr3_p1a_contact_v1_20261014_111702

- Freeze: 48f78d0ba7dfec424c8c3890333aa3e70c632433; committed/pushed candidate. Fixed three robots; isolated diagnostic, intentional contacts are not navigation safety evidence.
- Environment: system ROS Humble, PYTHONNOUSERSITE=1, rmw_fastrtps_cpp, ROS_LOCALHOST_ONLY=1.
- Command (canonical ROS root):

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/mr3_contact_native_fixture.py --output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_v1_20261014_111702 --ros-domain-id 210 --gazebo-port 11810
```

- Result pending at invocation; all outputs: /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_v1_20261014_111702.

- Finished 2026-10-14T11:20:55.343810+00:00; rc=1, success=False, error=lift tb1 rejected: . Original /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_v1_20261014_111702/fixture_result.json retained; no task/RL/network credit.

- Diagnosis of first fixture failure: GetEntityState response carries pose but not target name; copied EntityState had empty name and SetEntityState rejected it. Fixed diagnostic request.name/reference_frame explicitly. No production/controller/geometry/threshold change. Original v1 result/log/source selected into canonical P1A assets; retry predeclared with new ID mr3_p1a_contact_v2_20261014_112351, domain214/port11814 after new commit/push.

### MR3-P1A native contact fixture retry mr3_p1a_contact_v2_20261014_112351

- Freeze: bd62c7faad60d3bd51c179dcdff2aeb72e7ea8d0; production runtime unchanged from48f78d0. Diagnostic fixes: explicit EntityState name/world frame; newly received post-lift support samples; final latching/child-exit gates. Same model/world/.5s monitoring; original failure retained.
- Environment: system ROS Humble, PYTHONNOUSERSITE=1, rmw_fastrtps_cpp, ROS_LOCALHOST_ONLY=1.
- Command (canonical ROS root):

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/mr3_contact_native_fixture.py --output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_v2_20261014_112351 --ros-domain-id 214 --gazebo-port 11814
```

- Result pending at invocation; all outputs: /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_v2_20261014_112351.

- Finished 2026-10-14T11:29:16.228132+00:00; rc=1, success=False, error=continuous contact freshness failed in steady fixture phase. Original /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_v2_20261014_112351/fixture_result.json retained; no task/RL/network credit.

- V2 retained as fixture_v2_failure_{result.json,launch.txt,source.py}. All18 sources advanced at ~.05s but source age rose to .48–.53s at steady endpoint (10 stale). No duplicate/invalid timestamps, all post-lift ground pairs were new; shutdown clean. Consumption backlog is a hypothesis, not a proven producer root cause. Minimal persistent executor and redundant fixture classification fix predeclared as mr3_p1a_contact_v3_20261014_114354 before retry; all thresholds/rates/physics unchanged.

- Executor repair checks (system ROS overlay): contact/evaluator targeted pytest30passed; colcon multi_robot_exploration169passed/1skipped, no failures; exact commands: /usr/bin/python3 -m pytest src/multi_robot_exploration/test/test_mr3_contacts.py src/multi_robot_exploration/test/test_mr3_evaluator.py -q; /usr/bin/python3 /usr/bin/colcon test --packages-select multi_robot_exploration --event-handlers console_cohesion+. New JUnit executor_repair_tests.xml; fixture py_compile and git diff --check passed. No new simulator/native PASS yet.

### MR3-P1A native contact fixture retry mr3_p1a_contact_v3_20261014_114354

- Freeze: f6b73d15ce2ac30678090e157858a37306b74968 (committed/pushed); isolated3robot diagnostic; same20Hz/.5s/physics/contact history.
- Environment: system ROS Humble, PYTHONNOUSERSITE=1, rmw_fastrtps_cpp, ROS_LOCALHOST_ONLY=1.
- Command (canonical ROS root):

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/mr3_contact_native_fixture.py --output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_v3_20261014_114354 --ros-domain-id 215 --gazebo-port 11815
```

- All output retained: /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_v3_20261014_114354; result pending at invocation.

- Finished 2026-10-14T11:45:00.556032+00:00; rc=1, success=False, error=continuous contact freshness failed in steady fixture phase. Original JSON/log retained; no task/RL/network credit.

- V3 native failure retained as fixture_v3_failure_{result.json,launch.txt,source.py}; persistent executor/reduced diagnostic classification did not restore freshness. For steady2simsec, wall2.588/fixtureCPU2.637 sec; callbacks .135/drain .121 sec across1332messages, final ages .776–.788 across18. Strong CPU-backpressure evidence; decode not yet proven. Diagnostic profile predeclared mr3_p1a_contact_profile_v4_20261014_114629; profile overhead has no performance credit.

- Evaluator shutdown repair: retain nonzero finalization errors while nested finally closes executor within1wallsecond, node and context; handles external shutdown. Targeted task_evaluator+flake8 checks passed (18tests). Diagnostic profile wrapper initially refused to launch because lifecycle edits raced its clean-source check; no simulator/artifact started. Same predeclared profile ID remains unused; invoke after new pushed freeze.

### MR3-P1A native attempt mr3_p1a_contact_profile_v4_20261014_114629

- Freeze: ac6ba585104c177c53be071f6850a6f1fd30f59b committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; rmw_fastrtps_cpp; ROS_LOCALHOST_ONLY=1; ROS_DOMAIN_ID=216; GAZEBO_MASTER_URI=http://127.0.0.1:11816.
- Command (canonical ROS root):

```bash
/usr/bin/python3 -m cProfile -o /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_profile_v4_20261014_114629/profile.stats /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/mr3_contact_native_fixture.py --output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_profile_v4_20261014_114629 --ros-domain-id 216 --gazebo-port 11816
```

- Result pending at invocation; all native output retained.

- Correction to previous lifecycle check entry: root launched test_flake8.py from entire ROS workspace rather than package directory; its argv=[] therefore scanned unrelated upstream/build/log trees and failed style scope (17 functional tests passed,1 lint-scope failure). Agent scoped two-file lint and3 lifecycle regressions passed before freeze; root now reruns the18checks from package directory. This is not a simulator failure and does not justify editing unrelated code.

- Finished 2026-10-14T11:51:20.738569+00:00; rc=0; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_profile_v4_20261014_114629/fixture_result.json; success=False; error=contact sources not fresh after settling. All native JSON/log/failures retained.

- Scoped lifecycle/flake8 recheck from multi_robot_exploration package directory:18 passed/0failed (2.26s). V4 cProfile shows39.021s overall and _take_subscription30.840s (79.03%),1148280Vector3/261253Wrench/69878ContactState constructors; raw profile and cumulative/tottime outputs retained. cProfile process returned0 although fixture_result.success=false (not fresh after settling); JSON failure remains authoritative, no PASS. Native reducer + compact fixture predeclared mr3_p1a_contact_compact_v5_20261014_115529 without altering20Hz/.5s/full pair history.

- Compact integration checks from multi_robot_exploration package:86 functional tests passed (contacts/evaluator/task lifecycle/launch-and-smoke),1 lint failure at new100char metadata string; shortened metadata and targeted package lint then1passed. Fixture py_compile/diff-check clean. Complete geometry sample for first non-support pair now retained; compact native summary requires all18sources, one publisher, received=published, supported publication sequence with zero gaps/duplicates/regressions/unavailable. Settled ray height must agree nominal.131within2mm. No simulator gate relaxation.

- Native reducer build/checks: canonical system ROS /usr/bin/python3 /usr/bin/colcon build --packages-select multi_robot --symlink-install passed (34.7wallsec), installed executable confirmed by ros2 pkg executables multi_robot. Independent CMake/gtests5passed/0failed; native_reducer_checks.xml retained. ament_cpplint/uncrustify own3C++files passed; diff-check clean. First isolated colcon with /tmp install refused unresolved runtime dependencies (no simulator); independent CMake and canonical colcon then passed. Independent compact integration review found no relaxed task/monitoring gate or truth leakage. v5 starts only after this new committed/pushed freeze;3world batches then run in parallel80CPU host, isolated domains/ports, each3seed serial restart, all9same freeze.
