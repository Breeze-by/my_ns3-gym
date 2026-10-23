"""Read-only validity of the fixed sparse three-robot rotation experiment.

VALID means that the requested waveform reached guard, storage and wheel
actuation with complete passive observations. It is not a plant/safety PASS.
Only the standard library is imported; this module cannot control a simulator.
"""

import argparse
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re


ROBOTS = ("tb1", "tb2", "tb3")
QUANTUM = 20_000_000
TICK = 1_000_000
TURN_START = 1_200_000_000
PULSE_START = 2_200_000_000
PULSE_END = 2_240_000_000
TURN_END = 2_740_000_000
CHAIN_END = 4_000_000_000
WINDOW_START = 2_120_000_000
WINDOW_END = 2_340_000_000
SPAWNS = {"tb1": (-1.6, 0., .01), "tb2": (0., 0., .01), "tb3": (1.6, 0., .01)}


class EvidenceError(ValueError):
    pass


def require(value, message):
    if not value:
        raise EvidenceError(message)


def integer(value):
    return type(value) is int


def ns(value):
    require(type(value) in (int, float), "timestamp is not numeric")
    result = Decimal(str(value)) * 1_000_000_000
    require(result.is_finite() and result == result.to_integral_value(),
            "timestamp is not exact finite nanoseconds")
    return int(result)


def angular(arm, relative):
    return (800 if TURN_START <= relative < TURN_END
            and not (arm == "pulse" and PULSE_START <= relative < PULSE_END) else 0)


def graph(identity):
    require(isinstance(identity, dict), "request publisher identity is not an object")
    endpoints = identity.get("endpoints", [])
    require(identity.get("valid") is True
            and identity.get("topic") == "/tb3/cmd_vel_unguarded"
            and len(endpoints) == 1
            and endpoints[0].get("namespace") == "/tb3"
            and endpoints[0].get("node") == "velocity_smoother"
            and endpoints[0].get("topic_type") == "geometry_msgs/msg/Twist"
            and identity.get("scope") == "graph_at_callback"
            and nonzero_gid(endpoints[0].get("endpoint_gid")),
            "request publisher is not the sole actual smoother")
    return endpoints[0]["endpoint_gid"]


def nonzero_gid(value):
    return (isinstance(value, str) and re.fullmatch(r"(?:[0-9a-f]{2})+", value) is not None
            and any(bytes.fromhex(value)))


def receipt_graph(identity):
    require(isinstance(identity, dict), "receipt publisher graph is not an object")
    endpoints = identity.get("endpoints", [])
    require(identity.get("scope") == "graph_at_callback_not_per_packet_identity"
            and identity.get("topic") == "/motion_safety/diagnostic_request_receipt"
            and len(endpoints) == 1 and endpoints[0].get("namespace") == "/"
            and endpoints[0].get("node") == "motion_safety"
            and endpoints[0].get("type") == "std_msgs/msg/String"
            and nonzero_gid(endpoints[0].get("endpoint_gid")),
            "receipt publisher is not the sole actual guard")
    return endpoints[0]["endpoint_gid"]


def _json(raw):
    def constant(value):
        raise EvidenceError("nonfinite JSON constant: " + value)

    return json.loads(raw, parse_constant=constant)


class Reader:
    def __init__(self, directory):
        self.directory = directory
        self.proof = {}

    def document(self, name):
        path = self.directory / name
        raw = path.read_bytes()
        self.proof[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        return _json(raw)

    def rows(self, name):
        path = self.directory / name
        digest = hashlib.sha256()
        before = path.stat()
        count = 0
        with path.open("rb") as source:
            for count, raw in enumerate(source, 1):
                require(raw.endswith(b"\n"), name + " has an incomplete final record")
                digest.update(raw)
                row = _json(raw)
                require(isinstance(row, dict), name + " record is not an object")
                yield row, {"file": name, "line": count,
                            "raw_line_sha256": hashlib.sha256(raw).hexdigest()}
        after = path.stat()
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
                name + " changed while being read")
        self.proof[name] = {"bytes": after.st_size, "lines": count,
                            "sha256": digest.hexdigest(), "source_unchanged_while_read": True}


