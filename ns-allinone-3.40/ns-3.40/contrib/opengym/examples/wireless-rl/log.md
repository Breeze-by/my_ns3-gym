# DQN Iteration Log

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
