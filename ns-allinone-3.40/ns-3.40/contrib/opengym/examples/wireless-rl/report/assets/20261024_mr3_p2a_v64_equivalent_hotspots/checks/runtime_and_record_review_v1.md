# V64 runtime 与记录快路径：独立源码审查

本结论来自已停止候选的源码审查；不提供新的 World、原生吞吐、资格、学习或容量信用，不重读旧科学日志或解码 pstats。完整候选历史保存在同目录 `candidate_history_v1`，规范安装的首轮导入失败与后轮 CPU 结果保存在 `canonical_history_v1`。两包库存逐文件保留原路径、字节数、SHA、lstat，并以不落地执行的流式恢复核对全部普通文件。

审查候选：`mr3_reach_runtime.py`，31562 B，SHA256 `576c235901a51223f1d2723757f60c490045ba897d445d5c6fb3c739512a466b`；`motion_safety.py`，52034 B，SHA256 `b1aaa465f6fe1c940674b97f347d14840f79d04a3d233be6f143fb06fbbb6b1e`。

## runtime：单调尾键与 pending 逆序短路

四个索引的写入路径维持严格数值顺序：raw 新 source 比前项增加 20 ms，完全相同的重传在插入前返回；calibration 新 source 增加 20 ms、publication_sequence 增加 1，旧同键只有相同内容可覆盖，dict 覆盖不改变位置；APPLIED actuation sequence 增加 1、时钟增加 34 ms，完全相同重传先返回；published decision_sequence 严格递增。全文件的写入路径未发现额外写者。因此这些 dict 的尾部键与原 `max` 一致。

实际 DrivePhaseClient.receive 要求新 cmd_seq 与 decision_sequence 严格递增，source/storage 时钟不回退；最近项的完全相同重传立即返回，旧项或冲突重复失败。consume 用按原 items 顺序的筛选保留幸存项次序。逆序 pending 在遇到首个不大于当前 APPLIED 的 cmd_seq 之前，已检查所有更大序号；此前各项不可能满足原谓词中的更新序号条件。原严格时钟比较保留，同钟项的行为不变。未删证据、改阈值或改故障锁存行为。此有限变更无源码阻断。

## record：普通 JSON schema 域

对于生产当前发出的无环普通 dict/list/tuple 与 JSON 标量，先调用严格 json.dumps 成功时，输出与原 finite_json 后的 dumps 逐字一致。原 finite_json 保留 dict 的键；本结论不声称键被字符串化。NaN/Infinity 触发 ValueError 后仍调用原 sanitizer，保持非有限浮点转 null 的行为。sequence、sim/wall 取样位置与各一次取样保持，输入 payload 不被原地修改。

因此普通 schema 域无安装阻断。任意自定义容器、并发修改、极深递归，以及不支持对象与循环混合时的异常优先级，不属于本次等价结论；不据此声称任意 Python 对象均完全等价。

## 验证边界

候选历史保留 58 项 runtime 与 21 项 record CPU、原 hugeint 自动 fixture-ID collection FAIL 及显式 ID 修正、两个固定人工 kernel 基准和真实 root reap。规范安装历史另保留缺 merge_map 路径的 collection FAIL，以及仅补实际模块路径/环境记录后的 112 项 CPU PASS；生产源码未因该导入失败修改。

pending 4096 的约 98 倍和记录三轮约 3 倍收益只属于固定人工 kernel。它们不证明完整 native 性能、容量或安全资格。P2A 尚未完成，capacity 仍为 False；下一科学活动必须另有同 freeze 的完整资格与学习证据。
