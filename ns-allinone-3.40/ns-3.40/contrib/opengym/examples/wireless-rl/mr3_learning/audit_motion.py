"""Replay callback provenance and final velocity FIFO; no ROS or truth imports.

Geometry replay uses the exact frozen producer helper. It establishes that the
recorded input bytes produced the recorded result, not an independent proof of
its physical model, braking bounds or all possible trajectories. Humble records
publisher identity from the unique native graph at callback, not packet GIDs.
"""

from collections import deque
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from types import ModuleType


ROBOTS = ("tb1", "tb2", "tb3")
PURE_DIRECTORY = "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/" \
                 "multi_robot_exploration/"


def require(value, message):
    if not value:
        raise ValueError(message)


def same_json(left, right):
    """Compare recorded types as well as values; bool must not equal zero/one."""
    return json.dumps(left, sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(
        right, sort_keys=True, separators=(",", ":"), allow_nan=False)


def ns(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            "invalid motion timestamp")
    return round(value * 10**9)


def read(directory, name, lines=False):
    path = directory / name
    if not path.exists():
        path = Path(str(path) + ".gz")
    raw = path.read_bytes()
    decoded = gzip.decompress(raw) if path.suffix == ".gz" else raw
    value = ([json.loads(line) for line in decoded.splitlines() if line.strip()]
             if lines else json.loads(decoded))
    return value, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                   "decoded_sha256": hashlib.sha256(decoded).hexdigest()}


def load_frozen_helper(root, freeze):
    """Import only two SHA-bound pure files; never add ROS paths to sys.path."""
    require(re.fullmatch(r"[0-9a-f]{40}", freeze) is not None, "exact motion freeze required")
    modules, proof = {}, {}
    package = "multi_robot_exploration"
    names = [package, package + ".mr3_episode", package + ".mr3_motion_safety"]
    previous = {name: sys.modules.get(name) for name in names}
    try:
        placeholder = ModuleType(package)
        placeholder.__path__ = []
        sys.modules[package] = placeholder
        for filename in ("mr3_episode.py", "mr3_motion_safety.py"):
            relative = PURE_DIRECTORY + filename
            payload = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
            current = (root / relative).read_bytes()
            require(payload == current, "motion helper worktree differs from freeze: " + filename)
            name = package + "." + filename[:-3]
            spec = importlib.util.spec_from_file_location(name, root / relative)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            modules[filename] = module
            proof[relative] = {"sha256": hashlib.sha256(payload).hexdigest(),
                               "git_source": freeze + ":" + relative}
    finally:
        for name in names:
            if previous[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous[name]
    return modules["mr3_motion_safety.py"], proof


def stamp(header):
    value = header["stamp"]
    require(type(value["sec"]) is int and type(value["nanosec"]) is int
            and value["sec"] >= 0 and 0 <= value["nanosec"] < 10**9, "invalid raw source stamp")
    return value["sec"] + value["nanosec"] / 1e9


def yaw(quaternion):
    x, y, z, w = (quaternion[key] for key in ("x", "y", "z", "w"))
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y ** 2 + z ** 2))


def own_state(name, sources, sequences, epoch, settled_tracker=None, clock_ns=None):
    if "odom" not in sources or "tf" not in sources:
        return None
    odom, transform = sources["odom"], sources["tf"]
    if (odom["header"]["frame_id"].lstrip("/") != "odom"
            or odom["child_frame_id"].lstrip("/") not in ("base_footprint", "base_link")):
        return None
    orientation = odom["pose"]["pose"]["orientation"]
    rotation = transform["transform"]["rotation"]
    for quaternion in (orientation, rotation):
        values = [quaternion[key] for key in ("x", "y", "z", "w")]
        if (any(type(value) not in (int, float) or not math.isfinite(value) for value in values)
                or abs(sum(value * value for value in values) - 1.) > .01):
            return None
    angle = yaw(rotation)
    point, translation = odom["pose"]["pose"]["position"], transform["transform"]["translation"]
    odom_time, validity = stamp(odom["header"]), stamp(transform["header"])
    tf_time = validity - .2
    value = {
        "robot": name, "name": name, "epoch": epoch, "valid": True,
        "x": translation["x"] + math.cos(angle) * point["x"] - math.sin(angle) * point["y"],
        "y": translation["y"] + math.sin(angle) * point["x"] + math.cos(angle) * point["y"],
        "yaw": math.atan2(math.sin(angle + yaw(orientation)),
                          math.cos(angle + yaw(orientation))),
        "v": odom["twist"]["twist"]["linear"]["x"],
        "w": odom["twist"]["twist"]["angular"]["z"],
        "odom_source_stamp": odom_time, "tf_source_stamp": tf_time,
        "tf_validity_stamp": validity, "tf_validity_lead_sec": .2,
        "source_stamp": min(odom_time, tf_time),
        "input_sequences": {key: sequences[key] for key in ("odom", "tf")},
    }
    if settled_tracker is not None:
        linear = odom["twist"]["twist"]["linear"]
        value["planar_speed_mps"] = math.hypot(linear["x"], linear["y"])
        value["settled_turn"] = settled_tracker.certificate(clock_ns)
    return value


def causal_own_inputs(histories, sequences, clock_ns):
    """Reproduce the producer's bounded raw callback history, including ties."""
    selected, selected_sequences = {}, dict(sequences)
    for stream, lead_ns in (("odom", 0), ("tf", 200_000_000)):
        eligible = []
        for sequence, message in histories[stream]:
            header = message["header"]["stamp"]
            stamp(message["header"])
            source_ns = header["sec"] * 10**9 + header["nanosec"] - lead_ns
            if source_ns <= clock_ns:
                eligible.append((header["sec"], header["nanosec"], sequence, message))
        if not eligible:
            return {}, selected_sequences
        _, _, sequence, message = max(eligible, key=lambda item: item[:3])
        selected[stream], selected_sequences[stream] = message, sequence
    return selected, selected_sequences


