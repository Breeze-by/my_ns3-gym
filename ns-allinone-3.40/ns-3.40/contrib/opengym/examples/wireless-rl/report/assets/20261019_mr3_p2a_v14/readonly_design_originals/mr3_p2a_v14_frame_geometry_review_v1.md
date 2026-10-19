# V14 frame / geometry 只读设计审查

状态：用户已批准安全契约重设计方向；本稿是新合同设计审查，未修改生产、激活新门、运行native或把旧FAIL重标PASS。建议采用“原map门不减 + 同一已交付raw WORLD odom距离额外cap”的显式新校准合同，但连续disk与pair备份/交接仍必须另闭合。

## 实际坐标与信息链

1. 当前tagged driver只允许WORLD，`UpdateOdometryWorld`把`model_->WorldPose()`直接写入Odometry pose，没有减机器人spawn/初始位姿。三机坐标数值都来自同一Gazebo world；header仍叫`odom`，child是`base_footprint`。model origin与此SDF的base_footprint/base_link原点同点，既有完整身体盘半径.25仍围绕这一点。WORLD速度是该原点world XY经yaw旋转到body，参考点/范数不应另换。这个producer本身采用模拟真值生成既有local-odom测量；不能据此声称真实里程计无误差或安全端可另读truth。
2. information bridge以本机原odom和SLAM map→odom组成`c_i=G_i(u_i) z_i(s_i)`及yaw；odom/TF源分别保留，TF真实源为header−.2s；combined源是两者较旧者。它只在实际transport delivery后发布`/mr3/received/states`及side odom/TF。每条state已包含同一envelope的完整raw odometry、seq/epoch/source/received；transform字段被还原为side TF后从state payload移除。
3. guard对i使用i自己的causal raw odom/TF；对j使用已交付state j，而非j的新本地raw。own紧凑状态内odom/transform被删除，但node已有被引用的own原件与input_sequence。geometry当前比较各机map估计`c_i,c_j`，源龄用min(odom,TF)，均须source≤T、age≤.5s。actor/Nav2/candidates仍沿原map信息，不改变。
4. map merger只验证`map`标签、分辨率和轴对齐，不估计未知相对位姿，也不证明三个SLAM map的物理注册误差。共同frame是已有条件前提，消息同名不能证明该前提。

## 2R为何不需要历史anchor映射

固定own odom anchor A_i，整段假设`||z_i(t)−A_i||≤R=.0078`。若当前用于几何的raw样本s_i也属于该同一disk，则对任意未来同段t：

`||z_i(t)−z_i(s_i)|| ≤ ||z_i(t)−A_i||+||z_i(s_i)−A_i|| ≤ 2R=.0156`。

因此不用把历史anchor用历史TF变成map点，也不用随SLAM校正重映或重锚。任意一个固定、刚性的同一变换保持此范数。不能对anchor/current各用不同时间TF后仍援引等距性。该几何论证还要求odom对应同一物理点且其物理标定在整段固定；若真实关系`p_i(t)=H_i z_i(t)+e_i(t)`、H_i固定且`||e_i(t)||≤epsilon_i`，真实位移界为`2R+2epsilon_i`。若H_i漂移/重置或epsilon无界，2R不闭合。当前已绑定WORLD producer给出模拟内固定共同物理标定，真实encoder/硬件不能据此取epsilon=0。数值舍入须以保守比较处理，不能加epsilon放宽R。

若selected样本早于anchor、frame改变、source gap/重复冲突、样本非有限或盘已破坏，disk分支不能授予资格；不能从未来样本、最新TF或重锚补证。source≤clock的准入与记录全部真实incoming模型违例应分清，不能因为/clock回调晚于raw到达就抹去物理违例。

## 现行map几何缺口

在共同物理坐标的刚性表示F下，若`||p_i(s_i)−F c_i||≤E_i`，则

`d_true(T) ≥ d_map − (E_i+E_j) − V(a_i+a_j)`，V=.30，`a_i=T−min(s_i,u_i)`。

原`U=V(a_i+a_j)`只包源龄带来的身体运动，不包SLAM jump、各机器人map注册偏差、固定原点错误。原`.02m`几何余量没有被证明是定位误差上界，不能自行把全部注册误差塞进去；TF covariance/平滑或已过往无接触也不给确定界。

