# P2C.1 v31 等价几何优化组件 PASS

v30冻结c12db66首强制任务300.2秒EXPLORE timeout，仅一次导航/零charge；130次计算因原source+TTL到期而弃置。所有owned自然关闭后归档原FAIL，后3开发/17正式/2受控物理/917未调用。本候选不放宽原2秒位姿/5秒地图电池/300秒horizon/5秒原生保持；先减少同一几何的重复计算。

圆盘膨胀改为已有SciPy欧氏距离变换<=原整数半径；无occupied格特判全false，避免EDT域外虚拟零点成为假墙。12随机种子×5矩形/单行列尺寸×4密度×8半径，加3-4-5与5-12-13精确边界，逐格与旧binary_dilation闭圆盘相同。原unknown/free/occupied阈值、端点/.35/.45净空、角点与路线函数保持。

已有qualified_return_candidates几何缓存增加最多128位置的结果表，仅当fused与consulted local map均由不可变底层内存支持；按原图对象/各geometry/home/radius/位置绑定，任一源替换或几何改变即清空，可写底层的readonly别名跳过结果复用。仅缓存完整路线与local障碍否决结果，不缓存energy/age/lease。独立结果dict与不可变路径点避免调用者污染memo。初版只浅复制dict，列表position可修改缓存route的反例1FAIL已保留，补路径点tuple后通过；中间版本未进任务。

取v30唯一实际导航事件的211×253原交付地图，在固定原source/evaluation epoch且两机均idle的条件夹具内，五次完整调度冷计算中位数0.56805→0.21292秒；全部选择、路径/旅行偏好及预算数值相同。该只读组件不含原任务全历史、实际计算期间clock或真实Nav2派发，不是任务反事实/最坏延迟保证。当前coordinator类AST完全相同，只改两个纯函数。v28四份旧原始数据重新用新几何审核，原状态保持：corridors原未闭合返航FAIL，其余返航与各预算/目标/探索重建PASS；不把旧cohort改作新通过。

最终1238功能PASS72.15秒、四包5.56秒、171保护/4授权/54静态协议/8中央+2native deferred Future注册、两manifest PASS。实际ROS DDS clock+真实Future串行、native Future保护、visual79数值/旧JSON错误复现、相机兴趣/target survey/healthy quiet和lapsed turn均绑定最终源SHA PASS。native battery/sampler/action helper/launch/observer/严格gate/result reader相对c12字节保持，但native调用的shared geometry已变化，所以新任务和两受控物理原格仍必须验。两份声明case及physical刺激不变。

组件PASS，P2C.1尚未通过。新4开发→17正式+2物理须同clean pushed freeze，917仍未暴露。P3C.5已验收；无P4/ns-3/Wi-Fi/RL。
