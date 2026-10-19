# V14 received-state safety intent 接线设计（只读，未实施）

本稿只描述未来接线与 CPU 验证计划。没有修改生产、启动 native/正式消费者、取得科学 PASS、开放训练或新增预算。原 V13 matrix/optional/minimum FAIL 永久保留；新 38-role preparation 资格也不是策略成功证明。

## 真实现状与最小接线

当前只有一个 `IdealInformation`（一个 `IdealTransport/ReceivedStore`）、一个为三机生成障碍的 `PeerObstacles`、一个循环调用三逻辑 guard 的 `MotionSafety`。现有 ideal broadcast 是中央逻辑已交付副本，不是三个隔离网络端点，也没有 P3 的真实字节网络或独立延迟 fanout 证明。

受控 worker 已有 state→peer→motion→实际 native target 存储→20 个真实 tick 的顺序。Peer 真正匹配整 bundle 与 received odom/TF；Motion 真正订阅 state/peer ACK，并核同一完整 bundle SHA。这条链可以复用。每次 guard phase 必须先冻结同一完整 bundle/intent table，三次 guard 调用只读此表；不能先修改 tb1 本机意图，再让 tb2 从共享本机字典读取未交付的新值。

新增 source-owned `safety` 仅作为 `Envelope.payload` 的 sibling；原 odometry/transform/map bytes 不变。用已有 `std_msgs/String` canonical JSON 即可，不需要新 ROS 消息依赖。Motion 为各逻辑本机发布严格 typed intent；Information 从真实本地订阅接收、验证 owner/epoch/robot/seq/source/bytes，再把安全 sidecar 放进同一 state envelope。worker 只传前一个真实 motion ACK 的 expected intent refs，绝不把 worker 字典当成 intent 的交付。Information 必须等自己的订阅确实收到匹配 bytes 才 ACK。

state ACK/peer ACK/motion status 采用明确新版本，逐层绑定整 state bundle SHA 和 safety table SHA。由于 SHA 已覆盖整个 payload，额外 digest 是审阅索引，不是第二套可以不同步的真值。三逻辑 guard 同时核自己的 delivered self-intent 和 peer intents。own local sensor 继续本地；peer intent/geometry 仅来自相同收到的 state 表。

## D→X→N 的实际时序

1. **T, before next state commit**：Freeze one received bundle and intent table for all three logical guards. In D/HOLD, a request to start translation creates immutable pending X with declared admitted_signs and old anchor; the actual issued target at T is v=0,w=0. Publish owner intent and return its exact refs in the motion ACK; this publication is not storage or actuation.

2. **T, paused storage barrier**：Existing worker waits the exact three real driver storage receipts for current outputs. Match epoch/robot/clock/decision sequence/native cmd sequence and actual zero; no advance if missing or overwritten. Keep old D/HOLD physical obligation and conservative X bridge; do not re-anchor.

3. **T+20ms state phase**：Request exact refs from previous actual motion ACK (or explicit post-release bootstrap intents), never worker-invented intent bytes. Information independently receives source intents, waits for matching refs, and serializes the whole safety sidecar inside the immutable state envelope. Preserve odom/TF originals, existing measured source stamps and map streams. Carry separate intent evidence source/age; a historical anchor does not become a fresh source.

4. **T+20ms peer phase**：PeerObstacles must actually receive the matching entire state bundle plus raw odom/TF side publications. Validate all three typed sidecars, exact refs, table digest and unchanged .5s ages, then produce obstacle ACK bound to the whole bundle/table. Its cloud computation still uses existing received odom/TF; metadata does not create a new peer position.

5. **T+20ms motion phase**：MotionControlPhase requires its own actual subscriptions to the same state and peer ACKs, exact common bundle/table digest, and per-robot self-announcement matching the frozen table. All three guard calls read the same immutable table. Only then can a command within the preannounced signed family be nonzero; all corresponding geometric roles remain X (q=4R) until actual takeover is evidenced. A changed/reversed sign needs a new union/announcement or stopping, never hindsight sign fitting.

