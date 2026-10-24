# V74 派生结果：tb3 被哪个 peer/哪层拒绝，以及下一输入版本

结论：选择**外部 probe 输入调度层**作为下一改动层；当前证据不支持改 Reach 证书、authority、驱动或物理。V74 将 V73 的 D→X 拒绝明确定位到 tb2 的条件充分分离检查。建议仅准备显式新 workload：原合法 mask 集合内的 peer-away 软排序，加有限、零覆盖信用的自然完成暖身和每机异步两次 qualified cancel。尚未选 token/新上限、未实现或保证可行，待 Root 对齐方案。

仅读 STOP 的 `/tmp/mr3_p2a_v74_reach_rejection_description_v1.json`，894600B、SHA647f298934fe1a44b1ad666d5d532abac3deeb88337cb17dff75529bdf7d35b6，及两份当前解释源码。未打开原 motion/drive/summary/transitions，未执行 reader/World/数学重放。facts_v1.json 保留 literal aggregates、四个精确样本指针与原 rational 显示区间；小数仅方便阅读，不用于重新准入。

## 确定的拒绝链

固定 `[44.72,49.72)` 的250个 tb3 正 effective-v/零 output-v 决策中：

- 223条 `linear_brake_preserve_requested_turn`：实际 rejected X 在 `decision.component_filter.rejected_transition_checks`，tb1通过、tb2的 map/raw 全部不通过；返回的 `reach_pair_checks` 是**当前D**，两 peer 全通过，不能误读为 X 已通过。
- 27条 `reach_transition_envelope`：没有 component_filter；`decision.reach_pair_checks` 自身就是 prospective X，tb1全通过、tb2 map/raw 全不通过。第一个为46.18s/decision2184/原L84270。
- 两组 actual 检查中 `legacy_hard_gates_passed`、`common_world_odom_calibrated`、map/raw `reported_normal_defined` 全 True。没有缺 peer/未知请求导致这250条拒绝的证据。原审计/实际 unsafe 结论仍不由此 descriptor 授权。

首样本44.72s、decision2111、原L74325、lineSHA d9e4acd2058cd557cad8d1636e35f61ee53545c8b4de837dc5ae8b616c67b54b：raw/effective `[.0578947368,.2052631579]` → output `[0,.2052631579]`。tb3自身 intent D、tb1/tb2收到的 intent也为D。

| tb3↔tb2，同一原行 | map距离m | raw距离m | required centre distance m | squared slack map/raw m² |
|---|---:|---:|---:|---:|
| 返回当前D | .64102856 | .63344985 | .57130000 | +.08453392 / +.07487502 |
| 被拒prospectiveX | 相同 | 相同 | .73090000 | −.12329720 / −.13295610 |

四个保存样本（44.72/46.18/47.20/49.70s）的 tb2 X 左侧 direction mode 均为 `nonnegative_dot_full_L`，longitudinal=`18/125`=.144m、support显示区间包含.144；tb1相应为 `original_nonclosing_zero`、support0。四样本 tb3收到 yaw约.982–1.081rad。这里仅四样本模式，未假装提取了250条完整方向模式。后两个精确指针为decision2235/L90414和decision2360/L104764。所有250条不通过的计数来自 descriptor 全窗口 aggregates，不由四样本外推。

源码 `mr3_reach_runtime.py:496–521` 确实在D收到非零v时先提议X并检查pair；若X失败而当前D/w非零且D检查通过，只保原w、压线速0。`mr3_reach_support.py:55–121,142–158` 的非负投影分支给原L全上界，再用 base+两侧support 与中心距离平方比较。日志中的 `geometric_necessary` 在该版本是历史字段名，语义仍是**声明 Reach 集合条件下的充分分离准入**。失败不证明真实将碰撞，也不证明数学有bug；当前记录只说明原证书不能放行这种 prospectiveX。常量/R/STOP债务、raw/map AND、所有原physical界均不改。

## 单一有依据的后继层级与取舍

1. 新族保原 per-robot AND joint True 动作集合；将“对每个 peer 离开方向的最小归一化 dot”作为路径长度之前的**软输入排序**候选，不恢复 nonapproach 硬筛选、不把方向当安全证书。它针对已观察到的 tb3→tb2 X 全L投影，而不是为了凑较长数字。Root提出 action712（tb1南/tb2北/tb3东）的动机可进入人工候选比较；本报告没有重新读V72/证明712未来合法，也不声称目标向量等于 Nav2 真实 pathheading。
2. 仅换 rank 并保32秒同步窗口仍可能失败：V72 tb3近正前候选2仅约.3967m，可能在原accept+5s前自然SUCCEEDED；当前action56另一候选也只有约.4678m。不能为此延迟真实terminal或提前WAIT。新族若采用自然暖身，须提交前明确暖身0credit，真实自然terminal及原revoke/stop-ready/grant接续后再开始新的qualifiedGOAL。各机器人独立推进两次qualified链，不因另一台较慢共用初/次轮绝对窗口。
3. 两项属于同一个显式新 workload 的输入安排，原协议/authority/Reach执行层保持。实施前固定有限暖身次数、总步数/时长、各机会和失败截止；不把qualified早终态改列暖身，不无限试到成功。每机仍两次实际GOAL→满5s且same active owner的合法movingWAIT(v>=.08/本GOAL新增path>=.05)→真实cancel→三fresh rest+3s handoff→新GOAL；额外暖身全部18stream/physics/full/authority审计，0qualified信用不能隐藏任何违例。

最小软件接线位置已经独立封在 `/tmp/mr3_p2a_async_probe_implementation_map_v1/MAP.md`：旧masked-v1行为原样、新producer三函数/固定token、独立每机生命周期重建、新长度的V17/full eligibility精确适配、实际9probe/12authority/12EP30roles合取。没有理由现在改D/X条件、人工旋转命令、刷新anchor、servo rearm、放宽5s/停车界或读drive寻找正平移故障。

剩余明确未知：新排序产生的实际Nav2路径方向；原mask在暖身后是否仍给机会；完整几何是否能在任一真实heading放行X；自然完成/stop-ready交棒是否在有限上限内完成；后继goal能否活过5s并出现.08/.05；同freeze完整资格与预算/容量。V74是描述PASS，原V71 native FAIL不改，P2A/科学/容量信用均未增加。
