# P2C.1 当前集合顺序复核与永久改派意图组件 PASS

[v63四原失败](20261010_p2c_v63_failed_development.md)保留：同b488cd5 forced/lab/rooms原生COMPLETE156.5/234.5/209.2且strict PASS，corridors原RALLY300.0timeout。四零接触/耗尽/FAILED，owner/observer0关闭；27软件/仪器digest同源。原走廊18子审PASS，六原native return闭合、四原腿/八原图CDR绑定，不能替代任务完成。17正式、新物理对子和917未调用。

原走廊完整提案311.8s选出、314.1s计算结束、338.4s当前接纳；不把26.6秒全部归因排序。原当前顺序tb2→tb1→tb3三条完整body/local-map串行路线均合格。五次cold条件计算完整搜索中位1.2040s、三条顺序复核0.2267s；没有任务因果或最坏时限保证。新提案只保留上次排列这个几何偏好，每次用当前交付地图、身体位置和本地障碍重新规划完整三路线，不合格仍走原全排列搜索。原endpoint/LOS/yaw/间距、全参与pose/TF/map/battery/target的2/5/60s TTL和旁录后复查、后续普通完整去返/等待/5s保持预算均原样。该偏好有意不重排所有当前软成本，声明清楚，不称原全排序等价。

原末两tb3目标410.9/428.2s仍记local_return_yield，即使其正式集合终点已永久改派；旧return-owner/yield/probe状态继承了临时让行直视腿和目标/预算例外。新仅永久改派等待者时清掉这些旧角色及旧捐赠优先键，恢复普通RALLY；真实临时refuge仍保留原安全例外。私有改派记录明确movement_authorized=False，下一普通派发必须重新核验当前目标、完整body/local路线和全能量。原普通RALLY此前已能使用弯路，本次不改正常腿算法，也不将旧状态作为唯一轨迹因果。

实际DDS串行探针使用原完整几何、合成10/14/20秒epoch，并故意在旧全搜索结束后跳clock造成过期：冻原接纳[False,False,False]/搜索2次，新[False,True,False]/搜索1次；新fresh14复算三条路线接纳、20秒无交付仍拒绝。独立当前源读者和四个published map CDR绑定PASS，零Navgoal。实际永久改派探针使用合成走廊/旧角色/几何chooser，真实update_mission和ActionClient Future；旧等待者保留让行角色，新恢复普通角色，并在旧target过期和fresh电量.1时拒绝。含blocker的总goal旧4/新2；等待者旧0次普通预算、新2次完整预算，其中不足拒绝。新私有改派/角色读者及四个published map CDR PASS；旧缺新意图见证是预期组件拒绝，不回填旧任务。

两新探针所有Future/节点/线程关闭；无物理运动、原live回放或任务收益保证。旧全参与source DDS回归PASS，新[True,False,False,True]并绑定8headers；旧dispatch logger/旁录竞争DDS回归四变体PASS，过期零goal、fresh源才继续。后者isolated夹具没有final_target，因此只启用原lease读者，明确不证明新完整role契约；正式manifest新role旗保持强制。

28新增功能情形包括永久/临时角色区分、原三路线、失败fallback、到期只存排列、六伪造路径与目标/预算/时间/意图反例。80定向4.78秒、1954功能202.29秒、原symlink四包5.56秒、190保护6授权54协议与两新声明全部PASS。本候选无中间测试失败。仅3中央方法改变，80中央/101既有纯/globals保持，新增1纯函数；全部7 native/launch/SLAM文件逐字保持。300s/5s、TTL、body/净空、原生能量/credit/重试/物理刺激均保持。

新v64须clean pushed同源4开发→17正式+2原物理；15非留出和新两物理全部strict PASS才首次917。完整P2C.1仍未完成，无P4/ns-3/Wi-Fi/RL。[JSON](20261010_p2c_rally_intent_components.json)及provenance保存源字面、输出/声明/SHA，所有旧FAIL原样。
