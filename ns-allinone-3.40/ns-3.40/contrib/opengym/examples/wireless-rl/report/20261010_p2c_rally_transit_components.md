# P2C.1 同伴观测支持的中间腿朝向组件 PASS，完整任务仍待新冻结

原v47首forced RALLY300.1timeout、两机各charge1、零接触耗尽failed；末tb2仍运动、原生5秒保持未完成，严格FAIL保留。[原失败](20261010_p2c_v47_failed_development.md)的14独立子门PASS不能替代任务成功。中间点转向目标后再转回前进方向是诊断线索，没有用重跑或修改原数据制造反事实收益。

新普通RALLY中间腿仅在另一台ACTIVE同伴已到位且动作空闲、原位置/速度/FOV/已知LOS合格、该同伴自己的已交付目标确认在原5秒窗口内时，保留原路线入射yaw。最终位、量化最终格、返航让行、充电准备与失效支持仍走原朝向。各已知机器人的原确认source与实际相机metadata保留；最新全局确认由接近机器人发出也不会遮掉同伴仍新鲜的确认。原目标接收/版本/未来/改变目标拒绝规则保持，不续源戳，不增加应用观测流。

原同伴5秒确认作为额外最终派发deadline；准备/编码/private发布期间过期仍撤销，零未发送owner/尝试。独立读者同时重建当前geometry/yaw/速度/相机与原始已消费同伴receipt，不借全局60秒目标lease替代5秒观测支持。所有完整路径/身体/在途预约/去返能量、300秒及原生5秒保持均原样。

最终实际DDS输入/时钟/目标消息接收与ActionServer/Future：停驻tb2原确认10秒、接近tb1后来原确认10.1秒。旧版中间点发90度、新版保留26.565度原入射朝向；到15.1秒，tb2确认5.1秒失效，新版恢复90度。两个原确认source不续租，两个真实结果Future均消费后关闭。目标消息是声明的合成上下文，无Gazebo/真实Nav2任务，不作因果加速、通用安全或硬件最坏时限保证。

最终1733功能PASS168.70秒，最终56读者/接收/状态反例PASS，早期完整接口394与补强424PASS；四包5.32秒，190保护/6既有明确授权/54协议与两manifest声明PASS。仅4中央方法修改+1新增，其余76与全部纯函数/native battery/action queue/TF ingress/SLAM/Nav2/SDF/URDF/Karto/原case及物理刺激保持。首范围夹具FAIL与第三DDS QoS不匹配FAIL保留；中间单最后观测者版本在任务前被改进，其a144590完整源码SHA核验保存，1730功能与runtime1/2单独保留，均非任务结果。

所有实际owner/组件DDS关闭后编辑；SHA/原件/代码/所有验证stdout在[JSON](20261010_p2c_rally_transit_components.json)与同名provenance压缩包。新v48须clean committed/pushed同源4开发→17正式+2物理全审；917未暴露。P2C.1仍未完成，P3C.5已验收；无P4/ns-3/Wi-Fi/RL，actual airtime/J和容量未测。
