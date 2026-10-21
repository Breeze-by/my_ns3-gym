"""One charged proxy conformity activity; six closed V21 inputs, no training.

Native map bytes come from the original observation archive. Robot parameters
are recovered from the saved snapshot's sufficient normalized fields, including
the explicit receipt_sequence -> navigation.sequence inverse. Unrecorded raw
builder arguments are not claimed to have been recovered. Old native failures
and source identity remain unchanged. The system helper uses synthetic boxes,
never development episodes, to check integration and information separation.
"""

import argparse
from contextlib import contextmanager
import copy
import gzip
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from types import ModuleType

import numpy as np

from .audit_proxy2d import (PureBuilder, canonical, parse, require, tensor_proofs, ROOT, PURE,
                            EXACT_SEED_RULE, actor_record)
from .proxy2d_codec import encode_arrays


NATIVE_FREEZE = "c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90"
WIRELESS = Path(__file__).resolve().parent.parent
NATIVE_ASSETS = WIRELESS / "report/assets/20261020_mr3_p2a_v21"
DEFAULT_NATIVE_ROOT = ROOT / "ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v21_diagnostic/uniform_two_episodes"
ROBOTS = ("tb1", "tb2", "tb3")
COMPOSITION = "mr3-own-known-shared-unknown-v1"
ERRORS = (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError,
          AssertionError, OverflowError, subprocess.SubprocessError, EOFError)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_bindings(freeze, seed_rule="legacy"):
    require(type(freeze) is str and re.fullmatch(r"[0-9a-f]{40}", freeze), "exact current freeze required")
    require(seed_rule in ("legacy", EXACT_SEED_RULE), "unknown conformity seed rule")
    names = (Path(__file__), Path(__file__).with_name("audit_proxy2d.py"),
             Path(__file__).with_name("observation.py"), Path(__file__).with_name("proxy2d_codec.py"),
             PURE / "mr3_observation.py", PURE / "mr3_episode.py", PURE / "mr3_observation_archive.py",
             PURE / "mr3_proxy2d_world.py", PURE / "mr3_reward.py", PURE / "mr3_task_contract.py",
             PURE / "mr3_contacts.py", PURE / "mr3_transport.py",
             PURE / "mr3_reach_geometry.py", PURE / "mr3_seed_certificate.py",
             PURE.parents[1] / "multi_robot/models/turtlebot3_waffle/model.sdf",
             PURE.parents[1] / "multi_robot/config/mr3_p1a/open.json")
    proof, stable = {}, {}
    for path in names:
        raw = path.read_bytes(); relative = path.relative_to(ROOT).as_posix()
        frozen = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=ROOT)
        require(raw == frozen, "conformity source differs from freeze: " + relative)
        stable[path] = raw
        proof[relative] = {"sha256": sha(raw), "bytes": len(raw), "git_source": freeze + ":" + relative}
    for path in (PURE / "mr3_observation.py", PURE / "mr3_episode.py",
                 Path(__file__).with_name("observation.py"), PURE / "mr3_observation_archive.py"):
        relative = path.relative_to(ROOT).as_posix()
        original = subprocess.check_output(["git", "show", NATIVE_FREEZE + ":" + relative], cwd=ROOT)
        if seed_rule == "legacy" or path.name != "mr3_observation.py":
            require(original == stable[path], "V21 observation/encoder source changed")
            proof[relative]["native_git_source"] = NATIVE_FREEZE + ":" + relative
        else:
            # This is a new scientific source version, not V21 byte identity.
            # Preserve the complete immutable original blob reference; current
            # default-legacy behavior is additionally checked on all six inputs.
            proof[relative]["legacy_reference"] = {"git_source": NATIVE_FREEZE + ":" + relative,
                "sha256": sha(original), "bytes": len(original)}
    return proof, stable


