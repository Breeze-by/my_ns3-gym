"""Original episode gates for fixed external eight-action engineering evidence."""
import argparse
import ast
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from . import audit_activity, audit_evaluator_phase, audit_motion, audit_preparation
from .audit_controlled_physics import dispatch_controlled_physics, dispatch_controlled_readiness
from .audit_ppo import load_native_gates
from .native_custody import Reader, parse, require
from .observation import TENSOR_SCHEMA
from .supervisor import WORKSPACE


WIRELESS = Path("ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl")
ROS = Path("ros2_ws/ros2-multi-robot-automap")
LAUNCH = ROS / "src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py"
MODEL = ROS / "src/multi_robot/models/turtlebot3_waffle/model.sdf"
ACTIONS = (231, 888, 888, 889, 880, 658, 888, 888)
SPAWN = {"tb1": (0., -.45, .01), "tb2": (0., .45, .01), "tb3": (.45, 0., .01)}


def _raw(read, path):
    path = Path(path)
    if not path.exists():
        path = path.with_name(path.name + ".gz")
    raw = read(path)
    return gzip.decompress(raw) if path.suffix == ".gz" else raw


def _json(read, path):
    return parse(_raw(read, path))


def _digest(snapshot):
    raw = json.dumps({key: value for key, value in snapshot.items() if key != "digest"},
                     sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _argument(argv, key):
    require(argv.count(key) == 1 and argv.index(key) + 1 < len(argv),
            "actual argv lacks unique " + key)
    return argv[argv.index(key) + 1]


def _sources(summary, freeze, read):
    names = ("action_trace.py", "benchmark.py", "env.py", "supervisor.py", "plant_probe.py")
    require(set(summary["source_bindings"]) == set(names), "trace source bindings differ")
    proof = {}
    for relative in [*(WIRELESS / "mr3_learning" / name for name in names),
                     WIRELESS / "mr3_learning/audit_action_trace.py", LAUNCH, MODEL]:
        raw = read(WORKSPACE / relative)
        digest = hashlib.sha256(raw).hexdigest()
        require(subprocess.check_output(["git", "show", freeze + ":" + str(relative)],
                                        cwd=WORKSPACE) == raw,
                "trace audit/runtime source differs from exact Git freeze: " + str(relative))
        if relative.name in names:
            require(summary["source_bindings"][relative.name] == digest,
                    "trace collected under different source: " + relative.name)
        proof[str(relative)] = digest
    require(summary["source_sha256"] == proof[str(WIRELESS / "mr3_learning/action_trace.py")],
            "trace entry source SHA differs")
    return proof


def _spawn(episode, epoch, read, observer, observer_library=None):
    """Actual spawn argv are configuration proof; optional getters prove physical pose."""
    source = read(WORKSPACE / LAUNCH)
    definitions = [node.value for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "all_robots"
                           for target in node.targets)]
    require(len(definitions) == 1, "normal launch spawn source is ambiguous")
    normal = ast.literal_eval(definitions[0])[:3]
    require({robot["name"]: tuple(float(robot[key]) for key in ("x_pose", "y_pose", "z_pose"))
             for robot in normal} == SPAWN, "original near-peer source spawn changed")
    starts = []
    for line in _raw(read, episode / "launch.log").decode().splitlines():
        marker = "MR3_ORDERED_SHUTDOWN "
        if marker in line:
            row = parse(line.split(marker, 1)[1])
            if row.get("event") == "process_started" and any(
                    Path(value).name == "spawn_entity.py" for value in row.get("argv", [])):
                starts.append(row)
    require(len(starts) == 3, "actual launch lacks exactly three spawn argv receipts")
    seen, proof = set(), {}
    for row in starts:
        argv = row["argv"]
        robot = _argument(argv, "-entity")
        require(row.get("epoch") == epoch and robot in SPAWN and robot not in seen,
                "actual spawn epoch/robot repeated or differs")
        seen.add(robot)
        position = [float(_argument(argv, key)) for key in ("-x", "-y", "-z")]
        require(position == list(SPAWN[robot])
                and all(float(_argument(argv, key)) == 0. for key in ("-R", "-P", "-Y"))
                and _argument(argv, "-robot_namespace") == "/" + robot,
                "actual spawn is not original near-peer pose")
        model = episode / f"drive_model_{robot}.sdf"
        require(Path(_argument(argv, "-file")).resolve(strict=True) == model,
                "actual spawn file is not the saved effective model")
        tree = ET.fromstring(read(model))
        plugin = tree.findall(".//plugin[@name='turtlebot3_diff_drive']")
        require(len(plugin) == 1 and plugin[0].get("filename") == "libmr3_gazebo_diff_drive.so"
                and plugin[0].findtext("mr3_tagged_commands") == "true"
                and plugin[0].findtext("mr3_epoch") == epoch
                and not plugin[0].findall("mr3_odometry_period_ns")
                and plugin[0].findtext("mr3_audit_path") == str(episode / f"drive_{robot}.jsonl"),
                "actual spawn SDF driver/epoch/measurement source differs")
        # Compare every remaining physical SDF field to the frozen normal model.
        # Only the actual audit/protocol tags and the declared read-only observer
        # plugin are removed from this in-memory view.
        for key in ("mr3_audit_path", "mr3_epoch", "mr3_tagged_commands"):
            require(len(plugin[0].findall(key)) == 1, "effective SDF repeated protocol field")
            plugin[0].find(key).text = None
        extras = tree.findall(f".//plugin[@name='mr3_stop_response_observer_{robot}']")
        require(len(extras) == int(observer), "effective SDF observer presence differs")
        for extra in extras:
            require(extra.get("filename") == observer_library
                    and Path(observer_library).name == "libmr3_stop_response_observer.so",
                    "effective SDF observer implementation differs")
            parent = next(parent for parent in tree.iter() if extra in list(parent))
            parent.remove(extra)
        require(ET.canonicalize(ET.tostring(tree, encoding="unicode"), strip_text=True)
                == ET.canonicalize(read(WORKSPACE / MODEL).decode(), strip_text=True),
                "effective spawned physical SDF differs from frozen normal source")
        proof[robot] = {"actual_spawn_argv": argv, "requested_position_xyz": position,
                        "effective_sdf": str(model)}
        if observer:
            rows = _raw(read, episode / f"physics_{robot}.jsonl").splitlines()
            config = parse(rows[0])
            sample = next((row for row in map(parse, rows[1:]) if row.get("kind") == "sample"), None)
            require(config.get("kind") == "configuration" and config.get("epoch") == epoch
                    and config.get("robot") == robot and config.get("read_only") is True
                    and config.get("paused_only") is True and sample is not None
                    and sample.get("epoch") == epoch and sample.get("robot") == robot
                    and sample.get("measurements_finite") is True,
                    "initial observer model pose lacks real paused source identity")
            actual = sample["model"]["world_pose"]["position_xyz"]
            require(len(actual) == 3 and all(type(value) in (int, float) and math.isfinite(value)
                                            for value in actual)
                    and math.dist(actual, position) <= .01,
                    "initial real model pose is outside 1cm spawn admission")
            proof[robot]["initial_observer_model_pose"] = {
                "sim_time_ns": sample["sim_time_ns"], "record_sequence": sample["record_sequence"],
                "model": sample["model"], "distance_from_requested_spawn_m": math.dist(actual, position)}
    return {"robots": proof, "physical_pose_admission": observer,
            "scope": "actual requested spawn argv and saved SDF; " + (
                "first paused observer model getter within 1cm; no speed-threshold change" if observer
                else "no independent physical pose claim without the optional observer")}


