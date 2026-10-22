"""DISABLED development computation on exactly the two preselected V35 inputs.

This does not replay an episode, actor, path, command, scan, reward or truth.
The two known failing-development frames are not an unbiased validation set.
All six received-map attachment results, including zero-anchor results, remain
visible. Computation closure is separate from attachment acceptance and gives
no production, native, task, freshness, tracking or training qualification.
"""
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import sys


ROOT = Path("/home/zhuyulab/ns3-workspace")
WIRELESS = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
PACKAGE = ROOT / "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration"
ASSETS = WIRELESS / "report/assets"
PRIMITIVE = ASSETS / "20261022_mr3_p2a_v36_point_graph/point_graph_v1.py"
CODEC = WIRELESS / "mr3_learning/proxy2d_codec.py"
REPORT = ASSETS / "20261022_mr3_p2a_v35_grid_liveness/closed_execution/rooms_forensic_v1.json"
EPISODE = ASSETS / ("20261022_mr3_p2a_v34_seed_v2/closed_execution/seed_probe_v2/"
                    "stages/group3/worker1/episode001_rooms_101")
REPORT_FREEZE = "47dd6774e478bb714e1844e0056f2301269896a3"
EVIDENCE_FREEZE = "7816cced7067c4505bd2874f0ad323cbb4fad85e"
RULE = "exact-point-bridge-v2"
PROFILE = "mr3-point-graph-attachment-3x3-disabled-v1"
SCHEMA = "mr3-v36-fixed-input-attachment-development-v1"
COMPOSITION = "mr3-own-known-shared-unknown-v1"
ROBOTS = ("tb1", "tb2", "tb3")
PARAMETERS = {"raw_grid", "resolution", "origin", "robots", "now", "epoch", "map_version",
              "sequence", "map_source_stamp", "map_received_stamp", "map_sources", "task_start",
              "robot_maps", "navigation_maps", "seed_rule"}
SOURCE_NAMES = ("mr3_observation.py", "mr3_seed_certificate.py", "mr3_episode.py")
EXPECTED_INPUTS = (
    {"event_sequence": 1, "event": "reset",
     "roles": ["reset", "first_tb3_seed_cell_body_clearance"],
     "canonical_sha256": "28bd8e9acd5e0dc4a8ab12d29772e694a3e6aea5f82d567b8cd9bf667bbfbe39",
     "compressed_sha256": "5cc346cf57f622372037f9984cb3f12e4bf7f9610ba8d08842586833d5224964",
     "canonical_bytes": 1090436},
    {"event_sequence": 129, "event": "step_return", "roles": ["last_actor"],
     "canonical_sha256": "a32e7a37903152610d6f9293967fa9d060932a6938c5e40e8e096c007a3e4274",
     "compressed_sha256": "00ad33db448020b92c6ea9cafa323e6b9d6e2c911e1acff45ce160b2b2d34727",
     "canonical_bytes": 1094741},
)
MAX_FILE_BYTES = 16_000_000
MAX_INPUT_BYTES = 8_000_000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_limited(path, limit=MAX_FILE_BYTES):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "file byte limit exceeded")
    return raw


def decompress_limited(raw):
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        result = stream.read(MAX_INPUT_BYTES + 1)
    require(len(result) <= MAX_INPUT_BYTES, "decompressed byte limit exceeded")
    return result


def identity():
    fields = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": os.getpid(), "parent": int(fields[1]), "group": int(fields[2]),
            "session": int(fields[3]), "start_ticks": int(fields[19])}


def load_file(name, path):
    path = Path(path).resolve(strict=True)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(Path(module.__file__).resolve() == path, "file import differs from canonical source")
    return module


def source_paths():
    return [Path(__file__).resolve(), PRIMITIVE, CODEC, *(PACKAGE / name for name in SOURCE_NAMES)]


def source_bindings():
    return {str(path): digest(read_limited(path)) for path in source_paths()}


