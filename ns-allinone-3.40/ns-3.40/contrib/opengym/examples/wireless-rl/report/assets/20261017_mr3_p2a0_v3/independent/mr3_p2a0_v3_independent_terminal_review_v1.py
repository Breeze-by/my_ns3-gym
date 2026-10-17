"""Independent read-only exact received-map replay of P2A.0 native evidence."""

import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path("/home/zhuyulab/ns3-workspace")
RUN = ROOT / "ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v3_terminal"
FREEZE = "f9312e1ed245fb93af50614fd34c960870edb78d"
COMPONENT = ROOT / ("ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/"
                    "multi_robot_exploration")
OUTPUT = Path("/tmp/mr3_p2a0_v3_independent_terminal_review_v1.json")
assert not OUTPUT.exists()
inputs = {}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    raw = path.read_bytes()
    inputs[str(path)] = {"bytes": len(raw), "sha256": sha(raw)}
    return raw


def load(path):
    return json.loads(read(path))


def rows(path):
    raw = read(path)
    assert not raw or raw.endswith(b"\n"), "partial native JSONL: " + str(path)
    return [json.loads(line) for line in raw.splitlines()]


def payload_grid(payload):
    info = payload["info"]
    return np.asarray(payload["data"], dtype=np.int16).reshape(info["height"], info["width"])


def origin(payload):
    return tuple(payload["info"]["origin"]["position"][axis] for axis in ("x", "y"))


source_proof = {}
for name in ("mr3_observation.py", "mr3_episode.py", "mr3_observation_archive.py", "mr3_adapter.py",
             "mr3_information.py", "mr3_activity.py"):
    path = COMPONENT / name
    frozen = subprocess.check_output(["git", "show", FREEZE + ":" + str(path.relative_to(ROOT))],
                                     cwd=ROOT)
    assert frozen == read(path), "current source differs from native freeze: " + name
    source_proof[name] = {"freeze": FREEZE, "sha256": sha(frozen)}
sys.path.insert(0, str(COMPONENT.parent))
from multi_robot_exploration import mr3_observation as m  # noqa: E402
WIRELESS = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
for relative in ("mr3_learning/navigation_archive.py", "mr3_learning/audit_activity.py"):
    path = WIRELESS / relative
    frozen = subprocess.check_output(["git", "show", FREEZE + ":" + str(path.relative_to(ROOT))],
                                     cwd=ROOT)
    assert frozen == read(path)
    source_proof[relative] = {"freeze": FREEZE, "sha256": sha(frozen)}
sys.path.insert(0, str(WIRELESS))
from mr3_learning.navigation_archive import reconstruct_navigation_payload  # noqa: E402
from mr3_learning.audit_activity import audit_episode as audit_activity  # noqa: E402