6. **later actual wheel update A**：Native OnUpdate selects target under the existing command mutex, computes unchanged paired outputs, performs all actual wheel writes, and publishes a new typed actuation receipt before releasing the same phase. The receipt records actual consumed seven-field target, native cmd_seq, actuation_seq/time, dt, each pair index and actual current/desired/applied rim values, alpha and acceleration bound, plus payload/result identity.

7. **later local source O strictly greater than A**：Guard admits only actually received/causally promoted native actuation receipts; waits a matching own raw odom with source O>A and O<=guard clock. Same-clock odom cannot qualify: current OnUpdate publishes odom before wheel actuation. Check fresh raw consistency/model bounds and the declared signed role. Storage ACK alone, later unrelated odom, an audit JSON row or receipt publication alone cannot narrow X to N.

8. **next complete delivered N state**：Owner emits N intent with exact actuation/raw witnesses. All logical guards continue using X until the new N intent is actually delivered inside a new matching common state/peer bundle. Only then may they narrow to N(q=2R). Future re-anchor into a new D needs proven executed N lineage followed by genuine zero/rest qualification and a newly delivered anchor; a nonzero publication or unconsumed target cannot refresh the old D anchor.

这两个20ms阶段必须占用现有真实 task quanta；不得另走不计费的物理步、移动300s起点、增加 actor action 或先发非零后补包。缺交付/回执保持适当保守角色并零输出；永久 stop 仍不能恢复。反转需预先声明 old/new sign union 的逐 cone 检查或先停车，不能从实际 vx 事后选有利符号。

当前 `mr3-drive-target-consumed-v1` **只证明存储**，真实 actuation 消费身份仅存在 `drive_tbN.jsonl`。父代理已选择完整 native typed actuation receipt，明确不选“永远X”的另一简化合同。新 receipt 在原 OnUpdate command mutex/phase 内，原 paired 计算及全部实际 wheel writes 完成后真实发布；包含原七字段 target、native cmd_seq、actuation_seq/time/dt、每 pair 实际 current/desired/applied/alpha/acceleration 及其 canonical identity。source 未来的包只排队，不能先消费。在线 guard 禁止读取审计 JSON 文件当测量。

该 receipt 不证明 body 已按指令运动。X→N 仍须同目标的实际 receipt **实际到达**，然后出现 source 严格晚于 actuation 的本机 raw odom。当前同一次 OnUpdate 先发 odom 后更新轮，因此同 clock odom 无论 wall 到达顺序如何都不能作后响应。N 本机判定完成后，其他 guard 仍保持X，直到 N 被下一 state/peer phase 实际送达。后续新 D anchor 必须有 genuine executed N→真实新 zero/rest/delivery 完整谱系；仅发过非零、stored 后未用、零脉冲或重复资格都不能刷新旧 anchor。

## Sidecar 最少字段

- `schema`：new explicit mr3-safety-intent-v1 (proposed name; not implemented)
- `identity`：epoch；robot；strict positive intent_sequence；canonical intent payload SHA；source owner/node/publisher packet GID and graph custody
- `lineage`：previous intent identity/hash；role HOLD/D/X/N/STOP with explicit restrictions；admitted_signs immutable tuple, not measured actual sign；fixed anchor id/own odom source/digest/position and calibration identity；release timestamp and complete qualification watermark
- `timing`：source_clock_ns；real evidence_source_ns and received time kept distinct；not_before_clock_ns；explicit validity/fallback commitment; no freshening historical anchors or issue timestamps
- `target_evidence`：authorizing_zero_target: original seven exact target fields at T；exact eventual actual target references in actuation receipt, not a claim of future physical application；native cmd_seq/actuation_seq/clock and strictly later raw source/digest before N
- `embedding`：Envelope.payload["safety"] alongside x/y/yaw/v/w/odometry/transform, not inside ROS odometry/transform. All safety values are canonical immutable JSON bytes included in payload SHA and bundle SHA.
- `calibration`：Same native odometry source supplemental actual c/s metadata keyed by epoch/robot/source/odom SHA, conversion contract and producer identity; never ModelStates. It too must be bound to the same delivered state if a peer physical proof uses it.

