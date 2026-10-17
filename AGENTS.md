@/home/zhuyulab/.codex/RTK.md

# Codex Monorepo Memory — MR3

2026-10-17 continuation: P2A.0 remains authorized and incomplete. V13 freeze 1cfe74b4ad32 failed its first parameter response-reader match before any step; all originals are closed and archived in 60f932ed, with terminal/reset/deadline skipped. V14 adds only nine exact parameter-response writer waits of 1 second and retains all original client/task/body/stop gates, movement sources and actual a014 drive library. Source/CPU checks passed and the plan is ready; actual native admission still requires the new clean pushed exact40 preflight. No V14 native has started. Complete one reviewed clean pushed same-freeze four-stage matrix, commit/push evidence, then await user acceptance. No PPO/P2B/gateway; pilot balance1870 decisions/2905.954739546403 wallsec unchanged. See wireless-rl/report/20261017_mr3_p2a0_v14.md.

Historical first P2A.0 closure (2026-10-17): source freeze f8694025; six native episodes
closed cleanly, terminal audit PASS, reset benchmark/full audit FAIL with one
real peer-envelope task failure. The 300-step deadline was SKIPPED under the
prospective stop rule. P2A.0 exit is unmet; await user review, do not restart
pilot. Shared navigation-map occupied starts are now proved from exact raw maps.

2026-10-17 update: the user authorized continuing P2A and adding preparation.
Current work is MR3-P2A.0 (SLAM ownership teardown, failed collection evidence,
versioned received-frontier union and safety diagnostics). No new pilot is run
in this substep; the cumulative pilot balance remains 1870 decisions /
2905.954739546403 wall seconds. P2A.0 requires its own evidence and user
acceptance before the next preparation/training substep; P2A is unfinished.
See `wireless-rl/report/20261017_mr3_p2a0.md` at the canonical path below.

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

Current boundary: **MR3-P0 accepted on 2026-10-14; MR3-P1A/P1B accepted by the user on 2026-10-15; MR3-P1C accepted by the user on 2026-10-16; MR3-P2A authorized and in progress**.
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
leaving 1870/2905.954739546403 unused, without an automatic new run. There is
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
/usr/bin/python3 /usr/bin/colcon build --symlink-install --allow-overriding nav2_bringup
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
