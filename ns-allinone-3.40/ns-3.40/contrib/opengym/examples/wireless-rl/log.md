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
