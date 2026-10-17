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


def own_state(name, sources, sequences, epoch):
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
    return {"robot": name, "name": name, "epoch": epoch, "valid": True,
            "x": translation["x"] + math.cos(angle) * point["x"] - math.sin(angle) * point["y"],
            "y": translation["y"] + math.sin(angle) * point["x"] + math.cos(angle) * point["y"],
            "yaw": math.atan2(math.sin(angle + yaw(orientation)),
                              math.cos(angle + yaw(orientation))),
            "v": odom["twist"]["twist"]["linear"]["x"],
            "w": odom["twist"]["twist"]["angular"]["z"],
            "odom_source_stamp": odom_time, "tf_source_stamp": tf_time,
            "tf_validity_stamp": validity, "tf_validity_lead_sec": .2,
            "source_stamp": min(odom_time, tf_time),
            "input_sequences": {key: sequences[key] for key in ("odom", "tf")}}


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


def command_boundary(decision, request):
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
    require(rotation["allow"] is True and rotation["reason"] == "clear"
            and rotation.get("component_filter") is None
            and rotation.get("command_normalization") is None
            and rotation["output"] == output == [0., canonical[1]],
            "component filter changed angular direction or lacks clear rotation check")


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
    sources = {name: {} for name in ROBOTS}
    sequences = {name: dict.fromkeys(("odom", "tf", "request", "decision"), 0) for name in ROBOTS}
    requests, states, decisions = {}, {}, {}
    queues = {name: deque() for name in ROBOTS}
    stats = {name: {"nonzero_requests": 0, "passed_nonzero": 0, "stopped_nonzero": 0,
                    "rotation_only_filtered": 0,
                    "decisions": 0, "actual_outputs": 0, "near_events": 0,
                    "maximum_measured_abs_v": 0., "maximum_measured_abs_w": 0.,
                    "minimum_body_margin_m": None} for name in ROBOTS}
    started, halted, stop_ns = False, None, None
    previous_wall, previous_clock = -1, -1
    pending_stops, stop_responses = {}, []
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
            if stream == "tf":
                require(value["message"]["header"]["frame_id"].lstrip("/") == "map"
                        and value["message"]["child_frame_id"].lstrip("/") == "odom",
                        "own TF is not local map-to-odom")
            else:
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
                require(twist_pair(value["twist"]) == [request["v"], request["w"]],
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
            started = True
        elif kind == "stop_request":
            stop_ns = clock
        elif kind == "terminal":
            require(value["epoch"] == epoch, "motion terminal epoch mismatch")
            stop_ns = ns(value["end_sim_time_sec"])
        elif kind in ("invalid_terminal_notice", "failure"):
            halted = ("invalid_terminal_notice" if kind == "invalid_terminal_notice"
                      else "external_safety_failure")
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
            own = own_state(name, sources[name], sequences[name], epoch)
            peers = {peer: states.get(peer) for peer in ROBOTS if peer != name}
            request = requests.get(name)
            require(value["own_state"] == own,
                    "own state differs from raw local odom/TF input sequences")
            require(value["received_peers"] == peers,
                    "peer geometry bypassed original received states")
            require(value["request"] == request,
                    "decision request differs from raw callback sequence/content/GID")
            if value["ready"]:
                require(all(helper.valid_state(
                    own_state(peer, sources[peer], sequences[peer], epoch),
                    decision_clock / 1e9, epoch)
                            and helper.valid_state(states.get(peer), decision_clock / 1e9, epoch)
                            for peer in ROBOTS), "ready motion decision used unhealthy source")
            elif started and halted is None:
                halted = "motion_state_or_topology_unavailable"
            if not value["ready"]:
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
            command_boundary(value["decision"], request)
            require(value["decision"] == expected,
                    "motion decision differs from frozen helper replay")
            key = (name, value["decision_sequence"])
            decisions[key] = {"clock_ns": decision_clock, "ready": value["ready"], "wall_ns": wall}
            queues[name].append((expected["output"], key))
            item = stats[name]
            item["decisions"] += 1
            nonzero = bool(request and request["supported"] and (request["v"] or request["w"]))
            item["nonzero_requests"] += nonzero
            filtered = expected.get("component_filter") is not None
            item["passed_nonzero"] += nonzero and expected["allow"] and not filtered
            item["stopped_nonzero"] += nonzero and not expected["allow"]
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
        else:
            require(kind in ("configuration", "clock_changed_during_decision",
                             "output_observer_wait"), "unknown motion event")
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
        previous_wall = row["wall_monotonic_ns"]
        clock = ack["clock_ns"]
        for name, sequence in ack["decision_sequences"].items():
            require(type(sequence) is int and (name, sequence) in decisions,
                    "motion ACK sequence has no actual decision")
            decision = decisions[(name, sequence)]
            require(decision["clock_ns"] == clock and decision["ready"] == ack["ready"]
                    and decision.get("actual_wall_ns", 10**30) <= row["wall_monotonic_ns"],
                    "motion ACK does not bind three same-clock published decisions")
        if row["kind"] == "ack_received":
            require(clock >= previous_clock, "motion ACK source clock regressed")
            if clock in received:
                require(received[clock] == ack, "motion ACK changed at same clock")
            received[clock] = ack
            previous_clock = clock
        else:
            require(row["kind"] == "ack_consumed" and received.get(clock) == ack
                    and row["worker_clock_ns"] == row["worker_physical_ns"] == clock
                    and (not consumed or clock > consumed[-1]),
                    "motion ACK consumed without exact receipt")
            consumed.append(clock)
    require(sum(clock == release_ns for clock in consumed) == 1
            and received[release_ns]["ready"] is True,
            "motion initial release-clock healthy completion missing")
    physics = load("physics.jsonl", True)
    required = [row["end_time_ns"] for row in physics if row["end_time_ns"] > release_ns]
    require([clock for clock in consumed if clock > release_ns] == required,
            "motion ACK missed a native policy/cleanup quantum")
    stop_responses.extend(pending_stops.values())
    for response in stop_responses:
        response.pop("last_point", None)
    return {"passed": True, "epoch": epoch, "records": len(rows), "robots": stats,
            "passed_nonzero_scope": ("complete canonical request passed; "
                                     "rotation-only filters separate"),
            "consumed_motion_phases": len(consumed), "stop_responses": stop_responses,
            "artifact_proof": proof, "source_proof": source_proof,
            "scope": "callback graph identity, raw input/received-state provenance, frozen-helper "
                     "replay and observed final Twist FIFO; no packet MessageInfo, independent "
                     "geometric proof or blanket physical stop guarantee"}


def audit_episode(directory):
    directory = Path(directory)
    metadata, _ = read(directory, "metadata.json")
    root = Path(__file__).resolve().parents[7]
    helper, source_proof = load_frozen_helper(root, metadata["freeze"])
    return _audit_records(directory, helper, source_proof)
