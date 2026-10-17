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
                     "input_sequences": {"odom": 1, "tf": 1}}
        received[name] = {**copy.deepcopy(own[name]), "x": 100. + index * 3.}
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
        own, requests = {}, {}
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
        received = copy.deepcopy(own)
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
        request = {"v": .26000000000000006, "w": .6842105263157895}
        decision = {
            "allow": True, "output": [.26, request["w"]],
            "command_normalization": {"schema": "mr3-command-one-ulp-v1",
                                      "input": [request["v"], request["w"]],
                                      "canonical": [.26, request["w"]],
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
                changed["command_normalization"]["input"][0] = .26
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                command_boundary(changed, source)

    def test_component_consumer_requires_exact_turn_and_full_independent_recheck(self):
        def state(name, x, y):
            return {"name": name, "epoch": "fixture", "valid": True, "x": x, "y": y,
                    "yaw": 0., "v": 0., "w": 0., "source_stamp": 1.}
        own = state("tb1", 0., 0.)
        peers = {"tb2": state("tb2", .65, 0.), "tb3": state("tb3", 4., 4.)}
        request = {"v": .26000000000000006, "w": -.6842105263157895}
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
                        value["request"].update(v=.26000000000000006, w=-.6842105263157895)
                        value["twist"] = twist(.26000000000000006, -.6842105263157895)
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
