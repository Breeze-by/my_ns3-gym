# P2C.1 v37 预算评分上界组件 PASS

v36冻结7a7fde6首forced原任务FAIL：249.9s检测、251.7s进入RALLY、300.4s超时；两机各充电一次、最低能量6.940767563292112、零接触/耗尽/failed/任务期infra/retry，12独立审计PASS不能替代任务成功。owner/observer关闭后修改；两个post-task Nav2 lifecycle manager被SIGKILL/-9，不能称所有子进程优雅关闭。原始失败和严格检查保留在20261009_p2c_v36_failed_development.md/.json。其他三dev、17formal、2physical、917从未调用。

三份准确弃置EXPLORE输入中有87视场历史，两机器人idle，约73/8单位电量。固定原epoch完整计算会请求tb2充电、所需预算约15.29/15.35，但原条件计算约2.4秒超过1.31–1.51秒剩余来源租约。只按当前位置hold预算的首原型没有改善，已保留并拒绝。最终采用当前模型和原source ages下的接触圆盘直线距离，分别作为完整任务+返航以及当前返航储备的能量下界，从而给准确battery factor一个更紧的上界。该直线下界只决定计算顺序，不证明路线可用、不替代已知地图完整接触区路线或真实能量准入。

每个原refinement pass只有全部raw options都被证明unfunded时，准确找到最高可行充电意图后，才可停止该机器人更低优先级选项的预算计算；任何可能funded的替代、下一refinement以及完整raw充电lookahead池仍保留。昂贵价格结束后立即再检查原租约，过期则撤销全部暂定计划。原公平串行充电、body/accepted reservation/完整距离/源TTL/派发保持。

32项新增检查独立使用冻结7a原assign源码/SHA；三份原输入的预算、充电对象、原stamp、临时搜索选择逐项一致；三种改变电量的条件反例覆盖funded替代不丢失。12种种子各80组模型/曲线/更晚source ages证明计算factor上界；无效或缺失模型/过期年龄给中性上界1；未知地图仍不能准入；计算中来源过期即使返回高价也不进入heap或请求。第一次full18失败源于直接读取电池开关破坏原精简fixtures，修正生产入口getattr后原测试保持，不放宽门限。

| 保存输入 | v36中位wall秒 | v37中位wall秒 | 原来源剩余秒 |
|---|---|---|---|
| charging_candidate_generation | 2.58269 | 0.97142 | 1.51200 |
| charging_candidate_budget | 2.52851 | 0.95625 | 1.51400 |
| charging_route_admission | 2.50194 | 0.96536 | 1.31200 |
| dev_lab101 | 0.79454 | 0.80785 | 1.34400 |
| dev_rooms202 | 0.66918 | 0.69106 | 1.59100 |
| dev_corridors303 | 0.62194 | 0.63936 | 1.40600 |

五次交错cold、新缓存/固定原epoch，各完整选择相同。三份充电样本明显减算，三个早期样本略有开销或近似相同，完整数据保留；不是完整history/现场clock回放，也不保证最坏延迟或任务因果收益。

最终1408功能PASS/101.49s、四包build5.38s、171保护/4既授权/54static与8中央+2native Future注册PASS。八项实际ROS包括时钟/Future/视场、mapping/visual/rally、三份弃置输入和三次真实central charge publisher/独立DDS reader；均绑定最终SHA。真实请求与独立旧算法的充电对象、预算和原stamp相同，但隔离fixed epoch不含native battery/Nav2运动。旧v36十二原审计详细判断保持、strict仍FAIL。

AST只有assign_idle_robots改变、增加纯计算上界助手；native battery/dispatcher/TF/launch/observer/strict reader字节保持。所有原300s/.35/.05/.1/5s、2/5/60s TTL、SLAM/Nav2/physics/cases与真实断网刺激保持。新clean pushed freeze先forced原生且每机charge≥1，再另三dev；全四格通过才17formal+2physical，917最后首次暴露。P2C.1尚未完成；P3C.5已验收，无P4/ns-3/Wi-Fi/RL。
