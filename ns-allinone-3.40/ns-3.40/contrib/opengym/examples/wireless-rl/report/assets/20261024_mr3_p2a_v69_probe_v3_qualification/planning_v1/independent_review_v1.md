# PROBE_V3 A/B 独立静态复核

2026-10-24；只读当前源码和 Root 获准的 V68 派生文件 `/tmp/mr3_p2a_v68_probe_stimulus_description_v1.json`（692872B，SHA5124587818aed33a3a74f225341809f8f889422dd2772e2fd474f5498edd2951）。未读原两输入，未运行 producer/reader/CPU/World，未改 canonical。另读 helper 停写方案 `/tmp/mr3_p2a_reach_probe_v3_proposal_v1/PROPOSAL.md` 和 `proposal_v1.json`。

推荐 B，与 helper 方案核心一致：取消 hard endpoint>1.45；GOAL 仅依原合法 candidate/joint/nonapproach 及生命周期条件，不要求累计运动计量已初始化；同一真实接受且 active/owned 的 goal 后，首个 fresh/valid/finite/complete、activity.last_odom_source_stamp>=accepted_at 且<=当前snapshot时间的路径观测，捕获一次保守baseline。之后不刷新，保留v>=.08、相对该baseline新增path>=.05、原WAIT mask/5scommit/真实取消确认/rest/handoff全部门。

原因是两处阻断都已实际出现：task0 fresh/valid/idle/unowned和候选mask可用，但path=null/complete=False；task1这些common全部满足，却没有合法候选端点超过1.45。路径累计器未初始化不是原GOAL接口的安全禁止条件：`mr3_observation._action_masks`745–774 不依赖activity累计path，而 B 对真正计入运动/WAIT的路径要求保持。不能将null补0；baseline必须在accept后首次合格时捕获，早期已经发生的位移不计入新增.05，因而在计量上更保守。

A确为更少文字改动：只去hard1.45，继续保留GOAL path前提。已知前缀task1因此具备条件机会，但原initial窗口task<1.5只剩一个整数决策，实际accept必须<=task2。A不一定失败，B也不被这份无GOAL前缀证明为物理必要；B的优点是恢复task0原合法机会，消除启动计量与首次GOAL的耦合，同时不降低实际movingWAIT门。

基线必须带同一epoch/round/goal_id/command_id和实际snapshot sequence/digest、activity.state_sequence、last_odom_source_stamp；错误goal、未接受、unowned、非active、旧source、不完整/非finite或重复观测不得捕获。capture_count必须为1，后续zero/WAIT/重传/第二次complete不重捕获。首合格计量永不出现、自然SUCCEEDED早于可取消时刻或覆盖不足，都保留最终FAIL，不重试或延长。

## 原rank能复用的准确边界

保留**当前v2**排序与原joint/nonapproach原语即可；1.45只作既有名义距离readback，不需要新threshold/tiebreak或bank调整。原 `_probe_goal_order(outward=True)`（benchmark99–129）在外向margin后带升序path项；旧Reach-v1 alias实际走probe_action_v6→v4→v3并直接用原项，而当前v2在order中显式 `-base[3]` 才将该项变为长path优先。因此不能把v1/v2整个rank说成逐字相同。不要复制v1的 `path or 0`、any-owner moving、提交WAIT即信用、late15–26等较弱路径；仅复用原语和已审v2排序。

单机mask可用8/5/4不证明存在同时三机GOAL且满足原joint/nonapproach。派生描述只有原joint总数，没有全部bits，不能在这里补造counterfactual joint选择或可达保证。

## 32步内的条件时间余量

原 `GoalDispatcher.on_accept`294–310 从**实际接受交付时间**a启动5秒承诺，不从GOAL created_at启动，不额外机械加2秒TTL。合法WAIT是原mask第一次允许且实际movement条件满足的整数决策；a<=2时承诺最迟到7。通常GOAL0比GOAL1能提前一个采样机会，但实际回调/数据延迟未知，不能保证。

initial科学WAIT必须<=10。第一次接收terminal在c时，三条递增新鲜rest源样本且至少c+3后才能handoff；c<=10时可条件赶task13。若handoff晚，只能使用原13<=task<20（整数13..19）的剩余GOAL机会；second accept仍必须<=20。second承诺最迟到25，movingWAIT须<=28，final snapshot32仍须具备所需真实terminal和三rest；任一实际延迟可令覆盖失败。

短目标可能在5秒承诺解除前自然完成。端点/规划path长度只是刺激排序参考，既不是速度/轨迹证明，也不能保证活跃到首合法WAIT；B只修前提，不证明六GOAL/两轮完整取消覆盖。原B停车界、R/一次anchor/永久servo退出、received-only、5commit、32步/6GOAL/2round及独立native物理门保持。

## 后继实现准入事项

helper方案中的真实 GoalDispatcher/原observation masks CPU是合适的最小验证：GOAL0 pathnull仍合法；accept前/错goal/旧path_source不能capture；一次capture且不重捕；baseline前位移不计.05；forward .08/.05/commit/WAIT mask原边界；自然terminal和cleanupWAIT不补科学credit；missing handoff阻second；final32不足显式FAIL。新profile和原v1/v2分支需独立reader/plan/readiness/inventory全链登记，不能只有producer。

两个已知入口问题也必须随新freeze准备：matrix child argv使用 `[python,'-m','mr3_learning.reach_preparation',...]`，只outer加-B/无bytecode环境，不改原qualifier；若新token修改Supervisor，该模块属于A66实际21 build输入，必须新当前source实际有界build/manifest/bridge，不借旧A66输入证据（CPP/law/flags可不变，增量sameELF需诚实记录）。原V67 FAIL和V68描述PASS均不重判，capacity仍False，不自动pilot/final。