def identity(value, name, actual, topology):
    topic = f"/{name}/cmd_vel" + ("" if actual else "_unguarded")
    expected = ("/", "motion_safety") if actual else (f"/{name}", "velocity_smoother")
    require(value["scope"] == "graph_at_callback" and value["topic"] == topic
            and value["valid"] is True and len(value["endpoints"]) == 1,
            "motion callback has no unique native publisher identity")
    endpoint = value["endpoints"][0]
    require((endpoint["namespace"], endpoint["node"]) == expected
            and endpoint["topic_type"] == "geometry_msgs/msg/Twist"
            and re.fullmatch(r"[0-9a-f]{32,}", endpoint["endpoint_gid"])
            and int(endpoint["endpoint_gid"], 16) != 0, "wrong native motion publisher")
    if actual:
        require(endpoint == topology["endpoints"][topic][0],
                "actual motion callback GID differs from startup graph")


def twist_pair(value):
    require(set(value) == {"linear", "angular"}
            and all(set(value[axis]) == {"x", "y", "z"} for axis in value), "bad Twist shape")
    require(all(type(item) in (int, float) and math.isfinite(item)
                for vector in value.values() for item in vector.values()), "nonfinite Twist")
    require(all(value[axis][key] == 0 for axis, key in
                (("linear", "y"), ("linear", "z"), ("angular", "x"), ("angular", "y"))),
            "unsupported output/request Twist axes")
    return [value["linear"]["x"], value["angular"]["z"]]


def command_boundary(decision, request, settled_enabled=False):
    """Enforce hard limits, exact endpoint normalization and sole component filter."""
    output = decision["output"]
    require(abs(output[0]) <= .26 and abs(output[1]) <= .8, "final motion hard limit exceeded")
    normalization = decision.get("command_normalization")
    canonical = None if request is None else [request["v"], request["w"]]
    if normalization is not None:
        require(request is not None and normalization["schema"] == "mr3-command-one-ulp-v1"
                and normalization["input"] == canonical,
                "motion normalization lost original callback values")
        canonical, changed = [], []
        for axis, value, limit in zip(("v", "w"), normalization["input"], (.26, .8)):
            if abs(value) > limit:
                require(abs(value) == math.nextafter(limit, math.inf),
                        "motion normalization exceeded one binary64 neighbour")
                value = math.copysign(limit, value)
                changed.append(axis)
            canonical.append(value)
        require(changed and normalization["normalized_axes"] == changed
                and normalization["canonical"] == canonical,
                "motion normalization metadata differs from exact endpoints")
    component = decision.get("component_filter")
    if decision.get("reason") == "settled_turn_drift_reserve":
        settled_boundary(decision, settled_enabled)
    if component is None:
        if decision["allow"]:
            require(output == canonical, "allowed motion differs from canonical endpoint request")
        return
    require(canonical is not None and canonical[0] != 0 and canonical[1] != 0
            and decision["allow"] is True
            and decision["reason"] == "linear_brake_preserve_requested_turn"
            and component["schema"] == "mr3-linear-brake-requested-turn-v1"
            and component["canonical_input"] == canonical,
            "invalid requested-turn component filter")
    rejected, rotation = component["rejected_mixed_decision"], component["rotation_check"]
    require(rejected["allow"] is False and rejected["reason"] == "peer_braking_nonclosing"
            and rejected["output"] == [0., 0.] and rejected.get("component_filter") is None
            and rejected.get("command_normalization") == normalization,
            "component filter bypassed a different mixed-command rejection")
    require(rotation["allow"] is True and rotation["reason"] in (
                "clear", "settled_turn_drift_reserve")
            and rotation.get("component_filter") is None
            and rotation.get("command_normalization") is None
            and rotation["output"] == output == [0., canonical[1]],
            "component filter changed angular direction or lacks valid rotation check")
    if rotation["reason"] == "settled_turn_drift_reserve":
        settled_boundary(rotation, settled_enabled)


def settled_boundary(decision, enabled):
    """Require explicit provenance; full history and math are replayed separately."""
    check = decision.get("settled_turn_check")
    require(enabled and isinstance(check, dict)
            and check.get("schema") == "mr3-settled-turn-check-v1"
            and isinstance(check.get("certificate"), dict)
            and decision["output"][0] == 0. and decision["output"][1] != 0.,
            "settled turn lacks configured complete certificate/check")


