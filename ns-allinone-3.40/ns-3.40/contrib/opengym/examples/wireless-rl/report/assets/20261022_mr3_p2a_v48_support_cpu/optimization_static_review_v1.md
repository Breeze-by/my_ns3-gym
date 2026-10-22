# V45 support 数学恒等提速静态审查

本文件只依据冻结源文本。未导入或执行生产/reader、未读原始输入、未运行 CPU benchmark、World 或模型。以下是候选优先级，不是已测加速比，也不证明 31 秒/步或 full885 秒主要由此产生；应先结合 V46 有限诊断确定实际优先级。

审查源：

- production `mr3_reach_support.py`：`2b45311d33fb2c5f4c05fa39d3acde7bcfc0c17ee3c2e62e0d2bdfbd4c961f34`
- 独立 `reach_support_replay.py`：`555327657319000a313acba44fc35d548743ab04f0689d9ea1aa3b8c2e3864ed`
- 原 immutable `mr3_reach_geometry.py`：`cf46b49f0740f84511f3d34f9a8eb3e56720744515d9eea1dc81bd8bacb85f0a`；不需要修改它。

## 优先做的可证重复消除

| 位置 | 当前重复 | 最小恒等候选 | 边界 |
| --- | --- | --- | --- |
| production `direction_support_upper:56–105`，原 `nonclosing:97–122` | 自算点、axis²、dot/cross 后再调用原 nonclosing；负 dot 时原函数算一次 `h=dot*coslo+abs(cross)*sinhi`，未通过 zero 门时生产再算相同大 Fraction h | 在新 support 模块内一次得到相同 exact 中间量，先用原 zero 谓词，再复用 h 做 projected 分支 | 保留原 geometry 文件。`dot==0 && phi==0 && U==0` 特例、coslo≤0、所有 mode、字段出现/省略和 full exact frame SHA 均须完全相同；不得把数值更紧当恒等 |
| production `_frame_certificate:133–139` | `required*required` 在准入与 slack 各算一次 | 局部保存 `required_squared`，两处复用同一 immutable Fraction | 包括 delta²=0、恰等号、正负 slack；输出/异常不变。这是最小、最低风险的一项 |
| production `sqrt_bounds:27–41`；reader `sqrt_interval:28–34` | 同一 bearing 的左右方向与最终 frame distance 重复算 sqrt(delta²)；正负 sign 的 axis² 也相同 | 校验/规范化输入后调用 private bounded cache，key 是 exact Q value，value 仅 `(Q_lower,Q_upper)` | 96 bit 不变；不按浮点/毫秒/距离桶近似 key；无 mutable proof/list/dict 缓存；无不完整 state/clock key |
| production `_reach_support:117–124`、`_frame_certificate:133`、`_frame_summary:166–176` | support 先转巨大有理数字符串，再 Q(str) 解析；union 后再次 str，再解析用于 required，summary 又解析 | 私有内部同时携带数值 Q 与新建 proof dict，公共返回仍是原完整 dict；数值路径不 round-trip 字符串 | 每次构造独立可变输出；full proof 所有原字符串与 canonical SHA 完全相同。禁止为了省时删除 full-frame digest |

根缓存的确定性局部复用：每 frame 左右各一个方向时，delta² 的 sqrt 被调用三次（左、右、frame distance）；左右各两个方向时五次。map/raw、两个 peer 及 current/prospective 继续放大调用数。这是调用结构计数，不是运行采样或实测命中率；map/raw 的 norm 只有 exact Q 相等才可以共用，不能假定 TF 旋转使 binary Fraction norm 精确相等。

## Taylor 与大分母：先承认已有缓存

production 原 geometry 的 `_sin_cos_bounds` 已有 **128 项** LRU，返回 immutable 四个 Q；独立 reader 的 `trig_enclosure` 已有 **256 项** LRU，返回两个 Q。不能把“再加一个 trig cache”说成主要新优化。phi 来自每个 received source 的 exact 纳秒龄，不是跨时间固定角度；禁止按近似年龄共用结果。相同 robot/clock 的 map/raw、sign 与 peer 可以命中已有 exact-key cache。

reader `trig_enclosure:49–51` 的每次 cache miss 分别计算 86 个 `angle**k/factorial(k)` 再相加。可独立改为 exact 递推或整数共同分母/Horner，保持 **相同 degree84/85 多项式与 degree85/86 Lagrange 余项**，最终 Q 完全相同。不要减少项数、改用 libm、缩 SQRT_BITS，或调用生产 trig 来互证。

