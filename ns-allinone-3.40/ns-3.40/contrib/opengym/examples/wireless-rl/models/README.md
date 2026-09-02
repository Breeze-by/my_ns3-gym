# DQN 模型目录

`train_dqn.py` 将普通最终 checkpoint 保存为 `{runName}.pt`；开启
`--evalInterval` 后，还会将 validation mean cumulative reward 最好的模型保存为
`{runName}_best.pt`。

`.pt` 是可重新生成的本地训练产物，已被 Git 忽略。删除前先确认是否仍需复现实验。

当前保留的历史推荐模型：

```text
dqn_exp06_evalselect_p5k_h256_best.pt
```

它来自 2026-04-29 实验：15 维输入、5 个动作、hidden size 256、dueling
Double DQN、5000-step `delay_aware` synthetic warm start。validation seeds 为
1001–1003，最佳模型来自 zero-based episode 249。

评估示例：

```bash
python evaluate_dqn.py \
  --model models/dqn_exp06_evalselect_p5k_h256_best.pt \
  --agentName dqn_exp06_evalselect_p5k_h256_best_heldout \
  --seeds 2001,2002,2003,2004,2005,2006,2007,2008,2009,2010 \
  --device auto \
  --outputDir runtime/heldout_2001_2010
```

历史表格使用的 evaluation seeds 1–10 与训练 seeds 1–300 重叠，不是严格
held-out test。2026-09-02 已在新 seeds 2001–2010 上配套重跑相同 seeds 的
全部 baselines；DQN 在 reward、total delay 和 deadline misses 上均 10/10
seeds 优于 `greedy`。详见 `../report/20260902.md`。

旧的 10 维 `CQI + Queue` checkpoint 不能加载到当前 15 维
`CQI + Queue + Delay` 网络。完整训练配置和结果见 `../USER_GUIDE.md`。