outer state 的原 min(odom,TF) 源时间与 actor age 语义保留。安全 metadata 另有真实 evidence source/age，必须同时满足原 `.5s` 因果年龄门；历史 anchor/contract issue time 不能被更新成 now。若同源补充 calibration 或 intent 当前源不匹配，不得靠新 state 时间给它刷新资格。

## Bootstrap 的明确初始条件

- **required_new_condition**：Explicit conditional initial HOLD terminal invariant: for each robot, while initial full zero HOLD persists, centre remains within radius R=.0078 of one immutable release anchor and full planar residual<=.01; all pair checks use that declared role and original body/margin/age gates. This is a plant assumption to falsify/validate, not a fact proved by stored zero or three samples.
- **release_anchor**：Bind the actual release clock to the exact last successful controlled state/peer bundle and each corresponding already-allowed own raw odom payload. Own and received anchors use these fixed identical source identities; no SLAM-history remapping. Reject missing/mismatched raw anchor or calibration. Earlier source time may define the anchor if genuinely causal/fresh; it does not grant pre-release publication credit.
- **bootstrap_protocol**：Owner emits explicit PRE_RELEASE no-credit intents and zeros for initial phase, then post-Header RELEASE_HOLD intents bound to actual release and release bundle. Worker waits those real source refs; Information independently receives them before the next commit. This prevents a source-callback race and does not add a policy action/feature or move task release.
- **qualification**：.94 zero-publication qualification is clamped to release (existing release() behavior); all three qualifying raw samples must be later than release+.94, causal/fresh with original gap constraints. Before qualification only v=0,w=0; no angular settled exception. Original .78 stored-zero/160ms timing audit remains required.
- **not_proven**：Initial disk invariance, continuing terminal rest and continuous-time residual/sweep are not implied by finite CPU traces. If no such explicit source/plant assumption is defensible, bootstrap admission is blocked; generic .144 stop cannot silently substitute because original close initial spacing may fail that larger reach.

原 `SettledTurnTracker.release()` 已把 zero_since clamp 到 release 并清空 samples。该行为必须保留：release 后完整 `.94s` 与三条更晚新鲜 raw 才能给资格，此前全零（包括 angular=0）。初始 storage ACK 不是静止证明；三条过去 raw 不是未来 invariant 证明。初始 HOLD 的固定R disk是明确的新 plant 条件，必须独立审阅/校准和后续验证；不能偷用出生/释放前 publication 当 PUB credit。若此条件不成立，则 bootstrap 不能准入，不能悄换较大 generic stop 或借旧 PASS。

## WORLD body 转换的校准缺口与选定方向

- **fact**：Existing WORLD producer samples model WorldPose/WorldLinearVel once, then float yaw and cosf/sinf convert to body XY. A=[[c,s],[-s,c]], q=c²+s²; q is generally not 1, so raw body norm<=.01 is not itself an exact WORLD residual certificate.
- **selected_minimal_direction**：Same native odometry producer publishes typed supplemental actual c/s (and exact odom source/pose/payload identity and conversion contract). Information carries this inside the same safety sidecar; no new ModelStates subscription, no new actor fields and no extra WORLD velocity truth payload. Root CPU prototype calibration_metric_v1.py is mathematical only, not an implemented ROS conversion.
- **conditional_metric**：For actual finite coefficients and IEEE64 RN, including FMA/non-FMA envelope: E=(2u+u²)*V*(|c|+|s|)+(3+2u)*eta, u=2^-53, eta=2^-1075, V=.3. Full residual bound compares (|b0|+E)^2+(|b1|+E)^2 <= limit^2*q. Signed wrong-forward bound and lateral bound use the same q; STOP/empty signs uses the full speed. Exact outward arithmetic, never a threshold epsilon.
- **double_only_limit**：Changing yaw/c/s to double reduces error but does not make q exactly1 and is not sufficient proof. Such producer revision requires its own source/ELF binding and conversion-rounding qualification; the metric must use the coefficients actually used.
- **remaining_obligations**：V=.3 and floating-point/underflow/rounding assumptions must be explicitly part of the source model, not proved by this metric or by old samples. The normalized c/s axis must be calibrated against true physical heading/pose; a rigorous sector enclosure includes conversion angular error. An odom frame string alone does not prove this. Current WORLD odometry was already the accepted local measurement representation. Adding coefficient metadata is an explicit new measurement-calibration payload/contract; do not claim bytes/information schema unchanged. Directly adding WorldLinearVel XY would enlarge payload and needs separate reviewed information contract; not selected here.

