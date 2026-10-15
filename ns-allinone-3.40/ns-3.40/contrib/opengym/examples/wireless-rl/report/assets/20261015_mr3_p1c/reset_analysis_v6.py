#!/usr/bin/env python3
"""Describe completed v6 normal resets, offline; never start ROS or a simulator.

Run only after root authorizes final analysis. Initial pose/map differences are
descriptive, without an invented reproducibility tolerance. Source initialization,
saved identity/epoch evidence and delivered-source watermarks are separate proof
layers; different map hashes alone never establish absence of old state.
"""

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys


FREEZE = "c8d483228ecb0105c905459578eddbb4a23d4520"
WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
ASSETS = WIRELESS + "report/assets/20261015_mr3_p1c/"
ROS = "ros2_ws/ros2-multi-robot-automap/"
PACKAGE = ROS + "src/multi_robot/"
MODULE = ROS + "src/multi_robot_exploration/multi_robot_exploration/"
ROBOTS = ("tb1", "tb2", "tb3")
CHECKS_SHA = "3fa50ea70ca1716d73826f4c45cba0ddf88f9dbe4c9b33fc644f60bd0250516d"
PHASE_SHA = "3ce800bfa0455d25a1c3257635c7c4d593478082bbbf1c4dab6a10eed2fc6991"
SPAWNS = {"tb1": [0., -.45, .01, 0., 0., 0.],
          "tb2": [0., .45, .01, 0., 0., 0.],
          "tb3": [.45, 0., .01, 0., 0., 0.]}
PER_EPISODE = {"mr3_episode_epoch", "mr3_audit_path", "evaluation_episode_id",
               "evaluation_output_dir"}
INITIALIZATION_SCOPE = {
    "adapter": "new sequence0, empty history/map/state/handles/command caches and dispatcher",
    "information": "new epoch-owned empty local/delivered maps, states and transport stores",
    "reward": "new initial-mask ledger, rewarded count0, sequence0, counters0, unsealed cache",
    "worker": "new snapshot/reward counters, no previous terminal or response cache",
    "history": "empty at construction; current-epoch warmup may populate the first observation",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical(value):
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode())


def ns(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            "invalid finite nonnegative time")
    return round(value * 10**9)


class Reader:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.files = {}

    def raw(self, name):
        path = self.directory / name
        compressed = not path.exists()
        if compressed:
            path = path.with_suffix(path.suffix + ".gz")
        data = path.read_bytes()
        decoded = gzip.decompress(data) if compressed else data
        self.files[name] = {"path": str(path.resolve()), "stored_bytes": len(data),
                            "stored_sha256": sha(data), "decoded_bytes": len(decoded),
                            "decoded_sha256": sha(decoded), "gzip": compressed}
        return decoded

    def json(self, name):
        return json.loads(self.raw(name))

    def rows(self, name):
        return [json.loads(line) for line in self.raw(name).splitlines()]


def arguments(values):
    result = {}
    for value in values:
        if ":=" in value:
            key, item = value.split(":=", 1)
            require(key not in result, "duplicate launch argument " + key)
            result[key] = item
    return result


def flag(argv, key):
    require(argv.count(key) == 1, "missing/duplicate actual argv flag " + key)
    return argv[argv.index(key) + 1]


def frozen_catalogue(root):
    """Pin current runtime and immutable Git input blobs; import no ROS packages."""
    checks_path = root / ASSETS / "implementation_checks_v6.json"
    require(sha(checks_path.read_bytes()) == CHECKS_SHA, "implementation lock changed")
    checks = json.loads(checks_path.read_text())
    sources = dict(checks["source_sha256"])
    extra = [PACKAGE + "models/turtlebot3_waffle/model.sdf",
             PACKAGE + "urdf/turtlebot3_waffle.urdf",
             MODULE + "mr3_protocol.py", MODULE + "mr3_transport.py",
             ROS + "src/slam_toolbox/launch/online_async_multirobot_launch.py",
             ROS + "src/slam_toolbox/config/mapper_params_online_multi_async.yaml"]
    extra += [PACKAGE + "params/nav2_params_" + name + "_0.yaml" for name in ROBOTS]
    extra += [PACKAGE + "worlds/p1c_" + scene + ".world"
              for scene in ("open", "rooms", "corridors")]
    extra += [PACKAGE + "config/mr3_p1a/" + scene + ".json"
              for scene in ("open", "rooms", "corridors")]
    blobs, proof = {}, {}
    for name in sorted(set(sources) | set(extra)):
        blob = subprocess.check_output(["git", "show", FREEZE + ":" + name], cwd=root)
        digest = sha(blob)
        require(name not in sources or sources[name] == digest,
                "frozen lock/blob mismatch: " + name)
        require(sha((root / name).read_bytes()) == digest, "current input/source changed: " + name)
        blobs[name] = blob
        proof[name] = {"sha256": digest, "git_object": FREEZE + ":" + name,
                       "current_bytes_match": True}
    return blobs, proof