def _collection(episode, freeze, read):
    run = episode.parent.parent
    require(episode.parent.name == "worker0" and episode.name == "episode001_open_101",
            "fixed trace requires exactly first worker0 open101 episode")
    summary = _json(read, run / "action_trace_summary.json")
    metadata = _json(read, run / "action_trace_metadata.json")
    native = _json(read, episode / "metadata.json")
    supervisor = _json(read, episode / "supervisor_metadata.json")
    shutdown = _json(read, episode / "supervisor_shutdown.json")
    transitions = [parse(line) for line in _raw(read, episode / "transitions.jsonl").splitlines() if line.strip()]
    epoch = native["epoch"]
    require(summary.get("schema") == metadata.get("schema") == "mr3-fixed-action-trace-v1"
            and summary.get("freeze") == metadata.get("freeze") == native.get("freeze") == freeze
            and summary.get("epoch") == supervisor.get("epoch") == epoch,
            "trace source/episode freeze or epoch differs")
    require(all(key in summary and summary[key] == value for key, value in metadata.items()),
            "immutable trace metadata differs from final summary")
    require(summary["actions"] == list(ACTIONS) and summary["robots"] == list(SPAWN)
            and summary["scene"] == native.get("scene") == supervisor.get("scene") == "open"
            and summary["seed"] == native.get("seed") == supervisor.get("seed") == 101
            and summary["run_directory"] == str(run) and summary["episode_directory"] == str(episode),
            "trace fixture or actual run directory differs")
    for row in (native, supervisor):
        require(row.get("plant_stimulus_arm") is None
                and row.get("plant_stimulus_work_deadline_ns") is None
                and row.get("terminal_probe") is False,
                "fixed trace used a diagnostic stimulus/terminal arm")
    require(not any("plant_stimulus_arm" in value for row in (summary, native, supervisor)
                    for value in row.get("command", [])), "trace actual command contains plant stimulus")
    require(supervisor.get("startup_wall_guard_sec") == 420.
            and supervisor.get("request_wall_guard_sec") == 90., "trace RPC wall upper bounds differ")
    require(summary.get("policy_calls") == summary.get("optimizer_steps") == 0
            and summary.get("training_eligible") is False and summary.get("validity_audit_required") is True
            and summary.get("native_decisions_requested") == summary.get("native_decisions_returned") == 8
            and summary.get("completed_requested_collection") is True
            and summary.get("outcome") == "CAPTURED_PENDING_INDEPENDENT_VALIDITY_AUDIT"
            and summary.get("first_failure") is None and summary.get("cleanup_errors") == [],
            "fixed eight-action collection is incomplete or has a real failure")
    source_proof = _sources(summary, freeze, read)
    started, ended = summary["started_wall_monotonic_ns"], summary["ended_wall_monotonic_ns"]
    require(type(started) is int and type(ended) is int and 0 < started <= ended
            and ended - started <= 700 * 10**9
            and summary["wall_sec_including_startup_and_close"] == (ended - started) / 1e9
            and summary["wall_limit_seconds"] == 700. and summary["close_reserve_seconds"] == 120.
            and summary["allocation_deadline_monotonic_ns"] == started + 700 * 10**9
            and summary["work_deadline_monotonic_ns"] == started + 580 * 10**9
            and summary["wall_limit_exceeded"] is False
            and summary["rpc_admission_upper_bounds_seconds"] == {"reset": 420., "step": 90.},
            "trace total wall including close exceeds or differs from fixed allocation")
    require(summary.get("shutdown_clean") is True and summary["shutdown_receipts"] == [shutdown]
            and shutdown.get("epoch") == epoch and shutdown.get("worker_returncode") == 0
            and shutdown.get("forced_shutdown") is False and shutdown.get("failed_sample") is False
            and shutdown.get("remaining_owned_processes") == shutdown.get("remaining_owned_zombies") == [],
            "trace close lacks its actual clean native shutdown receipt")
    require(len(transitions) == 9 and transitions[0].get("kind") == "reset"
            and len(summary["steps"]) == len(summary["mask_checks"]) == 8,
            "trace is not exactly one real reset plus eight returned transitions")
    previous = transitions[0]["snapshot"]

    def wrapper_info(row, resetting=False):
        snap = row["snapshot"]
        info = dict(row["info"], epoch=epoch, observation_sequence=snap["sequence"],
                    observation_digest=snap["digest"], candidate_version=snap["candidate_version"],
                    tensor_schema=TENSOR_SCHEMA)
        if resetting:
            info.update(scene="open", seed=101)
        return info

    require(summary["initial_info"] == wrapper_info(transitions[0], True),
            "trace initial wrapper info differs from real reset")
    last_return = started
    for decision, (action, row, step, check) in enumerate(zip(
            ACTIONS, transitions[1:], summary["steps"], summary["mask_checks"])):
        require(previous.get("epoch") == epoch and previous["digest"] == _digest(previous),
                "trace previous snapshot digest/epoch differs")
        mask = previous["joint_action_mask"]
        require(len(mask) == 1000 and all(type(value) is bool for value in mask) and mask[action]
                and check == {"decision": decision, "action": action,
                              "observation_digest": previous["digest"],
                              "observation_sequence": previous["sequence"],
                              "joint_action_mask": mask, "legal": True},
                "fixed action does not match full previous received legal mask")
        command = row["info"]["command"]
        require(row.get("kind") == "step" and row.get("terminated") is False
                and row.get("truncated") is (decision == 7)
                and row["info"].get("action_submitted", True) is True
                and command.get("action") == action and command.get("epoch") == epoch
                and command.get("observation_sequence") == previous["sequence"]
                and command.get("observation_digest") == previous["digest"]
                and row["info"].get("dt") == row["info"].get("physical_dt") == 1.,
                "fixed submitted action/digest/flags/dt differs from actual transition")
        require(step["decision"] == decision and step["action"] == action
                and step["reward"] == row["reward"] and step["terminated"] is row["terminated"]
                and step["truncated"] is row["truncated"] and step["info"] == wrapper_info(row),
                "trace reported reward/info differs from original transition")
        sent, returned = step["started_wall_monotonic_ns"], step["returned_wall_monotonic_ns"]
        require(type(sent) is int and type(returned) is int and last_return <= sent <= returned <= ended
                and sent <= started + 490 * 10**9 and returned <= started + 580 * 10**9,
                "trace step admission/return clock violates reserved RPC/close allocation")
        last_return = returned
        previous = row["snapshot"]
    require(previous.get("epoch") == epoch and previous["digest"] == _digest(previous)
            and transitions[-1]["info"].get("reason") == "external_sampler_limit",
            "trace final real snapshot/external truncation differs")
    config = summary["physics_config"]
    if config is not None:
        raw = read(Path(config["path"]))
        configuration = parse(raw)
        binding = _json(read, episode / "physics_diagnostic_binding.json")
        require(hashlib.sha256(raw).hexdigest() == config["sha256"]
                and configuration == config["configuration"]
                and configuration.get("schema") == "mr3-physics-diagnostic-config-v2"
                and configuration.get("mode") == "observer_only" and "profile_library" not in configuration
                and binding.get("schema") == "mr3-physics-diagnostic-binding-v2"
                and binding.get("epoch") == epoch and binding.get("mode") == "observer_only"
                and binding.get("config_sha256") == config["sha256"]
                and binding.get("config_source") == config["path"]
                and binding["observer_library"]["path"] == configuration["observer_library"]["path"]
                and binding.get("physics_intervention") == "none_observer_only",
                "trace optional observer config differs or includes intervention")
    spawn = _spawn(episode, epoch, read, config is not None,
                   config["configuration"]["observer_library"]["path"] if config is not None else None)
    return {"passed": True, "outcome": "PASS", "epoch": epoch, "steps": 8,
            "source_bindings": source_proof, "wall_seconds_including_close": (ended - started) / 1e9,
            "spawn": spawn,
            "scope": "collection identity only; all original mathematical/physical gates remain required"}


