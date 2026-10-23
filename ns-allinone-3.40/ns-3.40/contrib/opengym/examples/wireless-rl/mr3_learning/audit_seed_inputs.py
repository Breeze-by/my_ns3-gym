"""Frozen-source full received-input replay for the explicit exact seed rule.

This reader never creates a world or imports ROS. It binds the actual worker,
supervisor, all actor snapshots and their seven archived received maps. The
legacy independent reader remains unchanged and is still used by legacy plans.
"""

import argparse
import copy
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import numpy as np

from .navigation_archive import reconstruct_navigation_payload
from .reach_gates import POINT_GRAPH_HELPER_SHA256
from .supervisor import (EXACT_SEED_VERSIONS, candidate_version_for_rules,
                         validate_start_graph_rule)


ROOT = Path(__file__).resolve().parents[7]
COMPONENT = Path("ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration")
RULE = "exact-point-bridge-v1"
VERSION = "mr3-navigation-geometric-staging-v6-exact-seed-v1"
ROBOTS = ("tb1", "tb2", "tb3")


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def audit_episode(directory, freeze, *, root=ROOT):
    directory, root = Path(directory), Path(root)
    require(type(freeze) is str and re.fullmatch(r"[0-9a-f]{40}", freeze), "exact source freeze required")
    bindings, sources = {}, {}

    def read(path):
        path = Path(path)
        actual = path if path.exists() else Path(str(path) + ".gz")
        raw = actual.read_bytes()
        spec = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        require(bindings.setdefault(str(actual.resolve()), spec) == spec, "input changed during replay")
        return gzip.decompress(raw) if actual != path else raw

    def load(path):
        return json.loads(read(path))

    def rows(path):
        raw = read(path)
        require(not raw or raw.endswith(b"\n"), "partial native JSONL")
        return [json.loads(line) for line in raw.splitlines()]

    native, supervisor = (load(directory / filename) for filename in
                          ("metadata.json", "supervisor_metadata.json"))
    from .motion_authority_profile import selected_motion_authority_profile
    authority = selected_motion_authority_profile(native)
    require(selected_motion_authority_profile(supervisor) == authority,
            "input archive native/supervisor receiving authority profile mismatch")
    seed_rule = native.get("seed_rule")
    require(type(seed_rule) is str and seed_rule in EXACT_SEED_VERSIONS and native.get("freeze") == freeze
            and supervisor.get("seed_rule") == seed_rule, "native/supervisor exact seed rule mismatch")
    start_graph_rule = validate_start_graph_rule(native.get("start_graph_rule", "original-seed-cell"),
                                                seed_rule=seed_rule)
    require(supervisor.get("start_graph_rule", "original-seed-cell") == start_graph_rule,
            "native/supervisor start graph rule mismatch")
    version = candidate_version_for_rules(seed_rule, start_graph_rule)
    require((directory / "summary.json").is_file(), "native episode has not closed")
    transitions, events = rows(directory / "transitions.jsonl"), rows(directory / "adapter.jsonl")
    require(transitions and transitions[0]["kind"] == "reset", "native reset missing")
    starts = [event["payload"]["start_sim_time_sec"] for event in events if event["kind"] == "task_start"]
    require(len(starts) == 1, "unique real task release required")
    unique, referenced, maps = {}, set(), {}
    names = ("__init__.py", "mr3_observation.py", "mr3_episode.py",
             "mr3_seed_certificate.py", "mr3_reach_geometry.py")
    if start_graph_rule != "original-seed-cell":
        names += ("mr3_point_graph.py",)
    learner = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/"
    for relative in (str(Path(__file__).resolve().relative_to(root)),
                     learner + "navigation_archive.py", learner + "supervisor.py", learner + "motion_authority_profile.py",
                     "ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py"):
        raw = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
        require((root / relative).read_bytes() == raw, "reader/source differs from native freeze: " + relative)
        sources[relative] = {"sha256": hashlib.sha256(raw).hexdigest(), "git_source": freeze + ":" + relative}
    with tempfile.TemporaryDirectory(prefix="mr3-exact-seed-reader-") as temporary:
        package = Path(temporary) / "multi_robot_exploration"
        package.mkdir()
        for name in names:
            relative = str(COMPONENT / name)
            raw = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
            require((root / relative).read_bytes() == raw, "current source differs from native freeze: " + relative)
            if name == "mr3_point_graph.py":
                require(hashlib.sha256(raw).hexdigest() == POINT_GRAPH_HELPER_SHA256,
                        "point graph helper differs from declared V37 source")
            sources[relative] = {"sha256": hashlib.sha256(raw).hexdigest(), "git_source": freeze + ":" + relative}
            (package / name).write_bytes(raw)
        prior = {name: value for name, value in sys.modules.items()
                 if name == "multi_robot_exploration" or name.startswith("multi_robot_exploration.")}
        for name in prior:
            del sys.modules[name]
        sys.path.insert(0, temporary)
        try:
            observation = importlib.import_module("multi_robot_exploration.mr3_observation")
            for transition in transitions:
                snapshot, info = transition["snapshot"], transition["info"]
                require(snapshot["epoch"] == native["epoch"]
                        and snapshot["candidate_rule"].get("seed_rule") == seed_rule
                        and snapshot["candidate_rule"].get("start_graph_rule", "original-seed-cell") == start_graph_rule
                        and snapshot["candidate_rule"].get("version") == version,
                        "actor snapshot did not use the declared exact seed rule")
                require(observation.snapshot_digest(snapshot) == snapshot["digest"], "actor snapshot digest differs")
                manifest_path = directory / "observation_inputs/snapshots" / (
                    f"{snapshot['sequence']:08d}_{snapshot['digest']}.json")
                manifest = load(manifest_path)
                require(manifest["schema"] == "mr3-observation-input-archive-v2"
                        and manifest["scope"] == "encoder_result_before_publication"
                        and manifest["snapshot_digest"] == snapshot["digest"]
                        and all(manifest[key] == snapshot[key] for key in
                                ("epoch", "sequence", "candidate_version", "source_stamp")),
                        "archived actor identity differs")
                bundle = manifest["metadata"]
                require(bundle["epoch"] == snapshot["epoch"] and bundle["map_version"] == snapshot["map_version"]
                        == info["watermarks"]["map_version"]
                        and bundle["map_sources"] == snapshot["map"]["sources"] == info["watermarks"]["map_sources"]
                        and bundle["map_payload_sha256"] == info["watermarks"]["map_payload_sha256"]
                        and bundle["map_source_stamp"] == snapshot["map"]["source_stamp"]
                        and bundle["map_received_stamp"] == snapshot["map"]["received_stamp"]
                        and bundle["navigation_sources"] == snapshot["navigation_sources"]
                        == info["watermarks"]["navigation_sources"]
                        and bundle["navigation_composition"] == {"version": observation.NAVIGATION_COMPOSITION_VERSION},
                        "received input metadata differs")
                require(set(manifest["maps"]) == {"fused", *ROBOTS, *("navigation:" + name for name in ROBOTS)},
                        "received map inventory differs")
                payloads = {}
                for role, entry in manifest["maps"].items():
                    expected = (bundle["map_payload_sha256"] if role == "fused" else
                                bundle["navigation_sources"][role.split(":", 1)[1]]["payload_sha256"]
                                if role.startswith("navigation:") else bundle["map_sources"][role]["payload_sha256"])
                    require(entry == {"payload_sha256": expected, "artifact": f"maps/{expected}.json.gz"},
                            "archived map reference differs")
                    path = directory / "observation_inputs" / entry["artifact"]
                    if expected not in maps:
                        raw = gzip.decompress(read(path)); value = json.loads(raw)
                        require(raw == canonical(value) and hashlib.sha256(raw).hexdigest() == expected,
                                "received map bytes differ")
                        maps[expected] = value
                    payloads[role] = maps[expected]; referenced.add(path)
                for name in ROBOTS:
                    require(reconstruct_navigation_payload(payloads[name], payloads["fused"])
                            == payloads["navigation:" + name], "navigation composition differs")
                if snapshot["digest"] in unique:
                    continue
                robots = copy.deepcopy(snapshot["robots"])
                for robot in robots:
                    if robot["navigation"]["missing"]:
                        robot["navigation"] = {}
                    else:
                        robot["navigation"]["sequence"] = robot["navigation"]["receipt_sequence"]

                def grid_record(role, metadata):
                    payload = payloads[role]; geometry = payload["info"]
                    return {"grid": np.asarray(payload["data"], dtype=np.int16).reshape(geometry["height"], geometry["width"]),
                            "resolution": geometry["resolution"],
                            "origin": tuple(geometry["origin"]["position"][axis] for axis in ("x", "y")),
                            "epoch": snapshot["epoch"], **metadata}

                fused = grid_record("fused", {})
                replay = observation.build_snapshot(fused["grid"], fused["resolution"], fused["origin"],
                    robots, snapshot["source_stamp"], snapshot["epoch"], snapshot["map_version"], snapshot["sequence"],
                    map_source_stamp=bundle["map_source_stamp"], map_received_stamp=bundle["map_received_stamp"],
                    map_sources=bundle["map_sources"], task_start=starts[0],
                    robot_maps={name: grid_record(name, bundle["map_sources"][name]) for name in ROBOTS},
                    navigation_maps={name: grid_record("navigation:" + name, bundle["navigation_sources"][name])
                                     for name in ROBOTS}, seed_rule=seed_rule,
                    **({"start_graph_rule": start_graph_rule} if start_graph_rule != "original-seed-cell" else {}))
                require(replay == snapshot, "full received-input exact seed replay mismatch")
                unique[snapshot["digest"]] = snapshot["sequence"]
        finally:
            sys.path.remove(temporary)
            for name in list(sys.modules):
                if name == "multi_robot_exploration" or name.startswith("multi_robot_exploration."):
                    del sys.modules[name]
            sys.modules.update(prior)
    manifest_paths = set((directory / "observation_inputs/snapshots").glob("*.json"))
    require(len(manifest_paths) == len(unique) == len(set(unique.values())), "extra/duplicate actor manifest")
    require(set((directory / "observation_inputs/maps").glob("*.json.gz")) == referenced,
            "extra/unreferenced received map")
    published = [event["payload"] for event in events if event["kind"] == "observation"]
    require(len(published) == len(unique) and {value["digest"] for value in published} == set(unique)
            and all(value in [row["snapshot"] for row in transitions] for value in published),
            "actual published actor inventory differs")
    completed = [event["payload"] for event in events if event["kind"] == "snapshot_completed"]
    require(len(completed) == len(unique) and all(value["ok"] for value in completed),
            "actual snapshot completion inventory differs")
    for path, expected in bindings.items():
        raw = Path(path).read_bytes()
        require(len(raw) == expected["bytes"] and hashlib.sha256(raw).hexdigest() == expected["sha256"],
                "received input changed before verdict")
    for relative, expected in sources.items():
        require(hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected["sha256"],
                "source changed before verdict")
    return {"schema": "mr3-exact-seed-native-input-replay-v1", "passed": True, "errors": [],
            **({"motion_authority_profile":authority,"authority_behavior_proved":False}
               if authority is not None else {}),
            "freeze": freeze, "seed_rule": seed_rule, "episode": str(directory),
            **({"start_graph_rule": start_graph_rule} if start_graph_rule != "original-seed-cell" else {}),
            "whole_observation_and_seven_map_replay_passed": True,
            "exact_full_snapshot_replays": len(unique), "input_bindings": bindings, "source_proof": sources,
            "robot_recovery_scope": "saved normalized sufficient fields; navigation missing/receipt_sequence inverted; not original raw kwargs",
            "scope": "frozen-source seven-map and full snapshot self-consistency; Information/activity/physical/task/closure gates remain independently necessary"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    require(not args.output.exists(), "output already exists")
    metadata = json.loads((args.episode / "metadata.json").read_text())
    freeze = metadata["freeze"]
    try:
        result = audit_episode(args.episode, freeze)
    except (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError, OverflowError,
            subprocess.SubprocessError) as error:
        result = {"schema": "mr3-exact-seed-native-input-replay-v1", "passed": False, "errors": [repr(error)],
                  "freeze": freeze, "seed_rule": metadata.get("seed_rule"), "episode": str(args.episode),
                  **({"start_graph_rule": metadata["start_graph_rule"]} if "start_graph_rule" in metadata else {})}
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write("\n")
    print(json.dumps({"passed": result["passed"], "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
