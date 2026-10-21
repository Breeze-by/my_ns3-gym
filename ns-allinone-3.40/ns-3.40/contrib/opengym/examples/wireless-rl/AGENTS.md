# wireless-rl memory — MR3

2026-10-21 V27 CPU候选已闭合：sensor-only mapper-v2未接默认；68项检查、14组人工对比完整，局部格线改善伴随free覆盖下降、corner退化，持续+2mm仍false-free=.04，free饱和首次hit仍free。保留禁用候选，不直接完整行为/PPO；先明确当前hit否决free、歧义unknown与量测假设，再设计新版本。工程新增0，仍45445.4237026666018/52000、余6554.5762973333982，pilot/final-only不动；P2A未完成。见[V27](report/20261021_mr3_p2a_v27_mapping.md)。

2026-10-21 V26已闭合：三场实际几何条件上包络.390342/.484456/.513595均高于原.20门，未排除也未证明可达；ROI子界未收紧。仅计算/来源/关闭PASS，无World/episode/训练/native资格。main+final工程union4.886817531，累计45445.4237026666018/52000、余6554.5762973333982，7保存身份gone，pilot/final-only不动。下一步转sensor-only mapper-v2 CPU边界/证据累计候选，不再收紧静态界或直接PPO；P2A未完成。见[V26](report/20261021_mr3_p2a_v26_geometry.md)。

2026-10-21 V25 CPU收口：协议117、人工建图7、导航缓存等价21项通过；仅按精确几何输入复用路径场，原scan/pair/源龄与pure源码保持。人工厚box的端点图IoU上限112/697低于.20，另有格线/2mm误差反例；不宣称实际三场不可达。下一步先量化代理质量可达性/逆传感器模型，不直接PPO或重跑V24。本轮无formal/工程新增，仍余6559.4631148643982秒，pilot/final-only不动；P2A未完成。见[V25](report/20261021_mr3_p2a_v25_cpu.md)。

2026-10-21 V24闭合FAIL：冻结9b33cf9b6ab491fd5e3b15269adb30d43be1354c实跑三场，544attempt/543verified return/1rooms错误，205/173/165sim秒均未完成任务。协议确认173.1s goal_lease_expired而上次返回仍非终态、次submit才stopped；原FAIL不改/不重跑，post-advance tick分类修复已通过27项CPU，未正式重验，租约/频率/门限保持。含有限故障提取实费1371.868831523秒，累计45440.5368851356018/52000、余6559.4631148643982；20保存身份gone、无训练/原生/pilot/final-only。下一步先接口/代理质量与长步成本，不直接PPO。见[V24](report/20261021_mr3_p2a_v24_behavior.md)。

2026-10-20 V23闭合：profile与优化后短容量均PASS；短冻结2e8fcac9439a1a53e3913e45abccdc0b6645825d实跑1/4env、30短EP/240attempt/240verified return、0step错误/30正常关闭，73保存身份gone。含reset/close单env .240650848、四env合计 .610735060步/墙秒；仅8步短容量、无训练/原生资格。V23总实费806.844068675秒，累计44068.6680536126018/52000、余7931.3319463873982；pilot/final-only不动，旧FAIL保留，P2A未完成。见[V23](report/20261020_mr3_p2a_v23_performance.md)。

2026-10-20 V23续接授权：用户“按你的想法继续”，推进新有界性能剖析/提速及短容量：profile最多1EP/8attempt/600秒，优化后一次1/4env短容量最多30EP/240attempt/1800秒，均含审计/外尾，工程仍限52000、入场余8738.1760150623982。旧V22 FAIL不重试/改判；训练、pilot/final-only、原生迁移/gateway/扩额不启动。见[V23预声明](report/20261020_mr3_p2a_v23_performance.md)，先测再优化、每次新freeze。

2026-10-20 V22闭合：冻结`1dc2a1f601693f542479f9b6b7c54c69519b5460`二维符合性6原件+3合成及独立review通过；唯一零更新容量活动284尝试/返回、0step错误，但首场open101未完成、无实际4env，严格时间差与审计verified计数缺陷使完整活动FAIL。旧FAIL不改/不重跑；17保存身份gone，新增1781.490347088秒，累计43261.8239849376018/52000，余8738.1760150623982。pilot/final-only不动，P2A未完成；常规整数时钟/审计信用CPU修复不供新资格，训练/迁移/gateway未启动。见[V22闭合与下一步](report/20261020_mr3_p2a_v22_proxy2d.md)。

