# P2C.1 v22 首个真实补查派发 FAIL

冻结 `89ee853151d45ae5dbe604f00ccafa8b522c7eb9` 的dev_forced2：真实补查目标group35680在私有导航决策JSON中仍为NumPy int64，序列化抛TypeError、control退出1。原launch第223行在第227行owned SIGINT之前，属于一次任务期间基础设施失败；外层owner/observer最终0自然关闭不能掩盖该失败。原EXPLORE timeout300.4s，无检测/集合/原生完成，充电次数1/0、最低11.548989，零接触/耗尽/机器人失效。其他三开发、17正式、两物理和917未调用，无重试或回填。

原strict gate FAIL及trace完整保留，未来只读子进程退出检查对同原launch单独重读也FAIL。独立输入检查仍PASS：3closed返航/2map预算/4pose租约/1本地腿/1charger return、121能量样本、两条原普通探索；第一条补查在JSON发布之前崩溃，没有有效私有补查记录，不能声称算法任务已验证或两机器人强制充电通过。原数据与命令/配置/源码/输入SHA、完整图、trace无损归档。

未来修复仅把候选网格行列转为Python int，不改坐标、收益、成本、能源、源龄、净空、Nav2、300s/5s或物理刺激。增加实际发布入口及DDS接收/独立读者验证，不使用通用JSON默认转换来掩盖类型错误。失败原格不重新运行替代。P3C.5已验收，无P4/ns-3/Wi-Fi/RL。