def audit(directory, freeze, arm):
    directory = Path(directory).resolve()
    result = {"schema": "mr3-fixed-sparse-plant-stimulus-validity-v1",
              "directory": str(directory), "freeze": freeze, "arm": arm,
              "errors": [], "layers": {}, "raw_response": {},
              "scope": ("fixed sparse spawn, one target robot, constant request and 40ms pulse; "
                        "not a reproduction of V7 near-peer state/20ms timing, not a policy, "
                        "95percent, safety or plant-PASS claim")}
    reader = Reader(directory)
    origin = None
    epoch = None

    def layer(name, operation):
        review = {"incomplete": []}
        result["layers"][name] = review
        try:
            operation(review)
        except FileNotFoundError as error:
            review["incomplete"].append("missing artifact: " + str(error.filename))
        except (EvidenceError, ValueError, TypeError, KeyError, IndexError, OSError, ArithmeticError) as error:
            result["errors"].append(name + ": " + str(error))
        review["complete"] = not review["incomplete"] and not any(
            error.startswith(name + ":") for error in result["errors"])

    def identity(row, name):
        require(row.get("epoch") == epoch, name + " epoch mismatch")

    def context(review):
        nonlocal origin, epoch
        require(re.fullmatch(r"[0-9a-f]{40}", freeze) is not None, "exact source freeze required")
        require(arm in ("continuous", "pulse"), "unknown arm")
        metadata = reader.document("metadata.json")
        epoch = metadata["epoch"]
        require(metadata["freeze"] == freeze and metadata.get("plant_stimulus_arm") == arm,
                "native freeze/arm mismatch")
        first = None
        for row, _ in reader.rows("transitions.jsonl"):
            if first is None:
                first = row
        require(first and first["kind"] == "reset", "initial native reset missing")
        origin = first["info"]["release_time_ns"]
        require(integer(origin) and origin > 0 and first["info"]["epoch"] == epoch,
                "invalid actual task release")
        result.update(epoch=epoch, origin_ns=origin,
                      comparison_window_ns=[origin + WINDOW_START, origin + WINDOW_END],
                      chain_window_ns=[origin, origin + CHAIN_END])

    layer("context", context)
    if origin is None or epoch is None:
        result.update(status="INVALID_EVIDENCE", passed=False, source_artifacts=reader.proof)
        return result
    clocks = range(origin, origin + CHAIN_END, QUANTUM)
    stimulus = {}
    decisions = {}
    raw_requests = {}
    stored = {name: {} for name in ROBOTS}
    actuations = {name: [] for name in ROBOTS}
    advances = {}
    physics = {}

    def fixture_layer(review):
        binding = reader.document("plant_fixture_binding.json")
        require(binding.get("schema") == "mr3-fixed-sparse-plant-fixture-v1"
                and binding.get("epoch") == epoch and binding.get("arm") == arm,
                "fixed sparse fixture identity differs")
        require(isinstance(binding.get("world_path"), str) and binding["world_path"]
                and all(isinstance(binding.get(key), str)
                        and re.fullmatch(r"[0-9a-f]{64}", binding[key]) is not None
                        for key in ("world_sha256", "launch_source_sha256")),
                "fixed sparse fixture lacks source/world bindings")
        values = binding["spawn_argument_values"]
        require(set(values) == set(ROBOTS), "fixed sparse fixture robot set differs")
        for robot, position in SPAWNS.items():
            expected = dict(zip(("x_pose", "y_pose", "z_pose", "roll", "pitch", "yaw"),
                                (*position, 0., 0., 0.)))
            require(set(values[robot]) == set(expected)
                    and all(isinstance(values[robot][key], str)
                            and Decimal(values[robot][key]) == Decimal(str(value))
                            for key, value in expected.items()),
                    "fixed sparse spawn arguments differ: " + robot)
        review.update(binding=binding, actual_pose_admission_tolerance_m=.01,
                      actual_initial_minimum_peer_distance_m=1.5,
                      scope="initial fixture admission only; no safety or motion threshold changes")

    layer("fixed_sparse_fixture", fixture_layer)

    def request_layer(review):
        previous_wall = -1
        for row, ref in reader.rows("plant_stimulus_worker.jsonl"):
            identity(row, "stimulus")
            require(row.get("schema") == "mr3-plant-stimulus-worker-v1"
                    and row.get("arm") == arm and row.get("origin_ns") == origin,
                    "stimulus schema/arm/origin differs")
            clock = row["worker_physical_ns"]
            wall = row["wall_monotonic_ns"]
            require(integer(clock) and row["worker_clock_ns"] == clock
                    and row["relative_ns"] == clock - origin
                    and clock >= origin and (clock - origin) % QUANTUM == 0
                    and integer(wall) and wall >= previous_wall, "stimulus clock/wall regressed")
            previous_wall = wall
            if clock >= origin + CHAIN_END:
                continue
            kind = row["kind"]
            require(kind in ("source_request", "service_ack", "guard_request_receipt_received",
                             "boundary_consumed"), "unknown stimulus record kind")
            group = stimulus.setdefault(clock, {})
            require(kind not in group, "duplicate stimulus event at one boundary")
            group[kind] = (row, ref)
        gids = set()
        guard_gids = set()
        previous_input = None
        for clock in clocks:
            group = stimulus.get(clock, {})
            kinds = ("source_request", "service_ack", "guard_request_receipt_received", "boundary_consumed")
            if any(kind not in group for kind in kinds):
                review["incomplete"].append("publication/guard reception missing at " + str(clock))
                continue
            source = group["source_request"][0]
            request = source["request"]
            expected = {"epoch": epoch, "arm": arm,
                        "sequence": (clock - origin) // QUANTUM + 1, "clock_ns": clock,
                        "angular_millirad": angular(arm, clock - origin)}
            require(request == expected and all(integer(request[key]) for key in (
                "sequence", "clock_ns", "angular_millirad")),
                "request differs from the fixed prospective waveform")
            ack_row = group["service_ack"][0]
            ack = ack_row["ack"]
            require(ack.get("schema") == "mr3-smoother-diagnostic-ack-v1"
                    and all(ack.get(key) == value for key, value in expected.items())
                    and ack.get("robot") == "tb3" and ack.get("linear_x") == 0.
                    and ack.get("publication_clock_ns") == clock
                    and ack.get("output_topic") == "/tb3/cmd_vel_unguarded"
                    and ack.get("completion_scope") == "smoother_publication_only_not_guard_or_storage",
                    "smoother ACK identity/request boundary mismatch")
            started, ended = (ack[key] for key in ("publication_started_wall_monotonic_ns",
                                                  "publication_completed_wall_monotonic_ns"))
            require(integer(started) and integer(ended)
                    and source["wall_monotonic_ns"] <= started <= ended
                    <= ack_row["wall_monotonic_ns"], "smoother publication wall order differs")
            receipt_row = group["guard_request_receipt_received"][0]
            guard_gids.add(receipt_graph(receipt_row["receipt_publisher_graph"]))
            receipt = receipt_row["receipt"]
            require(receipt.get("schema") == "mr3-guard-diagnostic-receipt-v1"
                    and receipt.get("epoch") == epoch and receipt.get("robot") == "tb3"
                    and receipt.get("clock_ns") == clock and receipt.get("v") == 0.
                    and receipt.get("w") == expected["angular_millirad"] / 1000.
                    and receipt.get("supported") is True and integer(receipt.get("input_sequence"))
                    and receipt["input_sequence"] > 0,
                    "real guard reception receipt mismatch")
            gids.add(graph(receipt["publisher_identity"]))
            require(previous_input is None or receipt["input_sequence"] == previous_input + 1,
                    "real guard request sequence skipped/duplicated an input")
            previous_input = receipt["input_sequence"]
            consumed = group["boundary_consumed"][0]
            require(consumed["source_request"] == request and consumed["smoother_ack"] == ack
                    and consumed["guard_receipt"] == receipt
                    and consumed["wall_monotonic_ns"] >= max(ack_row["wall_monotonic_ns"],
                                                             receipt_row["wall_monotonic_ns"]),
                    "consumed boundary substituted publication/reception evidence")
            group["request"] = request
            group["guard_receipt"] = receipt
            group["publication_started"] = started
        require(len(gids) <= 1, "actual smoother endpoint changed within the run")
        require(len(guard_gids) <= 1, "actual guard receipt endpoint changed within the run")
        review.update(boundaries=len(stimulus), expected_boundaries=len(clocks),
                      smoother_gids=sorted(gids), guard_receipt_gids=sorted(guard_gids))

    layer("request_publication_and_reception", request_layer)

    def guard_layer(review):
        previous_sequence = 0
        receipts = {}
        for row, ref in reader.rows("motion_safety.jsonl"):
            identity(row, "guard")
            sequence = row["record_sequence"]
            require(integer(sequence) and sequence > previous_sequence, "guard record order differs")
            previous_sequence = sequence
            payload = row["payload"]
            if row["kind"] == "diagnostic_request_receipt" and payload["robot"] == "tb3":
                clock = payload["clock_ns"]
                if origin <= clock < origin + CHAIN_END:
                    key = (clock, payload["input_sequence"])
                    require(key not in receipts, "duplicate actual guard diagnostic receipt")
                    receipts[key] = (payload, row, ref)
            if row["kind"] == "raw_request" and payload["robot"] == "tb3":
                request = payload["request"]
                clock = ns(request["received_stamp"])
                if origin <= clock < origin + CHAIN_END:
                    key = (clock, request["sequence"])
                    require(key not in raw_requests, "duplicate actual guard raw request")
                    raw_requests[key] = (request, row, ref)
            if row["kind"] != "decision":
                continue
            clock, robot = payload["clock_ns"], payload["robot"]
            if origin <= clock < origin + CHAIN_END:
                require(robot in ROBOTS and (clock, robot) not in decisions,
                        "duplicate/unknown guard decision")
                decisions[(clock, robot)] = (payload, row, ref)
        summaries = []
        for clock in clocks:
            for robot in ROBOTS:
                found = decisions.get((clock, robot))
                if found is None:
                    review["incomplete"].append(f"missing guard decision {robot}/{clock}")
                    continue
                payload, row, ref = found
                expected = [0., angular(arm, clock - origin) / 1000. if robot == "tb3" else 0.]
                if payload["decision"]["output"] != expected:
                    review["incomplete"].append(f"guard changed waveform {robot}/{clock}: "
                                                 + str(payload["decision"]))
                if payload.get("ready") is not True:
                    review["incomplete"].append(f"guard not ready {robot}/{clock}")
                if robot != "tb3":
                    continue
                group = stimulus.get(clock, {})
                receipt = group.get("guard_receipt")
                request = payload.get("request")
                if receipt is None or not isinstance(request, dict):
                    review["incomplete"].append("guard selected request unavailable at " + str(clock))
                    continue
                raw = raw_requests.get((clock, receipt["input_sequence"]))
                actual_receipt = receipts.get((clock, receipt["input_sequence"]))
                if actual_receipt is None:
                    review["incomplete"].append("actual guard diagnostic receipt missing at " + str(clock))
                    continue
                require(actual_receipt[0] == receipt,
                        "worker receipt differs from complete actual guard receipt object")
                if raw is None or request != raw[0] or request.get("sequence") != receipt["input_sequence"]:
                    review["incomplete"].append("guard selected an older/different actual request at " + str(clock))
                    continue
                require(request["v"] == 0. and request["w"] == expected[1]
                        and request["supported"] is True and graph(request["publisher_identity"])
                        == graph(receipt["publisher_identity"]), "guard request identity differs")
                require(group["publication_started"] <= raw[1]["wall_monotonic_ns"]
                        <= row["wall_monotonic_ns"]
                        and raw[1]["wall_monotonic_ns"] <= actual_receipt[1]["wall_monotonic_ns"]
                        <= row["wall_monotonic_ns"]
                        and raw[1]["wall_monotonic_ns"]
                        <= group["guard_request_receipt_received"][0]["wall_monotonic_ns"]
                        <= row["wall_monotonic_ns"], "publication/real guard callback order differs")
                if TURN_START <= clock - origin < TURN_END:
                    if payload["decision"].get("reason") != "clear":
                        review["incomplete"].append("far-peer clear precondition absent at " + str(clock))
                if WINDOW_START <= clock - origin < WINDOW_END:
                    summaries.append({"clock_ns": clock, "request_sequence": request["sequence"],
                                      "decision_sequence": payload["decision_sequence"],
                                      "decision": payload["decision"], "reference": ref,
                                      "actual_receipt_reference": actual_receipt[2]})
        review["comparison_decisions"] = summaries

    layer("actual_guard_decisions", guard_layer)

    def storage_layer(review):
        for robot in ROBOTS:
            commands = {}
            for row, ref in reader.rows("drive_" + robot + ".jsonl"):
                identity(row, "native driver")
                require(row.get("robot") == robot, "native driver robot mismatch")
                target = row.get("target_clock_ns")
                if not integer(target) or not origin <= target < origin + CHAIN_END:
                    continue
                if row["kind"] == "command_received":
                    require(target not in commands, "duplicate actual native stored target")
                    commands[target] = row
                elif row["kind"] == "status_publish":
                    require(target not in stored[robot], "duplicate native storage status")
                    stored[robot][target] = (row["status"], row, ref)
                elif row["kind"] == "actuation":
                    actuations[robot].append((row, ref))
            for clock in clocks:
                decision = decisions.get((clock, robot))
                status = stored[robot].get(clock)
                command = commands.get(clock)
                if not decision or not status or not command:
                    review["incomplete"].append(f"guard/native storage join missing {robot}/{clock}")
                    continue
                payload = decision[0]
                ack = status[0]
                output = payload["decision"]["output"]
                require(ack.get("schema") == "mr3-drive-target-consumed-v1"
                        and ack.get("epoch") == epoch and ack.get("robot") == robot
                        and ack.get("clock_ns") == ack.get("source_clock_ns") == clock
                        and ack.get("decision_sequence") == payload["decision_sequence"]
                        and [ack.get("linear_x"), ack.get("angular_z")] == output
                        and command["target_decision_sequence"] == ack["decision_sequence"]
                        and command["cmd_seq"] == ack["cmd_seq"]
                        and [command["desired_v"], command["desired_w"]] == output,
                        "native stored target differs from actual guard decision")
        for row, _ in reader.rows("physics.jsonl"):
            identity(row, "physics")
            if row.get("steps") == 20:
                require(row["request_id"] not in physics, "duplicate physical request identity")
                physics[row["request_id"]] = row
        bootstrap = []
        for row, _ in reader.rows("drive_phase_worker.jsonl"):
            identity(row, "drive phase")
            if row["kind"] != "advance_permitted":
                continue
            clock = row["start_time_ns"]
            if row.get("control_kind") == "bootstrap_zero":
                bootstrap.append(row)
            if origin <= clock < origin + CHAIN_END:
                require(clock not in advances, "duplicate physical advance at one boundary")
                advances[clock] = row
        require(len(bootstrap) == 1 and bootstrap[0]["start_time_ns"] + QUANTUM == origin,
                "origin lacks the actual unique bootstrap physical boundary")
        boot = physics.get(bootstrap[0]["request_id"])
        require(boot is not None and boot["ok"] is True and boot["paused"] is True
                and boot["start_time_ns"] == origin - QUANTUM and boot["end_time_ns"] == origin
                and boot["step_ns"] == TICK
                and boot["end_iterations"] - boot["start_iterations"] == 20,
                "bootstrap advance lacks its actual completed physical receipt")
        for clock in clocks:
            advance = advances.get(clock)
            if advance is None:
                review["incomplete"].append("physical advance missing at " + str(clock))
                continue
            completed = physics.get(advance["request_id"])
            if completed is None:
                review["incomplete"].append("physical completion missing at " + str(clock))
                continue
            require(advance.get("control_kind") == "normal" and advance.get("steps") == 20
                    and completed["ok"] is True and completed["paused"] is True
                    and completed["start_time_ns"] == clock
                    and completed["end_time_ns"] == clock + QUANTUM
                    and completed["step_ns"] == TICK
                    and completed["end_iterations"] - completed["start_iterations"] == 20,
                    "actual physical quantum differs")
            for robot in ROBOTS:
                status = stored[robot].get(clock)
                if status is not None:
                    require(advance["receipts"][robot] == status[0]
                            and advance["expected_motion"]["decision_sequences"][robot]
                            == status[0]["decision_sequence"]
                            and advance["expected_motion"]["outputs"][robot]
                            == {"linear_x": status[0]["linear_x"], "angular_z": status[0]["angular_z"]},
                            "physical advance substituted native storage receipts")
        review.update(expected_boundaries=len(clocks), actual_advances=len(advances))

    layer("native_storage_and_physical_advance", storage_layer)

    def actuation_layer(review):
        rows = []
        for robot in ROBOTS:
            for row, ref in actuations[robot]:
                target = row["target_clock_ns"]
                status = stored[robot].get(target)
                if status is None:
                    review["incomplete"].append("actuation target storage missing: " + robot)
                    continue
                ack = status[0]
                require(row["sim_time_ns"] >= target
                        and row["cmd_seq"] == ack["cmd_seq"]
                        and row["target_decision_sequence"] == ack["decision_sequence"]
                        and [row["desired_v"], row["desired_w"]]
                        == [ack["linear_x"], ack["angular_z"]], "wheel actuation target identity differs")
                if robot == "tb3" and origin <= row["sim_time_ns"] < origin + CHAIN_END:
                    rows.append({"sim_time_ns": row["sim_time_ns"], "target_clock_ns": target,
                                 "desired_v": row["desired_v"], "desired_w": row["desired_w"],
                                 "current_rim_mps": row["current_rim_mps"],
                                 "applied_rim_mps": row["applied_rim_mps"], "reference": ref})
        def present(begin, end, w):
            return any(origin + begin <= row["sim_time_ns"] < origin + end
                       and row["desired_v"] == 0. and row["desired_w"] == w for row in rows)
        for label, begin, end, w in (
                ("common initial zero", 0, TURN_START, 0.),
                ("common turn", TURN_START, PULSE_START, .8),
                ("pulse/continuous intervention", PULSE_START, PULSE_END, 0. if arm == "pulse" else .8),
                ("recovery turn", PULSE_END, PULSE_END + 100_000_000, .8),
                ("final zero", TURN_END, TURN_END + 100_000_000, 0.)):
            if not present(begin, end, w):
                review["incomplete"].append("wheel update did not consume " + label)
        review["actual_target_robot_wheel_updates"] = rows

    layer("actual_wheel_actuation", actuation_layer)

    def observer_layer(review):
        binding = reader.document("physics_diagnostic_binding.json")
        require(binding.get("schema") == "mr3-physics-diagnostic-binding-v2"
                and binding.get("epoch") == epoch and binding.get("mode") == "observer_only"
                and binding.get("physics_intervention") == "none_observer_only"
                and binding.get("observer_paused_only") is True
                and "profile_library" not in binding and "profile_output_path" not in binding,
                "observer-only no-intervention binding differs")
        source_sha = binding["observer_library"]["source_sha256"]
        initial_poses = {}
        for robot in ROBOTS:
            pending = None
            previous_clock = origin
            count = 0
            samples = []
            max_speed = 0.
            threshold_count = 0
            config_count = 0
            previous_sequence = 0
            for row, ref in reader.rows("physics_" + robot + ".jsonl"):
                identity(row, "passive observer")
                require(row.get("schema") == "mr3-stop-response-observer-v1"
                        and row.get("robot") == robot, "observer schema/robot differs")
                sequence = row["record_sequence"]
                require(integer(sequence) and sequence > previous_sequence, "observer record order differs")
                previous_sequence = sequence
                if row["kind"] == "configuration":
                    config_count += 1
                    require(row.get("paused_only") is True and row.get("read_only") is True
                            and row.get("compiled_source_sha256") == source_sha
                            and row.get("physics_type") == "ode"
                            and row.get("max_step_size_sec") == .001
                            and row["native_ode"]["available"] is True
                            and row["native_ode"]["values"]["iters"] == 150,
                            "observer actual readback/source/paused-only configuration differs")
                    continue
                clock = row.get("sim_time_ns")
                if row["kind"] != "sample" or not integer(clock) or not origin < clock <= origin + CHAIN_END:
                    continue
                require(row.get("measurements_finite") is True and row.get("physics_enabled") is True
                        and row["native_ode"]["available"] is True
                        and row["native_ode"]["values"]["iters"] == 150,
                        "observer actual sample/ODE150 readback differs")
                phase = row["phase"]
                if phase == "before_physics_after_collision":
                    require(pending is None, "unclosed observer before/after pair")
                    pending = row
                    continue
                require(phase == "world_update_end_after_physics_and_pose_propagation"
                        and pending is not None and row["sim_time_ns"] == pending["sim_time_ns"]
                        and row["world_iterations"] == pending["world_iterations"]
                        and row["pair_sequence"] == pending["pair_sequence"]
                        and row["before_record_sequence"] == pending["record_sequence"],
                        "passive observer pair identity differs")
                pending = None
                if clock != previous_clock + TICK:
                    review["incomplete"].append(f"1ms observer gap {robot}/{previous_clock}->{clock}")
                previous_clock = clock
                count += 1
                model = row["model"]
                require(model.get("name") == robot, "observer actual model identity differs")
                if count == 1:
                    position = model["world_pose"]["position_xyz"]
                    require(len(position) == 3 and all(type(value) in (int, float)
                            and math.isfinite(value) for value in position), "invalid native initial pose")
                    drift = math.dist(position, SPAWNS[robot])
                    initial_poses[robot] = {"clock_ns": clock, "position_xyz": position,
                                            "distance_from_spawn_m": drift, "reference": ref}
                    if clock != origin + TICK or drift > .01:
                        review["incomplete"].append("fixed sparse initial pose not realized: " + robot)
                velocity = model["world_linear_velocity_xyz"]
                require(len(velocity) == 3 and all(type(value) in (int, float)
                        and math.isfinite(value) for value in velocity), "nonfinite native body velocity")
                speed = math.hypot(velocity[0], velocity[1])
                max_speed = max(max_speed, speed)
                threshold_count += speed > .01
                if origin + WINDOW_START < clock <= origin + WINDOW_END:
                    samples.append({"clock_ns": clock, "model": model,
                                    "joints_right_left": row["joints_right_left"], "reference": ref})
            require(config_count == 1, "observer configuration is not unique")
            if pending is not None or count != CHAIN_END // TICK or previous_clock != origin + CHAIN_END:
                review["incomplete"].append("observer full origin/recovery coverage incomplete: " + robot)
            result["raw_response"][robot] = {
                "complete_1ms_pairs": count, "max_planar_model_origin_speed_mps": max_speed,
                "samples_above_point01_mps": threshold_count, "comparison_samples": samples,
                "interpretation": ("raw passive physical response; .01 is a descriptive reference here; "
                                   "far-peer clear guard did not invoke the settled-turn exception. "
                                   "No body steady-state or safety PASS is inferred from request .8")}
        distances = {left + "/" + right: math.dist(initial_poses[left]["position_xyz"][:2],
                                                   initial_poses[right]["position_xyz"][:2])
                     for index, left in enumerate(ROBOTS) for right in ROBOTS[index + 1:]
                     if left in initial_poses and right in initial_poses}
        if len(initial_poses) != 3 or min(distances.values(), default=0.) < 1.5:
            review["incomplete"].append("actual initial sparse peer separation below 1.5m/unavailable")
        review.update(actual_initial_poses=initial_poses, actual_initial_planar_peer_distances_m=distances,
                      initial_pose_admission_scope="1cm engineering fixture tolerance only; not a safety threshold")

    layer("passive_1ms_observation", observer_layer)
    result["source_artifacts"] = reader.proof
    result["status"] = ("INVALID_EVIDENCE" if result["errors"] else
                        "VALID" if all(row["complete"] for row in result["layers"].values()) else "INCOMPLETE")
    result["passed"] = result["status"] == "VALID"
    result["plant_pass_claimed"] = False
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--arm", required=True, choices=("continuous", "pulse"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output exists; choose a new evidence path")
    result = audit(args.directory, args.freeze, args.arm)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "passed": result["passed"],
                      "errors": result["errors"], "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
