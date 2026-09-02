# Runtime 输出目录

`runtime/` 保存可重新生成的实验产物，不是源码事实来源：

```text
results/       单个 episode 的 step-level CSV
summaries/     单 agent、单 seed summary CSV
comparisons/   单 seed 或多 seed 的聚合比较 CSV
plots/         SVG 图
command_logs/  手工保留的命令输出
*_train.csv    DQN 每 episode 训练日志
```

这些产物默认被 Git 忽略。复现实验时应同时记录：代码 commit、完整命令、模型文件名、
training/validation/evaluation seeds、`simTime` 和 `stepTime`。

当前目录保留了 2026-04-29 的历史实验产物，包括：

```text
comparisons/baseline_comparison_all_seeds.csv
comparisons/dqn_exp06_evalselect_p5k_h256_best_eval_all_seeds.csv
comparisons/dqn_vs_baselines_dqn_exp06_evalselect_p5k_h256_best.csv
```

这些 CSV 是历史证据，不会随源码自动更新。若环境或 reward 发生变化，必须重新运行
baseline 和 DQN 评估，不能把旧 CSV 与新代码产生的结果直接混用。当前命令和字段解释见
`../USER_GUIDE.md`。

2026-09-02 的 held-out seeds 2001–2010 复测保存在：

```text
heldout_2001_2010/comparisons/baseline_comparison_all_seeds.csv
heldout_2001_2010/comparisons/dqn_exp06_evalselect_p5k_h256_best_heldout_eval_all_seeds.csv
heldout_2001_2010/comparisons/dqn_vs_baselines_dqn_exp06_evalselect_p5k_h256_best_heldout.csv
```

对应的可提交结果摘要见 `../report/20260902.md`。