纯数学反例（非native）：真实中心距离.55m、零age，peer map误移+.30m后估计距离.85m。map-only margin=.85−.50−.02=.33，能够通过.1596；真实余量只有.03，不能保证后续.1596 reach。每条消息仍可新鲜、frame标签仍map。因而若坚持仅用map估计，必须新增有依据的E_i+E_j合同；当前代码/合同没有这个有限数值界。

## 推荐的最小闭合坐标合同

在**显式限于现有已绑定共同WORLD-origin local-odom producer**的模拟标定前提下，只复用：

- i已有causal own raw odom z_i；
- j当前已交付且通过原age/epoch/frame/原raw一致性检查的同一state envelope内odometry z_j；
- 原map估计和原min(odom,TF)源龄。

定义`d_raw=||z_j−z_i||`、`d_cap=min(d_map,d_raw)`，保留原body门并额外要求

`d_cap − .50 − U − .02 ≥ q_i+q_j`。

当前模拟共同标定时，raw pair distance是不同source时刻的真实测量点距离；U保守覆盖到当前T，原own TF较旧age继续计入，即使对raw而言重复保守也不缩减。新cap只可能deny原本被放行的几何，不放宽原map/body门，不把raw世界坐标变成actor特征、导航目标或新的规划地图。相同raw值已经传过delivery边界；不新增消息/传感/频率或读取未交付peer状态。

该方案仍是显式**新安全几何语义**，不能称旧门字节/数学等价。WORLD共同原点的事实须来自实际source/binary/config绑定，不得仅靠frame字符串或spawn参数断言；否则此分支fail closed。它只限当前模拟local-odom的已知理想标定，不声称未知相对位姿/现实定位的解法。若研究方不接受明确使用这一既有producer校准事实，则不能采用此cap来“证明真实几何”；应保留抽象E_ij为未闭合前提并停止seal。

## pair / backup独立限制

- i whole-segment disk给`q_i=2R`；若j被实际、持续地约束于其自己的同类disk，也可用`q_j=2R`，pair sum=.0312。可以保留更严格统一.1596门，但不能因更大数字而省略mode真实性。
- `q_j=.144`仅能引用有实际≤.16反应、完整stop envelope及终端集合的peer backup。当前v=0、三条rest样本、已发zero或worker storage ACK都不等于peer未来持续backup承诺；generic normal持续运行不能被当成只动.144m。
- 既有.78/.144停车到三条≤.01样本，不证明其后永久静止。若先stop再新disk，终端盘通常还要加到从当前点的总reach预算；除非明确证明总tail包含其中，不能把额外R/2R默默塞进原.144。
- 当前received/states没有mode/anchor/backup承诺字段。不能从peer raw静止推断disk，也不能偷读peer本地tracker或用全局worker ACK冒充已交付peer承诺。新增mode证书必须显式定义来源/epoch/seq/source/expiry/撤销和实际storage生效，是信息/执行合同扩展，不应在几何修补中暗加。
- 可研究中央joint fail-closed backup协议，但必须明确各robot final-output如何受控、source因果、三台真实storage/actuation交接与终端集合；它不能仅由“同进程能看到三机own raw”获得额外观测。mixed normal/disk及退出到translation在证明完成前拒绝。
- 不论pair模式，原.5s freshness、原身体/无非支撑接触/完整twist上界、未观测角加速与任务门都保留。map-only cap只解决坐标乐观误差，不能证明连续disk、备份响应或无侧滑。

## 可实施建议与剩余前提

先做纯函数/独立reader的CPU合同原型：绑定同source pair，计算map/raw/cap/U及qsum，每个判据留原输入引用；anchor始终在own odom中固定，累计path继续完整单调保留为旧合同反例诊断。关键负例包括异源raw替换、peer晚到/未来/.5s+1ns、same-name不同origin、map跳变虚增距离、odom frame/reset、anchor两侧2R、缺peer mode、只stop无terminal、translation storage迟到。它们是待做准入验证，不是本稿已跑的测试。

必须另闭合：连续采样间disk包络与对应真实物理前提；可证明的peer backup终端集合；received mode或明确joint控制协议；translation真正storage/actuation接管前后的完整覆盖。过去sample统计只能寻找反例，不能证明未来条件。旧V13 whole-path失败、原矩阵FAIL/optionalFAIL、minimum0更新及38准备资格的原范围均保留。本文无新native预算或执行授权。
