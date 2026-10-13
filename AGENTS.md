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

## Engineering Judgment

Use independent engineering judgment. Keep changes focused, preserve correctness
and research validity, and complete necessary validation. The two removed
coding-guideline skills must not be reinstalled, invoked, or used as constraints.

## Current Handoff

2026-10-13 recovery_v2 通用所有权候选完整组件1780PASS242.18s，4包build/source/native/Future/static/declaration与独立复审PASS；恢复原绝对探索等待目标，区分未发主/延后需求与已发请求/真实Nav2/原生返航，保持原模型和硬门限。预定新run-id `20261013_p2c_global_recovery_v2` 从四开发重新验证，无新任务信用，正式/物理/917均未运行。详细证据只在单一累计报告及log。

2026-10-13 中断恢复冻结 `9405e296cd176df82d598686aa1d7ede0be32e35` 的四开发与完整审计已关闭：forced/rooms/corridors严格PASS，lab晚发现后RALLY300.4s timeout，完整门禁FAIL；未运行正式/物理/917。原件run-id `20261013_p2c_global_recovery_v1`，不能补格或混拼v11。下一候选恢复有一致机会成本的原绝对等待评分，并修复已构造确证的“未发充电意图挡住真实返航清道”通用所有权问题；不放宽原预算/源龄/完成或物理门限。signed-energy修复 `d54ccd3` 及全部原FAIL保持，详细证据只在单一累计报告和log。

2026-10-13 新全局实现冻结 `9bb2c2c40a62f7b0819d5c2d4345595a9ad7fc61`：四开发完整严格PASS；15非留出正式严格10PASS/5FAIL（9原生COMPLETE、5timeout、1预声明空电池FAILED），两受控物理安全PASS。延迟格仅安全/协议PASS，物理fault任务也timeout，不提供任务完成信用。917未运行，P2C.1未完成。独立能量读者已按原native signed-meter约定修正，1644功能PASS；旧冻结FAIL保持，runtime/Native模型不变。全部实验/审计进程关闭。详见单一累计报告 `ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261012_p2c1_global_mission.md`，避免按单格继续叠规则或跨版本拼矩阵。

2026-10-12 用户授权接手 P2C.1 全局工作。长会话继续暂停，恢复基线 `b32c891` 的安全预算/本地返航/能量/Future 契约保留；当前独立分支 `p2c1/global-mission-20261012` 使用全局规划工作线程和统一导航所有权，选择性取回有原扫描证据的 SLAM 自体回波修复。新候选须以同一推送冻结完成四开发、17 正式和两物理，组件检查不计任务信用。详细实现与新原件结果集中在 `ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261012_p2c1_global_mission.md` 和实验 log，不能把历史 v95 PASS 算到本轮。P2C.1B 仍未完成，917 留出未调用，无 ROS/ns-3 Wi-Fi 联合实验。

v95 四开发与首正式 lab101 的单格 PASS 属于已回退版本的历史结果，不是当前源码的完整任务信用。当前判断见 [恢复审查](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261012_p2c1_session_recovery.md) 和 [补强评审](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261009_p2c_strengthening_review.md)。

2026-10-12 按用户要求清理：已回退长会话的逐候选报告和大型附件移出当前工作树，完整原件保存在 `backup/project-before-report-cleanup-20261012`；失败、超时及原始账本保留。文件位置与 Git 对象见 [归档索引](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/ARCHIVE_INDEX.json)。详细时间线集中在 `ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/log.md` 与日期报告中，不再复制进每份规划、指南和 AGENTS.md。

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

## Documentation Maintenance

Plans and guides describe current contracts and current status. Keep detailed
experiment chronology in the shared experiment log and dated reports, with
links rather than copies in every guide. Retain one canonical evidence set
and reference it. Historical failures remain available in the archive and
must not be relabeled as successful. User-requested archival cleanup is
recorded in the archive index.
