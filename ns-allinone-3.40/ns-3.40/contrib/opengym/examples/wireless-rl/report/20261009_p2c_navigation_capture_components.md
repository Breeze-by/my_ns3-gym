# P2C.1 精确原始导航输入记录

70定向功能/171保护源/54协议PASS。仅只读评估观察器记录local、交付fused、Nav2全局/局部地图与updates、原scan/odom/TF/static TF/plan的原始CDR，附receipt sim/wall，不改header，不发布控制输入。新的source摘要、命令、完整gzip与关闭计数受审计绑定。

实际DDS验证了非有限激光值保留、晚加入static TF、原CDR字节可逆与无机器人/融合地图发布。原三次夹具/配置失败完整保留：best-effort迟订阅TF无历史→改可靠transient；CDR padding并非canonical；Python .05经ROS float32编码。最后70PASS包括原始摘要、命令、source、关闭、不全topics、CDR篡改拒绝。任务源及模型/SLAM/Nav2参数未改。

新诊断run-id20261009_p2c_v42先运行原dev_forced2；300秒/5秒/native完成/全部TTL和安全阈值不变。旧v41与所有失败保持，本组件不代表P2C.1完整任务已完成。
