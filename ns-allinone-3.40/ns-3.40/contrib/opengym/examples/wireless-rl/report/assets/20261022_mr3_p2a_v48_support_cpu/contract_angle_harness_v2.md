# 合同角域 v2 人工性能准备

仅写文件，未执行。原 A48 v1 的 18 组检查、全部结果、cold-sqrt 退化和角域限制保持。

新输入直接来自合同：64 个 `age_ns=floor(i*500000000/63)`，`i=0..63`；`phi=(6/5)*(39/50+age_ns/1e9)` 精确覆盖 .936 至 1.536。不是来自 raw 的经验样本，也不是实际年龄分布。

- production 每个 age 配原 `i%12` 模板，合64 pair调用；两端均该age，全部方向用该phi，保留12模板的map/raw、Reach/sign与hard flag结构。固定变换系数分别用非整数Q及binary64 `.6/.8` 原位精确值，输入完整记录。不是64×12交叉，不调参。
- 原disk/no-direction/zero-delta模板可合法绕过trig，故production保留64个phi输入但不声称64次cold trig miss；每项direction存在标记与实际cache统计完整记录。reader的cold-trig专门强制计算全部64角。
- reader 只加载自己的 baseline/candidate 数学模块，各64 trig与64 direction；不用production数学或对照值。
- 各role/model做cold与warm各一次未profile计时，另重新准备缓存后同输入cProfile；baseline先于candidate，短块无统计/ENV保证。cold只在workload前清缓存；同workload内部自然重用保留。
- 每侧完整数值/公共JSON和production full-frameSHA由原公共返回自然覆盖；同侧baseline/candidate/cold/warm whole-outputSHA严格相等才PASS。不比较两个本来不同余项bounds族的数值相等。
- 不调用unittest suite，不重跑旧18组，不宣称增加独立tests，不新跑coldsqrt，不提供native/World/P2A信用。

由root统一绑定并实际wait后才执行：

```bash
/usr/bin/python3 -B /tmp/mr3_p2a_v48_contract_angle_harness_v2.py \
  --output /tmp/mr3_v48_contract_angle_result_v2.json \
  --profile-directory /tmp/mr3_v48_contract_angle_profiles_v2
```

输入引用固定为 canonical A48 两套禁用源；其中所有manifest来源在开始前逐SHA/bytes核，结束复核source bytes/stat。脚本若复制进新的assets仍引用既有A48原件，不修改A48。
