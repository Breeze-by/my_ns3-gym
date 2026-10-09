# P2C.1 v32 视场查表与按需前沿准备组件 PASS

v31首强制原任务300.3秒EXPLORE timeout/3导航/1charge/135原租约弃置，strict FAIL完整保留，后3/17/2/917未调用。后期212×253交付图/14视场历史的条件计算1.222秒，包含265射线、89视觉候选；早期.213秒样本不是此负载的时限界。没有执行器饥饿或Wi-Fi瓶颈的证明。本候选仍保持原真实clock、source/2秒位姿/5秒地图电池/native300秒/5秒与完整预算。

将原角度×步长浮点投影按radius缓存成最多8个bytes-backed不可变表，仍先加实际row/column再np.rint，保留半偶舍入与大整数坐标浮点行为。以平面bool hit mask代替flat cell排序去重，sorted cells与gain逐项相同。把整数相对格上原16yaw的atan2(sin,cos)/inclusive FOV谓词预计算为最多8个不可变radius/FOV表；不是cos近似、角度阈值放宽或未知空间可见化。每次实际地图、当前遮挡与历史interest仍重算，没有地图/header/age/energy缓存或新应用流。

只改两个纯计算函数、增加两个纯lookup，并修改assign_idle_robots一处准备顺序：完整mapping前沿仅在该分支需要时生成；原traversable/.35净空travel field保持，visual为空仍回原mapping，所有route/body/预约/完整budget/source/charge/dispatch门限保持。原mapping策略、目标选择与计划优先级没有改变。保存后期实际交付夹具验证不执行unused mapping rays且同导航点，空visual仍真实生成并使用mapping候选。固定原source/epoch/eligible tb2与pending tb1的五次cold条件完整调度中位1.15972→0.61908秒，所有选择/旅行偏好/预算值相同；前期只lookup约1.096→.944秒，按需准备进一步降低开销。这些均无真实机器人派发、原始全历史反事实或最坏界。

12种子/单行列与矩形地图/边界/七个整数和临界浮点radius/unknown与occupied遮挡，原sorted cell集/计数/yaw逐项一致；所有整数offset及1/2/5/20/40/41半径、3种FOV谓词与tie、百万坐标平移、不可写底层/有界内存检查通过。116定向PASS10.14秒；最终1260功能PASS75.14秒、四包6.52秒、171保护/4授权/54静态协议/8+2 Future注册/两声明PASS。native battery/action helper/TF sampler/launch/observer/严格gate/result reader字节相对f455保持。

首actual ROS validator在旧pure function AST必须相同处停止、未init DDS；该要求不适用于明确授权的等价算法优化。改为独立编译89ee853原visible_unknown_gain/known_search_interest/known_search_view/known_space_search_candidates，20组sorted rays与gain/yaw、79候选数值相同，并继续复现旧int64 JSON错误/新实际DDS发布及独立消费；原相机history、target survey、healthy quiet/lapsed checks PASS，clock与真实Future/native保护也绑定最终source PASS。只读v31原样重审12子门仍PASS且任务FAIL，不回填。

组件PASS，P2C.1未通过。新4开发→17正式+2物理必须同clean pushed freeze；917未暴露。P3C.5已验收，无P4/ns-3/Wi-Fi/RL。
