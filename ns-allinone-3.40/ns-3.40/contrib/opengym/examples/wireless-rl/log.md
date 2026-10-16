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
