"""Predeclared scripted sampler/reset measurements; never policy training."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from .env import MR3Env
from .supervisor import InfrastructureError, Supervisor, WORKSPACE, identity_alive, ros_environment


PARAMETER_REVIEW_SCRIPT = Path(
    "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/"
    "20261017_mr3_p2a0_v4/independent/mr3_actual_nav2_parameters_v4.py")
PARAMETER_REVIEW_PROFILE = Path(
    "ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/mr3_fastdds_loopback_udp.xml")
TRANSPORT_ENV_KEYS = (
    "RMW_IMPLEMENTATION", "ROS_LOCALHOST_ONLY", "FASTRTPS_DEFAULT_PROFILES_FILE",
    "SKIP_DEFAULT_XML", "FASTDDS_DEFAULT_PROFILES_FILE", "RMW_FASTRTPS_USE_QOS_FROM_XML",
    "RMW_FASTRTPS_PUBLICATION_MODE")
PREPARATION_PROBE_V2 = "mr3-p2a0-outward-cancel-v2"
PREPARATION_PROBE_V3 = "mr3-p2a0-outward-cancel-v3"


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


def _parameter_review_binding(freeze):
    """The only review executable must equal its tracked source at this freeze."""
    raw = (WORKSPACE / PARAMETER_REVIEW_SCRIPT).read_bytes()
    frozen = subprocess.check_output(
        ["git", "show", f"{freeze}:{PARAMETER_REVIEW_SCRIPT.as_posix()}"], cwd=WORKSPACE)
    if raw != frozen:
        raise RuntimeError("parameter review script differs from the declared source freeze")
    return {"relative_path": PARAMETER_REVIEW_SCRIPT.as_posix(), "freeze": freeze,
            "sha256": hashlib.sha256(raw).hexdigest()}


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
    binding = _parameter_review_binding(args.freeze)
    if binding != args.preparation_parameter_review_source:
        raise RuntimeError("parameter review script binding changed after preflight")
    directory = Path(episode["output_directory"])
    command = [
        "bash", "-c",
        'source /opt/ros/humble/setup.bash && '
        'source "$1" && shift && exec /usr/bin/python3 "$@"',
        "mr3_parameter_review",
        str(WORKSPACE / "ros2_ws/ros2-multi-robot-automap/install/setup.bash"),
        str(WORKSPACE / PARAMETER_REVIEW_SCRIPT), str(directory),
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
    preparation = args.preparation_motion_probe
    abort = (preparation_abort or _new_preparation_abort()) if preparation else None
    try:
        supervisor = Supervisor(run_id=args.run_id, worker_id=worker_id,
                                domain_id=args.base_domain + worker_id,
                                gazebo_port=args.base_port + worker_id,
                                output_root=args.output_root, terminal_probe=args.terminal_probe)
        environment = MR3Env(supervisor=supervisor, max_steps=args.steps)
    except Exception as error:
        _preparation_failure(abort, worker_id, "construction_exception", repr(error))
        raise
    result = {"worker_id": worker_id, "episodes": [], "error": None}
    if preparation:
        result["reset_attempts"] = []
    started = time.monotonic()
    episode, episode_index, episode_started = None, None, None
    try:
        for episode_index, (scene, seed) in enumerate(args.schedule):
            if _abort_requested(abort):
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
                    == PREPARATION_PROBE_V3):
                episode["preparation_probe_diagnostics"] = {
                    "reference_turn_samples": {}, "goal_decisions": []}
            result["episodes"].append(episode)
            if _abort_requested(abort):
                episode["intentional_abort_prefix"] = {
                    "after_rpc": "reset", "first_failure": abort["first_failure"]}
                break
            if getattr(args, "preparation_parameter_review", False):
                _run_parameter_review(args, worker_id, episode)
            for step_index in range(args.steps):
                if _abort_requested(abort):
                    episode["intentional_abort_prefix"] = {
                        "after_rpc": "reset" if step_index == 0 else "step",
                        "first_failure": abort["first_failure"]}
                    break
                if args.terminal_probe and step_index == 3:
                    if episode_index == 0:
                        episode["diagnostic_failure_arm"] = supervisor.arm_failure_probe()
                    else:
                        episode["diagnostic_failure_terminal"] = supervisor.trigger_failure_probe()
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
                if "preparation_probe_diagnostics" in episode:
                    action = probe_action_v3(supervisor.last_result["snapshot"],
                                             episode["preparation_probe_diagnostics"])
                else:
                    action = (888 if args.deadline_probe or args.terminal_probe else
                              probe_action(supervisor.last_result["snapshot"],
                                           outward_goals=args.preparation_motion_probe))
                step_started = time.monotonic()
                observation, reward, terminated, truncated, info = environment.step(action)
                episode["transition_wall_sec"] += time.monotonic() - step_started
                episode["transitions"] += 1
                episode["reward_sum"] += reward
                episode["dt_values"].append(info["dt"])
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
        if preparation:
            if episode is not None:
                episode["wall_sec_including_startup_and_closure"] = (
                    time.monotonic() - episode_started)
            result["preparation_abort"] = {
                "requested": _abort_requested(abort), "first_failure": abort["first_failure"],
                "scope": "cooperative stop after real RPC return; no synthetic transition"}
        result["wall_sec"] = time.monotonic() - started
        result["shutdown_receipts"] = supervisor.receipts
        (supervisor.directory / "worker_summary.json").write_text(
            json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, choices=(1, 2, 4), required=True)
    parser.add_argument("--schedule", default="open:101,open:101")
    parser.add_argument("--steps", type=int, default=16)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--base-domain", type=int, default=120)
    parser.add_argument("--base-port", type=int, default=12001)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--fault-probe", action="store_true")
    parser.add_argument("--deadline-probe", action="store_true")
    parser.add_argument("--terminal-probe", action="store_true")
    parser.add_argument("--preparation-motion-probe", action="store_true",
                        help="external engineering inputs: prefer outward legal goals; no policy")
    parser.add_argument("--preparation-probe-version",
                        choices=(PREPARATION_PROBE_V2, PREPARATION_PROBE_V3),
                        help="explicit external fixture version; v2=20 steps, v3=32 steps")
    parser.add_argument("--preparation-parameter-review", action="store_true",
                        help="paused one-worker open101: frozen readonly ROS parameter audit")
    args = parser.parse_args()
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
        expected_steps = 32 if args.preparation_probe_version == PREPARATION_PROBE_V3 else 20
        if args.steps != expected_steps:
            parser.error("preparation motion probe requires the explicit "
                         f"{expected_steps}-step fixture")
    if args.preparation_parameter_review and (
            not args.preparation_motion_probe or args.workers != 1
            or args.schedule != [("open", 101)]):
        parser.error("parameter review requires preparation motion probe, one worker, one open101")
    args.freeze = None
    args.preparation_parameter_review_source = None
    if args.preparation_parameter_review:
        args.freeze = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip()
        try:
            args.preparation_parameter_review_source = _parameter_review_binding(args.freeze)
        except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
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
    started = time.monotonic()
    metadata = {"kind": "scripted_p1c_sampling_not_rl", "workers": args.workers,
                "robots_per_worker": 3, "schedule": args.schedule, "steps_per_episode": args.steps,
                "command": sys.argv, "python": sys.executable,
                "freeze": args.freeze or subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip(),
                "base_domain": args.base_domain, "base_port": args.base_port,
                "fault_probe": args.fault_probe,
                "deadline_probe": args.deadline_probe,
                "terminal_probe": args.terminal_probe,
                "preparation_motion_probe": args.preparation_motion_probe,
                "preparation_probe_version": args.preparation_probe_version,
                "preparation_parameter_review": args.preparation_parameter_review,
                "preparation_parameter_review_source": args.preparation_parameter_review_source,
                "resource_scope": "host counters include unrelated activity; GPU driver reports",
                "num_logical_cpus": os.cpu_count(),
                "cpu_affinity_count": len(os.sched_getaffinity(0))}
    (directory / "benchmark_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    results = []
    preparation_abort = _new_preparation_abort() if args.preparation_motion_probe else None
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
    summary = {**metadata, "passed": passed, "wall_sec_including_all_attempts": wall,
               "valid_transitions": transitions,
               "effective_transition_per_wall_sec": transitions / wall,
               "workers_results": sorted(results, key=lambda value: value["worker_id"])}
    if preparation_abort is not None:
        summary["preparation_abort"] = {
            "requested": _abort_requested(preparation_abort),
            "first_failure": preparation_abort["first_failure"],
            "scope": "first observed failing RPC/worker; other in-flight RPCs finish then close"}
    (directory / "benchmark_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: value for key, value in summary.items()
                      if key != "workers_results"}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
