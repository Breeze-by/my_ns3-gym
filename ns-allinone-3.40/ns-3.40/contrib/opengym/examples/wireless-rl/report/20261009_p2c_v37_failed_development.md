# P2C.1 v37 首强制原任务 FAIL

冻结73fb1606d4976c7d3300fcd1c85105e12bab7297，control SHA3297194381fe74d095625c27a71c2838f754c4fc081f69b4556b91453dc7407b。原任务EXPLORE timeout300.1s，未确认目标；success=false、completion_time=null、native_rally_hold_proof=null。原生Nav2计数26，中央25决策(19mapping/6visual)；两机各charge1、最低8.340687732012016，零接触/耗尽/failed机器人/任务期infra/retry，owner/observer exit0且已关闭。全strict FAIL、277 live和12独立审计PASS不能代替任务成功。其余3dev/17formal/2physical/917未调用。

62次来源租约弃置(47candidate_generation/15candidate_budget)全部保留。tb2充电后停在(.2859,-.2568)，距自己充电点(0,.45)约.7624m，小于原.8m接触半径。原本地SLAM地图将当前位置单元标为100；融合图单元0/接触距离0，但连续本地障碍校验拒绝该融合路线，constrained_fused也无路线。不能为了放行改写占用或放松已知返航保护。这是被交付地图限制的真实决策，不证明物理墙体存在，也不证明其由某一动态障碍唯一导致。

原tb2返航从(.376,-1.423)于2159.582发送已规划接触目标(.273755673,-.076247627)，但进入原半径后提前取消，return_finished记录cancellation_count1。后半程只有tb1继续大幅探索；tb1/tb2真实路径分别36.38865/7.80898m。最后两份准确弃置输入的固定epoch完整计算约.79–.83/.68–.70wall秒，超过当时仅.502/.303秒剩余租约，且按原几何完整重建仍无法为tb2派发。条件CPU不是原时钟/完整history回放或唯一任务因果。

所有source/command/graph/ledger/安全原始数据和严格失败、准确snapshot逐字原ledger绑定与12详细检查见JSON/gzip。原300s/5s、2/5/60s TTL、占用/储备门槛未放宽。后续候选仅让已接受接触航段结束再进入CHARGING；可能仍受Nav2位置容差与地图占用影响，必须重新clean pushed freeze及新原任务验证。P2C.1未完成；P3C.5已验收，无P4/ns-3/Wi-Fi/RL。