def load_phase(root):
    path = root / ASSETS / "audit_mr3_env_contact_phase_v2.py"
    require(sha(path.read_bytes()) == PHASE_SHA, "phase helper changed")
    spec = importlib.util.spec_from_file_location("mr3_reset_phase_dependency", path)
    phase = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = phase
    spec.loader.exec_module(phase)
    audit, proof = phase.load_auditor(root)
    return phase, audit, proof


def initial_state(reset, adapter, epoch, audit):
    snapshot, info = reset["snapshot"], reset["info"]
    audit.validate_snapshot(snapshot, epoch)
    release = info["release_time_ns"]
    reward = info["reward_diagnostics"]
    require(reset["kind"] == "reset" and reset["reward"] == 0 and info["dt"] == 0
            and reset["terminated"] is False and reset["truncated"] is False
            and snapshot["sequence"] == 1 and info["epoch"] == epoch
            and ns(snapshot["source_stamp"]) == release
            and snapshot["task_elapsed_sec"] == 0 and snapshot["task_remaining_sec"] == 300
            and reward["sequence"] == 0 and reward["reward"] == 0
            and reward["kind"] == "reward_reset_binding" and reward["reset_bound"] is True
            and reward["delta_sim_time"] == 0 and reward["epoch"] == epoch
            and ns(reward["step_start"]) == ns(reward["effective_step_end"]) == release,
            "initial observation/time/reward ledger was not reset")
    watermark = info["watermarks"]
    require(reward["map_watermark"]["payload_sha256"] == watermark["map_payload_sha256"]
            and snapshot["map"]["sources"] == watermark["map_sources"],
            "initial map/reward/delivery pairing differs")
    observations = [i for i, row in enumerate(adapter) if row.get("kind") == "observation"
                    and row.get("payload", {}).get("sequence") == 1]
    require(len(observations) == 1 and adapter[observations[0]]["payload"] == snapshot,
            "first saved adapter observation differs from reset")
    first = observations[0]
    for row in adapter:
        require(row.get("epoch") == epoch, "cross-epoch adapter record")
    actions = [(i, row) for i, row in enumerate(adapter) if row.get("kind") == "action"]
    require(actions and actions[0][0] > first
            and actions[0][1]["payload"]["observation_sequence"] == 1
            and actions[0][1]["payload"]["observation_digest"] == snapshot["digest"],
            "first action refers to an old episode/observation")
    histories = {}
    for robot in snapshot["robots"]:
        name, nav = robot["name"], robot["navigation"]
        require(robot["epoch"] == epoch and robot["valid"] is True
                and all(type(robot[key]) in (int, float) and math.isfinite(robot[key])
                        for key in ("x", "y", "yaw"))
                and nav["phase"] == "idle" and nav["owned"] is False
                and all(nav.get(key) is None for key in
                        ("goal_id", "last_goal_id", "last_terminal", "command_id",
                         "requested_at", "lease_until", "last_failure"))
                and nav["commitment_remaining_sec"] == 0,
                "initial goal/ownership state leaked: " + name)
        require(0 < ns(robot["source_stamp"]) <= ns(robot["received_stamp"]) <= release,
                "initial robot source outside current warmup/pause: " + name)
        valid_stamps = {ns(item["source_stamp"]) for row in adapter[:first]
                        if row.get("kind") == "state_update" for item in row["payload"]["robots"]
                        if item["name"] == name and item.get("valid") is True}
        history = robot["history"]
        stamps = [ns(item["source_stamp"]) for item in history]
        require(len(stamps) <= 16 and all(a < b for a, b in zip(stamps, stamps[1:]))
                and all(stamp in valid_stamps and 0 < stamp <= ns(robot["source_stamp"])
                        for stamp in stamps)
                and all(type(item[key]) in (int, float) and math.isfinite(item[key])
                        for item in history for key in ("x", "y")),
                "history lacks current-epoch delivered-source proof: " + name)
        source, path = watermark["map_sources"][name], snapshot["path_maps"][name]
        require(path["epoch"] == epoch and path["missing"] is False
                and all(path[key] == source[key] for key in
                        ("payload_sha256", "sequence", "version", "source_stamp", "received_stamp"))
                and 0 < ns(source["source_stamp"]) <= ns(source["received_stamp"]) <= release,
                "own map lacks current delivered epoch/watermark: " + name)
        histories[name] = {"count": len(history), "min_source_ns": min(stamps, default=None),
                           "max_source_ns": max(stamps, default=None),
                           "all_stamps_match_current_epoch_state_records": True}
    return {"snapshot_sequence": 1, "reward_sequence": 0, "reward": 0.,
            "task_elapsed_sec": 0., "task_remaining_sec": 300., "release_ns": release,
            "initial_correct_free_cells": reward["initial_correct_free_cells"],
            "history": histories, "navigation_initially_idle_unowned": True,
            "warmup_map_and_history_are_not_claimed_blank": True,
            "history_xy_raw_state_replay_available": False}


