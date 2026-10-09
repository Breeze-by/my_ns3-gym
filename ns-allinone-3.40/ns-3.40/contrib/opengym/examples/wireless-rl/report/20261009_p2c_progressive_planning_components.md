# P2C.1 v35 分层集合与惰性视觉规划组件 PASS

v34冻结08fe5f7的四个原开发任务整体FAIL：forced269.7秒COMPLETE且每机charge1；lab77.5秒、corridors82.4秒已检测，却FOUND timeout300.1/300.4且RALLY未进入；rooms EXPLORE timeout300.3、仅一个Nav2。四格0接触/耗尽/failed/infra/retries，48独立子门PASS，不能替代原生成功。全部owner/observer退出0、关闭后才修改。17正式/2物理/917从未调用；旧原格不重跑或回填，完整原始证据见20261009_p2c_v34_failed_development.md/.json。

先实测等价后缀原型，原完整464名义选位保持，但corridors静态输入仍约4.1秒；于是显式改变候选策略：先使用原72个三圈样本，找不到完整可行分配才扩展到原0.4米bin angular代表、最多464。每层仍执行原known-free/LOS/.45米endpoint/.8米分离，以及完整contact return、observer保护、charge/wait/cap预算、soft exposure/parked-body评分。第一层有解即停止，所以放弃跨全部464的软成本最优性；没有宣称穷尽联合可行或最坏时限。后续实际每条导航仍原body/route/TTL/完整预算检查。测试专门覆盖粗层分离无解、粗层完整返航能量不可行、双层无解和粗层有解但细层软成本更好时的明确取舍。

共享reverse predecessor树的公共返航后缀只保存原逐点路径，不简化；field已有内容/shape/resolution/origin/home/radius校验，变更会清缓存。缓存最多2048节点、每个共享tuple最多2048原顶点，包括长迷宫约束；contact-connected mask仅同field复用。不缓存source/header/能量或可行决策。冻结v34原known_return_route源码以SHA夹具独立重算八随机图共768起点，精确距离、每个顶点与不可行结果相同；可变alias/content/home变化、长路径与邻起点后缀命中减少重复生成通过。连续局部占用veto及物理安全代码没有修改。

已知空间/视觉候选先用同一当前interest矩形数量作私有SearchGainBound；竞争时计算原360射线/16yaw准确gain/yaw，再回到原稳定budget heap。输出恢复普通Viewpoint/Assignment，任何预算、Nav2或充电forecast都不使用上界。候选池须先证明至少一个准确positive gain；全零仍返回原空池并走原mapping fallback。八随机种子×两类interest验证全部候选、准确朝向与排序等价，实际保留晚期14heading/5visit条件输入保持原派发、偏好和预算；同一admission/充电context使用同一地图/历史缓存，不能续租或跨源。

过期proposal已不可逆弃置后，既有private consumed audit每phase/stage最多每30sim秒保存冻结callback的交付图、source stamps、机器人状态与访问/朝向历史，补足rooms弃置现场。该数据只供只读诊断，不进入规划/通信准入/本地安全，没有增加应用网络packet或延长TTL。测试对有/无rally状态、map解码、原时间戳、限频和零派发/owner保持通过；同步审计仍有有限计算开销，不能当实时界。

| 固定输入条件 | v34中位wall秒 | v35中位wall秒 | 关系 |
|---|---|---|---|
| early2 | 0.22162 | 0.22000 | 派发/朝向/偏好/预算逐项相同 |
| rooms3 | 0.17532 | 0.18959 | 派发/朝向/偏好/预算逐项相同 |
| late_visual | 0.32949 | 0.24974 | 派发/朝向/偏好/预算逐项相同 |
| dev_lab101 | 1.62600 | 0.78087 | 与冻结旧优化器限制到同三圈候选的完整解相同，跨464选择改变 |
| dev_corridors303 | 4.83272 | 1.31805 | 与冻结旧优化器限制到同三圈候选的完整解相同，跨464选择改变 |

普通early2几乎持平，rooms首图略慢，尚不能证明后续停滞原因；不把所有条件写成提速。映射/视觉五cold、集合三cold，固定真实保存图/epoch与条件owner，不是原history或真实时钟界。集合lab/corr从约1.63/4.83降到.78/1.32秒的组件样本，仍必须在新完整原任务验证。

1348功能检查PASS70.86秒，四包build5.20秒，171保护/4授权/54静态协议/8中央+2native Future注册PASS；实际隔离ROS domains220 clock、221 native Future、215原视场、214两个普通mapping Assignment、216一个准确visual Assignment、217两组三机分层集合publisher/独立consumer PASS，全部绑定本source SHA。后四类使用保存的固定交付输入/合成goal sink，没有真实Nav2/Gazebo运动或时钟界。初visual sink错误kind触发正确独立reader FAIL，修正为生产同标签后PASS；原脚本/trace保留，reader与task代码没为此改动。首全功能1344PASS/1FAIL仅测试读取消失/proc ESRCH，修正两个明确不存在异常并验证权限错误仍可见；生产observer_lifetime未改，六定向和完整全量PASS。

旧四原任务48子门结果和细节逐项保持：old rally_assignment由其08fe冻结源码重建，其余reader/native geometry使用当前等价助手重审；不是把旧完整464记录套到新分层策略。Native battery/Future dispatcher/TF sampler/launch/observer/strict gate/视觉reader byte保持；类仅__init__添加限频状态、assign_idle_robots与既有forecast解析改变，三pure函数修改、三private定义增加。原300秒/.35米/.05mps/.1radps/5秒保持与2/5/60秒TTL/SLAM/Nav2/physics、全部case和真实断网刺激保持。

P2C.1未完成。下一新clean pushed freeze仍先forced2原生COMPLETE、每机charge≥1，再其余三个开发；全四通过才进入17正式+2物理，917最后首次暴露。P3C.5已验收；无P4/ns-3/Wi-Fi/RL。

提交前cached diffcheck最初拒绝三份新增测试的EOF多空行，未提交；仅清理末尾空白且AST相同，34项相关检查再次PASS，生产source SHA/功能证据不变。
