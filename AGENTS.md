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

## Current Handoff

2026-10-13: `main` was restored from P1C `99cf3a6`; the original route's latest
complete source and user files remain on `p2c1/global-mission-20261012`.
Only these two local/remote branches are maintained. The user requested
engineering repairs before providing a new research route. Do not advance old
P2/P3/network/RL checkpoints from the unchanged historical plans.

Runtime repairs, new checks, and actual simulator outcomes are recorded in
`wireless-rl/report/20261013_p1c_engineering_repair.md` and the shared `log.md`.
Current commands are in `ros2_ws/ros2-multi-robot-automap/launch_commands.md`.
The task still uses SLAM, conservative common-frame map fusion, frontier
allocation, and Nav2. Evaluator schema v3 enforces the original simulation
deadline, zero contact, monitoring availability, and navigation handshake
closure. Historical schema v2/P1C results apply only to their original source;
do not credit them to the repaired implementation.

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
