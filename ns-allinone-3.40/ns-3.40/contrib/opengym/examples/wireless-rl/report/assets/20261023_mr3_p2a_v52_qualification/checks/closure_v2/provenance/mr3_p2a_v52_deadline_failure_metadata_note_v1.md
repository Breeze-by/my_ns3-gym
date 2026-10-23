# V52 deadline 原生失败：闭合小元数据与静态代码路径

状态：诊断描述，非科学重审/新资格。仓库仍冻结1fa55bc56d5bb9e230d4b397f962d83b1604b278，归档由root进行。本稿只读下列9份已闭合小元数据/控制台，以及解释源码；没有读取motion/control/drive/odom/actor原件，没有运行reader、World、模型或测试，没有修改checkout。

## 已证实的失败

- deadline benchmark是open101、1worker、300步、action888 KEEP，非PPO。native真实wait rc1，5215.342431454墙秒；stage FAIL且within_stage_wall_allocation=true。实际native分配19751.697秒，benchmark.wall_limit_exceeded=false。不是本次wall budget到期，也不是300仿真秒截止先触发。
- benchmark记录203个完整返回，所有已保存dt=1；下一个step请求id205、action888、external_truncation=null失败。不能把request id当行动序号，更不能为失败请求补造第204条返回。
- epoch为mr3_p2a_reach_v52_deadline_w0_e1_426a2555。负ACK是mr3-motion-control-ack-v2，operation=commit，request_id=boundary244580000000，clock_ns=target_time_ns=244580000000，ok=false，error=normal_control_model_invalid。
- episode任务release为41.3s，stop为244.58s（203.28任务秒）；summary.reason=infrastructure_failure，transition_count=203。training_finalize_ack明确invalid_sample=true/no synthetic transition or reward。
- infrastructure_cleanup.json报告best-effort cleanup PASS/30.69882262405008s；summary中Nav2 shutdown success=true、launch_returncode=0、native_failures=[]。另supervisor receipt真实保留worker rc-15、forced_shutdown=true、failed_sample=true，不能把局部cleanup PASS当整个episode自然成功。root另外负责全保存身份关闭核。
- stage未运行科学审计（audits={}），driver在matrix失败后停止，minimum/pilot/final未启。driver原件费用为engineering_added_union19330.328322094、累计89873.5057367926018；不在本稿另造费用或资格。

## 精确代码路径及未知

1. benchmark.py:689选择888，:699调用env.step；仅成功返回后:703–706增加transition计数。:754–758捕获实际异常，登记rpc_or_worker_exception，再真实close。
2. mr3_motion_control.py:245–247：非stop且node.halted已是normal_control_model_invalid时，直接负ACK；另一条路径:264–271在真实dependency_ready后，normal_velocity_fault(target)返回fault，记录完整normal_control_model_invalid事件，再负ACK。
3. motion_safety.py:589–595的Reach分支会对每机tracker.synchronize(clock_ns)，捕获实际ValueError/KeyError/TypeError/OverflowError并返回包含robot、reason、commit_clock_ns的完整fault。已异步锁存的reach_failure(:248–277)则记录reach_model_failure并发布本epoch的真实首fault消息。该通用literal也可能代表输入/身份/时序矛盾，不能只凭名称认定机体速度或几何数学已违反。
4. controlphase的except(:292–296)保留halt、记录control_failure、真实ensure_stop；finish(:309–320)生成负ACK，故intent_refs=null及safety_table_sha256=null是失败ACK的既定形状，不是可据此倒推“没有table/intent才失败”。
5. env_worker.receive_control_phase(:603–611)先记录实际ACK，任何本epoch非终态特例的ok=false即抛actual controlled execution failure。callback wrapper(:256–265)保存callback_error，_healthy(:499–500)转ROS callback failed；main(:1842–1870)保留infrastructure_failure/cleanup后返回真实IPC error。Supervisor._rpc(:328–333)转InfrastructureError，benchmark中止。

现有小回执没有底层首fault的robot/reason，不能区分第2项两个分支，也不能据它选择“raw/calibration缺口”“残差/角加速度”“storage/角色矛盾”等根因。episode summary仅有worker生成的infrastructure_failure消息；这不证明motion首fault未发布，亦不证明其已被worker收到。132205B launch.log共449行，限定Error/ERROR/exception/Exception/Traceback/failure/normal_control/reach.*fault/model_invalid模式匹配为0；这里只是该控制台无相应文本，不是全系统无故障。

## V53最小预声明取证建议（禁用、未运行）

固定唯一原episode，不拓展场景/epoch。首目标仅识别生产端FIRSTFAULT robot/reason与实际广播接收，不重放Reach或物理数学、不重判V52。

必需raw源仅两份，现时只lstat，尚未读取字节：
- motion_safety.jsonl：2458997272B；含全机自己的原odom、收到的calibration/applied/storage、完整首fault及control request/ACK，足以找到生产端原因。
- startup_readiness.jsonl：286052B；receive_failure在任务期仍写exploration_failure_received，receipt.topic/data及epoch_bound_to_current_startup可确认实际接收，没记录必须NOT_RECORDED。

不需要先加544635914B的control_phase_worker；现有infrastructure_failure已保留负ACK。三份drive原件仅lstat分别13947810/13822685/13763655B；识别首fault不需要它们。若未来要另查producer与guard接收差异，应另预声明全部固定原件/问题，不能见到某robot结果后临时扩大本次输入。

