# Wireless RL Runtime Output

This directory stores generated experiment outputs.

Typical files are:

- `results/*.csv`: per-step episode records
- `summaries/*_summary.csv`: aggregate episode metrics
- `comparisons/*.csv`: cross-baseline summary tables
- `plots/*.svg`: quick visualization figures
- `dqn_train_seed*.csv`: DQN training curves

Recommended workflow:

- `python3 run_baselines.py --seed 1 --iterations 1`
- `python3 run_multi_seed.py --seeds 1,2,3,4,5`
- `python3 train_dqn.py --episodes 5 --simTime 2 --stepTime 0.5`
- `python3 evaluate_dqn.py --model models/dqn_seed1.pt --seeds 1,2`

Notes:

- Keep one episode per seed for baseline experiments. Multi-seed aggregation is
  handled by `run_multi_seed.py`.
- This directory is disposable runtime output. If it gets cluttered, clean the
  generated CSV and SVG files and rerun the scripts.

Generated files are ignored by Git. Keep source code, experiment scripts, and
configuration in version control; regenerate runtime outputs when needed.
