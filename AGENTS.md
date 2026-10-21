@/home/zhuyulab/.codex/RTK.md

2026-10-21 V26准备：按用户“继续”执行一次三开发场景只读几何审计，最多120工程秒（consumer90），不创建World/Node/episode或训练。几何21/守护10/元数据5项CPU通过；保留原ROI/质量门和全部旧FAIL。入场余6559.4631148643982，pilot/final-only不动；新clean冻结/前检后唯一执行，当前尚未实测。见[V26](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v26_geometry.md)。

2026-10-21 V25 CPU收口：协议117、人工建图7、导航缓存等价21项通过；仅按精确几何输入复用路径场，原scan/pair/源龄与pure源码保持。人工厚box的端点图IoU上限112/697低于.20，另有格线/2mm误差反例；不宣称实际三场不可达。下一步先量化代理质量可达性/逆传感器模型，不直接PPO或重跑V24。本轮无formal/工程新增，仍余6559.4631148643982秒，pilot/final-only不动；P2A未完成。见[V25](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v25_cpu.md)。

2026-10-21 V24闭合FAIL：冻结9b33cf9b6ab491fd5e3b15269adb30d43be1354c实跑三场，544attempt/543verified return/1rooms错误，205/173/165sim秒均未完成任务。协议确认173.1s goal_lease_expired而上次返回仍非终态、次submit才stopped；原FAIL不改/不重跑，post-advance tick分类修复已通过27项CPU，未正式重验，租约/频率/门限保持。含有限故障提取实费1371.868831523秒，累计45440.5368851356018/52000、余6559.4631148643982；20保存身份gone、无训练/原生/pilot/final-only。下一步先接口/代理质量与长步成本，不直接PPO。见[V24](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261021_mr3_p2a_v24_behavior.md)。

2026-10-20 V23闭合：profile与优化后短容量均PASS；短冻结2e8fcac9439a1a53e3913e45abccdc0b6645825d实跑1/4env、30短EP/240attempt/240verified return、0step错误/30正常关闭，73保存身份gone。含reset/close单env .240650848、四env合计 .610735060步/墙秒；仅8步短容量、无训练/原生资格。V23总实费806.844068675秒，累计44068.6680536126018/52000、余7931.3319463873982；pilot/final-only不动，旧FAIL保留，P2A未完成。见[V23](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_v23_performance.md)。

2026-10-20 V23续接授权：用户“按你的想法继续”，推进新有界性能剖析/提速及短容量：profile最多1EP/8attempt/600秒，优化后一次1/4env短容量最多30EP/240attempt/1800秒，均含审计/外尾，工程仍限52000、入场余8738.1760150623982。旧V22 FAIL不重试/改判；训练、pilot/final-only、原生迁移/gateway/扩额不启动。见[V23预声明](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_v23_performance.md)，先测再优化、每次新freeze。

2026-10-20 V22闭合：冻结`1dc2a1f601693f542479f9b6b7c54c69519b5460`二维符合性6原件+3合成及独立review通过；唯一零更新容量活动284尝试/返回、0step错误，但首场open101未完成、无实际4env，严格时间差与审计verified计数缺陷使完整活动FAIL。旧FAIL不改/不重跑；17保存身份gone，新增1781.490347088秒，累计43261.8239849376018/52000，余8738.1760150623982。pilot/final-only不动，P2A未完成；常规整数时钟/审计信用CPU修复不供新资格，训练/迁移/gateway未启动。见[V22闭合与下一步](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_v22_proxy2d.md)。

2026-10-20 V22授权：用户答复“继续，同意”，已接受二维代理实现、接口符合性和一次零更新容量活动；9000次ENV.step尝试/3600墙秒/最多30回合，1及4env共用上限，0模型/GPU/optimizer，无重试或补样。入场工程余10519.6663621503982/52000，pilot/final-only不动；训练、原生重试/迁移、60000、冻结规则变更和gateway均未授权。见[V22实现与预声明](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_v22_proxy2d.md)；旧V21/评估的“二维未批”是此前快照，以本授权为准。P2A未完成。

2026-10-20 V21实际闭合：用户指示继续P2A后，冻结`c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90`完成两回合/64步合法随机原生诊断；第一回合guard独立storage ACK回调晚于worker推进1.076029ms，Cadence/Runtime明确FAIL，原FAIL保留、不重试。来源、其余读者与关闭通过，111保存身份gone；工程累计41480.3336378496018/52000，余10519.6663621503982，pilot/final-only不动。保持现门的真实guard屏障修复已通过132项CPU，尚无修复后native资格/PPO。见[V21闭合](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_v21_feasibility.md)和[下一路线具体提案](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_next_route_proposal.md)；二维9000step/3600秒零更新活动、60000及冻结规则调整均未批准，旧60000提案按新末账也不足完整20100预约。P2A未完成。