class NativeInputs:
    """Read only original-inventory-bound files; verify bytes again at verdict."""

    def __init__(self, root, inventory_path):
        self.root, self.inventory_path = Path(root).resolve(), Path(inventory_path).resolve()
        raw = self.inventory_path.read_bytes()
        self.inventory = parse(raw)
        require(self.inventory.get("schema") == "mr3-closed-byte-inventory-v1", "wrong native inventory")
        require(Path(self.inventory["original_root"]).resolve() == self.root, "native root differs from original inventory")
        self.stable = {self.inventory_path: raw}
        self.proofs = {}

    def read(self, relative):
        relative = Path(relative).as_posix()
        path = self.root / relative
        require(not Path(relative).is_absolute() and path.resolve().is_relative_to(self.root), "native path escaped root")
        raw = path.read_bytes()
        expected = self.inventory["files"][relative]
        require(len(raw) == expected["bytes"] and sha(raw) == expected["sha256"], "closed native bytes differ: " + relative)
        require(self.stable.setdefault(path, raw) == raw, "native file changed between reads")
        self.proofs[relative] = {"path": str(path), "sha256": sha(raw), "bytes": len(raw),
                                 "inventory_relative_path": relative}
        return raw

    def verify(self):
        require(all(path.read_bytes() == raw for path, raw in self.stable.items()), "native input bytes changed before verdict")


def selected_rows(raw):
    lines = raw.splitlines()
    require(len(lines) == 33, "V21 must retain reset and all 32 returned steps")
    result = [(1, parse(lines[0])), (2, parse(lines[1])), (33, parse(lines[-1]))]
    require([row["kind"] for _, row in result] == ["reset", "step", "step"], "native selection kinds changed")
    require(result[-1][1]["truncated"] is True and result[-1][1]["terminated"] is False
            and result[-1][1]["info"]["reason"] == "external_sampler_limit", "V21 last step did not close externally")
    return result


def grid_from_payload(payload):
    info = payload["info"]
    grid = np.asarray(payload["data"])
    require(grid.ndim == 1 and grid.size == info["height"] * info["width"]
            and grid.dtype.kind in "iu" and np.all((grid >= -1) & (grid <= 100)), "bad archived occupancy grid")
    orientation = info["origin"]["orientation"]
    require(all(orientation[axis] == 0 for axis in ("x", "y", "z"))
            and abs(orientation["w"]) == 1, "rotated archived map")
    return {"grid": grid.astype(np.int16).reshape(info["height"], info["width"]),
            "resolution": info["resolution"],
            "origin": [info["origin"]["position"][axis] for axis in ("x", "y")]}


