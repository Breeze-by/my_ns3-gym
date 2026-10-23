"""Read-only gentle-turn readback with the reach reset/status-v2 identity.

The immutable nine-service collector and exact deployment parameter predicates
are reused. Only the release/status adapter and its provenance are new. A
parameter PASS is one independent leaf, never training or physical permission.
"""
import argparse
import copy
import importlib.util
import inspect
import json
import math
from pathlib import Path
import re
import subprocess
import time
from types import SimpleNamespace


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deployment = load_file("mr3_reach_parameter_deployment", Path(__file__).with_name("audit_nav2_parameters.py"))
WORKSPACE, PROFILE = deployment.WORKSPACE, deployment.PROFILE
CONTRACT = "mr3-reach-v1"
SCHEMA = "mr3-reach-nav2-parameter-readback-v1"
WIRE_RELATIVE = Path("ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_safety_intent.py")
STATUS_FIELDS = {"schema", "epoch", "clock_ns", "ready", "completion_scope",
                 "decision_sequences", "outputs", "safety_contract", "intent_refs", "safety_table_sha256"}
ROBOTS = ("tb1", "tb2", "tb3")
require, sha, canonical = deployment.require, deployment.sha, deployment.canonical


def validate_status(status, epoch, release, *, original_validator, wire, expected_status=None):
    require(type(status) is dict and set(status) == STATUS_FIELDS
            and status["schema"] == "mr3-motion-safety-status-v2"
            and status["safety_contract"] == CONTRACT
            and type(release) is int and release > 0
            and type(status["clock_ns"]) is int,
            "readback requires exact reach status-v2 identity")
    # Preserve the immutable reader's epoch/release/ready/sequence predicate.
    original = {key: value for key, value in status.items()
                if key not in {"safety_contract", "intent_refs", "safety_table_sha256", "outputs"}}
    original["schema"] = "mr3-motion-safety-status-v1"
    original_validator(original, epoch, release)
    wire.validate_intent_refs(status["intent_refs"], robots=ROBOTS)
    digest = status["safety_table_sha256"]
    require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest),
            "reset status requires an actually consumed safety table")
    outputs = status["outputs"]
    require(type(outputs) is dict and set(outputs) == set(ROBOTS)
            and all(type(output) is dict and set(output) == {"linear_x", "angular_z"}
                    and all(type(value) in (int, float) and math.isfinite(value) and value == 0
                            for value in output.values()) for output in outputs.values()),
            "paused reset status must contain three actual full-zero outputs")
    if expected_status is not None:
        require(canonical(status) == canonical(expected_status),
                "durable status differs from the original returned reset status")


def load_profile(root=WORKSPACE, *, expected_status=None):
    expected_status = copy.deepcopy(expected_status)
    reader, original_proof = deployment.load_profile(root)
    wire_path = root / WIRE_RELATIVE
    wire = load_file("mr3_reach_parameter_wire", wire_path)
    original_validator = reader.validate_status

    def status_adapter(status, epoch, release):
        validate_status(status, epoch, release, original_validator=original_validator,
                        wire=wire, expected_status=expected_status)

    reader.validate_status = status_adapter
    # The original callback still owns receipt/timeout/cleanup ordering; reject
    # duplicate JSON keys and NaN before its new status adapter is called.
    reader.json = SimpleNamespace(loads=wire.parse_json)
    proof = copy.deepcopy(original_proof)
    proof["schema"] = "mr3-reach-nav2-parameter-implementation-v1"
    proof["deployment_entry"] = proof.pop("effective_entry")
    proof["effective_entry"] = {"path": str(Path(__file__).resolve()),
                                "sha256": sha(Path(__file__).read_bytes())}
    proof["shared_wire_source"] = {"path": str(WIRE_RELATIVE), "sha256": sha(wire_path.read_bytes())}
    proof["original_status_function_sha256"] = proof["unchanged_function_sha256"].pop("validate_status")
    proof.update(safety_contract=CONTRACT, status_schema="mr3-motion-safety-status-v2",
                 status_adapter_sha256=sha(inspect.getsource(validate_status).encode()),
                 collection_adapters=["validate_status", "json.loads=strict_shared_parse_json"],
                 training_eligible=False)
    proof["scope"] += " Reach entry uses a separately identified status-v2 adapter and strict JSON parsing. decode_parameters, validate_parameters and nine-service collect function bytes are unchanged. Actual returned reset status is bound in full; independently received post-release HOLD references are not substituted for its prior consumed table. This leaf grants no native/training qualification."
    return reader, proof, wire


