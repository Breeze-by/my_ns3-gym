# P2C.1 原生完整返路前缀与全参与源组件 PASS

[v62四原FAIL](20261010_p2c_v62_failed_development.md)全部保留：同df0f3fc forced/lab/rooms原生COMPLETE242.1/193.8/158.8且strict PASS；corridors原RALLY300.0timeout、tb1第2次返航未闭合与提案缺tb2两源FAIL。四格零接触/耗尽/FAILED，owner/observer均0自然关闭；17正式、新物理对子和917未调用。三旧PASS不带入新源码。

原七次native decision严格复算：escape_vertices均1，短目标来自普通直视前缀；末五次目标约2.6–2.8cm，而完整contact返路仍约4.76m。新plan_charging_leg直接取原完整已知返路的最大不超过5m前缀，包括真实位置到栅格中心偏移。原膨胀区known-free有界逃离分支逐字保持，完整返充候选/当前source/局部障碍否决/预算/reserve/credit/动作状态/超时与重试保持。七个新前缀在原图上均独立通过.35m连续净空与初.6m逃离检查，并绑定14个原local/fused CDR；不声称Nav2物理沿每顶点执行。

admit_rally_proposal捕获并检查所有参与者的原pose/TF/map/battery源，包括RETURNING/CHARGING机器人，依原2/5/60秒TTL在几何前、顺序后和私有发布后重查。原顺序算法与assignment派发硬门槛不变。默认input_freshness_details仍用原过滤集合，仅显式proposal调用使用全部参与者。原epoch写入私有旁录，过期拒绝且不续源租约。

新增7原图前缀情形、14inactive source/发布竞争情形和3独立路径篡改反例；77定向先PASS，全部3新读者反例及现有膨胀区/unknown/断路安全在1926功能210.62秒回归PASS。初定向误写不存在测试文件exit4零执行保留；初全套1924PASS/2FAIL的旧正向夹具缺源戳，补真实必需源戳后全PASS，未放宽生产检查。

实际native DDS/ActionClient Future使用原native末段图/位置，静止条件：旧两goal仍约2.7cm、新两goal距原位约3.8m；clock14使旧11源过期，两版本拒绝追加goal；fresh14后再次真实派发，fresh15电量.1触发原FAILED reserve floor。新两条完整前缀独立审计及4个合成published map CDR绑定PASS。动作/节点/线程全关闭；该探针没有物理移动或return完成，不能代替原return闭合门禁。

实际三机proposal DDS使用合成10/13s源戳和返航中tb2：旧首次缺pose/TF旁录被原独立读者拒绝，新首次完整字段/4map CDR PASS；所有源过期两者拒绝；其他源fresh13而tb2 pose/TF仍10时，旧接受、新拒绝；全部fresh13双方接受。旧结果[True,False,True,True]与新[True,False,False,True]，新两提案8headers精确绑定。既有proposal local-map/order DDS回归PASS，全部owned关闭且零Navgoal。

初只读CDR helper错误优先导入/tmp旧check_p3a6导致argparse exit2，字面/log保留；显式仓库脚本优先后7原图/14源CDR PASS。未更改任何生产源/资格来适应导入错误。初“膨胀逃离”诊断撤回，原Nav2 xy_tol=.02而非.25m，不采用成功无运动猜测。以上是条件机制，非原live回放、唯一任务因果或最坏时限保证。

仅2中央变化，其余81中央/101纯/globals保持；native仅1纯函数变化，36状态方法/9纯/globals及其余6受保护native/launch/SLAM文件保持。四包原--symlink-install 5.65秒、190保护6历史授权54协议与两新声明PASS；原case/物理schedule/300s/5s/净空/Nav2/SLAM/能量/次数均保持。新v63须clean pushed同4开发→17正式+2原物理，15非留出和新两物理全部strict PASS才917。完整P2C.1未完成，无P4/ns-3/Wi-Fi/RL。

[JSON](20261010_p2c_native_return_curves_components.json)及provenance保存全部字面、初FAIL、输出/声明/SHA。
