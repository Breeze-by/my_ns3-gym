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