def recover_parameters(inputs, episode, row):
    """Recover the recorded snapshot's sufficient received-only builder inputs."""
    snapshot = row["snapshot"]
    archive = Path(episode) / "observation_inputs"
    manifest_name = archive / "snapshots" / f"{snapshot['sequence']:08d}_{snapshot['digest']}.json"
    manifest = parse(inputs.read(manifest_name))
    require(manifest.get("schema") == "mr3-observation-input-archive-v2"
            and manifest.get("scope") == "encoder_result_before_publication", "not the native navigation archive")
    require(all(manifest[key] == snapshot[key] for key in ("epoch", "sequence", "candidate_version", "source_stamp"))
            and manifest["snapshot_digest"] == snapshot["digest"], "native archive/snapshot identity differs")
    metadata = manifest["metadata"]
    require(metadata["navigation_composition"]["version"] == COMPOSITION
            and metadata["navigation_sources"] == snapshot["navigation_sources"]
            and metadata["map_sources"] == snapshot["map"]["sources"]
            and metadata["map_version"] == snapshot["map_version"], "native received source metadata differs")
    require(set(manifest["maps"]) == {"fused", *ROBOTS, *("navigation:" + name for name in ROBOTS)},
            "native archive omitted a received map role")
    payloads = {}
    for role, entry in manifest["maps"].items():
        digest = entry["payload_sha256"]
        require(re.fullmatch(r"[0-9a-f]{64}", digest) and entry["artifact"] == f"maps/{digest}.json.gz", "bad native map reference")
        raw = gzip.decompress(inputs.read(archive / entry["artifact"]))
        payload = parse(raw)
        require(canonical(payload) == raw and sha(raw) == digest, "native content addressed map differs")
        expected = (metadata["map_payload_sha256"] if role == "fused" else
                    metadata["navigation_sources"][role.split(":")[1]]["payload_sha256"]
                    if role.startswith("navigation:") else metadata["map_sources"][role]["payload_sha256"])
        require(expected == digest, "native map role changed source")
        payloads[role] = payload
    fused = grid_from_payload(payloads["fused"])
    own, navigation = {}, {}
    for name in ROBOTS:
        own[name] = {**grid_from_payload(payloads[name]), "epoch": snapshot["epoch"], **metadata["map_sources"][name]}
        navigation[name] = {**grid_from_payload(payloads["navigation:" + name]), "epoch": snapshot["epoch"],
                            **metadata["navigation_sources"][name]}
    robots = copy.deepcopy(snapshot["robots"])
    for robot in robots:
        if robot["navigation"]["missing"]:
            robot["navigation"] = {}
        else:
            robot["navigation"]["sequence"] = robot["navigation"]["receipt_sequence"]
    task_start_ns = round(snapshot["source_stamp"] * 1e9) - round(snapshot["task_elapsed_sec"] * 1e9)
    params = {"raw_grid": fused["grid"], "resolution": fused["resolution"], "origin": fused["origin"],
        "robots": robots, "now": snapshot["source_stamp"], "epoch": snapshot["epoch"],
        "map_version": snapshot["map_version"], "sequence": snapshot["sequence"],
        "map_source_stamp": metadata["map_source_stamp"], "map_received_stamp": metadata["map_received_stamp"],
        "map_sources": metadata["map_sources"], "task_start": task_start_ns / 1e9,
        "robot_maps": own, "navigation_maps": navigation}
    return params, manifest_name.as_posix()


def replay_native(inputs, builder):
    records = []
    for number in (1, 2):
        episode = f"worker0/episode{number:03d}_open_101"
        metadata = parse(inputs.read(Path(episode) / "metadata.json"))
        require(metadata["freeze"] == NATIVE_FREEZE and metadata["safety_contract"] == "mr3-reach-v1", "native source identity differs")
        transition_path = Path(episode) / "transitions.jsonl"
        raw = inputs.read(transition_path)
        for label, (line, row) in zip(("reset", "first_step", "last_step"), selected_rows(raw)):
            params, manifest = recover_parameters(inputs, episode, row)
            rebuilt = builder(**params)
            expected = {"snapshot_canonical_sha256": sha(canonical(row["snapshot"])), "tensor_proofs": tensor_proofs(row["snapshot"])}
            actual = {"snapshot_canonical_sha256": sha(canonical(rebuilt)), "tensor_proofs": tensor_proofs(rebuilt)}
            records.append({"episode": episode, "selection": label, "native_freeze": metadata["freeze"],
                "native_snapshot_ref": {**inputs.proofs[transition_path.as_posix()], "line_1based": line,
                                         "line_sha256": sha(raw.splitlines()[line - 1])},
                "manifest_ref": inputs.proofs[manifest], "expected": expected, "actual": actual,
                "candidate_mask_full_snapshot_equal": canonical(rebuilt) == canonical(row["snapshot"]),
                "sufficient_parameter_sha256": sha(canonical(encode_arrays(params))),
                "robot_recovery_scope": "saved normalized sufficient fields; navigation receipt_sequence/missing inverted; not unrecorded raw input"})
    return records


