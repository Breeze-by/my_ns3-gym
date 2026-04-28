# DQN 模型目录

`train_dqn.py` 会把训练好的模型保存在这个目录。

例如：

```text
dqn_seed1.pt
```

这些 `.pt` 文件是训练产物，已经被 Git 忽略，不会提交到仓库里。

如果你删掉了模型文件，可以重新训练生成：

```bash
conda activate ns3gym
cd ~/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
python3 train_dqn.py --episodes 300 --seed 1 --device cuda:0
```

如果你想评估模型：

```bash
python3 evaluate_dqn.py --model models/dqn_seed1.pt --seeds 1,2,3,4,5 --device cuda:0
```
