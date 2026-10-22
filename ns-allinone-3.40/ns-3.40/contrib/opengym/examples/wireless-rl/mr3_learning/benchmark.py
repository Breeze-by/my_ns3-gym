"""Predeclared scripted sampler/reset measurements; never policy training."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import threading
import time

from .env import MR3Env
from .supervisor import (
    InfrastructureError, Supervisor, WORKSPACE, identity_alive, ros_environment,
    PREPARATION_PROBE_REACH_V1, validate_preparation_profile,
    SEED_RULES, START_GRAPH_RULES, validate_seed_rule, validate_start_graph_rule,
)


PARAMETER_REVIEW_SCRIPT = Path(
    "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/"
    "20261017_mr3_p2a0_v13/independent/mr3_actual_nav2_parameters_v13.py")
GENTLE_PARAMETER_REVIEW_SCRIPT = Path(
    "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
    "mr3_learning/audit_nav2_parameters.py")
REACH_PARAMETER_REVIEW_SCRIPT = GENTLE_PARAMETER_REVIEW_SCRIPT.with_name("audit_reach_nav2_parameters.py")
PARAMETER_REVIEW_PROFILE = Path(
    "ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/mr3_fastdds_loopback_udp.xml")
TRANSPORT_ENV_KEYS = (
    "RMW_IMPLEMENTATION", "ROS_LOCALHOST_ONLY", "FASTRTPS_DEFAULT_PROFILES_FILE",
    "SKIP_DEFAULT_XML", "FASTDDS_DEFAULT_PROFILES_FILE", "RMW_FASTRTPS_USE_QOS_FROM_XML",
    "RMW_FASTRTPS_PUBLICATION_MODE")
PREPARATION_PROBE_V2 = "mr3-p2a0-outward-cancel-v2"
PREPARATION_PROBE_V3 = "mr3-p2a0-outward-cancel-v3"
PREPARATION_PROBE_V4 = "mr3-p2a0-outward-cancel-v4"
PREPARATION_PROBE_V5 = "mr3-p2a0-outward-cancel-v5"
PREPARATION_PROBE_V6 = "mr3-p2a0-outward-cancel-v6"
SAFETY_CONTRACTS = ("legacy", "mr3-reach-v1")


def _collection_safety_contract(args):
    """Engineering selection cannot reuse legacy preparation qualification."""
    profile = getattr(args, "safety_contract", "legacy")
    validate_seed_rule(getattr(args, "seed_rule", "legacy"))
    validate_start_graph_rule(getattr(args, "start_graph_rule", "original-seed-cell"),
                              seed_rule=getattr(args, "seed_rule", "legacy"))
    if profile not in SAFETY_CONTRACTS:
        raise ValueError("unknown safety contract")
    version = getattr(args, "preparation_probe_version", None)
    uniform_seed = getattr(args, "diagnostic_uniform_seed", None)
    if uniform_seed is not None:
        if type(uniform_seed) is not int or uniform_seed < 0:
            raise ValueError("diagnostic uniform seed must be a nonnegative integer")
        if (any(getattr(args, name, False) for name in (
                "preparation_motion_probe", "preparation_parameter_review",
                "terminal_probe", "deadline_probe", "fault_probe"))
                or version is not None
                or getattr(args, "preparation_parameter_profile", "original") != "original"):
            raise ValueError("diagnostic uniform actions cannot be combined with other probes")
    validate_preparation_profile(profile, version)
    if version is not None and not getattr(args, "preparation_motion_probe", False):
        raise ValueError("preparation probe version requires preparation motion probe")
    if profile == "mr3-reach-v1":
        preparation = getattr(args, "preparation_motion_probe", False)
        review = getattr(args, "preparation_parameter_review", False)
        selection = getattr(args, "preparation_parameter_profile", "original")
        if preparation and version != PREPARATION_PROBE_REACH_V1:
            raise ValueError("reach preparation requires its explicit new fixture version")
        if review and (not preparation or version != PREPARATION_PROBE_REACH_V1
                       or selection != "gentle_turn_v1"):
            raise ValueError("reach parameter review requires the reach fixture and gentle_turn_v1")
        if selection != "original" and not review:
            raise ValueError("nonoriginal parameter profile requires the explicit parameter review")
    return profile


def diagnostic_uniform_action(snapshot, generator):
    """Uniform legal joint input, without goal ranking, filtering or a model."""
    mask = snapshot["joint_action_mask"]
    if (type(mask) is not list or len(mask) != 1000
            or any(type(valid) is not bool for valid in mask)):
        raise ValueError("diagnostic uniform actions require the actual 1000-bit boolean mask")
    legal = [action for action, valid in enumerate(mask) if valid]
    if not legal:
        raise ValueError("diagnostic uniform actions require at least one legal joint action")
    return generator.choice(legal)


def _probe_goal_order(snapshot, action, outward_goals):
    choices = (action // 100, action // 10 % 10, action % 10)
    paths = sum(snapshot["candidates"][choice]["path_distances_m"][index] or 0.
                for index, choice in enumerate(choices) if choice < 8)
    goal_count = sum(choice < 8 for choice in choices)
    if not outward_goals:
        return (-goal_count, -paths, action)
    margins = []
    for index, choice in enumerate(choices):
        if choice >= 8:
            continue
        own, goal = snapshot["robots"][index], snapshot["candidates"][choice]
        gx, gy = goal["x"] - own["x"], goal["y"] - own["y"]
        goal_distance = math.hypot(gx, gy)
        peer_margins = []
        for peer_index, peer in enumerate(snapshot["robots"]):
            if peer_index == index:
                continue
            px, py = peer["x"] - own["x"], peer["y"] - own["y"]
            denominator = goal_distance * math.hypot(px, py)
            peer_margins.append(-(gx * px + gy * py) / denominator
                                if denominator else -1.)
        margins.append(min(peer_margins, default=-1.))
    return (-goal_count, -min(margins, default=-1.), -sum(margins), paths, action)


def probe_action(snapshot, *, outward_goals=False):
    """Explicit external cancellation-stress inputs, not a mapping baseline."""
    elapsed = snapshot["task_elapsed_sec"]
    mask = snapshot["joint_action_mask"]
    second_goal_start, second_goal_end = (13., 15.) if outward_goals else (10., 12.)
    goal_window = elapsed < 1.5 or second_goal_start <= elapsed < second_goal_end
    if goal_window:
        return min((action for action, valid in enumerate(mask) if valid),
                   key=lambda action: _probe_goal_order(snapshot, action, outward_goals))
    if (10. <= elapsed < 13. if outward_goals else elapsed >= 7.):
        return next(action for action in range(999, -1, -1) if mask[action])
    return 888


def probe_action_v3(snapshot, diagnostics):
    """32-step external turn/stop stimulus, never a policy or safety proof."""
    elapsed, mask = snapshot["task_elapsed_sec"], snapshot["joint_action_mask"]
    samples = diagnostics.setdefault("reference_turn_samples", {})
    if elapsed < 10.:
        for robot in snapshot["robots"]:
            w = robot.get("w")
            if (robot.get("fresh") is True and type(w) in (int, float)
                    and math.isfinite(w) and abs(w) >= .1 and robot["name"] not in samples):
                samples[robot["name"]] = {
                    "sign": math.copysign(1., w), "w": w,
                    "snapshot_sequence": snapshot.get("sequence"),
                    "source_stamp": robot.get("source_stamp"),
                    "odom_source_stamp": robot.get("odom_source_stamp"),
                }

    def reverse_robots(action):
        result = []
        for index, choice in enumerate((action // 100, action // 10 % 10, action % 10)):
            own = snapshot["robots"][index]
            reference = samples.get(own["name"])
            if choice >= 8 or reference is None:
                continue
            goal = snapshot["candidates"][choice]
            dx, dy = goal["x"] - own["x"], goal["y"] - own["y"]
            if not math.hypot(dx, dy):
                continue
            angle = math.atan2(dy, dx) - own["yaw"]
            bearing = math.atan2(math.sin(angle), math.cos(angle))
            if bearing * reference["sign"] <= -.25:
                result.append(own["name"])
        return result

    second_goal = 13. <= elapsed < 15.
    if elapsed < 1.5 or second_goal:
        legal = [action for action, valid in enumerate(mask) if valid]

        def order(action):
            base = _probe_goal_order(snapshot, action, True)
            return ((base[0], -len(reverse_robots(action)), *base[1:])
                    if second_goal else base)

        action = min(legal, key=order)
        max_goals = -_probe_goal_order(snapshot, action, True)[0]
        opportunities = [value for value in legal
                         if -_probe_goal_order(snapshot, value, True)[0] == max_goals]
        diagnostics.setdefault("goal_decisions", []).append({
            "snapshot_sequence": snapshot.get("sequence"), "task_elapsed_sec": elapsed,
            "stage": "second_goal" if second_goal else "initial_goal", "action": action,
            "max_legal_goal_components": max_goals,
            "max_reverse_robot_opportunities": max(len(reverse_robots(value))
                                                   for value in opportunities),
            "selected_reverse_robots": reverse_robots(action),
            "scope": ("received goal-bearing stimulus only; actual turn/stop coverage "
                      "audited separately"),
        })
        return action
    if 10. <= elapsed < 13. or elapsed >= 28.:
        return next(action for action in range(999, -1, -1) if mask[action])
    return 888


def probe_action_v4(snapshot, diagnostics, *, nonapproaching_goals=False,
                    late_goal_window=False):
    """Received-only bounded motion/cancel stimulus; never physical credit."""
    state = diagnostics.setdefault("v4_stimulus", {"rounds": {}, "decisions": []})
    if state.get("pending_submission") is not None:
        raise ValueError("previous preparation action submission is unresolved")
    elapsed = snapshot["task_elapsed_sec"]
    round_id = "initial" if elapsed < 13. else "second"
    current = state["rounds"].setdefault(round_id, {"waits": {}, "baseline_path_m": {
        robot["name"]: robot["activity"].get("estimated_path_m") or 0.
        for robot in snapshot["robots"]}})
    deadline = 10. <= elapsed < 13. or elapsed >= 28.
    late_goal = (late_goal_window
                 and 15_000_000_000 <= round(elapsed * 1e9) < 26_000_000_000)
    goal_window = elapsed < 1.5 or 13. <= elapsed < 15. or late_goal
    desired, reasons = [], {}
    for index, robot in enumerate(snapshot["robots"]):
        name, nav, activity = robot["name"], robot["navigation"], robot["activity"]
        speed, path = robot.get("v"), activity.get("estimated_path_m")
        moving = (robot.get("fresh") is True and robot.get("valid") is True
                  and nav.get("phase") == "active" and nav.get("owned") is True
                  and type(nav.get("goal_id")) is str and bool(nav["goal_id"])
                  and type(nav.get("accepted_goal_count")) is int
                  and nav["accepted_goal_count"] > 0
                  and type(speed) in (int, float) and math.isfinite(speed) and speed >= .08
                  and activity.get("path_observation_complete") is True
                  and type(path) in (int, float) and math.isfinite(path)
                  and path - current["baseline_path_m"][name] >= .05)
        reason = ("held_after_submitted_wait" if name in current["waits"] else
                  "bounded_deadline" if deadline else
                  "received_motion" if moving else None)
        if reason is not None and snapshot["per_robot_action_mask"][index][9]:
            desired.append((9,))
            reasons[name] = reason
            continue
        if reason is not None:
            reasons[name] = reason + "_wait_masked"
        first_wait = state["rounds"].get("initial", {}).get("waits", {}).get(name)
        recovering = (round_id == "second"
                      and (first_wait is None
                           or elapsed - first_wait["task_elapsed_sec"] < 3.
                           or nav.get("phase") != "idle"
                           or robot.get("fresh") is not True
                           or type(speed) not in (int, float) or not math.isfinite(speed)
                           or abs(speed) > .01))
        desired.append(tuple(range(9)) if goal_window and not recovering else (8,))
    legal = [valid and all(choice in desired[index] for index, choice in
             enumerate((action // 100, action // 10 % 10, action % 10)))
             and (not nonapproaching_goals or _probe_nonapproaching_goal_action(snapshot, action))
             for action, valid in enumerate(snapshot["joint_action_mask"])]
    if not any(legal):
        raise ValueError("no legal joint preparation action; never override a mask")
    filtered = dict(snapshot, joint_action_mask=legal)
    if late_goal:
        ranked = min((action for action, valid in enumerate(legal) if valid),
                     key=lambda action: _probe_goal_order(snapshot, action, True))
        diagnostics.setdefault("late_goal_decisions", []).append({
            "snapshot_sequence": snapshot.get("sequence"),
            "task_elapsed_sec": elapsed, "action": ranked,
            "late_goal_window_sec": [15., 26.],
            "late_goal_window_ns": [15_000_000_000, 26_000_000_000],
            "max_legal_goal_components": sum(choice < 8 for choice in
                                             (ranked // 100, ranked // 10 % 10, ranked % 10)),
            "original_joint_allowed_actions": sum(valid is True for valid
                                                  in snapshot["joint_action_mask"]),
            "filtered_stimulus_allowed_actions": sum(legal),
            "new_goal_filter": ("received_straight_nonapproach_v1"
                                if nonapproaching_goals else None),
            "scope": ("external late-window outward ranking on original received time; "
                      "counts refer to fixture subset, not actor interface availability; "
                      "no reverse preference or actual motion/stop credit"),
        })
    else:
        ranked = probe_action_v3(filtered, diagnostics)
    if nonapproaching_goals and goal_window and not late_goal:
        diagnostics["goal_decisions"][-1].update(
            new_goal_filter="received_straight_nonapproach_v1",
            original_joint_allowed_actions=sum(valid is True
                                               for valid in snapshot["joint_action_mask"]),
            filtered_stimulus_allowed_actions=sum(legal),
            scope=("max_legal_goal_components refers only to the external V5 stimulus subset "
                   "after lifecycle/nonapproach filtering; not actor interface availability; "
                   "actual turn/stop coverage audited separately"))
    if goal_window:
        action = ranked
    else:
        action = min(index for index, valid in enumerate(legal) if valid)
    if legal[action] is not True:
        raise ValueError("preparation action lost exact joint legality")
    request = {"epoch": snapshot["epoch"], "observation_sequence": snapshot["sequence"],
               "observation_digest": snapshot["digest"], "round": round_id,
               "task_elapsed_sec": elapsed, "action": action, "reasons": reasons,
               "wait_robots": [robot["name"] for index, robot in enumerate(snapshot["robots"])
                               if (action // (100, 10, 1)[index]) % 10 == 9],
               "received_motion_robots": [name for name, reason in reasons.items()
                                          if reason == "received_motion"],
               "scope": "planned legal input only, not submitted/cancelled/stopped credit"}
    if nonapproaching_goals:
        request["new_goal_filter"] = "received_straight_nonapproach_v1"
    state["pending_submission"] = request
    state["decisions"].append(dict(request))
    return action


def record_probe_v4_submission(diagnostics, info):
    """Called only after the actual step RPC returns; actual cancel is audited later."""
    state = diagnostics["v4_stimulus"]
    request = state.get("pending_submission")
    if request is None:
        raise ValueError("no planned preparation action")
    if "action_submitted" in info and type(info["action_submitted"]) is not bool:
        raise ValueError("explicit action_submitted must be bool")
    if info.get("action_submitted", True) is False:
        state.setdefault("not_submitted", []).append(dict(request))
        state["pending_submission"] = None
        return
    command = info.get("command")
    if (not isinstance(command, dict) or type(command.get("command_id")) is not int
            or command["command_id"] <= 0
            or any(type(command.get(key)) is not str for key in
                   ("epoch", "observation_digest"))
            or any(type(command.get(key)) is not int for key in
                   ("observation_sequence", "action"))
            or any(command.get(key) != request[key] for key in
                   ("epoch", "observation_sequence", "observation_digest", "action"))):
        raise ValueError("returned step does not bind the actual planned submission")
    current = state["rounds"][request["round"]]
    for name in request["wait_robots"]:
        current["waits"].setdefault(name, {
            "task_elapsed_sec": request["task_elapsed_sec"],
            "command_id": command.get("command_id"), "reason": request["reasons"].get(name),
            "scope": "actual step command submitted; native cancel/stop credit audited separately"})
    state["pending_submission"] = None


def _probe_nonapproaching_goal_action(snapshot, action):
    """External straight-direction filter only; never a trajectory/safety proof."""
    choices = (action // 100, action // 10 % 10, action % 10)
    if all(choice >= 8 for choice in choices):
        return True

    def finite(value):
        try:
            return type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            return False

    for robot in snapshot["robots"]:
        if (robot.get("fresh") is not True or robot.get("valid") is not True
                or any(not finite(robot.get(key)) for key in ("x", "y"))):
            return False
    for index, choice in enumerate(choices):
        if choice >= 8:
            continue
        own, goal = snapshot["robots"][index], snapshot["candidates"][choice]
        if any(not finite(goal.get(key)) for key in ("x", "y")):
            return False
        gx, gy = goal["x"] - own["x"], goal["y"] - own["y"]
        if not all(finite(value) for value in (gx, gy)):
            return False
        goal_distance = math.hypot(gx, gy)
        if not finite(goal_distance) or goal_distance <= 0.:
            return False
        for peer_index, peer in enumerate(snapshot["robots"]):
            if peer_index == index:
                continue
            px, py = peer["x"] - own["x"], peer["y"] - own["y"]
            if not all(finite(value) for value in (px, py)):
                return False
            peer_distance = math.hypot(px, py)
            denominator = goal_distance * peer_distance
            dot = gx * px + gy * py
            if (not all(finite(value) for value in (peer_distance, denominator, dot))
                    or denominator <= 0.):
                return False
            margin = -dot / denominator
            if not finite(margin) or margin < 0.:
                return False
    return True


def probe_action_v5(snapshot, diagnostics):
    """V4 lifecycle plus received non-approach new-GOAL screening."""
    return probe_action_v4(snapshot, diagnostics, nonapproaching_goals=True)


def probe_action_v6(snapshot, diagnostics):
    """V5 lifecycle with a bounded received-only late new-GOAL opportunity."""
    return probe_action_v4(snapshot, diagnostics, nonapproaching_goals=True,
                           late_goal_window=True)


def _new_preparation_abort():
    return {"event": threading.Event(), "lock": threading.Lock(), "first_failure": None}


def _abort_requested(abort):
    return abort is not None and abort["event"].is_set()


def _preparation_failure(abort, worker_id, kind, reason, episode_index=None, epoch=None):
    """Publish only the first observed failure; no RPC, signal or sample change."""
    if abort is None:
        return
    with abort["lock"]:
        if not abort["event"].is_set():
            abort["first_failure"] = {
                "worker_id": worker_id, "kind": kind, "reason": str(reason),
                "episode_index": episode_index, "epoch": epoch,
                "observed_wall_monotonic_ns": time.monotonic_ns(),
            }
            abort["event"].set()


def _wall_admission(args, abort, worker_id, operation, *, episode_index=None, epoch=None):
    """Reserve the existing RPC upper bound and close time before submitting work."""
    deadline = getattr(args, "allocation_deadline_monotonic_ns", None)
    if deadline is not None and not _abort_requested(abort):
        required = {"reset": 420., "step": 90., "after_rpc": 0.}[operation]
        remaining = (deadline - time.monotonic_ns()) / 1e9
        if remaining < required + args.close_reserve_seconds:
            _preparation_failure(
                abort, worker_id, "work_wall_allocation_exhausted",
                f"{operation}: remaining={remaining:.9f}s requires "
                f"{required + args.close_reserve_seconds:.9f}s including close reserve",
                episode_index, epoch)
    return not _abort_requested(abort)


def _parameter_review_binding(freeze, profile="original", safety_contract="legacy"):
    """The only review executable must equal its tracked source at this freeze."""
    if profile not in ("original", "gentle_turn_v1"):
        raise ValueError("unknown exact parameter readback profile")
    validate_preparation_profile(safety_contract)
    if safety_contract == "mr3-reach-v1" and profile != "gentle_turn_v1":
        raise ValueError("reach readback requires unchanged gentle_turn_v1 deployment facts")

    def bind(relative):
        raw = (WORKSPACE / relative).read_bytes()
        frozen = subprocess.check_output(
            ["git", "show", f"{freeze}:{relative.as_posix()}"], cwd=WORKSPACE)
        if raw != frozen:
            raise RuntimeError("parameter review script differs from the declared source freeze")
        return {"relative_path": relative.as_posix(), "freeze": freeze,
                "sha256": hashlib.sha256(raw).hexdigest()}

    binding = bind(REACH_PARAMETER_REVIEW_SCRIPT if safety_contract == "mr3-reach-v1" else
                   PARAMETER_REVIEW_SCRIPT if profile == "original"
                   else GENTLE_PARAMETER_REVIEW_SCRIPT)
    if profile == "gentle_turn_v1":
        from .audit_nav2_parameters import load_profile
        _, proof = load_profile(WORKSPACE)
        binding.update(profile_selection=profile,
                       profile_definition_sha256=proof["profile_sha256"],
                       immutable_reader=bind(PARAMETER_REVIEW_SCRIPT),
                       deployment_yaml_sources=[bind(Path(row["path"]))
                                                for row in proof["yaml_sources"]])
    if safety_contract == "mr3-reach-v1":
        from .audit_reach_nav2_parameters import WIRE_RELATIVE
        binding.update(safety_contract=safety_contract,
                       deployment_entry=bind(GENTLE_PARAMETER_REVIEW_SCRIPT),
                       shared_wire_source=bind(WIRE_RELATIVE))
    return binding


def _parameter_review_environment(args, worker_id, episode):
    """Match native discovery using only the seven frozen transport settings."""
    metadata_raw = (Path(episode["output_directory"]) / "metadata.json").read_bytes()
    metadata = json.loads(metadata_raw)
    if metadata["freeze"] != args.freeze or metadata["epoch"] != episode["epoch"]:
        raise RuntimeError("parameter review native metadata freeze/epoch mismatch")
    native = metadata["transport_environment"]
    profile = WORKSPACE / PARAMETER_REVIEW_PROFILE
    if profile.resolve() != profile:
        raise RuntimeError("parameter review profile must use the canonical unsymlinked path")
    raw = profile.read_bytes()
    profile_sha = hashlib.sha256(raw).hexdigest()
    expected = {
        "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp", "ROS_LOCALHOST_ONLY": "0",
        "FASTRTPS_DEFAULT_PROFILES_FILE": str(profile), "SKIP_DEFAULT_XML": "1",
        "FASTDDS_DEFAULT_PROFILES_FILE": None, "RMW_FASTRTPS_USE_QOS_FROM_XML": None,
        "RMW_FASTRTPS_PUBLICATION_MODE": None,
    }
    if (any(key not in native or native[key] != value for key, value in expected.items())
            or native.get("profile_sha256") != profile_sha):
        raise RuntimeError("parameter review native transport/profile declaration mismatch")
    frozen = subprocess.check_output(
        ["git", "show", f"{args.freeze}:{PARAMETER_REVIEW_PROFILE.as_posix()}"], cwd=WORKSPACE)
    if raw != frozen:
        raise RuntimeError("parameter review profile differs from the declared source freeze")
    environment = dict(ros_environment(args.base_domain + worker_id, args.base_port + worker_id))
    for key in TRANSPORT_ENV_KEYS:
        if native[key] is None:
            environment.pop(key, None)
        else:
            environment[key] = native[key]
    return environment, {
        "native_transport_environment": {
            **{key: native[key] for key in TRANSPORT_ENV_KEYS}, "profile_sha256": profile_sha},
        "selected_transport_environment": {
            key: environment.get(key) for key in TRANSPORT_ENV_KEYS},
        "metadata_sha256": hashlib.sha256(metadata_raw).hexdigest(),
        "profile_source": {"relative_path": PARAMETER_REVIEW_PROFILE.as_posix(),
                           "freeze": args.freeze, "sha256": profile_sha},
    }


def _run_parameter_review(args, worker_id, episode):
    selection = getattr(args, "preparation_parameter_profile", "original")
    contract = getattr(args, "safety_contract", "legacy")
    binding = (_parameter_review_binding(args.freeze, selection, contract)
               if contract != "legacy" else _parameter_review_binding(args.freeze, selection))
    if binding != args.preparation_parameter_review_source:
        raise RuntimeError("parameter review script binding changed after preflight")
    directory = Path(episode["output_directory"])
    command = [
        "bash", "-c",
        'source /opt/ros/humble/setup.bash && '
        'source "$1" && shift && exec /usr/bin/python3 "$@"',
        "mr3_parameter_review",
        str(WORKSPACE / "ros2_ws/ros2-multi-robot-automap/install/setup.bash"),
        str(WORKSPACE / (REACH_PARAMETER_REVIEW_SCRIPT if contract == "mr3-reach-v1" else
            GENTLE_PARAMETER_REVIEW_SCRIPT if getattr(
            args, "preparation_parameter_profile", "original") == "gentle_turn_v1"
            else PARAMETER_REVIEW_SCRIPT)), str(directory),
        "--freeze", args.freeze, "--output", str(directory / "actual_nav2_parameters.json"),
        "--wall-timeout-sec", "30"]
    trace = {"source": binding, "command_argv": command, "wall_timeout_sec": 45,
             "scope": "after returned reset, paused before first step; readonly GetParameters"}
    episode["preparation_parameter_review"] = trace
    environment, transport = _parameter_review_environment(args, worker_id, episode)
    trace["transport"] = transport
    try:
        response = subprocess.run(
            command, env=environment, text=True, capture_output=True, timeout=45)
    except subprocess.TimeoutExpired as error:
        trace.update(timed_out=True,
                     stdout=(error.stdout.decode(errors="replace")
                             if isinstance(error.stdout, bytes) else error.stdout),
                     stderr=(error.stderr.decode(errors="replace")
                             if isinstance(error.stderr, bytes) else error.stderr))
        raise
    trace.update(returncode=response.returncode, stdout=response.stdout, stderr=response.stderr)
    if response.returncode:
        raise RuntimeError(f"parameter review failed with returncode {response.returncode}")


def resource_sample():
    """Host counters and driver-reported GPU data, not an attribution claim."""
    stat = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
    ticks = [int(value) for value in stat]
    mem = {line.split(":", 1)[0]: int(line.split()[1]) for line in
           Path("/proc/meminfo").read_text().splitlines() if len(line.split()) >= 2}
    result = {"monotonic": time.monotonic(), "cpu_total_ticks": sum(ticks),
              "cpu_idle_ticks": ticks[3] + ticks[4], "load_average": list(os.getloadavg()),
              "mem_total_kib": mem["MemTotal"], "mem_available_kib": mem["MemAvailable"]}
    try:
        response = subprocess.run([
            "nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits"], text=True, capture_output=True, timeout=5.)
        result["gpu"] = ([[int(value.strip()) for value in row.split(",")]
                          for row in response.stdout.splitlines()]
                         if response.returncode == 0 else [])
        result["gpu_query_returncode"] = response.returncode
    except (OSError, subprocess.TimeoutExpired) as error:
        result["gpu_query_error"] = repr(error)
    return result


def run_worker(args, worker_id, preparation_abort=None):
    safety_contract = _collection_safety_contract(args)
    preparation = args.preparation_motion_probe
    uniform_seed = getattr(args, "diagnostic_uniform_seed", None)
    diagnostic = uniform_seed is not None
    generator = random.Random(uniform_seed + 1000003 * worker_id) if diagnostic else None
    budgeted = getattr(args, "allocation_deadline_monotonic_ns", None) is not None
    abort = ((preparation_abort or _new_preparation_abort())
             if preparation or budgeted or diagnostic else None)
    try:
        supervisor = Supervisor(run_id=args.run_id, worker_id=worker_id,
                                domain_id=args.base_domain + worker_id,
                                gazebo_port=args.base_port + worker_id,
                                output_root=args.output_root, terminal_probe=args.terminal_probe,
                                safety_contract=safety_contract,
                                **({"seed_rule": args.seed_rule}
                                   if getattr(args, "seed_rule", "legacy") != "legacy" else {}),
                                **({"start_graph_rule": args.start_graph_rule}
                                   if getattr(args, "start_graph_rule", "original-seed-cell") != "original-seed-cell" else {}),
                                **({"preparation_probe_version": getattr(args, "preparation_probe_version", None)}
                                   if getattr(args, "preparation_probe_version", None) is not None else {}))
        environment = MR3Env(supervisor=supervisor, max_steps=args.steps)
    except Exception as error:
        _preparation_failure(abort, worker_id, "construction_exception", repr(error))
        raise
    result = {"worker_id": worker_id, "episodes": [], "error": None}
    if diagnostic:
        result["diagnostic_uniform_worker_seed"] = uniform_seed + 1000003 * worker_id
    if preparation:
        result["reset_attempts"] = []
    started = time.monotonic()
    episode, episode_index, episode_started = None, None, None
    try:
        for episode_index, (scene, seed) in enumerate(args.schedule):
            if not _wall_admission(args, abort, worker_id, "reset", episode_index=episode_index):
                break
            episode = None
            episode_started = time.monotonic()
            if preparation:
                attempt = {"episode_index": episode_index, "scene": scene,
                           "seed": seed, "reset_returned": False}
                result["reset_attempts"].append(attempt)
            observation, info = environment.reset(seed=seed, options={"scene": scene})
            if preparation:
                attempt["reset_returned"] = True
            initial = supervisor.last_result["snapshot"]
            episode = {"epoch": info["epoch"], "scene": scene, "seed": seed,
                       "initial_observation_digest": info["observation_digest"],
                       "output_directory": str(supervisor.episode.directory),
                       "startup_wall_sec": info["startup_wall_sec"],
                       "initial_estimated_poses": [
                           {key: robot.get(key) for key in ("name", "x", "y", "yaw")}
                           for robot in initial["robots"]], "transitions": 0,
                       "transition_wall_sec": 0., "reward_sum": 0., "dt_values": []}
            if (preparation and getattr(args, "preparation_probe_version", None)
                    in (PREPARATION_PROBE_V3, PREPARATION_PROBE_V4, PREPARATION_PROBE_V5, PREPARATION_PROBE_V6, PREPARATION_PROBE_REACH_V1)):
                episode["preparation_probe_diagnostics"] = {
                    "reference_turn_samples": {}, "goal_decisions": []}
            result["episodes"].append(episode)
            if diagnostic:
                episode["diagnostic_uniform_actions"] = []
            if not _wall_admission(args, abort, worker_id, "after_rpc",
                                   episode_index=episode_index, epoch=episode["epoch"]):
                episode["intentional_abort_prefix"] = {
                    "after_rpc": "reset", "first_failure": abort["first_failure"]}
                break
            if getattr(args, "preparation_parameter_review", False):
                _run_parameter_review(args, worker_id, episode)
            for step_index in range(args.steps):
                if not _wall_admission(args, abort, worker_id, "step",
                                       episode_index=episode_index, epoch=episode["epoch"]):
                    episode["intentional_abort_prefix"] = {
                        "after_rpc": "reset" if step_index == 0 else "step",
                        "first_failure": abort["first_failure"]}
                    break
                if args.terminal_probe and step_index == 3:
                    if episode_index == 0:
                        episode["diagnostic_failure_arm"] = supervisor.arm_failure_probe()
                    else:
                        episode["diagnostic_failure_terminal"] = supervisor.trigger_failure_probe()
                    if not _wall_admission(args, abort, worker_id, "step",
                                           episode_index=episode_index, epoch=episode["epoch"]):
                        episode["intentional_abort_prefix"] = {
                            "after_rpc": "terminal_probe", "first_failure": abort["first_failure"]}
                        break
                if args.fault_probe and worker_id == 0 and episode_index == 0 and step_index == 4:
                    identity = supervisor.episode.identity
                    if not identity_alive(identity):
                        raise RuntimeError("fault target no longer matches the owned worker")
                    os.kill(identity["pid"], signal.SIGKILL)
                    try:
                        environment.step(888)
                    except InfrastructureError as error:
                        episode["expected_infrastructure_fault"] = repr(error)
                        result["fault_verified"] = True
                    else:
                        raise RuntimeError("killed worker was accepted as a valid transition")
                    break
                if diagnostic:
                    snapshot = supervisor.last_result["snapshot"]
                    action = diagnostic_uniform_action(snapshot, generator)
                    episode["diagnostic_uniform_actions"].append({
                        "decision": step_index, "action": action,
                        "observation_sequence": snapshot.get("sequence"),
                        "observation_digest": snapshot.get("digest"),
                        "legal_joint_actions": sum(snapshot["joint_action_mask"]),
                        "step_returned": False,
                    })
                elif "preparation_probe_diagnostics" in episode:
                    probe = (probe_action_v6 if args.preparation_probe_version
                             in (PREPARATION_PROBE_V6, PREPARATION_PROBE_REACH_V1) else probe_action_v5
                             if args.preparation_probe_version
                             == PREPARATION_PROBE_V5 else probe_action_v4
                             if args.preparation_probe_version == PREPARATION_PROBE_V4
                             else probe_action_v3)
                    action = probe(supervisor.last_result["snapshot"],
                                   episode["preparation_probe_diagnostics"])
                else:
                    action = (888 if args.deadline_probe or args.terminal_probe else
                              probe_action(supervisor.last_result["snapshot"],
                                           outward_goals=args.preparation_motion_probe))
                if not _wall_admission(args, abort, worker_id, "step",
                                       episode_index=episode_index, epoch=episode["epoch"]):
                    episode["intentional_abort_prefix"] = {
                        "after_rpc": "reset" if step_index == 0 else "step",
                        "first_failure": abort["first_failure"]}
                    break
                step_started = time.monotonic()
                observation, reward, terminated, truncated, info = environment.step(action)
                if diagnostic:
                    episode["diagnostic_uniform_actions"][-1].update(
                        step_returned=True, action_submitted=info.get("action_submitted", True))
                episode["transition_wall_sec"] += time.monotonic() - step_started
                episode["transitions"] += 1
                episode["reward_sum"] += reward
                episode["dt_values"].append(info["dt"])
                if getattr(args, "preparation_probe_version", None) in (
                        PREPARATION_PROBE_V4, PREPARATION_PROBE_V5, PREPARATION_PROBE_V6, PREPARATION_PROBE_REACH_V1):
                    record_probe_v4_submission(episode["preparation_probe_diagnostics"], info)
                if terminated or truncated:
                    episode.update(terminated=terminated, truncated=truncated,
                                   reason=info.get("reason"))
                    if args.terminal_probe:
                        episode["terminal_sample"] = {
                            "dt": info["dt"], "physical_dt": info["physical_dt"],
                            "terminal_observation_reused": info.get(
                                "terminal_observation_reused", False),
                            "action_submitted": info.get("action_submitted", True),
                        }
                if preparation:
                    if terminated:
                        _preparation_failure(
                            abort, worker_id, "unexpected_termination", info.get("reason"),
                            episode_index, episode["epoch"])
                    elif truncated and step_index + 1 < args.steps:
                        _preparation_failure(
                            abort, worker_id, "early_truncation", info.get("reason"),
                            episode_index, episode["epoch"])
                if diagnostic:
                    if terminated and info.get("reason") != "coverage_reached":
                        _preparation_failure(
                            abort, worker_id, "task_failure", info.get("reason"),
                            episode_index, episode["epoch"])
                    elif truncated and (info.get("reason") != "external_sampler_limit"
                                        or step_index + 1 != args.steps):
                        _preparation_failure(
                            abort, worker_id, "unexpected_truncation", info.get("reason"),
                            episode_index, episode["epoch"])
                _wall_admission(args, abort, worker_id, "after_rpc",
                                episode_index=episode_index, epoch=episode["epoch"])
                if preparation or budgeted or diagnostic:
                    if _abort_requested(abort):
                        if not (terminated or truncated):
                            episode["intentional_abort_prefix"] = {
                                "after_rpc": "step", "first_failure": abort["first_failure"]}
                        break
                if terminated or truncated:
                    break
            if _abort_requested(abort):
                break
            if not environment._episode_done:
                raise RuntimeError("sampler step limit did not produce explicit truncation")
            episode["wall_sec_including_startup_and_closure"] = time.monotonic() - episode_started
    except Exception as error:
        result["error"] = repr(error)
        _preparation_failure(
            abort, worker_id, "rpc_or_worker_exception", repr(error), episode_index,
            None if episode is None else episode["epoch"])
    finally:
        try:
            environment.close()
        except Exception as error:
            result["cleanup_error"] = repr(error)
            _preparation_failure(
                abort, worker_id, "cleanup_exception", repr(error), episode_index,
                None if episode is None else episode["epoch"])
        if preparation or budgeted or diagnostic:
            if episode is not None:
                episode["wall_sec_including_startup_and_closure"] = (
                    time.monotonic() - episode_started)
            result["diagnostic_abort" if diagnostic else
                   "preparation_abort" if preparation else "work_wall_abort"] = {
                "requested": _abort_requested(abort), "first_failure": abort["first_failure"],
                "scope": "cooperative stop after real RPC return; no synthetic transition"}
        result["wall_sec"] = time.monotonic() - started
        result["shutdown_receipts"] = supervisor.receipts
        (supervisor.directory / "worker_summary.json").write_text(
            json.dumps(result, indent=2) + "\n")
    return result


def main(argv=None):
    main_started_ns = time.monotonic_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, choices=(1, 2, 4), required=True)
    parser.add_argument("--schedule", default="open:101,open:101")
    parser.add_argument("--steps", type=int, default=16)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--safety-contract", choices=SAFETY_CONTRACTS, default="legacy",
                        help="mr3-reach-v1 collects engineering evidence only; new qualification required")
    parser.add_argument("--seed-rule", choices=SEED_RULES, default="legacy",
                        help="explicit candidate seed certificate; native qualification is version-specific")
    parser.add_argument("--start-graph-rule", choices=START_GRAPH_RULES, default="original-seed-cell")
    parser.add_argument("--diagnostic-uniform-seed", type=int,
                        help="nonnegative seed for uniform legal engineering inputs; never PPO or training")
    parser.add_argument("--base-domain", type=int, default=120)
    parser.add_argument("--base-port", type=int, default=12001)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--work-wall-seconds", type=float,
                        help="total native wall allocation from main entry, including close")
    parser.add_argument("--close-reserve-seconds", type=float, default=120.,
                        help="wall time reserved for normal close; default 120 seconds")
    parser.add_argument("--fault-probe", action="store_true")
    parser.add_argument("--deadline-probe", action="store_true")
    parser.add_argument("--terminal-probe", action="store_true")
    parser.add_argument("--preparation-motion-probe", action="store_true",
                        help="external engineering inputs: prefer outward legal goals; no policy")
    parser.add_argument("--preparation-probe-version",
                        choices=(PREPARATION_PROBE_V2, PREPARATION_PROBE_V3,
                                 PREPARATION_PROBE_V4, PREPARATION_PROBE_V5, PREPARATION_PROBE_V6, PREPARATION_PROBE_REACH_V1),
                        help="explicit external fixture version; v2=20 steps, v3=32 steps")
    parser.add_argument("--preparation-parameter-review", action="store_true",
                        help="paused one-worker open101: frozen readonly ROS parameter audit")
    parser.add_argument("--preparation-parameter-profile", choices=("original", "gentle_turn_v1"),
                        default="original", help="exact readback profile; never sets ROS parameters")
    command_line = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(command_line)
    if args.diagnostic_uniform_seed is not None and any(
            flag.split("=", 1)[0].startswith("--preparation-") for flag in command_line):
        parser.error("diagnostic uniform actions cannot be combined with preparation parameters")
    try:
        _collection_safety_contract(args)
    except ValueError as error:
        parser.error(str(error))
    if (not math.isfinite(args.close_reserve_seconds) or args.close_reserve_seconds <= 0
            or (args.work_wall_seconds is not None and (
                not math.isfinite(args.work_wall_seconds)
                or args.work_wall_seconds <= args.close_reserve_seconds))):
        parser.error("wall allocation must be finite and greater than the positive close reserve")
    args.allocation_deadline_monotonic_ns = (
        None if args.work_wall_seconds is None else
        main_started_ns + round(args.work_wall_seconds * 1e9))
    if not 1 <= args.steps <= 300:
        parser.error("steps must be in [1,300]")
    try:
        args.schedule = [(part.split(":")[0], int(part.split(":")[1]))
                         for part in args.schedule.split(",")]
        if any(scene not in ("open", "rooms", "corridors") or seed < 0
               for scene, seed in args.schedule):
            raise ValueError()
    except (ValueError, IndexError):
        parser.error("schedule must be a comma-separated list of declared scene:seed pairs")
    if args.fault_probe and (args.workers != 2 or len(args.schedule) != 2 or args.steps < 8):
        parser.error("fault probe requires two workers, two episodes, at least eight steps")
    if args.deadline_probe and (
            args.workers != 1 or len(args.schedule) != 1 or args.steps != 300
            or args.fault_probe or args.terminal_probe):
        parser.error("deadline probe requires one worker, one 300-step episode, no injected crash")
    if args.terminal_probe and (
            args.workers != 1 or args.schedule != [("open", 101)] * 2
            or args.steps != 4 or args.fault_probe or args.deadline_probe):
        parser.error("terminal probe requires one worker, two open101 episodes and four API steps")
    if args.preparation_motion_probe and any((
            args.terminal_probe, args.deadline_probe, args.fault_probe)):
        parser.error("preparation motion probe cannot be combined with other probes")
    if args.preparation_probe_version and not args.preparation_motion_probe:
        parser.error("preparation probe version requires preparation motion probe")
    if args.preparation_motion_probe:
        args.preparation_probe_version = args.preparation_probe_version or PREPARATION_PROBE_V2
        expected_steps = (32 if args.preparation_probe_version in
                          (PREPARATION_PROBE_V3, PREPARATION_PROBE_V4, PREPARATION_PROBE_V5, PREPARATION_PROBE_V6, PREPARATION_PROBE_REACH_V1) else 20)
        if args.steps != expected_steps:
            parser.error("preparation motion probe requires the explicit "
                         f"{expected_steps}-step fixture")
    if args.preparation_parameter_review and (
            not args.preparation_motion_probe or args.workers != 1
            or args.schedule != [("open", 101)]):
        parser.error("parameter review requires preparation motion probe, one worker, one open101")
    if args.preparation_parameter_profile != "original" and not args.preparation_parameter_review:
        parser.error("nonoriginal parameter profile requires the explicit parameter review")
    args.freeze = None
    args.preparation_parameter_review_source = None
    if args.preparation_parameter_review:
        args.freeze = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip()
        try:
            args.preparation_parameter_review_source = (
                _parameter_review_binding(args.freeze, args.preparation_parameter_profile, args.safety_contract)
                if args.safety_contract != "legacy" else
                _parameter_review_binding(args.freeze, args.preparation_parameter_profile))
        except (OSError, subprocess.CalledProcessError, RuntimeError, ValueError) as error:
            parser.error(f"frozen parameter review source unavailable: {error}")
    output_root = args.output_root or (
        WORKSPACE / "ros2_ws/ros2-multi-robot-automap/log/mr3_learning")
    directory = output_root / args.run_id
    if directory.exists():
        parser.error("run directory already exists; evidence cannot be overwritten")
    directory.mkdir(parents=True)
    resources = []
    stop = threading.Event()

    def sample_resources():
        while not stop.is_set():
            resources.append(resource_sample())
            stop.wait(1.)

    sampler = threading.Thread(target=sample_resources, name="mr3_resources", daemon=True)
    started = (time.monotonic() if args.work_wall_seconds is None else main_started_ns / 1e9)
    metadata = {"kind": "scripted_p1c_sampling_not_rl", "workers": args.workers,
                "safety_contract": args.safety_contract,
                "robots_per_worker": 3, "schedule": args.schedule, "steps_per_episode": args.steps,
                "command": (sys.argv if argv is None else
                            [sys.executable, "-m", "mr3_learning.benchmark", *argv]), "python": sys.executable,
                "freeze": args.freeze or subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip(),
                "base_domain": args.base_domain, "base_port": args.base_port,
                "fault_probe": args.fault_probe,
                "deadline_probe": args.deadline_probe,
                "terminal_probe": args.terminal_probe,
                "preparation_motion_probe": args.preparation_motion_probe,
                "preparation_probe_version": args.preparation_probe_version,
                "preparation_parameter_review": args.preparation_parameter_review,
                "preparation_parameter_profile": args.preparation_parameter_profile,
                "preparation_parameter_review_source": args.preparation_parameter_review_source,
                "resource_scope": "host counters include unrelated activity; GPU driver reports",
                "num_logical_cpus": os.cpu_count(),
                "cpu_affinity_count": len(os.sched_getaffinity(0))}
    if args.seed_rule != "legacy":
        metadata["seed_rule"] = args.seed_rule
    if args.start_graph_rule != "original-seed-cell":
        metadata["start_graph_rule"] = args.start_graph_rule
    if args.safety_contract == "mr3-reach-v1":
        metadata.update(training_eligible=False, scientific_readers_applied=False,
                        scientific_qualification="PENDING_NEW_FREEZE_INDEPENDENT_AUDITS",
                        qualification_scope="engineering_collection_only_no_legacy_qualification_credit")
        if args.preparation_motion_probe:
            metadata.update(preparation_fixture_implementation="unchanged_v6_external_actions",
                            preparation_fixture_schema="mr3-reach-preparation-fixture-v1")
    if args.diagnostic_uniform_seed is not None:
        metadata.update(kind="uniform_legal_engineering_diagnostic_not_rl",
                        diagnostic_uniform_seed=args.diagnostic_uniform_seed,
                        diagnostic_uniform_worker_seed_rule="seed + 1000003 * worker_id",
                        diagnostic_action_source="random.Random.choice on the actual legal joint mask",
                        training_eligible=False, policy_calls=0, optimizer_steps=0, gpu_calls=0,
                        policy_reliability_credit=False)
    if args.work_wall_seconds is not None:
        metadata["work_wall_budget"] = {
            "total_allocation_seconds": args.work_wall_seconds,
            "close_reserve_seconds": args.close_reserve_seconds,
            "started_wall_monotonic_ns": main_started_ns,
            "allocation_deadline_monotonic_ns": args.allocation_deadline_monotonic_ns,
            "work_deadline_monotonic_ns": args.allocation_deadline_monotonic_ns
            - round(args.close_reserve_seconds * 1e9),
            "scope": "cooperative admission; complete in-flight RPC then normal close; no hard kill",
            "rpc_admission_upper_bounds_seconds": {"reset": 420., "step": 90.}}
    (directory / "benchmark_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    results = []
    preparation_abort = (_new_preparation_abort() if args.preparation_motion_probe
                         or args.work_wall_seconds is not None
                         or args.diagnostic_uniform_seed is not None else None)
    sampler.start()
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_worker, args, worker_id, preparation_abort): worker_id
                       for worker_id in range(args.workers)}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as error:
                    _preparation_failure(
                        preparation_abort, futures[future], "worker_result_exception", repr(error))
                    results.append({"worker_id": futures[future], "episodes": [],
                                    "shutdown_receipts": [], "error": repr(error)})
    finally:
        stop.set()
        sampler.join(timeout=10.)
        (directory / "resources.json").write_text(json.dumps(resources, indent=2) + "\n")
    wall = time.monotonic() - started
    transitions = sum(episode["transitions"]
                      for worker in results for episode in worker["episodes"])
    passed = len(results) == args.workers and all(
        not worker["error"] and not worker.get("cleanup_error")
        and len(worker["episodes"]) == len(args.schedule)
        and all((args.fault_probe and worker["worker_id"] == 0 and index == 0
                 and episode.get("expected_infrastructure_fault") and episode["transitions"] == 4)
                or (args.diagnostic_uniform_seed is not None
                    and 0 < episode["transitions"] <= args.steps
                    and episode.get("terminated") and not episode.get("truncated")
                    and episode.get("reason") == "coverage_reached")
                or (episode["transitions"] == args.steps
                    and ((args.deadline_probe and episode.get("terminated")
                          and not episode.get("truncated") and episode.get("reason") == "timeout")
                         or (args.terminal_probe and episode.get("terminated")
                             and not episode.get("truncated")
                             and episode.get("reason") == "navigation_failure"
                             and [round(dt * 1e9) for dt in episode["dt_values"]]
                             == [10**9] * 3 + [20000000 if index == 0 else 0]
                             and episode["terminal_sample"]["terminal_observation_reused"]
                             == (index == 1)
                             and episode["terminal_sample"]["action_submitted"] == (index == 0))
                         or (not args.deadline_probe and not args.terminal_probe
                             and episode.get("truncated")
                             and not episode.get("terminated"))))
                for index, episode in enumerate(worker["episodes"]))
        and all(not receipt["remaining_owned_processes"]
                and not receipt["remaining_owned_zombies"]
                and ((args.fault_probe and worker["worker_id"] == 0 and index == 0
                      and receipt["failed_sample"] and receipt["worker_returncode"] == -9)
                     or (not receipt["forced_shutdown"] and receipt["worker_returncode"] == 0))
                for index, receipt in enumerate(worker["shutdown_receipts"]))
        and (not args.fault_probe or worker["worker_id"] != 0 or worker.get("fault_verified"))
        for worker in results)
    if preparation_abort is not None:
        passed = passed and not _abort_requested(preparation_abort)
    wall_limit_exceeded = args.work_wall_seconds is not None and wall > args.work_wall_seconds
    if wall_limit_exceeded:
        _preparation_failure(preparation_abort, None, "wall_allocation_exceeded",
                             f"actual wall including close={wall:.9f}s exceeds allocation")
    if args.work_wall_seconds is not None or args.diagnostic_uniform_seed is not None:
        passed = passed and all(len(worker["shutdown_receipts"]) == len(worker["episodes"])
                                for worker in results)
    passed = passed and not wall_limit_exceeded
    summary = {**metadata, "passed": passed, "wall_sec_including_all_attempts": wall,
               "valid_transitions": transitions,
               "effective_transition_per_wall_sec": transitions / wall,
               "workers_results": sorted(results, key=lambda value: value["worker_id"])}
    if preparation_abort is not None:
        summary["diagnostic_abort" if args.diagnostic_uniform_seed is not None else
                "preparation_abort" if args.preparation_motion_probe else "work_wall_abort"] = {
            "requested": _abort_requested(preparation_abort),
            "first_failure": preparation_abort["first_failure"],
            "scope": "first observed failing RPC/worker; other in-flight RPCs finish then close"}
    if args.work_wall_seconds is not None:
        summary.update(outcome="PASS" if passed else "FAIL" if wall_limit_exceeded else "INCOMPLETE",
                       wall_limit_exceeded=wall_limit_exceeded)
    (directory / "benchmark_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: value for key, value in summary.items()
                      if key != "workers_results"}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