map 与 raw 各自完整 certificate 再 AND（见 directional addendum v2）；不能混用 map 距离和 raw 方向，亦不能把 directional AND 称为标量 mincap。共同 WORLD 原点/参考点/同 producer 校准及 cone 中真实方向误差是外部条件，单有 frame 字符串、timestamp 或 exact CPU Fraction 不证明这些物理条件。

## 必须显式升级的入口

- **Information receive_state_phase_request, lines452-456**：当前 Exact five-key request set plus schema v1: rejects added expected_intents. 未来 New version with explicit exact expected_intents refs; do not weaken the old v1 parser.
- **Envelope/ReceivedStore**：当前 Canonical arbitrary JSON payload, no safety schema/authentication. Extras accepted mechanically. 未来 Keep immutable transport and original sequence/age rules; strict new safety validator at producer ingress and every safety consumer.
- **restore_message(Odometry/TransformStamped), Information134-141**：当前 Sets every supplied key as ROS message field. Unknown keys inside native ROS payload fail. 未来 Safety only a sibling to raw ROS payloads; raw originals unchanged.
- **DriveTarget ParseDriveTarget, header40-58**：当前 Exactly seven fields, schema mr3-drive-target-v1. 未来 Keep unchanged. New actuation publication uses separate topic/schema; embeds exact original target value.
- **DrivePhaseClient.receive35-44**：当前 Exact nine-key storage schema mr3-drive-target-consumed-v1; extra keys fail. 未来 Keep unchanged. A separate strict actuation receipt parser/causal queue must not reinterpret storage as wheel consumption.
- **PeerObstacles current bundle/request and MotionControlPhase dependency parsers**：当前 Some top-level extras are tolerated, but v1 schemas/scope and full canonical dependency equality are checked. Motion checks actual received bundle SHA. 未来 New v2 state/peer/motion phase/status contract, exact sidecar validation and intent-table digest. Permissive old parsing does not constitute validation of a new safety promise.
- **ControlPhaseClient.valid_motion_status19-36**：当前 Schema mr3-motion-safety-status-v1 and exact output shape; a v2 status is rejected. 未来 Explicit new status/phase version and independent replay; retain old fixtures/results.
- **Immutable information oracle, selection/send344-411; publish475-494**：当前 Reconstructs exact state from old raw schema and demands canonical envelope payload equality. Adding safety changes this equality; new ledger kinds are also not understood. 未来 New versioned information reader reconstructs original measurement projection identically, then separately replays real intent ingress/selection/delivery and full new payload. Do not strip new safety data to obtain an old PASS.
- **audit_motion plus source-pinned full/FIFO/control/drive custody entries**：当前 Old configuration/helper identities and old guard replay/event vocabulary reject or fail to assess the new contract. 未来 New explicit reader/version/provenance and reviewed source/ELF pins. Old physical wheel math stays original. Newly added events/actuation evidence must be consumed rather than silently ignored.
- **Adapter _robot_state and learner observation encoder**：当前 Existing explicit field projection excludes unknown safety metadata from the snapshot/tensors. 未来 Keep observation-v3/tensor-v2 dimensions/action-mask/candidate rules. Test complete byte/tensor equality for identical original inputs with differing safety metadata; retain safety evidence in separate audit records/watermarks.

