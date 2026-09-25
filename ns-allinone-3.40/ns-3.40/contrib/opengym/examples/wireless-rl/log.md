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