2026-10-20交接：用户要求将本次P2A完成度/继续价值评估存档，见[P2A评估与后续交接](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_assessment_handoff.md)。建议保留联合RL底座，先有限原生可行性与容量收口，再考虑二维预训练/原生迁移，并前瞻区分执行和离线审计版本；这些路线/规则调整及60000扩额尚未批准。下一会话先按下述顺序读活动计划，再读交接，优先形成具体有界方案，不直接重跑矩阵或启动二维/PPO；既有常规修改授权与P2A未完成状态不变。本次只有评估/文档，无新实验或费用。

2026-10-20 V20历史快照（实时余额以后续V21为准）：P2A未完成。V19冻结`3631c788ca46e03a52f34ad48c41611761c17f1e`的32步原生接口及六项审计通过，阶段超时/Information -2和其余角色缺口保留，58原身份gone。V20三reader性能修复通过131项CPU、whole-source逆投影及两个完整闭合原件开发重放（Runtime339.708353551秒、Information422.782810574秒），不提供新冻结资格。末账按并行区间union纠正重复269.000729653秒：累计38216.5104974146018/52000，余13783.4895025853982。60000总额提案未批准，未启动新矩阵/PPO；pilot余额与三final-only不动。用户已授权P2A常规修改、修复和验证直接执行，不再重复询问修改批准。见[V19闭合](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261019_mr3_p2a_v19.md)与[V20末账/提案](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261020_mr3_p2a_v20.md)。

# Codex Monorepo Memory — MR3

2026-10-19：P2A.0已验收，P2A未完成。用户已批准V14科学候选并授权生产实现；V15实现显式`mr3-reach-v1`安全模式、真实应用/同源校准回执、完整模式交付及版本化必要审计器，当前完成CPU/编译准备，待新冻结完整原生资格。默认`legacy`保留，旧FAIL不改判；本轮无新native/GPU/pilot/验证，P2B/gateway未启动。见[V15实现与验证](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261019_mr3_p2a_v15.md)和[新契约](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_REACH_CONTRACT.md)。

2026-10-19用户已批准工程累计上限52000墙秒，并授权后续实现/修复直接推进；截至V18闭合工程已用32673.5464309836018/52000墙秒，余19326.4535690163982；pilot1870决策/2905.9547395464029墙秒及三场final-only额度未动。旧V13同冻结独立38/38仅有原工程信用，原矩阵/optional/minimum FAIL保留；minimum整轮ineligible、0 eligible/0更新。详见[V13原始结果](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261019_mr3_p2a_v13.md)。

## Canonical checkout and components

The only Git root is `/home/zhuyulab/ns3-workspace`. Both components belong to
this same working tree and the same `origin` (`Breeze-by/my_ns3-gym`):

- `ros2_ws/ros2-multi-robot-automap/`: ROS 2 Humble, Gazebo Classic, TurtleBot3,
  SLAM, Nav2 and collaborative mapping.
- `ns-allinone-3.40/ns-3.40/`: ns-3.40, ns3-gym and the historical wireless-rl
  toy scheduling environment; the future MR3 gateway/network component.

The ROS tree was imported using git subtree on 2026-09-02. It is not a
submodule/nested repository. The former standalone checkout and compatibility
symlink under `/home/zhuyulab/ros2_ws/` were removed; use canonical paths only.

## Read first and authority

Before research or architecture decisions read, in order:

1. `ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md`.
2. The adjacent `IMPLEMENTATION_PLAN.md` for the current acceptance boundary.
3. The adjacent `AGENTS.md` for component/environment/evidence rules.
4. `ros2_ws/ros2-multi-robot-automap/user_guide.md` and `launch_commands.md` for
   actual current ROS behavior and executable commands.
5. `wireless-rl/report/20261014_mr3_route_audit.md` and `report/README.md` as needed.

Current code determines implemented behavior. Plans describe intended work;
dated reports and native artifacts establish results only for their original
source/contract. Historical reports, archived plans and upstream READMEs do not
set the active research route. Avoid repeating detailed chronology in guides.

## Active route and user acceptance

The user's 2026-10-14 direction supersedes the earlier research route:

