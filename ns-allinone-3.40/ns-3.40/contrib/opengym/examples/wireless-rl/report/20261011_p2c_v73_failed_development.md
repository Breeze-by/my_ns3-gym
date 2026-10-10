# P2C.1 v73 四原开发整体 FAIL 保留

冻结 `d0be454749a80d2d20a4daa4bdc9efe544a1e5f1`。按本冻结声明，四格逐格串行，实际任务不与检查并行。首强制原生 COMPLETE 231.7 秒并 strict PASS；房间原生 COMPLETE 285.0 秒。实验室 RALLY 300.1 秒 timeout；走廊中央 COMPLETE，原生 success=false/timeout 300.4 秒，不能将中央终态替代原生完整保持。完整 strict 两 PASS/两 FAIL；原所有 trace、结果和 source 原件保留。

四格充电次数 2/3/3/2，最低电量 14.916191/21.056135/27.284515/25.363943；零接触、耗尽、FAILED 或任务期基础设施退出。四 owner/observer 都为 0，所属 PID 全关闭，canonical/native 双图各自逐字相同。冻结各 21 子审均 PASS，包括原生完整返航闭合、能量与策略补能、真实命令和地图来源；这些不能替代任务成功。

实验室检测 150.0、RALLY 178.6 秒；tb1/tb3 截止时到位误差约 0.020/0.014 米，tb2 仍 3.060607 米。tb2 第一普通目标距原 native home 1.190119 米，小于原 2*radius=1.6 米；原日志明确在“frontier already observed”条件下取消该目标，未形成真实普通成功。TB1 唯一初始补能请求 61.6 秒，tb2/tb3 在集合阶段补能；tb2 首个最终接近腿直到 248.8 秒。充电方法原本拒绝活动 ordinary 动作，不能将首腿取消归因于补能请求。原成功中间集合腿会重置重试计数，也不能归因于重试记账。

下一候选应验证首个当前近家 ordinary 目标是否可在原身体/地图/完整去返及等待预算充足时继续到真实 Nav2 成功，保留原 timeout/no-progress 和初始补能真实成功条件。另需核对集合预约和合法顺序；所有诊断是原时间线，不是单一原因或反事实任务收益。17 正式、两物理和 917 均未调用，P2C.1 未完成，无 P4/ns-3/Wi-Fi/RL。

[JSON](20261011_p2c_v73_failed_development.json)