2026-10-20 V22授权：用户答复“继续，同意”，已接受二维代理实现、接口符合性和一次零更新容量活动；9000次ENV.step尝试/3600墙秒/最多30回合，1及4env共用上限，0模型/GPU/optimizer，无重试或补样。入场工程余10519.6663621503982/52000，pilot/final-only不动；训练、原生重试/迁移、60000、冻结规则变更和gateway均未授权。见[V22实现与预声明](report/20261020_mr3_p2a_v22_proxy2d.md)；旧V21/评估的“二维未批”是此前快照，以本授权为准。P2A未完成。

2026-10-20 V21实际闭合：用户指示继续P2A后，冻结`c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90`完成两回合/64步合法随机原生诊断；第一回合guard独立storage ACK回调晚于worker推进1.076029ms，Cadence/Runtime明确FAIL，原FAIL保留、不重试。来源、其余读者与关闭通过，111保存身份gone；工程累计41480.3336378496018/52000，余10519.6663621503982，pilot/final-only不动。保持现门的真实guard屏障修复已通过132项CPU，尚无修复后native资格/PPO。见[V21闭合](report/20261020_mr3_p2a_v21_feasibility.md)和[下一路线具体提案](report/20261020_mr3_p2a_next_route_proposal.md)；二维9000step/3600秒零更新活动、60000及冻结规则调整均未批准，旧60000提案按新末账也不足完整20100预约。P2A未完成。

2026-10-20交接：用户要求保存本次评估，先读活动计划后读[P2A评估与后续交接](report/20261020_mr3_p2a_assessment_handoff.md)。建议停止原样扩额重验循环，先具体化有限原生可行性/容量方案，再考虑二维预训练和执行/审计版本分层；这些调整尚未接受，本次不是新实验/训练或60000扩额授权。常规修改授权保留，P2A未完成、原FAIL/预算/资格门不变。

2026-10-20 V20历史快照（实时余额以后续V21为准）：P2A未完成。V19冻结`3631c788ca46e03a52f34ad48c41611761c17f1e`的32步原生接口及六项审计通过，阶段超时/Information -2和其余角色缺口保留，58原身份gone。V20三reader性能修复通过131项CPU、whole-source逆投影及两个完整闭合原件开发重放（Runtime339.708353551秒、Information422.782810574秒），不提供新冻结资格。末账按并行区间union纠正重复269.000729653秒：累计38216.5104974146018/52000，余13783.4895025853982。60000总额提案未批准，未启动新矩阵/PPO；pilot余额与三final-only不动。用户已授权P2A常规修改、修复和验证直接执行，不再重复询问修改批准。见[V19闭合](report/20261019_mr3_p2a_v19.md)与[V20末账/提案](report/20261020_mr3_p2a_v20.md)。

2026-10-19：P2A.0已验收，P2A未完成。用户已批准V14科学候选并授权生产实现；V15实现显式`mr3-reach-v1`安全模式、真实应用/同源校准回执、完整模式交付及版本化必要审计器，当前完成CPU/编译准备，待新冻结完整原生资格。默认`legacy`保留，旧FAIL不改判；本轮无新native/GPU/pilot/验证，P2B/gateway未启动。见[V15实现与验证](report/20261019_mr3_p2a_v15.md)和[新契约](MR3_REACH_CONTRACT.md)。

2026-10-19用户已批准工程累计上限52000墙秒，并授权后续实现/修复直接推进；截至V18闭合工程已用32673.5464309836018/52000墙秒，余19326.4535690163982；pilot1870决策/2905.9547395464029墙秒及三场final-only额度未动。旧V13同冻结独立38/38仅有原工程信用，原矩阵/optional/minimum FAIL保留；minimum整轮ineligible、0 eligible/0更新。详见[V13原始结果](report/20261019_mr3_p2a_v13.md)。