- Exactly **three robots**, tb1/tb2/tb3; no new 2/4/5-robot research matrices.
- First replace hand-coded global exploration decisions with a centralized
  joint RL policy. Retain SLAM/map fusion and local Nav2; start with stable
  subgoals, not unrestricted velocity or a hand-planner fallback.
- Establish a reliable **95%** mapping task under ideal communication, then
  freeze weights, normalization, observation/action and execution contracts.
- Route application uplink/downlink bytes through gateway and genuine ns-3
  Wi-Fi (1 AP + 3 STA). Received-only maps/states/goals/ACKs must causally govern
  the backend and remote shared information used by robot navigation/safety.
- No target search, charging, rally, learned communication scheduling or
  hardware work. Network remedies and deployment are outside this roadmap.

New checkpoints are namespaced **MR3-P0 … MR3-P5**, with individual substep
acceptance. Complete and verify each substep, commit/push, present evidence,
and wait for the user's explicit acceptance before the next substep.
Old P1C/P2C acceptance or PASS cannot be reused as MR3 credit.

Current boundary: **MR3-P0 accepted on 2026-10-14; MR3-P1A/P1B accepted by the user on 2026-10-15; MR3-P1C accepted by the user on 2026-10-16; MR3-P2A.0 accepted and continuation of MR3-P2A explicitly authorized on 2026-10-18; MR3-P2A in progress and incomplete**.
P1B freeze `f9928fe` passed the same-freeze open/rooms/corridors seed101 scripted
adapter audits; see the [P1B report](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261015_mr3_p1b.md).
The user authorized P2A's joint MaskablePPO minimum training/validation loop on 2026-10-16.
P2B and later remain unstarted; gateway work is not authorized.
The implemented environment contract is [MR3_ENV_CONTRACT.md](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_ENV_CONTRACT.md).
The P1C validation started on 2026-10-15; its actual closure time, capacity and conditional budgets
are in the [P1C report](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261015_mr3_p1c.md).
The [2D option](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261015_mr3_2d_option.md) awaits separate acceptance.
The 500k/72h per-run budget is a candidate, not an accepted training quota or permission to replace Gazebo.

## Current implementation and evidence

`main` was restored from P1C `99cf3a6` and repaired. Pre-route document commit
is `81b2f8b`; historical repair freeze is `c9344e1`. P1A changes the active launch and check defaults to three, retaining 1–4
compatibility without new non-three research runs. Use the explicit MR3 task
contract for 95% schema4 evaluation; legacy schema3 remains diagnostic only.

The default baseline retains handcrafted frontier control, common-frame
conservative map fusion and Nav2. The mutually exclusive adapter owns stable
goals and uses logical ideal-delivery map/state copies; it has no handcrafted
exploration fallback. P1C implements the Gymnasium/IPC environment, full reset and isolated
reward ledger. The W7 `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a` engineering matrix and independent audits are complete,
with 762 ROS semantic and 40 conda CPU checks. P1C was accepted on 2026-10-16.
The retained `b328f84` GPU interface probe has 3 forward/3 backward calls and 0 updates;
P1C made no new GPU training or multi-day stability claim.
P2A has separate eight-decision native engineering checkpoints (seed17 and seed41,
four GPU optimizer steps each). The v2 pilot was diagnostically interrupted after
390 recorded native decisions and zero updates, preserving two peer-safety failures.
Versioned v3 candidate/SLAM/Nav2 changes have native short-subgoal evidence.
The v4 16-decision chain passed native/reward/policy audits with four GPU updates.
Its pilot was diagnostically interrupted after 242 native decisions and zero
updates for a policy-independent discount/objective mismatch; all outcomes remain
preserved. V5 uses gamma=lambda=1 for the finite task, retaining one bootstrap for
external truncations. Its pilot retained 48 GPU optimizer steps and 797 saved
training samples before a genuine 40ms terminal-detection infrastructure failure;
all 16 attempts and three descriptive strict successes are preserved. No final
checkpoint was produced, so its final-only development validation was skipped.
V6 `af37b2a` adds an exact-clock evaluator ACK at each 20ms policy boundary.
Its two-episode terminal probe and fresh 16-decision/four-update minimum pass
independent native/scalar/policy/ACK audits. Its pilot retained 718 native
decisions and zero updates before a genuine controlled-shutdown Karto abort
(SLAM exit -6); all 167 saved process identities and its parent are gone. No
final model exists, so its final-only validation is skipped. That v6 pilot stopped
in P2A under its no-retry rule; the later P2A.0 preparation continuation does not restart it. The user explicitly approved a cumulative
4096-decision/14400-wall-second pilot ceiling plus three development validations;
2226 decisions/11494.045260453597 seconds have been charged across pilot versions,
leaving 1870/2905.954739546403 unused. The 2026-10-18 continuation uses a newly
declared freeze and preserves that remaining ceiling; it does not restart v6. There is
no frozen-policy reliability or 95% P2A acceptance credit; no validated exploration policy or ROS/ns-3 gateway exists. Historical
five-user/15-input/5-action toy DQN is a separate task.
P1A now measures all six actual body collisions per robot (18 streams), with
continuous freshness, raw publication-sequence audit and navigation terminal
closure. Freeze `5e47802` has 9 effective scene/seed slots: 6 strict successes
and 3 peer-envelope safety failures. All 10 attempts retain one native shutdown
infrastructure failure; a prospectively declared same-freeze replay fills its
slot without proving the SDK crash fixed. See the
[P1A report](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_p1a.md)
and shared `log.md`. The historical
`c9344e1` rooms/corridors seed101 90% evidence and base-only zero-contact records
retain their original scope; they do not supply MR3 credit.

