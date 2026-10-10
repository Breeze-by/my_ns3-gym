# P2C.1 首个近家普通目标继续组件

组件 PASS；完整 P2C.1 仍 FAIL。v73 四原开发两 native COMPLETE（强制231.7、房间285.0秒）、实验室RALLY300.1timeout、走廊中央COMPLETE但native success=false/300.4timeout；严格两PASS两FAIL和四格各21子审原件全部保留。四 owner/observer 0关闭，零接触/耗尽/FAILED/任务期infra；17正式、两物理和917未调用。

原实验室tb2第一普通目标距native home1.190119米，在原2*radius=1.6米范围内，却因“frontier already observed”取消，未形成真实普通成功。补能方法原本拒绝活动普通目标，此取消来自独立前沿失效判断。新分支只在完整对象EXPLORE/FOUND_UNCONFIRMED、未充电/未完成普通腿、当前已接收近家目标仍安全且充分有电时，允许该原动作继续。不是重新派发或源戳刷新，不将取消改为成功；仅原真实Future SUCCESS计入工作，之后沿用已有初次补能规则。

继续的每次核验使用当前2/5秒租约、保守本图/融合完整known路线、0.45米终点/0.35静态路线/0.6身体/1.8活动路线预约、原5米腿上限，以及完整去返预算加原60秒剩余等待成本。原60秒timeout和20秒no-progress优先取消保持。信息失效继续证据通过现有私有通道最多每机器人5秒记录，独立读者绑定先前真实普通命令、原始raw CDR地图与原生电池，复算源龄/路径/身体/等待与物理预算；不产生新应用流。

2290功能（357.23秒）、120定向/58新、四包原symlink5.96秒、190保护/6历史授权/54协议、三份31源声明及范围PASS。只1中央方法修改+1新增，其余85中央、104纯函数及11原native/SLAM/observer/command文件保持；strict gate仅接入新独立子审。native battery SHA f4845fb03667e766c0202a470fa5f2c3c4a49ff39f77a898bf90ec1b60261a6c。

隔离actual DDS/Future五情形：冻结d0be454取消、真实status5且普通成功0；新当前安全有电同一个动作不取消，真实SUCCESS1之后正常补能请求1。计算期间clock12→15源过期、timeout、no-progress仍取消/status5且零成功/补能。两版本的“存在合格前沿替代”布尔谓词是明确控制刺激，几何、租约、预算和Future为实际运行；静态地图/位姿/电池为合成输入。全部线程/node关闭，零实际Nav2/Gazebo运动、零原生充电credit周期，不是整任务收益或时限证明。11个原首派发快照归档，其中labtb2记录时几何预算合格；不冒称取消时刻的完整状态。首正向CDR夹具float32分辨率错配1FAIL/119PASS已按真实类型修复，原log保留，source binder未放宽。

新v74同clean-pushed冻结逐格串行4→17+2，且不与检查重叠。先15非留出和两物理全strictPASS才首次917。原300秒/5秒/TTL/物理刺激保持；P3C.5已验收，无P4/ns3/WiFi/RL，actual airtime/J未测。

[JSON](20261011_p2c_initial_goal_completion_components.json)
