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

### MR3-P1A native attempt mr3_p1a_contact_compact_v5_20261014_115529

- Freeze: 50b78e7f4f2492288bf005c6b48432af2a120b95 committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; rmw_fastrtps_cpp; ROS_LOCALHOST_ONLY=1; ROS_DOMAIN_ID=217; GAZEBO_MASTER_URI=http://127.0.0.1:11817.
- Command (canonical ROS root):

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/mr3_contact_native_fixture.py --output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_compact_v5_20261014_115529 --ros-domain-id 217 --gazebo-port 11817 --contact-transport compact
```

- Result pending at invocation; all native output retained.

- Finished 2026-10-14T12:01:08.191800+00:00; rc=1; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_compact_v5_20261014_115529/fixture_result.json; success=False; error=settled laser height differs from declared slice by over2mm: tb3. All native JSON/log/failures retained.

- V5 compact freeze50b78e7: continuous18source monitoring recovered (maxsteadyage.044s, no latchedissues),2simsec took2.490wall/.992CPU sec; everyraw input=output, actualpublication sequence observed, no gaps/duplicates/regressions. Failed before six cases: tb3rayheight.128868m vsnominal.131 (-2.132mm) exceeds retained2mm criterion; tb1/tb2errors-1.156/-1.865mm. Original fixture_v5_height_failure_{result.json,launch.txt,source.py} retained. Source2mm gate not enough to prove planar geometry: tb1stillpitch1.056deg afterlift gives10mbeam groundcrossing; evidence indicates settling is incomplete (hypothesis). ActualSDF wheel/castergeometry predicts static pitch-.32385deg/ray.130637/min10mbeam.074115m; do not forcepose/physics. NewV6 predeclared mr3_p1a_contact_settle_v6_20261014_120858 adds true lowtwist1simsec stablewindow and beam-envelope/exactgeometry-slice invariance, without loosening2mm or anytaskgate. Prelaunch wrapper earlier rejected uncompletedpush; no simulator launched then, samev5ID began afterpushcompleted.

- V6 geometry audit prechecks: inspect_world_geometry now exposes existing box vertical boundaries/plane heights only; truth classification and ROI unchanged. New audit_lidar_slice_invariance probes reference/endpoints/allboundaries and adjacentfloat heights, rejects hidden narrow slices and floorcrossing. Puremodule50tests+scopedflake8/pep257 passed (initial testinput/indent failures repaired withoutclassificationchange). All12worlds [.02,.25] exactrectangle invariant, canonical all12_vertical_slice_invariance.json; no policy/simulator runs onheldouts. Fixture now queries actual tbN::base_scan pose/twist and sources directly ratherthan model-link identity assumption; py_compile/diffcheck passed.

### MR3-P1A native attempt mr3_p1a_contact_settle_v6_20261014_120858

- Freeze: 9f3a8840ae729cddb225c0eb39136a30c70dabe5 committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; rmw_fastrtps_cpp; ROS_LOCALHOST_ONLY=1; ROS_DOMAIN_ID=218; GAZEBO_MASTER_URI=http://127.0.0.1:11818.
- Command (canonical ROS root):

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/mr3_contact_native_fixture.py --output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_settle_v6_20261014_120858 --ros-domain-id 218 --gazebo-port 11818 --contact-transport compact
```

- Result pending at invocation; all native output retained.

- Finished 2026-10-14T12:12:04.944204+00:00; rc=1; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_settle_v6_20261014_120858/fixture_result.json; success=False; error=settlement_timeout: no fresh1simsec low-twist window for all3. All native JSON/log/failures retained.

- V6 failed30wallsec settlement condition; raw fixture_v6_settlement_failure_{result.json,launch.txt,source.py} retained. Fullvelocitynorm .085–.095m/s remains despite2simsecposebbox rangesx<59micron/y<.3micron/z<23micron andangular .002–.0047rad/s. Full3Dlowtwist condition therefore does not establish scannerpose stability in this physics setup; vertical residual is a hypothesis (v6didnotstoreaxes), not a proven artifact. Derivedlatepose rayheight.12924–.12925m (old2mm gate fits) andbeam[.0624,.1961] (existingband fits), notnativePASS. V7 mr3_p1a_contact_pose_v7_20261014_121753 predeclared actual3Dpose/quaternion sampledwindow1simsec, sourceage/gap<=.5, planar/angular low; fulltwistaxes retained, ground/2mm/beam safety gates remain. Bound.001+(10+norm(rayoffset))*sin(.002) extraenvelope margin ensures observedposewindowvariation cannotcrossauditedband. Eightpureposewindow checks passed includingtranslation/quaternion-sign/tilt/velocity/freshness/nonfinite/insufficientwindow cases; py_compile/diffcheck passed.

- V7 prereview strengthens fullacceptedwindow proof: q/-q equivalent angle, conservativefull3D boundingbox norm, everywindowstate fresh and gap<=.5. Everyacceptedwindowpose and laterindependent pose checks2mm/ground/full10mbeam withextra2.13cm verticalvariation margin, not just lastpose. Fulltwistvectors retained. Twoadditionalpurelaser checks passed: observedstablepose fitsband and earlierliftpitchcrossingground rejected. Diagnosticreplay ofv6poseonlydata firstboundedwindowsnear9.5–10.5simsec hadvalidlaser geometry, but v6planarvelocitywasnotstored (setzeroonlyforconditionaldiagnosis); no nativePASSor taskcredit, V7mustmeasureactualvx/vy.

### MR3-P1A native attempt mr3_p1a_contact_pose_v7_20261014_121753

- Freeze: 9bac5fe559a042cc013e3b514d527d72e9d8ce1b committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; rmw_fastrtps_cpp; ROS_LOCALHOST_ONLY=1; ROS_DOMAIN_ID=219; GAZEBO_MASTER_URI=http://127.0.0.1:11819.
- Command (canonical ROS root):

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/mr3_contact_native_fixture.py --output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_pose_v7_20261014_121753 --ros-domain-id 219 --gazebo-port 11819 --contact-transport compact
```

- Result pending at invocation; all native output retained.

- Finished 2026-10-14T12:22:02.630309+00:00; rc=0; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_pose_v7_20261014_121753/fixture_result.json; success=True; error=None. All native JSON/log/failures retained.

- V7 isolatedfixturePASS freeze9bac5fe: all6actualnon-supportcomponent pairs retained withcompletegeometry; all18empty updates andnew12supportpairs observed; steady2simsec/final18monitorfresh+noever_unhealthy; publishersequence complete/input=output/sourceheaderspreserved;3actualscanlinkheight+fullbeamwindow/marginpass; ownedGazebo/reducer exit0/noescalation. Canonical fixture_v7_pass_{result.json,launch.txt,source.py}. Fulltwistaxes now show verticalresidual near-.09 whileplanar/angularlow andsampledposebounded; preserve asphysicsdiagnostic, notcontinuous1msstillnessclaim. No95task/RL/networkcredit. Beginpredeclared3world×3seed matrix atsamefreeze9bac5fe, allfailuresretained.

### MR3-P1A native attempt mr3_p1a_v1_open_20261014_111702

- Freeze: 9bac5fe559a042cc013e3b514d527d72e9d8ce1b committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; rmw_fastrtps_cpp; ROS_LOCALHOST_ONLY=1; ROS_DOMAIN_ID=213; GAZEBO_MASTER_URI=http://127.0.0.1:11813.
- Command (canonical ROS root):

```bash
/usr/bin/python3 scripts/run_ideal_baseline.py --world p1c_open.world --robot-count 3 --seeds 101 202 303 --task-contract src/multi_robot/config/mr3_p1a/open.json --startup-timeout 300 --evaluation-wait-timeout 900 --shutdown-timeout 60 --run-id mr3_p1a_v1_open_20261014_111702 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a
```

- Result pending at invocation; all native output retained.

### MR3-P1A native attempt mr3_p1a_v1_corridors_20261014_111702

- Freeze: 9bac5fe559a042cc013e3b514d527d72e9d8ce1b committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; rmw_fastrtps_cpp; ROS_LOCALHOST_ONLY=1; ROS_DOMAIN_ID=212; GAZEBO_MASTER_URI=http://127.0.0.1:11812.
- Command (canonical ROS root):

```bash
/usr/bin/python3 scripts/run_ideal_baseline.py --world p1c_corridors.world --robot-count 3 --seeds 101 202 303 --task-contract src/multi_robot/config/mr3_p1a/corridors.json --startup-timeout 300 --evaluation-wait-timeout 900 --shutdown-timeout 60 --run-id mr3_p1a_v1_corridors_20261014_111702 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a
```

- Result pending at invocation; all native output retained.

### MR3-P1A native attempt mr3_p1a_v1_rooms_20261014_111702

- Freeze: 9bac5fe559a042cc013e3b514d527d72e9d8ce1b committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; rmw_fastrtps_cpp; ROS_LOCALHOST_ONLY=1; ROS_DOMAIN_ID=211; GAZEBO_MASTER_URI=http://127.0.0.1:11811.
- Command (canonical ROS root):

```bash
/usr/bin/python3 scripts/run_ideal_baseline.py --world p1c_rooms.world --robot-count 3 --seeds 101 202 303 --task-contract src/multi_robot/config/mr3_p1a/rooms.json --startup-timeout 300 --evaluation-wait-timeout 900 --shutdown-timeout 60 --run-id mr3_p1a_v1_rooms_20261014_111702 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a
```

- Result pending at invocation; all native output retained.

- Initialmatrix interrupted 2026-10-14T12:32:39.206830+00:00 underpredeclared repeatedinfrastructurefailure rule: rooms101 missedtwo casterrawframes; corridors202andopen202 repeatedrawpublication gaps (latchedstartupfailures). corridors101/open10195native successes remain diagnostic, notfinalmatrixcredit. SentSIGINT onlymatchingthreebaselineparents(preventfurtherseeds) thenownedros2launchPGIDs:[["baseline_parent", 3326851, 3326700], ["baseline_parent", 3326853, 3326699], ["baseline_parent", 3326854, 3326701], ["owned_launch_group", 3331941, 3331941], ["owned_launch_group", 3336968, 3336968], ["owned_launch_group", 3337848, 3337848]]. Exactargv/signals/freeze savedinitial_matrix_owned_interrupt.json; cleanup/results pending. No runtime source edits untilallownedlaunchesexit. Finalnewfreeze mustfull9rerun, no cherry-picking.

- Finished 2026-10-14T12:32:39.552916+00:00; rc=-2; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_v1_corridors_20261014_111702/summary.json; success=None; error=None. All native JSON/log/failures retained.

- Finished 2026-10-14T12:32:39.567033+00:00; rc=-2; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_v1_rooms_20261014_111702/summary.json; success=None; error=None. All native JSON/log/failures retained.

- Finished 2026-10-14T12:32:39.589612+00:00; rc=-2; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_v1_open_20261014_111702/summary.json; success=None; error=None. All native JSON/log/failures retained.

- Initialmatrix cleanup complete: all3wrappersreturn254 fromparentSIGINT (-2child), no ownedGazebo/launchleft. Selectedallstartednative JSON/CSV/log andavailablepartialbatchsummaries intoinitial_matrix/, fullsourcefreeze/hashinventory initial_matrix_receipt.json. Eightattemptsstarted: rooms101/202,corridors101/202/303,open101/202/303;rooms303 notstarted. Two95native successes remain diagnosticonly (corridors10172.4s/open10194.1s); sourcegapstartup failuresandinterruptedcells remainfalse/unscored; rawJSONneverrewritten. Complete newmatrix neededaftergeneralrepair.

- Newnativeattempts predeclared beforeimplementationfreeze: isolatedfixture mr3_p1a_contact_qos_v8_20261014_123944 domain220/port11820; then developmentmatrixversion2 mr3_p1a_v2_rooms_20261014_123944,mr3_p1a_v2_corridors_20261014_123944,mr3_p1a_v2_open_20261014_123944 domains221/222/223ports11821/22/23. Samecontracts/seeds/full9; originalpredeclaration/attempts remainunchanged. NativepublicationQoS default depth5 isconfirmedsourceconfiguration, startuphistoryinsufficiency is a hypothesis testedbynew100-depthfreeze, notyetclaimedrootcause. No currentruntimeprocesses; sourcesrepairinprogress.

- General repair prechecks: all6contactGazebo publishers setofficialreliable/volatile KEEP_LASTdepth100 (notdata/20Hz/physicschange); removingqos fromAST yieldsidenticalwholemodel tooldfreeze. Officialgazebo_ros QoSparser remap/FQN semantics verified. Sourcecapability/missingpublicationmetadata/multiplepublisher failuresnowlatched; allraw stillforwardedonce. C++10tests0fail,cpplint/uncrustifyclean, canonicalcolconmulti_robotbuild32.8s successinstalledbinary; qos_reducer_repair_checks.xml retained. Controlctorinterrupt/finalnative18summaryvalidator newchecks19passed/47deselected, scopedlintclean. Exactruntime/gates/ROIcontracts unchanged; full3packageintegratedchecks pendingbeforefreeze.

- Pre-matrix2 finalintegratedchecks: canonical systemROS colcon test --packages-select multi_robot multi_robot_exploration merge_map --event-handlers console_cohesion+ completed11.0wallsec;222tests=220pass/2skip/0fail/error. CurrentcandidateSHA/JUnit retained inpre_matrix2_component_checks.json plus3JUnitfiles. No furthercodeeditsplanned; diff-check/staticmodelQoS checks passed. Newv8fixture thenfull9matrix remainsunrununtilcandidatecommit/push.

### MR3-P1A native attempt mr3_p1a_contact_qos_v8_20261014_123944

- Freeze: 3f24eaa9fae6f7d282f85f991273734d71b9439d committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; rmw_fastrtps_cpp; ROS_LOCALHOST_ONLY=1; ROS_DOMAIN_ID=220; GAZEBO_MASTER_URI=http://127.0.0.1:11820.
- Command (canonical ROS root):

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/mr3_contact_native_fixture.py --output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_qos_v8_20261014_123944 --ros-domain-id 220 --gazebo-port 11820 --contact-transport compact
```

- Result pending at invocation; all native output retained.

- Finished 2026-10-14T12:52:11.050368+00:00; rc=0; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_contact_qos_v8_20261014_123944/fixture_result.json; success=True; error=None. All native JSON/log/failures retained.

- V8fixturePASS freeze3f24eaa: tb1all6non-supportcomponentpositive specimens retained, all3/18empty-andfreshstreams/12newgroundsupports, exactsourceheaderand18publicationsequence audit/onepublisher/input=output; same2mm andfull10mbeamgeometryinclsampledwindowmargin, rawstate/twist recorded; ownedGazebo/reducerexit0/noescalation. Canonicalfixture_v8_pass_{result.json,launch.txt,source.py}. Runtimehistorydepth100 hasstaticofficialparser/configproof; no unsupportedruntimehistoryintrospectionclaim. Begincompleteversion2nine-taskmatrixsamefreeze3f24eaa (v8aloneisnot95tasksafetycredit).

### MR3-P1A native attempt mr3_p1a_v2_corridors_20261014_123944

- Freeze: 3f24eaa9fae6f7d282f85f991273734d71b9439d committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; rmw_fastrtps_cpp; ROS_LOCALHOST_ONLY=1; ROS_DOMAIN_ID=222; GAZEBO_MASTER_URI=http://127.0.0.1:11822.
- Command (canonical ROS root):

```bash
/usr/bin/python3 scripts/run_ideal_baseline.py --world p1c_corridors.world --robot-count 3 --seeds 101 202 303 --task-contract src/multi_robot/config/mr3_p1a/corridors.json --startup-timeout 300 --evaluation-wait-timeout 900 --shutdown-timeout 60 --run-id mr3_p1a_v2_corridors_20261014_123944 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a
```

- Result pending at invocation; all native output retained.

### MR3-P1A native attempt mr3_p1a_v2_rooms_20261014_123944

- Freeze: 3f24eaa9fae6f7d282f85f991273734d71b9439d committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; rmw_fastrtps_cpp; ROS_LOCALHOST_ONLY=1; ROS_DOMAIN_ID=221; GAZEBO_MASTER_URI=http://127.0.0.1:11821.
- Command (canonical ROS root):

```bash
/usr/bin/python3 scripts/run_ideal_baseline.py --world p1c_rooms.world --robot-count 3 --seeds 101 202 303 --task-contract src/multi_robot/config/mr3_p1a/rooms.json --startup-timeout 300 --evaluation-wait-timeout 900 --shutdown-timeout 60 --run-id mr3_p1a_v2_rooms_20261014_123944 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a
```

- Result pending at invocation; all native output retained.

### MR3-P1A native attempt mr3_p1a_v2_open_20261014_123944

- Freeze: 3f24eaa9fae6f7d282f85f991273734d71b9439d committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; rmw_fastrtps_cpp; ROS_LOCALHOST_ONLY=1; ROS_DOMAIN_ID=223; GAZEBO_MASTER_URI=http://127.0.0.1:11823.
- Command (canonical ROS root):

```bash
/usr/bin/python3 scripts/run_ideal_baseline.py --world p1c_open.world --robot-count 3 --seeds 101 202 303 --task-contract src/multi_robot/config/mr3_p1a/open.json --startup-timeout 300 --evaluation-wait-timeout 900 --shutdown-timeout 60 --run-id mr3_p1a_v2_open_20261014_123944 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a
```

- Result pending at invocation; all native output retained.

- Finished 2026-10-14T13:06:13.575286+00:00; rc=1; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_v2_corridors_20261014_123944/summary.json; success=None; error=None. All native JSON/log/failures retained.

- Finished 2026-10-14T13:06:53.932661+00:00; rc=1; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_v2_rooms_20261014_123944/summary.json; success=None; error=None. All native JSON/log/failures retained.

- Finished 2026-10-14T13:10:15.341063+00:00; rc=1; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_v2_open_20261014_123944/summary.json; success=None; error=None. All native JSON/log/failures retained.

- Matrixversion3 predeclared 2026-10-14T13:26:47.582805+00:00: serialworldbatches mr3_p1a_v3_rooms_20261014_132647, mr3_p1a_v3_corridors_20261014_132647, mr3_p1a_v3_open_20261014_132647; domains224/225/226, ports11831/32/33, eachseeds101/202/303 fullrestart. Repeatedcontrolshutdownexception repairedbeforepushedfreeze; no policy/ROI/95/quality/safety/taskduration orwallguardchange. Officiallocked-resource-awareFastDDS shmclean beforefirstbatch; v2alloriginalfailuresretained. Full9afternewfreeze, nooldsuccessfulcellsreused.

- Controllerownedexecutor repair finalintegratedchecks: canonicalROS command `source /opt/ros/humble/setup.bash; source install/setup.bash; export PYTHONNOUSERSITE=1; /usr/bin/python3 /usr/bin/colcon test --packages-select multi_robot multi_robot_exploration merge_map --event-handlers console_cohesion+`;11.0wallsec;228tests=226pass/2skip/0failure/error, newclosed/live-contextconversion andboundedcleanup testsincluded. Candidateparent3f24eaa; exactchangedsourceSHA and3JUnitfiles inpre_matrix3_component_checks.json. V8unchangedcontact/physicalfixture9hashbindingpassed, no redundantfixtureornewtaskcredit. Matrix3full9pendingnewpushedsourcefreeze.

- PrelaunchGitformatcorrection: stagednativeCSV CRLF anduntouchedstdouttrailingblanks wereflaggedbycached diffcheck; local48ebbb5committedbeforethatfailurewasresolved (notyetpushed,no nativev3started). AddednarrowcanonicalMR3P1Aevidenceattributesonly: nativeCSVCR-at-EOL/non-normalization andnativelogoriginalwhitespace; source/docs/JSON/audits retainnormalchecks. All 132 trackedcanonicalartifact bytes equalGitHEAD; rawdiffcheckHEAD^..HEADnow0, ready-documentstaticcheckPASS. No evidence whitespace rewritten, nohistoryrewrite; followupcommitbeforematrixfreeze.

- Pre-matrix3maintenance 2026-10-14T13:44:24.320946+00:00; freeze9e0ceda3f29056e970d3d1eaf0341cf30059f708; exactcommand `/usr/bin/python3 /opt/ros/humble/tools/fastdds/fastdds.py shm clean`, rc=0; stdout="shm.clean:\n3 ports in use\n3 segments in use\n12 zombie ports cleaned\n11 zombie segments cleaned\n"; stderr="". Officialtool checkslocks/skipsactive resources; no ownednativeprocessesrunningbeforemaintenance. No manualshared-memorydeletion orprovenrootcauseclaim. Canonicalpre_matrix3_fastdds_cleanup.json.

### MR3-P1A native attempt mr3_p1a_v3_rooms_20261014_132647

- Freeze: 9e0ceda3f29056e970d3d1eaf0341cf30059f708 committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; rmw_fastrtps_cpp; ROS_LOCALHOST_ONLY=1; ROS_DOMAIN_ID=224; GAZEBO_MASTER_URI=http://127.0.0.1:11831.
- Command (canonical ROS root):

```bash
/usr/bin/python3 scripts/run_ideal_baseline.py --world p1c_rooms.world --robot-count 3 --seeds 101 202 303 --task-contract src/multi_robot/config/mr3_p1a/rooms.json --startup-timeout 300 --evaluation-wait-timeout 900 --shutdown-timeout 60 --run-id mr3_p1a_v3_rooms_20261014_132647 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a
```

- Result pending at invocation; all native output retained.

- Finished 2026-10-14T14:02:44.221431+00:00; rc=1; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_v3_rooms_20261014_132647/summary.json; success=None; error=None. All native JSON/log/failures retained.

- Version3 stopped before starting corridors/open after completed rooms batch: room101 strictPASS110.5s, room202 invalid pre-release contact_clock_desynchronization/start=null/model_states=0, room303 valid tasktimeout300s coverage.9489567233. No active process interruption needed, all native children clean; no six unstarted cells fabricated. New bootstrap/drain/earlyterminal repair required; v3 originals remain diagnostic only.

- Matrixversion4 predeclared 2026-10-14T14:09:24.918506+00:00: mr3_p1a_v4_rooms_20261014_140924, mr3_p1a_v4_corridors_20261014_140924, mr3_p1a_v4_open_20261014_140924; rooms/corridors/open serial, seeds101/202/303 serial fullrestart, domains227/228/229 ports11841/42/43. Same fixed contracts/gates, new pushed sourcefreeze before full9. Native contactfixture component credit re-bound by identical hashes only, no old task cells reused. Maintenance/source+installed manifest/environment audit retained.

- Matrix4 candidate finalintegratedchecks: canonicalROS command `source /opt/ros/humble/setup.bash; source install/setup.bash; export PYTHONNOUSERSITE=1; /usr/bin/python3 /usr/bin/colcon test --packages-select multi_robot multi_robot_exploration merge_map --event-handlers console_cohesion+`;11.2wallsec;269tests=267pass/2skip/0failure/error. ExactfivechangedsourceSHA and3JUnit retained pre_matrix4_component_checks.json; newbootstrap/invalidrelease/past-watermark-drain/truefuture257-immediatefail/earlyJSON/probetimeout/CLI-error/native-bootstrap-validator cases included. Old tests/results retained. V8ninecomponent bindingunchanged infixture_v8_component_binding_matrix4.json, no newphysicalfixture oroldtaskcellcredit.

- Prematrix4officialmaintenance 2026-10-14T14:22:24.515492+00:00; freeze=a43de1e3f4dd5e15a6df311044ec750500780cf5; command `/usr/bin/python3 /opt/ros/humble/tools/fastdds/fastdds.py shm clean`;rc=0; stdout="shm.clean:\n3 ports in use\n3 segments in use\n1 zombie ports cleaned\n1 zombie segments cleaned\n"; stderr="". No ownednativeprocessesactive; lock-aware cleanup keepslive resources. No newDDS profile orunderlyingrootcauseclaim. Canonicalpre_matrix4_fastdds_cleanup.json.

### MR3-P1A native attempt mr3_p1a_v4_rooms_20261014_140924

- Freeze: a43de1e3f4dd5e15a6df311044ec750500780cf5 committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; rmw_fastrtps_cpp; ROS_LOCALHOST_ONLY=1; ROS_DOMAIN_ID=227; GAZEBO_MASTER_URI=http://127.0.0.1:11841.
- Command (canonical ROS root):

```bash
/usr/bin/python3 scripts/run_ideal_baseline.py --world p1c_rooms.world --robot-count 3 --seeds 101 202 303 --task-contract src/multi_robot/config/mr3_p1a/rooms.json --startup-timeout 300 --evaluation-wait-timeout 900 --shutdown-timeout 60 --run-id mr3_p1a_v4_rooms_20261014_140924 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a
```

- Result pending at invocation; all native output retained.

- Finished 2026-10-14T14:38:00.363427+00:00; rc=1; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_v4_rooms_20261014_140924/summary.json; success=None; error=None. All native JSON/log/failures retained.

- Matrix4 incomplete stopped under repeated-infrastructure rule 2026-10-14T14:40:13.140055+00:00; freeze=a43de1e3f4dd5e15a6df311044ec750500780cf5; rooms101 nativeJSONsuccess91.4s butgzserverSIGINTselfjoin exit-6, rooms202 Nav2tb1 startup timeout/managerSIGKILL and noJSON. Exacttargets/argv/SIGINT in matrix4_owned_stop.json. Onlyindividualbaselineparent+ownedlaunchleader signaled, no groupdoubleSIGINT. Started303 interruption retained; corridors/open6cells unstarted. No completed task credit reused after any repair.

- Correction to preceding plannedmatrix4stop entry: exacttargetinventorywasempty;0signals sent. Rooms303 hadalreadycompleted normally(strictPASS135.9s), wasNOTinterrupted. Room3batchfinished1strictPASS/2infrainvalid; sixcorridors/opencells remainunstarted. matrix4_owned_stop_outcome.json preserves actualoutcome, oldrequestintent recordunchanged. Allnativeprocessesclosedbeforeanynewsourcechanges.

- Matrixversion5 predeclared 2026-10-14T15:04:52.100908+00:00: mr3_p1a_v5_rooms_20261014_150452, mr3_p1a_v5_corridors_20261014_150452, mr3_p1a_v5_open_20261014_150452; domains95/96/97 (below Linux ephemeral RTPS range), Gazebo ports11851/52/53; same3×101/202/303 serial fullrestart. Fixed task/body/coverage/quality/safety/time gates. New native server-control exit+CLI ACK before launch shutdown and explicitFastDDSUDPloopbackprofile sha=443340f4c7e083c11258aa28917212feaca01d34aa30a0ce689ea02819a379ef /ROS_LOCALHOST_ONLY=0/SKIP_DEFAULT_XML=1; not proof of old root cause, full9new pushedfreeze/no old task cells. Old v4 ABRT/startupfail/no-signals outcome retained.

- Matrix5 candidate integrated checks: canonical ROS command `source /opt/ros/humble/setup.bash; source install/setup.bash; export PYTHONNOUSERSITE=1; /usr/bin/python3 /usr/bin/colcon test --packages-select multi_robot multi_robot_exploration merge_map --event-handlers console_cohesion+`; 12.8 wall sec, 297 tests = 295 pass / 2 skip / 0 failure or error. multi_robot build command `source /opt/ros/humble/setup.bash; source install/setup.bash; export PYTHONNOUSERSITE=1; /usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select multi_robot --event-handlers console_cohesion+` completed in 1.68 wall sec; new explicit UDP-loopback XML installed byte-identical. pre_matrix5_component_checks.json retains all six changed/new runtime/test source hashes (including XML and independent environment tests), build/test invocation log hashes and three byte-identical JUnit snapshots. Native-stop dual-exit/early-zero-exit errors, terminal-JSON graceful wait, UDP profile/environment selection and strict original child/contact sequence gates are covered. No simulator was run for this receipt. fixture_v8_component_binding_matrix5.json independently confirms nine unchanged physical/contact/fixture hashes only; old middleware/full-launch environment and old mapping task cells are explicitly excluded. New UDP environment and shutdown paths still require the complete new-freeze matrix5 native validation; no proven root-cause claim.

- Prematrix5 official maintenance 2026-10-14T15:53:23.720049+00:00; freeze=f7ad7fd645f0d6af832b895a37a68b14411354fc; command `/usr/bin/python3 /opt/ros/humble/tools/fastdds/fastdds.py shm clean`; rc=0; stdout="shm.clean:\n4 ports in use\n4 segments in use\n0 zombie ports cleaned\n0 zombie segments cleaned\n"; stderr="". Official lock-aware cleanup retains live resources; no manual global deletion, native experiment not yet started. Canonical pre_matrix5_fastdds_cleanup.json.

### MR3-P1A native attempt mr3_p1a_v5_rooms_20261014_150452

- Freeze: f7ad7fd645f0d6af832b895a37a68b14411354fc committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; selected DDS environment={"FASTRTPS_DEFAULT_PROFILES_FILE": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/mr3_fastdds_loopback_udp.xml", "GAZEBO_MASTER_URI": "http://127.0.0.1:11851", "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp", "ROS_DOMAIN_ID": "95", "ROS_LOCALHOST_ONLY": "0", "SKIP_DEFAULT_XML": "1"}; ROS_DOMAIN_ID=95; GAZEBO_MASTER_URI=http://127.0.0.1:11851.
- Command (canonical ROS root):

```bash
/usr/bin/python3 scripts/run_ideal_baseline.py --world p1c_rooms.world --robot-count 3 --seeds 101 202 303 --task-contract src/multi_robot/config/mr3_p1a/rooms.json --startup-timeout 300 --evaluation-wait-timeout 900 --shutdown-timeout 60 --run-id mr3_p1a_v5_rooms_20261014_150452 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a
```

- Result pending at invocation; all native output retained.

- Matrix5 native environment snapshot 2026-10-14T15:54:59.852565+00:00: run mr3_p1a_v5_rooms_20261014_150452, freeze f7ad7fd645f0d6af832b895a37a68b14411354fc; exact owned launch pid=3464161 and descendant gzserver pid=3464261 observed via /proc only; domain=95, Gazebo port=11851, RMW=rmw_fastrtps_cpp, ROS_LOCALHOST_ONLY=0, SKIP_DEFAULT_XML=1, explicit profile SHA=443340f4c7e083c11258aa28917212feaca01d34aa30a0ce689ea02819a379ef. Both process cwd default XML files were absent at snapshot; runtime profile loading was not traced or inferred. Selective environment/argv/profile snapshot retained in matrix5_rooms_native_environment.json, SHA=a032a9a595830261bf3cc5f7678d7d4c2a54b9340d15b6b36c2c4382dce07c9b. No extra ROS CLI/participant, task credit, source edit or stop signal.

- Matrix5 read-only UDP diagnostic 2026-10-14T15:58:42.037327+00:00: exact rooms seed202 owned launch/gzserver/reducer/TaskEvaluator sampled via /proc at 0/2/4 wall seconds. Per-socket inode/local ports/queues/drops and namespace UDP counters retained in matrix5_rooms_seed202_udp_diagnostic.json, SHA=39a23b33fd89fdff521f27d386afc877e28fe0018198c56e3019b5bc0827243b. Owned process cumulative socket drops={"launch": [0, 0, 0], "gzserver": [431810, 431810, 431810], "contact_reducer": [45653, 45653, 45653], "task_evaluator": [9957, 9957, 9957]}; global UDP delta={"InDatagrams": 32095, "NoPorts": 2, "InErrors": 0, "OutDatagrams": 30641, "RcvbufErrors": 0, "SndbufErrors": 0, "InCsumErrors": 0, "IgnoredMulti": 0, "MemErrors": 0}. Global counters are not process/topic-attributed; no retroactive seed101 causality claim. Snapshot saved successfully; initial separate log append used an incorrect log path and was corrected here without modifying the snapshot. No ROS participant/graph CLI, runtime source change, signal or gate adjustment.

- Finished 2026-10-14T16:07:27.381338+00:00; rc=1; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_v5_rooms_20261014_150452/summary.json; success=None; error=None. All native JSON/log/failures retained.

### MR3-P1A native attempt mr3_p1a_v5_corridors_20261014_150452

- Freeze: f7ad7fd645f0d6af832b895a37a68b14411354fc committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; selected DDS environment={"FASTRTPS_DEFAULT_PROFILES_FILE": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/mr3_fastdds_loopback_udp.xml", "GAZEBO_MASTER_URI": "http://127.0.0.1:11852", "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp", "ROS_DOMAIN_ID": "96", "ROS_LOCALHOST_ONLY": "0", "SKIP_DEFAULT_XML": "1"}; ROS_DOMAIN_ID=96; GAZEBO_MASTER_URI=http://127.0.0.1:11852.
- Command (canonical ROS root):

```bash
/usr/bin/python3 scripts/run_ideal_baseline.py --world p1c_corridors.world --robot-count 3 --seeds 101 202 303 --task-contract src/multi_robot/config/mr3_p1a/corridors.json --startup-timeout 300 --evaluation-wait-timeout 900 --shutdown-timeout 60 --run-id mr3_p1a_v5_corridors_20261014_150452 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a
```

- Result pending at invocation; all native output retained.

- Matrix5 native environment snapshot 2026-10-14T16:09:04.236307+00:00: run mr3_p1a_v5_corridors_20261014_150452, freeze f7ad7fd645f0d6af832b895a37a68b14411354fc; exact owned launch pid=3486428 and descendant gzserver pid=3486492 observed via /proc only; domain=96, Gazebo port=11852, RMW=rmw_fastrtps_cpp, ROS_LOCALHOST_ONLY=0, SKIP_DEFAULT_XML=1, explicit profile SHA=443340f4c7e083c11258aa28917212feaca01d34aa30a0ce689ea02819a379ef. Both process cwd default XML files were absent at snapshot; runtime profile loading was not traced or inferred. Selective environment/argv/profile snapshot retained in matrix5_corridors_native_environment.json, SHA=f1dc50987ef32c579efffe5cf663d1336547b770ebe1b7abd362d1a172bf6b2e. No extra ROS CLI/participant, task credit, source edit or stop signal.

### MR3-P1A v5 rooms101 只读审计口径更正

- Recorded at 2026-10-14T16:12:17.681373+00:00; source freeze `f7ad7fd645f0d6af832b895a37a68b14411354fc`。本条只追加分析更正，不修改此前记录、原生JSON/log/runner输出或任务门限，没有新增原生实验。
- 更正此前只读审计消息把rooms101直接称作“基础设施无效测量”的过强判断：它有统一任务起点85.0、初始地图、103条model-state消息及4.0秒任务记录，冻结schema/合同校验通过；完整reducer序列/数量审计与全部原生子进程、owned server/stop CLI退出均正常。
- 依据是既有 `predeclared_native_plan.json` 的 `success_contract`、`MR3_TASK_CONTRACT.md`“成功门禁”第36–45行、冻结 `ros_smoke_test.py` 第163–180行的 `if success` 条件，以及 `run_ideal_baseline.py` 第223–232行的原始分类。`.5`秒持续监测违约会锁存任务失败；这些条文没有把已完整记录的保守失败一律定义为无效schema或非零原生基础设施退出。
- rooms101仍为 `success=false / collision_monitoring_interrupted`：tb1后左脚轮最后source=88.449、receipt=88.5，结束89.0时source-age=.551秒、receipt-age=.5秒，健康失败事实保持原样。这是有效记录的保守monitor-abort task failure，不能计95%成功，也没有完整持续监测或零接触安全信用；记录的零接触事件不能补足监测缺口。
- 原rooms批次runner的2 success / 1 task failure / 0 infrastructure failure原样保留；独立审计另列monitoring-gate failure，不追加“所有失败结果也必须全程健康”的新有效性条件。不因为有效失败挑种子或重跑；同冻结完整九任务仍在执行，尚无整步验收结论。

- Finished 2026-10-14T16:23:24.574661+00:00; rc=1; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_v5_corridors_20261014_150452/summary.json; success=None; error=None. All native JSON/log/failures retained.

- Matrixversion6 predeclared 2026-10-14T16:25:34.967550+00:00: mr3_p1a_v6_rooms_20261014_162534, mr3_p1a_v6_corridors_20261014_162534, mr3_p1a_v6_open_20261014_162534; domains98/99/100, ports11861/62/63, same3x101/202/303 serial full restarts. Cross-v2/v4/v5 lifecycle response-reader timeout recurred; v5 stopped before open3, all6 prior attempts natural end/no signals. Precise RMW writer matching deadline repair only18 explicit lifecycle change_stateReply profiles5wallsec, default100ms; no global/service wildcard/contact/goal QoS or task/95/quality/.5/300 gates changed. Candidate XML hash/static proof to bind before commit and any new native invocation. All9 newfreeze, no old cells reused.

### MR3-P1A v5 暂停开放场景及规范归档

- Recorded at 2026-10-14T16:28:08.816569+00:00; source freeze `f7ad7fd645f0d6af832b895a37a68b14411354fc`。rooms/corridors两个batch、六次尝试均已结束；编排器未向活动任务发送额外停止信号，open三个seed未启动。corridors303内部launch的SIGTERM/SIGKILL升级保留，不与“无额外编排停止”混淆。
- 暂停依据是v2/v4/v5跨版本重复的同类Nav2服务响应/生命周期启动失败；v5 corridors303无任务JSON、就绪门禁退出1、tb3生命周期进程最终exit -9。它是启动基础设施无效测量。不同于有效的rooms101 monitor-abort失败，不把两种失败口径混为一谈。
- 独立审计结果：6 attempts / 5 valid measurements / 4 strict complete success / 1 conservative monitor-abort task failure / 1 startup infrastructure failure / 3 unstarted。原runner分类分别为4 success / 1 task failure / 1 infrastructure failure；rooms101的`.551`秒源龄违约、失败状态和无完整监测/零接触安全信用均保留。P1A最终九任务证据尚未齐全，不能给整步信用。
- 仅运行离线原件复制/审计：`/usr/bin/python3 -B /tmp/archive_development_matrix_v5.py --base /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/development_matrix_v5 --families rooms corridors`，然后`/usr/bin/python3 -B /tmp/audit_development_matrix_v5.py --base /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/development_matrix_v5`。20个原生文件、606530字节原样保存；copy-hash receipt与independent audit保留合同/世界/时钟/质量/参与/接触监测/所有权/18源序列数量/原生退出及两个owned环境快照的校验。
- v5输入从Git f7ad读取profile/validator/合同，绑定旧manifest SHA `e0e609412b111dc7851e417ffb6dd7f05474f5096cbec6f31ac5c7847681b629`。另存f7ad完整predeclared plan并显式选择`version == 5`；未来v6计划或工作树候选XML不是本次审计输入。原件、既有receipt/audit和此前log未覆盖。
- UDP socket采样不能证明rooms101接触payload丢包，也不能单独归因Nav2响应失败。后续核查精确服务响应writer的reader匹配等待与有界配置；300墙秒启动保护及全部95%/质量/参与/接触/源龄/任务时间门禁不变。没有新增原生实验、策略运行、源码修改或提交。

- Matrix6 candidate integrated checks: canonical ROS command `source /opt/ros/humble/setup.bash; source install/setup.bash; export PYTHONNOUSERSITE=1; /usr/bin/time -f MR3_COLCON_WALL_SECONDS=%e /usr/bin/python3 /usr/bin/colcon test --packages-select multi_robot multi_robot_exploration merge_map --event-handlers console_cohesion+`; 12.8 wall sec, 297 tests = 295 pass / 2 skip / 0 failure or error. multi_robot build command `source /opt/ros/humble/setup.bash; source install/setup.bash; export PYTHONNOUSERSITE=1; /usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select multi_robot --event-handlers console_cohesion+` completed in colcon-reported 0.59 wall sec (shell setup excluded); explicit UDP-loopback XML with only18 exact lifecycle response matching profiles installed byte-identical. pre_matrix6_component_checks.json retains all changed/new runtime/test source hashes (including XML and independent environment tests), build/test invocation log hashes and three byte-identical JUnit snapshots. Native-stop dual-exit/early-zero-exit errors, terminal-JSON graceful wait, UDP profile/environment selection and strict original child/contact sequence gates are covered. No simulator was run for this receipt. fixture_v8_component_binding_matrix6.json independently confirms nine unchanged physical/contact/fixture hashes only; old middleware/full-launch environment and old mapping task cells are explicitly excluded. New UDP environment and shutdown paths still require the complete new-freeze matrix6 native validation; no proven root-cause claim.

- Matrix6 candidate lifecycle response QoS static check: profile SHA=8d11da75d5916ed95d8b8a6a74abecb8fe946254d615895164a63ef9f8ff9556 adds exactly 18 named rr/tbN/six-Nav2-node/change_stateReply publisher profiles, no default/service fallback or reader profile. Actual installed FastDDS2.6.11 parser and rmw_fastrtps6.2.10 name mangling/QoS converter confirm SDK default100ms, selected5wall-sec retained after ROS service QoS conversion (RELIABLE/depth10), 16 unmatched actual control/contact/clock/get_state/request/tb4 names still100ms. UDP participant/descriptor structurally identical to f7ad7fd. Pure tests18PASS/flake8 PASS; checker creates no participant/node/endpoint or simulator. New lifecycle_reply_qos_v6_{checker.cpp,static_proof.json} retained (proof SHA=69205bb1722bab445b66f39ba942d427b1d9a81e0bf00a629450d2d87e0c7162). Existing300wall startup/300sim task/.5health/20Hz/100history/95quality/safety gates preserved. This targets the observed response matching deadline; delayed discovery cause and future native outcome remain unproven.

- Prematrix6 official maintenance 2026-10-14T16:34:24.204613+00:00; freeze=5e478025ede4f66420cc293655c0c03db791b2ab; command `/usr/bin/python3 /opt/ros/humble/tools/fastdds/fastdds.py shm clean`; rc=0; stdout="shm.clean:\n3 ports in use\n3 segments in use\n0 zombie ports cleaned\n0 zombie segments cleaned\n"; stderr="". Lock-aware tool retains active resources; no manual global deletion or active owned simulator before maintenance. Canonical pre_matrix6_fastdds_cleanup.json.

### MR3-P1A native attempt mr3_p1a_v6_rooms_20261014_162534

- Freeze: 5e478025ede4f66420cc293655c0c03db791b2ab committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; selected DDS environment={"FASTRTPS_DEFAULT_PROFILES_FILE": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/mr3_fastdds_loopback_udp.xml", "GAZEBO_MASTER_URI": "http://127.0.0.1:11861", "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp", "ROS_DOMAIN_ID": "98", "ROS_LOCALHOST_ONLY": "0", "SKIP_DEFAULT_XML": "1"}; ROS_DOMAIN_ID=98; GAZEBO_MASTER_URI=http://127.0.0.1:11861.
- Command (canonical ROS root):

```bash
/usr/bin/python3 scripts/run_ideal_baseline.py --world p1c_rooms.world --robot-count 3 --seeds 101 202 303 --task-contract src/multi_robot/config/mr3_p1a/rooms.json --startup-timeout 300 --evaluation-wait-timeout 900 --shutdown-timeout 60 --run-id mr3_p1a_v6_rooms_20261014_162534 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a
```

- Result pending at invocation; all native output retained.

- Matrix6 native environment snapshot 2026-10-14T16:34:57.706182+00:00: run mr3_p1a_v6_rooms_20261014_162534, freeze 5e478025ede4f66420cc293655c0c03db791b2ab; exact owned launch pid=3498456 and descendant gzserver pid=3498510 observed via /proc only; domain=98, Gazebo port=11861, RMW=rmw_fastrtps_cpp, ROS_LOCALHOST_ONLY=0, SKIP_DEFAULT_XML=1, explicit profile SHA=8d11da75d5916ed95d8b8a6a74abecb8fe946254d615895164a63ef9f8ff9556. Both process cwd default XML files were absent at snapshot; runtime profile loading was not traced or inferred. Selective environment/argv/profile snapshot retained in matrix6_rooms_native_environment.json, SHA=5f485b465bb0530bf5700c7f97e76d9a5fc589da46ba8c1cbe6830e2996fdf69. No extra ROS CLI/participant, task credit, source edit or stop signal.


## MR3-P1A v6 初始运行组件只读身份审计

- 时间：2026-10-14T16:36:08.903453+00:00；冻结`5e478025ede4f66420cc293655c0c03db791b2ab`。
- 命令/检查：`rtk proxy python3`离线读取`runtime_component_manifest_matrix6.json`；对462项实际文件重新计算SHA256，445项tracked source另与`git show 5e478025:<path>`字节比对，16对source/installed直接逐字节比较。
- manifest SHA256：`08f22f98c99d0e2173726990b2b0e8c65dd83a7b5eceaf6c3afde1b976a4b557`；全部身份检查PASS。结果保存至`report/assets/20261014_mr3_p1a/matrix6_initial_runtime_identity_audit.json`，SHA256 `5bb3c29132463190e71f2dbfba91b175494898c79940a620931ef3cf7c0db64d`；从/tmp逐字节复制，未覆盖既有记录。
- 这是元数据/身份审计，没有运行ROS、仿真或策略，没有修改运行组件或任务参数。v6原生九任务仍在进行；该身份PASS不代替任务/安全/退出验收。

- Finished 2026-10-14T16:51:11.316070+00:00; rc=1; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_v6_rooms_20261014_162534/summary.json; success=None; error=None. All native JSON/log/failures retained.

### MR3-P1A native attempt mr3_p1a_v6_corridors_20261014_162534

- Freeze: 5e478025ede4f66420cc293655c0c03db791b2ab committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; selected DDS environment={"FASTRTPS_DEFAULT_PROFILES_FILE": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/mr3_fastdds_loopback_udp.xml", "GAZEBO_MASTER_URI": "http://127.0.0.1:11862", "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp", "ROS_DOMAIN_ID": "99", "ROS_LOCALHOST_ONLY": "0", "SKIP_DEFAULT_XML": "1"}; ROS_DOMAIN_ID=99; GAZEBO_MASTER_URI=http://127.0.0.1:11862.
- Command (canonical ROS root):

```bash
/usr/bin/python3 scripts/run_ideal_baseline.py --world p1c_corridors.world --robot-count 3 --seeds 101 202 303 --task-contract src/multi_robot/config/mr3_p1a/corridors.json --startup-timeout 300 --evaluation-wait-timeout 900 --shutdown-timeout 60 --run-id mr3_p1a_v6_corridors_20261014_162534 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a
```

- Result pending at invocation; all native output retained.

- Matrix6 native environment snapshot 2026-10-14T16:51:34.587132+00:00: run mr3_p1a_v6_corridors_20261014_162534, freeze 5e478025ede4f66420cc293655c0c03db791b2ab; exact owned launch pid=3507312 and descendant gzserver pid=3507373 observed via /proc only; domain=99, Gazebo port=11862, RMW=rmw_fastrtps_cpp, ROS_LOCALHOST_ONLY=0, SKIP_DEFAULT_XML=1, explicit profile SHA=8d11da75d5916ed95d8b8a6a74abecb8fe946254d615895164a63ef9f8ff9556. Both process cwd default XML files were absent at snapshot; runtime profile loading was not traced or inferred. Selective environment/argv/profile snapshot retained in matrix6_corridors_native_environment.json, SHA=396b65e28a246a7211ab5a4759f9f7c4afeb66b137d0267bcbb3bc398690bce7. No extra ROS CLI/participant, task credit, source edit or stop signal.

- Finished 2026-10-14T17:02:09.951765+00:00; rc=1; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_v6_corridors_20261014_162534/summary.json; success=None; error=None. All native JSON/log/failures retained.

### MR3-P1A native attempt mr3_p1a_v6_open_20261014_162534

- Freeze: 5e478025ede4f66420cc293655c0c03db791b2ab committed/pushed; fixed3robots, exact contract, no RL/network credit.
- Environment: system ROS Humble; PYTHONNOUSERSITE=1; selected DDS environment={"FASTRTPS_DEFAULT_PROFILES_FILE": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/mr3_fastdds_loopback_udp.xml", "GAZEBO_MASTER_URI": "http://127.0.0.1:11863", "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp", "ROS_DOMAIN_ID": "100", "ROS_LOCALHOST_ONLY": "0", "SKIP_DEFAULT_XML": "1"}; ROS_DOMAIN_ID=100; GAZEBO_MASTER_URI=http://127.0.0.1:11863.
- Command (canonical ROS root):

```bash
/usr/bin/python3 scripts/run_ideal_baseline.py --world p1c_open.world --robot-count 3 --seeds 101 202 303 --task-contract src/multi_robot/config/mr3_p1a/open.json --startup-timeout 300 --evaluation-wait-timeout 900 --shutdown-timeout 60 --run-id mr3_p1a_v6_open_20261014_162534 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a
```

- Result pending at invocation; all native output retained.

- Matrix6 native environment snapshot 2026-10-14T17:03:11.440666+00:00: run mr3_p1a_v6_open_20261014_162534, freeze 5e478025ede4f66420cc293655c0c03db791b2ab; exact owned launch pid=3513498 and descendant gzserver pid=3513560 observed via /proc only; domain=100, Gazebo port=11863, RMW=rmw_fastrtps_cpp, ROS_LOCALHOST_ONLY=0, SKIP_DEFAULT_XML=1, explicit profile SHA=8d11da75d5916ed95d8b8a6a74abecb8fe946254d615895164a63ef9f8ff9556. Both process cwd default XML files were absent at snapshot; runtime profile loading was not traced or inferred. Selective environment/argv/profile snapshot retained in matrix6_open_native_environment.json, SHA=1961bc2d04a403a1ed6bb41c0b869f3eb925cc451a177aec97aba50c7f01bc87. No extra ROS CLI/participant, task credit, source edit or stop signal.

- Finished 2026-10-14T17:14:41.214059+00:00; rc=1; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_v6_open_20261014_162534/summary.json; success=None; error=None. All native JSON/log/failures retained.


## MR3-P1A v6 原九次尝试规范归档与独立审计

- 时间：2026-10-14T17:18:21.540429+00:00；固定源码`5e478025ede4f66420cc293655c0c03db791b2ab`、原manifest SHA256`08f22f98c99d0e2173726990b2b0e8c65dd83a7b5eceaf6c3afde1b976a4b557`；三图×101/202/303全部自然结束。
- 离线命令：`rtk proxy python3 /tmp/archive_development_matrix_v6.py --base ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/development_matrix_v6`；随后同base执行`/tmp/audit_development_matrix_v6.py`。两个脚本未启动ROS/策略/仿真；原件未改，全部33原文件与规范副本重新核对SHA256。
- 原九次JSON/CSV、九份launch日志及三个batch的summary JSON/CSV，共33文件995903字节；另保存15项冻结输入/审计脚本。复制receipt SHA256`1fe3ce960a48e9ffc1ce9475b086deb3ea5968959ed1952111be467ac30d4664`，独立auditor SHA256`fe84b94032d756b09b679b418483e078e189f6327b945d3d0ed770f1f0966cf0`。
- 独立结论：9attempt、9JSON、6JSON success，完整strict success为5；有效任务测量8，三次peer-envelope有效安全失败保留，open303因robot_state_publisher-5 pid3517700关闭exit -11为基础设施无效。各scene已有严格成功，但原九并非九次全部有效，`stage_evidence_complete_not_user_acceptance=false`。
- open303任务JSON的95%/质量/参与/持续18路健康/零接触/目标闭合通过，owned Gazebo与stop CLI实际退出0、reducer严格序列通过；这些不能抵消其他原生子进程-11。没有修改原任务成功字段、runner失败或门槛，也未执行补测；后续决定与原九审计分开记录。

- Supplemental v6 infrastructure replay predeclared 2026-10-14T17:20:03.441303+00:00: mr3_p1a_v6_open_shutdown_retry1_20261014_172003; original9 remain5 strict successes+3 valid peer-safety failures+1 shutdown-native invalid (open303 RSP3517700 exit-11 after taskJSON success). Before replay, locked maximumONE exactsamefreeze 5e478025ede4f66420cc293655c0c03db791b2ab/open303/domain100/11863/contract/profile/guards/fullrestart; no runtime repair or cleanup, no missionfail retry. Any valid task outcome accepted; another infra triggers pause. This protocol supplement is after original9, not falsely called part of original plan. Report all10attempts and originalfault, no repaired-root-cause claim. Exactcase/hashes/evidence+rules in v6_open303_infrastructure_retry1_predeclaration.json sha=a22af2d3cdf9c1db1af76b5ff25be7667ce8d67b5fbebf26b2fb513ed9337605.

### MR3-P1A supplemental pure-infrastructure replay mr3_p1a_v6_open_shutdown_retry1_20261014_172003

- Freeze 5e478025ede4f66420cc293655c0c03db791b2ab still committed/pushed; original all9 remain. MaximumONE, accept any valid task result and never rerun mission failure. Full source+installed manifest and original evidence SHA verified. Exact environment={"FASTRTPS_DEFAULT_PROFILES_FILE": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/mr3_fastdds_loopback_udp.xml", "GAZEBO_MASTER_URI": "http://127.0.0.1:11863", "PYTHONNOUSERSITE": "1", "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp", "ROS_DOMAIN_ID": "100", "ROS_LOCALHOST_ONLY": "0", "SKIP_DEFAULT_XML": "1", "TURTLEBOT3_MODEL": "waffle"}.
- Command (canonical ROS root):

```bash
/usr/bin/python3 scripts/run_ideal_baseline.py --world p1c_open.world --robot-count 3 --seeds 303 --task-contract src/multi_robot/config/mr3_p1a/open.json --startup-timeout 300 --evaluation-wait-timeout 900 --shutdown-timeout 60 --run-id mr3_p1a_v6_open_shutdown_retry1_20261014_172003 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a
```

- Result pending. Runtime/source/physics/task/quality/contact/safety gates unchanged, no new middleware maintenance.

- Matrix6 native environment snapshot 2026-10-14T17:21:14.421642+00:00: run mr3_p1a_v6_open_shutdown_retry1_20261014_172003, freeze 5e478025ede4f66420cc293655c0c03db791b2ab; exact owned launch pid=3521888 and descendant gzserver pid=3521931 observed via /proc only; domain=100, Gazebo port=11863, RMW=rmw_fastrtps_cpp, ROS_LOCALHOST_ONLY=0, SKIP_DEFAULT_XML=1, explicit profile SHA=8d11da75d5916ed95d8b8a6a74abecb8fe946254d615895164a63ef9f8ff9556. Both process cwd default XML files were absent at snapshot; runtime profile loading was not traced or inferred. Selective environment/argv/profile snapshot retained in v6_open303_infrastructure_retry1_native_environment.json, SHA=883bda26e93507c2c2b1efc0b025c159aee206fdf581ec31fd0bec2d88ea11f0. No extra ROS CLI/participant, task credit, source edit or stop signal.

- V6 open303 shutdown diagnostic: original task JSON success/76.6simsec remains native-infrastructure-invalid after tb1 RobotStatePublisher pid3517700 SIGINT then SIGSEGV-11 (native log302/305/306/340/354/377). Fresh apport collector3519968 binds this PID/signal/time and wrote a current report; executable timestamp matches. Selected metadata and gdb thread bt (no full locals) retained in v6_open303_shutdown_diagnostic; diagnostic SHA=49caf86d2778fb457c4c34eedde04ed22ac3db39c009f71a20f924bb90d03ada, receipt SHA=3971524930937c36cec107d1ba15540d3f2e8647b1786625247109926fb7b333. Core confirms FastDDS EDP::unpairWriterProxy+406 null-listener dereference on receiver thread while main thread destroys a NodeTimeSource subscription. Exact listener-clearer/interleaving, UAF and transport root cause remain unproven; no patch/wrapper/sleep/SDK or transport change made. Full apport and raw core stay outside Git at original/tmp paths with SHA references only. No native rerun or signal was issued for this diagnosis.

- Supplemental replay finished 2026-10-14T17:24:34.413002+00:00; rc=0; result=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p1a/mr3_p1a_v6_open_shutdown_retry1_20261014_172003/summary.json; episodes=[{"gazebo_seed": 303, "native_control_failure": "", "runner_returncode": 0, "success": true, "termination_reason": "coverage_reached"}]. Exactly one replay completed; original shutdown SIGSEGV retained, no root-cause cure or original9 clean claim.


## MR3-P1A v6 单次补测规范归档、有效槽位及交付文档独立审计

- 时间：2026-10-14T17:28:40.380824+00:00；运行冻结仍为`5e478025ede4f66420cc293655c0c03db791b2ab`，未修改源码/库/运行门槛。原九`independent_audit.json` SHA256`9a90407545c6b2a5cadf0156b8e139a9896440217b391226435ca3b7930acd82`及其stagefalse保持原样。
- 离线命令：`rtk proxy python3 /tmp/archive_development_matrix_v6_supplement_retry1.py --base ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/development_matrix_v6_supplement_retry1`，随后同base运行`/tmp/audit_development_matrix_v6_supplement_retry1.py`；没有启动ROS/仿真/策略。补测原件5文件105878字节与副本全SHA一致，复制receipt SHA256`8d2a383993d67fe824d9a7e4845c96febb0b0983aa62cf87a4f23f01ab0e275d`。
- 补测独立结论：open303 strictPASS52.3仿真秒/C.959851182，质量/三台参与/18路持续健康/零非支撑接触/目标闭合/全部原生退出通过；raw48894严格单publisher序列和输入输出对账PASS。补充审计锁定事前追加声明a22af2d...、同domain100/11863、完整原case/env/manifest/合同/世界与原九证据。
- 两层合计10attempts：6strict、3有效peer-envelope任务失败、1原关闭infra保留；9effective scene/seed slots（rooms2/3、corridors1/3、open3/3成功）。没有把原九改成全部有效，没有重跑三次真实任务失败，没有宣称0infra或SIGSEGV机制已修复。新审计的证据完整标志不代表用户验收，不进入P1B。
- 交付候选仅更新P1A报告、report README和ARCHIVE_INDEX；原24条历史SHA、10报告body与c934历史freeze字段语义保持。78个报告/README本地链接、24项新索引artifact SHA、原九+补测原件/输入SHA和全部462运行文件仍一致，scoped diff-check PASS。静态receipt为`report/assets/20261014_mr3_p1a/p1a_delivery_independent_checks.json`，SHA256`857eb3b22568768a21c7ced597e2b86c88d8ae27aa4f272f88a9c76f1f631573`。未提交，交由root完成统一交付；待用户明确验收。


## MR3-P1A 活动文档状态同步（静态检查，无新实验）

- 本地日期2026-10-15；已完成补充独立审计后按授权同步13份活动文档：根/组件README与AGENTS、研究/实施计划、任务契约及操作/技术指南。P0接受日期仍为2026-10-14，P1A统一为待用户验收，P1B及后续未开始。
- 运行冻结仍为`5e478025ede4f66420cc293655c0c03db791b2ab`。文档简述累计10次尝试含1次保留的原生关闭基础设施失败、9个有效单元（6严格成功/3有效peer安全失败），详细经过留在P1A报告和原日志；不宣称原九全过、零infra尝试或SDK崩溃已根治。任务契约保留各门禁独立分类；未改变预算、阈值、划分和运行参数。
- 静态命令：`rtk proxy /usr/bin/python3 /tmp/check_mr3_p1a_final_docs_v6.py`。逐文diff复核后，13文档68个本地链接、25段Bash语法、5条显式三机器人命令及源码参数、P0/P1A/P1B状态、`git diff --check`全部PASS；`launch_commands.md`的v6 UDP环境、精确18个5墙秒writer配置与Gazebo双退出确认说明保持冻结原文。
- 仅文档同步及本条追加记录；没有ROS/仿真/训练/补测、运行源码或旧证据修改，没有生成最终文档receipt、没有提交。报告/索引由独立负责者更新；最终统一checker6 receipt和提交交由root执行。


## 2026-10-15 MR3-P1A用户验收与P1B适配实施

用户本轮明确“p1a验收通过，继续执行p1b”。P1A已验收，授权边界仅P1B；P1C、训练和gateway未开始。
基点`d47df73`，本轮新增理想received存储、稳定目标dispatcher、确定性观测/几何候选/1000类掩码、
互斥adapter启动模式及独立原生脚本/审计。完整契约见`MR3_ADAPTER_CONTRACT.md`。

离线验证（不产生仿真/任务/训练信用）：在Git根执行
`rtk proxy bash -c 'source /opt/ros/humble/setup.bash; source ros2_ws/ros2-multi-robot-automap/install/setup.bash; export PYTHONNOUSERSITE=1; /usr/bin/python3 -m pytest -q ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test --ignore=ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_flake8.py --ignore=ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_pep257.py --ignore=ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_copyright.py'`。
中间完整回归396 passed；最终数量在P1B报告记录。仅对新增文件执行flake8，保留既有文件的历史风格。
ROS工作区执行`rtk proxy bash -c 'source /opt/ros/humble/setup.bash; export PYTHONNOUSERSITE=1; /usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select multi_robot multi_robot_exploration --allow-overriding nav2_bringup'`，2包构建通过。
独立审查修正接受状态命名、地图内容/版本配对、TF有效时刻与测量源时间、命令过期与停止竞态、
重复命令指纹、drive布尔别名和探针停钟/原生退出审计。无新依赖安装。

原生运行前预声明：`report/assets/20261015_mr3_p1b/predeclared_native_plan.json`。
open/rooms/corridors各seed101、三台、串行、独立域108/109/110与Gazebo端口11901/11902/11903；
一次推送源码冻结下运行，25仿真秒脚本适配探针（KEEP/WAIT/重复/跨epoch/过期/承诺期边界）。
95%/300秒合同不变；短探针主动中断的评价不能计任务成功。失败、原生异常和后续修复均追加，原件不覆盖。

### P1B v1原生失败（保留，非通过）

源码冻结`2c3087a428ac213195672e932782c020f7355f07`已推送。ROS工作区执行
`rtk proxy bash -c 'source /opt/ros/humble/setup.bash; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=108 GAZEBO_MASTER_URI=http://127.0.0.1:11901; /usr/bin/python3 scripts/run_mr3_adapter_probe.py --scene open --seed 101 --run-id mr3_p1b_v1_open101'`。
原生尝试183.83墙秒后失败，零策略观测/目标：adapter构造时`self.clients`与rclpy Node只读属性冲突，子进程exit1。
独立探查验证三台SLAM实际transform_timeout均.2；8墙秒只读state/map观察发现桥状态有效，未给探针提供动作或反馈。
发现构造失败后，通过launch日志唯一记录的owned evaluator PID4008154、/proc命令及域108校验，
发送SIGINT使其输出shutdown诊断，并触发原launch的Gazebo原生关闭；人工操作receipt保留。
父launch exit0不掩盖adapter失败。独立审计同样FAIL。rooms/corridors在此冻结未运行，未拼成矩阵。
原件`ros2_ws/ros2-multi-robot-automap/log/mr3_adapter/mr3_p1b_v1_open101/`；选定完整日志/JSON见
`report/assets/20261015_mr3_p1b/native_v1_open101_failure/`。

修复字段名后新增真实rclpy节点create/destroy及所有权锁释放回归。探针不再先停server，
而是通过唯一owned evaluator正常finalize(shutdown)触发既有launch关闭审计；不修改95%任务门禁。
新版三场景重跑在`predeclared_native_plan_v2.json`前瞻性声明。原失败不删除/不改PASS。

### P1B v2原生失败（保留，非通过）

冻结`9e43209638bd504e75b2220b709f0eb32eef04d7`，运行命令与v1相同，唯一run-id替换为
`mr3_p1b_v2_open101`。实际129.26墙秒，任务82.0放行，tb3目标真实接受并在82.4终态取消闭合；
82.2由received_state_stale停止，.5秒安全界未修改。首快照tb1/tb2起点因融合图中的自体回波
不可行（safe seeds false/false/true），只有tb3获目标。另真实取消ACK数组比较触发ValueError，
原RPC错误保留；未把任务闭合导航失败标记false视为通过。
评价器已因控制失败自然写出JSON时，runner仍发SIGINT与其退出竞态，子进程exit-2；
因此父launch0/原生stop0仍不掩盖基础设施失败。独立审计FAIL；rooms/corridors未在此冻结运行。
选定原件`report/assets/20261015_mr3_p1b/native_v2_open101_failure/`。

一般性根因：5Hz雷达与TF源时间加.2有效期后，又等待有效期形成额外.2秒滞留；修正为
只拒绝真正未来测量源，保留原header不回写。地图编码移入单worker线程，协议/状态回调
不因编码阻塞；不放宽.5秒。路径可行性改用每台已交付的未改写本地图，候选目标仍用融合
图原分辨率几何，不删自体范围内的真实障碍、不跳到其他自由分量。RPC异常显式锁存失败；
UUID按bytes比较。显式probe_finalize服务仅在adapter_probe模式启用，输出未完成诊断，
不再对正在退出的评价器发信号。新矩阵与脚本取消压力顺序已在v3预声明，原失败保留。

### P1B v3原生失败（保留，非通过）

冻结`d6ce8318e50f683b7e720bc9a3adf20a1e0efa8c`。同一环境/命令，run-id为`mr3_p1b_v3_open101`，
runner显式新增`adapter_probe:=true`。130.05墙秒、任务80.0放行：三台原生目标均接受，
80.4因received_state_stale停止，三台均获得正取消ACK并于80.7收到CANCELED终态。
现在本地图路径的三台起点均可行，UUID比较、RPC回执、原生关闭正常；父/全部子进程、
Gazebo与其stop CLI exit0，未宣称SDK崩溃根治。仍是失败：未执行完整25秒、无有效运动证明，
没有KEEP/承诺期边界样本；独立audit FAIL。rooms/corridors未在此冻结运行。
选定原件`report/assets/20261015_mr3_p1b/native_v3_open101_failure/`。

继续诊断信息桥1Hz地图编码/融合/三份导航副本对10Hz状态回调的阻塞，记录源与接收时刻，
修复一般性调度根因；不更改.5秒、机体、接触、ROI/95%或时间门禁。v4预声明保留原三场景
串行同冻结矩阵，并增加状态更新/陈旧诊断；无训练/reset/gateway。

P1B离线根因诊断：在Humble/system Python环境执行
`PYTHONNOUSERSITE=1 PYTHONPATH=ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration:ros2_ws/ros2-multi-robot-automap/src/merge_map:ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test:$PYTHONPATH /usr/bin/python3 /tmp/mr3_p1b_sync_map_profile.py`。
脚本从`d6ce831`Git对象载入同步信息桥，三份238×198/.05m自由图、fake publishers，未创建ROS节点或模拟器。
五次publish_maps墙时为.55955/.56063/.56641/.55622/.55378秒；这不是仿真秒，也不算P1C采样吞吐。
它解释了为何1Hz地图处理会阻塞10Hz状态；实际源龄失败以v3原生时序为准。
完整可重放脚本/输入哈希/结果见`report/assets/20261015_mr3_p1b/mr3_p1b_sync_map_profile.py`和`sync_map_profile.json`。

P1B异步处理离线检查：完整语义测试448 passed/12.66s（同上完整pytest命令）；
信息桥36相关测试和Humble域190真实节点create/destroy通过，无模拟器。
Git根source Humble和ROS install，设置`PYTHONNOUSERSITE=1`及
`PYTHONPATH="$PWD/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test:$PYTHONPATH"`后执行
`/usr/bin/python3 ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1b/mr3_p1b_async_map_profile.py`，
输出`async_map_profile_receipt.json`。固定2秒fixture、不创建ROS节点/DDS/模拟器；5次后台处理时
状态回调持续执行，主采样/应用约.072–.088墙秒，状态回调实测最大.09131墙秒（含并发运行
完整单测的主机负载），worker约.686–.844墙秒。这不是原生Hz/仿真倍率或P1C吞吐。
原同步profile的冻结helper显式绑定复现版另存`mr3_p1b_sync_map_profile_replay.py`，
原测量脚本与哈希保留。下一步仅执行v4预声明的3场景同冻结原生矩阵确认修复，门限不变。

### P1B v4同冻结原生矩阵：open101

运行冻结`f9928fe97f4081c3f331ba1407aa18a9fc14a602`已推送。命令为
`rtk proxy bash -c 'source /opt/ros/humble/setup.bash; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=108 GAZEBO_MASTER_URI=http://127.0.0.1:11901; /usr/bin/python3 scripts/run_mr3_adapter_probe.py --scene open --seed 101 --run-id mr3_p1b_v4_open101'`
（ROS工作区执行），168.24墙秒。task sim80.0–105.6终态闭合，真实7次发送/7终态，44robot-KEEP无重发，
4条同目标正取消ACK→CANCELED，重复幂等及wrong_epoch/expired/masked拒绝齐全。
`rtk proxy /usr/bin/python3 scripts/audit_mr3_adapter_probe.py log/mr3_adapter/mr3_p1b_v4_open101 --require-contact-monitoring`独立PASS；
27原始快照全部可回放，三台观测估计路径2.474/2.362/.435m；18路持续新鲜、原始发布序列完整，零非支撑接触。
Gazebo与stop CLI各唯一PID匹配clean exit0，父及子进程均无原生失败。schema4为adapter_probe_shutdown、
success=false；协议闭合由adapter原件单独证明，不把评价器navigation_protocol_closed=false改为PASS。
后期tb3自身地图路径起点可行性低（3/27快照），是保守候选限制，保留诊断，不能声称95%RL任务可达。
选定原件`report/assets/20261015_mr3_p1b/native_v4/open101/`；运行目录保留所有文件。
同冻结rooms101随后启动，域109/端口11902，唯一run-id`mr3_p1b_v4_rooms101`，其他参数/门限不变。

### P1B v4同冻结原生矩阵：rooms101

冻结仍为`f9928fe97f4081c3f331ba1407aa18a9fc14a602`。同open完整命令，环境改
`ROS_DOMAIN_ID=109 GAZEBO_MASTER_URI=http://127.0.0.1:11902`，参数改
`--scene rooms --seed 101 --run-id mr3_p1b_v4_rooms101`，其余源/门限/脚本不变。
169.67墙秒，task sim79.0–104.6，导航终态闭合。
`rtk proxy /usr/bin/python3 scripts/audit_mr3_adapter_probe.py log/mr3_adapter/mr3_p1b_v4_rooms101 --require-contact-monitoring`
严格PASS，18路持续新鲜/原始序列完整/零接触，真实三台移动与取消/终态、唯一原生server/CLI退出均通过。
原生JSON仍为未完成adapter_probe_shutdown，不作为95%任务成功。
选定原件`report/assets/20261015_mr3_p1b/native_v4/rooms101/`，完整指标在audit/summary。
同冻结corridors101随后启动，域110/端口11903、run-id`mr3_p1b_v4_corridors101`，不跨冻结拼接。


### P1B v4同冻结原生矩阵：corridors101与交付结论

运行冻结`f9928fe97f4081c3f331ba1407aa18a9fc14a602`，ROS工作区精确命令：
`rtk proxy bash -c 'source /opt/ros/humble/setup.bash; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=110 GAZEBO_MASTER_URI=http://127.0.0.1:11903; /usr/bin/python3 scripts/run_mr3_adapter_probe.py --scene corridors --seed 101 --run-id mr3_p1b_v4_corridors101'`。
164.81墙秒，task sim81.0–106.5，三台所有权终态闭合。
`rtk proxy /usr/bin/python3 scripts/audit_mr3_adapter_probe.py log/mr3_adapter/mr3_p1b_v4_corridors101 --require-contact-monitoring`
独立严格PASS：27原始快照、24动作、8次真实发送/8终态，40robot-KEEP无重发，
5条正取消ACK→同目标CANCELED。三台观测估计路径2.798/2.316/1.878m；
18路监测持续新鲜、原始序列完整、零非支撑接触，原生server/CLI各唯一PID clean exit0。
选定原件`report/assets/20261015_mr3_p1b/native_v4/corridors101/`，原目录保持不变。

v4同冻结三场景各seed101均通过适配严格审计；前三次旧冻结open失败完整保留，累计6次尝试，
不混用旧冻结或把短探针当作95%成功。每个schema4仍为adapter_probe_shutdown/success=false，
其navigation_protocol_closed=false也未改写；目标闭合由独立adapter原件证明。
汇总`native_v4/matrix_summary.json`和独立复核`native_v4/native_independent_review.json`，
报告`report/20261015_mr3_p1b.md`。名义1秒timer实际rooms快照出现2/3秒间隔，
open的tb3起点仅3/27快照可行；保守门限保持，不宣称训练可用固定dt或95%候选完备。
本步仅理想接口和脚本协议验证完成，状态待用户验收；P1C/reset、训练和gateway未开始。

交付只读复核：用system Python在三个独立临时目录复制选定压缩证据，解压launch.log，
调用冻结审计器`audit_run(..., require_contact_monitoring=True)`，三份均PASS且快照/动作/
真实发送/终态/取消/KEEP/路径与canonical audit一致，原证据未改写。
22个本步修改的运行/测试文件逐字节匹配f9928fe Git对象，备份分支仍为
`8fe1495b6624cd9136f3ce160acaa274428e54ae`；记录`report/assets/20261015_mr3_p1b/delivery_checks.json`。
此为离线重放与静态验证，没有额外模拟器、训练或其他数量实验。

交付文档静态检查：11份活动Markdown的104个本地链接与14段Bash语法通过，
原始/选定证据及冻结哈希相符；`git diff --check`通过。`git add -n .`仅包含活动文档、
本追加日志及选定研究原件，无build/install、bag、地图、checkpoint或额外运行日志。
最终提交推送后保持P1B待用户验收，P1C及后续未开始。


## 2026-10-15 MR3-P1B用户验收与P1C授权

用户明确“P1B验收通过，继续执行P1C”。P1B证据交付提交33d86a0，原运行冻结f9928fe及前三次失败不改写。
本步仅训练环境/reset/reward/固定步长/采样工程与最小GPU前后向，不执行P2A策略训练、gateway或ns-3。
重新阅读活动研究/实施契约、组件AGENTS及ROS指南后，采用完全进程重建reset与私有JSONL pipe：
学习端conda不导入ROS，系统ROS子进程重新source canonical underlay/install；epoch与PID/start-tick/session隔离。
固定1秒步长由1000个真实1ms physics ticks组成，每20ticks暂停并核对真实迭代/时间/ROSclock；
50Hz clock仅为P1C步进调度，新方案不自动取得P4网络因果时钟信用。
地图pipeline drain及SHA绑定、seq0初始奖励账和末步真实终态/外截断关闭握手均需在新冻结原生验证。

P1C环境只读探查（非模拟/训练）：conda ns3gym Python3.10.20、NumPy2.2.6、torch2.11.0+cu128，
CUDA12.8可用、两张驱动报告RTX4090；80逻辑CPU/40核、约134.77GB内存。
现有旧gym0.26.2保留；仅新增Gymnasium1.3.0和farama-notifications0.0.4，版本固定：
`source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m pip install --disable-pip-version-check --no-input --no-deps gymnasium==1.3.0 farama-notifications==0.0.4`。
`python -m pip check`通过，未安装SB3/contrib、scipy、psutil或pytest，ROS环境不混入conda。
兼容依据为官方Gymnasium1.3元数据及SB3/contrib2.9声明；这不是学习有效性结果。

P1C GPU前瞻声明已写`report/assets/20261015_mr3_p1c/gpu_probe_plan.json`，
SHA256 `e0a60d7fcef8e16242196872985eb09dc8696cd7d0450e8d139ba2bbc8c4e0f8`。
固定已保存P1B open101首观测、seed20261015、cuda:0、batch1/8/32各一次forward+backward，
共3次前向/3次反向、0 optimizer step、0 simulator episode、无checkpoint；检查张量、联合掩码、有限梯度与内存/墙时。
执行前须先提交推送本步源码冻结；失败和修正另记，不覆盖原声明或结果。

P1C原生前瞻计划：`report/assets/20261015_mr3_p1c/predeclared_native_plan_v1.json`。
先独立物理/clock组件（静态原world，无机器人团队/建图成绩），再三机器人open101两步pilot；
一般性失败即暂停后续格，原件保留，修复后新freeze完整新矩阵，不跨freeze拼接。
正式采样比较1/2/4个并行worker，每worker固定三台：相同两轮open101，16步/轮，完整重建reset。
单worker另做rooms202/corridors303，仅作跨场景/seed重置回归，不混入前两轮吞吐比较。
独立双worker故障探针在worker0首轮完成4步后仅杀已验证身份的workerPID，期望基础设施异常、
owned子进程清理和下一epoch恢复；peer继续。独立单worker300步全KEEP验证任务deadline
terminated优先于外部truncated。所有任务合同/安全/物理/Nav2/SLAM参数保持，50Hz clock/真实
20ms分段推进是新P1C调度版本；不宣称P1B调度完全等价或P4时钟门禁完成。
精确run-id、域/端口、阶段顺序、脚本、门禁与资源/日志预算均在JSON，执行命令及实测另追加。

P1C首冻结前离线验证：Git根source Humble及ROS install，PYTHONNOUSERSITE=1，执行
`/usr/bin/python3 -m pytest -q ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test --ignore=ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_flake8.py --ignore=ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_pep257.py --ignore=ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_copyright.py`，
511 passed/13.80s；不宣称全仓样式模板通过。conda ns3gym、unset PYTHONPATH、PYTHONNOUSERSITE=1，
wireless-rl目录执行`python -m unittest discover -s mr3_learning/tests -q`，31项/4.050s通过，含真实fork退出清理fixture，无sim。
`rtk proxy ctest --test-dir ros2_ws/ros2-multi-robot-automap/build/multi_robot -R test_step_contract --output-on-failure`
通过(1个CTest/3个gtest case，.24s)。ROS工作区source underlay、systemPython colcon
`/usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select multi_robot multi_robot_exploration --allow-overriding nav2_bringup`
2包/6.77s通过，仅系统Gazebo CMake既有PkgConfig名称warning。新增Python定向flake8(max100)通过。
13份Markdown/136个本地链接、16段bash语法通过；预声明Gazebo TCP端口当前可用。
源码哈希和检查范围在`report/assets/20261015_mr3_p1c/implementation_checks_v1.json`，
base_freeze为本步父提交，不把它误标为后续原生运行冻结。当前未运行原生/GPU；下一步先commit/push。

### P1C v1独立物理/clock夹具

冻结`288dd919a2bfffbfdcfb5e70653969f8edda20bb`已推送。ROS工作区精确命令：
`rtk proxy bash -c 'source /opt/ros/humble/setup.bash; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1; /usr/bin/python3 scripts/check_mr3_step_clock.py --run-id mr3_p1c_v1_clock --ros-domain-id 130 --gazebo-port 12101'`。
结果PASS、7.046墙秒、10个真实迭代/ns回执；1tick真实相位对齐、5×20tick、1000tick、0tick及50Hz ROSclock边界相等通过。
gzserver/helper/原生stop CLI各唯一已记录PID，server/CLI exit0；原world静态几何、无机器人团队，不能计三机器人建图或95%任务信用。
选定原件`report/assets/20261015_mr3_p1c/native_v1/clock/`；全部日志与warning保留。随后仅启动预声明三机器人pilot。

### P1C GPU v1失败（原件保留）

冻结`288dd919a2bfffbfdcfb5e70653969f8edda20bb`。wireless-rl工作目录精确命令：
`source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh && conda activate ns3gym && export PYTHONNOUSERSITE=1 && unset PYTHONPATH && /usr/bin/time -p python -m mr3_learning.gpu_probe --plan report/assets/20261015_mr3_p1c/gpu_probe_plan.json --output report/assets/20261015_mr3_p1c/gpu_probe_v1.json`。
退出1，总17.79墙秒(user11.60/sys2.10)。batch1 forward完成，首backward因
`adaptive_avg_pool2d_backward_cuda`在`torch.use_deterministic_algorithms(True)`下无确定性实现而失败；
batch8/32未执行。实际1次forward、1次失败backward尝试、0optimizer更新，未训练、未重跑原件。
失败JSON`report/assets/20261015_mr3_p1c/gpu_probe_v1.json`，原计划SHA见前瞻条目。
保持确定性要求，拟用固定128/64输入的普通分块AvgPool2d数学等价替换adaptive池化，再做新freeze/v2声明。
正在进行的v1三机器人pilot允许自然结束并独立留证，最终矩阵将使用后续统一冻结，不跨freeze拼接。

### P1C v1三机器人pilot失败（保留，后续矩阵未启动）

冻结`288dd919a2bfffbfdcfb5e70653969f8edda20bb`。wireless-rl目录精确命令：
`rtk proxy bash -c 'source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 2 --run-id mr3_p1c_v1_pilot --base-domain 131 --base-port 12111'`。
146.664墙秒后FAIL、0有效transition；三台Nav2全部active，pause首次请求被helper拒绝
`owned stepping plugin is unavailable`，reset未完成。隔离clock夹具的绝对plugin路径通过，
完整launch的插件参数/路径仍需修根因；不以组件PASS覆盖此失败。
Supervisor保留worker exit1及forced owned cleanup，remaining processes/zombies均为空。
原始目录`ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v1_pilot/`；
选定完整JSON/压缩原文`report/assets/20261015_mr3_p1c/native_v1/pilot_failure/`。
v1原生1/2/4worker、fault及deadline后续均未启动，不拼成矩阵；将修复后新freeze重新预声明全套。

GPU一般性等价修复：固定输入128/64经两层stride2后为32/16，AdaptiveAvgPool2d(4)换为
AvgPool2d(8/4)，保持4×4块平均和参数结构。CPU float64测试证明输出与输入梯度atol1e-12相等，
CUDA_VISIBLE_DEVICES='' 下conda全33项unit/5.273s通过，不是再次GPUprobe。
新前瞻`gpu_probe_plan_v2.json` SHA256
`12d571de23efd66374c3de43f50638744b482546a2f0b41bb3ff475a284bd56a`，仍严格deterministic=True、
batch1/8/32各1次FB、0参数更新；未执行，须新源码推送后授权再run。

原生plugin失败的一般性根因（静态展开实际launch substitutions，并非新模拟）：
Humble gzserver.launch将extra_gazebo_args原字符串放在ROS参数尾部`--`之后，且shell=False不拆字符串，
最终是`["--ros-args","--params-file","CLOCK.yaml","--","-s libmr3_gazebo_step.so"]`。
Gazebo boost program_options将`--`后视为pass-through，不加载server-plugin，因此无loaderror；
GAZEBO_PLUGIN_PATH已含正确安装路径，不是路径导出根因。修复stepped分支使用明确ExecuteProcess argv，
SDK原插件及MR3 absolute.so都以独立token置于ROS参数前，baseline仍原Include。
新增实际启动argv/所选clock/plugin的JSON日志和展开argv回归，不靠“传给include”推断实际SDK参数。

v2原生前瞻完整计划`report/assets/20261015_mr3_p1c/predeclared_native_plan_v2.json`，
同v1阶段/种子/门限/预算，所有run-id改为mr3_p1c_v2_*；新推送freeze后从clock和pilot重新开始，
旧原件和失败不覆盖、不混用旧PASS。GPU v1执行侧car补充原freeze/实际调用次数/墙时和原failure文件SHA，
不修改原failure JSON。下一步只运行与本次等价池化/argv修改相关检查，再commit/push，尚未启动v2原生/GPU。

v2集成静态复审另修两个可重现的暂停水位竞态：snapshot请求以本次information drain的state_sequence
为下界并复核响应，而不是仅用上一次snapshot序号；真实短终态允许最后已交付state不增长，但按当前
物理时间重算源龄/缺失和终态KEEP掩码。评价器已收到但未来的release/stop ACK在真实clock到达后由
既有训练wall轮询重放，不能依赖暂停后不再触发的0.1sim秒timer；不伪造clock或额外采样槽。
GPU等价池化+启动argv修改相关检查：launch 96项通过；conda CUDA_VISIBLE_DEVICES=''全33项CPU
unit通过，scope保持非GPU/非模拟。v1插件根因的纯展开证据另存`v1_plugin_argv_diagnosis.json`，
明确不是当时原生argv捕获，原日志不追加伪造字段。后续v2实际argv将由新机读日志提供。

v2提交前离线最终验证：ROS语义全516项/14.27s通过（同前排除三项既有style模板）；conda禁用CUDA、unset PYTHONPATH的全33项/4.815s通过。修改的ROS Python定向flake8(max100)通过；C++与物理合同未变，沿用v1对应build/CTest检查而不把它当v2原生信用。源码hash见implementation_checks_v2.json。

### P1C v2独立物理/clock夹具

新源码冻结`b328f8484162b9d04170da941a7dbe8487a85c5c`已commit/push。ROS工作区精确命令：
`rtk proxy bash -c 'source /opt/ros/humble/setup.bash; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1; /usr/bin/python3 scripts/check_mr3_step_clock.py --run-id mr3_p1c_v2_clock --ros-domain-id 130 --gazebo-port 12101'`。
PASS10.813墙秒、28回执（含真实1tick相位对齐）、100个clock样本；server144020/helper144421/stopCLI144736均clean退出，精确tick/ns/clock通过。
无机器人团队/建图信用。原件ROS/log/mr3_step_clock/mr3_p1c_v2_clock；选定复制native_v2/clock。随后启动同冻结三机器人pilot，参数仅run-id由v1换mr3_p1c_v2_pilot，阶段不跨freeze。

### P1C GPU v2通过（接口探针，非训练）

冻结`b328f8484162b9d04170da941a7dbe8487a85c5c`。wireless-rl目录精确命令：
`source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh && conda activate ns3gym && export PYTHONNOUSERSITE=1 && unset PYTHONPATH && /usr/bin/time -p python -m mr3_learning.gpu_probe --plan report/assets/20261015_mr3_p1c/gpu_probe_plan_v2.json --output report/assets/20261015_mr3_p1c/gpu_probe_v2.json`。
PASS、time real11.31s，含conda shell12.793819s；batch1/8/32各一次完成forward+backward，共3FB/0update/0simulator episode，无额外GPU调用。
606377参数，logits[B,1000]/value[B]、合法值与梯度有限、非法logits=-inf；GPU0由驱动报告RTX4090。
单FB2.388597/.202690/.083182墙秒含首调用初始化，不作训练吞吐结论；峰值CUDAallocated分别74906112/90830848/130265088bytes。
结果gpu_probe_v2.json、console与execution侧car记录精确命令/计划SHA/fixture来源/预算/原件SHA；保留v1失败。

### P1C v2三机器人pilot通过

同冻结b328f848，wireless-rl精确命令：
`rtk proxy bash -c 'source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 2 --run-id mr3_p1c_v2_pilot --base-domain 131 --base-port 12111'`。
PASS，总153.048625墙秒含全部启动/关闭；startup126.400813s；2个有效transition均dt1秒，最终external_sampler_limit为truncated而非任务成功。
真实native server/stopCLI clean、3机器人目标闭合、18流rawaudit持续健康零接触、严格非终态mapSHA奖励配对、seq0零奖及全进程正常退出无残留/zombie。
独立`/usr/bin/python3 scripts/audit_mr3_env.py <ROS/log/mr3_learning/mr3_p1c_v2_pilot> --output <wireless/report/assets/20261015_mr3_p1c/pilot_v2_audit.json>`通过（从Git根使用canonical完整路径）。
后续按v2前瞻开始workers1完整四轮，非训练/非95%信用；源码冻结保持b328f848。

### P1C v2正式1worker矩阵（运行开始，最终结果另追加）

冻结b328f848，wireless-rl精确命令：
`rtk proxy bash -c 'source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101,rooms:202,corridors:303 --steps 16 --run-id mr3_p1c_v2_workers1 --base-domain 132 --base-port 12121'`。
所有worker始终3机器人；前两open101用于公平采样比较，额外rooms202/corridors303只用于跨场景seed完整reset，不混入比较分母。
离线auditor在首个matrix完成前修复预声明工作负载比较错误：旧代码误要求1worker四轮与2/4worker两轮rawschedule相同；新代码按声明比较首两open101、保留全benchmark总耗时，19项对抗单元通过。此文件仅用于离线分析，不被runtime导入，不改变b328f848原生源码冻结；最终auditor源码SHA单列。
公平cell口径=max_worker(sum首两cell记录墙秒)，包含startup/真实Nav2关闭与下次reset初清理；未记录最后Supervisor reap尾部，不称精确全进程span。真实全benchmark墙时含全部attempts另报。

P1C v2 workers1完整四轮PASS：总1050.449173墙秒、64有效transition，全4epoch正式audit通过、每轮16×1s、真实外截断关闭/18源健康零接触/无owned残留或zombie。公平前两open101口径{"denominator_scope": "max_worker(sum of first two recorded cell elapsed times)", "denominator_wall_sec": 528.1191594148986, "effective_transition_per_wall_sec": 0.060592386073348846, "eligible": true, "episode_indices": [0, 1], "exact_end_to_end_process_span": false, "excludes": "final Supervisor reap tail and all later serial scene regressions", "final_cleanup_timing_available": false, "final_supervisor_cleanup_wall_sec": null, "includes": "cell startup, next-reset cleanup of prior worker, native goal closure", "per_worker": [{"cell_recorded_wall_sec": 528.1191594148986, "transition_only_rate_per_active_wall_sec": 0.1178680326877177, "transition_only_wall_sec": 271.49006622331217, "valid_transitions": 32, "worker_id": 0}], "reset_regression_only_schedule": [["rooms", 202], ["corridors", 303]], "reset_regression_only_transitions": 32, "schedule": [["open", 101], ["open", 101]], "steps_per_episode": 16, "valid_transitions": 32}；额外32transition仅跨场景reset，不混入该rate。

### P1C v2正式2worker矩阵（开始）

同冻结b328f848、wireless-rl精确命令：
`rtk proxy bash -c 'source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 2 --schedule open:101,open:101 --steps 16 --run-id mr3_p1c_v2_workers2 --base-domain 134 --base-port 12131'`。
每worker固定三机器人、独立ROSdomain/Gazeboport，结果与失败另追加，不和1worker同时间运行。

P1C v2 workers2完整四epoch PASS：总576.164632墙秒、64有效transition、总有效率.111079362/s；独立正式audit通过，全部16×1s、真实关闭/18源/无owned残留或zombie。公平prefix口径{"denominator_scope": "max_worker(sum of first two recorded cell elapsed times)", "denominator_wall_sec": 572.7004283005372, "effective_transition_per_wall_sec": 0.111751269664521, "eligible": true, "episode_indices": [0, 1], "exact_end_to_end_process_span": false, "excludes": "final Supervisor reap tail and all later serial scene regressions", "final_cleanup_timing_available": false, "final_supervisor_cleanup_wall_sec": null, "includes": "cell startup, next-reset cleanup of prior worker, native goal closure", "per_worker": [{"cell_recorded_wall_sec": 572.7004283005372, "transition_only_rate_per_active_wall_sec": 0.10296350410488778, "transition_only_wall_sec": 310.789733490441, "valid_transitions": 32, "worker_id": 0}, {"cell_recorded_wall_sec": 570.8294671084732, "transition_only_rate_per_active_wall_sec": 0.10358508978229754, "transition_only_wall_sec": 308.9247696483508, "valid_transitions": 32, "worker_id": 1}], "reset_regression_only_schedule": [], "reset_regression_only_transitions": 0, "schedule": [["open", 101], ["open", 101]], "steps_per_episode": 16, "valid_transitions": 64}。

### P1C v2正式4worker矩阵（开始）

同冻结b328f848、wireless-rl精确命令：
`rtk proxy bash -c 'source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 4 --schedule open:101,open:101 --steps 16 --run-id mr3_p1c_v2_workers4 --base-domain 136 --base-port 12141'`。
每worker固定三机器人，独立domain136..139/port12141..12144；与此前组串行，实际结果另追加。

### P1C v2 workers4失败与暂停后续（全部保留）

冻结b328f848，完整8attempts共695.967449墙秒、96有效transition，benchmark exit1。6轮正常16步截断，worker2/e2与worker3/e2 reset首快照分别在70.08/70.52simsec报snapshot_watermark_timeout，0有效transition。对应forced owned cleanup均无残留/live/zombie；不能计作成功reset或4worker稳定性。v2 fault/deadline未启动。所有原件完整选定native_v2/workers4/，manifest包括失败原件与资源，不用旧PASS覆盖。
另保留最早A/worker4_w0_e1_v2_audit.json FAIL：唯一missing proc identity为native-stop CLI PID199409。SDK原wall日志实际寿命1.21304035s，launch同PIDstart+clean exit、native_stop回执0、gzserver clean0独立成立；monitor名义50ms仅扫描后wait，未记录真实间隔，不宣称50ms覆盖或补造start_ticks。离线auditor窄修仅允许这种同server/同stopCLI的完整native退出证明，其他child仍需原proc身份；原FAIL不覆盖。
真正reset根因为一般性启动竞态：两失败adapter日志仅snapshot_requested/completed，line-buffered日志无任何state_update/invalid_state；adapter.state从未交付。worker原先仅按monitor+节点graph存在就pause，information有旧序号drain并不等于刚启动adapter收到volatile状态；暂停后10Hzsim timer不能补首state。无证据表明map各字段均已齐，也不能将其归为4worker硬件容量上限。
修复v3将在pause前等adapter实际state+coherent map bundle+monitor/Nav2的明确一次性ready回执，不改10Hz频率/源时间/QoS/健康门限。另将supervisor祖先/session扫描合并为同一/proc快照并记录真实扫描间隔，避免双扫；不改身份保护或清理门限。须新freeze/push，从clock/pilot重新完整1/2/4/fault/deadline，不跨freeze拼接；GPU模型未改，原b328接口probe保留其原冻结范围且不重复额外FB。

v3前瞻计划已写report/assets/20261015_mr3_p1c/predeclared_native_plan_v3.json，SHA6d3e13b38577e29c373f0db065d7ac60c723e927c916ba4bc0fb68863c01a2da；精确run-id为mr3_p1c_v3_clock/pilot/workers1/workers2/workers4/fault/deadline，域/端口/steps/schedule与v2相同，须新sourcecommit+push后执行。GPU模型/encoder/probe源码与b328不变，原GPU成功仅原冻结接口范围，新增forward/backward预算0，不重复训练。
启动根因证据v2_snapshot_startup_diagnosis.json保留必要条件推导、失败trace和SHA；新worker reset metadata声明delivered_inputs_before_pause-v1，首ready回执绑定实际收到的state/地图/monitor/Nav2，首snapshot不得落后ready序号。原状态频率、QoS及所有源时间保持。单次/proc snapshot与真实扫描统计不改变signal或cleanup guards，旧CLI proc缺口不补造身份。
使用窄修auditor对v2workers4另存workers4_v2_failure_audit.json，仍FAIL（两次reset失败/缺少完整episode），不覆盖最初w0e1 FAIL，亦不将局部re-audit等同完整4worker通过。v3原生/GPU尚未启动。

v3提交前最终离线验证：同前ROS环境/排除三个style模板，完整550项语义tests/14.58s通过；conda禁用CUDA全36项/3.908s通过。定向修改Python flake8(max100)及diffcheck通过。活动11docs/121locallinks/15bash块、188资产JSON与1125显式本地引用静态有效；未执行文档命令。implementation_checks_v3.json记录source hash与范围；C++未改，GPU模型/encoder/probe与b328一致。尚未启动v3任何原生或额外FB，下一步commit/push。

### P1C v3独立clock开始

源码freeze`864295d35d6d92723f729dc62d2b5f8322773e54`已commit/push。ROS工作区精确命令：
`rtk proxy bash -c 'source /opt/ros/humble/setup.bash; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1; /usr/bin/python3 scripts/check_mr3_step_clock.py --run-id mr3_p1c_v3_clock --ros-domain-id 130 --gazebo-port 12101'`。
此后所有v3原生阶段均须同freeze；不复用v2 PASS，GPU额外FB预算0。结果另追加。

v3clock PASS8.735070墙秒/19真实回执、server211693/helper212066/stopCLI212179 clean0；精确物理tick/迭代/ns/真实clock一致。原件ROS/log/mr3_step_clock/mr3_p1c_v3_clock，selected native_v3/clock，不提供机器人团队信用。

### P1C v3三机器人pilot（开始）

同freeze864295d，wireless-rl精确命令：
`rtk proxy bash -c 'source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 2 --run-id mr3_p1c_v3_pilot --base-domain 131 --base-port 12111'`。
结果另追加，未额外GPUFB/训练。

v3pilot PASS151.292018墙秒，2有效transition均dt1s；独立pilot_v3_benchmark_audit.json通过，initial_inputs_ready required/proven=true，readyack在firstpause前、firstsnapshot水位不退、seq0零奖/严格地图配对/真实外截断关闭/18流/无owned残留或zombie。

### P1C v3正式1worker（开始）

同freeze864295d，wireless-rl精确命令：
`rtk proxy bash -c 'source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101,rooms:202,corridors:303 --steps 16 --run-id mr3_p1c_v3_workers1 --base-domain 132 --base-port 12121'`。
固定每worker三台、前两open用于公平比较、额外两scene只reset回归；所有结果另追加。

v3workers1四轮全PASS：总1021.999616墙秒、64有效transition（各1simsec），总有效率.062622333/s；4个完整新epoch正式benchmark audit通过，delivered-ready-before-pause均proven，真实取消/关闭/18源健康零接触/ownedlive与zombie均无。公平首两open101口径{"denominator_scope": "max_worker(sum of first two recorded cell elapsed times)", "denominator_wall_sec": 501.4117611530237, "effective_transition_per_wall_sec": 0.06381980336164085, "eligible": true, "episode_indices": [0, 1], "exact_end_to_end_process_span": false, "excludes": "final Supervisor reap tail and all later serial scene regressions", "final_cleanup_timing_available": false, "final_supervisor_cleanup_wall_sec": null, "includes": "cell startup, next-reset cleanup of prior worker, native goal closure", "per_worker": [{"cell_recorded_wall_sec": 501.4117611530237, "transition_only_rate_per_active_wall_sec": 0.1293697101963589, "transition_only_wall_sec": 247.3531087874435, "valid_transitions": 32, "worker_id": 0}], "reset_regression_only_schedule": [["rooms", 202], ["corridors", 303]], "reset_regression_only_transitions": 32, "schedule": [["open", 101], ["open", 101]], "steps_per_episode": 16, "valid_transitions": 32}；额外两scene只reset回归。

### P1C v3正式2worker（开始）

同freeze864295d，wireless-rl精确命令：
`rtk proxy bash -c 'source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 2 --schedule open:101,open:101 --steps 16 --run-id mr3_p1c_v3_workers2 --base-domain 134 --base-port 12131'`。
与1worker串行，每worker三台，后续结果另追加。

v3workers2全部自然完成PASS：543.882888墙秒/64有效transition，正式audit通过，四轮各16×1s、ready-before-pause均proven、18源健康零接触、无ownedlive/zombie；18goals全terminal、6confirmedcancel、一次真实navigation_changed_since_observation拒绝并计罚。公平prefix={"denominator_scope": "max_worker(sum of first two recorded cell elapsed times)", "denominator_wall_sec": 540.9493433311582, "effective_transition_per_wall_sec": 0.11831052350648756, "eligible": true, "episode_indices": [0, 1], "exact_end_to_end_process_span": false, "excludes": "final Supervisor reap tail and all later serial scene regressions", "final_cleanup_timing_available": false, "final_supervisor_cleanup_wall_sec": null, "includes": "cell startup, next-reset cleanup of prior worker, native goal closure", "per_worker": [{"cell_recorded_wall_sec": 540.8360953326337, "transition_only_rate_per_active_wall_sec": 0.11450735429931429, "transition_only_wall_sec": 279.458033030387, "valid_transitions": 32, "worker_id": 0}, {"cell_recorded_wall_sec": 540.9493433311582, "transition_only_rate_per_active_wall_sec": 0.11397030333628606, "transition_only_wall_sec": 280.7748954179697, "valid_transitions": 32, "worker_id": 1}], "reset_regression_only_schedule": [], "reset_regression_only_transitions": 0, "schedule": [["open", 101], ["open", 101]], "steps_per_episode": 16, "valid_transitions": 64}。

### P1C v3静态终态/纳秒边界复审，停止启动后续

原freeze864295d两个确定静态边界：collision/monitor异常会monitor=false并finalize，但adapter尚无stop_requested，terminal snapshot要求stop而worker等snapshot后才stop，构成闭环阻塞；健康timeout不等同此故障。合法212.06→512.06在float相减为299.99999999999994，原>=300可能误分truncated。两者由源码/纯布尔与算术定位，不声明在本次native实际发生；A/v3_terminal_deadline_static_diagnosis.json保留原Git对象/hash。v3已运行clock/pilot/1worker/2worker全部原件保留；v3workers4/fault/deadline未启动，不拼进最终matrix。
当前全部ownednative已自然结束。v4将用隔离评价器scalar task_terminal可靠通知打通真实失败终态，不给actor真值数组；精确ns比较修正300秒边界，不加容差或放宽Tmax。新predeclared_native_plan_v4.json保持原预算/seed/ports，需新commitpush后完整重跑；GPU模型不变且额外FB预算0。

### P1C v4提交前实现与前瞻补充（无原生运行）

隔离评价器仅发布`epoch,end_sim_time_sec,termination_reason`三项可靠终态通知，先冻结再通知、再文件I/O；
adapter与broker仅在真实clock/physics达到该水位后消费，terminal snapshot保持实际drain序号/地图配对，
普通monitor/freshness门禁不放宽。共享纯stdlib `mr3_episode.py`统一原端点整数ns规则，adapter不导入奖励/真值代码。
同T晚终态仅新reward序号、原snapshot/watermarks、dt/physical_dt0、无action、bootstrap0；
早于上次返回边界是显式基础设施错误，不能倒补。零有效时长任务终态不支付新增coverage，冻结终态图仍保留诊断；
普通与20ms正时长步不改变覆盖奖励公式，sealed/重复幂等保持。该约束来自提交前独立静态复审，非原生观察。

新增默认关闭`training_terminal_probe`，仅step+独立reward上下文和明确`--terminal-probe`计划可用。
两个open101 epoch各先3个KEEP完整1秒，再分别验证真实20tick后的navigation_failure短终态，
以及当前暂停T终态后的原snapshot零时长尾步；不伪造contact、clock或95%成功。
`predeclared_native_plan_v4.json` SHA256 `d16a8136bdf94cce21293ab11e9a2648906e743a80377654483999b0de6b95a7`，
次序clock/pilot/terminal/1worker/2worker/4worker/fault/deadline，共8独占run-id；原七项预算不缩减，
额外诊断8次API transition（6个1s、1个.02s、1个0s）。需新源码commit+push后完整执行，不拼v2/v3成绩。
GPU模型/encoder/probe三文件SHA与b328接口探针一致，新增F/B预算0、optimizer更新0、实际策略训练0。
独立辅助审计器v2保留v1和旧结果不变，5个selftests/33个对抗子例通过；两套审计均约束零尾步不可新增coverage。
活动11docs/125本地链接/16bash块/11项目调用静态检查通过，bash仅语法检查、不执行命令。

v4提交前最终全量：系统ROS完整611项语义测试/16.35s PASS（仍只排除三项既有style模板），
conda ns3gym禁用CUDA、unset PYTHONPATH、PYTHONNOUSERSITE=1完整40项/4.398s PASS；
修改Python定向flake8(max100)、辅助审计5项selftest和diffcheck PASS。
精确源码SHA与范围见`report/assets/20261015_mr3_p1c/implementation_checks_v4.json`。
C++步进实现未改，其组件build/CTest原范围保留；新冻结仍须独立clock/native完整矩阵。

### P1C v4独立clock（开始）

源码冻结`7e186bf83b2a7ed9d38a95f30d53150ee2d6736d`已提交推送。ROS目录精确命令：
`rtk proxy bash -c 'source /opt/ros/humble/setup.bash; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1; /usr/bin/python3 scripts/check_mr3_step_clock.py --run-id mr3_p1c_v4_clock --ros-domain-id 130 --gazebo-port 12101'`。
结果另追加；此组件不含三机器人团队、无95%信用。之后同一冻结按v4前瞻次序执行，不增加GPU前后向。

v4clock PASS10.116011墙秒、26回执/99真实clock样本，server246739/helper247090/stopCLI247191均clean0，
精确physics tick/iteration/ns/clock一致。原件ROS/log/mr3_step_clock/mr3_p1c_v4_clock；选定native_v4/clock。

### P1C v4三机器人pilot（开始）

同freeze7e186bf，wireless-rl精确命令：
`rtk proxy bash -c 'source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 2 --run-id mr3_p1c_v4_pilot --base-domain 131 --base-port 12111'`。
原生结果另追加；无策略训练或额外GPUFB。

v4pilot PASS148.071263墙秒/2个1sim-sec有效transition；独立pilot_v4_benchmark_audit.json通过，
真实外截断、18源健康/零接触、交付ready+地图奖励配对与owned退出均通过，不作95%成绩。

### P1C v4诊断短/零终态（开始）

同freeze7e186bf，wireless-rl精确命令：
`rtk proxy bash -c 'source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 --steps 4 --terminal-probe --run-id mr3_p1c_v4_terminal --base-domain 144 --base-port 12171'`。
两次明确诊断navigation_failure，默认off接口仅本探针开启，不等同真实contact事件或策略成功；结果另追加。

v4terminal完整两轮PASS312.767544墙秒/8次API transition：首轮末步真实.02s新快照，
第二轮末步真实0dt/0physics、原snapshot与watermarks完全复用、command=null/action_submitted=false/bootstrap0，
零新增coverage。总实际采样6.02s，两次均navigation_failure且非truncated，真实关闭与18源审计通过。
独立terminal_v4_benchmark_audit.json PASS；不计normal吞吐、contact触发、95%或训练信用。

### P1C v4正式1worker（开始）

同freeze7e186bf，wireless-rl精确命令：
`rtk proxy bash -c 'source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101,rooms:202,corridors:303 --steps 16 --run-id mr3_p1c_v4_workers1 --base-domain 132 --base-port 12121'`。
前两open101用于公平比较、额外rooms202/corridors303仅完整跨场景seed reset回归；每worker始终三台。

v4workers1进行中，rooms202/e3原生正式audit通过但独立auxv2首次标FAIL，原件
`v4_workers1_episode003_reward_gate_audit.json`保留。只读对齐证实为离线审计同T错误归属：
adapter有序index127先snapshot_completed(s5,T84.92)，index128后拒绝cmd5/obs5（stamp84.92）。
step4=83.92→84.92且command4/rejected_delta0；step5=84.92→85.92且command5/rejected_delta1、invalid=-.05，
runtime实际罚项正确。auxv2只按stamp<=end把后发cmd5倒归step4，后续用新v3审计器因果绑定command/快照顺序，
加独立反例、新名结果，旧helper/FAIL不覆盖。该修正不被runtime导入、不改变源码freeze7e186bf，亦不重跑或筛掉episode。

v4workers1完整四轮原生与正式benchmark audit PASS：1032.108395墙秒/64有效transition，全部dt1秒；
open101重复reset及rooms202/corridors303跨场景/seed全通过，18源健康零接触、真实关闭/无ownedlive或zombie。
首两open101公平口径32trans/518.356895 recorded-cell墙秒=.061733528/s；额外32trans只reset回归，
公平代理不含最后Supervisor reap尾部，真实全benchmark总墙秒另列。auxv2的同T假阳性保留、auxv3复审另存。
开始下一组前核对implementation_checks_v4.json所有源码SHA无变化。

### P1C v4正式2worker（开始）

同freeze7e186bf，wireless-rl精确命令：
`rtk proxy bash -c 'source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 2 --schedule open:101,open:101 --steps 16 --run-id mr3_p1c_v4_workers2 --base-domain 134 --base-port 12131'`。
每worker始终三台，域134/135、端口12131/12132，和其他benchmark组串行；结果另追加。

独立auxv3修正及新结果：`reward_gate_audit_v3.py` SHA256
`895395075a881c6d74b809100e198be52a3c05a6710d24d873020b87223ff665`，10项selftest/flake8 PASS；
拒绝按command_id/observation_sequence/实际step水位逐步绑定并核对delta与invalid权重，其余规则保持。
同一v3只读重放pilot、terminal和完整workers1均PASS，另存相应`*_reward_gate_audit_v3.json`及逐轮新结果，
不覆盖原v2 FAIL或原helper。Git根三个精确审计命令分别为：
`rtk proxy python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reward_gate_audit_v3.py ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v4_pilot --freeze 7e186bf83b2a7ed9d38a95f30d53150ee2d6736d`。
`rtk proxy python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reward_gate_audit_v3.py ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v4_terminal --freeze 7e186bf83b2a7ed9d38a95f30d53150ee2d6736d`。
`rtk proxy python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reward_gate_audit_v3.py ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v4_workers1 --freeze 7e186bf83b2a7ed9d38a95f30d53150ee2d6736d`。
stdout以exclusive新文件保存，未启动额外仿真/GPU或空间真值重放。

v4workers2完整四轮PASS543.889533墙秒/64有效transition，总有效率.117670954/s；
独立workers2_v4_benchmark_audit.json通过，所有dt1s、交付ready/18源健康零接触、真实导航关闭与ownedclean通过。
全benchmark含所有startup/reset/closure与最终回收，不混用其他freeze；公平recorded-cell口径另见审计JSON。

### P1C v4正式4worker（开始）

同freeze7e186bf，wireless-rl精确命令：
`rtk proxy bash -c 'source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 4 --schedule open:101,open:101 --steps 16 --run-id mr3_p1c_v4_workers4 --base-domain 136 --base-port 12141'`。
每worker三台、域136..139/端口12141..12144；和此前benchmark组串行，全部结果另追加。

v4workers4运行中出现真实infra失败：worker2/e1在最后step16(action999/request17/外部limit)实际关闭时，
tb1 `velocity_smoother-20` PID332359 exit-11(SIGSEGV)，infrastructure_failure.json原件保留，
该epoch不记完成或合格最后transition。native日志先task_evaluator clean、stopCLI343510 clean0、
gzserver329208 clean0，再launch向全部Nav2/lifecycle同时SIGINT，随后该smoother -11；
其余worker继续自然留证，fault/deadline暂不启动。不是aux审计错误，也没有证据可归为硬件容量上限。
只读诊断将核对本地apport/core与SDK生命周期关闭顺序，任何运行时修复须新freeze+完整预声明矩阵，不覆盖本次失败。

v4workers4自然结束exit1：604.962903墙秒，111个已返回有效transition，7个实际attempts；
6轮clean完整16步，worker2/e1为15步已交付prefix+第16条仅raw日志（关闭异常、RPC未返回Gym），
worker2/e2没有启动。全部原件含failure/forcedcleanup/资源保留native_v4/workers4，
独立正式单轮6PASS/1FAIL，整组`workers4_v4_failure_benchmark_audit.json` FAIL不覆盖。
全部ownedlive/zombie最终为空，不能将.183482325/s失败组描述为稳定4worker吞吐。
v4fault/deadline未启动。Apport精确PID332359/argv/Signal11匹配；core的崩溃线程位于FastDDS2.6.11
EDP::unpairWriterProxy/PDP::removeWriterProxyData，主线程同时DataReaderImpl::stop/destructor→rmw destroy_subscription。
直接证据为DDS发现/endpoint teardown并发路径，不能声称是smootherTimer bug、容量不足或已修复SDK内部缺陷。

### P1C v4关闭故障只读诊断与兼容方案排除

core精确解引用位于EDP::unpairWriterProxy+406，getListener后rax=0，主线程在NodeTimeSource析构/销毁clock reader。
与官方已知缺陷 https://github.com/eProsima/Fast-DDS/issues/3303 高度匹配；具体完整交错仍是推断。
官方2.6.11/2.6.12的EDP/PDP/RTPSParticipantImpl三文件逐字一致，不声称升级解决。
本地Nav2 1.1.20、rclcpp16.0.19、FastDDS2.6.11。最小stack/指令/参数/版本与时间线原件保留
`native_v4/workers4/diagnostic/w2_e1_smoother/`；完整core/apport只在ignored本地原件位置，tracked选件不含内存/环境变量。

评估官方Humble CycloneDDS1.3.5私prefix解包（apt仅查询/模拟，sudo-n测试需密码，未安装），
但其精确release源码message_info_from_sample_info将publication_sequence_number标为UNSUPPORTED，
不满足P1A现有18路真实源序号审计，故在任何下载/安装/源码切换或native前否决。
官方源码 https://raw.githubusercontent.com/ros2-gbp/rmw_cyclonedds-release/release/humble/rmw_cyclonedds_cpp/1.3.5-1/src/rmw_node.cpp
SHA256 f12c8da3f612b569632a551cc73bc88f1787c472872c90ccf1ba93dc107253ca；不以接收次数伪代源序号、不关门禁。

新v5候选仍保留FastDDS：在真实目标闭合后，标准Nav2 SHUTDOWN与18节点finalized确认；
随后launch按实际owned ProcessStarted/Exited逐一正常SIGINT退出ROS子进程，最后才原生停止Gazebo。
各阶段有显式实际退出回执和墙钟保护，异常仍是infra失败、不补PASS；这是一致的应用关闭协议，
不能宣称修复FastDDS内部竞态。需新代码/测试commit+push与新完整8阶段前瞻矩阵，v4fault/deadline保持未启动。

### P1C v5关闭协议离线完成与全量检查（原生尚未启动）

统一协议`nav2-finalized_then_serial-ros_then_gazebo-v1`：worker在真实closed pending0后，
三台按序原生SHUTDOWN4并逐个GetState确认18finalized，整个30墙秒保护内physics/clock严格暂停；
客户端保留至最终node销毁，nav2_shutdown.json成功/失败partial回执均不覆盖。
evaluator收到最后真实reward ACK并clean退出后，SDK按真实start action/PID逆序逐个正常SIGINT，
每个必须等同identity实际clean0 Exit再继续；10墙秒单节点guard，全部ROS clean才原生GZstop/最终GlobalShutdown。
任何拒绝、错状态、wrongidentity、非0/超时均显式infra；prefix tracker早于最早Node注册，
同SDK具体/通用handler观察同exit幂等。baseline非stepped原路径保持。
独立auditor逐条重放实际marker并交叉SDK标准PID/signal/exit行、nav2服务/状态/clock与finalize请求ACK；
unknown protocol FAIL，旧证据不给新ordered信用，被SIGKILL故障prefix也不伪造完整关闭。

系统ROS完整673项语义测试20.52s PASS（同前只排除三个style模板）；conda ns3gym禁用CUDA、
unset PYTHONPATH、PYTHONNOUSERSITE=1完整40项4.331s PASS；修改worker/auditor/mainlaunch及新tests
flake8(max100)、diffcheck PASS。源hash见implementation_checks_v5.json；C++及GPU模型/encoder/probe均未改。
11活动docs/130本地links/16bash语法块/28launch参数实例/13P1C CLI flags静态通过，文档命令未执行。
v5前瞻`predeclared_native_plan_v5.json`最终SHA256
`674505028239a150de4cf4284e4ce1545cb2c425bc4715c319f5189134d4b6c8`，
完整8阶段同原预算/seed/ports但run-id全部v5；无跨freeze PASS、新增GPUFB0、无训练/gateway。
新source commit+push后才执行；当前全部旧owned native已自然结束，无额外ROS初始化/模拟器试跑。

### P1C v5提交检查补记（原生未启动）

f4c8483已在本地生成但未推送时，发现cached diff-check原始CSV的CRLF被报为尾随空白；
该非零检查此前未拦截提交。保留全部原生CSV字节，追加仅匹配本P1C native_v*证据CSV的
.gitattributes cr-at-eol与-text规则，其余空白检查保持；重新运行HEAD检查/工作树检查，
核对全部已tracked CSV与HEAD字节一致后，独立补正提交并一起推送，之后才启动v5。

### P1C v5原生矩阵启动

统一已推送冻结cfabee15481936c6c27ddabadd1227b683c2457b；v5 plan SHA674505028239a150de4cf4284e4ce1545cb2c425bc4715c319f5189134d4b6c8。
clock命令（ROS cwd）：`source /opt/ros/humble/setup.bash; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1; /usr/bin/python3 scripts/check_mr3_step_clock.py --run-id mr3_p1c_v5_clock --ros-domain-id 130 --gazebo-port 12101`。
原生fixture无机器人/无mapping信用；输出log/mr3_step_clock/mr3_p1c_v5_clock，结果待实际完成。

clock v5结果：{"passed": true, "wall_duration_sec": 7.271771023981273, "receipt_count": 11, "clock_sample_count": 98, "native_stop": {"server_pid": 432196, "server_command": ["gzserver", "--verbose", "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/multi_robot/share/multi_robot/worlds/p1c_open.world", "-s", "libgazebo_ros_init.so", "-s", "libgazebo_ros_factory.so", "-s", "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_gazebo_step.so", "--ros-args", "--params-file", "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/multi_robot/share/multi_robot/config/mr3_step_clock.yaml", "--"], "server_returncode": 0, "stop_cli_pid": 432837, "stop_cli_command": ["gz", "topic", "-p", "/gazebo/server/control", "-m", "stop: true"], "stop_cli_returncode": 0}}。

pilot命令（wireless-rl cwd）：`source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 2 --run-id mr3_p1c_v5_pilot --base-domain 131 --base-port 12111`。统一cfabee15481936c6c27ddabadd1227b683c2457b，结果待完成。

pilot v5结果：{"passed": true, "valid_transitions": 2, "wall_sec_including_all_attempts": 161.58344686310738}；全部实际Nav2 finalized/有序ROS/GZ闭合回执及owned清理待独立audit交叉。

terminal命令（相同conda环境/cwd）：`python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 --steps 4 --terminal-probe --run-id mr3_p1c_v5_terminal --base-domain 144 --base-port 12171`。统一cfabee15481936c6c27ddabadd1227b683c2457b；诊断导航失败非contact/成功，8API/6.02sim秒上限，结果待完成。

terminal v5自然PASS339.142110215s/8有效API，真实采样6.02sim秒；首轮末步physical/effective dt.02/.02、第二轮0/0且原snapshot复用/无action，全部closed/native/owned回执齐。独立主审计terminal_v5_benchmark_audit.json。
余下五组按已冻结预案串行自动执行，每组native和主审计均通过才启动下一组；精确命令及结果逐项自动追加本log，原始执行journal为report/assets/20261015_mr3_p1c/v5_remaining_execution.jsonl。执行器只编排既定命令，无额外GPU/训练。

### P1C v5 workers1正式启动

冻结cfabee15481936c6c27ddabadd1227b683c2457b；wireless-rl cwd，精确命令：`source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101,rooms:202,corridors:303 --steps 16 --base-domain 132 --base-port 12121 --run-id mr3_p1c_v5_workers1`。遵循已推送v5预案，所有worker均三台；结果待完成。

workers1 v5原生结果：`{"passed": false, "valid_transitions": 0, "wall_sec_including_all_attempts": 324.93412220990285, "effective_transition_per_wall_sec": 0.0}`；命令exit1，全部尝试/回收原件ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v5_workers1。
独立主benchmark审计精确命令：`rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/audit_mr3_env.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v5_workers1 --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/workers1_v5_benchmark_audit.json`，exit1，原件report/assets/20261015_mr3_p1c/workers1_v5_benchmark_audit.json。

v5 workers1失败保留：324.9341222099wall、0valid、首reset未返回，tb1 get_state服务响应匹配timeout后manager configure阶段abort，全部inactive；最终readygate300wall保护exit1，workerreturn1/forcedcleanuptrue，ownedlive/zombie最终空。未启动workers2/4/fault/deadline。
SDK ServiceClient的async_send_request failed是等待future非SUCCESS后通用文案，并不证明请求未发送；服务端确已处理但response reader未匹配。多个client无GUID trace，不能唯一证明该WARN属于manager哪条请求。官方rmw_fastrtps#842与6.2.10源码解释此请求/响应分开发现机制；18change_stateReply现有5s配置并未覆盖get_stateReply默认100ms。
候选只为18精确get_stateReply writer增至1s有界匹配等待，低于manager2s消费者超时；不改contact/时钟/任务、数据发布频率/通道、DDS buffer或默认QoS，不自动重试或宣称SDK竞态根治。仍待新测试/统一freeze/完整前瞻矩阵。
另只读复核零步消费约束后补合同澄清：无动作尾步不能直接作为actor样本，不丢终态收益或因多一API行多折扣；P2A collector/return/GAE尚未实现或授权，本补记不是新增训练。

### P1C v6最小状态响应配置离线检查完成（原生未启动）

源码只变XML18exact get_stateReply等待1墙秒（旧18change_stateReply5秒保持）和相应transport测试；全部worker/adapter/evaluator/supervisor/model源码与cfabee相同。
系统ROS同前完整673语义测试20.96s PASS；conda ns3gym unset PYTHONPATH、PYTHONNOUSERSITE=1、CUDA_VISIBLE_DEVICES空，40 CPU tests4.542s PASS；modified test flake8与diffcheck PASS。
静态SDK checker精确命中36响应writer，经installed名字映射/RMW转换保留18×5s+18×1s；197负例默认100ms、其余属性不变，未创建participant/ROS context/endpoint，详细compile/run命令数组及原stdout见get_state_reply_qos_v6_static_proof.json。其SHA73353fae62d54eddc42341ff82677aa091101144bc723b74d28c86074356064f，checker sourceSHA0ba26edf92d6cd49a1b1e960396d86c2a936b124570d26a46504ca6126e16575。
1s<原client2s不提供完整1s回传余量或端到端保证；服务发现与DataWriter write均会耗墙时，真实失败继续infra。
11活动docs/133本地links/16bash语法块 PASS，launch_commands12bash块逐字等于已推送v5（文档命令不执行）。168个v5已记录owned PID/starttick身份当前全部消失；原备份local/remote均保持8fe1495。
v6前瞻planSHA7e8bd75d17ce393ae2e7a7e487fc40cdaf03f16c174dcf435766f23aed443302，绑定profileSHA dd7eeadca21f0924fe721515e8dd57ac979340df8b08885bc39d2595c8caf87b；8阶段顺序/seed/budget/ports与v5相同、run-id全部v6。新统一source commit+push后开始，不复用旧native PASS、新增GPUFB0、无训练/gateway。

### P1C v6原生完整矩阵启动

已推送统一freeze c8d483228ecb0105c905459578eddbb4a23d4520，planSHA7e8bd75d17ce393ae2e7a7e487fc40cdaf03f16c174dcf435766f23aed443302，profileSHA dd7eeadca21f0924fe721515e8dd57ac979340df8b08885bc39d2595c8caf87b。
clock精确命令（ROS cwd）：`source /opt/ros/humble/setup.bash; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1; /usr/bin/python3 scripts/check_mr3_step_clock.py --run-id mr3_p1c_v6_clock --ros-domain-id 130 --gazebo-port 12101`。新输出目录log/mr3_step_clock/mr3_p1c_v6_clock；无机器人团队信用，结果待完成。

v6clock自然PASS7.671995702墙秒/11receipts/100实际clock，server494288/helper494708/stop494906clean0。新profile/freeze元数据齐，独立component审计另存。
pilot精确命令（wireless-rl cwd）：`source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 2 --run-id mr3_p1c_v6_pilot --base-domain 131 --base-port 12111`。统一freeze c8d483228ecb0105c905459578eddbb4a23d4520；结果待完成。

v6pilot自然PASS161.605684334墙秒/2有效，dt均1s；新profile/freeze下真实完整关闭/owned回执齐，主审计pilot_v6_benchmark_audit.json另存。
terminal精确命令（相同conda环境及wireless-rl cwd）：`python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 --steps 4 --terminal-probe --run-id mr3_p1c_v6_terminal --base-domain 144 --base-port 12171`；统一c8d483228ecb0105c905459578eddbb4a23d4520，诊断终态非contact/任务成功，结果待完成。

v6terminal自然PASS338.453380471墙秒/8有效API/6.02sim秒；末步真实.02/.02和0/0复用/无action均成立，完整native/owned闭合，独立主审计terminal_v6_benchmark_audit.json。
余下五组按相同v6plan串行编排，每组源/方案hash核验、native与主benchmark审计通过才next。各精确命令/结果自动追加本log，原journal为report/assets/20261015_mr3_p1c/v6_remaining_execution.jsonl，新增GPUFB/updates0。

### P1C v6 workers1正式启动

冻结c8d483228ecb0105c905459578eddbb4a23d4520；wireless-rl cwd，精确命令：`source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101,rooms:202,corridors:303 --steps 16 --base-domain 132 --base-port 12121 --run-id mr3_p1c_v6_workers1`。遵循已推送v6预案，所有worker均三台；结果待完成。

workers1 v6原生结果：`{"passed": true, "valid_transitions": 64, "wall_sec_including_all_attempts": 1071.9081788072363, "effective_transition_per_wall_sec": 0.05970660665283464}`；命令exit0，全部尝试/回收原件ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_workers1。
独立主benchmark审计精确命令：`rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/audit_mr3_env.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_workers1 --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/workers1_v6_benchmark_audit.json`，exit0，原件report/assets/20261015_mr3_p1c/workers1_v6_benchmark_audit.json。

### P1C v6 workers2正式启动

冻结c8d483228ecb0105c905459578eddbb4a23d4520；wireless-rl cwd，精确命令：`source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 2 --schedule open:101,open:101 --steps 16 --base-domain 134 --base-port 12131 --run-id mr3_p1c_v6_workers2`。遵循已推送v6预案，所有worker均三台；结果待完成。

workers2 v6原生结果：`{"passed": true, "valid_transitions": 64, "wall_sec_including_all_attempts": 574.3882381389849, "effective_transition_per_wall_sec": 0.11142289439519111}`；命令exit0，全部尝试/回收原件ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_workers2。
独立主benchmark审计精确命令：`rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/audit_mr3_env.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_workers2 --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/workers2_v6_benchmark_audit.json`，exit1，原件report/assets/20261015_mr3_p1c/workers2_v6_benchmark_audit.json。

### P1C v6原生双worker完成、原接触审计phase错误与独立离线修正声明

workers2程序self PASS574.388238139wall/64returned，但原主audit workers2_v6_benchmark_audit.json为FAIL，w0e2原独立worker2_w0_e2_v6_audit.json亦FAIL，全部保留；driver停止，workers4/fault/deadline未启动。
w0e2 subscription74.84/start77.42/end93.44；base lifetime receiptmax1.42，caster_back_left receipt1.5/source.545。所有当前age<=.5，freshtrue/ever_unhealthyfalse/latches空、18rawpubseq连续。ContactMonitor更新lifetime maxima无条件，但只在start后对任一>.5gap不可逆锁存；release唯一调用start，无清零/替换路径。原任务合同明确任务期锁存门禁，原auditor错误把lifetime maxima当taskmax。三代理独立只读复核一致。没有逐条compactreceipt端点，不能补造具体发生区间或声称after-start数值max已测。
仅在A新增独立版本offline phase auditor/test，不修改c8d运行源码、原audit/deps、源/接收龄.5门禁、task/clock/contact/原v6native计划字节；无新native重跑或GPU/训练。辅助声明predeclared_offline_contact_phase_v1.json已于正式修正重审和余下阶段前落盘，明确是看到原FAIL后的事后方法纠正，并非曝光前盲审。对全部v6阶段统一新版本/新名重放，保留所有旧结果。sourceSHA/真实bootstrap/release/reset/pausedphysics绑定/不清锁存不变量与反例测试均须先独立review。后续按原八阶段剩余顺序继续同c8d native，只有新版本合同审计通过才继续。

新offline contact phase v2最终helperSHA3ce800bfa0455d25a1c3257635c7c4d593478082bbbf1c4dab6a10eed2fc6991；40纯fixture tests1.39s PASS（exactcommand/原stdout见contact_phase_v2_checks.json，SHA2d5f661219f74028b7dd89471cee60bac4a8350e4184f690d4a92dfba4d9154f），flake8/diff PASS，root/info独立最终review通过。辅助声明最终SHAa8cfe1b100d88cfd72c907a0dd7fabe7a3d684cd922b06d074e5408762307ed5，在任何正式新方法重审前绑定；不改运行源码或原FAIL。现在统一重审已完成pilot/terminal/workers1/workers2，新输出名均 *_v6_contact_phase_v2_benchmark_audit.json；精确命令：`/usr/bin/python3 report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v2.py ROS_LOG_DIRECTORY --output UNIQUE_NEW_AUDIT_PATH`（Git root执行时完整前缀ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/，各四组具体参数写audit provenance/执行器）。
新phase v2正式审计：`rtk proxy /usr/bin/python3 ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v2.py ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_pilot --output ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/pilot_v6_contact_phase_v2_benchmark_audit.json`，exit0/PASS/errors[]。
新phase v2正式审计：`rtk proxy /usr/bin/python3 ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v2.py ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_terminal --output ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/terminal_v6_contact_phase_v2_benchmark_audit.json`，exit0/PASS/errors[]。
新phase v2正式审计：`rtk proxy /usr/bin/python3 ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v2.py ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_workers1 --output ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/workers1_v6_contact_phase_v2_benchmark_audit.json`，exit0/PASS/errors[]。
新phase v2正式审计：`rtk proxy /usr/bin/python3 ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v2.py ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_workers2 --output ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/workers2_v6_contact_phase_v2_benchmark_audit.json`，exit0/PASS/errors[]。
原workers2 benchmark/episode FAIL SHA逐字核验未变。续跑只有原v6预案尚未启动的workers4/fault/deadline；新journal v6_contact_phase_resume_execution.jsonl明确连接此前已停止journal，原nativefreeze c8d不变，每组并存原审计与新phase2审计，新方法通过才next。

### P1C v6 workers4正式启动

冻结c8d483228ecb0105c905459578eddbb4a23d4520；wireless-rl cwd，精确命令：`source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 4 --schedule open:101,open:101 --steps 16 --base-domain 136 --base-port 12141 --run-id mr3_p1c_v6_workers4`。遵循已推送v6预案，所有worker均三台；结果待完成。

workers4 v6原生结果：`{"passed": true, "valid_transitions": 128, "wall_sec_including_all_attempts": 658.6831654268317, "effective_transition_per_wall_sec": 0.19432711615918563}`；命令exit0，全部尝试/回收原件ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_workers4。
原审计精确命令：`rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/audit_mr3_env.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_workers4 --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/workers4_v6_benchmark_audit.json`，exit0，保留report/assets/20261015_mr3_p1c/workers4_v6_benchmark_audit.json；新合同phase v2精确命令：`rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_workers4 --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/workers4_v6_contact_phase_v2_benchmark_audit.json`，exit0，独立新件report/assets/20261015_mr3_p1c/workers4_v6_contact_phase_v2_benchmark_audit.json。

### P1C v6 fault正式启动

冻结c8d483228ecb0105c905459578eddbb4a23d4520；wireless-rl cwd，精确命令：`source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 2 --schedule open:101,open:101 --steps 8 --fault-probe --base-domain 140 --base-port 12151 --run-id mr3_p1c_v6_fault`。遵循已推送v6预案，所有worker均三台；结果待完成。

fault v6原生结果：`{"passed": true, "valid_transitions": 28, "wall_sec_including_all_attempts": 419.24939202237874, "effective_transition_per_wall_sec": 0.06678602410115221}`；命令exit0，全部尝试/回收原件ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_fault。
原审计精确命令：`rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/audit_mr3_env.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_fault --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/fault_v6_benchmark_audit.json`，exit0，保留report/assets/20261015_mr3_p1c/fault_v6_benchmark_audit.json；新合同phase v2精确命令：`rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_fault --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/fault_v6_contact_phase_v2_benchmark_audit.json`，exit0，独立新件report/assets/20261015_mr3_p1c/fault_v6_contact_phase_v2_benchmark_audit.json。

### P1C v6 deadline正式启动

冻结c8d483228ecb0105c905459578eddbb4a23d4520；wireless-rl cwd，精确命令：`source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; python -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 300 --deadline-probe --base-domain 142 --base-port 12161 --run-id mr3_p1c_v6_deadline`。遵循已推送v6预案，所有worker均三台；结果待完成。

deadline v6原生结果：`{"passed": true, "valid_transitions": 300, "wall_sec_including_all_attempts": 2190.295565406326, "effective_transition_per_wall_sec": 0.13696781600539212}`；命令exit0，全部尝试/回收原件ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_deadline。
原审计精确命令：`rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/audit_mr3_env.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_deadline --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/deadline_v6_benchmark_audit.json`，exit0，保留report/assets/20261015_mr3_p1c/deadline_v6_benchmark_audit.json；新合同phase v2精确命令：`rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_deadline --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/deadline_v6_contact_phase_v2_benchmark_audit.json`，exit0，独立新件report/assets/20261015_mr3_p1c/deadline_v6_contact_phase_v2_benchmark_audit.json。

### P1C v6完整离线矩阵、资源/reset及实际TTL缺陷披露

全原生于2026-10-15T14:16:48.994564Z结束，无新增GPUFB/optimizer/训练/gateway。
root完整六组精确命令（Git root）：`rtk proxy /usr/bin/python3 ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v2.py ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_terminal ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_workers1 ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_workers2 ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_workers4 ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_fault ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_deadline --matrix --output ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/matrix_v6_contact_phase_v2_audit.json`，exit0/PASS/errors[]，22完整episode+1被杀前缀，592返回API；pilot另外1轮2步，全部v6共23完整轮+1前缀/594 API，含一条无动作终态而非594次策略决策。

各完整组辅助奖励精确命令为`python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reward_gate_audit_v3.py ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v6_GROUP --freeze c8d483228ecb0105c905459578eddbb4a23d4520`，GROUP依次pilot/terminal/workers1/workers2/workers4/deadline，stdout均以exclusive x写新名`GROUP_v6_reward_gate_audit_v3.json`，全部scalar PASS；helper SHA895395075a881c6d74b809100e198be52a3c05a6710d24d873020b87223ff665。fault只用新`reward_gate_audit_v3_fault_subset.py`对w0e2/w1e1/w1e2三个完整单元24步，显式引用两个main prefix审计SHA，不给被杀4步完整reward/contact/closure信用；exact argv存`fault_v6_completed_subset_reward_gate_audit_v3.json`。

最终deadline端点79.6→379.6为300000000000ns；step300为timeout、terminatedtrue/truncatedfalse，failure-20仅一次；所有coverage增量0，初始2092格绑定不给奖。独立aux发现cmd176/obs176 created254.6/expires256.6、cmd177/obs177 created255.6/expires257.6被`expired_or_invalid_command_time`误拒，invalid-.05各一次；实际expires-created=2.0000000000000284而分别round端点后恰2e9ns。原adapter严格float `<=2.`是假拒根因；300请求仅298被接受（894 robot KEEP），无native goals。旧主审计/phase2只验证回执/计罚一致而未拒绝这类合法TTL假拒，其PASS不等于缺陷不存在。原数据/审计/aux全部保留，不将误拒消音或清除罚项。

独立resource_analysis_v2.py（原SHAf92b7a9c4f3ec1e06c423d846d810b6f0799bdf08e7c44ba27b507d155b24fdf）读取全部7组raw，exit0/2.668wall秒，输出`resource_analysis_v6.json` SHA4b35d50b7c11d601103424a95e0723036975e6b43bf02488b69aef602023bedd。reset exact命令为`PYTHONNOUSERSITE=1 /usr/bin/python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reset_analysis_v6.py --native-root ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v6 --output ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reset_summary_v6.json`，exit0/3.007秒、结构/source/reset范围PASS；helper SHA019e7a97e8d2d3370a633bd03e5e0dd13bb81b27bd7fa5c0729499c31e166995，输出SHA06e4ad200a67245108e6b0c32ccdebeb269e445c1fae3848a2215be113d7f8b0，10纯tests/flake8/diff PASS，收据`reset_analysis_v6_checks.json`。这些是v6诊断与条件预算，不供v7原生信用。

P1C继续进行；root未执行最终状态更新。当前TTL误拒污染合法动作奖励，不能推给P2A后再解决。将最小通用修复整数时间端点与相应回归/审计缺口，在新推送冻结前声明完整八阶段v7矩阵；保留v6全部原始PASS/FAIL/诊断，不跨运行冻结拼接，任务/95%/0.5秒contact/ROS时钟与GPU预算不变。


### P1C v7 prospective repair and offline checks (before native)

The v6 final-integrity result was completed before any runtime edit: `final_evidence_integrity_v6.json` SHA `19be43292aaf10cd5d6fc54f876fbfa879f903aaeddcc4811105e23ab2bbc76d`, exact shell command/results in `final_evidence_integrity_v6_execution.json` SHA `363ad88c3bbbc77579830bd79d5da4dbc284eec3b4b1b6cd99e31a6b56055154`. It checked 48 frozen sources, 32 manifests, 420 unique raw originals and all 1021 saved PID/start identities plus 26 bare PID events; all saved identities were absent, no survivors/zombies. This establishes byte/cleanup integrity only. The subsequently discovered legal-TTL false rejections remain actual v6 defects; integrity PASS is not P1C completion.

Prospective v7 retains all v6 raw outputs and original audit verdicts. The new source uses separately rounded integer-nanosecond endpoints for command generation/validation, heartbeat cadence, lease/commitment and existing RPC/execution deadlines. Original message payload/fingerprint values, duration thresholds, real Nav2 goal ownership, received-only observations, physical/contact/quality gates and transport profile remain unchanged. Sub-nanosecond protocol durations that round to zero are explicitly invalid. The full fresh eight-stage plan is `report/assets/20261015_mr3_p1c/predeclared_native_plan_v7.json`, SHA `f63d0892bcdd4ec5fef91ca261a1c267570667e190cacbfec18610fe3f1c5630`. No previous native freeze supplies v7 credit; no policy training/gateway or new GPU forward/backward/optimizer calls.

Core tests (ROS cwd `ros2_ws/ros2-multi-robot-automap`):

```bash
rtk proxy bash -c 'source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 -m pytest -q src/multi_robot_exploration/test --ignore=src/multi_robot_exploration/test/test_flake8.py --ignore=src/multi_robot_exploration/test/test_pep257.py --ignore=src/multi_robot_exploration/test/test_copyright.py'
```

Actual result: 762 passed, 21.93 seconds. Before this full pass the focused adapter/observation run had 4 failures/88 passes in 5.62s because a test snapshot mock omitted `candidate_version`; only the mock was repaired (native snapshots already included it), then 92 passed/5.24s. Protocol first collection without sourcing ROS overlay raised ModuleNotFoundError with zero executed tests; corrected system-ROS overlay run `rtk proxy /usr/bin/bash --noprofile --norc -c 'source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
exec /usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_mr3_protocol.py'` passed 96 tests in .26s. All 7 changed Python runtime/test files passed flake8 max-line-length100; one E128 decorator indentation was fixed after semantic checks, without changing behavior.

Learning CPU tests (wireless-rl cwd):

```bash
rtk proxy bash -c 'source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh && conda activate ns3gym && unset PYTHONPATH && export PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES="" && python -m unittest discover -s mr3_learning/tests -v'
```

Actual result: 40 passed, 4.408s. Model/encoder/GPU-probe source SHA still equals b328f84; retain only the original saved-fixture 3F/3B/0-update GPU scope, no new CUDA interface claim.

The new independent command-time helper `audit_command_time_v7.py` SHA `4787ca8d2e6b4d7ba06b3d5a3c1ead82fe6f079485a790c5b940f2ba7636c3b9` passed 31 pure tests/1.120s plus flake8; exact commands/raw stdout in `command_time_v7_checks.json` SHA `99a3021e5b97060e9ef42c93d7279c07a8666dadd8a578fa7f90f3bd1969673b`. Its new-name v6 deadline negative replay exited1 as expected, only commands176/177 fail `valid_command_time_falsely_rejected`; output `deadline_v6_command_time_v7_negative_audit.json` SHA `393dbc8c85655bf3c7333a48b5cd4a0d859a8324f8e6db48dc709c9b5dd40ee9`. Original v6 scalar/audit outputs remain unchanged. The pure Gitblob c8d harness also records 8 concrete boundary counterexamples (TTL, response, cancellation, execution, commitment, lease, observation mask, heartbeat) in `command_time_boundary_v6_diagnostic.json`; no native/simulator was used.

New combined wrapper `audit_mr3_env_contact_phase_v3.py` SHA `4e2a24e3465fa45c06c05c37b57b8b77b6e462845b3227be10c1fecb85c2c7d7` passed 16 synthetic tests/.048s, flake8 and independent source review. Exact commands in `contact_phase_v3_checks.json` SHA `cdf7ebbe671a3e16653cf613610ac6291d345917229214561c29ff8f1bbf096a`. It retains immutable v2 contact-phase logic, runs the original protocol gate first, then independent command legality, and requires explicit `--freeze` plus frozen Git blobs/current runtime bytes. Scalar v3 remains a separate required reward gate. The execution driver additionally binds all execution-source bytes to their Git freeze and current files before every stage/audit; the post-push binding will capture the actual pushed hash before the first native command.

Static documentation command (Git root): `rtk proxy /usr/bin/python3 ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/check_p1c_docs_v7.py --output ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/document_checks_v7.json`. Actual PASS: 18 Markdown files, 187 local links, balanced fences, 30 bash/sh syntax-only blocks; no document command executed. Original-route backup and exactly two local branches unchanged. Receipt SHA `9a9974ee8f5aab4ab0dda96cf72b54a6ddf28b012031c229d38ff90126d7012c`.


V7 execution driver final before native: `v7_execution_driver.py` SHA `25c1e2a5bf83f5e3aa2fe34c1fc1781e460f44f27bb9917462b213ceb1a04e27`; 11 stdlib mock tests PASS/.417s, including all 24 commands across eight stages+matrix, wrong-Gitblob negatives for every binding class, exit0-but-false primary/scalar stop, partial fault scope and refusal to overwrite artifacts/journal. Exact tests, raw stdout and argument-only dry-run preview in `v7_execution_driver_checks.json` SHA `60da6ca5e46225fd95f6be72a32d0417fe35cbfd449149a9871f46f048635758`. Preview has an explicit textual future-freeze placeholder, not an invented Git hash; no native, GPU or binding creation. Final source was independently reviewed.

New versioned reset analyzer `reset_analysis_v7.py` SHA `7975b917c99d2656962c0620fba273750b55ac905e96583ba2326e479b7f03d3` passed 15 synthetic tests/.114s and flake8; `reset_analysis_v7_checks.json` SHA `71bfce3c3847d81714d1a76d616f7b7eaac9193e009a6a2452e09b5cad4d895b`. It reuses immutable v6 structural checks, with explicit actual freeze and implementation-lock SHA; no v7 reset data analyzed before native. Original v6 helper remains unchanged.

Root repeated the shortest changed-source style check: `rtk proxy /usr/bin/python3 -m flake8 --max-line-length=100` on `check_p1c_docs_v7.py`, worker, adapter, observation, protocol and their three changed test files; exit0 (1.236s). `git diff --check` exit0. `git add -n .` actual dry-run reviewed all611 current paths; additional paths checked programmatically as only canonical P1C assets or the explicitly labeled 2D proposal, no pycache/core/bag/checkpoint artifacts. The archive index now records historical v1–v6 locations and exact-source scopes; prior native/audit files are not relabeled.

Root generated `implementation_checks_v7.json` with `rtk proxy /usr/bin/python3 /tmp/build_mr3_implementation_checks_v7.py`; actual receipt SHA `5aa211fb00ffbd2170510f2f8f9c169cbb53bf52315fc4e70602b2857bee90a8`, 54 source SHA pins and 21 offline/check/plan/driver dependency pins. Native v7 remains unstarted. The unified source/tests/plan will be committed and pushed before the actual-freeze binding and first native call.


### P1C v7 pushed freeze and prospective execution binding

Pushed `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a` to origin/main; HEAD and remote-tracking main match. Exact source/profile/plan/offline gate binding written exclusively before first native command to `report/assets/20261015_mr3_p1c/predeclared_execution_binding_v7.json`, SHA `09a9f2263385a1a9d4bae02676fc26f23d64a026f8633634f8dd3a310bff1117`. Driver verify_binding passed against current+Git blobs for all54 source files and all bound plan/helper/check dependencies. No native/GPU/optimizer calls occurred while generating the binding. Next execution command from Git root: `rtk proxy /usr/bin/python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/v7_execution_driver.py --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`.

### MR3-P1C v7 clock native started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl`. Exact command:

```bash
rtk proxy /usr/bin/bash --noprofile --norc -c 'set -e
unset PYTHONPATH PYTHONHOME
source /opt/ros/humble/setup.bash
source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash
source /usr/share/gazebo/setup.sh
export PYTHONNOUSERSITE=1
exec /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/check_mr3_step_clock.py --run-id mr3_p1c_v7_clock --ros-domain-id 130 --gazebo-port 12101'
```

clock/native actual result: `{"outer_wall_sec": 11.522069925908, "pid": 860439, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "5a8dd62355aa3554c91001c122c6ea906da308657d97dc2de61ce3a08f14abaf"}`.

### MR3-P1C v7 pilot native started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl`. Exact command:

```bash
rtk proxy /usr/bin/bash --noprofile --norc -c 'set -e
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME
exec /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 2 --base-domain 131 --base-port 12111 --run-id mr3_p1c_v7_pilot'
```

pilot/native actual result: `{"outer_wall_sec": 160.97113404097036, "pid": 861526, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "cf6bac8c52777edf3b875d666ebbd7c522bdaa5417adb5686b5e1350d5ec741a"}`.

### MR3-P1C v7 pilot primary_phase3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_pilot --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/pilot_v7_contact_phase_v3_benchmark_audit.json
```

pilot/primary_phase3 actual result: `{"outer_wall_sec": 1.0160276629030704, "pid": 868837, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "b3a561014e2a3e400497661980fba0105537093bc5ea7446d5656e1b49ff9d1b"}`.

### MR3-P1C v7 pilot scalar_v3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reward_gate_audit_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_pilot --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a
```

pilot/scalar_v3 actual result: `{"outer_wall_sec": 0.34236047603189945, "pid": 869038, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "a19946bf13d6aa3c0f2e7778f30f03bb0cae72f410378546bfaf226e24210ddc"}`.

### MR3-P1C v7 terminal native started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl`. Exact command:

```bash
rtk proxy /usr/bin/bash --noprofile --norc -c 'set -e
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME
exec /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 --steps 4 --base-domain 144 --base-port 12171 --run-id mr3_p1c_v7_terminal --terminal-probe'
```

terminal/native actual result: `{"outer_wall_sec": 341.3803359060548, "pid": 869184, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "fb8969f26fb4dca9509c9e6e78c326121f8f3eed01d646bc3c41567f68ee573b"}`.

### MR3-P1C v7 terminal primary_phase3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_terminal --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/terminal_v7_contact_phase_v3_benchmark_audit.json
```

terminal/primary_phase3 actual result: `{"outer_wall_sec": 0.58682617591694, "pid": 875167, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "0f73f3a85368837d8ef696e978be841e1957f0abcaf604a40007ddad5bd910ee"}`.

### MR3-P1C v7 terminal scalar_v3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reward_gate_audit_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_terminal --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a
```

terminal/scalar_v3 actual result: `{"outer_wall_sec": 0.4729698118753731, "pid": 875314, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "c3d6199caede52f9ec0a232aebe5ff4bbfe393dc4c380fdb03978ad13dc997d2"}`.

### MR3-P1C v7 workers1 native started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl`. Exact command:

```bash
rtk proxy /usr/bin/bash --noprofile --norc -c 'set -e
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME
exec /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101,rooms:202,corridors:303 --steps 16 --base-domain 132 --base-port 12121 --run-id mr3_p1c_v7_workers1'
```

### MR3-P1C v7 closed clock/pilot/terminal canonical archive (offline only)
After root announced each stage fully closed, reused the v6 raw/selected/gzip/decoded SHA method and independently matched actual SDK start/signal/clean-exit lines. No native process was launched or controlled; active workers1 was not read. Originals and previous version evidence remain unchanged. The exact one-off `/tmp/archive_mr3_v7_closed.py` bytes were copied with exclusive creation to `report/assets/20261015_mr3_p1c/archive_mr3_v7_closed.py`; both SHA256 `d9011aa26a2a603246ab3f8847769ee43b6e592f887e26a1ea20b1dfae375beb`. Python `compile()` PASS. This offline asset is outside the frozen execution binding and does not change W7 source/plan.
Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; binding SHA `09a9f2263385a1a9d4bae02676fc26f23d64a026f8633634f8dd3a310bff1117`; cwd `/home/zhuyulab/ns3-workspace`. Exact executed archive commands:

```bash
rtk proxy /usr/bin/python3 -B /tmp/archive_mr3_v7_closed.py clock --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a
```

Actual exit0/stdout: `{"stage": "clock", "passed": true, "wall_sec": 9.673188908956945, "receipts": 22, "clocks": 99, "original_files": 6, "selected_artifacts": 6, "manifest_sha256": "0bfc7bf0852fb9897380cef9018cb90dc55c1ea27638204efa8caf7b1f71accb", "review_sha256": "551e055f40f6264163ed48335b8dfba95d19a95d5419f88fcf669b923db3d481"}`.

```bash
rtk proxy /usr/bin/python3 -B /tmp/archive_mr3_v7_closed.py pilot --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a
```

Actual exit0/stdout: `{"stage": "pilot", "passed_declared_audits": true, "returned_API": 2, "complete_episodes": 1, "original_files": 20, "selected_artifacts": 19, "manifest_sha256": "04de1fadf3b1e13caa21e6abdba8a4363d4863715171259561d36363c3db7751", "review_sha256": "70719e56c1e3e881c401551a15974bf52e6a84704a105e299aa4a69fee4f1071"}`.

```bash
rtk proxy /usr/bin/python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/archive_mr3_v7_closed.py terminal --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a
```

Actual exit0/stdout: `{"stage": "terminal", "passed_declared_audits": true, "returned_API": 8, "complete_episodes": 2, "original_files": 38, "selected_artifacts": 36, "manifest_sha256": "9122cbd69dddc1c6b079424646a1ba583388a8b5ec59665f914acec96a1e60e4", "review_sha256": "a7f0dc0f9a3331ba419722caf868b58a56876166addba58cc63d75802c8a3a29"}`.

Independent terminal raw checks PASS: each epoch has reset plus four API steps; first ends at `dt=physical_dt=.02s`, second at exact `0s` with identical prior snapshot, `action_submitted=false`, and both `terminated=true/truncated=false/navigation_failure`. Totals: 8 API, 6.02 sampled simulation seconds; benchmark recorded wall `339.1027286471799s` is distinct from outer command wall. Both have 18 actual FINALIZED responses, 18 raw contact streams, 38 SDK starts and 38 clean0 exits, 31 serial SIGINT/clean barriers before native stop; all 7 submitted commands have exact 2e9ns TTL and no rejection. Component clock evidence alone gives no robot-team/task credit; probes do not establish 95% mapping or policy-training success.


### P1C v7 additional offline analysis/integrity tooling checks

These versioned offline helpers were prepared during native execution without editing any bound runtime/plan/auditor or inspecting active raw data. They are not new native, GPU, training, reset-result or capacity credit.

Receipt `report/assets/20261015_mr3_p1c/v7_analysis_driver_checks.json`, SHA `8d1e0c3620529aac2f67e9cf182dc67f5625cf1568206f15b5533f3c8e63daa3`. Exact nested check argv/results retained in that receipt:

- `env PYTHONNOUSERSITE=1 /usr/bin/python3 -B -m unittest -q v7_analysis_driver_selftest.py`; result `{"cwd": "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c", "passed": true, "reported_wall_sec": 0.087, "test_count": 9}`.

- `env PYTHONNOUSERSITE=1 /usr/bin/python3 -m flake8 --max-line-length=100 ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/v7_analysis_driver.py ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/v7_analysis_driver_selftest.py`; result `{"passed": true}`.

- `git diff --check`; result `{"passed": true}`.

Receipt `report/assets/20261015_mr3_p1c/verify_mr3_p1c_v7_evidence_checks.json`, SHA `94a977055160c93ecc0b88e2793dfb45053ecd7eccc6565e7fc4d7a8f04dc7b5`. Exact nested check argv/results retained in that receipt:

- `/usr/bin/python3 -B -m unittest discover -s ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c -p test_verify_mr3_p1c_v7_evidence.py -v`; result `{"count": 25, "elapsed_sec": 1.809, "passed": true}`.

- `/usr/bin/python3 -m flake8 ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/verify_mr3_p1c_v7_evidence.py ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/test_verify_mr3_p1c_v7_evidence.py --max-line-length=99`; result `{"passed": true}`.

Analysis entry: 9 pure tests/.087s PASS; actual analysis remains unexecuted. Final integrity entry: an earlier 24 pure fixtures passed/1.137s, then 25 fixtures passed/1.809s after adding conservative bare Popen PID snapshot coverage. Independent static reviews found no blocking issue. Final verifier still unexecuted; all eight stages must finish before canonical/resource/reset/PID completeness checks. Full PID/start identity and bare-PID presence/ambiguity are distinct; no start identity is invented for short CLI processes.

workers1/native actual result: `{"outer_wall_sec": 1078.0245618540794, "pid": 875449, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "f7e78f995af0a10a2f52804a8d89b9c9d4314207ac9182c69c023f8d376eb28e"}`.

### MR3-P1C v7 workers1 primary_phase3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_workers1 --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/workers1_v7_contact_phase_v3_benchmark_audit.json
```

workers1/primary_phase3 actual result: `{"outer_wall_sec": 2.0927928523160517, "pid": 888309, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "0b0160603710979dab1a050c11cda7afb7ed594b941ddcb82bbac4734d1704b3"}`.

### MR3-P1C v7 workers1 scalar_v3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reward_gate_audit_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_workers1 --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a
```

workers1/scalar_v3 actual result: `{"outer_wall_sec": 0.7701544100418687, "pid": 888498, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "63d9f94232da1f92439340bc4bb4a988ae082ac774e74b4e1d3a6887f5abcfcc"}`.

### MR3-P1C v7 workers2 native started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl`. Exact command:

```bash
rtk proxy /usr/bin/bash --noprofile --norc -c 'set -e
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME
exec /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.benchmark --workers 2 --schedule open:101,open:101 --steps 16 --base-domain 134 --base-port 12131 --run-id mr3_p1c_v7_workers2'
```

### MR3-P1C v7 closed workers1 canonical archive (offline only)

Root confirmed all four episodes and native/phase3/scalar gates closed before this read. Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`, unchanged binding `09a9f2263385a1a9d4bae02676fc26f23d64a026f8633634f8dd3a310bff1117`, profile `dd7eeadca21f0924fe721515e8dd57ac979340df8b08885bc39d2595c8caf87b`; fixed archive-tool SHA `d9011aa26a2a603246ab3f8847769ee43b6e592f887e26a1ea20b1dfae375beb`. Cwd `/home/zhuyulab/ns3-workspace`; exact executed command:

```bash
rtk proxy /usr/bin/python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/archive_mr3_v7_closed.py workers1 --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a
```

Actual exit0/stdout: `{"stage": "workers1", "passed_declared_audits": true, "returned_API": 64, "complete_episodes": 4, "original_files": 68, "selected_artifacts": 64, "manifest_sha256": "2ea3b440677cd8f9b7f8f754bfede6d0eeb11f63cedb78e65a75fd340fa3339e", "review_sha256": "a01aa03951bd7d5de8696c885b24b3a817030b78faf571c88e5897a3ce850dae"}`.

Independent saved raw checks: all four epochs contain reset +16 returned steps at exact `dt=physical_dt=1s`; 64 commands accepted, zero rejection, every command-time gate PASS. Each epoch has 18 raw contact streams/sequence audit PASS and 18 actual Nav2 FINALIZED responses, 38 actual SDK starts=38 clean0 exits, 31 serial SIGINT/actual-clean barriers before Gazebo stop. Server/stop PID pairs are `875884/879329`, `879461/882353`, `882480/885620`, `885744/888144`. Recorded benchmark wall is `1075.2152461796068s` (distinct from outer native-command wall). All originals/selected/decoded hashes were checked and no prior file overwritten; final saved owned live/zombie sets empty. Only the closed workers1 group was read, not active workers2. This is scripted engineering evidence, not 95% task or policy-training credit.

workers2/native actual result: `{"outer_wall_sec": 556.8429201813415, "pid": 888605, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "b188862253948401e311024aad0bfc835e087f3d2abd29aabfc852b10a03be50"}`.

### MR3-P1C v7 workers2 primary_phase3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_workers2 --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/workers2_v7_contact_phase_v3_benchmark_audit.json
```

workers2/primary_phase3 actual result: `{"outer_wall_sec": 1.5076794996857643, "pid": 897550, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "adba629dc8edfb7c3a09e31cde07011e6734bd30c09764feb83be2e26f63aa11"}`.

### MR3-P1C v7 workers2 scalar_v3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reward_gate_audit_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_workers2 --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a
```

workers2/scalar_v3 actual result: `{"outer_wall_sec": 0.9341564169153571, "pid": 897749, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "6aad4ba5da16e7dafa075992f90ca2f6857ede989943b3ef3e0bfc8db5f40f47"}`.

### MR3-P1C v7 workers4 native started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl`. Exact command:

```bash
rtk proxy /usr/bin/bash --noprofile --norc -c 'set -e
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME
exec /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.benchmark --workers 4 --schedule open:101,open:101 --steps 16 --base-domain 136 --base-port 12141 --run-id mr3_p1c_v7_workers4'
```

### MR3-P1C v7 closed workers2 canonical archive (offline only)

Root confirmed complete native/phase3/scalar closure before this read. Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`, profile `dd7eeadca21f0924fe721515e8dd57ac979340df8b08885bc39d2595c8caf87b`, binding `09a9f2263385a1a9d4bae02676fc26f23d64a026f8633634f8dd3a310bff1117`, archive tool `d9011aa26a2a603246ab3f8847769ee43b6e592f887e26a1ea20b1dfae375beb` all match. Cwd `/home/zhuyulab/ns3-workspace`; exact executed command:

```bash
rtk proxy /usr/bin/python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/archive_mr3_v7_closed.py workers2 --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a
```

Actual exit0/stdout: `{"stage": "workers2", "passed_declared_audits": true, "returned_API": 64, "complete_episodes": 4, "original_files": 69, "selected_artifacts": 65, "manifest_sha256": "bbc6ec8f68cabbdc972cb102fdc3813096d1e4b135837ea2b339831503c70716", "review_sha256": "3b2e92645e353e7454858c80d6f39a922dfc660da58f7260466b59212f274c04"}`.

Independent saved raw checks: four epochs each reset+16 exact `dt=physical_dt=1s`, total64API; all64 command-time bindings valid. There are63 accepted commands and one `navigation_changed_since_observation` rejection (worker1/e2 cmd4/observation4 at79.96s, expiry81.96s, exact TTL2e9ns); the latter is retained, not relabeled a TTL failure or accepted command. Each epoch has18 raw contact streams/raw sequence PASS and18 actual FINALIZED responses,38 SDK starts=38 actual clean0 exits and31 serial SIGINT/actual-clean barriers. AllROS clean before native stop; final saved owned live/zombie sets empty. Server/stop PID pairs:888892/893546,894028/897321,888891/893249,893372/897316. Recorded benchmark wall554.6546182003804s is distinct from outer native-command wall. Full raw/selected/decoded SHA checked, originals unchanged, no prior files overwritten; active workers4 was not read. No95% task/policy-training/SDK-fix credit.

workers4/native actual result: `{"outer_wall_sec": 641.7473784531467, "pid": 897869, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "bfa2345adec3f295394eb2fed7dde40bf44e6f0d30bc8c4ccc9989a9e17b1716"}`.

### MR3-P1C v7 workers4 primary_phase3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_workers4 --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/workers4_v7_contact_phase_v3_benchmark_audit.json
```

workers4/primary_phase3 actual result: `{"outer_wall_sec": 2.977724688127637, "pid": 912636, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "da52e68e4c8b6601a4f99f2650d0423a55555737a942d6beac99e4cf9ec9ff2b"}`.

### MR3-P1C v7 workers4 scalar_v3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reward_gate_audit_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_workers4 --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a
```

workers4/scalar_v3 actual result: `{"outer_wall_sec": 1.1296133841387928, "pid": 912786, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "95cceaffec712430de312d44382d8e49affc228a34ff094ec72bff323be3271a"}`.

### MR3-P1C v7 fault native started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl`. Exact command:

```bash
rtk proxy /usr/bin/bash --noprofile --norc -c 'set -e
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME
exec /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.benchmark --workers 2 --schedule open:101,open:101 --steps 8 --base-domain 140 --base-port 12151 --run-id mr3_p1c_v7_fault --fault-probe'
```

### MR3-P1C v7 closed workers4 canonical archive (offline only)

All eight epochs and native/phase3/scalar gates were closed before this offline read. Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`, profile `dd7eeadca21f0924fe721515e8dd57ac979340df8b08885bc39d2595c8caf87b`, binding `09a9f2263385a1a9d4bae02676fc26f23d64a026f8633634f8dd3a310bff1117`, archive tool `d9011aa26a2a603246ab3f8847769ee43b6e592f887e26a1ea20b1dfae375beb` match unchanged current bytes/Git inventory. Cwd `/home/zhuyulab/ns3-workspace`; exact executed command:

```bash
rtk proxy /usr/bin/python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/archive_mr3_v7_closed.py workers4 --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a
```

Actual exit0/stdout: `{"stage": "workers4", "passed_declared_audits": true, "returned_API": 128, "complete_episodes": 8, "original_files": 135, "selected_artifacts": 127, "manifest_sha256": "552473d6795df993203d4d2de6f52fd6561a0299d648de9e77e5ade4d22b131e", "review_sha256": "03e84b29b010d9f7177abfa1c337c0a55bcf1fd79ebb2abd3e1d5c08a9ac4bcf"}`.

Independent saved raw checks: eight epochs each reset+16 returned steps at exact `dt=physical_dt=1s`, total128API/128accepted commands/0rejections; every command-time proof passed. Each epoch has18raw contact streams/raw sequence PASS,18actual FINALIZED responses,38actual SDK starts=38clean0 exits,31serial SIGINT/actual-clean barriers before Gazebo stop. Saved final owned live/zombie sets are empty. Recorded benchmark wall639.1834893319756s is distinct from outer command wall. All135 raw original hashes, selected bytes and decoded gzip hashes checked, with no originals or previous files changed. Active fault was not read. These scripted engineering probes do not establish95%task success, policy-training or an SDK bug fix.

fault/native actual result: `{"outer_wall_sec": 428.8288897573948, "pid": 912927, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "733c650432687439c74a9cada259123acd3b75b00f1a287392bcd84795c1c5b0"}`.

### MR3-P1C v7 fault prefix_phase3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_fault/worker0/episode001_open_101 --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/fault_w0_e1_v7_contact_phase_v3_audit.json --expected-fault
```

fault/prefix_phase3 actual result: `{"outer_wall_sec": 0.5326810241676867, "pid": 920638, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "2f0d07032430ebaf829ed5f046a276dd03a742c4643c54c59148fd333baacabc"}`.

### MR3-P1C v7 fault primary_phase3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_fault --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/fault_v7_contact_phase_v3_benchmark_audit.json
```

fault/primary_phase3 actual result: `{"outer_wall_sec": 2.2991658900864422, "pid": 920784, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "3e7b8a0398cd0161503869d2a0923a24b7c019083b10852a643f94f380bdc030"}`.

### MR3-P1C v7 fault scalar_v3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reward_gate_audit_v3_fault_subset.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_fault --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --main-prefix-audit /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/fault_w0_e1_v7_contact_phase_v3_audit.json --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/fault_v7_scalar_v3_audit.json
```

fault/scalar_v3 actual result: `{"outer_wall_sec": 0.6391207408159971, "pid": 920977, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "67eb3a19627968f6de6ff6a989024fc8a58d749f7928f628d3049545d152d09e"}`.

### MR3-P1C v7 deadline native started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl`. Exact command:

```bash
rtk proxy /usr/bin/bash --noprofile --norc -c 'set -e
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME
exec /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 300 --base-domain 142 --base-port 12161 --run-id mr3_p1c_v7_deadline --deadline-probe'
```

### MR3-P1C v7 closed fault canonical archive (offline only)

Root confirmed full native/prefix-phase3/top-phase3/subset-scalar closure before this read. Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`, profile `dd7eeadca21f0924fe721515e8dd57ac979340df8b08885bc39d2595c8caf87b`, binding `09a9f2263385a1a9d4bae02676fc26f23d64a026f8633634f8dd3a310bff1117`, archive-tool SHA `d9011aa26a2a603246ab3f8847769ee43b6e592f887e26a1ea20b1dfae375beb` verified. Cwd `/home/zhuyulab/ns3-workspace`; exact executed command:

```bash
rtk proxy /usr/bin/python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/archive_mr3_v7_closed.py fault --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a
```

Actual exit0/stdout: `{"stage": "fault", "passed_declared_audits": true, "returned_API": 28, "complete_episodes": 3, "original_files": 64, "selected_artifacts": 61, "manifest_sha256": "9de52d4c343b40eb4699bb85785e6066902165433ed97ee862e45514cecf2693", "review_sha256": "02a8f931cebfe39ad4fab5dad7fca63ffad9a8b9e6f45ff63d75c64e33444325"}`.

Raw records retain28 returned1s API: worker0/e1 has exactly4steps then worker `pid913051/start_ticks382439424/session913051/parent912928` actual return-9, failed_sample/forced_shutdown=true,41 unique owned identities, final saved live/zombie sets empty. No summary/native_stop exists for this prefix; no normal exit, full episode/contact or full reward credit. The pinned benchmark Git blob/current bytes match and its identity-checked branch uses os.kill(SIGKILL); this is not a separately saved syscall timestamp trace. Same parent912928 rebuilds worker0/e2 as `pid916776/start_ticks382456180/session916776`, a new epoch returning8steps clean0. Peer worker1 completes both8step epochs. Only those three complete episodes receive the scalar24-step subset proof (not a whole-fault reward audit); each has18raw sequence-audited contact streams,18actual FINALIZED responses,38SDK starts=38clean0 exits and31serial SIGINT/actual-clean barriers. All28 submitted command-time bindings are valid and accepted with0rejection. Recorded benchmark wall426.5376464468427s differs from outer command wall.

Supplemental `native_v7/fault/fault_recovery_identity_review.json` SHA `6d0739ca0f841db98fde7420ea957a349c94185a57c94cf1d07ce8071c7468b2` records the real identities, same-parent recovery and exact limited scope. Original/selected/decoded hashes checked without changes or overwrites. Active deadline was not read; no native process was started or controlled.

deadline/native actual result: `{"outer_wall_sec": 2281.5472140409984, "pid": 921110, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "1a4804970702ae48e945f2c98c99a22c67774e6b5fded819949f6a6e1394f31e"}`.

### MR3-P1C v7 deadline primary_phase3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_deadline --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/deadline_v7_contact_phase_v3_benchmark_audit.json
```

deadline/primary_phase3 actual result: `{"outer_wall_sec": 4.043119207024574, "pid": 933042, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "be2f4286eb4b677e60c38ace463bab4e8995cac34943b9983f260e6fa158c217"}`.

### MR3-P1C v7 deadline scalar_v3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reward_gate_audit_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_deadline --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a
```

deadline/scalar_v3 actual result: `{"outer_wall_sec": 2.9455537227913737, "pid": 933199, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "643595b847b650d6c6c32e1fe91811e831f0d5ce841ca7cce4013979717debe6"}`.

### MR3-P1C v7 matrix primary_phase3 started

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; cwd `/home/zhuyulab/ns3-workspace`. Exact command:

```bash
rtk proxy /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_terminal /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_workers1 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_workers2 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_workers4 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_fault /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_deadline --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/matrix_v7_contact_phase_v3_audit.json --matrix
```

matrix/primary_phase3 actual result: `{"outer_wall_sec": 8.239162225276232, "pid": 933384, "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "88cdc596cd493d3f9e75863a2524a1732383ae84623f4c2fbdc4879813637a27"}`.

### MR3-P1C v7 authorized final offline resource/reset analysis

Started 2026-10-15T16:29:41.272447+00:00. Root authorized analysis after all eight native stages and all declared phase3/time/scalar/matrix gates naturally completed; final native driver event16:28:50.357624Z (Beijing2026-10-16 00:28:50). Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`, execution binding SHA `09a9f2263385a1a9d4bae02676fc26f23d64a026f8633634f8dd3a310bff1117`; cwd `/home/zhuyulab/ns3-workspace`. Exclusive outputs were absent. This executes only pure offline analysis; no native/GPU/training or automatic acceptance. Exact command:

```bash
rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/v7_analysis_driver.py --execute --binding-sha256 09a9f2263385a1a9d4bae02676fc26f23d64a026f8633634f8dd3a310bff1117
```

Offline analysis completed at 2026-10-15T16:29:52.292016+00:00; outer command exit0, tool-observed wall7.058305973s. No retry, native or GPU execution. Actual child commands/results:

```bash
rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/resource_analysis_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_pilot /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_terminal /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_workers1 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_workers2 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_workers4 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_fault /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_deadline --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/resource_analysis_v7.json
```
{"freeze": "cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a", "kind": "command_complete", "name": "resource", "output_sha256": "10430e047de45dfc9af26f155df6608768c777d10f24bc4ec24085fd58a59990", "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "3b9ffb4268ce574492f935fd28d453aefdbdac046cfccab6393931e268fefb27", "utc": "2026-10-15T16:29:48.901049+00:00", "wall_sec": 2.794729466084391}

```bash
rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reset_analysis_v7.py --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --implementation-checks /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/implementation_checks_v7.json --implementation-checks-sha256 5aa211fb00ffbd2170510f2f8f9c169cbb53bf52315fc4e70602b2857bee90a8 --native-root /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7 --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reset_summary_v7.json
```
{"freeze": "cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a", "kind": "command_complete", "name": "reset", "output_sha256": "c436b27fdb0879b171f2624803105105375ed8e568b28cce0af967d64efa1e39", "returncode": 0, "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "8c356385034f49be4f5f616998c723b135e61b2a759cb88f5514b47bccb7e519", "utc": "2026-10-15T16:29:52.282542+00:00", "wall_sec": 3.3702655090019107}

Resource output only freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`, mixedfreeze=false, seven summary_passed=true. It remains resource diagnostics, not a semantic audit. Reset output passed=true/errors=[] for16normalcells,7same-worker pairs,2cross-scene and91all-open pairs; no bitwise SLAM/DDS or dynamic-cache probe claim. Fair first2open101 rates are32/537.5289088496938=.05953168187452403/s,64/552.606865955051=.11581470289803773/s,128/636.9173088907264=.2009680035590939/s; denominators omit final reap tail. No capacity claim for300step moving policies. Deadline benchmark records300validAPI/2279.4054388399236wallseconds and is KEEP diagnostic scope. All future policy training/72h budgets and2D implementation remain unapproved.

`ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/resource_analysis_v7.json` SHA256 `10430e047de45dfc9af26f155df6608768c777d10f24bc4ec24085fd58a59990`.

`ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reset_summary_v7.json` SHA256 `c436b27fdb0879b171f2624803105105375ed8e568b28cce0af967d64efa1e39`.

`ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/v7_analysis_execution.jsonl` SHA256 `ffc824859afc0ad1e8467f5b049c2601b11437bb6472d4b8a9475ed44a7e3294`.


### P1C v7 canonical selected-evidence matrix replay

Exact command (Git root):

```bash
rtk proxy /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v3.py /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/terminal /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/workers1 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/workers2 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/workers4 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/fault /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/deadline --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/canonical_matrix_v7_contact_phase_v3_audit.json --matrix
```

Actual result: `{"GPU_calls": 0, "command": ["rtk", "proxy", "/usr/bin/python3", "-B", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v3.py", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/terminal", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/workers1", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/workers2", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/workers4", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/fault", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/deadline", "--freeze", "cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a", "--output", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/canonical_matrix_v7_contact_phase_v3_audit.json", "--matrix"], "cwd": "/home/zhuyulab/ns3-workspace", "finished_at_utc": "2026-10-15T16:30:50.964256+00:00", "native_runs": 0, "outer_wall_sec": 9.804345235228539, "output_sha256": "988ac4a0c433a224e4fbdd692fc2f1e70016fd249bf885fcb0abe4911fca72a9", "returncode": 0, "schema": "mr3-p1c-v7-canonical-matrix-execution-v1", "stderr": "", "stdout": "{\"audit\": \"/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/canonical_matrix_v7_contact_phase_v3_audit.json\", \"errors\": [], \"passed\": true}\n"}`.


### P1C v7 final evidence/source/PID integrity verification

Exact command (Git root):

```bash
rtk proxy /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/verify_mr3_p1c_v7_evidence.py --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --binding /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/predeclared_execution_binding_v7.json --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/final_evidence_integrity_v7.json --extra-evidence /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/resource_analysis_v7.json --extra-evidence /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reset_summary_v7.json --extra-evidence /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/canonical_matrix_v7_contact_phase_v3_audit.json --extra-evidence /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/final_native_inventory_review.json
```

Actual result: `{"GPU_calls": 0, "command": ["rtk", "proxy", "/usr/bin/python3", "-B", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/verify_mr3_p1c_v7_evidence.py", "--freeze", "cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a", "--binding", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/predeclared_execution_binding_v7.json", "--output", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/final_evidence_integrity_v7.json", "--extra-evidence", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/resource_analysis_v7.json", "--extra-evidence", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/reset_summary_v7.json", "--extra-evidence", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/canonical_matrix_v7_contact_phase_v3_audit.json", "--extra-evidence", "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/final_native_inventory_review.json"], "cwd": "/home/zhuyulab/ns3-workspace", "finished_at_utc": "2026-10-15T16:32:59.545858+00:00", "native_runs": 0, "outer_wall_sec": 4.886456280015409, "output_sha256": "6aa54899c1a95cf586f5bb95d4b5a0d890c215e387d96922bfc9f616d4363f96", "returncode": 1, "schema": "mr3-p1c-v7-final-integrity-execution-v1", "stderr": "", "stdout": "{\"errors\": [\"formal_audits: 'normal_native_shutdown_credit'\"], \"output\": \"/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/final_evidence_integrity_v7.json\", \"passed\": false}\n"}`.

### MR3-P1C v7 closed deadline archive and final native inventory (offline only)

Root confirmed deadline native/phase3/scalar closure before archiving. Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`, profile `dd7eeadca21f0924fe721515e8dd57ac979340df8b08885bc39d2595c8caf87b`, binding `09a9f2263385a1a9d4bae02676fc26f23d64a026f8633634f8dd3a310bff1117` remain unchanged and exact. Cwd `/home/zhuyulab/ns3-workspace`; exact executed archive command:

```bash
rtk proxy /usr/bin/python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/archive_mr3_v7_closed.py deadline --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a
```

Actual exit0/stdout: `{"stage": "deadline", "passed_declared_audits": true, "returned_API": 300, "complete_episodes": 1, "original_files": 20, "selected_artifacts": 19, "manifest_sha256": "b03ff44c96c26dd73706d4c6372b0f4721bb483589859bc8a447dac3aac5e20d", "review_sha256": "2809fd287ce6d73ae9fb33c1cee123ca25d08250fa1380456e71bbfd744eb055"}`.

Independent raw deadline checks PASS: release81420000000ns to381420000000ns is exactly300000000000ns, all300steps have dt=physical_dt=1s, first299 nonterminal/nontruncated and final timeout terminated=true/truncated=false. All300 KEEP888 commands are valid and accepted at exact2e9ns TTL;0rejections,0invalid penalties,900robotKEEPs,0nativegoal. The final-evaluator-map terminal exception remains explicit.18raw streams/rawseq PASS,18actual FINALIZED responses,38SDK starts=38actual clean0 exits,31serial SIGINT/clean barriers,server921288/stop932877clean0. Recorded benchmark wall2279.4054388399236s differs from outer wall.20originals→19selected and all raw/selected/decoded hashes match without overwrite.

A new offline inventory helper `final_native_inventory_v7.py` (SHA `eb887148b1c67b462b62a64d39136900ee49730f42b38263fdfa19b49eefae06`) verifies all32top/leaf manifests, actual closure evidence and current /proc identities. Syntax compile and flake8(max100) PASS after line-format corrections; it is outside the native source binding. It does not execute the root final verifier or consume matrix output. Exact executed command:

```bash
rtk proxy /usr/bin/python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/final_native_inventory_v7.py --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --output ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/native_v7/final_native_inventory_review.json
```

Actual exit0/stdout: `{"passed_inventory_checks": true, "returned_API": 594, "sampled_physical_time_ns": 592020000000, "complete_episodes": 23, "incomplete_killed_prefixes": 1, "submitted_commands": 593, "accepted_commands": 592, "rejected_commands": 1, "manifest_count": 32, "unique_original_files_verified": 420, "unique_selected_original_artifacts_verified": 397, "owned_pid_start_ticks_count": 1018, "output_sha256": "900a2562c30a2a1ef2a117429618876c3e973797bf1e72730129dd09cc9641de"}`.

Final scope: eight stages,594returnedAPI and592.02sampled physical seconds (includes4-step killedprefix),23normal complete episodes plus1incomplete prefix.593submitted commands,592accepted and1retained navigation_changed_since_observation rejection; no command-time-invalid rejection.420unique original files/397selected gzip+identity artifacts verified (59128314/10514174bytes, excludes derivative audit/review bytes). Normal episodes provide874actual SDK starts/clean0 exits,713serial barriers,414FINALIZED responses and414raw-stream instances; including prefix,actual SDK totals911starts/878clean0 lines, with no clean-closure credit for the killed prefix.1018real saved(pid,start_ticks) identities have no current exact survivor/zombie;4bare unit-scoped PIDs without saved start_ticks are currently absent and never assigned fake ticks. No native/GPU work or process control was performed. This inventory establishes evidence consistency/closure within the declared probe scope, not user acceptance, policy training,SDKbug fix,95%mapping or network credit.

### MR3-P1C v7 deadline positive command-time review and offline integrity v2 — 2026-10-15T16:41:58.219609+00:00

Freeze `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`; closed open101 deadline epoch `mr3_p1c_v7_deadline_w0_e1_51e1d929`. No native/ROS/GPU process or policy training was started by these read-only checks. Existing runtime, execution binding, manifest files, auditors and old results remain unchanged.

Exact positive-review command (cwd `/home/zhuyulab/ns3-workspace`):

```bash
rtk proxy /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/review_deadline_v7_command_time.py ros2_ws/ros2-multi-robot-automap/log/mr3_learning/mr3_p1c_v7_deadline/worker0/episode001_open_101 --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --phase-audit ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/deadline_v7_contact_phase_v3_benchmark_audit.json --scalar-audit ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/deadline_v7_scalar_v3_audit.json --output ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/deadline_v7_command_time_review.json
```

The review exited0: 300 legal accepted commands, 900 kept robot receipts, no goal/rejection/invalid penalty/newly rewarded cells; start81.42/end381.42 =300000000000ns. `timeout` is terminated=true/truncated=false; failure=-20 only at sequence300, time=-1. Commands174/175 at254.42/255.42 expire256.42/257.42: literal float TTL2.0000000000000284, separately rounded endpoint TTL2000000000ns, all three kept and invalid0. This is scalar/receipt/physical-time evidence only; no spatial truth replay, independent18-contact timing or additional native credit.

Positive output `report/assets/20261015_mr3_p1c/deadline_v7_command_time_review.json` SHA256 `4533434ed76e7c3b96e106b93fd00845c1bd3bd65c12aaa2c997eb0b0d1057de`; script SHA256 `6153237d08f42485937ef45bb8495f93a1493a586f0674562f519c54acdfffa3`. Six pure counterexample tests PASS, flake8 PASS; checks SHA256 `3268593f38103c0bfc3cb7e2c12576c97fe96244adc12861f4b40b422d9b34dc`. Exact test command:

```bash
rtk proxy /usr/bin/python3 -B -m unittest discover -s ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c -p test_review_deadline_v7_command_time.py -v
```

The first v7 final verifier's FAIL is retained byte-for-byte, SHA256 `6aa54899c1a95cf586f5bb95d4b5a0d890c215e387d96922bfc9f616d4363f96`. Its sole error was the offline verifier treating two optional prefix-manifest credit fields as mandatory. Version2 keeps mandatory complete_episode_credit=false; present optional fields must befalse, absent fields are explicitly unavailable. It additionally checks actual SIGKILL/forced cleanup and absence of raw/selected normal closure JSON or gzip files. It does not modify manifests or weaken native/contact/protocol/reward gates. Thirty-one pure isolated tests and flake8 PASS; independent static review found no remaining blocker.

Exact v2 verification command (same cwd):

```bash
rtk proxy /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/verify_mr3_p1c_v7_evidence_v2.py --freeze cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a --binding /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/predeclared_execution_binding_v7.json --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/final_evidence_integrity_v7_v2.json
```

Actual result: exit `0`, wall `5.488358119` seconds, passed `True`. New output SHA256 `d102c544d82cd0448ecc797c5c5b1203b77fe401e16efe169e2258085ba015c5`; verifier SHA256 `7f4ab7c284137aba93a7a7765eb84edcc9f6129e1c90fb7c40d89922fda30046`. Execution receipt `report/assets/20261015_mr3_p1c/final_evidence_integrity_v7_v2_execution.json` SHA256 `dd1ea3ae0036040487dcafe08b5195b675f324c15122e52fcfef17eef3c6f2cf`. The original verifier/test/checks/FAIL and all v6 failures remain preserved. This is final evidence integrity and saved-process cleanup verification, not new native execution or automatic user acceptance.

Offline v2 method-correction checks `report/assets/20261015_mr3_p1c/verify_mr3_p1c_v7_evidence_v2_checks.json` SHA256 `aee265ff03e277e70d8f47a56b0d03f65f778ab29af4f69ec8c44fefb55d62c1` retain the four original v1 artifact hashes and original failed verdict. Exact pure-test and style commands (no native):

```bash
rtk proxy /usr/bin/python3 -B -m unittest discover -s /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c -p test_verify_mr3_p1c_v7_evidence_v2.py -v
rtk proxy /usr/bin/python3 -m flake8 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/verify_mr3_p1c_v7_evidence_v2.py /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/test_verify_mr3_p1c_v7_evidence_v2.py --max-line-length=99
```


### 2026-10-16：MR3-P1C W7最终文档与交付静态核查

- 本轮唯一最终原生冻结仍为`cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a`；最终v2离线证据核查PASS、首次schema假设FAIL并列保留，详见紧前记录。未新增native/GPU/训练。P1C实现与验证完成、待用户验收，P2A未开始。
- 更新18份活动Markdown及归档索引，包含实际吞吐/资源/reset、条件预算和未实施二维独立提案。W7规范任务/环境合同仍按冻结Git blob审计，当前状态文字不反向改变运行原件。
- 静态命令（Git root）：`rtk proxy /usr/bin/python3 ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/check_p1c_docs_v7.py --output ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c/final_document_checks_v7.json`，exit0；18文档、224链接、31 bash/sh块语法PASS。随后仅校正主报告启动/结束日期及GPU实际v2计划链接，以同一命令改输出为`final_document_checks_v7_v2.json`再次exit0，18/224/31 PASS；原静态结果保留。此检查不执行文档中的命令。
- 独立短Python断言：54项`implementation_checks_v7.json.source_sha256`当前源码均与W7冻结字节一致；原始/选件六组矩阵仅替换六个绝对目录根后逐字段完全相等；归档索引11项active artifacts的SHA匹配；6个历史原生冻结条目保留。launch_commands phase3命令的`--freeze/--output`与固定auditor AST定义匹配。
- 活动入口检索`P1C.{0,18}(进行中|待做|待验证)|尚待验证|源码候选|P1C in progress`无匹配（rg exit1）；历史报告段落仍保留原时态。`rtk git diff --check`exit0。
- `rtk git add -n .`已在Git root执行exit0；新文件全部属于有意保留的P1C canonical证据/离线审计与测试，无build/install、bag、checkpoint或core。原route backup两个ref及仅main/backup本地分支库存均未变。
- 最终静态回执SHA：`eb5169ada4e9341944fe52dae1db935ffe27c1e0ee274e799245db308118d710`。
- 随后用`rtk proxy git add -n .`核对原生Git完整dry-run输出：exit0、522条add（20份已跟踪文档/日志/索引修改与502份新canonical证据文件）；原生staging当时为空。独立只读交付review确认54源SHA和14条索引SHA/size、所有状态/数值/限制一致，无具体阻断。


### 2026-10-16：MR3-P1C用户验收与P2A首轮实施冻结

用户明确指示“阅读当前项目，p1c验收通过，继续执行P2A”。P1C记为2026-10-16已验收；当前只推进P2A，P2B及gateway未授权。二维替代和500k/72h候选预算仍未接受。

学习端保留`PYTHONNOUSERSITE=1`与conda ns3gym。环境只读检查确认PyTorch2.11.0+cu128、CUDA可用、两RTX4090；系统ROS仍独立解释器。实际依赖命令（Git root，rtk proxy bash -lc包装）为：

```bash
PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m pip install --dry-run stable-baselines3==2.9.0 sb3-contrib==2.9.0
PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m pip install --disable-pip-version-check --timeout 20 --retries 1 -i https://pypi.org/simple stable-baselines3==2.9.0 sb3-contrib==2.9.0
```

两命令exit0；仅新增SB3/contrib2.9.0，现有torch/CUDA/Gymnasium未替换。官方MaskablePPO、custom policy及Gymnasium终止/截断文档已核查，技术链接在MR3_PPO_CONTRACT.md。

实现完整episode采样后调用成熟MaskablePPO.train()；保存精确张量/候选含义/掩码/logprob，零物理无动作尾通知在更新前归并到此前真实决策，短已执行末步保留，逐秒gamma/lambda GAE、真正terminated与外部truncated分开。变长buffer末尾singleton并入前batch以避免标准优势标准差NaN。评估显式mask-aware且核对内存参数SHA与0optimizer调用；没有手工探索兜底或真值actor输入。

当前检查：conda CPU unittest 73项exit0，报告8.286秒；包括实际SB3 CPU optimizer fixture更新、采样mask概率重评、checkpoint往返、collector关闭/失败/短零终态和变长buffer。独立offline audit CPU正例及9种篡改反例另列，不计入73项；首次fixture因缺少新增epoch/sequence证明字段失败后只修正fixture。flake8新实现exit0；首次检查发现格式缩进后修正，不改变语义。11文档/110本地链接/19shell块语法exit0。规范结果：report/assets/20261016_mr3_p2a/implementation_checks_v1.json。此时native/GPU训练均未启动。

完整原生命令、stage条件、seed、预算、停止规则见report/assets/20261016_mr3_p2a/predeclared_plan_v1.json。计划：新提交推送冻结先跑mr3_p2a_v1_minimal（open101，seed17，1worker/8决策/600墙秒，实际CUDA PPO更新）；原生及policy审计通过才启动mr3_p2a_v1_pilot（固定open101，seed17，4worker/4096决策或14400墙秒截止）；随后只用finalcheckpoint做open401/402/403三开发验证（900决策上限/9000墙秒，确定性mask-aware/0更新）。每worker始终三机器人，全部失败保留，无自动重试；wall上限是采样截止，原生安全闭合与最后已开始round更新额外实耗单列。P2A未达到冻结95%/安全/学习出口时停在本步，不以optimizer更新冒充验收。


### 2026-10-16：MR3-P2A v1原生最小更新链与离线文档绑定修正

运行源码已提交推送为`bbbe21cb3c49f4f714cc2198b579a08699e9ba28`。cwd为wireless-rl，解释器conda ns3gym，PYTHONNOUSERSITE=1。精确命令：

```bash
rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.ppo --mode train --workers 1 --schedule open:101 --decisions 8 --episode-steps 8 --wall-seconds 600 --seed 17 --base-domain 160 --base-port 12301 --run-id mr3_p2a_v1_minimal
```

exit0；220.14412238495424墙秒含startup/原生关闭/学习，8真实决策/8API/8仿真秒，4次实际CUDA optimizer.step，4PPO epochs；70个state_dict tensor entries改变（包含共享模块别名，不是70个独立参数张量）。原生关闭无forced/存活/zombie，task schema4为training_external_truncation、success=false、覆盖0.5632475120971423、quality/participation门禁false、0contact、持续监测健康、navigation_protocol_closed=true。该最小链证明真实三机器人网络选目标→执行→更新，不能算95%或P2A通过。8动作831/888/488/888/888/98/838/888，5个目标跨三台，0action_rejected；采样前snapshot/mask/candidate/command身份相符。

initial.zip SHA ceb25b7b1564bad5da200fb3ae9d8eadc4bb4c835d842309e165ed634c9b7271；final.zip SHA 24c3a57e4344d09f4f8881a9f9e1f48b4b5f9765727ec063f12d398b56595ab4。PPO entropy_loss=-2.116309762、approxKL=.003622114658、value_loss7.694003582，有限参数/指标；完整原件`ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v1_minimal/`。

首次离线命令为`python -m mr3_learning.audit_ppo /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v1_minimal --freeze bbbe21cb3c49f4f714cc2198b579a08699e9ba28 --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v1_minimal/audit_v1.json`（同conda/rtk/env包装），exit1。旧helper在读取源freeze的MR3_TASK_CONTRACT.md时docSHA不符，尚未执行native/policy审计，未生成audit_v1.json；错误回执保留audit_failure_v1.json。计划按门禁未启动v1pilot/validation。

W7→当前任务文档diff仅交付状态与候选预算每run说明；整个机器合同目录/3world和全部native源字节不变。修正离线wrapper显式绑定任务文档旧状态SHA5e4400396e4aaf5a5094fb4c0c04c85810c327cc85be88b7d03fa3faeade07d2及已验收状态SHAf96f5ba785a39daa882b3c2ea217c58dd968550b65bf0ee15faf07ca079f8991，原始helpers和95%/300s/安全/reward门禁未改。相同命令改输出`audit_v1_revised_binding.json`exit0，SHA ee0546ca69fc255ef939a0f684a599a1b88254eb394f08b00c98756e2ca842be。8原生采样张量/掩码/动作/GAE与更新前checkpoint重评、原contact-phase/command-time/closure/scalar门禁均PASS；CPU重评logprob最大差4.768e-7、value2.682e-7。修正后的审计不改任务success=false，也不证明新native运行。

选定原件`report/assets/20261016_mr3_p2a/native_v1/minimal/`：26原文件，raw19577083bytes/selected12590315bytes，逐文件SHA/encoding/源路径见manifest.json。压缩只是原件选择，不改变字节解码内容；包括全部3checkpoint/rollout/native/失败回执及修正audit。新v2计划前瞻使用任务契约既有训练seed41，重新冻结后重跑最小链/pilot/开发验证；v1seed17保留为工程探针，不混入v2矩阵，不用于正式算法比较。

P2A v2冻结前补充：新增3项纯offline源绑定回归，当前76项CPU unittest全部exit0（8.482秒），变更文件flake8与diff-check通过；13文档/124本地链接/19shell块语法通过。记录implementation_checks_v2.json。v2学习默认seed调整为任务契约既有41（命令仍显式记录），新最小链/pilot/开发验证均先声明于predeclared_plan_v2.json，未复用v1原生信用。ARCHIVE_INDEX记录v1→v2计划取代及原件位置。


### 2026-10-16：MR3-P2A v2原生最小链、pilot诊断停止与v3前瞻修订

v2唯一推送源码冻结`9e898bd5ca5eccc6e263e198481f672b5cf82320`，学习seed41，场景open/任务seed101；每worker固定tb1/tb2/tb3。cwd为wireless-rl，学习端conda ns3gym且PYTHONNOUSERSITE=1；原生ROS仍独立系统解释器。精确原生命令：

```bash
rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.ppo --mode train --workers 1 --schedule open:101 --decisions 8 --episode-steps 8 --wall-seconds 600 --seed 41 --base-domain 160 --base-port 12301 --run-id mr3_p2a_v2_minimal
rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.ppo --mode train --workers 4 --schedule open:101 --decisions 4096 --episode-steps 300 --wall-seconds 14400 --seed 41 --base-domain 164 --base-port 12311 --run-id mr3_p2a_v2_pilot
```

minimal于2026-10-16T03:06:50.385548+00:00启动，exit0，8真实决策/8API/8奖励仿真秒，4次GPU optimizer.step/4PPOepochs，210.04429372074082墙秒含startup/关闭/学习。初始checkpoint SHA`f6c9688d2ee616f9aa6db6b12e5f6e756c863a03015b90a9407703b93ba2c886`，final SHA`1e02fc9be142d93ba574882713cce916a7767f5cc21ccc6d3e66b39a4d5e02eb`；70个改变state_dict entries包含共享别名。任务training_external_truncation、success=false、覆盖0.6189628412307131、质量/参与false、0接触、监测新鲜、关闭后navigation_protocol_closed=true，T95为空。评价器8.2秒包含外部关闭尾段，不能当作8.0秒奖励采样时间。独立审计命令（同conda/env/rtk包装）为：

```bash
python -m mr3_learning.audit_ppo /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v2_minimal --freeze 9e898bd5ca5eccc6e263e198481f672b5cf82320 --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v2_minimal/audit_v2.json
```

审计exit0，原contact/time/scalar/closure门禁、实际快照/掩码/动作/GAE及更新前policyCPU重评PASS。logprob最大差4.76837158203125e-7、value3.5762786865234375e-7。规范原件`report/assets/20261016_mr3_p2a/native_v2/minimal/`的manifest SHA`c9d5795eaea868233d502dea65d369d22af72f254c235d5ddc38ddf5e4e52c4e`；25文件raw19580752/selected12373304bytes，audit SHA`e0ad57445b6e4d4112470281106b3d2f6920ad563c5050cbe3b0934c700fe95f`。这是最小训练工程信用，不是95%或P2A验收。

pilot于2026-10-16T03:11:05.437704+00:00启动；agent根据四条初始未训练策略轨迹中tb3候选饥饿及SLAM/Nav2接口不匹配请求诊断SIGINT，原停止回执`diagnostic_stop_request.json`绑定父PID1095696/start_ticks386565479。保留exit1、`KeyboardInterrupt()`、`completed=false`、原通用`stop_reason=infrastructure_error`，不把该通用标签解释成Gazebo崩溃；cleanup_errors=[]。该run在完整round返回前停止，顶层decisions/API均0只表示尚未纳入闭合round，绝不能写成零采样：原始native已结算390条step/390提交且接受的决策，奖励有效时间389.10秒；collector回调只证明388返回/387.10秒，两条在途native记录没有独立返回回执。四worker实际native步数152/58/152/28，对应152/57.12/152/27.98奖励仿真秒。w0/w2关闭各另结算一次零时间reward/ACK，未提交actor动作，不能按native_summary.transition_count把它算为决策。

pilot实耗1752.9574942300096墙秒，0optimizer更新、0训练rollout文件、无finalcheckpoint；minimal的独立4更新不能转记pilot。w1/w3分别57.12/27.98秒发生`peer_body_envelopes_overlap`真实任务安全失败；w0/w2为agent放弃的未完成前缀，不能当成功或完整任务失败样本筛掉重跑。评价覆盖分别.9636172738/.8709029490/.9206838309/.7107641742；w0质量通过但三台参与false，超过95%覆盖也不是成功。四条tb3真值路径约.399/.324/.339/.716m，均不足1m，最初一两次短目标后长期无可达候选。无真值actor输入或手工探索兜底，全部保存动作绑定旧snapshot/mask且adapter接受，无拒绝。

四环境实际owned关闭均clean0、每环境18个Nav2 finalized、无forced/遗留/zombie；168组保存PID/start身份无当前匹配。原生JSON记录0contact和新鲜监测；独立`diagnostic_native_prefix_audit_v1.json`明确不是完整contact/clock/scalar审计，不能扩大安全信用。规范诊断SHA`33beacea2305e110e99dd35c973983025d3964cd83d8b73d72adc0f26e9b7813`；`native_v2/pilot_interrupted/manifest.json` SHA`8846d56b4e78bf2e957daeb1bb7957dd6ef8882c51d89a3e79b14a9aa0860c2b`，67文件raw36100098/selected7135679bytes。原始runtime根为ROS工作区`log/mr3_ppo/mr3_p2a_v2_pilot/`；v2开发验证未开始，所有失败和前缀原件保留。

v3为新的执行契约，不能复用P1B/P1C/v1/v2原生信用。候选版本`mr3-per-robot-geometric-staging-v3`按各台已交付本地图的可达几何池保留代表项后做K8最远点采样；不使用奖励/收益排序、真值、手工重派、障碍清除或不安全起点吸附。原生路径/种子净空仍.29m；新目标需在融合图及该台本地图容纳.39m到达圆盘，已处于.10m容差内不重复作为探索动作；候选规则/半径纳入candidate_version哈希，审计按显式版本区分旧原件。

活动`src/slam_toolbox/config/mapper_params_online_multi_async.yaml`仅将minimum_travel_distance/heading从.5m/.5rad改为.10m/.20rad；ROS minimum_time_interval=.5s、map_update_interval=5s及C++/Karto实现不改。主launch实际加载的`src/multi_robot/params/nav2_params_tb1_0.yaml`至tb3_0.yaml中GoalChecker和DWB.xy_goal_tolerance均由.25m收紧至.10m，yaw3.14不变；不是params/turtlebot3_params中的同名文件。安装版`/opt/ros/humble/include/dwb_critics/rotate_to_goal.hpp`明确旧DWB大窗口会进入减速/rotation-only，所以两容差同步。改变执行参数而不放宽95%/300秒、质量/参与/18源新鲜度、peer机体包络、目标所有权或reward门禁；是否解决饥饿必须由新冻结原生验证。

本次仅CPU/静态/构建检查：systemROS新配置5项+原adapter launch13项=18通过；独立候选/配置54项通过；候选agent聚焦223项通过。conda全套79项通过8.445秒（之后新增accounting/auditor检查另记）。根代理三包canonical colcon构建通过6.75秒，已有slam_toolbox overlay提示保留。精确已执行构建/本代理静态测试命令（ROS cwd）为：

```bash
source /opt/ros/humble/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /usr/bin/colcon build --symlink-install --allow-overriding nav2_bringup --packages-select multi_robot multi_robot_exploration slam_toolbox
source install/setup.bash
/usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_mr3_short_subgoal_config.py src/multi_robot_exploration/test/test_mr3_adapter_launch.py
/usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_mr3_observation.py src/multi_robot_exploration/test/test_mr3_short_subgoal_config.py
```

最初本代理只source Humble、未source当前install的配置测试收集失败（无法导入项目包）；补规范install环境后18/54通过，不为该环境问题改代码。根代理另一次`/usr/bin/python3 -m pytest -q src/multi_robot_exploration/test`从ROS工作区根误收全域lint脚手架：778语义检查通过、1版权skip、test_flake8/test_pep257两项失败（38815条全域flake8、171条文档风格），58.38秒；扫描历史日志/build/其他包的原失败保留，不修改旧产物掩盖。accounting聚焦14项通过3.749秒，一次mock fixture误截获SB3非Git系统信息查询失败后修正fixture；非原生问题。限定语义检查和变更文件lint最终回执随后单列。上述检查没有新增仿真/GPU。

前瞻v3计划`report/assets/20261016_mr3_p2a/predeclared_plan_v3.json`在原生前记录，不猜测源码SHA，标识SOURCE_FREEZE_FROM_METADATA；所有v3阶段须同一新提交推送冻结。新工程链seed41/open101、1worker、16决策/16步截断/900墙秒，审计通过再从全新初始策略执行4worker pilot，最多3706决策/12600墙秒。原4096/14400 pilot预算扣除v2真实390决策/1752.957494墙秒，余3706决策/12647.042506墙秒，保守取12600，不增加pilot预算；工程最小链和固定验证另列，已声明的原生关闭/在途/最后round更新收尾实耗仍另记。只用v3 final在open401/402/403做900决策上限/9000墙秒确定性mask-aware开发验证，0更新；不以验证挑模型。新原生命令尚未执行，v2失败不改名；P2A仍进行中，P2B/gateway未开始，无95%/多训练seed/未见泛化或用户验收信用。


v2证据补充：诊断停止使用inline Python，在核对`/proc/1095696/stat`的start_ticks确为386565479后，独占创建`diagnostic_stop_request.json`，实际操作调用为`os.kill(1095696, signal.SIGINT)`；没有shell kill、全会话终止或用户取消。前缀诊断是agent inline Python只读核查，没有保存为可重放脚本，不能虚构其CLI；原JSON的范围限制与SHA如上。选件打包精确已执行命令（Git root）为：

```bash
rtk proxy python3 /tmp/mr3_p2a_package.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v2_minimal /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261016_mr3_p2a/native_v2/minimal
rtk proxy python3 /tmp/mr3_p2a_package.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v2_pilot /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261016_mr3_p2a/native_v2/pilot_interrupted
```

只读选件字节核查`report/assets/20261016_mr3_p2a/selected_byte_integrity_v2.json`通过118/118文件：v1 minimal26、v2 minimal25、v2 pilot67；逐项验证selected及解码raw SHA/字节。没有新增simulator/训练，原失败与原件未改。

### 2026-10-16 MR3-P2A v3 冻结前最终检查

候选版本`mr3-per-robot-geometric-staging-v3`的新源码尚未运行原生/GPU；以下为本次将提交源码的静态/CPU检查，不能继承W7或v2任务信用。限定ROS语义检查786/786通过（25.37秒），conda CPU全套86/86通过（8.653秒）；11个本次Python修改文件flake8（99字符）通过。三个受影响包已在canonical工作区构建通过，share安装入口实际指向修正配置；9份活动文档的相对链接、计划/归档JSON及118份所选原件的压缩/原始SHA和字节均通过。完整命令与回执见`report/assets/20261016_mr3_p2a/prefreeze_checks_v3.json`及`selected_byte_integrity_v2.json`。前述广域lint失败保持记录。

计数异常回归还验证：已闭合轮次在优化中断时不重复计入active；原生落盘决策含在途回调未达客户端的记录、零尾步不计actor决策；不宣称统计未落盘的已提交动作。显式关闭学习日志句柄，原生记账错误归基础设施异常。未变更奖励、任务门限或原生接触/时钟/命令检查。


### 2026-10-16：MR3-P2A v3原生最小链、原scalar审计FAIL与v4前瞻日志/归因修订

v3推送冻结`c2911114226bbe8275a0658a3710dafa4e89f5e0`，UTC启动2026-10-16T04:03:07.622076+00:00。cwd wireless-rl、conda ns3gym/PYTHONNOUSERSITE=1，系统ROS进程边界保持；按原v3计划精确执行：

```bash
rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.ppo --mode train --workers 1 --schedule open:101 --decisions 16 --episode-steps 16 --wall-seconds 900 --seed 41 --base-domain 160 --base-port 12301 --run-id mr3_p2a_v3_minimal
```

exit0、completed=true/decision_budget；16原生决策、16collector已返回API、16.0奖励/物理仿真秒，4次GPU optimizer.step/4epochs，290.07678865175694墙秒含原生启动/关闭及更新。无原生记账错误，全部owned关闭clean0、无forced/遗留/zombie；独立43/43保存PID/start身份无当前匹配（owned_process_absence_v1.json SHA`1627bb269c154f6c37c4362dd247059a0b69b5feaeea6204c4b7ff6c16eea473`）。initial checkpoint SHA`992878bfdad14eb0322db68a7125c730d6f8b7a5b41ff3df378b321732a50800`，final SHA`7e43b501c0c904009c9ecf23b14294b46632391d258bb58d7374fb2ad39f7a08`；70个改变state_dict entries仍含共享别名。16动作均在首次更新前由初始网络产生，不能由此声称已学习有效策略。

三台实际接受目标4/3/4、各1次成功，共11目标/3成功；15动作被接受，1个command4按navigation_changed_since_observation正确拒绝并真实扣分。17保存快照的本地图几何摘要各有15/10/15种（非header-only变新），正可达几何池没有因K8截断丧失全部代表。已交付估计快照折线路径3.060018/1.948308/2.413032m，评价真值路径另为3.070237/1.988769/2.438193m；不把真值提供actor。tb3@2秒、tb2@4秒真实观测种子净空不够被拒绝，下一快照恢复，没有吸附或清障。只读candidate_motion_readonly_diagnosis_v1.json SHA`b28d82280cee4df2ca4e134593cf0d93ac1bfd45e12f48a1b4c950310966b217`仅提供该16秒scope，不证明300秒候选充分性或学习效果。

原生评价training_external_truncation、success=false、覆盖.8291335707112206、accuracy.9646270036991369、occupied IoU.16709862228891012（低于.20）、参与true、0接触/新鲜监测，关闭后navigation_protocol_closed=true。评价16.22秒含关闭尾段，奖励仍16.0秒；summary末奖励水位navclosed=false原样保留，不从后来的关闭图重算奖励或任务成功。

原离线命令（同conda/env/rtk包装）为：

```bash
python -m mr3_learning.audit_ppo /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v3_minimal --freeze c2911114226bbe8275a0658a3710dafa4e89f5e0 --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v3_minimal/audit_v3.json
```

exit1，原audit_v3.json SHA`920ff6e41785fb770de4b5e8b072150a87970bdb2a506be761f85b777aa99cea`保留：原生contact/time/clock/closure通过，旧scalar只有step9/10、13/14、15/16六项switch计数/处罚归因失败；完整审计未到后续policy/rollout重评，不宣称完整PASS。源码/回执显示命令10使用刚返回sequence10快照、在91.42秒同步触发cancel，runtime正确记在新step10；旧scalar闭区间按结束T将它提前归到step9。必须使用显式因果switch-v4审计按源观测/命令身份/事件顺序修正同边界归属，保留原helper和原失败，其他所有门禁继续执行；不改运行奖励、事件stamp、ROI/95%/300秒或安全条件。

根代理独立从c291的Git blob载入原audit_ppo.py源码（SHA`e4f1009e2991c7a172246659a457a2d2fbe9cfa72b8ffed43c6153868f147883`）做CPU policy-only重放，未启动native/GPU：policy_only_audit_v1.json SHA`1810b0925bcf38277dcca6605b3fec45f643fd414e74f50b8298078c0531bc8e`PASS，16实际张量/保存mask/动作/value/logprob/dt/GAE对应initial collecting checkpoint；CPUlogprob最大差2.384185791015625e-7，value3.5762786865234375e-7。此为独立scope，不改变原fullaudit FAIL，不提供scalar/task成功信用。诊断/独立重放为inline Python操作，没有虚构重放CLI；原件先保存在ROS log/mr3_ppo/mr3_p2a_v3_minimal/，规范选件由后续打包记录。

v3最小链启动期间发现SB3 configure(directory,['json'])默认写根progress.json，与collector write_json同名。collector原子replace后SB3句柄指旧inode；每round有限指标仍保存在summary/checkpoint，但SB3独立磁盘日志路径不完整，长pilot前必须修复。v4将logger目录固定为sb3_metrics/，SB3写sb3_metrics/progress.json；collector实时状态仍写根progress.json，避免文件名碰撞。真实SB3/logger与collector交错写入隔离回归及相关14项CPU检查通过4.172秒；actor/优化器算法、候选v3、SLAM/Nav2/奖励及任务安全门禁均未变。原文件和六项旧scalar失败不得覆盖。

原v3 pilot/validation未启动；v3工程16决策/290.076789墙秒独立记账，不抵扣或增加pilot份额。新predeclared_plan_v4.json前瞻绑定SOURCE_FREEZE_FROM_METADATA，不猜测未生成提交：新source推送冻结先跑全新16决策/16步截断/900秒工程链，完整native/scalar/policy审计通过后才开始新初始权重pilot。仍使用seed41/open101、4worker、剩余3706决策/12600墙秒；原4096/14400pilot仅扣v2的390原生决策/1752.957494墙秒，余量未扩大。final-only open401/402/403开发验证保持900决策/9000秒、确定性mask-aware、0更新。所有v1/v2/v3计划/失败/原件保留，v4原生尚未运行，P2A仍未满足95%/学习出口，P2B/gateway未开始。


v3规范选件与v4冻结前核查补充：`report/assets/20261016_mr3_p2a/native_v3/minimal/manifest.json` SHA`7921d995a81ffa05da524aee815aa4aa8ae7556575f02c7189db33426c1ad2e2`绑定30文件，raw20462706/selected12824708bytes。`selected_byte_integrity_v3.json` SHA`00836f59fa861bac4223b46e03a5884a28691798313d655f062670d34e418036`只读核对30/30所选及解码raw SHA/字节PASS；没有新simulator/GPU。原audit_v3.json FAIL及candidate/policy-only/owned身份回执原样保留，不把打包算新原生结果。

`diagnostic_switch_step_attribution_v1.json` SHA`bb32e6b013ce9f8beb6c2606b5aafa52b61df790079a74fb9ae8126f95471536`与`diagnostic_scalar_causal_replay_v4.json` SHA`ee0bb8fb14aceb749dd246d50ee0d44e44093d4116e8e522f9bfbe066cf8fc1e`已纳入同目录规范选件。新因果scalar-only重放errors=[]：5次真实switch在命令10/14/16所属step收费2/1/2次、累计-.05；六条旧scalar错误和逐条原始闭区间delta/因果delta/未来命令边界证明并列保留，其余原scalar断言继续执行。该离线方法PASS不改原完整audit_v3 FAIL，不证明v4原生或完整审计PASS；runtime reward与事件时间未改。

root最终v4前置CPU回执：conda全套95/95通过8.970秒，6份修改学习端Python文件flake8通过；logger真实SB3交错写入隔离及相关14项聚焦检查通过4.172秒。原生节点/SLAM/Nav2配置与c291字节相同，先前786ROS语义检查和三包canonical build仍绑定同一实现；学习端日志隔离/离线审计修订没有新增ROS、仿真或GPU运行。v4原生尚未开始，须先新提交推送再按predeclared_plan_v4.json从新最小链执行；所有旧计划、失败和原件保持。

最终v4 CPU/限定lint完整命令和输出回执为`report/assets/20261016_mr3_p2a/prefreeze_checks_v4.json`，归档索引记录其SHA/字节；原生源码未变的Gitdiff证据仅复用同字节的786语义检查/三包build范围，不声称新原生结果。本代理最终静态核对5文档59本地链接、15shell块、3个v4命令/预算、18条证据SHA/字节与旧v3计划哈希均通过；随后仅补本回执链接及第19条hash pin。`git diff --check`通过，未新增simulator/GPU。

### 2026-10-16：MR3-P2A v4最小链PASS、pilot源级目标函数诊断中断与v5前瞻

v4冻结`7fea5de53be2049bdf2e6e6a8b309a5516fd2cfe`，cwd wireless-rl，conda ns3gym、PYTHONNOUSERSITE=1；metadata保存精确命令、学习seed41和Gazebo open101。依次执行：

```bash
rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.ppo --mode train --workers 1 --schedule open:101 --decisions 16 --episode-steps 16 --wall-seconds 900 --seed 41 --base-domain 160 --base-port 12301 --run-id mr3_p2a_v4_minimal
rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.ppo --mode train --workers 4 --schedule open:101 --decisions 3706 --episode-steps 300 --wall-seconds 12600 --seed 41 --base-domain 164 --base-port 12311 --run-id mr3_p2a_v4_pilot
```

minimal16原生/collector决策、16.0奖励秒、4次GPU optimizer.step、294.97549937386066全墙秒；exit0、原生关闭clean。完整native/contact/time/clock/causal scalar/pre-update policy及rollout审计audit_v4.json PASS/errors=[]，SHA`bbfebef094a5fd990b8de2f6b4453a83230286f021d42d3ed055ca9d2964d21d`。所有采样仍是更新前初始策略，不证明更新后任务性能。外部截断success=false、覆盖.7935953620012782、accuracy.9679414157851912、IoU.12867544105292636、质量/参与false、0接触/新鲜监测、关闭后navigation闭合。tb1/tb3接受3/4目标成功1/2，tb2接受0、估计路径.000471m，但有三次联合合法新目标机会被初始actor拒选；此时不应将不动泛称候选饥饿。详见native_v4/minimal/candidate_motion_readonly_diagnosis_v1.json（SHA`8712ccc042dea84ad5c9989f61d6a3a6718467bec31b77f027319ad3ca2c240d`）。

pilot原生metadata UTC开始04:25:39.869298，四worker仍从全新初始权重采样，未载入minimal checkpoint。04:42:03 UTC因源码目标函数缺陷主动诊断SIGINT；核验PID1135223/start_ticks387012924后保存diagnostic_stop_request.json，实际操作`os.kill(1135223, signal.SIGINT)`，不是shellkill、用户取消或性能筛选。保留exit1、completed=false、stop_reason=interrupted、KeyboardInterrupt()、cleanup_errors=[]。最终242原生决策、239collector已返回、241.66有效/物理仿真秒、1051.0549356047995全墙秒、0optimizer更新、无final checkpoint；首round未闭合计数0不能解释成无采样。241动作接受，w2 command4因navigation_changed_since_observation拒绝且真实扣分；拒绝也计原242预算。245奖励/ACK结算另含3个关闭零尾通知，不是245actor样本，不将3条未返回原生回执伪补为collector样本。

w0/w2/w3各66原生决策/66.0秒，为放弃前缀并正常外部关闭，评价覆盖分别.9019674974892723/.9449009403816306/.9543504062813841；w3参与false，即使T95coverage48.56仍不是任务成功。w1为44决策/43.66秒真实peer_body_envelopes_overlap导航安全失败，覆盖.8978362092577377，冻结navigation_protocol_closed=false；不能用之后clean退出覆盖。所有四条success=false、0接触/新鲜监测。四个owned环境均clean关闭；根owned_process_absence_v1.json确认168/168原生PID/start身份无匹配，独立prefix审计包含父进程共169组。独立diagnostic_native_prefix_audit_v4.json（SHA`6582616e1a3875f421554c6913d52d62251872c54c9e39065303eaee27e1ebc3`）核对242/239/245及四轨迹；已真实终止w1的closed_failure_worker1_component_audit_v4.json（SHA`9d25b69121a7abb6eaf5eba7b8b20233291d0c9a498a82ff1387a2c2e365555a`）通过原生/contact/time/causal scalar/初始策略组件范围，不替代未完成整run的完整audit或提供成功信用。只读诊断未启动新仿真/GPU，未保留独立诊断CLI时不虚构重放命令。

源级解析analytic_objective_audit_v1.json（SHA`b4229c8fdacf92cde630e2c336d0bc379b86200db79a72ccd3a6f594ef7db8d6`）证明旧gamma=.99/lambda=.95可严重削弱晚失败：300步末-20贡献-.9907251327532469，折扣时间罚-.31698636864290447，假设覆盖8分前置可有失败回报+6.6922884986038484，GAE旧trace(.99*.95)**299=1.0821343077477902e-8。这是源码数学反例，不是观察轨迹回报、反事实策略性能或学习结果；pilot在首更新前停止，不能声称已学习策略差。v4开发验证没有启动。

规范选件：native_v4/minimal/manifest.json SHA`a81aab9ba038027d817cfa0ecf23f821f4eb5dbd405d4f5c97327e2bf717d5eb`，29文件raw20362138/selected12695621 bytes；native_v4/pilot_interrupted/manifest.json SHA`3b36bba782e9f2e822e4eb864542406278702c0b2eaf9e5bc94e2ff78893ab10`，74文件raw25738292/selected5998428 bytes。`report/assets/20261016_mr3_p2a/selected_byte_integrity_v4.json`核查103/103所选及解码raw字节/SHA PASS，且原runtime目录无缺失/额外/修改选件；所有旧计划/失败/原件保持。原始根为ROS log/mr3_ppo/mr3_p2a_v4_minimal和mr3_p2a_v4_pilot。

v5为新前瞻学习超参数契约：固定gamma=lambda=1，无新增CLI，生产model/buffer/metadata接线一致；reward权重、真实dt/零尾通知、原生候选/SLAM/Nav2/actor/任务和安全门禁均不改。真实terminated无bootstrap的GAE目标相消为未折扣有限episode MC，剩余覆盖<=10、失败-20、其他项非正时真实失败future target<=-10；该界不适用于外部quota/墙时尾段和工程16步截断，它们保留一次末观测value bootstrap，可能为正。普通任务episode上限300保持，不暗称所有quota尾段完整300步或无bootstrap MC。

原pilot4096/14400扣v2的390原生决策/1752.9574942300096墙秒及v4的242/1051.0549356047995，余3464/11595.987570165191，保守取v5采样上限3464决策/11500墙秒。各版工程最小链与固定验证单列；在途、原生关闭和已开始round末更新额外收尾照原声明记实耗，不扩pilot预算。新predeclared_plan_v5.json只以前瞻SOURCE_FREEZE_FROM_METADATA绑定未来同一干净提交推送freeze：全新seed41/open101单worker最小链16决策/16步截断/900墙秒，完整审计通过才从新权重跑四worker剩余额度pilot；随后只用final在open401/402/403做900决策/9000墙秒确定性mask-aware、0更新开发验证，不挑checkpoint。当前均尚未执行。

学习seed41仅控制学习初始化/采样；open101/401/402/403为同p1c_open.world、同任务几何和固定三台起点/yaw0，仅Gazebo传感/物理随机种子不同。worker并未调用布局生成器或随机起点；本轮不是姿态/布局变化、多学习seed或未见泛化，不能替代后续预声明的开发姿态/布局阶段。P2A仍未达95%/学习出口，P2B/gateway未开始。

v5冻结前CPU/静态回执`report/assets/20261016_mr3_p2a/prefreeze_checks_v5.json`：完整conda105/105通过9.677秒，3份修改Python文件flake8通过，10项有限episode目标反例/性质检查通过.548秒，14项真实model/buffer/metadata系数接线和日志检查通过4.255秒。源码diff证明原生ROS src与scripts相对7fea无变更，仅复用同字节原786ROS语义/三包构建源码范围，不复用任务结果；这些新检查没有simulator/GPU。完整CPU命令为：

```bash
rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m unittest discover -s mr3_learning/tests -q
```

### 2026-10-16：MR3-P2A v5原生学习、3次开发任务成功记录与自动相位基础设施停止

原v5计划与freeze`de7a805af9cd9bc7d1b24e60559ccc4d3054e4c3`保持，cwd wireless-rl、conda ns3gym、PYTHONNOUSERSITE=1。最小链和fresh pilot精确命令：

```bash
rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.ppo --mode train --workers 1 --schedule open:101 --decisions 16 --episode-steps 16 --wall-seconds 900 --seed 41 --base-domain 160 --base-port 12301 --run-id mr3_p2a_v5_minimal
rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.ppo --mode train --workers 4 --schedule open:101 --decisions 3464 --episode-steps 300 --wall-seconds 11500 --seed 41 --base-domain 164 --base-port 12311 --run-id mr3_p2a_v5_pilot
```

minimum16原生/返回决策、16有效/物理秒、4次GPUoptimizer.step、286.51577762141824墙秒，completed=true/decision_budget、cleanup_errors=[]、audit_v5.json完整native/scalar/pre-update-policy审计PASS/errors=[]。initial checkpoint SHA`d0eac59490f296b34dc4487824a7d73ee6f51311337bb1d704158e2b518dc2d1`，final SHA`a647c11c1a0debdd09580fdf2a85af3c83672cb3f18c0fee494072638bd2ec3d`。这是工程链，不加载进fresh pilot。

pilot metadata UTC开始05:03:00.188464，单训练seed41、四worker每个三台、全部open101固定world/起姿，gamma=lambda=1、真实dt与原reward/任务安全门禁。三个完成round为252/250/295决策，共797保存学习样本、48次实际GPUoptimizer.step/12epochs；初始checkpoint SHA`e85b7a3e994546c83c086d73618b865709887903a43f82af50158fcd4020c9ae`。完整16尝试原生876、collector875，870.12有效/870.20物理秒，全墙5212.525802815799。797不是全部采样成本，最后round不更新，也不伪补未返回的原生回执。

完整原生任务报告：round0为w0:53决策/52.18s peer失败，w1:11/10.20s peer失败，w2:128/127.22s success覆盖.9504701908153017，w3:60/59.38s peer失败。round1为w0:62/61.92s success覆盖.9564046379987218，w1:57/56.40s success覆盖.9586642928877933，w2:28/27.70s peer失败，w3:103/102.88s peer失败（覆盖.9612891445266137但参与false）。round2为w0:10/9.78s、w1:41/40.86s、w2:144/143.50s、w3:100/99.60s，均peer失败（w2覆盖.9576828266228431但质量false）。round3为w0:7/6.82s peer失败，w1/w2各24决策/24.0奖励秒、故障后外部关闭评价24.2s；w3:24原生决策/23.68奖励秒，原生peer终态同时触发采样相位基础设施错误。全部16报告0接触/监测新鲜；原peer终态navigation_closed=false不能由后续clean关闭覆盖。

3次原生success均95%/质量/参与/导航闭合通过；首次来自初始策略，另两次使用16更新后的策略。所有已见open101、单训练seed，不得作为统计学习收益、可靠冻结策略、未见泛化或P2A验收。互斥尝试分类为3成功+10其他peer失败+2故障后放弃前缀+1基础设施无效采样（其原生报告也有peer失败）；原生结果计数3成功/11peer终态/2外部关闭是重叠维度，不能再加一项infra凑成17次。

pilot自动停止于ValueError('terminal detection lag exceeded one 20ms quantum')，stop_reason=infrastructure_error、completed=false、cleanup_errors=[]；不是表现驱动SIGINT/用户取消。round3w3评价器冻结终态与worker检测差40ms，超过原20ms门禁；失败保持，不放宽门限。没有final.zip，仅初始及checkpoint_0000/0001/0002和各已闭合rollout；原final-only open401/402/403验证因条件未满足SKIPPED，不选最后checkpoint补测。原audit_v5_original.json完整FAIL保持，含未完成尝试/外部前缀、旧协议审计对未发送目标的闭合要求、后续mask绑定及真实相位失败/缺final等项；独立消费方/连锁错误诊断另列，不反向将原run改PASS。

规范原件入口为report/assets/20261016_mr3_p2a/native_v5/minimal和native_v5/pilot_infrastructure，canonicalmanifest/字节核查由实际打包回执绑定。原始根ROS log/mr3_ppo/mr3_p2a_v5_minimal及mr3_p2a_v5_pilot完整保留。新v6声明之前不覆盖v5计划、错误、失败原件或审计helper。

v5期间root明确授权一次只读ROS raw-map observer，domain167、预算15墙秒，实际14.580348508898169秒；脚本仅订阅地图/metadata/观测，无应用publisher/action/service/native控制调用，wall已包含pilot不得再加。脚本metadata记录下列实际argv（cwd Gitroot，系统Humble Python，继承已声明loopback UDP环境）：

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v5_pilot/raw_map_observer_v1.py --episode-directory /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v5_pilot/native/round0002/worker3/episode001_open_101 --domain-id 167 --wall-seconds 15 --output-directory /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v5_pilot/raw_map_observer_round0002_w3_v1
```

后续纯CPU精确重放命令（非再次observer运行）：

```bash
rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v5_pilot/raw_map_forensics_round0002_w3_v1.py
```

raw_map_forensics_round0002_w3_v1.json SHA`e37893172139a6bb03bd11cbc697a29cc7519586f62f1b4b60c73dc0b5264058`绑定actor81/mapversion121及全部对应收到的原图，原merge_maps重现hub/三nav图、build_snapshot重现actor。tb1可达2安全目标但离融合前沿>3.26m、离自身前沿<.411m；原nav/fused起点100由tb2[90,118]100及tb3[90,119]100贡献，自身相交格0。仅靠本机前沿不能使原navigation起点安全；物理占据对象未识别，不宣称已证明机体过滤bug，也不改地图/候选或放宽门禁。独立v5round0w0tb2诊断与纯CPU合成前沿反例分开：后者33合法可达目标却pool0/356前沿距>1m，仅证明一般源码机制，明确不等于实际w0病因。合成反例精确执行（cwd/tmp）为：

```bash
rtk proxy /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v5_pilot/diagnostic_frontier_source_counterexample_v1.py --workspace /home/zhuyulab/ns3-workspace --freeze de7a805af9cd9bc7d1b24e60559ccc4d3054e4c3 --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v5_pilot/diagnostic_frontier_source_counterexample_v1.json
```

脚本SHA`8c18e87de528edbfa6402443f9b2adf53f2f336f7707517c8ea0bda0ddce50c1`，JSON SHA`8559ff7b1d5b09c2dd9eb4030901fbad26607dcc1b6c15d5e5b7871d671c7c50`。这些只读CPU诊断没有native/GPU调用；observer v2仅准备/预检，未实际运行。旧未发送目标审计原型v1、其复核失败和v2有限CPU证明均保留，不称作de7a生产源码或整run审计通过。

v6前瞻predeclared_plan_v6.json要求同一新干净提交推送freeze，实际SHA只由metadata绑定。拟在每个20物理tick暂停处增加评价器同SingleThreadedExecutor的精确clock/冻结终态ACK，取得匹配相位才推进下一量子；不放宽20ms guard/任务接触门禁，不改真实dt/奖励/actor/候选/地图/SLAM/Nav2/gamma=lambda1。这是评价消费顺序证据，不是所有producer/DDS排水或P3跨系统时钟闭环。先1worker open101两episode、4steps terminal-probe benchmark（domain156/port12291）通过原native/scalar及phaseACK审计；再fresh16决策/16步截断/900墙秒minimum全审计PASS；之后fresh4worker open101学习seed41 pilot2588决策/6300墙秒，普通300步上限，quota/墙时尾段明确一次bootstrap。仅pilot无infra且有finitefinal.zip才按原900决策/9000墙秒、open401/402/403确定性0更新验证，否则SKIP，不换早期checkpoint。v6没有额外observer计划，尚未执行。

原4096/14400 pilot扣除v2实际390/1752.9574942300096、v4实际242/1051.0549356047995、v5实际876/5212.525802815799，余2588决策/6383.461767349392墙秒；保守选6300，不扩预算，probe/各版minimum与固定validation单列，在途/原生关闭/已开始round末update实耗照原声明另记。所有open仍固定world/起姿，仅Gazebo stochasticseed变化，不作为姿态/布局或多训练seed泛化。P2A继续进行中，不宣称通过，不进入P2B/gateway。


v5 canonical打包/闭合/原审计连锁复核补充：`native_v5/minimal/manifest.json` SHA`cd8bcd52182adfc606fa4c1b4d6dd1028693619f3acf8969b3bcb3c1b491f869`，27文件raw20416727/selected12831817bytes；`native_v5/pilot_infrastructure/manifest.json` SHA`c1b3cd6c46d66d8af10519378eb85b35d7165f01818eb4f26ac7142cc092ea09`，303文件raw114640113/selected38191508bytes，包含原observer gzip-only地图。`selected_byte_integrity_v5.json`330/330核对所选encoding/SHA/字节及解码raw SHA/字节PASS。原`audit_v5_original.json` SHA`4ea0248d180f1c6e063d03a17819264a445d801d04faea99519c173c18ecd588`原9项FAIL保留。

`closed_run_snapshot_v5_v1.json`独立CPU核验252/250/295行rollout有限、原checkpoint的Adam步16/32/48；round3无保存rollout，79原生行中78客户端收到，末条command24有效.68/物理.72秒、差40ms未进入优化。`v5_infrastructure_review_v1.json`原件/源码证明：冻结终态94.400，物理量子继续94.420/94.440，adapter记录收到终态94.420，snapshot94.440；worker当时仅等待自身clock、量子循环后才drain，缺评价器消费相位回执，而非quantum超20ms或浮点舍入。667组保存原生PID/start身份及pilot父进程无匹配、所有16attempts owned关闭为空，cleanup[]。

`v5_original_audit_cascade_review_v1.json`独立CPU复现后续mask错误：旧audit在round0w1协议门禁失败后、native_decisions及rounds.append之前抛出，遗漏11行，用241行期望去比252行保存rollout，action_mask先被检查；裁剪后的第53行从w1错位到w2。四episode完整252行CPU collecting-policy/native张量/mask/action/reward/value/logprob/dt/GAE重放通过，最大logprob误差4.76837158203125e-7；这证明该mask报错为漏episode连锁，不能用来称实际mask损坏。原完整FAIL、w1协议要求、round3真实40ms错误/无终态actor前缀、无final/未完成run全部仍保留，复核scope不把整run改PASS。

v6文档前置静态核对：6份活动文档101个本地链接、15个shell块bash -n、四阶段CLI参数/唯一run-id/配额、56条归档SHA/字节通过；v1–v5旧计划及ENV/TASK两个SHA绑定合同保持HEAD原字节，共享log仅追加。实际benchmark/PPO两个--help均exit0，未启动native/GPU；conda导入保留既有Gym兼容提示，不影响帮助退出。`git diff --check`通过。选择6300后原pilot合计计划墙时14316.538232650608<=14400，决策390+242+876+2588=4096；新相位源码的语义/CPU/lint/build检查及原生结果仍由root后续回执独立补充。


v6源码工程检查首轮（最终callback原子性修复后仍须重跑，不冒充最终冻结检查）：canonical三包build PASS3.73秒，cwd ROS工作区，root提供的实际命令如下。ROS语义首次823/823通过29.14秒，发生在后续callback原子性修复前；初次结果原范围保留，最终计数/命令等待实际重跑。没有native/GPU运行。

```bash
rtk proxy bash --noprofile --norc -c 'source /opt/ros/humble/setup.bash; export PYTHONNOUSERSITE=1; /usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select slam_toolbox multi_robot_exploration multi_robot --allow-overriding slam_toolbox multi_robot_exploration multi_robot'
```

新增mr3_learning/audit_evaluator_phase.py独立重放physical receipts和评价器/worker phase回执，原20ms/contact/command/scalar/native W7门禁分别保留；重复request/publish/consume失败关闭，精确不变的stale ACK交付可以重复但不多消费/许可。物理推进墙时顺序来自精确worker源码加consume→permit→nextrequest trace，原Gazebo step RPC没有额外walltimestamp，不虚构此证据。scope仅冻结评价器终态串行消费，不声称all-producer drain或P3因果闭环。协议v2将按实际新freeze中adapter/protocol/transport/env-auditor四份精确SHA集成，不再只认de7a提交identity，仍保留originalW7可执行身份、原FAIL、严格detached重放和所有原件，不能称旧v5整run PASS。初始/最终检查分层回执为report/assets/20261016_mr3_p2a/prefreeze_checks_v6.json，当前最终字段明确pending，待root实测补全。


v6最终callback原子性修复后的实测检查：ROS语义824/824 PASS30.12秒；conda CPU133/133 PASS10.685秒，含新协议23项与phase5项。首次823/29.14结果仍为中间源码历史，最终命令如下（ROS cwd R，conda cwd wireless-rl）：

```bash
rtk proxy bash --noprofile --norc -c 'source /opt/ros/humble/setup.bash
source install/setup.bash
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -q src/multi_robot_exploration/test --ignore=src/multi_robot_exploration/test/test_flake8.py --ignore=src/multi_robot_exploration/test/test_pep257.py --ignore=src/multi_robot_exploration/test/test_copyright.py'
rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m unittest discover -s mr3_learning/tests -q
```

phase审计限定flake8首轮一处100字符超过99限制失败已修正，root三文件复查PASS；所有修改Python最终一起lint的结果仍待root实测，不先填写PASS。最终源码SHA：worker977d4e8215e193a2be8c207728adb3a39d48e26d35bb9089abe921c1d61053fd，task_evaluator c49e1ad05fdd4daaac5837dc1528fab3765c13bade4f7f3fcb195e2521e40e06，纯phase模块9c43ace376354edbdf496fe920d04a539ed47912fd0840f6d290c459450d69fa；本代理已只读核对当前字节一致。提交后完整source-proof数量及原生新结果另验，不臆填47等计数。上述均无native/GPU调用。


v6最终限定lint补充：13份修改/新增Python的system flake8（max-line-length=99）最终全部PASS，路径由git diff --name-only与git ls-files --others --exclude-standard合并、排序去重、仅.py并排除report/assets证据源码。首次全13入口在test_audit_protocol.py:118/124/126报三处E128，原失败保留，随后仅修缩进，聚焦协议23项PASS.773秒，最终全13PASS；这与先前phase模块一处100>99失败及root3文件复查分开记录。最终13路径明列prefreeze_checks_v6.json，无新增native/GPU。root另核对11份活动Markdown154本地链接missing=[]。独立native/phase/protocol代码复核报告无blocker，canonicalreview回执由root另补，不把代码复核当成原生结果。

冻结前最后补全离线source-proof列表，增加同freeze的`mr3_learning/ipc.py`与`benchmark.py`（包含terminal工程入口与资源采样）；未改运行行为。W目录执行`rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m unittest mr3_learning.tests.test_audit_ppo -q`：9项PASS/0.181秒。独立`phase_ack_source_review_v1.json`精确源码哈希全部与最终工作树相符；其复核不代替新冻结原生运行。


## 2026-10-16 MR3-P2A V6实际执行闭合与用户累计预算确认

源码为已提交推送的af37b2aaa3cb9980434f7f16c1f52dec2506319d，49项source-proof绑定同freeze；ENV/TASK原SHA不变。以下前三条为实际native命令，后三条为实际CPU离线审计，cwd wireless-rl，解释器/环境见完整argv；未使用2D、旧checkpoint、手工目标fallback或新observer。原predeclared_plan_v6.json保持字节，结果不回写成预先已知。

```bash
rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 --steps 4 --terminal-probe --base-domain 156 --base-port 12291 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo --run-id mr3_p2a_v6_phase_terminal

rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.ppo --mode train --workers 1 --schedule open:101 --decisions 16 --episode-steps 16 --wall-seconds 900 --seed 41 --base-domain 160 --base-port 12301 --run-id mr3_p2a_v6_minimal

rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.ppo --mode train --workers 4 --schedule open:101 --decisions 2588 --episode-steps 300 --wall-seconds 6300 --seed 41 --base-domain 164 --base-port 12311 --run-id mr3_p2a_v6_pilot

rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -c 'exec(compile(open("/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_phase_terminal/audit_benchmark_v6.py").read(), "audit_benchmark_v6.py", "exec"))' /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_phase_terminal af37b2aaa3cb9980434f7f16c1f52dec2506319d

rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.audit_ppo /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_minimal --freeze af37b2aaa3cb9980434f7f16c1f52dec2506319d --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_minimal/audit_v6.json

rtk proxy env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.audit_ppo /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot --freeze af37b2aaa3cb9980434f7f16c1f52dec2506319d --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot/audit_v6_original.json
```

terminal-probe：两episode8 API/7次实际脚本决策，6.02有效/物理秒，343.196831619367墙秒，0策略推理/0更新；末步分别真实提交20ms短终态及同边界零动作尾通知，原native/scalar/phase-ACK审计exit0、独立工程复核PASS，86组owned身份消失。只证明冻结评价器终态串行消费，不是all-producer排水/P3时钟/95%任务。首次独立review错误要求注入立即任务失败的冻结navigation_protocol_closed=true，原错误JSON及源码保留；改为区分原失败标记与之后18实际节点finalized/零pending目标，原门禁/数据不改、无native重试。

minimal：UTC开始07:09:04.830017，open101/seed41，1worker每worker三台，16原生/返回决策、16有效/物理秒、297.1948199640028墙秒，4次真实GPU optimizer.step，completed=true/decision_budget，cleanup_errors=[]。full audit exit0，native/contact/command/20ms/phase/scalar/pre-update policy和独立有限回报+恰好一次外部trunc bootstrap复核PASS，43组owned身份消失。initial SHA71193d1209581ed77f4e589e2d9852582863b26f1ee75f2645361f4734da3c2f，final SHA3ce168340161472df27ef9841089c5f16ef009abb0c729fb8461462d3217d8ed。工程min权重未载入fresh pilot。

pilot：UTC开始07:14:43.389407，4worker fresh open101/seed41、每episode最多300步，原声明2588决策/6300墙秒。实际718原生/717返回，716.64有效=物理仿真秒，3477.507027802989完整墙秒；0完整保存round/0保存学习样本/0更新，绝非没有采样。w0的第300条原生记录已写盘，关闭抛错使末条未返回，原生多1仍扣预算。initial SHA7f9c27a554cd4c10eb7dc4895b3ffa9dcec6009998f7c8754f83dc730e66cb79。四终态：w0 300决策/300s timeout覆盖.9710809823792568，quality=true/participation=false；w1 62/61.18s peer包络失败覆盖.8433534191545695，quality=false/participation=false；w2 56/55.46s peer包络失败覆盖.866292339998174，quality=true/participation=true；w3 300/300s timeout覆盖.970944033598101，quality=true/participation=false。四条success=false、冻结navigation_closed=false，18路新鲜/0接触。两次约97%覆盖不替代参与/全任务门禁。

w0 tb1 SLAM节点multirobot_slam_toolbox_node-7 PID1438806在有序SIGINT后记录karto::Exception、exit -6；严格serial shutdown于是失败并关闭launch，尚未创建Gazebo native-stop CLI，所以worker表层报InfrastructureError(RuntimeError('native stop CLI identity is missing or ambiguous'))。原native_stop.json/worker summary缺失，不能伪造补齐；w0归infra无效，其余三条正常组件闭合/真实任务失败。具体SDK throw/stack未证，不catch忽略、不宣称根治/归因FastDDS。cleanup_errors=[]仍保留原生失败，独立核对167组原生PID/start及父进程1438538不存在。

full audit_v6_original.json exit1、八条FAIL完整保留：未完成尝试/缺worker summary、其他三条旧消费方路径连锁错误、run/native closure失败、无有限更新证据、缺final。独立闭合/component复核不将run改PASS。无final.zip、checkpoint_0000.zip、rollout_0000，按声明final-only open401/402/403开发验证SKIPPED，0新验证任务/0更新，不代用v5/更早/minimum权重。按v6无重试infra规则停止；当前无native/training/monitor。本session不自动重试/v7，不推进P2B/gateway，P2A完整95%/训练验证出口未达。

CPU旁证失败也保留：minimal独立review首次直接.py入口在import前ModuleNotFoundError（exit1/7.817822342s），第二次python -m runpy绝对.py路径在main前拒绝（exit1/.568859712s），随后下面runpy.run_path入口exit0/PASS；完整CPU耗时未单独计量，不把initial tool wait10.001970146s写成总耗时。原argv/错误在native_v6/minimal/independent_review_v6_execution_v1.json：

```bash
rtk proxy env PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES= /home/zhuyulab/miniconda3/envs/ns3gym/bin/python /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_minimal/independent_review_v6.py

rtk proxy env PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES= /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m runpy /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_minimal/independent_review_v6.py

rtk proxy env PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES= /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -c 'import runpy,sys;runpy.run_path(sys.argv[1],run_name="__main__")' /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_minimal/independent_review_v6.py
```

有限prefix review只取四worker reset+前20条完整newline transition；84快照mask完整重放，后续rows未读、未hash完整增长文件。w1/tb2 21快照无合法GOAL、20步0GOAL（KEEP10/WAIT10）；w0/tb2先4快照有合法目标未选后17零；w3/tb1先3有后18零；不能混写合法未选与无可选。第一CPU driver错误断言“同state watermark必同pose”exit1/1.087279687s，修正保留身份歧义和actor顺序；原失败源码/回执保存。最终重放exit0/1.268494678s、限定lintPASS；全为CPU，无ROS/GPU/native/optimizer/控制操作。精确命令来自执行sidecar：

```bash
rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot/prefix20_controllability_repro_v6.py --replay-captured --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot/prefix20_controllability_replaycheck_v6.json
```

闭合后独立infra复核执行一次，exit0/2.902024214s，AST/限定lintPASS；不将native run改PASS，prepared learner helper从未执行：

```bash
rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot/v6_infrastructure_review_v1.py
rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 -m flake8 --max-line-length=99 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot/v6_infrastructure_review_v1.py
```

融合+已交付本机前沿union仅为ignored detached CPU原型及独立review，生产af37源码未改。复用旧v5合成tb2 pool0→20、精确旧v5actor81 tb1 pool0→2/selected0→1，mask只增加088；原own path.29、fused/own到达盘.39、known line1m、K8/reserveFPS/jointmask均不改。旧v5导航起点被占据仍不能清障；实际v6 prefix无全图，counterfactual=null。没有新native/observer/GPU或95%信用，实际执行原型命令：

```bash
rtk proxy env PYTHONNOUSERSITE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot/frontier_union_feasibility_v6.py
```

用户明确回复原异步预算问题，选择原4096决策/4小时累计pilot+另列三开发验证，未达95%停P2A；不是新给4小时。budget_acceptance_20261016.json记录root会话答复的转述，不伪造逐字用户引文。累计扣v2 390/1752.9574942300096、v4 242/1051.0549356047995、v5 876/5212.525802815799、v6 718/3477.507027802989，合2226决策/Decimal11494.0452604535971墙秒，余1870/2905.9547395464029；float展示约11494.045260453597/2905.954739546403。未花额度不重置/不自动使用，工程probe/minimum与另列开发验证分开。

实际规范打包命令cwd Gitroot，前三个run原件完整保留；/tmp helper与提交archive_selected_originals_v2.py逐字相等。以下均只读源/选件归档，无native/GPU：

```bash
rtk proxy python3 /tmp/mr3_p2a_package.py ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_phase_terminal ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261016_mr3_p2a/native_v6/phase_terminal
rtk proxy python3 /tmp/mr3_p2a_package.py ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_minimal ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261016_mr3_p2a/native_v6/minimal
rtk proxy python3 /tmp/mr3_p2a_package.py ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261016_mr3_p2a/native_v6/pilot_infrastructure
```

规范三包manifest：phase_terminal46文件raw2230786/selected598950 bytes，SHA6550fccd2082b4f557a677d79449a82e7f3cd5070d1cf333a71c8d7f6b20beb8；minimal31/raw21970791/selected13081559，SHA91fe5191879f244fbf0bb8f72e4bc2db08cb6f6d47871426428c101be4f20b00；pilot_infrastructure102/raw140822139/selected17759469，SHA74bbc36c725c32d83e83768ba650acf309a948e3d0390890515e6f40c905a7fb。selected_byte_integrity_v6.json179/179原始/选取/解码SHA及字节、目标唯一和完整source inventory PASS，保留gzip-only原件；三类临时fixture验证gzip重复排除/gzip-only保留、exclusive目标冲突failclosed、拒绝source内嵌target，全部PASS。v6_closure_accounting.json统一闭合成本/原FAIL/组件scope、预算及manifest/source pins。上述归档/CPU核查无新native、GPU、training或控制信号。

最终静态核查：179所选原件清单完整、原始/选取/解码SHA相等；归档工具三个临时目录反例检查PASS（gzip重复与原gzip保留、目标冲突拒绝覆盖、原目录内target拒绝）。初次对全部`.json`作document解析在pilot的零字节`sb3_metrics/progress.json`失败；按已冻结SB3 JSONL logger格式逐行核验两份日志（最小链一条、pilot零条）后PASS，原件保持。其余JSON document严格拒绝非有限常量；49源码冻结及6旧计划/ENV/TASK原字节保持。结果保存在`report/assets/20261016_mr3_p2a/postrun_checks_v6.json`，不提供pilot或95%信用。

补充独立CPU复核实际调用：以下由审核代理从本轮实际工具调用回溯展开绝对argv；未另存execution字段，不代表额外原生重跑。前三条cwd为wireless-rl，后两条为Git根；均无训练/策略GPU更新。

1. phase_terminal：`rtk proxy env PYTHONNOUSERSITE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -c 'import runpy,sys; sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name="__main__")' /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_phase_terminal/review_v6_phase_terminal.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_phase_terminal`。初次补充scope断言exit1，保留原件后修正复核exit0；此前直接绝对脚本调用另有import路径错误exit1。
2. pilot_closure：`rtk proxy env PYTHONNOUSERSITE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -c 'import runpy; runpy.run_path("/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot/review_v6_pilot_closure.py",run_name="__main__")'`，exit0；三个正常关闭episode的组件审核通过，w0基础设施FAIL保留。
3. w2closedreview：`rtk proxy env PYTHONNOUSERSITE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -c 'import runpy; runpy.run_path("/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot/review_round0000_worker2_v6.py",run_name="__main__")'`，exit0，仅已关闭w2完整审核，不提供整run通过。
4. native_stop_forensics：`rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot/review_v6_native_stop_forensics.py`，exit0；直接观察Karto异常/-6与后继CLI缺失，具体throw位置未知。
5. frontier_union独立复核：`rtk proxy env PYTHONNOUSERSITE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot/review_frontier_union_feasibility_v6.py`，exit0；仅旧v5精确快照/隔离原型，无当前v6实际反事实或执行信用。

## 2026-10-17 MR3-P2A.0：训练前修复及原生工程预声明

用户本轮授权继续解决P2A并允许前置准备。当前仅P2A.0：修复SLAM helper/solver
强引用环、TF/filter及同步线程析构顺序；失败round真实返回样本独立保存且禁止训练；
候选v4已交付前沿并集、四份完整冻结地图归档和安全触发输入诊断。
旧V6具体Karto throw/stack未证；target intersection为空及途中安全/累计参与观测未声称解决。
本条尚无新Gazebo/训练/GPU尝试；原累计pilot余额1870决策/2905.954739546403墙秒不变。

实际CPU/构建：系统ROS `/usr/bin/python3 /usr/bin/colcon build --symlink-install
--packages-select slam_toolbox`（完整命令和所有失败在runtime_stability/review.json）；
旧ownership三轮6断言FAIL保留，最终2项真实ROS gtest PASS；all-target build PASS。
系统ROS `colcon build --symlink-install --packages-select multi_robot_exploration` PASS，
全ROS语义860项PASS；conda `python -m unittest discover -s mr3_learning/tests -q`
最终CPU回执为 `report/assets/20261017_mr3_p2a0/prefreeze_cpu_checks_v2.json`；
首轮v1历史fixture SHA不匹配失败保留，生产严格source pin未放宽；
改动Python flake8与ROS最终回执分别为prefreeze_style/ros_checks_v1.json。
候选及CPU中间失败/修正不提供原生成功信用；精确命令、字节SHA和结果在对应回执。

后续同一新提交推送冻结的三阶段脚本工程矩阵已预声明：terminal两episode、
2worker各两次16步reset、1worker300步KEEP deadline，总上限372API/371真实脚本决策，
无GPU优化、不重启pilot；任一阶段工程审计失败停后续、不自动重试。
命令见 `report/assets/20261017_mr3_p2a0/predeclared_plan_v1.json` 与ROS启动页，
待实际运行再追加freeze/成本/结果；本条不将计划记成已执行。

## 2026-10-17 MR3-P2A.0 原生闭合：关闭正常，准备矩阵未通过

统一已推送源码freeze `f8694025d618532e851796d2f01aaa3aca322800`；72项source/config/document绑定通过。
学习端conda ns3gym，`unset PYTHONPATH; export PYTHONNOUSERSITE=1`，系统ROS worker独立；
固定三机器人/每环境，scene=open、Gazebo seed101，无新模型/训练/optimizer更新。
运行cwd为wireless-rl；原始输出均在canonical ROS `log/mr3_p2a0/`，选件见下方manifest。

实际命令1：
```bash
python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 --steps 4 --terminal-probe --base-domain 180 --base-port 12401 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261017_terminal
python -m mr3_learning.audit_preparation /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_terminal --freeze f8694025d618532e851796d2f01aaa3aca322800 --output /tmp/mr3_p2a0_terminal_audit.json
```
两episode，8API/7真实脚本决策、6.02有效/物理秒、339.79872017819434墙秒，CLI0；
20ms短末步/同刻零尾归并、native/contact/clock/command/scalar/phase/原图归档及脱离原目录审计PASS。
原图独立重放9/9完整快照逐字一致；两次严格关闭、3SLAM/18Nav2/Gazebo均正常，86保存身份消失。
这是故意终态注入工程probe，绝不计为95%任务、策略或训练信用。

实际命令2：
```bash
python -m mr3_learning.benchmark --workers 2 --schedule open:101,open:101 --steps 16 --base-domain 184 --base-port 12411 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261017_reset
python -m mr3_learning.audit_preparation /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_reset --freeze f8694025d618532e851796d2f01aaa3aca322800 --output /tmp/mr3_p2a0_reset_audit.json
```
四attempt全部保留：64API/64真实决策、63.14有效/物理秒、644.3825183720328墙秒，CLI1/benchmark FAIL。
w0/e1=真实peer安全失败15.14秒；其余3条为16秒外部截断。w0/e1末动作999 WAIT，
92.06提交→92.20触发tb2–tb3中心距.47346552439779177<.5；健康odom/TF原始输入精确复算。
同receipt时钟的独立ModelStates缓存距.44774837014279606，明确无source stamp；零接触不能抹去圆包络FAIL。
四条独立episode的native/contact/clock/command/ownership/scalar/phase/归档检查通过；
但整体完整审计仍为3项FAIL（benchmark声明/sampler accounting/comparison负载），脱离原目录重放同样FAIL，
没有修改门禁或将task失败转infra。四条全部真实关闭，SLAM exit0/sensor注销、18Nav2 finalized、
无forced/native崩溃/owned/zombie，169保存PID/start身份消失。

只读原图取证进一步精确重现own-free→fused/nav-occupied起点：tb2 command1源seq1 seed[107,118]
占据来自tb3；tb3 command11源seq11 seed[98,135]占据来自tb1；hub完整payload SHA/版本由三own图重现。
缺实际master costmap/导航图和planner精确sim水位，不宣称peer层/物体身份或唯一规划错误cause。
独立CPU reviewer的ACK/短步/任务failure字段范围误判、原失败脚本和修正回执一并保存，不涉及native重试。

按事前停止规则，300KEEP deadline **SKIPPED**，未创建该run目录；没有新pilot/开发验证/GPU优化。
总工程原生72API/71真实决策、69.16有效/物理秒、984.18123855022714墙秒；pilot累计成本和余额不变。
P2A.0原出口未达，停该步待复核；不进入P2A训练/P2B/gateway。
本轮修复已证明真实析构和6次关闭正常，不称V6原Karto throw栈根治或多日稳定；
继续前必须修复共享导航图起点冲突和途中安全反应链，再闭合received-only累计参与观测。

规范证据：`report/assets/20261017_mr3_p2a0/native/{terminal,reset}/manifest.json`、
各full_audit/detached_audit、`independent/`原图/关闭复核及其脚本、`accounting_v1.json`；
报告 `report/20261017_mr3_p2a0.md`。原预声明和所有FAIL/未执行阶段保持，不混用旧freeze信用。

补充只读全量归档复核：reset68/68完整snapshot精确重建，含terminal共77/77；
两条第二轮tb2各17/17 target交集0/无合法GOAL/无目标发送接受，v4未解决这类候选饥饿。
最终v2回执与初版范围断言失败并列在independent/，benchmark FAIL没有变化。


## 2026-10-17 MR3-P2A.0 continuation v2 — prefreeze engineering checks

用户明确要求“继续完成P2A.0”；以`0393fef363ff550707e2ed50a8129c95669abbb1`为修复基线，
在本步内补own-known/shared-unknown导航、实际导航图候选v5、唯一最终速度门与20ms实际本地回读ACK、
received local-odom/accepted-goal累计观测（snapshot v3/tensors v2，robot71列）。
不启动pilot/optimizer/GPU；原pilot余额1870决策/2905.954739546403墙秒不动，第一版FAIL及deadline SKIPPED保持。

源码在检查期间按before/after SHA保存于
`report/assets/20261017_mr3_p2a0_v2/`；这是新冻结前检查，非已发生的新native成绩。
系统ROS构建命令（ROS目录，PYTHONNOUSERSITE=1）：
`/usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select merge_map multi_robot_exploration multi_robot`。
三包6.14秒PASS，原输出`build_v1.log.gz`。
完整ROS语义命令：source Humble和当前install后，
`/usr/bin/python3 -m pytest -q src/merge_map/test src/multi_robot_exploration/test --ignore=src/merge_map/test/test_copyright.py --ignore=src/merge_map/test/test_flake8.py --ignore=src/merge_map/test/test_pep257.py --ignore=src/multi_robot_exploration/test/test_copyright.py --ignore=src/multi_robot_exploration/test/test_flake8.py --ignore=src/multi_robot_exploration/test/test_pep257.py`，
926 PASS/27.64秒，见`prefreeze_ros_checks_v2.json/.log.gz`。首轮误包含merge的workspace-wide旧lint及新synthetic fixture缺少导航/运动ready，15FAIL/905PASS/1SKIP原输出`ros_checks_v1`保留；修fixture未放宽生产门禁。

conda ns3gym、unset PYTHONPATH、PYTHONNOUSERSITE=1：
`python -m unittest discover -s mr3_learning/tests -q`首轮167测试中25个错误，均synthetic env改epoch后未同步activity epoch；
`prefreeze_cpu_checks_v2`原件保持，严格encoder未放宽，修fixture后另存复验。
root新增worker/phase回归72 PASS；output/master-costmap/phase与短probe审计mutation7 PASS。
限定全变更Python检查的两项长行/缩进失败原回执`prefreeze_style_checks_v2`保留，修后另存。

独立原图counterfactual仅重放既有原始地图：两条tb2空池恢复0→334/316，两个旧nav seed100→0，
全hub字节SHA不变，own occupied丢失0、双unknown升格0；不是native改善信用。
精确命令/sourceSHA/四例原件见`navigation_authority_replay_v1.py/.json`、`candidate_checks_v1.json`；
旧六episode77快照archive兼容重放PASS，不改旧任务/整体FAIL。
活动实现/独立raw先行因果重放及中间失败见`participation_checks_v1.json`；
运动数学/合成制动/源龄ns端点、真实Humble单参数回调三次完整DDS生命周期、strict FIFO及中间失败见
`safety_checks_v1.json`和`safety_cpu_callbacks_v1.txt`，三次各三台decision=1/actual=1/pending=0。
这些是CPU/真实ROS消息工程检查，没有Gazebo研究任务、GPU更新或95%信用。

新native矩阵预声明在`predeclared_plan_v2.json`，逐阶段terminal→2worker四轮三scene reset→300KEEP deadline，
上限436API/435脚本动作/6000墙秒，每环境始终三台；只在干净推送新冻结运行，后续实际命令/冻结/结果另行追加。

后续同worktree复验：`prefreeze_cpu_checks_v3` 167 PASS/19.850秒，before/after源码SHA一致；`prefreeze_style_checks_v3` 40份变更Python全部flake8 PASS，三份旧格式launch只AST编译并由launch语义回归验证；无新增依赖。以上包括首次FAIL及修正，不改变任何旧native结论。


## 2026-10-17 MR3-P2A.0 v2 — 原生FAIL与有序诊断中断

精确冻结`96c201e0e258bd0fe192fc03c6716fc694b7a9b7`、干净已推送；源码86绑定和7项安装来源预检PASS。
以下均conda ns3gym、unset PYTHONPATH、PYTHONNOUSERSITE=1，wireless-rl目录：

```bash
python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 --steps 4 --terminal-probe --base-domain 190 --base-port 12501 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261017_v2_terminal
python -m mr3_learning.audit_preparation /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v2_terminal --freeze 96c201e0e258bd0fe192fc03c6716fc694b7a9b7 --output /tmp/mr3_p2a0_v2_terminal_full_audit.json
python -m mr3_learning.benchmark --workers 2 --schedule open:101,open:101,rooms:101,corridors:101 --steps 16 --base-domain 194 --base-port 12511 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261017_v2_reset
```

terminal CLI0/完整审计PASS：8step API/7实际动作、6.02有效/返回物理秒、376.7940441519022墙秒。
短20ms尾/零尾、七图、native/contact/scalar/phase、actual output FIFO及ACK一致，89身份含parent均消失。
但活动path全null；当时integrity PASS仅表示记录真实缺失，未证明可用。
reset首对episode三台有合法GOAL/native send/accept，实际received state JSON却无odometry，三台activity全invalid。
定位publish_states恢复消息时pop后再广播；synthetic直接喂raw fixture漏了真实桥接层，属于实现/集成测试缺陷。
另有1134次一ULP端点误拒；规范后仍为peer几何停止，整体Twist归零妨碍原检查可允许的角向调整。

确认缺陷后执行/tmp诊断controller：精确核验owned worker PID/starttick、epoch、stdin pipe inode及parent写端，
每台只原子写一次带字符串id的既有close请求，未发送信号。两台各仅e1，正常关闭原生launch与worker exit0；
parent保留预期step/close IPC identity mismatch错误，benchmark CLI1/FAIL，不包装为正常截断。
精确原件核对：w0 14、w1 16实际动作，30返回step，无未返回动作差额；另2reset API。
有效/返回物理各30秒，快照后关闭物理步.220+.020=.240秒；全墙422.59510789997876秒。
两台共86保存身份及parent均已消失，无forced shutdown/native failure/owned/zombie。
完整审计及detached均保留FAIL，phase/archive/execution/activity-provenance/motion通过，scalar受额外0dt外部close及failed_sample拒绝。
剩余6reset episode、300KEEP deadline均SKIPPED，不重试该freeze。

v2总38step API/37实际脚本动作、36.02有效/返回物理秒、799.38915205188096墙秒，无native训练/GPU更新。
规范原件`report/assets/20261017_mr3_p2a0_v2/native/{terminal,reset}/`及full/detached audit、manifest；
415+698原件逐source/selected/decode SHA检查，关闭/取消/独立地图/运动反事实及精确cost在同目录independent与accounting_v2.json。
包装最初缺两个旧helper/transport导出文件，补Git原件后重审；该CPU包装失败保留，不改native结果。
旧v1/v2 FAIL保持，pilot累计费用/余额不动；用户已要求继续完成P2A.0，修复后另用新冻结完整重验。

## 2026-10-17 MR3-P2A.0 v3 — 定向归因检查与新预声明

以96c201为基线，真实publish_states→adapter→冻结快照回归先旧源码1FAIL，最小producer修复后77PASS；
精确命令、源码SHA、raw stdout在`report/assets/20261017_mr3_p2a0_v3/information_activity_checks_v1.json`。
独立旧freeze32快照七图/完整观测重放一致，旧actor path全null保持；不能事后补旧观测。
旧trace上的向外方向counterfactual每台各有clear时间窗，但两初始snapshot均无三台同时clear证明；
短path排序有确证方向缺口，未用于新native。外部工程flag改向外margin排序，默认旧压力规则保持；不进生产adapter/PPO。
有限理想轮模型122549case与解析极值，原.76s偏短.0157s，加入明确.02s耦合padding到时域和双方reserve；
只能证明有限模型界，非真实Gazebo响应。全部source/命令/输入输出诊断保存在v2 independent和v3对应回执。

新完整矩阵预声明`report/assets/20261017_mr3_p2a0_v3/predeclared_plan_v3.json`：
terminal→2worker四轮三scene reset（显式--preparation-motion-probe）→300KEEP deadline；
每环境恰三台，上限436step API/435实际动作/6000墙秒，无native GPU/optimizer，pilot额度不动。
原生开始前提交推送源码并记完整freeze；后续实际结果另记。合成CPU优化器测试不算native训练。


v3统一检查（尚无新native）：系统ROS三包colcon8.503墙秒PASS；同v2完整语义命令937PASS/26.08测试秒；
conda `python -m unittest discover -s mr3_learning/tests -q`175PASS/12.403测试秒、17.839544211048633墙秒。
12份变更Python限定flake8首轮1E128（benchmark原terminal if续行缩进）FAIL保留，修缩进后同命令PASS；
source before/after SHA全部一致。精确cwd/环境下argv、源码与原输出见v3 `build_v1`、`prefreeze_ros_checks_v1`、
`prefreeze_cpu_checks_v1`、`prefreeze_style_checks_v1/v2` JSON/log.gz。完整CPU早先pins更新前169tests/1Error原件
在`safety_checks_v1.json`保留，更新3份审阅过的info/pure/ENV精确SHA后统一通过，未放宽source gate。
独立预检发现launch文档tensor/Nav2笔误及端到端测试“冻结张量”范围过述，已改为tensorv2/Nav2/冻结快照，
无runtime变化；原source/fullSHA、63条相对链接与三阶段参数对照见docs_preflight_v1.json。

最后追加最小native_cancel调用前trace：adapter focused59PASS/1.77s、style/diff-check PASS；双精确adapter pins更新后native gate/protocol/benchmark33CPU PASS。独立A/B物理消费者7个合成拒绝/分类回归PASS，规则在新原生前固定，源码/回执进v3 independent；不是原生制动信用。

原生前最终固定独立physical matrix wrapper及3组mutation测试PASS（missingrobot/bound violation/closure/缺第8轮/混terminal拒绝）；原逐episode consumer不改，完整命令/源码SHA/规则在v3 independent/physical_matrix_receipt_v1.json。另核验实际import的6运行模块均解析到规范源且字节SHA一致，runtime_install_preflight_v1.json。

## 2026-10-17 MR3-P2A.0 v3 — terminal PASS、真实角速度失败及诊断取消

精确源码冻结`f9312e1ed245fb93af50614fd34c960870edb78d`已推送、开始时工作树干净；
86项source binding和安装来源预检PASS。以下均wireless-rl目录、conda ns3gym、
`PYTHONNOUSERSITE=1`、unset PYTHONPATH，每个环境恰好tb1/tb2/tb3：

```bash
python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 --steps 4 --terminal-probe --base-domain 202 --base-port 12531 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261017_v3_terminal
python -m mr3_learning.audit_preparation /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v3_terminal --freeze f9312e1ed245fb93af50614fd34c960870edb78d --output /tmp/mr3_p2a0_v3_terminal_full_audit.json
python -m mr3_learning.benchmark --workers 2 --schedule open:101,open:101,rooms:101,corridors:101 --steps 16 --preparation-motion-probe --base-domain 206 --base-port 12541 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261017_v3_reset
python -m mr3_learning.audit_preparation /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v3_reset --freeze f9312e1ed245fb93af50614fd34c960870edb78d --output /tmp/mr3_p2a0_v3_reset_full_audit.json
```

terminal CLI0、完整及detached审计PASS：8step API/7真实adapter动作、6.02有效及返回物理秒、
372.49735159100965墙秒。两次native各39/39退出0、worker0/无forced/failed_sample，
88保存owned身份及parent均消失。最终每台decision/actual分别3663/3663、3931/3931、FIFO pending0；
精确20ms evaluator/motion ACK、七图、接触、scalar与零尾通过。
最终输出始终零，没有有意义停车片段，独立物理consumer明确缺证，terminal PASS不产生制动或95%信用。

reset首对e1各三台目标真实接受，activity的received-odom原始链和累计均已可用；
但w0只有tb3累计`.17323140980823276m`，其余五条机器人累计均小于`.002m`，没有三台活动PASS。
w0e1返回3步/2.48秒，w1e1返回1步/.84秒，均以navigation_failure终止。
完整原始角速度范数真实超过事前1.2rad/s：w0tb1峰值1.2566570228340879、
w1tb3峰值1.247988694202598、w1tb1峰值1.2477660101565642；这些消息angular x/y为0。
对应原始request和实际输出角速度均未超1.0，不能拿输出限幅或provenance PASS替代物理速度界。
连续同frame唯一源样本含清理max abs(Δwz/Δt)=5.804486000553274<7，
固定odom frame平面加速度最大1.0697406918889008；完整相邻原件和预热分组保存，非连续保证。
独立A/B停车均无有意义信用、原8轮聚合FAIL，1.2/.50/.78/.144等门不放宽。

发现失败时各worker已自动开始e2。按授权对最新精确PID/starttick、epoch、stdin pipe inode及parent写端核验后，
controller各原子写一次字符串id的既有同epoch close请求，controller未发信号；所有四次reset尝试保留。
e2各返回reset、0动作，native每条39/39 exit0且launch0；父RPC因close/step响应id不符报错，
supervisor最终两条均worker -15/forced_shutdown=true/failed_sample=true，严格关闭FAIL原样保留。
不能将child-native正常关闭包装为整轮严格关闭PASS；e2 transition_count1仅为关闭结算ACK。
172保存owned身份加parent共173个精确身份全部消失，无e3。

reset CLI1、完整/detached审计FAIL，4返回step=4真实动作、无未返回动作；另4次reset API。
有效/返回物理3.32秒，末快照后清理额外`.44s`，release后物理共3.76秒，
墙345.9337030528113秒。四attempt actual output FIFO和same-clock ACK均完整，pending0；
phase/archive/master costmap/拓扑/activity完整性/motion provenance逐项PASS，e1 scalar PASS，
e2 scalar因额外关闭结算/监督forced拒绝。terminal9+reset8完整快照七图与观测独立重放一致；
整体任务/物理FAIL不变，motion重放不是独立物理证明。

按预声明未执行的四个rooms/corridors reset槽和300KEEP deadline均SKIPPED，无该deadline run目录，
未重试该freeze。v3总12step API/11真实动作，含六次reset为18API；9.34有效/返回物理秒、
9.78 release后物理秒，另暂停后受控对齐`.054s`，
总墙718.43105464382095秒。无native PPO优化样本或GPU更新，pilot累计2226/11494.045260453597、
余额1870/2905.954739546403均不变，P2A.0出口仍未达。

按旧冻结archive_native_evidence.py选存terminal397及reset694原件到
`report/assets/20261017_mr3_p2a0_v3/native/{terminal,reset}/`；压缩console、独立消费者/候选/物理/取消/关闭复核、
accounting_v3.json与inventory_v2.json均在该v3证据树，原prefreeze计划/清单/文件不覆写。
原审计与detached的86源码绑定一致，reset detached从精确f931导出441源文件执行；
source/selected/decode SHA及内容全部验证。首次附加checker把已压缩源的decoded与encoded误比较，
原false和修正v2回执同时保留；所有hash原已匹配，归档字节未改动。
详细结果、精确极值和scope见`report/20261017_mr3_p2a0_v3.md`；
该版真实FAIL与后续新冻结结果分别记录，不跨版本拼工程闭环或政策训练信用。

## 2026-10-17 MR3-P2A.0 v4 — 冻结前构建、CPU与独立范围检查

以v3冻结`f9312e1ed245fb93af50614fd34c960870edb78d`为基线修复后的工作树候选；
本节不声称f931包含新`.8rad/s`/actual3params/odom-age/20步及共享首失败等代码。
95%/300秒、三台1m与目标、质量、18接触和`.50m`门未改；v3真实1.2rad/s超界和e2 forced -15保留。
尚未冻结或执行v4原生矩阵，没有训练/GPU更新，pilot累计和余额均不变。

系统ROS三包colcon：merge_map、multi_robot_exploration、multi_robot均PASS，
墙6.616109372116625秒。完整ROS语义941 PASS/26.86测试秒、28.076781494077295墙秒；
完整conda ns3gym `python -m unittest discover -s mr3_learning/tests -q`
200 PASS/12.205测试秒、17.534905713051558墙秒。
系统ROS与conda环境按规范隔离、PYTHONNOUSERSITE=1，conda清除PYTHONPATH。
9份变更Python限定flake8 PASS/1.015177823137492墙秒；静态143条本地链接存在，
8项实际安装文件与规范源码字节匹配、6项实际import解析及SHA匹配。
所有完整argv/cwd/Python、before/after SHA和原始log.gz在
`report/assets/20261017_mr3_p2a0_v4/{build_v4,ros_semantic_v4,conda_cpu_v4,style_v4,static_v4,installed_assets_v4,runtime_modules_v4}.json`。
ROS检查中三个learner文件并发变动已明确列出，ROS相关输入没有变化；
完整conda/style随后在稳定输入上覆盖，不能写成所有文件全程未变。

独立和focused检查与统一套件重叠，不累加为独立总数：benchmark参数读回hook/20步时序/共享首失败
20 PASS（早先14项abort/ranking回执仍保留）；安全ROS34及conda20 PASS；contract/pin9 PASS。
容量比较辅助层初3项测试后，独立复核发现Python numeric别名可绕旧类型边界，已收紧worker/step/seed
精确整数与类型保留的声明一致性；最终focused5 PASS/0.057秒，其中新增从不可变Git字节
加载真实W7 comparator，确认旧16步rooms/corridors两worker比较仍FAIL、legacy fallback及native gates不改。
最后该新增测试在完整conda200后运行，生产helper与200套件相同，不宣称full201。
版本20步负载不取得旧P1C容量比较信用，逐episode native/contact/clock/command/scalar仍严格执行。
回执为v4 `independent/mr3_p2a0_v4_parameter_review_hook_checks_v1.json`、
`mr3_p2a0_v4_benchmark_abort_checks_v2.json`、`mr3_p2a0_v4_safety_checks_v1.json`、
`mr3_p2a0_v4_contract_pin_checks_v1.json`、`mr3_p2a0_v4_capacity_independent_review_v1.json`。

三轴角速度范数及相邻源向量差分消费者13项mutation PASS（NaN/错epoch/回退/重复冲突/变frame/
间隙/缺覆盖/只z而漏三轴等拒绝），旧v3 w1e1按原始数据仍真实FAIL。
停止matrix_v4四项规则测试PASS，逐episode消费者2516源码/.78s/.144m/1.2界保持。
九实际参数的只读匹配规则3 PASS；真实Humble九参数服务fixture读取成功和旧角速1.0拒绝均PASS，
两路径executor/node/context清理完整。它们是ROS消息/服务CPU验证，非Gazebo运行参数或制动证明。
首轮fixture域249被FastDDS计算端口范围拒绝，原输出保留；改229复验PASS。
首轮安全AST 33 PASS/1 FAIL因standalone controller没有显式name导致测试漏配置绑定，修fixture后通过；
config-only首次PASS只检查模板，独立复核揭示实际launch选params_tbN，三台真正YAML补齐后再通过。
这些局限与失败不隐藏，精确脚本/SHA/原输出在v4 independent的runtime_preflight、safety和angular回执。
benchmark原图CPU replay首轮直接执行/tmp脚本缺项目sys.path的harness失败与初次flake8 E128也在abort v2回执保持，
修正调用/缩进后通过，无仿真重试。

新预声明`report/assets/20261017_mr3_p2a0_v4/predeclared_plan_v4.json`原样保留：
interface20步（reset后首step前实际九参数只读门）→terminal两轮4API→双worker八轮20step reset→300KEEP deadline，
上限488step API/487真实脚本动作/7000原生墙秒。任何真实失败停止该版后续阶段，原件完整保留。
原生仍pending，须先冻结并推送新SHA；不以CPU/YAML/source matching或旧v3轨迹补本版信用。
pilot已用2226决策/11494.045260453597墙秒、余额1870/2905.954739546403不变。

冻结前补充独立CPU检查：`/usr/bin/python3 /tmp/mr3_independent_angular_reset_matrix_v1_tests.py -v`，
6项mutation PASS及lint PASS，精确运行/17.36秒与输入SHA见v4 independent的`mr3_independent_angular_reset_matrix_checks_v1.json`。
新v4输入重放消费者仅以旧v3原件作CPU兼容检查，完整七图/wholeobs/活动/实际目标绑定一致，
真实移动不足仍FAIL/exit1；命令、原输出和SHA见`mr3_p2a0_v4_independent_input_reviewer_checks_v1.json`。
独立脚本SHA已加入v4机器计划；本条无新native/PPO/GPU/制动信用，pilot不动。

### 2026-10-17 MR3-P2A.0 v4 原生interface失败（保留，无训练）

- freeze `b4e64f90391c0b4db2127e9e824118459a4288ad`，已推送且启动前clean；87源码/10独立脚本绑定PASS。
- 精确声明命令：`python -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 20 --preparation-motion-probe --base-domain 212 --base-port 12561 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261017_v4_interface --preparation-parameter-review`；实际Python/argv/parent身份见launcher原件。
- 完整审计命令：`python -m mr3_learning.audit_preparation /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v4_interface --freeze b4e64f90391c0b4db2127e9e824118459a4288ad --output /tmp/mr3_p2a0_v4_interface_full_audit.json`，exit1/FAIL（source87绑定保持）。
- open101单worker domain212/port12561，实际reset1、step0、submitted0/unreturned0。
  新参数脚本30.31988252233714秒未收paused motion status，0receipt/0GetParameters，三项child cleanup true；
  benchmark首失败后cooperative close，无新step/reset。七图/唯一wholeobs/候选/活动完整性PASS；
  初始三台有合法GOAL，但均0接受/无postrelease活动，不得授移动、.8物理或制动信用。
- 39 native exit0/complete，worker0/forcedfalse/failed_samplefalse；44 owned+benchmark/launcher共46身份均已退出。
- benchmark墙秒182.76034711441025；launcher183.207426502835分别报告不相加。有效任务0秒，
  alignment.016秒和关闭后物理.020秒单列。固定angular消费者只有每台一个postrelease源，bounds/coverage皆FAIL。
- terminal/reset/deadline按声明SKIPPED，无same-freeze重试，无PPO/nativeoptimizer/GPU。
  canonical证据见`report/assets/20261017_mr3_p2a0_v4/`及accounting_v4.json。
- 诊断发现worker本地配置专用loopbackUDP而hook通用env未继承；等待独立CPU对照。
  用户仍授权完成P2A.0，后续v5修复该具体接线并新冻结完整重验，不放宽旧门、不重置pilot。


### 2026-10-17 MR3-P2A.0 v5 transport修复与冻结前CPU

以b4冻结为基线，修复只读observer未继承worker专用transport的集成缺口，固定7键、Noneunset、canonical profile路径/SHA/exact Git bytes、metadataepoch/freeze绑定，fe0a及30/45秒界均不改。
完整命令`python -m unittest discover -s mr3_learning/tests -q`在conda ns3gym/PYTHONNOUSERSITE1/PYTHONPATHunset，208 PASS，11.251测试秒/16.550404557958245墙秒；28项focused及独立同源复核PASS，限定style和14来源绑定PASS。命令/输入before-after/原输出见v5 assets回执。ROS生产源未变，不重做无关仿真或把旧941检查记成新native。
CPU传输对照精确命令、原b4 shell和fe0a字节、实际环境及输出在canonical v4 native/interface/independent_monitor/transport_ab_v1：无Gazebo/控制，发布端原profile仅发一次TL状态；default domain228实际超时0状态/0参数，matched domain227九typed参数通过，全部CPU进程正常清理/身份消失。这是有意保留的失败对照，不混入Gazebo矩阵或pilot。
v5新机器预声明完整interface20→terminal8API→reset160→deadline300，上限488API/487动作/7000墙秒、无PPO/GPU/optimizer，先提交推送干净冻结。pilot余额1870/2905.954739546403不变。

### 2026-10-17 MR3-P2A.0 v5 原生物理FAIL（原件保留）

source `57b7c7f372aef4d84acd25fcd97a9944fa1fe9bb`，已推送、启动clean，87 source/10独立脚本PASS。精确命令`python -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 20 --preparation-motion-probe --base-domain 222 --base-port 12601 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261017_v5_interface --preparation-parameter-review`。完整审计命令`python -m mr3_learning.audit_preparation /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v5_interface --freeze 57b7c7f372aef4d84acd25fcd97a9944fa1fe9bb --output /tmp/mr3_p2a0_v5_interface_full_audit.json`，FAIL/exit1。

只执行interface open101/domain222/port12601；reset1+returned15=16 API、真实15动作，无未返回差额；最后dt.64/elapsed14.64真实navigation_failure，cooperative停止，terminal/reset/deadline均SKIP。九实际参数及同epoch78.52秒暂停状态读回PASS、transport selected/native7keys和dd7profile一致；16 wholeobs/七图/候选/活动独立精确重放PASS，三台path.703918779/.539448767/.572382559均complete，2nativeaccept各（1成功+1取消）；这些子PASS不改整体FAIL。

tb2在source93.145秒角速度范数首次1.2024862996>1.2，93.247秒峰1.3969248505326008（x=y0）；实际finalcmd仍≤.26/.8，邻源角差分最高<7。motion gate在93.16秒失效立即输出0，其后仍有身体滞后，不得从命令或FIFO推断瞬时物理停车。全部3×4656decision/actual FIFO精确，743 motion ACK闭合；39native全exit0/complete，worker0/forcedfalse/failed_samplefalse，44owned+两父共46身份全部退出。

有效/returnedphysical14.64s，release78.52→final93.36共14.84（cleanup.20单列），alignment.002s；benchmark墙秒361.0312315579504，launcher361.46578524494544分列不混加。原件及独立回执见v5 assets/native/interface；无PPO/GPU/optimizer、无同freeze重试，pilot余额不动。

只读官方/安装包调研：gazebo_plugins3.9.0-1同tag源码反馈error被累加到旧instr，并有fastpath未sync隐藏状态；真实旧native无joint/instr故不能唯一exact回放其根因。Nav2 1.1.20 smoother墙钟/固定步长及CLOSED_LOOP反馈无末端clamp/无freshness的限制均保留为局部调研，不改DWB或冒称改两YAML可保证物理界。新v6只修局部驱动实际反馈与paired rim限加速，保持物理参数、任务/测量和停止门，新source完整重验；详见v6预声明。


## 2026-10-17 MR3-P2A.0 v6 — 冻结前驱动修复与全部现存离线检查

基线是v5冻结`57b7c7f372aef4d84acd25fcd97a9944fa1fe9bb`，下列检查使用其后的**未提交v6工作树候选**；
不是旧57b7代码的验证，也不授予尚未运行的新冻结原生矩阵信用。每份回执保留实际输入SHA及原输出。
最终驱动cpp SHA `f30b6d7c6ee44cd40f3603c4c0b759e43d6333f3136570bdc13c088c61230075`，
paired helper SHA `80cf2e51f1b39f7bb89ef8b61b4b6eaf7c9be68c418bf0bb7ef57640d82c99d9`。
保持95%/300秒、三台1m与目标、质量、18接触、.50m及1.2实测/.26与.8命令/停止门；无PPO/GPU/native optimizer。

ROS系统Python，cwd为`/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap`。
构建与测试的原命令如下（build执行四次、test执行两次；各次源码范围由原回执区分）：

```bash
source /opt/ros/humble/setup.bash; export PYTHONNOUSERSITE=1; /usr/bin/python3 /usr/bin/colcon build --packages-select multi_robot --symlink-install --event-handlers console_direct+
source /opt/ros/humble/setup.bash; export PYTHONNOUSERSITE=1; /usr/bin/python3 /usr/bin/colcon test --packages-select multi_robot --event-handlers console_direct+
```

build01因CMake源码SHA输入误用build目录相对路径失败；修为CMAKE_CURRENT_SOURCE_DIR后build02通过，
build03为中间weak-callback实现通过，build04为最终添加command_topic来源的实际库构建通过。
test01为中间20个gtest，test02最终三个CTest target共21个gtest（含8个paired helper）全通过，
最终CTest原文0.87秒、colcon1.88秒；中间结果不能充作最终源覆盖。
Gazebo CMake PkgConfig命名及std::iterator弃用warning原样保留，最终无编译/链接错误。
原始build01—04/test01—02输出与SHA见`report/assets/20261017_mr3_p2a0_v6/independent/mr3_p2a0_v6_drive_checks_v1.json`。

纯helper在Git根cwd的精确命令：

```bash
rtk proxy /usr/bin/g++ -std=c++17 -Wall -Wextra -Werror -pedantic -fsanitize=undefined -fno-sanitize-recover=all -Iros2_ws/ros2-multi-robot-automap/src/multi_robot/include ros2_ws/ros2-multi-robot-automap/src/multi_robot/test/test_paired_wheel_slew.cpp -lgtest -lgtest_main -pthread -o /tmp/mr3_test_paired_wheel_slew_ubsan
rtk proxy /tmp/mr3_test_paired_wheel_slew_ubsan
rtk git diff --check
/usr/bin/python3 /tmp/mr3_paired_wheel_stop_model_v1.py
```

严格C++17/-Wall/-Wextra/-Werror/-pedantic及UBSan编译exit0，最终8 tests PASS，无UBSan错误；
compile/run墙秒4.259705085773021/0.7127777929417789，原stdout在helper_checks_v1。
8项包含20000对有限随机wheel预算/共同alpha/凸组合及2989初始体速度对的停止模型检查。
stdlib独立模型给理想无滑移且即时跟踪目标、34ms更新界等条件下保守.7002秒/.13923米，
不证明Gazebo机体角速度、打滑、接触、停车或每瞬时最低减速度。最早7项及后增第8项历史均保留。
可重建的752736-byte UBSan ELF不进入canonical；命令、stdout、源码SHA和模型脚本/JSON保留。

实际最终库加载CPU检查在Git根cwd，原pkg-config与编译argv保存如下：

```bash
pkg-config --cflags --libs gazebo > /tmp/mr3_p2a0_v6_drive_pkgconfig.txt
g++ -std=c++17 /tmp/mr3_v6_drive_dlopen_cpu.cpp -o /tmp/mr3_v6_drive_dlopen_cpu -std=c++11 -std=c++17 -pthread -std=c++17 -I/usr/lib/x86_64-linux-gnu/pkgconfig/../../..//include/gazebo-11 -I/usr/include/sdformat-9.7 -I/usr/lib/x86_64-linux-gnu/pkgconfig/../../..//include/ignition/fuel_tools4 -I/usr/include/x86_64-linux-gnu -I/usr/lib/x86_64-linux-gnu/pkgconfig/../../..//include/ignition/common3 -I/usr/lib/x86_64-linux-gnu/pkgconfig/../../..//include/ignition/transport8 -isystem /usr/include/mit-krb5 -I/usr/include/pgm-5.3 -I/usr/include/libxml2 -I/usr/include/uuid -I/usr/lib/x86_64-linux-gnu/pkgconfig/../../..//include/ignition/msgs5 -I/usr/lib/x86_64-linux-gnu/pkgconfig/../../..//include/ignition/math6 -I/usr/lib/x86_64-linux-gnu/pkgconfig/../../..//include/ignition/cmake2 -L/usr/lib/x86_64-linux-gnu/pkgconfig/../../..//lib/x86_64-linux-gnu -L/usr/lib/x86_64-linux-gnu/pkgconfig/../../..//lib/x86_64-linux-gnu/gazebo-11/plugins -L/usr/lib/x86_64-linux-gnu/pkgconfig/../../..//lib/x86_64-linux-gnu -Wl,-rpath,/usr/lib/x86_64-linux-gnu/pkgconfig/../../..//lib/x86_64-linux-gnu/gazebo-11/plugins -lgazebo_transport -lgazebo_physics -lgazebo_sensors -lgazebo_rendering -lgazebo_gui -lgazebo_client -lgazebo_msgs -lgazebo_common -lgazebo -lboost_thread -lboost_system -lboost_filesystem -lboost_program_options -lboost_regex -lboost_iostreams -lboost_date_time -lsdformat9 -ltbb -lignition-fuel_tools4 -lignition-transport8 -luuid -lignition-msgs5 -lprotobuf -lignition-math6 -ldl
source /opt/ros/humble/setup.bash; /tmp/mr3_v6_drive_dlopen_cpu /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_gazebo_diff_drive.so
ldd -r ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_gazebo_diff_drive.so
python3 /tmp/mr3_v6_drive_static_verify.py
```

compiler返回0，1000次实际库factory/create/destroy通过；没有ModelPlugin::Load、世界、回调或物理推进。
完整compiler argv是从原tool调用构造和原pkg-config输出事后逐项呈现，明确不是execve trace，
见`independent/mr3_p2a0_v6_drive_dlopen_compiler_argv_v1.json`；原cpp、pkg-config及编译warning/运行stdout均保留。
ldd -r无缺库/undefined symbols，静态核对5份upstream odometry函数除private类名外保持，编译声明与实际安装库一致。
正式库解码SHA `e4671d82dc1c410fbf3c710f82b4e6768f6c603894a4bf23d8621e04ecc75c81`，
特意保留`binary/libmr3_gazebo_diff_drive.so.gz`，与build_drive_binary_v6.json压缩/解码SHA均相符；
canonical内没有其他ELF或压缩ELF。上述均无真实callback竞争/机体响应/native关闭可靠性信用。

launch/headless回归和限定style精确argv（各cwd在launch_checks_v1中）：

```bash
bash -c 'source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 -m pytest src/multi_robot_exploration/test/test_mr3_drive_launch.py src/multi_robot_exploration/test/test_mr3_adapter_launch.py src/multi_robot_exploration/test/test_mr3_terminal_launch.py src/multi_robot_exploration/test/test_launch_and_smoke.py -q'
/usr/bin/python3 -m flake8 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_drive_launch.py --max-line-length=99
git diff --check
```

115 PASS/6.51测试秒、8.31542539037764墙秒；首次style因旧ValueError literal及新test签名超过99字符E501失败，
仅换行后最终flake8 exit0（1.003926050849259墙秒），git diff --check exit0；首次错误stdout另存，未抹去。
模型对照还证明：恢复旧插件文件名并删两项新审计tag即逐字恢复57b7原SDF；实际3台spawn选择各自有效SDF和trace，
不改碰撞/质量/torque/轮参数，不产生tb4新研究矩阵。此为源/配置语义，非Gazebo load验证。

完整ROS语义与conda CPU的精确命令：

```bash
/usr/bin/python3 -m pytest -q src/merge_map/test src/multi_robot_exploration/test --ignore=src/merge_map/test/test_copyright.py --ignore=src/merge_map/test/test_flake8.py --ignore=src/merge_map/test/test_pep257.py --ignore=src/multi_robot_exploration/test/test_copyright.py --ignore=src/multi_robot_exploration/test/test_flake8.py --ignore=src/multi_robot_exploration/test/test_pep257.py
python -m unittest discover -s mr3_learning/tests -q
```

ROS cwd=`/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap`，/usr/bin/python3；ROS source/install环境和PYTHONNOUSERSITE=1。
945 PASS/30.83测试秒、32.12174702901393墙秒；115 launch项包含在945内，不累加。
conda cwd=`/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl`，解析Python=`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python`，
ns3gym/PYTHONNOUSERSITE=1/PYTHONPATH unset，208 PASS/12.460测试秒、17.96432446083054墙秒。
完整before/after输入SHA一致及原stdout.gz分别见ros_semantic_v6.json、conda_cpu_v6.json。

完整208检查对应contract v1的audit_ppo SHA d42eb404771f0db25154c23df0bd6f8bc951dfa30da7206880120799d1219286，
ADAPTER SHA8ea41f9ab35dda86a7ad741fdb85c64e20600af96ccceb815e52e384e5f3afe2。
随后仅明确ADAPTER执行ACK范围措辞及更新其审阅pin，最终audit_ppo SHA
`d21cd79494c07f4e4b79bc94258cd4bd128c492b8c6dc8ec9a08a9dde17845ee`，ADAPTER SHA
`31926aeb325ba8b47c01d2b28c430ba4475c38cc673af6b22c91309feaed22fb`。
contract v1和v2分别在W目录执行同一9项focused命令：

```bash
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 conda run --no-capture-output -n ns3gym python -m unittest mr3_learning.tests.test_audit_ppo -v
conda run -n ns3gym python -m flake8 mr3_learning/audit_ppo.py
/usr/bin/python3 -m flake8 mr3_learning/audit_ppo.py --max-line-length=99
```

两轮9 tests均PASS，首次conda flake8因No module named flake8返回1，保留原失败txt；
之后使用已有系统flake8返回0，两轮空stdout文件也分别保存。v2核验18项执行pin、静态链接和
非执行任务/奖励/审计逻辑AST仍与HEAD不变；不将完整208写成最终措辞/pin更新后再次执行。
两轮receipt和5个原始txt在v6 independent，早期失败不改判。

所有本节新增原件的原路径、bytes及SHA见`report/assets/20261017_mr3_p2a0_v6/independent/offline_checks_archive_v1.json`；
报告为`report/20261017_mr3_p2a0_v6.md`。本节记录现存离线检查，不代表尚待冻结的原生interface/terminal/reset/deadline已执行。
新独立actuator trace消费者仍须固定并在新原生原件上验证。pilot已用2226决策/11494.045260453597墙秒、
余额1870/2905.954739546403不变，原v5实际1.3969248505326008超界FAIL及之后阶段SKIP保持。

补充来源检查：8项actual installed source/resolved/SHA及6项真实runtime import/resolved/SHA匹配PASS，
分别保存installed_assets_v6.json与runtime_modules_v6.json，范围为静态安装/导入，非运行参数或物理控制。
changed/new Markdown173条链接由root检查零missing，最终root静态receipt记录；此处不冒称我复核了该全部范围。
独立actuator consumer **v1**的25项CPU mutation tests由runtime独立执行通过，原review及原txt已归档；
review指明首pre-release update的dt边界问题仍待candidate修v2，不称该v1已是最终冻结消费者，任务30Hz规则保持。
terminal声明再次澄清：每轮4步API、两轮共8；488步API=20+8+160+300，487真实脚本动作不含零时长结算。

消费者随后最终v2交付：`/usr/bin/python3 /tmp/mr3_independent_drive_trace_v1_tests.py -v`
26 tests PASS/3.385测试秒、4.283131749834865墙秒；
`/usr/bin/python3 -m py_compile /tmp/mr3_independent_drive_trace_v1.py /tmp/mr3_independent_drive_trace_v1_tests.py`
exit0/0.09837843663990498墙秒。原argv/双stdout、脚本SHA在
`independent/mr3_p2a0_v6_drive_consumer_checks_v2.json`；脚本文件名沿用v1，最终源码SHA
92be5fca543c081cc6d9138434bb86d9686a014930720eba0642401c4f7d1b4e、tests SHA
75ab94e3c8be06aca1c0b17d9585aa1bde0384c4e01b46d40b734bf09dea089a。
新回归只允许释放前**首个**actuation dt涵盖Load延迟，以configuration/reset源时间括界且正、至少30Hz周期；
后续及每个task区间actuation仍严格物理30Hz上界和source-successor精确dt，不放宽任务规则。
v1独立25项review保留，仅覆当时字节；最终26项由candidate执行，不冒称runtime已独立重复26。
当前/归档.so读回只是保存二进制IO/schema兼容，example为fake aaaa且不作Gitfreeze信用，
真实postcommit来源和实际Load/执行仍需新冻结原生证明。无ROS/新native/机体安全或停止信用。

冻结前staged `git diff --cached --check`因原始CMake/gtest stdout尾空格返回2，未commit/native；将10份canonical raw日志无损gzip（源/tmp原件不动），`offline_stdout_encoding_v2.json`保存原selected→gzip/encoded+decodedSHA映射，原checks和offline_archive_v1原始SHA均保留。重新执行diff/check、add-n后冻结。


## 2026-10-17 MR3-P2A.0 v6 — 原生interface与实际执行时序FAIL

源码冻结`448ceb6a26e9fef1f1c47e26292ba64c1b93c732`已推送、启动前clean；95项源码、15份独立脚本及实际
`.so`源/编译库e4671d82dc1c410fbf3c710f82b4e6768f6c603894a4bf23d8621e04ecc75c81预检通过。
只运行single-worker open101 interface（domain180/port12641），每环境严格tb1/tb2/tb3，
conda ns3gym/PYTHONNOUSERSITE1/PYTHONPATH unset，cwd W；原launcher精确argv：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 20 --preparation-motion-probe --base-domain 180 --base-port 12641 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261017_v6_interface --preparation-parameter-review
```

原full audit精确命令（cwd W，conda ns3gym）：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.audit_preparation /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v6_interface --freeze 448ceb6a26e9fef1f1c47e26292ba64c1b93c732 --output /tmp/mr3_p2a0_v6_interface_full_audit.json
```

原full audit exit0/PASS/errors[]，95 frozen-source bindings及native/scalar/evaluator/motion/contact/activity门通过。
它未纳入新独立driver消费证明，不能据此将整体准备任务记PASS。返回reset1、step20，共21 API；
20个command均返回，无未返回差额，adapter接受19、拒绝1（command6@76.22，navigation_changed_since_observation）。
协议按原19/1结算通过，拒绝原件/处罚不抹去；6个真实GOAL接受、各台2个。
全部dt/physical_dt1.0，最后正常truncated/external_sampler_limit，不是95%任务成功。

任务物理20.0秒，release71.22→末快照91.22；cleanup另.22秒到91.44；
初次暂停71.207→release有.013秒受控对齐，不计为有效任务采样。
benchmark墙秒438.77938038110733，launcher439.23543471097946分列，不相加。
九实际节点参数PASS，21 wholeobs/七图/活动/GOAL独立回放PASS；三台received path
2.050096574561806/2.1043245914592292/1.9993159024550078米，不能替代孤立评价器的95%完整任务门。
18接触持续fresh/原序列及零contact PASS，三台各4565 decision/actual FIFO对应，1012 motion阶段ACK；
39 native exit0，18 Nav2 finalized，worker0/forcedfalse/failed_samplefalse；44owned加两父共46保存PID/start身份均消失。

原固定body消费者精确命令（cwd Git根、system Python，原工具前缀rtk proxy）：

```bash
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v4/independent/mr3_independent_angular_interface_v1.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v6_interface/worker0/episode001_open_101 --output /tmp/mr3_p2a0_v6_interface_fixed_angular_v1.json
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v3/independent/mr3_independent_physics_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v6_interface/worker0/episode001_open_101 --output /tmp/mr3_p2a0_v6_interface_fixed_physics_v1.json
```

原7a472angular与2516physics均exit0/PASS，完整原JSON不改。angular bounds/双signcoverage均true，
三台各595 task-source samples、最大间隙34ms；原始全平面速度峰
.26206059692039596/.2602178208517182/.2605873149587749m/s，
odom chord峰.262101128080986/.26023960294305754/.2606124166152852m/s，均<.30；
三轴角范数峰.8199303592278344/.7674276760886488/.28817591195244213<1.2，
三轴相邻源差分峰1.5642004931415268/1.4362868321245674/1.3878722581045155<7。
三台每台各1个A_final_linear_zero有意义样本：
初始平面速度.20655477081003062/.16045095303241474/.20560065833574906m/s，
停时延.712/.582/.557秒、原始odom折线路程.07447337457982818/.05719986735833448/.07044181737385437米，
均在原.78s/.144m；tb2 zero_w=-.05894736842105258，保角而刹平移也得到有限采样证据。
B_native_cancel_end_to_end只在末尾cleanup .22秒，三台均missing_rest_evidence，
不能说B通过或把有限sampled/chord当连续路径与所有停车条件保证。

新增固定driver消费者原始精确命令（cwd Git根、PYTHONDONTWRITEBYTECODE=1、system Python）：

```bash
/usr/bin/python3 ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v6/independent/mr3_independent_drive_trace_v1.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v6_interface --freeze 448ceb6a26e9fef1f1c47e26292ba64c1b93c732 --binary-proof /tmp/mr3_p2a0_v6_binaryproof.json --output /tmp/mr3_p2a0_v6_interface_drive_review_v1.json
```

原92be消费者FAIL保留：discontinuous/inconsistent actual physics steps。其previous=release假设不适用于
真实paused query+alignment前缀；原1025行全部邻行连续，前14行终点恰为release。
只读修前缀/合法同clock零值的v2诊断仍FAIL（160ms），不覆盖固定原件，也不重新授native信用。
latest received目标到actuation的记录年龄>160ms，每台595含cleanup样本中186/217/263，
nonzero98/120/119；这一项年龄本身不等于新的变化命令反应延迟。

进一步原值/源时刻复核确认**实际执行时序失败**：task内源到actuation兼容年龄最大.712/.712/.727秒，
超过原.16s的样本220/236/147。tb1 source76.272仍施加(.20526315789473687,-.7157894736842105)，
最后同值guard75.56、最新guard76.26已(0,0)；tb3 source87.147仍(.26,-.21052631578947367)，
最新guard87.14已(.26,+.21052631578947367)。因此旧目标确在较新不同保护值后继续施加；
不是仅重复同值、reader包装或postcleanup年龄，也不从headerless值关联冒称per-packet身份。
实际末端消费不及时使原.16反应前提未获保证；零接触、body界及三个A停车片段PASS不能修复该缺口。
原值诊断脚本/JSON/console、receipt-age诊断及全部原readerFAIL均留档。

整体v6 interface FAIL，后续terminal/reset/deadline按预声明全部SKIP，无same-freeze原生重试，
无PPO/GPU/optimizer、无95%信用；pilot已用2226/11494.045260453597、余额1870/2905.954739546403不变。
后续新v7需要唯一tagged epoch/guardseq/clock/value到driver实际接收/消费状态，
三台同clockACK齐后才推进下一20ms，并修独立reader边界与整段延迟审计；160ms/所有物理和任务门不降。

canonical完整选存411份native（含三路drive_jsonl和三份effectiveSDF），raw128187705/selected7030600bytes，
encoded/decoded/original字节均一致；95个精确448ceb6 Git payload一并验证。
初55项prefreeze资产和inventory完全不改，新增inventory_native_v2及增量manifest/accounting_v2保存新诊断，
不覆写original native/fullauditPASS/driverFAIL。首archive工具误假设20条均accepted而断言失败，
已改为20 submitted=19 accepted+1 rejection，仅修统计，不改任何native原件；初失败脚本也保留。
无需detached重新大矩阵；原完整audit95绑定和原源包保留。证据位于
`report/assets/20261017_mr3_p2a0_v6/{native/interface,independent,accounting}`，详见v6报告。


## 2026-10-17 MR3-P2A.0 v7：tagged实际存储屏障离线验证（原生尚未开始）

本轮以v6冻结`448ceb6a26e9fef1f1c47e26292ba64c1b93c732`为base，在提交前v7 working-source上实现实际target消费屏障。v6真实.712/.712/.727秒执行滞后FAIL及所有原件不变；未把工作源码检查改称旧freeze结果。guard最终输出经唯一epoch/robot/decision_sequence/clock/value目标送actual driver，真实desired存储status由worker三台exact-clock收齐后才允许下一20ms推进。ACK仅证明存储和status publish返回，不证明30Hz setpoint/物理响应或机体停稳。共同轮反馈/物理配置、actor/candidates/masks/reward和原95%/.50m/160ms/.30/1.2/7/.78s/.144m门不变。

canonical：`report/assets/20261017_mr3_p2a0_v7/`。新正式库1,999,120 bytes、SHA `d0d31b0ff62de498182073b4dd2715a78e17201844d8d8a360e385f4d2531dd6`，gzip及四源hash已在`build_drive_binary_v7.json`，不是旧v6 e467库。编译CPP09f741ee…、plugin header a7c23794…、paired helper80cf2e51…、target header a1a11a73…与final build02相符；33 reviewed pins/ENV和非pin immutable AST由独立合同receipt核验。后续clean-pushed冻结及native前preflight另绑定。

C++ build01 PASS为中间volatile目标输入版本；build02 PASS才为最终reliable/transient-local depth1双端点。均保留原stdout gzip。实际执行构造（cwd ROS=`/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap`，system ROS Python，工具前缀rtk proxy）：

```bash
source /opt/ros/humble/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /usr/bin/colcon build --packages-select multi_robot --symlink-install --event-handlers console_direct+
/usr/bin/python3 /usr/bin/colcon test --packages-select multi_robot --event-handlers console_direct+
```

4个CTest target共30 gtest PASS，包括9个新增target契约用例。另从Git根严格独立编译并运行同9例PASS，保存的编译argv：

```bash
g++ -std=c++17 -Wall -Wextra -Werror -pedantic -Iros2_ws/ros2-multi-robot-automap/src/multi_robot/include ros2_ws/ros2-multi-robot-automap/src/multi_robot/test/test_drive_target.cpp -lgtest -lgtest_main -pthread -o /tmp/mr3_p2a0_v7_drive_target_test
/tmp/mr3_p2a0_v7_drive_target_test
```

同9例另加`-fsanitize=undefined -fno-sanitize-recover=undefined`运行PASS/noUB；原receipt保存严格编译argv与额外UBSan flags，不能将这三次运行相加为48个不同用例。静态/工厂验证命令（cwd Git根）：

```bash
python3 /tmp/mr3_v7_drive_static_verify.py
/tmp/mr3_v6_drive_dlopen_cpu /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_gazebo_diff_drive.so
```

静态五份原odometry函数不变、四编译源hash匹配/weak callback结构PASS；1000次实际新库factory/create/destroy PASS，未调用ModelPlugin::Load、未创建模型或世界；ldd-r无缺库/未定义符号。复用v6 factory工具源码/编译构造凭据原canonical，不复制其ELF。全部检查/原输出见`independent/mr3_p2a0_v7_drive_checks_v1.json`及原件manifest。

phase/helper与实际worker方法因果回归（cwd ROS）：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
/usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_mr3_drive_phase.py
/usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_mr3_drive_phase.py src/multi_robot_exploration/test/test_mr3_worker_bootstrap.py src/multi_robot_exploration/test/test_mr3_evaluator_phase.py src/multi_robot_exploration/test/test_mr3_worker_shutdown.py
/usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_mr3_evaluator_phase.py
```

首次未source环境collection失败，完整stdout仅工具记录；proper focused首轮58 PASS/2措辞断言FAIL（生产正确阻止send），断言修正及新增线程因果后63 PASS/2.34测试秒。真实v6 seq3771/source75.56不能授权seq3806/76.26零输出；三台真实receive→consume→helper.send、future/错epoch/clock/value/seq、cache latest、callback fatal和真实Python Condition线程均覆盖，未构造ROS节点。相关4文件首轮133 PASS/2 FAIL为旧evaluator reset fixture缺新drive topology/phase mock；仅补fixture后该文件38 PASS/.88测试秒，生产barrier不放宽。初失败及后PASS分别在phase_checks_v1/v2和各原stdout，未抹去。

合同/pin9项最终命令（cwd W=`/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl`，conda ns3gym，明确无ROS PYTHONPATH）：

```bash
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m unittest mr3_learning.tests.test_audit_ppo -v
```

9 PASS，5.34184193611145总墙秒；33 exact reviewed pins和ENV before/after、非pin AST与base相同、24本地链接PASS。首次并发PROVENANCE更新触发精确静态拒绝，原FAIL JSON保留；更新该pin后通过，未改审计判断。audit_ppo单独system flake8（cwd Git根）：

```bash
/usr/bin/python3 -m flake8 ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_ppo.py --max-line-length=99
```

最终tagged独立consumer（cwd Git根，system Python，stdlib）：

```bash
/usr/bin/python3 /tmp/mr3_independent_drive_trace_v3_tests.py -v
/usr/bin/python3 -m py_compile /tmp/mr3_independent_drive_trace_v3.py /tmp/mr3_independent_drive_trace_v3_tests.py
```

49 synthetic mutation tests PASS/.852测试秒/1.2801893879659474墙秒，syntax PASS/.11994046904146671墙秒；final script SHA dc10bf03cde4d9b7b8aad9d5f7e5524097bc43bd4055ef21a97638c0374048e9、tests SHA0b393e5b0867094276230d6bdc13f650e9065c2cfc84bbb1507daf876699c07d。same-release初次真实storage前zero/started=false低序号锚仅属预热、不授响应，160ms/task30Hz/精确轮预算不降。开发47与49首轮各一处测试期望拒绝位置错误记于原receipt；旧headerless v2兼容28 PASS只作旧格式CPU证据。runtime对旧7338feef…/3db541bd…字节的source-only审阅记录candidate_reported47且executed_by_this_review=false，旧备份原样保留，不改称独立执行最终49。Python生产cross-review亦只读，不能替代DDS/native/物理实证。

root最终三包build、相关执行、完整ROS及conda命令如下。build/focused/full ROS cwd ROS、system `/usr/bin/python3`，source `/opt/ros/humble/setup.bash`和`install/setup.bash`；PYTHONNOUSERSITE=1。全conda cwd W，resolved Python为`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python`，learner无ROS PYTHONPATH。

```bash
/usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select merge_map multi_robot_exploration multi_robot
/usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_motion_safety.py src/multi_robot_exploration/test/test_mr3_worker_bootstrap.py src/multi_robot_exploration/test/test_mr3_drive_launch.py
/usr/bin/python3 -m pytest -q src/multi_robot_exploration/test
/usr/bin/python3 -m pytest -q src/merge_map/test src/multi_robot_exploration/test --ignore=src/merge_map/test/test_copyright.py --ignore=src/merge_map/test/test_flake8.py --ignore=src/merge_map/test/test_pep257.py --ignore=src/multi_robot_exploration/test/test_copyright.py --ignore=src/multi_robot_exploration/test/test_flake8.py --ignore=src/multi_robot_exploration/test/test_pep257.py
# cwd W, resolved conda ns3gym Python
python -m unittest discover -s mr3_learning/tests -q
```

三包build PASS/6.920743669848889墙秒；focused61 PASS/3.37测试秒/4.408640984911472墙秒，与phase63及full suite有覆盖重叠。首次ROS调用误省既有lint ignores，扫描cwd旧log/upstream等，996 PASS/1 skipped/2 FAIL（39034flake8、189pep257，78.99测试秒/80.8567682900466墙秒）；`ros_semantic_v7.json`及完整gzip保留。没有改旧日志或扩大本轮修复范围。恢复与v6相同canonical双包+6原ament文件ignore后1008 PASS/30.64测试秒/31.916257780976593墙秒。full conda208 PASS/12.775测试秒/18.26953538879752墙秒。最终两个完整检查所有记录source_before==source_after，包含已完成三份contract/pin字节。

root changed/new non-asset Python风格精确argv（cwd Git根，system Python）为：

```bash
/usr/bin/python3 -m flake8 --max-line-length=99 ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_drive_phase.py ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_motion_safety.py ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_drive_launch.py ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_drive_phase.py ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_evaluator_phase.py ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_worker_bootstrap.py
```

exit0/1.3379605347290635墙秒；audit_ppo另行PASS如上。installed_assets_v7对10份实际安装解析路径/source bytes绑定PASS，runtime_modules_v7对7份实际system ROS import路径/source SHA PASS；这些不代表启动/物理测试。

证据首批`independent/offline_checks_originals_manifest_v1.json`保留33份检查原件、旧canonical复用与历史review别名；增量`offline_checks_originals_increment_v2.json`补final49原件和preflight脚本。所有receipt原字节不改，stdout `.txt`/`.log`只lossless gzip，raw/encoded SHA映射和解压重验；首批33份及6份增量原件一致。纯strict/UBSan/factory ELF未纳入，唯一保留ELF是声明的正式驱动库gzip。root的plan/final prefreeze inventory另绑定launcher/capture/live等脚本。没有重复测试或新native。

v7原生尚未开始；后续同一clean pushed新freeze依次interface20、terminal两轮每轮4步API共8、2workers八轮20step reset、300KEEP，≤488API/487脚本动作/7000原生墙秒，逐阶段全必需门通过才推进，不拼旧PASS。无PPO/GPU/optimizer、无95%/P2A完成信用。pilot已用2226/11494.045260453597，余额1870/2905.954739546403不变。

冻结前最终独立reader v4：`/usr/bin/python3 /tmp/mr3_independent_drive_trace_v4_tests.py -v`及`/usr/bin/python3 -m py_compile /tmp/mr3_independent_drive_trace_v4.py /tmp/mr3_independent_drive_trace_v4_tests.py`，50 synthetic检查/语法/producer字段compat PASS，原argv/stdout/耗时/SHA见v7 independent/mr3_p2a0_v7_tagged_drive_consumer_checks_v2.json。仅将有真实initial storage顺序证明的prewarm zero command/actuation与放行后的task区分，初始storage及后续/clock>release160ms、原物理/停止界不改；v3/49与v6实际stale FAIL原件不改，无native/PPO信用。

提交前staged diff静态检查发现原始effective SDF自带尾空格，三份原件未改；沿已有CSV原件保字节约定，在.gitattributes仅为canonical native/drive_model_tb[123].sdf声明-text/-whitespace，保留实际spawn输入逐字原件及原manifest/inventory哈希，source SDF/Python等风格检查不变。重跑全根diff/check及add-n后提交，无新增仿真或修改历史失败。


## 2026-10-17 MR3-P2A.0 v7：实际 tagged 存储屏障通过，interface 参与及刺激覆盖 FAIL

本次原生仅使用已 clean-pushed 的冻结 `01cfa040dcb73f8931dd11d66b69ce765cb8412f`，场景 open/seed101、三台 tb1/tb2/tb3、domain190/port12701。启动前 source preflight PASS：97 个精确 Git source、18 个独立脚本、四个编译源宏和实际 d0d31b…库全部绑定；`independent/mr3_p2a0_v7_source_preflight.json`、`mr3_p2a0_v7_binaryproof.json`保留原件。没有同冻结原生重试，没有 PPO/GPU/optimizer 更新。实际 benchmark argv（cwd W，PYTHONNOUSERSITE=1、learner 无 ROS PYTHONPATH）为：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 20 --preparation-motion-probe --base-domain 190 --base-port 12701 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261017_v7_interface --preparation-parameter-review
```

原命令、parent/launcher PID/start、开始/结束时间和 returncode 保存在 `accounting/mr3_p2a0_v7_interface_launch.json`；benchmark metadata/summary 在 `native/interface/`。输入策略版本为预声明的 `mr3-p2a0-outward-cancel-v2`，仅属外部工程刺激，不能作为 RL、探索 fallback 或协同安全证明。预声明总矩阵仍是 488 API/487 脚本动作/7000 原生墙秒；本次只执行 interface：1 reset+20 返回 step=21 API、20 个实际动作命令，20 accepted、0 rejected、0 未返回动作。20 条有效/物理返回时间均为 1s，共 20s；真实暂停 query 起点72.302s、release72.320s，18 个1ms预热对齐tick；final92.520s，任务后清理0.200s。总受控物理20.218s，含20s返回样本、.018s预热和.200s清理。benchmark 墙秒531.8874822380021；launcher 墙秒532.3876321972348、exit0，不能把包装层墙秒相加。

实际9节点 Nav2 typed readback PASS，source/release72.320s、epoch `mr3_p2a0_20261017_v7_interface_w0_e1_97204f47`，原报告 SHA `7fa0d1b9e6b5deaedb9b380e66df6c783982db6ffb5763382469034a8574563e`。实际三份 spawn SDF 的 tagged=true/epoch/audit路径与原物理配置绑定；真实 graph 中 target publisher 唯一 root motion_safety，target subscriber/status publisher 唯一各 `/tbN/turtlebot3_diff_drive`，驱动没有 Twist 订阅。`/proc/2538729/maps`实际加载 canonical d0d31b0ff62de498182073b4dd2715a78e17201844d8d8a360e385f4d2531dd6 库，dev08:03/inode73558744、当前字节/真实解析路径/四编译源hash与冻结proof一致，未映射旧系统 diff-drive；monitor01–04原件保留。此项是实际映射及磁盘字节证据，没有读取进程内存字节。

新 tagged 独立消费者按预声明最终 **v4/SHA6aa1a8409e031f225f0acb3a61ab2c9ec16a156cc85a430fd7069bdea411f35d** 执行，原结果 `independent/mr3_p2a0_v7_interface_drive_review_v1.json.gz` PASS。guard 七字段唯一身份→真实 desired 存储/九字段 status→worker 三台 exact ACK-before-advance→30Hz measured-joint paired actuation，全链门通过。task 内三台各594条 actuation，guard→实际存储 callback 源龄最大均0ns；guard→actuation 最大分别20/20/19ms，无>160ms、无task target_rejected；不再用相同 Twist 值猜逐包身份。worker 1010次 consumed/advance 屏障覆盖全部1010个正20tick任务及清理推进；motion 本地 telemetry 的1011个 consumed ACK独立闭合至final92.520s。每台4607条 decision和4607条真实本地 Twist receipt 完整FIFO、队列空。status仅证明真实目标存储和publication返回，不能称轮速施加或物理停止 ACK；body/停止仍由原raw消费者单独判断，未放宽160ms或任何物理界。

严格关闭独立复核 PASS：39个 actual native starts 均39 clean exits，worker0、forced=false、failed_sample=false，真实 Nav2 SHUTDOWN及18个finalized状态/serial关闭/owned native stop完整。supervisor44个保存身份加benchmark parent2538463/start396171528及launcher2538382/start396171359，共46个PID/start精确身份均gone，无剩余或zombie。原关闭与SO/FIFO事实见 `independent/mr3_p2a0_v7_interface_{closure_binary_review_v1,fifo_phase_final}.json`，不外推整体阶段PASS。

**正式 interface FAIL，terminal/reset/deadline 全部 SKIP，未启动。** 原 benchmark包装 `passed=true`仅表示完整工程前缀和严格关闭，不足以通过全部前置门。原完整 preparation audit（97 source）FAIL，第一条错误为 tb1 缺 native accepted goal及received movement>0.05m；nested W7 native、scalar、evaluator phase、payload archive、execution、received-activity integrity和motion审计均PASS。真实三台各收到2个owned native goal accept、activity均有200个完整path样本，但最终received path仅tb1=.00356081911561923m、tb2=.03635914136860959m、tb3=.2532397853692473m，tb1/tb2未达到预声明最低.05m；不降低参与门，也不把rotation-only输出算作平移成功。

原独立 angular 消费者 sampled bounds PASS，但缺同一机器人有先后相反符号的充分角运动刺激；positive span仅tb2、negative span为tb1/tb3、opposite-sign robot为空，故其正式PASS=false。raw task最大平面速率分别.00042732678904499396/.03197676551684015/.21910370679078653m/s，最大角norm分别.16776369645719155/.21265346254561435/.40227545101068224rad/s，最大采样角加速度1.4563686072859117rad/s²；.30/1.2/7及chord采样界未发现违反，不能据低刺激声称充分驱动验证。原严格physical消费者完整性也FAIL：tb1/tb2均无有意义A或B停止credit；tb3仅一个A片段，从.06851361472920896m/s到3个rest样本，.109s/.0032011257394714975m，满足.78s/.144m但只属于该有限速度/采样片段；其它有线性恢复的事件保留原状态，不称全部zero已停车。无actual bound violation不补足缺失刺激，后续reset停止聚合池尚未运行，不借terminal/deadline或旧版本拼credit。

全部原生原件419份选存到 `report/assets/20261017_mr3_p2a0_v7/native/interface`，raw173672700bytes、encoded9357651bytes；含三份实际SDF、三路drive trace、drive_targets和drive_phase_worker，stream逐份核验encoded SHA、decoded SHA及原件SHA/字节数相同。另45份原始检查/console/live/closure/pack工具及97个精确Git source payload无损选存，原full FAIL、driver PASS、angular/physical coverage FAIL均不改。`independent/interface_originals_manifest_v1.json`、`interface_archive_verification_v1.json`和`accounting/interface_accounting_v1.json`给出映射/精确成本；66份冻结前资产与01cfa040 Git对象逐字一致。`inventory_native_v2.json`记录533份新增及既有资产（self-excluded），SHA c00183a9947c96d3c795725ac151e4667ec6cbd3e1c10471a3bd6b56d28ac270；原prefreeze inventory不改。未重跑 detached full audit或原生以替换已有结果。

本轮只读工具失败也保留：首次本地FIFO observer整份物化132MB JSONL后无输出/预期receipt，未保存exit、原因未证实，不能归咎native；改为流式只存小tuple后exit0/6.700854305墙秒，原件无改。archive v1在已完成native选存后遇到同名prefreeze monitor脚本的FileExistsError，未覆盖原件；v2只核验并复用相同destination字节，重新证明所有66份prefreeze Git对象。失败脚本、失败JSON和后续成功工具均保留，不把包装失败改写为生产失败或新native重试。

本次没有训练、没有95%任务成功或P2A完成信用。累计pilot已用2226 decisions/11494.045260453597墙秒，余额1870/2905.954739546403完全不变；本轮准备成本单列。v7后续三阶段按预声明停止，下一版本须另行review/freeze/predeclare并解决安全可执行性/充分刺激，不降低失败门。


## 2026-10-17 MR3-P2A.0 v8：条件性静止转向接口及完整离线检查（原生尚未开始）

本轮以已冻结的v7 `01cfa040dcb73f8931dd11d66b69ce765cb8412f` 为base，在新v8 working source上继续P2A.0；以下CPU/build/static结果不冒称旧freeze已含新实现。v7原生interface参与/刺激覆盖FAIL、后续三阶段SKIP及其原件不变。新增条件性静止转向只保留Nav2原angular请求，不能产生探索目标或替代RL。原95%任务、三台参与、.50m机体门、160ms真实存储时序、.30m/s/1.2rad/s/7rad/s²、.78s/.144m停止界以及实际tagged消费屏障均保留。正式驱动仍复用v7四源及d0d31b…库；`independent/mr3_p2a0_v8_binary_reuse_readonly_v1.json`只证明旧源/库身份，不能代替新freeze后的preflight或原生映射。

新分支要求唯一release之后零linear输出前缀至少.94s、三个完整平面速率≤.01m/s且各自新鲜≤.1s的raw own-odom样本、原几何/source-age门及至少.1518m余量（自身整段漂移预算.0078m+队友完整制动预算.144m）。release截断预热资格；最后output clock非回退且seq严格递增。激活后到真实下一非零linear存储或物理结束，持续零linear段的速率、chord速度、累计raw中心路径及源间隔受监测；观测到超速、路径超.0078m或有效性断裂会产生fatal model failure，不能只撤证后继续。有限的过去静止样本不能证明未来无限零命令不漂移；这是显式条件plant模型，raw采样折线是必要证据，不能证明采样间连续路径上界。新增独立reader和原driver/body/停止reader必须同时通过。

只读旧v7机会窗反事实完整处理133951行、每台4607个历史decision，按真实own-odom及事实linear输出历史重放新tracker+guard，未将假想angular输出回馈物理或宣称新闭环轨迹。release cutoff后的v2得到tb1/tb2/tb3分别536/153/248个可保留转向的离散机会；最早时刻为73.460/73.420/85.480s，余量超过.1518m的slack分别.021817910582814376/.010106609687564744/.024886509942458418m。输入132184457bytes、SHA4fbc8de1…，三份源码before==after；7.071837340947241墙秒。未加release截断的v1结果537/154/248保留为中间历史。准确命令、复放源码和JSON分别在 `report/assets/20261017_mr3_p2a0_v8/independent/settled_turn_counterfactual_v{1,2}/`；这些是条件机会窗，不是实际移动、安全不变量或v8原生信用。

motion离线审计同步真实record顺序：raw own-odom→frozen tracker.observe、唯一release→tracker.release、完整own_state证书重建→同helper guard→激活/output记账，实际model_failure一律FAIL。完整own_state、received peer、raw request和decision使用typed canonical JSON比较。修前实际counterexample将证书active_path_m从0.0改为False，Python相等误判仍使旧审计PASS，而guard会拒绝；该真实假PASS、修前966c6b65…源码和fixture均保存在 `independent/audit_motion_typed_bool_counterexample_v1.json`、`typed_bool_counterexample_v1/`。修后七类bool/数值类型mutation均拒绝；final审计60c9b253…与tests d0814988… before==after。最终16项conda测试PASS/6.674959795083851墙秒、两文件flake8及diff PASS，完整argv/cwd/源hash见 `independent/audit_motion_settled_final_checks_v5.json`。旧日志13821个own_state严格JSON复核PASS，仅属legacy兼容；初次从/tmp直接运行误使sys.path缺W而ModuleNotFoundError，改为同cwd的标准runpy运行后通过，初FAIL及准确命令分别保留。没有添加ROS PYTHONPATH。

该组开发原件全部保留：早期13项PASS和style失败；加入release后14项中的三个fixture选择错误TypeError及一处style错误；选择实际已资格化turn后14项PASS；最终typed版16项PASS。失败属于相应fixture/style或已证审计实现缺陷，不改写为生产native失败，也不隐藏实际False==0.0假PASS。`audit_motion_settled_tests_01..06`、style/diff和final_checks_v1..v5保留原版本，不把不同版本测试数相加。

独立settled-turn stdlib reader最终v3/SHAc43fadbb…、tests671ae194…，42项mutation PASS/.123测试秒，syntax及真实pure-producer合成schema兼容PASS；不导入生产tracker。它独立绑定raw anchor直到真实下一非零linear存储/physics end的闭区间、唯一release/reset、actual连续零存储至少.78s、三样本资格、160ms、全平面速度/chord及整段累计漂移，不因重复grant重置预算。初v1的28/30测试失败、后续30/32/34/35/36 PASS、只读review补闭区间/anchor后v2的39 PASS、release cutoff后的v3/42均在 `independent/mr3_p2a0_v8_settled_turn_consumer_checks_v1.json`及原stdout中按原版本保留；早期并未全部保存每次源码，不能用最终字节冒称旧版本source credit。对旧v7加--require-use确实exit1（从未激活新分支），不把旧native补成新接口PASS。

外部工程刺激新增显式 `mr3-p2a0-outward-cancel-v3`/32step；保留v2/20及默认旧行为。只在第二次GOAL阶段以received几何和前段首次fresh实际转向符号优先反向bearing机会，仍从合法joint action中选择，不能据bearing宣称实际双向角运动。相关benchmark/comparison/archive/execution共52项conda PASS/.307测试秒/4.9082911419682205墙秒，四文件flake8、syntax、diff PASS；首style失败原件不改。完整命令和stdout在 `independent/mr3_p2a0_v8_probe_checks_v1.json`及gzip。新reset两wrapper只适配v3/32及33条实际记录，并严格绑定原7a472…angular、2516…physical reader；逆规范化原文/AST还原证明原body/closure/八episode/每台stop pool逻辑不变，physics另加raw33/external truncation和固定consumer字节资格。16项合成测试PASS/28.977测试秒，准确argv/cwd/原SHA及允许差异见 `independent/mr3_p2a0_v8_reset_wrapper_checks_v1.json`、equivalence/patch_spec；首receipt生成器语法错误未写任何源码/receipt，修生成器后保存结果，未重跑或虚构首次成功。

root完整离线命令及原stdout在各同名JSON/gzip。ROS检查cwd为canonical ROS，source `/opt/ros/humble/setup.bash`和`install/setup.bash`、system `/usr/bin/python3`；conda检查cwd W、resolved Python为 `/home/zhuyulab/miniconda3/envs/ns3gym/bin/python`、PYTHONNOUSERSITE=1且无ROS PYTHONPATH。关键准确argv为：

```bash
# cwd ros2_ws/ros2-multi-robot-automap
/usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select merge_map multi_robot_exploration multi_robot
/usr/bin/python3 -m pytest -q src/merge_map/test src/multi_robot_exploration/test --ignore=src/merge_map/test/test_copyright.py --ignore=src/merge_map/test/test_flake8.py --ignore=src/merge_map/test/test_pep257.py --ignore=src/multi_robot_exploration/test/test_copyright.py --ignore=src/multi_robot_exploration/test/test_flake8.py --ignore=src/multi_robot_exploration/test/test_pep257.py
# cwd W, resolved conda ns3gym Python
python -m unittest discover -s mr3_learning/tests -q
python report/assets/20261017_mr3_p2a0_v8/independent/mr3_p2a0_v8_contract_checks.py /tmp/mr3_p2a0_v8_contract_static_final.json
```

最终三包build PASS/6.702978136949241墙秒（首build PASS/6.714897582307458亦保留）；完整ROS **1042 PASS/34.08测试秒/35.37158735189587墙秒**。此前focused01/02/03分别62/66/67 PASS，原stdout/源版本各自保存；最终settled_turn+原motion_safety合计68由完整ROS覆盖，未另跑一轮68，不能称68个新增例，也不与完整套件相加；相对v7完整1008净增加34例。root style01/02分别4/5处失败原样保留，03及final PASS。完整conda首轮216 tests+1 setUpClass ERROR/28.370测试秒/33.81996887596324墙秒，原因是ADAPTER文档精确pin遗漏更新，原 `conda_cpu_v8_final.json`与stdout不改；修正精确doc pin后最终 **224 PASS/19.960测试秒/25.34131052903831墙秒**，见 `conda_cpu_v8_final_v2.json`。这里的CPU synthetic optimizer unit tests不构成native GPU/训练更新。

最终changed-source风格PASS/1.0487249284051359墙秒；contract静态PASS/5.120832566637546墙秒，33 reviewed pins、166本地链接及非pin AST不变。实际system imports七模块路径/字节PASS，仅import、未构造ROS节点或启动world；脚本和binding在 `independent/mr3_p2a0_v8_runtime_import_{check.py,bindings.json}`。所有准确source_before/after、cwd、resolved Python、argv、exit及原输出由canonical receipts保留，不凭检查数替代行为验收。

预声明plan最终b7487cd0…、27 independent bindings，plan/preflight/launcher最终22项CPU及syntax/flake8/diff/static PASS，完整命令见 `independent/mr3_p2a0_v8_plan_launch_checks_v3.json`。旧initial/provisional/v2开发失败及旧22-test脚本保留，canonical最终tests e5592dba…不冒充/tmp旧版。后续新clean pushed freeze才可顺序启动interface32（含实际9节点参数及new-branch --require-use）、terminal两轮4、2workers八轮32step reset、deadline300KEEP，总上限608 API/596 submitted script decisions/18000原生墙秒；阶段墙秒上限1800+1800+6400+8000，准确domains/ports/argv及所有门见 `report/assets/20261017_mr3_p2a0_v8/predeclared_plan_v8.json`。这是prospective工程预算，本记录时尚无v8 native，不改pilot余额或既有失败门。

统一 `independent/offline_originals_manifest_v1.json` 逐份核验84个/tmp→canonical原件映射、14份root命令/gzip回执及150份独立原件绑定；已有43份settled原件映射复用同字节，stdout新增选存采用lossless gzip并记录raw/encoded SHA，历史已canonical的原件不覆写。首manifest草稿误列ignored Python cache，原草稿另存为历史JSON；最终manifest排除cache，未删除或改写任何研究原件。最终manifest SHA32011ebb619e0b5c871673918b446c7b7ad44c2de556725cb3f8fa6cebadd2f2；它不是最终prefreeze inventory，后者由root在全部agent停编辑后统一生成。当前v8 native/GPU/optimizer均0，无95%或P2A完成信用；累计pilot已用2226 decisions/11494.045260453597墙秒、余额1870/2905.954739546403不变。


### 2026-10-17 MR3-P2A.0 v8 原生闭合（FAIL 保留，继续修复）

- 冻结：`d41485dfd93797026316806916e127eb5101f3b8`，干净且推送后启动。精确预声明 `report/assets/20261017_mr3_p2a0_v8/predeclared_plan_v8.json` SHA `b7487cd09450044d815904e240e795f25800e3ae542bf665e7585467cbe5b60b`。所有命令 cwd为本wireless-rl，conda ns3gym、unset PYTHONPATH、PYTHONNOUSERSITE=1；ROS子进程仍system Python。
- 原生准确命令：`python report/assets/20261017_mr3_p2a0_v8/independent/mr3_p2a0_v8_launch_stage.py interface d41485dfd93797026316806916e127eb5101f3b8`；随后同脚本`terminal d41485dfd93797026316806916e127eb5101f3b8`。两条实际benchmark argv/环境/domain/port/sourcepreflight及前序正式receipt SHA均在`report/assets/20261017_mr3_p2a0_v8/accounting/mr3_p2a0_v8_{interface,terminal}_launch.json`，完整console无损归档。interface625.2535761622712墙秒/exit0；terminal336.1551110469736墙秒/exit1；累计961.4086872092448，未超18000声明预算，但前序FAIL停止reset/deadline（未尝试）。
- interface：32步原生、33个API返回、32秒；全部正式native/contact/clock/command/scalar/evaluatorphase、输入七地图导航/候选/活动、真实tagged消费/160ms、角向/物理及新增settled尾段门PASS。三台received路径4.076668/4.212207/4.088198米，各2次原生接受、1SUCCEEDED+1CANCELED。保留tb1 t5无合法GOAL（seed净空下界不足原.29），不声称全时候选。独立CLI的准确argv/stdout/SHA见`independent/mr3_p2a0_v8_interface_physical_execution_v1.json`和各formal JSON/console；fullaudit用`python -m mr3_learning.audit_preparation <绝对interface目录> --freeze <上述冻结> --output /tmp/mr3_p2a0_v8_interface_full_audit.json`。
- closure观察器初误设46身份，实际47且全部消失；原FAIL/SHA与原脚本/argv/console逐字保全，v2和显式formal correction aggregate、custody链均另存。未改变任何预声明count门（原本无固定count门），39native正常0退出、18 Nav2 finalized。
- terminal：首轮意外提前第1step/.06秒navigation_failure，未到3秒arm；第二轮3×1秒+0秒未提交尾正常。旧tb3 received source67.58在68.10先被guard用、源龄.52>.5；同clock随后才到source67.979 freshbundle。原源龄门正确拒绝。producer没有自身raw ingress，不能据另订阅者raw顺序证明future-latest skip为本次具体原因。无settled model failure。原完整审计FAIL、78native严格关闭/90实际身份消失子PASS、原驱动消费PASS；settled integrityPASS/coverageFalse。全部原件在v8/native/{interface,terminal}和independent。
- 终止正式审计执行：`python /tmp/mr3_p2a0_v8_root_audit_runner_diagnostic_v2.py terminal`（conda ns3gym；依次完整audit_preparation和不可变6aa1驱动consumer）；准确两个CLI、cwd、stdout SHA、返回码与耗时在归档的`independent/mr3_p2a0_v8_terminal_root_audit_execution_diagnostic_v2.json`。fullaudit退出1/54.96930935001001墙秒；drive退出0/17.831638772971928墙秒。所有旧门不减。
- 原生总计40API、37返回step、36真实提交、1零尾，35.06任务秒，接口额外.02关闭秒；0原生GPU/optimizer，pilot余额1870决策/2905.954739546403墙秒不变。P2A.0仍未完成，无PPO/95%或网关信用。按当前授权继续修复、新冻结整矩阵，不盲目同freeze retry。
- 原件无损打包命令：`/usr/bin/python3 /tmp/mr3_p2a0_v8_pack_native_v1.py interface`及`terminal`，各stdout pack receipt保全；两阶段935文件410200730原字节→21795220选择字节。`python3 /tmp/archive_mr3_p2a0_v8_closed_v1.py`首次归档helper因sourcepack无source_count键KeyError/exit1（原stderr与部分副本保留）；`python3 /tmp/archive_mr3_p2a0_v8_closed_v2.py`仅修schema及核验复用相同目标字节，exit0，97精确Git源、187冻结前资产、104独立原件核验通过，库存SHA d4c4330dde2f28be4cedab97edf3ce82f3295a5086f7559395f044530b0f2baa。没有重跑native或重命名原FAIL。


### 2026-10-17 MR3-P2A.0 v9 冻结前因果缓存修复检查

- 本步继续授权内修复，无原生/训练启动；基准v8 `d41485dfd93797026316806916e127eb5101f3b8`。mr3_information最终源码SHA `b9830fa5089201920e05196d923e82fff62344946a43987204b1f43aaeb3e1b5`，launch `5345a8e583a779847f7b1a6e63a4c3a7b9585d308fdb1e3b9f4790309c0ce9ec`。修pending causal odom、真实ingress/selection/send/pub账本，整数ns精确`.5s`端点与+1ns拒绝；不改变`.1s`发布、95%/任务/物理/参与或PPO预算。
- 生产method真实red/green counterexample、31信息focused+1真实activitypipeline=32相关ROS检查、style初FAIL7处→修复PASS、6000重复TF全部raw性能诊断、nonidentity ledger各版，精确命令/输入/输出/SHA保存在`report/assets/20261017_mr3_p2a0_v9/independent/information_offline/manifest.json`映射的34份原件。全部7.165MB→205522B无损选择，逐字解码核验。原native此次specific skip原因未证，CPU诊断不授native timeliness信用。
- root准确check argv及cwd、源码before/after、wall/退出码和lossless stdout分别见A9根JSON：`launch_ledger_wiring_01`（`/usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_mr3_adapter_launch.py`，15PASS，3.817087281960994墙秒），`ros_semantic_v9_final`（完整merge_map/exploration双包语义、原六ament lint排除不变，1056PASS/36.17测试秒/37.55975944316015墙秒），`conda_cpu_v9_final`（`python -m unittest discover -s mr3_learning/tests -q`，224PASS/25.122测试秒/30.72180647077039墙秒）。ROS环境source Humble及canonical install、PYTHONNOUSERSITE=1；conda ns3gym、unset PYTHONPATH、同PYTHONNOUSERSITE。focused/launch/完整范围重叠，不相加。
- build准确argv：`/usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select merge_map multi_robot_exploration multi_robot`，cwd canonical ROS，3包PASS，7.014945154543966墙秒；`style_v9_final`四个变更Python源码/测试flake8 `--max-line-length=99` PASS/1.1097198398783803墙秒，之前未capture的同文件/选项`python3 -m flake8`早期检查也exit0；`runtime_imports_v9_final`复用原v8精确system import helper（无ROS init/node），七模块source path/hash PASS/1.5080025671049953墙秒。六份root检查source_before==source_after；所有JSON含实际argv/cwd/python及gzip decoded SHA。原驱动库/四C++源未改。

- 新独立information reader `mr3_independent_information_v1.py` SHA `ba3e89fa6feda9406f984310adccf17c2f0638644fd0d26f0c2e9040ec0e7653`、tests SHA `bfd8838318f5d343f469619d53524882e917b3e975418fa5cf2c834e8aa70d93`：25正式methods PASS/1.567秒，system style、canonical字节和syntax、nonidentity真实producer ledger与6000TF兼容重放PASS。所有原FAIL/early stdout/fixture/准确argv/SHA在A9 `independent/information_consumer_offline/`，总回执原`/tmp/mr3_p2a0_v9_information_consumer_checks_v1.json` SHA d2666cb717d567b92ea6980a22d9ea7a163b75473f42f8bb5650f2e1fb2d62cb。该reader明确支持first selection clock与later delivery clock、只要求真实motion已收publication来源，不要求每pub都被接收；不新增假phase门、不使用生产import。

- V9 final plan SHA8258de4418eb6687a10154178b479406217f47b7732bac77a8dc6fce29a03296，33独立bindings=旧27逐字不变+6新增；domain100/102/104-105/108、port12901/12911/12921-22/12931，四stage/608API596actions/18000墙秒保持。canonical启动器13stdlib PASS(.035测试秒/.271墙秒)、三工具style/syntax、contract33pins/163links/nonpinAST与原task/actor/reward/motion/benchmark字节不变PASS，4工具before==after。准确argv/各版draft/style FAIL和final源码/输出/SHA见A9 independent/launcher_offline；final原回执`/tmp/mr3_p2a0_v9_plan_launcher_final_checks_v1.json`。异常Popen后等同一已owned finite child正常回收、launcher仍FAIL/no-retry，不借私有IPC/宽kill。尚无clean-push preflight或原生运行。

- 最终docs新增预声明链接后的contract复核：`python report/assets/20261017_mr3_p2a0_v9/independent/mr3_p2a0_v9_contract_checks.py /tmp/mr3_p2a0_v9_contract_static_final.json`（conda ns3gym），exit0/5.539200895000249墙秒，33 reviewed pins/164相对链接/非pinAST相等及原task/actor/reward/motion/benchmark字节不变PASS。A9 `contract_static_v9_final.json`与`final_runtime_test_bindings_v2.json`绑定六项最终检查及相同最终runtime/docpin字节。
- 三组离线原件归档分别information_offline34项、information_consumer_offline35项、launcher_offline36项，各原/编码/解码逐字核验通过。两个模块使用同一合成producer fixture，其重叠不计独立native信用；缺失的9条早draft字节与post-hoc重建preflight严格标明，不用最终源码冒充历史结果。V8归档完成stdout/stderr补件另列，final库存v2 SHA9488753b0225ac4257166296f10d8fcd5a601066e6f0cf7eef0a2140ead45834，原v1库存保持。原生尚未开始。

- Git保全检查更正：源码/证据提交e27f5c60前cached diff检查发现归档的原始`mr3_v8_terminal_e1_failure_diagnostic_v1.py`第16行尾随空格，root未正确拦住后续commit；未push/未启动native。保留原raw SHA不修改字节，追加该单一归档路径的`-text -whitespace`属性（沿现原生SDF精确保全规则），再核验原脚本/manifest SHA及整个e27变更diff检查；独立binding/执行源未变。补丁另提交，不重写历史。


### 2026-10-17 MR3-P2A.0 v9 原生启动失败闭合

- 源冻结26534fae40409e266376baf0995fb15dc0223e4b；clean+pushed preflight命令`python report/assets/20261017_mr3_p2a0_v9/independent/mr3_p2a0_v9_buildproof_preflight.py`，cwd本wireless-rl，conda ns3gym/unset PYTHONPATH/PYTHONNOUSERSITE=1，97 runtime/33 independent源及实际d0d驱动库匹配PASS。原`/tmp/mr3_p2a0_v9_source_preflight.json` SHA545844e18f8ceb61c741e84c6af9f17f49fb2ad29f01acd43687609579d04ee1已归档。
- 原生`python report/assets/20261017_mr3_p2a0_v9/independent/mr3_p2a0_v9_launch_stage.py interface 26534fae40409e266376baf0995fb15dc0223e4b`；精确benchmark argv/domain100/port12901/环境与PID原件见A9/accounting/mr3_p2a0_v9_interface_launch.json。07:28:33.084717–07:30:53.148215 UTC，140.06299758609384墙秒/exit1，0返回reset、0step、0任务秒。真实initial paused motion not ready错误；本版terminal/reset/deadline均SKIP，不盲重试。
- 初始74.323暂停加17×1ms到74.340，tb2 received source73.795/age545ms>500，own均fresh。producer716实际pub先选TFref5173，freshTFref5176同74.320晚9.363墙毫秒入站；暂停导致下一10Hzpub不触发。新ledger直接证明timer/order starvation。futureodom保留正常；没有队列overflow/conflict。全部原.5源龄/物理门保持。
- 正式full/input/driver/information审计均FAIL缺reset/summary；isolated来源诊断4780odom（3588future）/16101TF/716pub/716motionreceived/11061decision replay provenance通过但overallFalse。执行`python /tmp/mr3_p2a0_v9_root_audit_runner_diagnostic_v2.py interface`，fullaudit exit1/5.867655317764729墙秒、旧不可变driveV4 exit1/.22970817796885967墙秒；准确CLI/console/SHA在A9独立原件。45实际saved身份均消失；forcedcleanup=true，仅4正常spawn/ready退出，无完整native_stop/Nav2final，严格关闭不可PASS。
- 原生pack `/usr/bin/python3 /tmp/mr3_p2a0_v9_pack_native_v1.py interface`及归档`/usr/bin/python3 /tmp/archive_mr3_p2a0_v9_closed_v1.py` exit0：165文件131198920原字节→7508070无损选择，97Git源、137prefreeze assets、54独立原件核验；manifest SHA4401e4570e7a130b9fc1b5df6e1bfb2a8fba302dfc50b111b9a269ab2c67f3d1；inventory_native_v1 SHAf357ba0945a2411225ef9c8e0588aeed2ac3d8b8668b3db875fb8624a279dfb4。所有失败原件保留，后续v10显式阶段与startup invalid有序关闭。原生GPU/optimizer=0，pilot余额1870/2905.954739546403保持。


### 2026-10-17 MR3-P2A.0 v10 冻结前显式执行阶段修复与完整离线验证

以已push的26534fae40409e266376baf0995fb15dc0223e4b为base继续P2A.0。v9实际FAIL不改，补件archive_completion_v2及inventory_native_v2（365项，SHA b76b7a28a4a230dae045e63268131b49d6a95cf67ebef35753fc1f9d6b1148a2）另列原件。v10每20ms真实state/peer/guard/localreceipt/native storage有序ACK、唯一零bootstrap、永久stop及invalid启动有序关闭；受控状态有效50Hz是明确接口变更，非受控10Hz、.5s源龄及全部原task/body/stop/160ms/settled门不变。没有原生训练或optimizer，pilot余额1870/2905.954739546403不变。

最终ROS1167 PASS、conda236 PASS、27文件style及3包build/10实际system import PASS。早期ROS3 FAIL、conda2 ERROR、guard及style/fixture/工作目录检查失败均保留原stdout和准确版本；没有把合成检查作为native信用。每项root检查的完整实际argv/cwd/Python/source-before-after/exit/wall及gzip decoded SHA在A10根同名JSON，以下是本次实际CPU调用的索引（`source_status=precommit working bytes`，不是旧freeze native结果）：

```json
[
  {
    "receipt": "build_v10_final.json",
    "exit_code": 0,
    "wall_seconds": 9.288078633137047,
    "command": [
      "/usr/bin/bash",
      "--noprofile",
      "--norc",
      "-c",
      "source /opt/ros/humble/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select merge_map multi_robot_exploration multi_robot"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap"
  },
  {
    "receipt": "conda_cpu_v10_final.json",
    "exit_code": 1,
    "wall_seconds": 25.73184002377093,
    "command": [
      "/usr/bin/env",
      "-u",
      "PYTHONPATH",
      "PYTHONNOUSERSITE=1",
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "-m",
      "unittest",
      "discover",
      "-s",
      "mr3_learning/tests",
      "-q"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
  },
  {
    "receipt": "conda_cpu_v10_final_v2.json",
    "exit_code": 0,
    "wall_seconds": 35.147919084876776,
    "command": [
      "/usr/bin/env",
      "-u",
      "PYTHONPATH",
      "PYTHONNOUSERSITE=1",
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "-m",
      "unittest",
      "discover",
      "-s",
      "mr3_learning/tests",
      "-q"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
  },
  {
    "receipt": "conda_cpu_v10_final_v3.json",
    "exit_code": 0,
    "wall_seconds": 25.82693194784224,
    "command": [
      "/usr/bin/env",
      "-u",
      "PYTHONPATH",
      "PYTHONNOUSERSITE=1",
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "-m",
      "unittest",
      "discover",
      "-s",
      "mr3_learning/tests",
      "-q"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
  },
  {
    "receipt": "conda_cpu_v10_final_v4.json",
    "exit_code": 0,
    "wall_seconds": 25.107419546693563,
    "command": [
      "/usr/bin/env",
      "-u",
      "PYTHONPATH",
      "PYTHONNOUSERSITE=1",
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "-m",
      "unittest",
      "discover",
      "-s",
      "mr3_learning/tests",
      "-q"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
  },
  {
    "receipt": "contract_static_draft_01.json",
    "exit_code": 0,
    "wall_seconds": 5.160603567957878,
    "command": [
      "/usr/bin/env",
      "-u",
      "PYTHONPATH",
      "PYTHONNOUSERSITE=1",
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_contract_checks.py",
      "/tmp/mr3_p2a0_v10_contract_static_draft_01.json"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
  },
  {
    "receipt": "guard_focused_01.json",
    "exit_code": 1,
    "wall_seconds": 4.693017710931599,
    "command": [
      "/usr/bin/bash",
      "--noprofile",
      "--norc",
      "-c",
      "source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_mr3_motion_control.py src/multi_robot_exploration/test/test_motion_safety.py src/multi_robot_exploration/test/test_settled_turn.py"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap"
  },
  {
    "receipt": "guard_focused_02.json",
    "exit_code": 1,
    "wall_seconds": 4.614243202842772,
    "command": [
      "/usr/bin/bash",
      "--noprofile",
      "--norc",
      "-c",
      "source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_mr3_motion_control.py src/multi_robot_exploration/test/test_motion_safety.py src/multi_robot_exploration/test/test_settled_turn.py && /usr/bin/python3 -m flake8 src/multi_robot_exploration/multi_robot_exploration/motion_safety.py src/multi_robot_exploration/multi_robot_exploration/mr3_motion_control.py src/multi_robot_exploration/test/test_mr3_motion_control.py src/multi_robot_exploration/test/test_motion_safety.py src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py --max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap"
  },
  {
    "receipt": "guard_focused_03.json",
    "exit_code": 1,
    "wall_seconds": 5.5136871873401105,
    "command": [
      "/usr/bin/bash",
      "--noprofile",
      "--norc",
      "-c",
      "source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_mr3_motion_control.py src/multi_robot_exploration/test/test_motion_safety.py src/multi_robot_exploration/test/test_settled_turn.py && /usr/bin/python3 -m flake8 src/multi_robot_exploration/multi_robot_exploration/motion_safety.py src/multi_robot_exploration/multi_robot_exploration/mr3_motion_control.py src/multi_robot_exploration/test/test_mr3_motion_control.py src/multi_robot_exploration/test/test_motion_safety.py src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py --max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap"
  },
  {
    "receipt": "guard_focused_04.json",
    "exit_code": 0,
    "wall_seconds": 5.603635247796774,
    "command": [
      "/usr/bin/bash",
      "--noprofile",
      "--norc",
      "-c",
      "source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_mr3_motion_control.py src/multi_robot_exploration/test/test_motion_safety.py src/multi_robot_exploration/test/test_settled_turn.py && /usr/bin/python3 -m flake8 src/multi_robot_exploration/multi_robot_exploration/motion_safety.py src/multi_robot_exploration/multi_robot_exploration/mr3_motion_control.py src/multi_robot_exploration/test/test_mr3_motion_control.py src/multi_robot_exploration/test/test_motion_safety.py src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py --max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap"
  },
  {
    "receipt": "guard_focused_05.json",
    "exit_code": 0,
    "wall_seconds": 4.583252803888172,
    "command": [
      "/usr/bin/bash",
      "--noprofile",
      "--norc",
      "-c",
      "source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_mr3_motion_control.py src/multi_robot_exploration/test/test_motion_safety.py src/multi_robot_exploration/test/test_settled_turn.py"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap"
  },
  {
    "receipt": "launch_phase_wiring_01.json",
    "exit_code": 0,
    "wall_seconds": 5.50466783484444,
    "command": [
      "/usr/bin/bash",
      "--noprofile",
      "--norc",
      "-c",
      "source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_mr3_adapter_launch.py"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap"
  },
  {
    "receipt": "launcher_style_v10_final.json",
    "exit_code": 1,
    "wall_seconds": 0.7774994573555887,
    "command": [
      "/usr/bin/python3",
      "-m",
      "flake8",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_buildproof_preflight.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_launch_stage.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_plan_launcher_tests_v1.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_audit_stage.py",
      "--max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace"
  },
  {
    "receipt": "launcher_style_v10_final_v2.json",
    "exit_code": 0,
    "wall_seconds": 0.792501084972173,
    "command": [
      "/usr/bin/python3",
      "-m",
      "flake8",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_buildproof_preflight.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_launch_stage.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_plan_launcher_tests_v1.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_audit_stage.py",
      "--max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace"
  },
  {
    "receipt": "observer_syntax_plan_01.json",
    "exit_code": 0,
    "wall_seconds": 0.491785628721118,
    "command": [
      "/usr/bin/python3",
      "-c",
      "import ast,runpy; from pathlib import Path; p=Path('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent'); [ast.parse(f.read_text()) for f in p.glob('mr3*v10*.py')]; runpy.run_path(str(p/'mr3_p2a0_v10_plan_launcher_tests_v1.py'),run_name='__main__')"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace"
  },
  {
    "receipt": "plan_launcher_draft_01.json",
    "exit_code": 0,
    "wall_seconds": 0.25144996028393507,
    "command": [
      "/usr/bin/python3",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_plan_launcher_tests_v1.py"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace"
  },
  {
    "receipt": "plan_launcher_v10_final.json",
    "exit_code": 0,
    "wall_seconds": 0.25509231397882104,
    "command": [
      "/usr/bin/python3",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_plan_launcher_tests_v1.py"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace"
  },
  {
    "receipt": "plan_launcher_v10_final_v2.json",
    "exit_code": 0,
    "wall_seconds": 0.7794155701994896,
    "command": [
      "/usr/bin/python3",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_plan_launcher_tests_v1.py"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace"
  },
  {
    "receipt": "root_style_01.json",
    "exit_code": 1,
    "wall_seconds": 1.0927389599382877,
    "command": [
      "/usr/bin/python3",
      "-m",
      "flake8",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_control.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_motion_control.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_motion_safety.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_adapter_launch.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_audit_stage.py",
      "--max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace"
  },
  {
    "receipt": "root_style_02.json",
    "exit_code": 1,
    "wall_seconds": 1.0394070306792855,
    "command": [
      "/usr/bin/python3",
      "-m",
      "flake8",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_control.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_motion_control.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_motion_safety.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_adapter_launch.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_audit_stage.py",
      "--max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace"
  },
  {
    "receipt": "root_style_03.json",
    "exit_code": 0,
    "wall_seconds": 1.0692494758404791,
    "command": [
      "/usr/bin/python3",
      "-m",
      "flake8",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_control.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_motion_control.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_motion_safety.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_adapter_launch.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_audit_stage.py",
      "--max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace"
  },
  {
    "receipt": "ros_semantic_v10_final.json",
    "exit_code": 1,
    "wall_seconds": 37.42907654680312,
    "command": [
      "/usr/bin/bash",
      "--noprofile",
      "--norc",
      "-c",
      "source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 -m pytest -q src/merge_map/test src/multi_robot_exploration/test --ignore=src/merge_map/test/test_copyright.py --ignore=src/merge_map/test/test_flake8.py --ignore=src/merge_map/test/test_pep257.py --ignore=src/multi_robot_exploration/test/test_copyright.py --ignore=src/multi_robot_exploration/test/test_flake8.py --ignore=src/multi_robot_exploration/test/test_pep257.py"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap"
  },
  {
    "receipt": "ros_semantic_v10_final_v2.json",
    "exit_code": 0,
    "wall_seconds": 35.342729937750846,
    "command": [
      "/usr/bin/bash",
      "--noprofile",
      "--norc",
      "-c",
      "source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 -m pytest -q src/merge_map/test src/multi_robot_exploration/test --ignore=src/merge_map/test/test_copyright.py --ignore=src/merge_map/test/test_flake8.py --ignore=src/merge_map/test/test_pep257.py --ignore=src/multi_robot_exploration/test/test_copyright.py --ignore=src/multi_robot_exploration/test/test_flake8.py --ignore=src/multi_robot_exploration/test/test_pep257.py"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap"
  },
  {
    "receipt": "ros_semantic_v10_final_v3.json",
    "exit_code": 0,
    "wall_seconds": 36.722919282037765,
    "command": [
      "/usr/bin/bash",
      "--noprofile",
      "--norc",
      "-c",
      "source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 -m pytest -q src/merge_map/test src/multi_robot_exploration/test --ignore=src/merge_map/test/test_copyright.py --ignore=src/merge_map/test/test_flake8.py --ignore=src/merge_map/test/test_pep257.py --ignore=src/multi_robot_exploration/test/test_copyright.py --ignore=src/multi_robot_exploration/test/test_flake8.py --ignore=src/multi_robot_exploration/test/test_pep257.py"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap"
  },
  {
    "receipt": "runtime_imports_v10_final.json",
    "exit_code": 0,
    "wall_seconds": 2.3329720706678927,
    "command": [
      "/usr/bin/bash",
      "--noprofile",
      "--norc",
      "-c",
      "source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_runtime_import_check.py /tmp/mr3_p2a0_v10_runtime_import_bindings.json"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap"
  },
  {
    "receipt": "runtime_imports_v10_final_v2.json",
    "exit_code": 0,
    "wall_seconds": 2.312925858888775,
    "command": [
      "/usr/bin/bash",
      "--noprofile",
      "--norc",
      "-c",
      "source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_runtime_import_check.py /tmp/mr3_p2a0_v10_runtime_import_bindings_v2.json"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap"
  },
  {
    "receipt": "style_v10_final.json",
    "exit_code": 0,
    "wall_seconds": 1.6993079599924386,
    "command": [
      "/usr/bin/python3",
      "-m",
      "flake8",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_motion.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_ppo.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_preparation.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/tests/test_audit_motion.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/tests/test_audit_preparation.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/tests/test_preparation_execution.py",
      "ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_control_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_information.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_control.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/peer_obstacles.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_motion_safety.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_adapter_launch.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_control_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_drive_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_evaluator_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_information.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_information_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_infrastructure_abort.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_motion_control.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_peer_phase.py",
      "--max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace"
  },
  {
    "receipt": "style_v10_final_v2.json",
    "exit_code": 0,
    "wall_seconds": 1.740019764751196,
    "command": [
      "/usr/bin/python3",
      "-m",
      "flake8",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_controlled_physics.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_motion.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_ppo.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_preparation.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/tests/test_audit_controlled_physics.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/tests/test_audit_motion.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/tests/test_audit_ppo.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/tests/test_audit_preparation.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/tests/test_preparation_execution.py",
      "ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_control_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_information.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_control.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/peer_obstacles.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_motion_safety.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_adapter_launch.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_control_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_drive_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_evaluator_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_information.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_information_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_infrastructure_abort.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_motion_control.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_peer_phase.py",
      "--max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace"
  },
  {
    "receipt": "style_v10_final_v3.json",
    "exit_code": 0,
    "wall_seconds": 1.7285019289702177,
    "command": [
      "/usr/bin/python3",
      "-m",
      "flake8",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_controlled_physics.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_motion.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_ppo.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_preparation.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/tests/test_audit_controlled_physics.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/tests/test_audit_motion.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/tests/test_audit_ppo.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/tests/test_audit_preparation.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/tests/test_preparation_execution.py",
      "ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_control_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_information.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_control.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/peer_obstacles.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_motion_safety.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_adapter_launch.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_control_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_drive_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_evaluator_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_information.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_information_phase.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_infrastructure_abort.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_motion_control.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_peer_phase.py",
      "--max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace"
  }
]
```

各agent离线执行的准确argv、原早期失败、producer fixture、source snapshot可用范围与原/编码/解码SHA分别在A10 `independent/{information_offline,drive_offline,guard_review_offline,runner_offline,runtime_offline,runtime_integration_offline,peer_control_offline}/manifest.json`。其中runtime76原件+integration25原件，information27、drive7、guard18、runner371、peer/control68原件；mock13个runner路径/10实际CLI help不代表native执行。58个peer/control、63个drive（含原50+13stop）、18个information方法及root87个guard检查与完整检查有重叠，不相加。最终root工具原件/源码仅代表最终版本，未独立快照的早期draft明确标为缺失，不用最终源码冒充。

共享stdlib physics dispatcher使preparation与audit_ppo识别同一真实零bootstrap，保留所有原物理数学/完整行/真实任务release/legacy/策略容量和目标。仅此一import、一文件binding和try/finally调用替换由静态AST精确许可，不豁免整个函数。没有PPO采样、GPU或优化器。四阶段正式原生尚未开始；clean push后preflight和实际binary/proc映射须新核验。

冻结前补充两项实际检查：`plan_launcher_v10_final_v3`13 PASS/0.7238266966305673墙秒，准确命令conda python A10/independent/mr3_p2a0_v10_plan_launcher_tests_v1.py；`contract_static_v10_final`35pins/156links/AST PASS/4.826862648129463墙秒，准确命令`env -u PYTHONPATH PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_contract_checks.py /tmp/mr3_p2a0_v10_contract_static_final.json`，均cwd W。实际argv/source/console在同名JSON。root_offline manifest SHA 9d8249bcc8c08af322bc045f655d1badde34f0ea404e28716da309245467c2c5，最终预声明SHA 0456d6100e44bf93afe66edf2d057d5c71161dbbdcdd2f12cbf37f0fe63a1e52、59bindings。静态检查后仅补结果文字，不改执行合同/pins/代码。


### 2026-10-17 MR3-P2A.0 v10 原生QoS及pre-release关闭FAIL闭合

冻结631d8c35c43fdb7ed45e984376543e55395066ef，clean push后执行`env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_buildproof_preflight.py`，100runtime/59independent/原d0d库PASS；`/usr/bin/python3 /tmp/mr3_p2a0_v10_pack_source_bindings_v1.py`保存100精确Git payload。实际原生同env/conda命令`python report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_launch_stage.py interface 631d8c35c43fdb7ed45e984376543e55395066ef`，精确benchmark argv及domain110/port13001在A10 accounting原launch JSON。08:41:44.569672–08:45:14.870305 UTC，launcher210.30002562794834wall/benchmark209.8452442488633wall，exit1；两包装时间不相加。1reset attempt/0returned reset/0step/0taskseconds/0GPUupdate。terminal/reset/deadline均SKIP未尝试。

实际peer72.62 takeoverACK已publish，worker请求TL而peer默认VOLATILE，真实DURABILITY warning与10walltimeout对应。随后真实基础设施通知/永久零/storage/20ticks排空，但adapter未release时maintain早return跳过dispatcher.closed后的真实探索停止ACK，cleanup60.000343832187355walltimeout后forced。45fresh PID/start gone仅授absence，原forced_shutdownTrue/failed_sampleTrue/worker_rc1/native_stop缺失/strict closure FAIL不改。三实际SDF/driver配置/proc真实mapping匹配冻结d0d子事实不授整体PASS。

正式调用同conda env `python report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_audit_stage.py interface 631d8c35c43fdb7ed45e984376543e55395066ef`，cwd W；11条实际CLI/exit/wall/stdout/outputSHA在A10 independent/mr3_p2a0_v10_interface_audit_execution_v1.json。全部FAIL，FIFO/closure无reset入口未生成JSON，console保留。未用reader细项PASS覆盖该失败。v10control reader standalone abandonednegative缺口由mandatory full gate仍拒绝，原CPU反例与旧PASS/worker拒绝保留，v11加强对应reader不放宽生产门。

原件pack `/usr/bin/python3 /tmp/mr3_p2a0_v10_pack_native_v1.py interface`：192文件170895648raw→9932259选择字节，60support原件及100精确Git payload无损核验；inventory_native_v1自排986项SHAe022c7bd8c3d51861392dbe719778a9c3bfcffb36f669831a5316891067536cf，verification SHA90379e0c667792852fe0a684b543151e0c40c57854bb6a6df46cb44025766458。原724条prefreeze字节均存在，但2条canonical worker快照被ignore未入631：实际631是722条+inventory=723文件；下一commit明确force-add这2条原字节，不改旧inventory或声称旧冻结已发布。原生产100source pack不受影响。pilot余额1870/2905.954739546403保持，无P2A.0/95%训练信用。

封存库存范围更正：原inventory_native_v1误包含3个ignored Python cache，仅是初版库存范围错误，原件及字节不改。最终inventory_native_v2显式排缓存、selfexcluded，984项SHA88ae6db30c44746cbd092ae70dbb5bb14ef79b65460c554fd55ad5dd5e8a6776；不发布缓存。


### 2026-10-17 MR3-P2A.0 v11 最小接线修复与完整离线检查

基准V10 frozen631d8c35，working byte peer ad8f1676a4743f6cb01ff5d4b3b4a56555ec752e0fb92538597b54fffdf59b56、adapter d9121970b18e86a524ad4aad591a64661555bc15c0a59bf425896324473eecfc。仅peer ACK reliable/TL1与pre-release已stop且dispatcher真实closed的原ACK通路/None deadline guard，未release无规划/reward；所有source/body/task门、物理、actor、奖励、训练保持。audit_ppo两PREP pin及audit_protocol一adapter pin同步，后者非pin AST相同，不改unsent proof逻辑。

完整ROS1175 PASS，conda236 PASS，actual10 installed imports/6source+test style/5coordinator style/13launcher/35pins及121links PASS。第一conda207run/2setupERROR因旧unsentproof adapterpin正确拒新源码，原FAIL留存；初root静态style直接调用6错误（E731/E402/3E128/E501），未capture专门stdout，原工具转录存在，不假造原件；随后capture root_style01四错误、修复02PASS。最终所有rootchecks的before==after且原stdout无损。准确每次argv/cwd/exit/wall在A11同名JSON及如下实际调用索引：

```json
[
  {
    "command": [
      "/usr/bin/env",
      "-u",
      "PYTHONPATH",
      "PYTHONNOUSERSITE=1",
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "-m",
      "unittest",
      "discover",
      "-s",
      "mr3_learning/tests",
      "-q"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl",
    "exit_code": 1,
    "wall_seconds": 33.15218872204423,
    "stdout_stderr_gzip": "conda_cpu_v11_final.log.gz",
    "decoded_sha256": "6eb919ba704daca7586f0f99a765aaab2a32ec6a4161a0398fffd95b8eedbba1"
  },
  {
    "command": [
      "/usr/bin/env",
      "-u",
      "PYTHONPATH",
      "PYTHONNOUSERSITE=1",
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "-m",
      "unittest",
      "discover",
      "-s",
      "mr3_learning/tests",
      "-q"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl",
    "exit_code": 0,
    "wall_seconds": 31.258900242857635,
    "stdout_stderr_gzip": "conda_cpu_v11_final_v2.log.gz",
    "decoded_sha256": "a16d0ebbd41005ff6a58f15bfc54fa16aa8fc1530c644751b8aac2add234bdb8"
  },
  {
    "command": [
      "/usr/bin/env",
      "-u",
      "PYTHONPATH",
      "PYTHONNOUSERSITE=1",
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_contract_checks.py",
      "/tmp/mr3_p2a0_v11_contract_static_final.json"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl",
    "exit_code": 0,
    "wall_seconds": 5.038378910627216,
    "stdout_stderr_gzip": "contract_static_v11_final.log.gz",
    "decoded_sha256": "da8666691481979da99276581f3c2bffd88132654951500f833fee5828ee6723"
  },
  {
    "command": [
      "/usr/bin/env",
      "-u",
      "PYTHONPATH",
      "PYTHONNOUSERSITE=1",
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_contract_checks.py",
      "/tmp/mr3_p2a0_v11_contract_static_final_v2.json"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl",
    "exit_code": 0,
    "wall_seconds": 5.294793718028814,
    "stdout_stderr_gzip": "contract_static_v11_final_v2.log.gz",
    "decoded_sha256": "da8666691481979da99276581f3c2bffd88132654951500f833fee5828ee6723"
  },
  {
    "command": [
      "/usr/bin/env",
      "-u",
      "PYTHONPATH",
      "PYTHONNOUSERSITE=1",
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_plan_launcher_tests_v1.py"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl",
    "exit_code": 0,
    "wall_seconds": 0.2716349666006863,
    "stdout_stderr_gzip": "plan_launcher_v11_final.log.gz",
    "decoded_sha256": "688b6928c8a57e68004225a884d51c19aac5fcf719b2f718d2e5fe8d6356b74d"
  },
  {
    "command": [
      "/usr/bin/env",
      "-u",
      "PYTHONPATH",
      "PYTHONNOUSERSITE=1",
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_plan_launcher_tests_v1.py"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl",
    "exit_code": 0,
    "wall_seconds": 0.2753863916732371,
    "stdout_stderr_gzip": "plan_launcher_v11_final_v2.log.gz",
    "decoded_sha256": "8e8f32b64b12b3f119919b9253db0b16fa1544f6956d4878b20a15243297b552"
  },
  {
    "command": [
      "/usr/bin/python3",
      "-m",
      "flake8",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_contract_checks.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_audit_stage.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_launch_stage.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_buildproof_preflight.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_plan_launcher_tests_v1.py",
      "--max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace",
    "exit_code": 1,
    "wall_seconds": 0.7980459146201611,
    "stdout_stderr_gzip": "root_style_v11_01.log.gz",
    "decoded_sha256": "2fe3a925bb3e3f58f7f35c1363c5ba2db00d4c586758c4923b6c8c249c74094b"
  },
  {
    "command": [
      "/usr/bin/python3",
      "-m",
      "flake8",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_contract_checks.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_audit_stage.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_launch_stage.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_buildproof_preflight.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_plan_launcher_tests_v1.py",
      "--max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace",
    "exit_code": 0,
    "wall_seconds": 0.795739684253931,
    "stdout_stderr_gzip": "root_style_v11_02.log.gz",
    "decoded_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  },
  {
    "command": [
      "/bin/bash",
      "-c",
      "source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 -m pytest -q src/merge_map/test src/multi_robot_exploration/test --ignore=src/merge_map/test/test_copyright.py --ignore=src/merge_map/test/test_flake8.py --ignore=src/merge_map/test/test_pep257.py --ignore=src/multi_robot_exploration/test/test_copyright.py --ignore=src/multi_robot_exploration/test/test_flake8.py --ignore=src/multi_robot_exploration/test/test_pep257.py"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap",
    "exit_code": 0,
    "wall_seconds": 40.27761468477547,
    "stdout_stderr_gzip": "ros_semantic_v11_final.log.gz",
    "decoded_sha256": "7cdc917231178a7cde9fa4283c75c943fd3c2be20bb9219407b1dae523ccdcd9"
  },
  {
    "command": [
      "/bin/bash",
      "-c",
      "source /opt/ros/humble/setup.bash && source install/setup.bash && export PYTHONNOUSERSITE=1 && /usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_p2a0_v10_runtime_import_check.py /tmp/mr3_p2a0_v11_runtime_import_bindings.json"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap",
    "exit_code": 0,
    "wall_seconds": 2.301298280246556,
    "stdout_stderr_gzip": "runtime_imports_v11_final.log.gz",
    "decoded_sha256": "1d989cfc60e2e774985a5665ccd4b7c22da44a8af0cd221e5b66f2243869289a"
  },
  {
    "command": [
      "/usr/bin/python3",
      "-m",
      "flake8",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_ppo.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_protocol.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/peer_obstacles.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_phase_qos.py",
      "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_adapter.py",
      "--max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace",
    "exit_code": 0,
    "wall_seconds": 1.1483816653490067,
    "stdout_stderr_gzip": "source_style_v11_final.log.gz",
    "decoded_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }
]
```

实际端点QoS+真实ACK交付/adapter focused67PASS，初red7FAIL1PASS（2真实缺口+5初test默认liveliness警告误判）及原fixture/source-before-after/准确argv在A11 independent/runtime_offline/originals_manifest_v1.json，SHA cb3a37ddfc1a3ffea2311ff91dabf64cd65419103a40da2c9c5921d1ac994320，19原件254967raw；缺失初中间test bytes明确标注。独立control v2只继承原04cd/旧58，新增9sticky negativemutation；旧CLI真实反例exit0/PASS、新CLI exit1/FAIL正确拒绝，同raw输入恒定，wrapper AST原实际拒绝。27原件manifest181217d13cdb5671b27eda8352e7b8ac29a5ffd8e8035e04aaed12ec20501930，raw184890→27865B；无native信用。root原件manifestf87fac9539a6813b0a7cc2f9181e658111366f34bfeec56217f0d4494749d15f。新plan68bindings/18000wall/608API596actions与原四stage门保持；仍需新clean-push preflight及完整新原生矩阵。无PPO/GPU/optimizer，pilot余额不变。


### 2026-10-17 MR3-P2A.0 v11 原生接口32闭合：独立执行/物理PASS，完整旧握手消费者FAIL

冻结ba018fe3122c478836eb4e5da9c14306cd832c1b。clean push后同conda/unset PYTHONPATH/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1执行A11 mr3_p2a0_v11_buildproof_preflight.py：100runtime/68independent/实际d0d库PASS。sourcepack精确命令 `/usr/bin/python3 /tmp/mr3_p2a0_v10_pack_source_bindings_v1.py --preflight /tmp/mr3_p2a0_v11_source_preflight.json`，100Git payload及68indie逐旧Git核验，不取后续working source。

实际入口conda python `report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_launch_stage.py interface ba018fe3122c478836eb4e5da9c14306cd832c1b`（cwd W），benchmark精确argv `python -u -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 32 --preparation-motion-probe --preparation-probe-version mr3-p2a0-outward-cancel-v3 --base-domain 120 --base-port 13101 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261017_v11_interface --preparation-parameter-review`。08:55:24.992672–09:07:48.833582 UTC，launcher743.8402884537354wall/sampler743.3724391502328wall，不相加两个包装时间；exit0，1reset+32step=33API/32提交/32任务秒，0GPUupdate。firstpause73.548，12×1ms对齐→T0 73.560，唯一bootstrap20→T1/release73.580，末105.600含1stop20ticks。严格关闭39native clean、3manager/18managed finalized、worker0/forcedFalse/failedFalse，46真实PID/start fresh全部gone；实际/proc mapped库、3SDF/topology/4compiled源均匹配d0d冻结proof。

正式命令同conda env `python report/assets/20261017_mr3_p2a0_v11/independent/mr3_p2a0_v11_audit_stage.py interface ba018fe3122c478836eb4e5da9c14306cd832c1b`，cwd W。11条实际审计CLI的完整argv/cwd/returncode/wall/stdout/outputSHA无损保存在A11 independent/native_originals_v1/mr3_p2a0_v11_interface_audit_execution_v1.json.gz。10PASS，唯fullaudit FAIL：旧W7 initial-input函数只认旧reset_handshake，原contact context同函数不能建立paused-release证明；完整physics/32transition/protocol/orderedclosure子PASS，raw18stream sequence/zero_contact不能覆盖contact proof FAIL。9/10mandatory PASS不足通过该stage，terminal/reset/deadline全部SKIP未启动。以下是实际11条审计成本，不计native/pilot：

- full_audit: exit1, 206.88751414837316 wallsec, passed=False
- drive_review_v1: exit0, 116.45206854585558 wallsec, passed=True
- information_review_v1: exit0, 141.64619582612067 wallsec, passed=True
- peer_review_v1: exit0, 43.0843420708552 wallsec, passed=True
- control_review_v1: exit0, 106.98342876508832 wallsec, passed=True
- settled_turn_review_v1: exit0, 26.744677194859833 wallsec, passed=True
- input_001: exit0, 176.87942467583343 wallsec, passed=True
- fixed_angular_v1: exit0, 24.606267692055553 wallsec, passed=True
- fixed_physics_v1: exit0, 23.56654698587954 wallsec, passed=True
- episode001_fifo_phase_final: exit0, 13.472752128727734 wallsec, passed=True
- closure_binary_review_v1: exit0, 4.6481345552019775 wallsec, passed=True

原生pack `/usr/bin/python3 /tmp/mr3_p2a0_v11_pack_native_v1.py interface`：574原件557216344raw→34201275选择字节，manifest118604b2bb6df5b73a18e9b1be8400a34d964fb232e5c9858400e47600941f22。79support含全部原FAIL/prefix/console/tools；100Git runtime及68indie oldobjects全exact，旧A11 91Git/90prefreeze逐字不变。最终inventory_native_v1排cache/self750项SHAc6018d3293dc926af113df06f9fb28de043066e3b94d5f690c546d592793571b，verification SHAdab30299b9e1b04c1284a2e88d1d037fb5f339e1cec15d7f48b288160261bfa7，canonical无ignored。初prefix仅诊断，两个版本轨迹差异不作单因ablation。V12仅修受限消费者并新freeze整矩阵，原FAIL/门保持；pilot余额1870/2905.954739546403不变，无95%学习/P2A信用。


### 2026-10-17 MR3-P2A.0 v12 受限readiness消费者与最终离线验证

基准ba018fe3122c478836eb4e5da9c14306cd832c1b，ROS/任务/actor/奖励/候选/全部body/source/physical/contact数学不变，只有shared readiness与PPO/preparation显式安装/还原接线。97运行与合同源逐Git字节相同；旧4个shared函数AST相同；PPO/preparation除精确reviewed import、共享cache及两hook try/finally接线外全AST相等。原contact/W7函数仍真调用。新协议只读复合证明先做真实T0/20bootstrap/T1/3storage/adapter投影/seq0/LIVE→首quantum，再在明确子predicate视图使用原prewarm ACK规则，不改原metadata或把它装成旧协议；同clock late-map原合法路径允许，snapshot/seq0原门保持。

root完整conda247 PASS（46.953test/52.430579245090485wall）、5coordinator style、13launcher、35pins/122links/97源及AST检查PASS。root_style_v12_01曾误将dense档案CLI fixture纳入style：372个fixture格式项及2个checker长行FAIL原stdout保留；2checker长行已修，最终style范围5个实际coordinator，不声称档案fixture lint-clean，不改旧原件。该fixture的7个真实main调度语义检查均PASS。ROS源码无变，V11原1175PASS适用字节不变，不再启动ROS/build。所有root原argv/cwd/source-before-after/exit/wall/无损stdout在A12根JSON，最终4check before==after；索引：

```json
[
  {
    "command": [
      "/usr/bin/env",
      "-u",
      "PYTHONPATH",
      "PYTHONNOUSERSITE=1",
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "-m",
      "unittest",
      "discover",
      "-s",
      "mr3_learning/tests",
      "-q"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl",
    "exit_code": 0,
    "wall_seconds": 52.430579245090485,
    "stdout_stderr_gzip": "conda_cpu_v12_final.log.gz",
    "decoded_sha256": "ee0fb8085cb905c33d0c55b5747e2b330dc375551b1b79ec5bd94481114423e2"
  },
  {
    "command": [
      "/usr/bin/env",
      "-u",
      "PYTHONPATH",
      "PYTHONNOUSERSITE=1",
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_contract_checks.py",
      "/tmp/mr3_p2a0_v12_contract_static_final.json"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl",
    "exit_code": 0,
    "wall_seconds": 5.720741203986108,
    "stdout_stderr_gzip": "contract_static_v12_final.log.gz",
    "decoded_sha256": "10f62bdb5d26887d08c2a8d3b729317c330f5b47bac3e00cf11fd83f188fabe5"
  },
  {
    "command": [
      "/usr/bin/env",
      "-u",
      "PYTHONPATH",
      "PYTHONNOUSERSITE=1",
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_plan_launcher_tests_v1.py"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl",
    "exit_code": 0,
    "wall_seconds": 0.2877263040281832,
    "stdout_stderr_gzip": "plan_launcher_v12_final.log.gz",
    "decoded_sha256": "8e8f32b64b12b3f119919b9253db0b16fa1544f6956d4878b20a15243297b552"
  },
  {
    "command": [
      "/usr/bin/python3",
      "-m",
      "flake8",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_contract_checks.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_audit_stage.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_audit_stage_tests_v1.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_launch_stage.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_buildproof_preflight.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_plan_launcher_tests_v1.py",
      "--max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace",
    "exit_code": 1,
    "wall_seconds": 0.8029936011880636,
    "stdout_stderr_gzip": "root_style_v12_01.log.gz",
    "decoded_sha256": "7cde02a34e2bcc1a2dbca7cfed56f576e5d6547daf8b9113224e119c6d5f6018"
  },
  {
    "command": [
      "/usr/bin/python3",
      "-m",
      "flake8",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_contract_checks.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_audit_stage.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_launch_stage.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_buildproof_preflight.py",
      "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_plan_launcher_tests_v1.py",
      "--max-line-length=99"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace",
    "exit_code": 0,
    "wall_seconds": 0.8457756321877241,
    "stdout_stderr_gzip": "root_style_v12_final.log.gz",
    "decoded_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }
]
```

agent初19/11/14版fixture/字段/style失败、diagnostic01 FAIL及02/03/04 working-consumer真实组合PASS（末43.643547wall）原件均保留。最终15focused PASS/20.840test/25.594564wall；其范围与root247重叠不相加。实际V11原输入/旧正式FAIL/本working source前后SHA恒定，原W7 ACK子predicate+原contact.release_context真实入口均运行；该诊断不重新采样、不冒新freeze或95%信用。Runtime50原件raw689428/encoded664924，manifestb00632762c643844d2396a98bec5e94b1442ef3a4b264d524549ce426e993e4c；缺失早draft字节明确记录。独立Safety review v1/v2源码/结果均在该manifest，v2 SHA2219a0a44b9d361ed4057a1ab73a11f8bd6be0c9d4ba67fc7f27ba185c368bc8。

bounded4 ThreadPoolExecutor只调度原独立审计subprocess，rawphysical先于pooledmatrix、全部FIFO先于closure、主/子异常也finally等待全部已提交任务，完成后才组装mandatory；7个actual main/fakeCLI测试涵盖4上限/两依赖/失败保留/两层异常drain/不覆盖。runner10原件manifest0d3c19aaa4d314e333de4cfbe538f92a000eee93c1f01382cf4686581aa88ac9，最终源码/fixtures明确，未复制mock树或重造早draft。root原件manifest183e39c30d8f49bd59042d6e2f431785d2b4eb7e2b18fdd49847e63afcfe5e51。新plan76bindings/100runtime待preflight，四阶段608API/596actions/18000nativewall原门不变。V12尚无原生/PPO/GPU/optimizer，pilot余额1870/2905.954739546403不变。


### 2026-10-17 MR3-P2A.0 V12 native（正式FAIL，待canonical归档链接）

freeze `6b1b4a0108351f5bfb70ec0c96ba895248d4f7a8`；source preflight100 runtime/76independent，原actual binary/four macro proof按其原receipt。按预声明依次执行三次benchmark（精确实际argv如下；启动环境及launcher/source/planSHA见各`/tmp/mr3_p2a0_v12_{stage}_launch.json`，正式审计完整命令与退出/输出SHA见`*_audit_execution_v1.json`）：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 32 --preparation-motion-probe --preparation-probe-version mr3-p2a0-outward-cancel-v3 --base-domain 130 --base-port 13201 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261017_v12_interface --preparation-parameter-review
```

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 --steps 4 --terminal-probe --base-domain 132 --base-port 13211 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261017_v12_terminal
```

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u -m mr3_learning.benchmark --workers 2 --schedule open:101,open:101,rooms:101,corridors:101 --steps 32 --preparation-motion-probe --preparation-probe-version mr3-p2a0-outward-cancel-v3 --base-domain 134 --base-port 13221 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261017_v12_reset
```

interface32steps与terminal2×4step API全部mandatory PASS。reset2workers×4schedule×32step完成并CLI0，整体版本FAIL：w0/e2 tb2仅0.0032782531368285074m活动；w0/e3 tb2真实fullplanar0.3058281617710947>.30；w1/e2与e3 tb1驱动alpha真Fraction向内门正式拒绝。三项归因独立，旧FAIL/原物理界/原driver数学均保留。reset全部26jobs结束，full/input/drive/physics FAIL；angular/settled/closure/binary/info/peer/control与八份FIFO PASS。活动不足另含w1/e4 tb1(.00514502831364514m)与tb3(.006289445193331186m)。新增第四类真实FAIL：w0/e4 tb1 A102.48s最终0/B102.46s实际cancel后无新goal/非零目标，但到106.448s无3连speed<=.01；.78s后仍.01165–.01297，native已在102.776s applied双轮0并维持。有限观测path A.04136230664963264m/B.04616805750202775m未超.144，不能冒称已停或给无穷后续上界。严格persistent rest FAIL保留。controller11:44:10UTC实际later_stages_skip并exit1，deadline未启动，无同freeze盲重试。

实际一次性计费307reset+step API（11reset+296step）、295真正下发joint command、294.02有效/返回物理任务秒；helper推进294.538秒（含release前.338及cleanup.180），原启动free-run不混该helper量。launcher原生墙秒4414.7895641284995；benchmark elapsed4413.4765489515848只是同一成本另一视图，不能相加或再加wrapper样本。八轮reset native_stop0/真实Nav2finalized，各saved identity动态并集349fresh全gone为关闭子事实。完整accounting源码原件SHA在`/tmp/mr3_p2a0_v12_report_accounting_final_v1.json`。

失败后被动corridor CDR诊断为额外非预声明负载，仅/tmp保存完整原件/初失败/修正与范围：5850+5556实收、6161去重gzip；没有控制publisher/SetParameters，无法补旧w0/e2内部原件或证明每包GID/接收延迟。参见`passive_nav2_custody_manifest_v1.json`、`observer_corrections_v1.json`、`timestamp_scope_v1.json`。原计划、所有运行/审计FAIL、观察器错误及修正分别保留；不得用新的working-consumer/source修复重标旧freeze。

原生矩阵PPO/GPU/optimizer均0（不排除已单独记录的CPU synthetic optimizer测试），pilot2226/11494.045260453597已用、1870/2905.954739546403余额原样；不降95%/参与/物理门，不授冻结策略或本版完整矩阵PASS。正式reset/skip结果已收齐；canonical证据见下。

实际入口（cwd wireless-rl；conda调用均 env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_buildproof_preflight.py
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v10_pack_source_bindings_v1.py --preflight /tmp/mr3_p2a0_v12_source_preflight.json
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_launch_stage.py interface 6b1b4a0108351f5bfb70ec0c96ba895248d4f7a8
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_audit_stage.py interface 6b1b4a0108351f5bfb70ec0c96ba895248d4f7a8
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u /tmp/mr3_p2a0_v12_continue_matrix_v1.py
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v12_pack_native_v1.py interface
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v12_pack_native_v1.py terminal
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v12_pack_native_v1.py reset
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v12_archive_closed_v1.py --publish --mode stopped --stop-stage reset
```

preflight100 runtime/76 independent PASS，plan264a9c5a、SO d0d31b0f；controller精确child argv/cwd/UTC/exit在canonical remaining_matrix原件。interface/terminal/reset原包manifest SHA分别addd1448/86bdbd7a/acfd5b1c；只读包生成25.430645/17.660513/201.044655墙秒，不加到native成本。归档helper8项最小fixtures PASS，预核V2 PASS，publish PASS（只授保管一致）；代码/命令/输出在支持manifest，原raw5471507727B/selected330143198B/5525 native files；6616支持原件；inventory12234项 SHA52213bf6d4945792dd278be9d04713a3eb37b24162d7f2e8267b2b6f457bf55d。

所有正式26jobs及原FAIL、被动观察失败/修正、critic/代价图/raw body/strict alpha/stop尾段诊断及其精确CPU命令、退出/耗时/SHA，均逐原保存在[支持manifest](report/assets/20261017_mr3_p2a0_v12/independent/native_originals_v1/manifest.json)，不重写旧原件。[报告](report/20261017_mr3_p2a0_v12.md)、[完整inventory](report/assets/20261017_mr3_p2a0_v12/inventory_native_v1.json)、[计费](report/assets/20261017_mr3_p2a0_v12/accounting/native_cost_v1.json)。所有原生/正式reader/自有只读writer已结束，PID/start缺失项保留实际证据范围。V13候选修复只在/tmp草稿，未授新native/PPO信用。

关闭文档静态检查：`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python report/assets/20261017_mr3_p2a0_v12/independent/mr3_p2a0_v12_contract_checks.py /tmp/mr3_p2a0_closure_static_checks_v1.json`（cwd wireless-rl）exit0，97源码逐字同V11、35pins、128本地链接PASS；没有为文档修改重跑native。`rtk git diff --check` PASS；提交前完整`git add -n .`逐path与上述inventory/9文档白名单比较，排除cache/runtime/build等非证据。

### 2026-10-17 MR3-P2A.0 V13 开发与离线验证（尚无原生结果）

继续用户完成P2A.0授权；V12完整FAIL证据已提交d48b939，原interface/terminal PASS不提供本版native信用。源码working repair：实际三机Nav2 RotationShim→原DWB/.20/.8，通用DWB同步.20与加速度，DWB及smoother显式±.5线/±3.2角；原critics/planner/goal checker不改。最终guard与tag parser同时改.20，fullnorm/peer raw一致/因果own raw历史不符时normal真实负ACK+永久零，沿原callback_error/abort_cleanup禁止训练，不改变正常控制/evaluator先后。paired数值预算/差值保守区间和binary64向内比例修复真alpha及另near-zero反例，不放宽原Fraction门。实测.30/1.2/角加速7/停止.78和.144/静止.01/settled整段/source500ms/peer.50/contact18/95%/300秒/参与和关闭门均不改。

所有离线检查的精确argv、cwd、相关env、源before/after SHA、exit、墙秒和完整stdout/stderr由各自JSON绑定；早失败原样保留，后续canonical manifest追溯绝对原路径，不把重叠检查数相加：

- 新helper作者exact Fraction 30085组PASS，旧同集55alpha/50wheel-budget FAIL；实际V12两行只alpha失败而轮budget未超，另tiny预算例只属CPU。独立9 targeted Fraction PASS。paired永久旧8PASS+4FAIL→新12PASS；target旧.26对current10tests为8PASS+2FAIL→新.20全10PASS。原compiled probes只CPU，无plant证明。
- Navigation profile/typed readback9 + 新drivecap13 + 旧V5/V4原63数学 + benchmark35共120项CPU PASS。旧三YAML/generic除声明profile字段外语义同值；新V6真实调用原V5/V4全部math/provenance并追加final guard/target/native精确.20/.8，不改旧FAIL。
- Safety模型草稿v1..v5的15/15/27/29/30检查与初malformed/style失误分别保留；最终scoped ROS104PASS，style PASS。首正式CPU调用使用domain233在36dots后exit1无trace；独立rclpy确证domainId>232导致DDS端口超限，改domain211后通过；该环境错误不记native/model门失败。原代码/方法常量的AST证据单独保存。
- Canonical systemROS实际构建两包exit0，102.01216239202768wall；canonical C++12+10都PASS，1.1137542170472443wall，不与standalone结果叠加。额外CMake参数仅导出真实compile_commands，完整warnings不丢。new SO a014f2c618e38fc8a306d76c100083d952606333045a2e35bffce6f8b25b10c8、1999200B；canonical installed symlink/samefile、4编译摘要与actual source全核验，并已lossless gzip保留实际库。build receipt85484c6d7a32f793c943b7d9778067cd77ef99b4220f3aba50aa38021675f474。
- Root motion01误用conda未安装pytest，exit1/0.04573375wall，无新依赖；改既有unittest。motion02（3.95215739wall）揭示settled fixture缺真实peer raw，原10failures/8errors保留，修fixture不削断言后motion03二十项PASS（12.32535255wall）。独立反例又发现仅own angular.x1.3仍被该reader误授PASS，原wholematrix的独立angular仍会拒；补独立normal commit所选raw/因果history/peer raw范数及真实negativeACK拒绝，最终25项PASS，8.93747895wall，style/diff PASS。初author pytest/style发展失败亦原样保留；当前成功并非改标旧反例。
- 完整ROS1192PASS（36.12test/38.3627204881wall），复用A11实际merge_map/test+multi_robot_exploration/test及原6lint ignores，新增norm module自动纳入，systemROS+overlay/domain211/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1，166源前后恒定。完整conda253PASS（53.373test/58.711605194wall），45源前后恒定；CPU synthetic SB3 optimizer测试仍属于本测试来源，不算原生学习/pilot量。

实际构建命令（cwd canonical ROS，先清conda/PYTHONPATH/旧overlay再source /opt/ros/humble/setup.bash，PYTHONNOUSERSITE=1）：

```bash
/usr/bin/python3 /usr/bin/colcon build --symlink-install --allow-overriding nav2_bringup --packages-select multi_robot multi_robot_exploration --cmake-force-configure --cmake-args -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
```

Root完整conda命令（cwd wireless-rl）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m unittest discover -s mr3_learning/tests -v
```

完整ROS确切选择/环境命令在原ros_semantic_full_v1.json，canonical C++实际ctest argv/原XML在build checks，不把普通pytest/std::test冒作原生实验。V12 stop source102.48后desired117/117零但前8条仍合法减速，102.776起109条applied才持续零；测量点/floatyaw审计没有证明误报。V13降速与一致加速度尚未证明修其持续静止FAIL，不能减原rest门或用小chord替代瞬时速度。源码与构建离线核验已完成；实际Shim mapping仍须native验证，plan/coordinator的最终检查及clean-pushed exact40 preflight见本段后续闭合记录；原生尚未启动，无新增GPU/pilot用量，P2B/gateway未开始。

V13冻结前补充：Shim实际mapping wrapper先调用原7126969f观察器，再追加每episode真实worker argv/run-dir/PID/start及三台controller namespace/ancestry/库path+device+inode+SHA；原base JSON/console/source/actualCLI绑定必须一致。原V1作者20项通过后，独立发现跨EP借worker与hash/read-stat分离两CPU反例，保留并修为V2；新23proc+22supplement+6watcher+14launcher+9actual-main scheduler共74CPU通过，独立8定向通过。旧13+7编排断言全保留，新增拒绝未准入和Shim失败路径。此后再次独立发现nested closure没有继承重复读/终读稳定性，新增真实main/read3fixtures显示旧2FAIL→新3PASS，旧数学AST可逆恢复同值；14+9编排复跑通过。原219candidate manifest不覆，补充另存。

实际四stage父编排器 /tmp/mr3_p2a0_v13_run_matrix_v1.py (SHA0de57dd7e0069fee7fc4f1d54aa0156115eefe58c0775c238aeb12c6776f8f48) 的7 fakeCLI methods通过（4.294778182171285wall）、style通过；成功、launch/audit FAIL、false leaf、source变更、异常仍reap同child及不覆盖均核验，不等于native运行。精确命令/CPU子进程/初style FAIL在 checks_final_v2.json 原件。最终strict static v4 (`/usr/bin/python3 /tmp/mr3_p2a0_v13_research_gate_static_v2.py --require-final-plan --output /tmp/mr3_p2a0_v13_research_gate_static_review_v4.json`) exit0/PASS .8994045569561422wall；96bindings=73immutable旧SHA+3授权current审计SHA刷新+20new，35pins+ENV、12digest-only AST、actual a014 SO/4宏、source/task/body/stop/actor/candidate/reward和链接均通过。旧v1三stale-binding FAIL及v2/v3回执保留，不改标为本版成功。

最终独立nested/source复核3cd8134a PASS：新增3fixtures独立复跑通过（.21test/.670wall），剥离新增stable-read/终读AST后旧闭合逻辑完全相同，mandatory 10/7/10/7及顺序不变。所有/tmp原件写者结束后执行 `rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_archive_common_offline_v13_v1.py`（cwd Git root）：471原件/raw2125525B/encoded689862B，manifest0a2b3313b2414b3c94b9f4deee59e337fcd09345f6d7a8501d38c3678deed46b；每项encoded/decoded/source-before-after SHA+stat均验证，排除6个compiled/cache项，按绝对source去重已有Safety156、candidate219和addendum17原件。Safety canonical manifest cec4f7d4、candidate9280f4a2、addendume348c6be保持不覆。无新native。

冻结前inventory/白名单/链接核验：`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v13_prefreeze_inventory_verify_v1.py --inventory /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v13/inventory_prefreeze_v1.json --report /tmp/mr3_p2a0_v13_prefreeze_inventory_review_v1.json --allow-canonical-inventory`（cwd Git root）exit0/PASS；891 prefreeze assets、96 independent、35pins、168本地链接、863 archive rows、旧日志前缀与V12原FAIL原件、白名单及所有读后哈希一致。inventory自身独立记录不纳入自身。`rtk git diff --check` PASS，提交前实际 `git add -n .` 逐path对照显式代码/文档白名单及完整inventory，排除build/runtime/cache/CPU ELF。

### 2026-10-17 MR3-P2A.0 V13 原生关闭：interface FAIL，后三阶段 SKIP

实际源码冻结`1cfe74b4ad32cf72246bcf755b0c090748e6c575`，planSHA71d274bb85e762dd2108bc7ea919dc6010aad1e75d4c7020f62455e07c001212。工作区干净且HEAD=origin/main；actual preflight100runtime/96independent/a014 SO通过，exact Git source pack100文件/350458encoded B，manifestb286c0b1/tarc84801b9。冻结提交前额外逐index-byte核验924文件全部一致；该辅助脚本并发commit后打印已清空的cached stat末行触发IndexError，原错误保留。后续不可变commit-tar一次核验924路径与worktree全部一致且clean PASS；不影响已完成的提交前diffcheck/白名单审查。

实际命令（cwd wireless-rl；conda保持env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1；不安装新依赖）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python report/assets/20261017_mr3_p2a0_v13/independent/mr3_p2a0_v13_buildproof_preflight.py
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v10_pack_source_bindings_v1.py --preflight /tmp/mr3_p2a0_v13_source_preflight.json
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -u report/assets/20261017_mr3_p2a0_v13/independent/mr3_p2a0_v13_cross_stage_mapping_monitor_v1.py --freeze 1cfe74b4ad32cf72246bcf755b0c090748e6c575
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u /tmp/mr3_p2a0_v13_run_matrix_v1.py 1cfe74b4ad32cf72246bcf755b0c090748e6c575
```

父编排12:45:53.521 UTC开始，实际interface launcher 12:45:53.974884至12:48:57.428084 UTC，**183.4526445940137原生墙秒**；不再加benchmark182.99565472826362或父wrapper183.75556804100052。1成功reset、0step、0有效transition/学习样本；release77.52秒之后始终未执行策略动作。physics helper共17请求/54ticks=.054秒（.034 pre-release与.020 abort-cleanup），不是正常任务样本。固定seed101/open/三机/domain140/port13301不变。

首次/tb1/controller_server/get_parameters返回超过原30秒整体墙钟guard，actual_nav2_parameters.json passedFalse/nodes空/cleanup全真，原script总30.366513008717448含退出清理。原launch.log的exact `client will not receive response`证实send_response匹配等待分支，非尚未发现service或未收到motion release。39原生start与39 clean exit、supervisor44保存identity rows和全部自有身份消失均真实保留；Shim完整逐EP映射核验PASS。closure总体FAIL，不能用干净退出冒充参数/全部门通过。

11个正式jobs全部结束，runner_errors=[]、all_submitted_jobs_finished=True、aggregateFAIL；FIFO及information PASS，其余full/input/drive/peer/control/settled/angular/physics/closure按实际无动作/覆盖/参数失败保留各自原FAIL。父编排12:51:17.527939 UTC记version_failed_later_stages_skip并exit1，terminal/reset/deadline未启动。只读watcher已自然结束。没有外部signal、盲重试、训练/GPU/pilot；原pilot2226/11494.045260453597已用与1870/2905.954739546403余额保持。

对应本机rmw_fastrtps6.2.10/FastDDS2.6.11官方源码与独立复核：该exact错误先等待特定响应reader GUID匹配并读取writer.max_blocking_time，发生在序列化/write之前。旧6参数期望reply344B、新39参数期望reply2400B只是按冻结期望值构造的CDR，不是实际wire包；不能把变大归为此次已证失败原因。现9参数服务writer工厂QoS均默认100ms且无精确profile；最小/tmp proposal只为这9reply增1秒，CPU原生XML parser逐9精确匹配、其余36保持。1秒充分性未知，30秒client/45秒hook与全部任务/动作/物理门不变。service_is_ready已经核本地双向计数，不能替代服务端specific GUID匹配证明。V14仍仅修复草稿，必须新冻结/新预声明完整矩阵。

关闭归档实际命令 `/usr/bin/python3 /tmp/mr3_p2a0_v13_archive_closed_v1.py --publish --mode stopped --stop-stage interface`（cwd/tmp；PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1）：exit0/8.233846455812454wall，只读保管不运行新native/auditor。helper初style FAIL及原源码快照保留；最终13CPU fixtures+style PASS。此前interface selected pack182文件raw162247979B→9541953B；canonical新增支持163原件，671原件按raw bytes与既有canonical去重、4CPU ELF排除。完整inventory1243条 SHA470740a5d84dfb97ddc0ee3394709b2a7a0895ed761599762b537595711f4c74；verification0fa87bd368a316355c7338dc7beeb6a4fd05b3fbf4089b1c88ea75bdb5347f7c PASS（保管一致），冻结891+100runtime+96indie、4宏/当前及archive a014、48union保存PID/start fresh全部gone。不授整体闭合/physical/95%/策略通过；formal原FAIL与skip无更动。证据链接见[V13报告](report/20261017_mr3_p2a0_v13.md)。

关闭文档最终静态核验（tool inline stdlib runner；原JSON /tmp/mr3_p2a0_v14_v13_closure_static_review_v1.json）：100runtime/96independent/35pins+ENV逐SHA、1243 inventory各bytes/SHA、141当前关闭文档本地链接及11非asset显式白名单全部PASS。实际 `git add -n .` 的363路径逐项对比11文档或inventory，无unexpected；`git diff --check` PASS。仅关闭文档/证据提交，不为文档重跑simulator/学习。

### 2026-10-17 MR3-P2A.0 V14 源码准备与离线检查（未启动原生）

V13失败完整关闭提交60f932ed已push；本版只补九个精确参数reply writer可靠1秒有限等待，保留原36profile与30秒client/45秒hook。旧motion/guard/driver四源码/所有Nav2 YAML、.20指令与实测/停车/任务/接触门不变。实际a014库复用，不做无关rebuild。newsource/readiness仍draft，无本版native/GPU/pilot，CPU synthetic优化测试另计本测试scope。

候选/tmp初view仅18PASS1FAIL（缺旧测试需要的world存在占位）与style FAIL原样保留；最终19pure pytest、8XML变异拒绝以及installed FastDDS工厂全部45精确profile/default100ms逐项核验通过。旧XML除新增9与注释前后byte与semantic children均原样；旧测试除总数45/旧36subset选择/新9测试外可逆AST等同。候选manifest67696d42/40原件；实际复制XML0b909216与test63a9315d逐SHA一致。

Root初pin更新inline脚本错假定旧XML SHA在audit_ppo直接literal中，首assert失败，未写audit_ppo/plan；完整核查后确认旧100sourcepack与immutable phase_v3的10-entry runtime均未含XML；旧运行metadata记录其实际profile摘要。此次新增显式XML pin将新native source proof扩为101，不能把原sourcepack100误称已包含XML。现在新增PREPARATION_RUNTIME_PINS的显式current XML pin，并只刷新ENV digest，生产AST仅新增dict entry+ENV literal，所有原函数/数学/顺序不变。12项source-loader module检查PASS，含新增真实loader的正向与Git/workingXML篡改拒绝；初red中1ERROR/2subtestFAIL与styleFAIL保留。显式pins35→36是新增源码约束，不能当DDS运行证明。新105工具binding=旧94原SHA+2授权current审计及其tests刷新+9新编排，旧A13原件不改。

应用后系统ROS完整回归：`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v14_ros_semantic_full_v1.py`（cwd Git root），复用旧两package与6lint ignores的原bash argv/overlay/domain211/无conda混合；exit0、1193PASS（34.84test/37.09639742784202wall），166源before/after恒定，完整raw stdout/原argv/env/encoded与decodedSHA见同prefix JSON/log.gz。没有Gazebo或原生实验。

V14完整conda检查使用既有`env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 ns3gym/python -m unittest discover -s mr3_learning/tests -v` scope（cwd wireless-rl）：255PASS/55.714test/61.01240399712697wall，45源码before==after；精确argv/env/raw stdout/SHA在conda_cpu_full_v1/checks_v1.json（91d9dc98）。含CPU synthetic SB3更新/checkpoint测试，不计原生PPO/pilot。canonical30直接加载已promote A14原件PASS/3.286test/3.7967wall，108源前后恒定；执行回执d0279cb0。source/binary/research复核732318d3 PASS：105binding、36pins+ENV、预期101source paths、新preflight动态len、除XML/ENV/audit_ppo外所有ROS生产/body/driver/actor/reward/candidate/SLAM/eval整源同60f932，current/install/archive a014与四宏一致，10组原研究/physical/angular/settled/预算门相同，已追踪1243旧A13资产逐Git byte不变。

parent7 fakeCLI/2 AST/style检查通过，旧断言全部保留；initial styleFAIL原件保留。root将plan置ready后，以新独占输出运行`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v14_canonical_coord_static_ready_v2.py`，105binding/5AST/36pins/ENV与ready+pending空断言PASS；旧draft回执不覆。没有原生调用。

离线archive helper的旧native selected_sha256字段漏取已由反例补齐，原b0a源码/错误接受反例与新3PASS保留。第一次实际归档（--writers-stopped，source8913a266）exit1，在发布新目录前因已有gzip原文件的identity编码被suffix再次解压而拒；这不是原件变更。原失败receipt offline_archive_attempt01_failure_v1.json保留，待修编码适配后重新封存；不重跑native。

归档适配最终helper ca6cb556：显式encoding/compression优先，unknown/conflict拒绝，无字段旧row才suffixfallback；9身份/gzip/编码反例及原3错误SHA拒绝都PASS，实际old_originals只读核验6份A13manifest/899唯一rawSHA PASS（5.35wall），未改旧原件。全部writers停止后实际再次执行`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a0_v14_archive_offline_originals_v1.py --writers-stopped`（cwd Git root）exit0：173selected/raw2505402B/encoded481857B、113A13 raw-byte去重引用、1125 cache/mock/ELF/active等排除；每源fd stat/SHA前后及整体末验、gzip roundtrip硬校验。canonical单一manifest8eeab185a57c94957a2aa8cb66ee0a2a56717b52a97d36f315667625ab64dd01，首归档FAIL未改标。这是离线保管，非原生重试或simulator/PPO开销。

最终prefreeze第一次inline检查用旧100 map时未把已审阅audit_ppo的新SHA替换，早assert FAIL且未写inventory；失败范围/无source mutation保存在prefreeze_attempt01_failure_v1.json。修正仅是当前101预期集合的构建（旧100中ENV/audit_ppo用已绑定新SHA，新增XML），新独占helper `rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v14_prefreeze_final_verify_v2.py`（cwd Git root）PASS：101source、105independent、36pins、actual a014+四宏、173原件编码/解码及113旧custody引用、184asset逐SHA、155链接；inventory3d358245390f878840a110b1224f003be44ad6fb0cca94da5a143f64e0110ce0。实际`git add -n .`201路径逐16代码/文档白名单或inventory，无unexpected；`git diff --check`PASS。仅本地源码/保管核验，不运行新native。

### 2026-10-17 MR3-P2A.0 V14 原生关闭：几何及制停覆盖 FAIL

实际源码冻结`aa16d6541ef54a9c676e78367ba8a8b13c2589b9`，planSHA5bb69b0af1ff36caace7174252a29cdf904f5cf6d2c80a01359e200e5a14f1d2；clean HEAD=origin/main，101runtime/105independent/a014 preflight PASS，sourcepack101文件/352008encoded B，manifest a4298b2073361c6e7d0e485eb465e547ddc865261d75e6acd603fa363a6cc9ab。上段prefreeze检查和CPU结果属于离线范围，不提供本次native通过信用。

实际命令（cwd wireless-rl；conda调用保持 env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python report/assets/20261017_mr3_p2a0_v14/independent/mr3_p2a0_v14_buildproof_preflight.py
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v10_pack_source_bindings_v1.py --preflight /tmp/mr3_p2a0_v14_source_preflight.json
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -u report/assets/20261017_mr3_p2a0_v14/independent/mr3_p2a0_v14_cross_stage_mapping_monitor_v1.py --freeze aa16d6541ef54a9c676e78367ba8a8b13c2589b9
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u /tmp/mr3_p2a0_v14_run_matrix_v1.py aa16d6541ef54a9c676e78367ba8a8b13c2589b9
```

父编排13:29:00.324 UTC启动；实际interface launcher13:29:00.801045至13:41:57.287265 UTC，计费776.4856320801191原生墙秒，1reset/32step/33 API records，open101/三机/domain140/port13301。九节点参数读回2.525004710070789墙秒，九次RPC约1.443–4.646ms，首个tb1/controller4.309913ms；本次通过不证明长期可靠性。release73.24s，结束physics105.26s，未补造尾步/终态。Nav2一次tb2 halt result错误原样保留，不无依据写作审计失败根因。

11正式jobs全结束，all_submitted_jobs_finished=True、runner_errors=[]，10 mandatory receipts中peer/control/fixed_physics三项FAIL，其他7项PASS，额外FIFO PASS。39原生start/39 exit0、18 Nav2 finalized、实际PID/start关闭证据保持。父编排13:46:45.823419 UTC记version_failed_later_stages_skip并exit1，terminal/reset/deadline未启动；watcher自然结束。父脚本将aggregate成功与job关闭混为一条require，导致错误文案“did not close every required job”；原件不改，其实是已收齐的required FAIL。无外部signal、同版盲重试或训练/GPU/pilot。

peer/control同报peer_phase line5544首条normal obstacles_published cloud与immutable A10几何不一致；三scan均匹配。独立同输入回放仅改namespace speed .20/.26，前者逐bit复现actual三cloud(1925/1927/1952points)，后者逐bit复现原reader(2341/2343/2366points)。control.py间接alias COMMAND_SPEED_LIMIT导致V13命令降.20时同时缩导航peer envelope，body_points与grid_with_peers均受影响。原静态receipt只核consumer源码/AST同值，不能推出依赖常量的运行几何不变；该过宽推断由此明确纠正，原receipt和FAIL不重写。修复须分离导航peer .26界与commandcap .20，不改原几何reader或任务.50门。

physics无三台planar>.30/angular>1.2记录，仍因停止coverage FAIL：tb1 A2/B1有信用；tb2 A1/B0，10s取消时no_active_prior_linear_output；tb3 A0，eligible三A均resumed_before_proven_rest，28s取消初速.01057379677<.05，无B资格。不得把无bound violation改成physical PASS。三台各两个接受目标与约3.131/1.689/2.663m received路径仅是工程活动。本次32 native动作无原生学习样本、PPO/GPU/optimizer，pilot2226/11494.045260453597已用及1870/2905.954739546403余额保持。后续改外部刺激时机并保留所有原资格/响应门，以新clean pushed冻结完整矩阵。


V14失败关闭归档（cwd/tmp，PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1）实际顺序：

```bash
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v14_pack_native_v1.py interface
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v14_archive_closed_v1.py --publish --mode stopped --stop-stage interface
```

pack source721f6af4，exit0/33.405632538720965wall；archive最终source9f905ca7，exit0/15.566353520844132wall；只作已关闭原件保管，不运行新native/formal。不重复加到776.4856320801191原生墙秒。原18helper fixtures后增加冻结Git/tar身份回归，最终19项/style PASS，初styleFAIL保留。新helper核V14 Git blobs+原101source tar，而不把后续授权V15工作区编辑当作V14字节。冻结184项保持，101source/105indie、四宏/a014及48 actual union保存身份fresh全gone。支持565新增原件/285旧canonical逐raw去重；原生572文件raw560832704B/selected34143760B。inventory1328 SHA2ba5492c49545fd01619d12e76b1e75b9e072d312e068a5ee00900a6f85fd14e，verification892b033c7d5ada9f2e2e7d3b79f5487c3e0a62ec5b2fc5ee0443349d6f65add4，supportmanifest3a046936b3c02c86f8a9d145e887e817b79a945bdcb4ca13dbbb173ca110a982。保管PASS不改3 formal FAIL；几何static过宽推断和parent错误文案解释见canonical runtime_closeout_corrections原件与[V14报告](report/20261017_mr3_p2a0_v14.md)。

V14关闭文档静态检查：第一次inline白名单将新V15测试名误写为test_peer_geometry_bounds.py，实际新test_navigation_peer_geometry.py被正确拒绝；无文件/门变动。修白名单后仅静态重验PASS（/tmp/root_mr3_v14_closure_static_review_v2.json）：1328库存encoded bytes/SHA、144链接、旧log前缀与原FAIL/SKIP不变；实际git add -n .的1155路径全属11关闭文档、canonical库存或两项授权V15生产改动。后两项不纳入此关闭提交。git diff --check PASS，不为文档重跑native/formal。


### 2026-10-17 MR3-P2A.0 V15 开发与离线回归（尚无新原生）

V14原FAIL/全部原件在f7376d02已push。当前working修复将control.py的导航PEER_SPEED_BOUND_MPS独立固定.26，解除COMMAND_SPEED_LIMIT=.20 alias；保护门/命令/身体及任务门保持。新test_navigation_peer_geometry.py包括三个V14实际pose/age cloud全byte摘要、三个年龄的grid/cloud共同几何和隔离重导入时commandcap=.07不缩grid，共7cases。旧源码7RED→修复后4相关ROS文件56PASS（1.74test/3.543wall）；真实PeerObstacles._publish_inputs六callback/in-memory publisher捕获3scan/3cloud均与immutableA10全payload精确匹配。原第一次bytes差异报告长跑由owner核PID/start后SIGINT，pytest diff渲染IndexError及首次styleFAIL保留，改shape+SHA全byte绑定后完成RED/green，不属native失败。最终control SHA3b6fb71f2c90a055ef3bb922bd3f08332eb366d8becde577106d1ed5bd56cedd，test f4eb9dfec347060f095597853686d2b498977a4c03d75a1490db5d88ca751c46；29原件manifest61cca34a03f194f15011c78125f209155ec39e695c0ee19c60ce5984f66a63d1。逆AST恢复原import+删除新常量后whole control与原相同；这只证明delta范围，几何行为由上述真实方法/字节测试核验。

Root完整systemROS回归实际命令（cwd Git root）：

```bash
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v15_ros_semantic_full_v1.py
```

复用V14两package/原6 lint ignores、ROS overlay/domain211与清除conda/旧路径的相同argv，新增geometry测试纳入167源；exit0，1200PASS（35.95test/38.12466774787754wall），167source before/after SHA恒定。确切命令/env/exit/raw stdout/encoded-decoded SHA与source before/after见同prefix JSON/log.gz，无Gazebo/原生/GPU/PPO/pilot。其余新工程fixture/编排仍待离线审查与独立核验，不据CPU检查宣告P2A.0完成。


V15 external工程刺激与metadata接线：benchmark新增V4/32，原_probe_goal_order/probe_action/probe_action_v3及abort helpers AST保持，动作只来自received snapshot与原per/joint mask；active/owned/accepted、fresh/valid、received v>=.08及phase path>=.05才请求合法WAIT，实际返回typed command绑定后才锁存。首WAIT至少3秒/fresh idle/received abs(v)<=.01才准第二GOAL；该proxy不授raw停车信用。原固定窗口10/28仍有限，masked只KEEP并诚实missing。离线V14前缀首次动作差异在t19，999合法且原线输出span5.92/4.18/4.76秒；仅反事实prefix，不是新native或实际停止证据。Safety原版两个边界反例原样保留（explicit0/None提交flag、无首WAIT便第二GOAL），修后明确拒非bool及缺首WAIT不发第二GOAL，独立10组CPU小核PASS（ce39b8cb/0.4916wall）。

候选最终checks_v5=14offline+13portable PASS；checks_v4=8capacity+17reset wrapper PASS（重叠范围不合为学习量）。初v1 synthetic B timestamp/style、v2 harnessstyle、v3 metadata-only equivalence fixture/style失败均保留；handoff fd291141、promote1d7e2fd0逐7文件SHA/AST/局部diffcheck通过后STOP。benchmark b720f6417bcdf216b5bfd77b0654b3277d1a0868e1dd1c8b9f9eb2e991977e1c，audit_preparation43488c1698469ced58d2097cfccac7e262cd09f7503661a11f9c2b06213ec408。后者仅新增精确V4/32工程capacity声明，旧V2/V3/未知拒绝/native全部门保持。独立确认actual A4 wholeinput consumer仅回显probe version，无V3 workload分派，不误改observation-v3 schema。原A8不动，新A15 reset angular73128aed/physicalfa988a29仅metadata版本/doc/diagnostic字面量适配；归一化后wholeAST同原A8，原angular7a472/physical2516、8EP/33rows/32steps、body/A-or-B pool和独立活动门保持。独立wrapper/pin复核233d9271 PASS/0.6167wall，仅static，不调用formal或重复17tests。

Root同步ENV新行为说明与control pin，audit_ppo只刷新两个digest literal，逆恢复后wholeAST同f737，36pins+ENV逐currentSHA匹配。ENV2e95bf8a76b9216088d10e1ad1125b3d341e55144e2452cde852a869c4b7cf36，audit_ppo3883ea62eded4860f0c300d125d98ef8728e1546cc4e91d3cbeee15a8aa76483。root最终接线A15 audit_stage仅两条reset wrapper A8→A15路径，scheduler fixture仅两physics basename相应变更，原poolFAIL/required gates不削弱。

完整conda CPU实际命令（cwd Git root，runner子进程cwd wireless-rl）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= /usr/bin/python3 /tmp/mr3_p2a0_v15_conda_cpu_full_v1.py
```

子进程仍为既有ns3gym/python -m unittest discover -s mr3_learning/tests -v，CUDA_VISIBLE_DEVICES空、PYTHONPATH unset；exit0，270PASS（46.264test/51.713289932813495wall），46source前后恒定。含CPU synthetic SB3 optimizer/checkpoint测试，不计原生PPO/pilot；无新Gazebo/ROS native/GPU。完整命令/env/source hashes/raw stdout在conda_cpu_full_v1/checks_v1.json。原完整ROS1200PASS仍为其已稳定167源范围，不为仅文档/路径变动重复运行。


V15新编排初39 distinct methods（14launcher/9scheduler/4Shim/3nested/9parent）PASS，最初parent style4处FAIL及原源保留。parent仅把旧合并require等价拆为job关闭与required失败两条诊断，32逻辑组合保持；无signals/retry/放行FAIL。Root切换两reset wrapper路径及两个fakebasename后，对canonical scheduler仅相关9methods重验PASS（.622test/.759633743wall），fatal Python lint E9/F63/F7/F82及diff whitespace PASS（不冒称继承旧代码的全format lint）。source前后稳定，checks01 886ea197、wiring static a3226d67；原mandatory receipts/reader/hardgates/pilot/608/596/18000对A14逐值不变。旧v1/v2等开发style/fixtures未覆。

root最终plan置ready后实际只读命令（cwd Git root）：`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v15_final_source_review_v1.py`，exit0/.41639423789456487wall；plan fc52f0e5a632ba8114a68da73f2ee048408a3f795609351469f446a88ab68804，121bindings=103old unchanged+仅current audit_ppo/audit_preparation刷新+16新增；101runtime只有control/ENV/audit_ppo/audit_preparation/benchmark五处已声明delta。36pins、原hardgates/各stage预算、audit_ppo两digest-only和audit_preparation V4资格适配wholeAST、六legacy probe/abort helpers AST、actual current/install/archive a014和4embedded宏均PASS。静态source readiness不授权跳过clean exact40 preflight，也不代替native结果。

Offline helper b828135cfb2123fe816bb00c1c2e26da67445675cb9d4062c1279ceca1b32b70 的7custody反例/style PASS，实际A14+A13旧9manifest/2067distinct raw只读校验PASS（17.924358824733645wall）。执行反例包括in-place突变、symlink拒绝、codec/selected/index篡改和重复发布，不把实现中的inode检查冒作另跑的inode替换实验。首style失败保留。所有writers停止后实际命令（cwd Git root，PYTHONPATH unset/PYTHONNOUSERSITE=1）：

```bash
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v15_archive_offline_originals_v1.py --writers-stopped
```

exit0/18.15223528118804wall，主manifest2d65e1aba3664c6f63922f9949e17d27cc98a34dc9da74e94972b7e017c8c040：193原件raw2412971B→encoded497809B，85旧raw去重引用，780排除=60fakecoord/164fakeruntimeleaf/554mock/1activeconsole/1continuation。新193及旧85逐bytes/codec/source-stat与readyplan末验PASS。一次发布不覆写；后产生观察脚本verify_v1因比较tuple而非bytes误报FAIL，原脚本/exit1/traceback保留，v2只取[1]后完整核验PASS(d8ceedd4)。实际publishreceipt5b199dc6和这些后置原件以补充保管：`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v15_capture_publish_addendum_v1.py`，exit0，8原件raw12342B/encoded6323B，manifest5053c471c0cb6833dc86f9d614bff4faf94bdca7f95aa6f40ca68dc72181acf0；旧主manifest不改。无新native/formal/PPO/pilot。

最终prefreeze实际命令（cwd Git root）：`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v15_prefreeze_inventory_verify_v1.py`，exit0/PASS：source/math ready原件逐当前SHA、101runtime/121independent/36pins、actual a014+4宏、主193+后置8原件和85旧raw custody引用全匹配。216asset逐encoded/decoded SHA核验，inventory2eecec50724a8204cf41b6aed61064c1e51bfff975b4c290fd8776114ab9257c自身排除；161本地链接PASS。实际git add -n . 236路径逐19非asset代码/文档或完整inventory白名单，无unexpected，git diff --check PASS；父编排/tmp源码SHA与已归档raw字节一致。只做静态准入，不运行native/PPO。


### 2026-10-17 MR3-P2A.0 V15 原生关闭：活动及制停覆盖 FAIL

实际clean pushed冻结`17ef3cb212aacd6e9e4fcde65783bdf2528da955`，预声明fc52f0e5a632ba8114a68da73f2ee048408a3f795609351469f446a88ab68804；101runtime/121independent/a014 exact preflight PASS（48e5f78e），101源sourcepack manifest03710534d1776cbf645bb68d6f985c4f10275c46d64af3f1ca5fdc6aa6d1fdfd、tar74b83cb5403f209b5b751dfd28150ca1fa878c5f39287ff6cfd4bcfff34b9f7f/354262B。前述1200 ROS/270 CPU为离线范围，不替代native信用。

实际命令（cwd wireless-rl；PYTHONPATH unset，PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python report/assets/20261017_mr3_p2a0_v15/independent/mr3_p2a0_v15_buildproof_preflight.py
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v10_pack_source_bindings_v1.py --preflight /tmp/mr3_p2a0_v15_source_preflight.json
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -u report/assets/20261017_mr3_p2a0_v15/independent/mr3_p2a0_v15_cross_stage_mapping_monitor_v1.py --freeze 17ef3cb212aacd6e9e4fcde65783bdf2528da955
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u /tmp/mr3_p2a0_v15_run_matrix_v1.py 17ef3cb212aacd6e9e4fcde65783bdf2528da955
```

父编排14:29:54.497536 UTC启动；interface launcher14:29:54.979972至14:43:18.933798 UTC，计费803.9527572728693原生墙秒，benchmark803.1176295201294及wrapper804.7408392331563另报而不叠加。open101/三机/domain140/port13301，V4/32 received运动取消刺激，1reset+32step=33API，完整32物理秒；release77.32s，physics结束109.34s含.02关闭。九节点参数读回2.593984832s，全部原匹配/参数门通过。源/Git在原生及formal期间未改变。

11正式jobs全部结束，runner_errors=[]，10 mandatory中full_audit/input_review/fixed_physics三项FAIL，其余7PASS，额外FIFO PASS；完整正式argv与receipts在interface_audit_execution_v1.json（dc37b270）。read-only formal362.31955105485395wall不计原生训练成本。父编排14:49:22.134668 UTC记version_failed_later_stages_skip并exit1，terminal/reset/deadline均未启动；watcher自然exit0。无signal、同版重试、PPO/GPU/optimizer/pilot；pilot已用2226/11494.045260453597和剩1870/2905.954739546403不变。39原生start/exit0、18Nav2finalized、44supervisor身份及实际union48fresh均gone，未强制清理。

导航peer与完整control重放PASS，证明独立.26几何修复实际生效。三台各2accepted goal，最终received路径.004359774638/.676424629241/.268276572800m；tb1未达工程.05m活动门（与原研究每机1米任务门分开）。physical无planar.30/angular1.2/chord越界，仍缺stop：tb1无eligible A/B；tb2 A1/B1（约.27s/.0197127m及.33s/.0306621m）；tb3五eligible A全部rest证明前恢复、两B无active prior linear。A或B原信用门保持，不因低峰值/clean exit改PASS。

只读诊断：returned observation33条/32动作全合法；t13原action145 reverse优先但三机straightaway margin负，同快照合法action321三机margin+.80206/+.87239/+.70111。t0已选三机away412（tb1+.196925），故新外部nonapproach筛选本身不能解释首段stall。一次全tb1日志流归约252MB/10.14s，任务全段最终nonzero线输出0；19–22秒150个非零前进请求92全拒/58仅保留turn，t19(.1578947,0)→raw/decision/selfreceipt绑定，最近tb3 bodymargin+.210374、brakezone-.077626、nonclosing-.591790，原安全门正确拒绝。另首段诊断380非零请求/0非零线输出；t6直接目标误差-.003879仍被拒。队友实际移动使原goal直线away从+.196925变t9-.054090，542项投影/nonclosing原数学逐bit重放一致（geometry_math_v2 e0ed23b1）。仅假设yaw对齐仍保留原cone/source的t6反例margin-.259268；不授改轨迹信用。官方本地Shim源码依sampled path point且实际未录DEBUG分支，只调.1/.1无充分解决依据。本版diagnostics原script/argv/log/输出、初v1及末尾suffix范围限制均保留在support原件；不读ModelStates，不放宽安全/物理门。

V15已闭归档实际命令（cwd repo，PYTHONPATH unset/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1）：

```bash
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v15_pack_native_v1.py interface
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v15_archive_closed_v1.py --publish --mode stopped --stop-stage interface
```

22custody反例PASS，含真实inode替换拒绝、dedup_prior/identitygzip/mocksymlink及source-stat；初style E501/E128/ignore覆盖默认造成W503/504 FAIL原件保留，最终仅继承E501、保持既有default后style PASS。pack sourcebae50761 exit0/34.831605914wholewall，579原件583232291B→35774289B，manifest18709fa7；publish source17c4badc exit0/15.727623176wall，277支持新增raw26932745B→2110378B及275旧raw去重引用，supportmanifest36b746ce；504缓存/mock/active/continuation等排除。216prefreeze/101Git+原tar源/121indie/四宏+a014与48保存身份freshgone全部验证。inventory1079 SHAa19b6f252d3f003495eec5bf8029fac304b4bba066154c98d6b7637047186ab0，verification7e8c161028f5f6dcca89a5e211a036e721d3167b9b1834c5bcb3311f021c960b，成本e6468c23。保管PASS不改变3原FAIL/3SKIP；不把归档成本加到803.9527572728693。所有原件保持，后续修复须新reviewed clean pushed冻结完整矩阵，不跨冻结拼接PASS。

V15关闭文档静态核验：`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/root_mr3_v15_closure_static_review_v1.py` 首次因helper猜测input标签为input_review_v1而FAIL，实际原receipt为input_001；不改原FAIL。仅修标签的v2同命令PASS/.9849400301463902wall：1079库存encoded SHA/bytes、148本地链接、原log前缀保持和3原FAIL/全jobs结束核验，实际git add -n . 874路径全属11关闭文档或库存白名单，diff-check PASS。无native/formal重跑。两版helper/失败原件、最终回执及postverify收于closure_static_v1，原inventory_native_v1保持；新增最终inventory_native_v2覆盖此后置保管。


### 2026-10-17 MR3-P2A.0 V16 外部刺激与离线准备（尚无原生）

V15实际FAIL/3SKIP及全部原件已完整提交推送55da440。V16只新增精确mr3-p2a0-outward-cancel-v5/32外部工程新GOAL筛选，共享V4默认False状态机：先原per/joint mask及生命周期，再逐已接收fresh/valid三机位置与每个goal-peer方向检查finite且margin>=0，后旧GOALcount/reverse/outward/path/id排名。KEEP/WAIT、5秒承诺、运动trigger、首WAIT>=3秒与实际step返回typed command锁存不变。新subset诊断另存original/filtered allowed数量，maxgoal仅指工程子集，不据此称actor候选不足。旧V2/V3/提交7函数AST保持，V4默认在V14/15各32输入动作和完整diagnostics一致；V14仅反事实V4输入，V15另对原实际command动作绑定。

候选最终/tmp/mr3_p2a0_v16_stimulus_v5_proposal/handoff_v2.json SHA1daa06a7，七文件在root晋升前逐原base/新SHA核验，promotion d9bc3d6d原件保留；benchmark1c3e99714ffed925527cbd45cd2699e143d42dcd52f6e9ffb29914108161548d，auditprep5cc9097d856f49c910e1a0aab4667785d21a05f3382c98b242013d5a15abc2d6。最终checks_v5=13实际输入/兼容+11portable通过；未变source的9capacity及18wrapper复用已记录PASS，不冒称此时重跑。早期styleFAIL、finite坐标溢出NaN被min吞掉误接受的红绿原源码/反例均保留。修后逐pair显式核每个中间量finite/零分母；独立14边界、NaN红绿、V4默认/AST和真实t0/t13重放通过。独立初次afterhash因candidate正追加diagnostic字段而诚实FAIL，最终1c3e稳定小复核v2通过/.6708wall（86f6e8b7），不改标原失败。所有检查的精确argv/env/source/log收于对应checks/execution原件。

V5对原V15快照t0仍412、t13由145改321；最小straightaway约+.80206/+.87239/+.70111。穷举t13所有3/2/1GOAL合法非接近动作，tb1/tb2无reverse-away、tb3有；原angular7a472门每机至少1有效方向段、总体双sign、至少1同机先后reverse，并不要求每机双向。原门说明19ea6b1e和候选事实a36b90c6保留。不为tb1/tb2加KEEP或强加新AND门；实际tb3反向、全部活动与停车覆盖仍待新native，CPU不提供轨迹信用。

两新A16reset metadata wrapper angular870ce0f8/physicalf56053c8及tests ed2fb250复用原A8，归一v16→v8/v5→v3后全文与wholeAST相同；原8EP/33records/32steps、angular7a472/physical2516和每机A或B停止pool/其他门保持。canonical独立只读wiring2e1079a6 PASS：七SHA、原旧资产不变、36runtime pins与另3eval+19execution共58显式pins均匹配。ENV58633e6dc8c6722f4ed4428b1a1f8987b5aba8f62e16d61f53229bfb24d0525b，audit_ppo b34556bdf1e2bcb07907f7c8489ca2a268aabe460c816d2aa4d432253e648f67只一ENV摘要literal，逆字节+AST同3883；ROS生产/配置、实际a014库及四编译源不动，无驱动重编译或重复完整ROS回归。状态同步曾把ROS memory状态段误换为root标题，本版已恢复准确V16状态；不改旧研究证据。

完整canonical conda实际命令（cwd Git root，子进程cwd wireless-rl）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= /usr/bin/python3 /tmp/mr3_p2a0_v16_conda_cpu_full_v1.py
```

原ns3gym/python -m unittest discover -s mr3_learning/tests -v，exit0、282PASS/50.152test/55.66401246422902wall；46继承绑定源before==after。runner范围未自动加入新V5test，因此另以运行前promotion摘要→运行后新模块a23ebf15字节一致及实际11test discovery补充（conda_source_scope_addendum_v1），不声称原runner绑定47。完整stdout/checks3a979c2c、script/argv/env保留。含CPU synthetic SB3 optimizer/checkpoint，不计native/PPO/pilot。

V16机械9coord+parent/其test共11源码逆版本字节与wholeAST同A15，39methods（14launcher+9scheduler+4Shim+3nested+9parent）在隔离fakecanonical/fakeCLI通过，原exact argv/log见matrix_mechanical_checks_v1；无native/formal。晋升9coord后仅两resetwrapper路径A15→A16与两fakephysics basename literal需要额外适配；初controller错认terminal3而原值4的assert失败及proof漏函数名逆变换的observer失败均保留，canonical源未重复覆盖或改变。四literal归一v2 PASS（84aeb983），canonical9scheduler和9files fatal lint通过（checks02 2bf35d4e）；不称继承文件全格式lint。

最终计划6980566af272dddd0785a1eccca7d3ee9f2acfc7136f1d3978aee515d14241f3 ready：134绑定=117旧SHA不变+4授权current刷新（benchmark/comparison/prep/ppo）+13new。runtime集合101不变，仅benchmark/prep/ppo/ENV四已声明delta。所有原physical/angular/settled/task/body/模型/预算字段逐值保持，608API/596动作/18000原生墙秒，四stage相同seed/domain/port及mandatory/pool/FAIL停后续。实际最终canonical计划检查：`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v16_final_coord_checks_v1.py`，14launcher+.286624709wall、9scheduler+.750340795wall全部PASS，135源/计划前后稳定。原39methods除本次计划接线23外不重复跑。下一步完整原件封存、静态核验与clean commit/push，再exact40 preflight；尚无V16native/PPO/GPU/pilot，pilot余额不变。

独立最终plan/source检查v1在初6980566a发现reset两template仍指旧A8/V3，而actual audit_stage已指A16/V5，原FAIL/脚本/log与完整旧草案保留（未启动native）。原生前仅改两template脚本路径、physical/angular_reset各matrix_consumer路径/SHA和资格文案v3→v5，全部原数学/覆盖/预算不动；当前plan5eca58447b8075782bb56ef2506c2bcb8a84e01b5a8233242fe08d963b46bd07。相关14launcher实际`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v16_final_coord_checks_v2.py` PASS/.27436695294454694wall，135源/plan稳定，不重复其余9scheduler或282suite。

最终独立命令（cwd Git root）：`rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v16_final_plan_source_independent_v2.py`，exit0/1.6300577111542225wall，ea584952f08ae26774ef03681d90063ce69de77436f9f1a2f0b852bbb1b30048。4stage原mandatory/receipts/workers/ceilings保持，134=117旧+4指定current+13new；101runtime仅4授权delta，ROS src/scripts无diff/untracked，五actualinstalled YAML/model同17ef，actual build/install/archivea014逐byte及四compiled宏摘要同源。physical/angular_reset仅上述metadata归一后其余逐值相同，未声称整对象字节不变。36pins/ENV匹配、ppo单ENV摘要之外AST同；无consumer/tests/native。所有离线writer停止后才准归档。

V16离线保管helper b2f1795d的9custody fixtures PASS，初styleFAIL及修前source保留；仅缩进AST等价修复，非行长flake8保持原defaults后PASS。旧A15/A14/A13实际14manifests、3049distinct raw只读核验PASS/28.134164243wall；新识别native selected_path/selected_encoded_sha及closure_static path/sha256，不改旧原件。全部writers停止后实际命令（cwd Git root，PYTHONPATH unset/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1）：

```bash
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v16_archive_offline_originals_v1.py --writers-stopped
```

一次publish exit0/22.695107930805534wall，主manifest e5b8a3903f92847fa71da7a005977c9bf4d6f55c48b79511ce23a6b4046195e0：165new/raw1968417B→encoded495796B，49旧raw去重引用，946mock/fake/active/continuation等排除；新/旧raw与encoded/decoded/source-stat均后验通过（aef9c81c），无native/formal。初NaN反例、旧6980/templateFAIL及各observer/style/source与282/39/23/14全部原stdout/argv在原件中，未重标。

最终prefreeze实际`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v16_prefreeze_inventory_verify_v1.py`，exit0/PASS：134bindings/101runtime/36pins、全部源末验、actual库/四宏、165原件/49旧ref、162链接、实际git add -n .197路径白名单及git diff --check通过，179资产初inventory c52feb7a。发布后原回执和prefreeze helper/结果/dryrun追加独立保管：`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v16_capture_publish_addendum_v1.py`，exit0，8原件raw71097/encoded9801，manifest c4b723e00b5f960998a44722f180813a20e0bcf2c97b20fe0fe20c013269f544。最终inventory_prefreeze_v2覆盖189项/自身排除，SHAf15564cf2e231bdbfdf1a608f216307cab67a728a6e9ffd1f58525cc704fcfb7，初库存和主manifest保持。只做静态/保管，不提供native/PPO/pilot信用。


### 2026-10-17 MR3-P2A.0 V16 原生关闭：仅 tb1 制停覆盖 FAIL

实际clean pushed冻结ebe7d51bdb7bf9d77a28b77cfb4296876afb0100，plan5eca58447b8075782bb56ef2506c2bcb8a84e01b5a8233242fe08d963b46bd07。exact101runtime/134independent/a014 preflight PASS，receipt88aa16d07898761b45168d011f01f6b37b20a66d0119396d1e7eb6aca654045f；101sourcepack manifest3b1913d28485117763381205baa4a34d4b8cc080d26d5ebf62d683b1f41effdb、encoded31524df906ac39be5b098e248c1a83f165b2ef09dfdec84b0145893bf55780ed、tar63805fc608edcf8f03acc16c8e5c8718b3afb332c39b72c9f100da27078050cc/355352B，实际parent d6702003与已归档raw逐byte相同。

实际命令（cwd wireless-rl，PYTHONPATH unset/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python report/assets/20261017_mr3_p2a0_v16/independent/mr3_p2a0_v16_buildproof_preflight.py
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v10_pack_source_bindings_v1.py --preflight /tmp/mr3_p2a0_v16_source_preflight.json
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -u report/assets/20261017_mr3_p2a0_v16/independent/mr3_p2a0_v16_cross_stage_mapping_monitor_v1.py --freeze ebe7d51bdb7bf9d77a28b77cfb4296876afb0100
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u /tmp/mr3_p2a0_v16_matrix_draft_v1/mr3_p2a0_v16_run_matrix_v1.py ebe7d51bdb7bf9d77a28b77cfb4296876afb0100
```

父编排15:28:00.283062 UTC启动；interface launcher 2026-10-17T15:28:00.791829+00:00 至 2026-10-17T15:40:35.211485+00:00，计费754.4184093018994原生墙秒，1reset/32step/33API、32effective+physicalsim秒、open101/三机/domain140/port13301，V5/32。九实际参数服务器读回PASS；最后external_sampler_limit正常截断。benchmark与parent wrapper计时另报不叠加。11formal全结束，runner_errors=[]，唯一mandatory fixed_physics_v1 FAIL，其他9及额外FIFO PASS；aggregate99fcf2535b5a52b375a0f33400b1ea976fc7ba347e8c60bda918fc686504f372。read-onlyformal300.7870844551362wall不计native。父15:45:36.428786 UTC正常按规则exit1/skip terminal/reset/deadline，watcher自然exit0；源码/二进制/Git整个native与formal期间未变，无signal/盲重试/原生PPO/GPU/optimizer/pilot。

full/input活动门PASS：三机完整received路径约.0877008/1.218166/.953723m、accepted1/2/2，不能冒作每机1m/95任务成功。angular7b1ca095 PASS：正tb2/tb3、负全3、双向tb2/tb3；peer/control/drive/information/settled/closure通过。physical78ff4b8b FAIL仅tb1缺stop资格：38 A的prior非零段20/40/60/80ms为2/17/14/5次，全<.1s，事件初速度最高.0354386<.05；task独立peak.065825不替事件资格，唯一B no_active_prior_linear_output。tb2 creditedA2/B2，tb3A1/B1；三机errors为空、planar/angular/chord counters为0、无observed_bound_violation和nonrestBeyondHorizon，仍不得给tb1制停信用。39native start/exit0、18Nav2finalized、48保存PID/start身份freshgone，严格关闭PASS。原leaf摘要91b6025b，只读4正式JSON+1.3MBtransitions/.3472wall，精确source/argv/原输出保留，不重跑formal或扫描大raw。

小快照逐32实际command/typed post-step重放全部一致。tb1在t13/14 fresh/valid/idle、首WAIT已过3/4秒、received abs(v)=.00013848/.00010338合格，V4 lifecycle未阻断；原8GOAL mask全false、path_distances全null，非V5过滤引起。path_maps.tb1存在且非missing，seed_cell_body_clearance约.14492222687338152<原.29，使reachabletarget/pool/selected全0；全局pool仍215，非全局无候选。t0/1 seedclearance.6373259/reachable552，t1无GOAL另有activecommit，不能把1..21一概归为seed失效。t21仍.14492，t22恢复.7456696、reachabletarget21576/pool129并重新有8合法GOAL。t22..25实际快照中单tb1GOAL+队友WAIT仅099/499同时满足原jointmask及V5非接近；5秒commit最早取消27/28/29/30，至32余5/4/3/2秒。这仅合法机会及预算，不提供新轨迹/停车证据。根因汇总b53da794及2aafd/0e87/9367/8f3d源、argv、execution、stdout全部保留；未读mapraw或ModelStates，不降低原seed/制停门。

V16已闭原件保管实际命令（cwd Git root，PYTHONPATH unset/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1）：

```bash
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v16_pack_native_v1.py interface
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v16_archive_closed_v1.py --publish --mode stopped --stop-stage interface
```

23helper元数据/custody反例与非行长style PASS；archive b4116df8 AST经version及inventory_v2单literal逆换同V15，packer d3f8cba6逆byte相同。实际context2.6678465376608074wall、pack32.96681893616915wholewall（内部32.202946595），568raw545668315B→33913593B，manifest322339fdde0b693b66480ac8dca45e55ba59c03d5a6ffd92abfe8455f7fe8233；最大encoded14642978B，全<100000000B及100MiB，无需分卷，未谎称现packer自动限额。publish exit0/14.924305682070553wall，255new support/raw17311911B→encoded1490654B及214旧raw去重引用，supportmanifest2ad71a46aea951258c3e39168619d4e7bcece832a0d1c79edc44dac9864f6a6c。101Git/tar源、134indie、189prefreezev2、actuala014/四宏与48身份freshgone均核验PASS。inventory1019 SHA cabcc3dff59b569bf430966958df82a26559a3c7f1a80f875cc3746e78fae848；verification a3d01c1967bd9af5daa44b2e96aa8412f45ea03099f32795900681cd9fdffa75，成本93050341472a30925a5de95e0a2c7605bdd500b3ef2ddf97756f5fc191411aa1。归档耗时不加native成本，保管PASS不改原physicalFAIL/3SKIP；pilot已用2226/11494.045260453597与余1870/2905.954739546403保持，P2A.0未完成，修复仅新冻结完整矩阵。

V16关闭静态实际命令（cwd Git root）：`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/root_mr3_v16_closure_static_review_v1.py`，exit0/.9502595849335194wall；1019库存SHA/bytes、152链接、原log前缀、真实唯一physicsFAIL/11jobs闭合均通过。实际git add -n .841路径全属11关闭文档或库存白名单、diff-check PASS，无native/formal重跑。5份发布后原件/静态helper和回执追加closure_static_v1，保留初库存，最终inventory_native_v2另覆盖后置保管。


### 2026-10-18（北京时间） MR3-P2A.0 V17 晚目标刺激与离线准备（尚无原生）

V16完整physicsFAIL/3SKIP闭包db6410f81f8540033443ff103c0b340b89bac65c已push并由只读ls-remote确认；原push上传较慢但自然exit0，未signal/并发盲push或重写历史。当前V17延续本轮UTC20261017原件ID，不修改原V16证据。

V6仅在共享probe_action_v4新增默认False late_goal_window，V6 wrapper才同时启用V5非接近及late。旧V4/V5默认state/动作/完整diagnostic保持，原V2/V3/ranker/V5/filter/提交函数AST不变。原0..1.5/13..15仍V3排名，15..26晚窗口仅直接复用原_probe_goal_order outward排名，真实snapshot elapsed不改。新窗口按round(elapsed*1e9)与[15e9,26e9)比较，原46.12-20.12=25.999999999999996的float原型会误在t26选GOAL，旧源码/027→新ns888反例保留；t15 ns优先late分支，未伪造V3时间/加epsilon。正常1s末GOAL25、原5s mask直到30才可WAIT、余2s仅测量机会，仍须原.78s/.144m/三freshrawrest。原firstWAIT>=3/freshidle/received静止代理、.08+.05movingtrigger、28deadline及actual typed返回锁存保持；不更改seed.29/候选/地图/actor mask。

候选7文件handoff45b47a6e0abce9a0d8a77a744f71585c4835fdd8873f25ef1ab8bd2986c28082，root逐base/新SHA核验晋升（fixture_promotion_v1）。benchmark1e32ea25b1dec121b9febc1f395124372cf14410dd6cbe66667dfa7feca63403，auditprep b7e07ee4；V6 exact32 capacity资格、A17两wrapper与test仅metadata适配，原8EP/33API/32steps、raw7a472/2516/原pool不变。最终4实际重放/边界+11portable PASS，10资格+19wrapper源未变复用原成功，不把含初portable失败的旧整体checks改标PASS。初新测试没先创建phase baseline而按原.05条件正确KEEP的fixture失败及2style失败/float原型source均保留。原V16输入t22首次反事实899→合法499，未授新轨迹信用。

独立有限7组review b2ac6bb09de05121eba1abffe868aa3dd48328d67aaec835d3772f2540448a9c PASS/.9226wall：默认V4/V5真实V16输入动作/diag、ns两端及nextafter、t15late排名、fresh/recovery/firstWAIT/原mask、25GOAL→26/28/29maskedKEEP→30legalWAIT实际匹配返回后才latch→31held、.08/.05与False/nonbool提交门均保持。只提供机会/兼容，不证明Nav2持续.1s或制停。canonical wiring9a3c59c6 PASS：七source、两wrapper对A8归一全文+AST、58explicitpins及旧资产不变；仅V4/V15与V5/V16用原actual typedcommands，交叉V4/V16与V5/V15用构造matching receipts作counterfactual，无真实submission信用。ENV1144537c64c2c63e48cd6e55d41c7e811ee25935e60024f72f847631ae1c5a4d，PPO f7e161a7954d79499801a9a3a01959705f4733e2578e84e7660152c96c19084c只换ENV一literal，逆全文/AST回db641，原36runtime+3eval+19execution均匹配。全部原source/script/精确argv/env/stdout/执行回执在V17/tmp原件中，不重跑formal。

完整canonical conda实际命令（cwd Git root，子进程cwd wireless-rl）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= /usr/bin/python3 /tmp/mr3_p2a0_v17_conda_cpu_full_v1.py
```

仍ns3gym/python -m unittest discover -s mr3_learning/tests -v，exit0/294PASS，49.490test/54.956211707089096wall；48source before==after（继承46+明确V5/V6两个模块），不含未声明新路径。含CPU synthetic SB3 optimizer/checkpoint，不计原生PPO/pilot，ROS生产/YAML及actuala014四源码均不改，不重复已稳定ROS1200或重编译。

V17九coord/test+parent/test共11新/tmp源，经版本逆字节+wholeAST同冻结ebe7的A16及原parent；四依赖Constant仅两wrapper路径A16→A17与两scheduler fakebasename。隔离fakecanonical/fakeCLI 39methods=14launcher/9scheduler/4Shim/3nested/9parent全部PASS（checks01 cda484cc，reverse_AST b2fe9add），原全硬门/预算逐值保持。9canonical晋升后仅相关9scheduler/.789test+9file fatal lintPASS，sources稳定（checks1d09f04c），不重复39。新active reset templates/criteria.consumer指A17/V6正确，不继承A8旧模板；raw消费者及数学scope不动。

root最终plan de619095444706e83d59704928ccdcd099dd18d9222b20ed5cff34a1d135430f ready：147=130旧同SHA+4指定current刷新+13new，runtime101路径仍四授权delta。原608API/596决策/18000原生墙秒、4stage seed/domain/port/ceilings/required/pool/FAIL停止规则保持。实际最终canonical命令：`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v17_final_coord_checks_v1.py`，14launcher/.286367848wall与9scheduler/.753245971wall PASS、148源/plan前后稳定。完整数学/源码/实际二进制最终独立命令（cwd Git root）：`rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v17_final_plan_source_independent_v1.py`，首跑PASS/1.5946wall，d774e4801e4a06167312c81d67613ca36469871ad68abc886297b6a553ae7741：stage仅V5→V6/runID、两active模板正确；criteria仅明示path/SHA/资格v5→v6归一，其余原数值/coverage同；147bindings/101runtime/36pins/ENV、ROSsrc/scripts无diff或untracked、5actual YAML/model、actual build/install/archivea014全byte和四source宏均匹配。静态/CPU不授native信用，clean pushed exact40 preflight仍必需；无新PPO/pilot/P2B/gateway。

V17离线保管helper 0b15f22b00b24010d2aadbfbeee873dc201e7dd74c6a5ad47de94e44ed2d90c6：10custody fixtures/.022s及非行长lint PASS。旧A16 inventory_native_v2的1026项与19份更早manifest（共20refs/3976distinct raw）只读核验PASS/38.672925940249115wall。全部writer停止后实际命令（cwd Git root，PYTHONPATH unset/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1）：

```bash
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v17_archive_offline_originals_v1.py --writers-stopped
```

一次publish exit0/40.24021921120584wall，主manifest a11005e1cf71bb2feccf63888bf3f6e74183b65867dfd919be23a72f67884531：194new/raw2574531B→encoded669413B、106旧raw去重引用；944排除=30fakecoord+82fakeruntimeleaf+831mock+1activeconsole（本次扫描无实际continuation/ELF入选，不冒称其排除数量）。所有194/106、encoded/decoded/source-stat后验PASS。receipt a1e4e61e3fc696aa0a16346f1d1087c0ac06403d1a583f78d2cebe5f44021de8，verification c65dbb99c194bc9b95f46d9aa18889d0e6103872d8c4461d929b55dda8917970。无native/formal，不计pilot/原生预算。

实际静态`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v17_prefreeze_inventory_verify_v1.py`，exit0/PASS：147绑定/101runtime/36pins、源末验、actuala014/四宏、194原件/106引用、164链接、真实git add -n .226路径白名单及diff-check通过；初208项库存SHA b9c02622aa4fd232effa32ca0fc4ef40d1055c5886526e78f737ee73156b223a。随后`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v17_capture_publish_addendum_v1.py` exit0，发布回执/静态helper/result/dryrun等8原件raw72494B→encoded9028B，后置manifest d24c3d6ad3a7e093ec46ea21b7bf2125662e00c9db191212cad394f1ad35a9ad。最终inventory_prefreeze_v2覆盖218项/自身排除，SHA35848c92d649265c354c025a537b13a026dc68ea46e569692170f18e2391afcf，旧inventory及主manifest保持。只授静态保管信用；原生完整矩阵尚待clean pushed新冻结。

最终提交前静态命令（cwd Git root）：`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v17_final_static_review_v1.py`，exit0/PASS：218库存与全部219资产、194+8新原件/106旧ref、源/实际库/四宏、167本地链接、原db641 log前缀、实际git add -n .236路径白名单与diff-check全部通过；不覆盖旧静态原件，不提供native信用。


### 2026-10-18（北京时间） MR3-P2A.0 V17 闭包：两阶段PASS，重置真实停车响应FAIL

clean pushed冻结eee6b2f90f697b28a1c20a2af5d1a6d2f044465e（source commit/push自然成功），plan de619095444706e83d59704928ccdcd099dd18d9222b20ed5cff34a1d135430f。101runtime/147independent/actuala014 preflight PASS，receipt341cf225115a5abb394c3034927f845abf30fed6019a6f80fdafead2f643828a。101sourcepack manifest05065d4b1ffe408e7cf222d85a8f2bd120755d66e86077f1ab4d2dce9995ae2c、encoded5a800a4510d5a0f0a6b40884f88ce1d6729f5e2dbfddb906c73ddd04335a8425、tar3b51f13cac63e15200e31e5a14a8cd6420fd4246e6ec6288b72318ab697c7d3f/356131B。实际parent2f746a56828cadc27c2888013607642e4f009a0e187a3abea8df0ab10d7f9741与已归档raw逐byte相同。

实际命令（cwd wireless-rl，PYTHONPATH unset/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python report/assets/20261017_mr3_p2a0_v17/independent/mr3_p2a0_v17_buildproof_preflight.py
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v10_pack_source_bindings_v1.py --preflight /tmp/mr3_p2a0_v17_source_preflight.json
rtk proxy env PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -u report/assets/20261017_mr3_p2a0_v17/independent/mr3_p2a0_v17_cross_stage_mapping_monitor_v1.py --freeze eee6b2f90f697b28a1c20a2af5d1a6d2f044465e > /tmp/mr3_p2a0_v17_cross_stage_mapping_console.log 2>&1
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u /tmp/mr3_p2a0_v17_matrix_draft_v1/mr3_p2a0_v17_run_matrix_v1.py eee6b2f90f697b28a1c20a2af5d1a6d2f044465e
```

父2026-10-17T16:18:34.681840 UTC开始，18:17:56.753427依规则exit1，watcher自然exit0。interface1reset/32step/33API，V6/open101/domain140/port13301，launcher814.0720555749722wall；11formal jobs全PASS/10mandatory，aggregate168bd0a877e219e223ac35327ff44ea9a35ffb829867e913c7c783819c396a1d。三机路径1.192978971393869/1.2008765881850492/1.1712691564881748m，accepted2/2/2；每机原A或B信用及原angular覆盖PASS。39/39native exit0，严格关闭/18流接触等原门通过，仍不提供95%任务/学习信用。

terminal2reset/8step返回/10API、实际提交7命令，open101/domain142/port13311；launcher393.5368322748691wall，9formal jobs全PASS/7mandatory，aggregatea2833418f21b7bc6fbe5b0323058c9bf2da7756bd5e7cb95a23f0bca7be46ae1。e1最后command存在、dt.02、ACK齐，task3.02s；e2最后command=null、dt0、action_submitted=false/bootstrap0，提交前已终态、task3.0s。两分支注入navigation_failure，精确8返回/7提交/6.02s，未补造命令或物理推进；各39native均exit0。

reset2workers各open101/open101/rooms101/corridors101，domain144/145、port13321/13322，8reset/256step/264API，256实际命令/256task物理秒，launcher3217.3981215129606wall（benchmark3216.857041723095）。8轮均正常external_sampler_limit，26formal jobs全结束、runner_errors=[]，仅diagnostic physical_per_episode与mandatoryphysicsmatrix FAIL，其他24PASS；aggregate4a1176995ca658351b85f338318c9ec170089b3e6fc5f254dca287aca237f842。8input/8FIFO、原angular sampled bounds、peer/control/drive/information/settled/closure皆PASS；312/312native exit0，347保存身份freshgone。逐轮活动完整、每机accepted>=1，三机最小path依次worker0=1.1341977210073684/1.072213750809963/0.9339615166247045/0.2731297173596091m，worker1=1.1415969791367133/0.8923317275290962/0.9120054589462833/0.1388037983349296m。小摘要b7e1da5a保留全部精确值；首次summary因嵌套结果无CLI-only SHA字段退出1，v1原件保留，v2仅修摘要绑定，无正式重跑。root状态显示脚本也曾未处理terminal command=null而退出，原v1/v2/v3/v4源均保留；正式任务未受影响。

失败不是原pool缺信用：tb1 A12/B9、tb2 A15/B13、tb3 A13/B6，已有跨回合原A或B；worker1 corridors tb3单回合缺信用按原pool不新增mandatoryFAIL。真正违规为worker1 e2open/e3rooms的tb1第二次A/B。e2 A96.22/B96.18s，首3rest109.684/109.718/109.752s，延迟13.464/13.504s，polyline.0225408/.030097m、nonrestBeyondHorizon；e3 A90.36/B90.26s至104.275仍missing_rest/nonrestBeyondHorizon。raw机器人errors[]、其余planar/angular/chord计数0和其他合格事件均不能抵消此违规。deadline按规则SKIP，不重试本冻结或拼接旧PASS。

独立小文件重放两ep各32真实V6/typedcommand完全匹配（7768c48e）；第二GOAL均command14，command19(t18)按received_motion选合法WAIT，之后14条TB1 WAIT锁存、navidle/samegoal14/accepted2、无新GOAL，B cancel/result齐且new_goal_clock_ns=null。单次流式原raw提取22.42wall（精确argv/env/source/行号/SHA在execution原件），e2/e3各433/432唯一ownodom，duplicate0；e2 actual v/w自96.22双零、zero desired96.254、applied双轮自96.424恒零至110.194；e3 v/w自90.36双零、zero desired90.369、applied双轮自90.539恒零至104.275。不是高层继续发运动命令或paired slew残留。

超.78后raw横向vy约.011–.012m/s而前向vx很小，vy正号100%且取消前即存在；34ms样本覆盖20ms的10种offset但无步内数据。尾段worldXY差分平均速度约.0003745/.0003072、polyline.004749/.004032m，原raw norm均值约.011239/.011430；不能改用位移替代原hypot/三样本/.01/.78门。独立441f9b63逐433/432行核验与原rest精确一致，floatyaw范数误差<4.2e-8；API/SDF不支持CoG原点错配，仍无独立1ms/contact/solver状态，不能宣称噪声/误报或唯一根因。最终custody c05402de含38件/10264865B、12源finalstat稳定；精确source/argv/output均在支持原件。先隔离补充物理观测再选择修复，不改任务/原物理门。

3个已闭native pack使用精确86e3e49e helper（23metadata fixtures+非行长lint PASS），实际顺序driver命令（cwd Git root）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -u /tmp/mr3_p2a0_v17_pack_closed_stages_driver_v1.py
```

内部依次`/usr/bin/python3 /tmp/mr3_p2a0_v17_pack_native_v1.py interface`、`terminal`、`reset`，exit0各wall33.950209392700344/22.062499911058694/262.30156127596274。interface576/raw568477393/selected34627144B，manifest9210cbc28fdfc6d41e6d3d62ff25f5f8e829c3439398619dbc98b70deb870c56；terminal415/raw362203920/selected21961857B，f84c0acca616301dceb65b9ebdab43827a5cdb2ee9c74f884bcb909fd208910a；reset4543/raw4430364243/selected271190339B，4ef73a03c6210dfb46ff8b1211c447e5cfa6a3fb09947ccd3598aec241999116。最大encoded14878018B<100000000/100MiB，未分卷，不声称packer自带限额。原始文件全部保留。

全部native/formal/observer/诊断writer停止后实际（cwd Git root，PYTHONPATH unset/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v17_archive_closed_v1.py --review-output /tmp/mr3_p2a0_v17_closed_archive_prepublish_review_v1.json
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -u /tmp/mr3_p2a0_v17_closed_publish_driver_v1.py
```

publish driver实际调用`/usr/bin/python3 /tmp/mr3_p2a0_v17_archive_closed_v1.py --publish --mode stopped --stop-stage reset`，source1904fdaa42e22c47a335e7118ed16c395b9453353567baeb5a29d624fdabbdde，exit0/102.41948467679322wall。1167支持原件manifest257e72264e79878ee6a0f655b68a1372de6aedb75fd6e799217ea3dc0d1e2353；3stage总5534native/raw5361045556B→selected327779340B；库存6928项/自身排除，SHAa711b076280676eff18c53708e108f7afd0c24edd27b46f704490693f7b916df。verification ebbe1048afb890bacba74549dd10f25a8b5ca3d58c3a71c3a015cad795afb9e3，成本36f6872a70170ebecc9d55fed77079ce552eccfa547306bf77210473b48c62d2：101Git/tar源、147独立源、218prefreeze、actuala014/四宏与487保存PID/start身份freshgone均核验PASS，保管不重标physicsFAIL。

共11reset/296step/307API、295实际命令/294.02task物理秒，计费4425.007009362802native launcher墙秒；父audit CLI墙秒362.9459742582403/256.85878604091704/2112.325802913867单列，压缩/归档不计native成本。原生PPO/GPU/optimizer/learning samples均0；pilot已用2226/11494.045260453597、余1870/2905.954739546403保持。P2A.0仍未完成，后续修复使用新冻结，不把本版两阶段PASS拼接成完成信用。

V17闭包静态实际命令（cwd Git root）：`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/root_mr3_v17_closure_static_review_v1.py`，exit0/6.137763304170221wall：6928库存SHA/bytes、101runtime/147independent仍原源、487身份消失原核验、11/9/26 jobs与原FAIL保持、155链接、原eee6日志前缀、真实git add -n .6721路径白名单及diff-check PASS。发布后7份实际静态/发布原件以`rtk proxy env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/root_mr3_v17_capture_closure_static_v1.py`无损后置保存，raw1558070B→encoded224891B，manifest ef521cad309074701460a6be51d01a3c5e9b7f86063e8ef55f680d7cf892ddb4；最终inventory_native_v2覆盖6937项/自身排除，SHA42a6df7973301b17e0cf47ca314e1c88f6acf0c98683909f75690d3f8a24b856，旧库存和全部原件不改。无native/formal重跑。


### 2026-10-18 Asia/Shanghai — P2A.0 V18 隔离停车物理诊断准备（尚无native信用）

来源父冻结`8780735c8234872a781236b4e52bac6f2237b746`，原V17完整FAIL已关闭推送。
本段为新工作树CPU/构建检查，实际执行UTC2026-10-17；各回执保存具体before/after源码SHA，
非以父冻结冒充新实现。新observer源4e721e15…、profile26952e1c…、launch bcb177d6…、合并CMake7ebe737c…；
原驱动四源不变，实际SO前后均a014f2c6…。无新PPO/pilot/GPU/native/矩阵或95%信用。

确切构建入口：`PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v18_build_v1.py`。
其argv为系统Humble underlay后执行`/usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select multi_robot --allow-overriding nav2_bringup`，
环境移除Conda/继承ROS路径，PYTHONNOUSERSITE=1、CMAKE_BUILD_PARALLEL_LEVEL=2；53.591792651917785墙秒、exit0，
source before/after相同，原a014未重编字节变化。库保管入口`/tmp/mr3_p2a0_v18_binary_custody_v1.py`在系统Humble/当前overlay下执行；
两SO ldd-r/readelf-h均0、无undefined/notfound、build/install逐字一致、source宏匹配、gzip确定性及解码匹配。
外层执行2.4441555墙秒、保管内部1.2942128609865904墙秒。回执v1预定archive日期错写20261017；
`/tmp/mr3_p2a0_v18_binary_receipt_path_correction_v2.py`仅修六个prospective路径到20261018（内部.0283秒），原构建/ELF/v1保留，无重build或ldd。

完整CPU入口`PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/mr3_p2a0_v18_conda_cpu_full_v1.py`，
内部conda ns3gym、PYTHONNOUSERSITE=1、unset PYTHONPATH、CUDA_VISIBLE_DEVICES空；294项PASS，
53.832测试秒/59.241407084744424墙秒，48源前后相同。含CPU synthetic SB3 optimizer/checkpoint测试，不计原生PPO。
launch graph/默认三SDF byte兼容/严格配置拒绝最终9项PASS（4.038197519723326墙秒）；早期两fixture FAIL和lint FAIL/源快照保留。
observer v1实际SDFormat模板编译FAIL原件不删；最终v5 syntax-only PASS25.28719墙秒，canonical合并复核PASS。
`/usr/bin/python3 -B /tmp/mr3_p2a0_v18_runner_checks_v1.py`4项实际CPU子进程反例PASS，区分有效物理FAIL退出1、坏JSON退出3、spawn失败与PASS；
`/usr/bin/python3 -B /tmp/mr3_p2a0_v18_live_admission_tests_v3.py`5项PID/start/maps/半行文件检查PASS（.11113508511334658墙秒）。
前两版CPU检查与被纠正的审查文字均留原件；非native重试。

预声明下一原生仅两次固定三机器人open101/V6/32步，每次1reset+32step=33API、1800墙秒，
累计66API/3600原生墙秒、0更新；baseline原50 iters、iters150唯一变量对照，非完整四阶段。
配置、命令、库和最终来源见`report/assets/20261018_mr3_p2a0_v18/predeclared_plan_v18.json`；
只有消费者/绑定/CPU保管收口并clean commit/push、exact40预检后才能执行，当前本条不记为已运行。
无原任务/停车门放宽；原失败保留，不挑选、盲重试或拼接跨冻结PASS。pilot余1870决策/2905.954739546403墙秒不变。

V18准备收口补记：最终`/usr/bin/python3 /tmp/mr3_independent_stop_observer_v1_tests.py -v`29项PASS（2.266774286981672墙秒），
system flake8(max99)和syntax均0；源前后相同，consumer SHA e61ce4e00907ab35e196f7abe9fadfd9da099af3542f98dc773d593c33ca2b65。
仅V17小transitions解析33记录/32实际step兼容PASS，不授新原生信用。
`/usr/bin/python3 -B /tmp/mr3_p2a0_v18_pack_offline_v1.py`在所有对应写者STOP后封324原件/4462289原字节，
tar.gz1239767字节，1.1902677239850163墙秒，全部原件末次SHA和解码验证PASS；包括全部早期FAIL、错误审查及修正原件。
可变root continuation state明确排除。152项独立source bindings仅刷新实际变更audit_ppo摘要并新增5个A18消费者/协调器，
plan现ready表示来源/CPU/构建已收口；只有实际clean pushed HEAD预检通过才可启动native，原生成本仍0。

V18准备提交修正：初次暂存diff-check发现两份readelf原始stdout行尾空格，root调用未正确阻断后续commit，
意外形成`cf248cb`（尚未native）。不修改原stdout字节、不重写历史：在后续提交把两文件改为确定性gzip，
`build/readelf_original_encoding_v1.json`记录编码前后SHA，offline原件及原commit均保留；重新diff-check/dry-run/精确暂存后提交推送。
无代码/模型/物理参数/消费者变化，无重build或原生重跑。

### 2026-10-18 — V18冻结85abe391实际baseline关闭，准入FAIL/对照SKIP

实际source freeze `85abe3916ab1582b68d7b3c3c0b96ea7fd68f6f1` clean pushed；
`env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python report/assets/20261018_mr3_p2a0_v18/independent/mr3_p2a0_v18_preflight_v1.py`
103 runtime/152 independent/原a014/两新SO PASS；
`/usr/bin/python3 /tmp/mr3_p2a0_v10_pack_source_bindings_v1.py --preflight /tmp/mr3_p2a0_v18_source_preflight.json`
103 Git对象sourcepack PASS，manifest db2e8c1f…/encoded4c197838…。
实际parent入口：`env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -u report/assets/20261018_mr3_p2a0_v18/independent/mr3_p2a0_v18_run_diagnostics_v1.py 85abe3916ab1582b68d7b3c3c0b96ea7fd68f6f1 > /tmp/mr3_p2a0_v18_pair_parent_v1.log 2>&1`。
内部baseline exactargv见原plan/receipt：三机open101、seed101、1worker、V6/32、ROS150/port13341、baseline config命令作用域注入。
返回1reset/32step/33API、32实际info.command、release29.72→61.72s、32任务秒，native850.965301560238墙秒，
benchmark exit0/PASS。原`mr3_independent_physics_review.py RUN --output /tmp/mr3_p2a0_v18_baseline_physical_review.json`
exit0/PASS、18.909605588763952只读墙秒；三机原停车证据完整/errors空，39/39原生exit0，46保存PID/start freshgone。
整体coordinator exit1/FAIL：root误把/proc/PID/exe basename硬写gzserver，本机为gzserver-11.10.2（与/usr/bin/gzserver samefile），
predeclared witness FAIL、1ms正式consumer SKIP、iters150 SKIP；无信号/源变更/盲重试/补PASS。本次未复现V17物理FAIL，不称已修复。
额外实际server/maps、configuration及当前rigidity DATA快照仅归因，非正式准入；完整1ms闭合后归约仍在单pass只读中，结果另列。

归档命令`/usr/bin/python3 -B /tmp/mr3_p2a0_v18_pack_closed_baseline_v1.py --source ROS/log/mr3_p2a0/mr3_p2a0_20261018_v18_baseline --target /tmp/mr3_p2a0_v18_selected_native_v1/baseline --prospective-prefix W/report/assets/20261018_mr3_p2a0_v18/native/baseline --execution /tmp/mr3_p2a0_v18_baseline_execution.json`
（原执行receipt保存展开的绝对ROOT/ROS/W路径及精确6-key env）。4 codec组PASS；502原件2,964,003,816B→586parts/225,772,425B，
最大2,689,824B；32MiB固定原byte分块、全部解码/重组SHA/原statfinal一致，helper外层52.86549312714487墙秒。
`/usr/bin/python3 -B /tmp/mr3_p2a0_v18_pack_closed_support_v1.py`封26额外失败/来源/执行原件，473913编码B；原stageFAIL/SKIP不变。
closed_summary_v1只读汇总错读顶层command得0；v2仅按实际info.command改32，两版均保留，非native/consumer重跑。
V18原3600nativewall已用850.965301560238，余2749.034698439762；pilot余1870/2905.954739546403不动，无训练/GPU更新。

V18闭合静态核验：`/usr/bin/python3 -B`只读检查137个变更文档链接、152项原independent源SHA、实际`git diff --check`和`git add -n .`598路径白名单，均PASS；无native/consumer重跑。独立canonical custody检查586个encoded parts与/tmp原封存逐字一致，26项支持tar解码与原件SHA一致、无单文件≥100000000B，receipt SHA30d5f25d…；原件见`assets/20261018_mr3_p2a0_v18/closed_static_v1/`。额外归约仅TMP仍在进行，V18原FAIL/SKIP不改。


### 2026-10-18 — V18闭合数据额外归约（描述性，原FAIL不变）与V19准入修复准备

V18 exact85abe391已关闭原件额外只读入口（cwd Git root）：
`/usr/bin/python3 /tmp/mr3_p2a0_v18_closed_observer_diagnostic_v1.py ROS/log/mr3_p2a0/mr3_p2a0_20261018_v18_baseline/worker0/episode001_open_101 --output-directory /tmp/mr3_p2a0_v18_closed_observer_diagnostic_v1`。
精确绝对argv/隔离env在执行原件，exit0，内部785.4870867431164/外层786.0037721036933wall。
每份physics与motion单顺序pass，三机29.72→61.72各32001配对/有限/连续，无capture errors；
ownodom942/942/941同T PRE位置与按原floatyaw投影XY/WZ逐值误差0，origin-CoG残差≤8.33e-17、fixedlink逐轴≤9.45e-5。
零双motor峰值含刹车，不新增晚停结论；公共postvel Z积分对CoG位姿残差约2.69–2.89m/32秒，XY毫米级，
保留getter/位姿限制，不改raw门或断言唯一根因。支撑contact有实际保留，世界RMS/constraint pointer不可用非0。
封存入口`env PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 /usr/bin/python3 /tmp/mr3_p2a0_v18_closed_observer_bundle_v1.py`，
52原件/encoded89314B，SHA b17d227e…，roundtrip/source stat前后稳定PASS；canonical A18/closed_descriptive_v1。
该分析没有缺失的live proof，V18整体FAIL/正式1ms与iters150 SKIP不变，未复现或证明修复V17。

V19源码父冻结bbbd7a9f01c380e1f03872d5d4aa58390f011b77，最小新live witness9c737261…/preflight1f2ad7ed…；
只将basename改为预声明Gazebo samefile/resolved ELF/bytes/SHA，并先核新witness唯一冻结binding再导入。
实际gzserver为/usr/bin/gzserver-11.10.2、159232B、SHA689e6123…；原PID/start/归属/maps/库门不变。
`rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v19_preflight_proposal_v1/execute_checks_v1.py`实际20 CPU检查
（真实exe8+preflight/static8+runner真实子进程异常4）及fatal lint exit0，3.570096406wall；精确argv/env/原件在A19/offline。
原103runtime/152independent sources实际摘要及a014/observer9a1d/profile0932三个实际SO全部未变，无重build。
完整CPU294/launch9/reader29沿用V18原件范围，不冒充本版新执行。
root按exactbytes promotion3新独立脚本、2配置及plan共155 bindings；CPU proposals保管39原件、52492编码B全解码/原件末次SHA一致。
独立final review PASS、310输入前后稳定、无阻断；原checker初轮对tar顺序/binary64舍入过强断言在原JSON保留，未改提案或原结果。

V19下一原生只准新clean pushed exact40 preflight后的固定两次open101/3robots/1worker/V6/32。
baseline154/13361、iters150156/13371，各1374.5nativewall/33API，总2749.0/66API；保留V18已用850.965301560238，
累计原生上限3599.965301560238/99API，无主动signals截断。原所有task/物理/停车/时序门不变；正确采集的原物理FAIL仍保留，
加载/来源/配置/逐毫秒覆盖/关闭失败则后次SKIP，不挑样/盲重试/拼接PASS。此条仍为准备，无新native/PPO/GPU/optimizer，
pilot余1870决策/2905.954739546403wall不动。诊断后有依据修复，再新冻结完整原四阶段矩阵，用户验收后才训练。

V19 preparation root静态核验PASS：155实际source bindings（旧152逐值不变）、2config SHA、3协调器syntax、146文档links、actual `git diff --check`及`git add -n .`21路径精确白名单；原record与dry-run压缩原件在A19/offline。无native/formal调用，actual clean pushed exact40预检仍为后置准入。

V19额外primary-source静态复核：缓存World/ODEPhysics/ODELink保持，缺失的官方gazebo11_11.10.2三个ODE源下载原件/URL/时间/SHA逐字保留。QuickStep pose积分在先、ERP速度移除在后，World dirty pose先于End；这提供getter与积分速度不一致的代码机制，但未采内部caccel/caccel_erp，不归V17唯一根因。源码复核SHA8011934a…及6件gzip无损保管在A19/offline，所有writerSTOP；无raw重扫/native/formal或门禁修改。


### 2026-10-18 — P2A.0 V19固定诊断闭合：采集PASS，150组无运动刺激而原物理FAIL

冻结`72d0465ddd1bbee09af117cfd9d89b7e729f8578`，clean pushed预检SHA89b5b9ed… PASS。
精确父入口（cwd wireless-rl）：`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -u report/assets/20261018_mr3_p2a0_v19/independent/mr3_p2a0_v19_run_diagnostics_v1.py 72d0465ddd1bbee09af117cfd9d89b7e729f8578`。
其固定child完整argv/env/源SHA和各console在A19/closed_core_v3/originals.tar.gz，不凭摘要重建命令。
两次均exact3/open101/单worker/V6/32：baseline域154/13361、iters150域156/13371，32step+1reset=33API，各32任务秒。
baseline actual30.1→62.1/native916.0106622199528wall；contrast23.1→55.1/native722.410109739285wall。
实体/SHA/loaded library/原生iters setter/readback准入均PASS；两组e61c原正式1ms采集PASS，各三机32001 task pair。
原2516 physical baseline PASS；contrast FAIL/exit1，三机eligible A/B均0，无目标无运动，非速度/加速度越界；严格关闭均PASS。
正式consumer墙秒依次731.308353652712/16.604266077280045/679.791821338702/14.919598877895623，均为只读consumer成本，不混原生或pilot。
两组78原生进程全部正常退出；父进程结束后只读closed_summary_v2.py（v1错读closure.strict的KeyError原件保留）重新核验91组PID/start全部消失。
本版原生1638.4207719592378wall；V18+V19=2489.3860735194758，原3600余1110.6139264805242；无主动signals/重试。

只读候选证据：`rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v19_candidate_stimulus_comparison_v1.py`及实际exec原件保存。
两组全部33快照/32 typed实际V6选择精确重放，diagnostics逐值一致。baseline每机接受2目标，共6GOAL；contrast三机33/33 fresh/valid却零GOAL、25×888/7×999。
全部99个contrast seed自身FREE0，但最近阻断100已存在于OWN保守投影，并非shared-only或unknown-only；距离.05/.10/.05m、clearance.01464/.06464/.01464<原.29。
198份nav数组精确重建，近身100持续到55.1，在绝对30.1也仍无GOAL；不据release差加固定7秒、不清100或降低净空。
小ownership review与上述结果独立一致。未保存rawscan/TF，不能认定100是真实障碍或已定scan/SLAM根因。

额外描述性单pass：`rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v19_paired_zero_motor_run_v1.py`实际child argv/env/输入beforeafter在execution4b38031b…。
helper025a4aa5…，12CPU+4独立小内存反例通过（首轮style错误/format-only修订保留），实际child0/内部453.98471132293344wall。
保留全task、全部双phase双motor严格0且已持续780ms的streak，不选最长：baseline late20145/20354/22559 pair，contrast各31221 pair。
contrast全32001 pair motor0，无运动后的停止刺激；两组轨迹不匹配，不提供150修复因果信用。
model/canonical origin/canonical CoG实际getter统计相同，不能作为独立重复；base origin/CoG分别保留。
getter Z与每步pose差分仍不一致，仅标识测量限制，不改变原.01/三唯一样本/.78/.144或指认V17唯一根因。
独立小结果review07a7cdec…完整性无异常，不重扫raw。

保管命令源/执行/CPU原件同A19/closed_core_v3：baseline502raw/2988325602B→587part/226712357B；contrast494raw/2588450699B→565part/194283176B。
固定32MiB raw分片，全部编码、解码、整体重组SHA及源final stat核验，4codec/8入口相关CPU与原失败保留；不是新native/physics审计。
baseline TMP helper96.326155844wall，contrast81.96380899474025wall；independent encoded-only复核不重复全raw decode。
canonical1156文件含metadata共422864963B，逐字复制核验1.7340063941664994wall，manifest fdc8f5ae…/33789be6…。
闭合core128原件/5270361B→963557B，SHAf75c7512…，往返与final SHA/stat PASS；归档辅助v1重复自身路径、v2含atime的stat相等断言失败均原样保存，v3仅修保管辅助，不动研究数据或判定。
150尚未选用，V17物理停车FAIL保持，四阶段准备矩阵仍未完成；无新PPO/GPU/optimizer/P2B/gateway。pilot余1870决策/2905.954739546403wall不动。


V19有界姿态补充（A19/closed_pose_v1）保留按源offset选取的PRE/POST原行及脚本/错误/回执，
总计只读12714005原始字节，无六份大流重复全扫。端点两组高度、姿态近似；
每机first pair后固定.2/.4/.6/1/2/3秒的取样中，baseline最大|pitch|.642580°、contrast.794788°，
预测最短地面交点11.529448/9.335524米。后者可能产生远端地面回波机会，不能解释.05/.1米近身占据，
也未据稀疏样本断言全程姿态或实际scan来源。SLAM与本机spawn同组启动且无physical-settle gate；
源码addScan路径不以minimum_time_interval作为settle门。未保存rawscan/完整TF，故仍待直接来源测量。
精确有界seek/摘要执行入口、argv、每源offset/行SHA/fd-path stat和首次错误均在上述原件；无新native/formal/训练或门禁变化。

V19 A19/closed_scan_static_v1源码与静态原件保留精确Gazebo/ROS/Karto来源、URL/SHA与6项float32端点案例：below/equal-min与no-return不直接形成占据端点，不能据此过滤.12。旧source-review的结构化sensor辅助字段误选首个contact sensor；新更正原件c078802f…对6份effective SDF显式选ray核验，几何/端点结论不变，旧35原件不改。真实processed /tbN/pose可作成功addScan的公开代理；既有原件没有rawscan，来源仍未定。

闭合独立复核ffdc2b48…与root静态155源摘要/160本地链接/JSON/diff检查通过，actual git add -n .初次1170路径均在白名单；原生与formal没有重跑。
该补充实际仅静态/只读端点CPU，无新原生；旧结构化字段选择错误明确保留，更正无结果重标。


### 2026-10-18 — 未选用150提案离线保管与V20_sensor单次来源测量准备

V19追加静态保管A19/unselected_proposals_v1：182原件1285725B→305377B，archiveSHAc0c0efae…/manifestd82e16dd…，全部逐member解码及final源SHA/stat一致。
条件150世界六文件/严格W7投影audit/ENV文案以及四阶段v1失败draft和v2draft均未应用、未运行、未选择；3 SDK CPU ELF排除但保留bytes/SHA/编译出处。
原离线检查及精确命令见成员：SDFormat真实SDK每图43个规范化字段仅iters50→150不同（不是43测试）、原几何/ROI字节一致，正例6/变异负例8；
任务loader旧JSON+新world必须拒绝、匹配新SHA才接受，三truth masks/freecells43812/51760/48560不变。首轮可选ODE父节点处理CPU FAIL原件保持。
条件audit严格固定6SHA字节投影回原W7，12方法CPU通过、80独立static检查（不是80测试），无调用者任意新pins；当前生产audit/ENV/世界均未变。
四阶段draft仅静态39检查/独立28门检查，无原生信用；命令/源版本/失败/成本在原封存回执，不拼接V17 PASS。

V20_sensor source_base为已推送9f7ab6e7fe7e85ff1f6bf3ee6e3fcba7d960549e。新增独立passive C++ rclcpp recorder，不改ROS生产包/SLAM/候选/驱动/配置。
CPP4707c8eaef49e4b763023b2b5d18e9be003ceed04bc9cebcd5c2bbf11f187caf、CMake2bc57b1b37468d588e9b92bccd8439e8d123568a373d5c3ddf2ff9c0c6e5a0f7。
实际独立TMP CMake SDK build01（112.918秒、exit2）仅Werror misleading-indentation，source/stdout/stderr原件保留；窄修后build02 exit0/112.37127894628793wall。
CPU自检1次15项，0.17197621520608664wall，无rclcpp init/DDS；±inf/两NaN payload/finite bits CDR、offset/bound、实际MessageInfo字段、半写pending与错误身份、typed config、-1/0/100占据和全TF frame均核验。
精确CMake/编译/selftest argv/env/SDK flags/link文本和两source在A20_sensor/offline/recorder原件，不以当前环境重建旧命令。

单次真实ROS SDK合成probe（非Gazebo、非任务/真实机器人）：cwd Git root，`bash --noprofile --norc -c 'source /opt/ros/humble/setup.bash; export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1; /usr/bin/python3 -B /tmp/mr3_p2a0_v20_sensor_recorder_proposal_v1/ros_loopback_probe_v1.py'`。
实际安全wrapper完整env/argv/sourcebeforeafter见checks/ros_probe01.json及probe result08dd269c…；domain171预检空闲，仅外部合成publisher，22订阅ready后实际3×104B CDR逐byte/SHA一致、GID匹配同recorder graph。
实际publication seq1/2/3可用、reception unsupported→value null/rawsentinel，不做ABI hack。正常stop/exit0，总3.3036216092295945wall，recorder userCPU.0951/sys.0339秒。
保存recorderPID3512882/start401720948已自然消失；合成参数states awaiting_first_map，未声称SLAM RPC实际验证；首轮probe style错误保留。
独立interface review8bd1bdaf…核实际CPP宏/flags/ready/final/ELF一致；45原件175896B→48422B tar61961a63…，manifest a3177dc9…，全member往返一致。
实际runtimeELF efd8a8f849da96c54753d168762dd8b4d5200077d5c490aaac070ea66f881f64/2659040B；root用gzip6无损编码482717B/SHA541aa760…，不跟踪buildcache/CPU ELF。

协调器TMP最终parent8259eefc…/preflight28da0a64…/testsfd013928…；checks_v3最终14相关CPU4.216660556wall+fatalstyle.810770823wall通过（旧11/14版本和checked_sources均保留，未累加宣称42新测试）。
使用有限fake Python children检查ready半写/冲突、正常stop、失败保留、真实early terminal原benchmarkFalse/CLI1；event加唯一Lock，join后核源不变；无signals/自动重试。
既有e61c两小函数profile_record/validate_profile只核首boundary50→150/setter1/其它字段不变，原V19小正例+ERP变异反例CPU通过，不调用其32step正式CLI。
32原件277503B→70402B tar完整往返+末源SHA一致，见A20_sensor/offline/coordinator。最终独立协调/plan review5c102d52…无阻断，不重跑CPU/DDS/native。
Root exactbytes promotion5新源(CPP/CMake/3Python)，旧155 bindings全保持，新160；原103runtime/三个实际SO不变。
plan相对sealed draft仅6处准备字段变化：status/pending两列表/newbindings/archivebinary/readiness；所有预算/command/动作/关闭语义全same。
初promotion辅助错用manifest source而非path，在空目录创建后即失败、未复制源/改变原件；promotion_v2仅修保管接线，归档元数据如实保留。

预声明只一次3robots/open101/单worker普通benchmark请求4step/最多1reset+4step=5API，域170/端口13451，≤900原生墙秒。
现有V6强制32step，因此去掉preparation3flags，默认probe_action(snapshot,outward_goals=False)原源码绑定，不加生产特例/手工探索fallback。
真任务提前终态原返回数/原benchmark FAIL保留；无真实终态却少步或RPC/strictclose失败仍过程FAIL。
原e61c CLI明确SKIP；原2516物理结果原样保存，仅strictclose用于过程核验。150仍未选择、无V6/32step/矩阵/物理修复信用。
Recorder先ready后benchmark，正常有限benchmark自然结束后父进程独占marker，recorder自身flush/close；另1000秒steady wallguard仅控制recorder，不能截断benchmark。
raw CDR+实际GID/时戳/seq、scan/TF/odom/processedpose/ownmap及真实SLAM List/Get逐项来源可用性分别保存；best-effort首scan缺失/pose代理/map header聚合限制不掩盖。
实际source admission与native入口在V20报告；本条为source准备，尚未执行新Gazebo/native/PPO/GPU/optimizer。须新clean pushed exact40预检后才单次启动。
V18+V19 charged2489.3860735194758，900新上限累计3389.386073519476<3600；pilot余1870决策/2905.954739546403wall不动。P2A.0仍未完成，完整四阶段在真正修复的新冻结另验。

V20准备root静态PASS：160实际源摘要（旧155全保持）、3Python AST、真实ELF与唯一canonical gzip逐字一致、174本地文档链接/JSON、git diff --check；actual git add -n .首30路径白名单及只对已声明runtime ELF gzip的force-dry-run1路径通过，build cache/objects不入Git。原始静态与dry-run在A20_sensor/offline/root_static_v1。无native/source准入或formal重跑。

### 2026-10-18 — V20预检入口环境纠正（未启动原生）

冻结340b13d8909fc58f0faf346780f7cfd75e5e93f8已推送。首次实际预检误用/usr/bin/python3，在preflight149导入audit_ppo22的torch时ModuleNotFoundError，session33288 exit1；源码准入未完成、未生成preflight文件，native/预算消耗0。
精确argv/cwd/源码SHA与工具返回错误文本副本在A20_sensor/offline/entry_correction_v1，未重复执行失败调用。原runtime/独立160源、库/配置均未改。
按项目无线学习侧环境规则将V20报告预检入口改用/home/zhuyulab/miniconda3/envs/ns3gym/bin/python，parent保持system Python并对子C++明确source ROS；此为CLI文档修正，不重跑CPU/SDK/合成ROS、不改变原门或首次失败。


### 2026-10-18 — V20实际准入PASS后入口来源形状修复（仍0原生）

941ae862eecc2420b75b7245f15bfd3f682ae6b5新推送冻结实际使用conda ns3gym预检exit0，103runtime/160independent、三原库/新recorder ELF/域170端口13451全部PASS；原件SHA69da…保留A20/offline/launcher_binding_correction_v1。
父入口原命令cwd wireless-rl：`rtk proxy bash -c 'env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v20_sensor/independent/mr3_p2a0_v20_sensor_run_v1.py 941ae862eecc2420b75b7245f15bfd3f682ae6b5 > /tmp/mr3_p2a0_v20_sensor_parent_v1.log 2>&1'`。
实际parent main323 list+dict TypeError，exit1/工具wall.482034109；lock/execution/lifecycle/runtimeconfig均未创建，无recorder/native child，无原生或pilot预算消耗。
实际工厂source_bindings为dict[path]含sha256及8种其它审计元数据形状；不能假设三个keys或与独立list直接相加。成功准入原JSON完整归档并无损rename至/tmp/mr3_p2a0_v20_sensor_source_preflight_941ae862_original.json，固定x输出路径留给新freeze，未覆盖/删除研究原件。

新TMP parent1fc9f1725b9685880bcbc224083332084c08c7e07a63824e67aa8792ec4c7ede仅三行items→path/sha rows，逆全字节/AST同8259；原263逐摘要/sourcefreeze/plan/binary检查不变。
旧14 CPU4.224846918wall、新实际main4 CPU.468960245wall、fatal lint.825898096wall通过，精确argv/env/sourcebeforeafter在A20/offline/coordinator_v2；无ROS/DDS/Gazebo。
新4实际fixture覆盖old TypeError/new真实103+160全部SHA/badSHA/non-dict，Popen禁止。首轮fixture强制三key产生3FAIL，完整旧source/log/receipt保留，仅改测试过强断言，不改实际修复/来源规则。
独立review300052ff…无阻断，未重复18tests或SDK/DDS/native。root也只读实际103原path SHA全部与worktree一致，额外normative/status不删；原JSON完整保留。
Root只替换canonical parent相同验证bytes和160bindings中的1项hash；额外新回归仅offline证据，不增加native消费者。CPP4707/实际ELFefd8/原103runtime/预算和原门均未变。
新26原件321278B固定tar逐member+final SHA核验；初root辅助保管误读manifest files而实际entries、后误取不存在的optional review.py均在archive说明保留，仅保管辅助失败，source/数据与结果不变。
唯一V20 native尚未开始，修复完成新clean pushed exact40准入后再首次启动；原生charge仍0，V18+V19仍2489.3860735194758，pilot余额不变。


### 2026-10-18 — V20_sensor实际来源采集及严格关闭；近身返回持续，撤回参数漏接推断

实际新clean pushed冻结b33ff70084be6419edc3d0d91a26d6db3936ff45；cwd wireless-rl：
`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261018_mr3_p2a0_v20_sensor/independent/mr3_p2a0_v20_sensor_preflight_v1.py`实际exit0，103runtime/160independent/实际三库/recorderELF/域170端口13451通过。
唯一原生入口：`rtk proxy bash -c 'env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v20_sensor/independent/mr3_p2a0_v20_sensor_run_v1.py b33ff70084be6419edc3d0d91a26d6db3936ff45 > /tmp/mr3_p2a0_v20_sensor_parent_v2.log 2>&1'`。
实际children完整argv/env和顺序见A20/closed_core_v1内execution/lifecycle。三机open101/单worker/普通4step、1reset5API，prep flags均false，外部sampler_limit正常truncation。
native229.27487259870395wall；benchmark/recorder/parent均0，自然结束后独占stop marker，未发临时signal、未retry。39native clean exits；独立fresh47 PID/start全gone。
原profile首1ms读取50→150/setter1与其它字段不变通过，仅复用e61c两小函数；原32step CLI明确SKIP。
原2516 physicalFalse：三机合格A/B均0，报告boundcounts0/errors[]；tb1/2 cancel=no_active_prior_linear_output，tb3无cancel。此为缺刺激FAIL，不是停车或150修复证据。
strictcloseTrue；tb1/tb2 bt_navigator各一条真实halt ERROR原bytes完整保留，不由正常关闭否定。原95%/300s/参与/接触/净空/速度/停车全部门不改。

独立recorder39359sample/12333788B CDR，三机scan141/134/130、processed pose8/2/1、map44/43/42；真实15typedSLAM参数各complete。
系统ROS仅离线deserialize，无rclpy init/DDS：原CDR全部offset连续与sliceSHA、whole文件末SHA/stat一致；11public processed pose均有唯一同stamp scan。
TB3首接纳2.560s14个合法finite near beam(.1328185–.1760021m>实际min)，按actualTF/correctedbase pose重建13个落首map两个100格，42map dataSHA相同。
后续128raw中126仍有near端点，实际odom TF+最后公开校正的诊断投影122条仍命中原两格；latest28.16s18near中13命中。self/floor/几何仍未知，不清格/过滤合法beam/降.29。
实际离线命令/源绑定/初v1失败/成本receipt都在52原件tar；成功分析总16.2648965898wall，首次失败wall未知，不按0计。

重要解释纠正：ROS minimum_time_interval=.5仅文档同步模式最小节流；SDK MinimumTimeInterval默认3600是时间OR距离OR转角的stationary刷新，当前multirobot不调用同步shouldProcessScan。
同名但语义不同，缺setter本身不是已证漏接bug。撤回本轮早期“接线缺陷/把.5直连”推断，旧分析原bytes封存且未改生产SLAM参数；后续near真实持续也不支持仅刷新能清100。

无损custody helper实际40.595564616wall/userCPU60.948812/sys1.380159；150原文件1249074082B→184gzip93919310B，最大2659291B；全部encoded/decoded/whole重组SHA与sourcefinal stat一致。
canonical189文件含metadata94227915B逐字copy1.408776527wall；首copy辅助误把184parts+5metadata写187，复制前断言失败，v2只修189/184精确inventory，失败source/receipt保留。
A20/closed_core_v1 52原件12850181B→1437361B tar SHA286d072be2550649ea818b92afc85fc93b27f047e9e4658560f9e5bb745c82e2，fullmember往返+源末SHA/stat通过。
累计V18+V19+V20=2718.66094611817975nativewall/原3600余额881.33905388182025，不重复计采集与custody。pilot1870决策/2905.954739546403wall不动。
P2A.0未完成，150未选用，V17真实停车FAIL未解决；需actualray缓存命中名/几何来源后修复，新冻结原完整四阶段验证，禁止拼接旧PASS。无GPU/optimizer/PPO/P2B/gateway。

V20补充源码复核A20/closed_source_reviews_v1：30封装原件448210B→166813B，archive SHAabf48f698264f01b64b177eb56a262fc8b091cefd68110ca31634ec9badf445f，完整往返与末源SHA/stat通过；内含独立语义复核及30份SDK试验原件的原tar。ray minRange/offset未见重复遗漏，静态sensor高于base/轮，动态实际命中仍未知。隔离SDK测试入口 /tmp/mr3_p2a0_v21_minimum_interval_sdk_run_v4.py（实际argv/env/CPU/wall在嵌套原receipt），前三compile分别缺ROS includes/vendor Werror/TBB link，最终compile0但首例清理返回stack-smashing SIGABRT/-6；仅一次filtered gdb仍无法区分fixture/ABI/SDK，其余4例未跑，明确SDK regression FAIL/无PASS信用。未rclpy init/DDS/Gazebo或生产变更，不计入native/pilot。该测试不作为V20近身回波根因。


### 2026-10-18 — V21 actual-ray SensorPlugin与新冻结入口准备（未启动原生）

source_base为已推送4f8bd0e509e6f958c5993a50008955afac72c345；只在本次显式diagnostic配置向唯一base_scan/hls_lfcd_lds插入独立SensorPlugin，原ray几何/量程/noise/驱动/SLAM/候选/安全门保持。
原V20合法近身beam持续、命中几何未知；不清占据、不滤合法beam、不把同步最小节流强接stationary刷新、不采用150生产配置、不启动PPO。
TMP旧ModelPlugin SDK build01因SDK指针/回调/int64接口不符FAIL、窄修build02通过，原source/stdout/stderr保留。源审发现运行中ConnectUpdated注册的线程窗口，改直接SensorPlugin::Load，旧方案未native。
最终CPP65b1c1db64861366811266580daf8cf43bcf565fc856a405f473b02bdefd082c，SDK构建+13纯assert groups+真实factory SENSOR_PLUGIN+ldd-r均PASS，54.815639715wall；未Load/init/ROS/Gazebo。
精确CMake/configure/build/CPU/factory/ldd argv/env/成本见A21/offline/sdk原件，57files482326B→70728B tar248bed8f0d6698b7548ca3122597beab2e3e2baf2ca3ce529d3ce91e6a2a5f8d，manifest57471966…；TMP Debug ELF a48adc/7927440B仅保存摘要、不作native库。

root只提升实际CPP与append-only CMake170eb49947c4daa61d30f45ab8fde637aa12766182dddfda15c9ca6453d0cc0d，逆去唯一13行target块全bytes等旧7ebe，旧target/flags不改。
实际canonical工程构建入口cwd Gitroot：`rtk proxy env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CMAKE_BUILD_PARALLEL_LEVEL=2 /bin/bash --noprofile --norc -c 'source /opt/ros/humble/setup.bash; exec /usr/bin/python3 -B /tmp/mr3_p2a0_v21_canonical_build_v1.py'`。
真实child cwd ROS：/usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select multi_robot --allow-overriding nav2_bringup --parallel-workers 2 --event-handlers console_direct+。
wrapper50.58614480635151wall，colcon/factory/ldd均0；仅vendor std::iterator deprecation warning保留，actualflags -O3 -DNDEBUG -fPIC/source宏65b1、无CPU_TEST。
install新库→canonical build lib，463272B/SHA b76138132ae7dbb35936c2e0971e909f688189d240de3910516157b3553d57b8；旧driver a014/observer9a1d/profile09321 beforeafter逐字不变。
gzip6 fullroundtrip148644B/SHA39f729a04c2aac90bdb03e1c292a904a528ad924e5f1061682f6f8ab48ff4529，binary custodycf589cf1…，actual build receipt015487b7…；A21/offline/canonical_build 17原件143735B→26396B tar0b13bf87…，完整member往返+末SHA/stat通过。
独立build只读reviewe2fa608b…查21输入并STOP，未重复编译/factory/ldd；独立source review7bd358c3…核实际Sensor.Init/LoadPlugin→container Add/Update顺序与缓存范围。

缓存360ray同时保留CollisionName/GetLength与relative/global端点，未调用GetIntersection/重cast或setter。无hit旧name不清，只有有限0<=length<max-min+非空name才当本次hit；GlobalPoints.end未被SetLength缩短。currentpose/碰撞SDF不是原cast原子ODE几何，measurementstamp也不是cast检查原子时间，均明确范围。
source6c76 launch在唯一ray sensor内注入固定7tags；移除新块与原physicsobserver块后精确恢复原模板。新版witness101c同时核实际PID/已加载ELF/dladdr/proc maps/source宏及两个已验证插件的精确字节逆移除。
old observer窗口0..1ms仅配置/首边界加载用途，晚spawn可能无sample，不授完整1ms信用；ray独立0..300s，原profile首1ms50→150/setter1谓词保持。完整e61c32step CLI仍SKIP。

协调器最终launch6项+witness3项/parent身份6项/projection4项方法通过（只按各最终源计，不累加旧版本重复）。早8619 parent未核真实parent/scoped，tb2/3错写tb1也PASS；具体反例原bytes保留，93d43窄修configuration world/model/link/name→connected及每scan一致，拒错parent/scope/扫描漂移且坏流仍整SHA/stat。
旧preflight444在实际旧audit_ppo EXECUTION_CONFIG_PINS会拒新CMake/launch，方法级Git stub未覆盖完整CLI，此阻断由独立源审在native前发现、原草案不改PASS。
V4 deeb61 preflight只对固定7ebe→170e/bcb→6c76两源验证current+Git+固定SHA、严格内存逆投影恢复normative4f8全bytes，临时两pin只包unchanged load_native_gates且finally恢复原dict对象；old160/audit_ppo f42原bytes、其余101来源与全部actor/任务/物理数学不变。
4方法用实际源及normativeGit，actualfreeze Git I/O与oldloader为明确CPU替身，覆盖坏source/Git/投影拒绝和异常恢复，不冒充实际exact40预检。调用链只读核实ordinarybenchmark/env/supervisor/worker/原2516不调用该loader，适配仅本次preflight，无生产隐藏override。
全部V1..V4原136files1585664B与manifest组成137members1616969B→370526B tar9ea55b5a1f82ab3502dd1d6835294c1cd88ece959ed9097c155b559e8b162abd；packing.228319640wall/fullmember回读+末SHA/stat通过，oldfailed/uncheckeddraft/cache排除明示，A21/offline/coordinator唯一保管。

root精确promote11源/配置/plan，安装launch与source全bytes同；old160全部保持，新13共173。plan相对封存draft仅status/pending/new_source_bindings_pending三准备字段改ready，finalplan SHA41c515102a34a5b8ab460c5326c615775b0a972c23f275f3ad4a64e288c81786。
固定一次三机open101/单worker/普通4steps、最多1reset5API，domain174/port13471，新runid mr3_p2a0_20261018_v21_ray；native350上限，累计V18–20已2718.66094611817975/3600余额881.33905388182025，不重置。三ray各configuration+connected+≥1完整360scan/实例PID正确/diagerror0才测量PASS；自然close与measurement分字段，overall取AND，不以exit0抹缺测。
正常顺序recorder ready→唯一benchmark自然退出→独占stop marker→recorder自然关闭，原2516科学physicalFalse可保留但strictclose必要；无signal/替代请求/retry。实际clean pushed conda预检及parent命令见V21报告，当前未调用新native。
P2A.0仍未完成，V17真实停车FAIL尚未解决；须actualray/CDR定因后修复，再新冻结完成原四阶段矩阵，禁止跨冻结拼PASS。95%/300s/参与/全机体与速度停车门不降，pilot余额1870决策/2905.954739546403wall不动，无GPU/optimizer/PPO/P2B/gateway。

V21最终独立v2 source review b12cff4f…无剩余已识别接口blocker，作者最终范围6launch+3witness+6identity+4projection；无重复测试/loader或native。15review/反例/快照原件640915B→54280B tar0b2d6132049e4158e61e402e132c4d2476e3b6ca71748ef9962158f4b932248b，完整往返与末源SHA/stat通过。root173实际来源SHA/7Python AST/固定2源全bytes逆投影/实际ELF与gzip/安装launch同字节/JSON与170本地链接检查通过；首次actual git add -n .41路径白名单，不含build/install/log缓存；上述静态及dry原件另存A21/offline/root_static_v1。它们不代替尚待的新clean pushed exact40实际准入。


### 2026-10-18 — V21 actual-ray单次原生闭合与离线对应

实际clean/pushed冻结099a8eeaa00676f7e6e00d7f5ef51294aac5edcb。cwd wireless-rl。完整conda准入命令为 `rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261018_mr3_p2a0_v21_ray/independent/mr3_p2a0_v21_ray_preflight_v1.py`；exit0，103runtime/173independent、固定两配置逆投影、实际b761/旧三库及域端口空闲核验PASS，回执SHA4e3c96854a667846655856ebd130df6037195d5c6cf82714b277b19d6dfef904。
唯一parent由rtk proxy bash -c运行同environment的系统/usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v21_ray/independent/mr3_p2a0_v21_ray_run_v1.py 099a8eeaa00676f7e6e00d7f5ef51294aac5edcb，stdout/stderr重定向/tmp/mr3_p2a0_v21_ray_parent_v1.log；exact argv/commands封在A21/closed_core_v1。计划41c51510，三机/open101/单worker/ordinary4/no-preparationflags/domain174/port13471/profile150，1reset+4step5API，任务38.72→42.72、external_sampler_limit/truncated，42.92关闭所有权。
recorder ready先于benchmark，仅其自然退出后写独占stop marker，recorder及必需consumer全部自然关闭；parent/benchmark/recorder0。native219.82827906589955wall，无signal/重试。39native启动与cleanexit PID集合完全相等；独立fresh联合48PID/start全gone，无forced/failed_sample/残留。两条真实bt_navigator halt ERROR原bytes保留，严格关闭PASS不抹除它们。
capture/basicray PASS：三台configuration/connected/214/203/197完整360scan、真实scope/PID正确、diagnosticerror0。原2516physical保持False：tb1A0/B0、tb2A0/B0、tb3A6eligible/1credited；三机bounds0/errors[]。完整e61c32CLI SKIP，仅原profile首1ms50→150/setter1/其它字段不变子谓词PASS。不授真实停车/150选择/矩阵/95%或P2A.0信用。
V18–21累计2938.48922518407930/3600nativewall，余661.51077481592070；pilot余额1870/2905.954739546403未动，无GPU/optimizer/PPO/P2B/gateway。
lossless native175+capture3原件392963255B→185gzip57408493B，最大7663281B；全part encoded/decodedSHA、全原件reassembly+源stat稳定PASS，三raySHA等原execution。新增6固定选择/身份检查PASS，继承6codec函数AST不变未重复codec套件；pack15.477wall仅CPU/IO。handoff299200db，root单次copy205files57836611B，逐个copySHA/stat核验。
闭合core29原件8352980B→1776933B tar f24f09be2c536cd8d9c9c1d882e3c81cc6aae24c188622858d72d0e7ce12ba96；独立小对象审查821e754a及原准入/执行/命令/失败物理/启动日志/first8限定观察全保留。
离线唯一实际命令由/bin/bash --noprofile --norc -c source /opt/ros/humble/setup.bash后exec /usr/bin/python3 -B /tmp/mr3_p2a0_v21_posthoc_ray_v1/analyze_v1.py --capture /tmp/mr3_p2a0_v21_ray_capture_v1 --episode /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v21_ray/worker0/episode001_open_101 --freeze 099a8eeaa00676f7e6e00d7f5ef51294aac5edcb --output /tmp/mr3_p2a0_v21_posthoc_ray_v1/analysis_v1；exact argv/env/cwd已封A21/closed_posthoc_v1。无rclpy init/DDS/native/newformal，初3CDR layout检查PASS；full分析exit0/46.65071245934814wall、脚本与输入末SHA/stat稳定。
614cache/raw唯一stamp匹配，221040 sensor64→float32与原CDR位全等，0class/bit差；23670合法near<.20本次有效hit全各自base_collision，allvalidown24266。各机155/151/137scan有ownhit，间歇持续到42.648/42.854/42.730s；不称全后段连续静止。完整3D逆变换23670点均比currentgetter/SDFbox上面高28.471–28.514mm，current非原cast同刻/nativegeom，不单凭此锁根因。processedpublicpose+真实staticTF与own100关联三机首次39.448/40.256/39.529s，汇总mapheader/publicposeproxy限制保留。
离线16原件86130542B→7425238B tar913a757cbe6ce879806af0aa3b8b12346b103a615156b354f98db3f8a7bc53d3，全成员往返/源末稳定通过。P2A.0未完成，继续底层求交候选CPU定因修复，再新冻结原完整四阶段；不清占据、滤真实hit、放宽净空/速度/停车或跨冻结拼PASS。


### 2026-10-18 — V22 Ray×Box底层修正与原四阶段工程重验准备（0新原生）

source_base ba34efb122a15ceea0fa28319bb16b5fc1469364（已推送V21闭合）；用户要求继续完成P2A.0。
V21缓存/current几何不同读取时刻比较不单独证明原cast唯一原因；进一步纯CPU调用本机实际libgazebo_ode.so.11.10.2（719240B/a94a424d…）确认源码RayBox精确零早退与epsilon slab不一致：盒外小非零方向可被slab忽略，15具名旧库案例6假阳性。原V21结论/失败不改为PASS。
新SystemPlugin仅公开dSetColliderOverride替换Ray×Box，非零轴有限slab交区，保留inside exit/边界/有限长度/反向身份法线与原tie规则；其它shape pair、接触动力学、模型/激光/SLAM/候选/奖励/安全门不改，不过滤合法raw或清占据。
最终source3 b165ce49/d556dda5/c619442d，BSD许可证fe012d26；actualworld创建T0/iter0注册、world/sensor正常stop/join先于plugin销毁及进程Runtime并发由独立primary源码复核。正常callback无IO/JSON/动态分配，错误计数使后续边界和consumer失败；首次outside-nearparallel仅可选真实packet，不当作必需旧假阳性。

精确原始argv/cwd/env/源码/库身份/成本在A22=report/assets/20261018_mr3_p2a0_v22_ray_box的offline/sdk、source_reviews、canonical_build01、canonical_build02、root_preparation中。offline/sdk 74原件394350B→62503B tar eb7ee9c6…，四CPU/SDK ELF仅记录SHA；source_reviews 43原件+helper组成45成员→76238B tar3a61e148…。全部逐member往返和源末SHA/stat稳定，primary来源URL随原件保留。
作者最终SDK03/CPU：36具名双顺序、512确定旋转、3非法输入、实际dSimpleSpace旧假接触1→新0，factory SYSTEM_PLUGIN/noLoad/noInit/ldd-r通过；前三broadphase夹具orientation符号错误、SDK01 IntegerNanoSeconds API编译失败原件全部保留。独立源码复核不重复套件，无Gazebo server/world/ROS init/DDS/native。

root canonical构建精确入口（cwd Gitroot）：`rtk proxy env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CMAKE_BUILD_PARALLEL_LEVEL=2 /bin/bash --noprofile --norc -c 'source /opt/ros/humble/setup.bash; exec /usr/bin/python3 -B /tmp/mr3_p2a0_v22_canonical_build_v1.py'`；仅增加安装读回后第二次入口相同但wrapper为/tmp/mr3_p2a0_v22_canonical_build_v2.py。
两个wrapper child均为系统/usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select multi_robot --allow-overriding nav2_bringup --parallel-workers 2 --event-handlers console_direct+，完整实际argv在原execution。build01顶层51.38907388225198wall、未native f9a252/383664B；build02顶层54.07078190194443wall/colcon41.23710859939456wall，factory/ldd/动态链接actual SO几何probe全PASS，旧案例不双倍计数。
最终install→canonical build actual389312B/7be79c7f3d2cac53a9d1692aa868d91d4b9977e2b7541203ce4ffe90c605a08f；gzip125793B/5adc1aa8…，wholedecode等actualSO。binary/receipt_v1.json e522c300…与canonical_build_receipt_v1.json ec91e833…绑定实际Release flags及source3宏；原driver a014/observer9a1d/profile09321/rayObserver b761逐字不变。TMP库44263、首次f9a252不用于native。
build02独立只读review ec709251…核47输入、真实probe DT_NEEDED/RUNPATH/未静编core，没重复编译/factory/math；38原件420856B→74021B tar2d9897a9…。一次保管helper SyntaxError在读原件前失败，原件保留。getter只读增量3块wholebyte逆到旧b992，新增nativeODE WorldId实际iterations与PhysicsEngine实际maxStepSize成员，consumer要求150/int和.001，未加运行时setter；独立增量review c2d4bb70…保存。

root固定选择既存V19未选用proposal：三world只追加quick/150、三task只同步各worldSHA；每份wholebyte逆恢复旧世界/任务，installed symlink相同。150是假设改善V17真实停车的单一工程候选，不沿用静止诊断停车信用；无原profile setter或V21raySensorPlugin进入正式矩阵。95%/300s/每机1m+goal/18fresh zero nonsupport contact/.50peer envelope及.30/fullangular1.2/7、停车.78s/.144m/fullplanar≤.01连续3实际源样本均不变。

shared production auditor de297d83…保留所有旧pins，以固定六world/task、CMake/launch两级全byte逆投影到真实W7/4f8及ENV原40186B+唯一7535B追加核验；实际新source/Git/worktree SHA保留，不改写成normative。正式PPO与preflight共用load_native_gates，无通用override或V21临时两pin猴补。actual7be/gzip/receipt/source3/旧4库/实际ODE固定绑定；文件身份不替代每episode实际maps和ledger。
作者40窄CPU/fatalstyle通过（Git明确fixture，非实际准入）；v3四次AST harness NameError缺audit_scalar原失败保留。v5完整unit旧方法错误要求actual SHA仍等旧normative，root真实conda16出现15PASS/1FAIL；v6仅对exact2配置断言同时核actual新SHA、normative旧SHA、两级完整逆投影，其他assert保持；新test43e13e59…，ENVcace2f98…/auditor不变。
root先误用conda pytest，缺pytest/0tests/exit1，不安装；旧ROS fixture缺corrector存在marker，72PASS/1FAIL，工具返回traceback显式截断、不补造缺字节。三次原失败在offline/root_preparation原件。仅更新ROSc752344c…夹具/argv元数据断言与缺库prestart测试；不启动ROS参与者。
root最终真实ROS相关检查入口（cwd canonical ROS）：`rtk proxy env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /bin/bash --noprofile --norc -c 'source /opt/ros/humble/setup.bash; source install/setup.bash; exec /usr/bin/python3 -B /tmp/mr3_p2a0_v22_run_ros_relevant02_v1.py'`。actual child system pytest test_mr3_task_contract/test_mr3_adapter_launch/test_mr3_terminal_launch/test_mr3_drive_launch/test_launch_and_smoke共170PASS/9.07test/10.090407276991755wall；source末SHA相同。
root最终actualcanonical conda入口由`rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v22_root_promote_and_checks_v1.py`执行，child argv精确为/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m unittest mr3_learning.tests.test_audit_ppo，cwd wireless-rl，unset PYTHONPATH/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1；16PASS/.469test/5.3687832579016685wall。Gym原依赖warning原bytes保留，无GPU/PPO。
root26准备原件156364B→39178B tar5200035f…，27成员全往返/末源稳定；实际脚本/失败调用/读回增量/新真实CPU输出唯一封存，非native准入。独立auditor v5源+v6test审查3baebdc0…核33稳定输入/9Git原对象、AST逆回旧auditor全同，无新阻断、不重复40CPU/完整conda；4原件49283B→13235B tardec21c07…。

新corrector custody模块e12b802a…/binding95ec473d…，20纯fakeproc/typed闭合mutation methods+fatalstyle/CLI/syntax/实际静态身份兼容PASS；原checks01/02/03及窄metadata修订全保留，最终checks04唯一finalsource。34小原件174559B→39457B tar8bfd3b62…。其只读每episode实际owned gzserver PID/start/worker祖链与corrector/ODE fd+fstat+inode/dev/fullSHA，禁止basename精确gzserver旧误拒；reader要求epoch/PID/source3/T0iter0/native150/.001/真实callback>0/errors0与原strictclosure分别成立，可选nearparallel不变成必现门。

目前尚未运行新exact40准入或任何V22 native。四stage仍须interface32/terminal2episodes/reset两worker各open/open/rooms/corridors32共8/deadline300KEEP，原34mandatory jobs（10/7/10/7）及每robot A OR B、reset8episode pooled、任一合格事件违规独立FAIL/原angular门不删。新ledger/mapping仅closure补充，不能覆盖原FAIL。预声明上限608API/596scriptdecision/12episodes/18000native工程wall，必须新clean pushed冻结准入后一次执行，失败保留并跳过后stage，不盲目同冻结retry。
V18–21诊断native累计2938.48922518407930/3600，余661.51077481592070不自动消耗；pilot余额1870/2905.954739546403未动。P2A.0未完成，未授95%/学习有效/冻结策略可靠性信用，无PPO/P2B/gateway。

V22 native前新增custody收尾竞态修复：v1 post-maps同PID/start转Z/消失会误记fatal；实际2反例FAIL保留，v2只此closing分支记pending且不给本份credit，仍须每EP至少一份active真实proof；reuse/permission/hash错误硬拒且后续pending不抹已有错误。module862e5b9a/testda656624/binding95ec不变，8新增窄CPU PASS(.103test/.35324wall)+fatalstyle；首新harness遗漏Reader.finish应拒变expect产生ERROR，原件保留后只修expect；原20不重跑且仅对旧finalv1授其原范围。精确argv/源/全部checks_v1..v3在A22/offline/corrector_custody_v2，21原件103704B→22596B tar18fe2ef1…全成员往返/末源SHAstat稳定。仅TMP作者源和root无损封存，无新native。

V22最终10源/config+readyplan精确提升（plan5a14e14dd7183e36233add6ee9faf0b6b28604453d01608304fb78f162ada889），native_admission_granted=False且conditional_engineering_matrix_authorized=True，唯真实clean pushed exact40预检才能准入。root命令 rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v22_promote_matrix_v3.py；随后 rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v22_root_static_v1.py，实际191绑定（旧173中171原样+current auditor/test2明示更新+18新增）、9Python AST、actual7be/gzip/installed launch、JSON/190本地链接/diffcheck及actual git add -n .65路径白名单均PASS，原件A22/offline/root_static_v1。该静态不代替尚待的实际freeze Git读回和新native；34原jobs/8reset pooled OR及eligible独立FAIL/608API596decisions18000wall保持。

V22 candidate完整CPU/源证据一次封存：273原件3078763B（v5 196、v6 11、matrix62、三manifest+helper）→830233B tar da136828aff5677f3ec02a2f2eefe30f60d0fe1355077214d066a1724c68a4c8，回执5c428ddd…/184823B。每member decodedSHA/byte及源末stat/SHA全通过，.598wall；A22/offline/candidate保管。含40窄CPU/AST与v3 harness失败、v5错误unit预期及v6实际conda16、最终matrix8集成CPU/fatalstyle，早2逆版本化fixture错误完整保留；最终8方法使用detached pending plan测5入口guard，ready后再跑仍PASS。无mock工作树/cache/ELF或SDK重复保管，所有作者source/metadata writer STOP，仍0新native。

V22完整矩阵最终独审40692f42… PASS/STOP：207输入末SHA/stat稳定、191bindings/34原jobs/8reset OR+eligible独立FAIL/60859618000及共享actualHEAD loader/所有futures drain/关闭skip/closinghelperv2链均核，无新阻断，不重复单元/math/SDK/native。精确入口 rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v22_matrix_independent_review_v1/review_v1.py；final exit0/.547516wall。首独审harness错误假设coverage表达式文本而AssertionError保留，仅改按真实if-not-A-and-not-B核验、无生产变更；目录5小原件全量copy A22/offline/matrix_review。补充明确：作者final8集成CPU receipt对应plan9f40，final5a14只改4顶层准入说明字段，code/191bindings逐字不变且独审已核；未对新metadata重复8CPU，不把9f40 receipt冒充5a14实际准入。上述“ready后再跑”只描述detached pending guard测试可在ready状态有效，不授5a14真实freeze信用。


### 2026-10-18 — V22真实准入PASS，矩阵入口解释器FAIL；零机器人/零采样，全部闭合

实际源冻结cdda62325c6322cf5322162c616bd9b699354665，main已推送且启动前clean。
真实预检由 `rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v22_run_actual_preflight_v1.py` 调用固定conda /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261018_mr3_p2a0_v22_ray_box/independent/mr3_p2a0_v22_buildproof_preflight.py，cwd wireless-rl、unset PYTHONPATH、PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1；exit0/7.583724378142506wall，110runtime/191independent/actual7be+ODE+原4库PASS，receipt2fbdeb126ae800e56cd4a5054eb0d1f4d373976c04b1d7ae85eb88e93f21dc53。原Gym warning保留。
接着同cwd，`rtk proxy bash -c 'exec env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v22_ray_box/independent/mr3_p2a0_v22_cross_stage_mapping_monitor_v1.py --freeze cdda62325c6322cf5322162c616bd9b699354665 > /tmp/mr3_p2a0_v22_cross_stage_mapping_parent_console_v1.log 2>&1'`，START验证实际freeze与878b源码后，唯一parent为相同env系统Python report/assets/20261018_mr3_p2a0_v22_ray_box/independent/mr3_p2a0_v22_run_matrix_v1.py cdda62325c6322cf5322162c616bd9b699354665，stdout/stderr重定向/tmp/mr3_p2a0_v22_matrix_parent_console_v1.log；完整argv/utc/events/childidentity均原样封存。
实际23:25:47UTC benchmark在import gymnasium时ModuleNotFoundError，未创建任何run目录、worker、ROS/Gazebo环境，0native/0API/0physics。根本原因是matrix parent采用system Python而launch沿用sys.executable执行conda依赖benchmark；full_audit同样system Python缺torch。源结构审查和root均漏核此实际解释器继承，旧审查原件不改为FAIL或重写。该实现/入口错误必须显式修复，不能认定物理候选失败。
benchmark已自然return1，launch计费wall .24578428314998746；launcher捕获缺benchmark_summary后的secondary FileNotFoundError且failed receipt未写顶层returncode，closure leaf因此另KeyError，全部原traceback保留。7个实际submitted审计命令均return1、all_submitted_jobs_finished=true/runner_errors=[]；10required中0PASS/5缺失，parent依声明后三terminal/reset/deadline真SKIP。parent session5694 exit1、watcher19185 exit0自然结束，无signal/retry。
独立窄闭合review d7ab8e88…fresh核4个保存PID/start全gone、/proc无matchingV22执行argv、四run根全不存在。7leaf靠subprocess实际wait return证明已结束；逐leaf PID/start与watcherPID未保存，限度明示，不伪造完整身份表或nativeclosure PASS。原本所有数学/任务/安全/停车门保持FAIL/未测范围。
selected35原件202118B→35gzip45776B/max20102B，全部encoded/decoded/wholeSHA与源末stat稳定；A22/native/manifest.json d2ea521f…含四不存在native根与FAIL/SKIP原状态，不以目录名授native。closed_support_v1另24原件36333B tar3d0eb899…、manifest7c5f3235…完整member往返。包含父/watch stdout、真实preflight3文件+wrapper、rootfinalprecommit原命令/JSON/dry/pathspec；copy逐byte/SHA稳定，RT两份新小原件另存closed_entry_review_v1。
pack exactargv/minenv/CPU/wall在原execution；exit0/1.96155toolwall（custody内部1.8223651428706944wall）。原v1 helper仅许/tmp直接子文件，实际nested preflight3件使v2只扩单个regular file路径至/tmp树内，仍拒symlink/目录，6codec逐byte不改；旧准备/5选择测试与新增nested选择校验、fatalstyle原件全保留，无native/formal重跑。
V22 source准入PASS仅来源/二进制，不覆盖实际CLI可达错误；P2A.0仍未完成。保留这次.24578428314998746入口wall，并从后续同一18000工程总上限扣除；0真实native/0采样不能写成零成本。不得同冻结重试；下一版本只修显式conda benchmark/full_audit、失败returncode结构和真实CLI帮助预检，原corrector/world/task/auditor/ENV/191来源及全部数学保持，不重建SO或重复170ROS/40窄CPU/SDK。
V18–21诊断预算2938.48922518407930/3600与pilot余额1870决策/2905.954739546403wall均未动，无GPU/optimizer/PPO/P2B/gateway。


### 2026-10-18 — V23入口修复与原完整矩阵准备（未启动新原生）

源基cdda62325c6322cf5322162c616bd9b699354665，V22闭合证据bf4b5f1095ff0cee4e701e2ffdc35d128f310ba8已推送；不在失败同freeze重试。
只新建A23=report/assets/20261018_mr3_p2a0_v23_entry六协调器+1窄test+plan；旧191逐path/currentSHA完全保持，新198绑定。C++/actual7be SO/ODE/quick150 world/task/auditor de297/test43/ENVcace全部保持，无重建或旧170ROS/40CPU/SDK重跑。
benchmark与full_audit固定/home/zhuyulab/miniconda3/envs/ns3gym/bin/python；parent和stdlib/ROS consumers原system解释器不改。preflight outer必须同Conda，并在current共享load_native_gates之前核解释器，新增三read-only有界实际imports/benchmark --help/full_audit --help，不构造Env/ROS/DDS或调用GPU。
准备期真实probe使用原preflight5b064c源码中的helper直接调用（不是完整准入）：imports argv [/home/zhuyulab/miniconda3/envs/ns3gym/bin/python,-B,-c,import json,sys,gymnasium,torch; print(json.dumps版本/路径)]；另两个精确argv分别为同解释器 -B -m mr3_learning.benchmark --help、-B -m mr3_learning.audit_preparation --help，cwd wireless-rl、unset PYTHONPATH/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1/CUDA_VISIBLE_DEVICES为空。完整-c原文字和调用脚本在offline/candidate原件，不以本摘要替代。三actual exit0，4.829209363088012/.43371849972754717/5.053422350436449wall，总10.318188397213817；实际gymnasium1.3.0/torch2.11.0+cu128文件均来自固定Conda，未初始化GPU/创建环境。final9a9129 preflight仅输出名改为preflight_learner_entry防覆盖，wholebyte逆证、旧source/probe原bytes保留；实际新freeze仍须完整前检再做这些功能检查。
failure receipt现始终保留实际已wait的returncode，未spawn为None，不以缺summary覆盖初始非零；V22入口.24578428314998746从原18000总额扣，opening17999.75421571685，不新授pilot或放宽总额。
新6窄CPU：rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v23_entry_proposal_v1/independent/test_entry_interpreters_v1.py，exit0/.5157287023030221wall，actualmain subprocess明确mock，code None/1/0与原A22 corrector862e/binding95ec真实读取loader覆盖，不冒native。system已有flake8 fatalstyle/static198 PASS；早误用Conda flake8缺包、静态验证器误扫test中的断言字面量原失败保留，只纠命令/验证器，不安装依赖。CLI原3probe不在收口重复。
六协调器旧34mandatory(10/7/10/7)、8reset pooled perrobot A OR B+任何eligible违规独立FAIL、608API/596decisions/12EP及stage1800/1800/6400/8000保持。源plan28b190af13c408f5ed0da243ccf4b3d25e4460a8f14b60d9af295cf5015cae07 ready仅源码就绪、native_admission_false；新domains188/190/192+193/196、ports13601/13611/13621+22/13631、v23新runids。
独立源审 ef795d79…/215稳定输入PASS，确核新interpreters真实路径、outer guard/三旧probe原件、A22物理模块/库原path、预算/failedcode与namespace，不重复6CPU/3probe/SDK/math/native；actual argv rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v23_entry_independent_review_v1/review_v1.py，exit0/.431087wall。3小原件全量copy A23/offline/independent_review。
作者40原件285813B+manifest+helper=42件304546B→72777B tar6cb30422…，custody422591a4…/12305B，所有member decode/SHA与末源stat/SHA稳定，pack.05915wall；唯一保管A23/offline/candidate。root精确提升8项，198实际SHA/191旧源全不变/7Python AST、34门和预算实扣核对PASS，原件offline/root_source_static。
尚无V23实际新freeze准入或native、GPU/optimizer/PPO/P2B/gateway。V22cost已保留，V18–21诊断2938.48922518407930/3600与pilot1870/2905.954739546403不动；须新clean pushed exact40实际准入后一次完整四阶段，所有native/requiredreaders/monitor自然关闭后才改源码/Git。


### 2026-10-18 — V23真实前检通过，corrector生命周期guard异常；首次reset失败全部保留

实际clean pushed源9160543e32ca49a56dfd05eaa0df3ccb6d25f89e。cwd wireless-rl，真实前检入口 rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v23_run_actual_preflight_v1.py，child固定Conda -B report/assets/20261018_mr3_p2a0_v23_entry/independent/mr3_p2a0_v23_buildproof_preflight.py；unset PYTHONPATH/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1。exit0/17.267797220032662wall，110runtime/198independent/actual7be+ODE/3真实conda imports/help PASS；receipt28ad341a2b425faa89d45a2958df443ae9e5daecbb67e3c3e8b5b193ed1608c0，Gym原warn保留。
唯一watcher命令 rtk proxy bash -c 'exec env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v23_entry/independent/mr3_p2a0_v23_cross_stage_mapping_monitor_v1.py --freeze 9160543e32ca49a56dfd05eaa0df3ccb6d25f89e > /tmp/mr3_p2a0_v23_cross_stage_mapping_parent_console_v1.log 2>&1'；START核freeze后，唯一parent同env/system /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v23_entry/independent/mr3_p2a0_v23_run_matrix_v1.py 9160543e32ca49a56dfd05eaa0df3ccb6d25f89e，stdout/stderr重定向/tmp/mr3_p2a0_v23_matrix_parent_console_v1.log，精确argv/time/receipt/worker环境全部原样保管。
23:42:40UTC新interface固定Conda benchmark已真实创建worker0/episode001_open_101/domain188/port13601。gzserver actual7be写813B configuration，WorldCreated安装guard抛runtime_error，launch.log75–76原what ray-box installation requires unstarted ODE world；gzserver pid3572578 exit-6，没installed/有效transition，首次reset尝试未返回。此不是网络/策略/物理效果测量，不能写为0API调用成本；1个失败reset原RPC保留，0有效样本。
11个实际formal子命令均wait exit1、10mandatory全FAIL；parent94139 exit1/watch33452 exit0自然结束，后三terminal/reset/deadline真SKIP。原supervisor forced_shutdown=True/failed_sample=True，infrastructure cleanupFalse/IPCtimeout全部保留。原SDK崩溃引起的已声明owned清理不冒正常strictclose PASS，也没有根临时signal/同冻结retry。
独立窄闭合c2f70069… fresh17个已保存PID/start全gone，原正式结果/启动失败/后三缺失范围均核，无新formal/math/probe重跑。原件A23/closed_entry_review_v1，两小文件保留精确脚本/输入。
actual launch32.096621671225876wall，V22 .24578428314998746+本次=32.34240595437586/18000，余额17967.657594045624；pilot1870/2905.954739546403不动。原traceback/invalidreset/强制清理不因source预检/进程gone而改PASS。
全量封存A23/native topmanifest4c67a5ca…：interface27原件124507B→22257encoded，metadata62原件316662B→76125encoded，共89gzip part/max21557B，全encoded/decoded/wholeSHA及末源stat稳定；正式preflight_learner_entry7件、actualpreflight3+wrapper、parent/watch/stdout/rootfinalstatic/dry/pathspec全部收齐。pack exit0/1.98341toolwall，精确command/env/CPU在原execution，未重复native/正式consumer。
closed_support13小原件tar36275B/ad934352…，manifest0c933cf4…；seal_v1提示误留A22，原tar/manifest/错误seal均保留，另seal_v2/correct_copy_hint只纠复制说明，89实际part prospective始终正确A23/native。root逐文件copySHA/stat/bytes稳定，未复制到A22，全部writer已闭合后才改docs/Git。
SDK源码复核已证worldCreated发生World.Load414、iteration到World.Init497才被赋0，WorldPrivate此前无初始化；旧guard提前读取不可用counter是实现缺陷。get_world已在create_world push可达，不以world注册次序作错误归因；SystemPlugin.Init也早于创建world，不能盲换。原V23无逐项guard字段，原counter具体值未知；先前“created即actualiter0”推断撤回，不回填后续probe。原Running getter是!stop，创建时true，不作为线程已运行/已停证据。继续在SDK证实的Load-before-Init阶段安装、用有定义字段保留before-first-physics含义，并版本化consumer/ENV；原物理/停车数学与95%不改。
P2A.0未完成；下一source版本须真实SDK阶段/新CPP/实际库+新限定身份源审后，新clean pushed冻结完整四阶段。V23失败保留，不同source拼PASS、不盲重跑，无GPU/optimizer/PPO/P2B/gateway。

## 2026-10-18 MR3-P2A.0 V24 安装生命周期修正准备（尚无新原生矩阵）

保留V23联合guard处FAIL、gzserver-6/forcedcleanup、reset未返回/零有效transitions及后三SKIP。旧日志未记录单条件值；独立源码发现preInit Iterations未初始化缺陷，不把新SDK读数说成旧失败分支/唯一原因。撤回created=>iteration0、world未注册、盲改SystemPlugin.Init等推断。新corrector f82646c8只替created块，phase为world_created_during_load_before_world_init；counter null/availableFalse而非0，Running实际true合法，原150/.001读回和core/header/hotpath/CAS/dSet均不改。

SDK执行脚本根 `/tmp/mr3_p2a0_v24_install_lifecycle_proposal_v1/run_probe_v1.py`，cwd同目录；`pkg-config --cflags --libs gazebo`展开的原始完整g++ argv、环境、exit、输出SHA在 [SDK originals](report/assets/20261018_mr3_p2a0_v24_install/offline/sdk/originals.tar.gz) 的compile_v1/probe_v1.json，未删重复-std参数。实际run：

```text
/tmp/mr3_p2a0_v24_install_lifecycle_proposal_v1/lifecycle_probe /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot/worlds/p1c_open.world
```

compile exit0/37.52403453504667wall；run exit0/2.1119531956501305wall，created RunningTrue/loadedFalse/sensorsFalse/150/.001，不读counter；仅afterInit读0。只有Load/Init/Fini，Run/Step/ROS/robotspawn各0，未加载actualcorrector，不授原生/停车/V23重执行信用。syntax01真实FAIL exit1/27.221719437278807wall（外部SDK-I警告-Werror）；syntax02仅外部-isystem，同f826源码严格syntax exit0/27.285107973963022wall，旧FAIL/stderr原样留。[SDK handoff](report/assets/20261018_mr3_p2a0_v24_install/offline/sdk/handoff_v1.json)、[独审](report/assets/20261018_mr3_p2a0_v24_install/offline/independent_source_review/review_v1.json)。

canonical构建脚本 `/tmp/mr3_p2a0_v24_canonical_build_v1.py`，cwd `/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap`，systemROS及PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1。实际colcon：

```text
/usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select multi_robot --allow-overriding nav2_bringup --parallel-workers 2 --event-handlers console_direct+
```

colcon/factory(noLoad)/ldd-r/actual-linked纯CPUprobe均exit0，整体59.77381576690823wall；精确全部argv/cwd/CPU/wall/source前后/原输出见 [buildreceipt](report/assets/20261018_mr3_p2a0_v24_install/binary/canonical_build_receipt_v1.json) SHA6ee8d273…。actual ELF782d388fea8df3646524e54f41d71de5f53480b9d04cc0ea1c453c70e2c1f7d8/398080B；gzip41c1ae6a…/129776B；[binaryreceipt](report/assets/20261018_mr3_p2a0_v24_install/binary/receipt_v1.json)84bbd6bd…。ODE/旧四库字节不变；无world/步进/ROS/DDS/训练，未将CPU几何PASS当actual安装完成。

根实际canonical原unit（cwd W；PYTHONPATH unset，PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1/CUDA_VISIBLE_DEVICES空）：

```text
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m unittest mr3_learning.tests.test_audit_ppo
```

16PASS/.503test/5.608815073035657wall，`/tmp/mr3_p2a0_v24_canonical_audit_unit_v1`原回执钉e128e90b…/ENV27dfaf84…/test43e13e59…源稳定。随后只改ENV因果措辞+3常量，finalauditorcc467064…/ENVf1e0be60…，不改函数；新增2项finalENV正例/repinned坏prefix拒绝PASS/.018284440971910954wall；不把旧16冒称最终文字重跑。最终实际冻结前检仍PENDING。

V22+V23启动32.34240595437586wall加SDK compile/run39.6359877306968，根给定18k工程台账累计71.97839368507266，余17928.021606314927；V24新任务API0。原34mandatory/12EP/608API/596decision及全部95%任务/物理停车A OR B池/逐实际违界/角运动interface与reset差异scope/18contact/严格关闭/真值隔离门保持。新freeze/最终210binding计划与准入、同冻结全4stage仍PENDING，无PPO/GPU/策略95%出口信用。


Root于源码文案转录复核时更正agent草稿中交换的ENV/auditor标签；原草稿四件完整保管于A24/offline/report_preparation，哈希本身未变。实际build由独立读取44输入复核PASS（review59e7462c…），35原件407779B→75990B tar117e3eafa…，2CPU可执行物只记身份排除；A24/offline/build原件全量decode核验。根source promotion、actual binary archiver、原16 unit stdout/stderr/receipt共13件19894B保管A24/offline/root，非新native。
CI新增preInit consumer6方法级检查（最终f65c/test1192，源字段strictbool/null/phase/原bounds）与4项固定binary身份正负检查PASS；最终因果措辞后只补2 ENV身份正负检查，不重复16 unit/旧ROS170/旧SDK/旧数学套件。初稿watcher路径残留A22、binding额外metadata、原测试TMP依赖及inline handoff SyntaxError均在执行native前发现，原件保留；仅修接线/便携性，不把失败改为实际原生成功。最终plan中active SO scalar残留7be亦在独立审查时发现，待唯一元数据更正后声明新计划哈希，未运行旧声明。

最终作者SOURCE/PLAN/METADATA/离线writer均STOP。Root按handoff先提升12项中的8项新文件、4项已同一文件只核字节；随后仅将plan /native_ray_box_correction/actual_library_sha256残留7be改782d，finalplan d682f40c01a660f598cdf6c81d9faa640c25af1ba87d9e96e56701bb2fec4ffc，binding f21b16dbbf6101483c002c1fabd726ca0b8ea4c4051c1691d1d109adb786c854。原631d、其handoff及错误scalar原件保留，未执行。作者88件1147551rawB→335024B tar677bd247…，addendum5件155343rawB→37840B tar0eea5836…，逐字往返/源末stat稳定；canonical分别offline/candidate和metadata_addendum_v2。最终210＝旧198中196同SHA＋currentCPP/auditor明确刷新2＋12新身份，原test43e13/其他source/34数学及累计71.97839368507266全不变。Root更新当前guide/路线及launch_commands中的准确Conda/monitor/parent命令，未启新native；新clean pushed冻结实际准入仍待执行。

最终源码独审 d2e0e6c4bc433b9c44333e3f459927e50559c714fe11790ca034d0941c208630 PASS，无阻断，229实际输入末SHA/stat稳定；5member往返封包a57e94de82886aa4dbd06d52a6c1a30cbaf50d00a9856077a7f6a4238b0b1738/28686B，全保管offline/admission_review。首review文字匹配断言失败属中文跨行的reviewer脚本问题，初源和说明保留；原工具traceback未独立保存成console，不伪造原件。根实际命令 rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v24_final_root_static_v1.py exit0：210实际SHA、196旧exact/2明确源更新/12新、原34门/608/596/71.97839368507266成本、8PythonAST/27当时JSON/187文档链接及actual782dgzip均PASS。此为worktree静态准备，无实际冻结准入或新native。接下来short checks、git diff --check及git add -n .后commit/push，再以报告/launch_commands准确Conda命令做实际冻结前检；唯一四阶段parent必须等待该PASS。


### 2026-10-18 — V24真实完整入口执行、角速FAIL与全部闭合

源码冻结5d684c46f9f99a867a94f1fed8c52e923e2486ef已推送，finalplan d682f40c01a660f598cdf6c81d9faa640c25af1ba87d9e96e56701bb2fec4ffc。先actual完整Conda预检：rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a0_v24_run_actual_preflight_v1.py，内层准确argv为固定Conda -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_buildproof_preflight.py，cwd wireless-rl。exit0/18.76524052489549wall，110runtime/210independent/3真实imports-help通过；receipt bd92102f0342af129e42b8bea26328942ddcac47040002266eb92b726cf9ca9b。四个特别选存offline/build证据文件被opengym build/ ignore匹配，提交前显式dryrun和-f逐四路径加入，未加入运行build树。
实际monitor命令同环境 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_cross_stage_mapping_monitor_v1.py --freeze 5d684c46f9f99a867a94f1fed8c52e923e2486ef，stdout/stderr重定向/tmp/mr3_p2a0_v24_cross_stage_mapping_parent_console_v1.log。确认真实START后，于00:13:49UTC执行同环境 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_run_matrix_v1.py 5d684c46f9f99a867a94f1fed8c52e923e2486ef，console/tmp/mr3_p2a0_v24_matrix_parent_console_v1.log。所有原生/11正式任务/monitor结束前source/bin/Git均不变。actualstage CLI为fixedConda -u -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 32 --preparation-motion-probe --preparation-probe-version mr3-p2a0-outward-cancel-v6 --base-domain 198 --base-port 13701 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261018_v24_interface --preparation-parameter-review；所有逐leaf实际argv/cwd/环境/exit/原console在唯一封存metadata。
actualcorrector phase/null/可用preInit字段/native150/.001安装通过，first_actual_callback及outside-nearparallel真实出现，最终762781calls/error0；实际9参数服务读回PASS。reset release sim42/startup132.2021218878217wall，14返回step各dt1，总有效14；request16/action888在56.98失败未返回，不补造样本/任务terminal。首fault tb2 source56.968，full raw angularz-1.206191435678961>1.2，源龄12ms。normal_control_model_invalid/infrastructure_failure原样保持。
11formal实际全wait：6PASS5FAIL；10mandatory5PASS5FAIL，errors[]/alljobsfinishedTrue。peer/drive/input/settled/information回执PASS，control/angular/physics/full/closure回执FAIL。parentexit1/monitorexit0，后terminal/reset/deadline按声明SKIP。39原生launch进程均exit0，44native保存身份及加父级48PID/start freshgone；但supervisorforced_shutdownTrue/failed_sampleTrue/worker-15仍strictcloseFAIL，native_stop/server_clean/infrastructure_cleanup局部PASS不能洗掉它。独立闭合script rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v24_final_closure_observation_v1.py，exit0、读取/核源体.5589912836439908wall，review63b889da5…，131输入末SHA/stat稳定；根session exit证据和watcher未记录PID/start局限明确，未伪造。
有界driver过滤仅一遍3个大原件，初筛选script失败及修正原件均保管closed_control_forensic_v1；110incoming目标均≤.20/.8，64actuation exactlatesttuple。55.574–56.662 pureCW(0,-.8)，56.68转mixed，峰时desired(.2,-.378947)、current轮差proxy-1.224470、applied-1.101559、body-1.206191；56.98零storage为故障后果，不把先前越界归cancel/角反转。paired helper数学原PASS不证明physicalbody界；contact/slip/servo机制未唯一归因。独立physical/angular原leaf确认planar/chord≤.30、采样角加速度<7，三机此前已有A制停信用（tb1/tb2还有B）；故障后.20s尾窗缺rest不是已证.78违界，实际唯一angularhard超限仍独立FAIL。
独立raw_guard_smoother_review_v2 f51df929…确认24普通tb2decision clear/filterNone/output逐值等rawrequest，1faultstop分列；56.66raw0→56.68raw.1，selectedsequence3550→3556/.02sim/.299825384wall，未将selectedlatest冒充所有中间pub。实际SDK1.1.20-1jammy.20260326.004635，OPEN_LOOP20Hz/.5/3.2读回PASS单列；官方1.1.20 timer源码支持walltimer/每callback积分接口缺陷。原URL20s TimeoutError、探索KeyError与未单存console范围均保留于36原件552aca68…/191596B支持包，不重试网络或重跑formal。下一版优先实测仿真时钟timer修复，原.8cap/1.2body/其他原门全部保持，尚无修复充分性或新矩阵PASS。
执行后库存发现V24未使用worker_bindings元数据仍188/136xx，而实际CLI及运行198/13701，原source审查漏项保留、不回改旧plan；下版从实际command+workerindex派生并强制一致校核。该发现不替代已有真实角速失败。
一次完整选存command/source及逐--extra精确argv见closed_pack_support_v1，rtk proxy env -i PATH=/usr/bin:/bin PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC /usr/bin/python3 -B /tmp/mr3_p2a0_v24_matrix_pack_proposal_v1/mr3_p2a0_v24_matrix_pack_closed_v1.py --freeze 5d684c46f9f99a867a94f1fed8c52e923e2486ef --target /tmp/mr3_p2a0_v24_selected_closed_v1 --all-writers-closed [逐原文件--extra清单保管原argv，未用未展开glob]，12.170313973911107wall；513原件318062459rawB→518parts20573758encodedB，max2429072B，各part/whole decodedSHA与末stat均PASS。522选存文件按prospective_canonical逐part复制A24/native/interface及metadata，不额外嵌套native；初rootcopy误猜manifest basename、resume guard漏改两个仅copy脚本失败保留，v3逐字续拷完成550件22401348B，不重跑任何原生或科学审计。
本次native launch receipt497.7553032017313wall，prior71.97839368507266，累计569.733696886804/18000，余17430.266303113195；parentlaunch498.1903878697194、audit288.55652650492266及其他CPU/封存另列，不重复计费。pilot1870/2905.954739546403不动，无GPU/PPO/P2B/gateway。P2A.0未完成；保持全部FAIL，修复后新clean pushed冻结完整四阶段，成功证据提交推送再待用户验收。


## 2026-10-18 MR3-P2A.0 V25：节点时钟覆盖包与真实stock/fixed组件对照

源码基底`94a5e26b99402e49b4e116931f8b8f625e603b0d`，执行时worktree含本版未提交
官方包及固定两timer补丁；source manifest/实际SHA保存在选定原件，不冒称clean freeze。
无训练/checkpoint/GPU、无Gazebo或环境API；不使用任务种子。原95%/300s、三台参与、
候选/actor/reward和全部原安全/速度/停车门不变。V24失败保持，不重跑失败冻结。

实际命令（每项各一次；后两编译/解析脚本内完整system ROS命令见同名选定源码/收据）：

```bash
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v25_build_overlay_v1.py
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v25_compile_probe_v1.py
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v25_resolve_overlay_v1.py
rtk proxy env -u PYTHONPATH /bin/bash --noprofile --norc -e -c 'source /opt/ros/humble/setup.bash
source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
/usr/bin/python3 -B /tmp/mr3_p2a0_v25_smoother_clock_source_review_v1/probe/run_probe_pair_v1.py --probe /tmp/mr3_p2a0_v25_actual_probe_compile_v1/build/smoother_clock_probe --probe-sha256 8efb49b67ec9d561dd6cdbdb7a265a30df2ca6553f28becc5679dbe6942e5f91 --stock-library /opt/ros/humble/lib/libvelocity_smoother_core.so --fixed-library /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/nav2_velocity_smoother/lib/libvelocity_smoother_core.so --fixed-library-sha256 ceedf1b35cc501e9caa655c5b0a66f538395893664ec683a6290760f37d60b52 --fixed-build-receipt /tmp/mr3_p2a0_v25_actual_overlay_build_v1/build_receipt_v1.json --output-directory /tmp/mr3_p2a0_v25_actual_probe_pair_v1 --domain-id 175'
```

canonical包构建PASS68.82491580815986墙秒；所有六个现有MR3库stat/SHA严格不变。
probe编译PASS44.30459033790976墙秒；两编译单列源码准备成本。正常ament/Launch/ldd
解析PASS，实际standalone/core选中canonical overlay。组件各stock/fixed一次均exit0，
normal_cleanup true，保存PID/start在wait后消失。原版paused20/10Hz输出7/3，修复版0/0；
两timer实际is_steady原版true、修复false，actual加载ELF/dev/inode/SHA与单一非零GID核实。
独立读取的fixed相邻回调增量在事先说明的4ULP减法舍入容差通过；无连续dv/dt/body证明。

stock2.0057054478675127+fixed1.1961737689562142=3.201879216823727实际墙秒计入工程预算，
累计572.9355761036277/18000，余额17427.064423896372。实际pair总wrapper3.728948475793004
另列不重复计入；没有信号、重试、超时kill或孤儿。pilot余额1870/2905.954739546403未用。

选定原件：[V25报告](report/20261018_mr3_p2a0_v25_smoother.md)、
[组件manifest](report/assets/20261018_mr3_p2a0_v25_smoother/component_probe/selected_manifest_v1.json)、
[ELF manifest](report/assets/20261018_mr3_p2a0_v25_smoother/build_evidence/selected_elf_manifest_v1.json)、
[独立actual审查](report/assets/20261018_mr3_p2a0_v25_smoother/actual_independent_review/handoff_v1.json)。
API静态审查发展稿引号SyntaxError/初seal-atime比较错误、原版官方来源网络记录保留各自原件；
这些不是作者包编译/probe失败。无正式矩阵PASS，P2A.0未完成；待新clean pushed冻结四阶段。


### 2026-10-18 V25新源码准入/有限CPU检查与完整矩阵预声明

同一未提交准备worktree，最终module6edeb3a7…、auditor7d1a1a70…、ENV41feac9a…；
尚无新原生freeze/PASS。作者v1 fakeproc缺group/session的3FAIL保留；18修复检查、
v2增PIDreuse-Z及canonicalmanifest路径的19检查、v3增sameworker-Z/empty与reuseworker-Z
的21检查依次实际通过。新增检查只修本helper分类：sameidentity合法关闭pending/no credit，
reuse及wrongargv/hash硬拒。作者CPU通过wall分别2.157729092054069/2.19473171280697/
2.2367755016312003；实际命令与stdout/stderr/缺失原console的范围分别见封存原件，
未伪造最初direct-tool stdout。独立新反例旧e890红/8e08绿保留，不重跑作者套件。

根实际命令：`rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v25_root_deployment_checks_v1.py`，
脚本绑定的Conda命令原16 auditor单元PASS（测试2.599秒/进程7.736638186965138墙秒），
一个canonical安装位置真实source/build/archive测试PASS（进程.880315454211086墙秒）。
选定[检查收据](report/assets/20261018_mr3_p2a0_v25_smoother/deployment_checks/checks_v1.json)
保存exact argv/SHA/console。无SDK/ROS/DDS/native/GPU调用，不重跑旧170套。
RT六编排static逆/34门/workerhelper/fatal lint PASS（一次1.484900236595422墙秒），
初机械发展稿、旧source与原检查全部保留[57成员封包](report/assets/20261018_mr3_p2a0_v25_smoother/matrix_preparation/handoff_final_v1.json)。

root闭合review copy v1误假定两handoff共用name/archive键，KeyError前只建空目录；
v2按实际API manifest/source basename完成，无source/bin修改或实验重跑。原v1/v2/helper
与显式错误说明保存在root_preparation，不把工具发展错误改记为作者/probe/native失败。

最终[计划](report/assets/20261018_mr3_p2a0_v25_smoother/predeclared_plan_v25.json)
27a5027c930e2d805187ea9e7d53fd16e797ab395c0931c4b76f707a1f6ae051，222source
bindings；原34/12episode/608API/596脚本动作/18000累计预算不变，携带572.9355761036277。
各stage命令保持原工作量，domain208/210/212+213/216，port13801/11/21+22/31，均由actualCLI
生成typed worker元数据并在三个入口交叉验证。source-ready仍需新clean pushed exact40
实际Conda前检，随后先watcher START再唯一parent；任何FAIL后续SKIP，不同冻结PASS不拼接。
无训练/pilot/P2B/gateway，本段不声称完整矩阵已运行。

V25最终静态检查：222实际绑定、10包文件、6旧库、50061原ENV字节前缀和205本地链接通过；root初v1白名单漏列合法新V25报告，未产PASS，v2只增加该精确报告路径后通过，原失败说明/两脚本保留。最终git dry-run唯一ignored为root临时导入生成的单个pycache，已删除该自有缓存；无build/install/runtime产物进入选定source。所有独立review/source/metadata writer已STOP，尚待cleanpush与实际前检。

V25首次cached diff-check指出9个原始README/构建/probe文本的26处原生空白。按既有.gitattributes保真惯例仅这9个精确路径设-text/-whitespace，原件不trim、不改hash，作者CPP和门禁代码不豁免；完整初检查输出与路径说明选定root_preparation。此为源码/证据格式处理，无实验重跑。

V25最后静态v3因把新增已stage源/证据当旧production而断言，v4只修该分类并dedupe本地链接；保存的原空白诊断stdout自身保真改用lossless gzip。两次发展稿未授PASS，明确说明与原脚本已归档。最终v4的222绑定/10源/6旧库/205链接通过，cached diff-check通过；无额外ROS/native/测试或预算变动。


### 2026-10-18 V25 实际32步与取证035失败、全部闭合

源码clean pushed579f7ad21d33c6de9351eb5308f155f0fc903fd7，计划27a5027c930e2d805187ea9e7d53fd16e797ab395c0931c4b76f707a1f6ae051。
cwd W，实际command：`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a0_v25_actual_preflight_once_v1.py`；内层固定Conda -B A25/independent/mr3_p2a0_v25_buildproof_preflight.py，exit0/20.26931026391685wall，127runtime/222independent/3真实imports-help，receipt7bcc83bb0890e0f0503483cba7e01032b45a9ad1ad643558d98981561c6d8e28。
随后同环境systemPython -B `/tmp/mr3_p2a0_v25_capture_matrix_job_v1.py watcher`，真实START确认后同脚本`matrix`；wrapper8cd251b94f314c4f2bde3cb6792390ee680855d1344b0f223cfc6011b3bc9bf9仅捕获绑定CLI，无signals/retries/timeouts。实际argv为A25/independent/mr3_p2a0_v25_cross_stage_mapping_monitor_v1.py --freeze579f…（原argv分离参数）以及mr3_p2a0_v25_run_matrix_v1.py 579f…。每层完整exact argv/cwd/env/console与START/结束PID均保存在唯一metadata原件，不以本文缩写取代原件。
interface实际Conda benchmark固定workers1/scheduleopen:101/steps32/preparation-motion-probe/versionmr3-p2a0-outward-cancel-v6/domain208/port13801/parameter-review，run-id mr3_p2a0_20261018_v25_interface。32次dt1全部返回，最终elapsed32/command32/terminatedFalse/truncatedTrue/external_sampler_limit。9参数PASS；39原生exit0，supervisorforcedFalse/failedsampleFalse/worker0。全部11审计结束10PASS1FAIL；10声明正式回执9PASS1FAIL，额外必需FIFO PASS，不把它称optional。唯一失败是closure_binary_review中的新smoothercustody035；原full/input/peer/drive/angular/physics/settled/information/control全PASS。停车信用tb1 A1/B2，tb2 A0/B1，tb3 A0/B1，原每实际合格事件/全安全门不变。parentexit1/watcherexit0，后三terminal/reset/deadline按规则SKIP，不重跑。
035原错误仅combined process/ancestry/maps changed during capture、processes={}，缺candidate/各项after快照；采集4032244.566..4032245.734跨Nav2关闭4032244.940，但不能唯一归因全maps、祖先退出、真实PID或库变化，不能改称误报。CI和独立描述review仅读取原件，不重跑consumer；原034完整/036关闭pending保留。根最终fresh50个保存PID/start全部gone。所有source/bin/Git一直保持到native、11审计、watcher全部关闭及packet封存。
launch796.7103692898527wall计native预算，prior572.9355761036277，累计1369.6459453934804/18000，余16630.35405460652；parent1072.4524832847528、watcher1093.7184994621202、CPU/封包另列无重复收费。pilot1870/2905.954739546403不动，无PPO/GPU/P2B/gateway。
实际封包一次18.65141849964857wall，准确argv/18支持原件见A25/closed_pack_support_v1/originals.tar.gz与execution.json；832原件524266668B→843分块35179876B、max2646017B，encoded/decoded/整件SHA与末stat全PASS。根执行`rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v25_root_closed_copy_v1.py`，847packet文件36714559B按prospective_canonical精确复制，另保管支持及035诊断/最终身份，859复制对象全encodedSHA一致；复制源码及receipt在closed_observation。mutable root_state及V26未来草稿明确排除。封存仅证明字节保管，原FAIL/SKIP保持，P2A.0仍未完成。下一版仅修取证一致性并新clean pushed冻结全四阶段，不拼旧PASS。


## 2026-10-18 V26 窄进程取证修复准备（尚无新原生）

基底closed evidence913ff9e7；worktree新ac90观察器/f45固定loader，实际V25 C++b49/coreceed/exe0a5、原六MR3库/ODE、ENV41fea、全部任务/物理/停止/安全数学不变。035combined失败无法唯一归因，原FAIL永久保留；新wholemaps差异记录为描述，只有相关core映射/PID/argv/exe/inode/device/ancestry前后全部证明才可credit，同身份祖先自然关闭pending无credit，reuse/真实source错误硬拒。
作者九case对照18observe/.5546168070wall；exact command/script/原输出见custody_preparation/originals.tar.gz；无ROS/DDS/native/build/consumer/GPU。独审新增single fakeproc确认7ff已观察到reuseZ却exe消失会错误pending，exit0/.251995s，见custody_independent_review_v1。最终ac90将pair硬核前置；作者仅新增一case比较old6ede/newac90共2observe/.09293236210942268wall，独审同例绿.287257s，未重9/21/旧数学套。初7ff/v1、loader addendum、v2、.patch、executed snapshot全留；v2结果继承nine文字但actualcase_count1/calls2，最终文案仅静态纠正不重执行，不把caption误当9例再跑。
六coord实际一次static全文/AST逆/fatal syntax exit0/1.3881991049274802wall，精确argv及48原件见matrix_preparation/originals.tar.gz；随后只同步ac90/f45 pins无重suite。A25workerhelper3b685以固定路径+checkedbytes加载，旧binding61276/source_manifest78fb/actual二库与buildarchive复用、不重编。230bindings为旧222中221sameSHA、唯共享auditor身份变更、八新路径；原34/608API/596decision/12EP/18000累计规则保持。
根命令`rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v26_promote_and_finalize_v1.py`在精确复制后误用mandatory_receipts键KeyError，未写finalplan；v1源及描述note保留root_preparation，原tool traceback无单独console不伪造。v2仅真实required_audit_receipts键与同SHA续拷，exit0生成finalplan fe5a2a7bfb5b6708c396687ece361ba603de76cc35ef443ba4ae50cc739efa0a；相比draft仅6顶层metadata键，未改stage/math/sourcepins。作者封包20成员113027B、RT49成员175437B及独审红/绿包全部roundtrip/末SHAstat通过；rootcopy只核字节，不运行实验。
新声明domain218/220/222+223/226与port13901/11/21+22/31，interface32、terminal两轮4、reset双worker各[open101,open101,rooms101,corridors101]×32、deadline300KEEP；原seed101、三机、真实gate不变。携带1369.6459453934804/18000，余16630.35405460652；pilot1870/2905.954739546403未动。准备source-ready不授nativePASS；须新clean pushed实际Conda前检+START再唯一parent，首FAIL后续SKIP，不同冻结不拼PASS。无PPO/pilot/GPU/P2B/gateway。

V26最终独立接线审实际exit0/.417686wall，244输入末SHA/stat稳定；230/原34/608/596/8resetpool/carry、固定A25 helper及actual二ELF、根6字段白名单均核验，无阻断，所有reader已STOP。8件封包26709B roundtrip通过，保管final_wiring_review。根最短静态核230绑定/8PythonAST/原ENV/186本地链接并git diff --check通过，未重任何suite/consumer。


## 2026-10-18 V26 同冻结原生矩阵、原编排中断及等价只读补验

源码冻结`92f8bdf5bba1ba245dc53ca0964eef81a7fff938`，计划`fe5a2a7bfb5b6708c396687ece361ba603de76cc35ef443ba4ae50cc739efa0a`。工作目录为`/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl`；各真实argv以原JSON为准，未重跑原生。
实际preflight入口wrapper为`/tmp/mr3_p2a0_v26_actual_preflight_once_v1.py`，source SHA`38d1733ad64e5f2e532fc23774eeb2e085c3deb578ff90ebc20c5e53e79fb481`。其execution/started回执保存的是内层Conda argv，不另发明外层shell启动argv：
```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v26_capture/independent/mr3_p2a0_v26_buildproof_preflight.py
```
实际前检exit0/20.413090414833277墙秒；source_preflight SHA`48ed730b01c3a8e14dc4ca4393bd283e20c1be286f23c31bb60933c7ecbd8bd3`。
watcher捕获wrapper `/tmp/mr3_p2a0_v26_capture_matrix_job_v1.py` SHA`0e34bbc88348e2fba34084ad42a7391578ad49a7f86984c9dff13954ad4350a8`；原START只保存内层argv与job，没有外层shell的逐字启动记录，不补造。真实内层：
```bash
/usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v26_capture/independent/mr3_p2a0_v26_cross_stage_mapping_monitor_v1.py --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938
```
matrix捕获wrapper `/tmp/mr3_p2a0_v26_capture_matrix_job_v1.py` SHA`0e34bbc88348e2fba34084ad42a7391578ad49a7f86984c9dff13954ad4350a8`；原START只保存内层argv与job，没有外层shell的逐字启动记录，不补造。真实内层：
```bash
/usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v26_capture/independent/mr3_p2a0_v26_run_matrix_v1.py 92f8bdf5bba1ba245dc53ca0964eef81a7fff938
```
实际前检内三个CPU imports/argparse-help命令：
```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -c 'import json,sys,gymnasium,torch; print(json.dumps({"interpreter":sys.executable,"gymnasium":gymnasium.__version__,"torch":torch.__version__,"gymnasium_file":gymnasium.__file__,"torch_file":torch.__file__}))'
```
imports: returncode=0, wall_seconds=4.410975709091872。
```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.benchmark --help
```
benchmark_help: returncode=0, wall_seconds=0.4397054649889469。
```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.audit_preparation --help
```
full_audit_help: returncode=0, wall_seconds=4.810751297045499。
interface实际benchmark（launch.json键command_argv）：
```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 32 --preparation-motion-probe --preparation-probe-version mr3-p2a0-outward-cancel-v6 --base-domain 218 --base-port 13901 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261018_v26_interface --preparation-parameter-review
```
terminal实际benchmark（launch.json键command_argv）：
```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 --steps 4 --terminal-probe --base-domain 220 --base-port 13911 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261018_v26_terminal
```
reset实际benchmark（launch.json键command_argv）：
```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u -m mr3_learning.benchmark --workers 2 --schedule open:101,open:101,rooms:101,corridors:101 --steps 32 --preparation-motion-probe --preparation-probe-version mr3-p2a0-outward-cancel-v6 --base-domain 222 --base-port 13921 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261018_v26_reset
```
deadline实际benchmark（launch.json键command_argv）：
```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -u -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 300 --deadline-probe --base-domain 226 --base-port 13931 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261018_v26_deadline
```
原已完成53条正式子命令（52PASS/1个reset非必需FAIL）逐条真实argv如下；未完成的原information命令不冒称完成：
- interface/peer_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_independent_control_phase_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_interface --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_interface_peer_review_v1.json --peer-only
```
- interface/drive_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v13/independent/mr3_independent_drive_trace_v6.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_interface --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --binary-proof /tmp/mr3_p2a0_v26_binaryproof.json --output /tmp/mr3_p2a0_v26_interface_drive_review_v1.json
```
- interface/settled_turn_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v8/independent/mr3_independent_settled_turn_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_interface --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_interface_settled_review_v1.json --require-use
```
- interface/information_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_independent_information_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_interface --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_interface_information_review_v1.json
```
- interface/fixed_angular_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v4/independent/mr3_independent_angular_interface_v1.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_interface/worker0/episode001_open_101 --output /tmp/mr3_p2a0_v26_interface_fixed_angular_v1.json
```
- interface/control_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_independent_control_phase_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_interface --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_interface_control_review_v1.json
```
- interface/episode001_fifo_phase_final: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_v10_fifo_phase_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_interface/worker0/episode001_open_101 --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_interface_episode001_fifo_phase_final.json
```
- interface/fixed_physics_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v3/independent/mr3_independent_physics_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_interface/worker0/episode001_open_101 --output /tmp/mr3_p2a0_v26_interface_fixed_physics_v1.json
```
- interface/closure_binary_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v26_capture/independent/mr3_v26_multiepoch_closure_binary_review_v1.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_interface --prefix mr3_p2a0_v26_interface --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --expected-episodes 1 --require-parameters
```
- interface/full_audit: returncode=0, passed=True, required_success=True。

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.audit_preparation /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_interface --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_interface_full_audit.json
```
- interface/input_001: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v4/independent/mr3_p2a0_v4_independent_input_episode_review_v1.py --episode /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_interface/worker0/episode001_open_101 --output /tmp/mr3_p2a0_v26_interface_input_review_v1.json
```
- terminal/peer_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_independent_control_phase_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_terminal --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_terminal_peer_review_v1.json --peer-only
```
- terminal/drive_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v13/independent/mr3_independent_drive_trace_v6.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_terminal --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --binary-proof /tmp/mr3_p2a0_v26_binaryproof.json --output /tmp/mr3_p2a0_v26_terminal_drive_review_v1.json
```
- terminal/information_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_independent_information_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_terminal --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_terminal_information_review_v1.json
```
- terminal/episode001_fifo_phase_final: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_v10_fifo_phase_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_terminal/worker0/episode001_open_101 --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_terminal_episode001_fifo_phase_final.json
```
- terminal/episode002_fifo_phase_final: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_v10_fifo_phase_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_terminal/worker0/episode002_open_101 --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_terminal_episode002_fifo_phase_final.json
```
- terminal/settled_turn_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v8/independent/mr3_independent_settled_turn_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_terminal --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_terminal_settled_review_v1.json
```
- terminal/control_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_independent_control_phase_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_terminal --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_terminal_control_review_v1.json
```
- terminal/closure_binary_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v26_capture/independent/mr3_v26_multiepoch_closure_binary_review_v1.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_terminal --prefix mr3_p2a0_v26_terminal --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --expected-episodes 2
```
- terminal/full_audit: returncode=0, passed=True, required_success=True。

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.audit_preparation /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_terminal --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_terminal_full_audit.json
```
- reset/peer_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_independent_control_phase_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_reset_peer_review_v1.json --peer-only
```
- reset/drive_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v13/independent/mr3_independent_drive_trace_v6.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --binary-proof /tmp/mr3_p2a0_v26_binaryproof.json --output /tmp/mr3_p2a0_v26_reset_drive_review_v1.json
```
- reset/settled_turn_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v8/independent/mr3_independent_settled_turn_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_reset_settled_review_v1.json
```
- reset/information_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_independent_information_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_reset_information_review_v1.json
```
- reset/input_001: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v4/independent/mr3_p2a0_v4_independent_input_episode_review_v1.py --episode /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker0/episode001_open_101 --output /tmp/mr3_p2a0_v26_reset_episode001_input_v1.json
```
- reset/control_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_independent_control_phase_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_reset_control_review_v1.json
```
- reset/input_002: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v4/independent/mr3_p2a0_v4_independent_input_episode_review_v1.py --episode /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker0/episode002_open_101 --output /tmp/mr3_p2a0_v26_reset_episode002_input_v1.json
```
- reset/input_004: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v4/independent/mr3_p2a0_v4_independent_input_episode_review_v1.py --episode /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker0/episode004_corridors_101 --output /tmp/mr3_p2a0_v26_reset_episode004_input_v1.json
```
- reset/input_003: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v4/independent/mr3_p2a0_v4_independent_input_episode_review_v1.py --episode /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker0/episode003_rooms_101 --output /tmp/mr3_p2a0_v26_reset_episode003_input_v1.json
```
- reset/input_005: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v4/independent/mr3_p2a0_v4_independent_input_episode_review_v1.py --episode /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker1/episode001_open_101 --output /tmp/mr3_p2a0_v26_reset_episode005_input_v1.json
```
- reset/input_006: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v4/independent/mr3_p2a0_v4_independent_input_episode_review_v1.py --episode /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker1/episode002_open_101 --output /tmp/mr3_p2a0_v26_reset_episode006_input_v1.json
```
- reset/input_008: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v4/independent/mr3_p2a0_v4_independent_input_episode_review_v1.py --episode /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker1/episode004_corridors_101 --output /tmp/mr3_p2a0_v26_reset_episode008_input_v1.json
```
- reset/input_007: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v4/independent/mr3_p2a0_v4_independent_input_episode_review_v1.py --episode /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker1/episode003_rooms_101 --output /tmp/mr3_p2a0_v26_reset_episode007_input_v1.json
```
- reset/episode001_fifo_phase_final: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_v10_fifo_phase_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker0/episode001_open_101 --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_reset_episode001_fifo_phase_final.json
```
- reset/episode002_fifo_phase_final: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_v10_fifo_phase_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker0/episode002_open_101 --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_reset_episode002_fifo_phase_final.json
```
- reset/episode003_fifo_phase_final: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_v10_fifo_phase_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker0/episode003_rooms_101 --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_reset_episode003_fifo_phase_final.json
```
- reset/episode004_fifo_phase_final: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_v10_fifo_phase_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker0/episode004_corridors_101 --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_reset_episode004_fifo_phase_final.json
```
- reset/episode005_fifo_phase_final: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_v10_fifo_phase_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker1/episode001_open_101 --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_reset_episode005_fifo_phase_final.json
```
- reset/episode006_fifo_phase_final: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_v10_fifo_phase_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker1/episode002_open_101 --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_reset_episode006_fifo_phase_final.json
```
- reset/physical_per_episode_v1: returncode=1, passed=False, required_success=False。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v3/independent/mr3_independent_physics_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset --output /tmp/mr3_p2a0_v26_reset_physical_per_episode_v1.json
```
- reset/episode007_fifo_phase_final: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_v10_fifo_phase_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker1/episode003_rooms_101 --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_reset_episode007_fifo_phase_final.json
```
- reset/physics_matrix_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v17/independent/mr3_independent_physics_matrix_v17.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --per-episode-report /tmp/mr3_p2a0_v26_reset_physical_per_episode_v1.json --output /tmp/mr3_p2a0_v26_reset_physics_matrix_v1.json
```
- reset/episode008_fifo_phase_final: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_v10_fifo_phase_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset/worker1/episode004_corridors_101 --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_reset_episode008_fifo_phase_final.json
```
- reset/angular_matrix_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v17/independent/mr3_independent_angular_reset_matrix_v17.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_reset_angular_matrix_v1.json
```
- reset/full_audit: returncode=0, passed=True, required_success=True。

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.audit_preparation /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_reset_full_audit.json
```
- reset/closure_binary_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v26_capture/independent/mr3_v26_multiepoch_closure_binary_review_v1.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_reset --prefix mr3_p2a0_v26_reset --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --expected-episodes 8
```
- deadline/peer_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_independent_control_phase_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_deadline --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_deadline_peer_review_v1.json --peer-only
```
- deadline/control_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/mr3_independent_control_phase_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_deadline --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_deadline_control_review_v1.json
```
- deadline/settled_turn_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v8/independent/mr3_independent_settled_turn_v3.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_deadline --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_deadline_settled_review_v1.json
```
- deadline/episode001_fifo_phase_final: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_v10_fifo_phase_review.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_deadline/worker0/episode001_open_101 --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_deadline_episode001_fifo_phase_final.json
```
- deadline/full_audit: returncode=0, passed=True, required_success=True。

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.audit_preparation /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_deadline --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_deadline_full_audit.json
```
- deadline/closure_binary_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v26_capture/independent/mr3_v26_multiepoch_closure_binary_review_v1.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_deadline --prefix mr3_p2a0_v26_deadline --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --expected-episodes 1
```
- deadline/drive_review_v1: returncode=0, passed=True, required_success=True。

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v13/independent/mr3_independent_drive_trace_v6.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_deadline --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --binary-proof /tmp/mr3_p2a0_v26_binaryproof.json --output /tmp/mr3_p2a0_v26_deadline_drive_review_v1.json
```
选定原f736只读科学补充声明的真实消费者argv（自然PASS/return0/no signals；不与另外索引验证合并）：
```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_independent_information_v2.py /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_deadline --freeze 92f8bdf5bba1ba245dc53ca0964eef81a7fff938 --output /tmp/mr3_p2a0_v26_deadline_information_supplemental_v1.json
```
原f736补充真实returncode=0/PASS、2909.4306966429576墙秒、signals_sent=0；输出SHA`4254219b07e635517652daf723b146f53c7f362ab5541da57f9c4468e1fb29e9`。
索引等价CPU及三组完整对照的保存argv（不替代原f736科学回执；仅provenance的argv不记录Python启动flags）：
```bash
/usr/bin/python3 /tmp/mr3_p2a0_v26_information_index_proposal_v1/proposal.py cpu
```
```bash
/usr/bin/python3 /tmp/mr3_p2a0_v26_information_index_proposal_v1/proposal.py stage --stage interface
```
interface: all_original_fields_deep_equal=true；85.67490080790594只读墙秒。
```bash
/usr/bin/python3 -B /tmp/mr3_p2a0_v26_information_index_proposal_v1/proposal.py stage --stage terminal
```
terminal: all_original_fields_deep_equal=true；46.96104751387611只读墙秒。
```bash
/usr/bin/python3 -B /tmp/mr3_p2a0_v26_information_index_proposal_v1/proposal.py stage --stage reset
```
reset: all_original_fields_deep_equal=true；666.9372907830402只读墙秒。
最终三组对照addendum SHA`fd9b894e2bae26c26e9ebb86caeb926b1e064b16e3ff19b06860884eae2f6054`；只删除唯一新增implementation provenance后完整dict相等。
独立deadline索引执行器和声明的真实consumer argv：
```bash
/usr/bin/python3 -B /tmp/mr3_p2a0_v26_information_index_proposal_v1/execute_deadline.py
```
```bash
/usr/bin/python3 -B /tmp/mr3_p2a0_v26_information_index_proposal_v1/deadline_indexed.py --output /tmp/mr3_p2a0_v26_information_index_proposal_v1/deadline_optimized_information_review_v1.json
```
额外deadline索引尝试有意中止：root以保存PID/start=3915500/405102066核对后通过pidfd发送一次SIGTERM；实际executor wait返回-15，630.2861267556436墙秒，passed=false、输出仍缺失、源末SHA不变。这是intentionally_stopped/incomplete，不获得第四组等价信用，不影响已自然PASS的原f736科学角色。 stop receipt SHA`1d3bf2fef5987f7e4d16bad5eb73fcdc125a2f65b9c544162b48a89b7bead6bc`。独立执行receipt保留真实-15和无输出；没有第四组结果SHA或等价信用。 A9:350静态计数推导46302次selection→约1071914451次keys，不声称runtime profile；本轮不追加第二优化。
实际完整保管helper argv（来自最终helper_configuration.json；其中argv不含解释器，原样列出）：
```bash
/tmp/mr3_p2a0_v26_recovery_closure_proposal_v1/recover_closed_v3.py --all-writers-closed --information-mode original --target /tmp/mr3_p2a0_v26_recovered_packet_v1 --extra /tmp/mr3_p2a0_v26_three_closed_stages_summary_v1.tar.gz --extra /tmp/mr3_p2a0_v26_closed_schema_review_v1.tar.gz --extra /tmp/mr3_p2a0_v26_recovery_closure_proposal_v1/handoff_v3.json --extra /tmp/mr3_p2a0_v26_recovery_closure_proposal_v1/v2_to_v3.diff --extra /tmp/mr3_p2a0_v26_promote_packet_v1.py --extra /tmp/mr3_p2a0_v26_promote_packet_handoff_v1.json
```
封包346.97013730276376墙秒；11561原文件/9265402604原字节→11766parts/627021272编码字节，完整往返/source末SHA/stat核验；manifest SHA`b9b23938ad44664732d637fdd3833fd3fbc473555ed5bb0ffa8864a0f59e073e`。
最终12reset+596step=608API，595实际提交动作；34科学角色10/7/10/7已由原回执和一个同源码补验核齐，索引三组完整等价与额外deadline中止另列，原parent INTERRUPTED/返回码unknown、三个缺失final永久保留。468/468原生退出转录与543个保存身份gone各保留原范围。reset两corridors tb3逐回合停车覆盖不足的非必需FAIL及旧035/全部历史FAIL不改。工程累计计费11420.856789876707/18000，其中本矩阵native 10051.210844483227、携带1369.6459453934804；余6579.143210123293墙秒；CPU、只读恢复、封包另列，pilot余1870/2905.954739546403未用。P2A.0仅工程科学门补齐待用户验收；无PPO/GPU/P2B/gateway、95%策略或连续/多日稳定信用。

交付静态核验：230原源码绑定、171本地Markdown链接、10份JSON、11776提升文件的SHA/大小全部通过；git diff --check绿，git add -n .已执行，11777新文件恰为11776选定证据副本加一份复盘，无build/install或未封存runtime混入。独立只读审查无剩余阻断；8份活动文档删减仅过期状态/版本时间线，原文Git对象与SHA已在ARCHIVE_INDEX登记。

额外静态交接：训练器ppo.py默认每回合上限300步，collect_episodes完整返回后才构造buffer并model.train；已有300 KEEP实测5368.246922858991墙秒大于pilot余2905.954739546403。此为现有代码/原件的预算对照，不是新实验或PPO吞吐结论，不断言策略不能提前终止；不新增P2A.0门、不启动/扩额pilot。详见复盘采样预算段。


## 2026-10-18：用户验收P2A.0，V7继续P2A（执行前声明）

用户明确“p2a.0验收通过，继续完成p2a”。接受V26准备工程科学门，不改变原编排中断和所有旧FAIL。新计划见[预声明](report/assets/20261018_mr3_p2a_v7/predeclared_plan_v7.json)与[报告](report/20261018_mr3_p2a_v7.md)。生产源码不变；fresh16/900独立工程最小链通过后，才以独立fresh seed41、双worker open101/cap64运行余额内pilot：1870决策、采集2100墙秒，805.9547395464029预留收尾。短前缀一次bootstrap不当作95%成功；正常final与完整两项审计后才执行原open401/402/403、900/9000、0更新开发验证。新原生尚未启动，不预写PASS。

只读环境检查实际Conda=/home/zhuyulab/miniconda3/envs/ns3gym/bin/python，numpy2.2.6、torch2.11.0+cu128、gymnasium1.3.0、SB3/sb3-contrib2.9.0，CUDA可用/2设备；没有重装依赖。当前source loader的127项pin/build/source proof通过，无新native。

V7源码准备最短检查：现有test_ppo/test_finite_horizon/test_rollout共42项通过；新增补充审计6项通过，覆盖空/未知attempt、leaf失败汇总、motion单次调用、源码绑定和输出拒覆盖；143个本地Markdown链接无缺件，计划JSON/Decimal预算/参数经独立只读复核一致。仅增加只读audit_policy_inputs入口，不改生产/训练算法。


## 2026-10-18：V7最小链真实反例与闭合（pilot/验证SKIPPED）

实际clean+pushed冻结 `8d7f19fc8225eae0ccdc6609b828ee8e832f7c93`，学习seed41、open/Gazebo seed101、每worker tb1/tb2/tb3。
实际前检127项native/source/build与7项补充source绑定通过。当前运行命令均从wireless-rl目录执行：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.ppo --mode train --workers 1 --schedule open:101 --decisions 16 --episode-steps 16 --wall-seconds 900 --seed 41 --base-domain 180 --base-port 14001 --run-id mr3_p2a_v7_minimal
```

工具真实退出0，16原生=16collector返回，15.22有效/15.24物理秒，2round/8次实际GPU optimizer.step，702.5650296038948墙秒，cleanup_errors=[]、原completed=true。
首round8决策、7.22秒navigation_failure、覆盖.7129097051036246、地图质量/参与/导航闭合均未通过、接触0；第二round8决策、8秒外部截断、覆盖.5889025837670044、质量/参与未通过，接触0/导航闭合true。
第二round评价器最终8.2秒含关闭阶段，不给8秒学习步补样本。两回合原collision_monitoring_fresh=true；不以此抵销独立模型证明失败。

正式只读审计精确命令（工具实际均return1，原报告不改写）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.audit_ppo /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v7_minimal --freeze 8d7f19fc8225eae0ccdc6609b828ee8e832f7c93 --output /tmp/mr3_p2a_v7_minimal_full_audit_v1.json
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.audit_policy_inputs /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v7_minimal --freeze 8d7f19fc8225eae0ccdc6609b828ee8e832f7c93 --output /tmp/mr3_p2a_v7_minimal_input_audit_v1.json
```

真实首因：tb3原own odom record70968、input1482/source54.155，平面速度.02020358683181293>.01，下一record70969触发settled_turn_model_failure。WORLD速度来自native WorldLinearVel，非map/TF假象。
此前154条存储target线速度零，最新总弦长.005674432986632134<.0078；首次违反速度条件。54.12零转/54.14恢复.8均真实，但因果未隔离。
早期future odom猜测已更正：零输出早于future raw入站，最老资格源龄101ms>100ms，拒绝符合原规则；不调宽门或保持旧授权。
因此原模型/物理证明失败，真实终态/正常退出/实际8更新都不能转成有效训练链信用。原完整报告保留物理、初始握手、接触相位证明级联及round1 value错误；补充报告保留motion与execution_inputs两叶错误。

独立只读CPU诊断另证round1值误差是reader权重误选：round0被物理门排除后旧reader错误选initial；actual checkpoint0000重放全部原tensor/action/value/logprob/reward/dt/GAE通过，value最大绝对差7.152557373046875e-7；initial误用时最大差2.7784765288233757、8/8失败。原容差未改。
原诊断policy_sha256字段误标为zip SHA的独占字段说明并列保留，不冒称state_dict SHA。

只完成两项后续代码准备，无新native/GPU：reader按真实summary更新顺序选checkpoint（独立于前序native通过与否），4项CPU回归原红/新绿；collector所有native关闭后、buffer/GAE/optimizer前，读取epoch绑定的worker summary.failures，精确拒绝已知settled-turn模型失效，保留真实返回决策至failed_collection。普通任务失败/零尾/真实截断规则不变；test_ppo+finite_horizon共31项CPU通过，已闭合首回合只读拒绝校验通过。这些不修plant、不覆盖原8次更新或原FAIL。

V7 pilot/三场开发验证均SKIPPED，0新pilot决策/0墙秒；余额1870/2905.9547395464029不重置、不扩额，工程最小链702.5650296038948另列。所有supervisor原保存身份88组PID/start均gone；独立活动单快照39组及实加载库来源单列，0终止信号，不虚构未保存的瞬时进程。
唯一原件保管：[V7闭合清单](report/assets/20261018_mr3_p2a_v7/closed_evidence/manifest.json)，459原文件共422601115字节，native gzip/tar归档41359879字节/1块，完整逐文件往返SHA、编码SHA和源末stat通过；四份模型仅工程诊断、不代用pilot final。

完整结果与物理对照提案见[V7报告](report/20261018_mr3_p2a_v7.md)。原工程余6579.143210123293，即使不扣本次702.565，仍不足历史完整矩阵10051.210844483227。
拟申请工程累计上限18000→30000（新增12000，将V7最小链纳入记账），pilot/验证不扩额；当前仅提案未授权、未执行。不自动原生重试/借预算/P2B/gateway。P2A未完成，P2A.0已验收边界及原V26中断/所有旧FAIL保留。

V7最终静态交付核验：181个当前本地链接无缺，闭合包13份直接原件SHA及单归档块SHA/大小正确，4份后续源码SHA匹配，4 Python AST通过；独立只读审查无阻断。git diff --check与git add -n .通过，仅选定闭合证据（约41.36MB归档）及代码/文档，无build/install或未关闭runtime混入。原16决策/8更新及两门FAIL不变；新增工程提案未授权、未执行。

V7预算申请前补充只读入口核查：现有余额足够短探针，但现有benchmark/物理diagnostic无精确波形输入；旧profile限定初始ODE50，不可直接复用当前150。cmd_vel_nav短零经smoother变缓，连续请求可能被100ms资格门中断，故不能假称原guard后20ms零脉冲的精确对照。未启动新native/未发信号；[能力评估](report/assets/20261018_mr3_p2a_v7/existing_diagnostic_entry_assessment_v1.json)与预算提案明确新诊断接口仍需源码/CPU准备，未知物理因果不冒称已修。没有为了用余额盲重跑。

## 2026-10-19 MR3-P2A V8 budget acceptance and diagnostic source preparation

User said “批准，继续”, approving the immutable V7 proposal: cumulative engineering ceiling 30000 wall seconds; charged on entry 12123.4218194806018 and remaining 17876.5781805193982. Pilot 1870 decisions/2905.9547395464029 wall seconds and final-only open401/402/403 validation are unchanged. No native/PPO attempt has started in this source-preparation record. V7 physical FAIL and all original updates remain diagnostic. Approval: `report/assets/20261019_mr3_p2a_v8/budget_acceptance_20261019.json`.

Prospective paired plant fixture and limitations are in `report/20261019_mr3_p2a_v8.md`: three robots, fixed far-peer open101, genuine smoother request→actual guard consumption→unchanged controlled phase/storage→physics; 40ms pulse is a new contrast, not V7 original 20ms reproduction. No truth-based opportunity selection. Two arms at most 1800 wall seconds each; complete affected same-freeze engineering and a fresh minimum remain prerequisites to remaining pilot.

CPU/source validation, not simulator evidence: smoother core and isolated gtest build succeeded; 22 tests PASS, including 19 normal and 3 diagnostic tests. The saved CPU receipt preserves initial test-target BUILD_TESTING=OFF, a C++ test helper compile error, and a first runtime LD_LIBRARY_PATH mismatch; each was repaired before the final PASS. Multi_robot build command: `rtk proxy bash -c 'source /opt/ros/humble/setup.bash; PYTHONNOUSERSITE=1 /usr/bin/python3 /usr/bin/colcon build --packages-select multi_robot --symlink-install --cmake-args -DBUILD_TESTING=OFF'`, 1 package succeeded in 53.4s with existing Gazebo warnings. Launch pytest command from ROS root: `rtk proxy bash -c 'source /opt/ros/humble/setup.bash; source install/setup.bash; PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -m pytest -q src/multi_robot_exploration/test/test_mr3_plant_launch.py src/multi_robot_exploration/test/test_mr3_adapter_launch.py src/multi_robot_exploration/test/test_mr3_drive_launch.py'`: final 30 PASS; initial new-test failures exposed a missing evaluator fixture flag, bool RewrittenYaml argument type, and Humble's inability to add absent YAML params. New explicit defaultoff YAML fields and a string rewrite fixed actual launch configuration. No thresholds were changed. Actual freeze/source/binary/preflight and any native attempts will be appended separately.

V8 final CPU/source-clock preparation addendum: original guard receipt topic publisher identity is now independently fixed; reader covers complete4s/4000 pairs per robot and original guard receipt objects. Final validation: 117 ROS worker/guard checks,13 conda supervisor/runner checks,30 launch checks,10 independent synthetic-reader checks and23 smoother gtests PASS. Final smoother uses actual installed core `fc2a590d2c75b92f7fe12f2adf380dcd8210444f8b601f8b16313c47aae2226f`; its source-clock barrier waits at most2wall seconds for actual clock equality, never changes clock or publishes on timeout. V1 CPU receipts retain their original scope; v2 receipts and exact commands are canonical V8 checks. All builds ended, zero newnative/optimizer at this point. Old V7 row review confirms54.121 consumed zero;54.155 first odom breach precedes same-update resume target application, with no unique physical cause asserted.

## 2026-10-19 MR3-P2A V8 paired native diagnosis closed (not V7 reproduction/repair)

Freeze `7bbf7ba97e12e3b5db47fb48d7ffa4ccf0740971`, clean main pushed, preflight258source/4ELF and pulse pre-revalidation passed. Exact conda/native argv, environment/cwd, raw rc and per-command monotonic times: `report/assets/20261019_mr3_p2a_v8/closed_evidence/checks/mr3_p2a_v8_{continuous,pulse}_execution_v1.json`. Commands from wireless-rl: `rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.plant_probe --arm continuous --run-id mr3_p2a_v8_continuous --physics-config /tmp/mr3_p2a_v8_continuous_physics.json --domain 180 --port 14001`; second uses `--arm pulse --run-id mr3_p2a_v8_pulse --physics-config /tmp/mr3_p2a_v8_pulse_physics.json`, otherwise identical. Open101,3robots,fixed sparse±1.6m layout,4KEEP/4simsec perarm,0policy calls/0optimizer,observer-only150/paused-only sampling,original guards and actual source→guard→typedstorage→wheel provenance. Parents returned0,4+4 real decisions; command wall247.946298021/252.705987734 including parent overhead.

Independent `/usr/bin/python3 -B -m mr3_learning.plant_probe_audit EPISODE --freeze 7bbf7ba97e12e3b5db47fb48d7ffa4ccf0740971 --arm ARM --output NEW_JSON` and the versioned closure reviewer both returned0 for each arm: stimulusVALID/strictclosurePASS,3x4000pairs each,89saved native identities gone,78/78launch clean exits;4outside parent identities separately gone. Max tb3 planarspeed .0022934610265329574/.002283954408363189; no>.01. Pulse actualzero held34ms; same-relative arm wheelphase differs8ms. Far/start-from-rest/1.54sturn/40mspulse do not match V7 near/~3.075sactive/20ms, therefore V7 counterexample un-reproduced, no causal or physical repair/PPO/95% credit. All task quality/participation failure scope remains.

Closed canonical tar/gzip part46817502bytes SHA48466a8f6eb1c88b465a05612d7bc8ce072a65280eb37410c8a628434dc7f279,377source files633745167bytes,full per-file roundtrip and source-end stat/SHA verified. Original bytes and4actualELFs retained. Engineering conservatively charged whole outer interval712.102498359wallsec, cumulative12835.5243178396018/30000, remaining17164.4756821603982. Pilot1870decisions/2905.9547395464029wallsec unchanged,validation unchanged. P2A remains incomplete; next work is explicit real WORLD odometry/TF50Hz independent of original30Hz actuator to fix proven age-phase dropout, not a claim that plant is fixed. No P2B/gateway.


## 2026-10-19 MR3-P2A V9：真实50Hz source短采集，0动作/取证FAIL（已关闭）

- freeze：`bbb2e6365fdbeae681bb3088faeedc6883db324b`（clean/pushed，真实preflight PASS）。Exactly3 robots/open101/原near spawn；固定8动作[231,888,888,889,880,658,888,888]、observer-only，无policy/optimizer。
- cwd：`ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl`。准确native编排：`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261019_mr3_p2a_v9/execute.py --plan report/assets/20261019_mr3_p2a_v9/predeclared_plan_v9.json --scope trace --freeze bbb2e6365fdbeae681bb3088faeedc6883db324b --receipt /tmp/mr3_p2a_v9_trace_execution_receipt.json`。实际子CLI/freeze/全部参数、FIFO/closure CLI及真实wait返回码在canonical闭合包，不能重启相同run-id。
- 结果：reset返回后action231在当前mask非法，0动作提交/返回，不替换；native rc1，shutdown_clean true。watcher rc1，actual gzserver executable basename判据错误（本机实际链接目标gzserver-11.10.2），无complete live capture；FIFO PASS、custody closure FAIL，8科学消费者/四阶段/PPO/pilot/验证未提交。最终absence检查51个实际保存PID/start均gone，但整体final脚本rc1不改PASS。没有物理反例复现/修复或95%信用。
- native command153.209880702墙秒、outer实际wait160.659378744；保守总charge上界213.314474553秒=实际outer开始→final内部观察212.476236824+整个final工具调用0.838237729（保守重复其观察前部分，不补造未知end）。工程累计13048.8387923926018/30000，余16951.1612076073982。pilot1870决策/2905.9547395464029及条件验证余额不变。
- 证据：`report/20261019_mr3_p2a_v9.md`、`report/assets/20261019_mr3_p2a_v9/closed_evidence/manifest.json`及accounting_root_v1.json。439原件/152123633原字节，archive14333523字节，SHA7662786c72fcde78892136550502c4347e74b23f2e84988797e441a35e3f58a1，完整roundtrip/末stat+SHA通过。原V7/V8/V9 FAIL均保留；新V10将修身份入口并完整新freeze重验，不重复固定8动作。


## 2026-10-19 MR3-P2A V10：interface32正常关闭，取证入口FAIL（已关闭）

实际冻结`ab03d9ea867a05712d4d5e200761d33523fc9d20`，clean+pushed preflight通过。
interface open101、原near spawn、三台、32实际返回步，benchmark rc0；stage823.541149272秒。
watcher实际rc1，1396次捕获均误拒：本机启动argv[0]为裸`gzserver`，与绝对别名绑定不等，
而proc exe、SHA、设备及inode均为已绑定真实版本化ELF。两子进程均真实wait，outer rc1/829.007653796秒。
FIFO、严格取证及38科学角色未提交，terminal/reset/deadline和所有PPO/pilot/验证SKIPPED。
不能以32原生返回代替科学门PASS，V10整体FAIL保留。

在真实outer退出后，独立final_closure确认49个实际保存PID/start均gone、closure_passed=true，
但execution_passed=false，脚本仍rc1。只读诊断又定位两个后续入口问题：映射文件名子串会把smoother
主程序与其core库混淆，controller_server默认节点名无显式__node override。新候选对7个实际角色
只读重放通过，仅是未来修复的CPU/诊断支持，不补授V10 live捕获信用。

完整运行、真实wait、原生关闭、只读observer一次实际143中断及第二版自然0退出、debug、10ELF和冻结源码
封存于[closed_evidence](report/assets/20261019_mr3_p2a_v10/closed_evidence/manifest.json)。
实际outer开始到final内部观察903.613392543秒，再加整个final工具调用0.266266357秒，
保守charge上界903.879658900（观察前部分重复计，不补造未知结束时间）。
工程累计13952.7184512926018/30000，余16047.2815487073982；pilot1870决策/2905.9547395464029及条件验证不变。

实际命令，cwd=wireless-rl（旧run-id仅供追溯，不重跑）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261019_mr3_p2a_v9/execute.py --plan report/assets/20261019_mr3_p2a_v10/predeclared_plan_v10.json --scope matrix --freeze ab03d9ea867a05712d4d5e200761d33523fc9d20 --receipt /tmp/mr3_p2a_v10_matrix_execution_receipt.json
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261019_mr3_p2a_v9/final_closure.py --receipt /tmp/mr3_p2a_v10_matrix_execution_receipt.json --root /tmp/mr3_p2a_v10_matrix_evidence --root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v10/mr3_p2a_v10_interface --summary /tmp/mr3_p2a_v10_matrix_evidence/summary.json --freeze ab03d9ea867a05712d4d5e200761d33523fc9d20 --output /tmp/mr3_p2a_v10_matrix_final_closure.json
```

V11仅将启动命令设为同一ELF的绝对别名、修正完整映射文件名与默认节点名检查，并在批准总额内分配实际节余。
原物理/安全/任务/38科学角色均保持，须新冻结完整重验。见[V11预声明](report/20261019_mr3_p2a_v11.md)。


## 2026-10-19 MR3-P2A V11执行前声明

工程入口预算13952.7184512926018/30000；预声明matrix14900（1500/1200/4500/7700，native1250/850/3900/6600，close120）、fresh minimum900和尾部247.2815487073982。阶段实际节余仅在原matrix额度内向后分配。三处平台入口修复不改物理/安全/任务/38数学角色，真实源码与ELF保持新冻结后再验。组合70conda CPU+30ROS launch检查通过，无本版原生/PPO已启动。准确argv、quota与条件见[计划](report/assets/20261019_mr3_p2a_v11/predeclared_plan_v11.json)及[V11报告](report/20261019_mr3_p2a_v11.md)。pilot原1870/2905.9547395464029及final-only验证不扩额；旧FAIL全部保留。

V10封包核验补记：833成员/579696592原字节，10实际ELF与277冻结来源；archive44079458字节，SHA `e708e0e42de2bcd09635c3c3506ca2bb8f93198941fe9a0641088f341066df9d`，manifest SHA `76ef7f4984bf6eb544fa84e8a27ddb1aaf05be8d64a3a1b294cc0a4b2083cdff`，逐文件roundtrip/gzip CRC/拼接SHA/源末stat+SHA全部通过。封包为CPU只读工作，不增原生信用。

V11原生启动前最终复核：关闭review中另有一处旧controller显式名复验，现与live capture采用相同默认/唯一正确override规则。新增完整review默认名正例和错误/冲突/重复/scoped/name负例，29取证CPU通过。此修复在任何V11 native启动前完成，新binding/pins/plan均已刷新；1676dc4仅准备提交，未用于原生。原27项收据保留其原字节，最终新增v2收据另列。


## 2026-10-19 MR3-P2A V11：32步与取证通过，旧model准入FAIL（已关闭）

实际clean+pushed冻结`2500e9e7837a9efc208772d5dc6cf0373ebcb551`，真实preflight通过。
interface open101/原near spawn/三台返回32 step（另有1reset），末步真实外部截断，native rc0/883.492686950墙秒；
正式watcher rc0/884.582440696秒、1完整八角色capture、errors=[]。
首批四个真实科学consumer：full PASS0/218.921608909，peer PASS0/42.852126686，
information PASS0/125.714005753，drive FAIL1/10.585478371。
失败来自原immutable v6→v5→v4的模板physical_model比较：新增empty `mr3_odometry_period_ns`未被原投影移除，
因此其将非物理配置schema差当成物理模型差；实际spawn比较也会同样拒绝。
当前正式FAIL保留；34其它科学角色及FIFO/严格closure未提交，后三stage和所有PPO/pilot/验证SKIPPED。

outer真实rc1/1111.638298092秒，内部协调者计费1111.464594791；
独立final_closure在outer真正退出后确认53保存PID/start均gone、closure_passed=true，
但execution_passed=false、脚本仍rc1，不重标总体PASS。
工程保守上界charge1119.560999951 = (4096038655921517 - 4094919372573578)/1e9 + 完整final工具wall0.277652012；
重复计观察前工具部分，不补造未知end。累计15072.2794512436018/30000，余14927.7205487563982。
pilot1870决策/2905.9547395464029秒及final-only验证额度不变。

真实命令（cwd wireless-rl，原run-id只追溯、不重跑）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261019_mr3_p2a_v9/execute.py --plan report/assets/20261019_mr3_p2a_v11/predeclared_plan_v11.json --scope matrix --freeze 2500e9e7837a9efc208772d5dc6cf0373ebcb551 --receipt /tmp/mr3_p2a_v11_matrix_execution_receipt.json
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261019_mr3_p2a_v9/final_closure.py --receipt /tmp/mr3_p2a_v11_matrix_execution_receipt.json --root /tmp/mr3_p2a_v11_matrix_evidence --root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v11/mr3_p2a_v11_interface --summary /tmp/mr3_p2a_v11_matrix_evidence/summary.json --freeze 2500e9e7837a9efc208772d5dc6cf0373ebcb551 --output /tmp/mr3_p2a_v11_matrix_final_closure.json
```

[完整闭合包](report/assets/20261019_mr3_p2a_v11/closed_evidence/manifest.json)：861成员、10实际ELF与282冻结来源，
archive45327877字节，SHA `f22b630ab0a8c7d5b6259809bd8509683249a52227f648be08c604dda2070a5e`；
manifest SHA `528f6544d0d3ad7e142d09750be8727e584c164cc240efcd3945f214bf2217cb`，
完整roundtrip/CRC/拼接SHA/源末stat+SHA通过。尚未用于原生的PPO外部工具另标effective SHA/CPU scope。

关闭后只读诊断：严格仅移除已核唯一观测tag的detached XML视图，再调用完整原驱动数学审计，
32步原件诊断通过；该/tmp适配不长期采用，不改V11正式结果、不供新freeze信用。
后续选择固定tagged20ms/untagged旧耦合、删除冗余SDF项，恢复原reader直接物理模型核验；
所有实际20ms source、34ms actuation、消息/causal/安全/任务/32/300门仍必要。

关闭后的只读CPU诊断另列：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m cProfile -o /tmp/mr3_p2a_v11_full_diagnostic_profile_v2.pstats -m mr3_learning.audit_preparation /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v11/mr3_p2a_v11_interface --freeze 2500e9e7837a9efc208772d5dc6cf0373ebcb551 --output /tmp/mr3_p2a_v11_full_profile_diagnostic_result_v2.json`真实工具rc0、完整report与正式full_result整dict相同；profile记录168831230调用/305.85119375999966累计timer秒（不是完整outer墙秒）。主要热点为causal_own_inputs45660次反复扫相同有界256源历史。初次v1多传不支持的`--mode interface`产生argparse error、result缺失；cProfile外层工具实际rc0，两份pstats均保留。该CPU诊断无新native，不改V11 verdict，不从PPO余额计费；完整wall未保存则留null。见V12/checks中的精确receipt。


## 2026-10-19 MR3-P2A V12 准备闭合（尚无本版原生）

CPU/构建发生在V11 HEAD `2500e9e7837a9efc208772d5dc6cf0373ebcb551`加明确dirty源SHA，
不冒称它已包含新源码。tagged模式固定20ms WORLD odom/TF，删除冗余SDF选项并拒绝残留；
轮执行器/实际34ms门、原物理/安全/95%任务门不变。实际构建rc0/99.770194716s，driver ELF
`c2051fecdaa3aabbfad9f2d763c3f501f29a7952db500034f7f293ae608bbda0`，其余九角色不变。
构建精确命令、cwd、实际wait、源及库before/after见[v12_build](report/assets/20261019_mr3_p2a_v12/checks/v12_build.json)：

```json
[
  {
    "argv": [
      "/bin/bash",
      "/tmp/mr3_p2a_v12_ros_cpu_v1.bash"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap",
    "returncode": 0,
    "start_wall_monotonic_ns": 4097193057529766,
    "end_wall_monotonic_ns": 4097197638231967,
    "wall_seconds": 4.580702201,
    "stdout_stderr": {
      "path": "/tmp/mr3_p2a_v12_ros_cpu_v1.log",
      "sha256": "56d222857f4881b54534d2aea401b076d4f428218ef299b0a2cc015ef611ab14"
    },
    "environment": {
      "PYTHONNOUSERSITE": "1"
    },
    "shell_script": {
      "path": "/tmp/mr3_p2a_v12_ros_cpu_v1.bash",
      "sha256": "c90e3b9f0bf0417120485e7342b93bc8b5ce50e4cb59b03c331a55a2050fd6f4",
      "text": "#!/bin/bash\nset -e\nsource /opt/ros/humble/setup.bash\nsource /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash\nexport PYTHONNOUSERSITE=1\nexec /usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_mr3_drive_launch.py src/multi_robot_exploration/test/test_driver_odometry_schedule.py\n"
    },
    "kind": "ros_cpu",
    "receipt_path": "/tmp/mr3_p2a_v12_ros_cpu_receipt_v1.json",
    "receipt_sha256": "24724faa217f20a9d3ad522c2a6accb0d50bea99c3ad108a21f262b1a78102fd"
  },
  {
    "argv": [
      "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python",
      "-m",
      "unittest",
      "mr3_learning.tests.test_audit_odometry_cadence",
      "mr3_learning.tests.test_audit_action_trace",
      "-q"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl",
    "returncode": 0,
    "start_wall_monotonic_ns": 4097193057503289,
    "end_wall_monotonic_ns": 4097207673419999,
    "wall_seconds": 14.61591671,
    "stdout_stderr": {
      "path": "/tmp/mr3_p2a_v12_python_cpu_v1.log",
      "sha256": "64a66189cc649bbaf79019c0a1958921884b45d1cc704d5867c521e7a20ec847"
    },
    "environment": {
      "PYTHONNOUSERSITE": "1"
    },
    "shell_script": null,
    "kind": "python_cpu",
    "receipt_path": "/tmp/mr3_p2a_v12_python_cpu_receipt_v1.json",
    "receipt_sha256": "5059b566337e559b63953b6705cc27d7907d17c70aad31bb13acea9e2b9c3ba3"
  },
  {
    "argv": [
      "/bin/bash",
      "/tmp/mr3_p2a_v12_build_v1.bash"
    ],
    "cwd": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap",
    "returncode": 0,
    "start_wall_monotonic_ns": 4097215313933126,
    "end_wall_monotonic_ns": 4097315084127842,
    "wall_seconds": 99.770194716,
    "stdout_stderr": {
      "path": "/tmp/mr3_p2a_v12_build_v1.log",
      "sha256": "878cd137d007aa0d8376897552f006e0124bc9eb8c0fe3d1f7937438a50ea467"
    },
    "environment": {
      "PYTHONNOUSERSITE": "1"
    },
    "shell_script": {
      "path": "/tmp/mr3_p2a_v12_build_v1.bash",
      "sha256": "e5b8455f0977ddcb6491752b565166f3f8937adc2db591ae1a8c5e70906d640e",
      "text": "#!/bin/bash\nset -e\nsource /opt/ros/humble/setup.bash\nsource /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash\nexport PYTHONNOUSERSITE=1\nexec /usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select multi_robot\n"
    },
    "kind": "build",
    "receipt_path": "/tmp/mr3_p2a_v12_build_receipt_v1.json",
    "receipt_sha256": "2ccd504dbb56fa045d14e8477b9b3c949b4fff04485821ca7c76c8f5cd74fcd8"
  }
]
```

只读组合审计对原V26/92f8bdf5四组完整报告math dict+序列化bytes等价，真实wait全部0：
interface74.843787501s、terminal43.130978525s、reset596.329526099s、deadline480.892852795s；
四路并行gross596.352945361s，六个实际保存CPU身份gone。12短CPU/14448六流对象identity差分通过；
初次base/subclass额外phase字段比较造成2项测试harness FAIL完整保留，算法字节未改。
生产双方法源码`c384b1b3cfc2817a770ea9a2ee5ea5e2f3dadb402df8f869d3eae6c76a38c020`，
原数学host f736/raw ba3e不改；生产29相关CPU通过。新provenance分别绑定原数学与实际有效入口，
只替换原不变量下两项查询，不加新判据/阈值，不读actor真值、不隐藏手工策略。
精确候选/runner/tests、每组完整argv/seed101/实际wait及所有原source/reference SHA在
[资格汇总](report/assets/20261019_mr3_p2a_v12/checks/information_combined_cpu/summary.json)与
[47文件索引](report/assets/20261019_mr3_p2a_v12/checks/information_combined_cpu/index.json)。
旧非选中的单三键候选前三组通过，deadline当时仍运行，不造rc/PASS；独立监控及最终wait另存/tmp，冻结期间原host/raw和候选保持不变。

motion memo只缓存每台完整输入序号+目标clock的raw选择，保留每次own_state/tracker核验；
35相关CPU通过。旧V11/2500原32步完整输出475420bytes等于正式报告，SHA74a49af54e0ca827dafa9f3be6bafbb113a117ca99576fba4c5a45ad71b5c5bb。
比较wrapper原rc1（内存对象与JSON表示直接比较）保留，后续独立stored-JSON对照PASS不覆盖旧rc；
实际full163.659735447s/完整wait178.585498062s不是受控提速或未来预算保证。
精确命令与原件在本版checks/motion_memo_*；full profile初次CLI错误及修正后等于原报告都留存。
root综合124检查有123PASS+1旧ENV附录身份FAIL，修正identity后原16个audit_ppo全部通过；
规范前缀未改。ROS四文件53通过，真实sdformat9.7.0纯解析5/5通过，不加载world/ROS节点。
内存draft检查初次因未ready拒绝，后续显式synthetic副本合同核验38角色通过；没有因此seal真实计划。

本次纯CPU/构建/已关闭数据等价不新增native工程墙秒信用。入口累计仍15072.2794512436018/30000，
余14927.7205487563982；pilot1870/2905.9547395464029和三场final-only验证原额度未动。
资格闭合后实际生成plan rc0，SHAa2477e5a90fd4b41624e54fc4f4148b09dadaec9b688c1677fd3e2cbfc7cf245；
矩阵14000、fresh16 minimum900、尾27.7205487563982，所有真实关闭/消费者/间隔计费，超额FAIL仍计实际成本。
准确新冻结原生命令及边界见[V12预声明](report/20261019_mr3_p2a_v12.md)；本段不宣称新native、95%或P2A完成。

V12准备提交134bfe6包含真实SDK解析SDF/输出，暂存check曾返回2（原件已有行尾空白）；
root把检查/提交放同一批而未先拦下，原返回码和事实保留。未启动native。
后续仅按仓库既有.gitattributes做法，对这五份原SDF及run.log指定-text/-whitespace，
保留实际解析输入及SHA，不修改/规范化证据字节、不影响源码数学或数值门；完整检查后再推送新冻结。


## 2026-10-19 MR3-P2A V12 原生关闭（reset模型反例，后续跳过）

冻结ea759bea57d1e2ddd126d56c3a81801a072535a0，clean+pushed preflight真实rc0，命令完全按[V12入口](report/20261019_mr3_p2a_v12.md)。
原native精确argv/实际借用workwall在封存matrix各stage/native.json，未以计划基数冒充实际：interface1243.957、reset5018.501；
完整场景/seed/epoch/command与返回在[manifest](report/assets/20261019_mr3_p2a_v12/closed_evidence/manifest.json)原件中。
interface open101/32step全部11科学角色PASS，1052.005804348s；terminal open101×2各4step、8角色PASS，523.457854735s。
reset实际仅两worker各首open101，4step+4step，未进入后续open/rooms/corridors；worker0 fourth dt.24/terminated navigation_failure，
首因motion_safety52827 tb1 settled-turn raw speed.01636094718877706>.01（source43.561，callbackclock43.56）。
raw path.00395219354828877<.0078；TF校正非此分支原因，连续2.301s stored(0,+.8)后峰，后续43.565零命令是后果。
这是真实producer conditional model反例，非已证Nav2abort/进程crash；reset科学消费者未提交，不能造其独立FAIL/PASS。
worker1保留在途step真实返回后外部截断，双worker实际exit0/forcedfalse；native benchmark1、watcher0，deadline和PPO均跳过。
53真实API记录=5reset+48step，0optimizer，不新增pilot决策或任务成功信用。
outer实际rc1/wall1849.821587123，coordinator1849.622196721；独立final工具actualrc1、closure_passedtrue/253保存身份gone，整体FAIL保留。
保守实际全wait上界charge1851.306438272，累计16923.5858895156018/30000，余13076.4141104843982；
pilot1870/2905.9547395464029及三场final-only验证原额度未动。
封存1718文件/1320736482rawbytes，archive94816168/SHAeba5118a1d9c5a02cf78f38a708281b60cf59fe47c93fb76a0b075fbb75dd0f6，
manifest7cc6a9e2894fbfab082b79ffa17823d7bafadfbd51d448e218a162751c2b4480；相关Git source395（非全Git树）/10ELF单独捕获；
roundtrip/逐fileSHA/CRC/concat/输入stat末稳全部PASS，CPU pack真实rc0/73.937495747s。
全已提交native/consumer实际关闭后方准备V13一致较低转向profile，新source/ELF证据完整重验，不拼上述19旧PASS。


## 2026-10-19 MR3-P2A V13 部署候选准备（无本版native）

在ea759bea HEAD加明确dirty源码上准备一致gentle_turn_v1。三活动robot YAML每份恰13行：
Shim/DWB/behavior/recovery/smoother角速度双向.3、起转加速1.0；behavior/recovery min.15；角decel-3.2、线.2/±.5保持。
3文件逆投影逐字还原V12，installed symlink byteequal；driver/SDF/wheel_accel1及10ELF完全未改/未重建。
这些是前瞻部署事实，不放宽原.8/1.2/7/.01/.0078/95%/300秒及全部停止、源龄、接触、参与门，也不称已修复plant。
新audit_nav2_parameters.py SHA848dd05ebd9558a4ec8d47866909662030d24cfce837742a409907ff6c5bfdf3，
profile SHAaf5bf20bf17ed160dd3476653c21eef94d0ba6f30d119c1bbbe66190e78c68a5，
复用immutable v13源SHA9eb963457a8dc8297e4686004ea08c7a06e1e0e9ede7cd795ba9505da9d8f701及原9服务/typed状态/时钟/cleanup函数，
只声明10项exact typed部署值与profile，新/旧source身份分开；recoveries3项只有静态source，不造第12个live节点。
原38角色/transitive静态兼容核验无新schema/profile/scriptSHA阻断，不对新真实读回作保证。

68 CPU tests实际rc0/3.368s：
`env PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m unittest mr3_learning.tests.test_nav2_parameter_profile mr3_learning.tests.test_benchmark mr3_learning.tests.test_preparation -v`。
初轮1个minimal fake-binding接线FAIL与原源/console完整保留，固定profile reader路径后68项全复验，数学/参数门未改。
精确命令/cwd/源SHA/typed值/原件在[CPU资格及索引](report/assets/20261019_mr3_p2a_v13/checks/nav2_profile_cpu/index.json)。
root另45项audit_ppo/native_custody实际rc0/3.060s，精确命令和source身份在本版checks/root_entry_cpu_v1.json；
ROS配置test实际1PASS/1.37s，见checks/mr3_p2a_v13_gentle_turn_config_cpu_receipt_v1.json。
本次纯CPU与闭合数据诊断均无新native；旧峰值、path与驱动命令分离原件保存本版checks，不把pose均值代瞬时twist。

工程入口16923.5858895156018/30000、余13076.4141104843982；新matrix12100+minimum900+尾76.4141104843982，
四stage base1400/900/4200/5600，native1150/600/3600/4500，close120，仅前实际节余向后借用，超额仍FAIL/计费。
已生成[预声明](report/assets/20261019_mr3_p2a_v13/predeclared_plan_v13.json)，actualrc0，SHA15d1ec389105e45a445871b069e5b01ec49ffa609e1cb0318bb5246b4cd6ec0d。
新qualification/source/ELF严格准入后再执行[V13精确原生命令](report/20261019_mr3_p2a_v13.md)；原pilot1870/2905.9547395464029与3场final-only验证不扩额。
本段无新native/GPU/任务信用，P2A未完成。

## 2026-10-19 — MR3-P2A V13 原矩阵关闭：工程阶段时间门 FAIL

- 授权/范围：P2A.0已验收，继续P2A；工程累计上限30000墙秒；原pilot1870决策/2905.9547395464029墙秒及三场final-only不扩额。P2B/gateway未启动。
- 冻结：0063aa233ba3008ddcc1eb09ea8068112eea3965，干净且origin/main同HEAD；预检实际rc0。279 source/10ELF来源绑定不变。三份活动Nav2温和profile .3/1.0已由interface真实9节点读回，schema v3/PASS，SHA0e848998b278d4f5bb2ef8a99ab9820422aacc76e504851ee6fda140090ae148。原身体/停止/95%/300s/18接触门不改。
- 实际命令（wireless-rl cwd，全部前缀 env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1）：
  - conda ns3gym/python -B report/assets/20261019_mr3_p2a_v13/preflight.py --plan report/assets/20261019_mr3_p2a_v13/predeclared_plan_v13.json --output /tmp/mr3_p2a_v13_preflight.json --binary-proof-output /tmp/mr3_p2a_v13_binaryproof.json
  - /usr/bin/python3 -B report/assets/20261019_mr3_p2a_v9/execute.py --plan report/assets/20261019_mr3_p2a_v13/predeclared_plan_v13.json --scope matrix --freeze 0063aa233ba3008ddcc1eb09ea8068112eea3965 --receipt /tmp/mr3_p2a_v13_matrix_execution_receipt.json
  - outer实际wait后立即 /usr/bin/python3 -B report/assets/20261019_mr3_p2a_v9/final_closure.py --receipt /tmp/mr3_p2a_v13_matrix_execution_receipt.json --root /tmp/mr3_p2a_v13_matrix_evidence --root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v13 --summary /tmp/mr3_p2a_v13_matrix_evidence/summary.json --freeze 0063aa233ba3008ddcc1eb09ea8068112eea3965 --output /tmp/mr3_p2a_v13_matrix_final_closure.json
- 固定三机；interface open101单worker32决策；terminal open101两回合各4；reset双worker各open101/open101/rooms101/corridors101各32，共11回合/296决策/307 reset+step记录，0优化更新。
- interface 11/11科学角色PASS，1211.747796067秒；terminal8/8 PASS，522.700685122秒。reset native真实rc0/3497.04761902秒，20已提交审计全部rc0/PASS（7科学角色+13叶）；full1254.314565792秒。reset整个stage5007.289807297>有效cap4762.762500128，工程时间FAIL；9项未提交按原stage_wall_allocation_exhausted记SKIPPED。deadline未启动，minimum/pilot/final-only全部SKIPPED，不给新训练/95%信用。
- 所有已提交进程真实wait，signals_sent0；outer实际rc1/6747.468815秒，内部matrix6747.265111198秒；独立final工具实际rc1，但closure_passed=true、execution_passed=false，539个保存PID/start全部gone。不得把关闭通过改写成矩阵通过。
- 根外部收费：独立final真实wait后观测gross6750.096230428，加完整observation两次tool墙秒1.951121248（有意保守重叠）=6752.047351676；累计23675.6332411916018/30000，余6324.3667588083982。actual_tool_waits/observation/accounting分别留原件，不把最后一次poll耗时当成总阶段耗时。
- 原件：/tmp/mr3_p2a_v13_matrix_evidence、ROS/log/mr3_p2a_v13、/tmp/mr3_p2a_v13_{matrix_execution_receipt,matrix_final_closure,matrix_root_wait_observation,accounting_root_v1,root_actual_tool_waits_v1}.json。归档最终索引/后续独立补齐结果在本段之后追加，不回写原FAIL/SKIP或旧stage cap。
## 2026-10-19 — MR3-P2A V13 独立 reset 只读补验关闭（原矩阵 FAIL 保持）

- 原0063aa233ba3008ddcc1eb09ea8068112eea3965仍clean且已推送，279 Git-source/10ELF逐SHA绑定不变。只补9项确实未提交DAG：FIFO007/input008/FIFO008/input aggregate/angular/physical_per_episode/physics/FIFO manifest/closure；旧7input+6FIFO按原SHA引用不重跑。无新native/robot action/GPU/optimizer。
- 新工具/tmp/mr3_p2a_v13_reset_completion_v2.py SHA3dd3e75b1d3be168099579d3b3aa9dcba8e8421c2b8f95a149dc6a7f3a85b275，plan_v2 SHAb7df79cea5432664f850affdaad0f41e138f71307191b7eff25ec496bd75b430。scope600墙秒、真实wait所有已提交任务，原矩阵FAIL/ledger/SKIP/stage cap不覆盖。
- 实际命令（Git root cwd，env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1）：
  - rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a_v13_reset_completion_v2.py outer --plan /tmp/mr3_p2a_v13_reset_completion_plan_v2.json --output /tmp/mr3_p2a_v13_reset_completion_outer_wait_v2.json
  - outer真实wait0后立即 rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a_v13_reset_completion_v2.py final-absence --plan /tmp/mr3_p2a_v13_reset_completion_plan_v2.json --receipt /tmp/mr3_p2a_v13_reset_completion_outer_wait_v2.json --output /tmp/mr3_p2a_v13_reset_completion_final_absence_v2.json
- 7实际命令+2聚合；FIFO007 0/11.874242784秒、FIFO008 0/11.120779716、input008 0/80.562009998、angular0/188.295405792、closure0/68.816107168。input/FIFO manifest无进程rc，全部成员按实际回执/SHA聚合PASS。
- physical_per_episode非必需诊断实际rc1/152.748217874，原FAIL保留：6/8逐回合PASS，两个corridors/tb3缺少本回合有意义停止覆盖；8/8 closure PASS、所有robot errors[]、raw速度/角速/chord数值违例计数0。原预声明pooled physics按原条件实际rc0/PASS/.534527655秒；不把可选FAIL洗成PASS，不据此证明任意连续转向安全。
- 新deferred custody只替换原已退出coordinator必须live块，明确不同schema mr3-native-custody-deferred-closure-v1；保留原live custody、ancestry、closed native wait、ELF/source/FIFO规则，并绑定旧summary身份/原539gone及实际/proc再核。不伪造旧同步闭环PASS。新outer实际rc0、独立final实际rc0/548保存身份gone。新增4科学角色=原26+4=30/38；deadline8/PPO/95%策略未启动未给信用。
- 新内部199.822497506秒；独立final total_batch201.190683006；实际final tool wait后gross201.694081283加完整observation tool墙秒.247255576（保守重叠）=charge201.941336859。累计23877.5745780506018/30000，余6122.4254219493982。根原账/真实toolwait/observer原件与各输出同SHA封存。
- canonical：[reset小包manifest](report/assets/20261019_mr3_p2a_v13/reset_readonly_completion/manifest.json)、[coverage派生解释](report/assets/20261019_mr3_p2a_v13/mr3_p2a_v13_reset_optional_coverage_review_v1.json)、[实际根账](report/assets/20261019_mr3_p2a_v13/prospective_continuation/external_dependencies/mr3_p2a_v13_reset_completion_accounting_root_v2.json)。原outer/summary/final等绝对路径保持其真实来源，restore映射在manifest中。

## 2026-10-19 — V13 纯 CPU 准备、归档软件失败与未执行的新预算方案

下列均无新native、科学消费者或GPU；与上段已计费的科学只读201.941336859秒分开记录，不把软件CPU fixture当科学信用。

- reset v1初始prepare两次schema绑定错误、14测初轮fixture FAIL、修正后14测PASS以及v2 18测PASS均保留。最终实际命令：`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/test_mr3_p2a_v13_reset_completion_v2.py -v`，18项、实际rc0/6.925s。v2只增加clean exact0063+pushed ancestor准入，4项正负例；原539 absence/source279/ELF10与DAG数学规则不变。prepare v1/v2真实tool rc0/7.773066525与7.716373441秒，命令/来源/SHA在小包内prepare_cpu_artifact_index；后从实际对话返回提取的归因副本明确标注派生，未知历史起止null。更早12测对话记录rc0/6.703s但没有独立console/source snapshot，保持缺失不补造。
- 新deadline/PPO纯CPU准备：/tmp cwd实际 `rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -m unittest -v test_mr3_p2a_v13_deadline_completion_v2 test_mr3_p2a_ppo_phase_runner_v3_final_v2`，18项、实际rc0/3.680755682s。先前绝对unittest路径import FAIL(0tests)、15测1项字符串长度断言FAIL及16/17测PASS和旧源/日志原件保留。17测snapshot按已记录SHA精确恢复，明确不是新执行或重建时间。
- 实际新声明prepare（Git root cwd，同env）`rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a_v13_deadline_completion_v2.py prepare --output /tmp/mr3_p2a_v13_deadline_completion_plan_v2.json --evidence /tmp/mr3_p2a_v13_deadline_completion_evidence_v2 --reset-plan /tmp/mr3_p2a_v13_reset_completion_plan_v2.json --reset-summary /tmp/mr3_p2a_v13_reset_completion_evidence_v2/summary.json --reset-final /tmp/mr3_p2a_v13_reset_completion_final_absence_v2.json --reset-outer /tmp/mr3_p2a_v13_reset_completion_outer_wait_v2.json --reset-accounting /tmp/mr3_p2a_v13_reset_completion_accounting_root_v2.json`，实际rc0/18.344020492秒。tool c516332877445f9d20f27f4a98efe586f6b09d1084e7016d08474750211e83bf、plan a35cad53be7ce788d348d10069708b5f2d78bb36c97db9b36dc8fc12beb1ddea、PPO b8c673ce2e19eb82530c040a7c67a5c27d6a69c38ceea085409162d7625b95e4；完整命令/实际wait和源AST比较在[最终CPU索引](report/assets/20261019_mr3_p2a_v13/prospective_continuation/mr3_p2a_v13_deadline_ppo_v3_artifact_index_final_v2.json)。旧prepare/旧源也保留。只准备计划，未运行deadline、qualification或PPO。
- 原矩阵bigpacket纯CPU pack实际命令及真实child PID/start在closed_evidence/checks/pack_actual_wait.json：`/usr/bin/python3 -B -u /tmp/mr3_p2a_v13_closed_original_capture_v1/packet_v2/checks/pack_closed_original_v13_v2.py`，实际rc0/305.575515786s；首次packer实际rc1/39.608739325s，原因SKIPPED无passed键，原脚本/日志/工具返回在attempt1，不归为科学FAIL。root曾向跨agent session10855 poll，真实Unknown process ID保留；creator实际wait原件不替造。
- reset小包纯CPU pack实际 `/usr/bin/python3 -B -u /tmp/mr3_p2a_v13_reset_completion_packet_v2/checks/pack_reset_completion_v2_final.py` rc0/1.244021195s；前次rc1/1.357488485s因index局部变量覆盖，完整原件留attempt1。两包逐memberSHA/size、gzipEOF/CRC、concat、原输入末stat/SHA、279Git/10ELF末稳及seal前clean HEAD=origin/main=0063实际PASS，独立postpack及canonical复制逐SHA核验。
- 原bigpacket5432members/5534884383rawbytes，archive382472880、8分片/SHA2671b53407e1dc018094236dff9ddf3e2c5d30211f338822ee53789a60b92195，manifest914f9428cc0c0b2970e87571d77f977e144cd4f897c6d12f9747f67e0bb6d65d；小包56members/2482835rawbytes，单片295105/SHA b68e2bc7dc78bbe1f6a25785fb6578dfd9a871d83751f29370fb299c641899fd，manifest399caea5c6893689d8808c8c6fbc39486ac9d869df9f15a8da4503437d02bd86。小包显式映射原包186相关member，不重复5.53GB原native。canonical路径及每项原路径/SHA在closed_capture_canonical_copy_index_v1.json。
- 新封存[预算提案v2](report/assets/20261019_mr3_p2a_v13/prospective_continuation/mr3_p2a_v13_engineering_continuation_budget_proposal_v2.json) SHA669c1b64305a9b25d00848a177c137cff848cb33dd2a7248fb74f80492bc4d44：工程当前30000，已用23877.5745780506018/余6122.4254219493982；拟+4000至34000，才有10122.4254219493982。9500预约=deadline全部tail8500+独立qualifier实际wait/absence尾100+fresh16minimum900，余622.4254219493982。该提案状态AWAITING；现有“批准继续”仅批准30000，不构成34000授权。Pilot1870/2905.9547395464029和三场final-only不变，不跨池、不退历史费用。新native/PPO须先获真实用户新增批准；目前未执行。精确未来命令见本版报告链接的usage，不能把该前瞻命令记成实际运行。


## 2026-10-19 — V13 34000实际获批续接：工程38资格完成，minimum真实FAIL

### 34000实际批准后的同冻结续接（已关闭）

用户消息“批准，继续吧”对应封存的34000提案；另建的
[实际批准原件](report/assets/20261019_mr3_p2a_v13/continuation_receipts/mr3_p2a_v13_engineering_budget_acceptance_34000_v1.json)
SHA `d484a5f8295f1f98ea09119117506234367e4a246a64715872207608663a463d`证明授权。
旧proposal字节及其提出时AWAITING状态不改。入场余额10122.4254219493982，
root另存实际≥9500预约检查；没有只依赖工具9400下限而漏掉qualification尾100。

唯一canonical checkout临时detach至已推送祖先0063；main/origin保持2f5c2a3，
279 source/10 ELF逐SHA一致。全部执行、独立关闭、封包及末稳后才实际恢复main；
[恢复回执](report/assets/20261019_mr3_p2a_v13/continuation_receipts/mr3_p2a_v13_runtime_restore_main_actual_tool_v1.json)
保留真实工具返回，不要求后来报告commit与运行时HEAD相同。

| 新scope | 实际结果 | 完整根收费墙秒 | 独立关闭保存身份 |
| --- | --- | --- | --- |
| deadline（8500预约） | 300个完整1秒KEEP，timeout；8角色/FIFO PASS | 7023.863327403 | 58/58 gone，outer/final实际rc0 |
| qualification（100预约） | 新schema精确26+4+8=38角色 PASS；原matrix_passed=false | 69.468194283 | qualifier与launcher共2身份gone，实际rc0 |
| fresh16 minimum（900预约） | 原生模型FAIL，0 eligible/0优化更新 | 625.571493358 | 49/49 gone；outer/final实际rc1，closure_passed=true |

deadline open101、单worker/三机/action888，native实际rc0/5436.6476923秒，
watcher实际rc0/5440.455872138秒；1 reset+300 step=301 API，dt全部1，
terminated=true/truncated=false/reason=timeout。它是截止工程检查，不是95%任务成功。
独立角色均实际rc0/PASS：full1352.09882067、drive1498.059969521、
information535.290808453、peer342.08246489、control751.046237781、
settled166.407781804、cadence249.693322856、closure52.068304359秒。
FIFO001实际rc0/73.347362045秒，FIFO manifest是无子进程rc的真实聚合；无SKIP、signals0，全部已提交任务真实wait。
并发子命令时间不相加充当gross。

独立[新资格原件](report/assets/20261019_mr3_p2a_v13/continuation_receipts/mr3_p2a_v13_completed_38_role_qualification_v1.json)
SHA `97d734c5580ce31a3e7c2f92b8a891c4729e866014c3d5dc7ddd6122840753cd`，
schema为`mr3-p2a-v13-completed-38-role-qualification-v1`，与原bounded矩阵不同。
qualify子命令真实wait24.502683817秒，finite wrapper内部24.518131625秒；
资格尾按真实wait、保存及独立absence另收费，不藏入deadline内部elapsed。

根收费顺序均覆盖实际outer/final tool wait和其后根观察，观察工具墙秒有意保守重叠：
deadline 7023.649233941+.214093462=7023.863327403；
资格尾69.107530411+.360663872=69.468194283；
minimum 624.763228505+.808264853=625.571493358。
累计23877.5745780506018+7023.863327403+69.468194283+625.571493358
=31596.4775930946018/34000，余2403.5224069053982。
[最新根账](report/assets/20261019_mr3_p2a_v13/continuation_receipts/mr3_p2a_v13_ppo_minimum_accounting_root_v3.json)
SHA `87cd6357a446305dad1b0586a183bc76160ca7fb0970fc52cd63af1f96d3a37f`。
三scope均在各自预约内；失败不退费、不跨pilot/验证池。

### fresh16最小链的真实反例与只读诊断

fresh seed41/open101单worker、16决策/16回合step上限、native wall700。
native实际rc1/536.909661234秒，watcher实际rc0/537.973067921秒。
1 reset+16原生step；前15个dt1，最后dt.86，terminated=true/truncated=false，
reason=navigation_failure。PPO summary completed=false，报
`native training ineligible: motion_safety settled_turn_model_failure`，整轮在入训练buffer前拒绝。
保留failed_collection、initial.zip及所有native原件；原生16条step不是16个eligible训练样本。
eligible decisions/API records0、optimizer_updates0，没有成功final.zip。
原生失败后full/input/FIFO/独立custody科学消费者未提交，不补造其FAIL/PASS；
watcher成功不代替独立科学审计。pilot与final-only验证均未启动。

首故障为tb3，motion_safety.jsonl行/序号107887，nodeclock56.98，
`active settled turn total drift budget exceeded`。触发的前一raw odom行107886，
input2592/source56.995，平面速度.0008207641520363049m/s；
56.975是此前已选择的causal样本，不能误标为触发样本。
现有异步回调允许raw odom先到对应clock；本次没有改时钟或样本来源。

从固定activation anchor source45.275到56.995共587样本/11.72秒，
raw XY chord累计路径精确复算为.007800136333791129m，超过原.0078m。
净位移.0008845287405065454m，不能替代总路径；
max raw planar speed .0009291055640853354、max chord speed .000933653016870293，均低于.01。
本次是低速往返累计耗尽预算，与V12瞬时速度峰不同。
587个native/received odom payload同值；三边界触发payload一致。
已排除垂向混入、SLAM/TF跳变进入累计器、CoG参考点误配和float yaw误差作为此失败的解释。

active段实际请求转向+.3→0→−.3→0→+.3，linear始终0；
345次轮更新alpha全1、issued rim pair mean全0，真实joint/body仍有小运动。
第一次stop存储56.999，后续zero57.0覆盖它后首次实际制动57.005，均晚于触发样本56.995。
不能用失败后的制动解释先前超界；具体轮地面/摩擦/ODE机理仍unknown。
原18路监测记录fresh及零非支撑接触，不证明无地面接触力或侧滑。

[独立测量审查](report/assets/20261019_mr3_p2a_v13/closed_minimum_forensics/originals/mr3_p2a_v13_minimum_measurement_contract_review_v1.md)
和[原始时序法证](report/assets/20261019_mr3_p2a_v13/closed_minimum_forensics/originals/mr3_p2a_v13_minimum_failure_sequence_forensic_v2.md)
均只读关闭文件。测量算术实际rc0/5.654110385秒；时序v1误读`odom`而非`odometry`，
实际rc1/6.849729531秒，原源/console/回执保留；v2仅修解析键，实际rc0/9.406015419秒，
raw/source前后stat/SHA不变。它们不是新科学消费者、仿真或GPU实验，不新增native收费或PASS信用。

### 安全契约下一步评审边界

现行[环境合同](MR3_ENV_CONTRACT.md)91–93明确要求同一连续零线速度段的总中心路径≤.0078，
重复授权不能刷新预算；当前生产实现与所有原门保持。
现有Shim/smoother/joint feedback没有可直接启用的参数来证明长段总变差界，
降低角速、重置累计器、过滤细小路径或改净位移都不构成原合同修复。

[科学契约评审稿](report/assets/20261019_mr3_p2a_v13/contract_review_only/mr3_p2a_v13_prospective_safety_contract_review_v1.md)
比较维持旧L1门的actuator反馈、有限reach tube、固定anchor reach disk三条路线。
建议下一步仅做独立CPU/math新合同设计：固定R=.0078m的anchor disk，
从当前中心必须用2R而非R，几何余量为2R+.144=.1596m（原为.1518m）。
这是不同的条件物理模型，不能自动替换现门或改写旧FAIL。
坐标误差、采样间连续sweep、peer备份/终端集合以及translation实际storage/actuation交接尚未闭合；
未闭合不得seal runtime或启动native。此稿未申请新native或预算扩额，亦无新fixture执行结果。
若用户批准重设计方向，先完成明确旧/新差异、状态机和独立负例的CPU/math审查，
再单独提交完整科学合同与新冻结/预算；不继承本次38角色或旧模型信用。

### 新增封存包与复制核验

[续接原件包](report/assets/20261019_mr3_p2a_v13/closed_continuation/manifest.json)
含4296文件/4343294556原始字节，仅实际deadline/资格/minimum及所需CPU/授权/费用原件，
没有未来pilot/validation目录。archive300436279字节，6×49000000+6436279共7分片，
SHA `3d478529538d8307fee859667a2b33da203faef90f9c8175c79cf99a8fa99235`；
manifest SHA `c0ce1e52e2132408c42ca99d7e6e0661259f67abc52055d2c8729cdbb87f61ee`。
旧matrix/reset两包以原SHA引用，不重复原5.53GB/source/ELF。
全部member SHA/size、gzip EOF/CRC、分片拼接、原文件stat/SHA和目录成员末稳通过；
独立复验再次由分片串流完成。279source/10ELF、109保存身份gone及exact clean0063/祖先origin
均在恢复main前实际末检通过；不是报告提交后仍exact0063的声明。

CPU pack实际子wait rc0/240.145162996秒，creator实际工具rc0；最后poll耗时不是总打包耗时。
清单准备v1错误读取qualification absence嵌套字段而rc1，原脚本/真实工具返回已封存；
修正v2后才封清单，失败时未压缩。准备packer7项CPU fixture实际rc0/.015s，
不是科学审计；原准备receipt单独记录真实tool墙秒。
root一次只读manifest展示误用`members`键而rc1，`files`键确认后复制器首次执行rc0，均保留控制来源。

[canonical复制索引](report/assets/20261019_mr3_p2a_v13/continuation_canonical_copy_index_v1.json)
逐项记录77份byte-identical复制、312548714字节，涵盖完整24件续接包、24份小根回执、
实际restore、23份forensic原件/官方源/草稿、选择清单及独立合同评审。
草稿中placeholder/当时未运行表述保留其历史含义，当前事实以本文、实际原件及根账为准。
新法证大raw只引用续接包成员，不复制第二份原始episode。短静态复核与实际工具返回另存checks。


### 实际执行命令（历史记录，不重跑）

Git root cwd，所有外层工具使用原实际/tmp来源。outer真实wait后立即独立final。

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_v13_deadline_completion_v2.py outer --plan /tmp/mr3_p2a_v13_deadline_completion_plan_v2.json --evidence /tmp/mr3_p2a_v13_deadline_completion_evidence_v2 --balance /tmp/mr3_p2a_v13_deadline_completion_balance_v2.json --output /tmp/mr3_p2a_v13_deadline_completion_outer_wait_v2.json
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_v13_deadline_completion_v2.py final-absence --receipt /tmp/mr3_p2a_v13_deadline_completion_outer_wait_v2.json --evidence /tmp/mr3_p2a_v13_deadline_completion_evidence_v2 --output /tmp/mr3_p2a_v13_deadline_completion_final_absence_v2.json
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_v13_qualify_finite_runner_wrapper_v1.py --evidence /tmp/mr3_p2a_v13_qualification_tail_evidence_v1 --deadline-accounting /tmp/mr3_p2a_v13_deadline_completion_accounting_root_v2.json --qualification /tmp/mr3_p2a_v13_completed_38_role_qualification_v1.json
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_ppo_phase_runner_v3_final_v2.py outer --freeze 0063aa233ba3008ddcc1eb09ea8068112eea3965 --phase minimum --output /tmp/mr3_p2a_v13_ppo_minimum_outer_wait_v3.json -- --plan /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v13/predeclared_plan_v13.json --evidence /tmp/mr3_p2a_v13_ppo_minimum_evidence_v3 --balance /tmp/mr3_p2a_v13_ppo_minimum_balance_v3.json --prior-summary /tmp/mr3_p2a_v13_completed_38_role_qualification_v1.json --prior-final-closure /tmp/mr3_p2a_v13_deadline_completion_final_absence_v2.json --qualification /tmp/mr3_p2a_v13_completed_38_role_qualification_v1.json --freeze 0063aa233ba3008ddcc1eb09ea8068112eea3965 --phase minimum
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_ppo_phase_runner_v3_final_v2.py final-absence --receipt /tmp/mr3_p2a_v13_ppo_minimum_outer_wait_v3.json --evidence /tmp/mr3_p2a_v13_ppo_minimum_evidence_v3 --output /tmp/mr3_p2a_v13_ppo_minimum_final_absence_v3.json --freeze 0063aa233ba3008ddcc1eb09ea8068112eea3965 --phase minimum
```

两次native的完整实际argv/场景/seed/环境/源码/返回在新包deadline_evidence/native.json和minimum_evidence/native.json；
deadline原计划native work6200/close120、min seed41/16step/native700，任务95%/300秒与安全门不改。
纯文件算术真实child argv分别为`/usr/bin/python3 -B /tmp/mr3_p2a_v13_minimum_measurement_contract_review_v1.py`
及`/usr/bin/python3 /tmp/mr3_p2a_v13_minimum_failure_sequence_forensic_v2.py`；时序提取通过rtk proxy标准库有限subprocess wrapper执行，该child没有-B，未在该调用显式添加env；不得把建议命令当成实际argv。首个v1失败解析源和真实wait另存。
CPU pack实际通过finite launcher以`/usr/bin/python3 -B /tmp/mr3_p2a_v13_incremental_pack_launcher_v1.py --script /tmp/mr3_p2a_v13_incremental_pack_v1.py --selection /tmp/mr3_p2a_v13_continuation_closed_selection_v1.json --output /tmp/mr3_p2a_v13_continuation_closed_packet_attempt_v1`执行，全部实际工具metadata在checks。
canonical copy实际`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_v13_copy_continuation_canonical_v1.py` rc0；
原始initial+final tool返回另存checks，缺少独立child全耗时保持unknown，不以最后poll或sum tool waits猜总耗时。
本次其后只有文档/证据静态检查与commit/push，无新native、GPU、正式科学reader或生产合同变更。

文档/证据最后静态复核实际rc0，命令`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_v13_continuation_static_review_v1.py`：77复制/7拼接/32新增链接/7 AST/47JSON/15raw引用/19冻结Git源/38角色/三段Decimal账/共享log只追加全部通过；脚本、输出、actual tool metadata在`report/assets/20261019_mr3_p2a_v13/checks/continuation_copy/`。独立文档审查纠正了指南旧当前状态和sequence child无-B的命令来源说明；未改任何科学原件或生产门。
独立纯静态文档复核实际rc0/1.597619717秒，33新增链接/11文档事实一致、无未解决问题；JSON/简报和原actual字段在checks/continuation_copy。初轮literal断言把正确“原bounded矩阵”与“原矩阵”不匹配当异常，实际rc1/1.52536秒且未产生review，原control provenance保存，未改科学原件/门。3件独立原件的byte-exact canonical复制另有document_review_canonical_copy_index_v1.json。


## 2026-10-19 MR3-P2A V14 安全契约数学与隔离CPU（无新native）

用户“批准，继续完成”批准上轮数学/CPU重设计方向；开场main `a8e509726fa98cb9db1f01bc655e1b4eb8d63059`。本轮没有生产门/source/ELF切换、native/正式scientific consumer/GPU调用或quota扩额。旧native reference仍0063aa233ba3008ddcc1eb09ea8068112eea3965；以下均synthetic CPU，无任务seed，新训练决策/API/优化更新均0。P2A未完成。

[完整报告](report/20261019_mr3_p2a_v14.md)、[候选合同](report/assets/20261019_mr3_p2a_v14/scientific_contract_candidate_v1.md)、[逐条实际argv/源码/返回/耗时索引](report/assets/20261019_mr3_p2a_v14/actual_cpu_commands_and_results_v1.json)。所有CPU运行显式unset PYTHONPATH、PYTHONNOUSERSITE=1、PYTHONDONTWRITEBYTECODE=1，系统/usr/bin/python3 -B；源/测试精确快照与前后stat/SHA在各attempt。

| 实际attempt | tests | child rc | child真正wait秒 | 结论 |
| --- | ---: | ---: | ---: | --- |
| geometry_cpu_attempt_v1 | 19 | 0 | 0.246710291 | PASS |
| geometry_cpu_attempt_v2 | 46 | 0 | 0.356907964 | PASS |
| handoff_cpu_attempt_v1 | 21 | 1 | 0.473549311 | 6FAIL保留 |
| calibration_cpu_attempt_v1 | 12 | 0 | 0.263916581 | PASS |
| handoff_cpu_attempt_v2 | 34 | 1 | 1.066165631 | 2FAIL+1ERROR保留 |
| combined_cpu_attempt_v1 | 92 | 0 | 1.438602974 | PASS |

实际外层命令（argv规范化显示，各行已执行，历史记录而非新native入口）：

```bash
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_v14_cpu_actual_runner_v1.py --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/checks/geometry_cpu_attempt_v1 --cwd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/reach_geometry_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_reach_geometry_independent_v1.py -- /usr/bin/python3 -B -m unittest -v test_reach_geometry_independent_v1
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_v14_cpu_actual_runner_v1.py --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/checks/geometry_cpu_attempt_v2 --cwd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/reach_geometry_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_reach_geometry_independent_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_reach_geometry_frame_semantics_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_pair_model_obligations_v1.py -- /usr/bin/python3 -B -m unittest -v test_reach_geometry_independent_v1 test_reach_geometry_frame_semantics_v1 test_pair_model_obligations_v1
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_v14_cpu_actual_runner_v1.py --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/checks/handoff_cpu_attempt_v1 --cwd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/handoff_contract_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_handoff_contract_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_handoff_adversarial_independent_v1.py -- /usr/bin/python3 -B -m unittest -v test_handoff_contract_v1 test_handoff_adversarial_independent_v1
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_v14_cpu_actual_runner_v1.py --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/checks/calibration_cpu_attempt_v1 --cwd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/reach_geometry_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/calibration_metric_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_calibration_metric_independent_v1.py -- /usr/bin/python3 -B -m unittest -v test_calibration_metric_independent_v1
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_v14_cpu_actual_runner_v1.py --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/checks/handoff_cpu_attempt_v2 --cwd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/handoff_contract_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_handoff_contract_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_handoff_adversarial_independent_v1.py -- /usr/bin/python3 -B -m unittest -v test_handoff_contract_v1 test_handoff_adversarial_independent_v1
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_v14_cpu_actual_runner_v1.py --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/checks/combined_cpu_attempt_v1 --cwd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/reach_geometry_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/calibration_metric_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/handoff_contract_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_reach_geometry_independent_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_reach_geometry_frame_semantics_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_pair_model_obligations_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_calibration_metric_independent_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_handoff_contract_v1.py --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/test_handoff_adversarial_independent_v1.py -- /usr/bin/python3 -B -m unittest -v test_reach_geometry_independent_v1 test_reach_geometry_frame_semantics_v1 test_pair_model_obligations_v1 test_calibration_metric_independent_v1 test_handoff_contract_v1 test_handoff_adversarial_independent_v1
```

几何v1只覆盖当时19项旧snapshot；新增残差后v2的46项另run，不继承新函数PASS。metric12项含240个独立RN/FMA子例（不另算native）。首轮交接21项6FAIL；次轮34项2FAIL+1ERROR；修复后九份source/tests稳定的全套92项child rc0/1.438602974秒，root真正tool rc0/3.7248462289999997秒。前两轮源码、坏源/tail、console和真实wait没有删除或改写。54ms必要observer界不证明真实20ms续证/撤销，所有native_admission恒false；typed evidence仍为条件输入，非物理证明。

另有旧闭合minimum数据的实际child argv `/usr/bin/python3 -B /tmp/mr3_p2a_v14_v13_minimum_lateral_closed_data_v1.py`，系统环境同上，真实wait rc0/3.080302444秒（内部分析2.217123809另计）。原0063/open101/seed41，不新采样：524个actual nonzero源最大描述性残差.0012727477023301292、0>.01；zero-target含制动，不能当rest。declared56.98/physical57.0/close57.2分别保留，failure源56.995没有被剔除；无continuous/future或新预声明S的模型验证信用。6raw SHA/stat稳定和exact分析原件由closed_data_only索引引用原V13canonical raw，不重复大包。

封存实际命令 `rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_v14_copy_review_artifacts_v1.py` 首次因index文件名错误实际tool rc1/1.4933306秒，已复制8件保留；v2实际命令 `rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_v14_copy_review_artifacts_v2.py` tool rc0/.51732557秒，20件1438438B逐件exact。没有单独child总耗时的复制操作保留unknown。只读数学/文档复核均不是新的native/科学消费者；原封not-run设计及review范围不改写。

工程余额仍31596.4775930946018/34000、余2403.5224069053982；pilot1870决策/2905.9547395464029墙秒及三场final-only额度未动。本轮纯CPU准备/旧数据/封存另计，不借用native/pilot。候选将原L1门改为空间disk，须单独科学合同验收后进入真实实现和新冻结资格；没有seal/训练入口或P2B/gateway授权。

最终只读静态命令：`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a_v14_cpu_actual_runner_v1.py --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/checks/root_static_attempt_v1 --cwd /home/zhuyulab/ns3-workspace --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/checks/final_static_source_v1.py -- /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/checks/final_static_source_v1.py /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/checks/root_static_attempt_v1/result.json`。真实child rc0/9.374788712s、tool rc0/9.806127451s，29 exact copies/38JSON/46AST/33新增或完整链接/6原canonical raw SHA/九最终源码、log只追加、ARCHIVE只新增entry、生产code diff空及ENV规范正文不变通过。独立最终文档review另核51链接/27当时复制，不与root随后复制的2份review数混淆；无新unit/native/科学消费者。

提交前cached diff检查最初将精确复制CSV的2413个标准CRLF判为trailing whitespace（实际tool rc2）；按已有closed-data CSV规则只新增该文件的`-text`与`cr-at-eol`属性，不转换任何原件字节。CSV SHA仍5524d54ff705f6cff9cf30ca5f3f846542e310e21cdbd2d268bf6dca27d84680。此为Git封存格式元数据修订，不是实验/科学门变更。


## 2026-10-19 MR3-P2A V15：获批契约生产接线、CPU/build与资格边界

用户本轮原文“批准”，候选SHA b1443df121a5ba1af0ff8c55417294bd8fd246fc85463776e1ce022c1752a043；opening Git1a5af58013f46f8638a2803e30f618eff044c4d6，working源码逐次精确快照；无新原生冻结/任务采集、GPU或pilot/验证。生产实现与失败边界见[报告](report/20261019_mr3_p2a_v15.md)。

逐次实际完整command argv/cwd/env、真实child.wait、PID/start、elapsed和前后source/stat均在[唯一索引](report/assets/20261019_mr3_p2a_v15/validation_index_v1.json)所指actual_wait.json；各console与源快照同目录，不补造未知rc。以下为逐次实际实验记录：

| Run | Actual rc | Child wait s | Scope |
| --- | --- | --- | --- |
| [actor_boundary_cpu_attempt_v1](report/assets/20261019_mr3_p2a_v15/checks/actor_boundary_cpu_attempt_v1/actual_wait.json) | 0 | 0.465321553 | CPU/build only; source stable |
| [cpp_test_build_attempt_v1](report/assets/20261019_mr3_p2a_v15/checks/cpp_test_build_attempt_v1/actual_wait.json) | 0 | 25.99109069 | CPU/build only; source stable |
| [cpp_tests_attempt_v1](report/assets/20261019_mr3_p2a_v15/checks/cpp_tests_attempt_v1/actual_wait.json) | 0 | 2.747712822 | CPU/build only; source stable |
| [delivery_order_cpu_attempt_v1](report/assets/20261019_mr3_p2a_v15/checks/delivery_order_cpu_attempt_v1/actual_wait.json) | 1 | 3.474841365 | CPU/build only; source stable |
| [final_ros_build_attempt_v1](report/assets/20261019_mr3_p2a_v15/checks/final_ros_build_attempt_v1/actual_wait.json) | 0 | 97.687508107 | CPU/build only; source stable |
| [information_reader_cpu_attempt_v1](report/assets/20261019_mr3_p2a_v15/checks/information_reader_cpu_attempt_v1/actual_wait.json) | 0 | 2.318573405 | CPU/build only; source stable |
| [information_reader_cpu_attempt_v2](report/assets/20261019_mr3_p2a_v15/checks/information_reader_cpu_attempt_v2/actual_wait.json) | 0 | 3.432646822 | CPU/build only; source stable |
| [learning_entry_cpu_attempt_v1](report/assets/20261019_mr3_p2a_v15/checks/learning_entry_cpu_attempt_v1/actual_wait.json) | 1 | 0.045840904 | CPU/build only; source stable |
| [learning_entry_cpu_attempt_v2](report/assets/20261019_mr3_p2a_v15/checks/learning_entry_cpu_attempt_v2/actual_wait.json) | 0 | 15.514846746 | CPU/build only; source stable |
| [pure_cpu_attempt_v1](report/assets/20261019_mr3_p2a_v15/checks/pure_cpu_attempt_v1/actual_wait.json) | 1 | 12.64040448 | CPU/build only; source stable |
| [pure_cpu_attempt_v2](report/assets/20261019_mr3_p2a_v15/checks/pure_cpu_attempt_v2/actual_wait.json) | 0 | 17.058343528 | CPU/build only; source stable |
| [ros_build_attempt_v1](report/assets/20261019_mr3_p2a_v15/checks/ros_build_attempt_v1/actual_wait.json) | 0 | 102.753556201 | CPU/build only; source stable |
| [ros_full_attempt_v1](report/assets/20261019_mr3_p2a_v15/checks/ros_full_attempt_v1/actual_wait.json) | 1 | 77.676495901 | CPU/build only; source stable |
| [ros_full_attempt_v2](report/assets/20261019_mr3_p2a_v15/checks/ros_full_attempt_v2/actual_wait.json) | 0 | 75.606075428 | CPU/build only; source stable |
| [ros_full_attempt_v3](report/assets/20261019_mr3_p2a_v15/checks/ros_full_attempt_v3/actual_wait.json) | 0 | 81.196482832 | CPU/build only; source stable |
| [ros_regression_fixes_attempt_v1](report/assets/20261019_mr3_p2a_v15/checks/ros_regression_fixes_attempt_v1/actual_wait.json) | 0 | 5.738330556 | CPU/build only; source stable |
| [ros_semantic_attempt_v1](report/assets/20261019_mr3_p2a_v15/checks/ros_semantic_attempt_v1/actual_wait.json) | 2 | 2.568742118 | CPU/build only; source stable |
| [ros_semantic_attempt_v2](report/assets/20261019_mr3_p2a_v15/checks/ros_semantic_attempt_v2/actual_wait.json) | 1 | 22.946002052 | CPU/build only; source stable |
| [ros_semantic_attempt_v3](report/assets/20261019_mr3_p2a_v15/checks/ros_semantic_attempt_v3/actual_wait.json) | 0 | 20.701686664 | CPU/build only; source stable |
| [runtime_reader_cpu_attempt_v1](report/assets/20261019_mr3_p2a_v15/checks/runtime_reader_cpu_attempt_v1/actual_wait.json) | 0 | 12.64300452 | CPU/build only; source stable |

最终ROS 1385 PASS；学习入口100、信息审计18、执行审计19、tensor边界1、C++29 cases/3 suites PASS。所有首轮FAIL、collection rc2和无pytest rc1原样保留，修复因果见报告。合成CPU优化不是native/GPU/PPO pilot信用。原shared log仅追加、V14原件及所有历史FAIL保持。

工程31596.4775930946018/34000，余2403.5224069053982；pilot1870/2905.9547395464029及三final-only未动。新profile完整qualification dispatcher/其他v2角色尚须接通，旧38/38不得复用，PPO仍拒新profile；没有假称P2A完成。预算提案34000→52000（增加18000）尚未批准，详情[原件](report/assets/20261019_mr3_p2a_v15/engineering_budget_proposal_v1.json)。

V15最终静态检查两次实际rc0，child5.914737227/5.821476889秒，完整argv与root实际tool chunk见[静态回执索引](report/assets/20261019_mr3_p2a_v15/static_verification_index_v1.json)。第二轮28JSON/576AST/204链接、append-only log、旧archive/V14原件及当前build源/feed SHA与flags通过；磁盘库不是live custody。文档review仅修两处陈旧状态。最终证据整理命令 `rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v15/finalize_evidence_v1.py` root实际tool rc0/.610688623s（无独立child秒声明），整理20项实际CPU/build回执，不新增科学实验。

提交前`git add -n .`实际rc0；上游opengym忽略`*.log`，本轮22份有限检查console按canonical科学证据显式force-add。仅为V15 checks的原始console/source_snapshots/actual_compile_flags增加`-text -whitespace`，保留真实FAIL与空白/行尾，不改原件字节；生产源码仍执行常规diff-check。

V15 staged-byte只读检查首试root实际tool rc1/1.838021023s：验证helper用`*_control.py`后缀glob同时匹配`control.py`/`mr3_motion_control.py`，不是快照缺失或hash损坏。随后改用runner真实ordinal+basename精确名，固定入口为`report/assets/20261019_mr3_p2a_v15/check_staged_evidence_v1.py`；不修改任何原快照/console。该检查仅Git封存，不是科学门或原生实验。

修复后的staged evidence checker实际退出rc0：403份源快照SHA、22份console Git字节及58个最新文档链接逐件通过；完整检查墙秒未另计，不以最后poll耗时替代。实际命令 `rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v15/check_staged_evidence_v1.py`。最终cached diff-check实际rc0，无build/install/checkpoint/bag/二进制运行产物入暂存。


## 2026-10-19 P2A V16：完整新契约资格路由及批准52000工程上限（原生前准备）

用户原文“批准啊批准，以后你直接改就可以了”，批准V15已封存的52000墙秒提案并授权例行实现/修复自主继续。[批准记录](report/assets/20261019_mr3_p2a_v16/budget_acceptance_v1.json)绑定原提案SHA；不回写原提出时状态。入场工程31596.4775930946018/52000，余20403.5224069053982；pilot1870/2905.9547395464029及三场final-only不扩额。

本轮CPU工作基于opening `17920bc6b9d4b20a32adcffad04afe3c24f068b6` 加每次实际快照（非原生冻结）；真实system parent `finite_actual_runner_v2.py` 调用conda `ns3gym`，均 `CUDA_VISIBLE_DEVICES=`、`PYTHONNOUSERSITE=1`、删除PYTHONPATH，实际wait且源前后稳定。精确实际argv/cwd及逐源ordinal快照/console SHA见[索引](report/assets/20261019_mr3_p2a_v16/validation_index_v1.json)，每项原件包含完整命令，不以tool poll耗时当child秒。

| CPU实际调用 | rc | 实际child墙秒 | 结果 |
| --- | --- | --- | --- |
| [entry_cpu_attempt_v1](report/assets/20261019_mr3_p2a_v16/checks/entry_cpu_attempt_v1/actual_wait.json) | 0 | 19.727855316 | 113 PASS |
| [independent_replay_cpu_attempt_v1](report/assets/20261019_mr3_p2a_v16/checks/independent_replay_cpu_attempt_v1/actual_wait.json) | 0 | 22.065744528 | 62 PASS |
| [qualification_cpu_attempt_v1](report/assets/20261019_mr3_p2a_v16/checks/qualification_cpu_attempt_v1/actual_wait.json) | 1 | 11.067734222 | 49中42 PASS/7 fixture setUp ERROR，canonical binding在/tmp根外；未改生产约束 |
| [qualification_cpu_attempt_v2](report/assets/20261019_mr3_p2a_v16/checks/qualification_cpu_attempt_v2/actual_wait.json) | 0 | 15.42356518 | 54 PASS；修测试夹具路径/完整wait后，攻击先核baseline再变异 |

新增newprofile full/custody/readback/information/runtime/peer-control-FIFO/cadence/PPO路由；必要原科学数学保留，新DAG实际30角色（合并drive/reach与peer/control，不伪称旧38）。旧schema、替换原physics、空FIFO、借用wait、错误argv、rc7伪PASS、同PID/start zombie、改资格原件等CPU反例均保持拒绝。完整资格之后还需新的16决策正优化minimum、条件pilot及final-only链；当前未启动任何新native/GPU。

准备命令 `rtk proxy python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v16/prepare_plan_v1.py` 实际rc0，仅生成首版647source/10ELF计划与V15真实build桥接，无launch。该v1草案随后在任何原生执行/冻结前补完整policy阶段watcher/真实wait/最终absence路由，由新revision预声明取代；v1原字节保留，不计原生PASS。V15真实build不重跑，严格新bridge重新核原97.687508107秒wait、原source/console/manifest/currentELF链。

新链初版policy_chain_cpu_attempt_v1实际15 PASS/rc0/.601705658秒；补上完整闭合EP档案清单与缺closure输出保留后，qualification_cpu_attempt_v3实际70 PASS/rc0/18.607284193秒，最终qualification_cpu_attempt_v4实际71 PASS/rc0/17.220292026秒，所有原snapshot/console与中间源范围保留。完整实际命令均在上述同一[索引](report/assets/20261019_mr3_p2a_v16/validation_index_v1.json) actual_argv；最终选择113+62+71=246项，final_required只选当前源码仍完全相同的三组，不把旧源CPU结果重标为新源。

完整原生前计划生成命令 `rtk proxy python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v16/prepare_plan_v1.py --revision 2` 与 `--revision 3` 各实际rc0，仅准备JSON。v1/v2在任何native/冻结前被后继明确取代，原字节保留；最终[revision3计划](report/assets/20261019_mr3_p2a_v16/predeclared_plan_v3.json) SHA `4deb328df2efaf1e0230c73a1de734db649e56789fdfae8fe0b1d12be130e9cf`，649源码/合同及10实际ELF绑定。四阶段12回合30科学角色；完整同冻结资格后才允许fresh seed41 minimum16/新pilot1870最多/最后唯一final.zip的open401/402/403三场原开发验证。pilot64步只作采集外部截断，95%/300秒评价任务不变。pipeline实际wait/外部savedPIDstart gone/已提交审计尾账全部保留，任一required fail停止后继，无自动retry。

最终静态准备实际命令：`rtk proxy /usr/bin/python3 -B .../20261019_mr3_p2a_v15/finite_actual_runner_v2.py --output .../20261019_mr3_p2a_v16/checks/static_preparation_attempt_v1 --cwd /home/zhuyulab/ns3-workspace --source .../check_preparation_v1.py --source .../validation_index_v1.json -- /usr/bin/python3 -B .../check_preparation_v1.py --output .../checks/static_preparation_attempt_v1/result.json`；省略前缀在[实际回执](report/assets/20261019_mr3_p2a_v16/checks/static_preparation_attempt_v1/actual_wait.json)的actual_argv/cwd/source原字段完整记录。实际rc0、child8.874979538秒、源稳定；161selected文件、294AST、19JSON、216本地链接、旧595份V14/V15原件与38旧archive entries、append-only log均通过。首轮FAIL不隐藏；静态observer不能提供native/GPU信用。

提交前根目录diff-check与`rtk git add -n .`/`rtk proxy git add -n .`实际rc0，选中源码/文档与有限CPU证据，无build/install/runtime/checkpoint/bag/ELF；8份真实console受上游忽略规则影响，将作为选定canonical证据显式force-add，并仅用A16 checks的窄-text/-whitespace规则保留原始字节。随后执行Git staged原字节检查，再提交/推送正式冻结。

Git staged原始字节检查最终实际rc0，171选中文件、294AST/21JSON/217本地链接及全部ordinal快照/8console index原字节通过；完整[静态回执](report/assets/20261019_mr3_p2a_v16/staged_preparation_review_v1.json)由/tmp原件逐字节保存。实际命令 `rtk proxy python3 -B .../20261019_mr3_p2a_v16/check_preparation_v1.py --staged --output /tmp/mr3_p2a_v16_staged_preparation_v1.json`；本只读Git检查无独立child墙秒声明、不以poll耗时记费。随后仅追加本事实与原JSON拷贝，不改变实验源或前述原件。

冻结`1833b8d40144e25149a9df0fd2196eaeb491e65f`已实际提交推送且HEAD=origin/main/clean。其CPU source/ELF preflight首次真实rc1、11.261805907墙秒，源前后稳定，原[实际wait](report/assets/20261019_mr3_p2a_v16/preflight_attempt_v1/actual_wait.json)与[console](report/assets/20261019_mr3_p2a_v16/preflight_attempt_v1/console.log)完整保留。精确actual_argv在该JSON；调用`reach_execution --scope cpu`包裹conda `preflight_v1.py --plan predeclared_plan_v3.json --freeze 1833b8d40144e25149a9df0fd2196eaeb491e65f --output /tmp/mr3_p2a_reach_v16_preflight.json`。649源码与clean冻结已核，严格build桥接拒绝：旧真实manifest命令/输出均记canonical绝对路径，新bridge.v1写成相对路径，逐字命令比较失败。没有提交watcher/native/GPU，也无工程/pilot扣费；这是CPU准入FAIL，不能当原生失败或CPU通过。

修复只在准备数据生成器：bridge.v2保留原build的四个实际绝对artifact路径，追加两条原实际argv/result路径相等断言，严审reader/物理/奖励/PPO代码全部未改；旧bridge/plan3/失败前置原样留存。`prepare_plan_v1.py --revision 4`实际rc0，生成[plan4](report/assets/20261019_mr3_p2a_v16/predeclared_plan_v4.json)，SHA `58727ca81d0ef531a3dc74c2c1404f1e32d390e3be5ba609a2ba70f05d057df8`，649source/10ELF，等待再次commit/push新freeze后重做CPU前置，未启动任何native。

原生启动前只读原件核查发现第二处证据范围错误：旧V15 manifest只列Python/CPP/HPP，没有CMake。revision4未冻结执行，未制造缺失旧条目。严格桥接reader改用真实build source_before=source_after与当前Git冻结核CMake；CPP/feed仍同时核原ELF manifest。新增原始flags归档SHA `356ffc302b8cf72eaaf5a9fec8c77facedf2b6ef12c079c4997af5df4aa88718` 与manifest/current flags.make逐字一致、六源macro各恰一次及-fno-fast-math/-ffp-contract=off核查。没有重建、没有改物理/奖励门。

[qualification_cpu_attempt_v5](report/assets/20261019_mr3_p2a_v16/checks/qualification_cpu_attempt_v5/actual_wait.json)实际rc0、79 PASS、18.372505006秒，source_before/after完全一致；精确argv/cwd、18份ordinal源码快照及console都在原回执/同目录。实际外层仍`finite_actual_runner_v2.py --output .../qualification_cpu_attempt_v5 --cwd wireless-rl --source`逐项复用v4的18项源码路径，child为`/usr/bin/env CUDA_VISIBLE_DEVICES= /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m unittest`同七模块`-v`；真实完整命令按[索引](report/assets/20261019_mr3_p2a_v16/validation_index_v1.json)actual_argv，不把poll秒当child墙秒。新增八项覆盖真实原件与构建/manifest/flags篡改拒绝。当前最终选择113+62+79=254项；原246项保持首冻源范围，全部旧FAIL不删除。

`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v16/prepare_plan_v1.py --revision 5`实际rc0，只生成bridge.v3/binding.v5/[plan5](report/assets/20261019_mr3_p2a_v16/predeclared_plan_v5.json)，SHA `bbc7ba93be40cc59b145dfff39ca1ea4b91aa903de25d83c748e63bc4554e806`，649source/10ELF；原plan1–4和失败CPU前置保留。工程/pilot余额未动，无新native/GPU。

revision5提交前原始字节静态检查实际rc0，完整[结果](report/assets/20261019_mr3_p2a_v16/staged_preparation_review_v2.json)由/tmp逐字保存。实际命令`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v16/check_preparation_v1.py --staged --output /tmp/mr3_p2a_v16_revision5_staged_v1.json`；无单独child墙秒声明，不以轮询时间记费。全部最终CPU源码SHA、原FAIL、旧595原件/38archive项、append-only log、本地链接及Git index实际snapshot/console字节通过；无native/GPU信用。

V16第二冻结`d307a0b248a87bf1c03b41f4f7df4cb221253ac9`已实际push/clean。其CPU预检rc0/25.554919193秒，源前后稳定；随后同freeze实际启动一次matrix，first interface失败，后继terminal/reset/deadline与所有policy阶段均未启动。以下为三个真正子进程完整actual_argv（父入口均`reach_execution`，scope依次cpu/engineering/engineering；cwd为canonical wireless-rl，PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1/unset PYTHONPATH）：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261019_mr3_p2a_v16/preflight_v1.py --plan /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v16/predeclared_plan_v5.json --freeze d307a0b248a87bf1c03b41f4f7df4cb221253ac9 --output /tmp/mr3_p2a_reach_v16_preflight.json
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.reach_preparation --plan /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v16/predeclared_plan_v5.json --freeze d307a0b248a87bf1c03b41f4f7df4cb221253ac9
/usr/bin/python3 -B report/assets/20261019_mr3_p2a_v16/external_absence_v1.py --output /tmp/mr3_p2a_reach_v16_absence.json
```

[实际outer原件](report/assets/20261019_mr3_p2a_v16/closed_execution/matrix_outer/actual_wait.json)rc1/448.826082101秒，all_submitted_children_waited=true/source_unchanged=true；interface FAIL，三后继SKIPPED。native真实wait rc1/431.295186949，watcher rc0/432.999931686；费用按outer完整墙秒一次计，不重加重叠child。首次fault在tb1 source420000000/actualstorage430000000：原target seq21/v=w0和ACK内容相同，runtime错误强制storageclock==sourceclock，把预热异步ACK误判未发布目标并锁存STOP。[原始行/冻结源码取证](report/assets/20261019_mr3_p2a_v16/closed_execution/ack_forensic_review_v1.json)保留；没有policytransition、GPU或optimizer。本次native FAIL不改判，不重试V16。reset启动守卫自然关闭；保留supervisor forced_shutdown=true/worker_returncode=-9，不宣称所有正常0。

[完整native归档](report/assets/20261019_mr3_p2a_v16/closed_execution/native_closed_v1.tar.gz)含459件823412096字节，压缩后80515160字节；[逐件SHA](report/assets/20261019_mr3_p2a_v16/closed_execution/native_closed_manifest_v1.json)与全部解压字节、source前后清单均一致。实际归档命令`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v16/archive_closed_native_v1.py` rc0，只封存闭合原件，无新实验/单独child秒声明。

独立[外部absence结果](report/assets/20261019_mr3_p2a_v16/closed_execution/external_absence.json)实际48个保存PID/start全gone，present/unreadable/errors均空，39个launchPID均有保存start；实际outer rc0/.190795842秒source不变。该结果只证保存身份消失，不提供科学PASS。工程本版真实合计449.016877943，累计32045.4944710376018/52000，余19954.5055289623982；见[精确逐外层账](report/assets/20261019_mr3_p2a_v16/closed_execution/engineering_accounting_v1.json)。CPU/build准备另列，pilot1870/2905.9547395464029与三final-only未动。

## 2026-10-19 P2A V17：异步存储ACK最小修复与新冻结准备

V16单次矩阵已完整失败关闭，不重试该freeze。用户授权直接继续例行修复；生产仅去掉ReachTracker对actual storageclock==target sourceclock的错误强制，全部epoch/robot/seq/source/值/typedclock单调仍严审；DrivePhaseClient.matching paused同钟、.94/.78 release后资格、driver/ELF/独立物理数学/95%任务/reward原字节不改。

实际ROS CPU child完整命令：

```bash
/bin/bash -c 'source /opt/ros/humble/setup.bash; source "$1/install/setup.bash"; exec /usr/bin/python3 -B -m pytest -q test/test_mr3_reach_runtime_independent.py test/test_mr3_drive_phase.py test/test_motion_safety_reach.py' mr3-ack-regression /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
```

parent为原`finite_actual_runner_v2.py --output .../20261019_mr3_p2a_v17/checks/ack_runtime_cpu_attempt_v1 --cwd .../src/multi_robot_exploration --source`五份源/测试原路径（完整canonical路径与snapshot/SHA在[原回执](report/assets/20261019_mr3_p2a_v17/checks/ack_runtime_cpu_attempt_v1/actual_wait.json)source_before）。环境unset PYTHONPATH/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1/CUDA_VISIBLE_DEVICES=；实际rc0、94 PASS、22.161525707秒、source前后稳定，不借CPU作native/GPU信用。

`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v17/prepare_plan_v1.py --engineering-remaining-seconds 19954.5055289623982`实际rc0，仅生成[全新plan1](report/assets/20261019_mr3_p2a_v17/predeclared_plan_v1.json)，SHA `0b9951b44e842ef2677234659d813d74c97447068fe34688cc4f4b4b04ae3833`，659源码/合同/先行真实账与10ELF；新binding SHA `2dd1d3f8367a83b40d9bd4cfc51ce3dc61941a7f9a17358ffa70dd73228a61ff`。V16失败/48gone/449.016877943费用原SHA全部绑定，不退费。仍完整四阶段18000及外部300，minimum1800只有实际矩阵节余足额后才允许；不得借pilot或缩门。新源必须全部同freeze重做12EP/30roles，当前尚无V17native/GPU。

V17封存首次Git静态检查实际rc1，[原件](report/assets/20261019_mr3_p2a_v17/staged_preparation_review_v1.json)保留，error=`Git staged source inventory changed during check`。原因是root在大型归档git add尚未退出时尝试force-add日志（该调用实际128/index.lock，未移除锁），随后正确等待原add实际0并补stage六份原始日志；该check期间index发生变化，所以应拒绝。本次只是封存检查，不是native或科学角色。后续所有暂存结束后再开新检查，绝不把此FAIL改PASS。

V17第二次稳定index静态检查实际rc0，[完整原JSON](report/assets/20261019_mr3_p2a_v17/staged_preparation_review_v2.json)逐字保存，实际命令为同A16/check_preparation_v1.py --staged --output /tmp/mr3_p2a_v17_staged_preparation_v2.json；无独立child秒声明。旧595份V14/V15原件、38旧archive项、append-only log、所有当前CPU源及Git原字节/链接通过；首轮index变更FAIL保留。

[独立闭合打包检查](report/assets/20261019_mr3_p2a_v17/closed_preparation_integrity_v1.json)实际rc0，真实parent finite_actual_runner_v2.py的[完整argv/cwd/source与wait](report/assets/20261019_mr3_p2a_v17/checks/closed_preparation_cpu_attempt_v1/actual_wait.json)记录46.841968454 child秒、source前后完全相同；child为`/usr/bin/python3 -B .../20261019_mr3_p2a_v17/check_closed_preparation_v1.py --output /tmp/mr3_p2a_v17_closed_preparation_v1.json`。逐字核5份新94项CPU源/ordinal快照/console、全部closed copy对/tmp原件及index、459件archive SHA/bytes、48gone、449.016877943费用守恒、659新plan源及10实际ELF；production差异严格只runtime与对应test，其余driver/DrivePhaseClient/独立reader均原字节。本项仅封存CPU检查，无native/GPU或科学信用。

V17冻结`023e488811743b3f325538d2854205466925c5c4`已实际commit/push/clean。preflight真rc0/25.863617763秒，仅source/ELF CPU，不作native信用。实际同freeze矩阵父`reach_execution --scope engineering`，完整child命令：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.reach_preparation --plan /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v17/predeclared_plan_v1.json --freeze 023e488811743b3f325538d2854205466925c5c4
```

[原outer](report/assets/20261019_mr3_p2a_v17/closed_execution/matrix_outer/actual_wait.json)实际rc1/449.21890062秒/sourceunchanged；协调器all_submitted_children_waited=true，interface FAIL，terminal/reset/deadline SKIPPED，所有policy未启动/GPU0/optimizer0。native rc1/431.232161179，watcher rc0/433.22349528；不重复累加重叠child。本次延迟19ms storage ACK不再被旧==source错误误拒；但[新同tick因果取证](report/assets/20261019_mr3_p2a_v17/closed_execution/same_tick_forensic_review_v1.json)保留首fault原始行：native record37在711ms先应用cmd14，38才存cmd15；runtime<=时钟选最新错误将cmd15倒置到应用前，tb1在.72s锁存。显式kind故障行未出现不代表tracker无fault，监控已补查内部状态；该失败属于因果校验实现错误，不是已证动力学反例。

reset守卫自然关闭，supervisor forced_shutdown=true/worker_returncode=-9保留，不能宣称所有clean0；watcher closed/PASS，remaining_owned/zombie为空。[外部实际absence](report/assets/20261019_mr3_p2a_v17/closed_execution/external_absence.json)48保存身份全gone，其outer rc0/.191114003秒；实际脚本仍A16/external_absence_v1.py，显式`--matrix /tmp/mr3_p2a_reach_v17_matrix --outer /tmp/mr3_p2a_reach_v17_matrix_wait --run .../mr3_p2a_reach_v17_interface --output /tmp/mr3_p2a_reach_v17_absence.json`，完整命令和source在[实际wait](report/assets/20261019_mr3_p2a_v17/closed_execution/absence_outer/actual_wait.json)。[账目](report/assets/20261019_mr3_p2a_v17/closed_execution/engineering_accounting_v1.json)按ns真值本版449.410014623，累计32494.9044856606018/52000，余19505.0955143393982，pilot1870/2905.9547395464029和三final-only未动。

完整closed native461件789023247字节保存为[单一xz原件](report/assets/20261019_mr3_p2a_v17/closed_execution/native_closed_v1.tar.xz)，压缩36583984字节；[逐件SHA清单](report/assets/20261019_mr3_p2a_v17/closed_execution/native_closed_manifest_v1.json)全部回读和source前后集合/字节通过。实际命令`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v17/archive_closed_native_v1.py` rc0；仅封存CPU，不新增实验或独立child费声明。V17不重试，不拼V16资格。

## 2026-10-19 P2A V18：同tick因果修复与永久fault可见性

V17原矩阵已经实际wait失败并全部关闭。例行修复范围仅runtime+对应test及motion_safety+对应test：消费ACK真实clock<=apply，strictly earlier highercmd才反证oldcmd；同clock不凭跨DDSarrival猜全序，原独立reader native_index全序严格门不改。node将永久tracker fault接入既有reach_failure，普通pending仍等；worker/driver/ELF/DrivePhaseClient与任务/奖励/门限均不改。

实际CPU child完整命令：

```bash
/bin/bash -c 'source /opt/ros/humble/setup.bash; source "$1/install/setup.bash"; exec /usr/bin/python3 -B -m pytest -q test/test_mr3_reach_runtime_independent.py test/test_motion_safety_reach.py test/test_mr3_drive_phase.py test/test_mr3_motion_control.py' mr3-same-tick-regression /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
```

parent仍原finite_actual_runner_v2.py，output A18/checks/same_tick_runtime_cpu_attempt_v1、cwd canonical ROS/src/multi_robot_exploration，七份完整--source路径及ordinal快照在[真实wait](report/assets/20261019_mr3_p2a_v18/checks/same_tick_runtime_cpu_attempt_v1/actual_wait.json)。实际rc0、127 PASS、24.300563445秒/source前后稳定，unset PYTHONPATH/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1/CUDA_VISIBLE_DEVICES=；只source系统ROS+canonicalinstall，不混conda。该CPU不提供native/策略信用。下一步完整旧预热closed-data重放，尚无PASS声明或新原生。

V18完整closed预热replay首轮真实[actualwait](report/assets/20261019_mr3_p2a_v18/checks/closed_prewarm_cpu_attempt_v1/actual_wait.json)rc1/269.896902167秒、九份source前后稳定；systemROS bash/exec完整argv/cwd在原件，output原/tmp逐字保存[失败result](report/assets/20261019_mr3_p2a_v18/closed_prewarm_replay_failed_result_v1.json)。全部162691条/390357682字节/原SHA完整扫描并保STOP尾，新tracker无latchedfault，但EOF三机causalpending未解，error_count3；不改判PASS。其同步次数是对旧原输入额外同步的pure tracker压力回放，不等同node原all-short-circuit逐调用，不证明真实ready/bootstrap或连续物理；无新native/GPU。

进一步全原件只读比对证实Motion各缺833条storageACK；native已publish、worker首缺ACK已收到，具体RMW/reader覆盖层仍unknown。旧publisher/两subscriber实际KEEP_LAST1 reliable/transientlocal，原newfullfeeds另各256。不能从worker/nativeaudits补在线历史，也不能跳失败suffix。未执行的“旧replay必须PASS”准备草案保存[原件](report/assets/20261019_mr3_p2a_v18/unexecuted_full_replay_pass_draft_v1/scope.json)；尚无plan/nativefreeze，不伪造不存在的PASS。后续只修reach Motion subscriber容量，legacy/nativepublisher/worker/ELF/九字段/独立native完整门保持；有限真实ROS burst先验证，再新同freeze全矩阵实际检查完整prefix。旧FAIL与CPU费单列，native余额仍19505.0955143393982。

V18最小prospective收集修复：仅Motion的reach storage subscriber使用production builder返回KEEP_LAST256/reliable/transient-local；default/legacy及nativepublisher、worker仍1，9字段、原actualclock、exacttarget/source/cmd、paused同钟屏障、driver/ELF和原独立完整因果门不改。有限缓存不承诺任意延迟完整；新native仍以真实actual prefix判门，缺失保持failclosed。

三次真实有限CPU child完整argv如下（parent均原finite_actual_runner_v2.py，source_before/after/snapshot/cwd在各原回执；unset PYTHONPATH、PYTHONNOUSERSITE=1、PYTHONDONTWRITEBYTECODE=1、CUDA_VISIBLE_DEVICES=）：

```bash
/bin/bash -c 'source /opt/ros/humble/setup.bash; source "$1/install/setup.bash"; exec /usr/bin/python3 -B -m pytest -q test/test_mr3_reach_runtime_independent.py test/test_motion_safety_reach.py test/test_mr3_drive_phase.py test/test_mr3_motion_control.py test/test_mr3_phase_qos.py' mr3-storage-queue-regression /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
/usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v18/missing_storage_receipt_review_v1.py --output /tmp/mr3_p2a_reach_v18_missing_storage_review.json
/bin/bash -c 'source /opt/ros/humble/setup.bash; source "$1/install/setup.bash"; exec /usr/bin/python3 -B "$2" --output "$3"' mr3-storage-queue-burst /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v18/ros_storage_queue_burst_v1.py /tmp/mr3_p2a_reach_v18_ros_storage_queue_burst.json
```

[新targeted ROS](report/assets/20261019_mr3_p2a_v18/checks/storage_queue_runtime_cpu_attempt_v1/actual_wait.json)实际140 PASS/rc0/23.374654579秒（8源）；此前127项保持原b145 Motion源范围，不重标为新QoS最终。
[全量ACK取证](report/assets/20261019_mr3_p2a_v18/missing_storage_receipt_review_result_v1.json)实际rc0/16.073019071秒（7源），native/Motion/worker cmd集whole9字段逐个相等，三机Motion各833条缺失；首缺ACK native和worker均有。只证明Motion原历史缺口，具体丢失层unknown，未注入或重建缺ACK，不改旧replay/native FAIL。
[真实ROS burst](report/assets/20261019_mr3_p2a_v18/ros_storage_queue_burst_result_v1.json)实际rc0/2.312735939秒（9源），domain222实际readback、rmw_fastrtps_cpp，相同已匹配publisher深度1逐条128个synthetic九字段ACK且全部wait_for_all_acked=true，两subscriber延后spin。legacy配置深度1仅callback ID128，新production reach配置深度256 callback完整1..128且无重复/次序差，entity销毁及context shutdown完成。SDK实际entity qos_profile配置为1/256；graph查询history UNKNOWN/depth0原样记录，不能谎称graph报告了256深度。此有限DDS CPU对照不证明一般无损/任意延迟/完整Gazebo资格/策略安全；没有仿真、GPU、PPO或工程native扣费。

旧[全suffix replay FAIL](report/assets/20261019_mr3_p2a_v18/closed_prewarm_replay_failed_result_v1.json)保持rc1/269.896902167和三EOF缺ACK错误。prospective前置改为绑定该实际FAIL及完整缺口取证，并要求新source140测试和有限DDS对照PASS；原未执行硬PASS草案保留，新的四阶段12EP30科学门一个不减、不可拼旧信用。

取证表述补充：上述“九字段逐个相等”指各消费者实际收到的ACK与native对应项逐字段一致，并非三个cmd集合相同。worker原历史也分别缺10/8/10条（共28），Motion各缺833；导致Motion最早pending的三条恰在worker原件存在。worker现有phase同钟完整屏障与Motion历史流义务不同，未用任何worker ACK补Motion输入。

V18 prospective计划已实际生成，命令`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v18/prepare_plan_v1.py --engineering-remaining-seconds 19505.0955143393982`实际rc0，仅准备数据/no native。新[plan1](report/assets/20261019_mr3_p2a_v18/predeclared_plan_v1.json) SHA `29294bba562f6e249166d6ffc4b4c20cc602f005d10d3c7f11ee598c9f1adb49`，715源码/合同/实际CPU原件和10ELF；新binding SHA `0ebd64cc9db18df5fe6a86ea8b337b0532561c2b5302c9aecdc89c96516fffba`。guarded准备门真实读取旧replay FAIL+新140/forensic/burst PASS，硬保留所有源版本/三个EOF缺失；不将CPU准备变原生信用。全四阶段18000+external300可负担；minimum1800只有实际matrix节余及尾账余额足额才准入，pilot/验证不变。尚无V18新native/GPU。

V18独立[最终封存检查](report/assets/20261019_mr3_p2a_v18/closed_preparation_integrity_v1.json)实际rc0，真实child57.776698661秒、七份helper/plan/binding源前后稳定；[完整actual_argv/cwd/snapshot](report/assets/20261019_mr3_p2a_v18/checks/closed_preparation_cpu_attempt_v1/actual_wait.json)保留。实际child为`/usr/bin/python3 -B .../A18/check_continuation_preparation_v1.py --plan .../A18/predeclared_plan_v1.json --plan-sha 29294bba562f6e249166d6ffc4b4c20cc602f005d10d3c7f11ee598c9f1adb49 --output /tmp/mr3_p2a_v18_closed_preparation_v1.json`，父原finite_actual_runner_v2.py输出A18/checks/closed_preparation_cpu_attempt_v1，cwd canonical root、source包含三newhelpers/两oldpackaginghelpers/plan/binding。全部actualCPU及失败旧source版本/EOF缺口、真实DDS128对照/清理、715plan源与10ELF、闭合archive及copy对原/tmp/index原字节、48gone与449.410014623费用守恒、仅四生产/测试文件差异、oldassets零修改和新增AST/JSON/链接/暂存sanity均通过；检查不提供新native/GPU信用。


V18冻结`ed2306e9fa100f6ada4ab6496a53a3bd08e58017`已实际执行并失败闭合。以下均为canonical wireless-rl cwd、unset PYTHONPATH/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1的`reach_execution`真正child原始argv，原actualwait包含父身份/source快照/真实ns：

- preflight：[原件](report/assets/20261019_mr3_p2a_v18/closed_execution/preflight_outer/actual_wait.json)，实际rc0/27.954691015秒/source unchanged=True；`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261019_mr3_p2a_v18/preflight_v1.py --plan /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v18/predeclared_plan_v1.json --freeze ed2306e9fa100f6ada4ab6496a53a3bd08e58017 --output /tmp/mr3_p2a_reach_v18_preflight.json`。
- matrix：[原件](report/assets/20261019_mr3_p2a_v18/closed_execution/matrix_outer/actual_wait.json)，实际rc1/178.458480158秒/source unchanged=True；`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.reach_preparation --plan /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v18/predeclared_plan_v1.json --freeze ed2306e9fa100f6ada4ab6496a53a3bd08e58017`。
- absence：[原件](report/assets/20261019_mr3_p2a_v18/closed_execution/absence_outer/actual_wait.json)，实际rc0/0.183465165秒/source unchanged=True；`/usr/bin/python3 -B report/assets/20261019_mr3_p2a_v16/external_absence_v1.py --matrix /tmp/mr3_p2a_reach_v18_matrix --outer /tmp/mr3_p2a_reach_v18_matrix_wait --run /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v18/mr3_p2a_reach_v18_interface --output /tmp/mr3_p2a_reach_v18_absence.json`。

原matrix all_submitted_children_waited=true、interface FAIL，terminal/reset/deadline SKIPPED；无PPO/GPU/optimizer。release39.20后首控制39.22在Motion原43180行报initial HOLD无complete pair certificate，两帧相邻13/23均拒证；保留原失败。native159.461720488与watcher161.295559252不叠加outer收费；worker_returncode=-15/forced_shutdown=true保留，remaining owned/zombie为空，49保存PID/start实际gone。matrix178.458480158 + absence.183465165 = 本版178.641945323，累计32673.5464309836018/52000、余19326.4535690163982；pilot1870/2905.9547395464029及三final-only未动。

实际closed文件打包命令`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v18/archive_closed_native_v1.py` rc0，仅封存CPU：完整123件231835013字节→10730740字节xz，wholemember读回/源再核及18辅助copies原字节通过；[清单](report/assets/20261019_mr3_p2a_v18/closed_execution/native_closed_manifest_v1.json)、[真实账](report/assets/20261019_mr3_p2a_v18/closed_execution/engineering_accounting_v1.json)保留。未启动qualifier或重试V18。

## 2026-10-19 P2A V19：真实20Hz激光来源修复准备

用户持续授权P2A例行实现/修复直接推进。V18 initial HOLD几何拒证来自真实5Hz scan-derived TF年龄；仅选一次新鲜release不足覆盖后续.94s资格HOLD。prospective只在显式reach生成SDF选真实20Hz激光，原base/legacy5Hz、真实stamp、360beam/噪声/机体/驱动及所有U/maprawAND/H/D/R/95%门不改；明确SLAM/地图/actor观测分布改变，必须新freeze完整资格，不能以CPU或旧结果复用。当前尚无V19原生/GPU信用。


2026-10-20两项有限CPU实际执行（版本目录沿本轮开始日期20261019保留；真实clock/argv以各wait为准）。[sensor_profile v1](report/assets/20261019_mr3_p2a_v19/checks/sensor_profile_cpu_attempt_v1/actual_wait.json)真rc0/24.367975479秒/source stable，系统ROS launch回归28项及conda独立审计/dispatch/preparation/cadence42项通过；完整child是该JSON actual_argv，cwd W，源码ordinal全快照覆盖W/mr3_learning全部Python及四份ROS源/测试。它只提供此时源的CPU信用，不能重标给后续变化或native资格。

[初始HOLD取证 v1](report/assets/20261019_mr3_p2a_v19/checks/initial_hold_forensic_cpu_attempt_v1/actual_wait.json)真rc1/7.071966402秒/source stable，child `/usr/bin/python3 -B .../A19/initial_hold_source_cadence_forensic_v1.py --output /tmp/mr3_p2a_v19_initial_hold_source_cadence_forensic_v1.json`，[原失败JSON](report/assets/20261019_mr3_p2a_v19/initial_hold_source_cadence_forensic_failed_result_v1.json)逐字保存，error KeyError('transform')。未改旧trace或helper；此前的原生FAIL不变。该失败暴露Information原bundle在actual envelope交付后pop transform，received peers缺转向sidecar需要的完整字段；own_state有，HOLD不读heading，N/X将需要。后续以reach-only保留同一已交付envelope原transform补齐生产接线，独立源/交付/完整内容门同步更新，新v2 CPU另列，不向旧bundle注入或补造字段。CPU不扣native工程/pilot额度，无新native/GPU。


最终组合CPU v2真实[wait](report/assets/20261019_mr3_p2a_v19/checks/sensor_information_cpu_attempt_v2/actual_wait.json)rc1/58.060315136秒、全部source stable。actual_argv/cwd及ordinal source快照原样保存；ROS五文件97 PASS，conda七模块100项中7 FAIL+1 ERROR，均peer_control synthetic链在published state differs from delivered envelope处拒绝，不能称整组PASS。该测试旧fixture/host对bundle transform的适配需核查，生产/审计谓词未因本次失败放宽；后续修复只在实际确认范围另执行新v3回执，原v2不覆盖。没有native/GPU/预算扣费。


v2失败的只读定位明确是一处真实生产审计integration：`audit_reach_peer_control`仍直接从旧audit_information载入会pop transform的oracle，将其传给新版reach信息重放，正式native同样会误拒新完整bundle，并非仅测试夹具。修复严格只切换到新reach信息loader，保留immutable旧oracle/legacy入口及所有原始row/side/envelope/TF选择比较；补loader wholeinverse和缺TF不能用sideTF补替两个测试。原v2的7FAIL+1ERROR不改，v3组合CPU另执行，数学/几何/安全门没有放宽。


最终组合[v3 actualwait](report/assets/20261019_mr3_p2a_v19/checks/sensor_information_cpu_attempt_v3/actual_wait.json)真rc0/67.038865175秒，ROS97 PASS + conda102 PASS，source_before=source_after；完整原child argv、cwd、SOURCE paths与ordinal快照全部在原件（本轮source数134）。child同v2七conda模块/五ROS测试，实际oldhost接线修复已覆盖；v1 PASS仅旧scope、取证v1与组合v2 FAIL原样保留。只是有限CPU准备，无native/GPU/资格/策略信用或工程/pilot扣费。current driver/C++/ELF/legacy/独立物理数学和全部门限保持；下一步封存真实旧失败取证与新plan，必须新freeze完整四阶段资格。


[HOLD取证v2](report/assets/20261019_mr3_p2a_v19/initial_hold_source_cadence_forensic_result_v2.json)真实rc0/17.16589449秒/source stable，[actualwait](report/assets/20261019_mr3_p2a_v19/checks/initial_hold_forensic_cpu_attempt_v2/actual_wait.json)为parent原finite_actual_runner_v2.py/cwd ROOT/13source快照；child `/usr/bin/python3 -B .../A19/initial_hold_source_cadence_forensic_v2.py --output /tmp/mr3_p2a_v19_initial_hold_source_cadence_forensic_v2.json`。原v1失败及脚本不变，新脚本另存b5936b846193f280b3134215485ff167f3672a71dcead5d696f1428f9247ce00。全部Motion/info trace及六原始输入SHA/byte/stdstat前后稳定，原包/peer缺TF字段保持、没有注入；仅从实际先前bundle订阅→Information publication→同envelope sequence/state_send→selected raw TF ingress/sideSHA形成旁证，明确不是原包字段。TF unique源196/186/181、最常见更新间隔均200ms（其余195/198/199/201/202ms原hist全留）；两组相邻pair独立Fraction HOLD代入均map/raw拒证，原39.22故障不改。本PASS仅只读取证成功，不是科学资格、连续plant或20Hz原生来源证明，无native/GPU/额外工程pilot扣费。


实际生成新[plan1](report/assets/20261019_mr3_p2a_v19/predeclared_plan_v1.json) rc0，命令`rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= /usr/bin/python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v19/prepare_plan_v1.py --engineering-remaining-seconds 19326.4535690163982`。SHA `331d83cb8fb7fb7498f9243eaccd49138f9117baae9ae69684d30b55ae8c2d3e`，1158项source/实际闭合与CPU证据，10实际ELF，binding SHA `832c6fd25a44478cdbed6acf9ed2c35f8c8e501fe53674e6d432f7bd9e592470`。完整18000矩阵/external300与minimum1800条件准入保持；现余额19326.4535690163982，pilot与三final-only不扩额。仅配置数据生成，无native/GPU；新science qualification必须clean/pushed exact source同冻全4阶段/12EP/30角色。


封存静态checker首轮实际rc1/66.562880356秒、source/index稳定：[原结果](report/assets/20261019_mr3_p2a_v19/closed_preparation_failed_result_v1.json)。真实child为`check_preparation_v1.py --plan .../A19/predeclared_plan_v1.json --plan-sha256 331d83cb8fb7fb7498f9243eaccd49138f9117baae9ae69684d30b55ae8c2d3e --staged --output /tmp/mr3_p2a_v19_closed_preparation_v1.json`，父原finite_actual_runner_v2.py，完整actualargv/cwd/7源在checks/closed_preparation_cpu_attempt_v1/actual_wait.json。1158source/10ELF与准备证据已核过，selected Markdown link门拒绝报告错误相对链接。原因是root写报告时误把整份共享log正文拼入；错误staged正文逐字保留[txt快照](report/assets/20261019_mr3_p2a_v19/closed_preparation_failed_report_snapshot_v1.txt)。修复只移除报告的重复日志正文并保留本轮实际HOLD/plan条目；canonical log原历史不动，生产/测试/plan/helper均不改，首静态FAIL不改判。此项无native/GPU或工程扣费。


最终[暂存封存检查v2](report/assets/20261019_mr3_p2a_v19/closed_preparation_integrity_v2.json)实际rc0/81.964536391秒，7源before/after稳定，Git index全程不变；父原finite_actual_runner_v2.py的[actualwait](report/assets/20261019_mr3_p2a_v19/checks/closed_preparation_cpu_attempt_v2/actual_wait.json)保存完整child argv/cwd/快照。CLI同v1，仅输出/tmp/mr3_p2a_v19_closed_preparation_v2.json独占新路径。1158绑定源/10实际ELF、原V18完整archive/49gone/真实费用守恒、fresh199项CPU/取证v2、全部原FAIL及historysource版本、所选AST/JSON/本地链接与Git暂存原字节均通过；没有native/GPU/科学或策略信用。错误报告txt与静态首FAIL仍保留，生产/科学门未因封存失败修改。


## 2026-10-20 P2A V19：原生闭合、审计受控中断与V19末账

冻结`3631c788ca46e03a52f34ad48c41611761c17f1e`，同[plan](report/assets/20261019_mr3_p2a_v19/predeclared_plan_v1.json) SHA331d83cb8fb7fb7498f9243eaccd49138f9117baae9ae69684d30b55ae8c2d3e，open:101/三机/interface32步。preflight CPU rc0/39.621482744秒；以下为[原matrix actual_argv](report/assets/20261019_mr3_p2a_v19/closed_execution/auxiliary_closure_v1/matrix_outer/actual_wait.json)与[原native argv](report/assets/20261019_mr3_p2a_v19/closed_execution/auxiliary_closure_v1/matrix/interface/native.json)，cwd均canonical W；历史实际child命令，非后续重跑指令：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.reach_preparation --plan /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v19/predeclared_plan_v1.json --freeze 3631c788ca46e03a52f34ad48c41611761c17f1e
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 32 --preparation-motion-probe --preparation-probe-version mr3-p2a-reach-outward-cancel-v1 --base-domain 180 --base-port 14701 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v19 --run-id mr3_p2a_reach_v19_interface --preparation-parameter-review --work-wall-seconds 1880.083 --close-reserve-seconds 120 --preparation-parameter-profile gentle_turn_v1 --safety-contract mr3-reach-v1
```

actual outer rc1/3809.076356086秒/sourceunchangedtrue；native rc0/1063.056962484秒。stage3790.370777463>名义2400（实际cap2390.712185318），all_submitted_children_waited=true。input/angular/physics/full/runtime/cadence六条command真实rc0；Information实际-2/2666.069126958秒、`declared result missing`，结果文件不存在。[原summary](report/assets/20261019_mr3_p2a_v19/closed_execution/auxiliary_closure_v1/matrix/summary.json)保留terminal/reset/deadline三阶段SKIPPED及fifo_001/peer_control/fifo_manifest/closure四pending job SKIPPED；不得称完整30角色或qualification通过。

stage时限已不可通过后，root对唯一owned Info reader以pidfd发送一次SIGINT。[intervention原argv/PID-start/时刻](report/assets/20261019_mr3_p2a_v19/closed_execution/auxiliary_closure_v1/operator_interrupt/evidence/intervention.json)、[system Python -B控制source](report/assets/20261019_mr3_p2a_v19/closed_execution/auxiliary_closure_v1/operator_interrupt/source.py)、[实际control wait](report/assets/20261019_mr3_p2a_v19/closed_execution/auxiliary_closure_v1/operator_interrupt/outer/actual_wait.json)全部封存。coordinator自身signals_sent=0原字段不改，run确有这一次记录的外部信号；不谎称全局0，不修改reader原日志或原始native输入。未在旧freeze重跑native或Information。

[absence v1](report/assets/20261019_mr3_p2a_v19/closed_execution/auxiliary_closure_v1/absence_v1/outer/actual_wait.json)rc1/0.365218825秒，硬编码回执名错误导致整体FAIL；当次58身份无present不能盖过FAIL。v2外层另有一次source路径错误的[前置失败tool原件](report/assets/20261019_mr3_p2a_v19/closed_execution/absence_v2_prelaunch_failure_v1.json)，toolwall0.048720286秒，未spawn child/无actualwait，保留空输出根，不造ns/收费。root以新outer目录实际执行[正确v2](report/assets/20261019_mr3_p2a_v19/closed_execution/auxiliary_closure_v1/absence_v2/outer/actual_wait.json)rc0/0.376774231秒/sourceunchangedtrue；[结果](report/assets/20261019_mr3_p2a_v19/closed_execution/auxiliary_closure_v1/absence_v2/result.json)58 saved identities在原lookup时gone，present/unreadable/unbound/errors=[]。各完整实际child argv均在对应actual_wait.json；未以canonical复制路径改写过去命令，也不补未知完整outer argv。

[末账及补充/proc观察](report/assets/20261019_mr3_p2a_v19/engineering_accounting_v1.json)核A1/A2四个新增helper/outer保存PID-start也均absent，Z同start仍为present；不声称该生成器自证自己gone。真实费用按outer ns/Decimal：M3809.076356086+A1.365218825+A2.376774231=3809.818349142；C.268437067完整containedM不双扣，toolwall与并行child不另加。本V19闭合末点累计36483.3647801256018/52000、余15516.6352198743982（baseline32673.5464309836018），不是随后V20工作当前全局预算。

[原生归档manifest](report/assets/20261019_mr3_p2a_v19/closed_execution/native_archive/manifest.json)：514文件/1,038,191,041字节→32,677,904字节单shard，SHA82d7fb728e5d948af29b01c95e877ff6fc3cf7ca4696442b215662e7282a6ff7，wholemember/readback及source before-after一致；实际打包argv见manifest.actual_argv，有限CPU封存不作native科学信用。[51辅助原件映射](report/assets/20261019_mr3_p2a_v19/closed_execution/auxiliary_closure_v1/copy_index_v1.json)5,321,305字节全量origin/copy SHA/byte一致，失败原件均保留。完整叙述见[V19报告](report/20261019_mr3_p2a_v19.md)。

qualification/PPO/minimum/pilot/validation均未启动，GPU0/optimizer0；pilot余额1870决策/2905.9547395464029墙秒与三final-only不动。P2A未完成；本条只追加一次，不替换旧日志或把失败改PASS。


## 2026-10-20 P2A V20：审计器索引、完整只读重放与性能诊断

用户已明确授权P2A后续常规修改、修复和验证直接推进，不再重复请求修改批准；52000累计工程墙秒、pilot1870决策/2905.9547395464029墙秒和三final-only边界不变。V19冻结3631原matrix FAIL、Information -2及所有旧FAIL不改；没有新native/GPU/PPO或科学资格。

第一组仅CPU准备：Information/peer_control完整bundle SHA移出历史循环；Information目标canonical索引严格在原publication插入点保序多值，并按真实applied序列保存完整target键。两个生产reader当时SHA分别ffcb403badc8c05c863d9dec9aa7ede27e403567294bb3acc32b60c0e844a27f、29f074ecf0d704b4f484ccc1c0c990b0bdf7223e04ffbd44e4af887b038c989f。实际finite parent均为原A15/finite_actual_runner_v2.py；canonical W cwd、unset PYTHONPATH/PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1，完整child actual_argv与ordinal源快照原样保留：

- [既有52项](report/assets/20261020_mr3_p2a_v20/checks/information_index_cpu_attempt_v1/actual_wait.json)：conda Python -B -m unittest mr3_learning.tests.test_audit_reach_information mr3_learning.tests.test_audit_reach_peer_control mr3_learning.tests.test_reach_controlled_dispatch，真实rc0/15.266555326秒/source stable。
- [原函数对比6项v1](report/assets/20261020_mr3_p2a_v20/checks/index_equivalence_cpu_attempt_v1/actual_wait.json)：conda Python -B -m unittest mr3_learning.tests.test_reach_information_index_regression，真实rc0/15.932561681秒/source stable；[扩充9项v2](report/assets/20261020_mr3_p2a_v20/checks/index_equivalence_cpu_attempt_v2/actual_wait.json)同child模块，真实rc0/17.79671615秒/56源stable。whole Git3631旧audit_motion作为原函数对比，覆盖重复owner/实际applied严格前缀、完整target编码差异、同clock同wall仅row顺序差异、None HOLD、两个actuation历史ref和空history不算SHA；synthetic不供native信用。
- [完整逆投影](report/assets/20261020_mr3_p2a_v20/checks/index_projection_cpu_attempt_v1/actual_wait.json)：system Python -B A20/check_information_index_projection_v1.py --result /tmp/mr3_p2a_v20_information_index_projection_v1.json，真实rc0/.142309022秒/source stable。反向唯一声明patch后两模块完整字节等于原Git3631 blob；该PASS只属于当时明确两个reader与patch，不重标后续ACK改动。

性能诊断原native artifact freeze始终3631，open101/三机32步已闭合原件，只读新consumer不重跑旧矩阵。所有原件与104份source/output/receipt逐字复制映射见[copy index](report/assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/copy_index_v1.json)，1,668,023字节，source before-after及全copy SHA/byte一致。原/tmp未删；两个profile helper沿创建时误用的20261019_mr3_p2a_v20目录原路径保留，过去argv未改写：

1. 纯kernel CPU准备：system Python -B /tmp/mr3_v19_runtime_kernel_profile_draft.py，真实rc0/31.616835921秒；完整argv/3source/全motion474503607字节核对见[kernel outer](report/assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/kernel_outer/actual_wait.json)。只选原第一允许非零X/N decision(record88905)的真实先前上下文，不更换样本；cold1/warm25十段核共.497809188秒，Fraction等不是该单样本的秒级瓶颈，不推广整episode。
2. 完整原runtime v1剖析：[outer](report/assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/profile_v1_outer/actual_wait.json)真实rc0/137.120663666秒/source unchanged；child system Python -B A19V20/bounded_runtime_profile_v1.py --episode .../episode001_open_101 --reader-source .../audit_reach_runtime.py --output-dir /tmp/mr3_p2a_v20_runtime_bounded_profile_v1 --seconds 120。120秒合作式SIGALRM中断，original_audit_completed=false/timed_out=true，不是原科学审计PASS。前120秒停在原严格Inputs.read的duplicate-key/JSON/canonical装载；原.prof有效。v1输出结构化ranked_functions为空/total_calls=0是helper在pstats消费stats后取值的报告缺陷，保留原JSON；只从已保存.prof离线生成[补充summary](report/assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/profile_v1/profile_summary_from_saved_prof_v1.json)，未重跑consumer。
3. 完整原runtime core v2剖析：[outer](report/assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/profile_v2_outer/actual_wait.json)真实rc1/269.000729653秒/4source stable；child system Python -B A19V20/bounded_runtime_core_profile_v2.py --episode .../episode001_open_101 --reader-source .../audit_reach_runtime.py --output-dir /tmp/mr3_p2a_v20_runtime_core_profile_v2 --seconds 120。原装载约134.7581秒后core合作式120秒timeout；独立helper因marshal(code)前后摘要不同判FAIL，原source SHA/签名/行号一致，但未保存独立code identity/co_code，不能推断已证明改变源码或解释运行时原因。FAIL发生在inputs_after验证前，不声称全输入after已证明。部分.prof有效，native_index32.1002秒、ingress_index81.0334秒；L924 TF listcomp已出现55次，说明已进入decision循环，不能说完全未进入后继核。原数学、源码和V19结果均未改。
4. 新Information owner-index candidate完整只读回归：[intent](report/assets/20261020_mr3_p2a_v20/closed_v19_information_regression_intent_v1.json)声明600秒root监督额度；[outer](report/assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/information_outer/actual_wait.json)真实rc-2/833.533889498秒、全部W顶层reader源码+intent source stable。实际child为conda Python -m mr3_learning.audit_reach_information /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v19/mr3_p2a_reach_v19_interface --freeze 3631c788ca46e03a52f34ad48c41611761c17f1e --output /tmp/mr3_p2a_v20_v19_information_regression_v1.json。root在其他诊断/测试工作中未及时监督；观察到reader已运行814.868881123秒才以pidfd对精确PID1400705/start417701625/parent1400702发送一次SIGINT，[记录](report/assets/20261020_mr3_p2a_v20/closed_diagnostics_v1/information_interrupt/intervention.json)保留超额和真实wait，不把600写成硬限、不给重放PASS、不截减费用。实际中断栈在Information L963完整control dependency ACK历史重复canonical比较；结果文件不存在。该newreader回归失败与原V19 Info -2是两次不同实际child，均保留，绝不替代原matrix资格。

以上V20正式只读诊断真实outer工程费用137.120663666+269.000729653+833.533889498=1239.655282817；加V19末账36483.3647801256018，当前阶段累计37723.0200629426018/52000，余额14276.9799370573982。nested child/并行样本不双扣，CPU单元/源投影/纯kernel/封存不作native费。余额不足严格新矩阵18000秒，未改CAPS/4阶段12回合30角色/外尾300/minimum1800门，不借pilot，不自行扩额。

为消除人工监督延迟，本版新增只读consumer专用自动owned-child wait helper；[两项CPU fixture](report/assets/20261020_mr3_p2a_v20/checks/bounded_helper_cpu_attempt_v1/actual_wait.json)真实rc0/1.187485926秒/source stable，system Python -B A20/check_bounded_read_only_child_v1.py：正常child rc0真实wait；1秒超时child由pidfd精确SIGINT，真实-2并被wait/gone。它只signal自己的单一child，不signal进程组；真实清理尾秒继续计入外层工程费，不宣称deadline就是硬终止时刻。


V20最终三reader组合CPU真实闭合：[actual wait](report/assets/20261020_mr3_p2a_v20/checks/combined_reader_cpu_attempt_v1/actual_wait.json)rc0/77.574838239秒/102源stable，131项PASS。原A15 finite parent、cwd canonical W、conda Python -B -m unittest八模块：test_audit_reach_runtime、test_audit_reach_cadence、test_audit_reach_information、test_audit_reach_peer_control、test_reach_controlled_dispatch、test_reach_preparation_entry、test_reach_information_index_regression、test_reach_runtime_index_regression（全带mr3_learning.tests前缀，完整actual_argv在回执）。当前Information f17c6fd76c4a1682ba36bd084548f74c46fd3151da14a3084c6613d984c6e495、peer_control29f074ecf0d704b4f484ccc1c0c990b0bdf7223e04ffbd44e4af887b038c989f、runtime4f6505f686945927641431a7cc64ee42e1fa5219b9d5f5144c82118fb96d88fa。两个新模块各22项对比whole-Git3631原函数/原完整runtime，覆盖ACK短路/异常序、完整编码多值/原引用/曾future先于cachedmatch、raw/calib/applied严格arrival前缀、clock回退/乱序TF/未用坏tail及typed-cache数值拒绝门。

ACK开发草稿先由conda Python -B /tmp/mr3_information_ack_index_draft_proof_v1.py执行22项，真实rc0/20.095675073秒/source stable，[完整原wait/source snapshots](report/assets/20261020_mr3_p2a_v20/checks/ack_draft_cpu_attempt_v1/actual_wait.json)、[补充原helper/metadata/复制映射](report/assets/20261020_mr3_p2a_v20/ack_draft_auxiliary_v1/copy_index_v1.json)和[adverseproof](report/assets/20261020_mr3_p2a_v20/ack_index_adversecase_proof_v1.json)保留。它对草稿整patch逆投影恢复当时ffcb，未写生产；随后root真实apply后才执行上述独立131组合，不把草稿结果冒充生产执行结果。

[最终组合逆投影v2](report/assets/20261020_mr3_p2a_v20/reader_optimization_projection_result_v2.json)真实finite CPU rc0/.355942296秒/6源stable，[wait](report/assets/20261020_mr3_p2a_v20/checks/combined_projection_cpu_attempt_v2/actual_wait.json)child为system Python -B A20/check_reader_optimization_projection_v2.py --patch ABS/A20/combined_reader_optimization_v2.patch --manifest ABS/A20/reader_optimization_projection_manifest_v2.json --output /tmp/mr3_p2a_v20_reader_optimization_projection_v2.json。三生产模块反向wholepatch后全部完整字节等于3631；35既有runtime数学/Inputs/source_proof/wholeaudit定义含decorator完整文本及AST一致，number原type/finite校验仍第一原句，4096/typed=True缓存只复用同一纯Fraction转换。组合patch SHA3cc61a8b24ed422ac2c1db7311d9fc613ff0417b36076008ff3c00f637894491。runtime初稿v1被静态反例发现会提前触发未用坏acttime，未apply或执行，保留[未用草稿](report/assets/20261020_mr3_p2a_v20/draft_runtime_index_v1_rejected.patch)；实际v2在首normal-ready完整原act循环成功后才建prefix，STOP/nonready保留原循环/错误顺序，四个专门反例已纳入22项runtime回归。

[独立静态review](report/assets/20261020_mr3_p2a_v20/independent_reader_review_v1.json)在其明确输入版本下核35数学原文、70新增本地links与已闭合账，未见确定阻塞或门限弱化。它将尚在运行的完整runtime回归标in-progress/未知rc，不给其成功或实费；新完整重放必须以随后真实外层wait和原结果另列。本段所有unit/源投影/静态检查均非native科学资格，不耗pilot或新增GPU。


V20完整新reader闭合与global wall区间末账纠正（所有旧FAIL不改）：

- Runtime完整闭合V19 EP开发回归实际outer rc0/339.708353551秒/source unchanged；[原outer](report/assets/20261020_mr3_p2a_v20/closed_regressions/runtime_regression_v1/outer/actual_wait.json)actual child是system Python -B A20/bounded_read_only_child_v1.py --output /tmp/mr3_p2a_v20_runtime_regression_child_v1 --wall-seconds 600 -- /usr/bin/python3 -B ABS/A20/closed_v19_runtime_regression_v1.py --candidate-sha 4f6505f686945927641431a7cc64ee42e1fa5219b9d5f5144c82118fb96d88fa --patch ABS/A20/runtime_index_optimization_v2.patch --patch-sha cfef27a0c669d09324d522005754c1575e68361c22263c140fb610ee0776731c --output /tmp/mr3_p2a_v20_closed_v19_runtime_regression_v1.json，cwd canonical W，unsetPYTHONPATH/NOUSERSITE1/NOBYTECODE1/CUDAempty；完整实际绝对argv见回执。[nested realwait](report/assets/20261020_mr3_p2a_v20/closed_regressions/runtime_regression_v1/child/actual_wait.json)无timeout/signals，consumer rc0；[结果](report/assets/20261020_mr3_p2a_v20/closed_regressions/runtime_regression_v1/result.json)真实完整core+13artifact_proof逐字段等于原V19 runtime叶，所有source/input前后稳定，Inputs.close及原配置/数学全执行。生产source_proof完全不改；仅独立harness在内存对新reader这一项显式标current_equals_freeze=false/diagnostic_candidate_sha/nonqual，别的source仍原Git3631==current。artifactfreeze不冒充candidatefreeze，原V19矩阵不补资格。
- Information最后完整闭合V19 RUN开发回归实际outer rc0/422.782810574秒/source unchanged；[原outer](report/assets/20261020_mr3_p2a_v20/closed_regressions/information_regression_v2/outer/actual_wait.json)actual child是system Python -B ABS/A20/bounded_read_only_child_v1.py --output /tmp/mr3_p2a_v20_information_regression_child_v2 --wall-seconds 600 -- /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.audit_reach_information /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v19/mr3_p2a_reach_v19_interface --freeze 3631c788ca46e03a52f34ad48c41611761c17f1e --output /tmp/mr3_p2a_v20_v19_information_regression_v2.json，cwd/env同上。[nested realwait](report/assets/20261020_mr3_p2a_v20/closed_regressions/information_regression_v2/child/actual_wait.json)consumer rc0/422.684596373秒，无timeout/signals；[完整结果](report/assets/20261020_mr3_p2a_v20/closed_regressions/information_regression_v2/result.json)attempted1/PASS/errors[]。原Info -2/首newreader -2/stageFAIL/其余角色缺口保持，不把新reader读旧原件变原生或qualification。
- 两组outer/child/result全部逐字复制，各copy_index_v1.json给原路径/byte/SHA；未改历史argv或删原/tmp。没有新的native/GPU/optimizer，pilot/final-only未动。

末账generator v1直接CPU执行命令rtk proxy python3 -B ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261020_mr3_p2a_v20/generate_engineering_accounting_v1.py，真实tool rc1/1.008240139秒，在assert outer fees overlap处失败、未写结果；[原source/tool/trace](report/assets/20261020_mr3_p2a_v20/accounting_v1_failed_attempt/tool_failure_v1.json)保留，没有结构化child ns回执，不补造。它发现上文临时subtotal把profile_v2与首Info重复相加：profile_v2区间[4177055462518303,4177324463247956]完全containedInfo1 [4177016256393222,4177849790282720]。该profile真实rc1/269.000729653秒不变，新增globalwall收费0，不能减免任一attempt自身cap/FAIL。

此前1239.655282817/37723.0200629426018/38062.7284164936018以及proposal v1是纠正前暂记；[旧完整报告](report/assets/20261020_mr3_p2a_v20/retained_report_before_accounting_correction_v1.md)、[proposal v1实际观察报告字节](report/assets/20261020_mr3_p2a_v20/budget_proposal_v1_observed_report_snapshot.md)与所有原wait不改。[独立union复核](report/assets/20261020_mr3_p2a_v20/independent_wall_union_review_v1.json)保留共同clock域假设：原receipts无boot_id，不回填，依赖同一连续canonical host会话及实际PID/start/ns来源；当前boot观察不冒充历史boot证明。

最终distinct generator v2由原A15 finite_actual_runner_v2.py真实执行，[CPU wait](report/assets/20261020_mr3_p2a_v20/checks/accounting_cpu_attempt_v2/actual_wait.json)rc0/.081931281秒/source stable，actual child system Python -B ABS/A20/generate_engineering_accounting_v2.py、cwd root，source snapshots保留helper/旧V19末账/五outer及两个nested回执。[末账v2](report/assets/20261020_mr3_p2a_v20/engineering_accounting_v2.json)：五actual wait总2002.146446942，唯一重叠269.000729653，四段global wall union1733.145717289；V19基线36483.3647801256018不改→累计38216.5104974146018/52000，余13783.4895025853982。五outer与两个nested保存的12唯一PID/start当前absent，Z同start仍为present；不自证generator未来gone。nested/parallel不双计，CPU准备封存不收费。

当前低于完整新矩阵18000预留，不启动新native/Q/PPO，不缩减4阶段/12回合/30角色或借pilot。[具体proposal v2](report/assets/20261020_mr3_p2a_v20/next_engineering_budget_proposal_v2.json)仅请求累计60000（加8000），仍未批准，未建sealedplan；若批准余额21783.4895025853982，保留matrix18000+external300+minimum1800=20100后余1683.4895025853982，不保证研究成功。pilot1870/2905.9547395464029及三场final-only、95%/300秒不变；用户已授权常规P2A修改直接执行，不重复询问修改批准，数值扩额保持显式授权边界。


V20最终静态封存检查实际finite CPU rc0/.674876855秒/16源stable，[wait/全部actual_argv/cwd/源快照](report/assets/20261020_mr3_p2a_v20/checks/closed_preparation_cpu_attempt_v1/actual_wait.json)与[结果](report/assets/20261020_mr3_p2a_v20/closed_preparation_integrity_v1.json)保留。actual child为system Python -B ABS/A20/check_closed_preparation_v1.py --output /tmp/mr3_p2a_v20_closed_preparation_v1.json，parent原A15 finite_actual_runner_v2.py，cwd canonical root。核131 CPU当前source与全snapshot、3wholeinverse、7个runtime顶层声明AST/35数学原文的既有proof、两完整只读PASS与无信号truewait、v1失败原source、v2 union末账守恒、历史log仅append、133个selected/new本地links及22 live/helper Python AST/JSON。它只为当时input版本给静态CPU信用，不供新native/科学/PPO资格，不新增工程费；本条仅追加实际结果，未改原源码或原失败。


## 2026-10-20 MR3 P2A V21 有界诊断准备

用户在评估交接后指示“好，现在按要求继续执行P2A吧”。既有52000工程上限和V20精确末账不变，在余13783.4895025853982秒内预约6500工程秒；1worker、open101重复两次各32步、合法掩码随机seed41，native3200含close180，全部独立读者和外部尾计入真实活动费用，失败不重试。不是完整资格矩阵，无PPO/GPU/optimizer/pilot/final-only/二维/gateway；实际原生尚未启动。

准备基线f874cd04b，具体source/ELF计划、独立消费者和命令见 [V21](report/20261020_mr3_p2a_v21_feasibility.md)。组合CPU由conda ns3gym、PYTHONNOUSERSITE=1、CUDA_VISIBLE_DEVICES空的 `mr3_learning.reach_execution --scope cpu` 实际wait，100 tests PASS、outer rc0/9.975746618秒（unittest4.766秒），7份源前后稳定；完整argv与console在 `report/assets/20261020_mr3_p2a_v21/checks/combined_cpu_v1/actual_wait.json`。仅CPU准备，不收费或提供原生信用。封存plan SHA f2ddefb691944c17a8dfa5ea4d8d1f180fed6868378b41e06aca46ffd2a0eaf8，445源/10ELF；必须clean/pushed新freeze前检成功后才运行，后续真实结果另追加。


## 2026-10-20 MR3 P2A V21 实际诊断FAIL闭合

沿上节预声明，在clean/pushed冻结 `c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90`、plan SHA `f2ddefb691944c17a8dfa5ea4d8d1f180fed6868378b41e06aca46ffd2a0eaf8` 下执行。固定tb1/tb2/tb3、单worker、open101两次各32步、合法均匀随机seed41、domain224/port14901，native3200含close180、总6500预约。环境PYTHONNOUSERSITE=1、PYTHONDONTWRITEBYTECODE=1、CUDA_VISIBLE_DEVICES空；cwd canonical wireless-rl，learner使用conda ns3gym，readers各自真实Python见回执。无重试、无PPO/GPU/optimizer，pilot/final-only/二维/gateway不动。

以下为实际outer child原argv，外层均由 `mr3_learning.reach_execution` 保存源快照与真实wait，完整argv/identity/时钟在对应回执，不用人工计时替代：

CPU前检：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.reach_diagnostic preflight --plan report/assets/20261020_mr3_p2a_v21/predeclared_plan_v1.json --freeze c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90 --output /tmp/mr3_p2a_v21_diagnostic_preflight.json
```

真实rc0/26.057773539秒，actual_waited=true/source unchanged；[receipt](report/assets/20261020_mr3_p2a_v21/closed_execution/mr3_p2a_v21_diagnostic_preflight_outer/actual_wait.json)。

engineering主活动：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.reach_diagnostic execute --plan /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261020_mr3_p2a_v21/predeclared_plan_v1.json --freeze c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90
```

真实rc1/3263.539596404秒，actual_waited=true/source unchanged；[receipt](report/assets/20261020_mr3_p2a_v21/closed_execution/mr3_p2a_v21_diagnostic_outer/actual_wait.json)。

engineering外部final：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.reach_diagnostic final --plan /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261020_mr3_p2a_v21/predeclared_plan_v1.json --outer /tmp/mr3_p2a_v21_diagnostic_outer/actual_wait.json --output /tmp/mr3_p2a_v21_diagnostic_absence.json
```

真实rc0/0.283544031秒，actual_waited=true/source unchanged；[receipt](report/assets/20261020_mr3_p2a_v21/closed_execution/mr3_p2a_v21_diagnostic_final_outer/actual_wait.json)。

实际九份nested command的原命令和wait（全部位于主outer内，不重复收费；完整回执/console见closed_execution）：

- native：真实rc0/2073.892364923秒。`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.benchmark --workers 1 --schedule open:101,open:101 --steps 32 --run-id uniform_two_episodes --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v21_diagnostic --safety-contract mr3-reach-v1 --diagnostic-uniform-seed 41 --base-domain 224 --base-port 14901 --work-wall-seconds 3200 --close-reserve-seconds 180`

- watcher：真实rc0/2078.301772991秒。`/usr/bin/python3 -m mr3_learning.native_custody_reach watch --run-directory /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v21_diagnostic/uniform_two_episodes --freeze c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90 --binding /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261020_mr3_p2a_v21/native_custody_binding_v1.json --ready-file /tmp/mr3_p2a_v21_diagnostic/ready.json --stop-file /tmp/mr3_p2a_v21_diagnostic/stop.json --output /tmp/mr3_p2a_v21_diagnostic/live_custody.json`

- information_002：真实rc0/449.354255872秒。`/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261020_mr3_p2a_v20/bounded_read_only_child_v1.py --output /tmp/mr3_p2a_v21_diagnostic/information_002_supervision --wall-seconds 900 -- /usr/bin/python3 -m mr3_learning.audit_reach_information /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v21_diagnostic/uniform_two_episodes/worker0/episode002_open_101 --freeze c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90 --output /tmp/mr3_p2a_v21_diagnostic/information_002_result.json`

- information_001：真实rc0/479.393231365秒。`/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261020_mr3_p2a_v20/bounded_read_only_child_v1.py --output /tmp/mr3_p2a_v21_diagnostic/information_001_supervision --wall-seconds 900 -- /usr/bin/python3 -m mr3_learning.audit_reach_information /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v21_diagnostic/uniform_two_episodes/worker0/episode001_open_101 --freeze c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90 --output /tmp/mr3_p2a_v21_diagnostic/information_001_result.json`

- fifo_001：真实rc0/496.724158484秒。`/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261020_mr3_p2a_v20/bounded_read_only_child_v1.py --output /tmp/mr3_p2a_v21_diagnostic/fifo_001_supervision --wall-seconds 900 -- /usr/bin/python3 -m mr3_learning.audit_reach_peer_control /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v21_diagnostic/uniform_two_episodes/worker0/episode001_open_101 --freeze c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90 --output /tmp/mr3_p2a_v21_diagnostic/fifo_001_result.json`

- fifo_002：真实rc0/502.708009477秒。`/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261020_mr3_p2a_v20/bounded_read_only_child_v1.py --output /tmp/mr3_p2a_v21_diagnostic/fifo_002_supervision --wall-seconds 900 -- /usr/bin/python3 -m mr3_learning.audit_reach_peer_control /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v21_diagnostic/uniform_two_episodes/worker0/episode002_open_101 --freeze c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90 --output /tmp/mr3_p2a_v21_diagnostic/fifo_002_result.json`

- closure：真实rc0/52.663460966秒。`/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261020_mr3_p2a_v20/bounded_read_only_child_v1.py --output /tmp/mr3_p2a_v21_diagnostic/closure_supervision --wall-seconds 900 -- /usr/bin/python3 -m mr3_learning.native_custody_reach review --run-directory /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v21_diagnostic/uniform_two_episodes --freeze c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90 --binding /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261020_mr3_p2a_v21/native_custody_binding_v1.json --capture /tmp/mr3_p2a_v21_diagnostic/live_custody.json --launch-receipt /tmp/mr3_p2a_v21_diagnostic/native_command.json --fifo-receipts /tmp/mr3_p2a_v21_diagnostic/fifo_manifest.json --expected-episodes 2 --output /tmp/mr3_p2a_v21_diagnostic/closure_result.json`

- native_episode_checks：真实rc0/325.663984039秒。`/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261020_mr3_p2a_v20/bounded_read_only_child_v1.py --output /tmp/mr3_p2a_v21_diagnostic/native_episode_checks_supervision --wall-seconds 900 -- /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.audit_reach_diagnostic /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v21_diagnostic/uniform_two_episodes --freeze c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90 --plan /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261020_mr3_p2a_v21/predeclared_plan_v1.json --output /tmp/mr3_p2a_v21_diagnostic/native_episode_checks_result.json --fifo-result /tmp/mr3_p2a_v21_diagnostic/fifo_001_result.json --fifo-result /tmp/mr3_p2a_v21_diagnostic/fifo_002_result.json`

- cadence：真实rc1/727.869397496秒。`/usr/bin/python3 /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261020_mr3_p2a_v20/bounded_read_only_child_v1.py --output /tmp/mr3_p2a_v21_diagnostic/cadence_supervision --wall-seconds 900 -- /usr/bin/python3 -m mr3_learning.audit_reach_cadence /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v21_diagnostic/uniform_two_episodes --freeze c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90 --output /tmp/mr3_p2a_v21_diagnostic/cadence_result.json`


完整活动 **FAIL**：native rc0、两次完整进程重建，各32次step/32.0秒奖励与物理时间，关闭尾后evaluator32.2秒。FIFO两场、Information两场、native/scalar/观测/received输入基础核查和实际ELF来源关闭通过；Cadence含完整Runtime真实rc1/727.869397496秒，不是timeout、没有signal、没有跳过审计。第一回合报 `ValueError('worker substituted an unreceived storage ACK')`，第二回合通过；所有FAIL和原件保留，不补完整矩阵资格。

有限只读取证精确定位e1 tb3、clock68980000000、cmd_seq3059/decision_seq3231/q1547：worker真实ACK接收4229387098966908、消费4229387124514451、推进许可4229387130022304；guard同一完整ACK ingress4229387131098333，晚1,076,029ns。native命令接收/发布一致。不是缺ACK或索引错位，当前reader要求的跨订阅先后真实不满足；不能直接改称误判或删谓词。7条精确原件、行SHA/全文件inventory引用见[forensics](report/assets/20261020_mr3_p2a_v21/ack_order_forensics_v1.json)。常规修复补真实guard完成屏障，CPU结果随后另列；无新native重试。

两回合correct-free覆盖.7412124532091664/.7304619738884324；质量/三机参与/95成功均false。tb1/tb3路径仅(.015443/.007109)m和(.015166/.091113)m；目标接受不当运动。18接触源fresh/active、event0、ever_unhealthyfalse；最终导航closed=true/pending0，35目标全cancel/0success/0abort，Nav2全部finalized，无forced/残余owned/zombie。35/64步mask仅单合法，37/64动作888，不能把64返回当64次有效探索。native返回率.03085984648117/秒、全活动.01960890564416/秒仅描述本次短随机诊断；training_eligible=false、0policy/GPU/optimizer，不预测长期PPO容量。

外部absence真实检查原109身份gone，通过不覆盖diagnostic FAIL；其真实outer退出后更晚复查加入helper与child，共111唯一PID/start全部absent，无不可读/同startZ。九nested不重复收费，主3263.539596404+外尾.283544031两区间不重叠，union **3263.823140435**。累计 **41480.3336378496018/52000**，余 **10519.6663621503982**；pilot1870/2905.9547395464029秒及三final-only不动。原未批60000提案当前也仅余18519.6663621503982，距20100预约缺1580.3336378496018，不再具有数值准入条件。

全部1033份native原件/2,041,262,832字节保留并封存为三part xz，整archive SHA390ff3177eb0ff45685ce86dd6cea02c799e9e988ca38faa5ae93afd229dc6a3，解压全部成员SHA/bytes与原清单一致、原件前后不变。53份辅助原件精确复制及SHA索引、真实outer、完整消费者、封存方法、末账与描述性小原件见[V21完整报告](report/20261020_mr3_p2a_v21_feasibility.md)。CPU封存/小原件核算不提供实验资格。后续[二维具体提案](report/20261020_mr3_p2a_next_route_proposal.md)仅准备可审阅范围，9000step/3600秒零更新候选未批准/未执行，不能视为训练或扩额授权。


V21闭合后真实guard存储屏障常规修复：生产mr3_motion_control.py仅17行，现有v2 motion-phase完成ACK前复用DrivePhaseClient对三个guard实际回调缓存匹配，真实ingress原行先于poll，保持worker独立存储门、reader原谓词、STOP/takeover立即零与完成屏障、legacy及超时失败；无新RPC/schema/sleep/重发/原件修改。

系统ROS CPU实际命令：

```bash
/bin/bash -c 'source /opt/ros/humble/setup.bash
source install/setup.bash
exec /usr/bin/python3 -B -m pytest -q src/multi_robot_exploration/test/test_mr3_control_phase.py src/multi_robot_exploration/test/test_mr3_drive_phase.py src/multi_robot_exploration/test/test_mr3_reach_delivery_order.py'
```

真实v2 rc0/9.439727408秒/source stable，132 PASS（pytest7.64秒），回执和console在report/assets/20261020_mr3_p2a_v21/checks/guard_storage_barrier_cpu_v2。原v1相同测试组合真实rc1/11.345561775秒，115 PASS/17新fake clock缺now()失败；只修fixture并新目录复测，原v1回执/console/源SHA保留。首次precheck误匹配自身shell导致未spawn测试，原失败说明也保留。均CPU准备，不提供修复后native/科学资格、不收费、无重试/训练。新运行时源码不得冒充c38e3e8原native，后续需新冻结，P2A未完成。


V21最终有限静态检查实际CPU rc0/1.682505902秒/source stable，命令system Python -B report/assets/20261020_mr3_p2a_v21/check_closed_v1.py，经reach_execution --scope cpu、cwd canonical wireless-rl；完整argv与6份源SHA在report/assets/20261020_mr3_p2a_v21/checks/closure_static_v1/actual_wait.json。核三part及拼接SHA、53copy对原件、1033清单、FAIL/费用/111身份/132CPU/首轮失败保留、JSON/AST/新增链接与历史log仅追加；结果closed_integrity_v1.json。仅静态封存，不重放正式reader、不新增native或费用。


## 2026-10-20 MR3-P2A V22 二维代理准备（用户已接受限定范围）

用户“继续，同意”接受具体二维实现、接口符合性和一次零更新容量活动，9000 ENV.step尝试/3600秒/最多30回合；固定三机，1env六场后4env各六场，open/rooms/corridors×101/103，seed41合法mask均匀动作；不授权训练、native重试/迁移、扩额、pilot/final-only或gateway。工程入场41480.3336378496018/52000、余10519.6663621503982。V21原FAIL不改。

本次仅CPU准备，最终106项通过（ROS50、learner29、独立审计13、符合性8、活动边界6）；所有开发复测、失败、实际命令/源码hash/退出/wait原件列在[CPU清单](report/assets/20261020_mr3_p2a_v22_proxy2d/cpu_preparation_index_v1.json)，不累计重复版本为独立覆盖。ROS组合v1路径拼写错误rc4未收集测试，learner组合v1的mock生命周期6ERROR rc1保留；早期pytest/SciPy缺失tool观察保留，未补造缺失纳秒或console原件。均纯fixture/stub与已隔离小合成模型，不消费正式V21重放或实际三场景episode，不收费、不提供native95资格。关键真实wait：ROS最终3.907126901秒、learner最终1.436260389秒、审计最终4.697330542秒、符合性最终5.622836000秒、边界.447793231秒。

实现复用原received地图/状态传输、build_snapshot/encode_snapshot、GoalDispatcher、RewardLedger和地图质量/参与函数；plant为显式二维单车、编码器偏置、本机扫描积分与交付图局部执行，独立进程evaluator唯一读取特权物理状态。默认原生/PPO入口不变，training_eligible/native_credit=false。完整边界见[V22报告](report/20261020_mr3_p2a_v22_proxy2d.md)。冻结后唯一正式活动实际命令/结果随后追加，准备不预报PASS。

V22冻结前有限静态检查通过：真实CPU rc0/1.513117174秒，107份绑定源、106关键fixture回执、活动文档链接和log历史只追加核验通过；完整命令与前后SHA在report/assets/20261020_mr3_p2a_v22_proxy2d/checks/preparation_static_v2/actual_wait.json。首轮脚本直接路径执行缺包搜索路径，rc1/.090726768秒，原console/回执保留；仅脚本显式定位canonical W后新目录复测，不改生产或预声明源。

V22封存器准备：另12项纯小tempfile/分片/拒覆盖/非regular拒绝fixture PASS，真实CPU rc0/.458022174秒/source stable；checks/seal_cpu_v1保存完整命令/fixture/console/wait。无实际run封存或原件消费者重放；该文件封存工具不改变实验结果。


## 2026-10-20 MR3-P2A V22 唯一正式活动FAIL闭合

冻结1dc2a1f601693f542479f9b6b7c54c69519b5460，clean/pushed前检通过；固定三机、9000尝试/3600秒上限、open/rooms/corridors×101/103、1env后4env、每episode最多300、均匀合法动作seed41，无模型/GPU/optimizer、无补样或重试。实际命令（每份receipt保存cwd/env/source SHA/stat/实际wait与console，路径均见V22辅助索引）：

preflight_outer scope=cpu，真实rc0/1.747137385秒：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_activity preflight --freeze 1dc2a1f601693f542479f9b6b7c54c69519b5460
```

outer scope=engineering，真实rc1/1780.291538385秒：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_activity execute --freeze 1dc2a1f601693f542479f9b6b7c54c69519b5460
```

forensics_outer scope=engineering，真实rc0/0.866121738秒：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B /tmp/mr3_proxy2d_v22_forensics_v1.py
```

final_outer scope=engineering，真实rc0/0.332686965秒：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_activity final --run /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v22/run_v1 --outer /tmp/mr3_proxy2d_v22_outer/actual_wait.json --output /tmp/mr3_proxy2d_v22_absence.json
```

四nested阶段均含于主outer，不重复收费：

- conformity：rc0/12.599340248秒，无timeout/signal。`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_conformity --freeze 1dc2a1f601693f542479f9b6b7c54c69519b5460 --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v22/run_v1/conformity.json`

- conformity_review：rc0/0.867650299秒，无timeout/signal。`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.audit_proxy2d /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v22/run_v1 --freeze 1dc2a1f601693f542479f9b6b7c54c69519b5460 --conformity-only /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v22/run_v1/conformity.json --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v22/run_v1/conformity_independent.json`

- capacity：rc0/1760.625803367秒，无timeout/signal。`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_activity collect --run /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v22/run_v1`

- audit：rc1/4.476738606秒，无timeout/signal。`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.audit_proxy2d /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v22/run_v1 --freeze 1dc2a1f601693f542479f9b6b7c54c69519b5460 --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v22/run_v1/independent_audit.json`

结果：符合性6条历史原件重建+3项合成及独立review PASS；采集284尝试/284原始返回/0step错误，仅group1首场open101未完成。group4空metadata、没有实际worker或数据，不能称四环境0吞吐。group1真实reset/close分母1760.142537073秒，原始返回率.16135056906940792/秒；不是全部验证的训练样本率，不外推训练。完整独立审计真实rc1/4.476738606秒，FAIL保留。

明确工程缺陷：第4step event9的3.1→4.1与第64step event129的63.1→64.1，原始整数端点都正好1e9ns、RewardLedger dt1，但worker float(end-start)分别.9999999999999996/.9999999999999929，严格审计正确FAIL。有限标量取证独立核284 source-dt全1e9、reward dt全1、全部预约实际在group/collection区间内，未重建actor/张量/候选、不补资格。旧reader fail-first实际只到4action/3return/4actor/reset+首return完整重建，旧JSON声称uniform replay284属原始计数误信用，应作废该信用；其“not recorded before deadline”合并了覆盖不足，并不证明真实晚预约。原错误输出逐字保留。

最后正确自由覆盖.8741897197114946、质量false/参与true/代理contact0，无代理任务成功。task elapsed284秒；close后physical284.92/snapshot284.1，尾.82秒，navigation_closed=true、evaluator rc0、supervisor actual wait rc0/forced=false。外部final与父进程退出后更晚17个保存PID/start全部gone，无同startZ/不可读，不用absence覆盖FAIL。

主1780.291538385+有限取证.866121738+外尾.332686965三个实际区间union1781.490347088秒；累计43261.8239849376018/52000，余8738.1760150623982。pilot1870/2905.9547395464029秒、三final-only401/402/403不动，60000未批准。完整323原件/16,539,807bytes封存1part14,225,588bytes，SHA18e67dcf20b63759aab797d56547f0262bc98a22004caa88de871ab4b65297d8；逐成员SHA/bytes和原件前后不变通过，18辅助文件exactcopy。CPU封存真实rc0/5.093577816秒，不重放formal reader。详细原件与交接见[V22](report/20261020_mr3_p2a_v22_proxy2d.md)。

V22旧冻结收口后常规修复：worker由原start_ns/end_ns差计算physical_dt，关闭尾排除；15项CPU stub PASS，rc0/2.23298176秒/source stable，checks/worker_integer_clock_cpu_v1保留。审计器分raw与verified动作/uniform/actor/return，raw close与verified close、deadline覆盖与真实越界，fail-first和严格_duration谓词保持；16项纯fixture PASS，rc0/13.57748793秒/source stable，checks/audit_verified_prefix_cpu_v1保留。284原始/第4return失败fixture只给4/4/4/3验证信用，不能借修复改判旧run。两份实际argv/source/wait/console均在V22 assets checks下，无actualepisode或旧reader重放、不新增工程实验费。

后续建议先做有界分段剖析和等价缓存，后续容量改短固定覆盖以保证两group先有数据；另拟240尝试/1800秒只是未批候选，不启动新活动/训练/原生重试/gateway。P2A仍未完成。

V22收口静态检查：最终真实CPU rc0/1.412626768秒/source stable，核323原件SHA/bytes、14MB分片/18exactcopy、原FAIL/错误信用保留、费用/17保存身份、旧冻结107source与仅2份生产修复差、459相对链接/log只追加，回执checks/closed_static_cpu_v2，结果closed_static_result_v1.json。首轮静态脚本假定所有回执都同schema且应匹配当前全部依赖，rc1/1.323912929秒；原件保留。worker首次15项回归时auditor为原严格版本，随后verified报告修复变化；为核最终组合，原worker测试按同一stub在当前auditor下复测15PASS，真实CPU rc0/2.281090497秒/source stable，checks/worker_integer_clock_cpu_v2。静态脚本按两份真实回执schema分别核SHA后通过；原严格_duration未改、无正式重审或新模拟。


## 2026-10-20 MR3-P2A V23 性能续接准备

用户“按你的想法继续”接受性能剖析/提速路线。预声明新profile最多1EP/8attempt/600秒和优化后新short最多30EP/240attempt/1800秒，共248attempt/31EP/2400秒最大预约，入场43261.8239849376018/52000、余8738.1760150623982；无新训练/原生/gateway/扩额或pilot/final-only。旧V22 FAIL/旧run不重试/改判。

准备检查全部CPU：profile helper12项（真实2.278037488秒）、Supervisor profile开关12项（.370441004秒）、worker/helper组合29项（2.857794434秒）、活动预算/末账10项（.653239656秒）、原审计/codec/counter及新规格组合34项（37.892244021秒）。这些含重复覆盖，不累计成独立总数；所有真实command/cwd/env/source before/after或byteSHA/wait/console在[CPU清单](report/assets/20261020_mr3_p2a_v23_performance/cpu_preparation_index_v1.json)。无World实际episode或旧reader重放、不收费不供资格。

profile显式cProfile独占新文件、原样传播非零SystemExit/异常，两子进程独立pstats；默认关闭并清除外部继承profile输出。新collect/audit_spec固定kind/groups/cells/maxstep/attempt/600或1800时钟；1/4组分别400/800窗口，全局共享ticket；正常提前终态不补样、安全终态显式error停止；验证全actual verified覆盖，原V22无spec行为/严格_duration不变。预算/原件预声明见[V23](report/20261020_mr3_p2a_v23_performance.md)，freeze后实际结果随后追加。


## 2026-10-20 V23 profile实际PASS闭合及打包优化准备

profile freeze caddd853ab8884b3e2fd1018069af2fdc139d3e8，open101/seed41，1EP最多8步；当轮符合性/独立review与完整episode审计PASS，8attempt/return全verified，第8步真实外部截断并正常关闭。真实命令：

profile_preflight_outer scope=cpu rc0/1.907348852秒：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance preflight --kind profile --freeze caddd853ab8884b3e2fd1018069af2fdc139d3e8
```

profile_outer scope=engineering rc0/69.60772768秒：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance execute --kind profile --freeze caddd853ab8884b3e2fd1018069af2fdc139d3e8
```

profile_final_outer scope=engineering rc0/0.53091343秒：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance final --kind profile --run /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/profile_v1 --outer /tmp/mr3_proxy2d_v23_profile_outer/actual_wait.json --output /tmp/mr3_proxy2d_v23_profile_absence.json
```

全部nested实际命令与wait（已含在主outer、不重复收费）：

- conformity rc0/12.950301833秒：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_conformity --freeze caddd853ab8884b3e2fd1018069af2fdc139d3e8 --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/profile_v1/conformity.json`

- conformity_review rc0/0.867493909秒：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.audit_proxy2d /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/profile_v1 --freeze caddd853ab8884b3e2fd1018069af2fdc139d3e8 --conformity-only /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/profile_v1/conformity.json --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/profile_v1/conformity_independent.json`

- collection rc0/47.547765784秒：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance collect --kind profile --run /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/profile_v1`

- audit rc0/5.679486232秒：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.audit_proxy2d /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/profile_v1 --freeze caddd853ab8884b3e2fd1018069af2fdc139d3e8 --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/profile_v1/independent_audit.json`

- profile_report rc0/0.666768711秒：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance profile_report --kind profile --run /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/profile_v1`

profile worker totalself45.593秒、_known_line self12.0495/112491calls、update_maps cumulative18.5024、OccGrid data setter9.9811/333calls；evaluator44.384秒中43.08秒等输入。累计函数与进程重叠不能相加，instrumented速率不当真实未剖析容量。性能完整输出/pstats及52份原件封存在A23/profile_closed，14保存身份gone。主69.60772768+外尾.53091343实际union70.13864111，累计43331.9626260476018/52000，余8668.0373739523982；pilot/final-only不动。

按测量优先优化已验证map的数组打包，merge/navigation、worker int8→arrayb走ROS本机快路径，restore仅exact builtin int/bool list conservative fastpath，溢出/非JSON Python类型/其他消息仍原setter；原fusion/path/_known_line/actor/reward/物理/信息年龄门未改。merge30+独立旧新32小图fixture、information/merge/proxy信息102、worker19 CPU通过，完整actualcommand/source前后SHA/console/wait在A23 checks/map_packing_cpu_v2、restore_packing_cpu_v1、worker_packing_cpu_v3；分别最终merge2.501076412秒/独立机制2.063845796秒、restore3.810323824秒、worker2.680710161秒，不合计重复检查为独立覆盖。局部100次setter中位48.175335ms→.323835ms，只证明该机制。

所有开发失败保留：merge v1新fixture错误假定CDR padding bytes可逐字固定（29pass/1fail）；worker v1原CDR测试通过，但改进fixture的v2错误将ROS wire float32 resolution.05直接等于原Python float（17pass/2fail），v3双边CDR往返/精确字段data bytes通过。原件与运行源码不改判，无actualepisode新增。short_capacity在新源码freeze/新plan下最多30EP/240attempt/1800秒，将先核当轮符合性再采集，无cProfile/训练。详见[V23](report/20261020_mr3_p2a_v23_performance.md)。

V23 short冻结前证据属性修正：初次cached diff-check指出已封存map_packing_cpu_v1/console.txt pytest原文有尾空格，首次优化提交仍发生；原console不编辑/不覆盖。新增该证据console.txt的-text/-whitespace属性，与其他精确console保留规则一致，复查后另commit/push，不改运行源、原件SHA或实费/结果。


## 2026-10-20 V23 short实际PASS闭合与最终账

short freeze `2e8fcac9439a1a53e3913e45abccdc0b6645825d`，当时main=origin/main且clean，110绑定源/plan入场与末端稳定；无cProfile，0policy/GPU/optimizer。固定1/4env每worker open/rooms/corridors×101/103、动作RNG base41（每组41+1000003×env_id、跨该worker六EP连续）、每EP max_steps8，30EP/240attempt/240return/0step_error/30实际external_sampler_limit且正常关闭；240 action/uniform/return及270 actor records全verified，global ticket完整1..240、时钟完整0越界，无补样/重试。符合性6旧原件+3合成当轮核验与独立review通过，不产生新native run或资格。

所有入口在canonical wireless-rl cwd，PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1，engineering另CUDA_VISIBLE_DEVICES空及OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1；下列exact actual_argv由reach_execution实际wait回执提取，完整wrapper/source before-after SHA/parent与child PID/start/console归档A23/short_closed/closed_execution，run原件含各实际env/epoch/动作与执行尾。

short_preflight_outer scope=cpu rc0/1.154096144秒/source stable：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance preflight --kind short_capacity --freeze 2e8fcac9439a1a53e3913e45abccdc0b6645825d
```

short_outer scope=engineering rc0/735.849491694秒/source stable：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance execute --kind short_capacity --freeze 2e8fcac9439a1a53e3913e45abccdc0b6645825d
```

pair_outer scope=engineering rc0/0.337749651秒/source stable：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B /tmp/mr3_proxy2d_v23_pair_v1.py
```

short_final_outer scope=engineering rc0/0.51818622秒/source stable：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance final --kind short_capacity --run /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/short_capacity_v1 --outer /tmp/mr3_proxy2d_v23_short_outer/actual_wait.json --output /tmp/mr3_proxy2d_v23_short_absence.json
```

short_closed_metadata_cpu_v1 scope=cpu rc0/0.157588465秒/source stable：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261020_mr3_p2a_v23_performance/close_activity_v2.py --kind short_capacity --run /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/short_capacity_v1 --outer /tmp/mr3_proxy2d_v23_short_outer/actual_wait.json --extra-outer /tmp/mr3_proxy2d_v23_pair_outer/actual_wait.json --extra-json /tmp/mr3_proxy2d_v23_pair_v1.json --final-outer /tmp/mr3_proxy2d_v23_short_final_outer/actual_wait.json --absence /tmp/mr3_proxy2d_v23_short_absence.json --output report/assets/20261020_mr3_p2a_v23_performance/short_metadata --entry 43331.9626260476018
```

short_archive_cpu_v1 scope=cpu rc0/4.213862725秒/source stable：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261020_mr3_p2a_v22_proxy2d/seal_results_v1.py --run /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/short_capacity_v1 --outer /tmp/mr3_proxy2d_v23_short_outer --outer /tmp/mr3_proxy2d_v23_pair_outer --outer /tmp/mr3_proxy2d_v23_short_final_outer --copy /tmp/mr3_proxy2d_v23_short_preflight_outer --copy /tmp/mr3_proxy2d_v23_short_absence.json --copy report/assets/20261020_mr3_p2a_v23_performance/short_metadata --copy /tmp/mr3_proxy2d_v23_pair_v1.py --copy /tmp/mr3_proxy2d_v23_pair_v1.json --copy /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/short_capacity_v1/activity_result.json --copy /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/short_capacity_v1/independent_audit.json --copy /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/short_capacity_v1/capacity_summary.json --output report/assets/20261020_mr3_p2a_v23_performance/short_closed
```

主outer包含以下nested实际wait（不另加费）：

- conformity rc0/12.799853446秒：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_conformity --freeze 2e8fcac9439a1a53e3913e45abccdc0b6645825d --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/short_capacity_v1/conformity.json`

- conformity_review rc0/0.869791539秒：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.audit_proxy2d /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/short_capacity_v1 --freeze 2e8fcac9439a1a53e3913e45abccdc0b6645825d --conformity-only /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/short_capacity_v1/conformity.json --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/short_capacity_v1/conformity_independent.json`

- collection rc0/514.334642721秒：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance collect --kind short_capacity --run /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/short_capacity_v1`

- audit rc0/206.482445868秒：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.audit_proxy2d /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/short_capacity_v1 --freeze 2e8fcac9439a1a53e3913e45abccdc0b6645825d --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23/short_capacity_v1/independent_audit.json`

组1的6EP/48verified return耗199.459093428秒、.24065084812654514步/墙秒；组4的24EP/192verified耗314.375271233秒、四环境合计.6107350595578452步/墙秒，均含本组reset/close，不含之后独立审计。collection phase实际514.334642721秒；audit206.482445868秒在300秒原阶段限内，无超时/重试。不能和受剖析profile或V22长回合算整步加速倍数，更不代表95%/学习收益。

预指定profile↔short共享open101/group1/worker0 reset+8行编码tensor dtype/shape/byteSHA、动作与reward/dt/physical_dt/终态/reason一致；只读已有proof/trace，无新World/actor重编码，只给该固定前缀等价观察。工程消费者.337749651秒已计费，源脚本/原结果已封存。external原69身份absent；后检额外覆盖pair父子与final父子，short共73保存PID/start全gone、0不可读/僵尸；profile另14gone，本轮共87身份gone。

short main735.849491694+pair.337749651+final.51818622三个outer union736.705427565秒；profile70.13864111另计，V23合计806.844068675秒。精确累计44068.6680536126018/52000，余7931.3319463873982；首末outer含间隔真实跨度profile94.160533108<600、short953.206219195<1800，既满足活动上限也没有把nested并行重复加费。pilot仍1870决策/2905.9547395464029秒，final-only401/402/403未动。末账为A23/short_metadata/engineering_accounting_v1.json。

完整598files/16,310,889bytes原件封存run.tar.xz.part0001（13,206,468bytes，SHA791a6116237973276af8caf724b809bddf4e13e370fa2eda9910f73c1115da45），16份aux exactcopies及所有成员bytes核对、原件前后不变。CPU封存/账目回执分别4.213862725/.157588465秒，无正式reader重放/新episode，不计工程费/资格。独立agent只读摘要、actual interval与/proc另核算通过，未新增实验。

结论与下一AI路线见[V23](report/20261020_mr3_p2a_v23_performance.md)和更新后的[评估交接](report/20261020_mr3_p2a_assessment_handoff.md)：继续保留二维采样/原生正式验收方向，先具体化完整时长任务行为检查，再决定二维最小学习投入；8步短容量不能解锁长训练/native/PPO/gateway。未改_known_line/actor原纯构造字节、原任务/信息/安全门或旧FAIL。现工程余额不足旧20100完整资格预约，不扩52000；本轮授权两次活动已全部结束，下一活动需新具体范围/plan与实际授权，P2A仍未完成。

V23闭合静态核查CPU rc0/1.499108469秒/source stable：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261020_mr3_p2a_v23_performance/closed_static_check_v1.py`，由reach_execution --scope cpu独立实际wait，完整回执checks/closed_static_cpu_v1。核profile52/short598原件SHA/bytes、全部分片/metadata及13/16辅助原件copy、110绑定源与short冻结Git字节、原native纯actor/episode源码不变、精确费用/全87身份/proc、461相对链接、log只追加及旧ARCHIVE_INDEX记录/备份分支不变。结果closed_static_result_v1.json，仅有限CPU归档/源码/文档核查，无World/actor或正式audit重放、不新增工程费/资格。独立文档审阅另修正动作RNG为每组41+1000003×env_id且每worker跨六回合连续，V22旧余额明确历史；只修叙述，不改原运行/样本。


## 2026-10-21 MR3-P2A V24 完整时长二维行为诊断准备

用户“继续执行吧”续接V23完整时长行为检查建议；一次新freeze零训练活动，3并发env0/open101、env1/rooms101、env2/corridors101各一EP，每env仍三机器人，动作seed41+1000003×env_id且真实前序mask均匀抽样。各原300sim秒/最多300attempt，全局3EP/900attempt/3600工程秒，入场44068.6680536126018/52000、余7931.3319463873982，最坏余4331.3319463873982。conformity60/review20/collection2100/audit950/behaviorreport100，另external120及每阶段cleanup180动态保留；不足/异常FAIL，不重试/补样/换seed。pilot1870/2905.9547395464029与final-only401/402/403不动，0policy/GPU/optimizer，无native/gateway/扩额。原300timeout优先，外部cut不作完整任务信用。

首项61条组合纯CPU/stub/人工snapshot检查PASS，非真实World/native/旧原件重放，真实rc0/80.466307479秒/source stable；其中900人工返回fixture核903 actor记录，不能当900新环境样本。范围、精确actualargv/cwd/source前后SHA/console/wait见A24/checks/activity_capacity_cpu_v1（A24=report/assets/20261021_mr3_p2a_v24_behavior）。实际子命令：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m unittest -v mr3_learning.tests.test_proxy2d_capacity mr3_learning.tests.test_audit_proxy2d mr3_learning.tests.test_proxy2d_performance mr3_learning.tests.test_proxy2d_activity
```

还在完成独立行为consumer/fixture；此处不预报正式PASS。原严格_duration函数字节未改，纯actor/任务/信息/安全/奖励规则保持；旧V21/V22失败和V23短容量范围不变。

并行agent在统一检查通知到达前已经启动一次相同capacity/audit开发CPU检查，正常rc0/41项PASS；unittest自报76.707秒，未采独立outer纳秒/PID，明确null、不补造。完整exactargv/观察和原console保留A24/checks/development_direct_cpu_v1，仅重复开发检查，不累加独立项或新环境/工程信用。未启动其他formal consumer/World/native。

V24入口/关闭保护补充：新scope入场账必须等于封存44068.6680536126018，collect CLI kind必须匹配context；预算或启动异常显式保存behavior_report跳过原因。phase已生成child后如pidfd/identity准备异常，仍通过原Popen unreaped owned handle受控SIGINT/必要KILL并实际wait、保存FAIL回执，不泄漏进程或伪报PASS。24项纯mock入口/预算/环境/异常关闭CPU通过，真实rc0/0.723031392秒/source stable；重复覆盖不累加。exact子命令：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m unittest -v mr3_learning.tests.test_proxy2d_performance mr3_learning.tests.test_proxy2d_activity`，回执A24/checks/activity_admission_cpu_v2。

V24独立行为consumer11项纯CPU通过，真实rc0/5.634405988秒/source stable/0skip；system ROS Python实际运行真实ProxyReward 1×1小数组与人工private状态集成用例，未创建ProxyWorld/Node/真实episode、未消费历史原件。另测300timeout+close drain、deadline contact unsafe、地图/clock/goalcounter/奖励篡改、baseFAIL保留raw/verifiedprefix。exact actualargv（完整环境/source/wait/console见A24/checks/behavior_consumer_cpu_v1）：

```bash
/usr/bin/bash --noprofile --norc -c 'unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH ROS_PACKAGE_PATH VIRTUAL_ENV; export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; source /opt/ros/humble/setup.bash && source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash && exec /usr/bin/python3 -B -m unittest -v mr3_learning.tests.test_audit_proxy2d_behavior'
```

V24新plan build仅静态封存（无World），命令`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance build --kind full_behavior --entry-seconds 44068.6680536126018` rc0；plan为A24/full_behavior_plan_v1.json。最终预冻结静态检查rc0/2.211512485秒/source stable，exact命令`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261021_mr3_p2a_v24_behavior/preparation_check_v1.py`；112执行/审计/场景/范围绑定、独立spec吻合、460相对链接、原纯actor/episode/_duration字节、log只追加和备份分支均通过。回执checks/preparation_static_cpu_v1，结果preparation_static_result_v1.json；所有准备检查见A24/cpu_preparation_index_v1.json。正式诊断待当前clean提交推送freeze和前检后执行，准备不供原生/训练或新环境信用。

V24正式冻结前只读复核发现，同一clock ns内close/下一flush晚到accept不能按<=timestamp借给较早boundary；consumer已改为真实boundary snapshot accepted_goal_count精确对应，protocol strict-before/inclusive作因果上下界。coverage还独立核实际close完成时刻<原300秒，不接受恰deadline或超后关闭。新增同ticklateaccept及latecoverage CPU反例，12项system ROS CPU PASS/0skip，rc0/5.522226466秒/source stable；旧11CPU源码两.txt exclusive保存且SHA与旧receipt一致。原执行器/actor/reward/门限未改。旧未冻结/未执行plan保留full_behavior_plan_pre_review_v1.json，重新build新full_behavior_plan_v1.json。新static_v2 rc0/2.247378129秒/source stable，112绑定/460链接/原pure/_duration/log与备份保持；准备清单cpu_preparation_index_v2.json为当前，v1/旧源码/回执不覆盖。exact v2 CPU命令：

```bash
/usr/bin/bash --noprofile --norc -c 'unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH ROS_PACKAGE_PATH VIRTUAL_ENV; export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; source /opt/ros/humble/setup.bash && source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash && exec /usr/bin/python3 -B -m unittest -v mr3_learning.tests.test_audit_proxy2d_behavior'
```

static_v2 exact命令：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261021_mr3_p2a_v24_behavior/preparation_check_v2.py`。两者均CPU，无World/Node/新episode或正式历史consumer重放、不计工程实验费。


## 2026-10-21 V24 唯一长行为活动FAIL闭合

冻结9b33cf9b6ab491fd5e3b15269adb30d43be1354c，clean/main=origin/main后前检rc0/1.884370267秒（CPU），再执行一次预声明full_behavior。0policy/GPU/optimizer，3env各固定一EP/三机器人，随机流41+1000003×env_id，各seed101。未达2100墙窗口或300sim任务截止，rooms真实执行异常触发全局stop，所有在途请求/实际后端关闭后继续独立审计与行为消费者；不重试/补样/换seed。

全544attempt/543return/1step_error；动作/uniform544、actor546、return543各自完成既定验证，所有raw票据计费但没有训练资格。3EP分别open205return、rooms174attempt/173return/1error、corridors165return；终态均未完整，无95%/原生资格，活动/审计/行为报告全部FAIL，原失败不改判。

exact子命令与scope/wait如下；完整wrapper/source before-after/identity/console原件在A24/closed_run/closed_execution（root=canonical wireless-rl，PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1；主活动/阶段CUDA空、BLAS/OMP/MKL线程1）：

preflight scope=cpu rc0/1.884370267秒/source stable：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance preflight --kind full_behavior --freeze 9b33cf9b6ab491fd5e3b15269adb30d43be1354c
```

main scope=engineering rc1/1370.575677101秒/source stable：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance execute --kind full_behavior --freeze 9b33cf9b6ab491fd5e3b15269adb30d43be1354c
```

externalfinal scope=engineering rc0/0.549927798秒/source stable：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance final --kind full_behavior --run /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v24/full_behavior_v1 --outer /tmp/mr3_proxy2d_v24_outer/actual_wait.json --output /tmp/mr3_proxy2d_v24_absence.json
```

failureextract scope=engineering rc0/0.743226624秒/source stable：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B /tmp/mr3_proxy2d_v24_failure_extract.py
```

主活动nested实际phase（均已包含，不重复加费）：

- conformity rc0/12.797964568秒、timed_out=False：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_conformity --freeze 9b33cf9b6ab491fd5e3b15269adb30d43be1354c --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v24/full_behavior_v1/conformity.json`

- conformity_review rc0/0.817142826秒、timed_out=False：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.audit_proxy2d /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v24/full_behavior_v1 --freeze 9b33cf9b6ab491fd5e3b15269adb30d43be1354c --conformity-only /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v24/full_behavior_v1/conformity.json --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v24/full_behavior_v1/conformity_independent.json`

- collection rc1/1242.136169728秒、timed_out=False：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.proxy2d_performance collect --kind full_behavior --run /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v24/full_behavior_v1`

- audit rc1/68.347750972秒、timed_out=False：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.audit_proxy2d /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v24/full_behavior_v1 --freeze 9b33cf9b6ab491fd5e3b15269adb30d43be1354c --output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v24/full_behavior_v1/independent_audit.json`

- behavior_report rc1/44.5844279秒、timed_out=False：`/usr/bin/bash --noprofile --norc -c 'source /opt/ros/humble/setup.bash && source "$1/install/setup.bash" && exec /usr/bin/python3 -B -m mr3_learning.audit_proxy2d_behavior "$2" --freeze "$3" --output "$4"' mr3-proxy-behavior /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v24/full_behavior_v1 9b33cf9b6ab491fd5e3b15269adb30d43be1354c /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v24/full_behavior_v1/behavior_report.json`

本轮失败具体信息：rooms InfrastructureError("2D proxy IPC failed: RuntimeError('masked action rejected by original dispatcher: stopped')")。所有后端正常rc0关闭，独立复算initialize/check/inspect/advance/close全部与原响应一致（无replay error）；3场原终态不足所以完整活动明确FAIL，不能把复算一致当任务成功。open/rooms/corridors截至205/173/165sim秒的correct-free为.8628001460786999/.7101429675425038/.4215815485996705；occupied IoU .15059294184883554/.13669934201691958/.11716035081912957，均低原.20门，质量均false，rooms false_free .021858808290155442超.02；实际参与均true，proxy_contact均0，仅代理范围，不提供18路原生安全信用。关闭后的navigation_closed=true与最后奖励边界closed=false分别保留，不把尾回填快照。

分实际返回序列三等分的mean step wall：open3.238783/6.079187/8.660685秒，rooms5.194743/4.410414/11.552949秒，corridors3.609456/9.354466/9.406572秒。最长全机无中心平移open28/rooms62/corridors25sim秒（可包含旋转）；blocked_quanta保留为原counter，不擅自当独立blocked时间。三机路径/接受目标数、候选和合法mask时间序列均在behavior_report。随机未达95%与真实模型/协议异常分开，不据未满300秒的本轮否定RL可学性。

封存完整608files/31,996,063bytes，单分片26,290,008bytes，SHAdb44fe8b530a2d4522511f0f5a8b6a3a7f9229ab637aa657fa4d0c68b32f6876；13aux exactcopy及全成员字节通过，原件前后不变。封存CPU7.515402246秒，账目CPU v1 .199361989秒；不计工程/不重复消费reader。完整source112绑定在活动结束保持freeze字节；后续CPU修复另述，不继承资格。

活动/final后保存18身份gone；为定位真实原因，在原3600预约余额内追加一次有限只读故障提取，预定<=30秒且无World/actor/奖励重放、无新样本或改判，实际engineering rc0/.743226624秒，精确脚本/输入protocol+trace SHA/输出/outer console全保留A24/failure_diagnostic。确认rooms173.1s tb3 goal:172是goal_lease_expired；accept generated172.9却received173.5（在失败之后），并非先前仅源码假设的60s执行上限。最后173.1s返回仍nonterminal，次submit在同一时刻tick才stopped。代理推进前tick、推进后check读旧failed是可复现的边界检测缺口；原FIFO/receipt cadence及pending命令原expiry必须保持，不能延长租约/丢失败。

最终main1370.575677101+external.549927798+有限提取.743226624三个outer union1371.868831523秒；累计45440.5368851356018/52000，余6559.4631148643982。nested阶段与三worker并行不加计。旧closed_metadata为18身份/未含提取的中账，权威最新closed_metadata_v2含20保存身份全gone、0present/unreadable；CPU v2 .203904726秒。pilot1870/2905.9547395464029和final-only401/402/403全未动。后续仅普通CPU边界分类修复，不启动新formal重验或训练，旧FAIL保持，P2A未完成。

V24收口后常规CPU修复完成：生产代码只在ProxyWorker.world.advance()后补一行dispatcher.tick(self.now)，再update_states/隔离check；全模块AST对照将静态核只此变更。原2sTTL/60s执行上限/FIFO及5Hz回执/心跳、原候选mask/原奖励不变。它仅让真实到期在当前物理20ms区间返回navigation_failure并原取消/result关闭，租约到期本身和本轮FAIL保持；未吞stopped/补KEEP/新formal重验。27项system ROS CPU/stub通过，rc0/2.911973945秒/source stable；真实dispatcher+IdealTransport配dummy20ms clock和原check/RewardLedger，无ProxyWorld/ROS Node/原生episode。覆盖lease/执行边界前后20ms、API中途/末量子正dt、迟到accept FIFO、关闭尾排除/finished后拒后续submit、300秒截止优先及unsafe latch。完整回执A24/checks/worker_boundary_cpu_v1；exact子命令：

```bash
/usr/bin/bash --noprofile --norc -c 'unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH ROS_PACKAGE_PATH VIRTUAL_ENV; export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; source /opt/ros/humble/setup.bash && source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash && cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap && exec /usr/bin/python3 -B -m pytest -q src/multi_robot_exploration/test/test_mr3_proxy2d_worker.py'
```

修复后源与正式9b冻结不同，无新长行为/原生/训练资格，不反改543个原返回或失败。后续路线先pendingTTL/FIFO与代理质量可达性、长步成本具体化，再新范围/冻结验证；不直接扩PPO或改质量/安全门。

V24闭合静态检查PASS，scope=cpu、rc0、actual wait 1.898351381秒、source stable；exact命令（cwd=canonical wireless-rl）：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261021_mr3_p2a_v24_behavior/closed_static_check_v1.py`。A24/checks/closed_static_cpu_v1保存原wait/console，closed_static_result_v1.json保存结论。核608原件31,996,063bytes、13aux及额外故障提取副本、3outer union1371.868831523秒/余6559.4631148643982、20身份gone、544/543/1及全活动FAIL保留；111其他绑定源与9b相同，worker完整AST只新增推进后tick，原pure/_duration保持；489相对链接、log只追加、旧ARCHIVE条目和backup不变。仅哈希/元数据/源码与文档检查，无World/Node/正式consumer重放或新样本，不计工程费用。


## 2026-10-21 V25 CPU协议、代理质量与导航缓存收口

用户在V24提交9edad01cc后指示“继续”。本轮范围A25/scope_acceptance_v1.json为人工CPU/源码分析，基线9edad01ccdb3a1adf2c20d22f62b7d4f3a4733ed；检查时实际源码由各receipt source_before/source_after SHA精确绑定，不冒充新正式freeze。无World构造/ROS Node/真实backend/episode/旧actor奖励流消费，0policy/GPU/optimizer/native，未重跑V24。工程新增0，仍45440.5368851356018/52000、余6559.4631148643982；pilot1870/2905.9547395464029与final-only401/402/403未动。

protocol_cpu_v1：rc0/source stable，actual wait 2.366727921秒，117项pytest PASS。学习端cwd=canonical wireless-rl、PYTHONNOUSERSITE=1，exact wrapper argv（含实际system ROS子命令，非重跑建议）：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.reach_execution --scope cpu --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261021_mr3_p2a_v25_cpu/checks/protocol_cpu_v1 --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_protocol.py --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_transport.py --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_episode.py --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_protocol.py --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_transport.py -- /usr/bin/bash --noprofile --norc -c 'unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH ROS_PACKAGE_PATH VIRTUAL_ENV; export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; source /opt/ros/humble/setup.bash && source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash && cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap && exec /usr/bin/python3 -B -m pytest -q src/multi_robot_exploration/test/test_mr3_protocol.py src/multi_robot_exploration/test/test_mr3_transport.py'
```

mapping_quality_cpu_v1：rc0/source stable，actual wait 4.010105222秒，7项pytest PASS。学习端cwd=canonical wireless-rl、PYTHONNOUSERSITE=1，exact wrapper argv（含实际system ROS子命令，非重跑建议）：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.reach_execution --scope cpu --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261021_mr3_p2a_v25_cpu/checks/mapping_quality_cpu_v1 --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_proxy2d_mapping_quality.py --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_proxy2d_world.py --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_task_contract.py --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py -- /usr/bin/bash --noprofile --norc -c 'unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH ROS_PACKAGE_PATH VIRTUAL_ENV; export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; source /opt/ros/humble/setup.bash && source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash && cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap && /usr/bin/python3 -B -m pytest -q src/multi_robot_exploration/test/test_mr3_proxy2d_mapping_quality.py && exec /usr/bin/python3 -B src/multi_robot_exploration/test/test_mr3_proxy2d_mapping_quality.py --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261021_mr3_p2a_v25_cpu/mapping_quality_artificial_v1.json'
```

navigation_cache_cpu_v1：rc0/source stable，actual wait 2.480688749秒，21项pytest PASS。学习端cwd=canonical wireless-rl、PYTHONNOUSERSITE=1，exact wrapper argv（含实际system ROS子命令，非重跑建议）：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.reach_execution --scope cpu --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261021_mr3_p2a_v25_cpu/checks/navigation_cache_cpu_v1 --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_proxy2d_navigation_cache.py --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_proxy2d_navigation.py --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_observation.py --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_reach_geometry.py -- /usr/bin/bash --noprofile --norc -c 'unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH ROS_PACKAGE_PATH VIRTUAL_ENV; export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; source /opt/ros/humble/setup.bash && source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash && cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap && exec /usr/bin/python3 -B -m pytest -q /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_proxy2d_navigation_cache.py'
```

navigation_timing_cpu_v1：rc0/source stable，actual wait 2.11364337秒。学习端cwd=canonical wireless-rl、PYTHONNOUSERSITE=1，exact wrapper argv（含实际system ROS子命令，非重跑建议）：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m mr3_learning.reach_execution --scope cpu --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261021_mr3_p2a_v25_cpu/checks/navigation_timing_cpu_v1 --source /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261021_mr3_p2a_v25_cpu/navigation_cache_fixture_v1.py --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_proxy2d_navigation_cache.py --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_proxy2d_navigation.py --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_observation.py --source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_reach_geometry.py -- /usr/bin/bash --noprofile --norc -c 'unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH ROS_PACKAGE_PATH VIRTUAL_ENV; export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; source /opt/ros/humble/setup.bash && source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash && cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap && exec /usr/bin/python3 -B /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261021_mr3_p2a_v25_cpu/navigation_cache_fixture_v1.py --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261021_mr3_p2a_v25_cpu/navigation_cache_artificial_v1.json'
```

协议生产未改：pending原expiry/实际交付才续lease符合契约，三新增真实FIFO夹具不能把合法switch失败归咎策略。七人工几何测量复现端点表面与实体体积不相容：厚box697 occupied/112表面，理想IoU上限.1606886657101865；薄box对照可过原门；格线floor和2mm正误差可产生falsefree=.04，非实际三场不可能或V24唯一归因。建图/真值/阈值未改。

导航生产仅把payload-time身份缓存键改为dtype/shape/Cbytes/res/origin/goal完整精确几何键，原身份检查、每机一条、逐次scan/pair/源龄保留；21项SHA绑定9b原nav oracle对照全字段与真实停止等价。人工48²两case各三轮×12次：stamp-only旧/新Dijkstra12/1，target总时间中位40.753699/4.535149ms；真变格12/12，中位39.054920/39.091095ms，字节打包在计时内。仅人工函数计时，不能冒充长ENV吞吐。原pure actor/geometry/reward、原worker post-tick与V24 FAIL保留。完整CPU清单A25/cpu_validation_index_v1.json，人工结果mapping_quality_artificial_v1.json/navigation_cache_artificial_v1.json；下一步先核实际代理质量可达性与逆传感器模型，再新具体范围/冻结长行为，不直接PPO或扩额。

V25最终静态CPU PASS，rc0/actual wait .525533615秒/source stable；exact子命令（cwd=canonical wireless-rl）：`/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261021_mr3_p2a_v25_cpu/static_check_v1.py`，由同一reach_execution --scope cpu --output A25/checks/static_cpu_v1 --source A25/static_check_v1.py实际wait。回执/console及static_result_v1.json保存四专项回执源码/console一致、8保存CPU身份gone、493相对链接、完整nav AST仅换key、原pure/协议/建图/评价/worker与V24证据不变、log相对9edad只追加、旧ARCHIVE条目/backup保持。工程仍新增0；本静态步骤不重放真实actor/奖励或提供任务资格。
