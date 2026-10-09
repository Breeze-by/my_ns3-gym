# P2C.1 v36 首强制原任务 FAIL

冻结7a7fde63f0be9e75ce6e3f59899c956c709dd0b2，control SHAbf09ab831a02c6f069aa354d82234715849c23a32e096d94e158cb3d4345dd28。首required forced2在249.9秒确认目标、251.7秒进入RALLY，300.4秒仍未原生完成；success=false、completion_time=null、native_rally_hold_proof=null。28个原生Nav2计数，中央22次探索(10mapping/12visual)+5rally；二者是不同采样/路径计数，不能混为同一数字。两机各charge1，最低6.940767563292112，零接触/耗尽/failed机器人/任务时子进程失败；owner/observer自然exit0并已关闭。

中央完整选位耗时.809wall/.7sim秒，本次选位计算已完成；tb2检测时在另一侧，原RALLY只剩约48秒。原控制下51次planning lease弃置(29generation/19budget/3route)仍存在，原输入显示两机空闲、tb1约73/tb2约8能量、87条预测朝向历史；固定epoch重建会请求tb2充电，但全轮约2.4秒超过原1.3–1.5秒剩余lease。它是条件计算瓶颈证据，不是原轨迹唯一因果。

十二独立native return/energy/charge/AP veto/探索/集合/来源/进程/nativeTF审计PASS，首required strict仍FAIL；后三dev和正式17/真实物理2/917从未调用。原task300秒、真实5秒保持、所有源TTL与安全门限不放宽；无任务重试或原成功回填。任务结束后的两个Nav2 lifecycle manager按原launch关闭升级至SIGKILL，退出-9；原日志完整保留。此为post-task child cleanup，不能写成全部ROS children自然干净退出；原owner/observer退出0，task-time child exit审计PASS。

P2C.1仍未完成；P3C.5已验收，无P4/ns-3/Wi-Fi/RL。下一候选须重新clean pushed freeze并从新首强制原任务开始。所有完整命令/source/evidence SHA与原ledger逐字snapshot绑定见JSON与gzip旁证。
