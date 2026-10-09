# P2C.1 最终导航派发租约组件 PASS，完整集成待新冻结

v46四格原生完成但rooms一次2秒位姿TTL超期，完整FAIL原件保留，不能用完成结果代替来源协议正确。证据见[原失败](20261010_p2c_v46_failed_development.md)。

最终四类导航入口在目标、几何旁证和较重JSON准备完成后，用持续前进的真实时钟核验原始源戳；轻量metadata编码后再检查，private审计发布后过期/时钟回退/关闭则撤销，不发送动作、不消费尝试、不留下pending所有者。普通探索撤销还清理未发送的目标和路线。新命令header取当前准入时刻；任何观测源戳与原2/5/60秒TTL均不续租。独立读者从原始source/TTL重建最早deadline与撤销原因，仍保留原全账本严格TTL门禁。

真实隔离DDS、双worker串行状态与真实ActionServer/Future在日志和审计发布两个受控延迟点对照冻结1a6bed8与新代码。源保持10秒，clock进至12.1秒，旧两格各收到1个过期动作；新两格各0个过期动作/零pending/零尝试，实际收到12.1秒新输入后各收到1个新动作。最终结果Future均消费完后关闭。合成已知自由图，无Gazebo/真实Nav2任务，不称任务因果收益或硬件最坏时限。

511定向PASS44.12秒；完整1687功能PASS159.75秒；四包构建2.77秒；190保护/6既有明确授权/54协议PASS。仅5中央方法修改，其他75方法AST与全部纯函数保持，native battery/action队列/TF ingress字节保持。两manifest仅增加事先声明的private派发边界与读者source绑定；所有原case、seed、物理刺激、300秒任务与5秒原生保持不变。首4个夹具FAIL、首DDS错误key、第二DDS逻辑通过但收尾异常原件都保留，不用它们代替最后干净证明。

全部实际v46 owner/observer、组件DDS关闭后才编辑。完整来源、原失败旁证、代码快照、命令stdout和声明均在[JSON](20261010_p2c_dispatch_boundary_components.json)与同名provenance压缩包中。新v47须clean committed/pushed同源4开发→17正式+2物理全审；917仍未暴露。P2C.1未完成，P3C.5已验收；无P4/ns-3/Wi-Fi/RL，actual airtime/J与容量未测。
