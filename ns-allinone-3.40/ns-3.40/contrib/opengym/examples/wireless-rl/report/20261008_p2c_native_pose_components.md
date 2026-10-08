# P2C.1 v4 本地位姿源龄与充电证据（2026-10-08）

**840功能PASS/1 skip，四包构建与172保护文件/54协议格通过；待新推送冻结和任务门禁**。完整路径算法保持v3；新增本地native odometry/TF源龄检查，源TTL均沿用2秒。map仍5秒、任务300秒/原生保持5秒与原安全余量不变。证据与源SHA/原始stdout/新manifest见[JSON](20261008_p2c_native_pose_components.json)。

独立组件反例显示旧f637f64即使native pose source age111秒且map新鲜仍能给有限预算。新候选拒绝缺失/过期/未来的odometry或TF；重复/倒序/未来样本不会替换最新源，也不按收到时刻续租。TF generation source与gateway采用同一实际SLAM `transform_timeout`：launch把已读取配置的offset传给battery，native TF原有效时间戳不改。最新TF到达后，用最新已接受odom重新计算地图位姿。预算计入max(odom_age,frame_source_age)的运动/时间余量，保存两源时间与offset供重建。

过期姿态不能声明充电接触或累计稳定充电时间；已有充电保持并暂停稳定计时，仍受原60秒充电超时约束。本地失路/缺姿态先停止和有界等待30秒，缺姿态显式 `battery_return_pose_unavailable`，地图不可达仍 `battery_return_unreachable`，不会生成几何替代预算或盲返航。实际ROS synthetic fresh-map/stale-frame与disconnected-map两个独立DDS/clock/Nav2 action组件均正电量失败、零Nav2 goal；它们是接口组件，不是Gazebo物理返航。

第一次定向106PASS/3.82s，补充实际过期帧DDS变体及严格读者后完整840PASS/1skip/22.21s、最终四包5.48s；所有日志保留。读者额外拒绝pose age/stale odom/future TF/missing源字段篡改，历史v3不伪造新pose证据。v3首forced独立原格COMPLETE287.5/charge2/min9.385784已完整保留，但不能代替v4新源码。新4开发/17正式/两真实blackout仍须同前瞻规则执行，917未暴露，未启动P4/ns3/Wi-Fi/RL。仿真距离/时间能量单位不是joules；这些包络仍要求校准速度/偏离/停止与有限恢复，不能推出无限阻塞、坏执行器或未校准硬件的一般保证。
