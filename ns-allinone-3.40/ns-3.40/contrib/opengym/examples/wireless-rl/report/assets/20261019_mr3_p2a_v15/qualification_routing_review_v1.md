# 新profile资格路由只读评审（V15）

本文件由root根据collector_design对当前实际代码的独立只读评审整理；不是原生实验或科学通过回执。
当前两个新reader仅为必要叶节点，完整新profile资格入口尚未接通，PPO明确拒绝。

| 部分 | 可复用的原数学 | 新profile尚须接通的入口 |
| --- | --- | --- |
| full | contact/scalar/evaluator/archive/activity | audit_preparation、audit_motion、controlled readiness/physics v2汇合 |
| information | 原独立odom/TF投影 | 已实现新完整safety reader，不能剥字段调用旧PASS |
| peer/control | 精确cloud/scan及原偏序/FIFO数学 | 旧入口锁v1与decision，新版须消费v2/reach_decision与完整表 |
| drive | paired slew、SDF及target/storage/actuation数学 | 新profile实际receipt、六源身份、对应v2 status |
| settled | legacy原数学 | 新profile由独立reach runtime替代，不宣称旧L1门通过 |
| cadence/FIFO | 20ms raw/34ms轮与实际FIFO数学 | 新kind、v2状态及完整guard选择覆盖 |
| input | 原v4 actor/candidate/map/tensor重放 | 必须与新完整信息角色合取，未读safety不能代表它已验 |
| angular/physics | 原raw角速/完整停止及pooled覆盖 | 同新冻结重新实采；缺覆盖不能豁免 |
| custody | PID/start、alias/maps、祖先、真实wait与关闭 | 第六compiled_drive_feed_sha256和实际新ELF绑定 |
| 参数读回 | 九节点与gentle-turn精确值 | 旧底层status-v1 release检查须显式v2入口 |

当前benchmark明确拒绝reach加旧preparation/参数profile，preparation.py锁旧角色/argv，audit_ppo pin旧资格。
这些阻断有意保留，不能把旧38/38或旧source信用移过来。

后续最小DAG：新profile preflight/清洁冻结/实际ELF六源/参数/预算 → watcher ready → 单次native实际wait → watcher实际wait → 全部旧不变数学叶与新版drive/info/peer/control/reach/cadence/FIFO → 新full汇合 → FIFO manifest/strict custody closure → coordinator退出后的独立final absence及完整尾账 → 新schema资格 → 才可连接新的最小PPO链。

每一个已提交子任务真实wait，失败停止后续且保留已返回prefix、未知和缺失；完整新源/契约一致，不能跨冻结拼矩阵。
本V15交付是生产接线及CPU/build准备，不把未完成资格路由说成可运行或已通过。
