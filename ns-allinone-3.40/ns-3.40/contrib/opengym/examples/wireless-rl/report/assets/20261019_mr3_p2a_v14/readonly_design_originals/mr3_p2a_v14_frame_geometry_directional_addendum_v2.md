# V14 directional语义定稿补充v2（仍非native准入）

本稿保留v1全部原字节，明确替代其中“须两几何共同nonclosing才统一扣D”的过强/含混描述。Root已选择的语义是：**map和raw各自建立完整geometry certificate，再作逻辑AND**。每一边的距离、bearing、heading、cone support和所保留longitudinal都来自该边，不能交叉取标量。

对每个frame f，各robot方向集合全部nonclosing才在该frame内扣其.144；否则只在该frame内保留完整.144 isotropic reach。每一边独立使用同样的body .50、margin .02、原min-source age及各buffer，随后必须map.accepted AND raw.accepted。无direction/isotropic时两边所需距离相同，此时才等价min-distance cap；directional时不称“mincap”。

## 明确允许例

同一示意heading均+x，map peer在−.60、raw peer在+.90，zero age，left NORMAL/right DISK。map证明away，独立用.5512门并通过；raw不nonclosing，独立保留.144后用.6952门并通过，因而组合几何接受。统一min距离.60配最大D会更保守拒绝，但不是所选语义。物理安全推论仅依赖raw共同WORLD校准下完整raw proof，map是额外必要deny；它没有把map的方向优惠借给raw。

## 必须拒绝的混用反例

1. map距离.54且away、raw距离.90且toward：raw完整门能过，但map .54<.5512，组合必须拒绝，不能用raw远距离抹掉map额外deny。
2. map距离.60且away、raw距离.60且toward：map能过，raw保留D后的.6952门失败；组合必须拒绝，不能把map nonclosing优惠转给raw。

以上均为精确有理数synthetic集合条件，不是实跑位姿或mode承诺。新增两个独立unittest已写未运行，由root有限CPU runner统一保存实际wait/任何FAIL；首批19项测试的真实执行结果由root原attempt回执解释，本稿不冒称已执行新增测试。

## 仍保留的前提

同envelope raw bearing/yaw、source因果与共同WORLD-origin/同身体点校准仍必需；原map/body/source硬门不减。v1指出producer使用float yaw/cosf/sinf而pose quaternion是double的物理转换校准问题仍未消失。normal2R/transition4R/disk2R及D=.144仍只是待证连续physical reach集合；停止终端集合、真实mode承诺、storage/actuation交接与条件模型读回未闭合。几何CPU accepted始终native_admission=false，不能提供plant/actor/PPO可训练或旧FAIL修复信用。