def configuration(root, metadata, evaluator, starts, blobs, proof):
    scene, seed = metadata["scene"], metadata["seed"]
    args = arguments(metadata["command"])
    world = PACKAGE + "worlds/p1c_" + scene + ".world"
    contract = PACKAGE + "config/mr3_p1a/" + scene + ".json"
    require(evaluator["world_sha256"] == proof[world]["sha256"]
            and evaluator["task_contract_sha256"] == proof[contract]["sha256"]
            and json.loads(blobs[contract])["world_sha256"] == proof[world]["sha256"]
            and evaluator["gazebo_seed"] == seed and evaluator["robot_count"] == 3
            and args["world"] == Path(world).name and args["gazebo_seed"] == str(seed),
            "world/contract/seed input chain differs")
    servers = [r for r in starts if r["role"] == "gazebo_server"]
    require(len(servers) == 1 and "--seed=" + str(seed) in servers[0]["argv"]
            and evaluator["world_file"] in servers[0]["argv"], "actual Gazebo argv differs")
    spawn_rows = [r for r in starts if "spawn_entity.py" in r["process_name"]]
    require(len(spawn_rows) == 3, "expected exactly three actual spawn processes")
    spawns = {}
    model = PACKAGE + "models/turtlebot3_waffle/model.sdf"
    for row in spawn_rows:
        argv = row["argv"]
        name = flag(argv, "-entity")
        require(name in ROBOTS and name not in spawns
                and flag(argv, "-robot_namespace") == "/" + name, "spawn entity/namespace differs")
        coordinates = [float(flag(argv, key))
                       for key in ("-x", "-y", "-z", "-R", "-P", "-Y")]
        require(coordinates == SPAWNS[name], "spawn pose differs: " + name)
        deployed = Path(flag(argv, "-file")).resolve()
        require(deployed.is_relative_to(root)
                and sha(deployed.read_bytes()) == proof[model]["sha256"],
                "actual model path/current deployment differs")
        spawns[name] = {"pose_xyz_rpy": coordinates, "model_sha256": proof[model]["sha256"]}
    fixed = {key: value for key, value in args.items() if key not in PER_EPISODE}
    require(Path(fixed["evaluation_contract_path"]).name == Path(contract).name,
            "launch contract path differs")
    fixed["evaluation_contract_path"] = contract
    semantic = {"freeze": FREEZE, "launch_arguments": fixed,
                "physical_step_ns": metadata["physical_step_ns"],
                "policy_step_ns": metadata["policy_step_ns"],
                "quantum_steps": metadata["quantum_steps"],
                "transport_environment": metadata["transport_environment"], "spawns": spawns,
                "world_sha256": proof[world]["sha256"],
                "contract_sha256": proof[contract]["sha256"],
                "common_source_sha256": {k: v["sha256"] for k, v in proof.items()
                                         if "/worlds/" not in k and "/mr3_p1a/" not in k}}
    return {"semantic_input": semantic, "semantic_input_sha256": canonical(semantic),
            "actual_gazebo_argv": servers[0]["argv"], "actual_spawn_rows": spawn_rows,
            "deployment_hash_scope": (
                "current path bytes + frozen Git + actual argv; no saved temp YAML bytes")}


