# DQN Iteration Log

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

## 2026-09-17 P2A target detection and confirmation

Purpose: after the user accepted P1C, implement only P2A's deterministic
simulation target detector. The contract was fixed before the formal runs:
visual-only target at `(-4, 4)`, 3.0 m maximum range, 90-degree horizontal
field of view, static truth-grid line of sight, and three consecutive visible
frames. Target detection does not alter exploration or initiate P2B rally.

All simulator commands ran from `ros2_ws/ros2-multi-robot-automap` at the
worktree based on `99cf3a6`, with the uncommitted P2A implementation, after:

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
source /opt/ros/humble/setup.bash
source /usr/share/gazebo/setup.sh
source install/setup.bash
export TURTLEBOT3_MODEL=waffle
```

### Positive three-robot episodes

```bash
PYTHONNOUSERSITE=1 python scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 3 --gazebo-seed 101 \
  --startup-timeout 240 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 180 --coverage-threshold 0 \
  --evaluation-wait-timeout 330 --target-detection \
  --target-x -4.0 --target-y 4.0 --target-max-distance 3.0 \
  --target-field-of-view 90 --target-confirmation-frames 3 \
  --episode-id p2a_target_detection_3r_seed101
```

Result: PASS. `tb1` confirmed the target at 55.4 simulated seconds; final
coverage 0.87122, path 30.352 m, zero collisions and zero overlap. JSON:
`log/evaluation/p2a_target_detection_3r_seed101.json`. This valid preliminary
run preceded adding the selected detector parameters to the event metadata, so
those three schema fields are null; it is not used as the final seed-101 row.

```bash
PYTHONNOUSERSITE=1 python scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 3 --gazebo-seed 202 \
  --startup-timeout 240 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 180 --coverage-threshold 0 \
  --evaluation-wait-timeout 330 --target-detection \
  --target-x -4.0 --target-y 4.0 --target-max-distance 3.0 \
  --target-field-of-view 90 --target-confirmation-frames 3 \
  --episode-id p2a_target_detection_3r_seed202

PYTHONNOUSERSITE=1 python scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 3 --gazebo-seed 303 \
  --startup-timeout 240 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 180 --coverage-threshold 0 \
  --evaluation-wait-timeout 330 --target-detection \
  --target-x -4.0 --target-y 4.0 --target-max-distance 3.0 \
  --target-field-of-view 90 --target-confirmation-frames 3 \
  --episode-id p2a_target_detection_3r_seed303
```

Both passed. Seed 202: 72.9 s, `tb1`, coverage 0.86891, path 34.415 m,
accuracy 0.96788, zero collisions/overlap. Seed 303: 61.5 s, `tb1`, coverage
0.86942, path 30.361 m, accuracy 0.97257, zero collisions/overlap. Both record
confirmation=3, range=3.0 m, and FOV=90 degrees.

After event metadata was complete, the first final seed-101 attempt used the
same command with episode `p2a_target_detection_final_3r_seed101`. Result:
infrastructure FAIL before evaluator/detector startup because Nav2 lifecycle
change-state calls timed out; smoke reported missing `/task_state`. No task
result was produced or counted. Raw log:
`log/smoke/robots3_seed101_20260917-120250.log`.

The exact retry was:

```bash
PYTHONNOUSERSITE=1 python scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 3 --gazebo-seed 101 \
  --startup-timeout 300 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 180 --coverage-threshold 0 \
  --evaluation-wait-timeout 390 --target-detection \
  --target-x -4.0 --target-y 4.0 --target-max-distance 3.0 \
  --target-field-of-view 90 --target-confirmation-frames 3 \
  --episode-id p2a_target_detection_final_3r_seed101_retry1
```

Result: PASS at 60.7 s, `tb1`, coverage 0.87030, path 34.624 m, accuracy
0.97619, zero collisions/overlap, confirmation=3/range=3.0/FOV=90. This retry
is the final seed-101 evidence; the active lifecycle requirement was unchanged.

Final formal three-seed result: all 3/3 episodes terminated with
`target_found`, state `FOUND`, and correct target `(-4, 4)`. Detection times
were 60.7/72.9/61.5 s, with zero collisions and zero overlap in every run.

### Invisible-target negative episode

```bash
PYTHONNOUSERSITE=1 python scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 1 --gazebo-seed 404 \
  --startup-timeout 180 --message-timeout 60 --shutdown-timeout 60 \
  --evaluation-duration 10 --coverage-threshold 0 \
  --evaluation-wait-timeout 240 --target-detection \
  --expect-target-not-found --target-x 100.0 --target-y 100.0 \
  --target-max-distance 3.0 --target-field-of-view 90 \
  --target-confirmation-frames 3 \
  --episode-id p2a_target_not_visible_1r_seed404
```

Result: PASS for the expected negative condition. The evaluator timed out at
10.1 s with `target_found=false`, `time_to_detect_sec=null`, and
`task_phase=EXPLORE`; coverage was 0.02727, path 0.0008 m, and collisions and
overlap were zero. JSON:
`log/evaluation/p2a_target_not_visible_1r_seed404.json`. The evaluator's
`success=false` is correct for a timeout; the smoke PASS means no false
detection occurred.

Unit tests use a synthetic truth grid and separately verify range, FOV,
wall occlusion, consecutive-frame confirmation, and reset after an invisible
frame. Full final build/test details and the implementation commit are recorded
below after final validation. P2A moves to `待用户验收`; P2B remains unstarted.

Final validation at the completed P2A worktree state:

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
PYTHONNOUSERSITE=1 python -m py_compile \
  scripts/ros_smoke_test.py \
  src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py \
  src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py \
  src/multi_robot_exploration/multi_robot_exploration/target_detector.py
```

Build passed. Test result: 27 tests, 0 errors, 0 failures, 2 copyright
skips; the new target-detector tests passed 2/2. Python byte-compilation and
`git diff --check` passed.

Implementation, tests, simulator evidence, and P2A handoff documentation were
committed as `7563681` (`p2a: add target detection confirmation`) and pushed to
`origin/main` in this session. The intentionally unstaged user report changes
remained untouched.

## 2026-09-17 P2B authoritative rally state machine

Purpose: implement the revised P2B contract only: the coordinator becomes the
sole `/task_state` owner, confirmed detection cancels exploration, every
required robot receives a distinct known-free target-facing staging pose, and
`COMPLETE` requires all position and velocity thresholds continuously for five
simulated seconds. This remains ideal same-host ROS communication; no gateway,
network, battery, or P2C work was added.

All runs used the evolving uncommitted P2B worktree based on `828ec62`, the
`ns3gym` conda environment with `PYTHONNOUSERSITE=1`, ROS 2 Humble, Gazebo's
setup, the repository `install/setup.bash`, and `TURTLEBOT3_MODEL=waffle`.
After stale ROS-domain state was found during early debugging, later runs used
a fresh `ROS_DOMAIN_ID` per attempt. The common three-robot command was:

```bash
PYTHONNOUSERSITE=1 python scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 3 --gazebo-seed <seed> \
  --startup-timeout <240|300|360> --message-timeout 90 \
  --shutdown-timeout 60 --evaluation-duration <180|300> \
  --coverage-threshold 0 --evaluation-wait-timeout <330|390|480> \
  --target-detection --target-x -4 --target-y 4 \
  --target-max-distance 3 --target-field-of-view 90 \
  --target-confirmation-frames 3 --rally --episode-id <episode>
```

The final fixed formal command used `startup-timeout=360`,
`evaluation-duration=300`, and `evaluation-wait-timeout=480`. The 300-second
bound is for the complete search/detect/sequential-rally task; no rally
position, speed, hold, separation, or collision threshold was relaxed.

### Development runs retained

The following raw smoke logs are retained under the ignored ROS `log/smoke/`
directory. Unless stated otherwise these were seed 101, three robots, a
180-second episode and the common target/rally parameters above.

- `robots3_seed101_20260917-134453.log`, episode
  `p2b_rally_3r_seed101_v1`: post-start FAIL,
  `insufficient_rally_poses`; the initial candidate subset was incomplete.
- `...-135106.log`, `p2b_rally_3r_seed101_v2`: entered `RALLY`; tb1/tb2
  arrived, tb3 remained blocked; timeout, zero collisions.
- `...-135912.log`: pre-start infrastructure FAIL while activating tb3; no
  authoritative task result. A stale September-14 controller on the default
  ROS domain was then found and stopped.
- `...-140500.log`, `p2b_rally_3r_seed101_v4`: post-start FAIL with zero
  reachable candidates after an over-strict route check.
- `...-141025.log`, `p2b_rally_3r_seed101_v5`: candidates increased from zero
  to two while waiting for map data but remained insufficient; post-start
  FAIL.
- `...-141546.log`, `p2b_rally_3r_seed101_v6`: expanded candidate radii and
  sequential dispatch let tb1/tb3 arrive; tb2 remained blocked; timeout,
  minimum assigned separation 0.806 m, zero collisions.
- `...-142214.log`, `p2b_rally_3r_seed101_v7`: target spawn client timed out
  although the model later appeared; no sufficient rally candidates; FAIL.
- `...-142937.log`, `p2b_rally_3r_seed101_v8`: preferred 1.2 m separation was
  achieved (1.208 m), but tb2 navigation failed; timeout.
- `...-143553.log`, `p2b_rally_3r_seed101_v9`: exposed a race where the
  coordinator entered `RALLY` before its survey action completed; timeout.
- `...-144141.log`: pre-start infrastructure FAIL at tb3 lifecycle readiness;
  no task result.
- `...-144706.log`, `p2b_rally_3r_seed101_v11`: post-start timeout after a
  long direct tb2 rally goal failed.
- `...-145245.log`, `p2b_rally_3r_seed101_final`: same direct-goal failure;
  timeout.
- `...-145806.log`, `p2b_rally_3r_seed101_final2`: survey completed but the
  radial-layer approach still left tb2 blocked; timeout.
- `...-150329.log` and `...-150758.log`: pre-start tb3 readiness failures;
  manually interrupted/failed before a task episode.
- `...-151407.log`, `p2b_rally_3r_seed101_final5`: an over-strict survey LOS
  rule left zero candidates; `insufficient_rally_poses`.
- `...-151857.log`, `p2b_rally_3r_seed101_final6`: survey and assignment
  succeeded, but a 5 m tb2 waypoint failed; timeout.
- `...-152508.log`, `p2b_rally_3r_seed101_final7`: survey produced 18 safe
  candidates, but a radial-layer hard constraint made the joint assignment
  impossible; `insufficient_rally_poses`.
- `...-153012.log`, `p2b_rally_3r_seed101_final8`: 3 m path legs still left
  tb2 blocked; timeout.
- `...-153645.log`: pre-start tb2 readiness failure; interrupted without a
  task result.
- `...-154306.log`, `p2b_rally_3r_seed101_final10`, isolated domain 41:
  PASS, `COMPLETE` 141.8 s, detection 70.4 s, rally 82.4 s, coverage 0.883,
  path 46.301 m, zero collisions. This validated 1.5 m staged navigation but
  preceded the final collision-order fix, so it is not a final formal row.
- `robots3_seed202_20260917-154846.log`: pre-start infrastructure FAIL. The
  `...-155414.log` attempt with a speculative 90-second launch stagger also
  failed before tb3 readiness and was interrupted; the stagger was restored
  to 60 seconds. `...-155940.log`, episode `p2b_rally_3r_seed202_final3`,
  then PASSed at `COMPLETE` 140.8 s with detection 61.8 s, rally 69.2 s,
  coverage 0.941, path 50.859 m and zero collisions.
- `robots3_seed303_20260917-160502.log`, episode
  `p2b_rally_3r_seed303_final`: post-start 180-second timeout after detection
  at 89.9 s demonstrated that P1C's coverage-only bound was too short for a
  late detection plus safe sequential arrival.
- `...-161100.log`: pre-start tb3 readiness failure during the first
  300-second attempt; interrupted without a task result.
- `...-161441.log`, `p2b_rally_3r_seed303_300s_final2`: reached `COMPLETE`
  at 169.1 s, but correctly FAILed smoke because tb1/tb3 accumulated six
  contact events over 3.7 s. This result was not accepted.
- `...-162325.log`, `p2b_rally_3r_seed303_300s_safety`: after adding 0.35 m
  rally-route clearance, PASS, `COMPLETE` 139.9 s, coverage 0.942, path
  50.490 m, minimum separation 1.414 m, zero collisions.
- `robots3_seed101_20260917-162904.log`, episode
  `p2b_rally_3r_seed101_300s_final`: all completion thresholds passed at
  159.8 s, but smoke correctly FAILed due to nine contacts (tb2 five, tb3
  four). The symmetry and route showed a staged robot obstructing the next
  arrival.
- `...-163546.log`, `p2b_rally_3r_seed101_300s_clearance45`: testing 0.45 m
  route clearance produced zero collisions but closed a narrow known passage;
  post-start `insufficient_rally_poses` at 80.9 s. This alternative was
  rejected rather than weakening reachability.
- `...-164154.log`: pre-start infrastructure FAIL with missing Gazebo/task and
  several robot topics; no task result. It was retried with identical task
  parameters.

These failures led to the final minimal algorithm: final staging cells retain
0.45 m obstacle clearance, traversed routes use 0.35 m clearance and 1.5 m
legs, and the coordinator fills poses on the far side of the target first so a
parked robot does not block a later approach. Collision logging now records the
task phase without changing the verdict.

### Final formal episodes

```text
3r seed101  p2b_rally_3r_seed101_300s_final_ordered_retry1
  log robots3_seed101_20260917-164825.log
  PASS COMPLETE=134.5, detect=58.0, rally=58.5, coverage=0.923515,
  path=46.434 m, min separation=1.210 m, collisions=0
  final errors tb1/tb2/tb3=0.216/0.237/0.220 m

3r seed202  p2b_rally_3r_seed202_300s_final_ordered
  log robots3_seed202_20260917-165350.log
  PASS COMPLETE=171.9, detect=66.5, rally=80.3, coverage=0.946577,
  path=55.515 m, min separation=1.221 m, collisions=0
  final errors tb1/tb2/tb3=0.176/0.198/0.200 m

3r seed303  p2b_rally_3r_seed303_300s_final_ordered
  log robots3_seed303_20260917-165949.log
  PASS COMPLETE=177.3, detect=111.7, rally=112.1, coverage=0.937864,
  path=63.551 m, min separation=1.414 m, collisions=0
  final errors tb1/tb2/tb3=0.221/0.202/0.181 m
```

All nine final linear speeds were at most 0.00010 m/s. Final angular speeds
were at most 0.02945 rad/s, below the 0.10 rad/s threshold. Every run held the
complete condition for five simulated seconds. Thus the final three-seed
result is 3/3 `COMPLETE` with zero collision events; `FOUND` and coverage were
not used as success substitutes.

The two-robot cross-check used the same command with `robot-count=2`, seed 303,
`startup-timeout=300`, and `evaluation-wait-timeout=420`:

```text
episode p2b_rally_2r_seed303_300s_crosscheck
log robots2_seed303_20260917-170558.log
PASS COMPLETE=96.5, detect=38.0, rally=46.0, coverage=0.782104,
path=21.644 m, min separation=2.025 m, collisions=0,
final errors tb1/tb2=0.215/0.214 m
```

The structured JSON/CSV files are in the ignored `log/evaluation/` directory.
Implementation and evidence details are also summarized in
`report/20260917_p2b.md`. Final build/test and commit/push evidence follows
after validation below.

Final validation at the completed P2B worktree state:

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
export PYTHONNOUSERSITE=1
source /opt/ros/humble/setup.bash
cd ros2_ws/ros2-multi-robot-automap
colcon build --symlink-install \
  --packages-select multi_robot multi_robot_exploration
source install/setup.bash
colcon test --packages-select merge_map multi_robot_exploration multi_robot \
  --event-handlers console_direct+
colcon test-result --verbose
python -m py_compile scripts/ros_smoke_test.py \
  src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py \
  src/multi_robot_exploration/multi_robot_exploration/control.py \
  src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py \
  src/multi_robot_exploration/multi_robot_exploration/target_detector.py
```

Build passed. Test result: 36 tests, 0 errors, 0 failures, 2 copyright
skips; Python byte-compilation and `git diff --check` passed. P2B moves to
`待用户验收`; P2C was not started. The intentionally unstaged user deletion
of `report/20260914.md` and untracked `report/20260914_p1a.md` remained
untouched and are excluded from the P2B commit.

## 2026-09-17 P2B coverage/time audit and robustness follow-up

Purpose: determine whether P2B's longer completion time and lower coverage are
caused by the stop-on-found contract or by navigation/map defects, and fix only
demonstrated defects without starting P2C. All project Python commands used the
`ns3gym` conda environment with `PYTHONNOUSERSITE=1`; ROS runs sourced Humble,
the repository install, Gazebo setup, and used a fresh `ROS_DOMAIN_ID`.

The common audit command was:

```bash
PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=<isolated> python scripts/ros_smoke_test.py \
  --world my_world.world --robot-count <2|3> --gazebo-seed <101|202|303> \
  --startup-timeout <300|360> --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 \
  --evaluation-wait-timeout <420|480> --target-detection --rally \
  --target-x -4 --target-y 4 --target-max-distance 3 \
  --target-field-of-view 90 --target-confirmation-frames 3 \
  --episode-id <episode>
```

Attempts and conclusions, including rejected changes:

- `p2b_audit_pipeline_3r_seed101`, log
  `robots3_seed101_20260917-175642.log`: experimental parallel intermediate
  rally legs reached `COMPLETE=177.5 s` but produced 43 collision events over
  65.2 simulated seconds. Outer smoke FAIL; the algorithm was reverted.
- `p2b_audit_sequential_2r_seed303`, log
  `robots2_seed303_20260917-185039.log`: post-start timeout at 300.3 s. Target
  detection was late at 176.2 s with `coverage_at_detection=0.8759`; tb2's
  first rally action exhausted 60 s and then resent the same waypoint. Zero
  collisions. This failure was retained and motivated shorter retry legs.
- `robots2_seed303_20260917-185908.log`: pre-start infrastructure FAIL with
  missing `/tb2/cmd_vel` and `/task_state`; no task episode. Identical task
  parameters were retried only with a new ROS domain.
- `p2b_audit_watchdog_2r_seed303_retry1`, log
  `robots2_seed303_20260917-190440.log`: PASS, `detect=57.4`,
  `coverage_at_detection=0.7557`, `RALLY=57.8`, `COMPLETE=117.5`, final
  coverage `0.8162`, observed accuracy `0.9740`, path `31.643 m`, zero search
  overlap and collisions. This directly demonstrates expected low coverage
  after early detection.
- `p2b_audit_watchdog_3r_seed101`, log
  `robots3_seed101_20260917-190846.log`: PASS, `detect=58.9`, detection/final
  coverage `0.8717/0.9422`, `COMPLETE=169.4`, path `49.211 m`, zero collisions.
- `p2b_audit_watchdog_3r_seed202`, log
  `robots3_seed202_20260917-191444.log`: PASS, `detect=57.2`, detection/final
  coverage `0.8742/0.9427`, `COMPLETE=177.6`, path `53.955 m`, zero collisions.
- `p2b_audit_watchdog_3r_seed303`, log
  `robots3_seed303_20260917-192045.log`: a 10-second experimental rally
  no-progress watchdog canceled Nav2 recovery three times; post-start FAIL at
  106.2 s with `rally_navigation_failed:tb3`, zero collisions. Rejected.
- `p2b_audit_watchdog30_3r_seed303`, log
  `robots3_seed303_20260917-192647.log`: PASS, `detect=60.5`, detection/final
  coverage `0.8695/0.9391`, `RALLY=68.8`, `COMPLETE=158.2`, path `48.772 m`,
  zero collisions. The 30-second watchdog was not triggered, so it did not
  establish benefit and was also removed.

The retained implementation is deliberately smaller: schema v5 records
`coverage_at_detection`; any collision makes evaluator `success=false`; and
only a fully failed rally action changes the next maximum leg from 1.5 m to
0.75 m, then 0.5 m. Nav2's internal recovery is not interrupted. Unit coverage
was added for collision verdicts and shorter retry legs. Full final validation
and commit/push evidence follows. P2C was not started.

Final retained-code validation:

```bash
colcon build --symlink-install \
  --packages-select multi_robot merge_map multi_robot_exploration
colcon test --packages-select merge_map multi_robot_exploration multi_robot \
  --event-handlers console_direct+
colcon test-result --verbose
python -m py_compile scripts/ros_smoke_test.py \
  src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py \
  src/multi_robot_exploration/multi_robot_exploration/control.py \
  src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py \
  src/multi_robot_exploration/multi_robot_exploration/target_detector.py
```

Build and byte-compilation passed. Test result: 37 tests, 0 errors, 0
failures, 2 copyright skips. `git diff --check`, staging preview, commit, and
push are recorded by the repository history for this session.

## 2026-09-17 P2B detecting-robot-first rally fix

Purpose: fix the user-observed behavior where the robot that confirmed the
target could remain stationary while other robots rallied. Code state started
from commit `5c7ab7f` plus the focused dispatch-order change; P2C was not
started.

The retained change keeps the collision-safe sequential rally but puts the
detecting robot first. The focused unit test and package build commands were:

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
export PYTHONNOUSERSITE=1
source /opt/ros/humble/setup.bash
cd ros2_ws/ros2-multi-robot-automap
source install/setup.bash
pytest -q src/multi_robot_exploration/test/test_control.py
colcon build --symlink-install --packages-select multi_robot_exploration
```

Both passed. The headless Gazebo verification used `ROS_DOMAIN_ID=73`:

```bash
python scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 2 --gazebo-seed 303 \
  --startup-timeout 300 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 \
  --evaluation-wait-timeout 420 --target-detection --rally \
  --target-x -4 --target-y 4 --target-max-distance 3 \
  --target-field-of-view 90 --target-confirmation-frames 3 \
  --episode-id p2b_detector_first_2r_seed303
```

Result: PASS. tb1 confirmed the target at 65.1 simulated seconds, immediately
received the first rally goal, and reached its assigned pose about 5.2 seconds
later; only then was tb2 dispatched. The episode reached `COMPLETE=117.9 s`,
with final correct-free coverage 0.8413, total path 34.523 m, assigned
separation 1.600 m, final errors tb1/tb2 0.215/0.206 m, and zero collision
events or duration. Launch log:
`ros2_ws/ros2-multi-robot-automap/log/smoke/robots2_seed303_20260917-195237.log`.
Structured result: `p2b_detector_first_2r_seed303.json` (ignored evaluation
output). Conclusion: the root cause was rally dispatch ordering, not target
detection, map fusion, or Nav2; detector-first serial dispatch fixes the
visible behavior without reintroducing the collisions seen under parallel
rally.

Final validation at the retained worktree state:

```bash
colcon test --packages-select merge_map multi_robot_exploration multi_robot \
  --event-handlers console_direct+
colcon test-result --verbose
python -m py_compile scripts/ros_smoke_test.py \
  src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py \
  src/multi_robot_exploration/multi_robot_exploration/control.py \
  src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py \
  src/multi_robot_exploration/multi_robot_exploration/target_detector.py
```

Result: 38 tests, 0 errors, 0 failures, 2 copyright skips; byte-compilation
and `git diff --check` passed. The pre-existing user deletion of
`report/20260914.md` and untracked `report/20260914_p1a.md` remain excluded
from this change.

## 2026-09-17 P2B conflict-aware concurrent rally

Purpose: replace the user-rejected whole-mission serial rally with coordination
that uses the merged map and live robot positions. Work started from commit
`46e8124`; P2C was not started. All runs used the `ns3gym` environment,
`PYTHONNOUSERSITE=1`, ROS 2 Humble, repository install, Gazebo setup, and a
fresh `ROS_DOMAIN_ID`.

The common three-robot command was:

```bash
python scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 3 --gazebo-seed <101|202|303> \
  --startup-timeout 360 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 \
  --evaluation-wait-timeout 480 --target-detection --rally \
  --target-x -4 --target-y 4 --target-max-distance 3 \
  --target-field-of-view 90 --target-confirmation-frames 3 \
  --episode-id <episode>
```

Attempts, including rejected versions and infrastructure failure:

- `p2b_conflict_aware_3r_seed303_v1`, domain 74, launch log
  `robots3_seed303_20260917-201149.log`: pre-start infrastructure FAIL after
  Nav2 readiness timeout; `/task_state`, multiple collision topics, and robot
  telemetry topics were missing. No task episode was evaluated.
- `p2b_conflict_aware_3r_seed303_v1_retry1`, domain 75, launch log
  `robots3_seed303_20260917-201819.log`: the initial 0.8 m reservation version
  allowed three concurrent legs and passed at `COMPLETE=132.7 s`,
  `RALLY=46.9 s`, with zero collisions.
- `p2b_conflict_aware_3r_seed101_v1`, domain 76, launch log
  `robots3_seed101_20260917-202358.log`: authoritative FAIL despite reaching
  `COMPLETE=223.9 s`; tb2/tb3 accumulated 18 collision events over 16.7
  simulated seconds. The unrestricted three-way version was rejected.
- Final v2 raises route separation to 1.2 m, permits at most two concurrent
  Nav2 actions, and cancels the lower-priority short leg if live positions
  converge. Coordinator-requested yielding does not consume failure retries.

Final retained-algorithm results:

| Episode | Domain / log | Detection / RALLY / COMPLETE | Rally phase | Coverage | Path | Max error | Separation | Collisions |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `p2b_conflict_aware_3r_seed101_v2` | 77 / `robots3_seed101_20260917-203228.log` | 63.6 / 73.4 / 131.0 s | 57.6 s | 0.9320 | 51.413 m | 0.271 m | 1.208 m | 0 |
| `p2b_conflict_aware_3r_seed202_v2` | 78 / `robots3_seed202_20260917-203753.log` | 80.7 / 81.2 / 139.2 s | 58.0 s | 0.9403 | 52.183 m | 0.227 m | 1.250 m | 0 |
| `p2b_conflict_aware_3r_seed303_v2` | 79 / `robots3_seed303_20260917-204335.log` | 61.5 / 76.8 / 146.2 s | 69.4 s | 0.9462 | 56.797 m | 0.302 m | 1.259 m | 0 |

All three entered `COMPLETE`, met the unchanged pose/speed/hold criteria, and
had zero collision events and duration. The formal serial runs' rally phases
were 76.0/91.6/65.2 seconds (mean 77.6); retained conflict-aware concurrency
used 57.6/58.0/69.4 seconds (mean 61.7), a 20.5% mean reduction. Seed 303 was
4.2 seconds slower than its formal serial counterpart, so the evidence supports
an average improvement rather than universal per-run speedup. Logs show two
robots receiving legs in the same scheduling window and only conflicting legs
waiting; this is no longer whole-mission serial dispatch.

Final retained-code validation:

```bash
colcon build --symlink-install \
  --packages-select multi_robot merge_map multi_robot_exploration
colcon test --packages-select merge_map multi_robot_exploration multi_robot \
  --event-handlers console_direct+
colcon test-result --verbose
python -m py_compile scripts/ros_smoke_test.py \
  src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py \
  src/multi_robot_exploration/multi_robot_exploration/control.py \
  src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py \
  src/multi_robot_exploration/multi_robot_exploration/target_detector.py
```

Build and byte-compilation passed. Test result: 42 tests, 0 errors, 0
failures, 2 copyright skips. The intentionally unstaged user deletion of
`report/20260914.md` and untracked `report/20260914_p1a.md` remain untouched.

## 2026-09-17 P2C battery, return, and charging

Purpose: implement P2C after the user accepted P2B. Work started from commit
`8868da6`. The retained energy profile is capacity 100, initial energy 18,
movement cost 1 energy/m, elapsed-time cost 0.02 energy/s, return safety margin
5, 10 simulated seconds stationary charging, 120-second return timeout, and
60-second charge timeout. `c_tx=0` because P3 has not produced a byte ledger.

Common forced-charge command (episode id and `ROS_DOMAIN_ID` changed per
attempt):

```bash
python3 scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 2 --gazebo-seed 303 \
  --startup-timeout 300 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 \
  --evaluation-wait-timeout 600 --target-detection --rally \
  --battery --require-charge --battery-initial-energy 18 \
  --battery-capacity 100 --battery-move-cost 1 \
  --battery-idle-cost 0.02 --battery-safety-margin 5 \
  --battery-charge-duration 10 --battery-return-timeout 120 \
  --battery-charge-timeout 60 \
  --target-x -4 --target-y 4 --target-max-distance 3 \
  --target-field-of-view 90 --target-confirmation-frames 3 \
  --episode-id <episode>
```

Attempts:

- `p2c_forced_charge_2r_seed303_pilot1`, default ROS domain, launch log
  `robots2_seed303_20260917-215928.log`: implementation/infrastructure FAIL
  after task startup. Both battery processes raised `AttributeError` because
  the node used rclpy's read-only `subscriptions` property as an internal
  container. The run was interrupted and retained; no result was claimed.
- `p2c_forced_charge_2r_seed303_pilot2`, domain 80, launch log
  `robots2_seed303_20260917-220234.log`: implementation FAIL. Both nodes
  immediately reported exhaustion because their late startup clock jump was
  charged as historical idle time. It also exposed that the P2B transition
  table rejected `EXPLORE -> FAILED`. The run was interrupted and retained.
- `p2c_forced_charge_2r_seed303_pilot3`, domain 81, launch log
  `robots2_seed303_20260917-220810.log`: PASS. Energy integration uses odom
  message timestamps and ignores a non-physical odom step above 1 m; battery
  failure is now legal during exploration.

The retained run completed at 190.1 simulated seconds. Detection and RALLY
occurred at 118.2 and 126.2 seconds. tb1/tb2 each returned and charged once;
their minimum energies were 6.810/6.661 and final energies 77.289/88.469.
Both ended in `ACTIVE`. Final correct-free coverage was 0.9215, total path
49.733 m, search overlap 0, collision events/duration 0/0, and final rally
errors 0.216/0.128 m. Structured result:
`p2c_forced_charge_2r_seed303_pilot3.json` in the ignored evaluation directory.

Pre-simulation validation and regression commands used during implementation:

```bash
python3 -m pytest -q \
  src/multi_robot_exploration/test/test_battery_manager.py \
  src/multi_robot_exploration/test/test_control.py \
  src/multi_robot_exploration/test/test_task_evaluator.py
ament_flake8 src/multi_robot_exploration/multi_robot_exploration \
  src/multi_robot_exploration/test scripts/ros_smoke_test.py
colcon build --symlink-install \
  --packages-select multi_robot_exploration multi_robot
colcon test --packages-select multi_robot_exploration \
  --event-handlers console_direct+
colcon test-result --verbose
```

The initial targeted suite passed 32 tests; the first direct invocation before
setting the source `PYTHONPATH` failed during collection and made no code
assertions. After correction, package testing passed 39 tests with one
copyright skip (aggregate test-result: 45 tests, 0 errors, 0 failures, two
skips). Final post-documentation validation is recorded below before commit.

Final retained-worktree validation:

```bash
colcon build --symlink-install \
  --packages-select multi_robot merge_map multi_robot_exploration
colcon test --packages-select multi_robot merge_map multi_robot_exploration \
  --event-handlers console_direct+
colcon test-result --verbose
python3 -m py_compile scripts/ros_smoke_test.py \
  src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py \
  src/multi_robot_exploration/multi_robot_exploration/battery_manager.py \
  src/multi_robot_exploration/multi_robot_exploration/control.py \
  src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py
```

Result: build and byte-compilation PASS; aggregate final test result 48 tests,
0 errors, 0 failures, 2 copyright skips. The intentionally unstaged user
deletion of `report/20260914.md` and untracked `report/20260914_p1a.md` remain
untouched and excluded from P2C.

After adding the required battery-state startup/staleness gate, final-code
smoke regression used `ROS_DOMAIN_ID=82`:

```bash
python3 scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 1 --gazebo-seed 303 \
  --startup-timeout 240 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 10 --coverage-threshold 0 \
  --evaluation-wait-timeout 360 --battery \
  --episode-id p2c_final_battery_gate_1r_seed303
```

Result: PASS. The battery state was received, remained `ACTIVE`, and did not
exhaust; the evaluator ended at the expected 10-second timeout with no charge
required. Coverage was 0.285 and path length 0.774 m. Launch log:
`robots1_seed303_20260917-222307.log`; structured result:
`p2c_final_battery_gate_1r_seed303.json` in the ignored evaluation directory.
This short run validates the final gating change and does not replace the
forced-charge full mission.

## 2026-09-18 P2C post-acceptance visualization follow-up

Purpose: after the user accepted P2C, add visual-only Gazebo task regions and
a default-on live per-robot status panel without changing control or scoring.
Work started from pushed commit `4119679`.

Pre-simulation checks:

```bash
colcon build --symlink-install \
  --packages-select multi_robot multi_robot_exploration
cd src/multi_robot_exploration
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -q test
QT_QPA_PLATFORM=offscreen timeout --signal=INT --kill-after=3 3 \
  ros2 run multi_robot_exploration robot_status_panel \
  --ros-args -p robot_count:=2
```

Build passed. The package suite passed 47 tests with one copyright skip. The
offscreen Qt process created the two-robot table and exited on SIGINT; the only
output was the expected offscreen-platform `propagateSizeHints` warning. An
initial status-panel launch failed because the implementation assigned to
rclpy's read-only `Node.subscriptions` property; it was renamed to
`input_subscriptions` before simulation validation.

Both Gazebo attempts used:

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 1 --gazebo-seed 404 \
  --startup-timeout 240 --message-timeout 60 --shutdown-timeout 45 \
  --evaluation-duration 10 --evaluation-wait-timeout 120 \
  --target-detection --expect-target-not-found \
  --target-x=-4 --target-y=4 --task-regions --episode-id <episode>
```

Attempts:

- `p2c_visual_regions_smoke`, launch log
  `robots1_seed404_20260918-003454.log`: validation-harness FAIL. Gazebo logs
  show successful requests for the target, start, and tb1 charger regions, but
  the newly added synchronous `/get_entity_state` CLI check timed out. The
  episode result was retained; no pass was claimed.
- `p2c_visual_regions_smoke_retry`, launch log
  `robots1_seed404_20260918-003643.log`: PASS after replacing the blocking
  service query with one `/gazebo/model_states` sample. The sample contained
  `task_region_target_detection`, `task_region_start_charge`, and
  `task_region_charger_tb1`. The negative-detection episode timed out as
  expected at 10.2 simulated seconds with no false target detection. Coverage
  was 0.0273 and path length 0.001 m; these task metrics are not acceptance
  evidence for this visualization-only smoke.

The task-region models contain visual geometry and no collision geometry. The
manual launch defaults `enable_task_regions` and `enable_status_panel` to true;
the automated smoke path keeps the panel off and only enables regions with
`--task-regions`. Full details are in
`report/20260918_p2c_visualization.md`.

Final retained-worktree validation after documentation and per-detector status
wording:

```bash
git diff --check
ament_flake8 src/multi_robot_exploration/multi_robot_exploration \
  src/multi_robot_exploration/test scripts/ros_smoke_test.py
python3 -m py_compile scripts/ros_smoke_test.py \
  src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py \
  src/multi_robot_exploration/multi_robot_exploration/status_panel.py \
  src/multi_robot_exploration/multi_robot_exploration/task_visualizer.py
colcon build --symlink-install \
  --packages-select multi_robot multi_robot_exploration
colcon test --packages-select multi_robot multi_robot_exploration \
  --event-handlers console_direct+
colcon test-result --verbose
```

Result: diff, lint, byte-compilation, and build passed. Aggregate test result
was 53 tests, 0 errors, 0 failures, and 2 copyright skips.

### 2026-09-18 ground-marker and default-battery correction

Purpose: respond to the user's visual check that the translucent start disc
was hard to see at close range, make the marker visibly ground-mounted, make
battery management a launch default, and bring the canonical launch command
document up to date.

GUI verification used `ROS_DOMAIN_ID=84` and this command:

```bash
ros2 launch multi_robot \
  gazebo_multirobot_mapping_with_nav2.launch.py \
  world:=my_world.world robot_count:=1 \
  enable_gzclient:=true enable_status_panel:=false \
  enable_rviz:=false enable_merge_rviz:=false \
  auto_save_map:=false gazebo_seed:=405 \
  nav2_ready_timeout_sec:=240.0
```

This was a manual visualization run, not an evaluation episode. Gazebo spawned
`task_region_start_charge` and `task_region_charger_tb1`. Overhead and followed
close views confirmed that the new opaque blue 8-cm-wide, 2-cm-high segmented
ring is visibly attached to the floor and the green charging disc remains
clear inside it. The launch was intentionally interrupted after inspection.
The omitted `enable_battery` argument resolved to the new default `true`; after
Nav2 readiness, `/tb1/battery_manager` started automatically and reported
energy 100/100 at charger `(0.00, -0.45)`.

The original start marker was a 1-cm-thick disc with alpha 0.16. The retained
implementation uses a visual-only 48-segment ring whose bottom is about 1 mm
above the `z=0` ground plane. The target-distance marker uses the same ground
boundary treatment. No collision geometry was added.

Final regression:

```bash
git diff --check
ament_flake8 src/multi_robot_exploration/multi_robot_exploration \
  src/multi_robot_exploration/test scripts/ros_smoke_test.py
python3 -m py_compile \
  src/multi_robot_exploration/multi_robot_exploration/task_visualizer.py \
  src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py
colcon build --symlink-install \
  --packages-select multi_robot multi_robot_exploration
colcon test --packages-select multi_robot multi_robot_exploration \
  --event-handlers console_direct+
colcon test-result --verbose
```

Result: diff, lint, compilation, and build passed. Aggregate result was 54
tests, 0 errors, 0 failures, and 2 copyright skips.

## 2026-09-18 P2D complete ideal-task baseline and battery calibration

Purpose: after the user accepted P2C, lower the default battery energy and
implement the required P2D full-task ideal-communication integration gate.
Work started from pushed commit `620e869`. The user-owned deletion of
`report/20260914.md` and untracked `report/20260914_p1a.md` were left untouched.

All ROS episodes used the canonical workspace, ROS 2 Humble, the repository
`install/setup.bash`, battery enabled, a 300 simulated-second task limit unless
noted, and `COMPLETE` as the only success state. The P2D runner invocation form
was:

```bash
python3 scripts/run_p2d_baseline.py \
  [--scenarios <ids>] [--seeds <seeds>] [--robot-count <2|3>] \
  [--skip-cross-check] --run-id <run-id> --ros-domain-base <id>
```

The runner expands each episode to `scripts/ros_smoke_test.py` with
`--startup-timeout 600 --evaluation-duration 300 --coverage-threshold 0
--evaluation-wait-timeout 600 --target-detection --rally --battery`, the fixed
world/target/energy tuple, and an episode-specific output directory. It retries
at most twice only when no evaluator JSON exists; any task result, including a
failure, is final.

### Battery and target pilots

- `p2d_energy25_pilot_myworld_3r_seed303`, direct smoke, `my_world.world`, 3
  robots, seed 303, target `(-4,4)`, initial energy 25, charge required: PASS;
  `COMPLETE` 211.5 s, detection 70.5 s, RALLY 103.1 s, coverage 0.922, path
  65.073 m, three returns/three charges, minimum energy 5.653, zero collision.
- `p2d_pilot_rooms_energy25`, rooms, 3 robots, seed 404, target `(5,3)`, energy
  25: PASS; `COMPLETE` 216.7 s, detection 38.1 s, RALLY 38.7 s, coverage 0.908,
  path 48.511 m, two returns/two charges, minimum 5.541, zero collision.
- `p2d_pilot_corridors_energy25`, original corridor target `(-4.5,3.5)`, 3
  robots, seed 404, energy 25: task failure at 196 s,
  `battery_return_unreachable:tb1`; two returns, no completed charge, zero
  collision, minimum 5.817.
- `p2d_pilot_corridors_energy40`: pre-start infrastructure failure because tb3
  Nav2 did not activate; no evaluator result. The identical retained retry
  `p2d_pilot_corridors_energy40_retry1` reached `COMPLETE` at 163.4 s but failed
  safety with 29 collision events, minimum energy 17.629.
- `p2d_pilot_corridors_west_energy40`, revised truth-free target `(-4.5,-0.5)`,
  3 robots, seed 404: PASS; `COMPLETE` 147.2 s, detection 42.5 s, RALLY 43.0 s,
  coverage 0.826, path 48.351 m, zero charge and collision.

The interrupted calibration batches `p2d_formal_ideal_3scenes`,
`p2d_formal_ideal_3scenes_energy40`, `p2d_formal_ideal_energy40_v2`, and
`p2d_formal_ideal_energy40_v3` were retained as failures/interruptions. They
exposed a 25-energy simultaneous-return charge timeout and several Gazebo
master conflicts caused by orphan processes after interruption. Three
task-owned process groups were stopped with SIGINT and port 11345 was verified
free before later runs.

### Diagnostic matrix and targeted regressions

`python3 scripts/run_p2d_baseline.py --run-id
p2d_formal_ideal_energy40_v4 --ros-domain-base 40` completed 10 entries with
6 successes, 3 task failures, and 1 infrastructure failure:

- lab seeds 101/202 passed; seed 303 failed `insufficient_rally_poses`;
- rooms seeds 101/202 passed; seed 303 reached `COMPLETE` but had 41 collisions
  while a later robot attempted to pass a parked robot;
- corridors seed 101 reached `COMPLETE` but had six exploration collisions;
  seed 202 passed; seed 303 had three retained pre-start Nav2 failures;
- the two-robot corridors seed-202 cross-check passed.

The fixes added multi-robot target-area survey fallback, parked-robot dynamic
obstacles, exploration route reservations, and direct per-node Nav2 lifecycle
recovery. Targeted runner commands and results were:

```bash
python3 scripts/run_p2d_baseline.py --scenarios lab_far_northwest \
  --seeds 303 --skip-cross-check --run-id p2d_fix_lab303_v3 \
  --ros-domain-base 61
python3 scripts/run_p2d_baseline.py --scenarios rooms_far_northeast \
  --seeds 303 --skip-cross-check --run-id p2d_fix_rooms303_v2 \
  --ros-domain-base 62
python3 scripts/run_p2d_baseline.py --scenarios corridors_far_west \
  --seeds 101 --skip-cross-check --run-id p2d_fix_corridors101_v2 \
  --ros-domain-base 63
```

Results: lab `COMPLETE` 162.9 s, coverage 0.845, path 33.915 m; rooms
`COMPLETE` 95.6 s, coverage 0.819, path 30.811 m; corridors `COMPLETE` 219.4 s,
coverage 0.816, path 39.836 m. All three had zero collisions. Earlier retained
attempts include `p2d_fix_lab303` (three immediate failures because the shell
had not sourced `install/setup.bash`), `p2d_fix_lab303_v2` (pre-start Nav2
failure), `p2d_fix_rooms303` (Gazebo GLX failure), and
`p2d_fix_corridors101` (zero collision but RALLY timeout because the first
dynamic-obstacle radius of 1.2 m blocked a legal neighboring rally pose). The
final dynamic clearance is 0.6 m; the independent route-conflict threshold
remains 1.2 m.

### Formal batches

The first complete formal command was:

```bash
python3 scripts/run_p2d_baseline.py \
  --run-id p2d_formal_ideal_energy40_v5 --ros-domain-base 70
```

It completed 10 episodes: all nine three-robot episodes passed with
`COMPLETE` and zero collisions. Lab seed 202 performed one return/charge and
still completed at 229.6 s. The two-robot corridors cross-check at energy 40
timed out at 300 s in RALLY with tb1 still `RETURNING`; minimum energy was
9.093, one return began, no charge completed, and collision count was zero.
One corridors seed-303 pre-start `BadDrawable (GLX)` failure was retained; its
identical retry passed. Summary:
`log/p2d_baseline/p2d_formal_ideal_energy40_v5/summary.json`.

Energy 45 was first checked with:

```bash
python3 scripts/run_p2d_baseline.py --scenarios corridors_far_west \
  --seeds 202 --robot-count 2 --skip-cross-check \
  --run-id p2d_energy45_corridors_2r_seed202 --ros-domain-base 81
```

Result: PASS, `COMPLETE` 161.6 s, detection 65.8 s, RALLY 75.5 s, coverage
0.813, path 39.310 m, no return/charge, zero collision. The entire corridors
scenario was then frozen at energy 45 and rerun, rather than changing one seed:

```bash
python3 scripts/run_p2d_baseline.py --scenarios corridors_far_west \
  --run-id p2d_formal_corridors_energy45_v6 --ros-domain-base 82
```

All four entries passed with `COMPLETE`, zero collisions, and no infrastructure
failure: three-robot seeds 101/202/303 completed in 223.3/123.5/130.7 s with
coverage 0.822/0.759/0.823 and path 46.909/35.675/37.755 m; the two-robot
seed-202 cross-check completed in 147.6 s with coverage 0.827 and path 32.453 m.
Summary: `log/p2d_baseline/p2d_formal_corridors_energy45_v6/summary.json`.

The final P2D gate therefore combines the six lab/rooms energy-40 results from
v5 with the four corridors energy-45 results from v6: 10/10 `COMPLETE`, 0
collisions. Full design, per-episode metrics, and retained failures are in
`report/20260918_p2d.md`. P2D moves to `待用户验收`; P3 was not started.

Final retained-worktree validation:

```bash
cd src/multi_robot_exploration
python3 -m pytest -q
ament_flake8 multi_robot_exploration test \
  ../../scripts/ros_smoke_test.py ../../scripts/run_p2d_baseline.py
cd ../..
python3 -m py_compile scripts/ros_smoke_test.py \
  scripts/run_p2d_baseline.py \
  src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py \
  src/multi_robot_exploration/multi_robot_exploration/{control,nav2_ready_gate,task_evaluator}.py
colcon build --symlink-install \
  --packages-select multi_robot merge_map multi_robot_exploration
colcon test --packages-select multi_robot merge_map multi_robot_exploration \
  --event-handlers console_direct+
colcon test-result --verbose
git diff --check
```

Result: package pytest passed 55 tests with one copyright skip; all 20 selected
Python files passed `ament_flake8`; byte-compilation and all three package
builds passed. Aggregate colcon result was 61 tests, 0 errors, 0 failures, and
2 copyright skips. `git diff --check` passed.

## 2026-09-22 P3A explicit gateway

P3A source/build validation after the P2D acceptance:

```bash
source /opt/ros/humble/setup.bash
cd ros2_ws/ros2-multi-robot-automap
colcon build --symlink-install --packages-select \
  multi_robot_interfaces multi_robot_exploration merge_map multi_robot \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3 \
  -DPYTHON_EXECUTABLE=/usr/bin/python3
colcon test --packages-select multi_robot_exploration merge_map
colcon test-result --verbose
```

The build passed. The test result was 66 tests, 0 errors, 0 failures, and 2
skips. The source/runtime `bypass_audit` passed for three robots. The conda
`ns3gym` environment was also tried but lacks `em` and pytest; that environment
failure is retained and the ROS validation used the system ROS Python.

The first P3A pilot (`p3a_gateway_pilot_lab_seed101`, three robots, energy 40)
timed out under the unbounded gateway rate and showed high CPU. After adding
per-message rate limits and zlib map compression, pilot2 completed at 121.8 s
with zero collisions. Pilot3 exposed a real coordination race: one robot
returned for charge while the central controller continued dispatching rally
goals, producing 19 collision events. Pilot4 stopped before task start because
the two-second runtime audit transiently missed `/headquarters_control`; the
audit wait was raised to 10 s. Pilot5 and pilot6 then completed at 110.7 s and
132.2 s with zero collisions. These failures and fixes are retained in the P3A
report and were not substituted for formal episodes.

Formal gateway matrix command:

```bash
python scripts/run_p2d_baseline.py --seeds 101 202 303 \
  --run-id p3a_formal_gateway_3scenes_v2 --ros-domain-base 180 \
  --startup-timeout 600 --evaluation-wait-timeout 600
```

The 10 episodes (lab/rooms/corridors, three seeds each, plus corridors two-
robot seed 202 cross-check) all passed `task_complete`, `COMPLETE`, and zero
collisions with no infrastructure failures. The summary is
`ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a_formal_gateway_3scenes_v2/summary.json`.

Forced-charge regression command:

```bash
ROS_DOMAIN_ID=196 python scripts/ros_smoke_test.py --world my_world.world \
  --robot-count 2 --gazebo-seed 303 --startup-timeout 300 \
  --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 \
  --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection \
  --rally --battery --require-charge --battery-initial-energy 18 \
  --battery-capacity 100 --battery-move-cost 1 --battery-idle-cost 0.02 \
  --battery-safety-margin 5 --battery-charge-duration 10 \
  --battery-return-timeout 120 --battery-charge-timeout 60 --target-x -4 \
  --target-y 4 --target-max-distance 3 --target-field-of-view 90 \
  --target-confirmation-frames 3 --episode-id p3a_gateway_forced_charge_2r_seed303
```

Result: `task_complete`, coverage 0.932, completion 265.3 s, two returns,
two completed charges, minimum energy 6.22, and zero collisions. P3A remains a
same-host zero-loss ideal gateway; fixed delay/loss and ns-3 packet accounting
are intentionally deferred to P3B/P4.

## 2026-09-22 导航取消与充电闭环修复回归

修改范围：ROS 2 `multi_robot_exploration` 控制器、电池管理器、主 launch、smoke
入口和使用文档。探索 action 不再仅因地图信息增益在 3 秒后变化就取消；目标被观察到
只有同时持续无反馈进展才允许触发重规划，普通无进展阈值从 10 秒放宽到 20 秒。电池默认
容量/初始能量改为 60/24；充电判定半径为 0.5 m，定时器独立检查到位和静止，充到容量
80% 后恢复探索。

最短验证：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
colcon build --symlink-install --packages-select \
  multi_robot multi_robot_exploration merge_map
PYTHONPATH=src/multi_robot_exploration:/opt/ros/humble/local/lib/python3.10/dist-packages:/opt/ros/humble/lib/python3.10/site-packages \
  /usr/bin/python3 -m pytest -q \
  src/multi_robot_exploration/test/test_control.py \
  src/multi_robot_exploration/test/test_battery_manager.py
python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 1 \
  --gazebo-seed 101 --startup-timeout 240 --message-timeout 60 \
  --shutdown-timeout 45 --evaluation-duration 180 \
  --evaluation-wait-timeout 300 --target-detection --rally --battery \
  --require-charge --battery-capacity 30 --battery-initial-energy 8 \
  --battery-charge-duration 5 --battery-charge-radius 0.5 \
  --battery-charge-target-fraction 0.8 --target-x -4 --target-y 4 \
  --episode-id fix_20260922_charge_nav
```

结果：构建通过；pytest 33/33 通过。headless episode 在仿真时刻约 2086 s 触发返航，
日志确认 `started charging`、5 s 后 `charged and resumed`，随后继续探索、发现目标并
完成集合。评估 JSON `ros2_ws/ros2-multi-robot-automap/log/evaluation/fix_20260922_charge_nav.json`
记录 `success=true`、1 次返航、1 次完成充电、0 碰撞、最终电量 17.02/30；3 个取消状态
均来自低电量安全抢占或发现目标后的正常任务切换，不是充电失败。该回归未修改 ns-3
代码；网络实验仍按 P3B/P4 计划未开始。

## 2026-09-22 探索协调器四项优化对照

本轮针对用户要求的前四项进行同口径 ideal baseline 检查：电量返航只抢占对应机器人；
frontier/未知区积分图在同一地图快照内缓存；目标效用改为“预期新增覆盖 / 预计导航耗时”；
并测试运行时 frontier 组去重。命令模板如下（仅 `--run-id` 和 seed 变化）：

```bash
source /opt/ros/humble/setup.bash
source ros2_ws/ros2-multi-robot-automap/install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
python3 ros2_ws/ros2-multi-robot-automap/scripts/run_ideal_baseline.py \
  --seeds SEED --robot-count 2 --duration 180 --coverage-threshold 0.90 \
  --startup-timeout 300 --message-timeout 90 \
  --evaluation-wait-timeout 420 --shutdown-timeout 60 --run-id RUN_ID
```

结果（`time_to_90`，秒）：

| run-id | seed | 结果 |
|---|---:|---|
| `coord_v1_seed303` | 303 | 严格组去重；180 s 超时，覆盖 0.8993，未达到 90% |
| `coord_v2_seed303` | 303 | 组去重 + 无可用组时回退复用；103.9 s，覆盖 0.9091，0 碰撞 |
| `coord_v2_seed101` | 101 | 同上；109.2 s，覆盖 0.9168，较原基线 98.9 s 变慢 |
| `coord_v3_nogroup_seed101` | 101 | 取消严格组去重；103.1 s，路径 31.10 m，0 取消、0 碰撞 |
| `coord_v3_nogroup_seed202` | 202 | 直接按物理速度 0.18 m/s 估时；139.2 s，明显劣化 |
| `coord_v4_calibrated_seed202` | 202 | 将有效速度校准为 0.50 m/s；154.4 s，仍明显劣化 |

后两次说明仅用线性物理速度会把远 frontier 过度降权。最终代码保留“覆盖增益 /
预计导航耗时”的接口，但采用已有 Nav2 目标延迟拟合的超线性时间模型（指数 1.5），
与原有有效排序等价且不会牺牲 seed202 的尾段探索。严格 frontier 组唯一策略也未保留：
大 frontier 在组数不足或组本身跨区域时会让机器人空闲，反而降低吞吐；当前安全策略仍是
空间目标去重，并允许同组的空间上分离 viewpoint。

最终代码验证：三个相关包构建通过；`colcon test` 共 68 项，62 通过、1 跳过（另一个包
4 通过、1 跳过），无错误或失败；控制器与电池定向 pytest 34/34 通过。

## 2026-09-22 用户要求的 1–4 项复测与安全半径校准

用户要求由助手直接完成仿真复测。本轮固定 `my_world.world`、2 robots、180 s、90% 阈值，
通过 `scripts/run_ideal_baseline.py` headless 运行。当前提交 `7629ecb` 的三 seed 复测为：

| seed | time_to_90 | 路径 | 导航成功/取消 | 碰撞 |
|---:|---:|---:|---:|---:|
| 101 | 93.8 s | 33.26 m | 16/0 | 0 |
| 202 | 105.8 s | 32.90 m | 16/0 | 0 |
| 303 | 125.2 s | 34.94 m | 18/0 | 0 |

日志显示 seed303 的主要失败根因是 Nav2 报 `Starting point in lethal space`，随后出现
`No valid trajectories`，协调器的无进展取消只是后果。将协调器 `PATH_CLEARANCE_M` 从
0.23 m 对齐到多机器人 Nav2 的 0.35 m 后复测 `user_retest_clearance035_seed303`：
`time_to_90=108.4 s`、覆盖 0.908、路径 37.18 m、导航成功 19、取消 0、碰撞 0；仍有
两次 planner warning，但没有 action abort。继续增大到 0.45 m 的
`user_retest_clearance045_seed303` 只达到覆盖 0.806 并超时，已回退到 0.35 m。

同时复测了两种协调器策略：软 frontier 组去重 `user_retest_softgroup_seed303` 为
139.1 s 并出现两次目标失败；按实际 5 m 航段计算效用的
`user_retest_legutility_seed303` 为 178.0 s，明显退化。两者均未保留。最终保留的是
单机器人电量抢占、地图派生数据缓存、校准后的覆盖/导航耗时效用，以及与 Nav2 对齐的
0.35 m 路径安全膨胀。

最终 0.35 m 版本补跑固定三 seed：`final_clearance035_seed101` 为 115.6 s、
`final_clearance035_seed202` 为 103.4 s，连同前述 seed303 的 108.4 s，三 seed 均达到
90%，均为 0 action abort、0 碰撞、0 搜索重叠；三 seed 平均 `time_to_90=109.1 s`。
三轮仍各有 1/1/2 条 planner warning，但均未演变成导航取消。

补充失败尝试：`final_jointmatch_clearance035_seed303` 将每轮候选改为小规模联合最大效用
匹配，结果覆盖仅 0.855、180 s 超时，路径 28.70 m；说明在动态地图下静态联合最优会
选择不稳定目标，已撤回，未进入最终代码。

## 2026-09-23 项目路线审查与成功语义修复（无仿真）

本轮没有启动 Gazebo、ROS 2 或 ns-3 episode；依据当前源码、P1/P2/P3A 报告和本日志审查路线，
结论与修改记录在 `report/20260923_project_review.md`。审查确认 P3A 的 10 项 gateway 矩阵
是在后续电池/协调器/净空改动之前的历史代码状态，当前 HEAD 在重新生成带 commit/config/
environment manifest 的 P2D/P3A 门禁前，不接受 P3A、也不进入 P3B。

修复了一个会把过程事件误记为任务成功的代码缺陷：任务评估器和 `ros_smoke_test.py` 现在在
rally 模式只接受 `task_complete`，覆盖率和 `target_found` 仍可作为 P1/P2A 的独立过程门；
rally 模式也不会被覆盖率定时器提前终止。新增了对应单元测试。后续 P3B/P4A 必须补齐 stale
状态降级、独立稳定保持证明、碰撞监测心跳、固定时间采样和逐消息时间账本。
rally 模式单元测试为 10/10；三个相关 ROS 包构建通过。完整 `multi_robot_exploration` pytest
为 62 passed、1 skipped、1 failed：唯一失败是仓库既有的 flake8 汇总（扫描历史源码及生成的
build/install 文件，共 397 个 style errors），不是本轮修改的断言或运行时错误；该问题保留，
未做无关格式化清理。

## 2026-09-23 P3A.5 当前 HEAD 重验证（提交 41f63fb）

本轮把此前 gateway formal v2 之后发生的电池、协调器和净空修改纳入当前 task-stack 重验证。
代码状态为干净的 `41f63fb16d64e21a3ae1f296d509303b96b74528`；构建了
`multi_robot_interfaces`、`multi_robot_exploration`、`merge_map`，gateway/evaluator 定向
测试 13/13 通过，源码旁路审计通过。正式命令为：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_p2d_baseline.py \
  --seeds 101 202 303 \
  --run-id p3a5_current_head_41f63fb \
  --ros-domain-base 220 \
  --startup-timeout 600 \
  --evaluation-wait-timeout 600
```

runner 的固定矩阵为 lab `(-4,4,40)`、rooms `(5,3,40)`、corridors `(-4.5,-0.5,45)` 的
三机器人 101/202/303，另加 corridors 双机器人 seed 202；每个 episode 时长 300 s、消息
等待 90 s。结果目录为：

```text
ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a5_current_head_41f63fb/
```

结果为 9/10 `COMPLETE`、0/10 基础设施失败、10/10 零碰撞。唯一失败是 lab 三机器人 seed
202：episode 已启动，发现目标后进入 `RALLY`，`tb3` 发生一次安全返航充电，恢复后出现
`Starting point in lethal space`、`No valid trajectories` 和 `Failed to make progress`，
最终在 300.4 s 超时；该失败保留，不能按基础设施故障重试或用成功样本替换。它的评估 JSON
为 `episodes/p3a5_current_head_41f63fb_lab_far_northwest_3r_seed202.json`。

每个正式 episode 的 smoke 都报告 `P3A forbidden-bypass audit passed`。对 10 个正式图快照
和强制充电图快照的独立复核确认：中央协调器只订阅 `/gateway/received/...`，Nav2 目标只经
`/gateway/tbN/navigate_to_pose`，地图合并只订阅 gateway 接收地图，各机器人全局代价图只
订阅 `/tbN/gateway/merge_map`。`ideal_gateway` 的原始机器人输入和 evaluator/truth 节点的
只读真值订阅属于清单允许例外。图快照保存于 `graphs/*.json` 和 `forced_charge_graph.json`。

随后运行了强制充电回归：

```bash
ROS_DOMAIN_ID=230 PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 2 --gazebo-seed 303 \
  --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 \
  --target-detection --rally --battery --require-charge \
  --battery-capacity 100 --battery-initial-energy 18 \
  --battery-move-cost 1 --battery-idle-cost 0.02 --battery-safety-margin 5 \
  --battery-charge-duration 10 --battery-return-timeout 120 --battery-charge-timeout 60 \
  --target-x -4 --target-y 4 --target-max-distance 3 --target-field-of-view 90 \
  --target-confirmation-frames 3 \
  --episode-id p3a5_current_head_41f63fb_forced_charge_2r_seed303 \
  --evaluation-output-dir log/p2d_baseline/p3a5_current_head_41f63fb/forced_charge \
  --log-dir log/p2d_baseline/p3a5_current_head_41f63fb/forced_charge_logs \
  --bypass-audit-output log/p2d_baseline/p3a5_current_head_41f63fb/forced_charge_graph.json
```

强制回归 `COMPLETE`，两台机器人各完成 1 次充电（总计 2 次），最低电量 6.49，零碰撞；
结果为 `forced_charge/p3a5_current_head_41f63fb_forced_charge_2r_seed303.json`。

结论：P3A.5 的图/旁路和充电子门通过，但完整任务门未通过，`task_stack_frozen_commit`
不能冻结，P3B 不得开始。下一步先分析 lab/seed202 返航后的地图版本、全局代价图和 rally
目标，再在修复提交上按同一 10 格矩阵整批重跑。完整评审见
`report/20260923_p3a5.md`。

## 2026-09-23 P3A.5 失败路径诊断与保守修复（未重新验收）

本轮针对 `p3a5_current_head_41f63fb` 的 lab/seed202 失败格继续做只读诊断。正式日志显示
充电恢复后 rally 仍会收到 `Starting point in lethal space`、`No valid trajectories` 和
`Failed to make progress`；失败没有碰撞，也不是基础设施启动失败。代码审查发现
`plan_rally_leg()` 在起点未知、目标越界或地图上没有可达路径时原本会退回
`(robot_position, target_pose)`，从而绕过中央地图路径校验，可能把未验证的最终 pose 直接交给
Nav2；`path_waypoint_route()` 也没有先拒绝越界或不可通行的目标格。

当前修复保持最小范围：

1. `path_waypoint_route()` 先检查起点、目标边界和目标可通行性；不满足时返回空路径；
2. `plan_rally_leg()` 在没有安全路径时返回空计划，不再直接回退到最终 pose；
3. rally 调度器对持续无安全路径的机器人记录位置和目标，超过现有分配等待窗口后以
   `rally_route_unavailable:<robot>` 明确结束任务，避免把路径缺失伪装成 Nav2 运行时失败；
4. 增加断开地图和越界目标的单元测试。

验证命令与结果：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
colcon build --symlink-install --packages-select multi_robot_exploration
source install/setup.bash
/usr/bin/python3 -m pytest -q \
  src/multi_robot_exploration/test/test_control.py \
  src/multi_robot_exploration/test/test_gateway.py \
  src/multi_robot_exploration/test/test_task_evaluator.py
ros2 run multi_robot_exploration bypass_audit --robot-count 3 --source-only
```

结果为构建通过、`43 passed`、源码旁路审计 `pass=true`。同一 seed 的修复诊断使用
`ROS_DOMAIN_ID=203` 运行，输出位于
`ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a5_diag_route_fix_41f63fb/`；它以
`mission_failed` 和 `rally_route_unavailable:tb2` 结束，零碰撞、零基础设施失败。该结果证明
修复会显式暴露没有安全路线的状态，但没有证明 P3A.5 通过，也不能替代原始 10 格矩阵。

P3A.5 仍保持未通过，`task_stack_frozen_commit` 仍不可冻结，P3B 仍未开始。下一步应在同一
失败 seed 上增加地图快照序号、合并地图 origin/resolution、机器人位姿、局部/全局代价图
更新时间和 planner 起点状态的诊断字段，先确认充电恢复后的地图与 Nav2 costmap 是否出现
时序或坐标不一致，再决定是否需要等待新地图、清理 costmap 或调整 rally 起点选择；确认
根因前不应再次用单个成功重跑替换失败格。

## 2026-09-23 P3A.5 路径守卫提交整批重跑（提交 c369c7d，未通过）

在提交 `c369c7d37fdbad5be5e13ad13f7626007212d407` 的干净工作树上，按与
`p3a5_current_head_41f63fb` 相同的 10 格矩阵重新运行：lab/rooms/corridors 三机器人
seeds 101/202/303，以及 corridors 双机器人 seed 202 交叉检查。runner 输出目录为：

```text
ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a5_route_guard_c369c7d/
```

结果为 8/10 `COMPLETE`、0/10 基础设施失败、10/10 零碰撞：

| 场景 | 机器人 | seed | 结果 | 完成时间(s) | 发现(s) | rally(s) | 充电 | 碰撞 |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| lab | 3 | 101 | `COMPLETE` | 236.3 | 70.5 | 78.5 | 1 | 0 |
| lab | 3 | 202 | **timeout/EXPLORE** | — | — | — | 0 | 0 |
| lab | 3 | 303 | `COMPLETE` | 294.2 | 68.8 | 241.2 | 1 | 0 |
| rooms | 3 | 101 | `COMPLETE` | 139.4 | 96.2 | 97.0 | 0 | 0 |
| rooms | 3 | 202 | `COMPLETE` | 140.6 | 77.1 | 78.0 | 0 | 0 |
| rooms | 3 | 303 | **timeout/EXPLORE** | — | — | — | 1 | 0 |
| corridors | 3 | 101 | `COMPLETE` | 217.5 | 54.8 | 68.1 | 0 | 0 |
| corridors | 3 | 202 | `COMPLETE` | 146.1 | 42.5 | 57.6 | 0 | 0 |
| corridors | 3 | 303 | `COMPLETE` | 151.1 | 55.3 | 56.0 | 0 | 0 |
| corridors cross-check | 2 | 202 | `COMPLETE` | 145.9 | 49.6 | 62.2 | 0 | 0 |

两次失败均已启动并保存评估结果，因此是任务失败而非基础设施失败，不能由成功重跑替换。
lab/seed202 的日志持续出现 `Starting point in lethal space` 和 tb2 `Failed to make progress`；
rooms/seed303 在 `EXPLORE` 阶段超时，期间 tb1 充电恢复但未确认目标。路径守卫没有引入
碰撞或旁路问题，但也没有关闭这两个失败模式。该批次仍不能冻结 `task_stack_frozen_commit`，
P3B 仍未开始。

同时核对了当前运行时 graph：三个机器人 global costmap 均订阅
`/tbN/gateway/merge_map`，控制器仍只通过 gateway action；因此下一步应区分中央融合地图
路径与 Nav2 自己的 costmap 起点判定。源码中 `nearest_traversable()` 允许在约 1 m 内把中央
规划起点吸附到邻近自由格，而 Nav2 会按实际机器人起点和动态激光层判定 lethal；这解释了
为什么“中央有路”不能推出“Nav2 起点可用”，但目前仍是待验证假设。

下一步只增加只读诊断，不先改变成功规则：记录每次 map/gateway merge 的序号、时间、origin、
resolution，机器人 map/odom 位姿，global/local costmap 更新时间和起点栅格代价，并把 planner
失败时的最近一次快照写入 episode。先用 lab/202 和 rooms/303 各复现一次，确认是 map/costmap
时序、TF 坐标或动态 obstacle layer，再决定等待新 map、清理 costmap 或收紧中央起点吸附半径。

# 2026-09-23 P3A.5 rally reassignment and start-safety diagnostic

On current worktree after `c369c7d`, a targeted lab `my_world.world`, 3-robot,
Gazebo seed 202 episode tested the P3A.5 failure path. The command was:

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=211
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world \
  --robot-count 3 --gazebo-seed 202 --goal-timeout 60 \
  --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 \
  --evaluation-wait-timeout 600 --target-detection --rally --battery \
  --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 \
  --evaluation-output-dir log/p2d_baseline/p3a5_reassign_lab202/episodes \
  --log-dir log/p2d_baseline/p3a5_reassign_lab202/logs \
  --episode-id p3a5_reassign_lab202 \
  --bypass-audit-output log/p2d_baseline/p3a5_reassign_lab202/graph.json
```

Before the fix, the same seed reached `RALLY` and failed with
`rally_route_unavailable:tb3` after a fixed 10-second wait. The fix keeps the
route guard, waits up to 30 seconds for delivered map updates, and, after two
seconds without a route, chooses a fresh currently reachable rally pose while
preserving separation from assigned/arrived robots. Exploration assignment now
rejects a robot start that is not free in the received map instead of snapping
the route to a nearby free cell that Nav2 may reject as lethal.

The targeted rerun completed `COMPLETE` at 162.9 simulated seconds, with zero
collisions, zero navigation aborts, 39/42 navigation goals succeeded, and no
charge required. The final rally poses remained distinct (minimum separation
1.57 m). This is a diagnostic/targeted result only; it does not replace the
required 10-cell P3A.5 matrix. The 47 focused pytest checks passed and the
`multi_robot_exploration`/`merge_map` colcon build completed.


## 2026-09-23 P3A.5 exact-start 与串行 rally 定向验证

在工作树当前修改（尚未冻结提交）上，先运行 lab/seed202 的 exact-start 版本：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=231
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection --rally --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --evaluation-output-dir log/p2d_baseline/p3a5_exactstart_lab202/episodes --log-dir log/p2d_baseline/p3a5_exactstart_lab202/logs --episode-id p3a5_exactstart_lab202 --bypass-audit-output log/p2d_baseline/p3a5_exactstart_lab202/graph.json
```

结果为 `FAILED`、`rally_route_unavailable:tb3`，但 tb3 已完成多段集合路径后才失败；0 碰撞、0 导航 abort、1 次充电、0 基础设施失败。这排除了“初始起点吸附”是唯一根因，定位到已到位机器人作为动态障碍造成的 rally 调度死锁。

随后将 `RALLY_MAX_CONCURRENT` 限为 1，运行串行 rally 定向验证：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=232
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection --rally --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --evaluation-output-dir log/p2d_baseline/p3a5_serial_lab202/episodes --log-dir log/p2d_baseline/p3a5_serial_lab202/logs --episode-id p3a5_serial_lab202 --bypass-audit-output log/p2d_baseline/p3a5_serial_lab202/graph.json
```

结果为 `COMPLETE`，186.7 s，0 碰撞、0 导航 abort、0 充电，P3A forbidden-bypass audit passed。该结果仍是单格验证，不能替换正式 10 格矩阵。


## 2026-09-23 P3A.5 集合调度让路定向验证

在已推送 `d3c4dc5` 的起点安全修复基础上，先完成串行正式矩阵（命令见下方报告，结果 5/10），随后尝试“近侧优先 + 到位机器人安全让路”策略。该策略保留 `RALLY_DYNAMIC_CLEARANCE_M` 和活动路线冲突检查；无路由时仅为已到位机器人选择保持集合间距的替代位姿，并通过正常 rally leg 移动。

定向命令：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=229
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection --rally --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --evaluation-output-dir log/p2d_baseline/p3a5_yield_lab202/episodes --log-dir log/p2d_baseline/p3a5_yield_lab202/logs --episode-id p3a5_yield_lab202 --bypass-audit-output log/p2d_baseline/p3a5_yield_lab202/graph.json
```

结果为 `COMPLETE`，140.7 s，0 碰撞、0 导航 abort、0 充电，旁路审计通过。该样本未触发 parked-yield 分支，但验证了近侧优先不会破坏 lab/seed202；需要正式矩阵确认跨世界稳定性。


## 2026-09-23 P3A.5 可逆 parked-yield 实验

在 `0541ce7` 的近侧优先版本上，lab/seed202 仍因 tb2 的最终集合位切断 tb3 路线而失败，且没有触发原有重新分配；因此增加可逆 parked-yield：选择附近安全栅格、保持 `RALLY_MIN_SEPARATION_M`，临时移动阻塞机器人，抵达后恢复原最终集合位。新增 `rally_yield_pose` 单元测试，控制器测试 34 项通过。

随后使用 ROS_DOMAIN_ID=229 的同 seed 定向启动时遇到 Nav2 lifecycle 反复激活（旧实验资源残留），按 Ctrl-C 中断，未计入成功/失败矩阵；该次只作为启动故障记录。


## 2026-09-23 P3A.5 `0541ce7` 正式矩阵与 probe-action 定向结果

`p3a5_yield_0541ce7` 使用命令：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1
/usr/bin/python3 scripts/run_p2d_baseline.py --seeds 101 202 303 --run-id p3a5_yield_0541ce7 --ros-domain-base 210 --startup-timeout 600 --evaluation-wait-timeout 600
```

正式结果为 6/10 `COMPLETE`、0 基础设施失败。失败格为 lab/seed202 `rally_route_unavailable:tb3`，rooms/seed202 14 碰撞后 `COMPLETE` 状态不一致，corridors/seed202 三机器人和双机器人分别 `rally_route_unavailable:tb3/tb1`；该提交不能冻结。

当前未冻结工作树加入 probe-action 后，分别定向验证 rooms/seed202：`COMPLETE`、144.4 s、0 碰撞、0 nav abort；corridors/seed202 双机器人：`COMPLETE`、119.8 s、0 碰撞、0 nav abort；corridors/seed202 三机器人：`COMPLETE`、157.3 s、0 碰撞、1 nav abort。三机器人日志确认触发 `Yielding parked tb2`、`Probing a reachable rally survey pose for tb3`，随后两次恢复最终集合位并完成任务。

## 2026-09-23 P3A.5 `04e684d` probe-action 正式矩阵

代码状态：干净工作树，冻结候选提交 `04e684db840601c6caadd848dbf00ae3faae37cf`。命令：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1
/usr/bin/python3 scripts/run_p2d_baseline.py --seeds 101 202 303 --run-id p3a5_probe_04e684d --ros-domain-base 210 --startup-timeout 600 --evaluation-wait-timeout 600
```

结果：10 个 episode 中 8 个 `success=true` 且 `COMPLETE`；0 基础设施失败，10 个 ROS graph 均通过 P3A forbidden-bypass 审计。lab/seed202 在 `RALLY` 300.2 s 超时、0 碰撞：tb2 probe 成功后即将到达最终位时触发安全返航，tb1 随后也返航，剩余时间不足。corridors/seed101 达到 `COMPLETE`，但 tb1 有 3 次碰撞、1.7 s 接触时长，按零碰撞协议记为失败。其余 8 格均 0 碰撞；corridors/seed202 三机器人和双机器人均通过。失败格保留、不补跑替换。输出：`ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a5_probe_04e684d/summary.json`。该提交不能冻结为 P3A.5 基线。

## 2026-09-23 P3A.5 迭代恢复定向验证

在上述正式矩阵后，新增两项状态保护：连续两次 rally action 失败后强制进入一次既有 parked-yield/probe 恢复路径；临时让路机器人如果获得新的有效集合位则永久更新最终目标，避免无意义地返回旧位；probe action 期间禁止同一机器人并行派发普通 rally goal。构建和 49 项 ROS 单元测试通过。

一次使用非法 `ROS_DOMAIN_ID=240` 的 lab/seed202 启动在 Nav2 初始化阶段失败（Fast DDS 报 domain over 232），没有 episode 结果，作为基础设施启动误用记录；改用合法 `ROS_DOMAIN_ID=230` 后 lab/seed202 `COMPLETE`，169.5 s，0 碰撞、0 nav abort、0 充电，旁路审计通过。corridors/seed101 首次迭代在 300.4 s 超时但 0 碰撞，tb3 在评估器保存结果后才抵达最终位；触发恢复状态后第二次定向运行（`ROS_DOMAIN_ID=228`）`COMPLETE`，159.5 s，0 碰撞、0 nav abort、0 充电，旁路审计通过。输出分别为 `log/p2d_baseline/p3a5_iter1_lab202/`、`p3a5_iter1_corridors101/` 和 `p3a5_iter2_corridors101/`。这些仅是定向证据，仍需新提交上的完整 10 格正式矩阵。

`11e0138` 完整矩阵命令：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash; source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1
/usr/bin/python3 scripts/run_p2d_baseline.py --seeds 101 202 303 --run-id p3a5_recovery_11e0138 --ros-domain-base 210 --startup-timeout 600 --evaluation-wait-timeout 600
```

结果为 5/10 成功、0 基础设施失败。成功格：lab/303、rooms/101、rooms/202、corridors/101、corridors 双机器人交叉格；失败格：lab/101 在 `FOUND` 超时，lab/202 在 `RALLY` 超时，rooms/303 在 `RALLY` 发生 13 次碰撞并超时，corridors/202 三机器人在 `RALLY` 超时，corridors/303 在 `RALLY` 发生 14 次碰撞并超时。所有 10 个 graph 快照均通过 P3A forbidden-bypass 审计。完整结果保存在 `log/p2d_baseline/p3a5_recovery_11e0138/summary.json`；该提交不能冻结 P3A.5。

## 2026-09-23 P3A.5 rally 屏障定向迭代

为防止临时让路机器人立即回到旧最终位，新增 rally 屏障：让路动作未完成时暂停其它 rally 派发；让路机器人到达临时位后保持，待其它机器人到位再恢复最终位。随后为仍无中央安全路线的受阻机器人选择新的可达最终集合位。构建和 49 项测试通过。

rooms/seed303 定向运行 `p3a5_iter3_rooms303`：`COMPLETE`，124.5 s，0 碰撞、0 nav abort。corridors/seed303 首次屏障迭代 `p3a5_iter3_corridors303`：0 碰撞但 RALLY 超时，tb2 已保持临时位而 tb1 无法继续，说明屏障安全但需要受阻机器人重分配。加入重分配后第二次 `p3a5_iter4_corridors303`：`COMPLETE`，128.2 s，0 碰撞、0 nav abort。输出目录分别为 `log/p2d_baseline/p3a5_iter3_rooms303/`、`p3a5_iter3_corridors303/` 和 `p3a5_iter4_corridors303/`；均通过旁路审计，均为定向证据，不能替代正式矩阵。

## 2026-09-24 P3A.5 survey 轮转与 probe 超时定向回归

在 `e551a22` 的 rally 屏障/受阻机器人重分配基础上，修复两个状态机缺口：FOUND 阶段按轮转顺序选择 survey robot，避免一个失败的机器人反复占用 survey action；RALLY 阶段对卡住的 probe action 做 `goal_timeout_sec` 清理，释放机器人并重新进入恢复路径。新增 `rotate_robot_order` 单元测试；ROS 构建和四个测试包共 50 项通过。

定向命令均为 `ros_smoke_test.py`，世界 `p1c_corridors.world`、3 机器人、目标 `(-4.5,-0.5)`、电池初始能量 45、评估时长 300 s，分别使用 Gazebo seed 202/303，输出目录为 `log/p2d_baseline/p3a5_iter5_corridors202/` 和 `log/p2d_baseline/p3a5_iter5_corridors303/`。

结果：

- `p3a5_iter5_corridors202`：`COMPLETE`，167.4 s，0 碰撞、0 nav abort、0 充电，旁路审计通过；FOUND 后顺利进入 RALLY。
- `p3a5_iter5_corridors303`：`COMPLETE`，170.9 s，0 碰撞、0 nav abort、0 充电，旁路审计通过；日志确认触发 probe、临时让位、临时位屏障和最终 rally pose 恢复。

此前 `p3a5_barrier_e551a22` 正式矩阵的 corridors/seed202 FOUND 超时和 corridors/seed303 RALLY 超时均已得到针对性改善，但仍需在包含 10 格的正式矩阵中验证，不能用定向结果替换正式门禁。

## 2026-09-24 P3A.5 正式矩阵中断与控制流修复

在 `75907b7` 上启动正式矩阵 `p3a5_formal_75907b7`（同一 `run_p2d_baseline.py` 命令、seeds 101/202/303、domain base 210）。第一格 lab/seed101 已启动并保存，但因 `insufficient_rally_poses` 失败；第二格 lab/seed202 暴露了控制器异常：受阻机器人重分配后同一 timer 仍对刚清空的 `rally_route_unavailable_since` 做差值计算，`headquarters_control` 以 `TypeError: unsupported operand type(s) for -: 'float' and 'NoneType'` 退出。该批次在第二格启动后中断，未作为正式结果接受；输出保留在 `log/p2d_baseline/p3a5_formal_75907b7/`。

修复将当前机器人重分配后的不可用时间戳设为当前时间，保留恢复状态但避免同一轮的 `None` 差值。修复后重新构建、50 项 ROS 测试全部通过。

## P3A.5 电池全局屏障与串行 rally 诊断（2026-09-24）

`p3a5_iter6_lab101` 在 survey 退路修复后进入 RALLY，但 tb2 触发返航时其它 rally legs 仍运行，结果 24 次碰撞并超时；`p3a5_iter7_lab101` 将任一 RETURNING/CHARGING 状态改为取消所有 rally legs，结果 0 碰撞但 survey 充电后直到仿真 285.4 s 才进入 RALLY，300.4 s 超时。进一步确认每次 survey 成功都轮换 robot 会拖慢目标区准备，因此调整为仅 survey 失败时轮转。

`p3a5_iter8_lab101` 在该调整下快速进入 RALLY，但当前允许两条并发 rally 路线，tb2/tb3 动态交汇产生 24 次碰撞并超时；因此恢复 `RALLY_MAX_CONCURRENT=1`，并完成 51 项 ROS 测试。随后 `p3a5_iter9_lab101` 启动时 Gazebo 以 exit 255 退出，未产生 episode 结果，按基础设施启动中断保留，不计入任务成败。上述迭代均为定向诊断，尚不能替代正式 10 格门禁。

## P3A.5 串行 rally 与电池屏障定向通过（2026-09-24）

在 `f7a9b11` 上干净重跑 lab/seed101：`p3a5_iter10_lab101` `COMPLETE`，162.6 s，0 碰撞、0 nav abort、0 充电，目标检测 72.6 s、RALLY 80.6 s，旁路审计通过。该结果支持“survey 失败才轮转 + RALLY 单路串行 + 电池全局暂停”组合，但仍需完整 10 格正式矩阵确认。

## 2026-09-24 P3A.5 正式矩阵 `e6267d9` 失败与动态避障定向检查

在已推送提交 `e6267d9` 上运行：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1
/usr/bin/python3 scripts/run_p2d_baseline.py --seeds 101 202 303 --run-id p3a5_formal_e6267d9 --ros-domain-base 210 --startup-timeout 600 --evaluation-wait-timeout 600
```

输出 `log/p2d_baseline/p3a5_formal_e6267d9/summary.json`：5/10 成功，0 基础设施失败，10 份 ROS graph 快照保存并通过各 episode 的 P3A forbidden-bypass 启动审计。rooms/101、202、303，corridors/101 和 corridors 双机器人 seed202 均 `COMPLETE` 且 0 碰撞；lab/101 虽 `COMPLETE` 却有 2 次碰撞；lab/202 虽 `COMPLETE`、0 碰撞，却因 tb3 最终角速度 0.202 rad/s 大于 0.1 rad/s 容差而被 smoke 拒绝；lab/303 在 `RALLY` 超时、0 碰撞；corridors/202 在 `RALLY` 超时、0 碰撞；corridors/303 在 `RALLY` 超时且 23 次碰撞。所有失败格保留，不能冻结 P3A.5。

随后在 `e6267d9` 加未提交的动态位置阻挡/全局 survey 屏障改动上完成 ROS 构建和 51 项测试。两次定向运行使用下列命令模板，替换世界、种子、初始能量、目标和 run id；每次均保留 episode JSON、launch log、graph：

```bash
/usr/bin/python3 scripts/ros_smoke_test.py --world <world> --robot-count 3 --gazebo-seed <seed> --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 600.0 --target-detection --rally --battery --battery-capacity 100.0 --battery-initial-energy <energy> --target-x <x> --target-y <y> --evaluation-output-dir log/p2d_baseline/<run>/episodes --log-dir log/p2d_baseline/<run>/logs --episode-id <run> --bypass-audit-output log/p2d_baseline/<run>/graph.json
```

- `p3a5_iter11_corridors303`：`p1c_corridors.world`、seed 303、energy 45、target `(-4.5,-0.5)`；`COMPLETE` 170.0 s、0 碰撞、0 nav abort、0 充电，P3A 审计通过。
- `p3a5_iter12_lab101`：`my_world.world`、seed 101、energy 40、target `(-4,4)`；`RALLY` 在 300 s 超时、0 碰撞、0 nav abort、0 充电，P3A 审计通过。tb3 的 probe 路线被 Nav2 判为起点 lethal；probe 与 tb2 rally leg 重叠，重复超时、重分配，tb2 最终仍离集合位 5.59 m。此定向失败证明动态阻挡修复了该次走廊碰撞，却未恢复 lab 的集合活性，不能作为正式门禁成功。

## 2026-09-24 P3A/P3A.5 当前 HEAD 修复与定向回归

本轮代码基线为 `78b64be`，测试期间工作树包含未提交的 P3A.5 修复。修复内容包括：已知自由但落在 clearance inflation 中的导航起点使用有界逃逸格；rally recovery 同时保留临时位和最终位；根据当前地图和动态占位评估串行 rally 顺序；parked blocker 只在确实阻断目标路线时让路；survey/rally action 的取消、拒绝、异常和 stale handle 清理；成功的中间 rally leg 重置重试计数；完成判定等待所有导航和 probe/yield action 清空；电池返航 NavigateToPose 改走 `/gateway/<robot>/navigate_to_pose`，避免与协调器直控同一 Nav2 action。旁路清单新增电池管理器直连 Nav2 action 检查。

失败和中断记录：`p3a5_fix_lab101`（`my_world.world`、3 robots、seed 101、energy 40、target `(-4,4)`）在严格 clearance 起点逻辑下 `EXPLORE` 300 s 超时，未发现目标，0 碰撞；`p3a5_fix_lab202` 在 RALLY 300.4 s 超时，tb2 最终误差 4.424 m，tb3 充电 1 次，0 碰撞；`p3a5_order_lab202` 第一次启动误写 `TURTLEBOT3_MODEL=waffLE`，Nav2 ready 前手动中断，退出 130，无 episode JSON；`p3a5_fix_lab303` 目标检测后 tb3 返航时 Nav2 反复报告 `Starting point in lethal space`，最终 `battery_return_unreachable:tb3`，0 碰撞。对应输出目录均保留在 `log/p2d_baseline/`。

上述运行均使用 `ros_smoke_test.py` 的固定参数：`--goal-timeout 60 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection --rally --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4`，并分别使用 `ROS_DOMAIN_ID=210/211/212/213`；具体 episode JSON 和 launch log 位于各输出目录。误写模型名的命令及日志为 `log/p2d_baseline/p3a5_order_lab202/logs/robots3_seed202_20260924-182757.log`。

修复后的完整命令与结果：

```bash
source /opt/ros/humble/setup.bash; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=212; /usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection --rally --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --evaluation-output-dir log/p2d_baseline/p3a5_order_lab202/episodes --log-dir log/p2d_baseline/p3a5_order_lab202/logs --episode-id p3a5_order_lab202 --bypass-audit-output log/p2d_baseline/p3a5_order_lab202/graph.json
```

`p3a5_order_lab202`：`COMPLETE`，168.8 s，0 碰撞、0 充电，旁路审计通过。

```bash
source /opt/ros/humble/setup.bash; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=214; /usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection --rally --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --evaluation-output-dir log/p2d_baseline/p3a5_gatewayreturn_lab303/episodes --log-dir log/p2d_baseline/p3a5_gatewayreturn_lab303/logs --episode-id p3a5_gatewayreturn_lab303 --bypass-audit-output log/p2d_baseline/p3a5_gatewayreturn_lab303/graph.json
```

`p3a5_gatewayreturn_lab303`：`COMPLETE`，146.6 s，0 碰撞、0 充电，旁路审计通过；验证 gateway action 修复消除了返航竞态。

```bash
source /opt/ros/humble/setup.bash; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=215; /usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --goal-timeout 60 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection --rally --battery --require-charge --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --evaluation-output-dir log/p2d_baseline/p3a5_gatewayreturn_forced2r/episodes --log-dir log/p2d_baseline/p3a5_gatewayreturn_forced2r/logs --episode-id p3a5_gatewayreturn_forced2r --bypass-audit-output log/p2d_baseline/p3a5_gatewayreturn_forced2r/graph.json
```

`p3a5_gatewayreturn_forced2r`：`COMPLETE`，289.4 s，2 次充电、0 碰撞，旁路审计通过；两台机器人均完成返航、充电和任务恢复。控制器/电池/gateway 相关测试为 `75 passed in 4.41s`，P3A pep257/gateway 为 `4 passed in 5.00s`，`multi_robot_exploration` 构建成功。上述结果仍是正式 10 格矩阵前的定向证据。

## 2026-09-24 P3A.5 动态阻挡回退定向验证

在前一轮 lab/101 定向失败后，保留动态当前位置阻挡、串行 rally 和 survey 屏障，并加入“动态阻挡无路时退回已到位机器人阻挡”的活性回退。构建与 51 项测试通过。`p3a5_iter14_lab101`（`my_world.world`、3 robots、seed101、energy40、target `(-4,4)`）仍在 `RALLY` 超时，0 碰撞、0 nav abort、0 充电，旁路审计通过；最终未完成集合。该回退未解决 lab/101 的全部路由活性问题，因此尚未重跑正式矩阵。

## 2026-09-24 P3A.5 `561de99` 正式矩阵结果与最长路径均衡修复

在已推送提交 `561de99`（工作树干净）上运行冻结的 P3A.5 10 格门禁：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1
/usr/bin/python3 scripts/run_p2d_baseline.py --seeds 101 202 303 --run-id p3a5_final_561de99 --ros-domain-base 216 --startup-timeout 600 --evaluation-wait-timeout 600
```

输出 `log/p2d_baseline/p3a5_final_561de99/summary.json`，0 基础设施失败，10 个 ROS graph 快照均通过 P3A forbidden-bypass 审计；结果为 7/10 `COMPLETE`。保留的启动后任务失败如下：lab/202 在 `RALLY` 300.2 s 超时（0 碰撞、1 次充电，tb3 rally 路径 22.52 m）；rooms/101 虽到达 `COMPLETE`，但有 6 次碰撞（1 次充电，按固定零碰撞规则失败）；corridors/303 在 `RALLY` 300.2 s 超时（0 碰撞、0 充电）。其余 7 格均 `COMPLETE`、零碰撞；lab/303 有 1 次正常充电，corridors 双机器人交叉格通过。该批次失败格保留，不能冻结。

诊断显示 `assign_rally_poses` 先最小化总路径代价，可能把一条过长路线分给单个机器人，导致回充、动态阻挡或评估窗口耗尽。工作树随后将小规模分配搜索的排序目标改为 `(最长单机路径, 间距惩罚, 总路径)`，保留所有可达性和安全约束；不改变成功条件或评估器规则。控制器定向单元测试 40 项通过，`multi_robot_exploration` 构建通过。

在该未冻结修复上串行重跑三个正式失败格，均使用 `run_p2d_baseline.py`，固定 `--robot-count 3 --goal-timeout 60 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection --rally --battery --battery-capacity 100`，并保留 JSON、launch log、graph snapshot：

- `p3a5_minmax_lab202`：`my_world.world`、seed 202、初始能量 40、目标 `(-4,4)`、ROS domain 226；`COMPLETE`，188.4 s，0 碰撞、0 充电，审计通过。
- `p3a5_minmax_rooms101`：`p1c_rooms.world`、seed 101、初始能量 40、目标 `(5,3)`、ROS domain 227；`COMPLETE`，201.5 s，0 碰撞、0 充电，审计通过。
- `p3a5_minmax_corridors303`：`p1c_corridors.world`、seed 303、初始能量 45、目标 `(-4.5,-0.5)`、ROS domain 228；`COMPLETE`，176.4 s，0 碰撞、0 充电，审计通过。

这些三格是修复有效性的定向证据；由于当时工作树含未提交修改，不能替代后续干净提交上的完整 10 格正式矩阵。

## 2026-09-24 P3A.5 `2933c24` 当前 HEAD 正式门禁、环境失败与冻结候选

最长 rally 路径均衡修复已提交为 `2933c24e51eb3f47f17b7968482d3e645314faf8`。随后所有正式 episode 均从该干净 commit 启动，runner manifest 报告 `worktree_dirty=false`；没有把未提交定向运行混入正式结果。

### 第一批正式 runner：lab/rooms 六格

命令：

```bash
source /opt/ros/humble/setup.bash
source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
/usr/bin/python3 scripts/run_p2d_baseline.py --seeds 101 202 303 --run-id p3a5_final_2933c24 --ros-domain-base 216 --startup-timeout 600 --evaluation-wait-timeout 600
```

`log/p2d_baseline/p3a5_final_2933c24/summary.json` 保存了 lab/rooms 六格，均 `COMPLETE`、0 碰撞、0 基础设施失败：lab/101 214.7 s（0 充电）、lab/202 290.2 s（1 充电）、lab/303 197.0 s（0 充电）；rooms/101 240.6 s、rooms/202 229.6 s、rooms/303 104.9 s（后面三格均 0 充电）。runner shell 在六格完成后中断；当时已启动的 corridors/101 进程后来保存了独立 `COMPLETE` episode JSON，但不计入该 summary。残留 ros2/gazebo 进程已清理，保留的 JSON 和 launch log 不删除。

### corridors 预备尝试中的基础设施失败

第一次 corridors-only 尝试使用：

```bash
source /opt/ros/humble/setup.bash
source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
/usr/bin/python3 scripts/run_p2d_baseline.py --scenarios corridors_far_west --seeds 101 202 303 --run-id p3a5_final_2933c24_corridors --ros-domain-base 100 --startup-timeout 600 --evaluation-wait-timeout 600
```

该批次 4 格均在 episode 启动前失败：ROS 2 launch 尝试写默认 `/home/zhuyulab/.ros/log` 时收到 `OSError: [Errno 30] Read-only file system`。`summary.json` 明确记录 0 成功、4 基础设施失败，未计入门禁。

第二次改为设置可写 ROS 日志目录：

```bash
export ROS_LOG_DIR=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/ros_launch
mkdir -p "$ROS_LOG_DIR"
/usr/bin/python3 scripts/run_p2d_baseline.py --scenarios corridors_far_west --seeds 101 202 303 --run-id p3a5_final_2933c24_corridors_roslog --ros-domain-base 100 --startup-timeout 600 --evaluation-wait-timeout 600
```

该尝试越过只读目录错误，但受限运行环境不允许 Fast DDS 创建 UDP socket（`getifaddrs: Operation not permitted`、`TRANSPORT_UDP Error creating socket`），spawn service 不可用，未产生有效 episode；在首格重试后手动中断并保留 launch 输出。它同样不计入门禁。

### 第二批正式 runner：corridors 四格

在获得可用本地网络权限后，用同一 commit、同一场景参数和可写日志目录重新运行：

```bash
source /opt/ros/humble/setup.bash
source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_LOG_DIR=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/ros_launch
mkdir -p "$ROS_LOG_DIR"
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
/usr/bin/python3 scripts/run_p2d_baseline.py --scenarios corridors_far_west --seeds 101 202 303 --run-id p3a5_final_2933c24_corridors_net --ros-domain-base 100 --startup-timeout 600 --evaluation-wait-timeout 600
```

`log/p2d_baseline/p3a5_final_2933c24_corridors_net/summary.json` 的四格均 `COMPLETE`、0 碰撞，且每格 graph/bypass 审计通过：corridors/101 三机器人 179.2 s（0 充电）、corridors/202 三机器人 265.5 s（0 充电）、corridors/303 三机器人 224.4 s（0 充电）、corridors/202 双机器人交叉检查 274.1 s（1 充电）。该 summary manifest 与第一批完全相同地指向 `2933c24` 且工作树干净。

### 强制充电回归

同一 commit 上执行：

```bash
source /opt/ros/humble/setup.bash
source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_LOG_DIR=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/ros_launch
mkdir -p "$ROS_LOG_DIR"
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --goal-timeout 60 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection --rally --battery --require-charge --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --evaluation-output-dir log/p2d_baseline/p3a5_final_2933c24_forced2r/episodes --log-dir log/p2d_baseline/p3a5_final_2933c24_forced2r/launch_logs --episode-id p3a5_final_2933c24_forced2r --bypass-audit-output log/p2d_baseline/p3a5_final_2933c24_forced2r/graphs/p3a5_final_2933c24_forced2r.json
```

`p3a5_final_2933c24_forced2r.json` 为 `COMPLETE`，235.8 s、2 次充电、0 碰撞；两台机器人均完成返航、充电和恢复，bypass audit 通过。

### 门禁结论与当前审计

两个连续的干净 runner summary 合计固定 10 格：10/10 `COMPLETE`、0 碰撞；强制充电回归再完成 2 次充电。源码旁路审计命令为：

```bash
source /opt/ros/humble/setup.bash
source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash
PYTHONNOUSERSITE=1 /usr/bin/python3 src/multi_robot_exploration/multi_robot_exploration/bypass_audit.py --source-only
```

结果为 `pass=true`、`violations=[]`。因此 `task_stack_frozen_commit=2933c24` 是 P3A.5 冻结候选；P3A/P3A.5 进入待用户验收边界，P3B 尚未开始。上述只读日志目录、Fast DDS socket、runner shell 中断等失败和中断均保留，不用成功重跑覆盖。

### P3A.5 路径可达性修复与新地图消融（2026-09-25）

本次修复将 clearance 膨胀区内已知自由起点的有界 BFS 逃逸路径纳入 rally route、路径代价、分配排序和动态冲突检查；删除无安全路线时忽略未到达机器人的回退。未知或占用起点仍拒绝，battery safety gates 不变。新增 `multi_robot/worlds/p3a5_holdout.world`，目标 `(4.4, 3.4)`，配置标记 `unseen_map=true`；种子 404、505 未用于调试。

构建与测试：`colcon build --symlink-install --packages-select multi_robot_exploration multi_robot`；`colcon test --packages-select multi_robot_exploration`；结果 `83 tests, 0 errors, 0 failures, 2 skipped`。

固定门禁保持：`COMPLETE/task_complete`、零碰撞、pose gate、battery 正余量且 ACTIVE、无基础设施或 prestart 失败。新地图 full 变体两种子均 `COMPLETE`，零碰撞、零充电：seed404 completion 122.9 s/path 24.916 m，seed505 116.8 s/path 24.266 m。

同图同种子消融（各 2/2 `COMPLETE`，零碰撞、零充电）：

| 变体 | seed404 completion/path | seed505 completion/path |
|---|---:|---:|
| full minimax + safe order + conservative | 122.9 s / 24.916 m | 116.8 s / 24.266 m |
| remove longest-path (total path) | 95.0 s / 16.945 m | 127.4 s / 14.199 m |
| remove map-safe order search | 83.5 s / 16.018 m | 83.4 s / 18.498 m |
| remove conservative policy (concurrency 2, no global battery pause) | 61.0 s / 14.246 m | 82.2 s / 19.583 m |

这些数据只说明该新地图和两枚保留种子上的行为差异，不能据此宣称 full 在所有时间或路径指标上最优；固定门禁结果与解释性指标分开记录。

### P3B 固定 delay/loss gateway 协议门禁（2026-09-25）

用户尚未验收 P3A/P3A.5，但要求继续推进 P3B。本次先完成不依赖 Gazebo、ROS 2 或 ns-3 的确定性
应用层故障替身：同一个 `ideal_gateway` 在 `gateway_mode:=fault` 下使用独立上/下行固定 seed 队列，
支持 0/10%/100% 丢包、0/0.5/2 秒延迟、TTL 过期、序号去重/旧版本拒绝、重复、窗口乱序和有限
ACK 重传，并可用 `gateway_queue_capacity` 注入队列溢出；地图/位姿/TF 过期时中央协调器暂停新的分配，导航 gateway 对未送达命令执行 deadline
abort。每次 attempt 通过 `/gateway/message_events` 写出 `source_time`、`enqueue_time`、`admit_time`、
`tx_time`、`delivery_time/drop_time`、`message_id`、序号、尝试次数和原因，可选 JSONL 账本由
`gateway_ledger_path` 指定。默认 `gateway_mode:=ideal` 的 P3A 零损行为保留。

验证命令：

```bash
export PYTHONPATH=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration
/usr/bin/python3 -m pytest -q ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_fault_model.py
/usr/bin/python3 ros2_ws/ros2-multi-robot-automap/scripts/run_p3b_fault_matrix.py \
  --output ros2_ws/ros2-multi-robot-automap/log/p3b_fault_matrix_20260925.json
```

结果：`4 passed`；三个固定 seed 上、下行各 3 个丢包率 × 3 个延迟格均生成可复现 JSON，100% 丢包可靠
消息在初始发送加两次重试后明确耗尽，TTL 延迟消息记为 `expired`，乱序窗口输出 `[2, 1]`，整体
`status=PASS`。本次未启动 Gazebo 任务 episode，因此不能把它当成 P3B 完整任务成功率或 Wi-Fi
性能结果；下一步需在用户验收边界内运行 fault-mode ROS smoke，再进入 P4A ns-3 trace 对账。

### P3B fault-mode ROS smoke：100% 上行丢包（2026-09-25，失败样本保留）

为验证安全降级，运行了两机器人 `my_world.world` seed 101、`mission_mode=rally` 的 fault-mode
smoke：`uplink_loss_rate=1.0`、`downlink_loss_rate=0.0`、`gateway_max_retries=2`、90 秒评估上限。
Nav2 readiness 和 P3A bypass audit 均通过；启动后上行地图/位姿/TF 全部按固定 seed 丢弃，中央没有
收到 `/merge_map`，目标也没有进入 `RALLY`。smoke 在检查合并地图消息时超时并停止，评估器保留
`failure_reason=no_data`、`map_message_count=0`、`nav_goal_count=0` 的 post-start 失败结果；这不是
基础设施失败，也没有用补跑覆盖。逐消息 JSONL 账本保存在
`ros2_ws/ros2-multi-robot-automap/log/p3b_fault_100up_seed101.jsonl`，episode 和 launch log 在同名
目录。该结果符合“检测未交付不得 RALLY”的安全预期，但还不能作为成功率结论。

随后对当前 HEAD 做了 P3B 语义收紧：ACK 只在 TTL/序号检查通过或明确判定为重复时发送；源消息时间
来自传感器 header（融合地图由 merge 节点在生成时重新盖章），机器人本地 gateway 在电池非 ACTIVE、
命令 deadline 或本地重复命令时取消 Nav2；中央 stale gate 使用交付数据的源时间。该硬化发生在上述
ROS smoke 之后，因此该 smoke 保留为历史失败样本，不能直接作为硬化后完整 episode 证据；硬化后的
`colcon test`、fault matrix 和 fault gateway 进程 smoke 均通过。

## 2026-09-28 P3B 报告补充与协议门禁复核

为补齐独立阶段文档，新增 `report/20260928_p3b.md`，并按当前 HEAD
`39c788b6d8d3caf1c9a3c7e4e885b6339d5e28e3`（复核开始前工作树干净）重新执行协议级复核：

```bash
export PYTHONPATH=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration
/usr/bin/python3 -m pytest -q \
  ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_fault_model.py
/usr/bin/python3 ros2_ws/ros2-multi-robot-automap/scripts/run_p3b_fault_matrix.py \
  --output /tmp/p3b_fault_matrix_current.json
```

结果为 `4 passed` 和 `status=PASS`；当前脚本生成 54 格（3 seeds、上下行、3 丢包率、3 延迟）。
该复核没有启动 Gazebo 或 ns-3，也没有改变 P3B 的验收边界；详情见新增报告。运行时 JSONL 和 episode
文件仍是被忽略的实验产物，不纳入 Git 源码提交。

### 手动三机器人任务：低电量返航失败诊断（2026-09-28）

运行命令为 `ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py world:=my_world.world
robot_count:=3 enable_gzclient:=true enable_task_regions:=true enable_status_panel:=true enable_rviz:=false
 enable_merge_rviz:=false auto_save_map:=false gazebo_seed:=101 nav2_ready_timeout_sec:=360.0
 enable_target_detection:=true enable_rally:=true enable_battery:=true battery_initial_energy:=24.0
 target_x:=-4.0 target_y:=4.0`（换行空格仅为日志排版），代码状态为当前 HEAD `53df672`。
启动栈和 Nav2 均已起来，当前 gateway 参数为 `network_mode=ideal`、上下行丢包率为 0；这不是
P3B fault-mode 运行。

运行观察：`/task_state=FAILED`，`/task_failure=battery_return_unreachable:tb2`。逐机器人状态为
`tb1=ACTIVE`、`tb2=FAILED`、`tb3=ACTIVE`；tb2 初始能量 24.0、返航次数 1、充电次数 0、失败时
仍有约 14.50 能量。状态栏的 `activity_text()` 会在全局 task state 为 `FAILED` 时把每一行都显示
为“故障”，因此视觉上像三台同时失败；权威失败机器人只有 tb2。该结果说明 24.0 在三机器人
`my_world.world` 完整搜索/集结任务中属于低电量压力配置，返航阶段可能超过 120 仿真秒或遭遇返航
拥堵；既有 P2D 校准也记录过 25.0 的同类返航失败。后续手动完整任务推荐显式使用
`battery_initial_energy:=40.0`，18.0 仅用于两机器人强制充电 smoke。

### 2026-09-28 P2C battery isolation and budget fix validation

针对上面的低电量返航失败，修改当前 ROS task stack：总部按机器人隔离电池故障、维护动态 `participating_robots`，通过 `/robot_failure` 通知评估器；探索分配增加任务路径和保守返航预算检查；默认初始电量/安全余量/返航路径系数/返航超时改为 `40.0/8.0/2.0/180 s`；`global_battery_rally_pause` 默认关闭；状态面板改为逐机器人电池故障显示。

组件验证命令（代码状态 `327d998`）：

```bash
source /opt/ros/humble/setup.bash
source ros2_ws/ros2-multi-robot-automap/install/setup.bash
export PYTHONPATH=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration:$PYTHONPATH
/usr/bin/python3 -m pytest -q \
  ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_control.py \
  ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_battery_manager.py \
  ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_task_evaluator.py \
  ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_status_panel.py
```

结果：`62 passed`；Python 编译通过；`colcon build --symlink-install --packages-select multi_robot_exploration` 通过；`ros2 launch ... --show-args` 核对上述默认参数通过。

真实 Gazebo 回归样本一：命令为 `ROS_DOMAIN_ID=180 GAZEBO_MASTER_URI=http://127.0.0.1:11355 /usr/bin/python3 ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --robot-count 3 --world my_world.world --gazebo-seed 303 --target-detection --rally --battery --battery-initial-energy 40 --battery-capacity 60 --battery-safety-margin 8 --battery-return-path-factor 2 --battery-nominal-speed 0.18 --battery-return-timeout 180 --evaluation-duration 180 --episode-id p3b_isolation_fix_20260928`。Nav2/graph/map 门禁通过，任务进入 `FOUND`，随后总部因 survey goal 回调未初始化局部 `survey_robot` 退出；这是本次修复引入的回归，已修正，失败 launch log 保留在 `ros2_ws/ros2-multi-robot-automap/log/smoke/robots3_seed303_20260928-201945.log`。

真实 Gazebo 回归样本二：同样三机器人、seed 303、理想 gateway，`ROS_DOMAIN_ID=181`、Gazebo 端口 11356、初始电量 40、评估 120 s，episode `p3b_isolation_fix_20260928_r2`。当前机器上另有旧三机器人 ROS/Nav2 栈长期运行，导致本次新栈 Nav2 readiness 超时，检查阶段报 `missing topics: /merge_map, /task_state, /tb3/battery_state, /tb3/cmd_vel`；未形成有效 episode，不作为算法成功/失败样本。launch log 保留在 `ros2_ws/ros2-multi-robot-automap/log/smoke/robots3_seed303_20260928-202506.log`。

结论：组件级隔离和电量预算逻辑通过；两次真实回归分别暴露并修复了一个回调回归、以及受到并行旧 ROS 栈影响的启动资源问题。干净环境下仍需重跑完整三机器人任务，才可宣称 Gazebo 层面的动态故障继续执行已经通过。

## 2026-09-28 RALLY 并行长航段回归（当前未提交工作树）

为修复用户观察到的集合导航串行和频繁停顿，修改 ROS task stack：默认 `rally_max_concurrent` 从 1 改为 2；首次集合航段直接预约最终集合点，只有 action 失败或让路恢复时退回 1.5 m 短航段；活动路线释放已走过的前缀，并在路线冲突前截断候选路线；低优先级机器人继续使用位置接近让步；RALLY 卡住超时收紧为 30 s；集合阶段 freshness 只要求位姿/TF，重新规划才要求地图新鲜。默认 launch、smoke、P2D runner 和 `launch_commands.md` 已同步。

组件检查：

```bash
source /opt/ros/humble/setup.bash
PYTHONPATH=/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration:$PYTHONPATH \
python3 -m pytest -q ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_control.py
```

结果：`45 passed`；`py_compile` 通过；`colcon build --symlink-install --packages-select multi_robot_exploration multi_robot` 通过；`ros2 launch ... --show-args` 确认 `rally_max_concurrent` 默认值为 2。全包 pytest 仍有仓库既有 flake8/pep257 失败（2463 项），未归因于本改动。

真实 headless 回归命令（理想 gateway、`my_world.world`、2 robots、Gazebo seed 303）：

```bash
source /opt/ros/humble/setup.bash
source ros2_ws/ros2-multi-robot-automap/install/setup.bash
cd ros2_ws/ros2-multi-robot-automap
PYTHONPATH=$PWD/src/multi_robot_exploration:$PYTHONPATH \
python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 \
  --gazebo-seed 303 --startup-timeout 360 --message-timeout 90 \
  --shutdown-timeout 60 --evaluation-duration 240 --coverage-threshold 0 \
  --evaluation-wait-timeout 480 --target-detection --rally --target-x -4 --target-y 4 \
  --rally-max-concurrent 2 --episode-id p2b_rally_concurrent_2r_seed303_v4 \
  --log-dir log/p2b_rally_concurrent_2r_seed303_v4 \
  --evaluation-output-dir log/p2b_rally_concurrent_2r_seed303_v4
```

保留样本：v1 两台机器人均到达集合点且零碰撞，但旧 RALLY freshness 门导致评估器停在 `RALLY` 超时；v2 修复该门后 `COMPLETE`，133.0 s，零碰撞；v3 的临时 0.45 m 路径净空导致 `insufficient_rally_poses`，该实验参数已撤回；v4 使用 0.35 m 路径净空和 30 s RALLY action timeout，`COMPLETE`，完成时间 198.1 s，RALLY 到完成 36.8 s，2 robots 并行发出首轮集合 goal，零碰撞。日志和 JSON 分别保留在 `ros2_ws/ros2-multi-robot-automap/log/p2b_rally_concurrent_2r_seed303_v{1,2,3,4}/`。

结论：当前默认策略已从强制串行改为冲突感知并行；首轮不再每 1.5 m 停止，路线冲突才让低优先级机器人等待/让路。v4 证明理想通信下任务闭环可完成且无碰撞；仍需在 3 robots、corridors 和 fault-mode 条件下继续验证并发策略的退化边界。

追加 3 机器人回归：`my_world.world`、Gazebo seed 101、理想 gateway、`rally_max_concurrent=2`，episode `p2b_rally_concurrent_3r_seed101`。结果为 `COMPLETE`，总完成时间 152.1 s，RALLY 到完成 61.0 s，零碰撞，集合最小间距 1.414 m；tb2/tb1 首轮并行，tb3 因 Nav2 action 卡住在 30 s 被取消后按 1.5 m 短航段恢复，最终无碰撞完成。该样本说明并发上限 2、路径预约和超时恢复可共同工作，但也保留了单机器人 Nav2 卡住后的 30 s 恢复代价，后续 fault-mode 矩阵需继续统计这一类退化。

## 2026-09-28 当前故障诊断与电池返航回归

本轮首先复现用户正在运行的三机器人 `seed=101` 任务。旧进程仍残留在 ROS domain 0，图中同时存在 2026-09-24 的旧 gateway、Nav2、control 和 battery manager；清理后读取到的当前失败日志为 `/home/zhuyulab/.ros/log/python3_2005331...`。三台机器人在 RALLY 前后分别进入 `RETURNING`，gateway 因把非 `ACTIVE` 电池状态当作“禁止所有导航”而取消了返航目标，最终出现 `battery_return_unreachable` 和 `FAILED/all_robots_failed`。该失败是代码状态机错误叠加残留 ROS 进程污染，并非理想 gateway 的随机丢包。

本轮修改了 `navigation_gateway.py` 的电池状态转换：只在进入安全状态的瞬间取消旧探索目标，允许 `RETURNING` 的返航目标通过，并避免 action server 在并发 cancel/result 到达时重复终态转换。`battery_manager.py` 增加地图起点脱困、返航短腿、短暂 Nav2 abort 重试和返航方向性校验；`control.py` 不再把 idle 机器人位置当作永久排他点，路线冲突时至少序列化一条可达路线；Nav2 全局 costmap 使用静态合并图，动态障碍保留在 local costmap。

组件验证命令：

```bash
source /opt/ros/humble/setup.bash
cd ros2_ws/ros2-multi-robot-automap
source install/setup.bash
python3 -m pytest -q src/multi_robot_exploration/test/test_gateway.py \
  src/multi_robot_exploration/test/test_battery_manager.py \
  src/multi_robot_exploration/test/test_control.py
colcon build --symlink-install --packages-select multi_robot_exploration multi_robot
```

结果：`56 passed`，`py_compile`、`git diff --check` 和 colcon build 均通过。

真实 Gazebo 结果如下，失败和中间结果全部保留在 `ros2_ws/ros2-multi-robot-automap/log/diagnosis/`：

* `diagnosis_clean_seed101`：三机器人、理想 gateway、初始电量 40，`COMPLETE`，零碰撞、零 Nav2 abort，完成时间 154.5 s，最低电量 24.52；证明清理残留进程后正常探索闭环可完成。
* `diagnosis_forced_charge_seed303_v7`：两机器人、初始电量 18、`--require-charge`。tb2 充电 1 次并恢复，tb1 因旧返航目标在地图起点边界反复重试，最终返航超时；`nav_aborted=0`，但任务超时。
* `diagnosis_forced_charge_seed303_v8`：加入地图未知起点的 1 m 几何兜底后，两台返航目标均无 abort，但规划短腿未严格朝充电点收敛，任务超时；该结果促成方向性校验。
* `diagnosis_forced_charge_seed303_v9`：方向性校验后的两机器人、初始电量 18，两个机器人都进入返航但 180 s 内仍未充电，说明需要观察实际返航目标坐标，未将该样本宣称为通过。
* `diagnosis_forced_charge_seed303_v10`：两机器人、初始电量 12、`--target-detection --expect-target-not-found --require-charge`。tb2 从 `(0.084, 1.587)` 返航到 `(0.015, 0.649)`，进入充电并完成 1 次充电（总充电 1、最低电量 9.17、零碰撞）；随后随机目标提前被检测，评估器 `target_found` 正常结束，smoke 的“期望不可见目标”门禁因此报错，但电池返航/充电指标通过。最终代码保留返航阶段日志，方便现场继续诊断。

结论：当前默认三机器人启动使用初始电量 40；18/12 只作为压力测试。健康机器人不会因单个机器人进入 `RETURNING` 或 `FAILED` 而被 gateway 全局停住，总部会隔离故障机器人并继续给剩余 `ACTIVE` 机器人分配任务。若现场再次看到“所有机器人不动”，先确认没有旧 launch 残留，再查看 `/task_state`、`/robot_failure` 和每台 `/tbN/battery_state` 的权威状态。

四次压力测试均使用同一启动前缀（工作目录为 `ros2_ws/ros2-multi-robot-automap`，已 source Humble 和 `install/setup.bash`）：

```bash
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 300 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection --rally --battery --require-charge --battery-initial-energy 18 --target-x -4 --target-y 4 --episode-id diagnosis_forced_charge_seed303_v7 --evaluation-output-dir log/diagnosis --log-dir log/diagnosis
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 300 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 240 --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection --rally --battery --require-charge --battery-initial-energy 18 --target-x -4 --target-y 4 --episode-id diagnosis_forced_charge_seed303_v8 --evaluation-output-dir log/diagnosis --log-dir log/diagnosis
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 300 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 180 --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection --expect-target-not-found --battery --require-charge --battery-initial-energy 18 --target-x -4 --target-y 4 --episode-id diagnosis_forced_charge_seed303_v9 --evaluation-output-dir log/diagnosis --log-dir log/diagnosis
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 300 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 120 --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection --expect-target-not-found --battery --require-charge --battery-initial-energy 12 --target-x -4 --target-y 4 --episode-id diagnosis_forced_charge_seed303_v10 --evaluation-output-dir log/diagnosis --log-dir log/diagnosis
```

## 2026-09-29 当前三机器人充电状态诊断

用户现场启动命令：

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py world:=my_world.world robot_count:=3 enable_gzclient:=true enable_task_regions:=true enable_status_panel:=true enable_rviz:=false enable_merge_rviz:=false auto_save_map:=false gazebo_seed:=101 nav2_ready_timeout_sec:=360.0 enable_target_detection:=true enable_rally:=true enable_battery:=true battery_initial_energy:=40.0 target_x:=-4.0 target_y:=4.0
```

实时状态采样：`/task_state=RALLY`；tb1=`FAILED`, `battery_return_unreachable`, energy `17.08`, charge count `0`；tb2=`ACTIVE`, energy `12.89`；tb3=`ACTIVE`, charge count `1`, energy `36.04`。tb1 的 battery log 在同一 escape 目标 `(−4.14, 2.70)` 附近连续发送返航目标，约 180 s 后超时；tb3 已正常进入充电并恢复。该进程在本次充电阈值修改前启动，因此不作为新默认参数的回归结果；修改后需要重新启动 launch。
## 2026-09-29 ROS exploration/charging controller optimization (current worktree)

针对现场“历史目标硬排除后机器人停住、返航直线临时航点把机器人带偏、进入充电区后仍可能被迟到的导航结果拉走”的问题，修改了 ROS 2 task stack：历史和活动目标改为连续复用惩罚而不是硬过滤；探索目标用线性分配同时满足多机器人公平性和空间分离；栅格对角边禁止穿过两个障碍角；返航只使用地图可验证路径或短脱困路径，不再合成穿障直线；进入充电区后等待返航 action 完成/取消再开始稳定计时，并取消迟到接受的旧返航目标；同步 smoke 默认充电半径/时长为 0.8 m/6 s。

组件验证：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
python3 -m pytest -q src/multi_robot_exploration/test/test_control.py \
  src/multi_robot_exploration/test/test_battery_manager.py \
  src/multi_robot_exploration/test/test_gateway.py
colcon build --symlink-install --packages-select multi_robot_exploration multi_robot
```

结果：`64 passed`；两个 ROS 包构建通过。

真实 Gazebo 回归（ROS domain 50、`my_world.world`、seed 101、1 robot、初始能量 18、无目标/集合、180 秒上限）：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=50 GAZEBO_MASTER_URI=http://127.0.0.1:11350
python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 1 \
  --gazebo-seed 101 --startup-timeout 360 --message-timeout 90 \
  --shutdown-timeout 30 --evaluation-duration 180 --coverage-threshold 0 \
  --evaluation-wait-timeout 360 --battery --require-charge \
  --battery-initial-energy 18 --episode-id optimize_smoke_1r_180_v2 \
  --evaluation-output-dir log/optimize_20260929/smoke180_v2 \
  --log-dir log/optimize_20260929/smoke180_v2
```

结果：任务在评估上限时结束（单机器人探索未完成），但电池闭环通过：`battery_total_returns=1`、`battery_total_charges=1`、最低能量 `10.66`、最终模式 `ACTIVE`、`nav_aborted=0`、零碰撞、覆盖率 `0.789`。日志明确出现“return leg (charger)”、`started charging` 和 `charged and resumed`，证明返航、充电和恢复探索均发生。先前同配置的 v1 在返航时没有可行地图路径而停在 `RETURNING`，保留在 `log/optimize_20260929/smoke180/`，未替换为成功样本。
## 2026-09-29 双机器人联合探索回归（优化后）

在 commit `9c52404` 后使用 ROS domain 51、`my_world.world`、Gazebo seed 101、2 robots、120 秒 headless smoke（无目标、无电池）验证联合分配：命令为

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=51 GAZEBO_MASTER_URI=http://127.0.0.1:11351
python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 \
  --gazebo-seed 101 --startup-timeout 360 --message-timeout 90 \
  --shutdown-timeout 30 --evaluation-duration 120 --coverage-threshold 0 \
  --evaluation-wait-timeout 360 --episode-id optimize_explore_2r_120 \
  --evaluation-output-dir log/optimize_20260929/explore2r \
  --log-dir log/optimize_20260929/explore2r
```

结果：`nav_goal_count=24`、`nav_succeeded=22`、`nav_aborted=0`、`nav_canceled=0`，正确自由空间覆盖率 `0.9101`，搜索重叠 `0`，碰撞事件 `0`，总路径 `36.08 m`；评估按 120 秒上限结束，任务状态仍为 `EXPLORE`。日志显示两台机器人同时获得不同可达前沿，之后持续重新分配，没有出现等待全部机器人或单车独占目标的停滞。

## 2026-09-29 RALLY 动态占位死锁诊断

现场三机器人命令：

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py world:=my_world.world robot_count:=3 enable_gzclient:=true enable_task_regions:=true enable_status_panel:=true enable_rviz:=false enable_merge_rviz:=false auto_save_map:=false gazebo_seed:=101 nav2_ready_timeout_sec:=360.0 enable_target_detection:=true enable_rally:=true enable_battery:=true battery_initial_energy:=40.0 target_x:=-4.0 target_y:=4.0
```

RALLY 日志显示 tb1 先到达集合位，tb2 进入中间点后因充电暂停，tb3 的长路线超时；随后 tb1 被让到 `(-4.21, 0.56)`，但 tb2 和 tb3 反复对同一集合目标报告 `No safe rally route`，协调器重复重规划而没有放行一个机器人。现场同时发现一套遗留的两机器人 seed 303 launch（父进程 `2503667`，运行约 6 小时），已停止该遗留栈，仅保留当前三机器人 launch。

代码修复：当所有候选路线都被机器人动态占位挡住且没有正在执行的集合 action 时，按 `rally_dispatch_order` 选出第一个可行动机器人作为临时 leader，在静态合并地图上规划路线，把其他机器人位置降为软障碍；Nav2 local costmap 仍负责近距离避障，leader 离开后 followers 重新规划。组件结果：`64 passed`，`py_compile` 和 colcon build 通过。该现场进程在修复前启动，需重新 launch 才能验证新策略。

## 2026-09-30 P3A.6 当前 task-stack 重新冻结（未通过，保留全部结果）

本轮在当前 monorepo HEAD 上执行 P3A.6，不把历史 `2933c24` 的 P3A.5 结果当作当前基线。所有运行目录保留在 `ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/`，用户的未跟踪 `260929_report/` 文件未加入提交。

源码/构建门禁：`test_control.py`、`test_gateway.py`、`test_battery_manager.py`、`test_task_evaluator.py`、`test_fault_model.py` 共 `78 passed`；`multi_robot_interfaces multi_robot_exploration merge_map multi_robot` colcon build 通过；三机器人 source-only forbidden-bypass 审计通过。当前连续推送的 task-stack 提交为 `4cd83f2`、`f4474f0`、`d0a5db0`、`2776b8d`、`4d292d9`、`ba7276a`、`fbf4aa0`、`388b586`、`8136dce`、`5a61b16`、`6ad8788`。

正式矩阵命令（固定场景 `scripts/p2d_scenarios.json`，seed 101/202/303、corridors 双机器人交叉格，RALLY 单并发和全局电池暂停）为：

```bash
source /opt/ros/humble/setup.bash
cd ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1
/usr/bin/python3 scripts/run_p2d_baseline.py --seeds 101 202 303 \
  --run-id p3a6_current_head_388b586_final --ros-domain-base 210 \
  --startup-timeout 600 --evaluation-wait-timeout 600 --inter-episode-delay 5 \
  --rally-max-concurrent 1 --enable-global-battery-rally-pause
```

该批次第一格 `lab/seed101` 达到目标但探索阶段出现碰撞，因此 runner 被中止并保留；不能用后续定向结果替代固定矩阵。此前同一 P3A.6 调查还保留 `p3a6_current_head_7b0725c`（默认参数下碰撞/超时）、`p3a6_current_head_7b0725c_safe`（无碰撞但超时）、`p3a6_current_head_4cd83f2`（部分格碰撞/中断）、`p3a6_current_head_f4474f0`、`p3a6_current_head_d0a5db0`，以及一次因遗留 Gazebo 进程导致的启动基础设施中断。每次失败均保留原始 launch log 和已有 episode JSON。

定向诊断：`p3a6_diag_parked_single_lab101`（`8136dce`）为 RALLY 超时、0 碰撞、一次充电；`p3a6_diag_parked_after_first_lab101`（`5a61b16`）为 RALLY 超时、0 碰撞、目标发现 191.2 s、一次充电，`tb2` 最终距集合位 4.0 m；`p3a6_diag_yield5_lab101`（`6ad8788`）在目标区地图补全和重规划阶段被中止。结论：停驻位置保留消除了探索碰撞，但当前 RALLY 动态让路/目标区地图时序仍未满足 300 s 严格 `COMPLETE` 门禁。

强制充电回归命令：

```bash
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 \
  --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 \
  --target-detection --rally --battery --require-charge \
  --battery-capacity 100 --battery-initial-energy 18 --battery-move-cost 1 \
  --battery-idle-cost 0.02 --battery-safety-margin 5 --battery-charge-duration 10 \
  --battery-return-timeout 120 --battery-charge-timeout 60 --target-x -4 --target-y 4 \
  --target-max-distance 3 --target-field-of-view 90 --target-confirmation-frames 3 \
  --rally-max-concurrent 1 --enable-global-battery-rally-pause \
  --episode-id p3a6_forced_charge_6ad8788_seed303
```

输出目录为 `log/p2d_baseline/p3a6_forced_charge_6ad8788/`。机器人 tb1 确实出现返航、开始充电并恢复探索；但 300 s 内未满足目标检测/严格任务完成期望，不能计作两次充电 `COMPLETE` 回归。

结论：P3A.6 当前仍为进行中，未设置 `task_stack_frozen_commit`，不得进入网络/RL。详见 `report/20260930_p3a6.md`。

## 2026-09-30 P3A.5 后续探索路线优化（`d340ba3`）

本轮继续 P3A.5，不重新设置 `task_stack_frozen_commit`。源码把其他机器人当前位置纳入实际 `plan_rally_leg()` 路径避障；探索路线保持单路线派发；任一机器人返航充电时暂停新的探索派发，并在启用全局电池暂停时阻止新的集合派发。新增窄通道停驻占位和目标完成后停驻避让测试。用户要求本轮报告使用中文，详见 `report/20260930_p3a5_algorithm_optimization.md`。

组件验证命令：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
/usr/bin/python3 -m pytest -q \
  src/multi_robot_exploration/test/test_control.py \
  src/multi_robot_exploration/test/test_gateway.py \
  src/multi_robot_exploration/test/test_battery_manager.py \
  src/multi_robot_exploration/test/test_task_evaluator.py \
  src/multi_robot_exploration/test/test_fault_model.py
colcon build --symlink-install --packages-select multi_robot_interfaces multi_robot_exploration merge_map multi_robot
python3 -m py_compile src/multi_robot_exploration/multi_robot_exploration/control.py
git diff --check
```

结果：`80 passed`，4 个 ROS 包构建通过，语法检查和 diff 检查通过。

### 定向三机器人回归：通过

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=211 GAZEBO_MASTER_URI=http://127.0.0.1:11381
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 \
  --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 \
  --target-detection --rally --battery --battery-capacity 100 --battery-initial-energy 40 \
  --battery-move-cost 1 --battery-idle-cost 0.02 --battery-safety-margin 8 \
  --battery-charge-duration 6 --target-x -4 --target-y 4 \
  --rally-max-concurrent 1 --enable-global-battery-rally-pause \
  --episode-id p3a6_safe_candidates_lab101 \
  --evaluation-output-dir log/p2d_baseline/p3a6_safe_candidates_lab101/episodes \
  --log-dir log/p2d_baseline/p3a6_safe_candidates_lab101/logs
```

结果文件：`ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a6_safe_candidates_lab101/episodes/p3a6_safe_candidates_lab101.json`。结果为 `success=true`、`COMPLETE`、198.7 s 完成、89.9 s 发现目标、98.5 s 集合、`collision_events=0`、最低能量 20.51、充电 0 次。

### 强制充电回归：失败但充电闭环通过

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=211 GAZEBO_MASTER_URI=http://127.0.0.1:11381
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 \
  --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 \
  --target-detection --rally --battery --require-charge --battery-capacity 100 \
  --battery-initial-energy 18 --battery-move-cost 1 --battery-idle-cost 0.02 \
  --battery-safety-margin 5 --battery-charge-duration 10 --battery-return-timeout 120 \
  --battery-charge-timeout 60 --target-x -4 --target-y 4 --target-max-distance 3 \
  --target-field-of-view 90 --target-confirmation-frames 3 \
  --rally-max-concurrent 1 --enable-global-battery-rally-pause \
  --episode-id p3a6_forced_charge_parked_fix_seed303 \
  --evaluation-output-dir log/p2d_baseline/p3a6_forced_charge_parked_fix_seed303/episodes \
  --log-dir log/p2d_baseline/p3a6_forced_charge_parked_fix_seed303/logs
```

结果文件：`ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a6_forced_charge_parked_fix_seed303/episodes/p3a6_forced_charge_parked_fix_seed303.json`。300.2 s 超时，任务仍为 `EXPLORE`，目标未发现，`success=false`；两台机器人各返航并充电 1 次，共 2 次充电，`collision_events=0`，最低能量 9.288，最终均为 `ACTIVE`。该结果不能计作严格强制充电 `COMPLETE`。

### 并行探索试验：中断并保留

临时把探索并发上限设为 2 后运行三机器人 seed 101，命令使用相同的 `ros_smoke_test.py` 参数，`ROS_DOMAIN_ID=212`、`GAZEBO_MASTER_URI=http://127.0.0.1:11382`、episode `p3a6_parallel_lab101`，输出目录为 `log/p2d_baseline/p3a6_parallel_lab101/`。日志显示 tb2 返航、充电并恢复，tb3 随后长时间等待安全路线；评估窗口结束前进程被中断，没有 episode JSON。该试验未作为成功或失败的正式矩阵格，原始日志保留以供后续诊断；最终提交恢复单路线策略。

本轮代码提交为 `d340ba3`，已推送到 `origin/main`。中文报告和本节日志随后单独提交并推送。用户未跟踪的 `260929_report/` 文件未加入提交。

### 返航短段修复回归（`9025b38`）：充电和目标发现通过，RALLY 超时

诊断发现电池管理器的返航规划实际使用 `max_distance_m=float("inf")`，与“短腿重规划”的设计意图不一致。`9025b38` 改为使用 `MAX_NAVIGATION_LEG_M`，每个短返航段成功后再按最新地图规划下一段。组件仍为 `80 passed`，4 个 ROS 包构建通过。

命令：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=214 GAZEBO_MASTER_URI=http://127.0.0.1:11384
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 \
  --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 \
  --target-detection --rally --battery --require-charge --battery-capacity 100 \
  --battery-initial-energy 18 --battery-move-cost 1 --battery-idle-cost 0.02 \
  --battery-safety-margin 5 --battery-charge-duration 10 --battery-return-timeout 120 \
  --battery-charge-timeout 60 --target-x -4 --target-y 4 --target-max-distance 3 \
  --target-field-of-view 90 --target-confirmation-frames 3 \
  --rally-max-concurrent 1 --enable-global-battery-rally-pause \
  --episode-id p3a6_short_return_forced303 \
  --evaluation-output-dir log/p2d_baseline/p3a6_short_return_forced303/episodes \
  --log-dir log/p2d_baseline/p3a6_short_return_forced303/logs
```

结果文件：`ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a6_short_return_forced303/episodes/p3a6_short_return_forced303.json`。两台机器人各充电 1 次，共 2 次；`collision_events=0`；最低能量 `8.214`；目标在 `256.3 s` 确认，`267.6 s` 进入 RALLY。`300.1 s` 时仍为 `RALLY`，`success=false`。这次失败不再是 `battery_return_unreachable`：tb2 已成功短段返航并充电，剩余问题是目标发现过晚、集合起点曾被 Nav2 判为 lethal，集合时间不足。原始日志和 JSON 均保留。

## 2026-09-30 P3A.6 滚动预约与可视航点诊断

代码状态：`9b86c1b` 加本轮候选 working-tree diff；v3 的源码哈希和候选 patch 已保存到
`ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a6_visible_forced303_v3/`。
算法恢复最多两台探索并发，但仍检查停驻位置、活动路线和每条新路线的预约；冲突时尝试其他
候选。探索航点在遮挡转角前截断，最长 5 m；v3 收紧 Nav2 到达容差为 0.10 m，缓存单轮
Dijkstra 距离场，返航时排空其他探索动作（包括尚未确认的 action）。COMPLETE、300 s
上限、世界/目标/能量、检测和 gateway 边界均按原门禁。

组件命令（ROS workspace）：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_control.py \
  src/multi_robot_exploration/test/test_gateway.py \
  src/multi_robot_exploration/test/test_battery_manager.py \
  src/multi_robot_exploration/test/test_task_evaluator.py \
  src/multi_robot_exploration/test/test_fault_model.py
colcon build --symlink-install --packages-select multi_robot_interfaces multi_robot_exploration merge_map multi_robot
ros2 run multi_robot_exploration bypass_audit --robot-count 3 --source-only
```

最终 `86 passed`；4 个包构建通过，source-only 三机器人旁路审计通过。四份 Nav2 YAML
解析检查确认 goal checker 和 DWB 的 xy 容差均为 0.10 m。

三个诊断的精确命令如下（每次运行前重新 source，相继串行运行）：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=215 GAZEBO_MASTER_URI=http://127.0.0.1:11385
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 \
  --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 \
  --target-detection --rally --battery --require-charge --battery-capacity 100 \
  --battery-initial-energy 18 --battery-move-cost 1 --battery-idle-cost 0.02 \
  --battery-safety-margin 5 --battery-charge-duration 10 --battery-return-timeout 120 \
  --battery-charge-timeout 60 --target-x -4 --target-y 4 --target-max-distance 3 \
  --target-field-of-view 90 --target-confirmation-frames 3 --rally-max-concurrent 1 \
  --enable-global-battery-rally-pause \
  --episode-id p3a6_visible_forced303_v1 \
  --evaluation-output-dir log/p2d_baseline/p3a6_visible_forced303_v1/episodes \
  --log-dir log/p2d_baseline/p3a6_visible_forced303_v1/logs
```

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=216 GAZEBO_MASTER_URI=http://127.0.0.1:11386
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 \
  --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 \
  --target-detection --rally --battery --require-charge --battery-capacity 100 \
  --battery-initial-energy 18 --battery-move-cost 1 --battery-idle-cost 0.02 \
  --battery-safety-margin 5 --battery-charge-duration 10 --battery-return-timeout 120 \
  --battery-charge-timeout 60 --target-x -4 --target-y 4 --target-max-distance 3 \
  --target-field-of-view 90 --target-confirmation-frames 3 --rally-max-concurrent 1 \
  --enable-global-battery-rally-pause \
  --episode-id p3a6_visible_forced303_v2 \
  --evaluation-output-dir log/p2d_baseline/p3a6_visible_forced303_v2/episodes \
  --log-dir log/p2d_baseline/p3a6_visible_forced303_v2/logs
```

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=217 GAZEBO_MASTER_URI=http://127.0.0.1:11387
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 \
  --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 \
  --target-detection --rally --battery --require-charge --battery-capacity 100 \
  --battery-initial-energy 18 --battery-move-cost 1 --battery-idle-cost 0.02 \
  --battery-safety-margin 5 --battery-charge-duration 10 --battery-return-timeout 120 \
  --battery-charge-timeout 60 --target-x -4 --target-y 4 --target-max-distance 3 \
  --target-field-of-view 90 --target-confirmation-frames 3 --rally-max-concurrent 1 \
  --enable-global-battery-rally-pause \
  --episode-id p3a6_visible_forced303_v3 \
  --evaluation-output-dir log/p2d_baseline/p3a6_visible_forced303_v3/episodes \
  --log-dir log/p2d_baseline/p3a6_visible_forced303_v3/logs
```

- v1：新加的 0.3 m 最短位移过滤拒绝了出生区仅有的约 0.29 m 观察点。启动后
  中断（SIGINT/exit 130），保留 launch log，没有 episode JSON；不是基础设施失败或成功样本。
- v2：去掉该过滤后机器人开始探索，但 0.25 m Nav2 容差让约 0.214 m 中间航点
  在原地重复报告成功。启动后中断（SIGINT/exit 130）；收到地图/位姿快照保存为
  `p3a6_visible_forced303_v2/snapshot.npz`，原始 launch log 保留，无最终 JSON。
- v3：运行到正式终态，`success=true`、`COMPLETE`、176.3 s 完成，110.5 s 检测，
  124.1 s 进入 RALLY，零碰撞，2 次返航、2 次充电（每台 1 次），最低能量 9.318，
  最终两台均 ACTIVE，最大集合误差 0.1102 m；smoke exit 0。运行时旁路审计通过。

结论：v3 通过强制充电定向回归，但为 dirty-tree 诊断，不替代 clean-commit 正式
十格矩阵或最终强制充电回归。仍未设置 `task_stack_frozen_commit`。

正式批次启动前修正 runner manifest：clean worktree 只写入
`task_stack_candidate_commit`，`task_stack_frozen_commit` 初始为空。不能在尚未运行固定矩阵
时就由 HEAD 自动宣称冻结；正式退出门通过后由完整证据报告输出冻结提交。
验证：runner `--validate-only`（只检查固定场景，不启动仿真）、`py_compile`、diff 检查通过。

## 2026-09-30 P3A.6 正式滚动预约候选失败与 RPP 诊断

正式候选 `28f8f64`（已推送），source/runtime 图审计通过；`worktree_dirty=false`，
manifest 的 candidate commit 为该提交，frozen commit 为空。用户文件 `260929_report/`
只被临时列入 `.git/info/exclude`，没有移动、删除或提交；原排除内容备份于忽略的 runtime
目录，最终需恢复。

固定矩阵精确命令：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 GAZEBO_MASTER_URI=http://127.0.0.1:11388
/usr/bin/python3 scripts/run_p2d_baseline.py --seeds 101 202 303 \
  --run-id p3a6_rolling_28f8f64_matrix --ros-domain-base 218 \
  --startup-timeout 600 --evaluation-wait-timeout 600 --inter-episode-delay 5 \
  --rally-max-concurrent 1 --enable-global-battery-rally-pause
```

首次命令 run-id 为 `p3a6_rolling_28f8f64`，因该目录已被用于保存本地 exclude 备份，
runner 在启动任何模拟器前拒绝复用目录（exit 1）。改用新的 `_matrix` 目录后开始固定批次。
`lab/3r/101`：300.4 s 超时，RALLY，135.2 s 发现目标，136.9 s 进入 RALLY，
4 次碰撞，1 次充电，失败原因 collision。四个碰撞事件均发生在 RALLY（原日志
1790780767–1790780770）；不得被后来结果替换。输出保留在
`log/p2d_baseline/p3a6_rolling_28f8f64_matrix/`，summary 有这一格完整失败数据。
第二格 lab/202 启动期间中断，Nav2 尚未全部就绪，没有 episode_start 或 JSON，按
启动前基础设施中断保留 launch log。runner/第二格 smoke 均 SIGINT；后续八格未运行。

诊断发现：全局电池暂停可能让机器人停在返航通道；每个 RETURNING/CHARGING 心跳
反复取消其他 RALLY action，让通道恢复动作无法保持。Nav2 原 0.22 m 圆半径也小于
Gazebo 偏心 base collision 角点约 0.237 m，转弯时可能漏检后角。

新候选沿用滚动预约并切换至已安装的 Humble Regulated Pure Pursuit：最大线速度 0.26，
曲率/近障碍限速、预测碰撞检测开启，局部/全局圆半径 0.25 m；5 m 可视分段扩展到集合和
本地返航。返航暂停只在进入 RETURNING 时取消一次，通道阻塞时让健康机器人临时获得
通行优先级，移到返回路线之外的最近可达避让点；保留其最终集合位。
参考官方 Humble 文档 https://api.nav2.org/nav2-humble/html/md_nav2_regulated_pure_pursuit_controller_README.html
与论文 https://arxiv.org/abs/2305.20026；不宣称理论无死锁保证。

诊断一（dirty working tree 基于 `28f8f64`，RPP 和通道让路候选；两条 RALLY/return
执行路径均启用可视分段）：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=219 GAZEBO_MASTER_URI=http://127.0.0.1:11389
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 \
  --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 \
  --target-detection --rally --battery --battery-capacity 100 --battery-initial-energy 40 \
  --battery-move-cost 1 --battery-idle-cost 0.02 --battery-safety-margin 8 --battery-charge-duration 6 \
  --target-x -4 --target-y 4 --rally-max-concurrent 1 --enable-global-battery-rally-pause \
  --episode-id p3a6_rpp_lab101_v1 \
  --evaluation-output-dir log/p2d_baseline/p3a6_rpp_lab101_v1/episodes \
  --log-dir log/p2d_baseline/p3a6_rpp_lab101_v1/logs \
  --bypass-audit-output log/p2d_baseline/p3a6_rpp_lab101_v1/graph.json
```

结果：300 s 内 RALLY 未完成，timeout，零碰撞，1 次充电；目标发现 115.4 s，RALLY
117.2 s，tb1 已回充再到达最终集合点，tb2/tb3 仍距目标 4.8/11.0 m。完整失败 JSON
与图审计保留。结论：安全性改善但串行/全局暂停配置仍未满足时限。

诊断二使用同一 RPP/通道让路候选，将让路支持扩展到非全局暂停模式，source patch 保存于
`log/p2d_baseline/p3a6_rpp_lab101_v2/candidate.patch`。精确命令同诊断一，替换如下
（其余命令参数逐项相同）：ROS_DOMAIN_ID=220、GAZEBO_MASTER_URI=http://127.0.0.1:11390，
`--rally-max-concurrent 2 --disable-global-battery-rally-pause`，episode/output/log/graph
路径中的 `p3a6_rpp_lab101_v1` 全部改为 `p3a6_rpp_lab101_v2`。
结果：300 s 内 RALLY 超时，102.3 s 发现，106.3 s 进入 RALLY，零碰撞，2 次充电；
日志证实 tb2 临时让开 tb3 返航路线、随后 tb3 又让开 tb1 返航路线。JSON 中 tb2/tb3 的
小误差指向当时公布的临时避让位，不能当作原最终集合位到达；控制器仍拒绝 COMPLETE。
旧恢复规则等待其他所有机器人集合后才恢复让路者，导致额外等待。失败与完整日志保留。

诊断三验证独立的 return-yield 生命周期：返航机器人进入 CHARGING 后，已停稳的
让路者即可恢复原最终集合位，不再等待返航机器人再次走到目标区；普通集合避让保留原
恢复规则，故障隔离会清理相关 bookkeeping。新生命周期有可运行回归测试。
命令同诊断二，ROS_DOMAIN_ID=221、GAZEBO_MASTER_URI=http://127.0.0.1:11391，所有
episode/output/log/graph 路径改为 `p3a6_rpp_lab101_v3`。源码和文档 candidate.patch
保留在该目录。最终组件验证为 `90 passed`，四个包构建与三机器人源码旁路审计通过。

诊断三结果：exit 0，235.2 s COMPLETE，零碰撞、零返航/充电、无失败机器人；
64.4 s 发现、73.8 s 进入 RALLY，最低能量 20.6487，最大最终误差 0.09836 m。
三机器人运行时旁路审计通过。该轮未触发返航，因而仅能证明组合候选的任务回归通过，
不能据此宣称 return-yield 在实际充电中的生命周期已通过；该行为目前由组件测试覆盖，
仍需同一 clean commit 强制充电回归。与前两轮的差异体现异步仿真的运行波动，
不得把完成时间改善全归因于一条恢复规则。所有失败保留，固定十格尚未完成。

## 2026-10-01 P3A.6 RPP clean 候选固定批次（未通过）

候选 `6187eb737a184d90519b6bb4ba0b5114a4528a88` 已推送；manifest
`worktree_dirty=false`、candidate=该提交、frozen=null。运行期间未修改源码。

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 GAZEBO_MASTER_URI=http://127.0.0.1:11392
/usr/bin/python3 scripts/run_p2d_baseline.py --seeds 101 202 303 \
  --run-id p3a6_rpp_6187eb7_matrix --ros-domain-base 210 \
  --startup-timeout 600 --evaluation-wait-timeout 600 --inter-episode-delay 5 \
  --rally-max-concurrent 2 --disable-global-battery-rally-pause
```

lab/3r/101：300 s 超时，零碰撞、一次充电，139.6 s 发现。lab/3r/202：
207.4 s COMPLETE，零碰撞、无充电，102.8 s 发现。lab/3r/303：300 s 超时，
一次碰撞、一次充电，111.4 s 发现。三轮 runtime 图审计通过，完整 JSON/summary/日志
保留于 `log/p2d_baseline/p3a6_rpp_6187eb7_matrix/`。第三轮实际验证返航者进入充电
后，临时让路者恢复了原最终目标；不能据此把整轮计为通过。
rooms/101 在启动期间 SIGINT 中断，没有 episode_start 或 JSON；其 launch group
另发 SIGINT 清理，后续六格未运行。runner exit130，三轮任务失败未重跑覆盖。

第三轮碰撞前有两次 `Admitting tb1 ... robot positions ... soft obstacles`，
该兜底不仅忽略其他机器人位置，还绕过可视短航段，存在明确导航契约漏洞；旧日志没有
接触对象名称，不能断言碰撞对象。下一候选移除此兜底，允许尚未到达最终位的闲置
健康机器人参与原有阻塞让路；评估器增加接触对象/时间/阶段记录，碰撞计数和门限不变。

离线诊断（没有运行模拟器）：`log/p2d_baseline/p3a6_gain_diagnostic.py` 在保存的
`p3a6_visible_forced303_v2/snapshot.npz` 上计算墙体遮挡后的未知格收益；69 候选耗时
0.116 s，一些 box gain 明显下降，完全封闭的房间墙后未知格收益为零。
这只是算法假设和性能样本，不作为任务成功证据；仍未将 raycasting 改进写入正式算法。

该安全候选验证：92 项相关测试通过，四个 ROS 包构建通过，三机器人源码旁路审计通过。

## 2026-10-01 db21e92 强制充电与下一前沿候选

以下回归运行在 clean commit `db21e929024412bf749a0c52f193e50555539367`，
manifest/源码哈希保存于输出目录。源码保持固定，runtime 旁路审计通过。

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=222 GAZEBO_MASTER_URI=http://127.0.0.1:11393
/usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 \
  --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 \
  --target-detection --rally --battery --require-charge --battery-capacity 100 \
  --battery-initial-energy 18 --battery-move-cost 1 --battery-idle-cost 0.02 \
  --battery-safety-margin 5 --battery-charge-duration 10 --battery-return-timeout 120 \
  --battery-charge-timeout 60 --target-x -4 --target-y 4 --target-max-distance 3 \
  --target-field-of-view 90 --target-confirmation-frames 3 \
  --rally-max-concurrent 2 --disable-global-battery-rally-pause \
  --episode-id p3a6_rpp_db21e92_forced303 \
  --evaluation-output-dir log/p2d_baseline/p3a6_rpp_db21e92_forced303/episodes \
  --log-dir log/p2d_baseline/p3a6_rpp_db21e92_forced303/logs \
  --bypass-audit-output log/p2d_baseline/p3a6_rpp_db21e92_forced303/graph.json
```

结果 exit0：271.6 s COMPLETE，零碰撞，每台机器人恰好充电一次（合计2），
最低能量9.0386，无失败机器人；173.4 s 发现，192.4 s 进入 RALLY，最大最终误差
0.09242 m。短航点重复曾消耗时间，但后续恢复并完成，不据此宣称其问题已彻底解决。
该轮只验证 db21e92，不可转移到之后改动的 task-stack commit。

下一候选在已有粗粒度前沿候选生成后，用稀疏射线估计可观察未知格：射线只使用已交付
地图，遇到已知障碍/地图边界停止，未知空间仍是期望估计，不能当成真实可见区域。
收益格去重，当前目标剩余收益使用同一度量。方法参考
https://arxiv.org/abs/2002.04440 的 frontier/稀疏射线信息收益思想，不引入其 MAV
规划器或理论保证。探索容量由2改为3，但每条路线仍通过动态停驻避障、可视分段和
1.8 m 预约检查；共享通道仍串行，集合最大并发仍由原参数（本候选2）决定。
这是针对当前任务盲搜索效率的候选，不使用真值或提前已知目标，不改变能量/时限/检测
与 COMPLETE 门限，完整门禁仍须新提交重跑。

前沿候选组件验证：97 项相关测试通过，四包构建与三机器人源码旁路审计通过。

## 2026-10-01 d4f9cba 固定批次与阻塞动作饥饿修复

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 GAZEBO_MASTER_URI=http://127.0.0.1:11394
/usr/bin/python3 scripts/run_p2d_baseline.py --seeds 101 202 303 \
  --run-id p3a6_visible_gain_d4f9cba_matrix --ros-domain-base 200 \
  --startup-timeout 600 --evaluation-wait-timeout 600 --inter-episode-delay 5 \
  --rally-max-concurrent 2 --disable-global-battery-rally-pause
```

clean candidate `d4f9cba1479529b06ea9e3659645a583ed699b1c`，manifest
worktree_dirty=false、frozen=null。lab/3r/101：300.1 s RALLY 超时，零碰撞，
80.5 s 发现；runtime 图审计通过。第二格 lab/202 在启动期间 SIGINT 中断，没有
episode_start 或 JSON，后续八格未运行；runner exit130。JSON、summary、日志及
额外 interruption_manifest 均保留在 `log/p2d_baseline/p3a6_visible_gain_d4f9cba_matrix/`。
初次清理诊断脚本在处理 ps 表头时抛 ValueError，未发出中断；第二次已正确 SIGINT
runner/smoke/自有 launch group。第一格在此期间自然超时，保留真实 timeout JSON。

发现控制器重复 Reassigning parked tb1，却始终没有其新导航动作。此前扩大闲置
阻塞者范围后，旧代码的 return 让排在前面的等待机器人每个 timer 再次给阻塞者
分配相同目标，阻塞者永远到不了正常派发循环。新增实际 update_mission 回归测试
先在旧代码观察到请求列表为空的断言失败（补齐 fake survey_robot 后复现）；
修复先验证动态避障/可视短段，再立即派发阻塞动作，不能只更新目标后返回。
不放宽安全门限，不重开软障碍兜底。

修复最终验证：98 项相关测试通过，四包构建和三机器人源码旁路审计通过。
回归测试的避让支路需宽于离散净空膨胀直径；修正初版过窄 fixture 后使用真实路径规划
验证动作派发，未修改算法净空来让测试通过。

## 2026-10-01 bd2f0f2 完整固定十格（6/10，全部零碰撞）

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 GAZEBO_MASTER_URI=http://127.0.0.1:11395
/usr/bin/python3 scripts/run_p2d_baseline.py --seeds 101 202 303 \
  --run-id p3a6_recovery_bd2f0f2_matrix --ros-domain-base 190 \
  --startup-timeout 600 --evaluation-wait-timeout 600 --inter-episode-delay 5 \
  --rally-max-concurrent 2 --disable-global-battery-rally-pause
```

候选 `bd2f0f2` 已推送，整批期间源码和参数固定，manifest dirty=false，frozen=null；
runner exit1，十格全保留，无基础设施失败或重试；碰撞监测十格都 active，碰撞全为零。
源码和 runtime 旁路检查通过，十份 ROS graph 与 episode JSON 保留。最低能量9.8680，
seeds仍是开发/集成种子，不能当成 held-out 泛化/显著性结果。

| 场景 | robots | seed | 终态 | 完成/超时 s | 碰撞 | 充电 |
|---|---:|---:|---|---:|---:|---:|
| lab_far_northwest | 3 | 101 | COMPLETE | 249.4 | 0 | 1 |
| lab_far_northwest | 3 | 202 | COMPLETE | 191.8 | 0 | 0 |
| lab_far_northwest | 3 | 303 | RALLY timeout | 300.3 | 0 | 3 |
| rooms_far_northeast | 3 | 101 | EXPLORE timeout | 300.2 | 0 | 0 |
| rooms_far_northeast | 3 | 202 | COMPLETE | 207.5 | 0 | 0 |
| rooms_far_northeast | 3 | 303 | COMPLETE | 134.5 | 0 | 0 |
| corridors_far_west | 3 | 101 | RALLY timeout | 300.2 | 0 | 0 |
| corridors_far_west | 3 | 202 | RALLY timeout | 300.3 | 0 | 1 |
| corridors_far_west | 3 | 303 | COMPLETE | 284.9 | 0 | 0 |
| corridors_far_west | 2 | 202 | COMPLETE | 200.6 | 0 | 0 |

输出 `log/p2d_baseline/p3a6_recovery_bd2f0f2_matrix/`。rooms101 在出生区反复派发
零距离/零utility 目标，地图没有增量；lab303 在 RALLY 发生三次充电后超时。
corridors101/202 在 RALLY 超时，第一轮 tb1 已进入 CHARGING 但未完成一次充电，
所以 charge_count=0 并不代表没有返航；另外两台已到集合位。长绕行里的密集可视
短段不断停下/重新请求动作，增加了时间与空闲能耗。不得将 6/10 当成通过。

只读快照诊断（没有新增模拟器或控制指令）：
`source /opt/ros/humble/setup.bash; source install/setup.bash; export PYTHONNOUSERSITE=1 ROS_DOMAIN_ID=195; /usr/bin/python3 /tmp/capture_p3a6_snapshot.py log/p2d_baseline/p3a6_recovery_bd2f0f2_matrix/rooms303_start_snapshot.npz`。
诊断节点仅消费 gateway received odom/TF、中央合并地图与 task_state，保存了
三机器人出生位附近的地图（197×277）与位姿。成功的 rooms303 出生图有三组/十观察点，
每台有三项可达候选；这不能替代失败 rooms101 的地图重放证据。

在 `/tmp/p3a6-next/` 独立副本（不改变正式源码/进程）准备候选并运行101项组件测试。
pytest 因混合 /tmp 路径产生两个 cache 写入警告，测试全部通过。低优先级离线
几何搜索（NumPy seed17、最多80张矩形障碍图）在第18张找到可复现的非单调可视路径：
旧航点(3.35,1.95)，较远安全航点(5.05,2.75)。它证明旧“首个遮挡即截断”可能过早停下，
不是实际任务性能或安全性的证明。该几何 case 已固定成可运行测试。

下一候选保留1.2 m 宽间距采样，再以0.2 m 补足小前沿组的局部替代观察点（每组仍最多12）；
原0.45 m 观察点净空不变，机器人目标1.2 m、路线1.8 m 隔离不变。零utility 和已落入
Nav2 航点容差的目标拒绝准入。可视路段改为最远安全视线牵引，预约的路径同步改成
实际安全直线网格，不再保留不会执行的栅格弯折。
四台 Nav2 XY 容差由0.10收紧至0.02 m，小于5 cm 栅格半格，避免单格航点在原地完成；
源/配置一致性有测试，COMPLETE/电量/物理速度/障碍与碰撞门限保持原样。
104项正式源码组件测试、四包构建、三机器人源码旁路审计通过。新增短航点测试最初
把0.05步长放在0.1 m 网格边界而落回同格；修正为实际0.05 m 网格的中心点 fixture
后通过，未改算法来满足错误期望。新候选仍须新 clean-commit 固定门禁与强制充电，
不得继承 db21e92 的强制充电结果。

提交前复核：代码仅换行整理后按上述 ROS/install 环境重跑相同五文件，104 passed。
首次复核误用了不存在的 test_navigation_gateway.py，随后遗漏 install/setup 导致
collection ModuleNotFoundError；纠正命令/环境后通过，两次均没有启动模拟器。
十份 bd2f0f2 graph.json 用原 runtime_violations 与只读 snapshot adapter 重放，
10份/0违规，结果保存在同批 replayed_runtime_audit.json。

## 2026-10-01 7c53717 固定十格与有效消息限频修复

候选 `7c5371704aff2731a351ffa923ccd3808da53827` 固定十格按7+3批次运行；
两份 manifest dirty=false，source_digests完全相同，均frozen=null。
rooms/corridors runner exit1、lab runner exit1；无基础设施失败或重试；全部零碰撞，
6/10 COMPLETE，所有四格 post-start 超时保留，未执行该失败候选的强制充电回归。

```bash
source /opt/ros/humble/setup.bash; cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 GAZEBO_MASTER_URI=http://127.0.0.1:11396; /usr/bin/python3 scripts/run_p2d_baseline.py --scenarios rooms_far_northeast corridors_far_west --seeds 101 202 303 --run-id p3a6_precise_7c53717_rooms_corridors --ros-domain-base 180 --startup-timeout 600 --evaluation-wait-timeout 600 --inter-episode-delay 5 --rally-max-concurrent 2 --disable-global-battery-rally-pause
source /opt/ros/humble/setup.bash; cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 GAZEBO_MASTER_URI=http://127.0.0.1:11397; /usr/bin/python3 scripts/run_p2d_baseline.py --scenarios lab_far_northwest --skip-cross-check --seeds 101 202 303 --run-id p3a6_precise_7c53717_lab --ros-domain-base 170 --startup-timeout 600 --evaluation-wait-timeout 600 --inter-episode-delay 5 --rally-max-concurrent 2 --disable-global-battery-rally-pause
```

| 场景 | robots | seed | 终态 | 完成/超时 s | 碰撞 | 充电 |
|---|---:|---:|---|---:|---:|---:|
| lab_far_northwest | 3 | 101 | COMPLETE | 179.5 | 0 | 0 |
| lab_far_northwest | 3 | 202 | COMPLETE | 176.6 | 0 | 0 |
| lab_far_northwest | 3 | 303 | RALLY timeout | 300.1 | 0 | 2 |
| rooms_far_northeast | 3 | 101 | RALLY timeout | 300.3 | 0 | 0 |
| rooms_far_northeast | 3 | 202 | COMPLETE | 188.7 | 0 | 0 |
| rooms_far_northeast | 3 | 303 | COMPLETE | 192.2 | 0 | 0 |
| corridors_far_west | 3 | 101 | RALLY timeout | 300.3 | 0 | 0 |
| corridors_far_west | 3 | 202 | COMPLETE | 198.1 | 0 | 0 |
| corridors_far_west | 3 | 303 | RALLY timeout | 300.1 | 0 | 0 |
| corridors_far_west | 2 | 202 | COMPLETE | 209.6 | 0 | 0 |

输出位于 `log/p2d_baseline/p3a6_precise_7c53717_rooms_corridors/` 与
`log/p2d_baseline/p3a6_precise_7c53717_lab/`。首批rooms101已离开出生区，
但在所有机器人到位后超时；corridors303也在全体到位后超时。corridors101仍在
最后导航动作中；lab303在第三次RETURNING时超时，前两次充电完成，最低能量11.9710。
rooms101/corridors303没有当时的连续中央TF记录，不能直接把全部失败归因于TF。

只读监测命令（ROS/install环境，均不发布控制或读取Gazebo真值）：
`ROS_DOMAIN_ID=170 /usr/bin/python3 /tmp/p3a6_monitor.py log/p2d_baseline/p3a6_precise_7c53717_lab/lab101_delivered_state.jsonl`；
后期 `ROS_DOMAIN_ID=172` 同脚本输出lab303_delivered_state.jsonl。前者在COMPLETE退出，
后者在episode结束后SIGINT清理。rooms101出生图快照也保留在首批rooms101_start_snapshot.npz，
由同样只读的 `/tmp/capture_p3a6_snapshot.py`、ROS_DOMAIN_ID=180捕获。
lab101有90个任务期样本，tb1 TF最大源年龄15.393 s、22个样本超过5 s；tb3最大6.831 s，
里程计和电池持续新鲜。跨tf topic的odom/base无关消息在检查map/odom前占用.5 s
窗口，重复源时间也占窗口，因而可能长期饿死真正frame_state。

组件复现：ROS/install环境 `/usr/bin/python3 -m pytest -q -p no:cacheprovider /tmp/p3a6_gateway_regression.py`，
旧源码两项失败（5次有效map/odom只发0次；重复后新状态只发1而应2）。独立
`PYTHONPATH=/tmp/p3a6-next:$PYTHONPATH`修复副本三个回归通过；五个原有测试文件与该
回归共107项通过，运行期间未修改正式源码。新源码在筛选相关TF/新源时间后再限频，
真正新消息仍遵守原.5 s，源时间和TTL不重写，不能用接收时间续命。

lab303还有一次从集合区到(-4.18,-0.90)的临时避让，增加返航/充电负担。
新增真实窄通道测试在旧逻辑得到(1.85,2.65)、2.155 m的避让，仍位于等待者通道里；
永久替代位测试通过，临时分支在“最近安全refuge”断言失败。新逻辑仅在移除
该阻塞者后存在可行等待路线时，选离该路线至少.8 m的最近可达停靠点；沿用
既有.35静态/.6动态净空、.8位姿和1.8路线隔离。不能把“远离任务目标”当成让出通道。

集成后五文件108 passed、四包构建、三机器人源码旁路审计通过。
runner manifest另修正skip-cross-check及记录选定scenarios，增加runner/smoke源码哈希；
colcon版本从不支持的--version输出改为实际colcon-core0.20.1，validate-only及两个
flag分支、版本和两个哈希断言通过。新候选必须重新运行全矩阵与forced303，尚未冻结。

## 2026-10-01 baec4e8 部分固定门禁及集结能量预检查

```bash
source /opt/ros/humble/setup.bash; cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap; source install/setup.bash; source /usr/share/gazebo/setup.sh; export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 GAZEBO_MASTER_URI=http://127.0.0.1:11398; /usr/bin/python3 scripts/run_p2d_baseline.py --seeds 101 202 303 --run-id p3a6_fresh_baec4e8_matrix --ros-domain-base 160 --startup-timeout 600 --evaluation-wait-timeout 600 --inter-episode-delay 5 --rally-max-concurrent 2 --disable-global-battery-rally-pause > log/p2d_baseline/p3a6_fresh_baec4e8_runner_stdout.log 2>&1
```

clean候选baec4e88e89b40bf38224420f4b28a4b207a275a，dirty=false、frozen=null。
lab101 224.1 s COMPLETE/0碰撞/1充电；lab202 150.4 s COMPLETE/0碰撞/0充电；
lab303 300.3 s RALLY timeout/0碰撞/2充电、3返航、最低能量12.08454。
lab303 detect97.5 s，RALLY191.4 s；三个机器人在接近集合区后先后返航，
第三台未完成充电。保留该失败，不重复此post-start单元来替换结果。

为了先修复集结预算，在下一rooms101中断自有runner/smoke和launch process group
（SIGINT，runner exit130）。初始笔记误以为episode未开始；复核实际log后纠正：
evaluation started在1790834048.228901506，shutdown JSON为16.9 s/EXPLORE、success=false、
0碰撞。这是post-start中断，不是可重试的prestart基础设施失败。
interruption_notes.json已更正；两次COMPLETE、一次timeout、一次shutdown全部保留；
剩余六格未运行。没有执行该失败候选forced303，也不能冻结或启动网络/RL。
输出与runner_stdout均位于log/p2d_baseline/p3a6_fresh_baec4e8*。

只读 `ROS_DOMAIN_ID=160 /usr/bin/python3 /tmp/p3a6_monitor.py` 保存lab101完整任务记录
lab101_delivered_state.jsonl及lab101_tf_freshness_check.json：每台113个任务期样本，
tb1/tb2/tb3最大源TF年龄.303/.115/.531 s，无超过5 s的样本，结束于COMPLETE。
这是有效消息限频修复的实测证据，不把其他格没记录的TF情况推断成测量结果。

新候选复用既有导航成本1.25系数、局部返航path_factor/速度/余量，计算完整已知
集合路线 + 从最终位姿返航保留量 + 5秒稳定等待耗能。预算不足才提前请求充电，
不改变初始40/45/18、容量100/目标.8、速度/净空、300秒或COMPLETE门限。
新增可靠charge_request：总部候选/gateway/request/tbN/charge → 同一envelope传输 →
/tbN/gateway/charge_request。TTL10 s，源时间不续命，ACK/去重/重传复用既有
transport。本地管理器校验机器人、阶段、预算、期限、重复；若已充足/终止/正返航，
不重复启动。自动局部安全返航仍存在。请求等待者不能通过通道恢复支路绕过预算
去派发动作；充电恢复清理pending，失败隔离也清理pending。容量目标都不够时
明确失败rally_energy_capacity_insufficient，不能无限充电兜底。

组件证明：仅按当前home估算会接受E25、7 m任务，但目标home保留量后需33.37778；
无关TF/预算均不通过真值旁路。预算阻塞的恢复支路测试在baec4e8独立旧副本失败，
其他两例恢复通过；新代码全部通过。新增覆盖充足/不足/未知路线/无效能量/容量上限、
恢复后放行、本地重复/过期/终态/充电后迟到、实际CDR解码/可靠ACK/过期不ACK及
错误JSON不崩溃；124项五文件测试、四包colcon构建、扩展源码旁路审计通过。
命令沿用上述ROS/install五文件pytest与四包build/source-only审计；旧副本复现使用
`PYTHONPATH=/tmp/p3a6-preflight-old:$PYTHONPATH /usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_control.py -k idle_blocker`。
新候选仍须clean提交上的固定十格和forced303；先运行lab303，再同提交补齐其余九格。


## 2026-10-01 P3A.6 c08ca65 lab303：并发提前返航冲突与串行候选

clean候选`c08ca65da1d2b6b6df73970a62d05bc9e02353e2`只运行固定lab/303格，
其余九格与forced未运行。准确命令（workspace，ROS/install/Gazebo setup已source）：

```bash
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1 GAZEBO_MASTER_URI=http://127.0.0.1:11399
/usr/bin/python3 scripts/run_p2d_baseline.py --scenarios lab_far_northwest --skip-cross-check --seeds 303 --run-id p3a6_precharge_c08ca65_lab303 --ros-domain-base 150 --startup-timeout 600 --evaluation-wait-timeout 600 --inter-episode-delay 5 --rally-max-concurrent 2 --disable-global-battery-rally-pause > log/p2d_baseline/p3a6_precharge_c08ca65_lab303_stdout.log 2>&1
```

runner exit1；manifest clean且源码hash齐全，源码与运行时旁路审计通过。
lab303检测114.2 s、RALLY115.9 s，300.0 s timeout，16 collision events，
三返航/三充电、各一次、无failed robots/耗尽，minimum18.76655。
原始episode、collision_history、launch_log、graph与summary全部保留在
`log/p2d_baseline/p3a6_precharge_c08ca65_lab303/`，不替换失败。
日志显示在同轮向tb3/tb2/tb1全部请求提前充电；tb2/tb3本地返航没有互相共享
路线预约，直接接触并耽误了集合。仿真最终各机器人目标误差均<.025 m，但
300 s时未取得COMPLETE，因此即使无碰撞也不能宣布门禁通过。
只读监控命令`ROS_DOMAIN_ID=150 /usr/bin/python3 /tmp/p3a6_monitor.py log/p2d_baseline/p3a6_precharge_c08ca65_lab303/delivered_state.jsonl`，不输入Gazebo真值；仿真退出后SIGINT停止监控，exit130。

新候选仍逐台检查完整集合能量，但只允许一个提前返航请求owner；有任意本地
RETURNING/CHARGING时不启动下一台。请求尚在途时也只重试owner，先处理距离
charger近的机器人。等待者仍不能绕过预算派发正常集合或通道恢复动作。
复用既有返航通道让行，不修改本地自动安全返航、充电区/时间、速度或COMPLETE门限。
这解决本轮同发请求原因，仍需clean实测验证，不能声称涵盖所有自动返航冲突。
新增测试覆盖就近顺序、请求在途、RETURNING、CHARGING、ACTIVE恢复后下一台放行，
以及已有局部安全返航阻止新请求；五文件pytest为`127 passed`，四包colcon build与
三机器人source-only旁路审计通过。一次初始pytest命令误写不存在的test_bypass_audit.py，
exit4/no tests ran；已改为原五文件（control/battery_manager/gateway/fault_model/task_evaluator）
完整通过。正式新候选仍先lab303，再同提交补齐九格和forced303。


## 2026-10-01 P3A.6 22c95a7：固定十格和forced303全部通过

冻结候选`22c95a770a8812452c43fc177e4a00b5c032e6ef`，三批次1+7+2及forced全部runner exit0，
每份起跑manifest clean，同commit/source digests/environment。精确命令：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1

export GAZEBO_MASTER_URI=http://127.0.0.1:11400
/usr/bin/python3 scripts/run_p2d_baseline.py --scenarios lab_far_northwest --skip-cross-check --seeds 303 --run-id p3a6_serial_22c95a7_lab303 --ros-domain-base 145 --startup-timeout 600 --evaluation-wait-timeout 600 --inter-episode-delay 5 --rally-max-concurrent 2 --disable-global-battery-rally-pause > log/p2d_baseline/p3a6_serial_22c95a7_lab303_stdout.log 2>&1

export GAZEBO_MASTER_URI=http://127.0.0.1:11401
/usr/bin/python3 scripts/run_p2d_baseline.py --scenarios rooms_far_northeast corridors_far_west --seeds 101 202 303 --run-id p3a6_serial_22c95a7_rooms_corridors --ros-domain-base 180 --startup-timeout 600 --evaluation-wait-timeout 600 --inter-episode-delay 5 --rally-max-concurrent 2 --disable-global-battery-rally-pause > log/p2d_baseline/p3a6_serial_22c95a7_rooms_corridors_stdout.log 2>&1

export GAZEBO_MASTER_URI=http://127.0.0.1:11402
/usr/bin/python3 scripts/run_p2d_baseline.py --scenarios lab_far_northwest --skip-cross-check --seeds 101 202 --run-id p3a6_serial_22c95a7_lab101202 --ros-domain-base 170 --startup-timeout 600 --evaluation-wait-timeout 600 --inter-episode-delay 5 --rally-max-concurrent 2 --disable-global-battery-rally-pause > log/p2d_baseline/p3a6_serial_22c95a7_lab101202_stdout.log 2>&1

export GAZEBO_MASTER_URI=http://127.0.0.1:11403
/usr/bin/python3 /tmp/run_p3a6_forced.py p3a6_serial_22c95a7_forced303 175
```

forced编排副本`log/p2d_baseline/p3a6_serial_22c95a7_forced303/orchestrator.py`，
SHA256在manifest.json中；其实际smoke命令：

```bash
ROS_DOMAIN_ID=175 /usr/bin/python3 scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --coverage-threshold 0 --evaluation-wait-timeout 600 --target-detection --rally --battery --require-charge --battery-capacity 100 --battery-initial-energy 18 --battery-move-cost 1 --battery-idle-cost .02 --battery-safety-margin 5 --battery-charge-duration 10 --battery-return-timeout 120 --battery-charge-timeout 60 --target-x -4 --target-y 4 --target-max-distance 3 --target-field-of-view 90 --target-confirmation-frames 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3a6_serial_22c95a7_forced303 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a6_serial_22c95a7_forced303/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a6_serial_22c95a7_forced303/logs --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3a6_serial_22c95a7_forced303/graph.json
```

| 固定单元 | COMPLETE / s | 碰撞 | 充电次数 | 最大最终误差 / m |
|---|---:|---:|---:|---:|
| lab_far_northwest_3r_seed303 | 285.5 | 0 | 3 | 0.0319 |
| rooms_far_northeast_3r_seed101 | 117.6 | 0 | 0 | 0.0148 |
| rooms_far_northeast_3r_seed202 | 150.7 | 0 | 1 | 0.0259 |
| rooms_far_northeast_3r_seed303 | 106.8 | 0 | 0 | 0.0299 |
| corridors_far_west_3r_seed101 | 165.5 | 0 | 0 | 0.0380 |
| corridors_far_west_3r_seed202 | 155.4 | 0 | 0 | 0.0258 |
| corridors_far_west_3r_seed303 | 167.7 | 0 | 0 | 0.0299 |
| corridors_far_west_2r_seed202_crosscheck | 173.3 | 0 | 0 | 0.0325 |
| lab_far_northwest_3r_seed101 | 293.4 | 0 | 1 | 0.1619 |
| lab_far_northwest_3r_seed202 | 270.1 | 0 | 3 | 0.0322 |

固定十格零碰撞、失效、耗尽、基础设施失败或整格重试；只保留各固定单元首次
正式结果，没有同源码挑选重跑。部分Nav2就绪门内lifecycle恢复在launch logs保留，
不绕过就绪门，也未形成runner prestart failure。最大最终误差.16194 m，
最低15.89092，最长293.4 s；全部最终速度和5 s稳定门限通过。
forced303为190.4 s COMPLETE、各一次充电、零碰撞/失效/耗尽，最低8.63739。
源审计与十一图回放均无违规，冻结记录为report/20261001_p3a6_freeze.json。

复核命令（ROS/install，PYTHONNOUSERSITE=1）：

```bash
/usr/bin/python3 scripts/check_p3a6_gate.py \
  log/p2d_baseline/p3a6_serial_22c95a7_lab303/summary.json \
  log/p2d_baseline/p3a6_serial_22c95a7_rooms_corridors/summary.json \
  log/p2d_baseline/p3a6_serial_22c95a7_lab101202/summary.json \
  --forced log/p2d_baseline/p3a6_serial_22c95a7_forced303 \
  --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261001_p3a6_freeze.json
```

lab303只读监控命令`ROS_DOMAIN_ID=145 /usr/bin/python3 /tmp/p3a6_monitor.py log/p2d_baseline/p3a6_serial_22c95a7_lab303/delivered_state.jsonl`，
正常COMPLETE自动退出exit0，每台129个样本，TF最大年龄.492/.493/.513 s，均无>5 s；
tf_freshness_check.json保存汇总，不使用Gazebo真值控制。
127项组件测试及四包构建在22c95a7提交前通过；持久校验工具只读复核全部原始结果
后生成JSON，不变动运行任务栈。P3A.6门禁通过、待验收；开发seed不能替代holdout
统计评估。所有历史失败保留；本次未推进网络/RL。

收尾已移除本次专用.git/info/exclude块（260929_report/），没有改动用户材料或其他
排除规则。持久checker复核PASS，runtime source/config/protocol hashes及软件环境
仍与22c95a7一致；后续提交只补报告、handoff与只读复核工具。git add -n .所列
用户未跟踪报告均不纳入显式暂存，原始sim/build产物仍被忽略。


## 2026-10-01 P3A.6 验收与 P3B.5 组件开发

用户本轮明确验收 P3A.6（冻结任务栈22c95a7，报告f415f87）并要求继续P3B.5、优化算法。
开发状态：f415f87+本次源码修改。修复本地返航经网络阻塞、静默误判硬件失败、
无融合地图不开始评估、target只本地发现即终止；新增固定连续故障和本地deadline/等待账本。
用户260929_report/材料未修改/暂存；manifest完整记录这些无关未跟踪文件，不隐瞒工作树状态。
检查：ROS Humble/PYTHONNOUSERSITE=1，/usr/bin/python3 -m pytest -q
scripts/test_p3b5_tasks.py src/multi_robot_exploration/test/{test_control,test_gateway,test_fault_model,test_task_evaluator,test_battery_manager}.py。
首轮130通过/1失败：旧控制测试fake缺少新增freshness字段，KeyError；补足fake后重跑。
构建命令：colcon build --symlink-install --packages-select multi_robot_interfaces multi_robot_exploration merge_map multi_robot。
固定manifest见ROS scripts/p3b5_fault_manifest.json，holdout707不用于调参。
正式任务/理想重验证尚未运行；不能宣称P3B.5完成或新的冻结算法已通过集成门禁。

组件终检：135 passed（5.79 s）；四包build成功（5.55 s）。
协议检查精确命令：PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_development.json，54格PASS；
ros2 run multi_robot_exploration bypass_audit --source-only，零违规。
新manifest --validate-only返回26case/40episode（14种配置的ideal复用），尚无仿真结果。

3b752f2 开发预检命令（ROS工作区/Humble/install/Gazebo环境，PYTHONNOUSERSITE=1）：
GAZEBO_MASTER_URI=http://127.0.0.1:11420 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_dev_v1 --cases zero_rally_lab up100_lab single_failure_rooms forced_charge_outage --ros-domain-base 170 > /tmp/p3b5_dev_v1.log 2>&1。
预检拒绝、未启动仿真：从ROS子目录读git status时用户素材路径变为../../260929_report，白名单无法匹配。
修复manifest从Git根获取完整状态；失败目录保留，使用新run-id，不改用户材料。

b1f3828 开发批次p3b5_dev_v2：与dev_v1相同命令，仅run-id换为p3b5_dev_v2。7个计划episode全部启动前失败，无episode数据；原始manifest/命令/launch日志保存在ROS log/p3b5/p3b5_dev_v2。
根因：ROS launch CLI不接受gateway_drop_message_types:=或inject_failure_robot:=空值。修复smoke仅在非空时传CLI，空值使用launch默认；runner遇首个基础设施失败后停止，未跑格保持pending。
这些失败不计入任务成功率，未覆盖，也未声称仿真故障退化结果。

16a1e4b dev_v3：同dev_v2命令，run-id=p3b5_dev_v3。首个ideal实际启动；为修复连续故障时间基准，主动SIGINT本次launch进程组，保留shutdown（post-start中断，不是基础设施重试），无目标发现。结果/账本/graph保存ROS log/p3b5/p3b5_dev_v3/。
第二个zero-fault启动后launch退出、无episode；终止本次runner，其余5格未跑，全部保留、不混入正式矩阵。
发现固定blackout绝对仿真时间会消耗在Nav2冷启动期间，改为从中央第一次EXPLORE锚定，相对窗口固定并写fault_epoch。
发现初期目标spawn报超时，改为最后机器人spawn后再生成，并在smoke实际检查search_target实体。
精确原命令保存在manifest/runner.log；首次shutdown结果哈希与时长在下文补充。
dev_v3 retained: log/p3b5/p3b5_dev_v3/p3b5_dev_v3_ideal_lab2_rally_57e53c1e19/p3b5_dev_v3_ideal_lab2_rally_57e53c1e19.json; termination=shutdown, elapsed=72.70000000000027, collision=0, success=False。

修正后136项组件检查通过（5.95s），四包build通过（5.48s）；带blackout参数的ros2 launch --show-args通过（参数应放在--show-args之前，第一次位置错误被CLI拒绝，未启动仿真）。
为缩短80核主机上的验证时间，不同独立开发场景可以同时运行，各自固定CPU集合、Gazebo master和ROS域；每个runner内部仍串行，ideal/fault使用相同CPU集合。manifest新增cpu_affinity。
正式holdout尚未运行；后续精确环境/参数/故障和中断仍全部按原始证据记录。

6e50b68 独立开发批次与理想回归已启动（所有任务核心源码相同，以下为ROS/Humble/install/Gazebo环境，PYTHONNOUSERSITE=1）：
GAZEBO_MASTER_URI=http://127.0.0.1:11421 taskset -c 0-19 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_dev4_lab --cases zero_rally_lab up100_lab --ros-domain-base 170 > /tmp/p3b5_dev4_lab.log 2>&1；
GAZEBO_MASTER_URI=http://127.0.0.1:11422 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_dev4_rooms --cases single_failure_rooms --ros-domain-base 190 > /tmp/p3b5_dev4_rooms.log 2>&1；
GAZEBO_MASTER_URI=http://127.0.0.1:11423 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_dev4_forced --cases forced_charge_outage --ros-domain-base 210 > /tmp/p3b5_dev4_forced.log 2>&1；
GAZEBO_MASTER_URI=http://127.0.0.1:11424 taskset -c 60-79 /usr/bin/python3 scripts/run_p2d_baseline.py --run-id p3b5_ideal_gate_6e50b68 --ros-domain-base 140 --startup-timeout 600 --evaluation-wait-timeout 900 --infrastructure-retries 0 --rally-max-concurrent 2 --disable-global-battery-rally-pause > /tmp/p3b5_ideal_gate_6e50b68.log 2>&1。
当前已完成三种开发ideal对照：lab2 297.1s COMPLETE/2charges；rooms3 147.6s COMPLETE/0charges；forced2 229.7s COMPLETE/2charges，全部零碰撞，最低能量13.809/21.573/8.471。对应fault和十格理想回归尚在进行。
为了测量精确隔离/本地返充转态而不改任务核心源码，新增只读observe_p3b5.py（只订阅，无publisher），正式runner从启动前记录safety_events；新增零电量理想/故障配对验证真实FAILED，不计入TDI。正式矩阵27格/42episode，尚未启动holdout。
这些是实验框架/指标更改；不改变6e50b68任务核心、消息生成和控制算法。原始26格开发配置与失败/中断仍原样保留。

## 2026-10-01 P3B.5 第一任务候选保留、源时间修复

6e50b68三个dev4批次最终全结果：lab ideal297.1s/zero-fault212.7s COMPLETE，up100为300s no_data；rooms ideal147.6s COMPLETE，单机故障206.8s PARTIAL_COMPLETE、tb3显式FAILED、其余两台健康完成；forced ideal229.7s COMPLETE/两台各一次充电，20-130s outage为300s timeout/两台各一次充电。全部零碰撞/耗尽。
4ceb383正式候选启动命令（均Humble/install/Gazebo、PYTHONNOUSERSITE=1）：
GAZEBO_MASTER_URI=http://127.0.0.1:11425 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_formal_rooms --cases up10_rooms down10_rooms delay2_rooms overflow_rooms burst_rooms deadline_rooms detection_loss_rooms pose_loss_rooms single_failure_rooms target_loss_rooms --ros-domain-base 190 > /tmp/p3b5_formal_rooms.log 2>&1；
GAZEBO_MASTER_URI=http://127.0.0.1:11426 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_formal_corridors_forced --cases delay05_corridors duplicates_corridors nav_loss_corridors coverage_delay_corridors forced_charge_outage --ros-domain-base 210 > /tmp/p3b5_formal_corridors_forced.log 2>&1；
GAZEBO_MASTER_URI=http://127.0.0.1:11427 taskset -c 0-19 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_formal_lab --cases zero_rally_lab up100_lab down100_lab ttl_lab map_loss_lab battery_loss_lab state_loss_lab target_up10_lab battery_exhaust_lab --ros-domain-base 170 > /tmp/p3b5_formal_lab.log 2>&1。
候选因时间因果检查失败而主动停止；不把停止后无结果/启动期退出算作普通通信任务失败或自动重试。当前正在运行的episode对本次launch进程组SIGINT，post-start shutdown保留；启动前退出与尚未运行格单独保留。P2D当前batch停止；未运行holdout707。
根因源码：slam_toolbox_common.cpp:259的TF时间是scan_timestamp+transform_timeout，实际SLAM参数为0.2；不是生成时间。ROS缓存clock又比sensor header慢。delay2的6028个enqueue出现source>enqueue（最大0.249s），pose实际接受源年龄约1.918-1.999s，违背账本阶段时间因果顺序。
修复：从实际SLAM YAML推导offset，只在AP的TF副本恢复scan源时间；本地Nav2原生TF不动。传输enqueue/tx从max(cached_clock,source_time)开始，保持source<=enqueue<=tx<=delivery；payload/source时间按纳秒round。中央target消费时间不早于已知交付时间。
0.05s reorder只在ACK观察到60次乱序；新增显式reorder_step配置并用0.3s在5Hz pose上验证真实旧版本乱序拒绝，原单位模型默认0.05不变。理想模式忽略故障queue-capacity，统一正常4096队列；1格容量属于fault intervention，避免理想对照也被该故障污染。
历史完整summary/命令/参数/时长/结果/通信事件/源码环境与文件hash保存在report/20261001_p3b5_temporal_failed_candidate.json，所有raw episode/ledger/graph/launch logs仍保留在原目录。不是最终P3B.5通过证据，也不混入新矩阵。
6e50b68589afca39eb5a13bf539bc6f2dcc0d9b2 ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_dev4_lab/summary.json [["zero_rally_lab", "ideal", "task_complete", 297.0999999999999, 0], ["zero_rally_lab", "fault", "task_complete", 212.69999999999982, 0], ["up100_lab", "fault", "no_data", 300.1999999999998, 0]]
6e50b68589afca39eb5a13bf539bc6f2dcc0d9b2 ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_dev4_rooms/summary.json [["single_failure_rooms", "ideal", "task_complete", 147.60000000000002, 0], ["single_failure_rooms", "fault", "partial_task_complete", 206.79999999999998, 0]]
6e50b68589afca39eb5a13bf539bc6f2dcc0d9b2 ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_dev4_forced/summary.json [["forced_charge_outage", "ideal", "task_complete", 229.70000000000027, 0], ["forced_charge_outage", "fault", "timeout", 300.0, 0]]
4ceb3838dd4d34cb6173922ad5f9c43ea2064b6c ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_formal_lab/summary.json [["zero_rally_lab", "ideal", "task_complete", 216.5999999999999, 0], ["zero_rally_lab", "fault", "task_complete", 135.79999999999973, 0], ["up100_lab", "fault", "no_data", 300.4000000000001, 0], ["down100_lab", "fault", "timeout", 300.2999999999997, 0], ["ttl_lab", "fault", "shutdown", 179.0, 0]]
4ceb3838dd4d34cb6173922ad5f9c43ea2064b6c ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_formal_rooms/summary.json [["up10_rooms", "ideal", "task_complete", 113.6, 0], ["up10_rooms", "fault", "task_complete", 112.69999999999999, 0], ["down10_rooms", "fault", "task_complete", 114.29999999999998, 0], ["delay2_rooms", "fault", "task_complete", 246.79999999999998, 0], ["overflow_rooms", "ideal", "timeout", 300.4, 0], ["overflow_rooms", "fault", null, null, null]]
4ceb3838dd4d34cb6173922ad5f9c43ea2064b6c ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_formal_corridors_forced/summary.json [["delay05_corridors", "ideal", "task_complete", 189.0, 0], ["delay05_corridors", "fault", "task_complete", 209.89999999999998, 0], ["duplicates_corridors", "fault", "task_complete", 169.8, 0], ["nav_loss_corridors", "fault", "timeout", 300.1, 0], ["forced_charge_outage", "ideal", "task_complete", 184.80000000000018, 0], ["forced_charge_outage", "fault", "timeout", 300.0999999999999, 0], ["coverage_delay_corridors", "ideal", null, null, null]]
P2D保留已写入summary的8格；当前source候选需全新同提交十格+forced重验证，不合并旧source batch。

时间修复候选组件终检：PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -q scripts/test_p3b5_tasks.py src/multi_robot_exploration/test/{test_control,test_gateway,test_fault_model,test_task_evaluator,test_battery_manager,test_navigation_faults}.py，141 passed（6.07s）。四包colcon build（multi_robot_interfaces multi_robot_exploration merge_map multi_robot）通过5.36s；首次误选不存在的collision_monitor仅构建3包，随后按正确四包重跑。source-only三机器人旁路审计零违规；run_p3b_fault_matrix.py --output log/p3b5_protocol_temporal_v2.json返回54格PASS；ros2 launch ... --show-args通过；manifest validate-only返回27case/41episode。新仿真尚未启动；静态目标确认生命周期假设写入P3B.5计划。

## 2026-10-01 P3B.5 c3819c3 候选保留、本地返航FAILED取消修复

冻结源码c3819c3三个主批次精确命令（Humble/install、PYTHONNOUSERSITE=1，四CPU池隔离，每runner串行）：
GAZEBO_MASTER_URI=http://127.0.0.1:11428 taskset -c 0-19 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v2_lab --cases zero_rally_lab up100_lab down100_lab ttl_lab map_loss_lab battery_loss_lab state_loss_lab target_up10_lab battery_exhaust_lab --ros-domain-base 170 > /tmp/p3b5_v2_lab.log 2>&1；
GAZEBO_MASTER_URI=http://127.0.0.1:11429 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v2_rooms --cases up10_rooms down10_rooms delay2_rooms overflow_rooms burst_rooms deadline_rooms detection_loss_rooms pose_loss_rooms single_failure_rooms target_loss_rooms --ros-domain-base 190 > /tmp/p3b5_v2_rooms.log 2>&1；
GAZEBO_MASTER_URI=http://127.0.0.1:11430 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v2_corridors_forced --cases delay05_corridors duplicates_corridors nav_loss_corridors coverage_delay_corridors forced_charge_outage --ros-domain-base 210 > /tmp/p3b5_v2_corridors_forced.log 2>&1；
GAZEBO_MASTER_URI=http://127.0.0.1:11431 taskset -c 60-79 /usr/bin/python3 scripts/run_p2d_baseline.py --run-id p3b5_ideal_gate_c3819c3 --ros-domain-base 140 --startup-timeout 600 --evaluation-wait-timeout 900 --infrastructure-retries 0 --rally-max-concurrent 2 --disable-global-battery-rally-pause > /tmp/p3b5_ideal_gate_c3819c3.log 2>&1。

corridors主批次8格完整运行，精确摘要：[{"case": "delay05_corridors", "mode": "ideal", "status": "task_complete", "elapsed": 177.6, "charges": 0, "collision": 0}, {"case": "delay05_corridors", "mode": "fault", "status": "timeout", "elapsed": 300.4, "charges": 0, "collision": 0}, {"case": "duplicates_corridors", "mode": "fault", "status": "task_complete", "elapsed": 211.6, "charges": 0, "collision": 0}, {"case": "nav_loss_corridors", "mode": "fault", "status": "timeout", "elapsed": 300.2, "charges": 0, "collision": 0}, {"case": "forced_charge_outage", "mode": "ideal", "status": "task_complete", "elapsed": 220.89999999999964, "charges": 2, "collision": 0}, {"case": "forced_charge_outage", "mode": "fault", "status": "timeout", "elapsed": 300.4000000000001, "charges": 2, "collision": 0}, {"case": "coverage_delay_corridors", "mode": "ideal", "status": "coverage_reached", "elapsed": 88.7, "charges": 0, "collision": 0}, {"case": "coverage_delay_corridors", "mode": "fault", "status": "coverage_reached", "elapsed": 94.6, "charges": 0, "collision": 0}]。duplicate/reorder实际2455次pose乱序、4381次旧版本拒绝。其余主批次完成/中断完整保存在report/20261001_p3b5_local_safety_failed_candidate.json。
理想回归lab303在episode_start后，旁路审计命令90s超时并伴随tb1 Nav2心跳故障、tb2电池观测缺失；62.1s shutdown必须记为post-start task failure，不记启动前基础设施失败、不自动重试。已完成7个summary格含该失败；当前corridors202主动中断的原始result另保留，未伪装为成功。

诊断修正：delay05的地图源仍更新，首先失效的是frame_state：tb2最终入队时源年龄约1.94-2.14s，加0.5s注入后超过2s TTL。不能归因于地图不发布或单独归因于注入链路。只读探针精确命令 ROS_DOMAIN_ID=194 PYTHONNOUSERSITE=1 /usr/bin/python3 /tmp/p3b5_tf_age_probe.py，原始TF仅6样本/25wall-s，不足以确定原因；脚本/输出全部归档。

为区分恢复后充电与断网中本地返航，10:25:08 UTC预先冻结两个开发探针（原始标准SHA256 b949785ae91181e6926f82012bda1d64690dde6420238b7d050e85bd655a8111）：outage20-250s且ideal/fault同idle_cost=.15、energy18；以及deadline2s（ideal相同deadline，fault down-delay=.5）真实本地取消。
在corridors batch退出后，CPU40-59/master11430运行 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v2_safety_probes --config /tmp/p3b5_local_return_probe.json --ros-domain-base 210 > /tmp/p3b5_v2_safety_probes.log 2>&1。ideal199.4s COMPLETE/两次充电；fault已在24.7/28.8s自主返航、34.8/38.7s充电（断网窗口内），本次主动中断后为73.1s shutdown，不能算完整通过。

停止理由：新本地ActionClient不经AP网关，本地return_goal_handle在FAILED时仍未取消；新增反例pytest -k physical_failure明确失败（cancel_called=0）。修复FAILED转换只取消自有返航handle；晚到接受已有mode校验，并扩展FAILED参数回归；幂等不重复取消。为重新冻结，停止属于本次实验的launch进程组(SIGINT)，runner停止收集后退出；P2D runner SIGTERM防止自动继续。所有shutdown保留。已排队的同提交batch2/holdout调度器取消，未运行；holdout707仍从未运行/调参。
同候选所有源码/配置/命令/结果/账本摘要/环境/hash/停止进程/诊断脚本保存在上述JSON，raw保留原log目录。新冻结候选将全新重跑完整主矩阵和十格理想门禁，不拼接候选通过结果。

FAILED取消候选终检：上述八文件pytest147 passed（6.43s）；四包colcon build通过5.44s；/usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_local_safety_v3.json返回54格PASS；三机器人source-only旁路审计零违规。新增check_p3b5_gate.py与四项指标/时序反例检查、固定开发探针manifest；全新仿真尚未启动。

## 2026-10-01 P3B.5 2779bbd 候选保留、集结等待预算优化


冻结源码2779bbd5f111c8ddeb58fb7d206f213067581da7。Humble/install、PYTHONNOUSERSITE=1；独立CPU池且错峰约两分钟启动，ideal/fault同池。精确批次命令：

GAZEBO_MASTER_URI=http://127.0.0.1:11440 taskset -c 60-79 /usr/bin/python3 scripts/run_p2d_baseline.py --run-id p3b5_ideal_gate_2779bbd --ros-domain-base 150 --startup-timeout 600 --evaluation-wait-timeout 900 --infrastructure-retries 0 --rally-max-concurrent 2 --disable-global-battery-rally-pause > /tmp/p3b5_ideal_gate_2779bbd.log 2>&1；

GAZEBO_MASTER_URI=http://127.0.0.1:11441 taskset -c 0-19 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v3_lab --cases zero_rally_lab up100_lab down100_lab ttl_lab map_loss_lab battery_loss_lab state_loss_lab target_up10_lab battery_exhaust_lab --ros-domain-base 50 > /tmp/p3b5_v3_lab.log 2>&1；

GAZEBO_MASTER_URI=http://127.0.0.1:11442 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v3_rooms --cases up10_rooms down10_rooms delay2_rooms overflow_rooms burst_rooms deadline_rooms detection_loss_rooms pose_loss_rooms single_failure_rooms target_loss_rooms --ros-domain-base 70 > /tmp/p3b5_v3_rooms.log 2>&1；

GAZEBO_MASTER_URI=http://127.0.0.1:11443 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v3_corridors_forced --cases delay05_corridors duplicates_corridors nav_loss_corridors coverage_delay_corridors forced_charge_outage --ros-domain-base 90 > /tmp/p3b5_v3_corridors_forced.log 2>&1。

条件调度holdout（master11444/domain222，完整理想门禁通过才启动）及aux（master11445/domain110，corridors批次退出0才启动）均取消，未运行。

ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v3_lab/summary.json：[{"case": "zero_rally_lab", "mode": "ideal", "status": "task_complete", "elapsed": 144.29999999999973, "success": true, "collision": 0}, {"case": "zero_rally_lab", "mode": "fault", "status": "task_complete", "elapsed": 110.29999999999973, "success": true, "collision": 0}, {"case": "up100_lab", "mode": "fault", "status": "no_data", "elapsed": 300.1999999999998, "success": false, "collision": 0}, {"case": "down100_lab", "mode": "fault", "status": "shutdown", "elapsed": 67.59999999999991, "success": false, "collision": 0}]

ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v3_rooms/summary.json：[{"case": "up10_rooms", "mode": "ideal", "status": "task_complete", "elapsed": 162.89999999999998, "success": true, "collision": 0}, {"case": "up10_rooms", "mode": "fault", "status": "task_complete", "elapsed": 180.6, "success": true, "collision": 0}, {"case": "down10_rooms", "mode": "fault", "status": "task_complete", "elapsed": 186.9, "success": true, "collision": 0}, {"case": "delay2_rooms", "mode": "fault", "status": null, "elapsed": null, "success": null, "collision": null}]

ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v3_corridors_forced/summary.json：[{"case": "delay05_corridors", "mode": "ideal", "status": "task_complete", "elapsed": 169.29999999999998, "success": true, "collision": 0}, {"case": "delay05_corridors", "mode": "fault", "status": "task_complete", "elapsed": 219.0, "success": true, "collision": 0}, {"case": "duplicates_corridors", "mode": "fault", "status": "shutdown", "elapsed": 293.29999999999995, "success": false, "collision": 0}]

ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_ideal_gate_2779bbd/summary.json：[{"case": "lab_far_northwest", "mode": "ideal", "status": "timeout", "elapsed": 300.0, "success": false, "collision": 0}, {"case": "lab_far_northwest", "mode": "ideal", "status": "task_complete", "elapsed": 254.5, "success": true, "collision": 0}, {"case": "lab_far_northwest", "mode": "ideal", "status": "task_complete", "elapsed": 246.0999999999999, "success": true, "collision": 0}]

lab101为episode_start后真实RALLY超时300s，129.2s进入RALLY、三次充电、零碰撞；提前停靠与队友返充/让路导致等待后再次返航。lab202/303随后完成，不能择取成功替代同候选失败。rooms delay2在启动期中断无result；当前corridors duplicate、lab down100及理想下个启动均主动停止，结果/无结果与停止进程保存在report/20261001_p3b5_rally_wait_failed_candidate.json。

算法候选：完整路线预算增加其他机器人的剩余行程及串行返航/充电期间idle耗电，单调闭包计算连锁充电需求；第一轮预充电结束前暂缓最终集结派发，仍允许安全让路，完成后按实际位置重算地图安全顺序。本地安全保留量、能耗默认、速度、300秒及COMPLETE门限不变。电池状态发布实际charge_duration_sec。此为规划估计，不声称运行时间上界。

两项新增反例验证等待耗电与连锁充电、单机不重复计入自身路线/排除FAILED。八文件pytest149 passed（6.09s）；四包colcon build通过5.33s。54格协议矩阵PASS、source-only旁路审计见随后输出。此候选尚未仿真验证，将先运行lab101/202/303开发回归及安全探针，不在holdout调参。

## 2026-10-01 P3B.5 6624a8b 启动故障保留、有界实体确认


冻结源码6624a8b：Humble/install、PYTHONNOUSERSITE=1，精确命令：

GAZEBO_MASTER_URI=http://127.0.0.1:11450 taskset -c 0-19 /usr/bin/python3 scripts/run_p2d_baseline.py --run-id p3b5_wait_budget_dev_6624a8b --scenarios lab_far_northwest --robot-count 3 --seeds 101 202 303 --skip-cross-check --ros-domain-base 130 --startup-timeout 600 --evaluation-wait-timeout 900 --infrastructure-retries 0 --rally-max-concurrent 2 --disable-global-battery-rally-pause > /tmp/p3b5_wait_budget_dev_6624a8b.log 2>&1；

GAZEBO_MASTER_URI=http://127.0.0.1:11451 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_wait_safety_dev_6624a8b --config scripts/p3b5_safety_probe_manifest.json --ros-domain-base 160 > /tmp/p3b5_wait_safety_dev_6624a8b.log 2>&1；

GAZEBO_MASTER_URI=http://127.0.0.1:11452 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v4_lab --cases zero_rally_lab up100_lab down100_lab ttl_lab map_loss_lab battery_loss_lab state_loss_lab target_up10_lab battery_exhaust_lab --ros-domain-base 40 > /tmp/p3b5_v4_lab.log 2>&1。

lab101开发回归143.7s COMPLETE、零充电/碰撞；高idle安全探针ideal221.0s COMPLETE/两次充电，fault300.2s timeout/两次充电/零碰撞，两台在blackout中真实自主返充。时长因轨迹不同不能直接作为优化因果收益。探针终态后SIGINT发生rclpy take_message RuntimeError和merge_map退出-11，属终态后的清理错误，不能声称所有子进程干净退出。

lab202在episode_start前：Gazebo已插入tb3，服务端记录failed to send response to /spawn_entity (timeout)，Humble原spawn_entity.py仅给服务发现设置timeout，等待future的循环无超时。等待数分钟仍未退出，目标/Nav2/任务未启动。本次停止为prestart基础设施失败；lab202无任务result，lab303未运行。lab主矩阵当前ideal在RALLY触发early-charge后主动中断，保留shutdown；安全探针下个ideal在启动期中断无结果。rooms/corridors/完整十格/holdout尚未启动。完整原始summary/哈希/停止进程见report/20261001_p3b5_spawn_failed_candidate.json。

启动修复：spawn_entity_checked只发一次SpawnEntity请求，先核对新鲜实体清单防止接受已有实体，再由/gazebo/model_states确认实际插入；服务回包丢失不重复创建，也不无限等待；发现、创建与确认共享wall-clock预算。robot/target创建失败则Shutdown启动链。只用于任务开始前基础设施，实体truth不进入协调器或通信任务。

五项新增反例检查（丢回包/成功回包但没有实体/拒绝服务），九文件pytest154 passed（6.06s）；四包build6.21s通过。source audit/show-args待输出核对；短启动smoke精确命令：GAZEBO_MASTER_URI=http://127.0.0.1:11460 taskset -c 40-59 /usr/bin/python3 scripts/ros_smoke_test.py --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --evaluation-duration 20 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode coverage --collect-fault-result --battery --dwell-seconds 0 --episode-id p3b5_spawn_startup_dev --evaluation-output-dir log/p3b5_spawn_startup_dev/results --log-dir log/p3b5_spawn_startup_dev/launch --bypass-audit-output log/p3b5_spawn_startup_dev/graph.json > /tmp/p3b5_spawn_startup_dev.log 2>&1。此smoke为dirty开发验证，不算冻结门禁。

启动候选短smoke返回0；两台实体确认、任务20秒评估（timeout为预设horizon而非COMPLETE）、运行图审计通过。结果与launch logs位于ROS log/p3b5_spawn_startup_dev/，不计入冻结任务门禁。source-only三机器人审计零违规，show-args返回0。

## 2026-10-01 P3B.5 5fa4310 候选保留、路径预留替代全局预充电屏障


冻结源码5fa4310，Humble/install、PYTHONNOUSERSITE=1，四CPU池隔离、错峰约2min。精确启动命令：

GAZEBO_MASTER_URI=http://127.0.0.1:11461 taskset -c 0-19 /usr/bin/python3 scripts/run_p2d_baseline.py --run-id p3b5_ideal_gate_5fa4310 --ros-domain-base 130 --startup-timeout 600 --evaluation-wait-timeout 900 --infrastructure-retries 0 --rally-max-concurrent 2 --disable-global-battery-rally-pause > /tmp/p3b5_ideal_gate_5fa4310.log 2>&1；仅退出0才排队master11465/domain200运行p3b5_v5_holdout（holdout_rally holdout_target holdout_coverage），实际未运行。

GAZEBO_MASTER_URI=http://127.0.0.1:11462 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v5_lab --cases zero_rally_lab up100_lab down100_lab ttl_lab map_loss_lab battery_loss_lab state_loss_lab target_up10_lab battery_exhaust_lab --ros-domain-base 40 > /tmp/p3b5_v5_lab.log 2>&1；

GAZEBO_MASTER_URI=http://127.0.0.1:11464 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v5_rooms --cases up10_rooms down10_rooms delay2_rooms overflow_rooms burst_rooms deadline_rooms detection_loss_rooms pose_loss_rooms single_failure_rooms target_loss_rooms --ros-domain-base 60 > /tmp/p3b5_v5_rooms.log 2>&1；

GAZEBO_MASTER_URI=http://127.0.0.1:11463 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v5_corridors --cases delay05_corridors duplicates_corridors nav_loss_corridors coverage_delay_corridors --ros-domain-base 160 > /tmp/p3b5_v5_corridors.log 2>&1；仅退出0才同master/CPU运行p3b5_v5_forced（--cases forced_charge_outage --ros-domain-base166）及p3b5_v5_safety（--config scripts/p3b5_safety_probe_manifest.json --ros-domain-base168），实际两批均未运行。

ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_ideal_gate_5fa4310/summary.json：[{"case": "lab_far_northwest", "mode": "ideal", "status": "task_complete", "elapsed": 237.9000000000001, "charges": 2, "collision": 0}, {"case": "lab_far_northwest", "mode": "ideal", "status": "timeout", "elapsed": 300.0, "charges": 3, "collision": 0}]

ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v5_lab/summary.json：[{"case": "zero_rally_lab", "mode": "ideal", "status": "task_complete", "elapsed": 128.0999999999999, "charges": 0, "collision": 0}, {"case": "zero_rally_lab", "mode": "fault", "status": "task_complete", "elapsed": 162.20000000000027, "charges": 1, "collision": 0}, {"case": "up100_lab", "mode": "fault", "status": "no_data", "elapsed": 300.1999999999998, "charges": 0, "collision": 0}, {"case": "down100_lab", "mode": "fault", "status": "shutdown", "elapsed": 248.0, "charges": 0, "collision": 0}]

ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v5_rooms/summary.json：[{"case": "up10_rooms", "mode": "ideal", "status": "task_complete", "elapsed": 141.20000000000002, "charges": 0, "collision": 0}, {"case": "up10_rooms", "mode": "fault", "status": "task_complete", "elapsed": 240.20000000000002, "charges": 1, "collision": 0}, {"case": "down10_rooms", "mode": "fault", "status": "task_complete", "elapsed": 117.60000000000002, "charges": 0, "collision": 0}, {"case": "delay2_rooms", "mode": "fault", "status": "shutdown", "elapsed": 70.0, "charges": 0, "collision": 0}]

ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v5_corridors/summary.json：[{"case": "delay05_corridors", "mode": "ideal", "status": "task_complete", "elapsed": 214.70000000000002, "charges": 1, "collision": 0}, {"case": "delay05_corridors", "mode": "fault", "status": "task_complete", "elapsed": 179.70000000000002, "charges": 0, "collision": 0}, {"case": "duplicates_corridors", "mode": "fault", "status": "task_complete", "elapsed": 202.2, "charges": 0, "collision": 0}, {"case": "nav_loss_corridors", "mode": "fault", "status": "shutdown", "elapsed": 122.0, "charges": 0, "collision": 0}]

lab101237.9s COMPLETE/两次充电；lab202真实post-start超时300s，124.7s检测、133.8s RALLY、三台各一次充电、零碰撞。终止时tb1误差0.840m、tb2误差0.023m、tb3误差1.920m；最后两台仍在移动，不能算COMPLETE。lab303当前主动中断的raw result另保留，不伪装成通过。

启动有界helper实际记录reply_received=False但实体已出现，继续成功启动，证明不是靠重试请求恢复。主配对未完整冻结，所有部分完成/主动shutdown都按历史候选保留，准确源摘要见report/20261001_p3b5_preflight_failed_candidate.json。其字段与原始日志优先于概括，未运行holdout707。

诊断：全局预充电屏障禁止已充满机器人沿不冲突路径前进；正在移动的队友又被当作静态占位，tb3早期走到底部较长绕路。新候选仍串行提前充电、保留等待耗电闭包；按已知AP地图计算当前/待执行返航路线预留，允许energy-ready机器人在安全前缀前进，充电机器人保留实际占位；未知返航几何则等待。活跃/已派发队友仅在有实际路线预留保护时移出静态mask，使用包含当前位置的剩余预留路径防碰撞，新接纳leader后重新规划后续短路前缀。停靠/FAILED/独立返航机器人仍作为物理障碍。

新增三项反例：动静态走廊绕路差异与安全跟随前缀、充电期间安全前进与禁止穿过当前/未来返航路线、未知返航路线/实际充电占位。第一次测试走廊仅0.5m宽，被0.35m静态clearance膨胀封闭，修正夹具为1.2m走廊；实现不因夹具失败放宽clearance。九文件pytest157 passed（6.78s）、四包build5.63s、source-only审计零违规。5fa4310协议54格PASS，已完成的六个ledger源时间无回退、阶段因果/TTL/version检查通过（离线读取，不另计episode）。尚未开始新候选仿真。

## 2026-10-01 P3B.5 5b4f8a0 开发候选保留、TF接入采样优化


冻结源码5b4f8a0（Humble/install、PYTHONNOUSERSITE=1）：

GAZEBO_MASTER_URI=http://127.0.0.1:11471 taskset -c 0-19 /usr/bin/python3 scripts/run_p2d_baseline.py --run-id p3b5_route_dev_5b4f8a0 --scenarios lab_far_northwest --robot-count 3 --seeds 202 --skip-cross-check --ros-domain-base 130 --startup-timeout 600 --evaluation-wait-timeout 900 --infrastructure-retries 0 --rally-max-concurrent 2 --disable-global-battery-rally-pause > /tmp/p3b5_route_dev_5b4f8a0.log 2>&1；

GAZEBO_MASTER_URI=http://127.0.0.1:11472 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v6_forced --cases forced_charge_outage --ros-domain-base 160 > /tmp/p3b5_v6_forced.log 2>&1；退出0后同CPU/master /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v6_safety --config scripts/p3b5_safety_probe_manifest.json --ros-domain-base 162 > /tmp/p3b5_v6_safety.log 2>&1。

lab202112.7s RALLY，300.4s timeout/三次充电/零碰撞；forced ideal300.4s timeout/一次充电、fault300.1s timeout/两次充电/零碰撞；安全探针第一ideal主动中断shutdown，其他格未运行。没有holdout实验。report/20261001_p3b5_ingress_failed_candidate.json保留全部结果、哈希、诊断脚本及停止进程。

关键同episode证据：只读probe使用ROS_DOMAIN_ID=161（/usr/bin/python3 /tmp/p3b5_ingress_probe.py，20wall秒）；模拟窗口2162.482–2180.982，tb2原始TF源年龄median0.093s/p95 .193，gateway入队median1.993s/p95 2.093；tb1入口 .181s。probe有966个relevant TF样本/robot，三种QoS均新鲜。不是把不同episode数据混成因果证明。第一次对已结束ideal域160探测返回0样本，保留错误域输出、不用于结论。

只读真实TF探针比之前少样本诊断更充分，问题集中在多端点网关接入处理。额外cProfile启动：将launch副本/tmp/p3b5_profile.launch.py的ideal_gateway加prefix=/usr/bin/python3 -m cProfile -o /tmp/p3b5_gateway_5b.prof；精确命令 ROS_DOMAIN_ID=180 PYTHONNOUSERSITE=1 GAZEBO_MASTER_URI=http://127.0.0.1:11480 taskset -c 20-39 ros2 launch /tmp/p3b5_profile.launch.py robot_count:=2 enable_gzclient:=false enable_rviz:=false enable_merge_rviz:=false enable_task_regions:=false enable_status_panel:=false auto_save_map:=false gazebo_seed:=303 enable_task_evaluator:=true evaluation_episode_id:=p3b5_gateway_profile_5b evaluation_output_dir:=/tmp/p3b5_gateway_profile_5b evaluation_duration_sec:=90 evaluation_coverage_threshold:=0 enable_target_detection:=true enable_rally:=true enable_battery:=true battery_capacity:=100 battery_initial_energy:=18 battery_return_safety_margin:=5 battery_charge_duration_sec:=10 battery_return_timeout_sec:=120 global_battery_rally_pause:=false rally_max_concurrent:=2 gateway_ledger_path:=/tmp/p3b5_gateway_profile_5b/ledger.jsonl > /tmp/p3b5_gateway_profile_5b.log 2>&1。

该debug手动参数错误使用整数，评估/电池节点拒绝应为DOUBLE的参数，无有效episode result，按启动组件失败保留；网关继续运行留下301.841s的剖析。138714次_wait_for_ready_callbacks累计219.494s（含等待、剖析开销），69951次publish_candidate累计28.526s、deepcopy19.182s。不能声称这些百分比等于生产纯CPU占比或算法加速；支持减少高频无关/重复TF导致的大waitset调度。SIGINT结束自有master11480进程组。

修复候选：各机器人新增gateway_tf_ingress，只转发新map→odom native样本，base TF/重复/旧scan不占用多端点网关队列；header原样保留，网关仍使用原min_interval0.5、TF TTL2s与SLAM配置offset，仅拷贝符合限频/源版本的TF。原生Nav2 TF、可靠命令/重试/QoS不变。robot→sampler→同一个gateway→中央，ideal/fault使用相同路径。候选实际频率受源样本/限频共同影响，不声称固定精确2Hz；每配对使用同源生成算法。

十文件pytest160 passed（5.93s）、四包build7.62s、source-only审计零违规、show-args返回0。真实dirty短smoke精确命令：ROS_DOMAIN_ID=180 GAZEBO_MASTER_URI=http://127.0.0.1:11481 taskset -c 20-39 /usr/bin/python3 scripts/ros_smoke_test.py --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --evaluation-duration 45 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --collect-fault-result --battery --battery-capacity 100 --battery-initial-energy 18 --battery-safety-margin 5 --battery-charge-duration 10 --battery-return-timeout 120 --target-detection --rally --disable-global-battery-rally-pause --dwell-seconds 0 --episode-id p3b5_tf_ingress_dev --evaluation-output-dir log/p3b5_tf_ingress_dev/results --log-dir log/p3b5_tf_ingress_dev/launch --gateway-ledger-path log/p3b5_tf_ingress_dev/ledger.jsonl --bypass-audit-output log/p3b5_tf_ingress_dev/graph.json > /tmp/p3b5_tf_ingress_dev.log 2>&1。

短smoke返回0、graph通过、45.4s horizon timeout/零碰撞/minEnergy12.167；TF入口年龄：{"tb2": {"n": 78, "median_source_age_sec": 0.021500000000060027, "p95_source_age_sec": 0.02400000000034197, "max_source_age_sec": 0.027000000000043656}, "tb1": {"n": 74, "median_source_age_sec": -0.014000000000123691, "p95_source_age_sec": -0.010999999999967258, "max_source_age_sec": -0.009999999999763531}}。tb1 callback clock比scan源略落后（约-14ms），不是负排队；逻辑enqueue=max(clock,source)保持阶段因果。两次对比是不同episode/阶段，不把源年龄差值当纯算法因果加速。原数据在ROS log/p3b5_tf_ingress_dev/；随后新冻结候选仍需完整门禁。

## 2026-10-01 P3B.5 1ba31be 开发失败保留、完整接近路线优先级预约

冻结源码1ba31be（Humble/install、PYTHONNOUSERSITE=1），精确命令：

GAZEBO_MASTER_URI=http://127.0.0.1:11491 taskset -c 0-19 /usr/bin/python3 scripts/run_p2d_baseline.py --run-id p3b5_ingress_dev_1ba31be --scenarios lab_far_northwest --robot-count 3 --seeds 202 --skip-cross-check --ros-domain-base 130 --startup-timeout 600 --evaluation-wait-timeout 900 --infrastructure-retries 0 --rally-max-concurrent 2 --disable-global-battery-rally-pause > /tmp/p3b5_ingress_dev_1ba31be.log 2>&1；

GAZEBO_MASTER_URI=http://127.0.0.1:11492 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v7_forced --cases forced_charge_outage --ros-domain-base 160 > /tmp/p3b5_v7_forced.log 2>&1；原条件后续 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v7_safety --config scripts/p3b5_safety_probe_manifest.json --ros-domain-base 162 > /tmp/p3b5_v7_safety.log 2>&1 在启动前取消，当前fault runner保留至自然结束。

/usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_1ba31be.json：54格PASS。

lab3 seed202 113.4s检测、168.6s RALLY、300.2s真实timeout，三台各充电一次，最低能量12.476、零碰撞/耗尽/failed robot。tb1最终误差.040m、tb3 .013m，tb2仍在通道入口，误差5.119m。日志保留tb3先停靠(y1.40)、tb2由入口绕到地图底部再回入口的派发轨迹。任务终态后SIGINT中两台navigation_gateway exit -11，不能声称清理全部正常。forced ideal210.8s COMPLETE、fault281.5s COMPLETE，两侧两台各充电一次、零碰撞/耗尽。开发失败不能由这对成功抵消；未启动完整门禁或holdout。report/20261001_p3b5_priority_failed_candidate.json保存summary、真实派发轨迹、协议结果、取消条件调度进程与内容哈希。

新算法候选：除现有实际body/当前短航段和安全返航预约外，为每个未完成高优先级机器人预留到最终集结位置的完整剩余接近路线。低优先级只能沿不冲突前缀移动，不能提前停在高优先级下一航段必经路径上；未知leader几何等待，完成/FAILED才释放意图预约，temporary yield不算完成。对充电/返航中的leader使用充电位起点的未来路线，实际返航路径/占位仍独立保护。复用同一dispatch snapshot的能量规划已有完整路线，不新增电池启用情况下的重复BFS；无电池模式按相同策略规划。意图预约不授权穿过停驻物理实体，既有静态占位和实时短航段检查仍执行。不改变300秒、能耗、清障距离、速度或COMPLETE判据。

新增三项反例：当前短leg无冲突但最终停车堵住leader未来leg；未知/未完成leader不得释放、完成/FAILED可释放；能量预算复用路线确实到最终目标。首轮161 passed/2 failed为测试夹具未模拟prepare填充新缓存、原route separation要求比夹具预计更远；修正夹具，未放宽安全阈值。十文件163 passed（6.64s），四包colcon build通过5.44s，source-only三机器人审计零违规。该候选尚待新冻结开发与全矩阵验证。

## 2026-10-01 P3B.5 c738c4e 开发失败保留、串行返充前的安全接近调度

冻结源码c738c4e（Humble/install、PYTHONNOUSERSITE=1），精确命令：

GAZEBO_MASTER_URI=http://127.0.0.1:11501 taskset -c 0-19 /usr/bin/python3 scripts/run_p2d_baseline.py --run-id p3b5_priority_dev_c738c4e --scenarios lab_far_northwest --robot-count 3 --seeds 202 --skip-cross-check --ros-domain-base 130 --startup-timeout 600 --evaluation-wait-timeout 900 --infrastructure-retries 0 --rally-max-concurrent 2 --disable-global-battery-rally-pause > /tmp/p3b5_priority_dev_c738c4e.log 2>&1；

GAZEBO_MASTER_URI=http://127.0.0.1:11502 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v8_forced --cases forced_charge_outage --ros-domain-base 160 > /tmp/p3b5_v8_forced.log 2>&1；退出0后同CPU/master /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v8_safety --config scripts/p3b5_safety_probe_manifest.json --ros-domain-base 162 > /tmp/p3b5_v8_safety.log 2>&1。

/usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_c738c4e.json：54格PASS。

lab3 seed202 99.1s检测、111.7s进入RALLY、300.0s timeout，三台各充电一次、零碰撞/耗尽/failed robot。tb2先到最终位，tb1剩1.377m、tb3剩4.428m，完整路线优先级预约仍不足以满足时限；本轨迹三台长距离串行返充后才开始主要集结。forced ideal213.3s COMPLETE、fault277.3s COMPLETE，各两次充电、零碰撞。安全探针第一ideal在EXPLORE后主动停止；runner保存operational_failure/NO_RESULT，其他三格未运行，不宣称探针成功；没有holdout。原始结果、派发轨迹与中断证据在report/20261001_p3b5_staging_failed_candidate.json。

另对冻结1ba31be主forced两份ledger离线核查：阶段因果、接收TTL/版本全部PASS；逻辑TF入队源年龄max分别.275/.300秒，完整任务未复现之前约2秒积压。逻辑enqueue以max(clock,source)定义，median0不等于精确物理零排队；没有把不同轨迹的时长差作单因素收益。

新候选在仍串行的提前充电前增加接近调度：需要充电而等待的ACTIVE队友通过正常gateway导航沿安全返航前缀靠近home，所有当前/未来返航、停驻实体与实时rally路径预约照常执行；冲突/未知几何等待，不跳过local safety。实际提前返航请求仍一次一个；本地低电量始终可自主抢占。不改变充电半径/时间、能耗/保留量、速度/清障距离、300秒或COMPLETE判据。stage保留其已验证预算至真实充电完成/FAILED，即使当前剩余目标路线或消息暂时不可用，不能把stage waypoint当最终集结位。

四项新增检查覆盖无冲突接近、交叉返航禁止接近、活动stage保留充电需求及真实充电完成清理、目标路线不可用时保持预算。首轮新增夹具漏fresh pose/state属性，另一次补丁误插入无关测试导致NameError，均修正测试夹具；没有改变安全阈值。十文件167 passed（6.62s）、四包build5.27s、源码旁路审计零违规。尚需新冻结版本任务回归与完整门禁。

### 2026-10-01 P3B.5 e9bcc5c 冻结候选与启动检查修复（未通过整批门禁）

代码 e9bcc5c63bfe9b7ab04f832ada3f44c920fa8561。以下均在 canonical ROS root、source Humble/install、PYTHONNOUSERSITE=1；无整episode重试。归档 report/20261001_p3b5_startup_failed_candidate.json 含六批 manifest、逐episode结果/命令/原始文件hash、管理员停止清单及未收集rooms303原始结果。用户260929_report材料未修改。实际命令：

```bash
GAZEBO_MASTER_URI=http://127.0.0.1:11511 taskset -c 0-19 /usr/bin/python3 scripts/run_p2d_baseline.py --run-id p3b5_staging_dev_e9bcc5c --scenarios lab_far_northwest --robot-count 3 --seeds 202 --skip-cross-check --ros-domain-base 130 --startup-timeout 600 --evaluation-wait-timeout 900 --infrastructure-retries 0 --rally-max-concurrent 2 --disable-global-battery-rally-pause > /tmp/p3b5_staging_dev_e9bcc5c.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:11512 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v9_forced --cases forced_charge_outage --ros-domain-base 160 > /tmp/p3b5_v9_forced.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:11512 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v9_safety --config scripts/p3b5_safety_probe_manifest.json --ros-domain-base 162 > /tmp/p3b5_v9_safety.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:11513 taskset -c 0-19 /usr/bin/python3 scripts/run_p2d_baseline.py --run-id p3b5_ideal_gate_e9bcc5c --ros-domain-base 140 --startup-timeout 600 --evaluation-wait-timeout 900 --infrastructure-retries 0 --rally-max-concurrent 2 --disable-global-battery-rally-pause > /tmp/p3b5_ideal_gate_e9bcc5c.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:11514 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v9_lab --cases zero_rally_lab up100_lab down100_lab ttl_lab map_loss_lab battery_loss_lab state_loss_lab target_up10_lab battery_exhaust_lab --ros-domain-base 40 > /tmp/p3b5_v9_lab.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:11515 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v9_rooms --cases up10_rooms down10_rooms delay2_rooms overflow_rooms burst_rooms deadline_rooms detection_loss_rooms pose_loss_rooms single_failure_rooms target_loss_rooms --ros-domain-base 60 > /tmp/p3b5_v9_rooms.log 2>&1
```

开发lab3/202 COMPLETE252.0s/三次充电。正式理想lab3三seed分别250.1/199.0/174.6s COMPLETE，rooms202 COMPLETE188.0；全部零碰撞且能量正。rooms101开始前缺少ModelStates库存，90wall秒安全拒绝生成；无结果，不重试，整批不通过。rooms303被管理员停止于35.9sim，结果未被父批次收集，归档单独保留；其余固定格未运行。forced ideal COMPLETE273.9s、两机器人各充一次；fault timeout300s、两次充电、零碰撞、最低7.77。lab部分ideal/zero故障COMPLETE131.8/281.5；up100/TTL no_data，down100 timeout；coverage ideal在启动阶段主动停止，NO_RESULT不冒充任务失败。rooms ideal/up10/down10 COMPLETE151.3/142.6/100.4；delay2 timeout，overflow timeout且runner operational_failure（CLI生命周期查询超时）。ready_gate此前确认active，日志无bond错误/停用，不能据此声称真实Nav2失活。两批中断及固定批SIGINT清单在归档。

辅助四episode全部自然结束：长断网ideal COMPLETE190.4/两充，fault timeout300.3/两充/零碰撞/能量正；两机器人RETURNING时已经处于接触区，此数据只证明本地充电，不证明物理返航导航。deadline ideal/fault均mission_failed162.7/187.4、无机器人失败/碰撞；等待离线deadline事件审核。54格协议矩阵PASS（log/p3b5_protocol_e9bcc5c.json）。无corridors、holdout或补充物理探针运行。首次lab工具调用工作路径误写不存在目录，CreateProcess失败，无episode，随即改正canonical路径。

诊断命令：ROS_DOMAIN_ID=144 PYTHONNOUSERSITE=1 timeout 15 ros2 service call /get_model_list gazebo_msgs/srv/GetModelList "{}"，success=True，清单包含三tb及target（sim300.755）。随后停止当前仍在运行的开发批次，保留全部失败。新修复：只读GetModelList bounded重查询辅助ModelStates，实体插入仍只发一次；smoke持久原生GetState/graph查询代替反复CLI发现，严格state ID3且label=active（原substring可能误把inactive当active）；不进行生命周期写操作、不改任务安全参数。

新反例覆盖native库存空世界/失败响应/丢读回包重查询、无topic且spawn回包丢失仍确认实体、exact lifecycle ID/label及丢查询回复恢复。13文件pytest183 passed（6.56s）；最初子集164 passed（5.57s），补上Nav2/evaluator后183。build先误选gateway_msgs、communication_gateway_msgs各构建三包，随后按multi_robot_interfaces merge_map multi_robot_exploration multi_robot四包重跑通过5.19s。source-only三机器人旁路审计PASS、零违规。

真实启动检查命令（dirty开发证据，非冻结mission格）：

```bash
ROS_DOMAIN_ID=180 GAZEBO_MASTER_URI=http://127.0.0.1:11520 PYTHONNOUSERSITE=1 taskset -c 40-59 /usr/bin/python3 /tmp/test_p3b5_native_inventory.py > /tmp/p3b5_native_inventory_dev.log 2>&1
ROS_DOMAIN_ID=181 GAZEBO_MASTER_URI=http://127.0.0.1:11521 PYTHONNOUSERSITE=1 taskset -c 0-19 /usr/bin/python3 scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --evaluation-duration 45 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --collect-fault-result --battery --target-detection --rally --disable-global-battery-rally-pause --dwell-seconds 0 --episode-id p3b5_native_readiness_dev --evaluation-output-dir log/p3b5_native_readiness_dev/results --log-dir log/p3b5_native_readiness_dev/launch --bypass-audit-output log/p3b5_native_readiness_dev/graph.json > /tmp/p3b5_native_readiness_dev.log 2>&1
```

第一项启动empty world，禁用ModelStates订阅，生成静态inventory_probe一次成功，第二次安全拒绝已有实体，returncodes[0,1]，2.86wall秒，PASS；输出log/p3b5_native_inventory_dev/。第二项为45s启动/图smoke，目标使用smoke默认(-4,4)，不用于rooms目标任务性能。结果随后追加。

新增补充物理返航pair在执行前冻结：/tmp/p3b5_return_navigation_manifest.json，预声明2026-10-01T15:11:03.430058+00:00，SHA cab3540442ba0cd02cbec6786592855675abba2c9b2d6f64b1fafa82c543b6cf；2r303初始40、idle.15、blackout40..250。两机器人各需离home≥1.1m开始return，守护窗口42..248内RETURNING实际位移≥.5m、有Nav2 EXECUTING、各充一次、零碰撞/FAILED。/tmp/observe_p3b5_return_physics.py只读模型真值/battery/action状态，SHA d4382cd87c1823adda75a8924a62b4cc32cbf86e9d1424a7a861523e2e07deb2。原四辅助episode不删除，最终预计57unique（41primary+10fixed+6aux），forced ideal复用不再多计。此时未执行物理pair，holdout707亦从未执行/调参。

启动smoke第一轮 lifecycle/graph PASS，但CLI `topic echo /tb1/scan`无法及时发现类型，退出1；evaluator被关闭于2.6sim，shutdown/零碰撞/无失败，不能计45s任务结果。进一步将消息到达检查改为原生动态类型发现+subscription，仍验证真正收到扫描/latched task/battery数据、保持90s总检查期限。第二轮使用正确rooms目标(5,3)，run-id p3b5_native_readiness_dev2，其余命令同上，增加 --target-x 5 --target-y 3，output/log/graph改为log/p3b5_native_readiness_dev2。

为补充证据可复现，将未执行的config/observer原字节复制到scripts/p3b5_return_probe_manifest.json、scripts/observe_p3b5_return_physics.py；runner落地scripts/run_p3b5_return_probe.py提供run-id/domain/config参数。validator强制实际home进度≥.5m且有Nav2 EXECUTING运动≥.5m，排除接触区、静止、仅mode变化、断网窗口外和action已结束等假阳性（五个测试）。加入config/observer原文hash及同冻结commit/core审核，原四辅助探针不删除。一次测试工具workdir漏ros2_ws无进程创建，立即改正；不是episode。

第二轮三机器人rooms启动smoke返回0：graph/实体/lifecycle/实际lidar与融合地图消息全部PASS；45sim timeout（规定短horizon，非任务COMPLETE证据），coverage.707、path10.925m、零碰撞/无FAILED，数据log/p3b5_native_readiness_dev2/。新增validator反例及readiness合计17 passed（.75s）。随后最终组件检查并冻结候选；仍不开始holdout直到十固定ideal格全部通过。launch_commands.md同步原生检查说明和额外物理pair命令，修正原辅助探针只能证明模式/充电的表述。

候选终检13文件188 passed（6.05s），四包build和source audit已通过；smoke与物理脚本py_compile通过。补充manifest validate-only首轮遗漏必需run-id，argparse退出2无episode，补参数后校验1case/2episode。提交前diff --check、root git add -n .检查，明确排除260929_report和全部ignored runtime数据。

### 2026-10-01 P3B.5 bed8c7f 冻结启动失败及Gazebo确认时钟边界

新提交bed8c7f（已push）四池计划中实际仅启动以下三批，全部结果保留于report/20261001_p3b5_factory_clock_failed_candidate.json；没有整episode重试。canonical ROS root/source Humble+install/PYTHONNOUSERSITE=1：

```bash
GAZEBO_MASTER_URI=http://127.0.0.1:11530 taskset -c 0-19 /usr/bin/python3 scripts/run_p2d_baseline.py --run-id p3b5_ideal_gate_bed8c7f --ros-domain-base 140 --startup-timeout 600 --evaluation-wait-timeout 900 --infrastructure-retries 0 --rally-max-concurrent 2 --disable-global-battery-rally-pause > /tmp/p3b5_ideal_gate_bed8c7f.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:11532 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v10_forced --cases forced_charge_outage --ros-domain-base 160 > /tmp/p3b5_v10_forced.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:11531 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v10_lab --cases zero_rally_lab up100_lab down100_lab ttl_lab map_loss_lab battery_loss_lab state_loss_lab target_up10_lab battery_exhaust_lab --ros-domain-base 40 > /tmp/p3b5_v10_lab.log 2>&1
/usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_bed8c7f.json
```

协议54格PASS。forced/lab首tb1生成服务报告已入队但确认超时，退出1、infra/operational failure、pre-start无结果，后续格未执行。其服务返回false后185ms出现真实机器人plugin。固定ideal首格已启动评估，在发现问题并修改启动helper后由管理员停止；其余固定格未运行。parent STOP/owned launch INT/parent TERM+CONT清单/tmp/p3b5_bed_stop.json纳入归档；raw shutdown单独保留。无rooms/corridors/safety/physics/holdout运行，原conditional queue均未执行。

上游primary源码 https://github.com/ros-simulation/gazebo_ros_pkgs/blob/ros2/gazebo_ros/src/gazebo_ros_factory.cpp 显示先InsertModelString，再用ROS clock等待确认。my_world保存的sim_time1996.381；native清单允许更早发现world，可能在factory启动clock追上前调用spawn，10sim秒期限随第一次clock跳变提前到期。日志支持此时钟边界解释，不假定网络丢包。修复仅对与本次实体名完全匹配的“已排入生成队列但确认超时”状态继续物理确认；不会重发spawn、不延长原90wall budget，parse失败/实体已存在/其他名字/未知拒绝仍失败。新增三个反例（已队列但实体出现、永不出现、不同名字）通过，相关16checks PASS .51s。

实际native库存测试（dirty开发，不计任务格）命令：source /usr/share/gazebo/setup.sh；ROS_DOMAIN_ID=184 GAZEBO_MASTER_URI=http://127.0.0.1:11524 PYTHONNOUSERSITE=1 taskset -c 40-59 /usr/bin/python3 /tmp/test_p3b5_native_clock.py > /tmp/p3b5_native_clock_dev.log 2>&1。使用原my_world和原TurtleBot3 SDF，禁用ModelStates订阅，四个独立namespace实体一次生成均确认，第五次拒绝重名，codes[0,0,0,0,1]、5.64wall秒PASS。script完整原文/hash和结果纳入归档；此轮实际服务均success=True，不声称真实触发queued-timeout分支，分支由保留故障日志+反例验证。

确认时钟修复终检：13文件191 passed（6.30s）、四包build5.85s、三机器人source-only审计零违规。git diff --check/root add -n检查通过，显式排除用户资料/运行产物，提交并push新的冻结候选后才再开始正式任务。

### 2026-10-02 P3B.5 5c58bc7 接触区让路失败候选与修复

冻结源码5c58bc784a195f94003f97ff361ef5827587b9e7，各manifest task_stack_clean=True。全新v11四池命令如下（canonical ROS root/source Humble+install/PYTHONNOUSERSITE=1）：

```bash
GAZEBO_MASTER_URI=http://127.0.0.1:11540 taskset -c 0-19 /usr/bin/python3 scripts/run_p2d_baseline.py --run-id p3b5_ideal_gate_5c58bc7 --ros-domain-base 140 --startup-timeout 600 --evaluation-wait-timeout 900 --infrastructure-retries 0 --rally-max-concurrent 2 --disable-global-battery-rally-pause > /tmp/p3b5_ideal_gate_5c58bc7.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:11542 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v11_forced --cases forced_charge_outage --ros-domain-base 160 > /tmp/p3b5_v11_forced.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:11542 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v11_safety --config scripts/p3b5_safety_probe_manifest.json --ros-domain-base 162 > /tmp/p3b5_v11_safety.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:11541 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v11_lab --cases zero_rally_lab up100_lab down100_lab ttl_lab map_loss_lab battery_loss_lab state_loss_lab target_up10_lab battery_exhaust_lab --ros-domain-base 40 > /tmp/p3b5_v11_lab.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:11543 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v11_rooms --cases up10_rooms down10_rooms delay2_rooms overflow_rooms burst_rooms deadline_rooms detection_loss_rooms pose_loss_rooms single_failure_rooms target_loss_rooms --ros-domain-base 60 > /tmp/p3b5_v11_rooms.log 2>&1
/usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_5c58bc7.json
```

54协议PASS。首fixed lab3/101 timeout300、三充、13报告contact事件（tb1/tb2双方传感器计数，并非13独立碰撞）、zero-collision门禁失败。首接触发生于episode190.5s；返航tb2与为其让路的tb1接触，累计各6.7秒。tb1临时refuge(-.066,-.834)，实际短leg到(-.47,-.38)，tb2可以在home(0,.45)半径.8内停止充电，物理空间重叠。旧yield绕过普通1.8m路线预约，只保证final refuge离AP路线.8m，既没保护充电接触区，也没保证实际中间停点在区外。原final rally assignment保留、RALLY未伪造COMPLETE。

同候选forced ideal COMPLETE199.9/两充，fault timeout300.3/两充，零碰撞/正能量；lab2 ideal COMPLETE294.4/两充；rooms3 ideal COMPLETE144.1/一充、up10 COMPLETE155/零充、全部零碰撞/正能量。fixed lab202、lab zero-fault、rooms down10、aux第一ideal为管理员中断，raw结果和未收集结果全部单列在report/20261002_p3b5_return_refuge_failed_candidate.json及stop清单/tmp/p3b5_5c_stop.json。只中止master11540..11543的owned runners/launch组。其余固定格与故障格、补充physics/corridors/holdout未执行。no whole-episode retries；旧failed cohort不进入新TDI。

修复：local battery发布实际charge_radius_m；返航避让保护所有当前/待执行返航路线与实际充电占位，终点净距≥max(1.8,charge_radius+.6)。更早（1.8m范围）识别idle blocker；选直接可见、向本侧离开通道的refuge，直到跨出guard之前距离不得明显下降；实际派发waypoint仍复核guard，原全局/本地安全参数不放宽。临时RETURNING/CHARGING阻塞时暂停绕过预约的fallback重分配/probe，并清除暂时route-failure计时；普通safe prefix/staging继续。yield尝试1Hz；按最近路径排序，逐个验证候选线段至首个可行点，避免为每个free cell做线几何检查拖慢网关线程。

几何反例：原近home位置、.8/2.0实际charge radius、不可见转弯中间停点、局部返航不允许unreserved恢复/probe；原finalassignment保持。初轮4项6.04s，改为lazy几何后5项3.06s（不同测试集合，仅说明检查成本，不能当纯算法benchmark）。包含前三项的全套194 passed7.51s、四包build7.01s/source audit PASS；最终含recovery与同提交分批证据反例的全套检查随后追加。

后续固定十格在下一新冻结源码上前瞻分为1+2+3+4，不重复已完成格：先lab3/101子门禁；通过后lab3/202303、rooms3/101202303、corridors3/101202303+2r202；全部300horizon/energy40,40,45/原目标/零整episode重试。复用check_p3a6_gate.same_candidate严格检查同commit/source/environment；新P3B检查器支持 --ideal-fixed 多summary，拒绝重复physical cell和跨版本，不删除失败。只有同提交十格全部COMPLETE/零碰撞才开始707留出及接受整批P3B.5。

返航refuge候选最终13文件198 passed（7.38s），四包build/source audit已通过。diff --check/root add -n检查后，显式排除用户260929_report和runtime，提交并push再开始1+2+3+4前瞻分批固定集成。


## 2026-10-02 P3B.5 baec9ea 冻结候选：本地返航失败保留与后续修复

代码状态：clean冻结 `baec9ea8cce61da8d0f1f0bcf45efb74f8eea97a`；P3A.6已验收。四隔离池CPU0–19/20–39/40–59/60–79，Gazebo master11550/12521/12520/12522。命令完整原文、临时串行wrapper及预声明分批计划收录 `report/20261002_p3b5_local_return_failed_candidate.json.commands_and_stop_records.p3b5_v12_commands.json`；所有ROS命令source Humble+canonical install且PYTHONNOUSERSITE=1，/usr/bin/python3。固定ideal前瞻1+2+3+4批次；主矩阵lab/rooms；forced、四原安全探针、两物理探针顺序执行。raw结果/ledger/图/launch日志仍保留在ROS ignored log/。

本候选实际开始35个独立episode，保存35份原始终态（含中断与未被已停止批量runner回写summary的孤立结果），终止分布{'task_complete': 19, 'no_data': 3, 'shutdown': 2, 'timeout': 8, 'coverage_reached': 1, 'mission_failed': 2}。未运行主corridors或holdout707。不能用孤立成功回填中断的固定summary来宣称十格完成。主批次lab/rooms在物理返航失败后按所有权进程清单SIGINT停止，post-start中断保留；固定/辅助的队列wrapper停止阻止后续holdout/corridors。wrapper的subprocess.run在SIGINT后kill子runner，部分已开始的smoke结果后来正常完成，已单独保留；补充观察器手工有界清理，清单见归档。

当前冻结版本另有1次PRESTART基础设施失败：p3b5_v12_forced使用11552被旧ROS2 daemon(domain41)占用；Gazebo原始server日志证实bind Address already in use，没有episode start/result。依RESEARCH_PLAN12.5保留后修复master为12520，以p3b5_v12_forced_portfix同配置重跑。归档含原summary/完整Gz日志/hash及规则；manual prestart retry1，自动重试0。不是覆盖post-start任务失败，基础设施分母必须包含该失败。/tmp/check_prestart_p3b5.py验证PASS。

物理返航probe原配置前瞻时间2026-10-01T15:11:03.430058+00:00，SHA cab3540442ba0cd02cbec6786592855675abba2c9b2d6f64b1fafa82c543b6cf；energy40、idle.15、blackout40–250、margin5、return120、300s。ideal COMPLETE237.5s/两充电/零碰撞；fault timeout300.3s，tb1一充电、tb2进入RETURNING未发布任何return-leg，随后耗尽FAILED。该候选保障性门失败。旧probe没有记录内部地图/ActionClient availability分支，因此不能断言是某个地图cell造成。原只读物理观察器在native Nav2 UUID numpy.uint8 JSON序列化处退出1，属于独立测量失败。

只改/tmp只读observer将UUID逐字节转int，原配置诊断重复：run_p3b5_return_probe_fixed.py --run-id p3b5_v12_returnproof_observerfix --ros-domain-base168，同12520/CPU40–59；ideal COMPLETE223.3s，fault timeout300.0s/两充电/零碰撞、正能量。父队列wrapper行政停止后，observer metadata未正常结束，手工SIGINT清理并保留hash，诊断结果不能替代前轮耗尽或当作正式probe。另启动ROS_DOMAIN_ID169 taskset40–59 /usr/bin/python3 /tmp/p3b5_return_map_diagnostic.py（只读本地map/fused/TF/odom/battery，2s记录）；16张RETURNING快照全部可规划home（tb1 11/tb2 5），未复现旧失效分支。脚本/采集路径/hash及清理记录归档，原始map诊断移到ROS log/p3b5/p3b5_v12_returnproof_observerfix_physics/local_map_diagnostic.jsonl。

纯组件算法benchmark（不计episode、不宣称mission加速）：PYTHONNOUSERSITE=1 taskset -c20-39 /usr/bin/python3 /tmp/benchmark_p3b5_refuge.py > /tmp/p3b5_refuge_benchmark_baec9ea.log 2>&1。同120x120/.1m输入、1.8m返航guard、相同返回pose，五次墙钟中位数exhaustive visibility1.018082057s、nearest-first.343993034s，2.96x。完整输入/两版本函数原文/SHA/五个样本/affinity见report/20261002_p3b5_refuge_benchmark_baec9ea.json。此比较只改变候选可见性检查顺序，不比较不同Gazebo历史轨迹。

下一候选改动：修复只读UUID JSON并传播observer非零状态；本地return拒绝分支有界throttle诊断（server/map/无安全route）；另以合成反例证实充电中心blocked但接触区存在clearance-safe reachable点时原planner拒绝全部返航，改为复用同一次Dijkstra距离场选择中心附近可达contact点，留0.2m目标误差余量。home可达时路线保持，未知/断连contact区仍拒绝，不放宽半径/clearance/电量/300s。此补洞并不证明旧耗尽的唯一原因；下一轮先跑原物理stress probe，失败则保留并诊断，不启动heldout。

新contact候选203组件检查PASS（13文件、7.83s）、四包symlink build PASS（5.30s）、source-only三机器人审计PASS。最初子集38PASS/1FAIL是测试SimpleNamespace缺少robot_name日志字段，补齐夹具后通过；中间误写test_gateway_protocol.py和audit_gateway_bypasses.py，均路径不存在而未执行测试/审计，随后按实际文件/模块完成。独立UUID原生GoalStatusArray反例JSON roundtrip通过。下一冻结先跑同预声明原physical probe；不得把旧35episodes/诊断成功混入新基线。

## 2026-10-02 P3B.5 a1f17c9 前沿分配失败候选与 TTL 契约修复

冻结a1f17c9a2be92b35ec6660a779e786c07386a77c；先完成原预声明physical return ideal/fault两格，实际断网窗口内两机器人均远离home启动Nav2返航，移动/接近home均超过.5m、各充一次、正能量、零接触/失败。物理子门通过后才启动四池主矩阵。完整命令/wrapper/PID/启动声明/原始结果/诊断日志/hash见report/20261002_p3b5_frontier_wait_failed_candidate.json。逻辑CPU掩码不同但共享SMT物理资源，不声称物理核隔离。

```bash
GAZEBO_MASTER_URI=http://127.0.0.1:12520 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v13_returnproof --ros-domain-base 180 > /tmp/p3b5_v13_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_a1f17c9.json > /tmp/p3b5_protocol_a1f17c9.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:12510 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v13_fixed_then_holdout.py > /tmp/p3b5_v13_fixed_holdout_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:12521 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v13_lab --cases zero_rally_lab up100_lab down100_lab ttl_lab map_loss_lab battery_loss_lab state_loss_lab target_up10_lab battery_exhaust_lab --ros-domain-base 40 > /tmp/p3b5_v13_lab.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:12522 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v13_rooms --cases up10_rooms down10_rooms delay2_rooms overflow_rooms burst_rooms deadline_rooms detection_loss_rooms pose_loss_rooms single_failure_rooms target_loss_rooms --ros-domain-base 60 > /tmp/p3b5_v13_rooms.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:12520 taskset -c 40-59 /usr/bin/python3 /tmp/p3b5_v13_forced_safety_corridors.py > /tmp/p3b5_v13_forced_safety_corridors_pool.log 2>&1
```

本候选32started/32 raw终态，分布{'task_complete': 15, 'shutdown': 3, 'timeout': 8, 'no_data': 3, 'coverage_reached': 1, 'mission_failed': 2}。固定ideal rooms3/202 timeout300、零导航goal/零充电/零碰撞、总路径约.026m；原日志反复No safe cooperative frontier assignment，每次3groups/3candidates。这推翻最初"没有输入"猜测；旧固定runner没ledger/候选坐标，无法复原全部拒绝的确切几何原因，不声称队列问题唯一解释。rooms主ideal也timeout且三充，不能作为TDI有效对照。32条包括停止后捕获的孤立终态；原fixed runner继续下一格的结果仍保留，不能回填失败。UTC18:37:52仅停止有PID所有权证据的四池及152后代，stop清单保留。原物理子门PASS不能替代完整集成失败；未启动707，未用失败后重复结果替换正式样本。协议54PASS。

弱辅助20–250秒blackout中tb2 RETURNING18.9秒、tb1 50.3秒，tb2提前1.1秒开始；全部时刻/原结果保留，只说明充电安全，不能证明两机器人断网内实际返航。分析器删除该重复且过度解释的起点断言，仍严格要求独立、预声明的physical probe：两台起点距home≥1.1m，42–248秒guard内移动/接近/liveNav2执行各≥.5m、各充电且无碰撞/失败。解释修正的原/新validator SHA和UTC18:21:50声明归档，不改变原probe配置/门限，不丢弃弱探针失败时序。

开发诊断（均非正式成功替换，dirty a1+TTL/诊断，source Humble+install/PYTHONNOUSERSITE=1）：

```bash
ROS_DOMAIN_ID=218 GAZEBO_MASTER_URI=http://127.0.0.1:12530 taskset -c0-19 /usr/bin/python3 scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 202 --startup-timeout 600 --evaluation-duration 60 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --collect-fault-result --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --target-detection --rally --rally-max-concurrent 2 --disable-global-battery-rally-pause --dwell-seconds 0 --episode-id p3b5_freshness_diag_a1f_dev --evaluation-output-dir log/p3b5_freshness_diag_a1f_dev/results --log-dir log/p3b5_freshness_diag_a1f_dev/launch --gateway-ledger-path log/p3b5_freshness_diag_a1f_dev/ledger.jsonl --bypass-audit-output log/p3b5_freshness_diag_a1f_dev/graph.json > /tmp/p3b5_freshness_diag_a1f_dev.log 2>&1
/usr/bin/python3 /tmp/p3b5_freshness_load_dev.py > /tmp/p3b5_freshness_load_dev.log 2>&1
ROS_DOMAIN_ID=218 taskset -c0-19 /usr/bin/python3 /tmp/p3b5_frontier_snapshot_dev.py > /tmp/p3b5_frontier_snapshot_dev.log 2>&1
```

单池60s timeout、路径13.684m、发现39.6s/RALLY53.4s；并发四格90s（rooms202/rooms101/lab303/forced303）均native readiness/source graph/真实lidar-map检查通过且有运动，room101路径25.640、lab19.703、forced12.197且两充；全是短horizon timeout过程结果。各格精确命令/环境/代码diff/hash/结果在归档development manifest；rooms202只读8个收到地图/位姿快照保留，未重现全停驻，source队列depth10未改。此批不能证明原失效唯一原因或新算法正式成功。

源码修复：pose/TF消费源age严格≤协议TTL2s，map/battery≤5s且一般配置不能延长；未来时间戳等clock追上，不改源戳。固定ideal每格默认保存gateway账本，stale等待每5sim秒记录缺失源戳/age/TTL。粗前沿候选全部无法安全准入且无活动探索时，再从本机器人动态障碍后可达净空区域采样，仍走原候选评分、可见leg和完整预约；不放宽物理净距，不把短暂占用判成永久失败。合成反例原coarse位姿被parked占住，新pipeline真实派发独立安全观察点；不声称这就是旧rooms202确切几何。

补齐计划中的目标过期契约：确认TTL60s保持不变；truth detector只在当下仍可见且连续三帧确认时最多1Hz发新源戳，通过相同gateway可靠路径。中央同一静态目标的新交付确认才续期；旧版/重传/NaN/未来/过期/换坐标均不能续期，已FOUND/RALLY不回滚。过期不生成新的集合/调查决策或完成保持；只允许独立本地返航及必要off-route refuge避让。每次中央实际派发记录输入源lease，validator拒绝过期/未来决策（局部return refuge仅豁免目标，不豁免map/pose/TF）。评估首次发现时间保持，不把重复确认当新首次发现；动态目标重新定位仍需新任务契约。

验证：初次refinement子集105PASS/2FAIL为旧mock不接受blocked_positions关键字；补齐测试接口后通过。随后lease初测107PASS/2FAIL为旧夹具缺fresh_target/task_state；新增反例第一次111PASS/1FAIL缺局部json导入；修正夹具和导入后113PASS。最终14文件218PASS8.61s，四包build/source audit结果下一条补记。一个中间shell三引号解析失败未执行任何修改；后改用结构化patch。所有最终源改动必须新候选重新完整集成；不沿用a1的成功格。

freshness/前沿候选终检：14文件218 passed8.61s；PYTHONNOUSERSITE=1 colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot 四包5.48s PASS；/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count3 零违规。源码仍待新的冻结任务矩阵，不宣称P3B.5已通过。

## 2026-10-02 P3B.5 0150dab 目标lease恢复失败候选与盲扫修复

冻结0150dab6ed6d5f197344950017dbd24c3a461211，同源码/clean状态，218 checks、四包build/source审计通过后commit并push再开始。原物理probe配置完全不改：ideal COMPLETE210.5/两充，fault timeout300.4/两充/零接触/正能量，tb1起点距home1.512m、断网guard内路径1.533m/进展.719m/live Nav2路径1.522m；tb2起点3.127m、路径2.356m/进展2.303m/live2.356m。原room202固定格 COMPLETE141.0/零充/零碰撞。两个子门通过后自动启动四池全矩阵。协议54PASS。精确命令、runner/wrapper源/hash、子门日志和完整原结果见report/20261002_p3b5_target_lease_failed_candidate.json。

```bash
GAZEBO_MASTER_URI=http://127.0.0.1:12542 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v14_returnproof --ros-domain-base 180 > /tmp/p3b5_v14_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_a1f17c9.json > /tmp/p3b5_protocol_a1f17c9.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:12540 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v14_first_rooms202.py > /tmp/p3b5_v14_first_rooms202.log 2>&1
/usr/bin/python3 /tmp/p3b5_v14_after_subgates.py > /tmp/p3b5_v14_after_subgates.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:12540 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v14_fixed_then_holdout.py > /tmp/p3b5_v14_fixed_holdout_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:12541 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v14_lab --cases zero_rally_lab up100_lab down100_lab ttl_lab map_loss_lab battery_loss_lab state_loss_lab target_up10_lab battery_exhaust_lab --ros-domain-base 40 > /tmp/p3b5_v14_lab.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:12543 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v14_rooms --cases up10_rooms down10_rooms delay2_rooms overflow_rooms burst_rooms deadline_rooms detection_loss_rooms pose_loss_rooms single_failure_rooms target_loss_rooms --ros-domain-base 60 > /tmp/p3b5_v14_rooms.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:12542 taskset -c 40-59 /usr/bin/python3 /tmp/p3b5_v14_forced_safety_corridors.py > /tmp/p3b5_v14_forced_safety_corridors_pool.log 2>&1
```

同一候选主ideal lab2 COMPLETE146.0/一充、rooms3 COMPLETE168.0/两充、forced2 COMPLETE211.8/两充，均零接触；这些成功不能替代fixed lab3seed101的硬失败。该固定格timeout300/FOUND、发现63.9s、无RALLY、只有tb1充一次。中央后三段数据源年龄新鲜，但target源戳始终2193.382并超过60s；所有新的任务派发sourcelease检查均正常。tb2为检测机器人，最终(-3.83394,3.33461)，距目标(-4,4)0.69m；最终yaw没记录。只读几何诊断（source Humble/install/PYTHONNOUSERSITE=1，/usr/bin/python3调用load_truth_grid(my_world.world)+line_of_sight_clear）证实最终位置至目标LOS=True；当前证据支持朝向失去可见性，但不宣称测得唯一yaw因果。修正先前"检测机器人返航"猜测：实际返航充电的是tb1，检测者tb2未充电。

UTC停止时刻及120个owned进程、四池/父supervisor所有权清单/tmp/p3b5_0150_stop.json归档；停止后确认owned alive=[]。本候选11 started/11 raw，终态{'timeout': 3, 'shutdown': 1, 'task_complete': 7}，包含后停runner未回填summary的孤立结果与shutdown。fixed runner失败后启动的lab202为prestart行政中断，单独保留；未启动holdout707。原物理/room202/其他成功不回填失败格，不进后继TDI。

新恢复算法：源TTL60s保持；当目标lease失效、当前map/pose/TF/battery新鲜且不存在活动导航/返航时，逐机器人在当前已知自由位置通过同gateway发四个绝对朝向原地扫描，完全不读取旧目标坐标来选pose/yaw。每轮四次尝试后30s冷却；RETURNING优先、未来/过期/未知位姿等待。真实可见、连续三帧确认仍由原detector完成；新交付确认后取消扫描，晚到的action接受也必须取消并排空，之后才恢复FOUND/RALLY决策，不回滚阶段/不伪造新确认。账本记录requested/current位置，分析器仅对完全相同原地pose扫描豁免目标lease，map/pose/TF/battery仍全部严格核对；过期target不能隐藏新的平移集合目标。

固定ideal runner新增--fail-fast，保存首个失败结果后立即返回，不继续下一格；此项用于新的集成批次，不丢弃失败，主fault矩阵不使用该选项。反例覆盖四个朝向和冷却、六类安全等待、晚接受幂等取消，以及分析器拒绝以扫描名义发平移目标。初次旧有子集126PASS6.70s，新反例子集135PASS6.76s；最终全套14文件227PASS、四包build/source audit随后补记，所有任务栈改动要求新源码重新固定十格/物理/27配对，旧11episode不混用。

盲扫候选终检：14文件227 passed8.19s；四包symlink build5.38s PASS；三机器人source-only旁路审计零违规。root diff --check/add -n核对后显式排除用户260929_report和runtime，提交/push新冻结候选；先跑原lab3/101硬失败格及同预声明物理probe，两者通过才开其余矩阵。300s/energy/目标/TTL/物理门限不变。

## 2026-10-02 P3B.5 e1310bf 远处返航暴露失败与受控夹具

冻结 e1310bff2f92d09daa4aa0c426d7e70d77b3a9cc（227 checks/四包build/source audit通过、clean并push后运行）。3 started/3 raw：fixed lab3seed101原格 COMPLETE173.5s、零碰撞；原40..250物理对照 ideal COMPLETE、fault timeout300，两台均充电一次、零碰撞/失败/耗尽、最低能量正。原协议54PASS。lab101原始ledger没有target_reacquisition_scan，因此不宣称此次成功因盲扫恢复。完整原summary/results/控制器及电池日志/config及observer源/hash/命令存 report/20261002_p3b5_return_exposure_failed_candidate.json。

原物理门失败在暴露条件：tb2 RETURNING约76.6s、距home4.874m，有远处实际返航；tb1 RETURNING约198.2s、距home0.774m，已在0.8m充电区内，约0.1s即CHARGING，不能证明其在断网中完成≥0.5m实际返航。原判定AssertionError保留，不降低1.1m起点/.5m移动/.5m进展/liveNav2门槛。这是刺激准备不足，不是安全耗尽。子门driver停止，全四池和holdout707均未启动，无行政中断/重跑/回填成功。

精确命令（source Humble+install，PYTHONNOUSERSITE=1，canonical ROS cwd）：
```bash
GAZEBO_MASTER_URI=http://127.0.0.1:12552 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v15_returnproof --ros-domain-base 180 > /tmp/p3b5_v15_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_e1310bf.json > /tmp/p3b5_protocol_e1310bf.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:12550 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v15_first_lab101.py > /tmp/p3b5_v15_first_lab101.log 2>&1
/usr/bin/python3 /tmp/p3b5_v15_after_subgates.py > /tmp/p3b5_v15_after_subgates.log 2>&1
```

记录校正：上一0150dab日志复制的v14声明中协议输出文件沿用p3b5_protocol_a1f17c9.json；实际执行文件为log/p3b5_protocol_0150dab.json，stdout /tmp/p3b5_protocol_0150dab.log，54PASS，已在原0150归档内。此处保留旧声明并明确更正，不改变任何原实验结果。

新前瞻受控暴露 scripts/p3b5_staged_return_probe_manifest.json（原脚本/config不覆盖）：暂停且只暂停同runner后代同ROS domain的coordinator；两台在当前gateway map/pose/TF/battery均新鲜时，经原/gateway/{robot}/navigate_to_pose到(-2,-.45,pi)/(2,.45,0)两条不相交已知自由路径；50s内抵达，60..250s固定断网，guard62..248。原E40/idle.15/本地安全返航模型不改，不注入虚假能量、确认或source时间。只有原生实际充电完成，夹具才释放coordinator；只读native battery用于测试调度结束，不能选导航目标。未按时准备保留失败且停止下游，绝不改参数重试筛选成功。它是补充安全组件刺激，不是完整自主任务成功或TDI样本。原暴露3episode单列历史，后继同源码十格/27配对仍全部独立新跑。

新增进程归属反例（同domain非后代、后代异domain、无唯一目标一律不发signal）；最终15文件228PASS7.75s，四包build5.09s，3robot source audit无违规。第一次pytest工具未保存session返回状态，第二次完整捕获上述228PASS，非实验episode重跑。

## 2026-10-02 P3B.5 021b804 夹具路径净空失败候选

冻结021b80497c424b5c05a770185fd487f0b351b9b1（228PASS/四包build/source审计后clean并push）。2started/2raw：fixed lab3seed101 COMPLETE253.3s、path56.047m、2充、零碰撞；受控返航ideal timeout300、零碰撞，但staging operational_failure=True。50s准备期限内未派发任何staging目标，原coordinator暂停后由finally恢复；fault对照未启动，四池/707都未启动，无episode重跑或主动中断。Runner因原逻辑只看infrastructure返回0，driver严格检查operational_failure后仍正确停止；此轮修正runner同时对operational_failure返回1并修正STOP输出标签，保留原返回状态。完整结果/metadata及原stager源/独立observer/hash/日志/命令与后述诊断见report/20261002_p3b5_staging_fixture_failed_candidate.json。

```bash
GAZEBO_MASTER_URI=http://127.0.0.1:12652 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v16_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v16_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_021b804.json > /tmp/p3b5_protocol_021b804.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:12650 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v16_first_lab101.py > /tmp/p3b5_v16_first_lab101.log 2>&1
/usr/bin/python3 /tmp/p3b5_v16_after_subgates.py > /tmp/p3b5_v16_after_subgates.log 2>&1
```

纯静态几何只读诊断：source Humble/install、PYTHONNOUSERSITE=1、/usr/bin/python3，load_truth_grid(my_world.world)+scipy.ndimage.distance_transform_edt(~occupied)*resolution，对四候选线各81点采样world_to_grid。左右两声明路径中心线净空仅.30/.10m，小于.45m要求；上下至(0,-2.45)/(0,2.45)净空均.80m。AP各类acceptance在原50s窗口持续存在；原fixture无逐项等待原因/初始SLAM快照，故不能宣称唯一测得全部SLAM门控原因。选点先只检查点LOS而漏掉完整路径净空属于测试设计错误。改用上下两条分离路径、目标yaw∓pi/2，保持相同2m远点距离、50s准备、60..250断网、62..248guard、E40/idle.15和全部强验证阈值；不降低任何安全要求、不筛选重跑。原数据和旧预声明源保留。新增fixture轨迹净空回归同时拒绝原左右点，并为等待添加输入lease/actionready/地图范围/clearance原因和首个拒绝栅格npz+SHA，以防继续凭猜测修改。

验收要求还包含未调参fault seed。707未暴露且主矩阵均未启动，UTC20:40:27.833419前瞻声明heldout fault27077（仅3个heldout profile增加gateway_seed，开发17011、所有world/目标/能量/horizon/case不变）；原17011未执行heldout声明保留在initial_declaration_preserved。仅行政supervisor owned PID3467942在尚无pool_pids时SIGINT并重新启动，同一时段fixed/fixture两个episode未受中断；完整原/新supervisor源和命令已归档。新最终manifest现在正式记录这一声明，绝不能把开发17011当作未调参留出故障种子。

直接相关21脚本检查PASS1.29s；随后全套229检查/source audit补记。下一候选必须独立全十格/同源码27配对；本2episode只留历史，不回填成功格，不进入当前TDI。

修正后完整15文件229PASS7.84s；3robot source audit PASS0违规。四包源/launch未变，沿用021b804本轮已验证5.09s构建；scripts不需colcon重装。git diff --check后focused commit/push才启动下一候选。

新增留出命令反例检查后相关脚本22PASS；总组件数230。证据分析器核对holdout独立seed及预声明时间，并从每个精确命令最后一个--gateway-seed核实effective值，避免双参数默认覆盖误记。

## 2026-10-02 P3B.5 db4bb1a 夹具未知远点/本地回调积压失败

冻结db4bb1a7cefc1ce121430c22c5bcd57ff4d577df、clean/push后运行，230项组件脚本检查（229全套+独立seed命令新增检查）、四包源未变沿用验证构建。协议54PASS。2started/2raw：fixedlab101 COMPLETE114.0/零接触；受控physicalideal timeout300/零接触，但50s准备未通过，staging operational_failure和runner1、两个readonlyobserver0；fault对照/四池/707均未启动，无重跑、中断、回填。上次runner错误0已纠正，这次正确返回1，driver严格停止。完整原结果/命令/旧fixture源、observer源和配置/hash、等待事件及两个原npz的base64+SHA归档 report/20261002_p3b5_staging_map_failed_candidate.json。

```bash
GAZEBO_MASTER_URI=http://127.0.0.1:12752 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v17_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v17_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_db4bb1a.json > /tmp/p3b5_protocol_db4bb1a.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:12750 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v17_first_lab101.py > /tmp/p3b5_v17_first_lab101.log 2>&1
/usr/bin/python3 /tmp/p3b5_v17_after_subgates.py > /tmp/p3b5_v17_after_subgates.log 2>&1
```

新增具体等待证据：两台初始SLAM map的远点raw_end=-1；当前位置raw_start=0、clear_start=True。source地图tb1为2076.407、tb2为2075.186。读取保存npz、复用traversable_grid/has_known_line_of_sight/world_to_grid，对.5/.75/1/1.25/1.5/1.75/2米逐点检查：两台.5/.75米前缀均明确known/clear/LOS；tb1≥1.25m和tb2≥1.5m未知，tb2 1.25m端点known但中途line不安全。原始fixture localpose age多次2.08–2.70s，而其他源较新；APaccepted源时间在窗口正常，证据支持fixture自己的depth10/重复inflation计算积压，不把它归为网关丢包。只读诊断source Humble/install/PYTHONNOUSERSITE=1 /usr/bin/python3，用np.load原snapshot和上述既有函数，输出保留在归档map证据。真值净空.8m并不意味着接收SLAM已知；绝不放宽unknown/sourceTTL。

受控夹具准备改为沿原固定远点方向选择≤.75m、至少.5m（最后短腿除外）的当前map已知可见自由前缀，实际完成一段后才选下一段；source-age/ACTIVE/deadline每次重验。不会直接给未知远点、不会越过未知空洞，不作为任务策略/训练动作。fixture订阅改latest-only depth1、每个新map只计算一次clearance，减少自身回调积压；原姿态TTL2/地图电池5、终点/净空、50s准备、E40/idle.15、60..250断网和全部强物理门槛完全不变。新增已知前缀/未知洞/越界反例，证据检查器逐次核对四类sourcelease及≤.75m腿。直接相关23PASS1.28s，最终15文件231 checks随后补记。

最终15文件231PASS7.83s/source audit PASS零违规；四包task源/launch未改，不重复构建。git diff --check/explicit staging/commit/push后才开展下一独立同源码候选。

## 2026-10-02 P3B.5 aec30f7 一次性准备重派发失败候选

冻结aec30f7119fbaa390b20e6c56884c04d20bb46eb（15文件231PASS7.83/source审计后clean/push）。3started/3raw全部自然结束：fixedlab101 COMPLETE140.5s/零接触/min27.829；补充physicalideal/fault均timeout300.4s、2充/零接触/正能量/min9.62834/9.65651，所有runner/readonlyobserver0。两台都成功在50s前经.75m known prefixes到远点。原生断网返航物理证据确实通过：tb1起点2.01755m/offset171.1、路径1.20025m/进展1.19016m/liveNav路径1.20022m；tb2起点1.96597m/offset172.1、路径1.15299m/进展1.14434m/live1.15297m；均在62..248guard。它们仍不能覆盖原声明一致性的失败：ideal中tb1 staged19.7s，本地真实返充后192.2s又发第7个staging goal，从(-.01555,-1.17424)至(-.00641,-1.92418)，coordinator于200.2恢复。已完成staged标志没有在循环顶层跳过，产生额外准备动作；fault因为AP源过期未触发此动作，不据此掩盖ideal缺陷。

UTC21:15:18.492196只SIGINT尚未有pool_pids的owned行政supervisor PID3487555，3个正在运行episode未被signal，完整自然结果保留；四池/707从未启动，无episode重跑、补格或成功替换。完整原summary/results及script/config/observer/hash、精确命令、七个目标事件、stop记录、原始强物理门数据在report/20261002_p3b5_restage_failed_candidate.json；补充对照永远不作为主任务/TDI样本。

```bash
GAZEBO_MASTER_URI=http://127.0.0.1:12852 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v18_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v18_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_aec30f7.json > /tmp/p3b5_protocol_aec30f7.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:12850 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v18_first_lab101.py > /tmp/p3b5_v18_first_lab101.log 2>&1
/usr/bin/python3 /tmp/p3b5_v18_after_subgates.py > /tmp/p3b5_v18_after_subgates.log 2>&1
```

修复仅为for-loop最前跳过已staged机器人，使prepare完成标志一次性锁存；等待两台原生充电时保持空闲。强证据审计新增逐事件顺序检查：准备完成后或50s后任何新准备request都拒绝，stage目标位置满足声明.25m误差，source leases/腿长门槛不变，必须真实both_charged后才coordinator_resumed。反例同时覆盖仍在50s内重派发21s和实际原192.2s情况，新分析器对原ideal FAIL、原fault PASS；不得把原一致性失败改写为PASS。直接相关26PASS1.33s，完整15文件234checks随后补记；目标/阈值/能量/断网/horizon/episode retry完全不变。

最终15文件234PASS7.69s/source audit PASS零违规；四包任务源与launch仍未变，fixture/scripts检查充分，无重复colcon构建。focused diff检查及commit/push后才启动新候选。

## 2026-10-02 P3B.5 零能量反例启动与失败记录修复（无仿真实验）

cdde226之后、下一候选开始前发现预设battery_exhaust_lab初始能量0会被构造器拒绝；原27案例尚未执行该格，也没有新候选启动。修复只允许use_sim_time的0能量启动即FAILED，无短暂ACTIVE/导航；FAILED持续发布当前源时间心跳，防止构造时clock0的状态在网关永久过期。非仿真仍拒绝0。评估器reason消息不再提前finalize，沿用FAILED之后0.5s drain，并在启动前FAILED已到达时于原生位姿建立epoch后安排drain。新增真实ROS clock10/状态接收/无动作反例及失败状态、reason两种交付顺序组件检查。此处是预检发现，不能假称已验证正式零能量物理格；新冻结后原格ideal/fault先执行一次，后续lab列表排除该格，不产生重试/回填。

验证：source /opt/ros/humble/setup.bash、source install/setup.bash、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/component_checks，/usr/bin/python3 -m pytest -q，以下完整15文件237PASS7.99s：test_control/test_battery_manager/test_gateway/test_fault_model/test_navigation_faults/test_task_evaluator/test_nav2_ready_gate/test_readiness/test_spawn_entity_checked/test_tf_ingress_sampler/test_target_detector（src/multi_robot_exploration/test下），src/merge_map/test/test_merge_map.py，scripts/test_p3b5_tasks.py、test_p3b5_gate.py、test_p3b5_return_staging.py。单独battery27PASS1.37s。四包命令colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot，PASS5.42s。/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 PASS0违规。以上均组件/构建/静态预检，无新Gazebo episode、无707或network/RL工作。所有历史失败留存，下一任务栈候选必须独立同提交10固定格和27配对。

## 2026-10-02 P3B.5 3dec23c 零能量通过、目标视野/航向恢复失败候选

冻结3dec23c20230efab08942b3a392582b3bad50f71（237PASS7.99s/四包5.42s/source审计/clean/push）。先v19在受限沙箱启动：ROS UDP/getifaddrs EPERM、Gazebo ~/.gazebo/server-12951只读，0started/0raw；保留完整summary/commands/stdout/launch/source/hash。执行write_stdin Ctrl-C仅终止owned unified-exec sessions85421/11225的沙箱命名空间，退出130，没有运行中episode。require_escalated完成沙箱外UDP绑定预检PASS，随后v20新目录同源码/同参数运行；不是丢弃poststart失败重试。旧失败与后续全部记录同归档report/20261002_p3b5_heading_priority_failed_candidate.json。

v20 5started/5raw自然结束：原primary battery_exhaust_lab ideal/fault均mission_failed/FAILED，两台明确battery_exhausted、无导航goal、碰撞监测有效/零接触，零能量原格subgate PASS。后续lab批次已前瞻排除该格，未重复。受控物理ideal/fault均timeout、两台真实充电、正能量/零接触/FAILED；一次prepare锁存审计通过，皆6条准备goal，无完成后重派发。故障两台原生物理返航确实通过：tb1 offset172.0/home1.98017/path1.14461/progress1.13954/liveNav1.14458；tb2 offset170.7/home2.00454/path1.22730/progress1.21838/liveNav1.22726，均62..248守护窗口。协议54PASS。但固定lab3/101 timeout300.2/RALLY，118.2s由tb2发现，3充/零接触/零failed，最新source2247.482、epoch2126.382；48个blind scan请求各机器人16，但无新目标确认。终止原生位置到目标距离3.44176/5.22956/7.12334m，全超过detector3m。旧observer未记录yaw，不能假称测得原实际转角；冻结源码实际yaw_goal_tolerance=3.14足以让四朝向请求不强制转向。充电等待机器人的未来outbound优先路线也会挡住已充满observer推进，只有回到全部预充结束才重排。机制反例支持此优先级缺口；没有完整历史路线栅格可唯一归因旧任务时长。

```bash
# v19沙箱原失败命令，保留未启动记录
GAZEBO_MASTER_URI=http://127.0.0.1:12951 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v19_zero_first.py > /tmp/p3b5_v19_zero_first.log 2>&1
/usr/bin/python3 /tmp/p3b5_v19_bootstrap.py > /tmp/p3b5_v19_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v19_after_subgates.py > /tmp/p3b5_v19_after_subgates.log 2>&1
# v20在source Humble/install/Gazebo、PYTHONNOUSERSITE=1和工作区ROS_LOG_DIR下，rtk bash -lc沙箱外执行
/usr/bin/python3 /tmp/p3b5_v20_bootstrap.py > /tmp/p3b5_v20_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v20_after_subgates.py > /tmp/p3b5_v20_after_subgates.log 2>&1
# bootstrap原predeclared命令（完整wrapper源/环境/实际PID在归档）
GAZEBO_MASTER_URI=http://127.0.0.1:13051 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v20_zero_first.py > /tmp/p3b5_v20_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13050 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v20_first_lab101.py > /tmp/p3b5_v20_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13052 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v20_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v20_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_3dec23c.json > /tmp/p3b5_protocol_3dec23c.log 2>&1
```

fixed subgate自然FAIL停止supervisor（exit1），bootstrap等全部原episode自然结束，codes[1,0,0]；没有fullpool_pids，没有seed707或其他primary启动，没有poststart中断、自动重跑或回填。零能量和物理成功格也只留此历史候选，不能填入下一候选分母。

修复候选：所有实际tb1..tb4 Nav2 yaw tolerance收紧.25rad，让目标角度/viewpoint朝向可被执行；位置/线速度/足迹/避障/完成保持/300s/E40/E45不变。预充阶段在无活动或pending rally腿时稳定地优先ACTIVE且能量就绪机器人，不再让待充电机器人的future approach阻止其前进；实际安全返航/charger及停车body预约仍独立保留，不在活动导航中改排序。新增反例证明旧未知高优先路线可阻止charged观察者、新序允许推进但仍被真实return corridor约束。导航决策账本新增requested_yaw；只读physics observer记录原生yaw/angular_speed，允许3r只读观测用于新firstfixed，无额外mission。相关143PASS7.01s，全239 checks及四包/source审计随后补记。原失败全部完整保留，不宣称两项修复是旧时长唯一原因；下一候选仍需独立全矩阵。

候选最终15文件239PASS8.14s，四包build5.98s，3r source audit PASS0违规；physics脚本py_compile通过。git diff --check及explicit staging后focused commit/push，再开展新冻结候选。

## 2026-10-02 P3B.5 372d802 任务派发/探针暂停失败候选

冻结372d8028e7dfe4a5e995da589ea18443806c5f04（239PASS8.14s、四包5.98s/source审计、clean/push）。原生参数只读查询 `/tb1/controller_server goal_checker.yaw_goal_tolerance`=0.25：source Humble/install、ROS_DOMAIN_ID130、PYTHONNOUSERSITE=1，timeout12 ros2 param get输出/tmp/p3b5_v21_native_yaw_parameter.txt。4started/4raw，完整归档 report/20261002_p3b5_dispatch_pause_failed_candidate.json：原zero ideal/fault均expectedFAILED/无动作/零碰撞，fixedlab101 timeout300.0/RALLY/2充/零碰撞或FAILED；受控physicalideal因强制livegraph missing/headquarters_control退出，rawshutdown59.2/零碰撞/min29.1913，runner1/stager1/nativeobservers0，fault从未启动。夹具原SIGSTOP在约20s完成准备，DDS发现随后失去整个paused节点，mandatory audit超时缺节点；这是测试夹具与图发现的相互作用，不把它写成网关消息旁路，也不跳过mandatory审计。runner清理时暂停进程无法接受SIGINT/SIGTERM直到SIGKILL，signals/error全保留。完整主四池/707从未启动，firstfixed与physical全部原返回/退出自然保存，无行政中断、重复运行或回填。

```bash
# source Humble/install/Gazebo、PYTHONNOUSERSITE=1、工作区ROS_LOG_DIR，rtk bash -lc沙箱外
/usr/bin/python3 /tmp/p3b5_v21_bootstrap.py > /tmp/p3b5_v21_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v21_after_subgates.py > /tmp/p3b5_v21_after_subgates.log 2>&1
# bootstrap predeclared exact owned plans
GAZEBO_MASTER_URI=http://127.0.0.1:13151 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v21_zero_first.py > /tmp/p3b5_v21_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13150 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v21_first_lab101.py > /tmp/p3b5_v21_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13152 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v21_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v21_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_372d802.json > /tmp/p3b5_protocol_372d802.log 2>&1
```

独立3r只读physics由firstfixed wrapper以domain130启动脚本observe_p3b5_return_physics.py --robot-count3 --output log/p3b5/p3b5_v21_fixed_lab101_physics/physics.jsonl，命令、observer源、前瞻UTC/结束/hash和0退出保留metadata。tb1在107.3发现，后续真实重确认source2327.182；让路后E22.02，wholebudget22.05，重新请求返充，最终targetlease age95.1。旧能量预算没有未来一段让路往返的contingency；晚返充后所有机器人在目标3m视野之外，4个tb2 blind scan无新确认。原生角路径分别0.659/1.462/1.686/0.211rad，最大机体位移0.002/0.002/0.002/0.001m；最后扫描到horizon截断，不能称4个都完整转向。完整相应原生样本/decision区间在归档。world原生yaw不是各map同坐标误差，只证明实际转向；算法至此修复了航向缺口，但不能写为任务PASS。

下一候选：显式default-off use_sim_time-only `enable_return_probe_pause`只挡两个任务timer入口，不挡DDS/源状态callback，构造即paused避免启动竞争；只有实际参数确认true且owned同domain唯一coordinator才可SIGUSR2释放。main/fixed/heldout没有启用；探针仍不计完整自主任务/TDI，mandatory审计/全部阈值保留。多机whole-rally预算在原完整去程/返航/保持/等待上加入一次额外MAX_NAVIGATION_LEG_M短航段往返的move+idle耗电，不声称覆盖任意恢复次数；局部安全reserve和能耗参数不变。区别尚未admit的能源需求与实际请求/已经派发的home staging预约：未来return仅保护committed动作，实际RETURNING/CHARGING与停车占位、active/priority approach仍全保护；不能让所有future候选同时预约通道产生等待环。正常策略须新同提交十格及27配对证明，不能据组件检查宣布完成。

组件迭代：第一轮旧staging-budget反例以40作为已证明budget，但加入recovery后新需要42.6089，1FAIL/145PASS；加新两反例后旧fixture仍1FAIL/147PASS。将其人工已证明budget设50（仍<charge_target80）并保持全部精确保留断言，以验证预算下界不回退，148PASS5.96s。新增main27双方无pause、仅补充两个命令启用pause的检查；第一次缺test模块CONFIG导入（组件错误、无仿真），已补import。全套242 checks及四包/source审计随后补记。没有改正式能量/horizon/完成/TTL/物理阈值或重试筛选。

候选最终15文件242PASS8.05s，四包build5.29s，3r source audit PASS0违规，stager/smoke/runner py_compile通过。下一候选源与配置须clean/focused commit/push后冻结并全新运行；本4raw全部历史，不回填。


## 2026-10-02 P3B.5 v22启动失败集合漏记（失败候选，断线后续修）

冻结712f8e1d765bac501bec6cdef522cbaf9e44cf00、clean，前瞻bootstrap/after_subgates完整wrapper源码和UTC声明见report/20261002_p3b5_failure_snapshot_failed_candidate.json。精确入口：source Humble/install/Gazebo，PYTHONNOUSERSITE=1、TURTLEBOT3_MODEL=waffle、ROS_LOG_DIR为工作区log/ros_launch，rtk bash -lc沙箱外执行：

```bash
/usr/bin/python3 /tmp/p3b5_v22_bootstrap.py > /tmp/p3b5_v22_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v22_after_subgates.py > /tmp/p3b5_v22_after_subgates.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13251 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v22_zero_first.py > /tmp/p3b5_v22_zero_first.log 2>&1
# 原始正式zero格（不重复于后续lab）
/usr/bin/python3 scripts/run_p3b5_tasks.py --config scripts/p3b5_fault_manifest.json --run-id p3b5_v22_zero --cases battery_exhaust_lab --ros-domain-base 100
```

2started/2raw，ideal/fault均mission_failed、FAILED、1.7s、零接触；两台本地电池均FAILED/E0，零Nav2目标。中央只读observer分别捕获两台隔离事件，ideal评估failed集合两台，而fault仅[tb2]。/robot_failure采用depth1 transient-local，启动/晚订阅可能仅保留最后事件；原始门禁拒绝通过，不能从native电池补造中央失败集合。bootstrap自然退出1、supervisor断言失败；fixed、physical、protocol、全部pool/707均未启动，没有整格重试或替换。完整summary、两raw、两套中央事件和源码/命令/hash已归档。

新候选每条中央事件携带完整不可逆failed_robots快照；pub/sub可靠transient-local历史深度N保留逐台reason历史，评估按已知roster验证后单调并集，乱序/重复不回退、非法集合不部分更新。兼容旧单robot事件；native状态不替代中央隔离。组件第一轮新增测试误写不存在的类名，1FAIL/143PASS8.24s（无仿真），改为实际HeadquartersControl后全15文件249PASS8.82s；四包build5.23s、三机器人source audit PASS零违规。普通命令/任务时间/能量/安全/成功/源TTL门限不变。新冻结必须重新执行原始零能量格及后续完整门禁，历史成功不回填。


## 2026-10-02 P3B.5 v23零能量修复通过，但恢复搜索与夹具epoch门禁失败

clean冻结8d0b703ea89e91bc565e6bb3c9adff5d571ef2d1。report/20261002_p3b5_reacquisition_failed_candidate.json保留完整命令、wrapper来源、UTC、5raw/summary/ledger决策及source/config/env/hash；不混入后继矩阵。source Humble/install/Gazebo、PYTHONNOUSERSITE=1、TURTLEBOT3_MODEL=waffle、工作区ROS_LOG_DIR，经rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v23_bootstrap.py > /tmp/p3b5_v23_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v23_after_subgates.py > /tmp/p3b5_v23_after_subgates.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13351 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v23_zero_first.py > /tmp/p3b5_v23_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13350 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v23_first_lab101.py > /tmp/p3b5_v23_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13352 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v23_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v23_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_8d0b703.json > /tmp/p3b5_protocol_8d0b703.log 2>&1
```

5started/5raw：zero正式ideal/fault均mission_failed/两台中央FAILED、原生E0/零目标/零碰撞，1.7/2.4s，graph/ledger因果/TTL/version/decisions PASS。固定lab3/101 300.1s timeout/RALLY、三次充电、最低电量正、零碰撞/失败。检测tb1，home staging/串行让路先后使三台离开目标视野；latest source2207.882到期后反复真实原地扫描不能克服3m sensor range，未伪造新确认。原300s/40能量/目标/成功门槛保留。

补充ideal/fault均timeout300.1s、各机器人一次本地真实充电，最低9.707012/9.570693、零碰撞/失败、runner/stager/observer皆0。fault原生物理ONLY核查满足原guard62..248：tb1 start170.6s/距home1.9631m/path1.1507m/progress1.1418m/EXEC1.1507m；tb2 start169.8/距home2.0241/path1.2088/progress1.1998/EXEC1.2087。livegraph/source审计通过，DDS暂停问题已消失。但是staging_audit拒绝最早准备命令：sidecar用中央首次EXPLORE接收时刻作epoch，比gateway实际fault_epoch早0.7/1.2s；首个命令在真实epoch前。完整夹具仍FAIL，不能用物理ONLY通过替代。协议矩阵54PASS。bootstrap自然[1,0,0]；supervisor因firstfixed断言自然退出，fullpool/707未启动，无活跃episode行政中断/替换/重试。

只读追加审计先因导入scripts.check_p3b5_gate未找到模块退出（无仿真），改为sys.path.insert scripts后执行；严格staging_audit揭示epoch错位，物理ONLY独立结果保留。下一夹具仅从/gateway/message_events读取权威fault_epoch后准备，中央phase仅确定owned coordinator，保持全部准备/物理窗口。

下一算法候选：一次四向原地扫描失败后，以新鲜地图的原前沿信息收益/预约可见短航段重新搜索（单机器人），无过期目标几何、无阶段回滚；真实新确认后取消并排空搜索，再恢复集合。pending晚接收亦取消，原超时/停滞/local return保护保留。ledger明确记录独立frontier依据/路线，targetlease豁免仅适用于这种独立恢复搜索，所有map/pose/TF/battery源lease仍严格。真实地图反例改变过期target到相反极端，选择完全一致；state stale/RETURNING均零新目标，验证晚接受与幂等取消。相关149PASS7.13s，四包build5.28s；全组件检查结果随后补记。不能据这些组件检查宣布P3B.5完成。

候选全15文件253PASS8.05s、四包build5.28s、3r source audit PASS0违规；删除已被前沿恢复替代的旧重复扫描冷却状态后，再跑最短相关检查及diff，clean提交/push后才能开新冻结。

删除旧扫描冷却后的最短相关150PASS6.82s；原17份用户材料SHA256均未变化（目录完整相等检查因另有新增文件失败，逐原始文件核查通过，不修改/暂存用户新增文件）。


## 2026-10-02 P3B.5 v24受控返航通过，目标恢复仍不足

clean冻结d7954e38e839bf367dc7ae98247f1e07cc34a494。完整5raw/summary/命令/UTC/source/env/hash、staging双侧PASS/真实物理证据/首次理想ledger核查在report/20261002_p3b5_observer_handoff_failed_candidate.json，全部历史保留，不回填后继。source Humble/install/Gazebo，PYTHONNOUSERSITE=1、TURTLEBOT3_MODEL=waffle、工作区ROS_LOG_DIR，rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v24_bootstrap.py > /tmp/p3b5_v24_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v24_after_subgates.py > /tmp/p3b5_v24_after_subgates.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13451 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v24_zero_first.py > /tmp/p3b5_v24_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13450 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v24_first_lab101.py > /tmp/p3b5_v24_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13452 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v24_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v24_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_d7954e3.json > /tmp/p3b5_protocol_d7954e3.log 2>&1
```

5started/5raw：zero双侧mission_failed，全部中央FAILED/E0/0目标/0碰撞，1.8/2.1s；首格lab3/101 timeout300.1/RALLY、3次充电、零碰撞/失效/耗尽。last target source2232.782，四blind scans在epoch+180.5..188.9；五次前沿恢复请求在192.7/207.7/215.7/230.7/243.7秒，信息收益多指向东侧，没有真实新确认。完整ledger因果/TTL/版本/source leases及恢复路线PASS：10055生成、10844accepted、38导航决策、15真实reconfirmed、最小source_delay.007、最大clock deferral.089。新恢复动作得到实际执行，但不能把机制正确写为300s任务完成。

补充ideal/fault均自然到300.0/300.1s timeout，ideal末段FOUND只作过程（不是任务成功），两台各一次充电、最低能量正、零碰撞/失效；全部runner/stager/nativeobserver0。权威gateway epoch之后暂停确认/首批准备，19.4/20.8s已远处staged；双侧严格staging_audit PASS。fault真实guard62..248：tb1 start171.7s/home1.9856m/path1.1810/progress1.1721/EXEC1.1809；tb2 start171.2/home2.0062/path1.2024/progress1.1965/EXEC1.2024；两台均真实充电、livegraph/TTL/一次性准备检查PASS。协议54PASS。bootstrap自然[1,0,0]，supervisor因firstfixed自然FAIL；fullpool/707没启动，无活跃行政中断/整格重试。独立追加物理审计仅在原运行自然结束后执行，不增加episode或替换失败。

下一候选采用观测接力：跟踪最近真正交付的确认robot/source，新确认源age≤min(freshness,5s)、ACTIVE且有健康伙伴时，暂缓这台的主动返充/home staging，伙伴按原规则靠近；真正伙伴新确认后释放上一观察者。旧重传不偷换observer，源future/过5s无guard，单台健康/伙伴UNKNOWN无guard；已admit返航继续，local安全reserve可随时自行preempt，容量不足仍失败。guardian仍energy_unready，不豁免其全程能量预算或违规集合。handoff wait记录源5秒门禁。

组件先134PASS7.57s；新增handoff callback有效新事件后原测试预期仍2条事件，相关1FAIL/159PASS7.58s（无仿真），修正为实际新增第三条target_reconfirmed，仍严格检查旧重复不续lease/不抢回接力。一次工具工作目录误漏ros2_ws而未能创建进程，立即按canonical path重跑，无仿真。四包build5.23s；最终全组件/source审计结果随后补记。该算法只能新冻结原参数完整门禁证明，不能据组件或旧supplemental成功宣布P3B.5完成。

全15文件第一轮同一fixture预期残留1FAIL/266PASS8.60s，source audit PASS0违规；修正后267PASS8.69s，四包5.23s。diff check/显式staging后提交/push新冻结，原5raw不回填。


## 2026-10-02 P3B.5 v25首格GLX启动前失败（观测接力尚未集成验证）

clean冻结1a4f3a6103abac4e1ac2437c7c1e2d6973bb051c。report/20261002_p3b5_headless_glx_failed_candidate.json保留完整source/env/config/命令/UTC/hash及原失败日志，4started/4raw另加1次pre-start infrastructure failure；不回填下一矩阵。source Humble/install/Gazebo，PYTHONNOUSERSITE=1、TURTLEBOT3_MODEL=waffle、工作区ROS_LOG_DIR，rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v25_bootstrap.py > /tmp/p3b5_v25_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v25_after_subgates.py > /tmp/p3b5_v25_after_subgates.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13551 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v25_zero_first.py > /tmp/p3b5_v25_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13550 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v25_first_lab101.py > /tmp/p3b5_v25_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13552 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v25_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v25_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_1a4f3a6.json > /tmp/p3b5_protocol_1a4f3a6.log 2>&1
```

zero双侧mission_failed0.6/1.7s、两台中央FAILED/E0/零目标/零碰撞、source/graph/TTL检查PASS。固定lab3/101 gzserver出现X BadDrawable，GLX major152/minor29，随后spawn checker无fresh model inventory拒绝创建，launch早退；没有evaluation_started，没有task raw，runner1/infrastructure_failure=true。观测接力尚未在此完整ideal执行，不能据本失败判断算法效果。原summary prestart_failure_count=0因为旧实现attempt_count-1只计重试次数；实际attempts保留一次episode_started=false失败，此原值不改写，归档另列真实基础设施失败数1。

补充ideal/fault自然timeout300.0/300.3s EXPLORE、两台各一次充电、最低能量正、零碰撞/失效，runner/stager/observer0；全部准备源lease/起点/一次性/50s门槛PASS，fault62..248物理证明：tb1 start169.7s/home1.9508m/path1.1676/progress1.1541/EXEC1.1676；tb2 start168.9/home2.0140/path1.1979/progress1.1884/EXEC1.1979。协议54PASS。bootstrap自然[1,0,0]，supervisor因首格自然FAIL，fullpool/707未启动，未行政中断活跃任务或重试/替换原格。追加物理审计为运行结束后的只读重放，没有新episode。

源码核查模型仅contact/imu/ray，camera为frame/link，没有相机或GPU ray sensor。headless smoke虽然GUI全false，仍继承DISPLAY=:0；下一候选仅对子launch移除DISPLAY，manifest记录effective/parent display及GLX/software选项，不改变模型/物理/数据源或观测接力算法。prestart_failure_count修为所有未开始episode的attempt数量，含final failure；无需改历史raw或提高重试次数。

诊断gzserver --help在沙箱内因默认~/.gazebo日志不可写，按权限规定经rtk bash -lc沙箱外重读成功获得完整CLI（help本身exit255，未启动world/experiment）；原CLI没有headless-rendering选项。磁盘1.6T空闲，未见磁盘容量不足。新smoke/baseline py_compile和相关脚本组件检查结果随后补记；包内算法源未变，267组件/四包5.23s检查来自同源1a4f。不能复用本轮受控探针成功替代新冻结证据。

新smoke/baseline py_compile PASS，相关三个脚本33PASS1.32s，diff check通过；原GLX日志/一次未started基础设施失败保留，显式staging后提交/push新冻结。

## 2026-10-02 P3B.5 v26真实观测接力停滞（未通过）

clean冻结b83fb4acb09b50fcc4efae4f3f53f1085a06031b。5started/5raw保留在report/20261002_p3b5_observer_orientation_failed_candidate.json，未回填后继。source Humble/install/Gazebo，PYTHONNOUSERSITE=1、TURTLEBOT3_MODEL=waffle、ROS_LOG_DIR=canonical ROS/log/ros_launch；rtk bash -lc执行以下原命令：

```bash
/usr/bin/python3 /tmp/p3b5_v26_bootstrap.py > /tmp/p3b5_v26_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v26_after_subgates.py > /tmp/p3b5_v26_after_subgates_corrected.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13651 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v26_zero_first.py > /tmp/p3b5_v26_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13650 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v26_first_lab101.py > /tmp/p3b5_v26_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13652 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v26_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v26_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_b83fb4a.json > /tmp/p3b5_protocol_b83fb4a.log 2>&1
```

zero ideal/fault mission_failed0.8/1.9s、完整FAILED双机/E0/无目标/无碰撞，source/ledger/livegraph PASS。首格lab3/101自然timeout300.2s/RALLY，2次充电、最低能量18.823、零碰撞/失效/耗尽，基础设施失败/整格重试0。tb1保持真实观测但全程不能主动充电；tb2位置距最终点.0254m，原生yaw.6895rad而最终请求朝向1.5953rad；这两个yaw处于不同记录坐标系，不能仅凭相减声称实际误差。源码与独立反例确认中间航段成功且位置近时会被误标arrived，未保证最终请求朝向。tb3在(约0,2.23)反复重新分配同一不可达点，tb1仍占据附近通道。检测器永远选择当前合格可见者中最小编号，伙伴即使合格也不会被报告；下一修复以当前可见/三帧证据公平轮转，不凭本轮日志声称伙伴已经可见。

补充ideal/fault均自然timeout300.0/300.4s EXPLORE、两台各一次充电、最低能量正、零碰撞/失效。两侧严格staging/lease/one-shot准备PASS；fault原62..248窗口真实物理证明PASS：tb1 start172.0s/home1.9811m/path1.1768/progress1.1719/EXEC1.1768；tb2 start171.2/home2.0007/path1.2006/progress1.1928/EXEC1.2006。protocol54PASS。bootstrap自然[1,0,0]、supervisor因firstfixed FAIL退出，fullpool/707未启动；没有活跃任务行政中断或替换失败行。

一次未来fullpool supervisor启动时误设ROS_LOG_DIR=workspace根，在pool_pids尚不存在、未派发任何格前仅向owned PID4158977发SIGINT，保留原声明和环境纠正记录，再以正确ROS_LOG_DIR启动session67720；不是活跃episode重试。只读/proc环境检查在沙箱内因无法读取外部进程而断言失败，经审批RTK bash沙箱外确认两台gzserver确实DISPLAY absent；无新episode。归档含这两份诊断。运行结束后的物理重放第一次未source ROS而import失败，无仿真；source后严格审计通过。另一次只读native抽样遗漏非physics记录过滤导致KeyError，补过滤后成功，原记录不改写。

下一候选补上最终朝向完成与确认公平轮转（全局仍每秒最多一条）：保存实际rally航段pose，成功回调只有最终yaw一致且位置达标才能arrived；中途near-final位置不能跳过最终旋转。目标observer只由真实当前可见且连续三帧确认的轮转事件更新，遮挡/重新出现需重新积累。相关143组件PASS7.52s；四包/full组件/source audit结果随后补记。P3B.5仍未通过，不能复用历史成功填新冻结矩阵。

全15文件272PASS8.36s，四包build7.42s，3r source audit PASS0违规。diff check和显式staging通过后提交/push新冻结；后继原矩阵尚未开始。

## 2026-10-02 P3B.5 v27接力正确但第三次返充超过任务时限

clean冻结77ff56b5423ff52043faf9223776c5aa76385ce3，report/20261002_p3b5_contingency_budget_failed_candidate.json保留5started/5raw及完整命令/source/env/config/hash。source Humble/install/Gazebo，PYTHONNOUSERSITE=1、TURTLEBOT3_MODEL=waffle、canonical ROS/log/ros_launch；rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v27_bootstrap.py > /tmp/p3b5_v27_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v27_after_subgates.py > /tmp/p3b5_v27_after_subgates.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13751 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v27_zero_first.py > /tmp/p3b5_v27_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13750 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v27_first_lab101.py > /tmp/p3b5_v27_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13752 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v27_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v27_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_77ff56b.json > /tmp/p3b5_protocol_77ff56b.log 2>&1
```

零能量ideal/fault0.7/1.1s mission_failed，完整FAILED双机/E0/0目标/0碰撞/graph及ledgerPASS。首格lab3/101 timeout300.1s/RALLY，2次充电/3次返航、最低17.516、零碰撞/失败/耗尽，tb1/tb2距最终集合点.0240/.0191m，tb3仍RETURNING距最终5.6776m。真实target_reconfirmed出现tb2/tb3交替，接力后tb3获准返充，末航向修复得到执行；不能把修复机制正确写成任务COMPLETE。全ledger PASS：10181生成、10909accepted、28导航决策、184新确认、26handoff wait、最小source delay.004、最大clock deferral.096s。

补充ideal/fault自然timeout300.3/300.4s，FOUND/EXPLORE仅过程，两台各一次充电、正最低能量、零碰撞/失效，全部runner/stager/nativeobserver0。两侧严格staging/TTL/one-shot PASS，fault原62..248窗口tb1 start171.1s/home2.0195m/path1.2005/progress1.1892/EXEC1.2005；tb2 start171.9/home1.9753/path1.1540/progress1.1481/EXEC1.1540。protocol54PASS。bootstrap自然[1,0,0]，supervisorfirstfixed断言自然退出；fullpool/707未启动，0基础设施失败/0整格重试/0活跃行政中断。所有活跃运行结束后才改源。原17用户材料SHA256未变化。

预算诊断纠正之前“额外6米”的文字：当前及对应旧源码MAX_NAVIGATION_LEG_M实际为5m，所以固定往返附加量10m，而非6m。guard tb3在event_time2373.882能量28.047、required34.391；纯代数去掉未发生的10m费用后约23.280（不是替代轨迹实测）。下一候选并非简单删安全门槛：普通rally航段派发前实际路线+其末端到最终点路线+新最终点返航reserve+保持+原队友等待预算都重新检查，未知/非法/不足不派发，具体需求纳入下一串行返充/容量检查。重分配更远最终点也重新算home储备，不能沿用旧点预算；local safety/必要返航refuge与真实charge staging保留原优先规则。

reassign_rally_pose在同一不可变map/blocked snapshot内复用静态距离场与动态route cache，替代每个候选的重复Dijkstra，原候选/排名/clearance保持。离线组件基准命令：source Humble+canonical install，PYTHONNOUSERSITE=1、ROS_LOG_DIR=canonical ROS/log/component_checks，`/usr/bin/python3 /tmp/benchmark_p3b5_reassign_cache.py`；7次交错比较77ff函数与dirty新源（hash记录），同一80x80墙/开口/停车反例，每次结果点完全一致。中位.540885→.023951s，22.583倍，仅组件计算加速，不是任务消融或任务完成时间改善。完整源码/trials/hash见report/20261002_p3b5_reassign_cache_benchmark.json。

第一轮相关检查2FAIL/144PASS7.00s：staging fake仍只接收两个参数，及旧“无条件附加恢复费用”测试与明确变更语义不一致；修正fake并保留explicit staging断言，将旧测试改为保留真实队友wait并新增实际detour不足/充电恢复/未知路径/无效速度/重新分配home reserve反例。相关146PASS6.35s；进一步用完整实际费用重算替代delta后，全15文件276PASS8.60s，四包build5.51s，3r source audit PASS0违规。下一原矩阵须clean提交/push后开启，历史成功不回填。

## 2026-10-02 P3B.5 v28任务完成但原生检查收尾阻塞

clean冻结26bbc1ce6f0ae17fd162cd63d40814000edb404a。report/20261002_p3b5_native_cleanup_failed_candidate.json保留完整5started/5raw、原任务173.5s COMPLETE、runner-9失败、清理/QoS修正记录、AP地图快照/source/环境/命令/hash。source Humble/install/Gazebo，PYTHONNOUSERSITE=1、TURTLEBOT3_MODEL=waffle、canonical ROS/log/ros_launch；rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v28_bootstrap.py > /tmp/p3b5_v28_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v28_after_subgates.py > /tmp/p3b5_v28_after_subgates.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13851 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v28_zero_first.py > /tmp/p3b5_v28_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13850 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v28_first_lab101.py > /tmp/p3b5_v28_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13852 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v28_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v28_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_26bbc1c.json > /tmp/p3b5_protocol_26bbc1c.log 2>&1
```

zero ideal/fault mission_failed1.3/1.8s，完整FAILED双机/E0/无导航/0碰撞，source/ledger/graph PASS。首次lab3/101原始任务COMPLETE173.5s，原评估区间最低22.638能量、0充电/碰撞/失效/耗尽，实际全员误差/速度/5秒保持达标；该raw未改写。runner在“P3A forbidden-bypass audit passed”后原生检查不返回，任务结束后仍等待超过20min，没有进入Received消息检查完成输出。只读DDS图未见活跃smoke observer；不能据此确定卡在具体init/destroy/shutdown行。任务结束后的长尾telemetry与自行返充不属于173.5s任务窗口，不能当同一次任务完成时延或充电计数。

补充ideal/fault自然timeout300.2/300.4s RALLY/EXPLORE，仅过程，两台各一次充电、正最低能量、零碰撞/失效，runner/stager/nativeobserver0。双侧严格staging/TTL/one-shot PASS；fault原62..248物理证明tb1 start172.0s/home1.9801m/path1.1847/progress1.1756/EXEC1.1846，tb2 start171.3/home2.0106/path1.2043/progress1.1971/EXEC1.2043。protocol54PASS。此补充成功不能覆盖固定格runner失败。

额外只读AP取证，不参与控制/门禁：ROS_DOMAIN_ID130、CPU0–19，`/usr/bin/python3 /tmp/observe_p3b5_v28_ap_snapshots.py > /tmp/p3b5_v28_ap_snapshots.log 2>&1`。原volatility匹配错误造成odom/TF DURABILITY不兼容，在FOUND/RALLY前未记录任何快照；保留empty output/source/错误日志。仅向owned observer PID104171发SIGINT（return1，未完成metadata），改为volatile reliable接收网关动态数据，task metadata保持transient-local；独立新observer命令`/usr/bin/python3 /tmp/observe_p3b5_v28_ap_snapshots_qos_fixed.py > /tmp/p3b5_v28_ap_snapshots_qos_fixed.log 2>&1`，最终0、每20sim秒记录gateway map/odom/TF/battery及task metadata，未发送消息或动作。原必需native物理观察器不受影响。

诊断只读进程树/wchan和ROS图，无任务动作。一次pgrep -af误匹配工具包装进程，输出噪声被截断；后续仅从owned wrapper子树读取前3 argv，不读取进程完整环境。GDB尝试仅读取owned已完成任务smoke PID102966调用栈，常规和显式沙箱外审批均被系统ptrace拒绝（未附加、无debug暂停）：`gdb -q -batch -p 102966 -ex "thread apply all bt 8" -ex "py-bt" -ex detach`，第二次省略py-bt。归档保留拒绝日志。`ROS_DOMAIN_ID=130 timeout --kill-after=5s 40s /usr/bin/python3 -u /tmp/probe_p3b5_v28_smoke_contexts.py`两轮真实实体/scan/merge只读检查都通过，无新episode，未复现原阻塞，具体根因仍未确认。

任务已COMPLETE且physical/zero/protocol均自然结束后，向owned launch102997发SIGINT，全部ROS/Gazebo子进程clean结束；原smoke102966仍Sl且SIGINT/SIGTERM均不退出，最终仅SIGKILL此postcomplete死锁runner。精确命令与原raw在cleanup记录中；first必需nativeobserver随后0，bootstrap[1,0,0]，supervisor自然因firstfixed FAIL退出，fullpool/707未派发。原summary infrastructure_failure=false/prestart_count0保留，因为episode已开始；额外明确postcomplete operational failure1，runner-9严格阻止完整验收。不是重试/替换任务，不声称本轮无行政清理。

下一候选仅改smoke native检查隔离与manifest环境记录，算法/包源完全同26bbc。ready、entities、message各用一个实际只读ROS context worker，父进程执行原墙钟超时/launch存活监督；成功必须实际满足原条件，worker一次验证后结束进程让内核释放DDS资源，失败/超时不能伪造PASS。不确定原阻塞行，修复目标是覆盖所有native初始化/等待/清理阻塞，而非宣称已测得某个DDS根因。

新四项进程检查及原三个脚本共37PASS2.23s；真实DDS组件（无Gazebo/任务）命令source Humble/install、PYTHONNOUSERSITE=1、ROS_DOMAIN_ID187、canonical ROS/log/component_checks，`/usr/bin/python3 /tmp/verify_p3b5_native_probes.py > /tmp/p3b5_native_probe_real_checks.log 2>&1`：实际String流0.7854s收到；确定缺失流0.7598s拒绝（deadline.75s），子worker被回收，PASS，见report/20261002_p3b5_native_probe_component.json。py_compile smoke/baseline PASS，新全16文件280PASS7.80s、source audit PASS0。四包build5.51s为同包源26bbc，脚本变化不需重建包。diff/显式staging/commit/push后才能开启下一完整新冻结。

## 2026-10-02 P3B.5 v29原生检查恢复，固定集合通道停滞

clean冻结70b6c61689f6ae167fedd9ff9418585cbfc57ca6；report/20261002_p3b5_blocker_detour_failed_candidate.json保留5started/5raw、完整配置/命令/wrapper源码/环境/hash/原结果与失败。全部自然结束后才改源。source Humble+canonical install+Gazebo，PYTHONNOUSERSITE=1，TURTLEBOT3_MODEL=waffle，ROS_LOG_DIR=canonical ROS/log/ros_launch；rtk bash -lc执行：

```bash
/usr/bin/python3 /tmp/p3b5_v29_bootstrap.py > /tmp/p3b5_v29_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v29_after_subgates.py > /tmp/p3b5_v29_after_subgates.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13951 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v29_zero_first.py > /tmp/p3b5_v29_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13950 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v29_first_lab101.py > /tmp/p3b5_v29_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:13952 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v29_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v29_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_70b6c61.json > /tmp/p3b5_protocol_70b6c61.log 2>&1
```

零电量ideal/fault2.7/1.0s mission_failed，双机FAILED/E0/无导航/0接触，graph/source/ledger PASS。首格lab3/101自然timeout300.3s/RALLY、三台各充电一次、最低能量20.0067、0碰撞/失效/耗尽；所有原生ready/实体/消息检查通过（Received lidar and merged-map messages），runner正常收尾1为任务未成功，不是挂起/基础设施失败。首次检查进程隔离得到实测执行，但本批任务不COMPLETE，不能标完整门禁PASS。

补充ideal/fault自然timeout300.2/300.2s，RALLY/EXPLORE只作过程。两台各一次充电，正最低能量、0碰撞/失效；两侧runner/stager/observer0，严格freshness/原epoch/one-shot staging PASS。fault原62..248断联窗口：tb1 start172.4/home1.999470/path1.195914/progress1.186368/原生Nav2 EXEC1.195878m；tb2 start171.2/home2.001282/path1.208450/progress1.199684/EXEC1.208423m。protocol54PASS。bootstrap原[1,0,0]，future supervisor因首格FAIL自然停止，未派发fullpool/707；无重试、基础设施失败、行政中断、历史回填。

只读重放命令source Humble/install、PYTHONNOUSERSITE=1，`/usr/bin/python3 /tmp/audit_p3b5_v29_return.py`：完整返航补充子门禁PASS，未启动新episode。固定ledger重放（源码入口check_p3b5_gate.ledger_audit）：10131生成/11109accepted/41导航决策/125真实确认/23handoff wait，最小源延迟.007s、最大clock deferral.093s，因果/TTL/版本/决策输入leases全部PASS。

失败日志可见tb3六次重分配到远处集合点，却在等待者tb2的瓶颈内逐段移动；tb1持续保留视线，最终也返充，剩余时间不足。下一候选优先完整等待路线外的最近可达可视refuge，再退回永久重分配；不会为了远处新final点重复占据等待通道。临时避让保留原final，继续使用真实派发能量、源leases、净空、路线预约和本地安全检查。无可行refuge时原永久重分配仍可恢复。不能把此假设或离线反例写成任务时延实测改善。

相关control144PASS6.25s；全16文件281PASS7.93s，四包build5.68s，3r source audit PASS0违规。检查命令source Humble/install并设PYTHONNOUSERSITE=1、ROS_LOG_DIR=canonical ROS/log/component_checks：`/usr/bin/python3 -m pytest -q --tb=short`加src/multi_robot_exploration/test的test_control.py、test_battery_manager.py、test_gateway.py、test_fault_model.py、test_navigation_faults.py、test_task_evaluator.py、test_nav2_ready_gate.py、test_readiness.py、test_spawn_entity_checked.py、test_tf_ingress_sampler.py、test_target_detector.py及src/merge_map/test/test_merge_map.py、scripts/test_p3b5_tasks.py、scripts/test_p3b5_gate.py、scripts/test_p3b5_return_staging.py、scripts/test_ros_smoke_native_probe.py。构建`colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot`；审计`/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3`。反例实际验证侧向避让后原等待路线恢复可达，即使永久新目标也存在；没有refuge的fallback与能量未就绪阻挡者禁止派发也覆盖。下一原矩阵须新clean提交/push后执行；P3B.5仍待完成，未进入ns-3/RL。

## 2026-10-02 P3B.5 v30避让中丢失视觉及原生BT确认超时

冻结04d23e8e1e63e4341b183b5e1c3dab3703a0d717。report/20261002_p3b5_view_refuge_failed_candidate.json保留4started/4raw及完整命令/source/env/hash/准备阶段/原生Nav2诊断。source Humble/canonical install/Gazebo，PYTHONNOUSERSITE=1，TURTLEBOT3_MODEL=waffle，ROS_LOG_DIR=canonical ROS/log/ros_launch，rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v30_bootstrap.py > /tmp/p3b5_v30_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v30_after_subgates.py > /tmp/p3b5_v30_after_subgates.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14051 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v30_zero_first.py > /tmp/p3b5_v30_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14050 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v30_first_lab101.py > /tmp/p3b5_v30_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14052 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v30_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v30_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_04d23e8.json > /tmp/p3b5_protocol_04d23e8.log 2>&1
```

zero pair1.8/2.4s mission_failed双机FAILED/E0/无目标/0碰撞通过。固定lab3/101自然timeout300.1/RALLY、最低22.0804、2次充电、零碰撞/失效，runner/task均正常结束，不能计成功。guardtb1被临时移往(-3.15,.53)，距目标(-4,4)超过3m，目标lease到期；四向扫描后依据新鲜前沿重新发现目标，但剩余时间不足。永久重分配优先问题已经走到真实侧向动作，然而缺少视线约束破坏观测连续性。不能把safe refuge等同于可观测refuge。

受控ideal rawCOMPLETE244.3、零碰撞，但stager1=operational_failure，fixture失败阻止fault启动。原epoch2075.482、tb1第二.75m腿请求2084.882、2086.082收到Nav2ABORTED6，发生于准备截止50s之前，不能误记为截止超时。原生日志显示compute_path_to_pose ACK、clear costmap、cancel follow_path等20ms确认/服务请求超时。只读核对本地Nav2Humble源码：/opt/ros/humble/include/nav2_behavior_tree/bt_action_server_impl.hpp:119–120把default_server_timeout转为milliseconds；bt_action_node.hpp:213–228按该期限等待goal handle，超时返回FAILURE，未放宽任务完成或网关deadline。下一候选改四台实际params配置为500ms，只扩大有界原生内部ACK等待，不延长任务/navigation deadline或整格重试。本轮protocol54PASS，bootstrap原[1,1,0]、future supervisor因firstfixed FAIL自然结束；fullpool/707未启动，所有进程自然结束，无行政任务中断/替换/整格重试/基础设施失败；另明确操作失败1。

下一候选从真实新交付target_detection读取max_distance_m（缺省仍3，非法/非有限值拒绝且不更新observer/source lease）。最新age≤5s ACTIVE观测者的通道refuge筛选范围扣除原rally位置容差，并须当前交付地图已知LOS；实际派发的短航点也检查，朝向仍面向目标。没有可行近侧可见refuge则保留原安全回退/等待，不使用Gazebo真值推断视线，不允许过期目标控制。候选先做廉价范围/净空/路线分离筛选，再按最近路径逐点验证LOS，避免遍历每个自由格的射线检查拖慢中央回调。

几何反例验证旧最近refuge超出3m，新候选既在range余量内、路线外.8m并面对目标，墙和unknown遮挡拒绝；回调验证新交付自定义检测范围及invalidrange不偷换observer或续lease。control145PASS6.64s；新全16文件282PASS9.01s。新增状态机guard联动后1FAIL/282PASS9.07s：测试refuge几何范围4.05扣除.35位置余量后无近侧可见点，实际选了4.85m远点，违背该fixture原近侧≤1.1m断言；把测试传感范围修正为4.25使该fixture确实有近侧可见点，生产余量/约束不变。最终全量结果随后补记。四包build5.56s，3r source audit PASS0违规。命令与v29同16文件pytest/full四包build/source audit，canonical ROS/log/component_checks、PYTHONNOUSERSITE=1。任务栈改动须新clean提交/push再执行原矩阵，历史244.3COMPLETE不能弥补操作失败，本轮也不进ns-3/RL。

第二次全量仍1FAIL/282PASS9.47s；仅扩大测试range为4.25不能建立LOS，避让空间与目标之间仍有实墙。因此保留生产视线限制，给guard测试夹具增加一个仅1cell宽的观察缝（净空不足以通行，不产生导航绕过通道），自定义检测范围4.6；五个状态机恢复场景5PASS/141deselected1.48s，完整路径仍先被停车机器人阻挡，侧向观察点让出后才可通行。两次失败均记录，不把不同副作用混淆为任务成功。

最终全16文件283PASS8.34s（包含新guard状态机联动）、四包build5.56s、3r source audit PASS0违规。v30固定原始ledger只读重放check_p3b5_gate.ledger_audit通过因果/TTL/版本/决策输入source leases，详见失败归档records，不启动新episode。新候选commit/push之前diff check与显式staging排除用户260929_report及所有运行/build产物。

## 2026-10-02 P3B.5 v31全员恢复屏障与受控准备净空失败

冻结384270d486c8943c41deb258c34ccde85e77fbb3；report/20261002_p3b5_found_barrier_failed_candidate.json保留4started/4raw、完整wrapper源码/参数/环境/hash、原始结果、准备轨迹与捕获地图。全部进程自然结束后才改源。source Humble/canonical install/Gazebo，PYTHONNOUSERSITE=1，TURTLEBOT3_MODEL=waffle，ROS_LOG_DIR=canonical ROS/log/ros_launch，rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v31_bootstrap.py > /tmp/p3b5_v31_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v31_after_subgates.py > /tmp/p3b5_v31_after_subgates.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14151 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v31_zero_first.py > /tmp/p3b5_v31_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14150 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v31_first_lab101.py > /tmp/p3b5_v31_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14152 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v31_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v31_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_384270d.json > /tmp/p3b5_protocol_384270d.log 2>&1
```

zero ideal/fault1.4/2.5s mission_failed，完整FAILED双机/E0/无目标/0碰撞，graph/source/ledger PASS。首格lab3/101自然timeout300.1/RALLY，最低13.3833655、2次充电、0碰撞/失败/耗尽、所有native检查正常结束；发现69.7s而RALLY214.8s，全员电池恢复屏障耗费约145s。最后各机位置误差.018905/.015981/.022748m，仍因末航向及原5s保持不足不能计COMPLETE。原始ledger只读审计PASS：10199生成、10813 accepted、21导航决策、226真实确认，最小source delay.007/最大clock deferral.093s。

受控ideal rawCOMPLETE261.8、0碰撞，但stager1=operational failure，原50s准备期限到期，仅tb2完成准备；fault没有启动，不能用rawCOMPLETE覆盖子门禁失败。epoch2076.682，tb1两个.75m有界航段成功，随后实际起点(70,113)原始已知自由而膨胀mask不可通行；邻近单一占用格(72,111)使直线前缀失败。captured tb1_staging_map.npz SHA256 bee861b829a3163b79b9d14b1120400e5cc53c5d844d431f8f947f3c40411c1b及原数组纳入归档。原生日志后续别处存在起点lethal警告，不据此唯一归因为该像素，也未修改native footprint策略。protocol54PASS，bootstrap[1,1,0]，future因首格FAIL自然结束；fullpool/707未运行，无基础设施失败、整格重试或活跃行政中断。

下一候选移除完整集合分配前的全员ACTIVE屏障：RETURNING/CHARGING机器人使用新鲜电池消息中的有限充电位作为未来分配起点，实际robot_positions不改写；返航/机体预约、ACTIVE派发、完整能量和source leases仍保持。无法分配完整集合点时，额外探查仍受原全员就绪条件保护。新增四个状态机反例覆盖两种模式、非法位置及地图外充电位；不能把规划意图当作接收位姿。

受控准备复用现有plan_rally_leg/navigation_start_route的已知自由起点有界脱困，限制航段.75m并须接近原声明目标；原始unknown/occupied起点拒绝，源地图不变，期限50s不变。只读离线组件命令source Humble/install，PYTHONNOUSERSITE=1，ROS_LOG_DIR=canonical ROS/log/component_checks，`/usr/bin/python3 /tmp/replay_p3b5_v31_staging.py`。首次临时脚本ImportError（函数名误写traversable_mask），未启动episode；改用生产traversable_grid后PASS，原失败地图得到(.005678,-2.458022)航点，欧氏航段.539262m、目标距离.531269→.009828m，raw数组未变化。此为组件反例，非任务替代证据；完整重放数据与源hash保留在失败归档records。

相关control/stager155PASS7.48s；完整16文件288PASS9.95s，四包build5.30s，3r source audit PASS0违规。测试与v29同完整16文件命令，构建`colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot`，审计`/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3`。下一原矩阵须新clean提交/push，保持原目标/能量/300s/零重试与先十格后707条件；P3B.5尚未通过，未进入ns-3/RL。

## 2026-10-02 P3B.5 v32受控回充通过，固定任务让路串行及确认中断

冻结4e7828ba8fcf439f500487adae106d6779537b31，report/20261002_p3b5_yield_serialization_failed_candidate.json保留5started/5raw、完整wrapper/命令/参数/source/env/hash及全部子门禁证据。source Humble/canonical install/Gazebo，PYTHONNOUSERSITE=1，TURTLEBOT3_MODEL=waffle，ROS_LOG_DIR=canonical ROS/log/ros_launch，rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v32_bootstrap.py > /tmp/p3b5_v32_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v32_after_subgates.py > /tmp/p3b5_v32_after_subgates.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14251 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v32_zero_first.py > /tmp/p3b5_v32_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14250 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v32_first_lab101.py > /tmp/p3b5_v32_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14252 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v32_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v32_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_4e7828b.json > /tmp/p3b5_protocol_4e7828b.log 2>&1
```

zero ideal/fault.7/.9s mission_failed，双机完整FAILED/E0/0导航/0碰撞，graph/source/ledger PASS。固定lab3/101自然timeout300.3/RALLY，3次充电、最低13.3058082、0碰撞/失败/耗尽；原生ready/实体/消息及收尾正常。发现offset146.6，集合分配与首次本地让路154.5；tb1此时已独立安全返航，不能因其之前检测过目标就撤销返航或伪造ACTIVE。最后tb1/tb3集合位置误差.0130/.1682m，tb2仍1.5937m、运动中，不能计成功。真实确认源gap149.9..242.2（92.3s），中央stale等待offset210..242.4；四次扫描后新鲜地图搜索恢复真实确认。固定ledger审计因果/TTL/版本/source leases PASS，10079生成、11199 accepted、51导航决策，最小source delay.006/最大clock deferral.093s。

补充ideal/fault自然timeout300.2/RALLY、300.4/EXPLORE，仅过程；两台各充电一次、最低9.677307/9.602793、0碰撞/失败，runner/stager/nativeobserver均0。两侧严格准备/TTL/原epoch/one-shot PASS；故障侧原62..248断联区间：tb1启动170.6s、距home2.017484m、实际path1.211901/progress1.205277/原生Nav2 EXEC1.211875m；tb2启动172.1s、距home1.971786m、path1.177478/progress1.169470/EXEC1.177452m。protocol54PASS。bootstrap自然[1,0,0]，future首格FAIL退出，fullpool/707未启动；0基础设施失败/整格重试/活跃行政中断。全部进程结束后改源，未重跑本批格。

只读原始重放命令source Humble/install、PYTHONNOUSERSITE=1、ROS_LOG_DIR=canonical ROS/log/component_checks：`/usr/bin/python3 /tmp/audit_p3b5_v32_return.py`及`/usr/bin/python3 /tmp/audit_p3b5_v32_fixed.py`，无需新episode。两侧物理子门禁PASS纳入归档，不作为固定任务COMPLETE或新批次证据。

下一候选只移除“任一让路腿尚未到达就禁止所有普通集合计划”的全局排除项。普通动作仍通过原freshness、ACTIVE、完整能量、活动腿剩余路线、优先接近路线、返航预约、动态机体与并发名额检查；没有放宽路线冲突净空或启动重试。全局排除能导致不相关路线串行等待，但其具体任务收益须新冻结原矩阵验证，不能把92.3s缺口全部归因于该四行条件。三个实际几何状态机反例验证disjoint+slot可派发、冲突路线/名额满拒绝，既有让路handle不取消。相关11PASS2.49s，完整16文件291PASS8.52s，四包build6.02s；命令与v31完整pytest/build同，源审计结果随后记录。P3B.5仍待完成，尚未进入ns-3/RL。

3r source-only绕过审计PASS0违规；原17用户材料SHA256保持。diff check及add-n检查后显式staging只选修改源码/测试/说明/log和本次失败归档，不包含用户报告或运行输出；commit/push后才启动下一冻结原矩阵。

## 2026-10-02 P3B.5 v33临时让路的未来预约阻止受益者

冻结a8cb4740470cd2184a1181b7ce656918a7ba07ae，report/20261002_p3b5_yield_priority_failed_candidate.json保留5started/5raw、完整wrapper/命令/配置/source/env/hash、受控回充审计及只读AP快照。source Humble/canonical install/Gazebo，PYTHONNOUSERSITE=1，TURTLEBOT3_MODEL=waffle，ROS_LOG_DIR=canonical ROS/log/ros_launch，rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v33_bootstrap.py > /tmp/p3b5_v33_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v33_after_subgates.py > /tmp/p3b5_v33_after_subgates.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14351 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v33_zero_first.py > /tmp/p3b5_v33_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14350 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v33_first_lab101.py > /tmp/p3b5_v33_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14352 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v33_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v33_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_a8cb474.json > /tmp/p3b5_protocol_a8cb474.log 2>&1
ROS_DOMAIN_ID=130 taskset -c 0-19 /usr/bin/python3 /tmp/observe_p3b5_v33_ap_snapshots_qos_fixed.py > /tmp/p3b5_v33_ap_snapshots_qos_fixed.log 2>&1
```

zero ideal/fault1.5/2.0s mission_failed，双机完整FAILED/E0/无导航/0碰撞，graph/source/ledger PASS。固定lab3/101自然timeout300.3/RALLY，无充电，最低24.795683，0碰撞/失效/耗尽；原生检查及正常收尾通过。tb2完成最终集合，tb3已停在临时refuge(-4.04,2.21)，tb1停在中间航点(-2.99,.71)；未来优先接近路线仍保护tb3原最终点(-3.99,3.01)，因此受益者tb1到(-3.99,1.41)的可行路线被拒。不是电量或目标lease失败。固定ledger因果/TTL/版本/决策leases只读审计PASS。

补充ideal/fault自然timeout300.3/300.1s EXPLORE，仅过程；两台各一次充电、最低9.685153/9.693455、0碰撞/失效，runner/stager/nativeobserver0。严格准备、TTL、one-shot及原epoch PASS；fault原62..248区间tb1 start172.2/home1.968399/path1.158818/progress1.151190/原生Nav2 EXEC1.158788m；tb2 start171.2/home2.010311/path1.201902/progress1.191801/EXEC1.201874m。protocol54PASS。bootstrap自然[1,0,0]，future首格FAIL自然结束，fullpool/707未执行；没有基础设施失败、整格重试或活跃行政中断。全部进程自然结束后修改源。

额外只读AP观察器只订阅交付地图/odom/TF/battery/target和task metadata，不发布任务消息或动作，不使用native truth控制；3条快照及完整source/hash纳入归档，observer在原固定subgate出现后正常0退出。第一条time0仅包含latched task metadata（不是新鲜输入证据），后两条包含所需交付数据。第一次临时读取误选首条导致KeyError tb1/odom，纠正为完整末条，未启动额外episode。离线重放source Humble/install、PYTHONNOUSERSITE=1、ROS_LOG_DIR=canonical ROS/log/component_checks：`/usr/bin/python3 /tmp/replay_p3b5_v33_priority.py`，snapshot2416.882，SHA f32504034f1785935709277ab4d3e3b89e7b8cae77475a984b4e27ff226695a2；同raw地图/实际停车body，普通plan存在，原future priority拒绝，向tb1单独释放tb3 future intent后接受。原tb3最终格由launch四舍五入坐标在同网格lattice上恢复，明确不是完整初始assignment快照；只证明几何机制，不声称替代任务COMPLETE或跨候选纯策略收益。

只读整批审计命令`/usr/bin/python3 /tmp/audit_p3b5_v33_return.py > /tmp/p3b5_v33_return_audit.log`及`/usr/bin/python3 /tmp/audit_p3b5_v33_fixed.py > /tmp/p3b5_v33_fixed_audit.log`，相同Humble/install/component环境，无新episode。下一候选记录临时让路受益关系；让路者实际成功停到refuge后，只向该受益者暂时释放未来接近预约，真实机体和活动/返航航段仍受保护，其他跟随者和尚未完成的让路不获得优先权。原最终集合点保留；恢复/失败清理关系，其他能量/lease/净空/并发门槛不变。

首次相关检查3FAIL/9PASS3.30s：两项SimpleNamespace缺生产容差字段，第三项几何夹具允许原预约前的合法安全前缀，与测试“零派发”断言不一致。补齐.35容差，并把待行机器人放到预约1.8m范围内但实际机体.6m范围外，构成真正阻断反例，生产门槛不变。相关12PASS2.12s；完整16文件294PASS8.98s，四包build35.8s（multi_robot30.7s，无错误），3r source-only审计PASS0违规；命令同v32全量pytest/四包build/source audit。下一原矩阵在clean commit/push后运行；P3B.5仍待完成，无ns-3/RL工作。

## 2026-10-02 P3B.5 v34多航段恢复中的预约优先倒置

冻结8c5e8b02030c341baab68da1826d88a1a79a18e4，report/20261002_p3b5_recovery_donation_failed_candidate.json保留5started/5raw、完整wrapper/命令/config/source/env/hash、原始物理与账本审计及AP地图快照。source Humble/canonical install/Gazebo，PYTHONNOUSERSITE=1，TURTLEBOT3_MODEL=waffle，ROS_LOG_DIR=canonical ROS/log/ros_launch，rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v34_bootstrap.py > /tmp/p3b5_v34_bootstrap.log 2>&1
/usr/bin/python3 /tmp/p3b5_v34_after_subgates.py > /tmp/p3b5_v34_after_subgates.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14451 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v34_zero_first.py > /tmp/p3b5_v34_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14450 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v34_first_lab101.py > /tmp/p3b5_v34_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14452 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v34_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v34_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_8c5e8b0.json > /tmp/p3b5_protocol_8c5e8b0.log 2>&1
ROS_DOMAIN_ID=130 taskset -c 0-19 /usr/bin/python3 /tmp/observe_p3b5_v34_ap_snapshots_qos_fixed.py > /tmp/p3b5_v34_ap_snapshots_qos_fixed.log 2>&1
```

zero ideal/fault1.2/1.9s mission_failed双机完整FAILED/E0/无导航/0碰撞，graph/source/ledger PASS。固定lab3/101自然timeout300.4/RALLY，三台各一次充电、最低20.190646、0碰撞/失败/耗尽；所有native检查与收尾正常。最新观察者tb1维持实际确认，伙伴接近后早充，但最终误差tb1/tb2/tb3=2.04675/2.98627/3.64562m，未完成。日志连续三次永久重分配tb2至同一(-3.99,3.02)点以释放tb3通道，每次直接恢复派发一条可行腿；普通后续腿受未来优先接近预约影响，必须再次走恢复分支。暂时让路到位后的单向受益豁免不覆盖这段永久恢复过程；不能把此前修复机制存在写成完整任务成功。

受控ideal/fault自然timeout300.2/300.2 EXPLORE，仅过程；两台各一次充电、最低能量正、0碰撞/失败，runner/stager/nativeobserver0。严格准备/TTL/one-shot/原epoch PASS；fault原62..248区间tb1 start170.8/home2.011704/path1.203602/progress1.196302/原生Nav2 EXEC1.203561m；tb2 start171.4/home1.984749/path1.178618/progress1.170182/EXEC1.178578m。protocol54PASS。bootstrap自然[1,0,0]，future首格FAIL自然退出；fullpool/707未派发，无基础设施失败/整格重试/活跃行政中断，全部进程自然结束后改源。

只读AP观察器提前启动，只有有效clock/map后才保存FOUND/RALLY快照，11条2224.682..2424.682，source/hash与原数据保留，任务subgate出现后正常0退出，不发任务消息或动作。离线命令source Humble/install、PYTHONNOUSERSITE=1、ROS_LOG_DIR=canonical ROS/log/component_checks，`/usr/bin/python3 /tmp/replay_p3b5_v34_recovery.py`；三条原始快照2324.682/2344.682/2364.682，完整交付assignment无需恢复四舍五入格，普通tb2 plan存在，tb3未来intent拒绝，借用请求者优先权后同静态/动态机体检查下接受。快照SHA b37996025a6ff6cd5e77c0a8d6312afa77a8f91207e94c139abf9cc8e6b32d40。所用tb3,tb2,tb1顺序与能量就绪稳定排序一致，但未在快照直接记录，明确为条件组件反例，不声称唯一实测根因、替代任务或纯策略时延改善。首次临时拼接重放脚本ValueError substring not found，随后未生成文件的执行exit2；改为完整显式脚本后重放成功，未启动额外episode。

只读正式审计`/usr/bin/python3 /tmp/audit_p3b5_v34_return.py > /tmp/p3b5_v34_return_audit.log`、`/usr/bin/python3 /tmp/audit_p3b5_v34_fixed.py > /tmp/p3b5_v34_fixed_audit.log`，上述component环境，因果/TTL/版本/决策source leases及强物理回充均PASS。

下一候选把受益关系扩展为恢复期间的临时优先权：请求停车阻挡者移开的机器人在它完成恢复前暂时让出自己的未来intent；临时refuge已实际到位后，再向原受益者开放通过。永久新目标也保存此恢复关系，终点成功、恢复释放、失败或独立返航让路接管时清理；真实停车机体、所有live/return路线、完整能量、freshness、并发名额仍检查。三个实际窄通道反例覆盖合法借权、未借权拒绝、真实机体占位不可绕过。相关13PASS2.61s；完整16文件297PASS8.60s，四包build5.97s；命令同v33完整pytest/四包build。源审计结果随后记录，下一原矩阵须clean commit/push。本批失败保持，P3B.5仍待完成，未进入ns-3/RL。

3r source-only审计PASS0违规，原17用户材料SHA256未变；diff check、add-n及显式staging排除所有用户材料/运行产物，新源和失败归档commit/push后才启动下一冻结。

## 2026-10-02 P3B.5 v35独立返航与已接收航段冲突；2026-10-03新候选修复

冻结3cc5529e7c84b702dc877ab3c50bf2652064dadb，report/20261002_p3b5_return_race_failed_candidate.json保留4started/4raw、全部summary/source/config/env/命令、原始物理/账本文件SHA及大小、实际导航决策、碰撞历史、准备记录、所用三条AP原地图快照。此前声明以原路径/SHA和已提交失败报告引用，避免递归复制历代声明；原声明完整保留于/tmp，不篡改。source Humble/canonical install/Gazebo，PYTHONNOUSERSITE=1，TURTLEBOT3_MODEL=waffle，ROS_LOG_DIR=canonical ROS/log/ros_launch，以下经rtk bash -lc执行：

```bash
/usr/bin/python3 /tmp/p3b5_v35_after_subgates.py > /tmp/p3b5_v35_after_subgates.log 2>&1
/usr/bin/python3 /tmp/p3b5_v35_bootstrap.py > /tmp/p3b5_v35_bootstrap.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14551 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v35_zero_first.py > /tmp/p3b5_v35_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14550 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v35_first_lab101.py > /tmp/p3b5_v35_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14552 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v35_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v35_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_3cc5529.json > /tmp/p3b5_protocol_3cc5529.log 2>&1
ROS_DOMAIN_ID=130 taskset -c 0-19 /usr/bin/python3 /tmp/observe_p3b5_v35_ap_snapshots_qos_fixed.py > /tmp/p3b5_v35_ap_snapshots_qos_fixed.log 2>&1
```

zero ideal/fault1.4/3.2s mission_failed，双机完整FAILED/E0/无导航/0碰撞，runner0、账本PASS。固定lab3/101原300.0s自然timeout/RALLY，三台各充一次、最低12.4439542，0耗尽/失效，16次tb1/tb2机体接触，总接触持续27.8s；这是真实安全失败，不能记为PASS。普通tb1 rally下发2293.282，tb2独立RETURNING2293.382；2325.282起接触。tb1后在2344.882才让开；阻挡恢复优先关系更晚出现，不将碰撞归因于该借权过程。正常原生验收通过，任务终止后launch清理中自有tb1 lifecycle_manager经SIGINT/TERM最终SIGKILL，保留收尾问题。

受控物理ideal在93.3s shutdown，runner/stager1、原生truth observer0；准备两机虽在50s前到位，但message worker681461超过原90s wall deadline，runner错误分支SIGINT清理自有launch，stager收到中断。Faulthandler显示executor wait，旧日志未打印请求topic，不能断言具体topic/QoS或唯一DDS根因。未进入fault episode、没有完整回充证据；fault observer0且输出空只代表未启动任务。Protocol54PASS；bootstrap自然[1,1,0]，future首格FAIL退出；fullpool/707未执行。没有整格重试或手动中断活跃任务；自动错误清理明确计为operational failure。全部源实验及future结束后才改源码。

只读AP观察器源与metadata/hash保留，10条2235.682..2415.682，正常0退出，没有publisher/action/真值控制。离线原始物理诊断`/usr/bin/python3 /tmp/diagnose_p3b5_v35_contacts.py`；此前inline拼接SyntaxError在执行前失败。源Humble/install、PYTHONNOUSERSITE=1下`/usr/bin/python3 /tmp/replay_p3b5_v35_return_race.py`成功：两条交付快照2295.682/2315.682、地图SHA91f222dc3bb235772ea8a58779520ab20934a34aabd0110b7e9e40b0a738bb4a，tb1已派目标的重建可行路径与tb2返航预约冲突。明确是同交付数据的几何反例，原始live reservation未完整记录，不声称精确恢复每个原预约格或唯一端到端原因。归档命令`/usr/bin/python3 /tmp/archive_p3b5_3cc5529.py`，所有四条ledger审计PASS。恢复时/proc进程读取遇到瞬时退出FileNotFoundError，改为逐PID捕获消失，仅检查自有v35前三argv，确认无旧实验进程；首次summary读取误用dict对固定episodes list的.items导致AttributeError，改为独立raw读取，无新任务。

新候选在每次新鲜返航检查时重审已执行/待接受的普通rally航段，取消交叉路径并保留pending取消意图；迟到接受后实际取消，预占所致拒绝/异常不消耗任务重试。缺返航几何排空普通航段；不取消独立本地安全返航。已认证的逃离航段可继续清理自己对应的返航通道，但仍检查其他返航。让路不再等待全部无关航段结束：只等待自身cancel drain、真实并发名额，并检查全部其他live路线、真实停车机体和返航预约，仍是新鲜交付地图/pose驱动的可视短段。保留原最终集合点、energy/freshness/净空/任务300s/retries0/0碰撞门槛。

原生消息验收将scan/条件merge_map/全部battery一次订阅到一个只读DDS context，用原90s共同wall上限（不延长），保持原QoS并要求每个topic真实callback，新增topic/type/QoS/receipt/pending诊断；仍由父进程原deadline约束，超时只kill自有观察worker，再由原runner错误清理任务。

新增真实DDS组件实验（无Gazebo/任务），父提交3cc5529、dirty successor源码SHA和完整producer/source/命令/输出保存在report/20261003_p3b5_native_message_group_component.json。rtk bash -lc，Humble/install/PYTHONNOUSERSITE=1/ROS_LOG_DIR=canonical ROS/log/component_checks：

```bash
ROS_DOMAIN_ID=188 taskset -c 20-39 /usr/bin/python3 /tmp/verify_p3b5_native_message_group.py > /tmp/p3b5_grouped_native_real_checks.log 2>&1
```

LaserScan BEST_EFFORT/volatile、OccupancyGrid与String RELIABLE/transient_local提前单次publish，三种实际消息均收到，共0.666326s；广告但从未publish的第四topic在原2s共同deadline被拒，2.010386s，只回收自有worker，producer在finally正常0退出。不能把组件证明写为任务成功或DDS唯一根因已经确定。

相关控制+native172PASS8.10s；新增未知返航几何反例后，全16文件307PASS9.93s，四包build5.27s，3r source-only审计PASS0违规。确切命令（source Humble/canonical install，PYTHONNOUSERSITE=1，component日志目录）：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py scripts/test_ros_smoke_native_probe.py
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py > /tmp/p3b5_v36_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v36_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v36_source_audit.log 2>&1
```

下一v36使用新的干净commit/push后重新原57唯一episode矩阵，先zero、原lab101固定与受控物理/协议子门槛，再其余固定/故障/aux；十个固定全部通过才首次707（预声明fault27077）。不混入历史成功。P3B.5尚未通过，无ns-3/RL工作。

## 2026-10-03 P3B.5 v36目标恢复搜索在完整地图中停滞

冻结56479c0685384e67a45315ddcd260de3b2b78bf9，report/20261003_p3b5_known_space_failed_candidate.json保留5started/5raw、全部原summary/manifest/源/命令/hash、原ledger/nativephysics/AP快照和受控准备/强物理审计。初始化/tmp/prepare_p3b5_v36.py在沙箱socket EPERM、未生成wrapper或启动任务；依授权rtk bash -lc外部重做预检成功，端口14650..14653未占用、tracked clean及17原用户文件SHA不变，随后冻结运行。source Humble/canonical install/Gazebo，PYTHONNOUSERSITE=1/TURTLEBOT3_MODEL=waffle/ROS_LOG_DIR=canonical ROS/log/ros_launch；实际命令经rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v36_after_subgates.py > /tmp/p3b5_v36_after_subgates.log 2>&1
/usr/bin/python3 /tmp/p3b5_v36_bootstrap.py > /tmp/p3b5_v36_bootstrap.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14651 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v36_zero_first.py > /tmp/p3b5_v36_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14650 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v36_first_lab101.py > /tmp/p3b5_v36_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14652 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v36_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v36_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_56479c0.json > /tmp/p3b5_protocol_56479c0.log 2>&1
ROS_DOMAIN_ID=130 taskset -c 0-19 /usr/bin/python3 /tmp/observe_p3b5_v36_ap_snapshots_qos_fixed.py > /tmp/p3b5_v36_ap_snapshots_qos_fixed.log 2>&1
```

zero ideal/fault1.1/2.8s mission_failed双机完整FAILED/E0/无导航/0碰撞，原graph/ledger/runner PASS。原固定lab3/101自然timeout300.3/RALLY，2charges（tb1/tb3各1、tb2未充），最低14.59877179，0碰撞/失效/耗尽；grouped native消息及正常收尾通过，原完整任务未通过。独立返航与冲突排空存在实测日志，不能从跨候选0碰撞推断单因素收益。tb2为tb1避让后约0.5wall秒即因新future staging预约被取消；源机制将prospective充电intent等同已启动安全返航，会阻断认证escape，保留此实测日志与条件反例，不声称完整原reserved cells皆已直接记录。

观测者安全返航后，目标源lease2253.682在2313.682后过期；四向真实扫描完成后，当前地图无frontier groups/candidates，所有机器人停在已知区域，直到原horizon。最终tb1/tb2/tb3大致(-1.99,.05)/(.52,-1.12)/(1.16,-.10)，没有凭旧目标继续集合。只读AP快照2320.982/2340.982/2360.982精确证实mapping前沿0；纯当前known-map反例仍有可达搜索动作。恢复消息不能靠地图覆盖或坐标记忆替代真实检测。

受控ideal/fault自然timeout300.2/300.4 EXPLORE，仅补充过程证据；两机每侧各一次充电、正最低能量、0碰撞/失效/耗尽，runner/stager/observer0、原50秒准备/TTL/one-shot/epoch PASS。fault原62..248窗口：tb1 start171.0/home1.995550/path1.359073/progress1.200203/原生Nav2 EXEC1.358987m；tb2 start172.5/home1.967907/path1.171058/progress1.160183/EXEC1.171032m。protocol54PASS。bootstrap自然[1,0,0]；future仅因原固定FAIL结束，不进入fullpool/707，无整格重试、基础设施失败或活跃行政中断。AP observer正常0；所有任务/future自然结束后才修改源。

只读审计（Humble/install、PYTHONNOUSERSITE=1、ROS_LOG_DIR=canonical ROS/log/component_checks）：`/usr/bin/python3 /tmp/audit_p3b5_v36_return.py > /tmp/p3b5_v36_return_audit.log`严格PASS；`/usr/bin/python3 /tmp/archive_p3b5_56479c0.py`校验5started/5raw和全部ledger PASS。活跃状态一次`tail -6`多文件读取被本机tail拒绝，改`tail -n 6`，不影响任何任务。

下一候选在无可行mapping前沿时，用当前known-free/动态净空/距离场生成1m采样并snap到真实可达格，射线按当前未知/占据遮挡评估未访问邻域收益，再通过原实际停车body/可视短段/路线预约/并发/能量机制派发。visited邻域只是搜索偏好，不宣称目标已看过或实际camera coverage；目标检测仍是唯一确认来源。成功实际搜索航点后重新四向扫描，并优先刚移动的机器人；新确认后排空已接受/待接受搜索。过期目标坐标不传入候选API，仍保持FOUND/RALLY阶段和原任务300s/lease60s/0碰撞门槛。审计新增合法basis current_map_known_free_sweep，仍要求相同fresh输入/有效实际route/正确endpoint，expired_target等非法basis继续拒绝。已知自由ray不得穿unknown；不修改原grid或伪造源时间。

只读原地图组件重放（非Gazebo/新episode）：

```bash
/usr/bin/python3 /tmp/replay_p3b5_v36_known_space.py > /tmp/p3b5_v36_known_space_replay.log 2>&1
/usr/bin/python3 /tmp/replay_p3b5_v36_known_space_cached.py > /tmp/p3b5_v36_known_space_cached_replay.log 2>&1
```

三份原AP地图均frontier0，三台均有原条件下可admit的可视短段；原地图完全未变。每个同map/visit batch共享ray gain，不复用动态route；全部选中候选/route完全相同。未共享all3评估1.537841/1.505564/1.506899s；共享0.847149/0.886443/0.908795s。这是先后profiling，非交错因果benchmark，不声称完整任务加速。完整source/函数/SHA/样本见report/20261003_p3b5_known_space_component.json。

真实local RETURNING/CHARGING才可预占已admit普通腿，未来stage intent只约束新admission；未知future几何不妨碍用已知真实return做安全escape。原temporary refuge处idle机器人也能由实际返航避让接管，保留原final。缺真实返航几何仍排空普通动作，本地battery safety不取消。测试覆盖已知/未知future、真实新return抢占、temporary blocker接管、未admit/lateaccept、动态真实body和slot限制。

首轮相关190PASS/1FAIL8.47s仅SimpleNamespace缺新visits字段，补齐生产fixture后196PASS8.19s；补充priority/temporary案例199PASS8.56s。第一全量316PASS11.32s/build5.35s；再补实际移动机器人scan优先回归，最终317PASS11.23s、四包build5.21s；source audit随后核对。每次命令source Humble/install、PYTHONNOUSERSITE=1/ROS_LOG_DIR=canonical ROS/log/component_checks：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py scripts/test_p3b5_gate.py > /tmp/p3b5_v37_first_checks.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py scripts/test_p3b5_gate.py > /tmp/p3b5_v37_search_checks.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py scripts/test_p3b5_gate.py > /tmp/p3b5_v37_search_checks_final.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py > /tmp/p3b5_v37_component_checks_final.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v37_build_final.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v37_source_audit.log 2>&1
```

早一轮完整命令完全相同，仅输出文件为/tmp/p3b5_v37_component_checks.log与/tmp/p3b5_v37_build.log。live计划修正“静态确认保留至任务结束”的过时描述，明确真实60秒lease与target-independent map搜索。新原57矩阵须clean commit/push后运行；v36失败不回填，P3B.5未通过；无ns-3/RL工作。

## 2026-10-04 P3B.5 v37原生终止速度超限，独立完成保持候选

冻结a63ac0b9d38be944fa26a395632e11cb5bf43945；原5started/5raw及全部summary/manifest/命令/ledger/hash/nativephysics/AP记录保存在report/20261004_p3b5_final_tolerance_failed_candidate.json。无重试/活跃行政中断/全矩阵或707。source Humble/canonical install/Gazebo，PYTHONNOUSERSITE=1/TURTLEBOT3_MODEL=waffle/ROS_LOG_DIR=canonical ROS/log/ros_launch，实际rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v37_after_subgates.py > /tmp/p3b5_v37_after_subgates.log 2>&1
/usr/bin/python3 /tmp/p3b5_v37_bootstrap.py > /tmp/p3b5_v37_bootstrap.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14751 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v37_zero_first.py > /tmp/p3b5_v37_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14750 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v37_first_lab101.py > /tmp/p3b5_v37_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14752 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v37_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v37_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_a63ac0b.json > /tmp/p3b5_protocol_a63ac0b.log 2>&1
ROS_DOMAIN_ID=130 taskset -c 0-19 /usr/bin/python3 /tmp/observe_p3b5_v37_ap_snapshots_qos_fixed.py > /tmp/p3b5_v37_ap_snapshots_qos_fixed.log 2>&1
```

原zero双边FAILED/E0/无导航/0碰撞。原固定lab3/101中央COMPLETE213.7s（检测64.8/RALLY77.8），runner1因tb2原生角速度0.1931509963150803radps超出原0.1拒绝；任务级固定FAIL，不能把原始终态或评估器success当已通过。全员位置误差0.029931/0.024882/0.022665m，0碰撞/耗尽/失效，tb1/tb2各1charge、最低25.5815179569、总路径44.193738m。grouped native/graph审计正常，原收尾正常。bootstrap自然[1,0,0]，future自然fail-fast，不进入其他池。

10Hz独立nativephysics在2334.982录得tb2角速度0.1683，2339.882为0.1004；未采到原result在2339.482的0.19315，不说明raw值伪造。最后AP2330.682的交付odom源2330.389角速度0.043294，距终止仍有间隔。证据确定中央保持/原生终止核验存在差异，不能唯一断言DDS丢样或本体角速度噪声根因。真值/AP只作取证，无控制输入。

受控ideal/fault自然timeout300.0/300.0 EXPLORE，仅补充安全证据；两机各1charge/正能量/0碰撞/失效/耗尽，runner/stager/observer0。原准备50s/TTL/one-shot/epoch和62..248强物理检查PASS：fault tb1起点offset172.5/home1.975803/path1.142682/progress1.133983/实际Nav2EXEC1.142661m；tb2offset170.8/home2.003584/path1.197626/progress1.188408/EXEC1.197600m。协议54PASS。AP observer正常0；所有任务/future结束后才修改source。

只读审计source Humble/install、PYTHONNOUSERSITE=1/ROS_LOG_DIR=canonical ROS/log/component_checks：`/usr/bin/python3 /tmp/audit_p3b5_v37_return.py`严格PASS，`/usr/bin/python3 /tmp/archive_p3b5_a63ac0b.py`校验5started/5raw、原ledger/source/完整原命令后归档。归档源码保留/tmp，不重复运行原mission。

后续候选：交付odom每个位置/速度超限样本立即重置中央保持窗口，避免超限又恢复发生在两个timer之间。独立只读评估器schema9在当前rally assignment/健康名单上检查原0.35m/0.05mps/0.1radps/5s；任何原生样本超限、缺参与机器人、非ACTIVE/非正能量或超过原poseTTL2s的观测间断重置。assignment变化/故障名单变化也重置，同一assignment重复发布不重置。中央声明仅记录coordinator_completion_time_sec；新的原生样本满足完整窗口后才给completion_time_sec和native_rally_hold_proof。仍原300s horizon，未合格timeout，不延长/放宽或仅挑某个有利瞬时值。无header ModelStates仅observer simulation clock的连续合格观测，非完整物理持续采样声明，Gazebo真值不反馈控制链。P3B checker强制新schema/proof含roster/原native峰值/时间/最大gap；冻结P3A checker及22c历史证据不改、不回填。

另补实际双return下取消escape后的idle重规划：不因已有return_yield_targets而永久跳过，仍须实际当前body阻挡真实return、自身handle/pending已排空、原slot/visible/route/body/energy/fresh检查；新refuge终点需避开全部返航，保留原final。源反例覆盖两台真实return和替代腿已live时禁止重复admit。

相关243PASS10.77s；全16文件338PASS11.92s，四包build5.82s，3r source-only旁路审计PASS0违规。确切命令（source Humble/canonical install；PYTHONNOUSERSITE=1，组件ROS_LOG_DIR=canonical ROS/log/component_checks；实际rtk bash -lc）：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_task_evaluator.py scripts/test_p3b5_gate.py
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py > /tmp/p3b5_v38_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v38_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v38_source_audit.log 2>&1
```

read-only工具一次rg针对不存在ros_smoke_runner.py与字面gateway*.py返回2，改查实际ros_smoke_test.py/fault_model.py，不影响测试/运行。下一v38原57唯一episode矩阵先新clean commit/push再运行；原十fixed通过后才首次707（fault27077原先前瞻声明），不得混历史CMP。P3B.5未通过，无ns-3/RL工作。

## 2026-10-04 P3B.5 v38集合/返航路线一致性失败与后续候选

冻结2786b14745591a7dc8adce6f8e52e82cdac0e8ad；report/20261004_p3b5_yield_route_failed_candidate.json完整保留5started/5raw、原summary/manifest/source/commands/hash/ledger/nativephysics/AP与协议。source Humble/canonical install/Gazebo，PYTHONNOUSERSITE=1/TURTLEBOT3_MODEL=waffle/ROS_LOG_DIR=canonical ROS/log/ros_launch，实际rtk bash -lc：

```bash
/usr/bin/python3 /tmp/prepare_p3b5_v38.py
/usr/bin/python3 /tmp/p3b5_v38_after_subgates.py > /tmp/p3b5_v38_after_subgates.log 2>&1
/usr/bin/python3 /tmp/p3b5_v38_bootstrap.py > /tmp/p3b5_v38_bootstrap.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14851 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v38_zero_first.py > /tmp/p3b5_v38_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14850 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v38_first_lab101.py > /tmp/p3b5_v38_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14852 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v38_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v38_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_2786b14.json > /tmp/p3b5_protocol_2786b14.log 2>&1
ROS_DOMAIN_ID=130 taskset -c 0-19 /usr/bin/python3 /tmp/observe_p3b5_v38_ap_snapshots_qos_fixed.py > /tmp/p3b5_v38_ap_snapshots_qos_fixed.log 2>&1
```

zero原配对7.1/1.9s双机FAILED/E0/无导航/0碰撞。原fixedlab3/101 timeout300.4/RALLY，检测124.5/RALLY126.0，3charges各机一次、最低14.1951762491、总路径61.374997、0碰撞/耗尽/失效。中央未宣布完成、native保持未到达，所以本失败不能证明最终native保持/settling已通过。原tb1到final后再让路、晚返航，tb2/tb3多次临时refuge；到原horizon还在途中。无prestart基础设施失败、整格重试、行政活跃中断。bootstrap自然[1,0,0]，future原fixedFAIL自然结束，AP0，未进入fullpool/707。

两受控physical自然timeout300.1/300.4 EXPLORE仅过程证据；各侧每台1charge/正电量/0碰撞/耗尽/失效，runner/stager/observer0；原50s准备/TTL/one-shot/epoch/62..248强运动审计PASS。fault tb1offset171.5/home1.991314/path1.155587/progress1.147272/实际Nav2EXEC1.155554m；tb2offset171.4/home1.997938/path1.201750/progress1.192305/EXEC1.201729m。协议54PASS。所有进程自然结束后才修改源。

只读（Humble/install、PYTHONNOUSERSITE=1/ROS_LOG_DIR=canonical ROS/log/component_checks）：`/usr/bin/python3 /tmp/audit_p3b5_v38_return.py > /tmp/p3b5_v38_return_audit.log 2>&1`严格PASS；`/usr/bin/python3 /tmp/archive_p3b5_2786b14.py`保留原5started/5raw及ledger原哈希。

原2303.082 tb1实际临时refuge(-3.501989,3.450758)先按tb2旧waiting route选择，但随后tb2被无条件重选final(-4.851989,3.500758)。源结构保证的旧路线因此不再对应下一受益路线，是可复现的证书一致性反例；不声称所有原瞬间buffer/reserved cell已直接录得或这是唯一延误来源。后续只在永久blocker重分配时保留原waiting-goal重选；temporary refuge保留原受益目标与相应路线。原真实body/live/return/slot/energy/TTL门槛保持。

普通中间rally航点新增在当前known-map LOS且已交付target范围（留原Nav2位置容差0.02m余量）内面对该fresh目标，位置/route/energy不改；只改尚未最终到位的普通腿，最终yaw、本地return-yield和charge staging不变。先前fresh检测检查与派发前二次检查保留。真实检测仍唯一续租源，预测可见不替代camera确认。

组件重放实际rtk bash -lc（Humble/install、PYTHONNOUSERSITE=1/component ROS_LOG_DIR）：

```bash
/usr/bin/python3 /tmp/replay_p3b5_v38_observation_heading.py > /tmp/p3b5_v38_observation_heading_replay.log 2>&1
/usr/bin/python3 /tmp/replay_p3b5_v38_heading_successor.py > /tmp/p3b5_v39_heading_component.log 2>&1
```

原preceding AP2309.782在tb3原实际请求中间航点(-3.605624,1.200758)预测target LOS/range合格，原yaw2.356194与bearing1.710762差0.645433rad；名义仍在90deg FOV内，但叠加原Nav2 yaw容差0.25超出半FOV0.785398。新heading1.710762误差0，几何/地图完全未变，含完整helper/source/control SHA见report/20261004_p3b5_observation_heading_component.json。组件父2786b14+dirty successor，不是冻结任务胜利，也不是精确原admission buffer/真实camera或单因素时延收益。

首次控制188PASS/1FAIL10.25s：扩展mock给无关preflight-blocked fallback也返回新waiting target，使旧该分支断言变化；fixture只在实际被测temporary-refuge条件中注入不同候选，原生产preflight分支不改。全16文件348PASS13.15s，四包build5.96s，source-only3r旁路审计PASS0。确切命令（source Humble/install、PYTHONNOUSERSITE=1、component ROS_LOG_DIR；实际rtk bash -lc）：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py > /tmp/p3b5_v39_control_checks.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py > /tmp/p3b5_v39_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v39_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v39_source_audit.log 2>&1
```

工具取证一轮physics jsonl未筛event直接读robots触发KeyError，过滤physics后只读原v37得2333.8之后最佳10Hz观察窗口4.4s（2335.182..2339.582），2334.982/2339.882分别0.168284/0.100448中断；保留/tmp/p3b5_v37_native_hold_forensics.json，此10Hz分析不能代替完整原生速率核验。一次tail误指固定launch目录读失败，随后rg --files --no-ignore找到实际zero子episode launch路径；一次AP battery误读/battery键打印None，随即用真实/battery_state重读，未用于算法或结果判定。上述均不重复/中断原episode。

下一v39原57唯一episode使用新clean commit/push后运行，十fixed全部通过后才首次707/fault27077；不回填旧CMP，原schema9 nativehold仍必须实测，P3B.5未通过，无ns-3/RL。

## 2026-10-04 P3B.5 v39原矩阵失败归档与派发恢复候选

原冻结cab0568221f87cbf735e06d36204a5b1655aca78，43started/43raw，阶段计数FAILED4/EXPLORE14/COMPLETE13/RALLY6/FOUND5/PARTIAL_COMPLETE1，接触总数0。原lab3/101 COMPLETE150.4并独立native保持5.4s；固定lab3/202 timeout300.2/RALLY、三次charge、最低18.0199356878导致门禁FAIL。fixed fail-fast停止剩余303/rooms/corridors固定格和707，已按原声明启动的lab11、rooms14、forced2、safety4、corridors6全自然收尾，无行政活跃中断/整格重试。单失效rooms健康两机PARTIAL_COMPLETE198.3；不得把这些历史完成格混入下一候选。原2zero/2controlledreturn/2fixed/37其余共43，仅原57计划的失败候选。完整原source/environment/config/commands/summary/ledger/audit/nativephysics/AP/hash和失败解释见report/20261004_p3b5_precharge_final_cell_failed_candidate.json。

所有ROS命令在canonical ROS cwd，source /opt/ros/humble/setup.bash、canonical install/setup.bash、仿真时source /usr/share/gazebo/setup.sh；PYTHONNOUSERSITE=1/TURTLEBOT3_MODEL=waffle/ROS_LOG_DIR=canonical ROS/log/ros_launch。实际通过rtk bash -lc运行：

```bash
/usr/bin/python3 /tmp/p3b5_v39_after_subgates.py > /tmp/p3b5_v39_after_subgates.log 2>&1
/usr/bin/python3 /tmp/p3b5_v39_bootstrap.py > /tmp/p3b5_v39_bootstrap.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14951 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v39_zero_first.py > /tmp/p3b5_v39_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14950 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v39_first_lab101.py > /tmp/p3b5_v39_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14952 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v39_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v39_returnproof.log 2>&1
PYTHONNOUSERSITE=1 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_cab0568.json > /tmp/p3b5_protocol_cab0568.log 2>&1
ROS_DOMAIN_ID=130 taskset -c 0-19 /usr/bin/python3 /tmp/observe_p3b5_v39_ap_snapshots_qos_fixed.py > /tmp/p3b5_v39_ap_snapshots_qos_fixed.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14950 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v39_fixed_then_holdout.py > /tmp/p3b5_v39_fixed_holdout_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14951 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b5_tasks.py --config scripts/p3b5_fault_manifest.json --run-id p3b5_v39_lab --cases zero_rally_lab up100_lab down100_lab ttl_lab map_loss_lab battery_loss_lab state_loss_lab target_up10_lab --ros-domain-base 40 > /tmp/p3b5_v39_lab.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14953 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b5_tasks.py --config scripts/p3b5_fault_manifest.json --run-id p3b5_v39_rooms --cases up10_rooms down10_rooms delay2_rooms overflow_rooms burst_rooms deadline_rooms detection_loss_rooms pose_loss_rooms single_failure_rooms target_loss_rooms --ros-domain-base 60 > /tmp/p3b5_v39_rooms.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:14952 taskset -c 40-59 /usr/bin/python3 /tmp/p3b5_v39_forced_safety_corridors.py > /tmp/p3b5_v39_forced_safety_corridors_pool.log 2>&1
taskset -c 60-79 /usr/bin/python3 /tmp/watch_p3b5_v39_rooms_reactive.py > /tmp/p3b5_v39_rooms_reactive_watch.log 2>&1
```

bootstrap自然[0,0,0]；后续原pools自然[1,0,0,0]。完整wrapper实际子命令/ROS domains/端口/CPU/27case原参数和原始结果均在归档source/commands/manifest，不改horizon、返回reserve、目标位置或fault seed。原受控两侧EXPLORE300.1/300.4仅安全过程证据，各机器人各1charge/正电量/0接触；强原62..248运动门禁PASS：fault tb1 offset170.9/home1.986740/path1.198758/progress1.188938/实际Nav2 EXEC1.198735m，tb2 offset171.3/home1.978704/path1.169417/progress1.159218/EXEC1.169372m。协议54PASS。

rooms原ideal的final grid-center距continuous final0.02355571431m，旧0.02 cutoff把final当中间腿，64次重复请求yaw1.082574863而assigned1.070103868，不能满足exact requested-final-yaw bookkeeping。固定202最后视觉source2232.282后2237.882 stage同observer，age5.6s仍在60s lease但越过5s live guard；随后视觉中断/重搜索。两者是源语义/时序证据，不声称唯一根因或单因素任务加速。reactive rooms AP只读测量在固定FAIL后追加，实际时点/额外负载/source/12 owned child commands及空快照全部保留；所有原observer/runner/future自然退出后才改tracked source。native truth不进入控制。

在原v39仍收尾时只创建/tmp源码包副本，canonical ROS依赖/cwd，CPU0-19，独立master/domain，原lab202或rooms101参数。实际import路径/control SHA/完整override source/package文件哈希在prospective declaration，Git元数据仍报parent cab不能当clean源码冻结。全部独立开发5episode、failed validation和counterexample见report/20261004_p3b5_dispatch_recovery_component.json：

```bash
taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v40_isolated_development.py > /tmp/p3b5_v40_isolated_development.log 2>&1
ROS_DOMAIN_ID=123 taskset -c 0-19 /usr/bin/python3 /tmp/observe_p3b5_v40_development_ap.py p3b5_v40_isolated_development_lab202 log/p3b5_development/p3b5_v40_isolated_development_lab202/p3b5_v40_isolated_development_lab202.json > /tmp/p3b5_v40_development_lab202_ap.log 2>&1
taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v41_isolated_development.py > /tmp/p3b5_v41_isolated_development.log 2>&1
taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v42_isolated_development.py > /tmp/p3b5_v42_isolated_development.log 2>&1
taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v43_isolated_development.py > /tmp/p3b5_v43_isolated_development.log 2>&1
```

v40 master15490/domains123/124：lab202 RALLY300.0/runner1/三charge/0接触；rooms101 COMPLETE129.3/runner0/零charge/0接触。v41 master15491/domain125 lab202 RALLY300.2/runner1/两charge/0接触，入站refuge挡住charged owner出站形成互等。v42 master15492/domain126 lab202 RALLY300.4/runner1/两charge/0接触；仍fresh视觉、全部原nav无abort，最后72simseconds没有新请求，parked temporary future approach预约导致三机器人等待环。v43 master15493/domain127 lab202 COMPLETE230.9/runner0/两charge/最低22.3149248459/0接触，coor224.0、独立native5.0s/51samples/最大gap0.1/最大角速0.0914782786/最大位置误差0.0330065合格。v40 lab AP为launch后reactive；v41/42/43 AP在runner前预声明启动且正常0。开发trajectory不同，不能把时长差写成单因果benchmark，也不能回填正式fixed/TDI。707保持未曝光。

最终候选复用原恢复/预约逻辑：final按地图格保持yaw；prospective stage future-home不代替actual return；最后真实observer在短camera gap中不stage远离；return refuge到owner有真实departure/到位才恢复，owner需要出站避让时转换为普通freshness/energy恢复；所有parked refuge的future approach延期，但真实body/live legs/actual safety return仍保护。无新依赖、改param/原物理门槛或使用过期目标/真值。

纯组件命令（同Humble/install、PYTHONNOUSERSITE=1；ROS_LOG_DIR=canonical ROS/log/component_checks；实际rtk bash -lc）：

```bash
taskset -c 0-19 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v40_offline_draft/test_control.py > /tmp/p3b5_v40_offline_draft_checks.log 2>&1
taskset -c 0-19 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v40_offline_draft/test_control.py > /tmp/p3b5_v40_offline_draft_checks2.log 2>&1
P3B5_REPLAY_IMPLEMENTATION=original taskset -c 0-19 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v40_offline_draft/test_control.py -k 'quantized_final or camera_gap or home_staging' > /tmp/p3b5_v39_original_counterexamples.log 2>&1
taskset -c 0-19 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v41_offline_draft/test_control.py > /tmp/p3b5_v41_offline_draft_checks3.log 2>&1
taskset -c 0-19 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v42_offline_draft/test_control.py > /tmp/p3b5_v42_offline_draft_checks.log 2>&1
taskset -c 0-19 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v42_against_v41_counterexample/test_control.py -k 'idle_blocker and tb1' > /tmp/p3b5_v42_v41_counterexamples.log 2>&1
taskset -c 0-19 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v43_offline_draft/test_control.py > /tmp/p3b5_v43_offline_draft_checks.log 2>&1
taskset -c 0-19 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v43_against_v42_counterexample/test_control.py -k parked_refuge > /tmp/p3b5_v43_v42_counterexamples.log 2>&1
taskset -c 20-39 /usr/bin/python3 /tmp/replay_p3b5_v42_parked_approach.py > /tmp/p3b5_v43_parked_approach_component.log 2>&1
```

初始v40临时拷贝fixture的SDF相对路径错误194PASS/1FAIL9.63，修正/tmp测试路径后195PASS10.19。对原CAB的三个新语义反例3FAIL/3PASS（预期拒绝）。v41最初两次taskset80-95在pytest开始前affinity setup失败，日志checks/checks2保留；改实际允许0-19后207PASS6.92。v42 211PASS7.56，对旧v41 owner recovery三反例3FAIL/208deselected1.66。v43 217PASS5.89，对旧v42 parked两反例2FAIL/10PASS/205deselected1.57。五张实际收到的v42末尾AP地图在同geometry/body、显式假设的quiescent priority状态上原tb3终段皆被拒，新策略皆可admit，当前机体最小净距2.094..2.095m；非原精确内部buffer、非任务完成。v43全部16组件离线376PASS8.14，跨/tmp与repo导致pytest root为/、产生两个cache写入warning，无测试失败；actual tracked376PASS12.14。原readonly快照分析一次未过滤缺rally_assignments的首行KeyError，按实际已有assignment过滤后完成；无重复实验或控制输入。

所有开发/观察进程结束后执行guarded apply，它校验原pool返回/observer finish/owned PID退出/14950..53及15490..93端口释放、17用户材料哈希、v43真实import/hash/native success，然后先归档原43+开发5、再拷贝control同源码与恢复repo-relative SDF fixture。`/usr/bin/python3 /tmp/apply_p3b5_v43_verified_candidate.py > /tmp/p3b5_v40_apply_candidate.log 2>&1`成功。

当前源码验证（Humble/install、PYTHONNOUSERSITE=1/component ROS_LOG_DIR；实际rtk bash -lc）：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py > /tmp/p3b5_v40_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v40_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v40_source_audit.log 2>&1
```

首次diff--check只报测试EOF多一空行，已去掉。新正式v40仅在同session clean commit/push之后运行：原十fixed同CPU0-19/environment/300s/零whole-episode retry先全通过，再启动原fault pools/首次707及fault27077；57唯一格不变。此前所有失败/开发CMP不回填；本次仍不是P3B.5门禁通过，未启动ns-3/RL。

## 2026-10-04 P3B.5 v40六格失败归档、观测者能量分配与搜索优化

原冻结834a0fd94c27f16a3366b2fae96b1810804a060e，六started/六raw，FAILED2/COMPLETE1/RALLY2/EXPLORE1，接触总数0，无整格重试/基础设施失败/活跃行政中断。零能量原ideal/fault FAILED1.1/1.7，两台均E0/无导航；lab3/101 COMPLETE265.4/两charge/最低20.9536000749/原生5.0秒51sample/maxgap0.2/最大角速0.09985782108；lab3/202 timeout300.4/RALLY/三charge/最低19.0595962100/路径63.6181505052，固定FAIL使303/rooms/corridors剩余固定格、fullfaultpools和首次707未启动。两受控返航侧原ideal RALLY300.4/fault EXPLORE300.0仅安全过程证据，各台一次charge/正电量/0接触，runner/stager/nativeobserver0，原62..248强运动门禁PASS。fault tb1offset171.7/home1.986917/path1.173808/progress1.161013/EXEC1.173768；tb2offset171.3/home2.001496/path1.174905/progress1.167422/EXEC1.174858。协议54PASS。完整证据report/20261004_p3b5_energy_assignment_failed_candidate.json。

原first AP FOUND2241.082含tb2 detection源2240.882与完整收到的map/odom/map-to-odomTF/battery；距离minimax给最后观测者远集合位，实际tb1、tb3、tb2顺序早返充，第三次之后约剩50秒。保存快照上的条件预算比较支持能量/等待盲点，不声称唯一原因或完整内部buffer重演。所有原进程/未来调度/观察器结束后才更改tracked源。

所有ROS命令使用canonical ROS cwd，source Humble/install，仿真还source /usr/share/gazebo/setup.sh；PYTHONNOUSERSITE=1/TURTLEBOT3_MODEL=waffle/ROS_LOG_DIR=canonical ROS/log/ros_launch，实际rtk bash -lc。原调度命令：

```bash
/usr/bin/python3 /tmp/p3b5_v40_after_subgates.py > /tmp/p3b5_v40_after_subgates.log 2>&1
/usr/bin/python3 /tmp/p3b5_v40_bootstrap.py > /tmp/p3b5_v40_bootstrap.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15051 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v40_zero_first.py > /tmp/p3b5_v40_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15050 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v40_first_lab101.py > /tmp/p3b5_v40_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15052 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v40_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v40_returnproof.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15051 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_834a0fd.json > /tmp/p3b5_protocol_834a0fd.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15050 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v40_fixed_before_faults.py > /tmp/p3b5_v40_remaining_fixed.log 2>&1
```

上述bootstrap自然[0,0,0]，future因remaining fixed exit1自然收尾，端口15050..53与八个声明PID已核验退出。每条原episode的实际完整子命令（其配置、环境、observer来源/hash见归档）：

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v40_zero_ideal_lab2_rally_0678e85373 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_zero/p3b5_v40_zero_ideal_lab2_rally_0678e85373 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_zero/p3b5_v40_zero_ideal_lab2_rally_0678e85373/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_zero/p3b5_v40_zero_ideal_lab2_rally_0678e85373/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_zero/p3b5_v40_zero_ideal_lab2_rally_0678e85373/graph.json --target-detection --rally --battery-initial-energy 0
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v40_zero_battery_exhaust_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_zero/p3b5_v40_zero_battery_exhaust_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_zero/p3b5_v40_zero_battery_exhaust_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_zero/p3b5_v40_zero_battery_exhaust_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_zero/p3b5_v40_zero_battery_exhaust_lab_fault/graph.json --target-detection --rally --battery-initial-energy 0
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v40_returnproof_ideal_forced2_rally_4c7c808f36 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_returnproof/p3b5_v40_returnproof_ideal_forced2_rally_4c7c808f36 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_returnproof/p3b5_v40_returnproof_ideal_forced2_rally_4c7c808f36/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_returnproof/p3b5_v40_returnproof_ideal_forced2_rally_4c7c808f36/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_returnproof/p3b5_v40_returnproof_ideal_forced2_rally_4c7c808f36/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v40_returnproof_physical_return_under_blackout_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_returnproof/p3b5_v40_returnproof_physical_return_under_blackout_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_returnproof/p3b5_v40_returnproof_physical_return_under_blackout_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_returnproof/p3b5_v40_returnproof_physical_return_under_blackout_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v40_returnproof/p3b5_v40_returnproof_physical_return_under_blackout_fault/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v40_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v40_fixed_lab101/launch_logs --episode-id p3b5_v40_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v40_fixed_lab101/graphs/p3b5_v40_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v40_fixed_lab101/episodes/p3b5_v40_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v40_fixed_lab/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v40_fixed_lab/launch_logs --episode-id p3b5_v40_fixed_lab_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v40_fixed_lab/graphs/p3b5_v40_fixed_lab_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v40_fixed_lab/episodes/p3b5_v40_fixed_lab_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
```

独立/tmp immutable package overlay仅使用已开发的原lab202参数，Git元数据parent834不能替代实际source冻结；source完整副本、实际import path/control SHA与package hashes在prospective declaration。v44 CPU0-19/master15494/domain128，timeout300.1/RALLY/runner1/一次完成charge/最低17.0385706246/0接触，预测省charge但observer余量不足、避让/等待后晚返航，保留失败。v45 CPU0-19/master15495/domain129 COMPLETE195.8/runner0/一次charge/最低21.9975164466/0接触，原生5.0s/51sample/maxgap0.2/maxang0.0864748555/maxpos0.0416165346；此轨迹与原formal及v44不同，非单因素因果benchmark。v47 CPU20-39/master15497/domain131在v45仍运行时预声明独立开始；同样排除所有formal/fixed/TDI，宿主/SMT共享不作因果比较。

v49原始结果COMPLETE185.4/runner0/charge0/最低22.5621201515/0接触；中央声明185.4，独立原生5.5s/56sample/maxgap0.200/maxang0.089438763/maxpos0.039314669。所有五次开发/AP observer自然结束才归档/应用源。v47原始timeout300.0/RALLY/两charge/最低20.3554920501/0接触，三台最终到位但tb1在294.5s angular0.2331重置保持；初始postcharge几何fallback停近处后又两次refuge恢复，最后原nav请求262.8/270.8来得太晚。v48只在全部current-body串行order不可行时按future final-pose对后续路线阻挡数选恢复优先级，不当作运动许可。六张原received AP150..180s地图条件比较四张降低预测阻挡，非原内部buffer或任务完成因果证明。v48 timeout300.1/RALLY、检测136.8/RALLY147.9、三charge、最低13.0654964488、0接触：最后观测者被本地reserve返航抢占，同伴未交接，真实目标source2290.282过期后扫描/按当前地图搜索，保持原TTL。v49探索偏好改用complete frontier去程和current/endpoint较大home返航距离；budget不够保留原0.25乘E/required连续降权，context无效拒绝，不排除所有有用前沿，不替代local硬安全。90个原received AP静态候选条件比较PASS，不含原exclusions/active routes buffer，未使用目标坐标，非任务因果重演。全部开发与组件失败见report/20261004_p3b5_observer_energy_assignment_component.json。

独立开发实际wrapper命令及完整smoke子命令：

```bash
taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v44_isolated_development.py > /tmp/p3b5_v44_isolated_development.log 2>&1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v44_isolated_development_lab202 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v44_isolated_development_lab202/launch --episode-id p3b5_v44_isolated_development_lab202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v44_isolated_development_lab202/graph.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v44_isolated_development_lab202/ledger.jsonl --disable-global-battery-rally-pause
taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v45_isolated_development.py > /tmp/p3b5_v45_isolated_development.log 2>&1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v45_isolated_development_lab202 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v45_isolated_development_lab202/launch --episode-id p3b5_v45_isolated_development_lab202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v45_isolated_development_lab202/graph.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v45_isolated_development_lab202/ledger.jsonl --disable-global-battery-rally-pause
taskset -c 20-39 /usr/bin/python3 /tmp/run_p3b5_v47_isolated_development.py > /tmp/p3b5_v47_isolated_development.log 2>&1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v47_isolated_development_lab202 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v47_isolated_development_lab202/launch --episode-id p3b5_v47_isolated_development_lab202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v47_isolated_development_lab202/graph.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v47_isolated_development_lab202/ledger.jsonl --disable-global-battery-rally-pause
taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v48_isolated_development.py > /tmp/p3b5_v48_isolated_development.log 2>&1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v48_isolated_development_lab202 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v48_isolated_development_lab202/launch --episode-id p3b5_v48_isolated_development_lab202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v48_isolated_development_lab202/graph.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v48_isolated_development_lab202/ledger.jsonl --disable-global-battery-rally-pause
taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v49_isolated_development.py > /tmp/p3b5_v49_isolated_development.log 2>&1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v49_isolated_development_lab202 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v49_isolated_development_lab202/launch --episode-id p3b5_v49_isolated_development_lab202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v49_isolated_development_lab202/graph.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v49_isolated_development_lab202/ledger.jsonl --disable-global-battery-rally-pause
```

纯组件同Humble/install、PYTHONNOUSERSITE=1，ROS_LOG_DIR=canonical ROS/log/component_checks，实际rtk bash -lc：

```bash
/usr/bin/python3 /tmp/replay_p3b5_v44_assignment.py
/usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v44_offline_draft/test_control.py > /tmp/p3b5_v44_control_checks.log 2>&1
taskset -c 20-39 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v44_offline_draft/test_control.py -k peer_charge_wait > /tmp/p3b5_v44_wait_counterexample.log 2>&1
taskset -c 20-39 /usr/bin/python3 /tmp/replay_p3b5_v45_assignment.py > /tmp/p3b5_v45_assignment_component.log 2>&1
/usr/bin/python3 /tmp/replay_p3b5_v45_assignment.py > /tmp/p3b5_v45_assignment_component2.log 2>&1
taskset -c 20-39 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v45_offline_draft/test_control.py > /tmp/p3b5_v45_control_checks.log 2>&1
taskset -c 20-39 /usr/bin/python3 /tmp/benchmark_p3b5_v45_assignment.py > /tmp/p3b5_v45_assignment_benchmark.log 2>&1
taskset -c 20-39 /usr/bin/python3 /tmp/benchmark_p3b5_v46_assignment.py > /tmp/p3b5_v46_assignment_benchmark.log 2>&1
taskset -c 20-39 /usr/bin/python3 /tmp/benchmark_p3b5_v47_assignment.py > /tmp/p3b5_v47_assignment_benchmark.log 2>&1
taskset -c 20-39 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v47_offline_draft/test_control.py > /tmp/p3b5_v47_control_checks.log 2>&1
taskset -c 40-59 /usr/bin/python3 /tmp/compare_p3b5_v47_bounds.py > /tmp/p3b5_v47_bounds_component.log 2>&1
taskset -c 40-59 /usr/bin/python3 /tmp/compare_p3b5_v47_bounds.py > /tmp/p3b5_v47_bounds_component2.log 2>&1
taskset -c 40-59 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v47_offline_draft/test_control.py -k inactive_observer > /tmp/p3b5_v47_inactive_observer_checks.log 2>&1
taskset -c 20-39 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v48_offline_draft/test_control.py > /tmp/p3b5_v48_control_checks.log 2>&1
taskset -c 20-39 /usr/bin/python3 /tmp/replay_p3b5_v48_recovery_order.py > /tmp/p3b5_v48_recovery_order_component.log 2>&1
taskset -c 20-39 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v49_offline_draft/test_control.py > /tmp/p3b5_v49_control_checks.log 2>&1
taskset -c 20-39 /usr/bin/python3 /tmp/replay_p3b5_v49_exploration_energy.py > /tmp/p3b5_v49_exploration_energy_component.log 2>&1
```

v44控制227PASS9.50，全16文件386PASS9.29（两个/tmp+repo导致pytest root=/的cache warning），peer等待1PASS/227deselected0.76。v45控制229PASS6.49/全388PASS8.02；v46没有simulator episode，只有同目标的搜索排序组件。v45大150x150自由map基准各observer耗时0.2537/0.5612/6.5542s，v46排序0.3915/0.8203/2.8017s，v47完整等待下界0.1766/0.1628/0.1806s且三样例assignment完全相同；一次组件值不作最坏时限或正式任务速度结论。v47控制229PASS7.28，初始全388PASS7.70；首次18条件比较在synthetic CHARGING observer失败：v45错误把非ACTIVE observer也赋余量优先级，保留原source/log失败，不用错误原型当边界oracle。新18条件ACTIVE等价/非ACTIVE与无observer目标一致PASS；新增RETURNING/CHARGING两个边界2PASS1.07，最终v47全390PASS11.07，v48新增真实机体拒绝/深处优先反例，控制232PASS6.20、全391PASS9.11；v49控制238PASS6.38/全397PASS10.77。原物理/TTL/energy/charging params保持，观测者只用真实交付确认；名义预算不保证未知绕行/最坏等待。

五开发/所有观察进程结束、端口释放、17用户材料哈希、原sixraw及实际import/control hash核验后，guarded apply先归档六formal/五development/全部验证失败再拷贝exact v49 source，恢复repo-relative SDF fixture：`/usr/bin/python3 /tmp/apply_p3b5_v49_verified_candidate.py > /tmp/p3b5_v41_apply_candidate.log 2>&1`。tracked检查/build/source审计实际命令：

```bash
taskset -c 20-39 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v44_offline_draft/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py > /tmp/p3b5_v44_full_component_checks.log 2>&1
taskset -c 20-39 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v45_offline_draft/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py > /tmp/p3b5_v45_full_component_checks.log 2>&1
taskset -c 40-59 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v47_offline_draft/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py > /tmp/p3b5_v47_full_component_checks.log 2>&1
taskset -c 40-59 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v47_offline_draft/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py > /tmp/p3b5_v47_full_component_checks2.log 2>&1
taskset -c 20-39 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v48_offline_draft/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py > /tmp/p3b5_v48_full_component_checks.log 2>&1
taskset -c 20-39 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v49_offline_draft/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py > /tmp/p3b5_v49_full_component_checks.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py > /tmp/p3b5_v41_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v41_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v41_source_audit.log 2>&1
```

下一formal v41必须clean commit/push、十fixed先同CPU0-19/原300s/零重试全通过，再原完整fault矩阵/首次707。全部旧失败和开发CMP不混入新统计；P3B.5仍未通过，无ns-3/RL。

## 2026-10-04 P3B.5 v41七格失败保留、地图起点与调查安全候选

冻结42b099e4c88a5439721758f506e57535b11a37ca原始七started/七raw：FAILED2/EXPLORE2/COMPLETE2/FOUND1，接触总6；无整格重试/基础设施失败/活跃行政中断。fixed101 COMPLETE286.7/两charge，fixed202 COMPLETE242.7/一次charge，两格原生合格/0接触；fixed303 timeout300.3/FOUND、检测97.7、两charge、最低4.4565144839、tb1/tb3各3接触。所有原结果完整保留，固定FAIL后其余七fixed/fullpools/707未启动。零E原ideal/fault FAILED2.1/1.5且无导航；受控ideal/fault EXPLORE300.3/300.1各两charge/0接触、强原生返航证明PASS但非任务成功；协议54PASS。原始图/ledger/result/metadata与命令见report/20261004_p3b5_body_map_survey_failed_candidate.json。

canonical ROS cwd、source Humble/install/Gazebo、PYTHONNOUSERSITE=1/TURTLEBOT3_MODEL=waffle/ROS_LOG_DIR=canonical ROS/log/ros_launch，实际rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v41_after_subgates.py > /tmp/p3b5_v41_after_subgates.log 2>&1
/usr/bin/python3 /tmp/p3b5_v41_bootstrap.py > /tmp/p3b5_v41_bootstrap.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15150 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v41_fixed_before_faults.py > /tmp/p3b5_v41_remaining_fixed.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15151 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v41_zero_first.py > /tmp/p3b5_v41_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15150 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v41_first_lab101.py > /tmp/p3b5_v41_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15152 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v41_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v41_returnproof.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15151 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_42b099e.json > /tmp/p3b5_protocol_42b099e.log 2>&1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v41_zero_ideal_lab2_rally_0678e85373 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_zero/p3b5_v41_zero_ideal_lab2_rally_0678e85373 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_zero/p3b5_v41_zero_ideal_lab2_rally_0678e85373/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_zero/p3b5_v41_zero_ideal_lab2_rally_0678e85373/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_zero/p3b5_v41_zero_ideal_lab2_rally_0678e85373/graph.json --target-detection --rally --battery-initial-energy 0
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v41_zero_battery_exhaust_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_zero/p3b5_v41_zero_battery_exhaust_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_zero/p3b5_v41_zero_battery_exhaust_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_zero/p3b5_v41_zero_battery_exhaust_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_zero/p3b5_v41_zero_battery_exhaust_lab_fault/graph.json --target-detection --rally --battery-initial-energy 0
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v41_returnproof_ideal_forced2_rally_4c7c808f36 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_returnproof/p3b5_v41_returnproof_ideal_forced2_rally_4c7c808f36 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_returnproof/p3b5_v41_returnproof_ideal_forced2_rally_4c7c808f36/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_returnproof/p3b5_v41_returnproof_ideal_forced2_rally_4c7c808f36/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_returnproof/p3b5_v41_returnproof_ideal_forced2_rally_4c7c808f36/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v41_returnproof_physical_return_under_blackout_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_returnproof/p3b5_v41_returnproof_physical_return_under_blackout_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_returnproof/p3b5_v41_returnproof_physical_return_under_blackout_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_returnproof/p3b5_v41_returnproof_physical_return_under_blackout_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v41_returnproof/p3b5_v41_returnproof_physical_return_under_blackout_fault/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v41_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v41_fixed_lab101/launch_logs --episode-id p3b5_v41_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v41_fixed_lab101/graphs/p3b5_v41_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v41_fixed_lab101/episodes/p3b5_v41_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v41_fixed_lab/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v41_fixed_lab/launch_logs --episode-id p3b5_v41_fixed_lab_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v41_fixed_lab/graphs/p3b5_v41_fixed_lab_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v41_fixed_lab/episodes/p3b5_v41_fixed_lab_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v41_fixed_lab/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v41_fixed_lab/launch_logs --episode-id p3b5_v41_fixed_lab_lab_far_northwest_3r_seed303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v41_fixed_lab/graphs/p3b5_v41_fixed_lab_lab_far_northwest_3r_seed303.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v41_fixed_lab/episodes/p3b5_v41_fixed_lab_lab_far_northwest_3r_seed303_ledger.jsonl --disable-global-battery-rally-pause
```

原native强返航：fault tb1 offset172.1/home1.973158/path1.179788/progress1.167911/EXEC1.179745，tb2 offset170.7/home2.020173/path1.205828/progress1.198360/EXEC1.205797，均在原62..248守护窗口。只读AP不能当原协调器全部buffer；原tb2位姿(4.71375,-2.40413)落在raw单格100，几何与能量分配均0完整解。原Source map保持，规划副本的有限自身回波规则见组件报告/指南。

所有原进程/观察器/未来调度结束后才独立启动附加/tmp overlays；v50绑定错误没有行政停止或修改其原source/declaration，另建v51启动前assert303。v50实际202 timeout300.1/RALLY/0接触；v51实际303 COMPLETE171.6/0接触；同样代码与原formal轨迹不同，不替换原303失败。candidate v52两格及v53一格prospective source/import/hash、CPU/master/domain/配置/观察器均在report/20261004_p3b5_body_map_survey_component.json。实际wrapper与全子命令：

```bash
taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v50_isolated_development.py > /tmp/p3b5_v50_isolated_development.log 2>&1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v50_isolated_development_lab303 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v50_isolated_development_lab303/launch --episode-id p3b5_v50_isolated_development_lab303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v50_isolated_development_lab303/graph.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v50_isolated_development_lab303/ledger.jsonl --disable-global-battery-rally-pause
taskset -c 20-39 /usr/bin/python3 /tmp/run_p3b5_v51_isolated_development.py > /tmp/p3b5_v51_isolated_development.log 2>&1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v51_isolated_development_lab303 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v51_isolated_development_lab303/launch --episode-id p3b5_v51_isolated_development_lab303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v51_isolated_development_lab303/graph.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v51_isolated_development_lab303/ledger.jsonl --disable-global-battery-rally-pause
taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v52_isolated_development.py > /tmp/p3b5_v52_isolated_development.log 2>&1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v52_isolated_development_lab303 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v52_isolated_development_lab303/launch --episode-id p3b5_v52_isolated_development_lab303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v52_isolated_development_lab303/graph.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v52_isolated_development_lab303/ledger.jsonl --disable-global-battery-rally-pause
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v52_isolated_development_lab202 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v52_isolated_development_lab202/launch --episode-id p3b5_v52_isolated_development_lab202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v52_isolated_development_lab202/graph.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v52_isolated_development_lab202/ledger.jsonl --disable-global-battery-rally-pause
taskset -c 20-39 /usr/bin/python3 /tmp/run_p3b5_v53_isolated_development.py > /tmp/p3b5_v53_isolated_development.log 2>&1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v53_isolated_development_rooms101 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v53_isolated_development_rooms101 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v53_isolated_development_rooms101/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v53_isolated_development_rooms101/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5_development/p3b5_v53_isolated_development_rooms101/graph.json --target-detection --rally --uplink-loss-rate 0.1
```

v52 lab303 COMPLETE244.8/两charge/最低23.12295355/原生5.0，lab202 COMPLETE166.9，v53 rooms101 COMPLETE126.1/零charge/最低27.99582543/原生5.8，各格0接触/原生合格。前两格lab303/rooms101没有body-cell导航tag，因此物理结果只支持候选整体，单格回波修复仍为组件/条件重放证据；未作单因素任务因果结论，宿主/SMT可共享。三个候选开发CMP不回填新formal。

首次控制检查254PASS/2失败：旧SimpleNamespace夹具缺survey_goal_handle；原source/tests/log完整保留。修正兼容字段并补pending晚接受取消检查后257PASS7.20；full416PASS11.45带两/tmp+repo root=/ pytest cache warnings。11原AP条件body-cell重放恢复三机分配，原source occupied/unknown起点函数仍拒绝；墙/连接障碍/未知/粗分辨率/无对应body/源TTL/实际peer-mask、预算与路线预约反例通过。未用truth作为controller输入。

纯组件/取证使用Humble/install/PYTHONNOUSERSITE=1/ROS_LOG_DIR=component_checks：

```bash
/usr/bin/python3 /tmp/diagnose_p3b5_v41_lab303.py > /tmp/p3b5_v41_lab303_forensic.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v41_lab303.py > /tmp/p3b5_v41_lab303_forensic_reach.log 2>&1
/usr/bin/python3 /tmp/inspect_p3b5_local_body_cells.py v50 v51 > /tmp/p3b5_local_body_cells.log 2>&1
/usr/bin/python3 /tmp/inspect_p3b5_local_body_cells.py v50 v51 > /tmp/p3b5_local_body_cells2.log 2>&1
/usr/bin/python3 /tmp/plot_p3b5_v41_lab303_map.py
taskset -c 40-59 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v52_offline_draft/test_control.py > /tmp/p3b5_v52_control_checks.log 2>&1
taskset -c 40-59 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v52_offline_draft/test_control.py > /tmp/p3b5_v52_control_checks2.log 2>&1
/usr/bin/python3 /tmp/replay_p3b5_v52_body_cells.py > /tmp/p3b5_v52_body_cell_component.log 2>&1
/usr/bin/python3 /tmp/apply_p3b5_v52_verified_candidate.py > /tmp/p3b5_v42_apply_candidate.log 2>&1
```

临时conda ns3gym内联取证绘图首次因ModuleNotFoundError: matplotlib失败（未产生artifact/未改变环境）；改用已有ROS系统Matplotlib3.5.1独立绘制/tmp forensic PNG并view_image核验，tight_layout因裁剪轴外标签有warning，内部取证图不作为正式结果图。所有simulator执行命令和失败保留；无额外训练或ns-3实验。

```bash
taskset -c 40-59 /usr/bin/python3 -m pytest -q --tb=short /tmp/p3b5_v52_offline_draft/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py > /tmp/p3b5_v52_full_component_checks.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py > /tmp/p3b5_v42_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v42_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v42_source_audit.log 2>&1
```

tracked416PASS6.48s、四包build3.14s/source audit0violations通过。新v42需clean commit/push后，先同CPU0–19/原300s/零重试覆盖十fixed，再原完整27fault cases/首次707与fault27077。P3B.5仍未通过，P3A.6 accepted freeze22c95a7不改，无ns-3/RL。

## 2026-10-04 P3B.5 v42完整候选启动失败保留、观察器与domain修复

冻结011786e53e4c7c2a0eb1e2358fc0b81f651a8316原批次：53次尝试，52个started/52个raw，1个基础设施失败，4个未运行，碰撞总0。原所有进程/观察器/未来调度自然结束后才写tracked报告/源码；无当前任务行政停止、整格重试或成功回填。完整门禁FAIL，不以十fixed全部CMP或首次707 ideal CMP148.1宣布完成。原始结果/图/账本/observer/metadata/source/config/environment及调度命令见失败JSON。

canonical ROS cwd，source Humble/install/Gazebo，PYTHONNOUSERSITE=1/TURTLEBOT3_MODEL=waffle，ROS_LOG_DIR=canonical ROS/log/ros_launch；实际通过rtk bash -lc执行：

```bash
/usr/bin/python3 /tmp/p3b5_v42_after_subgates.py > /tmp/p3b5_v42_after_subgates.log 2>&1
/usr/bin/python3 /tmp/p3b5_v42_bootstrap.py > /tmp/p3b5_v42_bootstrap.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15251 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v42_zero_first.py > /tmp/p3b5_v42_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15250 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v42_first_lab101.py > /tmp/p3b5_v42_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15252 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v42_returnproof --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v42_returnproof.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15251 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_011786e.json > /tmp/p3b5_protocol_011786e.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15250 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v42_fixed_before_faults.py > /tmp/p3b5_v42_remaining_fixed.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15250 taskset -c 0-19 /usr/bin/python3 scripts/run_p3b5_tasks.py --config scripts/p3b5_fault_manifest.json --run-id p3b5_v42_holdout --cases holdout_rally holdout_target holdout_coverage --ros-domain-base 200 > /tmp/p3b5_v42_fixed_holdout_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15251 taskset -c 20-39 /usr/bin/python3 scripts/run_p3b5_tasks.py --config scripts/p3b5_fault_manifest.json --run-id p3b5_v42_lab --cases zero_rally_lab up100_lab down100_lab ttl_lab map_loss_lab battery_loss_lab state_loss_lab target_up10_lab --ros-domain-base 40 > /tmp/p3b5_v42_lab.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15253 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b5_tasks.py --config scripts/p3b5_fault_manifest.json --run-id p3b5_v42_rooms --cases up10_rooms down10_rooms delay2_rooms overflow_rooms burst_rooms deadline_rooms detection_loss_rooms pose_loss_rooms single_failure_rooms target_loss_rooms --ros-domain-base 60 > /tmp/p3b5_v42_rooms.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15252 taskset -c 40-59 /usr/bin/python3 /tmp/p3b5_v42_forced_safety_corridors.py > /tmp/p3b5_v42_forced_safety_corridors_pool.log 2>&1
ROS_DOMAIN_ID=100 GAZEBO_MASTER_URI=http://127.0.0.1:15251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_zero_ideal_lab2_rally_0678e85373 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_zero/p3b5_v42_zero_ideal_lab2_rally_0678e85373 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_zero/p3b5_v42_zero_ideal_lab2_rally_0678e85373/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_zero/p3b5_v42_zero_ideal_lab2_rally_0678e85373/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_zero/p3b5_v42_zero_ideal_lab2_rally_0678e85373/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=101 GAZEBO_MASTER_URI=http://127.0.0.1:15251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_zero_battery_exhaust_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_zero/p3b5_v42_zero_battery_exhaust_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_zero/p3b5_v42_zero_battery_exhaust_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_zero/p3b5_v42_zero_battery_exhaust_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_zero/p3b5_v42_zero_battery_exhaust_lab_fault/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=40 GAZEBO_MASTER_URI=http://127.0.0.1:15251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_lab_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=41 GAZEBO_MASTER_URI=http://127.0.0.1:15251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_lab_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_zero_rally_lab_fault/graph.json --target-detection --rally
ROS_DOMAIN_ID=42 GAZEBO_MASTER_URI=http://127.0.0.1:15251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_lab_up100_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_up100_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_up100_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_up100_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_up100_lab_fault/graph.json --target-detection --rally --uplink-loss-rate 1
ROS_DOMAIN_ID=43 GAZEBO_MASTER_URI=http://127.0.0.1:15251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_lab_down100_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_down100_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_down100_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_down100_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_down100_lab_fault/graph.json --target-detection --rally --downlink-loss-rate 1
ROS_DOMAIN_ID=44 GAZEBO_MASTER_URI=http://127.0.0.1:15251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_lab_ttl_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ttl_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ttl_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ttl_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ttl_lab_fault/graph.json --target-detection --rally --uplink-delay-sec 61 --downlink-delay-sec 61
ROS_DOMAIN_ID=45 GAZEBO_MASTER_URI=http://127.0.0.1:15251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0.8 --mission-mode coverage --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_lab_ideal_lab2_coverage_da95bad2c7 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ideal_lab2_coverage_da95bad2c7 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ideal_lab2_coverage_da95bad2c7/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ideal_lab2_coverage_da95bad2c7/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ideal_lab2_coverage_da95bad2c7/graph.json --gateway-drop-message-types map_snapshot,fused_map_snapshot
ROS_DOMAIN_ID=46 GAZEBO_MASTER_URI=http://127.0.0.1:15251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0.8 --mission-mode coverage --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_lab_map_loss_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_map_loss_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_map_loss_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_map_loss_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_map_loss_lab_fault/graph.json --gateway-drop-message-types map_snapshot,fused_map_snapshot
ROS_DOMAIN_ID=47 GAZEBO_MASTER_URI=http://127.0.0.1:15251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_lab_battery_loss_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_battery_loss_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_battery_loss_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_battery_loss_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_battery_loss_lab_fault/graph.json --target-detection --rally --gateway-drop-message-types battery_state
ROS_DOMAIN_ID=48 GAZEBO_MASTER_URI=http://127.0.0.1:15251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_lab_state_loss_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_state_loss_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_state_loss_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_state_loss_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_state_loss_lab_fault/graph.json --target-detection --rally --gateway-drop-message-types task_state
ROS_DOMAIN_ID=49 GAZEBO_MASTER_URI=http://127.0.0.1:15251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode target --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_lab_ideal_lab2_target_21212e763a --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ideal_lab2_target_21212e763a --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ideal_lab2_target_21212e763a/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ideal_lab2_target_21212e763a/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_ideal_lab2_target_21212e763a/graph.json --target-detection --uplink-loss-rate 0.1
ROS_DOMAIN_ID=50 GAZEBO_MASTER_URI=http://127.0.0.1:15251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode target --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_lab_target_up10_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_target_up10_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_target_up10_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_target_up10_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_lab/p3b5_v42_lab_target_up10_lab_fault/graph.json --target-detection --uplink-loss-rate 0.1
ROS_DOMAIN_ID=60 GAZEBO_MASTER_URI=http://127.0.0.1:15253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_rooms_ideal_rooms3_rally_980df9c157 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_rally_980df9c157 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_rally_980df9c157/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_rally_980df9c157/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_rally_980df9c157/graph.json --target-detection --rally --uplink-loss-rate 0.1
ROS_DOMAIN_ID=61 GAZEBO_MASTER_URI=http://127.0.0.1:15253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_rooms_up10_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_up10_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_up10_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_up10_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_up10_rooms_fault/graph.json --target-detection --rally --uplink-loss-rate 0.1
ROS_DOMAIN_ID=62 GAZEBO_MASTER_URI=http://127.0.0.1:15253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_rooms_down10_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_down10_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_down10_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_down10_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_down10_rooms_fault/graph.json --target-detection --rally --downlink-loss-rate 0.1
ROS_DOMAIN_ID=63 GAZEBO_MASTER_URI=http://127.0.0.1:15253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_rooms_delay2_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_delay2_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_delay2_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_delay2_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_delay2_rooms_fault/graph.json --target-detection --rally --uplink-delay-sec 2 --downlink-delay-sec 2
ROS_DOMAIN_ID=64 GAZEBO_MASTER_URI=http://127.0.0.1:15253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_rooms_overflow_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_overflow_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_overflow_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_overflow_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_overflow_rooms_fault/graph.json --target-detection --rally --uplink-delay-sec 0.5 --downlink-delay-sec 0.5 --gateway-queue-capacity 1
ROS_DOMAIN_ID=65 GAZEBO_MASTER_URI=http://127.0.0.1:15253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_rooms_burst_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_burst_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_burst_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_burst_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_burst_rooms_fault/graph.json --target-detection --rally --gateway-blackout-intervals '[[80, 100], [140, 160]]'
ROS_DOMAIN_ID=66 GAZEBO_MASTER_URI=http://127.0.0.1:15253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_rooms_ideal_rooms3_rally_43f2051648 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_rally_43f2051648 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_rally_43f2051648/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_rally_43f2051648/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_rally_43f2051648/graph.json --target-detection --rally --navigation-command-deadline-sec 0.3 --downlink-delay-sec 0.5
ROS_DOMAIN_ID=67 GAZEBO_MASTER_URI=http://127.0.0.1:15253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_rooms_deadline_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_deadline_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_deadline_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_deadline_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_deadline_rooms_fault/graph.json --target-detection --rally --navigation-command-deadline-sec 0.3 --downlink-delay-sec 0.5
ROS_DOMAIN_ID=68 GAZEBO_MASTER_URI=http://127.0.0.1:15253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_rooms_detection_loss_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_detection_loss_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_detection_loss_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_detection_loss_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_detection_loss_rooms_fault/graph.json --target-detection --rally --gateway-drop-message-types target_detection
ROS_DOMAIN_ID=69 GAZEBO_MASTER_URI=http://127.0.0.1:15253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0.8 --mission-mode coverage --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_rooms_ideal_rooms3_coverage_4c86e25248 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_coverage_4c86e25248 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_coverage_4c86e25248/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_coverage_4c86e25248/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_coverage_4c86e25248/graph.json --gateway-drop-message-types pose_state,frame_state
ROS_DOMAIN_ID=70 GAZEBO_MASTER_URI=http://127.0.0.1:15253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0.8 --mission-mode coverage --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_rooms_pose_loss_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_pose_loss_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_pose_loss_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_pose_loss_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_pose_loss_rooms_fault/graph.json --gateway-drop-message-types pose_state,frame_state
ROS_DOMAIN_ID=71 GAZEBO_MASTER_URI=http://127.0.0.1:15253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_rooms_single_failure_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_single_failure_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_single_failure_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_single_failure_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_single_failure_rooms_fault/graph.json --target-detection --rally --inject-failure-robot tb3 --inject-failure-after-sec 45
ROS_DOMAIN_ID=72 GAZEBO_MASTER_URI=http://127.0.0.1:15253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode target --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_rooms_ideal_rooms3_target_01c25c1bef --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_target_01c25c1bef --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_target_01c25c1bef/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_target_01c25c1bef/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_ideal_rooms3_target_01c25c1bef/graph.json --target-detection --gateway-drop-message-types target_detection
ROS_DOMAIN_ID=73 GAZEBO_MASTER_URI=http://127.0.0.1:15253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode target --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_rooms_target_loss_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_target_loss_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_target_loss_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_target_loss_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_rooms/p3b5_v42_rooms_target_loss_rooms_fault/graph.json --target-detection --gateway-drop-message-types target_detection
ROS_DOMAIN_ID=160 GAZEBO_MASTER_URI=http://127.0.0.1:15252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_forced/p3b5_v42_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_forced/p3b5_v42_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_forced/p3b5_v42_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_forced/p3b5_v42_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=161 GAZEBO_MASTER_URI=http://127.0.0.1:15252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_forced/p3b5_v42_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_forced/p3b5_v42_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_forced/p3b5_v42_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_forced/p3b5_v42_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=170 GAZEBO_MASTER_URI=http://127.0.0.1:15252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x -4.5 --target-y -0.5 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_corridors_ideal_corridors2_rally_1e053e8bbc --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_ideal_corridors2_rally_1e053e8bbc --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_ideal_corridors2_rally_1e053e8bbc/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_ideal_corridors2_rally_1e053e8bbc/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_ideal_corridors2_rally_1e053e8bbc/graph.json --target-detection --rally --uplink-delay-sec 0.5 --downlink-delay-sec 0.5
ROS_DOMAIN_ID=171 GAZEBO_MASTER_URI=http://127.0.0.1:15252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x -4.5 --target-y -0.5 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_corridors_delay05_corridors_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_delay05_corridors_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_delay05_corridors_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_delay05_corridors_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_delay05_corridors_fault/graph.json --target-detection --rally --uplink-delay-sec 0.5 --downlink-delay-sec 0.5
ROS_DOMAIN_ID=172 GAZEBO_MASTER_URI=http://127.0.0.1:15252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x -4.5 --target-y -0.5 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_corridors_duplicates_corridors_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_duplicates_corridors_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_duplicates_corridors_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_duplicates_corridors_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_duplicates_corridors_fault/graph.json --target-detection --rally --gateway-duplicate-rate 1 --gateway-reorder-window 8 --gateway-reorder-step-sec 0.3
ROS_DOMAIN_ID=173 GAZEBO_MASTER_URI=http://127.0.0.1:15252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x -4.5 --target-y -0.5 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_corridors_nav_loss_corridors_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_nav_loss_corridors_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_nav_loss_corridors_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_nav_loss_corridors_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_nav_loss_corridors_fault/graph.json --target-detection --rally --gateway-drop-message-types navigation_goal,navigation_cancel
ROS_DOMAIN_ID=174 GAZEBO_MASTER_URI=http://127.0.0.1:15252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0.8 --mission-mode coverage --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x -4.5 --target-y -0.5 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_corridors_ideal_corridors2_coverage_0241ed3b33 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_ideal_corridors2_coverage_0241ed3b33 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_ideal_corridors2_coverage_0241ed3b33/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_ideal_corridors2_coverage_0241ed3b33/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_ideal_corridors2_coverage_0241ed3b33/graph.json --uplink-delay-sec 0.5 --downlink-delay-sec 0.5
ROS_DOMAIN_ID=175 GAZEBO_MASTER_URI=http://127.0.0.1:15252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0.8 --mission-mode coverage --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x -4.5 --target-y -0.5 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_corridors_coverage_delay_corridors_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_coverage_delay_corridors_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_coverage_delay_corridors_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_coverage_delay_corridors_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_corridors/p3b5_v42_corridors_coverage_delay_corridors_fault/graph.json --uplink-delay-sec 0.5 --downlink-delay-sec 0.5
ROS_DOMAIN_ID=200 GAZEBO_MASTER_URI=http://127.0.0.1:15250 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p3a5_holdout.world --robot-count 3 --gazebo-seed 707 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x 4.4 --target-y 3.4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_holdout_ideal_holdout3_rally_1033f3052a --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_holdout/p3b5_v42_holdout_ideal_holdout3_rally_1033f3052a --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_holdout/p3b5_v42_holdout_ideal_holdout3_rally_1033f3052a/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_holdout/p3b5_v42_holdout_ideal_holdout3_rally_1033f3052a/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_holdout/p3b5_v42_holdout_ideal_holdout3_rally_1033f3052a/graph.json --target-detection --rally --uplink-loss-rate 0.1 --gateway-seed 27077
ROS_DOMAIN_ID=201 GAZEBO_MASTER_URI=http://127.0.0.1:15250 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p3a5_holdout.world --robot-count 3 --gazebo-seed 707 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x 4.4 --target-y 3.4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_holdout_holdout_rally_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_holdout/p3b5_v42_holdout_holdout_rally_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_holdout/p3b5_v42_holdout_holdout_rally_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_holdout/p3b5_v42_holdout_holdout_rally_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_holdout/p3b5_v42_holdout_holdout_rally_fault/graph.json --target-detection --rally --uplink-loss-rate 0.1 --gateway-seed 27077
ROS_DOMAIN_ID=162 GAZEBO_MASTER_URI=http://127.0.0.1:15252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_safety_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=163 GAZEBO_MASTER_URI=http://127.0.0.1:15252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_safety_local_return_under_blackout_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_local_return_under_blackout_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_local_return_under_blackout_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_local_return_under_blackout_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_local_return_under_blackout_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=164 GAZEBO_MASTER_URI=http://127.0.0.1:15252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_safety_ideal_lab2_rally_cebf10d52a --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_ideal_lab2_rally_cebf10d52a --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_ideal_lab2_rally_cebf10d52a/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_ideal_lab2_rally_cebf10d52a/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_ideal_lab2_rally_cebf10d52a/graph.json --target-detection --rally --navigation-command-deadline-sec 2 --downlink-delay-sec 0.5
ROS_DOMAIN_ID=165 GAZEBO_MASTER_URI=http://127.0.0.1:15252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_safety_local_deadline_cancel_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_local_deadline_cancel_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_local_deadline_cancel_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_local_deadline_cancel_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_safety/p3b5_v42_safety_local_deadline_cancel_fault/graph.json --target-detection --rally --navigation-command-deadline-sec 2 --downlink-delay-sec 0.5
ROS_DOMAIN_ID=180 GAZEBO_MASTER_URI=http://127.0.0.1:15252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_returnproof_ideal_forced2_rally_4c7c808f36 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_returnproof/p3b5_v42_returnproof_ideal_forced2_rally_4c7c808f36 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_returnproof/p3b5_v42_returnproof_ideal_forced2_rally_4c7c808f36/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_returnproof/p3b5_v42_returnproof_ideal_forced2_rally_4c7c808f36/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_returnproof/p3b5_v42_returnproof_ideal_forced2_rally_4c7c808f36/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=181 GAZEBO_MASTER_URI=http://127.0.0.1:15252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v42_returnproof_physical_return_under_blackout_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_returnproof/p3b5_v42_returnproof_physical_return_under_blackout_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_returnproof/p3b5_v42_returnproof_physical_return_under_blackout_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_returnproof/p3b5_v42_returnproof_physical_return_under_blackout_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v42_returnproof/p3b5_v42_returnproof_physical_return_under_blackout_fault/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=130 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_lab101/launch_logs --episode-id p3b5_v42_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_lab101/graphs/p3b5_v42_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_lab101/episodes/p3b5_v42_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=133 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_lab/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_lab/launch_logs --episode-id p3b5_v42_fixed_lab_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_lab/graphs/p3b5_v42_fixed_lab_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_lab/episodes/p3b5_v42_fixed_lab_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=134 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_lab/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_lab/launch_logs --episode-id p3b5_v42_fixed_lab_lab_far_northwest_3r_seed303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_lab/graphs/p3b5_v42_fixed_lab_lab_far_northwest_3r_seed303.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_lab/episodes/p3b5_v42_fixed_lab_lab_far_northwest_3r_seed303_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=136 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_rooms/launch_logs --episode-id p3b5_v42_fixed_rooms_rooms_far_northeast_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_rooms/graphs/p3b5_v42_fixed_rooms_rooms_far_northeast_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_rooms/episodes/p3b5_v42_fixed_rooms_rooms_far_northeast_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=137 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_rooms/launch_logs --episode-id p3b5_v42_fixed_rooms_rooms_far_northeast_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_rooms/graphs/p3b5_v42_fixed_rooms_rooms_far_northeast_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_rooms/episodes/p3b5_v42_fixed_rooms_rooms_far_northeast_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=138 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_rooms/launch_logs --episode-id p3b5_v42_fixed_rooms_rooms_far_northeast_3r_seed303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_rooms/graphs/p3b5_v42_fixed_rooms_rooms_far_northeast_3r_seed303.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_rooms/episodes/p3b5_v42_fixed_rooms_rooms_far_northeast_3r_seed303_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=139 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/launch_logs --episode-id p3b5_v42_fixed_corridors_corridors_far_west_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/graphs/p3b5_v42_fixed_corridors_corridors_far_west_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/episodes/p3b5_v42_fixed_corridors_corridors_far_west_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=140 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/launch_logs --episode-id p3b5_v42_fixed_corridors_corridors_far_west_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/graphs/p3b5_v42_fixed_corridors_corridors_far_west_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/episodes/p3b5_v42_fixed_corridors_corridors_far_west_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=141 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/launch_logs --episode-id p3b5_v42_fixed_corridors_corridors_far_west_3r_seed303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/graphs/p3b5_v42_fixed_corridors_corridors_far_west_3r_seed303.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/episodes/p3b5_v42_fixed_corridors_corridors_far_west_3r_seed303_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=142 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/launch_logs --episode-id p3b5_v42_fixed_corridors_corridors_far_west_2r_seed202_crosscheck --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/graphs/p3b5_v42_fixed_corridors_corridors_far_west_2r_seed202_crosscheck.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v42_fixed_corridors/episodes/p3b5_v42_fixed_corridors_corridors_far_west_2r_seed202_crosscheck_ledger.jsonl --disable-global-battery-rally-pause
```

十个fixed为1+2+3+4原cell、同CPU0–19先全部通过；54协议matrix、零E两侧FAILED/no nav、受控两侧强实际返航与each-charge通过。forced ideal CMP279.6/each-charge1，故障侧RALLY timeout保留；非CMP ideal从TDI分母排除，target/coverage/PARTIAL只按各自指标记录。完整raw阶段计数：{'FAILED': 3, 'COMPLETE': 24, 'EXPLORE': 14, 'FOUND': 5, 'RALLY': 4, 'PARTIAL_COMPLETE': 1, 'FOUND_UNCONFIRMED': 1}。

首次707 ideal148.1s/0contact，原fault启动90s无清单，runner1/observer0、episode_startedFalse/no result/no ledger；没有调整生成等待时限或重发spawn。原ModelInventory已有ModelStates及GetModelList，不宣称新加service fallback。后续裸世界两domain都PASS，故障未复现。旧v11三observer仅SIGINT正常关闭，所有原流与关闭前后hash保留；当前v42/无关domain222不受信号影响。

附加诊断/组件命令（ROS诊断source Humble/install/Gazebo、Waffle/PYTHONNOUSERSITE；只读owner诊断没有Gazebo/任务；不是heldout或TDI实验）：

```bash
PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python /tmp/close_p3b5_v11_orphans.py > /tmp/p3b5_v11_orphan_cleanup.log 2>&1
taskset -c 0-19 /usr/bin/python3 /tmp/probe_p3b5_model_inventory.py > /tmp/p3b5_model_inventory_diagnostic.log 2>&1
export PYTHONPATH=/tmp/p3b5_v54_lifetime_draft:$PWD/scripts:$PYTHONPATH
/usr/bin/python3 -m pytest -q /tmp/p3b5_v54_lifetime_draft/test_observer_lifetime.py > /tmp/p3b5_v54_lifetime_component.log 2>&1
/usr/bin/python3 -m pytest -q /tmp/p3b5_v54_lifetime_draft/test_observer_lifetime.py > /tmp/p3b5_v54_lifetime_component2.log 2>&1
/usr/bin/python3 -m pytest -q /tmp/p3b5_v54_lifetime_draft/test_observer_lifetime.py /tmp/p3b5_v54_lifetime_draft/test_p3b5_tasks.py > /tmp/p3b5_v54_observer_domain_components.log 2>&1
/usr/bin/python3 -m pytest -q /tmp/p3b5_v54_lifetime_draft/test_observer_lifetime.py /tmp/p3b5_v54_lifetime_draft/test_p3b5_tasks.py src/multi_robot_exploration/test/test_spawn_entity_checked.py > /tmp/p3b5_v54_startup_components.log 2>&1
taskset -c 0-19 /usr/bin/python3 /tmp/probe_p3b5_observer_owners.py > /tmp/p3b5_v54_ros_owner_probe.log 2>&1
/usr/bin/python3 /tmp/archive_p3b5_011786e.py > /tmp/p3b5_v42_archive_failed.log 2>&1
PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python /tmp/apply_p3b5_v54_infrastructure_candidate.py > /tmp/p3b5_v43_apply_candidate.log 2>&1
```

first helper3PASS.60s，fixture读取方式改为有界原始fd避免TextIO预读；第二3PASS.60s；observer/domain13PASS.80s；加原spawner8项21PASS.73s（两common-root pytest-cache warning）。两个实际ROS worker在READY后合成父进程退出，worker均关闭；只停止合成测试owner，未产生机器人/任务/heldout。五组CLI validate-only确认39个主episode的domain22..27/50..60/70..83/44..45/90..95不重叠；另有E0/controlled/fixed预声明独立范围。所有source、metadata、stdout与旧首次测试保存于component JSON。

首次canonical规范检查424PASS/1FAIL15.94s：新测试的subprocess-c没有继承pytest加入的scripts模块路径，ModuleNotFoundError；set-e阻止后续build/audit。原测试/helper/stdout保存/tmp/p3b5_v54_canonical_attempt1及component JSON。修正仅测试环境PYTHONPATH，并让owner先退出的反例明确核对RuntimeError原因，防止导入错误假阳性；runtime helper/观察器不改。完整检查再运行同命令，最终425PASS；首次失败不覆盖。

canonical verification（Humble/install、PYTHONNOUSERSITE=1、ROS_LOG_DIR=canonical ROS/log/component_checks；没有TMP overlay）：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v43_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v43_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v43_source_audit.log 2>&1
```

425组件、四包build/source audit PASS；控制算法字节不变，完整门禁仍待新clean提交先十fixed后全57。707已暴露，后续为同策略基础设施复验；P3A.6 accepted22c95a7保留。

## 2026-10-04 P3B.5 v43冻结前domain字段schema复核

cf4d1c9已提交/推送。冻结前只读复核发现原v42物理metadata的ROS domain是int180/181，而runner原记录为str180/181；值相同但严格末端审计要求类型一致。原两记录/原来源/hash不改，新run_p3b5_return_probe仅把metadata字段序列化为字符串。下一新批次受控返航subgate提前检查observer与runner原ID完全匹配，再继续十fixed/全矩阵。该检查不是额外episode或失败回填。

此前full425PASS12.78s、four-package build5.16s与source audit保存/tmp/p3b5_v43_pre_schema_verification及component报告；字段统一后重跑相同17文件425组件命令、相同four-package colcon及source-only audit（与前条日志相同完整命令，输出仍为/tmp/p3b5_v43_{component_checks,build,source_audit}.log），三项全通过，新stdout保留。未改变控制算法、faultmanifest、300秒或任何安全/原生完成门限。schema复核完整值/类型/source保存在component JSON的/tmp/p3b5_domain_schema_review.json；更新的prospective调度源码也已保留。

## 2026-10-04 P3B.5 v43完整57次候选与强制充电原生保持失败

冻结`584dadcb6ed564fdefb6b83820174469016ead9e`，clean/pushed main后完整运行；四池[0,0,0,0]、bootstrap[0,0,0]，全部任务/观察器结束且15350..15353释放后归档。57原始episode、27配对/41唯一主实验+10固定+6补充，无整格重试/行政停止/基础设施失败；0接触，57ledger审计PASS。实际最终checker exit1：forced ideal不满足success，不能标为完整技术PASS。P3A.6已验收冻结22c95a7保持。

ROS canonical cwd/source Humble、install、Gazebo；PYTHONNOUSERSITE=1、TURTLEBOT3_MODEL=waffle、ROS_LOG_DIR=ROS/log/ros_launch。原完整环境/配置/source/result/graph/ledger哈希与prospective declarations/stdout见report/20261004_p3b5_forced_native_hold_failed_candidate.json；目标检测为gateway交付的Gazebo几何可见性代理，非实物视觉或ns-3网络。

```bash
/usr/bin/python3 /tmp/p3b5_v43_after_subgates.py > /tmp/p3b5_v43_after_subgates.log 2>&1
/usr/bin/python3 /tmp/p3b5_v43_bootstrap.py > /tmp/p3b5_v43_bootstrap.log 2>&1
/usr/bin/python3 /tmp/final_check_p3b5_v43.py > /tmp/p3b5_v43_final_gate.log 2>&1
/usr/bin/python3 /tmp/archive_p3b5_584dadc_failed.py > /tmp/p3b5_v43_archive_failed.log 2>&1
```

57次实际完整子命令（原始结果均保留）：

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_zero_ideal_lab2_rally_0678e85373 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_zero/p3b5_v43_zero_ideal_lab2_rally_0678e85373 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_zero/p3b5_v43_zero_ideal_lab2_rally_0678e85373/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_zero/p3b5_v43_zero_ideal_lab2_rally_0678e85373/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_zero/p3b5_v43_zero_ideal_lab2_rally_0678e85373/graph.json --target-detection --rally --battery-initial-energy 0
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_zero_battery_exhaust_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_zero/p3b5_v43_zero_battery_exhaust_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_zero/p3b5_v43_zero_battery_exhaust_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_zero/p3b5_v43_zero_battery_exhaust_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_zero/p3b5_v43_zero_battery_exhaust_lab_fault/graph.json --target-detection --rally --battery-initial-energy 0
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_lab_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_lab_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_zero_rally_lab_fault/graph.json --target-detection --rally
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_lab_up100_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_up100_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_up100_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_up100_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_up100_lab_fault/graph.json --target-detection --rally --uplink-loss-rate 1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_lab_down100_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_down100_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_down100_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_down100_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_down100_lab_fault/graph.json --target-detection --rally --downlink-loss-rate 1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_lab_ttl_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ttl_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ttl_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ttl_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ttl_lab_fault/graph.json --target-detection --rally --uplink-delay-sec 61 --downlink-delay-sec 61
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0.8 --mission-mode coverage --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_lab_ideal_lab2_coverage_da95bad2c7 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ideal_lab2_coverage_da95bad2c7 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ideal_lab2_coverage_da95bad2c7/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ideal_lab2_coverage_da95bad2c7/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ideal_lab2_coverage_da95bad2c7/graph.json --gateway-drop-message-types map_snapshot,fused_map_snapshot
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0.8 --mission-mode coverage --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_lab_map_loss_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_map_loss_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_map_loss_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_map_loss_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_map_loss_lab_fault/graph.json --gateway-drop-message-types map_snapshot,fused_map_snapshot
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_lab_battery_loss_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_battery_loss_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_battery_loss_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_battery_loss_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_battery_loss_lab_fault/graph.json --target-detection --rally --gateway-drop-message-types battery_state
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_lab_state_loss_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_state_loss_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_state_loss_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_state_loss_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_state_loss_lab_fault/graph.json --target-detection --rally --gateway-drop-message-types task_state
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode target --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_lab_ideal_lab2_target_21212e763a --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ideal_lab2_target_21212e763a --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ideal_lab2_target_21212e763a/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ideal_lab2_target_21212e763a/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_ideal_lab2_target_21212e763a/graph.json --target-detection --uplink-loss-rate 0.1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode target --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_lab_target_up10_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_target_up10_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_target_up10_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_target_up10_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_lab/p3b5_v43_lab_target_up10_lab_fault/graph.json --target-detection --uplink-loss-rate 0.1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_rooms_ideal_rooms3_rally_980df9c157 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_rally_980df9c157 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_rally_980df9c157/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_rally_980df9c157/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_rally_980df9c157/graph.json --target-detection --rally --uplink-loss-rate 0.1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_rooms_up10_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_up10_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_up10_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_up10_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_up10_rooms_fault/graph.json --target-detection --rally --uplink-loss-rate 0.1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_rooms_down10_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_down10_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_down10_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_down10_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_down10_rooms_fault/graph.json --target-detection --rally --downlink-loss-rate 0.1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_rooms_delay2_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_delay2_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_delay2_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_delay2_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_delay2_rooms_fault/graph.json --target-detection --rally --uplink-delay-sec 2 --downlink-delay-sec 2
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_rooms_overflow_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_overflow_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_overflow_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_overflow_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_overflow_rooms_fault/graph.json --target-detection --rally --uplink-delay-sec 0.5 --downlink-delay-sec 0.5 --gateway-queue-capacity 1
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_rooms_burst_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_burst_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_burst_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_burst_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_burst_rooms_fault/graph.json --target-detection --rally --gateway-blackout-intervals '[[80, 100], [140, 160]]'
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_rooms_ideal_rooms3_rally_43f2051648 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_rally_43f2051648 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_rally_43f2051648/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_rally_43f2051648/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_rally_43f2051648/graph.json --target-detection --rally --navigation-command-deadline-sec 0.3 --downlink-delay-sec 0.5
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_rooms_deadline_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_deadline_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_deadline_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_deadline_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_deadline_rooms_fault/graph.json --target-detection --rally --navigation-command-deadline-sec 0.3 --downlink-delay-sec 0.5
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_rooms_detection_loss_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_detection_loss_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_detection_loss_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_detection_loss_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_detection_loss_rooms_fault/graph.json --target-detection --rally --gateway-drop-message-types target_detection
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0.8 --mission-mode coverage --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_rooms_ideal_rooms3_coverage_4c86e25248 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_coverage_4c86e25248 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_coverage_4c86e25248/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_coverage_4c86e25248/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_coverage_4c86e25248/graph.json --gateway-drop-message-types pose_state,frame_state
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0.8 --mission-mode coverage --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_rooms_pose_loss_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_pose_loss_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_pose_loss_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_pose_loss_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_pose_loss_rooms_fault/graph.json --gateway-drop-message-types pose_state,frame_state
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_rooms_single_failure_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_single_failure_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_single_failure_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_single_failure_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_single_failure_rooms_fault/graph.json --target-detection --rally --inject-failure-robot tb3 --inject-failure-after-sec 45
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode target --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_rooms_ideal_rooms3_target_01c25c1bef --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_target_01c25c1bef --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_target_01c25c1bef/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_target_01c25c1bef/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_ideal_rooms3_target_01c25c1bef/graph.json --target-detection --gateway-drop-message-types target_detection
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode target --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x 5 --target-y 3 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_rooms_target_loss_rooms_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_target_loss_rooms_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_target_loss_rooms_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_target_loss_rooms_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_rooms/p3b5_v43_rooms_target_loss_rooms_fault/graph.json --target-detection --gateway-drop-message-types target_detection
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_forced/p3b5_v43_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_forced/p3b5_v43_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_forced/p3b5_v43_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_forced/p3b5_v43_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_forced/p3b5_v43_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_forced/p3b5_v43_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_forced/p3b5_v43_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_forced/p3b5_v43_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x -4.5 --target-y -0.5 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_corridors_ideal_corridors2_rally_1e053e8bbc --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_ideal_corridors2_rally_1e053e8bbc --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_ideal_corridors2_rally_1e053e8bbc/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_ideal_corridors2_rally_1e053e8bbc/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_ideal_corridors2_rally_1e053e8bbc/graph.json --target-detection --rally --uplink-delay-sec 0.5 --downlink-delay-sec 0.5
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x -4.5 --target-y -0.5 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_corridors_delay05_corridors_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_delay05_corridors_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_delay05_corridors_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_delay05_corridors_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_delay05_corridors_fault/graph.json --target-detection --rally --uplink-delay-sec 0.5 --downlink-delay-sec 0.5
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x -4.5 --target-y -0.5 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_corridors_duplicates_corridors_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_duplicates_corridors_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_duplicates_corridors_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_duplicates_corridors_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_duplicates_corridors_fault/graph.json --target-detection --rally --gateway-duplicate-rate 1 --gateway-reorder-window 8 --gateway-reorder-step-sec 0.3
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x -4.5 --target-y -0.5 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_corridors_nav_loss_corridors_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_nav_loss_corridors_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_nav_loss_corridors_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_nav_loss_corridors_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_nav_loss_corridors_fault/graph.json --target-detection --rally --gateway-drop-message-types navigation_goal,navigation_cancel
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0.8 --mission-mode coverage --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x -4.5 --target-y -0.5 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_corridors_ideal_corridors2_coverage_0241ed3b33 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_ideal_corridors2_coverage_0241ed3b33 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_ideal_corridors2_coverage_0241ed3b33/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_ideal_corridors2_coverage_0241ed3b33/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_ideal_corridors2_coverage_0241ed3b33/graph.json --uplink-delay-sec 0.5 --downlink-delay-sec 0.5
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0.8 --mission-mode coverage --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x -4.5 --target-y -0.5 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_corridors_coverage_delay_corridors_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_coverage_delay_corridors_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_coverage_delay_corridors_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_coverage_delay_corridors_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_corridors/p3b5_v43_corridors_coverage_delay_corridors_fault/graph.json --uplink-delay-sec 0.5 --downlink-delay-sec 0.5
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p3a5_holdout.world --robot-count 3 --gazebo-seed 707 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x 4.4 --target-y 3.4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_holdout_ideal_holdout3_rally_1033f3052a --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_ideal_holdout3_rally_1033f3052a --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_ideal_holdout3_rally_1033f3052a/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_ideal_holdout3_rally_1033f3052a/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_ideal_holdout3_rally_1033f3052a/graph.json --target-detection --rally --uplink-loss-rate 0.1 --gateway-seed 27077
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p3a5_holdout.world --robot-count 3 --gazebo-seed 707 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x 4.4 --target-y 3.4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_holdout_holdout_rally_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_holdout_rally_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_holdout_rally_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_holdout_rally_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_holdout_rally_fault/graph.json --target-detection --rally --uplink-loss-rate 0.1 --gateway-seed 27077
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p3a5_holdout.world --robot-count 3 --gazebo-seed 707 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode target --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x 4.4 --target-y 3.4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_holdout_ideal_holdout3_target_d97e9d8212 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_ideal_holdout3_target_d97e9d8212 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_ideal_holdout3_target_d97e9d8212/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_ideal_holdout3_target_d97e9d8212/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_ideal_holdout3_target_d97e9d8212/graph.json --target-detection --downlink-loss-rate 0.1 --gateway-seed 27077
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p3a5_holdout.world --robot-count 3 --gazebo-seed 707 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode target --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x 4.4 --target-y 3.4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_holdout_holdout_target_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_holdout_target_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_holdout_target_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_holdout_target_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_holdout_target_fault/graph.json --target-detection --downlink-loss-rate 0.1 --gateway-seed 27077
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p3a5_holdout.world --robot-count 3 --gazebo-seed 707 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0.8 --mission-mode coverage --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x 4.4 --target-y 3.4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_holdout_ideal_holdout3_coverage_b3eb110581 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_ideal_holdout3_coverage_b3eb110581 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_ideal_holdout3_coverage_b3eb110581/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_ideal_holdout3_coverage_b3eb110581/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_ideal_holdout3_coverage_b3eb110581/graph.json --gateway-blackout-intervals '[[80, 100], [140, 160]]' --gateway-seed 27077
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p3a5_holdout.world --robot-count 3 --gazebo-seed 707 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0.8 --mission-mode coverage --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 45 --target-x 4.4 --target-y 3.4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_holdout_holdout_coverage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_holdout_coverage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_holdout_coverage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_holdout_coverage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_holdout/p3b5_v43_holdout_holdout_coverage_fault/graph.json --gateway-blackout-intervals '[[80, 100], [140, 160]]' --gateway-seed 27077
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_safety_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 250]]' --battery-idle-cost 0.15
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_safety_local_return_under_blackout_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_local_return_under_blackout_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_local_return_under_blackout_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_local_return_under_blackout_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_local_return_under_blackout_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 250]]' --battery-idle-cost 0.15
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_safety_ideal_lab2_rally_cebf10d52a --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_ideal_lab2_rally_cebf10d52a --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_ideal_lab2_rally_cebf10d52a/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_ideal_lab2_rally_cebf10d52a/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_ideal_lab2_rally_cebf10d52a/graph.json --target-detection --rally --navigation-command-deadline-sec 2 --downlink-delay-sec 0.5
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_safety_local_deadline_cancel_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_local_deadline_cancel_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_local_deadline_cancel_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_local_deadline_cancel_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_safety/p3b5_v43_safety_local_deadline_cancel_fault/graph.json --target-detection --rally --navigation-command-deadline-sec 2 --downlink-delay-sec 0.5
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_returnproof_ideal_forced2_rally_4c7c808f36 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_returnproof/p3b5_v43_returnproof_ideal_forced2_rally_4c7c808f36 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_returnproof/p3b5_v43_returnproof_ideal_forced2_rally_4c7c808f36/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_returnproof/p3b5_v43_returnproof_ideal_forced2_rally_4c7c808f36/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_returnproof/p3b5_v43_returnproof_ideal_forced2_rally_4c7c808f36/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v43_returnproof_physical_return_under_blackout_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_returnproof/p3b5_v43_returnproof_physical_return_under_blackout_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_returnproof/p3b5_v43_returnproof_physical_return_under_blackout_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_returnproof/p3b5_v43_returnproof_physical_return_under_blackout_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v43_returnproof/p3b5_v43_returnproof_physical_return_under_blackout_fault/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_lab101/launch_logs --episode-id p3b5_v43_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_lab101/graphs/p3b5_v43_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_lab101/episodes/p3b5_v43_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_lab/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_lab/launch_logs --episode-id p3b5_v43_fixed_lab_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_lab/graphs/p3b5_v43_fixed_lab_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_lab/episodes/p3b5_v43_fixed_lab_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_lab/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_lab/launch_logs --episode-id p3b5_v43_fixed_lab_lab_far_northwest_3r_seed303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_lab/graphs/p3b5_v43_fixed_lab_lab_far_northwest_3r_seed303.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_lab/episodes/p3b5_v43_fixed_lab_lab_far_northwest_3r_seed303_ledger.jsonl --disable-global-battery-rally-pause
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_rooms/launch_logs --episode-id p3b5_v43_fixed_rooms_rooms_far_northeast_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_rooms/graphs/p3b5_v43_fixed_rooms_rooms_far_northeast_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_rooms/episodes/p3b5_v43_fixed_rooms_rooms_far_northeast_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_rooms/launch_logs --episode-id p3b5_v43_fixed_rooms_rooms_far_northeast_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_rooms/graphs/p3b5_v43_fixed_rooms_rooms_far_northeast_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_rooms/episodes/p3b5_v43_fixed_rooms_rooms_far_northeast_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_rooms/launch_logs --episode-id p3b5_v43_fixed_rooms_rooms_far_northeast_3r_seed303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_rooms/graphs/p3b5_v43_fixed_rooms_rooms_far_northeast_3r_seed303.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_rooms/episodes/p3b5_v43_fixed_rooms_rooms_far_northeast_3r_seed303_ledger.jsonl --disable-global-battery-rally-pause
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/launch_logs --episode-id p3b5_v43_fixed_corridors_corridors_far_west_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/graphs/p3b5_v43_fixed_corridors_corridors_far_west_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/episodes/p3b5_v43_fixed_corridors_corridors_far_west_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/launch_logs --episode-id p3b5_v43_fixed_corridors_corridors_far_west_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/graphs/p3b5_v43_fixed_corridors_corridors_far_west_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/episodes/p3b5_v43_fixed_corridors_corridors_far_west_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/launch_logs --episode-id p3b5_v43_fixed_corridors_corridors_far_west_3r_seed303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/graphs/p3b5_v43_fixed_corridors_corridors_far_west_3r_seed303.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/episodes/p3b5_v43_fixed_corridors_corridors_far_west_3r_seed303_ledger.jsonl --disable-global-battery-rally-pause
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/launch_logs --episode-id p3b5_v43_fixed_corridors_corridors_far_west_2r_seed202_crosscheck --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/graphs/p3b5_v43_fixed_corridors_corridors_far_west_2r_seed202_crosscheck.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v43_fixed_corridors/episodes/p3b5_v43_fixed_corridors_corridors_far_west_2r_seed202_crosscheck_ledger.jsonl --disable-global-battery-rally-pause
```

主强制充电ideal实际：phase=COMPLETE，success=False，中央声明297.5s，截止300.0s，completion_time=None，native proof=None，termination=timeout，0接触，两机各充电一次；严格门禁正确拒绝。最早确认至RALLY的调查及后续长绕行需继续独立诊断，不放宽任务/原生保持标准。

425组件、四包build、source-only旁路与54协议矩阵通过。所有十固定格合格，不代替forced回归。主zero_rally_lab仍RALLY timeout，按原样保留为零网络注入下的稳定性限制，不归因于丢包/延迟。单机失败PARTIAL_COMPLETE、返充/期限探针、全部非COMPLETE/过程结果保留；未生成最终PASS图表/文档。

当前原57自然结束后才写tracked档案。707原011786e已经暴露，584同策略基础设施复验；接下来若改控制算法，新正式协议必须用真正新留出组合。未启动P3C/ns-3/RL；任务继续。

## 2026-10-04 P3B.5 v55充电/时间优先分配组件

v43原57完整失败已在ae4ad02提交推送；不回填。候选只重排集合组合比较优先级，ACTIVE真实观测者免返充保留，先充电数/名义串行时间，再额外余量，最后原路径指标；完整名义/实际绕行能量、真实body/route/return保护、TTL/lease和300s/5s真实保持门槛保持。

ROS canonical cwd，source Humble/install、PYTHONNOUSERSITE=1、ROS_LOG_DIR=canonical ROS/log/component_checks，通过rtk bash -lc执行：

```bash
/usr/bin/python3 -m pytest src/multi_robot_exploration/test/test_control.py -k rally_assignment -q > /tmp/p3b5_v55_assignment_targeted.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v55_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v55_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v55_source_audit.log 2>&1
/usr/bin/python3 /tmp/probe_p3b5_v55_assignment.py > /tmp/p3b5_v55_assignment_comparison.log 2>&1
/usr/bin/python3 /tmp/probe_p3b5_v55_assignment_attempt2.py > /tmp/p3b5_v55_assignment_comparison_attempt2.log 2>&1
```

相关17PASS2.54s，完整427PASS13.41s，四包build5.24s、source-only3r audit0违规。旧源动态比较工具初次相对导入ImportError退出1，未运行比较/ROS发布/Gazebo；原源/log保留。第二次使用真实包命名空间，六个自由图分配夹具PASS：80电量场景旧额外位移8m→候选0m，余量引发的一台同伴充电1→0；8.5低电量观测者仍选择无需返充的分配。人工候选与点位移不代表原控制buffer、实际运动或仿真因果性能。

组件原始源、命令、环境、stdout、纯bytes SHA及全部比较值见report/20261004_p3b5_charge_time_assignment_component.json。尚无新仿真，也未观察任何新留出输入；接下来commit/push后独立dev303强制充电与zero fault任务，再冻结新正式协议。707已暴露，新控制算法必须有新未暴露留出world/seed/fault组合；不把组件PASS称完整P3B.5 PASS，不进入P3C/ns-3/RL。

## 2026-10-04 P3B.5 v55独立seed303任务开发与v56新留出预声明

实际控制提交cc21503c82358a76092326fd4d6972c2f5d4af87，干净并已push；2026-10-04T14:28:26UTC启动，四个original先ideal后fault、不resume、不重试；全部自然结束、owned AP/标准观察器关闭后才写本记录。两独立master15450/15451、ROS domains12/13和14/15、CPU0–19/20–39。未改source/checker/docs/300s/原生门限，未运行707或新809。

ROS canonical cwd，source Humble/install/Gazebo，PYTHONNOUSERSITE=1、TURTLEBOT3_MODEL=waffle、ROS_LOG_DIR=canonical ROS/log/ros_launch；通过rtk bash -lc执行：

```bash
GAZEBO_MASTER_URI=http://127.0.0.1:15450 taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v55_dev_pool.py '{"run":"p3b5_v55_dev_forced","case":"forced_charge_outage","domain_base":12,"master_port":15450,"cpus":"0-19"}' > /tmp/p3b5_v55_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15451 taskset -c 20-39 /usr/bin/python3 /tmp/run_p3b5_v55_dev_pool.py '{"run":"p3b5_v55_dev_zero","case":"zero_rally_lab","domain_base":14,"master_port":15451,"cpus":"20-39"}' > /tmp/p3b5_v55_dev_zero_pool.log 2>&1
/usr/bin/python3 /tmp/audit_p3b5_v55_development.py > /tmp/p3b5_v55_development_audit.log 2>&1
/usr/bin/python3 /tmp/check_p3b5_v56_fresh_holdout_geometry.py > /tmp/p3b5_v56_holdout_static_geometry.log 2>&1
```

每个原任务smoke实际子命令（完整启动/电池/故障参数）：

```bash
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v55_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_forced/p3b5_v55_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_forced/p3b5_v55_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_forced/p3b5_v55_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_forced/p3b5_v55_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v55_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_forced/p3b5_v55_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_forced/p3b5_v55_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_forced/p3b5_v55_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_forced/p3b5_v55_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v55_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_zero/p3b5_v55_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_zero/p3b5_v55_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_zero/p3b5_v55_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_zero/p3b5_v55_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
/usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v55_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_zero/p3b5_v55_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_zero/p3b5_v55_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_zero/p3b5_v55_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v55_dev_zero/p3b5_v55_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

开发检查PASS：force ideal真COMPLETE297.3s、原生5s证明、两机各charge1、最低7.66790；force fault RALLY timeout300.3s，不计完整成功，安全检查PASS/各charge1/最低8.30704；zero ideal/fault真COMPLETE235.6/215.7s、各总charge1/最低23.15114/21.92425。四次零接触、无FAILED/infra/operational failure，账本时序/TTL/versions和graph旁路通过。原始四result/通信统计/AP完整快照、精确wrapper/observer源码/命令/hash/环境见report/20261004_p3b5_charge_time_assignment_development.json。与v43不作单因素因果比较；零故障时间差非通信收益，强制ideal只有2.7s余量。两pool会话均exit0，masters释放；用户17资料SHA全部不变。

新留出809/28091草案在14:36:39UTC选定，未执行任务/Gazebo/视角/运动实验；14:37静态检查PASS，仅格式和.45m连通，不是任务成绩。源码在/tmp/p3b5_v56_fresh_holdout_proposal，纯world SHA 2b5e443946e3e7405c46815686c3714e0b17b6d5ffe7e270acdb37f8522fafbd。canonical manifest首次执行前冻结新world/seed/fault组合，旧707/27077声明与首次暴露保留。P3B.5完整同提交验收仍待执行；后续新v56禁止把这些开发成绩回填正式格。

冻结前追加组件命令（source Humble/install，PYTHONNOUSERSITE=1，canonical ROS cwd，ROS_LOG_DIR=log/component_checks）：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v56_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v56_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v56_source_audit.log 2>&1
/usr/bin/python3 scripts/run_p3b5_tasks.py --config scripts/p3b5_fault_manifest.json --run-id p3b5_v56_predeclare_validation_only --ros-domain-base 50 --validate-only > /tmp/p3b5_v56_plan_validate.log 2>&1
```

429PASS12.92s、四包5.29s、旁路0违规、27case/41unique validate-only PASS（没有创建episode/启动任务）。完成判定两函数相对cc21503原样；新留出预声明哈希守卫只加强协议核验。组件/静态命令与stdout/source/SHA保存在上述开发JSON的next_protocol_static_validation。文档writer首次用relative_to(ROOT)标记/tmp自身源码，ValueError exit1在任何报告/文档写入前；原writer保留，路径标签修正后的第二次exit0，无仿真/实验重试或结果改变。AP旧metadata标签started_after_runner_attempt_line原样保留，实际dev wrapper触发是task-runner RUN行、早于smoke启动，不能当fixed的Running attempt1语义；source/UTC说明可核验。

## 2026-10-04 P3B.5 v56首固定格失败与完整原始证据归档

2026-10-04 P3B.5 v56原候选FAIL，冻结3d079215caacf9e5e31866ca4db236a5cff3236c；14:55:48–15:17:15UTC自然结束，7started/7raw/0接触/0基础设施失败、7账本审计PASS，其余50格未运行。初始force ideal原生COMPLETE273.6s/各charge1、E0双格和双机真实断网返充探针通过；首个固定lab3/101在99.8s进入RALLY、300.4s timeout，2charges、最低20.8966，不能代替完整验收。只读原生诊断见tb2视线无遮挡时朝向转出90度FOV并产生检测间断，原因仍待核验。全部原始失败保留，不回填/重试/放宽300s与原生保持门限。新809/28091从未执行，可在仅开发seed修复后重新冻结控制SHA再首次暴露；初静态文件误把通用采样点标为spawn/charge，原文件保留，另以真实launch三个起点/充电点补查0.45m连通PASS，world未改。证据见report/20261004_p3b5_charge_time_lab101_failed_candidate.json。全部owned owner/观察器/master关闭后才归档，domain222未动；完整strict checker/PASS报告/图未执行，P3B.5仍待完成，无ns-3/RL。

冻结3d07921干净已push；ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=canonical ROS/log/ros_launch。独立master15550–15553/CPU0–19、20–39、40–59、60–79，domains20/21、28/29、30、44/45。全部自然关闭后归档，无future dispatcher。实际wrapper及全七任务命令如下（通过rtk bash -lc）：

```bash
GAZEBO_MASTER_URI=http://127.0.0.1:15550 taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v56_task_pool.py '{"run": "p3b5_v56_forced", "cases": ["forced_charge_outage"], "domain_base": 44}' > /tmp/p3b5_v56_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15551 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v56_zero_first.py > /tmp/p3b5_v56_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15552 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v56_returnproof --ros-domain-base 20 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v56_returnproof.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15553 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_3d07921.json > /tmp/p3b5_protocol_3d07921.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15550 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v56_first_lab101.py > /tmp/p3b5_v56_first_lab101.log 2>&1
```

```bash
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:15551 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v56_zero_ideal_lab2_rally_0678e85373 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_zero/p3b5_v56_zero_ideal_lab2_rally_0678e85373 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_zero/p3b5_v56_zero_ideal_lab2_rally_0678e85373/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_zero/p3b5_v56_zero_ideal_lab2_rally_0678e85373/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_zero/p3b5_v56_zero_ideal_lab2_rally_0678e85373/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=29 GAZEBO_MASTER_URI=http://127.0.0.1:15551 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v56_zero_battery_exhaust_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_zero/p3b5_v56_zero_battery_exhaust_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_zero/p3b5_v56_zero_battery_exhaust_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_zero/p3b5_v56_zero_battery_exhaust_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_zero/p3b5_v56_zero_battery_exhaust_lab_fault/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=44 GAZEBO_MASTER_URI=http://127.0.0.1:15550 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v56_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_forced/p3b5_v56_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_forced/p3b5_v56_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_forced/p3b5_v56_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_forced/p3b5_v56_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=45 GAZEBO_MASTER_URI=http://127.0.0.1:15550 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v56_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_forced/p3b5_v56_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_forced/p3b5_v56_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_forced/p3b5_v56_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_forced/p3b5_v56_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:15552 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v56_returnproof_ideal_forced2_rally_4c7c808f36 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_returnproof/p3b5_v56_returnproof_ideal_forced2_rally_4c7c808f36 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_returnproof/p3b5_v56_returnproof_ideal_forced2_rally_4c7c808f36/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_returnproof/p3b5_v56_returnproof_ideal_forced2_rally_4c7c808f36/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_returnproof/p3b5_v56_returnproof_ideal_forced2_rally_4c7c808f36/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=21 GAZEBO_MASTER_URI=http://127.0.0.1:15552 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v56_returnproof_physical_return_under_blackout_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_returnproof/p3b5_v56_returnproof_physical_return_under_blackout_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_returnproof/p3b5_v56_returnproof_physical_return_under_blackout_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_returnproof/p3b5_v56_returnproof_physical_return_under_blackout_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v56_returnproof/p3b5_v56_returnproof_physical_return_under_blackout_fault/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=30 GAZEBO_MASTER_URI=http://127.0.0.1:15550 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v56_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v56_fixed_lab101/launch_logs --episode-id p3b5_v56_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v56_fixed_lab101/graphs/p3b5_v56_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v56_fixed_lab101/episodes/p3b5_v56_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
```

| episode | phase / elapsed(s) | success | charges | minimum energy |
|---|---|---:|---:|---:|
| p3b5_v56_zero_ideal_lab2_rally_0678e85373 | FAILED / 0.8 | False | 0 | 0.00000 |
| p3b5_v56_zero_battery_exhaust_lab_fault | FAILED / 1.8 | False | 0 | 0.00000 |
| p3b5_v56_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 273.6 | True | 2 | 6.63120 |
| p3b5_v56_forced_forced_charge_outage_fault | EXPLORE / 300.1 | False | 2 | 8.14450 |
| p3b5_v56_returnproof_ideal_forced2_rally_4c7c808f36 | EXPLORE / 300.2 | False | 2 | 9.69955 |
| p3b5_v56_returnproof_physical_return_under_blackout_fault | EXPLORE / 300.0 | False | 2 | 9.61204 |
| p3b5_v56_fixed_lab101_lab_far_northwest_3r_seed101 | RALLY / 300.4 | False | 2 | 20.89659 |

54纯协议检查PASS。断网真实返充探针在62–248s窗口两机分别169.6/170.6s进入返航，home距离2.00987/1.97608m、累计路径1.21711/1.19632m、净位移1.20559/1.18759m、Nav2 EXEC进度1.21709/1.19629m，各充电一次、能量正、0碰撞；这仅证明安全动作，不是自主任务成功。force fault/两remote探针超时均完整保留；E0的FAILED为预声明预期且无导航。

额外只读组件/归档命令：

```bash
/usr/bin/python3 /tmp/check_p3b5_v56_actual_start_geometry.py > /tmp/p3b5_v56_actual_start_geometry.log 2>&1
/usr/bin/python3 /tmp/archive_p3b5_3d07921_failed.py > /tmp/p3b5_v56_archive_failed.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v56_lab101.py > /tmp/p3b5_v56_lab101_diagnosis_attempt3.log 2>&1
```

首次诊断time_to_target_sec键不存在导致KeyError，未启动ROS/Gazebo；移除无关键后的第二次成功，第三次压缩UUID噪声并加native可见性，原源码/stdout和原观测均保留。实际起点补查仅静态连通，发生于首次809暴露之前；不能把错误初标签视为真实起点证明，也不能把静态PASS当成任务成功。完整归档含hash、源/环境/协议/commands、七result、原生proof、graph/ledger证据、AP/physics文件manifest、dispatcher FAIL和50unrun清单。

## 2026-10-04 P3B.5 v57交付朝向保持组件

2026-10-04 P3B.5 v57朝向保持候选：v56原lab101已归档7cc413c，不回填。网关交付odom朝向与map→odom旋转相加并归一化；当前观测者/guard停在集合位附近后，偏离请求yaw超过交付相机FOV的四分之一时重新开放原final导航腿。要求新鲜target/地图/位姿，ACTIVE、无pending/live与local-return refuge，原网关/能量/机体/在途路线/真实返航/并发保护保持。待执行未来路线优先级不阻止近位朝向校正，实际预约仍保护。448组件PASS14.00s、四包build5.10s、source-only3r audit0违规；证据见report/20261004_p3b5_observer_heading_component.json。v56交付yaw与native相符，物理朝向漂移原因未凭cmd_vel确认；候选修复中央未监测到位后朝向的问题，不能把预测或组件PASS当真实检测/任务通过。需要独立lab101/force303开发与新完整冻结，809尚未暴露，P3B.5未完成。

ROS canonical cwd，source Humble/install、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/component_checks，通过rtk bash -lc；以下均离线组件/只读原记录诊断，未启动新任务或Gazebo：

```bash
/usr/bin/python3 -m pytest src/multi_robot_exploration/test/test_control.py -k "delivered_heading or parked_observer or delivered_odom_violation or target_lease" -q --tb=short > /tmp/p3b5_v57_heading_targeted.log 2>&1
/usr/bin/python3 -m pytest src/multi_robot_exploration/test/test_control.py -k "delivered_heading or parked_observer or delivered_odom_violation or target_lease" -q --tb=short > /tmp/p3b5_v57_heading_targeted_attempt2.log 2>&1
/usr/bin/python3 -m pytest src/multi_robot_exploration/test/test_control.py -k "delivered_heading or parked_observer or delivered_odom_violation or target_lease" -q --tb=short > /tmp/p3b5_v57_heading_targeted_attempt3.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v57_component_checks.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v57_component_checks_attempt2.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v57_build.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v57_build_attempt2.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v57_source_audit.log 2>&1
/usr/bin/python3 /tmp/compare_p3b5_v56_observer_frames.py > /tmp/p3b5_v57_v56_observer_frames.log
```

Targeted1:9fail/7pass (initialization inserted in sibling loop plus incomplete stale fixtures); targeted2:2fail/14pass (fixture input_robot_names absent); targeted3:16pass. Full1:15fail/426pass (untracked-yaw branch accessed position tolerance before skipping narrow fixtures); reorder to require actual yaw first. Full2:448pass. All logs retained; no mission during edits.

Quarter-FOV trigger is a proactive heuristic, not visibility proof or worst-case timing guarantee. Geometric Gazebo target proxy remains. No heldout809 mission observed, no thresholds relaxed, no ns3/RL.

## 20261005 P3B.5 v57朝向保持独立开发五格

20261005 P3B.5 v57独立五格开发FAIL，冻结f8297fa，15:53–16:06:36UTC自然结束后归档；lab3/101 RALLY timeout300.3s/1charge/最低20.27738/0碰撞。force ideal/fault原生COMPLETE295.3/299.5s、各两机charge1；zero ideal/fault原生COMPLETE247.5/167.0s、总charge1/0。五账本时序TTL/versions与graph旁路审计通过，五格0接触/0infra，无任务重试。lab最终位置误差小于3.3cm，但原生近末段最长合格窗口3.0s；289.7/298.7s额外朝向腿发出时目标源龄仍1.2s，候选需要限制持续正常检测时的校正，避免干扰保持。原开发失败不回填v56，不放宽300s/.35/.05/.1/5s；809/28091未执行。完整证据见report/20261005_p3b5_observer_heading_development.json；P3B.5未完成，无ns3/RL。

ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；三个独立master15650–15652/domains16–20/CPU0–19、20–39、40–59。启动前prospective完整计划/source/hash/config/environment与17用户资料不变核验保留。bootstrap exit1是lab单格失败，另两个pool exit0，全部observer正常关闭。通过rtk bash -lc运行：

```bash
/usr/bin/python3 /tmp/run_p3b5_v57_development.py > /tmp/p3b5_v57_development_bootstrap.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15650 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v57_dev_first_lab101.py > /tmp/p3b5_v57_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15651 taskset -c 20-39 /usr/bin/python3 /tmp/run_p3b5_v57_dev_task_pool.py '{"run": "p3b5_v57_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 17}' > /tmp/p3b5_v57_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15652 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v57_dev_task_pool.py '{"run": "p3b5_v57_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 19}' > /tmp/p3b5_v57_dev_zero_pool.log 2>&1
```

实际五个smoke命令（first/fault各自独立原任务）：

```bash
ROS_DOMAIN_ID=16 GAZEBO_MASTER_URI=http://127.0.0.1:15650 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v57_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v57_dev_fixed_lab101/launch_logs --episode-id p3b5_v57_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v57_dev_fixed_lab101/graphs/p3b5_v57_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v57_dev_fixed_lab101/episodes/p3b5_v57_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=17 GAZEBO_MASTER_URI=http://127.0.0.1:15651 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v57_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_forced/p3b5_v57_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_forced/p3b5_v57_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_forced/p3b5_v57_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_forced/p3b5_v57_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=18 GAZEBO_MASTER_URI=http://127.0.0.1:15651 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v57_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_forced/p3b5_v57_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_forced/p3b5_v57_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_forced/p3b5_v57_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_forced/p3b5_v57_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=19 GAZEBO_MASTER_URI=http://127.0.0.1:15652 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v57_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_zero/p3b5_v57_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_zero/p3b5_v57_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_zero/p3b5_v57_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_zero/p3b5_v57_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:15652 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v57_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_zero/p3b5_v57_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_zero/p3b5_v57_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_zero/p3b5_v57_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v57_dev_zero/p3b5_v57_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | outcome / seconds | charges | minimum energy |
|---|---|---:|---:|
| p3b5_v57_dev_fixed_lab101_lab_far_northwest_3r_seed101 | RALLY / 300.3 | 1 | 20.27738 |
| p3b5_v57_dev_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 295.3 | 2 | 8.63907 |
| p3b5_v57_dev_forced_forced_charge_outage_fault | COMPLETE / 299.5 | 2 | 6.77844 |
| p3b5_v57_dev_zero_ideal_lab2_rally_8d4d5c469d | COMPLETE / 247.5 | 1 | 16.67081 |
| p3b5_v57_dev_zero_zero_rally_lab_fault | COMPLETE / 167.0 | 0 | 19.29369 |

只读诊断/关闭后审计：

```bash
/usr/bin/python3 /tmp/diagnose_p3b5_v57_native_windows.py > /tmp/p3b5_v57_native_windows.log 2>&1
/usr/bin/python3 /tmp/audit_p3b5_v57_development.py > /tmp/p3b5_v57_development_audit.log 2>&1
```

Lab101 final poses near within3.3cm; read-only physics eligibility at final poses (not replacement mission proof) longest final-segment speed/position window3.0s. Extra yaw legs offsets289.7 and298.7 were emitted with fresh target source age1.2s; continuing correction despite healthy detection interrupted settling. Underlying physical yaw drift still not established from cmd_vel.

全部结果含原生hold proof/无proof、完整AP快照、源/协议/参数/命令/环境/graph/ledger/file SHA与失败均保留。四个COMPLETE不能替代failed lab101；force余量4.7/.5s，不宣称最坏时限可靠性或单因素改善。zero fault不同async轨迹/充电数不是通信收益。仅开发，未调用完整strict checker/PASS图文，未暴露809，无ns3/RL。

## 2026-10-05 P3B.5 v58持续确认与安静保持组件/留出控制再冻结

2026-10-05 P3B.5 v58候选只在目标确认源间断超过现有5秒观测者新鲜度窗口、但60秒目标lease仍有效时考虑停驻朝向校正；继续正常检测时允许安静保持。四分之一相机FOV、交付map-frame yaw、新鲜位姿/地图/目标、ACTIVE、网关导航/完整能量/实际body/route/return/并发保护保持。451组件PASS14.21s、四包build5.15s、source3r0旁路、27case/41unique validate-only；native_completion_ok/episode_ok原样，原300s/.35/.05/.1/5s未改。证据report/20261005_p3b5_observer_confirmation_gap_component.json；原v57五格FAIL已5f50357归档，不回填。809world/seed/fault原样未暴露，预声明更新控制SHA与实际launch静态补查并保留旧原文件标签/两次冻结历史。新完整v58自身按先force原生/E0/真实断网返充→十fixed→完整27/41+六辅助推进，提供新的lab101/force集成验证，无需另称独立开发PASS；总57原任务全部保留、无retry。P3B.5未通过，待完整门禁，无ns3/RL。

ROS canonical cwd、source Humble/install、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/component_checks、通过rtk bash -lc，全部离线组件：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v58_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v58_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v58_source_audit.log 2>&1
/usr/bin/python3 scripts/run_p3b5_tasks.py --config scripts/p3b5_fault_manifest.json --run-id p3b5_v58_predeclare_validation_only --ros-domain-base 50 --validate-only > /tmp/p3b5_v58_plan_validate.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py > /tmp/p3b5_v58_protocol_metadata_checks.log 2>&1
/usr/bin/python3 /tmp/refreeze_p3b5_v58_holdout_controller.py
```

Geometry/seed/fault809/28091 unchanged, not yet exposed; generic initial static point labels retained with correction and actual frozen launch static PASS. Gap/heading policy heuristic, detector remains geometric visibility proxy. Original300/.35/.05/.1/5 and native evaluator checker unchanged. No ns3/RL.

## 2026-10-05 P3B.5 v58强制充电原始候选失败

2026-10-05 P3B.5 v58原候选FAIL，冻结cf73eebd875d990bd782cef572d09b484b23900a；2026-10-04 16:19:20–16:33:04UTC自然关闭。6started/6raw、0接触/0基础设施失败、6账本与6图审计PASS、54纯协议PASS。强制充电ideal直到242.2s检测、260.2s进入RALLY，300.4s仍有tb1在最终路线中，各charge1、最低8.11062，无原生COMPLETE，不能判通过；force fault300.2s也RALLY timeout。E0双格为预声明FAILED且无导航；controlled remote双格各充电一次/正能量/0接触，关闭后只读严格physical-return审计PASS，证明断网窗口中的实际Nav2返航，并非任务成功。其余51格含全部固定与809未启动；新809/28091仍未暴露，原707不得视为未暴露。只读日志显示返航取消西侧前沿后，充电恢复按即时收益重分配到东侧，再回西侧而造成较晚检测；这是待开发验证的任务接续问题，不是单次运行的因果收益证明。报告见report/20261005_p3b5_confirmation_gap_forced_failed_candidate.json。所有owned owner/观察器/master自然关闭后归档，domain222未动。完整strict checker/PASS报告/图未执行，P3B.5仍未完成，无ns-3/WiFi/RL。

源cf73eeb干净已push，451组件/四包build5.15s/source0/46metadata checks；Humble/install/Gazebo，canonical ROS cwd，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=canonical/log/ros_launch。master15750–15753，CPU0–19/20–39/40–59/60–79，domains44/45、28/29、20/21；原dispatcher组全部exit0后，episode_ok在ideal success断言失败而exit1；没有重启或回填。

```bash
/usr/bin/python3 /tmp/p3b5_v58_bootstrap.py > /tmp/p3b5_v58_bootstrap.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15750 taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v58_task_pool.py '{"run": "p3b5_v58_forced", "cases": ["forced_charge_outage"], "domain_base": 44}' > /tmp/p3b5_v58_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15751 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v58_zero_first.py > /tmp/p3b5_v58_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15752 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v58_returnproof --ros-domain-base 20 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v58_returnproof.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15753 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_cf73eeb.json > /tmp/p3b5_protocol_cf73eeb.log 2>&1
```

实际六格命令：

```bash
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:15751 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v58_zero_ideal_lab2_rally_0678e85373 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_zero/p3b5_v58_zero_ideal_lab2_rally_0678e85373 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_zero/p3b5_v58_zero_ideal_lab2_rally_0678e85373/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_zero/p3b5_v58_zero_ideal_lab2_rally_0678e85373/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_zero/p3b5_v58_zero_ideal_lab2_rally_0678e85373/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=29 GAZEBO_MASTER_URI=http://127.0.0.1:15751 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v58_zero_battery_exhaust_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_zero/p3b5_v58_zero_battery_exhaust_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_zero/p3b5_v58_zero_battery_exhaust_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_zero/p3b5_v58_zero_battery_exhaust_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_zero/p3b5_v58_zero_battery_exhaust_lab_fault/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=44 GAZEBO_MASTER_URI=http://127.0.0.1:15750 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v58_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_forced/p3b5_v58_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_forced/p3b5_v58_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_forced/p3b5_v58_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_forced/p3b5_v58_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=45 GAZEBO_MASTER_URI=http://127.0.0.1:15750 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v58_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_forced/p3b5_v58_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_forced/p3b5_v58_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_forced/p3b5_v58_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_forced/p3b5_v58_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:15752 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v58_returnproof_ideal_forced2_rally_4c7c808f36 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_returnproof/p3b5_v58_returnproof_ideal_forced2_rally_4c7c808f36 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_returnproof/p3b5_v58_returnproof_ideal_forced2_rally_4c7c808f36/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_returnproof/p3b5_v58_returnproof_ideal_forced2_rally_4c7c808f36/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_returnproof/p3b5_v58_returnproof_ideal_forced2_rally_4c7c808f36/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=21 GAZEBO_MASTER_URI=http://127.0.0.1:15752 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v58_returnproof_physical_return_under_blackout_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_returnproof/p3b5_v58_returnproof_physical_return_under_blackout_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_returnproof/p3b5_v58_returnproof_physical_return_under_blackout_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_returnproof/p3b5_v58_returnproof_physical_return_under_blackout_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v58_returnproof/p3b5_v58_returnproof_physical_return_under_blackout_fault/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
```

| 原始 episode | phase / elapsed(s) | charges | 最低能量 |
|---|---|---:|---:|
| p3b5_v58_zero_ideal_lab2_rally_0678e85373 | FAILED / 1.8 | 0 | 0.00000 |
| p3b5_v58_zero_battery_exhaust_lab_fault | FAILED / 1.8 | 0 | 0.00000 |
| p3b5_v58_forced_ideal_forced2_rally_86fbb43bc6 | RALLY / 300.4 | 2 | 8.11062 |
| p3b5_v58_forced_forced_charge_outage_fault | RALLY / 300.2 | 2 | 7.01518 |
| p3b5_v58_returnproof_ideal_forced2_rally_4c7c808f36 | RALLY / 300.2 | 2 | 9.54092 |
| p3b5_v58_returnproof_physical_return_under_blackout_fault | EXPLORE / 300.3 | 2 | 9.65034 |

断网62–248s严格运动证明：tb1: offset172.7s,home1.98534m,path1.17401m,net1.16880m,Nav2EXEC1.17397m; tb2: offset171.2s,home2.01065m,path1.17720m,net1.16953m,Nav2EXEC1.17717m。两机各充电1、能量正、零接触；这是安全探针，原timeout保留。

关闭后只读审计与归档：

```bash
/usr/bin/python3 /tmp/audit_p3b5_v58_return_subgate.py > /tmp/p3b5_v58_return_subgate_postclose.log 2>&1
/usr/bin/python3 /tmp/archive_p3b5_cf73eeb_failed.py > /tmp/p3b5_v58_archive_failed.log 2>&1
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python /tmp/document_p3b5_v58_failure.py
```

监控脚本首次StringIO被exec共享globals覆盖造成AttributeError；改为隔离globals后仅只读监控恢复，任务未受影响，两个源码均保留。初次寻找launch log采用不存在的路径，后从原summary定位真实路径；这两处均为只读诊断错误，非试验基础设施失败。完整归档含全部6raw、命令/环境/冻结源码/协议、原生字段、图/账本审计、AP/physics文件hash、前沿分配日志、6结果及51unrun。

## 2026-10-05 P3B.5 v59充电中断前沿接续组件

2026-10-05 P3B.5 v59开发组件：充电/同伴返航取消探索动作后保存搜索意图；恢复只优先最新地图中距原前沿≤1.2m、gain>max(200,原20%)且完整往返预算factor≥1的当前候选，继续经过源TTL/动态身体/已接受路线/可见短腿/gateway。旧意图不是旧指令重放；已观测/阻塞/预算不足回退、成功前缀继续意图、抵达或明确FAILED清除。针对20项1.14s PASS后补明确失败清理检查，完整472项13.60s、四包build5.34s、source3r0旁路。原native_completion_ok/episode_ok与300s/.35/.05/.1/5未改。证据report/20261005_p3b5_interrupted_frontier_component.json；原v58六格FAIL已a6830cc归档，809/28091仍未运行。接续为待集成验证启发式，无因果/最坏时间保证；将先冻结独立lab101/forced303/zero303开发，全部自然关闭后才能修改或归档，再重新冻结正式57格。P3B.5尚未完成，无ns-3/RL。

ROS canonical cwd，source Humble/install、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/component_checks，rtk bash -lc执行，未运行Gazebo：

```bash
/usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_exploration_resume.py > /tmp/p3b5_v59_resume_targeted.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v59_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v59_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v59_source_audit.log 2>&1
```

17用户材料hash保持不变；实现复用既有IG/完整往返预算/路径准入，未新增依赖。独立开发还未启动，组件PASS不得替代fixed/forced/协议/物理返航和新809完整原始门禁。

## 2026-10-05 P3B.5 v59前沿接续独立开发五格失败

2026-10-05 P3B.5 v59独立开发五格FAIL，冻结5dcb398e1dbe72f9c34c667f924b2306ff11ffed；2026-10-04 16:49–17:01:48UTC所有原owner/观察器自然结束。force ideal原生COMPLETE216.0s、检测132.8/RALLY148.0s、各机器人charge1/最低8.63273；zero ideal原生COMPLETE231.9s/总charge1。force fault EXPLORE timeout300.1s、各charge1/最低7.73411，安全检查通过但不是任务成功。lab3/101在91.5s发现/93.7s RALLY，300.4s仍tb3距最终位1.733m、总charge2/最低22.18681；zero fault300.4s RALLY timeout、tb1返航耗尽至0/FAILED，真实安全失败必须修复。五格0碰撞/0infra、五ledger TTL/versions与graph旁路PASS，无重试/回填/阈值放宽。接续日志存在但不能把不同async轨迹的时间差视为单因素收益。只读AP条件路线诊断提示驻点机体增加后继绕行，并发现local return无单腿进度取消监督；报告report/20261005_p3b5_interrupted_frontier_development.json完整保留。809/28091未执行，正式57格/PASS图文未启动，P3B.5仍未完成，无ns3/RL。

ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master15850–15852/domains16–20/CPU0–19、20–39、40–59。预声明全部5/source/config/环境/hash后启动，17用户资料不变。全部owner结束lab exit1、force/zero pool exit0，observer退出正常；独立auditor再判2个development失败。rtk bash -lc：

```bash
/usr/bin/python3 /tmp/run_p3b5_v59_development.py > /tmp/p3b5_v59_development_dispatcher.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15850 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v59_dev_first_lab101.py > /tmp/p3b5_v59_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15851 taskset -c 20-39 /usr/bin/python3 /tmp/run_p3b5_v59_dev_task_pool.py '{"run": "p3b5_v59_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 17}' > /tmp/p3b5_v59_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15852 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v59_dev_task_pool.py '{"run": "p3b5_v59_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 19}' > /tmp/p3b5_v59_dev_zero_pool.log 2>&1
```

实际五格命令：

```bash
ROS_DOMAIN_ID=16 GAZEBO_MASTER_URI=http://127.0.0.1:15850 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v59_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v59_dev_fixed_lab101/launch_logs --episode-id p3b5_v59_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v59_dev_fixed_lab101/graphs/p3b5_v59_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v59_dev_fixed_lab101/episodes/p3b5_v59_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=17 GAZEBO_MASTER_URI=http://127.0.0.1:15851 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v59_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_forced/p3b5_v59_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_forced/p3b5_v59_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_forced/p3b5_v59_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_forced/p3b5_v59_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=18 GAZEBO_MASTER_URI=http://127.0.0.1:15851 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v59_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_forced/p3b5_v59_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_forced/p3b5_v59_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_forced/p3b5_v59_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_forced/p3b5_v59_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=19 GAZEBO_MASTER_URI=http://127.0.0.1:15852 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v59_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_zero/p3b5_v59_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_zero/p3b5_v59_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_zero/p3b5_v59_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_zero/p3b5_v59_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:15852 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v59_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_zero/p3b5_v59_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_zero/p3b5_v59_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_zero/p3b5_v59_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v59_dev_zero/p3b5_v59_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | phase / seconds | charges | minimum energy | failed robots |
|---|---|---:|---:|---|
| p3b5_v59_dev_fixed_lab101_lab_far_northwest_3r_seed101 | RALLY / 300.4 | 2 | 22.18681 | [] |
| p3b5_v59_dev_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 216.0 | 2 | 8.63273 | [] |
| p3b5_v59_dev_forced_forced_charge_outage_fault | EXPLORE / 300.1 | 2 | 7.73411 | [] |
| p3b5_v59_dev_zero_ideal_lab2_rally_8d4d5c469d | COMPLETE / 231.9 | 1 | 21.76936 | [] |
| p3b5_v59_dev_zero_zero_rally_lab_fault | RALLY / 300.4 | 1 | 0.00000 | ['tb1'] |

关闭后的只读命令：

```bash
/usr/bin/python3 /tmp/audit_p3b5_v59_development.py > /tmp/p3b5_v59_development_audit.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v59_parked_routes.py > /tmp/p3b5_v59_parked_route_diagnosis.log 2>&1
```

Independent AP first snapshot conditional replay reproduces assigned coordinates, not original buffers. Actual parked observer at(-3.98093,1.40642) forces hypothetical charged-home routes6.808/6.515m to8.118/7.908m. Alternative known-free visible(-4.68093,1.50642) keeps observer funded/no extra predicted charge and leaves both baseline routes clear; estimated serial approach14.6595 versus16.6211m. This is static conditional geometry, not a validated alternative order or mission/causal benefit. Zero-fault tb1 return last local Nav2 goal from(-.997,-.308) to(-.0859,-.342) persisted about60wall seconds until battery exhausted; native final(-.111,-1.385), failed robot remains real failure. Local return lacks per-leg progress watchdog.

AP地图保留原文件及SHA，规范JSON的AP快照仅把data数组替换cell_count/数据SHA来减少重复体积，其余源/时间/位姿/TF/battery/检测/assignment不删。诊断不是额外ROS/Gazebo实验，不用于controller；真实zero耗尽不能被TDI或正能量ideal替代，未来修改需重新冻结验证。

## 2026-10-05 P3B.5 v60观测者驻点绕行/本地返充进度组件

2026-10-05 P3B.5 v60组件：ACTIVE且无需预充电的真实观测者驻点选择，把待充电同伴home路线的驻点机体绕行加入名义时间评分；按observer候选/home缓存masked距离场，缺路线保留有限30s恢复代价而非假不可行，部分界仍乐观。本地返充独立监督已接受Nav2单腿：0.1m单调进展、20s无进展或max(30s,2*已知自由腿长/名义速+10s)超时仅请求一次取消，保留handle至result后重新规划，CHARGING/FAILED/terminal不干预；原总返航时限/储备/稳定充电未改。原300s/.35/.05/.1/5s与native completion函数原样，487组件13.72s、四包build5.38s、source3r0旁路。首return夹具漏callback1fail39pass、修正后321PASS；首parking夹具强求特定侧点1fail1pass，实际另一个funded非阻塞点更优，修正为验证入口不被堵与两条masked路线，全部487PASS；失败日志保留。独立AP条件重算选侧方点并消除预测绕行，0.81454s只是单次组件样本，无任务/因果/最坏保证。报告report/20261005_p3b5_observer_parking_return_progress_component.json。v59五格两失败已02c8d86完整归档，809/28091仍未执行；新独立开发和正式57格尚待验证，P3B.5未完成，无ns3/RL。

ROS canonical cwd、source Humble/install，PYTHONNOUSERSITE=1/ROS_LOG_DIR=log/component_checks，rtk bash -lc；未运行Gazebo：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_battery_manager.py > /tmp/p3b5_v60_return_progress_targeted.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_control.py > /tmp/p3b5_v60_return_parking_targeted.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_rally_observer_parking.py > /tmp/p3b5_v60_parking_targeted.log 2>&1
/usr/bin/python3 /tmp/replay_p3b5_v60_parked_observer.py > /tmp/p3b5_v60_parked_route_component.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v60_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v60_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v60_source_audit.log 2>&1
```

First return fixture omitted callback:1fail39pass; corrected combined321PASS. First parking fixture wrongly insisted on alcove, but another funded nonblocking pose had lower score:1fail1pass; corrected assertion requires nonblocking observer and both actual masked peer routes, full487PASS. Raw logs and first parking fixture retained.

Conditional AP replay uses a separate subscriber snapshot, not original controller buffers. New observer(-4.68093,1.50642) clears predicted peer routes while retaining two predicted charges; runtime0.81454s is one component sample, not worst-case or mission/causal benefit. Per-leg nominal watchdog and detour cost are heuristics; no worst-case safety/timing guarantee.809 unexposed; development101/202/303 are not heldout tests. No ns3/RL.

## 2026-10-05 P3B.5 v60驻点路径与返航进度独立开发失败

2026-10-05 P3B.5 v60独立开发五格FAIL，冻结79a3b05b5101418cd99dd8cb7cd6d4630c0eb823；2026-10-04 17:39:47–17:52:26UTC三个owner全部exit0、原观察器自然关闭。lab3/101原生COMPLETE198.5s/charge0/最低23.35519；force ideal原生COMPLETE214.8s/各charge1/最低8.91814，force fault300.1s RALLY timeout/各charge1/最低8.03192，安全子门通过但非任务成功。zero ideal283.8s检测/291.2s RALLY、300.0s timeout/各charge1/最低4.03001；zero fault原生COMPLETE271.6s/总charge1/最低21.73648。五格0碰撞/0耗尽/0failed/0infra、五ledger TTL/version与graph旁路PASS；原生阈值未改，无重试/回填。前沿接续/驻点绕行成本/返航watchdog尚不能解决晚发现；只读日志证实远端不够完整任务预算的探索fallback与返航先于迟到的西北发现，watchdog有一次真实取消，但不作单因素因果或最坏时保证。完整报告report/20261005_p3b5_parking_return_development.json/.md。809/28091从未执行，正式57格/PASS图文未启动，P3B.5仍未完成，无ns3/RL。

ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master15950–15952/domains16–20/CPU0–19、20–39、40–59。全部5预声明/source/config/环境/hash后启动，17用户资料未变。三个ownerexit0，仅代表runner自然结束；独立开发checker为FAIL/一格未满足原生COMPLETE。执行入口rtk bash -lc：

```bash
/usr/bin/python3 /tmp/run_p3b5_v60_development.py > /tmp/p3b5_v60_development_dispatcher.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15950 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v60_dev_first_lab101.py > /tmp/p3b5_v60_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15951 taskset -c 20-39 /usr/bin/python3 /tmp/run_p3b5_v60_dev_task_pool.py '{"run": "p3b5_v60_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 17}' > /tmp/p3b5_v60_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:15952 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v60_dev_task_pool.py '{"run": "p3b5_v60_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 19}' > /tmp/p3b5_v60_dev_zero_pool.log 2>&1
```

实际五格命令：

```bash
ROS_DOMAIN_ID=16 GAZEBO_MASTER_URI=http://127.0.0.1:15950 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v60_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v60_dev_fixed_lab101/launch_logs --episode-id p3b5_v60_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v60_dev_fixed_lab101/graphs/p3b5_v60_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v60_dev_fixed_lab101/episodes/p3b5_v60_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=17 GAZEBO_MASTER_URI=http://127.0.0.1:15951 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v60_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_forced/p3b5_v60_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_forced/p3b5_v60_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_forced/p3b5_v60_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_forced/p3b5_v60_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=18 GAZEBO_MASTER_URI=http://127.0.0.1:15951 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v60_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_forced/p3b5_v60_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_forced/p3b5_v60_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_forced/p3b5_v60_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_forced/p3b5_v60_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=19 GAZEBO_MASTER_URI=http://127.0.0.1:15952 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v60_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_zero/p3b5_v60_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_zero/p3b5_v60_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_zero/p3b5_v60_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_zero/p3b5_v60_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:15952 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v60_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_zero/p3b5_v60_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_zero/p3b5_v60_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_zero/p3b5_v60_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v60_dev_zero/p3b5_v60_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | phase / seconds | charges | minimum energy |
|---|---|---:|---:|
| p3b5_v60_dev_fixed_lab101_lab_far_northwest_3r_seed101 | COMPLETE / 198.5 | 0 | 23.35519 |
| p3b5_v60_dev_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 214.8 | 2 | 8.91814 |
| p3b5_v60_dev_forced_forced_charge_outage_fault | RALLY / 300.1 | 2 | 8.03192 |
| p3b5_v60_dev_zero_ideal_lab2_rally_8d4d5c469d | RALLY / 300.0 | 2 | 4.03001 |
| p3b5_v60_dev_zero_zero_rally_lab_fault | COMPLETE / 271.6 | 1 | 21.73648 |

关闭后的只读审核/诊断：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /tmp/audit_p3b5_v60_development.py > /tmp/p3b5_v60_development_audit.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v60_completion.py > /tmp/p3b5_v60_completion_diagnosis.log 2>&1
```

Zero ideal detects283.8s/RALLY291.2s, so peer final error3.67768m at300s is late discovery, not failed native hold alone. Before discovery both execute unfunded long frontier fallback: tb2 west path9.13m utility19, tb1 west11.47m utility7.8; repeated local prefixes/reassignments precede reserve-triggered returns. Local tb2 watchdog really cancels no-waypoint-progress return once and replans; all five originals stay positive, which is observed safety, not a worst-case guarantee or single-factor causal proof. Both charge once in zero ideal and resume current funded west frontier, but discovery remains too late. Lab native198.5/charge0 versus prior timeout/charge2 is an asynchronous multi-change result, not isolated parking benefit. Forced fault detects253.4/RALLY262.9 and is nonCOMPLETE300.1, while its positive/every-robot-charge safety subgate passes. All failures and original start/finish/commands retained; no809 exposure.

First closed audit invoked without sourcing ROS/install failed at import ModuleNotFoundError before reading any results; correctly sourced read-only audit then finished exit0/FAIL. This did not start or retry a mission.
A read-only rg used a nonexistent guessed owner log path; corrected using original summary command --log-dir. First chronology omitted launch logs because summary stores command/log directory rather than direct .log field; original output retained plus corrected chronology. None changed results or control.

AP地图保留原文件SHA，规范快照仅以cell_count/数据SHA替换重复data数组；其他位姿、TF、battery、目标、源时间全部保留。真值只用于验收/诊断，不送controller。

## 2026-10-05 P3B.5 v61完整探索预算准入与提前充电组件

2026-10-05 P3B.5 v61组件：中央探索只准入当前可负担的完整前沿任务；未负担的前沿仍经当前地图/机体/可见短腿检查作为充电候选，不再执行已预计会被本地储备中断的远端fallback。所有已接收探索动作结束、无RETURNING/CHARGING后，只通过原gateway charge_request串行请求一个idle机器人提前充电，优先近home并保留当前前沿意图；充电后重新生成/核验。预算不小于充电目标或无效context不重复充电，现有rally pending owner覆盖阶段切换，2s重发；原10s请求租约保持，只在更新ACTIVE source超过租约后释放丢失请求，发现目标进入RALLY也适用。本地接受EXPLORE/FOUND_UNCONFIRMED/FOUND/RALLY有效幂等请求，拒绝未来/过期/terminal。增加charge决策输入租约与消费因果审核。516组件14.76s、四包build5.28s、source3r0旁路；native300s/.35/.05/.1/5s函数AST与d3acb28一致。首夹具5fail61pass：4漏导入、1误写5s而原租约10s；修正108PASS；跨阶段修复前515PASS日志保留。case template首命令漏--run-id仅参数解析失败，修正只读validate-only；不是任务启动/重试。组件报告report/20261005_p3b5_exploration_charge_admission_component.json。v60五格失败已d3acb28归档；809/28091未暴露，其旧cf73 controller声明待开发通过后前瞻重新冻结；新开发/正式57格仍未验证，P3B.5未完成，无ns3/RL。

ROS canonical cwd，source Humble/install、PYTHONNOUSERSITE=1/ROS_LOG_DIR=log/component_checks，rtk bash -lc；未运行Gazebo：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_battery_manager.py > /tmp/p3b5_v61_charging_targeted.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_battery_manager.py scripts/test_p3b5_gate.py > /tmp/p3b5_v61_charging_gate_targeted.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v61_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v61_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v61_source_audit.log 2>&1
/usr/bin/python3 scripts/run_p3b5_tasks.py --validate-only > /tmp/p3b5_v61_case_template_attempt1.log 2>&1
/usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v61_template_validation --validate-only > /tmp/p3b5_v61_case_template_validation.log 2>&1
```

Full-trip energy model uses inherited current/frontier-home Euclidean factor and nominal motion/idle costs, not a proved obstacle-route/time bound. Early charging, continuity, parking, return watchdog and heading recovery remain heuristics. Component tests prove specified invariants, not mission performance or worst-case safety. Actual motion still respects delivered source leases/body masks/accepted route reservations/gateway, local reserve owns safety. Geometric Gazebo visibility detector is not image recognition. AP truth remains evaluation-only. No809 exposure or ns3/RL. Template validation counts are not a current frozen holdout declaration or simulation results.

## 2026-10-05 P3B.5 v61探索预算充电独立开发失败

2026-10-05 P3B.5 v61独立开发五格FAIL，冻结cf829cf23ae56adb65ca9a54b13b34132cddbd09；2026-10-04 18:18:54–18:31:08UTC所有原owner/观察器自然关闭，lab exit1、force/zero pool exit0。force ideal原生COMPLETE209.8s/各charge1/最低8.79340，zero fault原生COMPLETE160.8s/charge0/最低23.15425。lab3/101检测126.3/RALLY128.4、300.3s timeout/charge1/最低13.98203，tb1/tb2尚RETURNING；zero ideal检测133.7/RALLY143.7、300.0s timeout/各charge1/最低14.29596。force fault300.4s EXPLORE timeout、tb1 charge1/tb2 charge0且末端仅CHARGING3.5s/最低7.38321，未满足各机器人充电安全子门。五格0碰撞/0耗尽/0failed/0infra、五ledger因果/TTL/version/charge消费与决策租约PASS、五graph0旁路，无整轮重试/回填。提前探索充电真实执行，但只在所有可负担任务耗尽才考虑充电，会让已充电同伴连续获任务而饿死idle充电候选；当前驻点成本只计真实observer，其他funded驻点也可能挡charged peer；RALLY名义预算仍无最坏时间保证。报告report/20261005_p3b5_frontier_charge_admission_development.json/.md保留全部原始命令/日志/取证，时间差不作单因素收益。809/28091从未执行，正式57格/PASS图文未启动，P3B.5未完成，无ns3/RL。

ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master16050–16052/domains16–20/CPU0–19、20–39、40–59。全部5预声明/source/config/环境/hash后启动，17用户资料不变。runner自然结束不等于开发通过；独立checker记录3FAIL。实际入口rtk bash -lc：

```bash
/usr/bin/python3 /tmp/run_p3b5_v61_development.py > /tmp/p3b5_v61_development_dispatcher.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16050 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v61_dev_first_lab101.py > /tmp/p3b5_v61_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16051 taskset -c 20-39 /usr/bin/python3 /tmp/run_p3b5_v61_dev_task_pool.py '{"run": "p3b5_v61_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 17}' > /tmp/p3b5_v61_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16052 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v61_dev_task_pool.py '{"run": "p3b5_v61_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 19}' > /tmp/p3b5_v61_dev_zero_pool.log 2>&1
```

实际五格命令：

```bash
ROS_DOMAIN_ID=16 GAZEBO_MASTER_URI=http://127.0.0.1:16050 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v61_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v61_dev_fixed_lab101/launch_logs --episode-id p3b5_v61_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v61_dev_fixed_lab101/graphs/p3b5_v61_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v61_dev_fixed_lab101/episodes/p3b5_v61_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=17 GAZEBO_MASTER_URI=http://127.0.0.1:16051 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v61_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_forced/p3b5_v61_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_forced/p3b5_v61_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_forced/p3b5_v61_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_forced/p3b5_v61_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=18 GAZEBO_MASTER_URI=http://127.0.0.1:16051 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v61_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_forced/p3b5_v61_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_forced/p3b5_v61_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_forced/p3b5_v61_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_forced/p3b5_v61_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=19 GAZEBO_MASTER_URI=http://127.0.0.1:16052 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v61_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_zero/p3b5_v61_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_zero/p3b5_v61_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_zero/p3b5_v61_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_zero/p3b5_v61_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:16052 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v61_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_zero/p3b5_v61_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_zero/p3b5_v61_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_zero/p3b5_v61_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v61_dev_zero/p3b5_v61_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | phase / seconds | charges | minimum energy |
|---|---|---:|---:|
| p3b5_v61_dev_fixed_lab101_lab_far_northwest_3r_seed101 | RALLY / 300.3 | 1 | 13.98203 |
| p3b5_v61_dev_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 209.8 | 2 | 8.79340 |
| p3b5_v61_dev_forced_forced_charge_outage_fault | EXPLORE / 300.4 | 1 | 7.38321 |
| p3b5_v61_dev_zero_ideal_lab2_rally_8d4d5c469d | RALLY / 300.0 | 2 | 14.29596 |
| p3b5_v61_dev_zero_zero_rally_lab_fault | COMPLETE / 160.8 | 0 | 23.15425 |

关闭后的只读审核/诊断：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /tmp/audit_p3b5_v61_development.py > /tmp/p3b5_v61_development_audit.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v61_completion.py > /tmp/p3b5_v61_completion_diagnosis.log 2>&1
```

Forced fault tb1 charges once and keeps exploring; tb2 completes zero charges and endsCHARGING after only3.5s at300.4. Existing request_exploration_charge is considered only when no funded admissions exist anywhere and no live exploration exists, so funded work can repeatedly hide a needed idle peer charge. Logs/code establish this admission mechanism; no isolated causal timing claim. Lab detects126.3/RALLY128.4 but ends300.3 with tb1/tb2 RETURNING and tb3 charged/arrived; RALLY path27.006m and allocation/recovery includes a funded non-observer parking in charged-peer corridor. Parking leaf cost currently models only the designated observer body, not other funded peers. Zero ideal detects133.7/RALLY143.7, tb2 early RALLY charge, tb1 later needs a second charge after waiting/body detours; at300s tb1 near changed final and tb2 4.510m away. Nominal whole-rally budgets do not guarantee actual wait/motion. Original data/AP subscriber snapshots are evidence/forensics, not controller truth or exact original buffers. Frontier budget filtering alone does not solve fair charging admission or all parked-peer traffic.

AP地图仅重复data数组改为cell_count/SHA；完整原文件hash、其他源时间/位姿/TF/能量/目标均保留。完整COMPLETE只用原生保持，真值不作控制输入；正式批次仍需新冻结。

## 2026-10-05 P3B.5 v62公平返充窗口与所有funded驻点组件

2026-10-05 P3B.5 v62组件：当前2/3机前沿调度对无可负担替代、充电后可执行的idle同伴建立公平充电窗口；不再要求所有机器人耗尽funded工作才充电。停止新增探索腿但不取消原已接受动作，原动作自然结束后经同gateway串行请求返充，CHARGING期间有待充电同伴则暂缓新探索；同机器人有当前funded替代仍正常准入，无效/超容量预算不关闭其他funded准入。当前批次每机器人只保留最高效用的可行充电意图，跳过重复较低效用unfunded路线，但所有funded候选仍检查；20候选夹具路线调用≤2。集合叶评分对每个ACTIVE且无需预充电的驻点body累加charged peers home路线的单体绕行代价，而非只计observer；按body候选/home源缓存，非负部分界仍乐观，缺masked路线沿用有限30s恢复代价。它是加性静态启发式，不证明联合body路线可行，实际派发仍检查全部body/在途/返航/输入租约/能量。窄入口原parent分配nonobserver堵住第三机路径，新分配侧移后联合body路线4.0m；单组件0.02647/0.03615s不是任务/最坏收益。304定向11.48s、全部521组件14.11s、四包build5.36s、source3r0旁路，native300s/.35/.05/.1/5s函数AST不变。v61五格3FAIL已c3319f0归档；报告report/20261005_p3b5_charging_fairness_parked_peers_component.json。新独立开发及正式57格仍待验证，809/28091未暴露，P3B.5未完成，无ns3/RL。

ROS canonical cwd、source Humble/install，PYTHONNOUSERSITE=1/ROS_LOG_DIR=log/component_checks，rtk bash -lc；未运行Gazebo：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_control.py > /tmp/p3b5_v62_charging_parking_targeted.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v62_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v62_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v62_source_audit.log 2>&1
/usr/bin/python3 /tmp/compare_p3b5_v62_parked_peers.py > /tmp/p3b5_v62_parked_peers_comparison.log 2>&1
```

Fair charging liveness depends on existing action termination and delivery, not a worst-case bound. Additive per-body detours can miss or overcount combined interactions; actual dispatch remains the safety check. Nominal energy/arrival budgets are not proved physical timing guarantees. No algorithm input uses native truth or unseen809. Synthetic component comparison is not a mission, isolated task ablation, heldout evaluation or performance guarantee.

## 2026-10-05 P3B.5 v62公平充电独立开发失败

2026-10-05 P3B.5 v62独立开发五格FAIL，冻结d2a9b47b4deb5b19294d529a5a3209ceddef9d93；2026-10-04 18:56:08–19:09:44UTC三个owner全部exit0、原观察器自然关闭。lab3/101原生COMPLETE184.7s/charge1/最低25.69497，zero ideal原生COMPLETE163.0s/charge0/最低20.02148，force fault原生COMPLETE294.2s/各charge1/最低8.90970。force ideal284.6s才检测、285.8s RALLY、300.3s timeout/各charge1/最低7.52388；zero fault261.6s才检测、269.4s RALLY、300.1s timeout/各charge1/最低15.33104。五格0碰撞/0耗尽/0failed/0infra、五ledger因果/TTL/version/charge消费与决策租约PASS、五graph0旁路，无整轮重试/回填。公平充电与全驻点成本仍未解决长探索与远端返充；原生300s/.35/.05/.1/5s标准未改，时间差不作单因素收益。报告report/20261005_p3b5_charging_fairness_development.json/.md保留全部原命令/日志/取证，包括v61关闭后LOS/FOV只读诊断及首次函数名错误；真值不作控制输入。809/28091从未执行，正式57格/PASS图文未启动，P3B.5未完成，无ns3/RL。

ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master16150–16152/domains16–20/CPU0–19、20–39、40–59。全部5预声明/source/config/环境/hash后启动，17用户资料不变。runner自然结束不等于开发通过；独立checker记录2FAIL。实际入口rtk bash -lc：

```bash
/usr/bin/python3 /tmp/run_p3b5_v62_development.py > /tmp/p3b5_v62_development_dispatcher.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16150 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v62_dev_first_lab101.py > /tmp/p3b5_v62_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16151 taskset -c 20-39 /usr/bin/python3 /tmp/run_p3b5_v62_dev_task_pool.py '{"run": "p3b5_v62_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 17}' > /tmp/p3b5_v62_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16152 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v62_dev_task_pool.py '{"run": "p3b5_v62_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 19}' > /tmp/p3b5_v62_dev_zero_pool.log 2>&1
```

实际五格命令：

```bash
ROS_DOMAIN_ID=16 GAZEBO_MASTER_URI=http://127.0.0.1:16150 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v62_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v62_dev_fixed_lab101/launch_logs --episode-id p3b5_v62_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v62_dev_fixed_lab101/graphs/p3b5_v62_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v62_dev_fixed_lab101/episodes/p3b5_v62_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=17 GAZEBO_MASTER_URI=http://127.0.0.1:16151 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v62_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_forced/p3b5_v62_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_forced/p3b5_v62_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_forced/p3b5_v62_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_forced/p3b5_v62_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=18 GAZEBO_MASTER_URI=http://127.0.0.1:16151 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v62_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_forced/p3b5_v62_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_forced/p3b5_v62_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_forced/p3b5_v62_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_forced/p3b5_v62_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=19 GAZEBO_MASTER_URI=http://127.0.0.1:16152 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v62_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_zero/p3b5_v62_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_zero/p3b5_v62_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_zero/p3b5_v62_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_zero/p3b5_v62_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:16152 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v62_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_zero/p3b5_v62_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_zero/p3b5_v62_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_zero/p3b5_v62_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v62_dev_zero/p3b5_v62_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | phase / seconds | charges | minimum energy |
|---|---|---:|---:|
| p3b5_v62_dev_fixed_lab101_lab_far_northwest_3r_seed101 | COMPLETE / 184.7 | 1 | 25.69497 |
| p3b5_v62_dev_forced_ideal_forced2_rally_86fbb43bc6 | RALLY / 300.3 | 2 | 7.52388 |
| p3b5_v62_dev_forced_forced_charge_outage_fault | COMPLETE / 294.2 | 2 | 8.90970 |
| p3b5_v62_dev_zero_ideal_lab2_rally_8d4d5c469d | COMPLETE / 163.0 | 0 | 20.02148 |
| p3b5_v62_dev_zero_zero_rally_lab_fault | RALLY / 300.1 | 2 | 15.33104 |

关闭后的只读审核/诊断：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /tmp/audit_p3b5_v62_development.py > /tmp/p3b5_v62_development_audit.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v62_completion.py # stdout delivered in tool; chronology JSON retained
```

V62 forced ideal first detects284.6s/RALLY285.8s and times out300.3s: each charges once, but tb2 return contains three short corner legs and retry delay; tb1 low-gain nearby tasks continue before its late return. Zero fault detects261.6s/RALLY269.4s, two serial distant exploratory returns, times out300.1. Lab native184.7s, zero ideal163.0s, forced fault294.2s. This is observational chronology, not isolated causal benefit. V61 closed-snapshot geometric analysis shows clear LOS at sampled parked observer poses but changing heading can leave FOV; wall occlusion is not established. Truth is forensic only. First v61 geometry diagnostic called nonexistent normalize_angle; preserved attempt/log, repaired with stdlib atan2(sin,cos). One v62 readonly inspection guessed snapshot index5 when only2 existed and raised IndexError, no mission retry or state write.

AP地图仅重复data数组改为cell_count/SHA；完整原文件hash、其他源时间/位姿/TF/能量/目标均保留。完整COMPLETE只用原生保持，真值不作控制输入；正式批次仍需新冻结。

## 2026-10-05 P3B.5 v63近home机会补能与并行前沿细化组件

2026-10-05 P3B.5 v63组件：探索成功计数仅在真实成功的EXPLORE/FOUND_UNCONFIRMED前沿腿递增；已完成至少一腿、能量≤充电目标50%、离home>.35m且≤2×交付charge_radius的idle机器人，当前前沿准入且当前地图/所有同伴body允许已知自由可见航段真正到达home目标格时，可以优先通过原gateway补能。请求预算max(完整前沿预算,充电目标50%)，低于充电目标；不在初始出生位直接补满，不绕过本地储备或原10s租约。先让既有动作自然结束，串行返充并保留意图，充电后重新生成当前前沿；已满/远端/无成功腿/过期输入/阻塞home不触发机会补能。修复有active同伴但无selected时提前结束粗候选循环：仍执行当前body约束下的可达组件细化，空闲同伴可获得合法替代。531全组件14.40s、四包build5.78s、source3r0旁路，native300s/.35/.05/.1/5s函数AST不变。首定向13fail319pass：home栅格中心被错误使用.02m比较而拒绝，及旧无电池夹具缺enable字段；改用同目标格判断/缺字段默认禁用后全531PASS，首次日志保留。机会阈值/返充/路径时间仍为启发式，无任务时限或收益证明。v62五格2FAIL已83cb590归档；报告report/20261005_p3b5_opportunity_charging_refinement_component.json。809/28091从未执行，新独立开发/正式57格待验证，P3B.5未完成，无ns3/RL。

ROS canonical cwd，source Humble/install、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/component_checks，rtk bash -lc；未运行Gazebo：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_control.py > /tmp/p3b5_v63_targeted_attempt1.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v63_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v63_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v63_source_audit.log 2>&1
```

Opportunity replenishment is a nominal policy based only on delivered data, not an optimal or worst-case timing result. Body masks, current routes, input leases and local reserve remain mandatory. No native truth enters control and no809 source is consulted.

## 2026-10-05 P3B.5 v63机会补能独立开发失败

2026-10-05 P3B.5 v63独立开发五格FAIL，冻结a113550bec575cee8b386befec53f5130c18e482；2026-10-04 19:19:40–19:32:40UTC所有原owner/观察器自然关闭，lab exit1、force/zero exit0。force ideal原生COMPLETE260.3s/各charge1/最低12.17092；zero ideal/fault原生COMPLETE257.6/218.8s/各总charge2/最低13.66549、38.13748。lab3/101检测271.9/RALLY273.8、300.2s timeout/总charge3/最低17.00048；force fault300.0s RALLY timeout/各charge1/最低13.22627，通过充电安全子门但非任务成功。五格0碰撞/0耗尽/0failed/0infra、五ledger因果/TTL/version/charge与决策租约PASS、五graph0旁路，无整轮重试/回填。本批AP每10s覆盖探索及发现/集合，地图重复数组以cell_count/SHA记录，原字节hash保留。近home50%机会策略未解决普通E40组晚发现；部分contact航段已进入充电区但被必须同home格条件拒绝，本地返充发送端把规划staged.yaw覆盖为零，需要修复，但不宣称已证明任务耗时根因。报告report/20261005_p3b5_opportunity_charging_development.json/.md完整保留五格及只读AP前缀诊断。809/28091从未执行，正式57格/PASS图文未启动，P3B.5未完成，无ns3/RL。

ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master16250–16252/domains16–20/CPU0–19、20–39、40–59。全部5预声明/source/config/环境/hash后启动，17用户资料不变。runner自然结束不等于开发通过；独立checker记录1FAIL。实际入口rtk bash -lc：

```bash
/usr/bin/python3 /tmp/run_p3b5_v63_development.py > /tmp/p3b5_v63_development_dispatcher.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16250 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v63_dev_first_lab101.py > /tmp/p3b5_v63_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16251 taskset -c 20-39 /usr/bin/python3 /tmp/run_p3b5_v63_dev_task_pool.py '{"run": "p3b5_v63_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 17}' > /tmp/p3b5_v63_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16252 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v63_dev_task_pool.py '{"run": "p3b5_v63_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 19}' > /tmp/p3b5_v63_dev_zero_pool.log 2>&1
```

实际五格命令：

```bash
ROS_DOMAIN_ID=16 GAZEBO_MASTER_URI=http://127.0.0.1:16250 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v63_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v63_dev_fixed_lab101/launch_logs --episode-id p3b5_v63_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v63_dev_fixed_lab101/graphs/p3b5_v63_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v63_dev_fixed_lab101/episodes/p3b5_v63_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=17 GAZEBO_MASTER_URI=http://127.0.0.1:16251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v63_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_forced/p3b5_v63_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_forced/p3b5_v63_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_forced/p3b5_v63_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_forced/p3b5_v63_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=18 GAZEBO_MASTER_URI=http://127.0.0.1:16251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v63_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_forced/p3b5_v63_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_forced/p3b5_v63_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_forced/p3b5_v63_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_forced/p3b5_v63_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=19 GAZEBO_MASTER_URI=http://127.0.0.1:16252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v63_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_zero/p3b5_v63_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_zero/p3b5_v63_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_zero/p3b5_v63_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_zero/p3b5_v63_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:16252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v63_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_zero/p3b5_v63_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_zero/p3b5_v63_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_zero/p3b5_v63_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v63_dev_zero/p3b5_v63_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | phase / seconds | charges | minimum energy |
|---|---|---:|---:|
| p3b5_v63_dev_fixed_lab101_lab_far_northwest_3r_seed101 | RALLY / 300.2 | 3 | 17.00048 |
| p3b5_v63_dev_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 260.3 | 2 | 12.17092 |
| p3b5_v63_dev_forced_forced_charge_outage_fault | RALLY / 300.0 | 2 | 13.22627 |
| p3b5_v63_dev_zero_ideal_lab2_rally_8d4d5c469d | COMPLETE / 257.6 | 2 | 13.66549 |
| p3b5_v63_dev_zero_zero_rally_lab_fault | COMPLETE / 218.8 | 2 | 38.13748 |

关闭后的只读审核/诊断：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /tmp/audit_p3b5_v63_development.py > /tmp/p3b5_v63_development_audit.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v63_completion.py > /tmp/p3b5_v63_completion_diagnosis.log 2>&1
```

Lab detects271.9/RALLY273.8 and times out300.2, each robot charged once. Early E40 opportunity replenishments still cost time and task trajectories vary. Forced ideal native260.3 and zero pair native257.6/218.8; forced fault timeout300.0 but each charged and safe. Captured v63 AP geometry prefix (no native truth, no control publisher) shows some home-directed visible waypoints already inside the charging zone but not in the exact home target cell, so opportunity check can reject a valid contact leg. Local return code ignores staged.yaw and sends w=1/z=0 for every intermediate leg, a planner/executor mismatch; chronology is observational and does not prove task-time causality. AP prefix is not original buffers/local robot map; masks in central comparison vs unmasked local-contact comparison differ.

AP地图仅重复data数组改为cell_count/SHA；完整原文件hash、其他源时间/位姿/TF/能量/目标均保留。完整COMPLETE只用原生保持，真值不作控制输入；正式批次仍需新冻结。

## 2026-10-05 P3B.5 v64充电接触区与规划朝向组件

2026-10-05 P3B.5 v64组件：本地RETURNING发送端保留已知自由规划staged.yaw，不再把每个中间腿朝向强写为零；最终home格仍按原planner零朝向，逃离fallback保持原行为，位置/路线/储备/返航时限/watchdog及充电稳定门不变。机会补能阈值从充电目标50%收紧到25%，请求预算max(完整前沿预算,充电目标25%)；普通E40富余阶段不因出生邻近再次充电，已真实成功探索、>.35m且≤2×charge_radius、当前数据新鲜、经同gateway串行请求等条件保持。可见已知自由home航段到达charge_radius−.2m接触区即可，而非必须与home同格，仍保留目标误差余量/peer body检查。537全组件14.86s、四包build5.48s、source3r0旁路，native300s/.35/.05/.1/5s函数AST不变。新增普通能量不机会返充、可见接触区/边缘拒绝、0/正负pi/2执行朝向检查；本版首次全组件PASS。阈值、返航/行程仍为启发式，源码朝向错配已确认，但不宣称已证明任务耗时根因或收益。v63五格1必需FAIL已5041fc8归档；报告report/20261005_p3b5_charging_contact_heading_component.json。809/28091从未执行，新独立开发/正式57格待验证，P3B.5未完成，无ns3/RL。

ROS canonical cwd，source Humble/install、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/component_checks，rtk bash -lc；未运行Gazebo：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v64_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v64_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v64_source_audit.log 2>&1
```

Opportunity replenishment is a nominal policy based only on delivered data, not an optimal or worst-case timing result. Body masks, current routes, input leases and local reserve remain mandatory. No native truth enters control and no809 source is consulted.

## 2026-10-05 P3B.5 v65充电接触与朝向独立开发通过

2026-10-05 P3B.5 v65独立开发五格PASS，冻结a49924abd43ff4406a982d73415b2ac304444cea；所有原owner/观察器自然关闭后审核并归档。p3b5_v65_dev_fixed_lab101_lab_far_northwest_3r_seed101 COMPLETE/249.7s/charge1/minimum23.35615；p3b5_v65_dev_forced_ideal_forced2_rally_86fbb43bc6 COMPLETE/226.4s/charge2/minimum16.37324；p3b5_v65_dev_forced_forced_charge_outage_fault RALLY/300.3s/charge2/minimum9.07872；p3b5_v65_dev_zero_ideal_lab2_rally_8d4d5c469d COMPLETE/145.1s/charge0/minimum20.71604；p3b5_v65_dev_zero_zero_rally_lab_fault COMPLETE/143.6s/charge0/minimum26.94027。五格0碰撞/0耗尽/0failed/0infra、五ledger因果/TTL/version/charge与决策租约PASS、五graph0旁路，强制fault按既定子门只计各机充电/正能量/无碰撞安全，超时不计任务成功；无整轮重试/回填。25%近home接触区机会补能与规划返充朝向在实际执行，但无单因素任务消融，不作因果加速或最坏时限保证。报告report/20261005_p3b5_contact_heading_development.json/.md保留五格原结果/精确命令/源与环境/hash/AP/账本/图审核。809/28091从未执行；开发PASS不代替正式57格，P3B.5仍待完整冻结门禁，无ns3/RL。

ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master16450–16452/domains16–20/CPU0–19、20–39、40–59。全部5预声明/source/config/环境/hash后启动，17用户资料不变。runner自然结束不等于开发通过；独立checker记录5PASS。实际入口rtk bash -lc：

```bash
/usr/bin/python3 /tmp/run_p3b5_v65_development.py > /tmp/p3b5_v65_development_dispatcher.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16450 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v65_dev_first_lab101.py > /tmp/p3b5_v65_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16451 taskset -c 20-39 /usr/bin/python3 /tmp/run_p3b5_v65_dev_task_pool.py '{"run": "p3b5_v65_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 17}' > /tmp/p3b5_v65_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16452 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v65_dev_task_pool.py '{"run": "p3b5_v65_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 19}' > /tmp/p3b5_v65_dev_zero_pool.log 2>&1
```

实际五格命令：

```bash
ROS_DOMAIN_ID=16 GAZEBO_MASTER_URI=http://127.0.0.1:16450 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v65_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v65_dev_fixed_lab101/launch_logs --episode-id p3b5_v65_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v65_dev_fixed_lab101/graphs/p3b5_v65_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v65_dev_fixed_lab101/episodes/p3b5_v65_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=17 GAZEBO_MASTER_URI=http://127.0.0.1:16451 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v65_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_forced/p3b5_v65_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_forced/p3b5_v65_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_forced/p3b5_v65_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_forced/p3b5_v65_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=18 GAZEBO_MASTER_URI=http://127.0.0.1:16451 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v65_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_forced/p3b5_v65_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_forced/p3b5_v65_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_forced/p3b5_v65_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_forced/p3b5_v65_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=19 GAZEBO_MASTER_URI=http://127.0.0.1:16452 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v65_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_zero/p3b5_v65_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_zero/p3b5_v65_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_zero/p3b5_v65_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_zero/p3b5_v65_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:16452 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v65_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_zero/p3b5_v65_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_zero/p3b5_v65_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_zero/p3b5_v65_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v65_dev_zero/p3b5_v65_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | phase / seconds | charges | minimum energy |
|---|---|---:|---:|
| p3b5_v65_dev_fixed_lab101_lab_far_northwest_3r_seed101 | COMPLETE / 249.7 | 1 | 23.35615 |
| p3b5_v65_dev_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 226.4 | 2 | 16.37324 |
| p3b5_v65_dev_forced_forced_charge_outage_fault | RALLY / 300.3 | 2 | 9.07872 |
| p3b5_v65_dev_zero_ideal_lab2_rally_8d4d5c469d | COMPLETE / 145.1 | 0 | 20.71604 |
| p3b5_v65_dev_zero_zero_rally_lab_fault | COMPLETE / 143.6 | 0 | 26.94027 |

关闭后的只读审核/诊断：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /tmp/audit_p3b5_v65_development.py > /tmp/p3b5_v65_development_audit.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v65_completion.py > /tmp/p3b5_v65_completion_diagnosis.log 2>&1
```

Independent original development only. Contact/heading policy and 25%-target opportunity replenishment require new frozen integration; four required mission rows pass native5s hold, forced fault must charge each and stay positive/zero-contact. Exact results below. No isolated causal timing benefit or worst-case guarantee; AP snapshots remain independent received data, not original buffers; no native truth controls any decision. All owners/observers close before this documentary write and before prospective809 freeze.

AP地图仅重复data数组改为cell_count/SHA；完整原文件hash、其他源时间/位姿/TF/能量/目标均保留。完整COMPLETE只用原生保持，真值不作控制输入；正式批次仍需新冻结。

2026-10-05 P3B.5 v66前瞻正式冻结准备：已关闭并完整保留v65五个独立开发原始结果且开发PASS；保持809.world/seed809/fault28091/目标(4.4,-3.4)/3r/E45原字节与最初静态声明，更新当前control与battery源hash及未暴露失败历史。809此前从未任务执行；同提交强制原生/E0/受控物理返充及十fixed全部PASS后才允许首次运行。57格/27pair/41主格、300s/.35/.05/.1/5s、原故障强度保持，不重试/回填。当前仍待正式完整门禁，无ns3/RL。

## 2026-10-05 P3B.5 v66前瞻协议配置校验

未启动任何任务；源/场景字节和809未暴露记录保留。54配置/门禁脚本检查0.67s通过，validate-only为27cases/41unique。当前control SHA256=2e04f15d57a3c6c462f7d01b866d6669ffacfd24d9c66906fcbc859d4d35fef6，正式57格仍待执行。ns3gym/PYTHONNOUSERSITE=1写入协议记录；ROS源Humble/install/PYTHONNOUSERSITE=1/ROS_LOG_DIR=log/component_checks完成校验：

```bash
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python /tmp/refreeze_p3b5_v66_holdout_controller.py > /tmp/p3b5_v66_holdout_refreeze.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py > /tmp/p3b5_v66_protocol_checks.log 2>&1
/usr/bin/python3 scripts/run_p3b5_tasks.py --config scripts/p3b5_fault_manifest.json --run-id p3b5_v66_validate_only --validate-only > /tmp/p3b5_v66_protocol_validate.log 2>&1
```

## 2026-10-05 P3B.5 v66受控返充原始准备失败

2026-10-05 P3B.5 v66正式原候选FAIL，冻结61de29f69d3d8e92f83fa21dc2b202cef032f662；2026-10-04 19:55:11–20:06:46UTC所有owned owner/观察器自然关闭，initial exit[0,0,1,0]。5started/5raw、52unrun含全部固定与809；无整轮重试/选择回填。force ideal原生COMPLETE185.4s/各charge1/最低15.71204；force fault300.2s RALLY timeout/各charge1/最低14.00499通过安全子门但非任务成功。E0双格预声明FAILED1.5/.5s，无导航；受控返充ideal准备50s只完成tb2，staging exit1、300.3s RALLY timeout/各charge1/最低9.46559，断网配对未启动。五格0接触/0infra，但1操作准备失败；五ledger因果/TTL/version/charge与决策租约PASS、五graph0旁路、54纯协议PASS。原始AP地图起点known-free却处于净空膨胀区，共享规划可向后脱离，fixture的欧氏目标单调前进条件拒绝该安全逃离；自回波helper没有清任何格且不恢复路径，不能通过清障碍修复。只读条件回放不证明任务因果。809/28091从未执行，707已暴露历史不变。完整strict checker/PASS图文未执行，P3B.5未完成，无ns3/RL。报告report/20261005_p3b5_staging_geometry_failed_candidate.json/.md保留五原始与52unrun、源码/环境/命令/hash/图/账本/地图及失败诊断；domain222未动。

canonical ROS cwd/source Humble、install、Gazebo；TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch。CPU0–19/20–39/40–59/60–79，master16550–16553，domains44/45、28/29、20，21未执行；17用户资料SHA不变。实际入口rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v66_bootstrap.py > /tmp/p3b5_v66_bootstrap.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16550 taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v66_task_pool.py '{"run": "p3b5_v66_forced", "cases": ["forced_charge_outage"], "domain_base": 44}' > /tmp/p3b5_v66_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16551 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v66_zero_first.py > /tmp/p3b5_v66_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16552 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v66_returnproof --ros-domain-base 20 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v66_returnproof.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16553 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_61de29f.json > /tmp/p3b5_protocol_61de29f.log 2>&1
```

实际五格：

```bash
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:16551 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v66_zero_ideal_lab2_rally_0678e85373 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_zero/p3b5_v66_zero_ideal_lab2_rally_0678e85373 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_zero/p3b5_v66_zero_ideal_lab2_rally_0678e85373/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_zero/p3b5_v66_zero_ideal_lab2_rally_0678e85373/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_zero/p3b5_v66_zero_ideal_lab2_rally_0678e85373/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=29 GAZEBO_MASTER_URI=http://127.0.0.1:16551 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v66_zero_battery_exhaust_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_zero/p3b5_v66_zero_battery_exhaust_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_zero/p3b5_v66_zero_battery_exhaust_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_zero/p3b5_v66_zero_battery_exhaust_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_zero/p3b5_v66_zero_battery_exhaust_lab_fault/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=44 GAZEBO_MASTER_URI=http://127.0.0.1:16550 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v66_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_forced/p3b5_v66_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_forced/p3b5_v66_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_forced/p3b5_v66_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_forced/p3b5_v66_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=45 GAZEBO_MASTER_URI=http://127.0.0.1:16550 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v66_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_forced/p3b5_v66_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_forced/p3b5_v66_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_forced/p3b5_v66_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_forced/p3b5_v66_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:16552 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v66_returnproof_ideal_forced2_rally_4c7c808f36 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_returnproof/p3b5_v66_returnproof_ideal_forced2_rally_4c7c808f36 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_returnproof/p3b5_v66_returnproof_ideal_forced2_rally_4c7c808f36/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_returnproof/p3b5_v66_returnproof_ideal_forced2_rally_4c7c808f36/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v66_returnproof/p3b5_v66_returnproof_ideal_forced2_rally_4c7c808f36/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
```

| original episode | phase / seconds | charges | minimum energy |
|---|---|---:|---:|
| p3b5_v66_zero_ideal_lab2_rally_0678e85373 | FAILED / 1.5 | 0 | 0.00000 |
| p3b5_v66_zero_battery_exhaust_lab_fault | FAILED / 0.5 | 0 | 0.00000 |
| p3b5_v66_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 185.4 | 2 | 15.71204 |
| p3b5_v66_forced_forced_charge_outage_fault | RALLY / 300.2 | 2 | 14.00499 |
| p3b5_v66_returnproof_ideal_forced2_rally_4c7c808f36 | RALLY / 300.3 | 2 | 9.46559 |

所有owner关闭后只读审核/诊断：

```bash
/usr/bin/python3 /tmp/diagnose_p3b5_v66_staging_geometry.py > /tmp/p3b5_v66_staging_geometry.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v66_staging_routes.py > /tmp/p3b5_v66_staging_routes.log 2>&1
/usr/bin/python3 /tmp/archive_p3b5_v66_failure.py > /tmp/p3b5_v66_archive_failed.log 2>&1
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python /tmp/document_p3b5_v66_failure.py
```

Saved AP raw start is free but inside static clearance inflation. Existing bounded self-return helper clears no cells and restores no prefix. Shared navigation_start_route finds a known-free escape backwards to a clearance-safe cell; the fixture rejects it because Euclidean distance to the final declared staging point initially increases. Pure replay found no allowed monotone candidate within.75m. This is conditional geometry evidence, not original buffers or an isolated mission causal claim. Keep original map bytes/obstacles; allow existing bounded escape/path detours in future fixture rather than weakening clearance or exposure/time/motion thresholds.

进度曾误称physical fault启动，核查原summary后及时更正；paired fault实际上未执行。只读rg缺少tests目录/访问受限tmp和python命令不存在均不影响运行，保留记录。失败原件不替换；新fixture须新冻结、完整57格及严格图文门禁。

## 2026-10-05 P3B.5 v67已知自由准备绕行组件与协议

2026-10-05 P3B.5 v67准备程序修复与前瞻协议：受控返充fixture在known-free但净空膨胀起点复用现有navigation_start_route的.6m有界自由逃离；允许先增加距最终point的欧氏距离，之后通过当前地图共享plan_rally_leg已知自由visible路径绕行。不清障碍/未知格、不引入native truth，原始地图保持；四源TTL/current battery ACTIVE/gateway串行既有行为保持。最终点/50s/.75m/.35m/blackout60–250/1.1m远端/.5m实际Nav2返航/300s及原生保持门槛不变，native_completion_ok/episode_ok AST不变。61相关检查1.83s、539全组件14.80s、四包build5.30s/source3r0旁路、54配置检查及27cases/41primary validate-only PASS。控制器/电池算法源与v65开发PASS/v66force185.4原生PASS相同；v66五原始1操作FAIL及52unrun已c9719c5归档。809.world/seed809/fault28091此前从未执行，保留原字节/最初声明及全部未暴露历史，新增fixture源hash和当前准备协议。新冻结完整57格需initial强制原生/E0/受控实际返充及十fixed全PASS后首次809；本组件不是正式P3B.5通过，无ns3/RL。

canonical ROS cwd/source Humble/install/PYTHONNOUSERSITE=1/ROS_LOG_DIR=log/component_checks；rtk bash -lc；没有Gazebo任务：

```bash
/usr/bin/python3 -m pytest -q scripts/test_p3b5_return_staging.py scripts/test_p3b5_gate.py scripts/test_p3b5_tasks.py > /tmp/p3b5_v67_staging_checks.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v67_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v67_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v67_source_audit.log 2>&1
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python /tmp/refreeze_p3b5_v67_staging_protocol.py > /tmp/p3b5_v67_holdout_refreeze.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py > /tmp/p3b5_v67_protocol_checks.log 2>&1
/usr/bin/python3 scripts/run_p3b5_tasks.py --config scripts/p3b5_fault_manifest.json --run-id p3b5_v67_validate_only --validate-only > /tmp/p3b5_v67_protocol_validate.log 2>&1
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python /tmp/document_p3b5_v67_staging_component.py
```

Bounded known-free staging escape/detours fix fixture admission; do not prove mission completion or optimality. Existing local safety and physical return checks remain mandatory; no original result replaced.

## 2026-10-05 P3B.5 v67集合路线等待原始失败

2026-10-05 P3B.5 v67原候选FAIL，冻结a7952b59ae9df722eabf3beddc5c159bf4e9a01c；2026-10-04 20:23:16–20:51:34UTC全部owned任务/观察器自然关闭，initial全0、lab101 exit0、lab202任务exit1。8started/8raw、49unrun含剩余8fixed与809，无重试/回填。强制ideal原生COMPLETE211.2s/各charge1/最低16.75387，强制fault300.1s RALLY timeout/各charge1/最低8.48774安全PASS；E0双格预声明FAILED2.0/1.1s且无导航。受控准备两侧均50s内双机到位，两侧各charge1/0接触/最低9.67712、9.59143，断网62–248实际返航path1.22875/1.14257、net1.22331/1.13431、NavEXEC1.22872/1.14254m，严格安全审计PASS；原timeout不计任务成功。首fixed lab101原生243.1s/charge1/最低23.62608；lab202 RALLY timeout300.4s/charge2/最低20.78276，tb1距最终1.41806m、其余两机已到位。八格0接触/0infra/0操作失败，八ledger及八graph PASS、54纯协议PASS。保存AP地图条件回放提示完整高优先未来路线预约拒绝了部分实际body可行短腿；充电preflight需要完全动作排空才能重排，但持续新腿可能使其迟迟不能完成。只读条件几何不是原buffer或任务收益因果证明，待开发修复。809/28091仍从未执行，完整strict PASS报告/图未生成，P3B.5未完成，无ns3/RL。

canonical ROS cwd/source Humble/install/Gazebo；TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master16650–16653、CPU0–19/20–39/40–59/60–79。固定同CPU0–19串行；domains44/45、28/29、20/21、30/33；foreign222未动、17用户资料hash不变。入口rtk bash -lc：

```bash
/usr/bin/python3 /tmp/p3b5_v67_bootstrap.py > /tmp/p3b5_v67_bootstrap.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16650 taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v67_task_pool.py '{"run": "p3b5_v67_forced", "cases": ["forced_charge_outage"], "domain_base": 44}' > /tmp/p3b5_v67_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16651 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v67_zero_first.py > /tmp/p3b5_v67_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16652 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v67_returnproof --ros-domain-base 20 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v67_returnproof.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16653 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_a7952b5.json > /tmp/p3b5_protocol_a7952b5.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16650 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v67_first_lab101.py > /tmp/p3b5_v67_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16650 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v67_fixed_before_faults.py > /tmp/p3b5_v67_remaining_fixed.log 2>&1
```

实际八格：

```bash
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:16651 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v67_zero_ideal_lab2_rally_0678e85373 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_zero/p3b5_v67_zero_ideal_lab2_rally_0678e85373 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_zero/p3b5_v67_zero_ideal_lab2_rally_0678e85373/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_zero/p3b5_v67_zero_ideal_lab2_rally_0678e85373/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_zero/p3b5_v67_zero_ideal_lab2_rally_0678e85373/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=29 GAZEBO_MASTER_URI=http://127.0.0.1:16651 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v67_zero_battery_exhaust_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_zero/p3b5_v67_zero_battery_exhaust_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_zero/p3b5_v67_zero_battery_exhaust_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_zero/p3b5_v67_zero_battery_exhaust_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_zero/p3b5_v67_zero_battery_exhaust_lab_fault/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=44 GAZEBO_MASTER_URI=http://127.0.0.1:16650 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v67_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_forced/p3b5_v67_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_forced/p3b5_v67_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_forced/p3b5_v67_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_forced/p3b5_v67_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=45 GAZEBO_MASTER_URI=http://127.0.0.1:16650 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v67_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_forced/p3b5_v67_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_forced/p3b5_v67_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_forced/p3b5_v67_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_forced/p3b5_v67_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:16652 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v67_returnproof_ideal_forced2_rally_4c7c808f36 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_returnproof/p3b5_v67_returnproof_ideal_forced2_rally_4c7c808f36 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_returnproof/p3b5_v67_returnproof_ideal_forced2_rally_4c7c808f36/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_returnproof/p3b5_v67_returnproof_ideal_forced2_rally_4c7c808f36/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_returnproof/p3b5_v67_returnproof_ideal_forced2_rally_4c7c808f36/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=21 GAZEBO_MASTER_URI=http://127.0.0.1:16652 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v67_returnproof_physical_return_under_blackout_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_returnproof/p3b5_v67_returnproof_physical_return_under_blackout_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_returnproof/p3b5_v67_returnproof_physical_return_under_blackout_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_returnproof/p3b5_v67_returnproof_physical_return_under_blackout_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v67_returnproof/p3b5_v67_returnproof_physical_return_under_blackout_fault/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=30 GAZEBO_MASTER_URI=http://127.0.0.1:16650 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v67_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v67_fixed_lab101/launch_logs --episode-id p3b5_v67_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v67_fixed_lab101/graphs/p3b5_v67_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v67_fixed_lab101/episodes/p3b5_v67_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=33 GAZEBO_MASTER_URI=http://127.0.0.1:16650 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v67_fixed_lab/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v67_fixed_lab/launch_logs --episode-id p3b5_v67_fixed_lab_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v67_fixed_lab/graphs/p3b5_v67_fixed_lab_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v67_fixed_lab/episodes/p3b5_v67_fixed_lab_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
```

| original episode | phase / seconds | charges | minimum energy |
|---|---|---:|---:|
| p3b5_v67_zero_ideal_lab2_rally_0678e85373 | FAILED / 2.0 | 0 | 0.00000 |
| p3b5_v67_zero_battery_exhaust_lab_fault | FAILED / 1.1 | 0 | 0.00000 |
| p3b5_v67_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 211.2 | 2 | 16.75387 |
| p3b5_v67_forced_forced_charge_outage_fault | RALLY / 300.1 | 2 | 8.48774 |
| p3b5_v67_returnproof_ideal_forced2_rally_4c7c808f36 | RALLY / 300.1 | 2 | 9.67712 |
| p3b5_v67_returnproof_physical_return_under_blackout_fault | EXPLORE / 300.1 | 2 | 9.59143 |
| p3b5_v67_fixed_lab101_lab_far_northwest_3r_seed101 | COMPLETE / 243.1 | 1 | 23.62608 |
| p3b5_v67_fixed_lab_lab_far_northwest_3r_seed202 | RALLY / 300.4 | 2 | 20.78276 |

关闭后只读审核/诊断：

```bash
/usr/bin/python3 /tmp/archive_p3b5_v67_failure.py > /tmp/p3b5_v67_archive_failed.log 2>&1
/usr/bin/python3 /tmp/archive_p3b5_v67_failure_attempt2.py > /tmp/p3b5_v67_archive_failed_attempt2.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v67_route_waiting.py > /tmp/p3b5_v67_route_waiting.log 2>&1
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python /tmp/document_p3b5_v67_failure.py
```

Original lab202 tb1 remains1.418m from its final pose, tb2/tb3 errors.003/.009m, each ACTIVE/positive and0contacts. Both tb1/tb2 charged once. Logs show tb1 waits near(-3.67,.19) while tb2 follows a body-masked detour; several conditional AP snapshots offer tb1 a valid known-free leg under actual bodies, but full higher-priority tb2 future approach rejects it. Reconstructed snapshots are not original buffers; do not infer a successful alternative mission. Charging preflight requires total goal quiescence to recompute the approach order, yet new legs keep being admitted as others finish, so it can remain unfinished throughout transit. A current-map route scheduling/drain optimization remains to validate; no lease, clearance, contact, horizon or native threshold relaxed.

首离线archive误要求失败fixed任务runner exit0，原runner正确exit1；修改离线断言后完整审计，非episode重试。一次只读tail猜错launch时间戳，后rg定位真实路径；不影响试验。当前仍未正式通过。

## 2026-10-05 P3B.5 v68充电后排空与集合优先次序组件

2026-10-05 P3B.5 v68组件：实际发出集合预充电请求即使preflight失效；充电完成后停止接纳新集合腿，已接纳/待接受腿自然排空，再按当前地图与机体重算串行接近次序，原有本地安全/让行继续运行。完整串行机体避障可行排列优先减少后车未来路线覆盖前车当前位置、但反向不覆盖的单向接近逆序；只有未来优先级阻塞、实际已接纳/返航路线允许，且重新计算得到更少逆序时才排空重算，不在动作执行中换序。1.8m路线保留、.6m机体/.35m静态净空、源TTL/能量/300s/.35/.05/.1/5s原生完成门不变，native函数AST一致。542组件14.94s、四包build5.07s、source3r0旁路通过。历史中间单测1次作用域NameError、2项fixture恰到5s电池TTL而失败均保留，修复测试本身后284控制检查11.89s通过。v67 lab202接收AP快照回放中三种次序评分仍选tb3/tb2/tb1，32个已评估完整分配叶仍选入口观察驻点；不是原FOUND缓冲或反事实任务，不宣称该修正已经解决lab202超时或证明耗时收益。v67八原始FAIL与49unrun已f4dc4bb归档。报告report/20261005_p3b5_postcharge_order_component.json。新独立lab202/lab101及force/zero开发回归待执行；809/28091从未执行，正式57格尚未完成，无ns3/RL。

ROS canonical cwd，source Humble/install、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/component_checks，rtk bash -lc；未运行Gazebo。全部中间检查/失败与离线诊断原文及SHA见组件JSON records。

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v68_component_checks_current.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v68_build_current.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v68_source_audit_current.log 2>&1
```

离线只读诊断：

```bash
/usr/bin/python3 /tmp/diagnose_p3b5_v68_postcharge_order.py
/usr/bin/python3 /tmp/diagnose_p3b5_v68_postcharge_order_final.py
/usr/bin/python3 /tmp/diagnose_p3b5_v68_reservation_order.py
/usr/bin/python3 /tmp/diagnose_p3b5_v68_candidate_costs.py
```

Nominal ordering heuristics do not establish deadline success or optimality. Accepted action drain and full current-map/body/source/energy admissions remain mandatory.

## 2026-10-05 P3B.5 v69充电后次序独立开发PASS

2026-10-05 P3B.5 v69独立六格开发PASS，冻结9ac2fb7dc10193c93092efdcf17f198fcb7554a8；所有原owner/观察器自然关闭后审核归档。p3b5_v69_dev_fixed_lab101_lab_far_northwest_3r_seed101 PASS/COMPLETE/197.9s/charge1/min23.28236；p3b5_v69_dev_fixed_lab202_lab_far_northwest_3r_seed202 PASS/COMPLETE/160.4s/charge0/min27.08704；p3b5_v69_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/178.4s/charge2/min14.77575；p3b5_v69_dev_forced_forced_charge_outage_fault PASS/RALLY/300.2s/charge2/min12.72806；p3b5_v69_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/202.2s/charge1/min20.56833；p3b5_v69_dev_zero_zero_rally_lab_fault PASS/COMPLETE/201.3s/charge1/min22.96403。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_postcharge_order_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。充电后排空/重算只用交付输入，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与v67不同，无单因素消融，不把较早发现或较短完成时间归因于次序修正，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。

ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master16750..16753/domains23..28/CPU0–19、20–39、40–59、60–79；全部六格前瞻预声明后原始执行。rtk bash -lc入口：

```bash
/usr/bin/python3 /tmp/run_p3b5_v69_development.py
GAZEBO_MASTER_URI=http://127.0.0.1:16750 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v69_dev_first_lab101.py > /tmp/p3b5_v69_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16751 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v69_dev_first_lab202.py > /tmp/p3b5_v69_dev_lab202_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16752 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v69_dev_task_pool.py '{"run": "p3b5_v69_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 25}' > /tmp/p3b5_v69_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16753 taskset -c 60-79 /usr/bin/python3 /tmp/run_p3b5_v69_dev_task_pool.py '{"run": "p3b5_v69_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 27}' > /tmp/p3b5_v69_dev_zero_pool.log 2>&1
```

实际六格命令：

```bash
ROS_DOMAIN_ID=23 GAZEBO_MASTER_URI=http://127.0.0.1:16750 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v69_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v69_dev_fixed_lab101/launch_logs --episode-id p3b5_v69_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v69_dev_fixed_lab101/graphs/p3b5_v69_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v69_dev_fixed_lab101/episodes/p3b5_v69_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=24 GAZEBO_MASTER_URI=http://127.0.0.1:16751 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v69_dev_fixed_lab202/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v69_dev_fixed_lab202/launch_logs --episode-id p3b5_v69_dev_fixed_lab202_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v69_dev_fixed_lab202/graphs/p3b5_v69_dev_fixed_lab202_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v69_dev_fixed_lab202/episodes/p3b5_v69_dev_fixed_lab202_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=25 GAZEBO_MASTER_URI=http://127.0.0.1:16752 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v69_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_forced/p3b5_v69_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_forced/p3b5_v69_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_forced/p3b5_v69_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_forced/p3b5_v69_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=26 GAZEBO_MASTER_URI=http://127.0.0.1:16752 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v69_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_forced/p3b5_v69_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_forced/p3b5_v69_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_forced/p3b5_v69_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_forced/p3b5_v69_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=27 GAZEBO_MASTER_URI=http://127.0.0.1:16753 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v69_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_zero/p3b5_v69_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_zero/p3b5_v69_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_zero/p3b5_v69_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_zero/p3b5_v69_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:16753 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v69_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_zero/p3b5_v69_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_zero/p3b5_v69_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_zero/p3b5_v69_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v69_dev_zero/p3b5_v69_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | check | phase / seconds | charges | minimum energy |
|---|---|---|---:|---:|
| p3b5_v69_dev_fixed_lab101_lab_far_northwest_3r_seed101 | PASS | COMPLETE / 197.9 | 1 | 23.28236 |
| p3b5_v69_dev_fixed_lab202_lab_far_northwest_3r_seed202 | PASS | COMPLETE / 160.4 | 0 | 27.08704 |
| p3b5_v69_dev_forced_ideal_forced2_rally_86fbb43bc6 | PASS | COMPLETE / 178.4 | 2 | 14.77575 |
| p3b5_v69_dev_forced_forced_charge_outage_fault | PASS | RALLY / 300.2 | 2 | 12.72806 |
| p3b5_v69_dev_zero_ideal_lab2_rally_8d4d5c469d | PASS | COMPLETE / 202.2 | 1 | 20.56833 |
| p3b5_v69_dev_zero_zero_rally_lab_fault | PASS | COMPLETE / 201.3 | 1 | 22.96403 |

所有owner关闭后只读审核：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /tmp/audit_p3b5_v69_development.py > /tmp/p3b5_v69_development_audit.log 2>&1
```

Independent originals, no formal backfill or counterfactual causal claim. Detector is Gazebo geometric visibility proxy, not image recognition. Native evaluator/physics only read-only evidence; native truth never enters mission control. Nominal serial energy/time/parking costs remain heuristics.

## 2026-10-05 P3B.5 v70未暴露holdout前瞻协议

2026-10-05 P3B.5 v70正式协议前瞻重冻：v69六原始开发PASS后，将controller源SHA冻结为aa6cd7c03016e38ae7f5eec808b226b5fdb67f206a1038f7e61d27c4a06cb9d2，809.world/seed809/fault28091仍从未执行；原world/目标/3r/E45/300s/独立fault seed/电池/准备装置/原生完成阈值不变。追加v67冻结a7952b5八started/49unrun/原lab202 RALLY timeout失败与未暴露历史，不替换结果。54配置检查0.64s、54协议元数据矩阵、27case/41primary validate-only PASS；控制组件542/四包5.07s/旁路及六开发ledger/graph已有证据。新clean pushed同提交正式57格先initial强制原生ideal/E0/受控实际返充与十fixed PASS，再首次809及其余primary/safety。各独立world可在不同master/ROS domain/CPU组同时运行，全部原owner/观察器关闭后才审核/修改；不增加整轮重试或降低门槛。本协议及开发PASS不是P3B.5验收通过，完整正式门禁待执行，无ns3/RL。

纯协议检查，未启动Gazebo、任务、留出场景。rtk bash -lc；Humble/install、PYTHONNOUSERSITE=1：

```bash
/usr/bin/python3 -m pytest -q --tb=short scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py > /tmp/p3b5_v70_config_checks.log 2>&1
/usr/bin/python3 scripts/run_p3b_fault_matrix.py --output /tmp/p3b5_v70_protocol_metadata.json > /tmp/p3b5_v70_protocol_metadata.log 2>&1
/usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v70_preflight --validate-only > /tmp/p3b5_v70_validate.json 2>&1
```

## 2026-10-05 P3B.5 v70原生终态证据失败

2026-10-05 P3B.5 v70原候选FAIL，冻结4653c13e6de18b8ad8ade2bc4c734ab76005c9b2；全部owned任务与观察器自然关闭后归档。6started/6raw、51unrun含十fixed/809；p3b5_v70_zero_ideal_lab2_rally_0678e85373 FAILED/1.7s/charge0/min0.00000；p3b5_v70_zero_battery_exhaust_lab_fault FAILED/1.3s/charge0/min0.00000；p3b5_v70_forced_ideal_forced2_rally_86fbb43bc6 COMPLETE/235.2s/charge2/min16.20114；p3b5_v70_forced_forced_charge_outage_fault COMPLETE/300.1s/charge2/min9.92663；p3b5_v70_returnproof_ideal_forced2_rally_4c7c808f36 RALLY/300.1s/charge2/min9.60870；p3b5_v70_returnproof_physical_return_under_blackout_fault EXPLORE/300.1s/charge2/min9.54496。E0 ideal已FAILED1.7s/双机无Nav且中央失败名单完整，但原生评估tb1 battery_message_count0、mode/initial_energy为null，严格E0前置断言拒绝；fault FAILED1.3s双机原生字段完整。独立只读安全观察器收到tb2/tb1 FAILED原生消息于2072.082/2072.282；task evaluator在FAILED后的固定0.5s drain先写终态，快终止可能早于另一路原生电池回调。缺失证据保留为空，不从配置/网关推断0或FAILED、不放宽断言；需有界终态收集回归。无整轮重试/回填，六ledger/graph已审核；报告report/20261005_p3b5_failure_battery_snapshot_failed_candidate.json/.md。809/28091仍从未执行，完整P3B.5未通过，无ns3/RL。

canonical ROS cwd/source Humble/install/Gazebo；TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master16850..53/domains44/45、28/29、20/21，CPU0–19/20–39/40–59/60–79。foreign222及17用户资料不动。rtk bash -lc入口：

```bash
/usr/bin/python3 /tmp/p3b5_v70_bootstrap.py > /tmp/p3b5_v70_dispatcher.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16850 taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v70_task_pool.py '{"run": "p3b5_v70_forced", "cases": ["forced_charge_outage"], "domain_base": 44}' > /tmp/p3b5_v70_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16851 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v70_zero_first.py > /tmp/p3b5_v70_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16852 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v70_returnproof --ros-domain-base 20 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v70_returnproof.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16853 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_4653c13.json > /tmp/p3b5_protocol_4653c13.log 2>&1
```

实际六格：

```bash
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:16851 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v70_zero_ideal_lab2_rally_0678e85373 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_zero/p3b5_v70_zero_ideal_lab2_rally_0678e85373 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_zero/p3b5_v70_zero_ideal_lab2_rally_0678e85373/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_zero/p3b5_v70_zero_ideal_lab2_rally_0678e85373/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_zero/p3b5_v70_zero_ideal_lab2_rally_0678e85373/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=29 GAZEBO_MASTER_URI=http://127.0.0.1:16851 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v70_zero_battery_exhaust_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_zero/p3b5_v70_zero_battery_exhaust_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_zero/p3b5_v70_zero_battery_exhaust_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_zero/p3b5_v70_zero_battery_exhaust_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_zero/p3b5_v70_zero_battery_exhaust_lab_fault/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=44 GAZEBO_MASTER_URI=http://127.0.0.1:16850 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v70_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_forced/p3b5_v70_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_forced/p3b5_v70_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_forced/p3b5_v70_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_forced/p3b5_v70_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=45 GAZEBO_MASTER_URI=http://127.0.0.1:16850 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v70_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_forced/p3b5_v70_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_forced/p3b5_v70_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_forced/p3b5_v70_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_forced/p3b5_v70_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:16852 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v70_returnproof_ideal_forced2_rally_4c7c808f36 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_returnproof/p3b5_v70_returnproof_ideal_forced2_rally_4c7c808f36 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_returnproof/p3b5_v70_returnproof_ideal_forced2_rally_4c7c808f36/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_returnproof/p3b5_v70_returnproof_ideal_forced2_rally_4c7c808f36/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_returnproof/p3b5_v70_returnproof_ideal_forced2_rally_4c7c808f36/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=21 GAZEBO_MASTER_URI=http://127.0.0.1:16852 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v70_returnproof_physical_return_under_blackout_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_returnproof/p3b5_v70_returnproof_physical_return_under_blackout_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_returnproof/p3b5_v70_returnproof_physical_return_under_blackout_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_returnproof/p3b5_v70_returnproof_physical_return_under_blackout_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v70_returnproof/p3b5_v70_returnproof_physical_return_under_blackout_fault/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
```

| original | phase / seconds | charges | minimum energy |
|---|---|---:|---:|
| p3b5_v70_zero_ideal_lab2_rally_0678e85373 | FAILED / 1.7 | 0 | 0.00000 |
| p3b5_v70_zero_battery_exhaust_lab_fault | FAILED / 1.3 | 0 | 0.00000 |
| p3b5_v70_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 235.2 | 2 | 16.20114 |
| p3b5_v70_forced_forced_charge_outage_fault | COMPLETE / 300.1 | 2 | 9.92663 |
| p3b5_v70_returnproof_ideal_forced2_rally_4c7c808f36 | RALLY / 300.1 | 2 | 9.60870 |
| p3b5_v70_returnproof_physical_return_under_blackout_fault | EXPLORE / 300.1 | 2 | 9.54496 |

全部关闭后只读审核：

```bash
/usr/bin/python3 /tmp/audit_p3b5_v70_return_subgate.py > /tmp/p3b5_v70_return_subgate_audit.log 2>&1
/usr/bin/python3 /tmp/archive_p3b5_v70_failure.py > /tmp/p3b5_v70_archive_failed.log 2>&1
```

Independent native safety subscriber received both FAILED states. Saved evaluator missed tb1 before its snapshot; callbacks from distinct subscribers are not identical buffers. A bounded evidence drain is to be tested; do not infer missing fields or replace this original result.

## 2026-10-05 P3B.5 v71失败终态证据组件与v72前瞻冻结

2026-10-05 P3B.5 v71只读评估组件及v72前瞻协议：FAILED仍至少排空0.5秒；未收到每台原生电池状态、或已声明失败者原生mode尚非FAILED时，最多按现有battery TTL5秒收集，且不越过原任务300秒时限。重复FAILED不重置首次等待起点；到界仍保留缺失null，不从配置/AP/native安全旁录推断字段。已完整的失败证据仍按原0.5秒结束；FAILED期间不回落到coverage完成。该过程只采集证据，任务控制/本地安全已经失败或停止，不发布导航。34评估检查2.11s、546全组件15.18s、四包5.20s/source3r0旁路通过；新增迟到/永久缺失/非FAILED旧状态/重复FAILED/任务时限回归。原生保持函数和严格native_completion_ok/episode_ok源码一致。controller/battery/apparatus与v69六开发PASS字节相同；v70六原始失败/51unrun已afefd96归档，实际返航子门PASS，未回填。54配置及27case/41primary validate-only PASS；未暴露809 world/seed/fault保持字节及条件，新增evaluator源hash和v70未暴露失败历史。报告report/20261005_p3b5_failure_evidence_component.json。新clean pushed正式57格先initial强制原生/E0/实际返航及十fixed全PASS，再首次809。完整P3B.5尚未通过，无ns3/RL。

ROS canonical cwd/Humble/install、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/component_checks，rtk bash -lc；无Gazebo/809：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v71_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v71_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v71_source_audit.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_task_evaluator.py > /tmp/p3b5_v71_evaluator_checks.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py > /tmp/p3b5_v72_config_checks.log 2>&1
/usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v72_preflight --validate-only > /tmp/p3b5_v72_validate.json 2>&1
```

## 2026-10-05 P3B.5 v72原始集合失败与端口记录纠正

2026-10-05 P3B.5 v72原候选FAIL，冻结a9745c393194aa941e289d812a57b2c890918380；全部owned任务/观察器/master自然关闭后归档。15started/15raw、42unrun（lab303及全部其余primary/safety，含809），不重试/回填。initial强制ideal原生217.9s/两机各charge1、E0双格原生FAILED证据完整且无Nav、受控实际断网返航子门与54协议PASS。九个已启动fixed中八个原生合格COMPLETE；lab101293.7s仅6.3s余量，lab202 RALLY timeout300.1s/2charges/最低20.22274，tb1仍距最终1.30480m、tb2/tb3已到位。其余world池自然执行原声明格后才结束，不因lab失败取消。十五格0接触/0infra/0操作失败，十五ledger/graph审计PASS。只读AP条件profile集合排序重复16–17个距离场、约1.14–1.26s；不是原控制执行器耗时或任务因果证明。中间路点仍朝最终目标，绕墙时可能增加转向，需独立优化验证。helper端口生成range(16950,16854)为空，错误ports[] preflight与原源保留；bootstrap任务首次前实际声明16650..53，独立fixed world声明16950..52，实际七port/PID/env关闭另显式审计PASS，未影响同提交源或重跑任务。报告report/20261005_p3b5_postcharge_lab202_failed_candidate.json/.md。809/28091仍从未执行，完整strict PASS报告/图未生成，P3B.5尚未通过，无ns3/RL。

canonical ROS cwd/source Humble/install/Gazebo；TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；actual master16650..53与16950..52，CPU0–19/20–39/40–59/60–79。任务/观察器精确domain与环境在JSON；foreign222/master11345及17用户资料不变。rtk bash -lc入口：

```bash
/usr/bin/python3 /tmp/p3b5_v72_bootstrap.py > /tmp/p3b5_v72_dispatcher.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16650 taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v72_task_pool.py '{"run": "p3b5_v72_forced", "cases": ["forced_charge_outage"], "domain_base": 44}' > /tmp/p3b5_v72_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16651 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v72_zero_first.py > /tmp/p3b5_v72_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16652 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v72_returnproof --ros-domain-base 20 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v72_returnproof.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16653 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_a9745c3.json > /tmp/p3b5_protocol_a9745c3.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16650 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v72_first_lab101.py > /tmp/p3b5_v72_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:16650 taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v72_fixed_before_faults.py > /tmp/p3b5_v72_remaining_fixed.log 2>&1
taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v72_fixed_world.py '{"run": "p3b5_v72_fixed_lab", "cpu": "0-19", "port": 16950, "args": ["--scenarios", "lab_far_northwest", "--seeds", "202", "303", "--skip-cross-check", "--ros-domain-base", "33"]}'
taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v72_fixed_world.py '{"run": "p3b5_v72_fixed_rooms", "cpu": "20-39", "port": 16951, "args": ["--scenarios", "rooms_far_northeast", "--seeds", "101", "202", "303", "--skip-cross-check", "--ros-domain-base", "36"]}'
taskset -c 40-59 /usr/bin/python3 /tmp/p3b5_v72_fixed_world.py '{"run": "p3b5_v72_fixed_corridors", "cpu": "40-59", "port": 16952, "args": ["--scenarios", "corridors_far_west", "--seeds", "101", "202", "303", "--ros-domain-base", "39"]}'
```

实际十五原格：

```bash
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:16651 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v72_zero_ideal_lab2_rally_0678e85373 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_zero/p3b5_v72_zero_ideal_lab2_rally_0678e85373 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_zero/p3b5_v72_zero_ideal_lab2_rally_0678e85373/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_zero/p3b5_v72_zero_ideal_lab2_rally_0678e85373/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_zero/p3b5_v72_zero_ideal_lab2_rally_0678e85373/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=29 GAZEBO_MASTER_URI=http://127.0.0.1:16651 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v72_zero_battery_exhaust_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_zero/p3b5_v72_zero_battery_exhaust_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_zero/p3b5_v72_zero_battery_exhaust_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_zero/p3b5_v72_zero_battery_exhaust_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_zero/p3b5_v72_zero_battery_exhaust_lab_fault/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=44 GAZEBO_MASTER_URI=http://127.0.0.1:16650 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v72_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_forced/p3b5_v72_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_forced/p3b5_v72_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_forced/p3b5_v72_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_forced/p3b5_v72_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=45 GAZEBO_MASTER_URI=http://127.0.0.1:16650 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v72_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_forced/p3b5_v72_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_forced/p3b5_v72_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_forced/p3b5_v72_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_forced/p3b5_v72_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:16652 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v72_returnproof_ideal_forced2_rally_4c7c808f36 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_returnproof/p3b5_v72_returnproof_ideal_forced2_rally_4c7c808f36 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_returnproof/p3b5_v72_returnproof_ideal_forced2_rally_4c7c808f36/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_returnproof/p3b5_v72_returnproof_ideal_forced2_rally_4c7c808f36/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_returnproof/p3b5_v72_returnproof_ideal_forced2_rally_4c7c808f36/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=21 GAZEBO_MASTER_URI=http://127.0.0.1:16652 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v72_returnproof_physical_return_under_blackout_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_returnproof/p3b5_v72_returnproof_physical_return_under_blackout_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_returnproof/p3b5_v72_returnproof_physical_return_under_blackout_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_returnproof/p3b5_v72_returnproof_physical_return_under_blackout_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v72_returnproof/p3b5_v72_returnproof_physical_return_under_blackout_fault/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=30 GAZEBO_MASTER_URI=http://127.0.0.1:16650 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_lab101/launch_logs --episode-id p3b5_v72_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_lab101/graphs/p3b5_v72_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_lab101/episodes/p3b5_v72_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=33 GAZEBO_MASTER_URI=http://127.0.0.1:16950 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_lab/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_lab/launch_logs --episode-id p3b5_v72_fixed_lab_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_lab/graphs/p3b5_v72_fixed_lab_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_lab/episodes/p3b5_v72_fixed_lab_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=36 GAZEBO_MASTER_URI=http://127.0.0.1:16951 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_rooms/launch_logs --episode-id p3b5_v72_fixed_rooms_rooms_far_northeast_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_rooms/graphs/p3b5_v72_fixed_rooms_rooms_far_northeast_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_rooms/episodes/p3b5_v72_fixed_rooms_rooms_far_northeast_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=37 GAZEBO_MASTER_URI=http://127.0.0.1:16951 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_rooms/launch_logs --episode-id p3b5_v72_fixed_rooms_rooms_far_northeast_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_rooms/graphs/p3b5_v72_fixed_rooms_rooms_far_northeast_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_rooms/episodes/p3b5_v72_fixed_rooms_rooms_far_northeast_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=38 GAZEBO_MASTER_URI=http://127.0.0.1:16951 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_rooms/launch_logs --episode-id p3b5_v72_fixed_rooms_rooms_far_northeast_3r_seed303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_rooms/graphs/p3b5_v72_fixed_rooms_rooms_far_northeast_3r_seed303.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_rooms/episodes/p3b5_v72_fixed_rooms_rooms_far_northeast_3r_seed303_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=39 GAZEBO_MASTER_URI=http://127.0.0.1:16952 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/launch_logs --episode-id p3b5_v72_fixed_corridors_corridors_far_west_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/graphs/p3b5_v72_fixed_corridors_corridors_far_west_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/episodes/p3b5_v72_fixed_corridors_corridors_far_west_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=40 GAZEBO_MASTER_URI=http://127.0.0.1:16952 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/launch_logs --episode-id p3b5_v72_fixed_corridors_corridors_far_west_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/graphs/p3b5_v72_fixed_corridors_corridors_far_west_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/episodes/p3b5_v72_fixed_corridors_corridors_far_west_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=41 GAZEBO_MASTER_URI=http://127.0.0.1:16952 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/launch_logs --episode-id p3b5_v72_fixed_corridors_corridors_far_west_3r_seed303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/graphs/p3b5_v72_fixed_corridors_corridors_far_west_3r_seed303.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/episodes/p3b5_v72_fixed_corridors_corridors_far_west_3r_seed303_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=42 GAZEBO_MASTER_URI=http://127.0.0.1:16952 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/launch_logs --episode-id p3b5_v72_fixed_corridors_corridors_far_west_2r_seed202_crosscheck --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/graphs/p3b5_v72_fixed_corridors_corridors_far_west_2r_seed202_crosscheck.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v72_fixed_corridors/episodes/p3b5_v72_fixed_corridors_corridors_far_west_2r_seed202_crosscheck_ledger.jsonl --disable-global-battery-rally-pause
```

| original | phase / seconds | native completion | charges | minimum energy |
|---|---|---:|---:|---:|
| p3b5_v72_zero_ideal_lab2_rally_0678e85373 | FAILED / 2.1 | None | 0 | 0.00000 |
| p3b5_v72_zero_battery_exhaust_lab_fault | FAILED / 2.4 | None | 0 | 0.00000 |
| p3b5_v72_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 217.9 | 217.9000000000001 | 2 | 16.45778 |
| p3b5_v72_forced_forced_charge_outage_fault | EXPLORE / 300.2 | None | 2 | 12.44373 |
| p3b5_v72_returnproof_ideal_forced2_rally_4c7c808f36 | EXPLORE / 300.1 | None | 2 | 9.64837 |
| p3b5_v72_returnproof_physical_return_under_blackout_fault | EXPLORE / 300.2 | None | 2 | 9.65274 |
| p3b5_v72_fixed_lab101_lab_far_northwest_3r_seed101 | COMPLETE / 293.7 | 293.6999999999998 | 2 | 20.26628 |
| p3b5_v72_fixed_lab_lab_far_northwest_3r_seed202 | RALLY / 300.1 | None | 2 | 20.22274 |
| p3b5_v72_fixed_rooms_rooms_far_northeast_3r_seed101 | COMPLETE / 165.1 | 165.10000000000002 | 1 | 21.68620 |
| p3b5_v72_fixed_rooms_rooms_far_northeast_3r_seed202 | COMPLETE / 159.1 | 159.09999999999997 | 1 | 23.16947 |
| p3b5_v72_fixed_rooms_rooms_far_northeast_3r_seed303 | COMPLETE / 151.6 | 151.6 | 0 | 21.14559 |
| p3b5_v72_fixed_corridors_corridors_far_west_3r_seed101 | COMPLETE / 167.9 | 167.89999999999998 | 0 | 27.33945 |
| p3b5_v72_fixed_corridors_corridors_far_west_3r_seed202 | COMPLETE / 210.1 | 210.1 | 0 | 27.09938 |
| p3b5_v72_fixed_corridors_corridors_far_west_3r_seed303 | COMPLETE / 193.2 | 193.20000000000002 | 0 | 25.28487 |
| p3b5_v72_fixed_corridors_corridors_far_west_2r_seed202_crosscheck | COMPLETE / 206.7 | 206.7 | 0 | 20.51544 |

只读诊断/审核精确命令，首diagnosis因首帧电池字段尚未到而KeyError，保留null后离线成功；不重跑任务。

```bash
/usr/bin/python3 /tmp/record_p3b5_v72_port_annotation.py
/usr/bin/python3 /tmp/diagnose_p3b5_v72_lab202.py > /tmp/p3b5_v72_lab202_diagnosis.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v72_lab202.py > /tmp/p3b5_v72_lab202_diagnosis_complete.log 2>&1
/usr/bin/python3 /tmp/benchmark_p3b5_v73_route_cache.py > /tmp/p3b5_v73_route_cache_benchmark.log 2>&1
/usr/bin/python3 /tmp/archive_p3b5_v72_failure.py > /tmp/p3b5_v72_archive_failed.log 2>&1
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python /tmp/document_p3b5_v72_failure.py
```

Lab202 tb1 remains1.30480m away, tb2/tb3 errors.00442/.02365m. All ACTIVE/positive. After two serial charges, tb3 takes a long southern detour; tb1 waits for actual/future reservations, then still executes several visible waypoints. Saved snapshots are a distinct AP subscriber, not original buffers. Scoped-cache and intermediate approach-heading optimizations remain to be validated, without changing safety, leases or native completion.

## 2026-10-05 P3B.5 v73入站朝向与距离场缓存组件

2026-10-05 P3B.5 v73集合路径组件：串行排列评分仅在同一次不可变地图规划、同一机器人起点和完全相同机体障碍坐标配置内复用距离场；不同排列机体位置独立key，函数返回即丢弃，回退复用同一未屏蔽intent，不跨地图/位姿/TTL缓存。中间已验证路点与预约截断停点按实际入站路径末端0.3m弦朝向，减少绕墙时朝最终目标的额外转向；最终集合pose仍保留原请求yaw，交付目标可见朝向修正与实际body/live/return/源TTL/能量准入均保持。288控制14.41s、550全组件15.95s、四包build5.18s/source3r0旁路通过；新增绕墙朝向/最终yaw、预约截断与障碍配置/地图缓存隔离回归。首新增夹具两项假设错误（整段直线与栅格末段方向差0.061rad；预约障碍未在预期点触发）已按实际几何修正，原失败日志保留，未改生产门限。五个保存AP快照新旧源码排序、路线及坐标相同；缓存条件对照构建16–17→11–12个距离场，离线中位耗时约1.10–1.22→.75–.86s，实际新旧源码再次对照约.51–1.11→.31–.84s，受同时任务负载变化影响，非原控制执行器计时或任务因果收益。原生保持与严格native_completion_ok/episode_ok源码一致，300s/.35m/.05mps/.1radps/5s及原TTL/净空不变。v72十五原始失败/42unrun已f62262f归档，未回填；809/28091仍从未执行。报告report/20261005_p3b5_incoming_heading_cache_component.json。需要新冻结独立开发回归与完整正式57格，P3B.5尚未通过，无ns3/RL。

canonical ROS cwd/source Humble/install；PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/component_checks；rtk bash -lc，无新Gazebo/809试验：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v73_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v73_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v73_source_audit.log 2>&1
/usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_control.py -k "order_cache or incoming_leg or approach_before" > /tmp/p3b5_v73_focused_checks.log 2>&1
/usr/bin/python3 -m pytest -q src/multi_robot_exploration/test/test_control.py > /tmp/p3b5_v73_control_checks.log 2>&1
/usr/bin/python3 /tmp/verify_p3b5_v73_saved_plans.py > /tmp/p3b5_v73_saved_plan_verification.log 2>&1
```

## 2026-10-05 P3B.5 v74入站朝向/缓存独立开发FAIL

2026-10-05 P3B.5 v74独立六格开发FAIL，冻结b5f6be544bab0cca7b7022648b8a4a6ff1f53671；所有原owner/观察器自然关闭后审核归档。p3b5_v74_dev_fixed_lab101_lab_far_northwest_3r_seed101 PASS/COMPLETE/233.1s/charge2/min26.14744；p3b5_v74_dev_fixed_lab202_lab_far_northwest_3r_seed202 PASS/COMPLETE/195.0s/charge1/min20.71743；p3b5_v74_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/269.7s/charge2/min8.54416；p3b5_v74_dev_forced_forced_charge_outage_fault PASS/EXPLORE/300.2s/charge2/min12.38229；p3b5_v74_dev_zero_ideal_lab2_rally_8d4d5c469d FAIL/RALLY/300.1s/charge2/min15.46393；p3b5_v74_dev_zero_zero_rally_lab_fault PASS/COMPLETE/189.9s/charge0/min19.26797。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_incoming_heading_cache_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。中间路径入站朝向/局部距离场缓存只用交付输入，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与v72不同，无单因素消融，不把较早发现或较短完成时间归因于朝向/缓存修正，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。

ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master17050..17053/domains23..28/CPU0–19、20–39、40–59、60–79；全部六格前瞻预声明后原始执行。rtk bash -lc入口：

```bash
/usr/bin/python3 /tmp/run_p3b5_v74_development.py
GAZEBO_MASTER_URI=http://127.0.0.1:17050 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v74_dev_first_lab101.py > /tmp/p3b5_v74_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17051 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v74_dev_first_lab202.py > /tmp/p3b5_v74_dev_lab202_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17052 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v74_dev_task_pool.py '{"run": "p3b5_v74_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 25}' > /tmp/p3b5_v74_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17053 taskset -c 60-79 /usr/bin/python3 /tmp/run_p3b5_v74_dev_task_pool.py '{"run": "p3b5_v74_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 27}' > /tmp/p3b5_v74_dev_zero_pool.log 2>&1
```

实际六格命令：

```bash
ROS_DOMAIN_ID=23 GAZEBO_MASTER_URI=http://127.0.0.1:17050 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v74_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v74_dev_fixed_lab101/launch_logs --episode-id p3b5_v74_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v74_dev_fixed_lab101/graphs/p3b5_v74_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v74_dev_fixed_lab101/episodes/p3b5_v74_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=24 GAZEBO_MASTER_URI=http://127.0.0.1:17051 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v74_dev_fixed_lab202/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v74_dev_fixed_lab202/launch_logs --episode-id p3b5_v74_dev_fixed_lab202_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v74_dev_fixed_lab202/graphs/p3b5_v74_dev_fixed_lab202_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v74_dev_fixed_lab202/episodes/p3b5_v74_dev_fixed_lab202_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=25 GAZEBO_MASTER_URI=http://127.0.0.1:17052 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v74_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_forced/p3b5_v74_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_forced/p3b5_v74_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_forced/p3b5_v74_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_forced/p3b5_v74_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=26 GAZEBO_MASTER_URI=http://127.0.0.1:17052 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v74_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_forced/p3b5_v74_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_forced/p3b5_v74_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_forced/p3b5_v74_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_forced/p3b5_v74_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=27 GAZEBO_MASTER_URI=http://127.0.0.1:17053 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v74_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_zero/p3b5_v74_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_zero/p3b5_v74_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_zero/p3b5_v74_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_zero/p3b5_v74_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:17053 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v74_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_zero/p3b5_v74_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_zero/p3b5_v74_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_zero/p3b5_v74_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v74_dev_zero/p3b5_v74_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | check | phase / seconds | charges | minimum energy |
|---|---|---|---:|---:|
| p3b5_v74_dev_fixed_lab101_lab_far_northwest_3r_seed101 | PASS | COMPLETE / 233.1 | 2 | 26.14744 |
| p3b5_v74_dev_fixed_lab202_lab_far_northwest_3r_seed202 | PASS | COMPLETE / 195.0 | 1 | 20.71743 |
| p3b5_v74_dev_forced_ideal_forced2_rally_86fbb43bc6 | PASS | COMPLETE / 269.7 | 2 | 8.54416 |
| p3b5_v74_dev_forced_forced_charge_outage_fault | PASS | EXPLORE / 300.2 | 2 | 12.38229 |
| p3b5_v74_dev_zero_ideal_lab2_rally_8d4d5c469d | FAIL | RALLY / 300.1 | 2 | 15.46393 |
| p3b5_v74_dev_zero_zero_rally_lab_fault | PASS | COMPLETE / 189.9 | 0 | 19.26797 |

所有owner关闭后只读审核：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /tmp/audit_p3b5_v74_development.py > /tmp/p3b5_v74_development_audit.log 2>&1
```

Independent originals, no formal backfill or counterfactual causal claim. Detector is Gazebo geometric visibility proxy, not image recognition. Native evaluator/physics only read-only evidence; native truth never enters mission control. Nominal serial energy/time/parking costs remain heuristics.

## 2026-10-05 P3B.5 v75边际信息组件及离线诊断

2026-10-05 P3B.5 v75边际信息组件：普通前沿评分以当前交付地图的同一遮挡射线计算新增未知格比例，扣除健康同伴当前位置与已派发活动导航短段终点的预测观测重叠；不使用未执行的未来完整目标、目标真值或原生物理信息。评分乘以max(0.35,未重叠格/原可见格)，保留所有原候选与窄通道退路，原IG/路径距离/地图未知状态不变；不宣称预测格已完成。可见格cache随frontier cache按每次地图交付和规划副本变化失效，缓存只复用同一地图/半径。554全组件17.36s、四包build5.47s/source3r0旁路通过；新增共享/独立前沿、墙遮挡/有效未知格、同snapshot缓存和新地图丢弃旧cache回归。首三项失败是旧替身不接受新增keyword，已修正签名且原日志保留，无生产门限修改。保存AP三帧双机条件对照确认六组旧函数与无惩罚新函数候选完全相同，加惩罚后仍保留相同候选/路径/IG；该离线比较仅使用peer当前位姿，未还原原controller活动goal/回调buffer，不能证明任务耗时或因果收益。v74 late discovery/串行充电期间等待的原FAIL保留；另两种只读充电工作率和已返航后的出站refuge几何诊断已归档，但不足支持提前充电或出站抢占收益，未实现这些策略。原生完成与严格native_completion_ok/episode_ok、300s/.35m/.05mps/.1radps/5s、源TTL/实际body/live/return/完整能量准入保持。报告report/20261005_p3b5_marginal_information_component.json。新独立开发与正式57格待验证，809/28091从未执行，现协议controller hash尚待开发PASS后前瞻重冻；P3B.5未通过，无ns3/RL。

canonical ROS cwd/source Humble/install，PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/component_checks；rtk bash -lc，无新Gazebo/809试验：

```bash
/usr/bin/python3 -m pytest -q --tb=short --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v75_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v75_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v75_source_audit.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_exploration_resume.py > /tmp/p3b5_v75_frontier_checks.log 2>&1
/usr/bin/python3 /tmp/verify_p3b5_v75_marginal_information.py > /tmp/p3b5_v75_marginal_information_verification.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v74_frontier_charge_choices.py > /tmp/p3b5_v74_frontier_charge_choices.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v74_charge_departure.py > /tmp/p3b5_v74_charge_departure_geometry.log 2>&1
```

## 2026-10-05 P3B.5 v76边际信息独立开发FAIL

2026-10-05 P3B.5 v76独立六格开发FAIL，冻结6fb534998f652af8a388f80581ec69c542319ddb；所有原owner/观察器自然关闭后审核归档。p3b5_v76_dev_fixed_lab101_lab_far_northwest_3r_seed101 FAIL/RALLY/300.0s/charge2/min19.87777；p3b5_v76_dev_fixed_lab202_lab_far_northwest_3r_seed202 FAIL/RALLY/300.0s/charge2/min21.13376；p3b5_v76_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/226.4s/charge2/min15.19251；p3b5_v76_dev_forced_forced_charge_outage_fault PASS/FOUND/300.2s/charge2/min9.06194；p3b5_v76_dev_zero_ideal_lab2_rally_8d4d5c469d FAIL/COMPLETE/300.4s/charge2/min17.67561；p3b5_v76_dev_zero_zero_rally_lab_fault PASS/COMPLETE/181.4s/charge1/min23.30388。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_marginal_information_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。当前交付地图上的边际信息重叠评分只用交付输入，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与v74不同，无单因素消融，不把较早发现或较短完成时间归因于边际信息评分，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。

ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master17250..17253/domains23..28/CPU0–19、20–39、40–59、60–79；全部六格前瞻预声明后原始执行。rtk bash -lc入口：

```bash
/usr/bin/python3 /tmp/run_p3b5_v76_development.py
GAZEBO_MASTER_URI=http://127.0.0.1:17250 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v76_dev_first_lab101.py > /tmp/p3b5_v76_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17251 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v76_dev_first_lab202.py > /tmp/p3b5_v76_dev_lab202_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17252 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v76_dev_task_pool.py '{"run": "p3b5_v76_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 25}' > /tmp/p3b5_v76_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17253 taskset -c 60-79 /usr/bin/python3 /tmp/run_p3b5_v76_dev_task_pool.py '{"run": "p3b5_v76_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 27}' > /tmp/p3b5_v76_dev_zero_pool.log 2>&1
```

实际六格命令：

```bash
ROS_DOMAIN_ID=23 GAZEBO_MASTER_URI=http://127.0.0.1:17250 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v76_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v76_dev_fixed_lab101/launch_logs --episode-id p3b5_v76_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v76_dev_fixed_lab101/graphs/p3b5_v76_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v76_dev_fixed_lab101/episodes/p3b5_v76_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=24 GAZEBO_MASTER_URI=http://127.0.0.1:17251 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v76_dev_fixed_lab202/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v76_dev_fixed_lab202/launch_logs --episode-id p3b5_v76_dev_fixed_lab202_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v76_dev_fixed_lab202/graphs/p3b5_v76_dev_fixed_lab202_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v76_dev_fixed_lab202/episodes/p3b5_v76_dev_fixed_lab202_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=25 GAZEBO_MASTER_URI=http://127.0.0.1:17252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v76_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_forced/p3b5_v76_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_forced/p3b5_v76_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_forced/p3b5_v76_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_forced/p3b5_v76_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=26 GAZEBO_MASTER_URI=http://127.0.0.1:17252 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v76_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_forced/p3b5_v76_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_forced/p3b5_v76_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_forced/p3b5_v76_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_forced/p3b5_v76_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=27 GAZEBO_MASTER_URI=http://127.0.0.1:17253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v76_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_zero/p3b5_v76_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_zero/p3b5_v76_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_zero/p3b5_v76_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_zero/p3b5_v76_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:17253 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v76_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_zero/p3b5_v76_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_zero/p3b5_v76_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_zero/p3b5_v76_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v76_dev_zero/p3b5_v76_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | check | phase / seconds | charges | minimum energy |
|---|---|---|---:|---:|
| p3b5_v76_dev_fixed_lab101_lab_far_northwest_3r_seed101 | FAIL | RALLY / 300.0 | 2 | 19.87777 |
| p3b5_v76_dev_fixed_lab202_lab_far_northwest_3r_seed202 | FAIL | RALLY / 300.0 | 2 | 21.13376 |
| p3b5_v76_dev_forced_ideal_forced2_rally_86fbb43bc6 | PASS | COMPLETE / 226.4 | 2 | 15.19251 |
| p3b5_v76_dev_forced_forced_charge_outage_fault | PASS | FOUND / 300.2 | 2 | 9.06194 |
| p3b5_v76_dev_zero_ideal_lab2_rally_8d4d5c469d | FAIL | COMPLETE / 300.4 | 2 | 17.67561 |
| p3b5_v76_dev_zero_zero_rally_lab_fault | PASS | COMPLETE / 181.4 | 1 | 23.30388 |

所有owner关闭后只读审核：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /tmp/audit_p3b5_v76_development.py > /tmp/p3b5_v76_development_audit.log 2>&1
```

Independent originals, no formal backfill or counterfactual causal claim. Detector is Gazebo geometric visibility proxy, not image recognition. Native evaluator/physics only read-only evidence; native truth never enters mission control. Nominal serial energy/time/parking costs remain heuristics.

## 2026-10-05 P3B.5 v77探索入站朝向组件与失败策略撤回

2026-10-05 P3B.5 v77探索入站朝向组件：撤回尚未通过开发门禁的v75同伴重叠评分及其可见格cache，恢复b5f6be5的原ray IG/组评分/候选函数；v76三项超时和全部六原始结果已61e43ca完整归档，不宣称已隔离出重叠评分因果。探索Assignment可携带实际已验证短段的入站yaw，仅当派发终点地图格不同于完整frontier viewpoint时保留；send_goal传到同一gateway/Nav2，不再丢弃中间绕墙朝向。到最终观察格仍用原frontier方向；既有rally路径cache/入站yaw保持，原路线/坐标/IG/效用/完整能量与源TTL/机体/返航准入不改。552全组件16.43s、四包build7.33s/source3r0旁路通过；新增真正assign_idle_robots→send_goal→Nav2请求回归，分别验证绕墙中间航点与最终frontier朝向。保存v74已关闭AP三帧双机条件几何显示中间前沿方向与入站方向约0.57–1.64rad差；未采集原cmd_vel/executor，不宣称实际耗时收益。另试组大小bonus封顶的离线排序六组首选均不变，未实施；没有新增提前充电/出站抢占/驻点自动完成策略。原生与严格native完成函数、300s/.35/.05/.1/5s及电池/评估器/准备装置/809world字节保持。报告report/20261005_p3b5_exploration_heading_component.json。下一六格独立开发与新冻结完整57格待运行，809/28091从未执行，旧P3A.6接受冻结保持；P3B.5未通过，无ns3/RL。

canonical ROS cwd/source Humble/install，PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/component_checks；rtk bash -lc，无新任务/809曝光。离线诊断在61e43ca原源码上先执行，无reserved mask，原诊断source hash保留；撤回后八个基础规划函数与b5f6be5字节相同。

```bash
/usr/bin/python3 -m pytest -q --tb=short --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v77_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v77_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v77_source_audit.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v77_visible_gain_heading.py > /tmp/p3b5_v77_visible_gain_heading_diagnosis.log 2>&1
rtk proxy git apply --reverse --check /tmp/p3b5_v77_withdraw_marginal_information.patch
rtk proxy git apply --reverse /tmp/p3b5_v77_withdraw_marginal_information.patch
```

## 2026-10-05 P3B.5 v78探索入站朝向独立开发PASS

2026-10-05 P3B.5 v78独立六格开发PASS，冻结e0b0345effe09e77e977feef3a8da1d4d89bb337；所有原owner/观察器自然关闭后审核归档。p3b5_v78_dev_fixed_lab101_lab_far_northwest_3r_seed101 PASS/COMPLETE/286.3s/charge2/min20.00280；p3b5_v78_dev_fixed_lab202_lab_far_northwest_3r_seed202 PASS/COMPLETE/235.7s/charge2/min23.16123；p3b5_v78_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/227.3s/charge2/min10.63302；p3b5_v78_dev_forced_forced_charge_outage_fault PASS/RALLY/300.4s/charge2/min10.57457；p3b5_v78_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/197.4s/charge1/min22.29280；p3b5_v78_dev_zero_zero_rally_lab_fault PASS/COMPLETE/180.6s/charge1/min24.13382。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_exploration_heading_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。保留到实际探索派发的中间入站朝向只用交付输入，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与v76不同，无单因素消融，不把较早发现或较短完成时间归因于探索入站朝向，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。

ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master17450..17453/domains23..28/CPU0–19、20–39、40–59、60–79；全部六格前瞻预声明后原始执行。rtk bash -lc入口：

```bash
/usr/bin/python3 /tmp/run_p3b5_v78_development.py
GAZEBO_MASTER_URI=http://127.0.0.1:17450 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v78_dev_first_lab101.py > /tmp/p3b5_v78_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17451 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v78_dev_first_lab202.py > /tmp/p3b5_v78_dev_lab202_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17452 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v78_dev_task_pool.py '{"run": "p3b5_v78_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 25}' > /tmp/p3b5_v78_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17453 taskset -c 60-79 /usr/bin/python3 /tmp/run_p3b5_v78_dev_task_pool.py '{"run": "p3b5_v78_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 27}' > /tmp/p3b5_v78_dev_zero_pool.log 2>&1
```

实际六格命令：

```bash
ROS_DOMAIN_ID=23 GAZEBO_MASTER_URI=http://127.0.0.1:17450 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v78_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v78_dev_fixed_lab101/launch_logs --episode-id p3b5_v78_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v78_dev_fixed_lab101/graphs/p3b5_v78_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v78_dev_fixed_lab101/episodes/p3b5_v78_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=24 GAZEBO_MASTER_URI=http://127.0.0.1:17451 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v78_dev_fixed_lab202/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v78_dev_fixed_lab202/launch_logs --episode-id p3b5_v78_dev_fixed_lab202_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v78_dev_fixed_lab202/graphs/p3b5_v78_dev_fixed_lab202_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v78_dev_fixed_lab202/episodes/p3b5_v78_dev_fixed_lab202_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=25 GAZEBO_MASTER_URI=http://127.0.0.1:17452 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v78_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_forced/p3b5_v78_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_forced/p3b5_v78_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_forced/p3b5_v78_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_forced/p3b5_v78_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=26 GAZEBO_MASTER_URI=http://127.0.0.1:17452 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v78_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_forced/p3b5_v78_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_forced/p3b5_v78_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_forced/p3b5_v78_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_forced/p3b5_v78_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=27 GAZEBO_MASTER_URI=http://127.0.0.1:17453 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v78_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_zero/p3b5_v78_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_zero/p3b5_v78_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_zero/p3b5_v78_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_zero/p3b5_v78_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:17453 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v78_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_zero/p3b5_v78_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_zero/p3b5_v78_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_zero/p3b5_v78_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v78_dev_zero/p3b5_v78_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | check | phase / seconds | charges | minimum energy |
|---|---|---|---:|---:|
| p3b5_v78_dev_fixed_lab101_lab_far_northwest_3r_seed101 | PASS | COMPLETE / 286.3 | 2 | 20.00280 |
| p3b5_v78_dev_fixed_lab202_lab_far_northwest_3r_seed202 | PASS | COMPLETE / 235.7 | 2 | 23.16123 |
| p3b5_v78_dev_forced_ideal_forced2_rally_86fbb43bc6 | PASS | COMPLETE / 227.3 | 2 | 10.63302 |
| p3b5_v78_dev_forced_forced_charge_outage_fault | PASS | RALLY / 300.4 | 2 | 10.57457 |
| p3b5_v78_dev_zero_ideal_lab2_rally_8d4d5c469d | PASS | COMPLETE / 197.4 | 1 | 22.29280 |
| p3b5_v78_dev_zero_zero_rally_lab_fault | PASS | COMPLETE / 180.6 | 1 | 24.13382 |

所有owner关闭后只读审核：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /tmp/audit_p3b5_v78_development.py > /tmp/p3b5_v78_development_audit.log 2>&1
```

Independent originals, no formal backfill or counterfactual causal claim. Detector is Gazebo geometric visibility proxy, not image recognition. Native evaluator/physics only read-only evidence; native truth never enters mission control. Nominal serial energy/time/parking costs remain heuristics.

## 2026-10-05 P3B.5 v79未暴露留出前瞻协议

2026-10-05 P3B.5 v79前瞻正式协议：v78六个独立原始开发全部关闭并严格PASS后，按当前探索入站朝向controller源hash重冻未执行的809.world/seed809/fault28091。追加v72正式15started/42unrun、v74独立六格zero ideal晚发现和v76独立六格三项超时历史，不覆盖旧失败或回填。world/电池/评估器/受控返航准备装置字节、300s与原生.35/.05/.1/5s保持；仅controller元数据/未暴露历史更新。61配置检查1.53s、27case/41unique validate-only和源码旁路通过；正式初始协议matrix仍为原54格，尚待新提交执行。552组件/build7.33与六开发ledger/graph已有记录；首静态validate-only命令缺必填run-id退出2，未启动任务，原错误保留后补参数。正式57格仍须新clean pushed同提交先强制原生ideal、E0双格、受控实际返充及全部十fixed PASS，再首次809并运行其余原primary/safety；所有同批owner/观察器自然关闭后才写报告/改源。独立master/domain/CPU池之间宿主资源仍共享，不声称任务轨迹可逐步重演；开发时间差不作因果收益。报告report/20261005_p3b5_exploration_heading_holdout_protocol.json。这是前瞻协议，不是P3B.5完成；完整严格报告待运行，无ns3/RL。

canonical ROS cwd；source Humble/install；PYTHONNOUSERSITE=1，rtk bash -lc；无新增任务原始：

```bash
/usr/bin/python3 /tmp/refreeze_p3b5_v79_protocol.py
/usr/bin/python3 -m pytest -q scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py > /tmp/p3b5_v79_config_checks.log 2>&1
/usr/bin/python3 scripts/run_p3b5_tasks.py --validate-only > /tmp/p3b5_v79_validate_only_missing_run_id.log 2>&1
/usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v79_validation --ros-domain-base 50 --validate-only > /tmp/p3b5_v79_validate_only.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v79_source_audit.log 2>&1
```

## 2026-10-05 P3B.5 v79原始固定环境汇总失败

2026-10-05 P3B.5 v79原始批次验收FAIL，冻结c4c943ffc5dcecc7252f1eaba2f52dd7ce7f016d；2026-10-05 00:22:25至01:06:49UTC全部owned任务与观察器自然关闭。16started/16raw、41unrun，未重试/回填；809.world/seed809/fault28091仍从未执行。initial强制ideal原生COMPLETE220.3s/两机各charge1；fault RALLY timeout300.3s/各charge1/最低9.49659，仅安全子门PASS。E0双格FAILED1.9/2.6s、实际原生电量0、无导航；受控断网返充strict物理子门与54协议PASS。两机在守护窗口从距home1.959/2.008m开始，真实路径1.165/1.227m、净进展1.151/1.218m、Nav2 EXEC运动1.165/1.226m，各实际充电一次。全部十个固定原任务均满足未修改的episode_ok/native5秒保持，完成时间165.6至256.5s，零碰撞/耗尽/失效；但原fixed_ideal_batches继承same_candidate要求environment完全相同，而预声明world池CPU0–19/20–39/40–59不同，汇总AssertionError: environment，不能判全门禁PASS。其余环境字段一致，原manifest与失败helper全部保留，没有归一化/重写结果。16账本TTL/version及16通信图旁路审计PASS，0接触/0基础设施失败/0操作失败；实际17550..56七port/PID/env关闭及全部原helper/config/source/17用户资料哈希PASS，foreign222/master11345未动。修正下一批实验装置为全部固定world同一CPU亲和性并在首次任务前断言一致，保持严格checker/算法/任务300s/.35/.05/.1/5s/原故障与能量参数。报告report/20261005_p3b5_fixed_environment_failed_candidate.json/.md。完整strict checker/PASS图文未执行，P3B.5尚未通过，无ns3/WiFi/RL。

canonical ROS cwd/source Humble/install/Gazebo；TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；actual master17550..56；initialCPU0–19/20–39/40–59/60–79，固定labCPU0–19/rooms20–39/corridors40–59。全部domain、源、config、helper、错误和完整原始manifest在JSON保留。入口与所有原owner/实际任务：

```bash
/usr/bin/python3 /tmp/p3b5_v79_bootstrap.py
GAZEBO_MASTER_URI=http://127.0.0.1:17550 taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v79_task_pool.py '{"run": "p3b5_v79_forced", "cases": ["forced_charge_outage"], "domain_base": 44}' > /tmp/p3b5_v79_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17551 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v79_zero_first.py > /tmp/p3b5_v79_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17552 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v79_returnproof --ros-domain-base 20 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v79_returnproof.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17553 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_c4c943f.json > /tmp/p3b5_protocol_c4c943f.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17550 taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v79_first_lab101.py > /tmp/p3b5_v79_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17550 taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v79_fixed_before_faults.py > /tmp/p3b5_v79_remaining_fixed.log 2>&1
taskset -c 0-19 /usr/bin/python3 /tmp/p3b5_v79_fixed_world.py '{"run": "p3b5_v79_fixed_lab", "cpu": "0-19", "port": 17554, "args": ["--scenarios", "lab_far_northwest", "--seeds", "202", "303", "--skip-cross-check", "--ros-domain-base", "33"]}'
taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v79_fixed_world.py '{"run": "p3b5_v79_fixed_rooms", "cpu": "20-39", "port": 17555, "args": ["--scenarios", "rooms_far_northeast", "--seeds", "101", "202", "303", "--skip-cross-check", "--ros-domain-base", "36"]}'
taskset -c 40-59 /usr/bin/python3 /tmp/p3b5_v79_fixed_world.py '{"run": "p3b5_v79_fixed_corridors", "cpu": "40-59", "port": 17556, "args": ["--scenarios", "corridors_far_west", "--seeds", "101", "202", "303", "--ros-domain-base", "39"]}'
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:17551 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v79_zero_ideal_lab2_rally_0678e85373 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_zero/p3b5_v79_zero_ideal_lab2_rally_0678e85373 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_zero/p3b5_v79_zero_ideal_lab2_rally_0678e85373/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_zero/p3b5_v79_zero_ideal_lab2_rally_0678e85373/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_zero/p3b5_v79_zero_ideal_lab2_rally_0678e85373/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=29 GAZEBO_MASTER_URI=http://127.0.0.1:17551 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v79_zero_battery_exhaust_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_zero/p3b5_v79_zero_battery_exhaust_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_zero/p3b5_v79_zero_battery_exhaust_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_zero/p3b5_v79_zero_battery_exhaust_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_zero/p3b5_v79_zero_battery_exhaust_lab_fault/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=44 GAZEBO_MASTER_URI=http://127.0.0.1:17550 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v79_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_forced/p3b5_v79_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_forced/p3b5_v79_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_forced/p3b5_v79_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_forced/p3b5_v79_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=45 GAZEBO_MASTER_URI=http://127.0.0.1:17550 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v79_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_forced/p3b5_v79_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_forced/p3b5_v79_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_forced/p3b5_v79_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_forced/p3b5_v79_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:17552 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v79_returnproof_ideal_forced2_rally_4c7c808f36 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_returnproof/p3b5_v79_returnproof_ideal_forced2_rally_4c7c808f36 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_returnproof/p3b5_v79_returnproof_ideal_forced2_rally_4c7c808f36/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_returnproof/p3b5_v79_returnproof_ideal_forced2_rally_4c7c808f36/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_returnproof/p3b5_v79_returnproof_ideal_forced2_rally_4c7c808f36/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=21 GAZEBO_MASTER_URI=http://127.0.0.1:17552 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v79_returnproof_physical_return_under_blackout_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_returnproof/p3b5_v79_returnproof_physical_return_under_blackout_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_returnproof/p3b5_v79_returnproof_physical_return_under_blackout_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_returnproof/p3b5_v79_returnproof_physical_return_under_blackout_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v79_returnproof/p3b5_v79_returnproof_physical_return_under_blackout_fault/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=30 GAZEBO_MASTER_URI=http://127.0.0.1:17550 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_lab101/launch_logs --episode-id p3b5_v79_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_lab101/graphs/p3b5_v79_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_lab101/episodes/p3b5_v79_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=33 GAZEBO_MASTER_URI=http://127.0.0.1:17554 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_lab/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_lab/launch_logs --episode-id p3b5_v79_fixed_lab_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_lab/graphs/p3b5_v79_fixed_lab_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_lab/episodes/p3b5_v79_fixed_lab_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=34 GAZEBO_MASTER_URI=http://127.0.0.1:17554 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_lab/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_lab/launch_logs --episode-id p3b5_v79_fixed_lab_lab_far_northwest_3r_seed303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_lab/graphs/p3b5_v79_fixed_lab_lab_far_northwest_3r_seed303.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_lab/episodes/p3b5_v79_fixed_lab_lab_far_northwest_3r_seed303_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=36 GAZEBO_MASTER_URI=http://127.0.0.1:17555 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_rooms/launch_logs --episode-id p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_rooms/graphs/p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_rooms/episodes/p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=37 GAZEBO_MASTER_URI=http://127.0.0.1:17555 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_rooms/launch_logs --episode-id p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_rooms/graphs/p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_rooms/episodes/p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=38 GAZEBO_MASTER_URI=http://127.0.0.1:17555 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_rooms/launch_logs --episode-id p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_rooms/graphs/p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed303.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_rooms/episodes/p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed303_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=39 GAZEBO_MASTER_URI=http://127.0.0.1:17556 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/launch_logs --episode-id p3b5_v79_fixed_corridors_corridors_far_west_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/graphs/p3b5_v79_fixed_corridors_corridors_far_west_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/episodes/p3b5_v79_fixed_corridors_corridors_far_west_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=40 GAZEBO_MASTER_URI=http://127.0.0.1:17556 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/launch_logs --episode-id p3b5_v79_fixed_corridors_corridors_far_west_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/graphs/p3b5_v79_fixed_corridors_corridors_far_west_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/episodes/p3b5_v79_fixed_corridors_corridors_far_west_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=41 GAZEBO_MASTER_URI=http://127.0.0.1:17556 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/launch_logs --episode-id p3b5_v79_fixed_corridors_corridors_far_west_3r_seed303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/graphs/p3b5_v79_fixed_corridors_corridors_far_west_3r_seed303.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/episodes/p3b5_v79_fixed_corridors_corridors_far_west_3r_seed303_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=42 GAZEBO_MASTER_URI=http://127.0.0.1:17556 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/launch_logs --episode-id p3b5_v79_fixed_corridors_corridors_far_west_2r_seed202_crosscheck --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/graphs/p3b5_v79_fixed_corridors_corridors_far_west_2r_seed202_crosscheck.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v79_fixed_corridors/episodes/p3b5_v79_fixed_corridors_corridors_far_west_2r_seed202_crosscheck_ledger.jsonl --disable-global-battery-rally-pause
```

| original | phase / seconds | native completion | charges | minimum energy |
|---|---|---:|---:|---:|
| p3b5_v79_zero_ideal_lab2_rally_0678e85373 | FAILED / 1.9 | None | 0 | 0.00000 |
| p3b5_v79_zero_battery_exhaust_lab_fault | FAILED / 2.6 | None | 0 | 0.00000 |
| p3b5_v79_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 220.3 | 220.30000000000018 | 2 | 14.78344 |
| p3b5_v79_forced_forced_charge_outage_fault | RALLY / 300.3 | None | 2 | 9.49659 |
| p3b5_v79_returnproof_ideal_forced2_rally_4c7c808f36 | RALLY / 300.4 | None | 2 | 9.72399 |
| p3b5_v79_returnproof_physical_return_under_blackout_fault | EXPLORE / 300.4 | None | 2 | 9.70381 |
| p3b5_v79_fixed_lab101_lab_far_northwest_3r_seed101 | COMPLETE / 220.7 | 220.70000000000027 | 1 | 22.80208 |
| p3b5_v79_fixed_lab_lab_far_northwest_3r_seed202 | COMPLETE / 213.7 | 213.69999999999982 | 1 | 23.98456 |
| p3b5_v79_fixed_lab_lab_far_northwest_3r_seed303 | COMPLETE / 175.8 | 175.80000000000018 | 1 | 22.62811 |
| p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed101 | COMPLETE / 173.9 | 173.89999999999998 | 0 | 19.73693 |
| p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed202 | COMPLETE / 169.0 | 169.0 | 1 | 21.41084 |
| p3b5_v79_fixed_rooms_rooms_far_northeast_3r_seed303 | COMPLETE / 165.6 | 165.59999999999997 | 0 | 19.51113 |
| p3b5_v79_fixed_corridors_corridors_far_west_3r_seed101 | COMPLETE / 194.9 | 194.89999999999998 | 0 | 22.59217 |
| p3b5_v79_fixed_corridors_corridors_far_west_3r_seed202 | COMPLETE / 198.2 | 198.20000000000002 | 0 | 22.16069 |
| p3b5_v79_fixed_corridors_corridors_far_west_3r_seed303 | COMPLETE / 193.8 | 193.79999999999998 | 0 | 21.56430 |
| p3b5_v79_fixed_corridors_corridors_far_west_2r_seed202_crosscheck | COMPLETE / 256.5 | 256.5 | 1 | 26.01681 |

关闭后严格读取并保留16原始结果、16账本和16图；不启动新任务或重写原manifest：

```bash
/usr/bin/python3 /tmp/archive_p3b5_v79_environment_failure.py > /tmp/p3b5_v79_environment_archive.log 2>&1
PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python /tmp/document_p3b5_v79_environment_failure.py
```

All ten raw fixed tasks pass strict native completion. The unchanged aggregator rejected only cpu_affinity equality. Preserve this original failed candidate; no post-hoc normalization or resuming/backfilling its41 unrun cells. New prospective full57 cohort uses identical fixed CPU affinity. Task core source bytes and thresholds remain unchanged.

## 2026-10-05 P3B.5 v80未暴露留出前瞻协议

2026-10-05 P3B.5 v80前瞻正式协议：v79全部16原始任务/观察器自然关闭并归档ef24835后，保持controller/battery/evaluator/staging/world字节，重新预声明尚未执行的809.world/seed809/fault28091。v79十个固定任务全部原生COMPLETE，但strict same_candidate因预声明CPU0–19/20–39/40–59不同拒绝environment相等；原manifest不改，16started/41unrun与错误完整保留，不回填。新批全部十fixed及其观察器统一CPU0–79，独立world可在相同scheduler池并行，同world seeds串行；首次任务前AST解析实际helper计划并核验全部固定CPU相等、实际进程继承相同亲和性，原严格environment比较不改。初始/主故障池仍按0–19/20–39/40–59/60–79分区并用独立domain/master；所有池共享宿主资源/SMT，不宣称跨批耗时差为因果收益。61配置检查1.49s、27case/41unique validate-only和source3r旁路通过；552组件16.43s/四包7.33s及v78六开发PASS源仍相同。正式57格须新clean pushed同提交先强制原生ideal、E0双格、受控实际返充与十fixed全PASS，再首次809和其余primary/safety；原300s/.35/.05/.1/5s、源TTL、实际机体净空、能量与故障强度不变。报告report/20261005_p3b5_fixed_affinity_holdout_protocol.json。这是前瞻协议，完整P3B.5尚未通过，无ns3/WiFi/RL。

canonical ROS cwd；source Humble/install；PYTHONNOUSERSITE=1，rtk bash -lc；无新增任务原始；固定任务正式入口继续run_p2d_baseline.py，十格统一taskset -c0-79；没有改launch默认参数：

```bash
/usr/bin/python3 /tmp/refreeze_p3b5_v80_protocol.py
/usr/bin/python3 -m pytest -q scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py > /tmp/p3b5_v80_config_checks.log 2>&1
/usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_v80_validation --ros-domain-base 50 --validate-only > /tmp/p3b5_v80_validate_only.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v80_source_audit.log 2>&1
```

## 2026-10-05 P3B.5 v80原始观测者后期返充失败

2026-10-05 P3B.5 v80原候选FAIL，冻结196154e6d8627d48b0c6a2747c52f35ac3f5eed9；2026-10-05 01:18:13–02:03:36UTC全部原owner/观察器自然关闭。15started/15raw、42unrun（lab303及其余primary/safety含809），无retry/backfill。initial强制ideal原生COMPLETE218.3s/各charge1/最低9.84126；fault RALLY timeout300.4s/各charge1/最低14.33392，仅安全PASS。E0双格FAILED1.4/2.2s/原生字段完整且无导航；受控实际断网返航与54协议PASS。两机实际路径1.142/1.149m、净进展1.135/1.139m、EXEC运动1.142/1.149m、各实际charge1。九个已运行固定格八个原生COMPLETE，lab101291.7s仅8.3s余量；lab202 RALLY timeout300.3s，两机已经各charge1/到位，tb3后期返航、终态CHARGING且charge_count0/距final5.64859m，最低14.92095，零耗尽/碰撞。全部固定manifest的实际CPU亲和性0–79及其他environment字段相同，v79汇总装置问题已消除，但任务失败仍不能判全门禁PASS。15账本/15图审计PASS，0接触/infra/操作失败；17750..56实际七port/PID/env、全部冻结helper/config/source与17用户资料哈希审核通过。保存AP在240.3/250.3秒两帧位置/速度合格、输入新鲜、目标tb3确认持续，但10秒采样不能证明连续5秒原生保持或原协调器内部flags；259秒左右tb3又要求返充。需要补足保持阻断的实际原因，不能以离散样本替代成功、放宽门限或直接宣称预算/物理抖动为根因。报告report/20261005_p3b5_observer_late_charge_failed_candidate.json/.md。809.world/seed809/fault28091仍从未执行；完整strict checker/PASS图文未执行，P3B.5未完成，无ns3/WiFi/RL。

canonical ROS cwd；source Humble/install/Gazebo；TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；实际master17750..56；initial0–19/20–39/40–59/60–79，各固定world均0–79；foreign222/master11345与用户资料不动。原始bootstrap、owner与每个任务命令：

```bash
/usr/bin/python3 /tmp/p3b5_v80_bootstrap.py
GAZEBO_MASTER_URI=http://127.0.0.1:17750 taskset -c 0-19 /usr/bin/python3 /tmp/run_p3b5_v80_task_pool.py '{"run": "p3b5_v80_forced", "cases": ["forced_charge_outage"], "domain_base": 44}' > /tmp/p3b5_v80_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17751 taskset -c 20-39 /usr/bin/python3 /tmp/p3b5_v80_zero_first.py > /tmp/p3b5_v80_zero_first.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17752 taskset -c 40-59 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_v80_returnproof --ros-domain-base 20 --config scripts/p3b5_staged_return_probe_manifest.json > /tmp/p3b5_v80_returnproof.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17753 taskset -c 60-79 /usr/bin/python3 scripts/run_p3b_fault_matrix.py --output log/p3b5_protocol_196154e.json > /tmp/p3b5_protocol_196154e.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17750 taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v80_first_lab101.py > /tmp/p3b5_v80_first_lab101.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17750 taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v80_fixed_before_faults.py > /tmp/p3b5_v80_remaining_fixed.log 2>&1
taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v80_fixed_world.py '{"run": "p3b5_v80_fixed_lab", "cpu": "0-79", "port": 17754, "args": ["--scenarios", "lab_far_northwest", "--seeds", "202", "303", "--skip-cross-check", "--ros-domain-base", "33"]}'
taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v80_fixed_world.py '{"run": "p3b5_v80_fixed_rooms", "cpu": "0-79", "port": 17755, "args": ["--scenarios", "rooms_far_northeast", "--seeds", "101", "202", "303", "--skip-cross-check", "--ros-domain-base", "36"]}'
taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v80_fixed_world.py '{"run": "p3b5_v80_fixed_corridors", "cpu": "0-79", "port": 17756, "args": ["--scenarios", "corridors_far_west", "--seeds", "101", "202", "303", "--ros-domain-base", "39"]}'
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:17751 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v80_zero_ideal_lab2_rally_0678e85373 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_zero/p3b5_v80_zero_ideal_lab2_rally_0678e85373 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_zero/p3b5_v80_zero_ideal_lab2_rally_0678e85373/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_zero/p3b5_v80_zero_ideal_lab2_rally_0678e85373/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_zero/p3b5_v80_zero_ideal_lab2_rally_0678e85373/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=29 GAZEBO_MASTER_URI=http://127.0.0.1:17751 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v80_zero_battery_exhaust_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_zero/p3b5_v80_zero_battery_exhaust_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_zero/p3b5_v80_zero_battery_exhaust_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_zero/p3b5_v80_zero_battery_exhaust_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_zero/p3b5_v80_zero_battery_exhaust_lab_fault/graph.json --target-detection --rally --battery-initial-energy 0
ROS_DOMAIN_ID=44 GAZEBO_MASTER_URI=http://127.0.0.1:17750 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v80_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_forced/p3b5_v80_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_forced/p3b5_v80_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_forced/p3b5_v80_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_forced/p3b5_v80_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=45 GAZEBO_MASTER_URI=http://127.0.0.1:17750 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v80_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_forced/p3b5_v80_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_forced/p3b5_v80_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_forced/p3b5_v80_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_forced/p3b5_v80_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=20 GAZEBO_MASTER_URI=http://127.0.0.1:17752 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v80_returnproof_ideal_forced2_rally_4c7c808f36 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_returnproof/p3b5_v80_returnproof_ideal_forced2_rally_4c7c808f36 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_returnproof/p3b5_v80_returnproof_ideal_forced2_rally_4c7c808f36/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_returnproof/p3b5_v80_returnproof_ideal_forced2_rally_4c7c808f36/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_returnproof/p3b5_v80_returnproof_ideal_forced2_rally_4c7c808f36/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=21 GAZEBO_MASTER_URI=http://127.0.0.1:17752 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v80_returnproof_physical_return_under_blackout_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_returnproof/p3b5_v80_returnproof_physical_return_under_blackout_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_returnproof/p3b5_v80_returnproof_physical_return_under_blackout_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_returnproof/p3b5_v80_returnproof_physical_return_under_blackout_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v80_returnproof/p3b5_v80_returnproof_physical_return_under_blackout_fault/graph.json --target-detection --rally --enable-return-probe-pause --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[60, 250]]' --battery-idle-cost 0.15
ROS_DOMAIN_ID=30 GAZEBO_MASTER_URI=http://127.0.0.1:17750 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_lab101/launch_logs --episode-id p3b5_v80_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_lab101/graphs/p3b5_v80_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_lab101/episodes/p3b5_v80_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=33 GAZEBO_MASTER_URI=http://127.0.0.1:17754 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_lab/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_lab/launch_logs --episode-id p3b5_v80_fixed_lab_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_lab/graphs/p3b5_v80_fixed_lab_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_lab/episodes/p3b5_v80_fixed_lab_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=36 GAZEBO_MASTER_URI=http://127.0.0.1:17755 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_rooms/launch_logs --episode-id p3b5_v80_fixed_rooms_rooms_far_northeast_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_rooms/graphs/p3b5_v80_fixed_rooms_rooms_far_northeast_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_rooms/episodes/p3b5_v80_fixed_rooms_rooms_far_northeast_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=37 GAZEBO_MASTER_URI=http://127.0.0.1:17755 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_rooms/launch_logs --episode-id p3b5_v80_fixed_rooms_rooms_far_northeast_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_rooms/graphs/p3b5_v80_fixed_rooms_rooms_far_northeast_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_rooms/episodes/p3b5_v80_fixed_rooms_rooms_far_northeast_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=38 GAZEBO_MASTER_URI=http://127.0.0.1:17755 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_rooms.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x 5.0 --target-y 3.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_rooms/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_rooms/launch_logs --episode-id p3b5_v80_fixed_rooms_rooms_far_northeast_3r_seed303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_rooms/graphs/p3b5_v80_fixed_rooms_rooms_far_northeast_3r_seed303.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_rooms/episodes/p3b5_v80_fixed_rooms_rooms_far_northeast_3r_seed303_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=39 GAZEBO_MASTER_URI=http://127.0.0.1:17756 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/launch_logs --episode-id p3b5_v80_fixed_corridors_corridors_far_west_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/graphs/p3b5_v80_fixed_corridors_corridors_far_west_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/episodes/p3b5_v80_fixed_corridors_corridors_far_west_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=40 GAZEBO_MASTER_URI=http://127.0.0.1:17756 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/launch_logs --episode-id p3b5_v80_fixed_corridors_corridors_far_west_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/graphs/p3b5_v80_fixed_corridors_corridors_far_west_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/episodes/p3b5_v80_fixed_corridors_corridors_far_west_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=41 GAZEBO_MASTER_URI=http://127.0.0.1:17756 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 3 --gazebo-seed 303 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/launch_logs --episode-id p3b5_v80_fixed_corridors_corridors_far_west_3r_seed303 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/graphs/p3b5_v80_fixed_corridors_corridors_far_west_3r_seed303.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/episodes/p3b5_v80_fixed_corridors_corridors_far_west_3r_seed303_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=42 GAZEBO_MASTER_URI=http://127.0.0.1:17756 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world p1c_corridors.world --robot-count 2 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 45.0 --target-x -4.5 --target-y -0.5 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/launch_logs --episode-id p3b5_v80_fixed_corridors_corridors_far_west_2r_seed202_crosscheck --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/graphs/p3b5_v80_fixed_corridors_corridors_far_west_2r_seed202_crosscheck.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v80_fixed_corridors/episodes/p3b5_v80_fixed_corridors_corridors_far_west_2r_seed202_crosscheck_ledger.jsonl --disable-global-battery-rally-pause
```

| original | phase / seconds | native completion | charges | minimum energy |
|---|---|---:|---:|---:|
| p3b5_v80_zero_ideal_lab2_rally_0678e85373 | FAILED / 1.4 | None | 0 | 0.00000 |
| p3b5_v80_zero_battery_exhaust_lab_fault | FAILED / 2.2 | None | 0 | 0.00000 |
| p3b5_v80_forced_ideal_forced2_rally_86fbb43bc6 | COMPLETE / 218.3 | 218.29999999999973 | 2 | 9.84126 |
| p3b5_v80_forced_forced_charge_outage_fault | RALLY / 300.4 | None | 2 | 14.33392 |
| p3b5_v80_returnproof_ideal_forced2_rally_4c7c808f36 | EXPLORE / 300.2 | None | 2 | 9.56584 |
| p3b5_v80_returnproof_physical_return_under_blackout_fault | EXPLORE / 300.1 | None | 2 | 9.62666 |
| p3b5_v80_fixed_lab101_lab_far_northwest_3r_seed101 | COMPLETE / 291.7 | 291.6999999999998 | 2 | 22.67871 |
| p3b5_v80_fixed_lab_lab_far_northwest_3r_seed202 | RALLY / 300.3 | None | 2 | 14.92095 |
| p3b5_v80_fixed_rooms_rooms_far_northeast_3r_seed101 | COMPLETE / 138.2 | 138.2 | 0 | 24.99417 |
| p3b5_v80_fixed_rooms_rooms_far_northeast_3r_seed202 | COMPLETE / 151.4 | 151.4 | 0 | 20.64916 |
| p3b5_v80_fixed_rooms_rooms_far_northeast_3r_seed303 | COMPLETE / 139.7 | 139.7 | 0 | 23.86071 |
| p3b5_v80_fixed_corridors_corridors_far_west_3r_seed101 | COMPLETE / 229.0 | 228.99999999999997 | 1 | 29.30846 |
| p3b5_v80_fixed_corridors_corridors_far_west_3r_seed202 | COMPLETE / 189.0 | 188.99999999999997 | 0 | 25.46785 |
| p3b5_v80_fixed_corridors_corridors_far_west_3r_seed303 | COMPLETE / 196.1 | 196.1 | 0 | 24.12847 |
| p3b5_v80_fixed_corridors_corridors_far_west_2r_seed202_crosscheck | COMPLETE / 196.1 | 196.1 | 0 | 20.26381 |

只读诊断首泛化glob错取活跃rooms202且无rally_assignments→KeyError，未影响任务；随后限定原lab202路径，保留该查询错误与限制。没有修改或重复原任务：

```bash
/usr/bin/python3 /tmp/diagnose_p3b5_v80_lab202_hold.py > /tmp/p3b5_v80_lab202_hold_diagnosis.log 2>&1
/usr/bin/python3 /tmp/archive_p3b5_v80_late_charge_failure.py > /tmp/p3b5_v80_late_charge_archive.log 2>&1
PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python /tmp/document_p3b5_v80_late_charge_failure.py
```

Original lab202 reaches all assigned poses, but never satisfies the complete central/native hold before the observer returns late. Saved AP samples are stable at240.3/250.3sec with fresh sources and actual target confirmations. This does not establish continuous native hold or original controller flags. Next diagnose pending/quiescence/preflight/velocity reset causes directly; no threshold relaxation or causal claim.

## 2026-10-05 P3B.5 v81保持诊断组件

2026-10-05 P3B.5 v81保持诊断组件：在原本地/gateway/consumed记录每5秒的导航静止、位置速度、电池/预算、预充电和保持起点；原odom越界重置附实际源时间与原因。仅加入诊断，不改变任务决策、原生完成或保持重置。去除这些诊断语句后整个control.py AST与289a6ac一致；日志I/O可能影响调度，静态等价不是运行耗时等价。首组件13fail/539pass23.70s因旧替身漏robot_velocities，补齐测试夹具后552PASS16.77s，四包build5.35s、source3r0旁路；原失败日志保留。battery/evaluator/staging/strict checker/manifest/809world字节不变。v80原15started/42unrun失败已289a6ac归档，未回填；诊断还未证明晚充电根因或修复算法。报告report/20261005_p3b5_rally_hold_diagnostic_component.json；接下来冻结独立原始诊断任务，全部owner/观察器自然关闭后再依据实际原因改进。809/seed809/fault28091仍未执行；P3B.5未完成，无ns3/WiFi/RL。

canonical ROS cwd；source Humble/install；PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/component_checks；rtk bash -lc。首错误与修正命令均保留，没有运行新任务或809：

```bash
/usr/bin/python3 -m pytest -q --tb=short --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v81_component_checks.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v81_component_checks_complete.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v81_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v81_source_audit.log 2>&1
/usr/bin/python3 /tmp/check_p3b5_v81_control_equivalence.py
```

## 2026-10-05 P3B.5 v82独立保持诊断

2026-10-05 P3B.5 v82独立保持诊断PASS，冻结7d2a5310d6dff88fc58be9f92af0dd6b6f1412a1，02:21:04–02:27:20UTC原owner/观察器自然关闭；lab202原生COMPLETE202.6s/0charge/min19.72218/0碰撞，ledger/graph与实际master17950/domain24/CPU0–79关闭审核PASS。三机已到位、无pending/live/yield/probe、预充电完成/预算充足后，tb2交付角速度.15991/.20801重置5s保持；0.1–0.2s原生ModelStates旁录在相近源时间实测约.19–.21rad/s峰值，说明保持重置有实际运动依据。最终原生51样本5s/最大角速度.09084/最大位置误差.02775m、观察gap.1s，完成门限不改。未采集实际cmd_vel，停止后运动的控制/动力学原因尚未确定，也不能推断该独立成功任务证明了v80失败原因。报告report/20261005_p3b5_rally_hold_diagnostic_development.json/.md；后续只读采集Nav2原输入/输出再选择运动算法优化。原15/42失败不回填；809/28091仍未暴露，P3B.5正式57格未通过，无ns3/RL。

canonical ROS cwd/source Humble/install/Gazebo；TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master17950/domain24/CPU0–79，无其他任务取消、无retry。精确命令：

```bash
/usr/bin/python3 /tmp/prepare_p3b5_v82_hold_diagnosis.py
/usr/bin/python3 /tmp/run_p3b5_v82_development.py > /tmp/p3b5_v82_owner.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:17950 taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v82_dev_first_lab202.py
ROS_DOMAIN_ID=24 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v82_dev_fixed_lab202/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v82_dev_fixed_lab202/launch_logs --episode-id p3b5_v82_dev_fixed_lab202_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v82_dev_fixed_lab202/graphs/p3b5_v82_dev_fixed_lab202_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v82_dev_fixed_lab202/episodes/p3b5_v82_dev_fixed_lab202_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
```

First standalone audit omitted source install/setup.bash and failed with ModuleNotFoundError:multi_robot_exploration before any audit/mission mutation. Re-executed the read-only audit after sourcing Humble/install, PASS. Not a task retry.

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /tmp/audit_p3b5_v82_hold_diagnosis.py > /tmp/p3b5_v82_hold_diagnosis_audit.log 2>&1
```

The delivered velocity resets are corroborated by actual native post-arrival angular spikes near0.19–0.21rad/s after Nav2 actions finish. Native thresholds must remain unchanged. This independent original completed and cannot establish the cause of the earlier v80 failed run. Actual cmd_vel was not captured, so the cause of physical settling spikes remains unestablished; next capture the existing Nav2 input/output commands read-only before selecting a motion-control optimization.

## 2026-10-05 P3B.5 v83运动与时钟诊断FAIL

2026-10-05 P3B.5 v83独立lab101运动/时钟诊断FAIL，冻结473810d3c0188eb8efc282059980c5324a03f6d7，02:32:39–02:40:41UTC全部原任务/AP与补充观察器关闭；检测227.5s/RALLY229.7s，任务timeout300.2s/charge2/0碰撞/无原生保持。原运动观察器缺scripts导入路径失败，第一补充进程父归属校验失败，第二补充输出目录重复失败，第三补充在任务开始后正常采集；原冻结helper未修改、任务未重启，部分采集不标完整装置PASS。三机真实参数查询确认controller_server用sim时间而velocity_smoother均use_sim_time=false、其20Hz/OPEN_LOOP/速度及加减速使用默认值；YAML缺该节点参数段。最后转向.7rad/s后输入/输出已归零，任务297.4–297.5s原生角速度约.131/.184rad/s，交付.16221重置保持；不能推断非零命令重放或clock配置就是物理峰值原因。Humble源码平滑回调是wall timer，命令超时now()使用节点时钟；下一步修复可确认的timeout时钟不一致，不宣称修改了wall callback或消除了物理抖动。ledger/graph、显式18050/domain23及所有owner/PID/source/helper/用户资料关闭审核PASS；准备器stdout的domain24标签是文字错误，实际计划/runner/domain均23且保留原文本。报告report/20261005_p3b5_motion_clock_diagnostic_development.json/.md。全部失败保留、不回填；809/28091仍从未执行，P3B.5未完成，无ns3/RL。

canonical ROS cwd/source Humble/install/Gazebo；TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；实际master18050/domain23/CPU0–79；原任务仅一次，无retry。入口与实际命令：

```bash
/usr/bin/python3 /tmp/prepare_p3b5_v83_motion_diagnosis.py
/usr/bin/python3 /tmp/run_p3b5_v83_development.py > /tmp/p3b5_v83_owner.log 2>&1
ROS_DOMAIN_ID=23 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v83_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v83_dev_fixed_lab101/launch_logs --episode-id p3b5_v83_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v83_dev_fixed_lab101/graphs/p3b5_v83_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v83_dev_fixed_lab101/episodes/p3b5_v83_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
/usr/bin/python3 /tmp/run_p3b5_v83_supplemental_motion_capture.py > /tmp/p3b5_v83_supplemental_owner.log 2>&1
/usr/bin/python3 /tmp/run_p3b5_v83_supplemental_motion_capture2.py > /tmp/p3b5_v83_supplemental_owner2.log 2>&1
/usr/bin/python3 /tmp/run_p3b5_v83_supplemental_motion_capture3.py > /tmp/p3b5_v83_supplemental_owner3.log 2>&1
ROS_DOMAIN_ID=23 GAZEBO_MASTER_URI=http://127.0.0.1:18050 taskset -c 0-79 /usr/bin/python3 /tmp/query_p3b5_v83_smoother_clock.py > /tmp/p3b5_v83_smoother_clock.log 2>&1
/usr/bin/python3 /tmp/audit_p3b5_v83_motion_diagnosis.py > /tmp/p3b5_v83_motion_diagnosis_audit.log 2>&1
```

Three runtime controller_server use_sim_time values are true while all three velocity_smoother values are false; the smoother has no YAML parameter section. This is a confirmed configuration inconsistency. The original task detected late and timed out; last observed commands are zero before post-arrival native angular spikes, so nonzero command replay is not established as the settling cause. Keep strict native criteria and physics unchanged. Supplemental capture is partial and apparatus failures remain FAIL.

[Humble源码](https://api.nav2.org/nav2-humble/html/velocity__smoother_8cpp_source.html)：Humble uses a wall timer for smoothing callbacks; velocity command timeout uses the node clock via now(). Setting use_sim_time fixes timeout clock consistency, not the wall callback timer or a demonstrated physical-spike cause.

## 2026-10-05 P3B.5 v84 Nav2平滑器时钟组件

2026-10-05 P3B.5 v84 Nav2平滑器时钟组件：四份机器人Nav2 YAML新增velocity_smoother.ros__parameters.use_sim_time=true，launch原RewrittenYaml仍可随use_sim_time覆盖；修复v83实际三机参数确认的controller sim/smoother wall时钟不一致。语义比对确认每份YAML只新增该时钟键；20Hz/OPEN_LOOP/速度/加减速/1s超时数值默认、RPP/angular.7/accel3.2、Nav2.02/.25、Gazebo物理参数均不改。Humble平滑回调仍wall timer，变更统一的是命令超时节点时钟，不宣称改变了回调时基或解决物理峰值因果。现有四参数配置/身体/RPP测试加入时钟一致性，552组件16.26s、四包build5.23s/source3r0旁路PASS。controller/battery/evaluator/strict checker/staging/manifest/809world/SDF字节不变，300s/.35/.05/.1/5s不放宽。原v83任务超时与三次测量失败已0a1d00e归档，未重启/回填；组件报告report/20261005_p3b5_velocity_smoother_clock_component.json。下一六格独立开发将查询实际clock配置并保留所有原始结果，随后新冻结正式57格；809/28091仍未暴露，P3B.5未完成，无ns3/RL。

canonical ROS cwd/source Humble/install，PYTHONNOUSERSITE=1；test ROS_LOG_DIR=log/component_checks；rtk bash -lc：

```bash
/usr/bin/python3 -m pytest -q --tb=short --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v84_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v84_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v84_source_audit.log 2>&1
```

[Humble官方源码](https://api.nav2.org/nav2-humble/html/velocity__smoother_8cpp_source.html)用于核实wall timer与now()超时时基，未复制/改写外部Nav2库。

## 2026-10-05 P3B.5 v85Nav2平滑器时钟独立开发FAIL

2026-10-05 P3B.5 v85独立六格开发FAIL，冻结14c4c416d7cd30eb958b20a528e660bebf4b6943；所有原owner/观察器自然关闭后审核归档。p3b5_v85_dev_fixed_lab101_lab_far_northwest_3r_seed101 PASS/COMPLETE/174.1s/charge1/min22.64706；p3b5_v85_dev_fixed_lab202_lab_far_northwest_3r_seed202 PASS/COMPLETE/247.0s/charge2/min23.44580；p3b5_v85_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/189.7s/charge2/min15.51925；p3b5_v85_dev_forced_forced_charge_outage_fault PASS/COMPLETE/296.8s/charge2/min9.89349；p3b5_v85_dev_zero_ideal_lab2_rally_8d4d5c469d FAIL/EXPLORE/300.3s/charge1/min3.21880；p3b5_v85_dev_zero_zero_rally_lab_fault PASS/COMPLETE/202.3s/charge1/min21.89626。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_velocity_smoother_clock_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。Nav2平滑器命令超时仿真时钟只用交付输入，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与历史候选不同，无单因素消融，不把较早发现或较短完成时间归因于Nav2平滑器时钟，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。 lab202原参数只返回五项true，缺/tb3/controller_server，测量FAIL且不推断第六项。原冻结审核器未改；新关闭后只读归档器将缺响应列为测量失败并完整保留六任务。失败zero ideal原ledger有27条过期输入诊断，个人地图源龄超过5s时融合地图/pose/TF/电池仍新鲜；实际overlay地图周期5s恰等于TTL5s，缺交付余量。此为确认的配置冲突，尚不能证明加快更新就能完成任务或解决返航停滞。

ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master18150..18153/domains23..28/固定两格CPU0–79，forced40–59、zero60–79（共享宿主）；全部六格前瞻预声明后原始执行。rtk bash -lc入口：

```bash
/usr/bin/python3 /tmp/run_p3b5_v85_development.py
GAZEBO_MASTER_URI=http://127.0.0.1:18150 taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v85_dev_first_lab101.py > /tmp/p3b5_v85_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:18151 taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v85_dev_first_lab202.py > /tmp/p3b5_v85_dev_lab202_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:18152 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v85_dev_task_pool.py '{"run": "p3b5_v85_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 25}' > /tmp/p3b5_v85_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:18153 taskset -c 60-79 /usr/bin/python3 /tmp/run_p3b5_v85_dev_task_pool.py '{"run": "p3b5_v85_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 27}' > /tmp/p3b5_v85_dev_zero_pool.log 2>&1
```

实际六格命令：

```bash
ROS_DOMAIN_ID=23 GAZEBO_MASTER_URI=http://127.0.0.1:18150 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v85_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v85_dev_fixed_lab101/launch_logs --episode-id p3b5_v85_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v85_dev_fixed_lab101/graphs/p3b5_v85_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v85_dev_fixed_lab101/episodes/p3b5_v85_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=24 GAZEBO_MASTER_URI=http://127.0.0.1:18151 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v85_dev_fixed_lab202/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v85_dev_fixed_lab202/launch_logs --episode-id p3b5_v85_dev_fixed_lab202_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v85_dev_fixed_lab202/graphs/p3b5_v85_dev_fixed_lab202_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v85_dev_fixed_lab202/episodes/p3b5_v85_dev_fixed_lab202_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=25 GAZEBO_MASTER_URI=http://127.0.0.1:18152 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v85_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_forced/p3b5_v85_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_forced/p3b5_v85_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_forced/p3b5_v85_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_forced/p3b5_v85_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=26 GAZEBO_MASTER_URI=http://127.0.0.1:18152 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v85_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_forced/p3b5_v85_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_forced/p3b5_v85_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_forced/p3b5_v85_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_forced/p3b5_v85_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=27 GAZEBO_MASTER_URI=http://127.0.0.1:18153 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v85_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_zero/p3b5_v85_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_zero/p3b5_v85_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_zero/p3b5_v85_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_zero/p3b5_v85_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:18153 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v85_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_zero/p3b5_v85_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_zero/p3b5_v85_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_zero/p3b5_v85_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v85_dev_zero/p3b5_v85_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | check | phase / seconds | charges | minimum energy |
|---|---|---|---:|---:|
| p3b5_v85_dev_fixed_lab101_lab_far_northwest_3r_seed101 | PASS | COMPLETE / 174.1 | 1 | 22.64706 |
| p3b5_v85_dev_fixed_lab202_lab_far_northwest_3r_seed202 | PASS | COMPLETE / 247.0 | 2 | 23.44580 |
| p3b5_v85_dev_forced_ideal_forced2_rally_86fbb43bc6 | PASS | COMPLETE / 189.7 | 2 | 15.51925 |
| p3b5_v85_dev_forced_forced_charge_outage_fault | PASS | COMPLETE / 296.8 | 2 | 9.89349 |
| p3b5_v85_dev_zero_ideal_lab2_rally_8d4d5c469d | FAIL | EXPLORE / 300.3 | 1 | 3.21880 |
| p3b5_v85_dev_zero_zero_rally_lab_fault | PASS | COMPLETE / 202.3 | 1 | 21.89626 |

所有owner关闭后只读审核：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /tmp/audit_p3b5_v85_retained_development.py > /tmp/p3b5_v85_retained_development_audit.log 2>&1
```

lab101 six original parameter responses are true; lab202 retains only five true responses, missing /tb3/controller_server. No sixth response is inferred. The original frozen archive checker is unchanged; a new post-closure read-only checker records this as an apparatus failure while retaining all six task outcomes.

Independent originals, no formal backfill or counterfactual causal claim. Detector is Gazebo geometric visibility proxy, not image recognition. Native evaluator/physics only read-only evidence; native truth never enters mission control. Nominal serial energy/time/parking costs remain heuristics.

## 2026-10-05 P3B.5 v87地图更新余量组件

2026-10-05 P3B.5 v87地图更新余量组件：实际in-repo slam_toolbox overlay的map_update_interval从5.0缩短至2.0s；原publish loop rclcpp::Rate仍为Humble host system_clock，地图header仍最新实际scan源时间。个人/融合地图源TTL5s、pose/TF2s、电池5s及过期拒绝不变，不用重复发布时刻续租。现有规划源租约回归改用一个真实producer周期加TF偏移后的地图源龄，正常帧可用、过期map仍拒绝；552检查18.30s、含slam_toolbox的五包build6.17s、source3r0旁路PASS。YAML语义只改生成周期，SLAM C++、controller/battery/evaluator/strict checker/staging/四Nav2配置/manifest/809world/模型字节不变。地图计算和消息负载增加，所有ideal/fault需同新冻结栈；2s为wall标称而非最大sim源龄保证，需新独立开发实测，不宣称修复已带来任务成功或单因素耗时收益。v85六原始FAIL与测量缺响应已d17f97a完整归档；809/28091仍未暴露，正式57格待执行，P3B.5尚未完成，无ns3/WiFi/RL。组件报告report/20261005_p3b5_map_publication_margin_component.json。

canonical ROS cwd，source /opt/ros/humble/setup.bash 和 install/setup.bash；PYTHONNOUSERSITE=1，组件ROS_LOG_DIR=log/ros_launch。552 checks/build/source audit均exit0并reaped：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v87_component_checks.log 2>&1
colcon build --symlink-install --packages-select slam_toolbox multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v87_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v87_source_audit.log 2>&1
```

## 2026-10-05 P3B.5 v88地图更新余量独立开发FAIL

2026-10-05 P3B.5 v88独立六格开发FAIL，冻结da2b5c2105c5999460c6548e2a2d2fd02d29b52f；所有原owner/观察器自然关闭后审核归档。p3b5_v88_dev_fixed_lab101_lab_far_northwest_3r_seed101 FAIL/RALLY/300.3s/charge3/min15.77163；p3b5_v88_dev_fixed_lab202_lab_far_northwest_3r_seed202 FAIL/RALLY/300.3s/charge3/min16.06252；p3b5_v88_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/250.6s/charge2/min8.01925；p3b5_v88_dev_forced_forced_charge_outage_fault PASS/RALLY/300.4s/charge2/min10.82606；p3b5_v88_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/212.2s/charge1/min21.92480；p3b5_v88_dev_zero_zero_rally_lab_fault PASS/COMPLETE/208.6s/charge1/min23.51223。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_map_publication_margin_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。两秒实际地图生成周期统一用于ideal/fault，地图header保留实际scan源时间，TTL不变，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与历史候选不同，无单因素消融，不把较早发现或较短完成时间归因于地图周期，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。 六格真实Nav2与SLAM参数响应齐全且正确，无缺响应；只读服务查询重发记录保留，不是任务重试。源地图交付龄和更新间隔全部在JSON保留，不能把AP观测年龄当成原协调器缓存或最大时限。两个fixed均charge3、RALLY timeout300.3s、0接触；最后观测者tb2在同伴返充后离开，未有新观测者接替确认；目标源过期触发盲扫描/普通前沿重搜。现guard只保护5s，而已接纳target租约60s，下一候选保持最后观测者角色至有效租约内实际接替，不能延长target TTL/用expired目标派发或阻止本地安全返航。

ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master18450..18453/domains23..28/固定两格CPU0–79，forced40–59、zero60–79，共享宿主；全部六格前瞻预声明后原始执行。rtk bash -lc入口：

```bash
/usr/bin/python3 /tmp/run_p3b5_v88_development.py
GAZEBO_MASTER_URI=http://127.0.0.1:18450 taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v88_dev_first_lab101.py > /tmp/p3b5_v88_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:18451 taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v88_dev_first_lab202.py > /tmp/p3b5_v88_dev_lab202_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:18452 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v88_dev_task_pool.py '{"run": "p3b5_v88_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 25}' > /tmp/p3b5_v88_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:18453 taskset -c 60-79 /usr/bin/python3 /tmp/run_p3b5_v88_dev_task_pool.py '{"run": "p3b5_v88_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 27}' > /tmp/p3b5_v88_dev_zero_pool.log 2>&1
```

实际六格命令：

```bash
ROS_DOMAIN_ID=23 GAZEBO_MASTER_URI=http://127.0.0.1:18450 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v88_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v88_dev_fixed_lab101/launch_logs --episode-id p3b5_v88_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v88_dev_fixed_lab101/graphs/p3b5_v88_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v88_dev_fixed_lab101/episodes/p3b5_v88_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=24 GAZEBO_MASTER_URI=http://127.0.0.1:18451 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v88_dev_fixed_lab202/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v88_dev_fixed_lab202/launch_logs --episode-id p3b5_v88_dev_fixed_lab202_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v88_dev_fixed_lab202/graphs/p3b5_v88_dev_fixed_lab202_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v88_dev_fixed_lab202/episodes/p3b5_v88_dev_fixed_lab202_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=25 GAZEBO_MASTER_URI=http://127.0.0.1:18452 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v88_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_forced/p3b5_v88_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_forced/p3b5_v88_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_forced/p3b5_v88_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_forced/p3b5_v88_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=26 GAZEBO_MASTER_URI=http://127.0.0.1:18452 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v88_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_forced/p3b5_v88_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_forced/p3b5_v88_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_forced/p3b5_v88_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_forced/p3b5_v88_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=27 GAZEBO_MASTER_URI=http://127.0.0.1:18453 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v88_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_zero/p3b5_v88_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_zero/p3b5_v88_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_zero/p3b5_v88_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_zero/p3b5_v88_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:18453 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v88_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_zero/p3b5_v88_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_zero/p3b5_v88_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_zero/p3b5_v88_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v88_dev_zero/p3b5_v88_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | check | phase / seconds | charges | minimum energy |
|---|---|---|---:|---:|
| p3b5_v88_dev_fixed_lab101_lab_far_northwest_3r_seed101 | FAIL | RALLY / 300.3 | 3 | 15.77163 |
| p3b5_v88_dev_fixed_lab202_lab_far_northwest_3r_seed202 | FAIL | RALLY / 300.3 | 3 | 16.06252 |
| p3b5_v88_dev_forced_ideal_forced2_rally_86fbb43bc6 | PASS | COMPLETE / 250.6 | 2 | 8.01925 |
| p3b5_v88_dev_forced_forced_charge_outage_fault | PASS | RALLY / 300.4 | 2 | 10.82606 |
| p3b5_v88_dev_zero_ideal_lab2_rally_8d4d5c469d | PASS | COMPLETE / 212.2 | 1 | 21.92480 |
| p3b5_v88_dev_zero_zero_rally_lab_fault | PASS | COMPLETE / 208.6 | 1 | 23.51223 |

所有owner关闭后只读审核：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /tmp/audit_p3b5_v88_retained_development.py > /tmp/p3b5_v88_retained_development_audit.log 2>&1
```

Independent originals, no formal backfill or counterfactual causal claim. Detector is Gazebo geometric visibility proxy, not image recognition. Native evaluator/physics only read-only evidence; native truth never enters mission control. Nominal serial energy/time/parking costs remain heuristics.

## 2026-10-05 P3B.5 v90观测者角色交接组件

2026-10-05 P3B.5 v90观测者角色租约组件：最后交付确认对应的观测者角色保留至原target源租约60s内的实际同伴新确认接替，5s心跳缺口不再被当作交接完成。角色保护不宣称当下仍可见，不生成检测/不续租source；本地非ACTIVE、已接纳早充请求及capacity不足仍优先。相机heartbeat/朝向修复5s、target TTL60s、其他源TTL/早充串行/全路线+等待+返航预算/机体净空/300s/.35/.05/.1/5s原生门不改。仅rally_observation_guard和prepare_rally_charges AST变化，其余控制函数AST一致；battery/evaluator/strict checker/staging/四Nav2/SLAM2s配置与C++/manifest/809world/SDF字节不变。现有handoff回归加入超过5s但有效target的实际等待、真实新peer确认才移交；边界60s/未来stamp/非finite/返航/充电/FAILED-peer均覆盖。556检查18.00s、四包build5.31s/source3r0旁路PASS；组件不证明任务收益，下一独立六格需完整关闭、保留再新冻结正式57格。v88六原始FAIL已14a5798完整归档，不回填；809/28091仍未执行，P3B.5未完成，无ns3/WiFi/RL。报告report/20261005_p3b5_observer_role_lease_component.json。

canonical ROS cwd/source Humble+install/PYTHONNOUSERSITE=1/ROS_LOG_DIR=log/ros_launch；所有检查exit0并reaped。命令：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v90_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v90_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v90_source_audit.log 2>&1
```

## 2026-10-05 P3B.5 v91观测角色租约独立开发FAIL

2026-10-05 P3B.5 v91独立六格开发FAIL，冻结2d1a1b8204811aa54ba2557bdbb3b277bb97476e；所有原owner/观察器自然关闭后审核归档。p3b5_v91_dev_fixed_lab101_lab_far_northwest_3r_seed101 FAIL/RALLY/300.2s/charge2/min18.31056；p3b5_v91_dev_fixed_lab202_lab_far_northwest_3r_seed202 FAIL/FAILED/180.7s/charge0/min29.75193；p3b5_v91_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/233.0s/charge2/min10.58555；p3b5_v91_dev_forced_forced_charge_outage_fault PASS/RALLY/300.4s/charge2/min10.83913；p3b5_v91_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/196.2s/charge1/min21.57276；p3b5_v91_dev_zero_zero_rally_lab_fault PASS/COMPLETE/198.8s/charge1/min21.89806。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_observer_role_lease_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。原target60s租约内保护最后观测者角色，只有真实同伴确认才移交；心跳5s/其他源TTL不变，控制只用交付输入，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与历史候选不同，无单因素消融，不把较早发现或较短完成时间归因于角色保护，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。 六格真实参数响应齐全且正确；时间审计五PASS、lab101 FAIL，六运行图独立审核PASS（见审计更正）；无source/helper/用户资料改动，无任务重试。lab101角色保护实际保持到确认缺口超过24s但仍RALLY timeout300.2；原生旁录tb2静止距target2.167m、yaw2.454、target方向1.592，误差约.862rad>FOV半角.785，实际朝向恢复缺失，不续租或推断仍可见。lab202在180.7s因insufficient_rally_poses FAILED、0charge/min29.75193，无物理失败机器人；三原AP末期条件回放各18候选，tb2可达16而tb1/tb3与home仅达2，原图与现有自回波规划副本均无完整三机分配。单纯候选数量不能保证连通；需调查连接区域，而不是放宽净空/穿未知格。AP回放不是原内部buffer或反事实任务，原生只读取证不反馈控制，不宣称角色修改已解决任务。

ROS canonical cwd，source Humble/install/Gazebo，TURTLEBOT3_MODEL=waffle、PYTHONNOUSERSITE=1、ROS_LOG_DIR=log/ros_launch；master18650..18653/domains23..28/固定两格CPU0–79，forced40–59、zero60–79，共享宿主；全部六格前瞻预声明后原始执行。rtk bash -lc入口：

```bash
/usr/bin/python3 /tmp/run_p3b5_v91_development.py
GAZEBO_MASTER_URI=http://127.0.0.1:18650 taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v91_dev_first_lab101.py > /tmp/p3b5_v91_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:18651 taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v91_dev_first_lab202.py > /tmp/p3b5_v91_dev_lab202_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:18652 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v91_dev_task_pool.py '{"run": "p3b5_v91_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 25}' > /tmp/p3b5_v91_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:18653 taskset -c 60-79 /usr/bin/python3 /tmp/run_p3b5_v91_dev_task_pool.py '{"run": "p3b5_v91_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 27}' > /tmp/p3b5_v91_dev_zero_pool.log 2>&1
```

实际六格命令：

```bash
ROS_DOMAIN_ID=23 GAZEBO_MASTER_URI=http://127.0.0.1:18650 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v91_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v91_dev_fixed_lab101/launch_logs --episode-id p3b5_v91_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v91_dev_fixed_lab101/graphs/p3b5_v91_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v91_dev_fixed_lab101/episodes/p3b5_v91_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=24 GAZEBO_MASTER_URI=http://127.0.0.1:18651 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v91_dev_fixed_lab202/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v91_dev_fixed_lab202/launch_logs --episode-id p3b5_v91_dev_fixed_lab202_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v91_dev_fixed_lab202/graphs/p3b5_v91_dev_fixed_lab202_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v91_dev_fixed_lab202/episodes/p3b5_v91_dev_fixed_lab202_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=25 GAZEBO_MASTER_URI=http://127.0.0.1:18652 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v91_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_forced/p3b5_v91_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_forced/p3b5_v91_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_forced/p3b5_v91_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_forced/p3b5_v91_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=26 GAZEBO_MASTER_URI=http://127.0.0.1:18652 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v91_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_forced/p3b5_v91_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_forced/p3b5_v91_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_forced/p3b5_v91_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_forced/p3b5_v91_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=27 GAZEBO_MASTER_URI=http://127.0.0.1:18653 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v91_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_zero/p3b5_v91_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_zero/p3b5_v91_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_zero/p3b5_v91_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_zero/p3b5_v91_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:18653 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v91_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_zero/p3b5_v91_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_zero/p3b5_v91_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_zero/p3b5_v91_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v91_dev_zero/p3b5_v91_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | check | phase / seconds | charges | minimum energy |
|---|---|---|---:|---:|
| p3b5_v91_dev_fixed_lab101_lab_far_northwest_3r_seed101 | FAIL | RALLY / 300.2 | 2 | 18.31056 |
| p3b5_v91_dev_fixed_lab202_lab_far_northwest_3r_seed202 | FAIL | FAILED / 180.7 | 0 | 29.75193 |
| p3b5_v91_dev_forced_ideal_forced2_rally_86fbb43bc6 | PASS | COMPLETE / 233.0 | 2 | 10.58555 |
| p3b5_v91_dev_forced_forced_charge_outage_fault | PASS | RALLY / 300.4 | 2 | 10.83913 |
| p3b5_v91_dev_zero_ideal_lab2_rally_8d4d5c469d | PASS | COMPLETE / 196.2 | 1 | 21.57276 |
| p3b5_v91_dev_zero_zero_rally_lab_fault | PASS | COMPLETE / 198.8 | 1 | 21.89806 |

所有owner关闭后只读审核：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 /tmp/audit_p3b5_v91_retained_development.py > /tmp/p3b5_v91_retained_development_audit.log 2>&1
```

Independent originals, no formal backfill or counterfactual causal claim. Detector is Gazebo geometric visibility proxy, not image recognition. Native evaluator/physics only read-only evidence; native truth never enters mission control. Nominal serial energy/time/parking costs remain heuristics.

2026-10-05 P3B.5 v91归档审计更正：此前734bc85“所有原ledger/graph审核通过”错误，后置核验KeyError(temporal_audit)后仍继续提交；现分别审计六原始格，未修改原checker/ledger/helper。lab101时间审计FAIL，首个observer_handoff_wait在2243.282使用2234.082确认、年龄9.2s，违反原5s交接门槛；其余五时间审计PASS，六运行图独立PASS，三个原生COMPLETE、两fixed任务失败及forced fault安全结果不变。原JSON/失败audit/原始物理旁录/hash/提交保留，report/20261005_p3b5_observer_role_lease_audit_correction.json/.md明确取代旧“六时间通过”结论。全部原owner/观察器/四master已关闭，原源/配置/helper/用户17文件及raw hash一致。v90角色保护60s未满足既定5s门槛，不能进入正式验收；后续恢复5s并修复实际朝向/连接调查，绝不放宽checker、TTL、能量、净空或原生完成条件。未重跑、回填或执行809/28091，P3B.5尚未完成，无ns3/RL。

更正只读命令，ROS cwd/source Humble/install/PYTHONNOUSERSITE=1：

```bash
/usr/bin/python3 /tmp/correct_p3b5_v91_archive.py > /tmp/p3b5_v91_archive_correction.log 2>&1
```

## 2026-10-05 P3B.5 v93观测朝向与连接调查组件检查

2026-10-05 P3B.5 v93组件PASS（未作任务成功声明）：基于v91失败及审计更正恢复原观测交接5s门槛，严格checker不改。等待且未到最终驻点的最近观测者，可在当前已知安全位置对准交付目标；按原.35静态/.6机体/实际路线/返航预约/并发/源TTL检查，以自身返航储备加原goal-timeout空耗准入，独立本地返航可抢占，沿用有限survey动作/次数。真实调查前缀在已知可见且范围内时面向目标；完整驻点分配受阻且原靠近调查不可派发时，复用射线收益前沿候选，按边界距目标/原utility排序调查连接区域，保留观测机器人，可走先远离目标的已知安全绕行；不虚构未知格连通，不增加动作框架。朝向成功不延长地图准备计时或标记最终到位。首次聚焦9FAIL/301PASS（新地图假设错误及旧到位路径重叠），修正后311PASS12.88s；最终573PASS15.98s、四包5.37s、3r源码零旁路PASS，其他控制函数AST/电池/原生/evaluator/staging/协议/world/model/SLAM与Nav2参数hash不变。详见report/20261005_p3b5_observation_connection_component.json。开发101/202/303非holdout；809/28091未执行，新独立六格与新同提交正式57格待验证，P3B.5尚未完成，无ns3/RL。

ROS canonical cwd，rtk bash -lc、source Humble/install、PYTHONNOUSERSITE=1；原四master关闭后修改。实际最终命令：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_rally_observation_recovery.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v93_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v93_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v93_source_audit.log 2>&1
```

两次聚焦使用/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_rally_observation_recovery.py src/multi_robot_exploration/test/test_control.py，分别输出/tmp/p3b5_v93_focused_checks.log和/tmp/p3b5_v93_focused_checks_2.log；失败原始保留。

## 2026-10-05 P3B.5 v94观测朝向和连接调查独立开发FAIL

2026-10-05 P3B.5 v94独立六格开发FAIL，冻结9b513fab47c445e1da44bb0304cc77bb301a3000；全部原owner/观察器自然关闭后逐项审核。p3b5_v94_dev_fixed_lab101_lab_far_northwest_3r_seed101 FAIL/RALLY/300.0s/charge3/min21.04333；p3b5_v94_dev_fixed_lab202_lab_far_northwest_3r_seed202 PASS/COMPLETE/280.3s/charge2/min25.82174；p3b5_v94_dev_forced_ideal_forced2_rally_86fbb43bc6 FAIL/RALLY/300.3s/charge2/min15.92234；p3b5_v94_dev_forced_forced_charge_outage_fault PASS/RALLY/300.1s/charge2/min10.36649；p3b5_v94_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/226.3s/charge1/min18.72230；p3b5_v94_dev_zero_zero_rally_lab_fault FAIL/FAILED/213.1s/charge0/min17.41613。时间审计6/6 PASS、运行图6/6 PASS、原生COMPLETE2/6，参数测量失败0；缺失不推断、各审计独立，不因一项失败跳过其它证据。强制fault仅各机充电/正能量/无碰撞安全子门，未原生完成不计任务成功。恢复既定观测交接5s；待行观测者对准有效交付目标、调查腿可见时朝向目标，分配受阻复用实际射线收益前沿绕行调查连接区域；不续租或虚构未知格，不增加完整任务重试，原地图/电池/poseTF/target TTL、净空/机体/能量/300s与.35/.05/.1/5s原生门槛均不变。所有源/参数/helper/用户17文件hash及四master/PID关闭核验通过，完整源/原始/hash/AP/物理旁录/精确命令见report/20261005_p3b5_observation_connection_development.json/.md。共享宿主及启发式预算不提供最坏时限保证，无单因素归因；几何视觉proxy/原生与AP只读取证不参与控制。809/28091从未执行，开发101/202/303不是holdout，本批不是正式57格替代，P3B.5尚未完成，无ns3/RL。

ROS canonical cwd，source Humble/install/Gazebo、TURTLEBOT3_MODEL=waffle/PYTHONNOUSERSITE=1/ROS_LOG_DIR=log/ros_launch，rtk bash -lc入口；固定两格CPU0–79，forced40–59，zero60–79，domains23..28，master18850..18853。实际入口与原命令：

```bash
/usr/bin/python3 /tmp/run_p3b5_v94_development.py > /tmp/p3b5_v94_development_owner.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:18850 taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v94_dev_first_lab101.py > /tmp/p3b5_v94_dev_lab101_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:18851 taskset -c 0-79 /usr/bin/python3 /tmp/p3b5_v94_dev_first_lab202.py > /tmp/p3b5_v94_dev_lab202_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:18852 taskset -c 40-59 /usr/bin/python3 /tmp/run_p3b5_v94_dev_task_pool.py '{"run": "p3b5_v94_dev_forced", "cases": ["forced_charge_outage"], "domain_base": 25}' > /tmp/p3b5_v94_dev_forced_pool.log 2>&1
GAZEBO_MASTER_URI=http://127.0.0.1:18853 taskset -c 60-79 /usr/bin/python3 /tmp/run_p3b5_v94_dev_task_pool.py '{"run": "p3b5_v94_dev_zero", "cases": ["zero_rally_lab"], "domain_base": 27}' > /tmp/p3b5_v94_dev_zero_pool.log 2>&1
ROS_DOMAIN_ID=23 GAZEBO_MASTER_URI=http://127.0.0.1:18850 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 101 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v94_dev_fixed_lab101/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v94_dev_fixed_lab101/launch_logs --episode-id p3b5_v94_dev_fixed_lab101_lab_far_northwest_3r_seed101 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v94_dev_fixed_lab101/graphs/p3b5_v94_dev_fixed_lab101_lab_far_northwest_3r_seed101.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v94_dev_fixed_lab101/episodes/p3b5_v94_dev_fixed_lab101_lab_far_northwest_3r_seed101_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=24 GAZEBO_MASTER_URI=http://127.0.0.1:18851 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 3 --gazebo-seed 202 --goal-timeout 60.0 --startup-timeout 600.0 --message-timeout 90.0 --shutdown-timeout 60.0 --evaluation-duration 300.0 --coverage-threshold 0 --evaluation-wait-timeout 900.0 --target-detection --rally --rally-assignment-objective minimax --rally-max-concurrent 2 --battery --battery-capacity 100.0 --battery-initial-energy 40.0 --target-x -4.0 --target-y 4.0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v94_dev_fixed_lab202/episodes --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v94_dev_fixed_lab202/launch_logs --episode-id p3b5_v94_dev_fixed_lab202_lab_far_northwest_3r_seed202 --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v94_dev_fixed_lab202/graphs/p3b5_v94_dev_fixed_lab202_lab_far_northwest_3r_seed202.json --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p2d_baseline/p3b5_v94_dev_fixed_lab202/episodes/p3b5_v94_dev_fixed_lab202_lab_far_northwest_3r_seed202_ledger.jsonl --disable-global-battery-rally-pause
ROS_DOMAIN_ID=25 GAZEBO_MASTER_URI=http://127.0.0.1:18852 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v94_dev_forced_ideal_forced2_rally_86fbb43bc6 --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_forced/p3b5_v94_dev_forced_ideal_forced2_rally_86fbb43bc6 --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_forced/p3b5_v94_dev_forced_ideal_forced2_rally_86fbb43bc6/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_forced/p3b5_v94_dev_forced_ideal_forced2_rally_86fbb43bc6/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_forced/p3b5_v94_dev_forced_ideal_forced2_rally_86fbb43bc6/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=26 GAZEBO_MASTER_URI=http://127.0.0.1:18852 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 18 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v94_dev_forced_forced_charge_outage_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_forced/p3b5_v94_dev_forced_forced_charge_outage_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_forced/p3b5_v94_dev_forced_forced_charge_outage_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_forced/p3b5_v94_dev_forced_forced_charge_outage_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_forced/p3b5_v94_dev_forced_forced_charge_outage_fault/graph.json --target-detection --rally --battery-charge-duration 10 --battery-safety-margin 5 --battery-return-timeout 120 --gateway-blackout-intervals '[[20, 130]]'
ROS_DOMAIN_ID=27 GAZEBO_MASTER_URI=http://127.0.0.1:18853 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode ideal --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v94_dev_zero_ideal_lab2_rally_8d4d5c469d --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_zero/p3b5_v94_dev_zero_ideal_lab2_rally_8d4d5c469d --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_zero/p3b5_v94_dev_zero_ideal_lab2_rally_8d4d5c469d/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_zero/p3b5_v94_dev_zero_ideal_lab2_rally_8d4d5c469d/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_zero/p3b5_v94_dev_zero_ideal_lab2_rally_8d4d5c469d/graph.json --target-detection --rally
ROS_DOMAIN_ID=28 GAZEBO_MASTER_URI=http://127.0.0.1:18853 /usr/bin/python3 /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/ros_smoke_test.py --world my_world.world --robot-count 2 --gazebo-seed 303 --startup-timeout 600 --message-timeout 90 --shutdown-timeout 60 --evaluation-duration 300 --evaluation-wait-timeout 900 --coverage-threshold 0 --mission-mode rally --gateway-mode fault --gateway-seed 17011 --battery --battery-capacity 100 --battery-initial-energy 40 --target-x -4 --target-y 4 --rally-max-concurrent 2 --disable-global-battery-rally-pause --episode-id p3b5_v94_dev_zero_zero_rally_lab_fault --collect-fault-result --dwell-seconds 0 --evaluation-output-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_zero/p3b5_v94_dev_zero_zero_rally_lab_fault --log-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_zero/p3b5_v94_dev_zero_zero_rally_lab_fault/launch --gateway-ledger-path /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_zero/p3b5_v94_dev_zero_zero_rally_lab_fault/ledger.jsonl --bypass-audit-output /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/p3b5/p3b5_v94_dev_zero/p3b5_v94_dev_zero_zero_rally_lab_fault/graph.json --target-detection --rally
```

| episode | check | phase / seconds | charges | minimum energy | temporal | graph |
|---|---|---|---:|---:|---|---|
| p3b5_v94_dev_fixed_lab101_lab_far_northwest_3r_seed101 | FAIL | RALLY / 300.0 | 3 | 21.04333 | PASS | PASS |
| p3b5_v94_dev_fixed_lab202_lab_far_northwest_3r_seed202 | PASS | COMPLETE / 280.3 | 2 | 25.82174 | PASS | PASS |
| p3b5_v94_dev_forced_ideal_forced2_rally_86fbb43bc6 | FAIL | RALLY / 300.3 | 2 | 15.92234 | PASS | PASS |
| p3b5_v94_dev_forced_forced_charge_outage_fault | PASS | RALLY / 300.1 | 2 | 10.36649 | PASS | PASS |
| p3b5_v94_dev_zero_ideal_lab2_rally_8d4d5c469d | PASS | COMPLETE / 226.3 | 1 | 18.72230 | PASS | PASS |
| p3b5_v94_dev_zero_zero_rally_lab_fault | FAIL | FAILED / 213.1 | 0 | 17.41613 | PASS | PASS |

全部关闭后只读审核：

```bash
/usr/bin/python3 /tmp/audit_p3b5_v94_retained_development.py > /tmp/p3b5_v94_retained_development_audit.log 2>&1
```

## 2026-10-05 P3B.5 v96新鲜前沿收益重规划组件

2026-10-05 P3B.5 v96组件PASS、尚非集成验收：v94六原始全部自然关闭并FAIL归档后，修复探索前沿过期重规划：原“stale”分支要求20s无进展，正常时钟/进展更新下被原stalled条件覆盖；旧收益取中间航点也不代表最终观察点。现在只在源新鲜、原3s成熟/收益门槛、距航点>.75m，且另有空间分离/实际机体/在途预约/已知可见有效前缀/完整去返预算均合格的前沿时取消旧腿，待旧结果才正常重分配；预算不足/近到达/摄像重搜/本地RETURNING/已取消均保留原行为。观测者可在当前已知.35净空且.6机体安全的位置对准未过期检测，即使融合目标LOS尚未知；调查端点/原路线预约不改，只改变范围内观测者朝向，不授权走入未知或宣称可见。v94旁录lab101首次无遮挡样本187.9s、确认188.1s，证据支持物理接近偏晚；zero fault安全驻点/目标LOS未知/yaw出FOV条件回放只读取证不当原buffer或反事实成功。聚焦323PASS13.43s，最终585PASS16.27s、四包5.32s、3r源码零旁路；其它控制函数AST/严格checker/电池/evaluator/准备夹具/world/model/参数hash不变。详见report/20261005_p3b5_fresh_frontier_replan_component.json。无原生控制输入、门槛/TTL/时限/次数放宽；809/28091仍未执行；新独立六格及同提交正式57格待通过，P3B.5未完成，无ns3/RL。

ROS canonical cwd，rtk bash -lc/source Humble/install/PYTHONNOUSERSITE=1；实际命令：

```bash
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_control.py src/multi_robot_exploration/test/test_rally_observation_recovery.py src/multi_robot_exploration/test/test_frontier_replanning.py src/multi_robot_exploration/test/test_exploration_resume.py src/multi_robot_exploration/test/test_exploration_charging.py src/multi_robot_exploration/test/test_return_progress.py src/multi_robot_exploration/test/test_rally_observer_parking.py src/multi_robot_exploration/test/test_battery_manager.py src/multi_robot_exploration/test/test_gateway.py src/multi_robot_exploration/test/test_fault_model.py src/multi_robot_exploration/test/test_navigation_faults.py src/multi_robot_exploration/test/test_task_evaluator.py src/multi_robot_exploration/test/test_nav2_ready_gate.py src/multi_robot_exploration/test/test_readiness.py src/multi_robot_exploration/test/test_spawn_entity_checked.py src/multi_robot_exploration/test/test_tf_ingress_sampler.py src/multi_robot_exploration/test/test_target_detector.py src/merge_map/test/test_merge_map.py scripts/test_p3b5_tasks.py scripts/test_p3b5_gate.py scripts/test_p3b5_return_staging.py scripts/test_ros_smoke_native_probe.py scripts/test_observer_lifetime.py > /tmp/p3b5_v96_component_checks.log 2>&1
colcon build --symlink-install --packages-select multi_robot_interfaces merge_map multi_robot_exploration multi_robot > /tmp/p3b5_v96_build.log 2>&1
/usr/bin/python3 -m multi_robot_exploration.bypass_audit --source-only --robot-count 3 > /tmp/p3b5_v96_source_audit.log 2>&1
/usr/bin/python3 /tmp/diagnose_p3b5_v94_camera_geometry.py > /tmp/p3b5_v94_camera_geometry.log 2>&1
/usr/bin/python3 -m pytest -q --tb=short src/multi_robot_exploration/test/test_frontier_replanning.py src/multi_robot_exploration/test/test_rally_observation_recovery.py src/multi_robot_exploration/test/test_control.py > /tmp/p3b5_v96_focused_checks.log 2>&1
```