benchmark = load(RUN / "benchmark_summary.json")
assert benchmark["freeze"] == FREEZE
episodes = []
short_steps, zero_tails, replay_count = 0, 0, 0
for metadata_path in sorted(RUN.glob("worker*/episode*/metadata.json")):
    episode = metadata_path.parent
    metadata = load(metadata_path)
    assert metadata["freeze"] == FREEZE
    transitions = rows(episode / "transitions.jsonl")
    audit = rows(episode / "adapter.jsonl")
    starts = [entry["payload"]["start_sim_time_sec"] for entry in audit if entry["kind"] == "task_start"]
    assert len(starts) == 1
    archive = episode / "observation_inputs"
    snapshot_dir = archive / "snapshots"
    unique, referenced, zero_tail_rows, short_rows = {}, set(), [], []
    previous = None
    for index, transition in enumerate(transitions):
        snapshot = transition["snapshot"]
        info = transition["info"]
        assert snapshot["epoch"] == metadata["epoch"]
        assert m.snapshot_digest(snapshot) == snapshot["digest"]
        manifest_path = snapshot_dir / f"{snapshot['sequence']:08d}_{snapshot['digest']}.json"
        manifest = load(manifest_path)
        assert manifest["schema"] == "mr3-observation-input-archive-v2"
        assert manifest["scope"] == "encoder_result_before_publication"
        for key in ("epoch", "sequence", "candidate_version", "source_stamp"):
            assert manifest[key] == snapshot[key]
        assert manifest["snapshot_digest"] == snapshot["digest"]
        bundle = manifest["metadata"]
        assert bundle["epoch"] == snapshot["epoch"]
        assert bundle["map_version"] == snapshot["map_version"] == info["watermarks"]["map_version"]
        assert bundle["map_sources"] == snapshot["map"]["sources"] == info["watermarks"]["map_sources"]
        assert bundle["map_source_stamp"] == snapshot["map"]["source_stamp"]
        assert bundle["map_received_stamp"] == snapshot["map"]["received_stamp"]
        assert bundle["map_payload_sha256"] == info["watermarks"]["map_payload_sha256"]
        assert set(manifest["maps"]) == {"fused", *m.ROBOT_NAMES,
                                          *("navigation:" + name for name in m.ROBOT_NAMES)}
        assert bundle["navigation_sources"] == snapshot["navigation_sources"] == info[
            "watermarks"]["navigation_sources"]
        assert bundle["navigation_composition"] == {"version": m.NAVIGATION_COMPOSITION_VERSION}
        payloads = {}
        for name, binding in manifest["maps"].items():
            expected = (bundle["map_payload_sha256"] if name == "fused" else
                        bundle["navigation_sources"][name.split(":", 1)[1]]["payload_sha256"]
                        if name.startswith("navigation:") else
                        bundle["map_sources"][name]["payload_sha256"])
            assert binding == {"payload_sha256": expected, "artifact": f"maps/{expected}.json.gz"}
            path = archive / binding["artifact"]
            decoded = gzip.decompress(read(path))
            assert sha(decoded) == expected
            payloads[name] = json.loads(decoded)
            canonical = json.dumps(payloads[name], sort_keys=True, separators=(",", ":"),
                                   allow_nan=False).encode()
            assert decoded == canonical
            if name == "fused" or name.startswith("navigation:"):
                shape = payload_grid(payloads[name]).shape
                geometry = (snapshot["map"] if name == "fused" else
                            snapshot["path_maps"][name.split(":", 1)[1]])
                assert list(shape) == geometry["native_shape"]
                assert payloads[name]["info"]["resolution"] == geometry["native_resolution_m"]
                assert list(origin(payloads[name])) == geometry["native_origin_m"]
                if name != "fused":
                    assert geometry["payload_sha256"] == expected
            referenced.add(path)
        for name in m.ROBOT_NAMES:
            source = bundle["navigation_sources"][name]
            assert source["input_own_map_payload_sha256"] == bundle["map_sources"][name]["payload_sha256"]
            assert source["input_shared_map_payload_sha256"] == bundle["map_payload_sha256"]
            assert source["composition_version"] == m.NAVIGATION_COMPOSITION_VERSION
            rebuilt = reconstruct_navigation_payload(payloads[name], payloads["fused"])
            assert rebuilt == payloads["navigation:" + name]
            assert sha(json.dumps(rebuilt, allow_nan=False, sort_keys=True,
                                  separators=(",", ":")).encode()) == source["payload_sha256"]
        if snapshot["digest"] not in unique:
            robots = copy.deepcopy(snapshot["robots"])
            for robot in robots:
                robot["navigation"]["sequence"] = robot["navigation"]["receipt_sequence"]
            maps = {name: {
                "grid": payload_grid(payloads[name]),
                "resolution": payloads[name]["info"]["resolution"],
                "origin": origin(payloads[name]), "epoch": snapshot["epoch"],
                **bundle["map_sources"][name],
            } for name in m.ROBOT_NAMES}
            navigation_maps = {name: {
                "grid": payload_grid(payloads["navigation:" + name]),
                "resolution": payloads["navigation:" + name]["info"]["resolution"],
                "origin": origin(payloads["navigation:" + name]),
                **bundle["navigation_sources"][name],
            } for name in m.ROBOT_NAMES}
            replay = m.build_snapshot(
                payload_grid(payloads["fused"]), payloads["fused"]["info"]["resolution"],
                origin(payloads["fused"]), robots, snapshot["source_stamp"], snapshot["epoch"],
                snapshot["map_version"], snapshot["sequence"],
                map_source_stamp=bundle["map_source_stamp"],
                map_received_stamp=bundle["map_received_stamp"],
                map_sources=bundle["map_sources"], task_start=starts[0], robot_maps=maps,
                navigation_maps=navigation_maps)
            assert replay == snapshot, "full received-map replay mismatch: " + str(manifest_path)
            unique[snapshot["digest"]] = snapshot["sequence"]
            replay_count += 1
        if transition["kind"] == "step":
            dt = info["dt"]
            if dt == 0:
                assert transition["terminated"] and not transition["truncated"]
                assert info["action_submitted"] is False and info["command"] is None
                assert info["physical_dt"] == 0 and info["terminal_observation_reused"] is True
                assert snapshot == previous
                zero_tails += 1
                zero_tail_rows.append(index)
            elif dt < 1:
                assert dt == info["physical_dt"] == .02
                assert transition["terminated"] and info.get("action_submitted", True)
                short_steps += 1
                short_rows.append(index)
        previous = snapshot
    manifests = sorted(snapshot_dir.glob("*.json"))
    assert len(manifests) == len(unique)
    assert len(set(unique.values())) == len(unique)
    assert set((archive / "maps").glob("*.json.gz")) == referenced
    published = [entry["payload"] for entry in audit if entry["kind"] == "observation"]
    assert len(published) == len(unique)
    assert {value["digest"] for value in published} == set(unique)
    assert all(value in [row["snapshot"] for row in transitions] for value in published)
    completed = [entry["payload"] for entry in audit if entry["kind"] == "snapshot_completed"]
    assert len(completed) == len(unique)
    assert all(entry["ok"] for entry in completed)
    activity_proof = audit_activity(episode)
    assert activity_proof["passed"]
    for path in (episode / "adapter.jsonl", episode / "transitions.jsonl"):
        read(path)
    episodes.append({"directory": str(episode), "epoch": metadata["epoch"],
                     "activity_independent_replay": activity_proof,
                     "actual_navigation_maps_reconstructed_independently": True,
                     "received_activity_observation": {name: {
                         "final_snapshot": published[-1]["robots"][index]["activity"],
                         "snapshots_non_null": sum(value["robots"][index]["activity"]["estimated_path_m"] is not None for value in published),
                         "snapshots_complete": sum(value["robots"][index]["activity"]["path_observation_complete"] for value in published),
                         "task_movement_credit": False,
                     } for index, name in enumerate(m.ROBOT_NAMES)},
                     "transition_rows": len(transitions), "unique_snapshots": len(unique),
                     "manifest_files": len(manifests), "unique_full_payloads": len(referenced),
                     "zero_tail_rows": zero_tail_rows, "short_20ms_terminal_rows": short_rows,
                     "no_extra_or_duplicate_manifest_or_blob": True,
                     "full_observation_replayed_exact": True})