保留原七字段 target 与九字段 storage ACK，不塞新字段进去。新 receipt 用独立 schema/topic。旧 information oracle 会逐 canonical payload 比较由 raw 重建的旧状态，因此不能把 safety 填进去后仍声称旧 reader 原字节 PASS；新 reader 必须同时重建原测量投影和新元数据实际交付。旧 motion 数学及 helper pins 同样不能冒充新 D/N/X 合同审计。旧 archive/FAIL 不改。

actor 侧现有 `_robot_state` 枚举字段投影和 tensor encoder 不读取 safety metadata。保持此投影：同原输入仅改变安全 metadata，原 snapshot 投影、tensor、candidate/mask、map payload 需精确不变；真实安全拦截导致将来的真实位置/地图变化属于自然执行影响，不应伪造相等。

## 最小文件范围（未来候选）

- `/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py`：Intent owner, immutable per-phase table, zero-first handoff, bootstrap release anchoring, genuine local actuation/calibration receipt ingress and raw-after-actuation lineage.
- `/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_safety.py`：New version of conditional D/N/X/HOLD reach/qualification semantics; old failed cumulative-path contract must remain historical, not mislabeled as passed.
- `/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_information.py`：Actual local intent/calibration subscription, typed admission/causal history, safety sibling in state envelope, source ledger, expected-ref readiness and v2 ACK.
- `/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/peer_obstacles.py`：Typed safety table from actual bundle, matching intent refs/table digest in phase ACK; preserve cloud math/received side topics.
- `/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_control_phase.py`：Explicit v2 typed refs/status validation, bootstrap intent reference barrier; preserve one outstanding phase/idempotence/stop semantics.
- `/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_control.py`：Actual subscribed v2 state/peer ACK and frozen full bundle/table equality; one common view for three logical guards.
- `/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py`：Wait owner-published bootstrap refs, feed previous motion refs into next state phase; maintain real storage/physics barriers and all existing terminal/zero-tail rules. New handoffs occupy existing 20ms quanta, not extra hidden task time.
- `/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_gazebo_diff_drive.cpp`：New readonly typed native actuation and same-source conversion metadata publications at the actual producer; preserve paired limiting/wheel writes/physical cadence. Future source/ELF freeze and native revalidation required.
- `/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_gazebo_diff_drive.hpp`：Only declarations/state for new receipt publisher/measurement coefficients if class storage requires it; no new dependency beyond current std_msgs JSON.
- `one small pure parser/state module if needed (proposed mr3_safety_intent.py)`：One exact canonical sidecar/receipt validator reused by nodes/tests; no generic transport framework, no duplicated rules.
- `new versioned independent audit entry plus corresponding tests and audit_ppo/preparation pins/plan/binding/contract docs`：Information delivery, mode lineage/geometry/calibration, drive receipt/actual actuation, phase FIFO, release bootstrap, source/ELF custody. Each changed scientific role explicit; unchanged roles not removed.

`mr3_adapter.py/mr3_observation.py` 与 learner encoder 首选不改生产字段；只加证明忽略 sidecar 的测试。驱动新增纯发布仍需新源码/ELF及同冻结复验，不能由于 paired 数学未改而借旧执行 PASS。新审计来源/plan/binding/contract 文档必须准确记录修改角色；不得移除科学消费者或直接复用旧 FAIL 为 PASS。

## 具体 CPU 测试计划（未运行）

