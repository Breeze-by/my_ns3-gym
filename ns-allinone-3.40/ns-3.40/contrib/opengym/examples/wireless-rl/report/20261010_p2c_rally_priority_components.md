# P2C.1 空闲集合顺序修复组件 PASS

[v59四原整体FAIL](20261010_p2c_v59_failed_development.md)保留：forced/rooms/corridors原生COMPLETE230.0/206.5/224.9秒且完整strict PASS；lab RALLY timeout300.0、三机各charge1、18独立子审及完整native return闭合PASS仍不能代任务。四零接触耗尽FAILED，owner/observer均0关闭，原日志/CDR/结果与SHA全保留。

旧可行当前腿仅被未来优先路挡住时，已经找到更少approach inversion的map-safe顺序，却只设置preflight=False后返回。真正常规重算要求所有机器人energy-ready且无充电，因此保留观察角色、资金不足的机器人使未来重排一直不执行。新分支仅在每个central RALLY accepted/pending为空时保存同一计算结果，立即返回；下个原回调先按当前能源状态排序，并重新核验当前地图、机体完整路径、return预约、实际完整去返/等待/保持预算及原源TTL。存在任何旧动作时保留原顺序和drain，既不修改执行中预约，也不在重排回调立即派发。

3个新单元情形覆盖无腿/待接受/已接受，另原2个drain和纯顺序回归共6 PASS。窄通道角色夹具旧10/11秒两回调均零派发，新10秒仅改变未来顺序、11秒发送就绪near，未就绪观察者不发送。该unit readiness为角色stub，不能独自证明能源/原生导航；真实DDS独立使用实际prepare_rally_charges与rally_plan_has_energy。

实际隔离DDS四情形：原冻结两回调零目标；新空闲先重排再由下一回调发tb2；旧pending与旧accepted ActionServer Future均保持顺序，原真实响应/结果清空之后才重排，再下一回调发tb2。三个新情形均旧source在真实clock15拒绝、fresh15重新派发、fresh16但energy0.1拒绝；资金不足的观察tb3始终零派发。全部实际目标由原完整预算/身体/返路/reservation/source guards授权，独立dispatch/outbound读者核验8决策/180路径点，真实Future/线程/节点关闭。目标/分配、栅格几何和模型是合成条件；不是物理Nav2、原live回调重放、完整任务因果收益或一般死锁自由。

仅update_mission改变；其余82中央方法、101纯函数、globals/native七类/既有读者逐字节或AST保持。1881功能208.81秒（增加3新测试及2原merge-map测试），四包原symlink构建5.77秒，190保护6历史授权54协议、两新声明PASS。原300s/5s/2-5-60s/.45端点/.35路线/1.8预约/5m腿/次数/Nav2/SLAM/物理全保持。

原trial1/2夹具属性失败、3/4开放地图未进入阻塞断言失败、5进入另一恢复分支的夹具失败和首full不存在文件exit4全部保留；没有用这些结果称PASS或修改生产保护来迎合夹具。最终窄通道10/11回调和实际DDS证明有限机制；不意味着更晚恢复行为全局收敛。

新v60须同clean pushed4开发→17正式+2原物理；15非留出和新物理全PASS后才首次917。组件PASS不替代完整P2C.1，无P4/ns-3/Wi-Fi/RL。[JSON](20261010_p2c_rally_priority_components.json)与provenance保存全部实际输出、初失败、字面源、声明和SHA。