def audit_control_worker(load, epoch, physics, node_requests, node_acks, published,
                         completed, output_windows):
    """Bind the worker's causal chain to actual callbacks, outputs and advances.

    The separate independent control reader validates side-topic delivery and
    obstacle payload construction. This check never claims costmap consumption.
    """
    records = load("control_phase_worker.jsonl", True)
    requests, received, consumed, motion, motion_references = {}, {}, {}, [], {}
    rejected, cancellations, observed_stops = {}, set(), []
    previous_wall = -1
    for row in records:
        wall, kind = row["wall_monotonic_ns"], row["kind"]
        require(row.get("schema") == "mr3-controlled-execution-phase-v1"
                and row.get("epoch") == epoch and type(wall) is int and wall >= previous_wall,
                "worker control ledger identity/wall order mismatch")
        previous_wall = wall
        if kind == "request":
            component, request = row["component"], row["request"]
            key = (component, request["request_id"])
            schema = ("mr3-motion-control-request-v1" if component == "motion"
                      else f"mr3-{component}-phase-request-v1")
            require(component in ("state", "peer", "motion") and key not in requests
                    and request.get("schema") == schema
                    and request.get("epoch") == epoch
                    and request.get("operation") in ("takeover", "commit", "stop")
                    and type(request.get("target_time_ns")) is int
                    and request["target_time_ns"] == row["worker_clock_ns"]
                    == row["worker_physical_ns"], "worker control request was not paused/exact")
            if component == "motion":
                require(same_json(node_requests.get(request["request_id"]), request),
                        "worker motion request has no actual guard callback")
            requests[key] = (request, wall)
        elif kind == "ack_received":
            component, ack = row["component"], row["ack"]
            if ack.get("epoch") != epoch:
                continue
            key = (component, ack.get("request_id"))
            require(key in requests, "worker control receipt has no preceding request")
            require(key not in received or same_json(received[key][0], ack),
                    "worker actual control receipt changed")
            received[key] = (ack, min(wall, received.get(key, (None, wall))[1]))
        elif kind in ("ack_consumed", "ack_rejected"):
            component, ack = row["component"], row["ack"]
            key = (component, ack.get("request_id"))
            require(key in requests and key in received
                    and same_json(received[key][0], ack) and received[key][1] <= wall,
                    "worker consumed control ACK without its actual receipt")
            request = requests[key][0]
            target = request["target_time_ns"]
            schema = ("mr3-motion-control-ack-v1" if component == "motion"
                      else f"mr3-{component}-phase-ack-v1")
            require(ack.get("epoch") == epoch
                    and ack.get("schema") == schema
                    and type(ack.get("target_time_ns")) is int
                    and ack.get("target_time_ns") == target
                    and ack.get("operation") == request["operation"]
                    and type(ack.get("clock_ns")) is int and type(ack.get("ok")) is bool
                    and row["worker_clock_ns"] == row["worker_physical_ns"] == target,
                    "worker control ACK identity or paused boundary differs")
            if kind == "ack_rejected":
                require(ack.get("ok") is False and component == "state"
                        and ack.get("error") == "state_phase_task_terminal"
                        and ack.get("scope") == "terminal_cancelled_uncommitted_state_phase"
                        and 0 <= ack["clock_ns"] <= target,
                        "actual rejected control phase is not a terminal cancellation")
                rejected[key] = ack
                continue
            require(ack.get("ok") is True and ack["clock_ns"] == target and key not in consumed,
                    "worker control success was duplicated, failed or inexact")
            if component == "motion":
                require(same_json(node_acks.get(ack["request_id"]), ack)
                        and any(start <= received[key][1] for start, _ in published.get(
                            ack["request_id"], [])),
                        "worker guard ACK has no matching actual publication interval")
                status = ack["status"]
                status_key = (target, status.get("phase_kind", "normal"),
                              tuple(status["decision_sequences"][name] for name in ROBOTS))
                require(same_json(completed.get(status_key), status),
                        "worker controlled motion lacks completed actual outputs")
                if request["operation"] == "commit" and status.get("phase_kind") != "stop":
                    for dependency in ("state", "peer"):
                        dependency_key = (dependency, request["request_id"])
                        require(dependency_key in consumed
                                and same_json(consumed[dependency_key][0],
                                              request[dependency + "_commit"])
                                and consumed[dependency_key][1] <= requests[key][1],
                                "guard request preceded consumed state/peer commits")
                motion.append((status, wall))
                motion_references[status_key] = (ack["request_id"], request["operation"])
            elif component == "peer" and request["operation"] == "commit":
                state_key = ("state", request["request_id"])
                require(state_key in consumed and consumed[state_key][1] <= requests[key][1]
                        and same_json(consumed[state_key][0], request["state_commit"])
                        and same_json(ack.get("state_commit"), request["state_commit"]),
                        "peer request/ACK preceded or changed consumed state commit")
            consumed[key] = (ack, wall)
        elif kind == "stop_observed":
            status = row["status"]
            key = (status["clock_ns"], "stop",
                   tuple(status["decision_sequences"][name] for name in ROBOTS))
            require(row.get("origin") in ("stop_topic", "control_ack")
                    and same_json(completed.get(key), status),
                    "worker stop observation lacks an actual zero output completion")
            if row["origin"] == "stop_topic":
                require(output_windows[key][0] <= wall,
                        "stop callback preceded actual stop publication start")
            observed_stops.append((status, wall))
        elif kind == "terminal_cancelled":
            key = (row["component"], row["ack"].get("request_id"))
            notice = row["terminal_notice"]
            require(key in rejected and same_json(rejected[key], row["ack"])
                    and same_json(notice, row["ack"].get("terminal_notice"))
                    and notice.get("epoch") == epoch
                    and ns(notice["end_sim_time_sec"]) <= row["worker_physical_ns"],
                    "worker terminal cancellation lost its real notice/failed ACK")
            cancellations.add(key)
        else:
            raise ValueError("unknown or actual failed worker control event: " + kind)
    require(records and set(rejected) == cancellations, "unsettled worker control cancellation")
    require(motion, "no consumed actual controlled motion")
    takeovers = [ack for (component, _), (ack, _) in consumed.items()
                 if component == "motion" and ack["operation"] == "takeover"]
    require(len(takeovers) == 1, "controlled execution takeover missing/duplicated")
    takeover_clock = takeovers[0]["clock_ns"]
    takeover_id = takeovers[0]["request_id"]
    require(all((component, takeover_id) in consumed
                and consumed[(component, takeover_id)][0].get("operation") == "takeover"
                and consumed[(component, takeover_id)][0].get("clock_ns") == takeover_clock
                for component in ("state", "peer", "motion")),
            "bootstrap lacks three actual consumed takeovers")
    require(all(output == {"linear_x": 0., "angular_z": 0.}
                for output in takeovers[0]["status"]["outputs"].values()),
            "takeover did not preserve real pre-release zeros")
    drive = load("drive_phase_worker.jsonl", True)
    permitted, bootstraps = {}, 0
    for row in drive:
        if row["kind"] != "advance_permitted":
            continue
        status, wall = row["expected_motion"], row["wall_monotonic_ns"]
        candidates = [(value, stamp) for value, stamp in motion
                      if stamp <= wall and value["clock_ns"] == row["start_time_ns"]]
        require(candidates and same_json(max(candidates, key=lambda item: item[1])[0], status),
                "physics advance did not use latest consumed controlled motion")
        status_key = (status["clock_ns"], status.get("phase_kind", "normal"),
                      tuple(status["decision_sequences"][name] for name in ROBOTS))
        reference, operation = motion_references[status_key]
        expected_kind = ("bootstrap_zero" if operation == "takeover" else
                         "stop" if status.get("phase_kind") == "stop" else "normal")
        require(row.get("control_kind") == expected_kind
                and row.get("control_request_id") == reference,
                "physical advance control kind/request binding differs")
        if expected_kind == "bootstrap_zero":
            bootstraps += 1
            require(bootstraps == 1 and row["steps"] == 20
                    and row["start_time_ns"] == takeover_clock
                    and all(consumed[(component, takeover_id)][1] <= wall
                            for component in ("state", "peer", "motion")),
                    "bootstrap was repeated or preceded its real three takeover receipts")
        stops = [(value, stamp) for value, stamp in observed_stops
                 if stamp <= wall and value["clock_ns"] == row["start_time_ns"]]
        require(not stops or same_json(max(stops, key=lambda item: item[1])[0], status),
                "physics advanced using normal motion after a permanent stop observation")
        require(row["request_id"] not in permitted, "duplicate controlled physical advance")
        permitted[row["request_id"]] = row
    for row in physics:
        if row.get("steps", 0) > 0 and row["start_time_ns"] >= takeover_clock:
            permission = permitted.get(row["request_id"])
            require(permission is not None and permission["steps"] == row["steps"]
                    and permission["start_time_ns"] == row["start_time_ns"],
                    "actual controlled physical quantum lacked the commit/storage chain")
    require(bootstraps == 1, "the single real zero bootstrap quantum is missing")
    return {"records": len(records), "consumed_motion_phases": len(motion),
            "stop_clocks": sorted({value["clock_ns"] for value, _ in motion
                                   if value.get("phase_kind") == "stop"}),
            "normal_clocks": sorted({value["clock_ns"] for value, _ in motion
                                     if value.get("phase_kind") != "stop"}),
            "terminal_cancellations": len(cancellations),
            "bootstrap_zero_quanta": bootstraps,
            "scope": ("worker causal request/actual receipt/guard output provenance; actual side "
                      "delivery and obstacles require the separate independent control reader")}


