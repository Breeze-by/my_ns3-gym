# P2C.1 v34 两级惰性前沿收益组件 PASS

v33首强制原任务24e1e27自然FOUND timeout300.0秒/检测291.4秒/RALLY未进入，13Nav2、两机各charge1、最低11.4660094、零接触/耗尽/failed/infra/retries。全部owned关闭后才修改；十二独立子门PASS不能代替任务成功，87次原租约弃置完整保留，后3开发/17正式/2物理/917未运行。

先实测批量射线1/2/4/8/16/32 chunk：157个原前沿单元gain逐项相同，但五次中位约.391/.439/.612/.824/.890/.929秒，原逐点.183秒。该方法更慢，拒绝进入任务版本；原脚本/输出保留，无其任务。当前上界不是改善地图分辨率、视场范围或放宽阻挡。

原frontier几何采样仅依赖矩形unknown integral分数、距离、LOS和原spacing，不依赖最终ray gain。因此先按完全相同的采样顺序生成私有ViewpointGainBound/AssignmentGainBound，矩形unknown数是原射线实际unknown集的上界。竞争到优先级顶部时计算原精确ray gain和原reuse factor/utility，重入heap；再竞争胜出才计算完整return预算与relative/diversity评分。必须重入gain上界再做预算，避免把收益已下降候选多做预算（首组件试型ray21但budget26，最终两级ray21/budget4）。固定source/epoch下yield顺序与完整稳定greedy相同，实际所有动作仍原body/route/完整预算/source门限。

私有上界只保存在规划context，准确解析后恢复原Viewpoint/Assignment类型与数值；普通任务/本地安全/通信数据结构不变。只缓存同一不可变source数组的前沿几何，源替换或mutable alias不得复用；准确ray cache属于同一map/admission/充电context，无source/header/age或能量续租。完整raw候选池保留给原two-frontier forecast，以同样惰性准确gain实现原稳定排序、gain>200、half-utility、组/空间分离与最多三候选规则。实际已有原充电夹具和真实交付图的eager/deferred forecast路径及预算逐项相同。

十二随机地图验证几何/顺序/矩形上界/准确gain/带reuse的全部候选与排序相同，十二种子200候选两级稳定排序、失败界、竞争预算不提前计算、source替换与实际样本少于半数rays、派发普通类型/准确gain通过。首stage夹具146PASS/1FAIL仅因新增gain检查提前在candidate_generation撤销而旧断言期待candidate_budget；保持所有无导航/charge/live owner断言，更新准确stage后完整1309PASS73.38秒。首validate-only错用连写domain参数exit2，无task，修正两清单PASS。generic patch误落其他方法的cache block在任何任务前移除，AST比较只两中央方法改变。

原2089.582秒交付map/固定epoch/两个idle的条件完整调度（不重放原owner和路径历史）五cold中位0.38687→0.22383秒，157→21 ray、4→4预算、导航/旅行偏好/预算证据逐项相同。四包6.95秒、171保护/4授权/54协议/8+2 Future检查、actual ROS clock/native Future/原视场20数值79候选/独立发布消费PASS。新增domain214实际ROS中央assign_idle_robots用保留静态交付输入与合成goal sink，两个正常Assignment经实际DDS记录发布并独立重建原完整旅行/收益/预算/source证据；这是组件而非真实Nav2/Gazebo运动或clock时界。Native battery/共享Future/TF sampler/launch/观察器/严格gate与读者/视场validator相对24e1e27字节保持。旧v33十二子门只读重审PASS、原任务FAIL不回填。

P2C.1未完成。新4开发→17正式+2物理仍需同clean pushed freeze，先强制双机native COMPLETE且各charge≥1。917未暴露，P3C.5已验收，无P4/ns-3/Wi-Fi/RL。组件提速没有最坏界或任务因果收益证明。