一个可直接证明的共同分母式（`x=p/q` 为规范 Q，`0≤x≤2`）：

```
cos_lower = [Σ(k=0..42) (-1)^k p^(2k) q^(85-2k) 85!/(2k)! − p^85] / [85! q^85]
sin_upper = [Σ(k=0..42) (-1)^k p^(2k+1) q^(85-2k) 86!/(2k+1)! + p^86] / [86! q^86]
```

各系数均为整数。可用 `z=p²,w=q²` 的 homogeneous Horner，cos 分子 polynomial 部分再乘 q，sin 部分再乘 p*q，最后只构造两个 Q。它减少中间 Fraction 约分次数；整数分母仍可能很大，不能宣称已解决运行成本。生产 alternating42 的四个 bounds 若需要优化，应在新 support 私有 helper 中另行给出逐个相同截断的恒等式；原 cf46 immutable geometry 不动，reader 仍保留不同余项证明。

## 进一步低风险候选

- `log_interval:144–151` 的 floor/ceil 可直接用 `(numerator<<48)//denominator` 和负数 ceil，而不是先构造 `value*2**48` 的 Fraction；所有 48-bit 向外端点字符串必须相同。
- sqrt 的“恰好在网格根上”判定可用 `k*k*denominator == numerator<<192`；不能把 tiny positive 的 lower=0 擅自改为正数。
- reader `direction_support_upper:80` 只把 projection² 用于 exact 布尔比较，可评估整数交叉乘法避免构造/约分巨大平方 Q；数学必须与当前 `h²≥U²*axis²` 完全相同。生产的 required² 仍用于完整 slack，先复用一次平方比只改比较更简单。
- 正 numerator 若已 `>= axis_lower*delta_lower`，可先精确比较并返回原 cap1，而不先除出巨大 ratio 再 min；生产仍须保留原记录字段。

## 调用路径与不可省略的工作

production `pair_checks` 对两个 peer，各核 map/raw；`ReachTracker.decide` 的 current 与 prospective 都要核，不能为提速只保留一个 callsite。`reach_for` 的 source/safety 校验不能因缓存命中而省略。reader `independent_pair` 也必须保留 map/raw AND、两端 sign union max、原 U/base 与全部 source/intent/calibration 门。

`audit_reach_cadence` 内嵌 runtime、PPO full 又有本身的 runtime/FIFO 等合取，确有重复数学调用；本轮不要通过删除审计/合并不同信用角色省时间。进程内 exact immutable 小核缓存可各自获益，但不能缓存整个 episode PASS 或用 producer summary 作为 oracle。

若优化 state geometry，只可在**单个已校验决定内**复用 immutable 数值 tuple，或用完整 exact 数学依赖作 bounded key；不能按 mutable state 对象 id、robot/epoch/seq 的不完整键跳过 fresh/来源校验。第一轮不建议扩展到这种较复杂缓存。

## 新源进入任何实际活动前的最短 CPU 证明

1. 冻结旧 helper 字节作对照，人工固定输入逐完整公共字典、canonical JSON/full-frame SHA、异常类型/条件比较；不得只比 PASS bool。
2. 覆盖 delta0、axis0拒绝、dot0/phi0/U0、dot≥0、nonacute、tiny norm lower0、原 nonclosing0、projected numerator≤0/正值、cap1、恰等号与两侧、map/raw 不同、双 sign、D/N/X/STOP 与 age0/500ms；所有 constants/96bit/48bit 不变。
3. 缓存冷/热、超过 maxsize 后淘汰、交替 exact angles、异常类型别名与修改上次返回的 dict/list；重复调用不得受外部 mutation 影响。先验证 public 数值输入，再缓存规范 Q，以免缓存命中绕过 bool/NaN/范围拒绝。
4. fixed-angle warm 与 distinct-angle cold 两种人工 timing 分开报告；固定规模、轮次与输入，不看结果调参数。不外推为 World/ENV 吞吐或重新获得 native 资格。
5. 更新新冻结 source proof/plan/binary binding，保留独立 reader 不导入 production；保留原 v1/旧 FAIL、两个 v2 callsite 与所有必要科学角色。

当前建议次序：**复用 required² → 单次 dot/cross/h → exact norm tuple 小缓存 → 去内部 str/Q 往返 → 冷 trig 整数化**。次序按静态改动风险与确定重复给出，实际收益和根因仍待 V46/有限 CPU 证据，尚未选择或实施任何候选。
