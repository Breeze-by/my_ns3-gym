# Codex Monorepo Memory

This is the single Git repository for the multi-robot task-oriented Wi-Fi RL
research project. Its Git root and canonical local checkout are:

```text
/home/zhuyulab/ns3-workspace
```

The repository contains both active components in the same working tree:

```text
ns-allinone-3.40/ns-3.40/
    ns-3, ns3-gym, and wireless-rl code

ros2_ws/ros2-multi-robot-automap/
    ROS 2 Humble, Gazebo, TurtleBot3, SLAM, Nav2, and multi-robot exploration
```

The ROS 2 tree was imported from `Breeze-by/ros_mutirobot_nav` with
`git subtree` on 2026-09-02. It is not a submodule or nested Git repository.
The monorepo `origin` (`Breeze-by/my_ns3-gym`) is now the source of truth for
both components. The former standalone checkout and compatibility symlink
under `/home/zhuyulab/ros2_ws/` were removed on 2026-09-02. Use only the
canonical monorepo path above.

## Read First

Before making research or architecture decisions, read:

1. `ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md`
   for the final thesis goal, system boundary, metrics, risks, and roadmap.
2. `ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/IMPLEMENTATION_PLAN.md`
   for engineering checkpoints, exit criteria, and current progress.
3. `ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/AGENTS.md`
   for the current ns-3 experiment state, environment, results, and rules.
4. `ros2_ws/ros2-multi-robot-automap/user_guide.md` for the current ROS 2 task
   stack, launch commands, topics, and troubleshooting.

Planning documents describe intended work, not functionality that is already
implemented. Use current code as the source of truth and dated reports/logs as
the source of experimental claims.

## Coding Guidance Note

Ponytail and `karpathy-guidelines` are advisory lenses for simplicity, scope
control, and careful reasoning. They are not absolute rules or token-saving
targets. User intent, correctness, required validation, safety, research
validity, and a complete solution take priority. Use independent engineering
judgment: prefer simple solutions when they satisfy the requirements, but add
necessary instrumentation, tests, abstractions, or experiments when they make
the result correct and reviewable.

User clarification (2026-09-23): learn the useful workflows and engineering
habits in these two skills (tools, testing, iteration, identifying pitfalls),
but never let their brevity or minimalism prescriptions limit creativity or
problem-solving. Try alternative methods when evidence warrants it. Saving
tokens is not a reason to leave a problem unresolved or inadequately tested.

## Current Handoff

As of 2026-09-23, the user has accepted P1C, P2A, P2B, P2C, and P2D. Each robot has
a local distance/time energy model, safety-reserve return, a distinct charging
pose, and charge/resume behavior. A forced-charge two-robot episode completed
with two charges, no exhaustion, and zero collisions. The P2C follow-up adds
visual-only Gazebo task regions and a default-on per-robot status panel for
manual runs; battery managers are also enabled by default. P2D's final fixed
matrix has ten `COMPLETE`, zero-collision episodes across three worlds
(lab/rooms energy 40, corridors energy 45), including a two-robot corridors
cross-check. P3A is implemented and awaiting user acceptance; its formal
gateway matrix is historical because later HEAD commits changed the
coordinator, battery, and clearance logic. The current-HEAD P3A.5 run at
`41f63fb` passed the graph/bypass subgate and forced-charge regression, but
only 9/10 formal episodes completed: lab seed 202 failed after episode start
in `RALLY`. The failed episode is retained as a historical failed candidate; the
current P3A.6 evidence below supersedes it.
Update 2026-10-01: P3A.6 integration gate passed and accepted by the user on 2026-10-01.
The clean frozen task-stack commit is `22c95a770a8812452c43fc177e4a00b5c032e6ef`.
Three same-commit batches cover all ten fixed cells (1+7+2), all COMPLETE
with zero collisions, exhaustion, failed robots, infrastructure failures or
whole-episode retries. The same-commit forced303 regression completed in
190.4 s with each robot charging once and zero collisions. 127 component
checks, four-package build, source audit and eleven graph audits pass.
RPP, ray information gain, hierarchical viewpoints, visible waypoints,
nearest off-route refuge, relevant-TF throttling and serial gateway-mediated
early charging are now part of the frozen baseline. Historical failures remain
retained. The final report and source/environment/protocol hashes are in
report/20261001_p3a6_freeze.md and .json under wireless-rl. P3B.5 is the next
checkpoint; no network/RL work was started. Task-stack changes require a new
integration batch. Development seeds 101/202/303 are not held-out tests.

