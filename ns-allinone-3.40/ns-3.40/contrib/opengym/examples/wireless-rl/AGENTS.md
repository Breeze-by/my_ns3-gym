# wireless-rl Codex Memory

This directory is the real project area for the ns3-gym + DQN wireless resource
allocation experiment. Prefer this file as the first external memory when a new
Codex chat/session starts.

## What To Read First

Read these files before making project decisions:

1. `USER_GUIDE.md`  
   Main operating guide. It records environment setup, baseline commands, DQN
   training/evaluation commands, important script parameters, and the current
   recommended model.

2. `report/20260429.md`  
   Progress report for advisor-facing context. It explains the project goal,
   ns-3/ns3-gym/RL roles, current toy wireless scenario, state/action/reward,
   baseline design, DQN results, conclusions, and next steps.

3. `log.md`  
   Lightweight experiment record. Use it for historical context, but prefer
   `USER_GUIDE.md` and the latest report for the clean current summary.

4. Key source files, only after reading the guide/report:
   - `sim.cc`
   - `test.py`
   - `run_baselines.py`
   - `run_multi_seed.py`
   - `dqn_common.py`
   - `train_dqn.py`
   - `evaluate_dqn.py`
   - `compare_dqn_with_baselines.py`

## Environment

Python commands for this project should run in the conda environment:

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
```

Typical working directory:

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
```

If `sim.cc` changes, rebuild from the ns-3 root:

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40
./ns3 build
```

## Current Project Summary

The project is a toy wireless resource allocation environment built with
ns-3 + ns3-gym. It is not a full 5G/Wi-Fi protocol simulation yet.

Current environment:

- `userNum = 5`
- Observation dimension: 15
- Per-user features: `CQI`, `Queue`, `Delay`
- Observation format:

```text
[cqi0, queue0, delay0, ..., cqi4, queue4, delay4]
```

- Action space: `Discrete(5)`, where `action=i` serves user `i`.
- Service model: `serviceRate = CQI_i * 2`, then serve `min(queue_i, serviceRate)`.
- Delay is user-level backlog age, not packet-level delay.
- Deadline miss currently means the number of users still backlogged with delay
  greater than the deadline at the current step.
- CQI evolves with a Markov-style random delta, not independent random sampling.

Reward:

```text
served - 0.01 * rewardQueue - 0.1 * totalDelay - 5.0 * deadlineMisses
```

## Baselines

Keep baseline support aligned across `test.py`, `run_baselines.py`, and
`run_multi_seed.py`.

Current baseline agents:

```text
random
round_robin
max_cqi
max_queue
max_delay
greedy
delay_aware
```

The strongest current hand-written baseline is usually `greedy`. The
delay-aware baselines are important for fair comparison because DQN also sees
delay in the state.

## Current DQN Result To Remember

Current recommended model:

```text
models/dqn_exp06_evalselect_p5k_h256_best.pt
```

Recommended training approach:

- Dueling DQN
- Double DQN
- hidden size 256
- learning rate `5e-4`
- conservative epsilon schedule
- `delay_aware` synthetic warm start
- validation checkpoint selection with `--evalInterval 25`

Key 10-seed comparison from `report/20260429.md`:

| Agent | Reward | Throughput | Queue | Delay | Misses | Fairness |
|---|---:|---:|---:|---:|---:|---:|
| `greedy` | -278.111 | 9.6525 | 70.4775 | 45.5050 | 2.2700 | 0.9531 |
| `delay_aware` | -361.319 | 9.2350 | 80.7225 | 48.7325 | 2.5175 | 0.9567 |
| `max_delay` | -550.375 | 6.7925 | 127.6375 | 53.5050 | 2.7850 | 0.7978 |
| `dqn_exp06_evalselect_p5k_h256_best` | -105.792 | 9.3250 | 73.8050 | 34.4425 | 1.5575 | 0.8974 |

Interpretation: DQN improves cumulative reward, delay, and deadline misses over
the strongest baseline, while giving up some fairness and a small amount of
throughput.

## Git And Output Hygiene

Do not commit generated runtime outputs or model checkpoints unless the user
explicitly asks.

Generated outputs live under:

```text
runtime/
models/*.pt
__pycache__/
```

`runtime/.gitignore` is intended to keep all runtime outputs ignored except the
runtime documentation files. `models/README.md` documents the model directory,
while `.pt` checkpoints are ignored.

The `report/` directory is intended to be committed. It contains advisor-facing
reports and selected copied assets/CSV summaries needed for GitHub rendering.

Before committing, run:

```bash
git add -n .
```

Check that only source/docs/report files are staged, not large runtime outputs.

## Working Style For Future Codex Sessions

- Start with this `AGENTS.md`, then `USER_GUIDE.md`, then the latest report.
- Avoid global scans of the whole ns-3 tree.
- Do not modify environment logic or baseline logic unless the user asks.
- For DQN work, focus on `dqn_common.py`, `train_dqn.py`, `evaluate_dqn.py`,
  and comparison/reporting scripts.
- For formal experiments, use multi-seed evaluation rather than
  `test.py --iterations > 1`.