P1C validation started 2026-10-15; actual closure time is in the P1C report. The active contract is [RESEARCH_PLAN.md](RESEARCH_PLAN.md),
then [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Follow root AGENTS.md.
MR3-P0 was explicitly accepted on 2026-10-14; MR3-P1A was accepted on 2026-10-15 and the user authorized P1B.
P1B was accepted by the user on 2026-10-15. The user accepted P1C and authorized P2A's
joint MaskablePPO minimum training/validation loop on 2026-10-16. The user accepted
P2A.0 and explicitly authorized P2A continuation on 2026-10-18. P2A is in progress and incomplete;
P2B and later remain unstarted. The 2026-10-20 2D implementation/conformity/9000-step/3600-second zero-update activity is accepted; 2D training and the candidate 500k/72h quota remain unaccepted; gateway work is not authorized.
The implemented environment contract is [MR3_ENV_CONTRACT.md](MR3_ENV_CONTRACT.md).
This route replaces the old search/charging/rally/communication-scheduler plan.

## Task and source of truth

Exactly three robots. First learn centralized joint exploration subgoals under
ideal communication, retain local SLAM/Nav2 and conservative fusion, prove a
95% task; then freeze the policy and its interfaces and route actual application
bytes through gateway and ns-3 Wi-Fi (one AP, three STA). Stop at measured
network effects; remedies, hardware, other team sizes and target/charging/rally
are out of scope. Detailed method decisions live in the plan and
[route audit](report/20261014_mr3_route_audit.md), not in historical report instructions.

Default baseline retains handcrafted ROS frontier allocation; the mutually
exclusive adapter owns stable goals and consumes logical ideal-delivery copies.
P2A has separate eight-decision engineering checkpoints (seed17/41, four GPU steps each).
The v2 pilot diagnostic interruption retains 390 native decisions, zero updates and
two peer-safety failures. The v4 16-decision native/reward/policy chain passed with
four GPU updates; its pilot diagnostic stop retains another 242 native decisions,
zero updates and one genuine peer-safety failure. V5 corrects the finite-horizon
objective to gamma=lambda=1 while retaining external-truncation bootstrap.
Its pilot retained 48 optimizer steps/797 saved samples before a genuine 40ms
terminal-detection infrastructure failure; three strict successes remain
descriptive sampling outcomes. No final checkpoint exists and final-only
validation was skipped. V6 `af37b2a` adds an evaluator exact-clock/terminal ACK at each20ms boundary;
its two-episode terminal probe and16-decision/four-update minimum pass the
independent gates. Its pilot preserves718 native decisions/zero updates before
a genuine SLAM Karto abort(-6) during controlled shutdown. All167 saved process
identities and its parent are gone; no final.zip exists, so final-only validation
is skipped. The session stops in P2A under the no-retry rule. User-approved
cumulative pilot4096decisions/14400wall seconds has charged2226/11494.045260453597,
leaving1870/2905.954739546403 unused. The newly authorized continuation must use
a new declared freeze and preserve that ceiling, without restarting v6. There is no
frozen-policy reliability or95% P2A acceptance credit; no validated robot policy or ROS/ns-3 gateway exists. P1C implements Gymnasium
tensors/IPC, full process rebuild, explicit stepping and isolated first-correct-cell rewards.
W7 `cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a` has the complete eight-stage engineering matrix and independent audits,
762 ROS semantic and 40 conda CPU checks. The unchanged `b328f84` GPU interface probe
retains its original 3-forward/3-backward/0-update scope; P1C itself performed no
policy training. P2A GPU evidence is separately versioned above. Freeze `f9928fe`
passed all three same-freeze open/rooms/corridors seed101 adapter audits; see the
[P1B report](report/20261015_mr3_p1b.md). K8/5 s are this interface version,
not 95% task evidence. The P1B asynchronous nominal 1 s timer had 2/3 s rooms gaps;
P1C supplies separate stepped 1 s/reset/1-2-4-worker evidence. The non-stepped timer nominal cadence and skip rules are unchanged. P1A launch/check defaults are three;
1–4 compatibility remains.
MR3 evaluation uses an explicit hash-bound 95%/300s schema4 task contract. Plans are
not implemented features. P1A includes 18-stream body contact/freshness audit
and 9 effective slots at freeze `5e47802` from 10 attempts, including one
retained native infrastructure failure; see the [P1A report](report/20261014_mr3_p1a.md).
Historical runtime freeze `c9344e1` has only 90% three-robot
rooms/corridors seed101 engineering credit, not a new 95% or multi-seed result.
Its evidence remains in [repair report](report/20261013_p1c_engineering_repair.md).

The actual ROS workspace is:
`/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap`.
Read its `user_guide.md` and `launch_commands.md` for current commands.
The Git root is `/home/zhuyulab/ns3-workspace`, origin is `Breeze-by/my_ns3-gym`.
Original route backup: `p2c1/global-mission-20261012@8fe1495`, not active work.

Current code is the implementation authority. [report/README.md](report/README.md)
separates current engineering, route audit and historical evidence. Old P1C/P2C
and toy DQN results cannot count as MR3 acceptance. Do not read historical
“next steps” as instructions. User acceptance is required after each MR3 substep,
not after running every old branch of the project.

## Learning, ROS and ns-3 environment boundaries

Wireless-rl Python commands must use conda `ns3gym`:

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
export PYTHONNOUSERSITE=1
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
```

Check before diagnosing imports/CUDA; this does not launch a simulation:

```bash
which python
python -c "import ns3gym; print(ns3gym.__file__)"
python -c "import torch; print(torch.__file__, torch.__version__, torch.cuda.is_available())"
```

Python must resolve under `/home/zhuyulab/miniconda3/envs/ns3gym/bin/`.
Historical environment checks (2026-09-02) saw Python3.10.20, NumPy2.2.6,
PyTorch2.11.0+cu128 and two RTX4090. Verify versions at implementation time;
these are not a fresh hardware probe. User-site CPU torch previously shadowed
CUDA torch; preserve PYTHONNOUSERSITE instead of reinstalling blindly.

ROS nodes run system ROS2 Humble Python, not conda. The learning environment
uses explicit IPC; do not merge interpreters via PYTHONPATH. Two GPUs help the
learner but do not establish Gazebo sampling speed. Worker isolation/reset and throughput are measured in MR3-P1C; short engineering
runs do not establish multi-day training stability. New Gymnasium/algorithm dependencies must be
version-pinned and checked independently of the legacy Gym/ns3-gym API.

## Legacy toy toolchain (only when specifically needed)

[USER_GUIDE.md](USER_GUIDE.md) now describes only the historical scheduling toy.
Its state is 5 users x `(CQI, queue, backlog age)`, action serves one user,
15 inputs/5 actions. Service/arrival and reward are implemented in `sim.cc`;
backlog age is not packet delay, misses are not packet drops, and this is not a
Wi-Fi PHY/MAC simulation. Retained toy weights cannot initialize a robot policy.

For explicit toy maintenance, keep reward/current-state snapshots distinct,
baseline semantics aligned across `test.py` and `run_baselines.py`, and old
checkpoints incompatible when state/action shape changes. Use a new ns-3
process per formal seed; globals make multi-iteration reset unproven. Keep
training, validation and final test seeds disjoint. Historical held-out seeds
2001–2010 establish only this toy; all exact data remain in dated reports.

If toy `sim.cc` changes, build from the ns-3 root in the conda environment:

```bash
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40
./ns3 build wireless-rl
```

`check_project.py` includes a build and simulator run; run it only for relevant
implementation/environment changes, not as an automatic response to document
work. Every simulator check is an experiment requiring the shared log.

## Required engineering and evidence rules

- RL decides exploration; a protocol/safety adapter must not silently call
  handcrafted goal scoring, bad-target reallocation or truth-based masks.
- Preserve stable goal IDs, acceptance/cancel/result ownership and source ages.
  Adapter mode uses logical received map/state copies; baseline retains raw
  shared Nav2 map and all-peer odom/TF. P3A must still prove byte transport,
  DDS/process isolation and absence of bypasses; ideal objects do not prove this.
- Preserve genuine contacts, truth/model boundaries and fixed measurement ROI.
  No held-out tuning, changing time/safety gates after failure or cross-freeze matrices.
- Append all training/evaluation/baseline/ablation/smoke/simulator attempts,
  including failures, to [log.md](log.md), with commands/freeze/seeds/outputs.
- Keep plans/guides concise current contracts. Date reports, retain immutable
  original assets, and record archival/supersession in [ARCHIVE_INDEX.json](report/ARCHIVE_INDEX.json).
- Generated runtime, ROS build/install/log, bags, maps, weights and pycache are
  ignored by default. Only deliberately selected evidence enters Git.
- Verify the change, diff-check, dry-run staging, commit and push to origin in
  the same session. Update ROS launch_commands.md if run modes/commands change.