The revised plan adds the previously missing
P2D full ideal-task integration gate, splits ns-3 time/packet coupling from
Wi-Fi calibration, and fixes formal run/statistical rules. From P2B onward only
`COMPLETE` is mission success; `FOUND` and 90% coverage are process metrics.
The roadmap review requires deterministic stale-message fault tests before
ns-3, and treats `101/202/303` as development/integration seeds rather than
final held-out test seeds.
Before P3 exits, all central map/pose/detection and Nav2 direct paths, plus robot
Nav2's direct `/merge_map` subscription, must be replaced by the same gateway
path used by every baseline, including ideal. Follow the revised checkpoint
table in `IMPLEMENTATION_PLAN.md` and do not skip directly from component tests
to network/RL work.

The detailed metrics, validation commands, known limitations, and intentionally
uncommitted user report files are recorded in the nested `wireless-rl/AGENTS.md`.

## Environments

All wireless-rl Python/ns3-gym commands must run in conda environment
`ns3gym`. Preserve `PYTHONNOUSERSITE=1`; detailed commands are in the nested
wireless-rl `AGENTS.md`.

ROS 2 commands use ROS 2 Humble and the in-repository workspace:

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
colcon build --symlink-install
source install/setup.bash
```

Do not copy old ROS `build/`, `install/`, or `log/` directories into this tree;
colcon caches absolute source paths. They are ignored and must be regenerated
at the canonical path.

## Git And Push Discipline

The user requires every completed modification to be committed and pushed to
`origin` in the same work session. Do not leave verified source or documentation
changes only in the local checkout unless the user explicitly asks for that.

Before every commit:

1. Run the shortest relevant build/test/smoke check.
2. Run `git diff --check` from the repository root.
3. Run `git add -n .` and confirm that build artifacts, runtime outputs,
   checkpoints, maps, bags, and logs are not being staged accidentally.
4. Commit focused changes, then push the current branch to `origin`.

Whenever a launch argument, default-enabled component, recommended run mode,
or copy-paste launch command changes, update
`ros2_ws/ros2-multi-robot-automap/launch_commands.md` in the same commit.

Do not force-push or rewrite shared history unless the user explicitly requests
it. Feature branches contain both ns-3 and ROS 2; do not place the two components
on mutually exclusive branches.

Every training, evaluation, baseline, ablation, formal smoke, simulator run, or
hardware experiment must also be appended in the same work session to:

```text
ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/log.md
```

Record failures and interruptions as well as successes, with exact command,
code state, seeds, parameters, outputs, and conclusion.

2026-10-04 P3B.5 v43完整57次候选已自然结束，冻结584dadc；最终严格门禁FAIL，尚未完成P3B.5。十固定格原生合格COMPLETE，57次均0接触/0基础设施失败，57份时序账本审计PASS，425组件/四包build/54协议矩阵通过；这些不能代替完整门禁。主强制充电ideal中央297.5s声明COMPLETE，但300.0s截止时success=false、completion_time_sec=null、native_rally_hold_proof=null、termination=timeout，各机器人虽充电一次仍未合格。零注入zero_rally_lab同样RALLY超时，作为稳定性限制保留，不归因于通信损伤。完整原始结果、源/环境/协议/命令/graph/ledger哈希、观察器关闭与严格checker traceback见report/20261004_p3b5_forced_native_hold_failed_candidate.json；全部原格保留，不重跑回填或放宽300s/5s/位速阈值。当前需继续独立开发改进集合能量/时间分配并重新冻结。707此前011786e已暴露，584为同算法基础设施复验；下一次控制算法变化后必须使用预先冻结、真正未暴露的新留出组合，不再把707称为未暴露验证。P3A.6已验收22c95a7历史冻结保持；无ns-3/Wi-Fi/RL实验。