assert len(episodes) == 2
assert short_steps == zero_tails == 1
assert "rclpy" not in sys.modules and "torch" not in sys.modules
script_raw = read(Path(__file__).resolve())
for path, binding in inputs.items():
    current = Path(path).read_bytes()
    assert len(current) == binding["bytes"] and sha(current) == binding["sha256"]
result = {
    "schema": "mr3-p2a0-v3-independent-native-map-archive-replay-v1", "passed": True,
    "freeze": FREEZE, "benchmark_passed": benchmark["passed"],
    "source_proof": source_proof, "inputs": inputs, "script_sha256": sha(script_raw),
    "exact_full_snapshot_replays": replay_count, "short_20ms_terminal_steps": short_steps,
    "zero_duration_reused_terminal_tails": zero_tails, "episodes": episodes,
    "jobs": {"ROS_messages": 0, "services": 0, "native_starts": 0, "process_signals": 0,
             "GPU": 0, "repository_writes": 0},
    "scope": "Independent seven-map/native-navigation NumPy provenance, full candidate/mask/raster/activity replay and terminal reuse",
    "limits": ["No policy efficacy, physical safety envelope, 95% success or multi-day stability claim.",
               "The benchmark's complete native/scalar/ACK gates are audited separately."],
}
with OUTPUT.open("x") as stream:
    stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
print(json.dumps({"passed": True, "output": str(OUTPUT), "sha256": sha(OUTPUT.read_bytes()),
                  "exact_full_snapshot_replays": replay_count, "episodes": episodes}, indent=2))