建议一次有界stdlib流式consumer：
- root封存两份输入的确切原字节SHA/bytes/regular stat、旧证据freeze1fa与解释源SHA、未来执行freeze/consumer SHA和命令。读取前/后lstat+完整输入SHA与库存一致；每文件单pass，固定总字节上限例如3GiB、单行8MiB，strict JSON含duplicate/nonfinite(包括1e999溢出)检查。这里只是可审阅上限建议，实际scope由root封存；不保证300s内吞吐。
- 对motion每行只读取真实顶层schema/epoch/record_sequence/kind/sim_time_sec/wall_monotonic_ns/payload，不执行生产数学。全文件统计kind与fault事件计数，按文件顺序保留首次reach_model_failure、normal_control_model_invalid、invalid_reach_driver_ingress、invalid_received_states，以及error=normal_control_model_invalid的control_failure和负control_ack；保留原line/record_sequence、raw_line_SHA、原payload。first不是跨文件wall排序后补出来的。
- 原时钟固定窗口244.48至244.62秒；保留该窗口实际own_odom、reach_driver_ingress、reach_intent_publish、control_request/control_failure/control_ack/control_ack_published代表记录。保留真实raw source时间、input_sequence、calibration publication_sequence、applied actuation_sequence/target/cmd_seq、storage decision_sequence及epoch，不能拿seq推时延或跨对象拼齐缺失字段。源窗口与callback窗口分别标注；错误/缺字段只报告，不补值。
- 全局首fault即使不在窗口也照固定选择规则保留，但不扩大窗口或输入。每类可固定首/末数量及≤200选行、≤2MiB输出，写selection_complete/drop计数；超限或坏JSON要保留完整FAIL receipt，不在最终allow_nan序列化异常外丢结果。
- startup保留真实exploration_failure_received的receipt原文、clock/wall/epoch，并与固定metadata负ACK作描述比较；无日志不得补“未发布”或“没收到”。
- 最多300工程秒新scope，无World/模型/训练/消费者重审。parent提交前至真实wait返回全费、TERM/KILL/actualwait及外尾由root既有owned guard机制封存；所有超时/截断/parse错误保留FAIL，不借本次改旧FAIL或资格。新执行freeze与旧证据freeze分列，当前解释源码字节须与Git1fa及source SHA一致，新增consumer由未来freeze/source seal绑定。

第一步只需把首fault的robot/reason/原记录及244.58负ACK链取出；在真实结果前不选修复、不放宽门限/源龄/20ms相位，也不重跑deadline或整链。

## 本稿实际读取的小元数据库存

以下SHA是本次只读时对小文件重新计算，读取前后stat一致；不冒充root独立关闭或归档总库存。

```json
[
  {
    "path": "/tmp/mr3_p2a_reach_v52_matrix/deadline/native.json",
    "bytes": 4714,
    "sha256": "eacdf0400f465490bf90922bc2574b3789b54edeff38870ab683d5ce14b8ac4a",
    "stat_stable_during_this_metadata_read": true
  },
  {
    "path": "/tmp/mr3_p2a_reach_v52_matrix/deadline/native.log",
    "bytes": 3486,
    "sha256": "879d797c92e58b59fc18315eba1f91eb24506fbfca0f70d3381143356224eec5",
    "stat_stable_during_this_metadata_read": true
  },
  {
    "path": "/tmp/mr3_p2a_reach_v52_matrix/deadline/stage.json",
    "bytes": 10204,
    "sha256": "45a8dea609286fcf768c7242cf2728fa8c978714a9a0f9d65c2d8054cadcc11d",
    "stat_stable_during_this_metadata_read": true
  },
  {
    "path": "/tmp/mr3_p2a_reach_v52_driver_v1/summary.json",
    "bytes": 4401,
    "sha256": "d7a0cd6f06fc9dbb9d579cf3fa73a14cee7f2dc7279dbf26541f842ad39dbbd5",
    "stat_stable_during_this_metadata_read": true
  },
  {
    "path": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v52/mr3_p2a_reach_v52_deadline/benchmark_summary.json",
    "bytes": 20329,
    "sha256": "476323e2ce2f99a23dc9977aeb1510797b328bc6e5cd8b2edbd650b958f85297",
    "stat_stable_during_this_metadata_read": true
  },
  {
    "path": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v52/mr3_p2a_reach_v52_deadline/worker0/episode001_open_101/summary.json",
    "bytes": 13672,
    "sha256": "dcaaa686408df51bb68ed5e86da29dd0cfc7a09a962716085bec007de4e13528",
    "stat_stable_during_this_metadata_read": true
  },
  {
    "path": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v52/mr3_p2a_reach_v52_deadline/worker0/episode001_open_101/infrastructure_failure.json",
    "bytes": 704,
    "sha256": "38398e4409f321f1adc785f8384f31786d31083133c20bff474f2747d8503b63",
    "stat_stable_during_this_metadata_read": true
  },
  {
    "path": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v52/mr3_p2a_reach_v52_deadline/worker0/episode001_open_101/infrastructure_cleanup.json",
    "bytes": 693,
    "sha256": "f8a0df882b61739f6e417a7bb88df8e84d2dffae2df5670657d5c66c32524f9f",
    "stat_stable_during_this_metadata_read": true
  },
  {
    "path": "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v52/mr3_p2a_reach_v52_deadline/worker0/episode001_open_101/launch.log",
    "bytes": 132205,
    "sha256": "8705f9ec3d72b2247916e36750d74649373859e66f0d775cfebb798d8187b467",
    "stat_stable_during_this_metadata_read": true
  }
]
```