def summarize_episode(root, directory, phase, audit, blobs, proof):
    reader = Reader(directory)
    metadata, supervisor, shutdown = (
        reader.json(name) for name in
        ("metadata.json", "supervisor_metadata.json", "supervisor_shutdown.json"))
    epoch = metadata["epoch"]
    require(metadata["freeze"] == FREEZE and supervisor["epoch"] == epoch
            and supervisor["reset_kind"] == "complete_process_rebuild",
            "reset epoch/freeze differs")
    reset = reader.rows("transitions.jsonl")[0]
    adapter = reader.rows("adapter.jsonl")
    evaluator = reader.json(epoch + ".json")
    summary = reader.json("summary.json")
    text = reader.raw("launch.log").decode()
    native = reader.json("native_stop.json")
    require(evaluator["episode_id"] == summary["epoch"] == epoch,
            "evaluation/summary epoch differs")
    process = audit.audit_processes(supervisor, shutdown, epoch)
    launch_coverage = audit.audit_launch_process_coverage(text, native, shutdown)
    context = phase.release_context(audit, directory)
    starts = [json.loads(line.split("MR3_ORDERED_SHUTDOWN ", 1)[1])
              for line in text.splitlines() if "MR3_ORDERED_SHUTDOWN " in line]
    starts = [row for row in starts if row.get("event") == "process_started"]
    critical = {}
    for needle in ("gzserver", "mr3_adapter", "mr3_information", "task_evaluator"):
        matches = [row for row in starts if row["process_name"].rsplit("-", 1)[0] == needle]
        require(len(matches) == 1, "missing new process " + needle)
        identities = [row for row in shutdown["owned_processes_seen"]
                      if row["pid"] == matches[0]["pid"]]
        require(len(identities) == 1, "critical process lacks actual start identity " + needle)
        critical[needle] = identities[0]
    initial = initial_state(reset, adapter, epoch, audit)
    config = configuration(root, metadata, evaluator, starts, blobs, proof)
    robots = {row["name"]: {key: row[key] for key in
              ("x", "y", "yaw", "source_stamp", "received_stamp",
               "source_age_sec", "received_age_sec")}
              for row in reset["snapshot"]["robots"]}
    return {"directory": str(Path(directory).resolve()), "epoch": epoch,
            "scene": metadata["scene"], "seed": metadata["seed"],
            "worker_id": supervisor["worker_id"],
            "initial_state": initial, "robots": robots, "configuration": config,
            "processes": process, "critical_actual_identities": critical,
            "launch_identity_coverage": launch_coverage, "paused_release": context,
            "initial_snapshot_digest": reset["snapshot"]["digest"],
            "map_payload_sha256": reset["info"]["watermarks"]["map_payload_sha256"],
            "map_sources": reset["info"]["watermarks"]["map_sources"],
            "path_maps": reset["snapshot"]["path_maps"], "map_geometry": reset["snapshot"]["map"],
            "input_files": reader.files}


def pair(left, right, same_seed=True):
    require(left["epoch"] != right["epoch"], "epoch reused across reset")
    old = {tuple(p) for p in left["processes"]["owned_pid_identities"]}
    new = {tuple(p) for p in right["processes"]["owned_pid_identities"]}
    require(not old.intersection(new), "owned PID/start identity reused")
    if same_seed:
        require(left["configuration"]["semantic_input_sha256"] ==
                right["configuration"]["semantic_input_sha256"],
                "same-seed input configuration differs")
    differences = {}
    for name in ROBOTS:
        a, b = left["robots"][name], right["robots"][name]
        xy = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
        yaw = abs(math.atan2(math.sin(b["yaw"] - a["yaw"]), math.cos(b["yaw"] - a["yaw"])))
        differences[name] = {"xy_m": xy, "yaw_rad": yaw, "yaw_deg": math.degrees(yaw),
                             "left": a, "right": b}
    return {"left": left["directory"], "right": right["directory"],
            "new_epoch_and_disjoint_saved_process_identities": True,
            "same_seed_comparison": same_seed, "pose_differences": differences,
            "max_xy_m": max(row["xy_m"] for row in differences.values()),
            "max_yaw_rad": max(row["yaw_rad"] for row in differences.values()),
            "map_payload_equal": left["map_payload_sha256"] == right["map_payload_sha256"],
            "own_map_payload_equal": {
                name: left["map_sources"][name]["payload_sha256"] ==
                right["map_sources"][name]["payload_sha256"] for name in ROBOTS},
            "geometry_digest_equal": {
                name: left["path_maps"][name]["geometry_sha256"] ==
                right["path_maps"][name]["geometry_sha256"] for name in ROBOTS}}