def replay_exact_native(inputs, builder, directory, stable=None):
    """New-version calls from the same sufficient received inputs, not native runs."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "inputs").mkdir()
    records = []
    for number in (1, 2):
        episode = f"worker0/episode{number:03d}_open_101"
        raw = inputs.read(Path(episode) / "transitions.jsonl")
        for selection, (_, original) in zip(("reset", "first_step", "last_step"), selected_rows(raw)):
            params, _ = recover_parameters(inputs, episode, original)
            legacy_parameters_sha256 = sha(canonical(encode_arrays(params)))
            params["seed_rule"] = EXACT_SEED_RULE
            encoded = canonical(encode_arrays(params))
            digest = sha(encoded)
            input_path = directory / f"inputs/{digest}.json.gz"
            if not input_path.exists():
                with input_path.open("xb") as stream:
                    stream.write(gzip.compress(encoded, mtime=0))
            if stable is not None:
                stable[input_path] = input_path.read_bytes()
            snapshot = builder(**params)
            row = {"epoch": params["epoch"], "snapshot": snapshot, "tensor_proofs": tensor_proofs(snapshot),
                   "actor_input_ref": {"path": str(input_path.relative_to(directory)), "sha256": digest}}
            # Same input/reference format as prospective actor traces. Do not
            # claim the changed candidates are equal to the old native ones.
            checked, _ = actor_record(directory, row, builder=builder)
            record_path = directory / f"episode{number}_{selection}.json"
            body = canonical(row)
            with record_path.open("xb") as stream:
                stream.write(body)
            if stable is not None:
                stable[record_path] = body
            records.append({"episode": episode, "selection": selection, "seed_rule": EXACT_SEED_RULE,
                "native_freeze": NATIVE_FREEZE, "legacy_parameters_sha256": legacy_parameters_sha256,
                "sufficient_parameter_sha256": digest,
                "actor_record_ref": {"path": str(record_path), "sha256": sha(body), "bytes": len(body)},
                "actual": {"snapshot_canonical_sha256": sha(canonical(snapshot)), "tensor_proofs": row["tensor_proofs"]},
                "exact_seed_robot_checks": checked["exact_seed_robot_checks"],
                "scope": "current-version reconstruction of original sufficient received inputs; not native execution/equivalence"})
    return records


@contextmanager
def pure_package():
    """System helper only; load pure ROS-package modules without ROS paths."""
    previous = {k: v for k, v in sys.modules.items() if k == "multi_robot_exploration" or k.startswith("multi_robot_exploration.")}
    package = ModuleType("multi_robot_exploration"); package.__path__ = [str(PURE)]
    for key in previous:
        del sys.modules[key]
    sys.modules[package.__name__] = package
    try:
        yield
    finally:
        for key in list(sys.modules):
            if key == package.__name__ or key.startswith(package.__name__ + "."):
                del sys.modules[key]
        sys.modules.update(previous)


def write_artifact(path, value):
    raw = canonical(encode_arrays(value))
    with Path(path).open("xb") as stream:
        stream.write(raw)
    return {"path": str(Path(path).resolve()), "sha256": sha(raw), "bytes": len(raw)}


def file_ref(path):
    path = Path(path).resolve(); raw = path.read_bytes()
    return {"path": str(path), "sha256": sha(raw), "bytes": len(raw)}


def asset_refs(assets):
    return [file_ref(Path(assets) / name) for name in (
        "worlds/p1c_open.world", "config/mr3_p1a/open.json", "models/turtlebot3_waffle/model.sdf")]


def synthetic_assets(directory, *, hidden=False):
    assets = Path(directory); native = PURE.parents[1] / "multi_robot"
    (assets / "worlds").mkdir(parents=True)
    (assets / "config/mr3_p1a").mkdir(parents=True)
    (assets / "models/turtlebot3_waffle").mkdir(parents=True)
    shutil.copyfile(native / "models/turtlebot3_waffle/model.sdf", assets / "models/turtlebot3_waffle/model.sdf")
    boxes = [(-2.95, 0., .1, 6.), (2.95, 0., .1, 6.), (0., -2.95, 6., .1), (0., 2.95, 6., .1), (1.5, 0., .1, 5.8)]
    if hidden:
        boxes.append((2., 0., .2, .2))
    text = ["<sdf version='1.7'><world name='synthetic'><model name='walls'><static>true</static><link name='walls'>"]
    for index, (x, y, sx, sy) in enumerate(boxes):
        text.append(f"<collision name='c{index}'><pose>{x} {y} .5 0 0 0</pose><geometry><box><size>{sx} {sy} 1</size></box></geometry></collision>")
    text.append("</link></model></world></sdf>"); raw = "".join(text).encode()
    (assets / "worlds/p1c_open.world").write_bytes(raw)
    contract = parse((native / "config/mr3_p1a/open.json").read_bytes())
    contract["world_sha256"] = sha(raw); contract["roi"]["bounds"] = [-3., -3., 3., 3.]
    (assets / "config/mr3_p1a/open.json").write_bytes(canonical(contract))
    return assets


def received_parameters(world):
    """Build synthetic actor inputs only from actual local sensor deliveries."""
    from multi_robot_exploration.mr3_transport import IdealTransport, ReceivedStore
    now, epoch = world.time_ns / 1e9, "synthetic-conformity"
    transport, store = IdealTransport(epoch), ReceivedStore(epoch)
    for name, sample in world.own_sensors().items():
        robot = {**sample["odom"], "name": name, "epoch": epoch, "valid": True,
                 "sequence": 1, "version": 1, "odom_source_stamp": now, "tf_source_stamp": now,
                 "tf_validity_stamp": now, "tf_validity_lead_sec": 0.,
                 "navigation": {"phase": "idle", "source_stamp": now, "received_stamp": now,
                                "sequence": 1, "accepted_goal_count": 0}, "history": [], "activity": None}
        transport.send("state", name, robot, source_stamp=now, now=now)
        item = world.map_record(name)
        payload = {**item, "grid": item["grid"].tolist(), "origin": list(item["origin"])}
        transport.send("map", name, payload, source_stamp=item["source_stamp"], now=now)
    transport.deliver(store, now, sampled=True)
    robots, own, map_sources = [], {}, {}
    for name in ROBOTS:
        state, map_ = store.get("state", name), store.get("map", name)
        robots.append({**state.payload, "received_stamp": state.received_stamp})
        item = map_.payload
        own[name] = {**item, "grid": np.asarray(item["grid"], dtype=np.int16), "epoch": epoch,
                     "sequence": map_.sequence, "version": map_.version, "received_stamp": map_.received_stamp,
                     "payload_sha256": sha(canonical(item))}
        map_sources[name] = {k: own[name][k] for k in ("source_stamp", "received_stamp", "sequence", "version", "payload_sha256")}
    fused = np.maximum.reduce([own[name]["grid"] for name in ROBOTS])
    shared_sha = sha(fused.tobytes()); navigation = {}
    for name in ROBOTS:
        grid = np.where(own[name]["grid"] >= 0, own[name]["grid"], fused).astype(np.int16)
        navigation[name] = {"grid": grid, "resolution": world.resolution, "origin": world.origin,
            "epoch": epoch, "sequence": 1, "version": 1, "source_stamp": now, "received_stamp": now,
            "composition_version": COMPOSITION, "payload_sha256": sha(grid.tobytes()),
            "input_own_map_payload_sha256": map_sources[name]["payload_sha256"],
            "input_shared_map_payload_sha256": shared_sha, "input_own_source_stamp": now,
            "received_stamp_scope": "synthetic_delivered_shared_map", "shared_map_version": 1}
    return {"raw_grid": fused, "resolution": world.resolution, "origin": world.origin,
            "robots": robots, "now": now, "epoch": epoch, "map_version": 1, "sequence": 1,
            "map_source_stamp": now, "map_received_stamp": now, "map_sources": map_sources,
            "task_start": now, "robot_maps": own, "navigation_maps": navigation}


def convergence_metrics(first, second, stopped_before, stopped_after):
    pose_error = max(math.hypot(first["poses"][n]["x"] - second["poses"][n]["x"],
                                first["poses"][n]["y"] - second["poses"][n]["y"]) for n in ROBOTS)
    return {"pose_error_m": pose_error,
        "yaw_error_rad": max(abs(first["poses"][n]["yaw"] - second["poses"][n]["yaw"]) for n in ROBOTS),
        "path_error_m": max(abs(first["path_lengths"][n] - second["path_lengths"][n]) for n in ROBOTS),
        "collision_count_difference": abs(first["collision_events"] - second["collision_events"]),
        "stop_displacement_m": max(math.hypot(stopped_before["poses"][n]["x"] - stopped_after["poses"][n]["x"],
                                               stopped_before["poses"][n]["y"] - stopped_after["poses"][n]["y"]) for n in ROBOTS)}


def synthetic_cases(directory, seed_rule="legacy"):
    require(seed_rule in ("legacy", EXACT_SEED_RULE), "unknown synthetic seed rule")
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
    with pure_package():
        world_module = importlib.import_module("multi_robot_exploration.mr3_proxy2d_world")
        reward_module = importlib.import_module("multi_robot_exploration.mr3_reward")
        build = importlib.import_module("multi_robot_exploration.mr3_observation").build_snapshot
        assets = synthetic_assets(directory / "box")
        worlds = [world_module.ProxyWorld("open", 17, dt, asset_root=assets) for dt in (.02, .01)]
        for command in ((.2, 0.), (0., .8), (0., 0.)):
            for world, count in zip(worlds, (5, 10)):
                world.apply_commands({name: command if name == "tb1" else (0., 0.) for name in ROBOTS})
                for _ in range(count):
                    world.advance()
        states = [world.evaluation_state() for world in worlds]
        before = worlds[0].evaluation_state(); worlds[0].advance(); after = worlds[0].evaluation_state()
        metrics = convergence_metrics(*states, before, after)
        bounds = {"pose_error_m": 1e-10, "yaw_error_rad": 1e-10, "path_error_m": 1e-10,
                  "collision_count_difference": 0, "stop_displacement_m": 0}
        refs = [write_artifact(directory / "convergence_inputs.json", {"quantums": [.02, .01], "commands": [[.2, 0.], [0., .8], [0., 0.]],
                                                                    "duration_each_sec": .1}),
                write_artifact(directory / "convergence_states.json", {"first": states[0], "second": states[1], "stop_before": before, "stop_after": after})]
        refs.extend(asset_refs(assets))
        cases = [{"id": "forward_turn_stop_halved_integration", "comparison": "upper_bounds", "expected": bounds,
                  "actual": metrics, "input_refs": refs}]
        hidden_assets = synthetic_assets(directory / "hidden_box", hidden=True)
        pair = [world_module.ProxyWorld("open", 41, asset_root=item) for item in (assets, hidden_assets)]
        for world in pair:
            for _ in range(5): world.advance()
        parameters = [received_parameters(world) for world in pair]
        if seed_rule != "legacy":
            for params in parameters:
                params["seed_rule"] = seed_rule
        snapshots = [build(**params) for params in parameters]
        hashes = [{"actor_parameters_sha256": sha(canonical(encode_arrays(params))),
                   "snapshot_sha256": sha(canonical(snapshot))} for params, snapshot in zip(parameters, snapshots)]
        refs = [write_artifact(directory / f"hidden_actor_{index}.json", {"parameters": params, "snapshot": snapshot})
                for index, (params, snapshot) in enumerate(zip(parameters, snapshots))]
        refs.extend(asset_refs(assets) + asset_refs(hidden_assets))
        cases.append({"id": "hidden_obstacle_same_received_actor", "comparison": "equal", "expected": hashes[0], "actual": hashes[1], "input_refs": refs})
        actor_before = copy.deepcopy(parameters[0])
        free = np.ones((2, 2), dtype=bool); perturbed = free.copy(); perturbed[1, 1] = False
        correct = np.zeros((2, 2), dtype=bool); correct[0, 0] = True
        rewards = []
        for truth in (free, perturbed):
            ledger = reward_module.RewardLedger("isolated", 0., truth, np.zeros((2, 2), dtype=bool))
            rewards.append(ledger.advance(epoch="isolated", sequence=1, step_start=0., step_end=1.,
                current_correct_free_mask=correct, collision_events=0, goal_switches=0, rejected_actions=0)["reward"])
        snapshot_after = build(**parameters[0])
        weights = reward_module.RewardWeights()
        expected = {"actor_parameters_sha256": sha(canonical(encode_arrays(actor_before))),
                    "snapshot_sha256": sha(canonical(snapshots[0])),
                    "rewards": [weights.coverage / 4. - weights.time / 300., weights.coverage / 3. - weights.time / 300.]}
        actual = {"actor_parameters_sha256": sha(canonical(encode_arrays(parameters[0]))),
                  "snapshot_sha256": sha(canonical(snapshot_after)), "rewards": rewards}
        refs = [write_artifact(directory / "reward_truth_inputs.json", {"truth_free": [free, perturbed], "correct": correct,
            "initial_correct": np.zeros((2, 2), dtype=bool), "epoch": "isolated", "sequence": 1,
            "start_sim_time": 0., "step_start": 0., "step_end": 1., "collision_events": 0,
            "goal_switches": 0, "rejected_actions": 0, "terminal_reason": None, "external_truncation": None,
            "actor_before": actor_before, "actor_after": parameters[0], "snapshot_before": snapshots[0], "snapshot_after": snapshot_after})]
        cases.append({"id": "reward_truth_only_reward_branch", "comparison": "equal", "expected": expected, "actual": actual, "input_refs": refs})
    for case in cases:
        case["passed"] = (case["expected"] == case["actual"] if case["comparison"] == "equal"
                          else set(case["actual"]) == set(case["expected"]) and all(case["actual"][k] <= limit for k, limit in case["expected"].items()))
    return {"schema": "mr3-proxy2d-synthetic-conformity-v1", "cases": cases,
            "passed": all(case["passed"] for case in cases), "native_runs": 0, "optimizer_steps": 0, "gpu_calls": 0,
            "seed_rule": seed_rule}


def process_identity(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": pid, "parent": int(fields[1]), "start_ticks": int(fields[19])}


def run_synthetic_helper(freeze, output, result):
    """Keep an actual wait receipt on success, helper error or caller exception."""
    helper_output = output.with_name(output.stem + "_synthetic.json")
    require(not helper_output.exists(), "synthetic output exists")
    environment = os.environ.copy(); environment.pop("PYTHONPATH", None)
    environment.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="")
    argv = ["/usr/bin/python3", "-B", "-m", "mr3_learning.proxy2d_conformity", "--synthetic-cases",
            "--freeze", freeze, "--output", str(helper_output)]
    if result.get("seed_rule", "legacy") != "legacy":
        argv += ["--seed-rule", result["seed_rule"]]
    receipt = {"argv": argv, "cwd": str(WIRELESS), "started_monotonic_ns": time.monotonic_ns(),
               "actual_waited": False, "termination_requested": False, "kill_requested": False}
    child = None
    try:
        with output.with_suffix(".synthetic.log").open("xb") as console:
            child = subprocess.Popen(argv, cwd=WIRELESS, env=environment, stdout=console, stderr=subprocess.STDOUT)
            receipt["child_identity"] = process_identity(child.pid)
            child.wait(timeout=120.)
    finally:
        if child is not None:
            if child.poll() is None:
                receipt["termination_requested"] = True
                child.terminate()
                try:
                    child.wait(timeout=5.)
                except subprocess.TimeoutExpired:
                    receipt["kill_requested"] = True
                    child.kill(); child.wait()
            child.wait()
            receipt.update(returncode=child.returncode, actual_waited=True)
        receipt["ended_monotonic_ns"] = time.monotonic_ns()
        result["synthetic_actual_wait"] = receipt
    require(receipt["returncode"] == 0, "synthetic conformity helper failed")
    raw = helper_output.read_bytes()
    result["synthetic_result_ref"] = {"path": str(helper_output), "sha256": sha(raw), "bytes": len(raw)}
    synthetic = parse(raw)
    require(synthetic.get("schema") == "mr3-proxy2d-synthetic-conformity-v1"
            and synthetic.get("freeze") == freeze, "synthetic helper source identity differs")
    return synthetic["cases"]


def run(freeze, native_root, inventory_path, output, seed_rule="legacy"):
    output = Path(output).resolve(); require(not output.exists(), "exclusive conformity output required")
    proof, stable = source_bindings(freeze, seed_rule)
    inventory_raw = Path(inventory_path).read_bytes()
    relative_inventory = Path(inventory_path).resolve().relative_to(ROOT).as_posix()
    require(subprocess.check_output(["git", "show", freeze + ":" + relative_inventory], cwd=ROOT) == inventory_raw,
            "original native inventory is not frozen")
    inputs = NativeInputs(native_root, inventory_path)
    result = {"schema": "mr3-proxy2d-conformity-v2" if seed_rule == EXACT_SEED_RULE else "mr3-proxy2d-conformity-v1",
              "freeze": freeze, "native_freeze": NATIVE_FREEZE,
              "passed": False, "errors": [], "source_proof": proof, "native_records": [],
              "qualification": False, "training_eligible": False, "native_credit": False,
              "native_inventory": {"path": str(Path(inventory_path).resolve()), "sha256": sha(inventory_raw), "bytes": len(inventory_raw)}}
    if seed_rule != "legacy":
        result.update(seed_rule=seed_rule, exact_records=[],
            native_reference_scope="original V21 closed inputs and snapshots; current legacy compatibility only",
            exact_scope="new source-version received-input reconstruction; no new native execution/equivalence")
    try:
        builder = PureBuilder()
        try:
            result["native_records"] = replay_native(inputs, builder)
            if seed_rule != "legacy":
                result["exact_records"] = replay_exact_native(inputs, builder, output.with_suffix(".exact"), stable)
        finally:
            result["pure_builder_actual_wait"] = builder.close()
        result["synthetic_cases"] = run_synthetic_helper(freeze, output, result)
        require(len(result["native_records"]) == 6 and all(row["expected"] == row["actual"]
                and row["candidate_mask_full_snapshot_equal"] for row in result["native_records"]), "native six-input full snapshot/tensor replay differs")
        require(all(case["passed"] for case in result["synthetic_cases"]), "synthetic isolation/convergence differs")
        if seed_rule != "legacy":
            require(len(result["exact_records"]) == 6
                    and all(row["exact_seed_robot_checks"] == 3 for row in result["exact_records"]),
                    "exact six-input seed verification is incomplete")
    except ERRORS as error:
        result["errors"].append(str(error))
    try:
        inputs.verify(); require(all(path.read_bytes() == raw for path, raw in stable.items()), "conformity source bytes changed")
        result["input_bytes_unchanged"] = True
    except ERRORS as error:
        result["errors"].append(str(error)); result["input_bytes_unchanged"] = False
    result["native_input_index"] = inputs.proofs
    result["passed"] = not result["errors"]
    with output.open("x") as stream: json.dump(result, stream, indent=2, allow_nan=False); stream.write("\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--native-root", type=Path, default=DEFAULT_NATIVE_ROOT)
    parser.add_argument("--native-inventory", type=Path, default=NATIVE_ASSETS / "native_inventory_v1.json")
    parser.add_argument("--synthetic-cases", action="store_true")
    parser.add_argument("--seed-rule", choices=("legacy", EXACT_SEED_RULE), default="legacy")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    require(not args.output.exists(), "exclusive conformity output required")
    if args.synthetic_cases:
        proof, stable = source_bindings(args.freeze, args.seed_rule)
        result = synthetic_cases(args.output.with_suffix(".inputs"), args.seed_rule)
        require(all(path.read_bytes() == raw for path, raw in stable.items()), "synthetic source changed")
        result.update(source_proof=proof, freeze=args.freeze)
        with args.output.open("x") as stream: json.dump(result, stream, indent=2, allow_nan=False); stream.write("\n")
    else:
        result = run(args.freeze, args.native_root, args.native_inventory, args.output, args.seed_rule)
    print(json.dumps({"passed": result["passed"], "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
