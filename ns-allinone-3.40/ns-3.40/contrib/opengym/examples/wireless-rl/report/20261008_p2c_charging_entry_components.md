# P2C.1 v6 统一充电入口恢复保护（2026-10-08）

**850功能PASS/1skip、四包5.46秒、172保护文件/54协议PASS，待新冻结完整任务验证**。统一begin_charging先恢复已负担的初始缺姿态等待，覆盖快速odom和timer两入口。实际DDS domain209分别覆盖源领先clock的有界暂存和clock已成熟TF先于odom；两顺序都保持charge0、原source戳和单次能量结算。新增只读反例正确拒绝v5原两次起点补电，同时允许真正不足预算的站内充电。详见[JSON](20261008_p2c_charging_entry_components.json)。

第一组夹具3失败/114通过：直接callback夹具误假设不同DDS topic的先后顺序，改为等真实TF交付后再发布odom；两负例缺map_age_sec，修正夹具。完整850通过。validate-only初调用漏case/domain/port仅参数解析失败，完整参数预声明通过，无任务重试。原v5 nativeCOMPLETE251.1但起点补电的整格FAIL和全部原始证据保留；不以它替代远端低电量验证。新4开发/17正式/两物理blackout尚待运行，917未暴露。原300s/5s/TTL、预算、保留失败原则与accepted P3C.5保持，无P4/ns3/Wi-Fi/RL。
