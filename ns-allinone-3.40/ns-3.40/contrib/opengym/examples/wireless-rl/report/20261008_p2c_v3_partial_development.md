# P2C.1 v3 一个独立开发原格（2026-10-08）

**首个 forced 开发格 PASS，完整开发/集成门禁尚未完成**。源码冻结 `f637f64ce0054b9554bc34030d67f731dcdf77b6` 推送后只运行lab2/303/E18；原生COMPLETE287.5s、两机各charge1、最低9.385784，零接触/耗尽/机器人失效/infra/retry。owner和observer exit0/无升级关闭；完整协议/时序/graph/live269快照、原地图预算和实际返航成本通过，精确命令/实际环境/每原始SHA与严格partial gate见[JSON](20261008_p2c_v3_partial_development.json)。

两实际返航0.805016/2.353636m，预测误差-2.396769/-3.733164。原生5秒保持已验证，不从中央到位信息推断成功。new two-frontier机会充电分支仍0，不能宣称其物理触发或因果提速；此格只能验证该控制SHA的任务回归。完成余量仅12.5秒，无最坏时限保证。

其余三个开发、17正式、physicalblackout与917未执行。关闭后复核发现本地完整预算未明确检查native odometry/TF源龄（新鲜map仍可配过期pose）；新v4将补齐这个独立安全边界，再重新冻结整个4开发/17正式/physical协议。此处不把未运行格补为PASS、不把原forced结果重复当新实验；v1/v2失败和所有原raw保持，P3C.5已用户验收，无P4/ns3/Wi-Fi/RL。