def _audit_records(directory, helper, source_proof):
    """Actual consumer, split only so synthetic fixtures need no fabricated Git freeze."""
    directory = Path(directory)
    proof = {}

    def load(name, lines=False):
        value, proof[name] = read(directory, name, lines)
        return value

    metadata = load("metadata.json")
    epoch = metadata["epoch"]
    topology = load("motion_topology.json")
    transitions = load("transitions.jsonl", True)
    require(transitions and transitions[0]["kind"] == "reset"
            and all(row["snapshot"]["epoch"] == epoch for row in transitions),
            "motion transitions/epoch mismatch")
    release_ns = transitions[0]["info"]["release_time_ns"]
    require(topology["schema"] == "mr3-motion-output-topology-v1" and topology["epoch"] == epoch
            and ns(topology["stamp"]) <= release_ns
            and set(topology["endpoints"]) == {f"/{name}/cmd_vel" for name in ROBOTS},
            "motion startup topology identity mismatch")
    for name in ROBOTS:
        identity({"scope": "graph_at_callback", "topic": f"/{name}/cmd_vel", "valid": True,
                  "endpoints": topology["endpoints"][f"/{name}/cmd_vel"]}, name, True, topology)
    require(len({topology["endpoints"][f"/{name}/cmd_vel"][0]["endpoint_gid"]
                 for name in ROBOTS}) == 3, "motion output endpoint GIDs are not distinct")
    rows = load("motion_safety.jsonl", True)
    require(rows and rows[0]["kind"] == "configuration", "motion configuration missing")
    configuration = rows[0]["payload"]
    require(configuration["robots"] == list(ROBOTS)
            and configuration["twist_source_stamp_available"] is False
            and configuration["publisher_identity_scope"] ==
            "graph_at_callback; packet MessageInfo unavailable on installed Humble",
            "unknown motion identity scope/configuration")
    settled_enabled = "settled_turn_contract" in configuration
    causal_selection = configuration.get("own_input_selection") == "latest_causal_v1"
    require("own_input_selection" not in configuration or causal_selection,
            "unknown own motion input selection")
    controlled = configuration.get("controlled_execution", False)
    require(type(controlled) is bool, "invalid controlled execution configuration")
    if controlled:
        require(causal_selection and metadata.get("execution_phase_protocol")
                == "mr3-controlled-execution-phase-v1", "unknown controlled motion protocol")
    if settled_enabled:
        contract = configuration["settled_turn_contract"]
        require(isinstance(contract, str) and contract.startswith("mr3-settled-turn-v1;")
                and callable(getattr(helper, "SettledTurnTracker", None)),
                "unknown settled turn configuration/helper")
    trackers = ({name: helper.SettledTurnTracker() for name in ROBOTS}
                if settled_enabled else {})
    settled_activations = dict.fromkeys(ROBOTS, 0)
    sources = {name: {} for name in ROBOTS}
    histories = {name: {stream: deque(maxlen=256) for stream in ("odom", "tf")}
                 for name in ROBOTS}
    sequences = {name: dict.fromkeys(("odom", "tf", "request", "decision"), 0) for name in ROBOTS}
    requests, states, decisions = {}, {}, {}
    queues = {name: deque() for name in ROBOTS}
    stats = {name: {"nonzero_requests": 0, "passed_nonzero": 0, "stopped_nonzero": 0,
                    "rotation_only_filtered": 0,
                    "controlled_stop_decisions": 0,
                    "decisions": 0, "actual_outputs": 0, "near_events": 0,
                    "maximum_measured_abs_v": 0., "maximum_measured_abs_w": 0.,
                    "minimum_body_margin_m": None} for name in ROBOTS}
    started, halted, stop_ns = False, None, None
    previous_wall, previous_clock = -1, -1
    pending_stops, stop_responses = {}, []
    control_requests, control_acks, control_dependencies = {}, {}, {}
    control_commits, completed_outputs = {}, {}
    control_publish_windows, output_publish_windows = {}, {}

    def selected_own(name, target, tracker=None):
        selected, selected_sequences = sources[name], sequences[name]
        if causal_selection:
            selected, selected_sequences = causal_own_inputs(
                histories[name], sequences[name], target)
        return own_state(name, selected, selected_sequences, epoch, tracker, target)

    def completed_status(status, wall):
        require(isinstance(status, dict) and status.get("epoch") == epoch
                and status.get("schema") == "mr3-motion-safety-status-v1"
                and type(status.get("clock_ns")) is int and type(status.get("ready")) is bool
                and status.get("completion_scope") == "publication_and_local_topic_receipt"
                and set(status.get("decision_sequences", {})) == set(ROBOTS)
                and set(status.get("outputs", {})) == set(ROBOTS),
                "invalid completed motion status")
        kind = status.get("phase_kind", "normal")
        require(kind in ("normal", "stop") and (kind != "stop" or controlled
                and status["ready"] is False), "unconfigured completed stop status")
        for name in ROBOTS:
            sequence = status["decision_sequences"][name]
            require(type(sequence) is int and (name, sequence) in decisions,
                    "completed output has no actual decision")
            decision = decisions[(name, sequence)]
            require(decision["clock_ns"] == status["clock_ns"]
                    and decision["phase_kind"] == kind
                    and decision["ready"] is status["ready"]
                    and same_json(status["outputs"][name], {
                        "linear_x": decision["output"][0], "angular_z": decision["output"][1]})
                    and decision.get("actual_wall_ns", 10**30) <= wall,
                    "completed output lacks exact decision/local topic receipt")
        return (status["clock_ns"], kind,
                tuple(status["decision_sequences"][name] for name in ROBOTS))

    for index, row in enumerate(rows, 1):
        clock, wall = ns(row["sim_time_sec"]), row["wall_monotonic_ns"]
        require(row["schema"] == "mr3-motion-safety-v1" and row["epoch"] == epoch
                and type(row["record_sequence"]) is int and row["record_sequence"] == index
                and type(wall) is int and wall >= previous_wall and clock >= previous_clock,
                "motion record epoch/sequence/clock order mismatch")
        previous_wall, previous_clock = wall, clock
        kind, value = row["kind"], row["payload"]
        if kind in ("own_odom", "own_tf"):
            name, stream = value["robot"], "odom" if kind == "own_odom" else "tf"
            require(name in ROBOTS and type(value["input_sequence"]) is int
                    and value["input_sequence"] == sequences[name][stream] + 1,
                    "motion raw input sequence mismatch")
            sequences[name][stream] += 1
            sources[name][stream] = value["message"]
            histories[name][stream].append((value["input_sequence"], value["message"]))
            if stream == "tf":
                require(value["message"]["header"]["frame_id"].lstrip("/") == "map"
                        and value["message"]["child_frame_id"].lstrip("/") == "odom",
                        "own TF is not local map-to-odom")
            else:
                if settled_enabled:
                    trackers[name].observe(value["message"], value["input_sequence"])
                twist = value["message"]["twist"]["twist"]
                for axis, key in (("linear", "v"), ("angular", "w")):
                    measured = abs(twist[axis]["x" if key == "v" else "z"])
                    require(math.isfinite(measured), "nonfinite measured velocity")
                    field = "maximum_measured_abs_" + key
                    stats[name][field] = max(stats[name][field], measured)
                if name in pending_stops:
                    pending = pending_stops[name]
                    source_ns = ns(stamp(value["message"]["header"]))
                    if source_ns >= pending["stop_clock_ns"]:
                        point = value["message"]["pose"]["pose"]["position"]
                        if pending["last_point"] is not None:
                            pending["observed_odom_path_m"] += math.hypot(
                                point["x"] - pending["last_point"][0],
                                point["y"] - pending["last_point"][1])
                        pending["last_point"] = [point["x"], point["y"]]
                        if abs(twist["linear"]["x"]) <= .01 and abs(twist["angular"]["z"]) <= .02:
                            pending.update(status="observed_rest", rest_source_clock_ns=source_ns,
                                           observed_latency_sec=(
                                               source_ns - pending["stop_clock_ns"]) / 1e9)
                            stop_responses.append(pending_stops.pop(name))
        elif kind == "raw_request":
            name, request = value["robot"], value["request"]
            require(name in ROBOTS and type(request["sequence"]) is int
                    and request["sequence"] == sequences[name]["request"] + 1
                    and type(request["supported"]) is bool
                    and ns(request["received_stamp"]) == clock,
                    "raw motion request binding mismatch")
            sequences[name]["request"] += 1
            if request["supported"]:
                require(same_json(twist_pair(value["twist"]), [request["v"], request["w"]]),
                        "raw motion request differs from callback Twist")
            else:
                require(request["v"] is None and request["w"] is None and value["twist"] is None,
                        "unsupported command was fabricated into a supported Twist")
            if request["publisher_identity"]["valid"]:
                identity(request["publisher_identity"], name, False, topology)
            requests[name] = request
        elif kind == "received_states":
            require(value["epoch"] == epoch and len(value["robots"]) == 3
                    and {r["name"] for r in value["robots"]} == set(ROBOTS),
                    "invalid original received peer state set")
            states = {r["name"]: r for r in value["robots"]}
        elif kind == "invalid_received_states":
            states = {}
        elif kind == "release":
            require(not started and ns(value["stamp"]) == release_ns, "motion release mismatch")
            if settled_enabled:
                for tracker in trackers.values():
                    tracker.release(release_ns)
            started = True
        elif kind == "stop_request":
            stop_ns = clock
        elif kind == "terminal":
            require(value["epoch"] == epoch, "motion terminal epoch mismatch")
            stop_ns = ns(value["end_sim_time_sec"])
        elif kind in ("invalid_terminal_notice", "failure"):
            halted = ("invalid_terminal_notice" if kind == "invalid_terminal_notice"
                      else "external_safety_failure")
        elif kind == "settled_turn_model_failure":
            raise ValueError("actual settled turn model failure: " + str(value))
        elif kind == "decision":
            name = value["robot"]
            require(name in ROBOTS
                    and type(value["decision_sequence"]) is int
                    and value["decision_sequence"] == sequences[name]["decision"] + 1
                    and type(value["clock_ns"]) is int and value["clock_ns"] == clock
                    and value["started"] is started and type(value["ready"]) is bool,
                    "motion decision identity/phase mismatch")
            sequences[name]["decision"] += 1
            decision_clock = value["clock_ns"]
            own = selected_own(name, decision_clock, trackers.get(name))
            peers = {peer: states.get(peer) for peer in ROBOTS if peer != name}
            request = requests.get(name)
            require(same_json(value["own_state"], own),
                    "own state differs from raw local odom/TF input sequences")
            require(same_json(value["received_peers"], peers),
                    "peer geometry bypassed original received states")
            require(same_json(value["request"], request),
                    "decision request differs from raw callback sequence/content/GID")
            is_stop = value.get("phase_kind") == "stop"
            require("phase_kind" not in value or controlled and is_stop,
                    "unknown/unconfigured motion phase kind")
            if is_stop:
                require(value["ready"] is False, "stop decision falsely claims input readiness")
            elif value["ready"]:
                require(all(helper.valid_state(
                    selected_own(peer, decision_clock),
                    decision_clock / 1e9, epoch)
                            and helper.valid_state(states.get(peer), decision_clock / 1e9, epoch)
                            for peer in ROBOTS), "ready motion decision used unhealthy source")
            elif started and halted is None:
                halted = "motion_state_or_topology_unavailable"
            if is_stop:
                reason = halted or "controlled_stop"
            elif not value["ready"]:
                reason = "state_or_topology_unavailable"
            elif not started:
                reason = "before_release"
            elif halted or (stop_ns is not None and decision_clock >= stop_ns):
                reason = halted or "task_stopped"
            elif (request is None
                  or not 0 <= decision_clock - ns(request["received_stamp"]) <= 200000000):
                reason = "command_timeout"
            elif not request["publisher_identity"]["valid"]:
                reason = "command_publisher_unavailable"
            elif not request["supported"]:
                reason = "unsupported_command"
            else:
                reason = None
            expected = (helper.guard_motion([request["v"], request["w"]], own, peers,
                                            decision_clock / 1e9, epoch) if reason is None else
                        {"allow": False, "reason": reason, "output": [0., 0.],
                         "minimum_margin_m": None})
            command_boundary(value["decision"], request, settled_enabled)
            require(same_json(value["decision"], expected),
                    "motion decision differs from frozen helper replay")
            if settled_enabled:
                rotation = (expected.get("component_filter") or {}).get("rotation_check", {})
                if (expected["reason"] == "settled_turn_drift_reserve"
                        or rotation.get("reason") == "settled_turn_drift_reserve"):
                    trackers[name].activate(decision_clock)
                    settled_activations[name] += 1
                trackers[name].output(expected["output"][0], decision_clock,
                                      value["decision_sequence"])
            key = (name, value["decision_sequence"])
            decisions[key] = {"clock_ns": decision_clock, "ready": value["ready"],
                              "wall_ns": wall, "phase_kind": "stop" if is_stop else "normal",
                              "output": expected["output"]}
            queues[name].append((expected["output"], key))
            item = stats[name]
            item["decisions"] += 1
            item["controlled_stop_decisions"] += is_stop
            nonzero = bool(request and request["supported"] and (request["v"] or request["w"]))
            item["nonzero_requests"] += nonzero
            filtered = expected.get("component_filter") is not None
            item["passed_nonzero"] += nonzero and expected["allow"] and not filtered
            item["stopped_nonzero"] += nonzero and not expected["allow"] and not is_stop
            item["rotation_only_filtered"] += filtered
            item["near_events"] += sum(check["near"]
                                       for check in expected.get("near_peer_checks", []))
            margin = expected.get("body_margin_m")
            if margin is not None:
                old_margin = item["minimum_body_margin_m"]
                item["minimum_body_margin_m"] = margin
                if old_margin is not None:
                    item["minimum_body_margin_m"] = min(old_margin, margin)
            if expected["output"][0] != 0:
                if name in pending_stops:
                    pending_stops[name]["status"] = "resumed_before_observed_rest"
                    stop_responses.append(pending_stops.pop(name))
            elif (nonzero and (expected["reason"].startswith("peer_") or filtered)
                  and name not in pending_stops):
                pending_stops[name] = {"robot": name, "stop_clock_ns": decision_clock,
                                       "status": "incomplete", "observed_odom_path_m": 0.,
                                       "last_point": None}
        elif kind == "actual_cmd_vel":
            name = value["robot"]
            require(name in ROBOTS, "unknown actual motion robot")
            identity(value["publisher_identity"], name, True, topology)
            require(queues[name], "actual motion output has no preceding publication")
            expected, key = queues[name].popleft()
            require(twist_pair(value["twist"]) == expected,
                    "actual cmd_vel differs from final publication FIFO")
            require(value["observed_decision_sequence"] == key[1],
                    "actual output sequence differs from publication FIFO")
            decisions[key]["actual_wall_ns"] = wall
            stats[name]["actual_outputs"] += 1
        elif kind == "output_completed":
            require(causal_selection, "unconfigured completed-output event")
            status = value["status"]
            start, end = value.get("publish_started_wall_monotonic_ns"), value.get(
                "publish_completed_wall_monotonic_ns")
            require(type(start) is int and type(end) is int and 0 <= start <= end <= wall,
                    "completed output publication window invalid")
            key = completed_status(status, start)
            require(key not in completed_outputs or same_json(completed_outputs[key], status),
                    "completed output status changed")
            completed_outputs[key] = status
            output_publish_windows[key] = (start, end)
        elif kind == "control_failure":
            raise ValueError("actual motion controlled phase failure: " + str(value))
        elif kind == "control_request":
            require(controlled and value.get("schema") == "mr3-motion-control-request-v1"
                    and value.get("epoch") == epoch
                    and isinstance(value.get("request_id"), str) and value["request_id"]
                    and type(value.get("target_time_ns")) is int
                    and value["target_time_ns"] >= clock
                    and value.get("operation") in ("takeover", "commit", "stop"),
                    "invalid actual motion control request")
            key = value["request_id"]
            require(key not in control_requests or same_json(control_requests[key], value),
                    "motion control request identity changed")
            control_requests[key] = value
        elif kind == "control_dependency":
            component, ack = value["component"], value["value"]
            require(controlled and component in ("state", "peer") and ack.get("epoch") == epoch
                    and isinstance(ack.get("request_id"), str),
                    "invalid actual control dependency")
            key = (component, ack["request_id"])
            require(key not in control_dependencies or same_json(control_dependencies[key], ack),
                    "actual control dependency changed")
            control_dependencies[key] = ack
        elif kind == "control_commit":
            request = value["request"]
            require(controlled and request.get("operation") == "commit"
                    and request.get("target_time_ns") == clock
                    and same_json(control_requests.get(request.get("request_id")), request),
                    "normal control commit lacks its actual request")
            for component in ("state", "peer"):
                dependency = request[component + "_commit"]
                require(same_json(control_dependencies.get((component, request["request_id"])),
                                  dependency)
                        and dependency.get("schema") == f"mr3-{component}-phase-ack-v1"
                        and dependency.get("operation") == "commit"
                        and dependency.get("ok") is True and dependency.get("epoch") == epoch
                        and type(dependency.get("clock_ns")) is int
                        and dependency["clock_ns"] == dependency["target_time_ns"] == clock
                        and dependency.get("request_id") == request["request_id"],
                        "normal control commit lacks exact actually received dependencies")
            state, peer = request["state_commit"], request["peer_commit"]
            require(same_json(peer.get("state_commit"), state)
                    and type(state.get("state_sequence")) is int and state["state_sequence"] > 0
                    and type(peer.get("commit_sequence")) is int and peer["commit_sequence"] > 0
                    and isinstance(state.get("bundle_sha256"), str)
                    and re.fullmatch(r"[0-9a-f]{64}", state.get("bundle_sha256", ""))
                    and peer.get("bundle_sha256") == state["bundle_sha256"]
                    and clock not in control_commits, "normal control boundary changed/duplicated")
            control_commits[clock] = request
        elif kind == "control_ack":
            request = control_requests.get(value.get("request_id"))
            require(controlled and request is not None
                    and value.get("schema") == "mr3-motion-control-ack-v1"
                    and value.get("epoch") == epoch and value.get("ok") is True
                    and type(value.get("clock_ns")) is int
                    and value["clock_ns"] == value["target_time_ns"] == clock
                    and value["target_time_ns"] == request["target_time_ns"]
                    and value.get("operation") == request["operation"],
                    "invalid or failed actual motion control ACK")
            status = value["status"]
            key = completed_status(status, wall)
            require(same_json(completed_outputs.get(key), status),
                    "motion control ACK lacks actual completed output status")
            if status.get("phase_kind") != "stop" and request["operation"] == "commit":
                require(clock in control_commits, "normal control ACK lacks dependency commit")
            require(request["operation"] != "stop" or status.get("phase_kind") == "stop",
                    "stop control ACK returned normal motion")
            identity_key = value["request_id"]
            require(identity_key not in control_acks
                    or same_json(control_acks[identity_key], value),
                    "actual control ACK changed")
            control_acks[identity_key] = value
        elif kind == "control_abandoned":
            require(controlled and value.get("operation") != "stop"
                    and same_json(control_requests.get(value.get("request_id")), value),
                    "invalid abandoned normal control request")
        elif kind in ("control_ack_published", "control_cached_ack_published"):
            ack = value["ack"]
            start, end = value.get("publish_started_wall_monotonic_ns"), value.get(
                "publish_completed_wall_monotonic_ns")
            require(controlled and same_json(control_acks.get(ack.get("request_id")), ack)
                    and type(start) is int and type(end) is int and 0 <= start <= end <= wall,
                    "control ACK publication window lacks recorded actual ACK")
            control_publish_windows.setdefault(ack["request_id"], []).append((start, end))
        else:
            require(kind in ("clock_changed_during_decision", "output_observer_wait")
                    or kind == "configuration" and index == 1, "unknown/duplicate motion event")
    require(started and all(not queue for queue in queues.values()),
            "motion output observer did not close every published command FIFO")
    require(all(item["decisions"] and item["actual_outputs"] for item in stats.values()),
            "missing actual robot motion stream")
    phase = load("motion_phase_worker.jsonl", True)
    received, consumed = {}, []
    previous_wall, previous_clock = -1, -1
    for row in phase:
        ack = row["ack"]
        require(row["epoch"] == epoch and ack["epoch"] == epoch
                and ack["schema"] == "mr3-motion-safety-status-v1"
                and ack["completion_scope"] == "publication_and_local_topic_receipt"
                and type(ack["clock_ns"]) is int and type(ack["ready"]) is bool
                and set(ack["decision_sequences"]) == set(ROBOTS)
                and row["wall_monotonic_ns"] >= previous_wall,
                "motion phase identity/wall order mismatch")
        require("phase_kind" not in ack, "stop status overwrote the normal motion ACK channel")
        previous_wall = row["wall_monotonic_ns"]
        clock = ack["clock_ns"]
        for name, sequence in ack["decision_sequences"].items():
            require(type(sequence) is int and (name, sequence) in decisions,
                    "motion ACK sequence has no actual decision")
            decision = decisions[(name, sequence)]
            require(decision["clock_ns"] == clock and decision["ready"] == ack["ready"]
                    and decision["phase_kind"] == "normal"
                    and decision.get("actual_wall_ns", 10**30) <= row["wall_monotonic_ns"],
                    "motion ACK does not bind three same-clock published decisions")
            if controlled:
                require(same_json(ack.get("outputs", {}).get(name), {
                    "linear_x": decision["output"][0], "angular_z": decision["output"][1]}),
                    "normal phase outputs differ from exact published decisions")
        if row["kind"] == "ack_received":
            require(clock >= previous_clock, "motion ACK source clock regressed")
            if clock in received:
                require(same_json(received[clock], ack), "motion ACK changed at same clock")
            received[clock] = ack
            previous_clock = clock
        else:
            require(row["kind"] == "ack_consumed" and same_json(received.get(clock), ack)
                    and row["worker_clock_ns"] == row["worker_physical_ns"] == clock
                    and (not consumed or clock > consumed[-1]),
                    "motion ACK consumed without exact receipt")
            consumed.append(clock)
    require(sum(clock == release_ns for clock in consumed) == 1
            and received[release_ns]["ready"] is True,
            "motion initial release-clock healthy completion missing")
    physics = load("physics.jsonl", True)
    required = [row["end_time_ns"] for row in physics if row["end_time_ns"] > release_ns]
    controlled_result = None
    if controlled:
        controlled_result = audit_control_worker(
            load, epoch, physics, control_requests, control_acks, control_publish_windows,
            completed_outputs, output_publish_windows)
        stop_clocks = set(controlled_result["stop_clocks"])
        normal_clocks = {clock for clock in consumed if clock > release_ns}
        require(set(required) <= normal_clocks | stop_clocks
                and normal_clocks <= set(required)
                and {clock for clock in stop_clocks if clock > release_ns} <= set(required),
                "controlled normal/stop completion missed a native policy/cleanup quantum")
    else:
        require([clock for clock in consumed if clock > release_ns] == required,
                "motion ACK missed a native policy/cleanup quantum")
    stop_responses.extend(pending_stops.values())
    for response in stop_responses:
        response.pop("last_point", None)
    result = {
        "passed": True, "epoch": epoch, "records": len(rows), "robots": stats,
        "passed_nonzero_scope": ("complete canonical request passed; "
                                 "rotation-only filters separate"),
        "consumed_motion_phases": len(consumed), "stop_responses": stop_responses,
        "artifact_proof": proof, "source_proof": source_proof,
        "scope": "callback graph identity, raw input/received-state provenance, frozen-helper "
                 "replay and observed final Twist FIFO; no packet MessageInfo, independent "
                 "geometric proof or blanket physical stop guarantee",
    }
    if settled_enabled:
        result["settled_turn_replay"] = {
            "configured_contract": configuration["settled_turn_contract"],
            "qualifying_decisions": settled_activations,
            "scope": "Exact frozen tracker raw-odom/issued-target history, certificate, "
                     "activation and model-failure replay; not an independent proof of "
                     "the conditional continuous plant drift bound",
        }
    if controlled_result is not None:
        result["controlled_execution_replay"] = controlled_result
    if causal_selection:
        result["own_input_selection_replay"] = "latest_causal_v1; raw callback deque256"
    return result


def audit_episode(directory):
    directory = Path(directory)
    metadata, _ = read(directory, "metadata.json")
    root = Path(__file__).resolve().parents[7]
    helper, source_proof = load_frozen_helper(root, metadata["freeze"])
    return _audit_records(directory, helper, source_proof)