def load_helpers():
    # No ad hoc sys.path/PYTHONPATH; the owning runner sources system ROS.
    primitive = load_file("mr3_v36_disabled_point_graph", PRIMITIVE)
    codec = load_file("mr3_v36_fixed_input_codec", CODEC)
    for filename in SOURCE_NAMES:
        name = "multi_robot_exploration." + filename.removesuffix(".py")
        module = sys.modules.get(name)
        require(module is not None and Path(module.__file__).resolve() == PACKAGE / filename,
                "pure helper resolved outside canonical source: " + name)
    require(primitive.PROFILE == PROFILE, "wrong disabled attachment profile")
    return primitive, codec


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_report(report, episode, expected_inputs):
    require(report.get("schema") == "mr3-v34-rooms-received-geometry-forensic-v1"
            and report.get("source_freeze") == REPORT_FREEZE
            and report.get("evidence_freeze") == EVIDENCE_FREEZE
            and report.get("source_stable") is True and not report.get("error"),
            "not the closed source-stable V35 forensic report")
    require(report.get("scene") == "rooms" and type(report.get("seed")) is int
            and report["seed"] == 101 and isinstance(report.get("epoch"), str)
            and bool(report["epoch"]), "wrong declared episode")
    actual, metadata = report.get("actual", {}), report.get("trace_metadata", {})
    require(actual == {"trace_events": 130, "selected_actors": 2, "decoded_actor_inputs": 2},
            "selection differs from the fixed two V35 inputs")
    require(metadata == {"epoch": report["epoch"], "env_id": 1, "episode_index": 1,
                         "scene": "rooms", "seed": 101, "evidence_freeze": EVIDENCE_FREEZE,
                         "first_event_sequence": 1, "last_event_sequence": 130},
            "V35 trace metadata differs")
    records = report.get("records")
    require(isinstance(records, list) and len(records) == len(expected_inputs) == 2,
            "exactly two fixed frames required")
    paths = []
    for record, expected in zip(records, expected_inputs):
        require(record.get("event_sequence") == expected["event_sequence"]
                and record.get("trace_line_1based") == expected["event_sequence"]
                and record.get("event") == expected["event"]
                and record.get("roles") == expected["roles"], "fixed selection identity differs")
        reference = record.get("actor_input_ref", {})
        path = episode / "inputs" / (expected["canonical_sha256"] + ".json.gz")
        require(reference == {"path": str(path), **{key: expected[key] for key in (
                    "compressed_sha256", "canonical_sha256", "canonical_bytes")}},
                "fixed actor input reference differs")
        require(path.resolve() == path and not path.is_symlink(), "actor input path aliases another location")
        require(reference in report.get("input_index", []), "actor reference missing from V35 index")
        require(re.fullmatch(r"[0-9a-f]{64}", record.get("snapshot_canonical_sha256", "")) is not None,
                "missing original snapshot reference")
        require(finite_number(record.get("geometry", {}).get("now")), "missing bound actor time")
        paths.append(path)
    require(len(set(paths)) == 2, "two distinct inputs required")
    return paths


def decode_input(path, record, expected, epoch, codec):
    raw = read_limited(path)
    require(digest(raw) == expected["compressed_sha256"], "compressed input SHA differs")
    unpacked = decompress_limited(raw)
    require(len(unpacked) == expected["canonical_bytes"]
            and digest(unpacked) == expected["canonical_sha256"], "canonical input SHA/bytes differ")
    encoded = json.loads(unpacked)
    require(canonical(encoded) == unpacked and isinstance(encoded, dict)
            and set(encoded) <= PARAMETERS, "noncanonical or unknown actor parameters")
    params = codec.decode_arrays(encoded)
    require(params.get("epoch") == epoch and params.get("seed_rule") == RULE,
            "actor epoch/seed rule differs")
    require(finite_number(params.get("now"))
            and canonical(params["now"]) == canonical(record["geometry"]["now"]),
            "actor now differs from bound V35 time")
    require(type(params.get("sequence")) is int and params["sequence"] >= 0,
            "invalid actor sequence")
    states = params.get("robots")
    require(isinstance(states, list) and len(states) == 3
            and all(isinstance(state, dict) for state in states)
            and {state.get("name") for state in states} == set(ROBOTS), "three unique received robots required")
    require(isinstance(params.get("navigation_maps"), dict)
            and set(params["navigation_maps"]) == set(ROBOTS), "three own delivered navigation maps required")
    for state in states:
        require(finite_number(state.get("x")) and finite_number(state.get("y")),
                "invalid received estimated XY")
        entry = params["navigation_maps"][state["name"]]
        require(isinstance(entry, dict) and entry.get("composition_version") == COMPOSITION
                and {"grid", "resolution", "origin"} <= set(entry), "invalid delivered navigation-map input")
    return params


def descriptive_stamps(source, now):
    result = {key: source.get(key) for key in (
        "epoch", "sequence", "version", "source_stamp", "received_stamp", "payload_sha256")}
    for key in ("source_stamp", "received_stamp"):
        value = source.get(key)
        result[key.removesuffix("_stamp") + "_age_signed_sec"] = now - value if finite_number(value) else None
    return result