def analyse(root, native):
    blobs, source = frozen_catalogue(root)
    phase, audit, phase_proof = load_phase(root)
    episodes, pairs, cross, errors, links = [], [], [], [], []
    all_identities, all_epochs = set(), set()
    for workers in (1, 2, 4):
        directory = native / ("workers" + str(workers))
        benchmark = Reader(directory)
        declaration = benchmark.json("benchmark_metadata.json")
        require(declaration["workers"] == workers and declaration["freeze"] == FREEZE,
                "benchmark reset configuration differs")
        schedule = [["open", 101], ["open", 101]]
        if workers == 1:
            schedule += [["rooms", 202], ["corridors", 303]]
        require(declaration["schedule"] == schedule, "normal reset schedule changed")
        link = root / ASSETS / f"workers{workers}_v6_contact_phase_v2_benchmark_audit.json"
        verdict = json.loads(link.read_text())
        require(verdict["passed"] is True and verdict["freeze"] == FREEZE
                and verdict["offline_contact_phase_audit"]["wrapper_sha256"] == PHASE_SHA,
                "normal benchmark lacks the uniform phase2 audit")
        links.append({"path": str(link), "sha256": sha(link.read_bytes()),
                      "benchmark_inputs": benchmark.files})
        for worker in range(workers):
            group = []
            for index, (scene, seed) in enumerate(schedule, 1):
                path = directory / f"worker{worker}" / f"episode{index:03d}_{scene}_{seed}"
                try:
                    row = summarize_episode(root, path, phase, audit, blobs, source)
                    require([row["scene"], row["seed"]] == [scene, seed]
                            and row["worker_id"] == worker, "episode declaration differs")
                    identities = {tuple(p) for p in row["processes"]["owned_pid_identities"]}
                    require(row["epoch"] not in all_epochs
                            and not identities.intersection(all_identities),
                            "epoch/owned full process identity reused across normal matrix")
                    all_epochs.add(row["epoch"])
                    all_identities.update(identities)
                    group.append(row)
                    episodes.append(row)
                except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
                    errors.append({"directory": str(path), "error": str(error)})
            if len(group) == len(schedule):
                try:
                    pairs.append(pair(group[0], group[1]))
                    cross.extend(pair(a, b, False) for a, b in zip(group[1:], group[2:]))
                except (ValueError, TypeError, KeyError) as error:
                    errors.append({"worker": worker, "workers": workers, "error": str(error)})
    opens = [row for row in episodes if row["scene"] == "open"]
    require(len(episodes) == 16 and len(pairs) == 7 and len(cross) == 2 or errors,
            "reset cell coverage differs")
    equivalence = {row["configuration"]["semantic_input_sha256"] for row in opens}
    if len(equivalence) != 1:
        errors.append({"error": "open101 semantic input configuration differs across workers"})
    all_pairs = [pair(a, b) for a, b in itertools.combinations(opens, 2)] if not errors else []
    return {"schema": "mr3-p1c-reset-summary-v1", "freeze": FREEZE, "passed": not errors,
            "errors": errors, "required_cells": 16, "observed_cells": len(episodes),
            "episodes": episodes, "same_seed_pairs": pairs, "cross_scene_isolation": cross,
            "same_seed_max_xy_m": max((p["max_xy_m"] for p in pairs), default=None),
            "same_seed_max_yaw_rad": max((p["max_yaw_rad"] for p in pairs), default=None),
            "all_open101_pairwise_maxima": {
                "pair_count": len(all_pairs),
                "xy_pair": max(all_pairs, key=lambda p: p["max_xy_m"], default=None),
                "yaw_pair": max(all_pairs, key=lambda p: p["max_yaw_rad"], default=None)},
            "open101_semantic_input_hash_count": len(equivalence), "source_proof": source,
            "phase_source_proof": phase_proof, "initialization_source_scope": INITIALIZATION_SCOPE,
            "initialization_proof_kind": (
                "reviewed pinned construction code; no dynamic cache probe"),
            "primary_audit_links": links, "current_proc_snapshot_performed": False,
            "scope": ("Saved reset identities/source chain and estimated initial differences; "
                      "no bitwise DDS/SLAM claim"),
            "limitations": [
                "No saved temp RewrittenYaml bytes; frozen sources and actual launch paths only",
                "Deployed model digest checked now; no independent run-time file attestation",
                "History lacks per-point epoch/raw XY logs; process/filter/source-stamp proof only",
                "Payload SHA includes headers; hash inequality is not occupancy/no-residual proof",
                "Snapshot SHA includes epoch/time; its inequality is not a reproducibility failure",
                "No per-message contact timing replay or initial raw reward_ready payload",
                "No invented numerical tolerance; pose differences are descriptive",
                "Saved cleanup receipts do not supply an exact cross-episode process span"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output exists; choose a new filename")
    root = next(p for p in Path(__file__).resolve().parents if (p / ".git").exists())
    report = analyse(root, args.native_root or root / ASSETS / "native_v6")
    report.update(created_at_utc=datetime.now(timezone.utc).isoformat(),
                  analyzer_sha256=sha(Path(__file__).read_bytes()),
                  command=[sys.executable, *sys.argv])
    with args.output.open("x") as output:
        json.dump(report, output, sort_keys=True, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"passed": report["passed"], "errors": report["errors"],
                      "output": str(args.output)}, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
