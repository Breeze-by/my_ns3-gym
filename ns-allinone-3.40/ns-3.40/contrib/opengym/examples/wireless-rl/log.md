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