def inspect_fixed_inputs(source_freeze, *, report_path=REPORT, episode=EPISODE,
                         expected_inputs=EXPECTED_INPUTS, helpers=None):
    require(re.fullmatch(r"[0-9a-f]{40}", source_freeze) is not None, "exact source freeze required")
    report_path, episode = Path(report_path), Path(episode)
    raw_report = read_limited(report_path)
    report = json.loads(raw_report)
    paths = validate_report(report, episode, expected_inputs)
    primitive, codec = load_helpers() if helpers is None else helpers
    # Validate both fixed references and both decoded identities before geometry.
    decoded = [decode_input(path, record, expected, report["epoch"], codec)
               for path, record, expected in zip(paths, report["records"], expected_inputs)]
    results = []
    accepted, anchors = 0, 0
    for params, record in zip(decoded, report["records"]):
        memory_before = digest(canonical(codec.encode_arrays(params)))
        states = {state["name"]: state for state in params["robots"]}
        robot_results = []
        for name in ROBOTS:
            state, entry = states[name], params["navigation_maps"][name]
            grid = entry["grid"]
            grid_digest = digest(grid.tobytes(order="C"))
            computed = primitive.point_graph_attachments(
                grid, entry["resolution"], entry["origin"], (state["x"], state["y"]))
            require(computed.get("profile") == PROFILE and computed.get("production_enabled") is False
                    and computed.get("graph_mutated") is False
                    and type(computed.get("accepted")) is bool
                    and computed["accepted"] == bool(computed.get("anchors")), "invalid disabled primitive result")
            require(grid_digest == digest(grid.tobytes(order="C")), "primitive changed received map")
            accepted += int(computed["accepted"])
            anchors += len(computed["anchors"])
            robot_results.append({"robot": name, "estimated_xy": [state["x"], state["y"]],
                "state_metadata_descriptive_only": descriptive_stamps(state, params["now"]),
                "navigation_map": {"shape": list(grid.shape), "dtype": grid.dtype.str,
                    "grid_bytes_sha256_before": grid_digest, "grid_bytes_sha256_after": grid_digest,
                    "resolution": entry["resolution"], "origin": entry["origin"],
                    "metadata_descriptive_only": descriptive_stamps(entry, params["now"])},
                "attachment": computed})
        require(memory_before == digest(canonical(codec.encode_arrays(params))), "decoded input changed")
        results.append({"roles": record["roles"], "event_sequence": record["event_sequence"],
            "event": record["event"], "epoch": params["epoch"], "now": params["now"],
            "sequence": params["sequence"], "seed_rule": params["seed_rule"],
            "actor_input_ref": record["actor_input_ref"],
            "original_snapshot_canonical_sha256": record["snapshot_canonical_sha256"],
            "decoded_input_sha256_before": memory_before, "decoded_input_sha256_after": memory_before,
            "robots": robot_results})
    before = {str(report_path): digest(raw_report),
              **{str(path): expected["compressed_sha256"] for path, expected in zip(paths, expected_inputs)}}
    after = {path: digest(read_limited(path)) for path in before}
    require(before == after, "fixed forensic report or compressed inputs changed")
    return {"schema": SCHEMA, "source_freeze": source_freeze, "report_source_freeze": REPORT_FREEZE,
        "evidence_freeze": EVIDENCE_FREEZE, "profile": PROFILE, "passed": True,
        "computation_passed": True, "production_enabled": False, "qualification": False,
        "training_eligible": False, "native_qualification": False, "task_success_claimed": False,
        "freshness_recertified": False, "unbiased_validation": False,
        "scene": "rooms", "seed": 101, "epoch": report["epoch"],
        "counts": {"selected_frames": 2, "decoded_inputs": 2, "robot_computations": 6,
                   "robots_with_attachments": accepted, "robots_without_attachments": 6 - accepted,
                   "total_anchors": anchors}, "records": results,
        "input_bindings_before": before, "input_bindings_after": after, "input_stable": True,
        "scope": "two preselected known development frames; all three own maps/received estimated poses; no path or command",
        "limitations": ["new attachment model replaces the old containing-cell admission rule; core graph remains unchanged",
            "timestamps and signed source ages are descriptive; no new freshness or execution gate is certified",
            "original audited-input credit does not certify this new computation or production integration",
            "zero anchors is a valid negative in the fixed 3x3 model, not a task or continuous-space impossibility proof",
            "no physical pose, tracking, peer/scan safety, exploration policy, task, native or training qualification"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-freeze", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    # Claim output before evidence reads; never replace earlier successful/failed evidence.
    with args.output.open("x") as stream:
        own_identity = identity()
        before = {}
        try:
            before = source_bindings()
            result = inspect_fixed_inputs(args.source_freeze)
            after = source_bindings()
            require(before == after, "consumer/helper source changed during computation")
            result.update(source_bindings=before, source_bindings_after=after,
                          source_stable=True, identity=own_identity)
        except Exception as error:
            stream.write(json.dumps({"schema": SCHEMA, "source_freeze": args.source_freeze,
                "passed": False, "computation_passed": False, "error": repr(error),
                "source_bindings": before, "source_stable": False, "identity": own_identity,
                "production_enabled": False, "qualification": False, "training_eligible": False},
                indent=2, allow_nan=False) + "\n")
            raise
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
