"""Small raw-input/received-peer/FIFO consumer fixtures, with deliberate mutations."""

import copy
import gzip
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest

from mr3_learning.audit_motion import PURE_DIRECTORY, ROBOTS, _audit_records, command_boundary


def helper_module():
    root = Path(__file__).resolve().parents[8]
    names = ["multi_robot_exploration", "multi_robot_exploration.mr3_episode",
             "multi_robot_exploration.mr3_motion_safety"]
    previous = {name: sys.modules.get(name) for name in names}
    try:
        package = ModuleType(names[0])
        package.__path__ = []
        sys.modules[names[0]] = package
        for name in names[1:]:
            path = root / PURE_DIRECTORY / (name.rsplit(".", 1)[1] + ".py")
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        return module
    finally:
        for name in names:
            if previous[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous[name]


def twist(v=0., w=0.):
    return {"linear": {"x": v, "y": 0., "z": 0.},
            "angular": {"x": 0., "y": 0., "z": w}}


def write_fixture(directory, helper):
    epoch = "fixture-motion"
    endpoints = {f"/{name}/cmd_vel": [{"namespace": "/", "node": "motion_safety",
                 "topic_type": "geometry_msgs/msg/Twist", "endpoint_gid": f"{index + 1:032x}"}]
                 for index, name in enumerate(ROBOTS)}
    own, received, rows, requests = {}, {}, [], {}

    def record(kind, payload, clock=1.):
        rows.append({"schema": "mr3-motion-safety-v1", "epoch": epoch,
                     "record_sequence": len(rows) + 1, "kind": kind, "payload": payload,
                     "sim_time_sec": clock, "wall_monotonic_ns": 1000 + len(rows) * 10})

    identity_scope = "graph_at_callback; packet MessageInfo unavailable on installed Humble"
    record("configuration", {"robots": list(ROBOTS), "twist_source_stamp_available": False,
                             "publisher_identity_scope": identity_scope})
    for index, name in enumerate(ROBOTS):
        point = {"x": index * 3., "y": 0., "z": 0.}
        rotation = {"x": 0., "y": 0., "z": 0., "w": 1.}
        odom = {"header": {"frame_id": "odom", "stamp": {"sec": 1, "nanosec": 0}},
                "child_frame_id": "base_footprint",
                "pose": {"pose": {"position": point, "orientation": rotation}},
                "twist": {"twist": twist()}}
        transform = {"header": {"frame_id": "map", "stamp": {"sec": 1, "nanosec": 200000000}},
                     "child_frame_id": "odom", "transform": {
                         "translation": {"x": 0., "y": 0., "z": 0.}, "rotation": rotation}}
        record("own_odom", {"robot": name, "input_sequence": 1, "message": odom})
        record("own_tf", {"robot": name, "input_sequence": 1, "message": transform})
        own[name] = {"robot": name, "name": name, "epoch": epoch, "valid": True,
                     "x": index * 3., "y": 0., "yaw": 0., "v": 0., "w": 0.,
                     "odom_source_stamp": 1., "tf_source_stamp": 1., "tf_validity_stamp": 1.2,
                     "tf_validity_lead_sec": .2, "source_stamp": 1.,
                     "input_sequences": {"odom": 1, "tf": 1}, "planar_speed_mps": 0.}
        received[name] = {**copy.deepcopy(own[name]), "x": 100. + index * 3.,
                          "odometry": copy.deepcopy(odom)}
    record("received_states", {"epoch": epoch, "robots": list(received.values())})
    for index, name in enumerate(ROBOTS):
        request_identity = {
            "scope": "graph_at_callback", "topic": f"/{name}/cmd_vel_unguarded", "valid": True,
            "endpoints": [{"namespace": f"/{name}", "node": "velocity_smoother",
                           "topic_type": "geometry_msgs/msg/Twist",
                           "endpoint_gid": f"{index + 10:032x}"}]}
        requests[name] = {"v": .2, "w": 0., "received_stamp": 1., "sequence": 1,
                          "supported": True, "publisher_identity": request_identity}
        record("raw_request", {"robot": name, "request": requests[name], "twist": twist(.2)})
    phase = []
    for sequence, clock in ((1, 1.), (2, 1.02)):
        if sequence == 2:
            record("release", {"stamp": 1.})
        for name in ROBOTS:
            peers = {peer: value for peer, value in received.items() if peer != name}
            decision = (helper.guard_motion([.2, 0.], own[name], peers, clock, epoch)
                        if sequence == 2 else {"allow": False, "reason": "before_release",
                                               "output": [0., 0.], "minimum_margin_m": None})
            record("decision", {"robot": name, "clock_ns": round(clock * 1e9),
                                "decision_sequence": sequence, "request": requests[name],
                                "own_state": own[name], "received_peers": peers,
                                "decision": decision, "started": sequence == 2,
                                "ready": True}, clock)
        for name in ROBOTS:
            record("actual_cmd_vel", {
                "robot": name, "twist": twist(.2 if sequence == 2 else 0.),
                "observed_decision_sequence": sequence, "publisher_identity": {
                    "scope": "graph_at_callback", "topic": f"/{name}/cmd_vel", "valid": True,
                    "endpoints": endpoints[f"/{name}/cmd_vel"]}}, clock)
        ack = {"schema": "mr3-motion-safety-status-v1", "epoch": epoch,
               "clock_ns": round(clock * 1e9), "ready": True,
               "completion_scope": "publication_and_local_topic_receipt",
               "decision_sequences": dict.fromkeys(ROBOTS, sequence)}
        for index, kind in enumerate(("ack_received", "ack_consumed")):
            phase.append({"kind": kind, "epoch": epoch, "ack": ack,
                          "worker_clock_ns": round(clock * 1e9),
                          "worker_physical_ns": round(clock * 1e9),
                          "wall_monotonic_ns": rows[-1]["wall_monotonic_ns"] + 1 + index})
    files = {"metadata.json": {"epoch": epoch, "freeze": "0" * 40},
             "motion_topology.json": {"schema": "mr3-motion-output-topology-v1", "epoch": epoch,
                                      "stamp": 1., "endpoints": endpoints},
             "transitions.jsonl": [
                 {"kind": "reset", "snapshot": {"epoch": epoch, "source_stamp": 1.},
                  "info": {"release_time_ns": 1000000000}},
                 {"kind": "step", "snapshot": {"epoch": epoch, "source_stamp": 1.02}}],
             "physics.jsonl": [{"end_time_ns": 1020000000}],
             "motion_safety.jsonl": rows, "motion_phase_worker.jsonl": phase}
    write_files(directory, files)
    return json.loads(json.dumps(files))


def write_files(directory, files):
    for name, value in files.items():
        payload = ("\n".join(json.dumps(row, allow_nan=False) for row in value) + "\n"
                   if name.endswith("jsonl") else json.dumps(value, allow_nan=False))
        (directory / name).write_text(payload)


def write_settled_fixture(directory, helper, mixed=False, prewarm=False):
    """A full zero-output prefix, raw rest sources and two actual turn quanta."""
    epoch, release = "fixture-settled-motion", 1_000_000_000
    original = write_fixture(directory, helper)
    endpoints = original["motion_topology.json"]["endpoints"]
    rows, phase = [], []
    trackers = {name: helper.SettledTurnTracker() for name in ROBOTS}

    def record(kind, payload, clock):
        rows.append({"schema": "mr3-motion-safety-v1", "epoch": epoch,
                     "record_sequence": len(rows) + 1, "kind": kind, "payload": payload,
                     "sim_time_sec": clock / 1e9, "wall_monotonic_ns": 1000 + len(rows) * 10})

    start = 20_000_000 if prewarm else 1_000_000_000
    record("configuration", {
        "robots": list(ROBOTS), "twist_source_stamp_available": False,
        "publisher_identity_scope": "graph_at_callback; packet MessageInfo unavailable "
                                    "on installed Humble",
        "settled_turn_contract": "mr3-settled-turn-v1; synthetic complete source history",
    }, start)
    for sequence, clock in enumerate(range(start, 2_000_000_001, 20_000_000), 1):
        own, requests, raw_odometry = {}, {}, {}
        for index, name in enumerate(ROBOTS):
            v = .001 if name == "tb1" else 0.
            x, y = ((.001 * (clock / 1e9 - 1.), 0.) if name == "tb1" else
                    ((.75, 0.) if name == "tb2" else (4., 4.)))
            rotation = {"x": 0., "y": 0., "z": 0., "w": 1.}
            sec, nano = divmod(clock, 10**9)
            tf_sec, tf_nano = divmod(clock + 200_000_000, 10**9)
            odom = {"header": {"frame_id": "odom", "stamp": {"sec": sec, "nanosec": nano}},
                    "child_frame_id": "base_footprint",
                    "pose": {"pose": {"position": {"x": x, "y": y, "z": 0.},
                                      "orientation": rotation}},
                    "twist": {"twist": twist(v)}}
            transform = {"header": {"frame_id": "map", "stamp": {
                "sec": tf_sec, "nanosec": tf_nano}}, "child_frame_id": "odom", "transform": {
                "translation": {"x": 0., "y": 0., "z": 0.}, "rotation": rotation}}
            record("own_odom", {"robot": name, "input_sequence": sequence,
                                "message": odom}, clock)
            raw_odometry[name] = copy.deepcopy(odom)
            trackers[name].observe(odom, sequence)
            record("own_tf", {"robot": name, "input_sequence": sequence,
                              "message": transform}, clock)
            source = sec + nano / 1e9
            validity = tf_sec + tf_nano / 1e9
            own[name] = {"robot": name, "name": name, "epoch": epoch, "valid": True,
                         "x": x, "y": y, "yaw": 0., "v": v, "w": 0.,
                         "odom_source_stamp": source, "tf_source_stamp": validity - .2,
                         "tf_validity_stamp": validity, "tf_validity_lead_sec": .2,
                         "source_stamp": min(source, validity - .2),
                         "input_sequences": {"odom": sequence, "tf": sequence}}
        received = {name: {**copy.deepcopy(state), "odometry": raw_odometry[name]}
                    for name, state in own.items()}
        record("received_states", {"epoch": epoch, "robots": list(received.values())}, clock)
        for index, name in enumerate(ROBOTS):
            v, w = ((.2 if mixed else 0., .5) if name == "tb1" else (0., 0.))
            request_identity = {
                "scope": "graph_at_callback", "topic": f"/{name}/cmd_vel_unguarded",
                "valid": True,
                "endpoints": [{
                    "namespace": f"/{name}", "node": "velocity_smoother",
                    "topic_type": "geometry_msgs/msg/Twist",
                    "endpoint_gid": f"{index + 10:032x}",
                }],
            }
            requests[name] = {
                "v": v, "w": w, "received_stamp": clock / 1e9, "sequence": sequence,
                "supported": True, "publisher_identity": request_identity,
            }
            record("raw_request", {"robot": name, "request": requests[name],
                                   "twist": twist(v, w)}, clock)
            own[name]["planar_speed_mps"] = math.hypot(own[name]["v"], 0.)
            own[name]["settled_turn"] = trackers[name].certificate(clock)
        outputs = {}
        for name in ROBOTS:
            request = requests[name]
            peers = {peer: value for peer, value in received.items() if peer != name}
            if clock > release:
                decision = helper.guard_motion(
                    [request["v"], request["w"]], own[name], peers, clock / 1e9, epoch)
            else:
                decision = {"allow": False, "reason": "before_release", "output": [0., 0.],
                            "minimum_margin_m": None}
            rotation = (decision.get("component_filter") or {}).get("rotation_check", {})
            if (decision["reason"] == "settled_turn_drift_reserve"
                    or rotation.get("reason") == "settled_turn_drift_reserve"):
                trackers[name].activate(clock)
            trackers[name].output(decision["output"][0], clock, sequence)
            record("decision", {"robot": name, "clock_ns": clock,
                                "decision_sequence": sequence, "request": request,
                                "own_state": copy.deepcopy(own[name]), "received_peers": peers,
                                "decision": decision, "started": clock > release,
                                "ready": True}, clock)
            outputs[name] = decision["output"]
        for name in ROBOTS:
            record("actual_cmd_vel", {
                "robot": name, "twist": twist(*outputs[name]),
                "observed_decision_sequence": sequence, "publisher_identity": {
                    "scope": "graph_at_callback", "topic": f"/{name}/cmd_vel", "valid": True,
                    "endpoints": endpoints[f"/{name}/cmd_vel"]}}, clock)
        if clock >= release:
            ack = {"schema": "mr3-motion-safety-status-v1", "epoch": epoch,
                   "clock_ns": clock, "ready": True,
                   "completion_scope": "publication_and_local_topic_receipt",
                   "decision_sequences": dict.fromkeys(ROBOTS, sequence),
                   "outputs": {name: dict(zip(("linear_x", "angular_z"), outputs[name]))
                               for name in ROBOTS}}
            for offset, kind in enumerate(("ack_received", "ack_consumed"), 1):
                phase.append({"kind": kind, "epoch": epoch, "ack": copy.deepcopy(ack),
                              "worker_clock_ns": clock, "worker_physical_ns": clock,
                              "wall_monotonic_ns": rows[-1]["wall_monotonic_ns"] + offset})
        if clock == release:
            record("release", {"stamp": release / 1e9}, clock)
            for tracker in trackers.values():
                tracker.release(release)
    files = {"metadata.json": {"epoch": epoch, "freeze": "0" * 40},
             "motion_topology.json": {"schema": "mr3-motion-output-topology-v1",
                                      "epoch": epoch, "stamp": release / 1e9,
                                      "endpoints": endpoints},
             "transitions.jsonl": [{"kind": "reset", "snapshot": {"epoch": epoch},
                                    "info": {"release_time_ns": release}},
                                   {"kind": "step", "snapshot": {"epoch": epoch}}],
             "physics.jsonl": [{"end_time_ns": clock}
                               for clock in range(release + 20_000_000,
                                                  2_000_000_001, 20_000_000)],
             "motion_safety.jsonl": rows, "motion_phase_worker.jsonl": phase}
    write_files(directory, files)
    return files


class MotionAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = helper_module()

    def test_settled_raw_history_activation_and_mixed_turn_fifo_are_replayed(self):
        for mixed in (False, True):
            with self.subTest(mixed=mixed), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = write_settled_fixture(directory, self.helper, mixed)
                result = _audit_records(directory, self.helper, {})
                self.assertTrue(result["passed"])
                self.assertEqual(result["settled_turn_replay"]["qualifying_decisions"]["tb1"], 2)
                self.assertEqual(result["robots"]["tb1"]["rotation_only_filtered"],
                                 2 if mixed else 0)
                last = next(row["payload"] for row in reversed(files["motion_safety.jsonl"])
                            if row["kind"] == "decision" and row["payload"]["robot"] == "tb1")
                certificate = last["own_state"]["settled_turn"]
                self.assertEqual(certificate["active_since_ns"], 1_980_000_000)
                self.assertGreater(certificate["active_path_m"], 0.)

    def test_release_discards_qualified_prewarm_sources_before_new_task_qualification(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            files = write_settled_fixture(directory, self.helper, prewarm=True)
            self.assertTrue(_audit_records(directory, self.helper, {})["passed"])
            decisions = [row["payload"] for row in files["motion_safety.jsonl"]
                         if row["kind"] == "decision" and row["payload"]["robot"] == "tb1"]
            before_release = next(value for value in decisions
                                  if value["clock_ns"] == 1_000_000_000)
            first_task = next(value for value in decisions if value["started"])
            self.assertIsNotNone(before_release["own_state"]["settled_turn"])
            self.assertIsNone(first_task["own_state"]["settled_turn"])
            first_grant = next(value for value in decisions
                               if value["decision"]["reason"] == "settled_turn_drift_reserve")
            self.assertEqual(first_grant["clock_ns"], 1_980_000_000)
            first_task["own_state"]["settled_turn"] = copy.deepcopy(
                before_release["own_state"]["settled_turn"])
            write_files(directory, files)
            with self.assertRaisesRegex(ValueError, "own state differs"):
                _audit_records(directory, self.helper, {})

    def test_settled_certificate_cannot_forge_zero_history_raw_hash_or_full_planar_speed(self):
        for fault in ("zero_start", "last_zero", "source", "hash", "planar", "path"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = write_settled_fixture(directory, self.helper)
                decision = next(row["payload"] for row in reversed(files["motion_safety.jsonl"])
                                if row["kind"] == "decision" and row["payload"]["robot"] == "tb1")
                own = decision["own_state"]
                certificate = own["settled_turn"]
                if fault == "zero_start":
                    certificate["zero_since_ns"] -= 1
                elif fault == "last_zero":
                    certificate["last_zero_decision_sequence"] -= 1
                elif fault == "source":
                    certificate["samples"][-1]["source_ns"] -= 1
                elif fault == "hash":
                    certificate["samples"][-1]["odom_sha256"] = "f" * 64
                elif fault == "planar":
                    own["planar_speed_mps"] = 0.
                else:
                    certificate["active_path_m"] = 0.
                write_files(directory, files)
                with self.assertRaisesRegex(ValueError, "own state differs"):
                    _audit_records(directory, self.helper, {})

    def test_settled_active_raw_speed_path_or_source_gap_breach_is_fatal(self):
        for fault in ("speed", "path", "gap"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = write_settled_fixture(directory, self.helper)
                raw = next(row["payload"]["message"]
                           for row in reversed(files["motion_safety.jsonl"])
                           if row["kind"] == "own_odom" and row["payload"]["robot"] == "tb1")
                if fault == "speed":
                    raw["twist"]["twist"]["linear"]["y"] = .02
                elif fault == "path":
                    raw["pose"]["pose"]["position"]["x"] += .01
                else:
                    raw["header"]["stamp"]["nanosec"] = 120_000_001
                write_files(directory, files)
                with self.assertRaisesRegex(ValueError, "active settled turn"):
                    _audit_records(directory, self.helper, {})

    def test_settled_reason_requires_configured_complete_rotation_check(self):
        for fault in ("configuration", "missing_check", "check_math"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = write_settled_fixture(directory, self.helper, mixed=True)
                row = next(row["payload"] for row in files["motion_safety.jsonl"]
                           if row["kind"] == "decision" and row["payload"]["robot"] == "tb1"
                           and row["payload"]["decision"].get("component_filter") is not None)
                rotation = row["decision"]["component_filter"]["rotation_check"]
                if fault == "configuration":
                    del files["motion_safety.jsonl"][0]["payload"]["settled_turn_contract"]
                elif fault == "missing_check":
                    del rotation["settled_turn_check"]
                else:
                    rotation["settled_turn_check"]["required_body_margin_m"] = 0.
                write_files(directory, files)
                with self.assertRaises(ValueError):
                    _audit_records(directory, self.helper, {})

    def test_actual_settled_model_failure_event_never_becomes_ignored_telemetry(self):
        for configured in (False, True):
            with self.subTest(configured=configured), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = (write_settled_fixture(directory, self.helper) if configured else
                         write_fixture(directory, self.helper))
                row = files["motion_safety.jsonl"][-1]
                row.update(kind="settled_turn_model_failure", payload={
                    "robot": "tb1", "reason": "active settled turn total drift budget exceeded"})
                write_files(directory, files)
                with self.assertRaisesRegex(ValueError, "actual settled turn model failure"):
                    _audit_records(directory, self.helper, {})

    def test_typed_json_provenance_rejects_bool_for_equal_numeric_value(self):
        for fault in ("own", "peers", "request", "decision", "raw_request"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = write_fixture(directory, self.helper)
                value = next(row["payload"] for row in files["motion_safety.jsonl"]
                             if row["kind"] == "decision" and row["payload"]["started"])
                if fault == "own":
                    value["own_state"]["v"] = False
                elif fault == "peers":
                    value["received_peers"]["tb2"]["w"] = False
                elif fault == "request":
                    value["request"]["w"] = False
                elif fault == "decision":
                    value["decision"]["output"][1] = False
                else:
                    raw = next(row["payload"] for row in files["motion_safety.jsonl"]
                               if row["kind"] == "raw_request")
                    raw["request"]["w"] = False
                write_files(directory, files)
                with self.assertRaises(ValueError):
                    _audit_records(directory, self.helper, {})

    def test_false_active_path_never_passes_recorded_certificate_or_decision_replay(self):
        for field in ("own", "decision"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = write_settled_fixture(directory, self.helper)
                value = next(row["payload"] for row in files["motion_safety.jsonl"]
                             if row["kind"] == "decision" and row["payload"]["decision"]["reason"]
                             == "settled_turn_drift_reserve")
                if field == "own":
                    value["own_state"]["settled_turn"]["active_path_m"] = False
                    self.assertFalse(self.helper.valid_settled_turn(
                        value["own_state"], value["clock_ns"] / 1e9))
                else:
                    value["decision"]["settled_turn_check"]["certificate"]["active_path_m"] = False
                write_files(directory, files)
                with self.assertRaises(ValueError):
                    _audit_records(directory, self.helper, {})

    def test_independent_exact_endpoint_consumer_rejects_wider_or_unbounded_changes(self):
        import math
        request = {"v": math.nextafter(.20, math.inf), "w": .6842105263157895}
        decision = {
            "allow": True, "output": [.20, request["w"]],
            "command_normalization": {"schema": "mr3-command-one-ulp-v1",
                                      "input": [request["v"], request["w"]],
                                      "canonical": [.20, request["w"]],
                                      "normalized_axes": ["v"]},
        }
        command_boundary(decision, request)
        for fault in ("output", "two_ulps", "metadata", "original"):
            changed, source = copy.deepcopy(decision), copy.deepcopy(request)
            if fault == "output":
                changed["output"][0] = request["v"]
            elif fault == "two_ulps":
                source["v"] = math.nextafter(request["v"], math.inf)
                changed["command_normalization"]["input"][0] = source["v"]
            elif fault == "metadata":
                changed["command_normalization"]["canonical"][0] = .25
            else:
                changed["command_normalization"]["input"][0] = .20
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                command_boundary(changed, source)

    def test_old_captured_endpoint_requires_its_old_frozen_command_limit(self):
        request = {"v": .26000000000000006, "w": .4}
        decision = {"allow": True, "output": [.26, .4],
                    "command_normalization": {
                        "schema": "mr3-command-one-ulp-v1", "input": [request["v"], .4],
                        "canonical": [.26, .4], "normalized_axes": ["v"]}}
        with self.assertRaises(ValueError):
            command_boundary(decision, request)
        command_boundary(decision, request, command_limits=(.26, .8))

    def test_component_consumer_requires_exact_turn_and_full_independent_recheck(self):
        def state(name, x, y):
            return {"name": name, "epoch": "fixture", "valid": True, "x": x, "y": y,
                    "yaw": 0., "v": 0., "w": 0., "source_stamp": 1.,
                    "planar_speed_mps": 0., "odometry": {"twist": {"twist": twist()}}}
        own = state("tb1", 0., 0.)
        peers = {"tb2": state("tb2", .65, 0.), "tb3": state("tb3", 4., 4.)}
        request = {"v": math.nextafter(.20, math.inf), "w": -.6842105263157895}
        decision = self.helper.guard_motion(
            [request["v"], request["w"]], own, peers, 1., "fixture")
        command_boundary(decision, request)
        self.assertEqual(decision["output"], [0., request["w"]])
        for fault in ("linear", "angular", "missing", "rejected", "rotation"):
            changed = copy.deepcopy(decision)
            if fault == "linear":
                changed["output"][0] = .01
            elif fault == "angular":
                changed["output"][1] = -request["w"]
            elif fault == "missing":
                changed["component_filter"] = None
            elif fault == "rejected":
                rejected = changed["component_filter"]["rejected_mixed_decision"]
                rejected["reason"] = "peer_uncertainty_envelope"
            else:
                changed["component_filter"]["rotation_check"]["allow"] = False
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                command_boundary(changed, request)

    def test_independent_angular_endpoint_consumer_preserves_point_eight_hard_limit(self):
        import math
        for sign in (-1., 1.):
            request = {"v": 0., "w": sign * math.nextafter(.8, math.inf)}
            decision = {
                "allow": True, "output": [0., sign * .8],
                "command_normalization": {
                    "schema": "mr3-command-one-ulp-v1", "input": [0., request["w"]],
                    "canonical": [0., sign * .8], "normalized_axes": ["w"]}}
            command_boundary(decision, request)
            for fault in ("unbounded_output", "old_limit", "two_ulps"):
                changed, original = copy.deepcopy(decision), copy.deepcopy(request)
                if fault == "unbounded_output":
                    changed["output"][1] = request["w"]
                elif fault == "old_limit":
                    changed["output"][1] = sign
                else:
                    original["w"] = sign * math.nextafter(abs(request["w"]), math.inf)
                    changed["command_normalization"]["input"][1] = original["w"]
                with self.subTest(sign=sign, fault=fault), self.assertRaises(ValueError):
                    command_boundary(changed, original)

    def test_filtered_turn_binds_actual_fifo_and_is_never_counted_as_full_request_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            files = write_fixture(directory, self.helper)
            rows = files["motion_safety.jsonl"]
            received = next(row["payload"] for row in rows if row["kind"] == "received_states")
            received["robots"][1]["x"] = .65
            peers = {robot["name"]: robot for robot in received["robots"]}
            requests, outputs = {}, {}
            for row in rows:
                value, kind = row["payload"], row["kind"]
                if kind == "raw_request":
                    if value["robot"] == "tb1":
                        value["request"].update(v=math.nextafter(.20, math.inf),
                                                w=-.6842105263157895)
                        value["twist"] = twist(math.nextafter(.20, math.inf), -.6842105263157895)
                    requests[value["robot"]] = value["request"]
                elif kind == "decision":
                    name = value["robot"]
                    value["request"] = copy.deepcopy(requests[name])
                    value["received_peers"] = {
                        peer: copy.deepcopy(state) for peer, state in peers.items()
                        if peer != name}
                    if value["started"]:
                        request = requests[name]
                        value["decision"] = self.helper.guard_motion(
                            [request["v"], request["w"]], value["own_state"],
                            value["received_peers"], value["clock_ns"] / 1e9, "fixture-motion")
                    outputs[name, value["decision_sequence"]] = value["decision"]["output"]
                elif kind == "actual_cmd_vel":
                    output = outputs[value["robot"], value["observed_decision_sequence"]]
                    value["twist"] = twist(*output)
            write_files(directory, files)
            result = _audit_records(directory, self.helper, {})
            self.assertEqual(result["robots"]["tb1"]["passed_nonzero"], 0)
            self.assertEqual(result["robots"]["tb1"]["rotation_only_filtered"], 1)
            self.assertEqual(result["robots"]["tb1"]["actual_outputs"], 2)
            actual = next(row for row in rows if row["kind"] == "actual_cmd_vel"
                          and row["payload"]["robot"] == "tb1"
                          and row["payload"]["observed_decision_sequence"] == 2)
            actual["payload"]["twist"]["linear"]["x"] = .01
            write_files(directory, files)
            with self.assertRaisesRegex(ValueError, "publication FIFO"):
                _audit_records(directory, self.helper, {})

    def test_raw_received_and_actual_fifo_pass_including_gzip_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            write_fixture(directory, self.helper)
            path = directory / "motion_safety.jsonl"
            Path(str(path) + ".gz").write_bytes(gzip.compress(path.read_bytes(), mtime=0))
            path.unlink()
            result = _audit_records(directory, self.helper, {})
            self.assertTrue(result["passed"])
            self.assertEqual(result["consumed_motion_phases"], 2)
            self.assertEqual(result["robots"]["tb1"]["passed_nonzero"], 1)
            self.assertEqual(result["robots"]["tb1"]["actual_outputs"], 2)

    def test_raw_own_received_request_and_helper_output_mutations_are_rejected(self):
        mutations = {
            "own_sequence": lambda r: r["own_state"]["input_sequences"].update(odom=2),
            "own_geometry": lambda r: r["own_state"].update(x=.1),
            "raw_peer_bypass": lambda r: r["received_peers"]["tb2"].update(x=3.),
            "request_sequence": lambda r: r["request"].update(sequence=2),
            "request_gid": lambda r: r["request"]["publisher_identity"]["endpoints"][0].update(
                endpoint_gid="f" * 32),
            "geometry_replay": lambda r: r["decision"].update(body_margin_m=42.),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = copy.deepcopy(write_fixture(directory, self.helper))
                decision = next(row for row in files["motion_safety.jsonl"]
                                if row["kind"] == "decision")
                mutate(decision["payload"])
                write_files(directory, files)
                with self.assertRaises(ValueError):
                    _audit_records(directory, self.helper, {})

    def test_actual_graph_fifo_missing_receipt_and_ack_mutations_are_rejected(self):
        for label in ("gid", "value", "observed_sequence", "missing_actual",
                      "ack_sequence", "ack_clock", "ack_early", "initial_missing",
                      "initial_not_ready"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = copy.deepcopy(write_fixture(directory, self.helper))
                rows = files["motion_safety.jsonl"]
                actual = next(row for row in rows if row["kind"] == "actual_cmd_vel")
                if label == "gid":
                    actual["payload"]["publisher_identity"]["endpoints"][0].update(
                        endpoint_gid="f" * 32)
                elif label == "value":
                    actual["payload"]["twist"]["linear"]["x"] = .1
                elif label == "observed_sequence":
                    actual["payload"]["observed_decision_sequence"] = 2
                elif label == "missing_actual":
                    rows.remove(actual)
                    for sequence, row in enumerate(rows, 1):
                        row["record_sequence"] = sequence
                elif label == "ack_sequence":
                    files["motion_phase_worker.jsonl"][0]["ack"]["decision_sequences"]["tb1"] = 2
                elif label == "ack_clock":
                    files["motion_phase_worker.jsonl"][0]["ack"]["clock_ns"] += 1
                elif label == "ack_early":
                    files["motion_phase_worker.jsonl"][0]["wall_monotonic_ns"] = 1
                elif label == "initial_missing":
                    files["motion_phase_worker.jsonl"] = files["motion_phase_worker.jsonl"][2:]
                else:
                    files["motion_phase_worker.jsonl"][0]["ack"]["ready"] = False
                write_files(directory, files)
                with self.assertRaises(ValueError):
                    _audit_records(directory, self.helper, {})

    def test_epoch_record_order_and_missing_file_are_rejected(self):
        for label in ("epoch", "sequence", "missing"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = write_fixture(directory, self.helper)
                if label == "epoch":
                    files["motion_safety.jsonl"][1]["epoch"] = "stale"
                elif label == "sequence":
                    files["motion_safety.jsonl"][1]["record_sequence"] = 1
                write_files(directory, files)
                if label == "missing":
                    (directory / "motion_topology.json").unlink()
                with self.assertRaises((ValueError, FileNotFoundError)):
                    _audit_records(directory, self.helper, {})


def write_controlled_fixture(directory, helper):
    """Two real controlled quanta and a same-clock permanent zero stop."""
    files = write_fixture(directory, helper)
    original = files["motion_safety.jsonl"]
    first_decision = next(i for i, row in enumerate(original) if row["kind"] == "decision")
    rows = copy.deepcopy(original[:first_decision])
    epoch = files["metadata.json"]["epoch"]
    configuration = rows[0]["payload"]
    configuration.update(own_input_selection="latest_causal_v1", controlled_execution=True)
    files["metadata.json"]["execution_phase_protocol"] = "mr3-controlled-execution-phase-v1"
    base = {row["payload"]["robot"]: copy.deepcopy(row["payload"])
            for row in original if row["kind"] == "decision"
            and row["payload"]["decision_sequence"] == 1}
    worker, normal_phase, drive = [], [], []
    native = {name: [] for name in ROBOTS}
    wall = rows[-1]["wall_monotonic_ns"] + 10

    def tick():
        nonlocal wall
        wall += 10
        return wall

    def node(kind, value, clock):
        rows.append({"schema": "mr3-motion-safety-v1", "epoch": epoch,
                     "record_sequence": len(rows) + 1, "kind": kind, "payload": value,
                     "sim_time_sec": clock / 1e9, "wall_monotonic_ns": tick()})

    def event(kind, clock, **values):
        worker.append({"schema": "mr3-controlled-execution-phase-v1", "epoch": epoch,
                       "kind": kind, "worker_clock_ns": clock, "worker_physical_ns": clock,
                       "wall_monotonic_ns": tick(), **values})

    def request(component, operation, clock, identity, **refs):
        value = {"schema": f"mr3-{component}-phase-request-v1", "epoch": epoch,
                 "request_id": identity, "target_time_ns": clock, "operation": operation, **refs}
        if component == "motion":
            value["schema"] = "mr3-motion-control-request-v1"
        event("request", clock, component=component, request=value)
        return value

    def ack(req, **fields):
        identity = {key: req[key] for key in (
            "epoch", "request_id", "target_time_ns", "operation")}
        return {**identity,
                "schema": req["schema"].replace("request", "ack"),
                "clock_ns": req["target_time_ns"], "ok": True, **fields}

    def consume(component, response):
        for kind in ("ack_received", "ack_consumed"):
            event(kind, response["clock_ns"], component=component, ack=copy.deepcopy(response))

    def emit(clock, sequence, released=False, stop=False):
        outputs = {}
        for name in ROBOTS:
            value = copy.deepcopy(base[name])
            value.update(clock_ns=clock, decision_sequence=sequence, started=released,
                         ready=not stop)
            if stop:
                value["phase_kind"] = "stop"
            value["decision"] = ({"allow": False, "reason": "controlled_stop" if stop
                                  else "before_release", "output": [0., 0.],
                                  "minimum_margin_m": None} if stop or not released else
                                 helper.guard_motion([.2, 0.], value["own_state"],
                                                     value["received_peers"], clock / 1e9, epoch))
            node("decision", value, clock)
            outputs[name] = {"linear_x": value["decision"]["output"][0],
                             "angular_z": value["decision"]["output"][1]}
        for name in ROBOTS:
            source = next(row["payload"] for row in original if row["kind"] == "actual_cmd_vel"
                          and row["payload"]["robot"] == name)
            value = copy.deepcopy(source)
            value.update(observed_decision_sequence=sequence,
                         twist=twist(outputs[name]["linear_x"], outputs[name]["angular_z"]))
            node("actual_cmd_vel", value, clock)
        status = {"schema": "mr3-motion-safety-status-v1", "epoch": epoch, "clock_ns": clock,
                  "ready": not stop, "completion_scope": "publication_and_local_topic_receipt",
                  "decision_sequences": dict.fromkeys(ROBOTS, sequence), "outputs": outputs}
        if stop:
            status["phase_kind"] = "stop"
        start, end = tick(), tick()
        node("output_completed", {"status": status,
                                  "publish_started_wall_monotonic_ns": start,
                                  "publish_completed_wall_monotonic_ns": end}, clock)
        return status

    def motion_response(req, status):
        response = ack(req, status=status)
        clock = response["clock_ns"]
        node("control_ack", response, clock)
        start, end = tick(), tick()
        node("control_ack_published", {"ack": response,
                                       "publish_started_wall_monotonic_ns": start,
                                       "publish_completed_wall_monotonic_ns": end}, clock)
        consume("motion", response)
        if "phase_kind" not in status:
            for kind in ("ack_received", "ack_consumed"):
                normal_phase.append({"kind": kind, "epoch": epoch, "ack": status,
                                     "worker_clock_ns": clock, "worker_physical_ns": clock,
                                     "wall_monotonic_ns": tick()})
        return response

    def advance(identity, clock, status):
        kind = ("bootstrap_zero" if clock == 1_000_000_000 else
                "stop" if status.get("phase_kind") == "stop" else "normal")
        reference = (f"takeover{clock}" if kind == "bootstrap_zero" else
                     f"stop{clock}" if kind == "stop" else f"boundary{clock}")
        receipts = {}
        for name in ROBOTS:
            sequence = status["decision_sequences"][name]
            receipt = {"schema": "mr3-drive-target-consumed-v1", "epoch": epoch,
                       "robot": name, "clock_ns": clock, "source_clock_ns": clock,
                       "cmd_seq": sequence, "decision_sequence": sequence,
                       **status["outputs"][name]}
            receipts[name] = receipt
            command = {"schema": "mr3-drive-actuation-v2", "epoch": epoch, "robot": name,
                       "kind": "command_received", "cmd_seq": sequence, "sim_time_ns": clock,
                       "target_clock_ns": clock, "target_decision_sequence": sequence,
                       "desired_v": receipt["linear_x"], "desired_w": receipt["angular_z"],
                       "record_sequence": len(native[name]) + 1}
            native[name].append(command)
            native[name].append({**command, "kind": "status_publish", "status": receipt,
                                 "record_sequence": len(native[name]) + 1})
            drive.append({"kind": "ack_received", "epoch": epoch, "topic_robot": name,
                          "ack": receipt, "wall_monotonic_ns": tick()})
        drive.append({"kind": "ack_consumed", "epoch": epoch, "expected_motion": status,
                      "receipts": receipts, "wall_monotonic_ns": tick()})
        drive.append({"kind": "advance_permitted", "epoch": epoch, "request_id": identity,
                      "start_time_ns": clock, "steps": 20, "expected_motion": status,
                      "control_kind": kind, "control_request_id": reference,
                      "receipts": receipts, "worker_clock_ns": clock,
                      "worker_physical_ns": clock,
                      "wall_monotonic_ns": tick()})

    initial = emit(1_000_000_000, 1)
    req = request("motion", "takeover", 1_000_000_000, "takeover1000000000")
    node("control_request", req, 1_000_000_000)
    motion_response(req, initial)
    for component in ("state", "peer"):
        req = request(component, "takeover", 1_000_000_000, "takeover1000000000")
        consume(component, ack(req))
    advance("q2", 1_000_000_000, initial)
    for sequence, clock in ((2, 1_020_000_000), (3, 1_040_000_000)):
        identity = f"boundary{clock}"
        state_req = request("state", "commit", clock, identity)
        state = ack(state_req, state_sequence=sequence, bundle_sha256="a" * 64,
                    scope="actual_state_and_side_publish_calls_returned")
        consume("state", state)
        peer_req = request("peer", "commit", clock, identity, state_commit=state)
        peer = ack(peer_req, state_commit=state, commit_sequence=sequence,
                   bundle_sha256="a" * 64, scope="actual_obstacle_publish_calls_returned")
        consume("peer", peer)
        node("control_dependency", {"component": "state", "value": state}, clock)
        node("control_dependency", {"component": "peer", "value": peer}, clock)
        req = request("motion", "commit", clock, identity, state_commit=state, peer_commit=peer)
        node("control_request", req, clock)
        status = emit(clock, sequence, released=sequence == 3)
        node("control_commit", {"request": req}, clock)
        motion_response(req, status)
        if sequence == 2:
            node("release", {"stamp": clock / 1e9}, clock)
            advance("q3", clock, status)
    node("stop_request", {"stamp": 1.04}, 1_040_000_000)
    req = request("motion", "stop", 1_040_000_000, "stop1040000000", reason="task_terminal")
    node("control_request", req, 1_040_000_000)
    stopped = emit(1_040_000_000, 4, released=True, stop=True)
    event("stop_observed", 1_040_000_000, status=stopped, origin="stop_topic", duplicate=False)
    motion_response(req, stopped)
    advance("q4", 1_040_000_000, stopped)
    req = request("motion", "stop", 1_060_000_000, "stop1060000000", reason="task_terminal")
    node("control_request", req, 1_060_000_000)
    stopped = emit(1_060_000_000, 5, released=True, stop=True)
    motion_response(req, stopped)
    files.update({"motion_safety.jsonl": rows, "motion_phase_worker.jsonl": normal_phase,
                  "control_phase_worker.jsonl": worker, "drive_phase_worker.jsonl": drive,
                  "transitions.jsonl": [
                      {"kind": "reset", "snapshot": {"epoch": epoch, "source_stamp": 1.02},
                       "info": {"release_time_ns": 1_020_000_000,
                                "initial_motion_status": normal_phase[2]["ack"]}},
                      {"kind": "step", "snapshot": {"epoch": epoch, "source_stamp": 1.04}}],
                  "physics.jsonl": [
                      {"request_id": "q1", "steps": 0, "start_time_ns": 1_000_000_000,
                       "end_time_ns": 1_000_000_000},
                      {"request_id": "q2", "steps": 20, "start_time_ns": 1_000_000_000,
                       "end_time_ns": 1_020_000_000},
                      {"request_id": "q3", "steps": 20, "start_time_ns": 1_020_000_000,
                       "end_time_ns": 1_040_000_000},
                      {"request_id": "q4", "steps": 20, "start_time_ns": 1_040_000_000,
                       "end_time_ns": 1_060_000_000}]})
    files.update({f"drive_{name}.jsonl": values for name, values in native.items()})
    for row in files["physics.jsonl"]:
        row.update(epoch=epoch, ok=True, paused=True, step_ns=1_000_000,
                   start_iterations=row["start_time_ns"] // 1_000_000,
                   end_iterations=row["end_time_ns"] // 1_000_000)
    write_files(directory, files)
    return json.loads(json.dumps(files))


def add_controlled_own_samples(files, helper, samples, before_clock=1_040_000_000):
    """Insert genuine callback rows, preserving the original cross-ledger wall order."""
    rows = files["motion_safety.jsonl"]
    index = next(i for i, row in enumerate(rows) if row["kind"] == "decision"
                 and row["payload"]["clock_ns"] == before_clock)
    original = next(row for row in rows if row["kind"] == "own_odom"
                    and row["payload"]["robot"] == "tb1")
    inserted = []
    for sequence, (source, angular_x) in enumerate(samples, 2):
        row = copy.deepcopy(original)
        row.update(sim_time_sec=before_clock / 1e9,
                   wall_monotonic_ns=rows[index - 1]["wall_monotonic_ns"] + sequence - 1)
        row["payload"]["input_sequence"] = sequence
        raw = row["payload"]["message"]
        sec, nano = divmod(source, 10**9)
        raw["header"]["stamp"] = {"sec": sec, "nanosec": nano}
        raw["twist"]["twist"]["angular"]["x"] = angular_x
        inserted.append(row)
    rows[index:index] = inserted
    for sequence, row in enumerate(rows, 1):
        row["record_sequence"] = sequence
    for row in rows[index + len(inserted):]:
        if row["kind"] != "decision" or row["payload"]["robot"] != "tb1":
            continue
        value = row["payload"]
        eligible = [(source, sequence) for sequence, (source, _) in enumerate(samples, 2)
                    if source <= value["clock_ns"]]
        source, sequence = max([(1_000_000_000, 1), *eligible])
        own = value["own_state"]
        own["odom_source_stamp"] = source / 1e9
        own["source_stamp"] = min(source / 1e9, own["tf_source_stamp"])
        own["input_sequences"]["odom"] = sequence
        if value["started"] and "phase_kind" not in value:
            request = value["request"]
            value["decision"] = helper.guard_motion(
                [request["v"], request["w"]], own, value["received_peers"],
                value["clock_ns"] / 1e9, files["metadata.json"]["epoch"])


class ControlledMotionAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = helper_module()

    def test_same_clock_explicit_stop_retains_full_fifo_and_distinct_normal_ack(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            write_controlled_fixture(directory, self.helper)
            result = _audit_records(directory, self.helper, {})
            self.assertTrue(result["passed"])
            self.assertEqual(result["controlled_execution_replay"]["stop_clocks"],
                             [1040000000, 1060000000])
            self.assertEqual(result["robots"]["tb1"]["controlled_stop_decisions"], 2)

    def test_normal_commit_rejects_selected_raw_angular_xyz_peak(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            files = write_controlled_fixture(directory, self.helper)
            raw = next(row["payload"]["message"] for row in files["motion_safety.jsonl"]
                       if row["kind"] == "own_odom" and row["payload"]["robot"] == "tb1")
            raw["twist"]["twist"]["angular"]["x"] = 1.3
            write_files(directory, files)
            with self.assertRaisesRegex(
                    ValueError, "selected_own.*measured_angular_speed_exceeded"):
                _audit_records(directory, self.helper, {})

    def test_normal_commit_rejects_causal_history_peak_hidden_by_new_healthy_sample(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            files = write_controlled_fixture(directory, self.helper)
            add_controlled_own_samples(files, self.helper,
                                       [(1_025_000_000, 1.3), (1_030_000_000, 0.)])
            write_files(directory, files)
            with self.assertRaisesRegex(ValueError, "own_history.*measured_angular_speed_exceeded"):
                _audit_records(directory, self.helper, {})

    def test_unselected_prewarm_and_future_peaks_are_not_normal_task_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            files = write_controlled_fixture(directory, self.helper)
            add_controlled_own_samples(files, self.helper,
                                       [(990_000_000, 1.3), (1_080_000_000, 1.3)])
            write_files(directory, files)
            self.assertTrue(_audit_records(directory, self.helper, {})["passed"])

    def test_new_raw_peak_during_stop_does_not_become_a_normal_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            files = write_controlled_fixture(directory, self.helper)
            add_controlled_own_samples(files, self.helper, [(1_050_000_000, 1.3)],
                                       before_clock=1_060_000_000)
            write_files(directory, files)
            self.assertTrue(_audit_records(directory, self.helper, {})["passed"])

    def test_actual_model_invalid_event_and_negative_ack_cannot_be_success(self):
        for mutation in ("model_invalid", "negative_ack"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = write_controlled_fixture(directory, self.helper)
                rows = files["motion_safety.jsonl"]
                if mutation == "model_invalid":
                    target = next(row for row in rows if row["kind"] == "control_commit")
                    target.update(kind="normal_control_model_invalid", payload={
                        "schema": "mr3-normal-control-model-fault-v1",
                        "classification": "normal_control_model_invalid_not_task_attributed"})
                    message = "actual normal control model invalid"
                else:
                    target = next(row for row in rows if row["kind"] == "control_ack"
                                  and row["payload"]["operation"] == "commit")
                    target["payload"].update(ok=False, error="normal_control_model_invalid")
                    target["payload"].pop("status")
                    message = "failed actual motion control ACK"
                write_files(directory, files)
                with self.assertRaisesRegex(ValueError, message):
                    _audit_records(directory, self.helper, {})

    def test_control_mutations_cannot_hide_missing_side_order_or_zero_completion(self):
        for mutation in ("failure", "nonzero_stop", "missing_self", "wrong_dependency",
                         "missing_publication", "normal_overwrite", "advance_without_chain",
                         "bootstrap_kind"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = write_controlled_fixture(directory, self.helper)
                rows = files["motion_safety.jsonl"]
                if mutation == "failure":
                    target = next(row for row in rows if row["kind"] == "control_commit")
                    target.update(kind="control_failure", payload={"error": "actual timeout"})
                elif mutation == "nonzero_stop":
                    target = next(row for row in rows if row["kind"] == "decision"
                                  and row["payload"].get("phase_kind") == "stop")
                    target["payload"]["decision"]["output"][0] = .01
                elif mutation == "missing_self":
                    target = next(row for row in rows if row["kind"] == "actual_cmd_vel"
                                  and row["payload"]["observed_decision_sequence"] == 4)
                    target["payload"]["observed_decision_sequence"] = 3
                elif mutation == "wrong_dependency":
                    target = next(row for row in rows if row["kind"] == "control_commit")
                    target["payload"]["request"]["state_commit"]["bundle_sha256"] = "b" * 64
                elif mutation == "missing_publication":
                    for row in rows:
                        if row["kind"] == "control_ack_published":
                            row["kind"] = "configuration"
                elif mutation == "normal_overwrite":
                    files["motion_phase_worker.jsonl"][-1]["ack"]["phase_kind"] = "stop"
                elif mutation == "advance_without_chain":
                    files["drive_phase_worker.jsonl"] = []
                else:
                    next(row for row in files["drive_phase_worker.jsonl"]
                         if row.get("control_kind") == "bootstrap_zero")["control_kind"] = "normal"
                write_files(directory, files)
                with self.assertRaises(ValueError):
                    _audit_records(directory, self.helper, {})

    def test_future_and_late_old_own_callbacks_do_not_replace_latest_causal_source(self):
        for source in (1.04, .98):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = write_fixture(directory, self.helper)
                rows = files["motion_safety.jsonl"]
                rows[0]["payload"]["own_input_selection"] = "latest_causal_v1"
                index = next(i for i, row in enumerate(rows) if row["kind"] == "decision")
                injected = []
                for name in ROBOTS:
                    original = next(row for row in rows if row["kind"] == "own_odom"
                                    and row["payload"]["robot"] == name)
                    row = copy.deepcopy(original)
                    row["payload"]["input_sequence"] = 2
                    row["payload"]["message"]["header"]["stamp"] = {
                        "sec": int(source), "nanosec": round((source % 1) * 1e9)}
                    injected.append(row)
                rows[index:index] = injected
                for i, row in enumerate(rows, 1):
                    row["record_sequence"] = i
                    row["wall_monotonic_ns"] = 1000 + i * 10
                # Keep real ACK receipts after the newly inserted actual outputs.
                for row in files["motion_phase_worker.jsonl"]:
                    row["wall_monotonic_ns"] += (len(injected) + 1) * 10
                write_files(directory, files)
                self.assertTrue(_audit_records(directory, self.helper, {})["passed"])
                target = next(row for row in rows if row["kind"] == "decision")
                target["payload"]["own_state"]["input_sequences"]["odom"] = 2
                write_files(directory, files)
                with self.assertRaisesRegex(ValueError, "raw local"):
                    _audit_records(directory, self.helper, {})