def audit_collection(episode, freeze):
    read = Reader()
    result = {"passed": False, "outcome": "INCOMPLETE", "errors": []}
    try:
        result.update(_collection(Path(episode), freeze, read))
    except (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError, StopIteration) as error:
        result["errors"].append(repr(error))
    try:
        read.finish()
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        result.update(passed=False, outcome="INCOMPLETE")
        result["errors"].append(repr(error))
    result["artifact_proof"] = read.bindings
    return result


def audit(episode, freeze):
    episode = Path(episode).resolve(strict=True)
    phase, base, native, command, scalar, sources = load_native_gates(WORKSPACE, freeze)
    result = {"schema": "mr3-fixed-action-trace-native-audit-v1", "freeze": freeze,
              "episode": str(episode), "source_bindings": sources, "components": {}, "errors": [],
              "scope": "Original episode/scalar/phase/archive/input/activity/motion gates. "
                       "No32-step fixture coverage, benchmark capacity, policy or task reliability credit."}
    cache = {}
    readiness = native.audit_initial_inputs_ready
    physics = dispatch_controlled_physics(native, [episode], cache)
    try:
        dispatch_controlled_readiness(native, [episode], cache)
        result["components"]["native"] = phase.corrected_audit(base, native, command, [episode])
    finally:
        native.audit_physics = physics
        native.audit_initial_inputs_ready = readiness
    motion = cache.get(episode)
    if motion is None:
        motion = audit_motion.audit_episode(episode)
    operations = {
        "collection": lambda: audit_collection(episode, freeze),
        "scalar": lambda: scalar.audit_episode(episode, freeze),
        "evaluator_phase": lambda: audit_evaluator_phase.audit_episode(episode),
        "archives": lambda: audit_preparation.audit_archives(episode),
        "execution_inputs": lambda: audit_preparation.audit_execution_inputs(episode, motion),
        "activity": lambda: audit_activity.audit_episode(episode),
        "motion": lambda: motion,
    }
    for name, operation in operations.items():
        try:
            result["components"][name] = operation()
        except (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError) as error:
            result["components"][name] = {"passed": False, "error": repr(error)}
    for name, value in result["components"].items():
        # The original scalar reader reports errors rather than a passed flag.
        if (name == "scalar" and value.get("errors") == []) or (
                name != "scalar" and value.get("passed") is True):
            continue
        result["errors"].append(name + ": " + str(value.get("errors", value.get("error", "failed"))))
    result["passed"] = not result["errors"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("evidence output already exists")
    try:
        result = audit(args.episode, args.freeze)
    except (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError) as error:
        result = {"schema": "mr3-fixed-action-trace-native-audit-v1", "freeze": args.freeze,
                  "passed": False, "error": repr(error)}
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": result["passed"], "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
