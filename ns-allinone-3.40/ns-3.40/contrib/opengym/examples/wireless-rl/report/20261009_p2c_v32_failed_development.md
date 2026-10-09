# P2C.1 v32 首原开发 FAIL

冻结0972eec6561b92efb55b195a07b0716d3aca114b，2026-10-09T05:33:25.613406..05:40:06.743930UTC。强制二机原任务300.0秒EXPLORE timeout，无目标发现；6个实际Nav2 goal（5中央探索/1本地返航）、两机各charge1，最低13.4646764，零接触/耗尽/failed机器人，owner609588/observer609606退出0，所有owned关闭后才编辑。严格首格FAIL，后3开发/17正式/2物理/917从未调用，无重试/回填/原300秒、5秒或TTL放宽。全部原始结果/source/config/command/environment/ledger/metrics/native图/关闭和SHA归档。

十二独立检查PASS：4闭合返航/2地图预算/5位姿租约/1local腿/2charger returns、120能量、5探索（3视觉补查/3接续）证据。125次规划因原source+TTL到期而弃置，其中candidate_budget96/route_admission11/dispatch15/candidate_generation3。只读组件提速不等于任务通过；这也不是远端断网返航或硬件保证。

当前完整候选集先逐个预算核验，再进行派发，仍使多个初步有效候选随同后续预算计算一起过期。下一候选可用原utility与最高continuation倍率作安全上界，按上界逐步完成原能量/relative/diversity评分，只有已核验候选优先级超过所有未核验上界时才进入同一route/body/full-budget/lease派发路径。固定source/epoch应与原greedy顺序及选择一致；真实输入仍必须新冻结任务验证，不续租、不把未核验候选派发或丢失请求回填。

P3C.5已验收，P2C.1未完成；无P4/ns-3/Wi-Fi/RL。
