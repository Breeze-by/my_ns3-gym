# Runtime 输出目录

`runtime/` 用来保存实验运行过程中生成的结果文件、汇总文件、图表和命令日志。

常见来源包括：

- `test.py` 生成的单个 baseline step 级结果、summary 和 SVG 图。
- `run_baselines.py` 生成的单 seed baseline 对比结果。
- `run_multi_seed.py` 生成的多 seed baseline 聚合结果。
- `train_dqn.py` 生成的 DQN 训练日志 CSV。
- `evaluate_dqn.py` 生成的 DQN 多 seed 评估结果。
- `compare_dqn_with_baselines.py` 生成的 DQN 与 baseline 对比 CSV 和图。

这些文件通常体积较大、数量较多，并且可以通过重新运行实验生成，所以默认不会提交到 Git 仓库。

如果需要复现实验结果，请优先保留或记录对应命令、随机种子、模型文件名和关键汇总 CSV 路径；具体运行产物建议留在本地。
