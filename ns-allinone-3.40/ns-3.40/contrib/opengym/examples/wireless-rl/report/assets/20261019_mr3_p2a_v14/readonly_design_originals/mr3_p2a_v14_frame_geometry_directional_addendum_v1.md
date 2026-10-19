# V14 normal directional tube：frame审查补充

本稿补充而不覆盖frame_geometry_review_v1。用户已批准设计方向，当前仍是conditional geometry CPU原型；未启用新门、未授权native、旧FAIL不变。

## 距离cap不能替代方向

纯数学反例（非plant）：own=(0,0)，raw peer=(+.60,0)，map peer=(−.60,0)，own两边heading都沿+x。d_map=d_raw=.60，min距离cap不变。map判断peer在后方，可把向+x的normal longitudinal sector判为nonclosing；raw实际peer在前方，同方向会接近。两边消息可同样fresh。normal+disk的纯buffer阈值.5512可过，保留.144 longitudinal后阈值.6952不能过。故map方向相反但距离相同是必须拒绝省略longitudinal的反例。

对新NORMAL/transition，map和同envelope raw WORLD几何必须分别核所有admitted signed-heading cones。仅当两边相应cones均已保守证实nonclosing，才允许扣该方.144 longitudinal；任一side/任一可能sign未证则保留完整isotropic longitudinal reach。没有承诺support不接近时，不得把“不知道”当nonclosing。原map必要门和原source ages/.5、body .50/.02不减。

raw bearing从own causal raw及同一已交付peer raw得到；raw yaw也来自对应各自同envelope pose quaternion。不可混用raw distance/map bearing、原state yaw/后到raw、新本机peer raw或隐含未来TF。两方calibration必须是同一固定WORLD metric/handedness及同身体点；同名odom不足以证明。

## producer数值校准与physical模型边界

原driver将WORLD XY转body用float yaw/cosf/sinf，而原pose quaternion保留double。新physical normal η/r若按double quaternion理想yaw重构world速度，实际producer矩阵并非逐数值精确同一旋转。可以对声明给定的heading cone做exact rational/Taylor几何证明；不能据此声称producer转换误差或真实连续r也已经证明。须给实际转换的保守包围/逆矩阵或将有证的转换误差纳入physical residual/heading前提，不能用无证明float epsilon放宽边界。该细节不影响纯raw位置disk的2R距离论证。

当前buffer提案normal=2R（transientR+terminalR）、transition=4R（旧disk2R+normal2R）、disk=2R仍是待证physical reach集合。几何函数接受只证明集合假设下的数学推论，不证明真实mode承诺、continuous slip、terminal或storage交接。原V13zero-target真实brake瞬态有planar>.01，所以NORMAL→BRAKE→DISK必须区分；actual target_v0不是即时rest或disk mode。
