# 禁用 production support CPU 候选

本目录不在仓库中，未接生产。当前只写源文件，尚未执行 helper、测试或 profile。

- `support_baseline_v1.py`：冻结 production support 原字节，SHA `2b45311d33fb2c5f4c05fa39d3acde7bcfc0c17ee3c2e62e0d2bdfbd4c961f34`。
- `geometry_reference_v1.py`：原 immutable cf46 geometry 原字节，SHA `cf46b49f0740f84511f3d34f9a8eb3e56720744515d9eea1dc81bd8bacb85f0a`，未改。
- `support_candidate_v1.py`：只复用 required²、把原 nonclosing 精确 dot/cross/h 判据单次计算、validated-Q sqrt 私有256项 LRU，返回 immutable tuple；96/48bit、完整公共字段、mode 与 full frame SHA 不变。
- `harness_v1.py`：stdlib 私有模块命名空间载入三份人工 pure 源；只对 geometry 的 import 做一个明确 literal 替换，不碰真实 ROS 包或 sys.path。固定14 direction/12 pair，9个 unittest groups；不把 subtest 数量叠成测试项。

根代理统一 source-seal/actual-wait 后可执行（当前未执行）：

```bash
/usr/bin/python3 -B /tmp/mr3_p2a_v47_support_cpu_candidate/harness_v1.py \
  --output /tmp/mr3_v47_support_cpu_v1.json \
  --profile-directory /tmp/mr3_v47_support_baseline_profiles_v1
```

该命令先完整对照公共 dict/canonical bytes/full frame SHA/异常、冷暖/淘汰/输入和返回值 mutation，然后只 cProfile frozen baseline。每种模式3轮×12公共pair调用：warm重复及12个不同 exact angle 的cold首用；不读场景、raw、World、模型或独立reader。

若基于 baseline profile 决定测候选，另行新实际回执/输出可加 `--compare-performance`；默认不开。参数及输入不在看到 profile 后调整。同一 geometry reference 的 trig cache 在每实现/轮前清空；warm模式有明示相同warmup，cold模式仍保留一次pair内本来就发生的 exact angle重用。timing包含完整public proof/JSON digest，不表示ENV吞吐，也不提供资格或任务信用。

所有比对均为各自冻结生产baseline vs本候选。独立reader数学使用不同余项，不能一般性要求其数值上界与生产相等；两方不互import。
