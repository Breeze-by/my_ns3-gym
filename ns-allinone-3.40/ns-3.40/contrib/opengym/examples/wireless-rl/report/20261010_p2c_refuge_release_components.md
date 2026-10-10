# P2C.1 充电清道避让的顺序释放组件 PASS

[v50四原整体FAIL](20261010_p2c_v50_failed_development.md)保持：forced/rooms/corr原生完成，lab300.1秒RALLY超时。lab充电后tb3在临时清道点等待ACTIVE的tb2先离开；tb2先走集合前缀再让行，tb3才恢复最终目标。新组件处理这段先后等待关系，不修改地图或物理。

只有全部机器人ACTIVE、零充电请求/普通导航awaiting Future、集合pending/活动动作及重获扫描pending/活动动作、refuge已原导航到位、所有当前输入和目标鲜度合格时，才评估提前释放。当前完整地图安全顺序必须让refuge机器人先行；按当前所有机体位置核验其完整最终路，再以其假定最终位置作为机体约束核验返充者的完整路。两机均重新按原完整contact返路、保持5秒、原等待预算与源龄报价，并另保护当前位置的返航预算。任意缺图、缺最终目标、占用起点、完整未来路被堵、低电量、非法等待或2/5/60秒TTL过期均继续等待。证据序列化/发布前后复核原输入源龄；仅恢复final元数据，后续普通实际动作仍须当前身体、返航、完整能源和最终lease边界重核验。旧返充者已经持有预约动作的释放分支保持。

新增私有eligibility记录保存原图、位置、两条完整顺序路、原电量模型/等待/源戳。独立读者重建路径与两个完整contact返航候选，另以原能量公式独立计算预算并绑定原CDR地图。它证明释放时的条件几何与预算，不宣称未来执行持续连通或已完成任务。未新增AP应用数据流。

原lab条件组件：原完整冻结旧源码继续等待，新恢复tb3；完整所需预算tb3约34.246668、tb2约30.392071，原native记录约79.09/79.98。三份地图严格绑定原CDR。两机精确TF原CDR缺失，位置使用相邻原private诊断；电量使用决策前最后原native energy_accounting样本并显式标记其源，不伪称原AP电量快照。因此不是完整原回调回放、任务反事实或实测时间收益。更换候选细化条件对lab无效、时间评分提前仅约1.456秒名义差，均未采用。tb1成功后偏转成因仍未知，原Path保留请求yaw，没有调整Nav2/SLAM/物理。

真实DDS输入map/odom/TF/energy，完整冻结旧e8af控制器保持refuge、零goal；新控制器恢复先行者并通过原派发检查向合成ActionServer发一个普通goal，真实Future闭合。clock13后原源10过期，没有新增goal，全部owned节点关闭。合成完成refuge状态和target不是实际Nav2运动或原生任务完成。

1799功能PASS（原stdout记录实际时间），定向69PASS3.39秒（最终功能集合另含缺最终owner反例），四包7.26秒、190保护/6原授权/54协议及两前瞻声明PASS。只修改一个中央方法、增加一个中央方法，80其他中央/98纯AST一致，native battery/action/TF/SLAM/scan/Nav2/physics字节、case/schedule和原300s/5s/TTL保持。所有失败stdout和脚本在provenance中保留，未修改历史golden地图、原失败结果或安全阈值。

[JSON](20261010_p2c_refuge_release_components.json)和同名provenance绑定最终control SHA `5dd929703ada43ba5062f4b104bc06861aa11b6aac3fe76094bfc9daa9f0274f`、reader、原图条件/原CDR绑定、实际DDS、声明、全部输出及源码。新v51须clean committed/pushed同源4开发→17正式+2物理，917仅非留出全部PASS后首次调用。P2C.1尚未完成；P3C.5已验收，无P4/ns-3/Wi-Fi/RL，actual airtime/J和容量未测。
