# P2C.1 v39 外圈可见边界自适应采样组件 PASS

v38冻结56de2b首forced原任务262.8s PARTIAL_COMPLETE、success=false、一个正电量tb1 FAILED；两机各charge1/min8.90048、0contacts/exhaustion/task-time infra/retry。全部原失败见20261009_p2c_v38_failed_development.md/.json。12原独立审计PASS不能抵消失败；其余3dev/17formal/2physical/917未调用。

保留原72候选及顺序，仅第一层集合提案对2.6m外圈24角度的可见/不可见邻接边界增加5/10度点。最多24有向交界×2=48新增，第一层上限120；全可见外圈不新增。每个新点仍需原0.45m端点净空与已知地图视线，原0.8m分离、完整qualified已知返航、当前地图占用veto、全往返能量/串行充电/observer与soft exposure目标保持。若该层没有完整可行分配，原最多464角边界层仍执行；dense返路修复与候选函数默认采样保持。停止在首个可行层仍牺牲跨层全局软目标最优性，不保证区域可行性穷尽或未来地图鲁棒。

四方法同一原AP输入对照：original72实际11有效点、adaptive13、uniform216为33、全边界55。原分配tb1在门洞内(-4.267,3.023)；adaptive把两机选到门洞外(-3.567,1.423)/(-4.667,1.473)，soft窄返路暴露合计1.614727613→0.666123834m。原三cold约.488–.504s、adaptive.499–.505、uniform.587–.598、全边界.711–.721。没有把样本wall时间当实时上界或单因素任务收益。代码修改后的另5cold中位原.4924/新.4824s，独立DDS接收的两份真实coordinator witness均按各自源码完整重建PASS，原source epochs保持。

之后2339.282s的原native地图仅用于离线压力检查：原tb1分配在该图无合格返路，adaptive两个假设位置在同图均有完整已知净空接触路径(3.708/5.049m)。它不是原机器人已经处在这些位置，不是轨迹反事实回放，也未作为未来地图输入进入选点。原门洞断开当前自由/安全单元仍无法返航；原始自由图连通但0.35m净空图断开。未配准静态SDF比较不能归因于同伴，未增加SLAM回波过滤或Gazebo真值感知输入。

新增15 meaningful checks覆盖可见窄弧补采、原前缀、全可见不增、原dense/stratified不变、12有占用/未知的随机图中净空/视线/唯一性/朝向/≤48界和图外目标。325定向PASS19.21s；全1428PASS106.16s，测试替身只为新的可选keyword扩展，额外恢复无关lambda后test_control独立294PASS。四包build5.87s、171保护/4已有授权变化/54static、8中央+2native Future注册PASS。仅3纯集合函数AST变化，coordinator class/native/clock/TF/action桥与原Nav2/SLAM/物理字节保持；原300s/.35/.05/.1/5s和2/5/60s TTL未变。

初只读诊断调用不存在API及全边界prototype重复stratified参数的tracebacks保留，修正后全部比较成功；均不是任务调用/重试。所有输入/运行脚本/检查/manifest/失败与gzip SHA见JSON。新clean pushed freeze后先forced2原生COMPLETE及每机charge≥1，再另3开发；all4通过才同freeze17正式+2物理，917最后首次暴露。P2C.1尚未完成；P3C.5已验收，无P4/ns-3/Wi-Fi/RL。