- **delivery_bytes**：Mutate original dict after send; mutate decoded received copy; missing/extra safety keys, bool-as-int, NaN/Inf, wrong schema/robot/epoch, unknown role/signs. All malformed fail closed; immutable bytes stable.
- **real_ingress**：Worker supplies plausible refs but Information never receives source intent; wrong packet GID/multiple owners; wrong topic/robot; queued source later than target. No state ACK/nonzero; do not manufacture envelope from RPC refs.
- **common_view**：Each of state, peer, motion sees different intent bytes with same claimed id; changed table digest; shuffled guard iteration order; arrival of a newer bundle between phases. Require actual canonical equality and all three logged decisions use the same frozen table.
- **age**：.5s accepted only for otherwise valid state/evidence; +1ns rejects. Future/reordered/duplicate-conflicting intent sources reject. Old anchor identity may remain old but renewal must carry real fresh evidence and must never rewrite anchor/source history.
- **D_to_X**：Nonzero requested while D: first actual published/stored target is zero. No X delivery, only X publisher return, wrong state phase, stale peer ACK, one missing robot => no nonzero. Exact next true20ms complete state/peer X permits only the announced signed family.
- **storage_vs_actuation**：A zero/nonzero target is stored then overwritten before wheel update. Storage never counts as actual takeover or anchor refresh. Later odom alone and audit-file presence do not repair missing online actuation receipt.
- **actuation_identity**：Wrong epoch/robot/native cmdseq/target clock/decisionseq/actuationseq/pair order/result hash; dropped pair or mismatched paired arrays; duplicate changed record. Strict parser rejects; unchanged duplicate idempotent only.
- **causal_source**：Actuation receipt source A may arrive before /clock A; retain pending until causal. Raw source=A rejects for N, raw source>A<=clock with exact target witness can advance owner state. Wall arrival ordering cannot override source ordering.
- **N_delivery**：Owner N computed locally but envelope still X => every logical guard keeps X. Full delivered N permits narrowing only after actual lineage proof. Mode reversal requires predeclared old/new sign union or stop; actualvx sign cannot select a convenient sector after observation.
- **reanchor**：Repeated zero grants, zero pulses, nonzero publication not actuated, pending-X canceled, or a single changed scalar must not reset old anchor/qualification. Only actual executed handoff followed by complete new zero/rest/delivery lineage may create a new anchor.
- **bootstrap**：Pre-release .94 history, stamps before release, repeated release, wrong release bundle/raw anchor, missing explicit initial HOLD terminal assumption, nonzero w before qualification, zero ACK mistaken for rest. Reject qualification/advance as appropriate. First valid grant requires full release-based .94 plus three later causal fresh samples and original storage audit.
- **information_boundary**：Hold delivered peer records fixed and alter forbidden raw peer/SLAM/truth/oracle data: per-robot guard geometry must not change. Local own sensors still allowed. A source-identity mismatch or unavailable calibration denies; no fallback to live peer raw/ModelStates.
- **actor_and_maps**：Vary only safety sidecar bytes; original observation JSON projection, all encoded tensors/dimensions, masks/candidates, goals, original maps and navigation-map payloads remain identical for identical original inputs. Real motion effects are allowed to alter later genuine observations, never falsified to force equality.
- **calibration**：q!=1 counterexample, wrong-sign forward residual, STOP with residual=full planar speed, FMA/non-FMA rounding and subnormal bounds, c/s metadata from another odom/source/pose, missing actual coefficients. No epsilon, no new truth; body/publication match alone not a calibration proof.
- **failure_and_close**：Stop during each pending phase, timeout, missing receipt, actual model failure, terminal cancellation, changed saved identity. Preserve actual samples/errors and original forbidden-training behavior; no buffer/GAE/optimizer admission from an invalid round. No hidden extra reset/action/native retry.

本稿及 synthetic CPU 条件即使通过，仍只证实协议/数值/几何实现，对 plant 未来行为、原连续路径失败、95%任务、actor可训练性和 native admission 都不给信用。当前尚缺 online actuation receipt 接线、初始 terminal invariant 与测量/真实 heading 校准；它们是后续 enable 前的明确阻塞条件，不是一个可忽略的 PASS 注脚。

## 读取来源

JSON 同名原件保存当前实际读到的源码 bytes/SHA 和行范围，以及依赖设计/metric原件 SHA。这里只读哈希，不运行 source_check、不宣称当前 Git HEAD/clean 等于历史 runtime freeze，不改任何生产或预算。
