"""Pure CPU counterexamples for the separate reach readback entry; no ROS."""
import contextlib
import copy
import inspect
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mr3_learning import audit_reach_nav2_parameters as entry


EPOCH, RELEASE = "reach-readback-cpu", 1_000_000_000


def status():
    return {"schema": "mr3-motion-safety-status-v2", "epoch": EPOCH,
            "clock_ns": RELEASE, "ready": True,
            "completion_scope": "publication_and_local_topic_receipt",
            "decision_sequences": {name: n for n, name in enumerate(entry.ROBOTS, 1)},
            "outputs": {name: {"linear_x": 0., "angular_z": 0.} for name in entry.ROBOTS},
            "safety_contract": entry.CONTRACT,
            "intent_refs": {name: {"intent_sequence": n, "payload_sha256": str(n)*64}
                            for n, name in enumerate(entry.ROBOTS, 1)},
            "safety_table_sha256": "a"*64}


def odometry(name, source):
    return {"header": {"stamp": {"sec": source//10**9, "nanosec": source%10**9}, "frame_id": name+"/odom"},
            "child_frame_id": name+"/base_footprint",
            "pose": {"pose": {"position": {"x": 0., "y": 0., "z": 0.},
                              "orientation": {"x": 0., "y": 0., "z": 0., "w": 1.}}, "covariance": [0.]*36},
            "twist": {"twist": {"linear": {"x": 0., "y": 0., "z": 0.},
                                "angular": {"x": 0., "y": 0., "z": 0.}}, "covariance": [0.]*36}}


def write_release(episode, wire):
    reset = {"kind": "reset", "snapshot": {"epoch": EPOCH},
             "info": {"release_time_ns": RELEASE, "initial_motion_status": status()}}
    (episode/"transitions.jsonl").write_text(json.dumps(reset)+"\n")
    rows, refs = [], {}
    for name in entry.ROBOTS:
        intent = {"schema": "mr3-safety-intent-v1", "epoch": EPOCH, "robot": name,
                  "intent_sequence": 2, "source_clock_ns": RELEASE, "role": "HOLD",
                  "anchor": {"source_clock_ns": RELEASE, "odometry": odometry(name, RELEASE)},
                  "admitted_signs": [], "lineage": {"release_clock_ns": RELEASE},
                  "target": {"schema": "mr3-drive-target-v1", "epoch": EPOCH, "robot": name,
                             "clock_ns": RELEASE, "decision_sequence": 2, "linear_x": 0., "angular_z": 0.}}
        refs[name] = {"intent_sequence": 2, "payload_sha256": wire.payload_sha256(intent)}
        rows.append({"schema": "mr3-controlled-execution-phase-v2", "epoch": EPOCH,
                     "kind": "owner_intent_received", "robot": name, "intent": intent,
                     "payload_sha256": wire.payload_sha256(intent),
                     "publisher_graph": [{"namespace": "/", "node": "motion_safety",
                                          "type": "std_msgs/msg/String", "endpoint_gid": name}],
                     "identity_scope": "graph_at_callback_not_per_packet_identity"})
    rows.append({"schema": "mr3-controlled-execution-phase-v2", "epoch": EPOCH,
                 "kind": "release_intents_captured", "release_clock_ns": RELEASE,
                 "worker_clock_ns": RELEASE, "worker_physical_ns": RELEASE, "intent_refs": refs})
    (episode/"control_phase_worker.jsonl").write_text("".join(json.dumps(row)+"\n" for row in rows))
    return rows, refs


class ReachParameterReadbackTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        sources = [entry.deployment.LEGACY_RELATIVE, entry.WIRE_RELATIVE]
        sources += [Path(row["path"]) for row in entry.deployment.yaml_bindings()]
        for relative in sources:
            path = self.root/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((entry.WORKSPACE/relative).read_bytes())
        self.reader, self.proof, self.wire = entry.load_profile(self.root)

    def test_complete_deployment_math_and_nine_service_collector_bytes_are_unchanged(self):
        old, old_proof = entry.deployment.load_profile(self.root)
        self.assertEqual(self.reader.EXPECTED, old.EXPECTED)
        self.assertEqual(self.proof["profile_definition"], old_proof["profile_definition"])
        self.assertEqual(self.proof["profile_sha256"], old_proof["profile_sha256"])
        for function in ("decode_parameters", "validate_parameters", "collect"):
            self.assertEqual(inspect.getsource(getattr(self.reader, function)),
                             inspect.getsource(getattr(old, function)))
        self.assertNotIn("validate_status", self.proof["unchanged_function_sha256"])
        self.assertEqual(self.proof["status_schema"], "mr3-motion-safety-status-v2")
        self.assertFalse(self.proof["training_eligible"])
        self.assertEqual(self.proof["effective_entry"]["sha256"], entry.sha(Path(entry.__file__).read_bytes()))

    def test_status_v2_requires_exact_same_release_healthy_complete_typed_identity(self):
        self.reader.validate_status(status(), EPOCH, RELEASE)
        cases = (("schema", "mr3-motion-safety-status-v1"), ("epoch", "foreign"),
                 ("clock_ns", True), ("clock_ns", RELEASE+1), ("ready", False),
                 ("safety_contract", "legacy"), ("safety_table_sha256", None),
                 ("safety_table_sha256", "g"*64), ("intent_refs", None))
        for key, value in cases:
            bad = status(); bad[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.reader.validate_status(bad, EPOCH, RELEASE)
        for mutate in (lambda s: s.update(extra=True),
                       lambda s: s["decision_sequences"].update(tb1=True),
                       lambda s: s["intent_refs"]["tb1"].update(intent_sequence=True),
                       lambda s: s["outputs"]["tb1"].update(linear_x=True),
                       lambda s: s["outputs"]["tb1"].update(angular_z=.01)):
            bad = status(); mutate(bad)
            with self.assertRaises(ValueError):
                self.reader.validate_status(bad, EPOCH, RELEASE)

    def test_actual_status_is_bound_as_a_whole_and_caller_mutation_cannot_change_it(self):
        expected = status()
        reader, _, _ = entry.load_profile(self.root, expected_status=expected)
        expected["intent_refs"]["tb1"]["intent_sequence"] += 1
        reader.validate_status(status(), EPOCH, RELEASE)
        for field in ("intent_refs", "safety_table_sha256", "decision_sequences"):
            bad = status()
            if field == "intent_refs": bad[field]["tb1"]["payload_sha256"] = "f"*64
            elif field == "safety_table_sha256": bad[field] = "f"*64
            else: bad[field]["tb1"] += 1
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "original returned reset"):
                reader.validate_status(bad, EPOCH, RELEASE)

    def test_actual_post_release_subscriptions_are_required_not_only_rpc_refs(self):
        episode = self.root/"episode"; episode.mkdir()
        rows, refs = write_release(episode, self.wire)
        metadata = {"epoch": EPOCH, "safety_contract": entry.CONTRACT}
        release, initial, binding = entry.release_binding(episode, metadata, self.wire)
        self.assertEqual(release, RELEASE)
        self.assertEqual(initial, status())
        self.assertEqual(binding["post_release_intent_refs"], refs)
        path = episode/"control_phase_worker.jsonl"
        for invalid in (rows[1:], rows[:-1], [*rows[:-1], {**rows[-1], "release_clock_ns": RELEASE+1}],
                        [{**rows[0], "publisher_graph": []}, *rows[1:]]):
            path.write_text("".join(json.dumps(row)+"\n" for row in invalid))
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                entry.release_binding(episode, metadata, self.wire)

    def test_unchanged_deceleration_wrong_parameter_types_and_duplicate_json_still_fail(self):
        for kind, name, wrong in (("controller_server", "FollowPath.decel_lim_theta", -1.),
                                  ("velocity_smoother", "max_decel", [-.5, 0., -1.])):
            rows = [{"name": key, "type": value[0], "value": copy.deepcopy(value[1])}
                    for key, value in self.reader.EXPECTED[kind].items()]
            next(row for row in rows if row["name"] == name)["value"] = wrong
            with self.assertRaises(ValueError):
                self.reader.validate_parameters(kind, rows)
        for raw in ('{"ready":true,"ready":false}', '{"v":NaN}'):
            with self.assertRaises(ValueError): self.reader.json.loads(raw)

    def test_legacy_episode_is_rejected_before_service_collection_or_source_git(self):
        episode = self.root/"episode"; episode.mkdir()
        (episode/"metadata.json").write_text(json.dumps({"epoch": EPOCH, "freeze": "a"*40,
                                                        "safety_contract": "legacy"}))
        output = self.root/"failure.json"
        with patch.object(entry, "load_profile", return_value=(self.reader, self.proof, self.wire)), \
                patch.object(self.reader, "collect") as collect, \
                patch.object(entry.subprocess, "check_output") as git, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(entry.main([str(episode), "--freeze", "a"*40, "--output", str(output)]), 1)
        collect.assert_not_called(); git.assert_not_called()
        result = json.loads(output.read_text())
        self.assertFalse(result["passed"])
        self.assertEqual(result["nodes"], [])
        self.assertEqual(result["schema"], entry.SCHEMA)


if __name__ == "__main__":
    unittest.main()