def release_binding(episode, metadata, wire):
    require(metadata.get("safety_contract") == CONTRACT, "episode safety contract mismatch")
    transition_path = episode / "transitions.jsonl"
    reset = wire.parse_json(transition_path.read_text().splitlines()[0])
    require(reset["kind"] == "reset" and reset["snapshot"]["epoch"] == metadata["epoch"],
            "original returned reset binding missing")
    release = reset["info"]["release_time_ns"]
    require(type(release) is int and release > 0, "invalid reset release source clock")
    expected_status = reset["info"]["initial_motion_status"]
    control_path = episode / "control_phase_worker.jsonl"
    rows = [wire.parse_json(line) for line in control_path.read_text().splitlines()]
    captured = [index for index, row in enumerate(rows) if row.get("kind") == "release_intents_captured"]
    require(len(captured) == 1, "one actual post-release intent capture required")
    index = captured[0]
    capture = rows[index]
    require(capture.get("schema") == "mr3-controlled-execution-phase-v2"
            and capture.get("epoch") == metadata["epoch"]
            and type(capture.get("release_clock_ns")) is int and capture["release_clock_ns"] == release
            and type(capture.get("worker_clock_ns")) is int and capture["worker_clock_ns"] == release
            and type(capture.get("worker_physical_ns")) is int and capture["worker_physical_ns"] == release,
            "actual intent capture release identity differs")
    refs = wire.validate_intent_refs(capture.get("intent_refs"), robots=ROBOTS)
    received = {}
    for row in rows[:index]:
        if row.get("kind") != "owner_intent_received":
            continue
        name = row.get("robot")
        require(name in ROBOTS and row.get("schema") == "mr3-controlled-execution-phase-v2"
                and row.get("epoch") == metadata["epoch"], "owner intent receipt identity differs")
        intent = wire.validate_intent(row["intent"], epoch=metadata["epoch"], robot=name)
        if intent["role"] == "HOLD" and intent["lineage"]["release_clock_ns"] == release:
            wire.validate_intent(intent, epoch=metadata["epoch"], robot=name, now_ns=release)
            graph = row.get("publisher_graph")
            require(type(graph) is list and len(graph) == 1
                    and graph[0].get("namespace") == "/" and graph[0].get("node") == "motion_safety"
                    and graph[0].get("type") == "std_msgs/msg/String"
                    and type(graph[0].get("endpoint_gid")) is str and bool(graph[0]["endpoint_gid"])
                    and row.get("identity_scope") == "graph_at_callback_not_per_packet_identity"
                    and row.get("payload_sha256") == wire.payload_sha256(intent),
                    "post-release HOLD actual subscription identity differs")
            received[name] = {"intent_sequence": intent["intent_sequence"],
                              "payload_sha256": wire.payload_sha256(intent)}
    require(canonical(received) == canonical(refs), "captured HOLD refs lack actual matching subscriptions")
    return release, expected_status, {"reset_transition_sha256": sha(transition_path.read_bytes()),
        "control_phase_worker_sha256": sha(control_path.read_bytes()), "post_release_intent_refs": refs,
        "initial_motion_status_sha256": sha(canonical(expected_status)),
        "identity_scope": "worker actual subscriptions with graph_at_callback, not per-packet publisher proof"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode_directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--wall-timeout-sec", type=float, default=30.)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output exists")
    if not (math.isfinite(args.wall_timeout_sec) and 0 < args.wall_timeout_sec <= 60):
        parser.error("wall timeout must be finite and at most 60 seconds")
    result = {"schema": SCHEMA, "safety_contract": CONTRACT, "profile": PROFILE, "passed": False,
              "freeze": args.freeze, "episode_directory": str(args.episode_directory),
              "script_sha256": sha(Path(__file__).read_bytes()), "nodes": [], "errors": [],
              "training_eligible": False, "scope": __doc__}
    started = time.monotonic()
    try:
        require(re.fullmatch(r"[0-9a-f]{40}", args.freeze), "exact source freeze required")
        reader, proof, wire = load_profile()
        metadata_raw = (args.episode_directory / "metadata.json").read_bytes()
        metadata = wire.parse_json(metadata_raw.decode())
        require(metadata["freeze"] == args.freeze, "episode metadata freeze mismatch")
        release, status, binding = release_binding(args.episode_directory, metadata, wire)
        reader, proof, wire = load_profile(expected_status=copy.deepcopy(status))
        reader.validate_status(status, metadata["epoch"], release)
        sources = [Path(__file__).resolve().relative_to(WORKSPACE),
                   Path(deployment.__file__).resolve().relative_to(WORKSPACE),
                   deployment.LEGACY_RELATIVE, WIRE_RELATIVE,
                   *(Path(row["path"]) for row in proof["yaml_sources"])]
        source_bytes = {}
        for relative in sources:
            raw = (WORKSPACE / relative).read_bytes()
            frozen = subprocess.check_output(["git", "show", args.freeze+":"+str(relative)], cwd=WORKSPACE)
            require(raw == frozen, "parameter source differs from freeze: "+str(relative))
            source_bytes[relative] = raw
        result.update(epoch=metadata["epoch"], source_clock_ns=release,
                      metadata_sha256=sha(metadata_raw), release_binding=binding,
                      implementation_provenance=proof, expected_typed_parameters=reader.EXPECTED,
                      source_bindings=[{"path": str(path), "sha256": sha(raw)} for path, raw in source_bytes.items()])
        reader.collect(metadata["epoch"], release, args.wall_timeout_sec, result)
        require(all((WORKSPACE / path).read_bytes() == raw for path, raw in source_bytes.items()),
                "parameter source changed during readback")
        require((args.episode_directory / "metadata.json").read_bytes() == metadata_raw
                and release_binding(args.episode_directory, metadata, wire)[2] == binding,
                "paused reset evidence changed during readback")
        result["passed"] = True
    except Exception as error:
        result["errors"].append(repr(error))
    result["wall_duration_sec"] = time.monotonic()-started
    with args.output.open("x") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"passed": result["passed"], "nodes": len(result["nodes"]),
                      "errors": result["errors"], "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