The explicit ROI/95% contract, scene audits and sustained contact monitoring
are implemented for P1A. P1B adds exclusive goal ownership, deterministic
observations/candidates/masks and received-information navigation copies in
ideal mode. Same-process/DDS delivery is not P3A isolation or byte transport.
K8 and the 5 s commitment describe this interface version, not a 95% task proof.
The accepted P1B nominal 1 s asynchronous timer had 2/3 s gaps in rooms; that historical
behavior is not a fixed-dt training claim. P1C independently validates explicit 1000-tick/1 s
stepping in 20-tick quanta, real 50 Hz clock phase/drain barriers and full process rebuilds
at W7. The non-stepped timer nominal cadence and skip rules are unchanged. Actual payload transport, absence of
network bypasses and network-coupled causal clocks remain later gates.

## Engineering judgment

Use independent engineering judgment, simple direct solutions, existing code
and mature dependencies. Preserve correctness, data safety and research
validity; do not limit necessary analysis or validation to save tokens.
User requirements take precedence over repository preferences. Keep scope
focused. The two removed coding-guideline skills must not be reinstalled,
invoked, or used as constraints (user preference 2026-10-12).

Do not hide a hand-coded exploration policy behind the RL adapter, expose truth
to actor/candidates/masks/safety, loosen failed task gates, cherry-pick seeds,
or assemble a matrix across different code freezes. Ground truth is permitted
only for isolated evaluation/training reward and network propagation position.
Local own sensors remain local; cross-robot information must respect delivery.

## Environments

Wireless-rl/ns3-gym Python uses conda `ns3gym`, preserving
`PYTHONNOUSERSITE=1`; see nested instructions. ROS nodes use system ROS Python:

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
export PYTHONNOUSERSITE=1
/usr/bin/python3 /usr/bin/colcon build --symlink-install --allow-overriding nav2_bringup nav2_velocity_smoother
source install/setup.bash
```

Do not copy old ROS build/install/log directories or mix conda and ROS Python
through ad hoc PYTHONPATH. Colcon absolute-path caches must be regenerated at
the canonical location when needed. Preserve evidence logs; only stop owned
process groups. Separate wall-clock startup guards from sim-time task budgets.

## Git, push and experiment discipline

Only `main` and original-route backup `p2c1/global-mission-20261012` are maintained.
The backup's latest complete state is `8fe1495`; leave it untouched unless the
user requests otherwise. Do not create extra archival branches, force-push or
rewrite shared history. Both components stay together on each feature branch.

Every completed modification must be committed and pushed to `origin` in the
same session unless explicitly instructed otherwise. Before every commit:

1. Run the shortest relevant checks; documentation-only changes need static
   links/consistency/evidence checks, not simulator or training runs.
2. Run `git diff --check` from the Git root.
3. Run `git add -n .`; exclude accidental build/runtime/log/bag/map/checkpoint
   artifacts. Selected canonical research evidence may be intentionally tracked.
4. Commit focused changes and push the current branch.

Whenever a launch argument, default component, recommended mode or copy/paste
launch command changes, update ROS `launch_commands.md` in the same commit.
Every training, evaluation, baseline, ablation, formal smoke, simulator or
hardware experiment is appended, including failures/interruptions, in the
same session to:

`ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/log.md`.

Record exact command, freeze, seeds, parameters, outputs and conclusion. Keep
one canonical evidence set. Do not relabel old failures or rewrite experiment
history; archive/supersession locations belong in `report/ARCHIVE_INDEX.json`.
