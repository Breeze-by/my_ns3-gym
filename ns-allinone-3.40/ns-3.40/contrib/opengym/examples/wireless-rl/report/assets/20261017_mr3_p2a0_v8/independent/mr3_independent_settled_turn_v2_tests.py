"""Adversarial external evidence tests, with no production tracker import."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("independent_settled_turn", Path(__file__).with_name("mr3_independent_settled_turn_v2.py"))
consumer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)


def message(stamp, x=.0002, y=0.):
    return {"header": {"stamp": {"sec": stamp // 10**9, "nanosec": stamp % 10**9},
                       "frame_id": "odom"}, "child_frame_id": "base_footprint",
            "pose": {"pose": {"position": {"x": stamp / 1e9 * .0002, "y": 0., "z": 0.}}},
            "twist": {"twist": {"linear": {"x": x, "y": y, "z": 0.}}}}


def fixture():
    epoch = "synthetic-epoch"
    motion = []
    publications = []
    def append(kind, payload):
        row = {"epoch": epoch, "record_sequence": len(motion) + 1,
               "kind": kind, "payload": payload}
        motion.append(row)
        return row
    def decision(sequence, clock, detail, request=None, own=None):
        payload = {"robot": "tb1", "clock_ns": clock, "decision_sequence": sequence,
                   "decision": detail, "started": True, "ready": True,
                   "request": request, "own_state": own,
                   "received_peers": {name: {"name": name, "x": x, "y": 0., "yaw": 0.,
                        "v": 0., "w": 0., "source_stamp": 2.98, "epoch": epoch, "valid": True}
                                      for name, x in (("tb2", .70), ("tb3", -.90))}}
        append("decision", payload)
        target = {"schema": "mr3-drive-target-v1", "epoch": epoch, "robot": "tb1",
                  "clock_ns": clock, "decision_sequence": sequence,
                  "linear_x": detail["output"][0], "angular_z": detail["output"][1]}
        publications.append({"epoch": epoch, "target_json": json.dumps(target)})
    decision(1, 20_000_000, {"allow": True, "reason": "before_release", "output": [0., 0.]})
    decision(2, 2_900_000_000, {"allow": True, "reason": "clear", "output": [0., 0.]})
    samples = []
    for sequence, source in enumerate((2_920_000_000, 2_950_000_000, 2_980_000_000), 1):
        row = append("own_odom", {"robot": "tb1", "input_sequence": sequence,
                                  "message": message(source)})
        sample = consumer.odom_sample(row, len(motion))
        samples.append({key: sample[key] for key in ("source_ns", "input_sequence",
                       "planar_speed_mps", "odom_sha256")})
    certificate = {"schema": "mr3-settled-turn-v1", "zero_since_ns": 20_000_000,
                   "last_zero_decision_sequence": 2, "samples": samples, "active_since_ns": None,
                   "active_anchor_source_ns": None, "active_path_m": 0.}
    own = {"name": "tb1", "robot": "tb1", "x": 0., "y": 0., "yaw": 0., "v": .0002,
           "w": -.1, "source_stamp": 2.98, "odom_source_stamp": 2.98, "tf_source_stamp": 2.98,
           "epoch": epoch, "valid": True, "planar_speed_mps": .0002, "settled_turn": certificate}
    detail = {"schema": "mr3-settled-turn-check-v1", "certificate": certificate,
              "horizon_sec": .78, "own_drift_reserve_m": .01 * .78,
              "peer_braking_reserve_m": .144, "required_body_margin_m": .1518}
    rotation = {"allow": True, "reason": "settled_turn_drift_reserve", "output": [0., -.8],
                "settled_turn_check": detail}
    decision(3, 3_000_000_000, rotation, {"v": 0., "w": -.8}, own)
    for sequence, source in enumerate((3_020_000_000, 3_060_000_000), 4):
        append("own_odom", {"robot": "tb1", "input_sequence": sequence,
                            "message": message(source)})
    native = {}
    for name in consumer.ROBOTS:
        records = []
        for sequence, clock, w in ((1, 20_000_000, 0.), (2, 2_900_000_000, 0.), (3, 3_000_000_000, -.8)):
            records.append({"epoch": epoch, "robot": name, "record_sequence": sequence,
                            "kind": "command_received", "cmd_seq": sequence,
                            "sim_time_ns": clock, "target_clock_ns": clock,
                            "target_decision_sequence": sequence, "desired_v": 0., "desired_w": w})
        native[name] = records
    return {"metadata": {"epoch": epoch, "freeze": "a" * 40}, "motion": motion,
            "publications": publications, "native": native, "physics_end": 3_080_000_000}


def grant(data):
    return next(row["payload"] for row in data["motion"]
                if row["kind"] == "decision" and row["payload"]["decision_sequence"] == 3)


def odoms(data):
    return [row for row in data["motion"] if row["kind"] == "own_odom"]


class ExternalEvidenceTests(unittest.TestCase):
    def test_valid_finite_condition_is_separate_from_physical_theorem(self):
        result = consumer.audit_records(**fixture(), require_use=True)
        self.assertTrue(result["passed"])
        self.assertTrue(result["stimulus_coverage_passed"])
        self.assertEqual(len(result["qualification_intervals"]), 1)
        self.assertEqual(result["criteria"]["pair_required_body_margin_m"], .1518)

    def reject(self, edit, match=None):
        data = fixture()
        edit(data)
        with self.assertRaises((ValueError, KeyError, TypeError)) as caught:
            consumer.audit_records(**data, require_use=True)
        if match:
            self.assertIn(match, str(caught.exception))

    def test_own_v_cannot_substitute_a_different_raw_odometry(self):
        self.reject(lambda d: grant(d)["own_state"].update(v=0.), "raw source binding")

    def test_source_epoch_cannot_be_borrowed(self):
        self.reject(lambda d: d["motion"][2].update(epoch="other"))

    def test_actual_zero_storage_must_be_continuous_780ms(self):
        def edit(d):
            d["native"]["tb1"][0]["desired_v"] = .1
            d["native"]["tb1"][1]["desired_v"] = .1
        self.reject(edit, "actual zero storage history")

    def test_native_settle_is_required_at_grant_not_later_receipt(self):
        def edit(data):
            data["native"]["tb1"][0].update(sim_time_ns=2_300_000_000)
            data["native"]["tb1"][-1].update(sim_time_ns=3_100_000_000)
        self.reject(edit, "actual zero storage history")

    def test_v6_fresh_receipt_of_stale_source_does_not_authorize(self):
        def edit(d):
            row = d["native"]["tb1"][-1]
            row["sim_time_ns"] += 712_000_000
        self.reject(edit, "producer age")

    def test_publication_history_cannot_disagree_with_decisions(self):
        def edit(d):
            p = json.loads(d["publications"][1]["target_json"])
            p["linear_x"] = .1
            d["publications"][1]["target_json"] = json.dumps(p)
        self.reject(edit, "publication/output history")

    def test_published_nonzero_resets_qualification(self):
        def edit(d):
            d["motion"][1]["payload"]["decision"]["output"][0] = .1
            p = json.loads(d["publications"][1]["target_json"])
            p["linear_x"] = .1
            d["publications"][1]["target_json"] = json.dumps(p)
        self.reject(edit, "prior zero publication history")

    def test_rest_source_requires_full_planar_vector(self):
        self.reject(lambda d: odoms(d)[2]["payload"]["message"]["twist"]["twist"]["linear"].update(y=.011), "rest bound")

    def test_pure_nan_never_supplies_rest(self):
        self.reject(lambda d: odoms(d)[1]["payload"]["message"]["twist"]["twist"]["linear"].update(z=float("nan")))

    def test_future_rest_not_a_past_certificate(self):
        self.reject(lambda d: odoms(d)[2]["payload"]["message"]["header"]["stamp"].update(sec=3, nanosec=40_000_000))

    def test_three_source_gap_is_strict(self):
        self.reject(lambda d: odoms(d)[0]["payload"]["message"]["header"]["stamp"].update(nanosec=800_000_000))

    def test_certificate_hash_count_seq_values_are_raw_bound(self):
        edits = [lambda c: c["samples"][1].update(odom_sha256="0" * 64),
                 lambda c: c["samples"].pop(),
                 lambda c: c["samples"][1].update(input_sequence=99),
                 lambda c: c["samples"][1].update(planar_speed_mps=0.)]
        for edit in edits:
            with self.subTest(edit=edit):
                self.reject(lambda d: edit(grant(d)["own_state"]["settled_turn"]))

    def test_geometry_retains_full_peer_and_original_source_age(self):
        self.reject(lambda d: grant(d)["received_peers"]["tb2"].update(x=.65), "pair body margin")
        self.reject(lambda d: grant(d)["received_peers"]["tb2"].update(source_stamp=2.60), "pair body margin")

    def test_required_margin_cannot_be_lowered_in_metadata(self):
        self.reject(lambda d: grant(d)["decision"]["settled_turn_check"].update(required_body_margin_m=.15))

    def test_unknown_or_missing_peer_rejected(self):
        self.reject(lambda d: grant(d)["received_peers"].pop("tb3"))

    def test_nonzero_linear_output_cannot_use_conditional_branch(self):
        self.reject(lambda d: grant(d)["decision"]["output"].__setitem__(0, .01))

    def test_turn_cannot_be_invented_or_reversed(self):
        self.reject(lambda d: grant(d)["request"].update(w=.8), "requested angular")

    def test_endpoint_one_ulp_only(self):
        data = fixture()
        grant(data)["request"]["w"] = -math.nextafter(.8, math.inf)
        self.assertTrue(consumer.audit_records(**data, require_use=True)["passed"])
        self.reject(lambda d: grant(d)["request"].update(w=-math.nextafter(math.nextafter(.8, math.inf), math.inf)))

    def test_mixed_retains_only_original_requested_angular(self):
        data = fixture()
        payload = grant(data)
        rotation = copy.deepcopy(payload["decision"])
        payload["request"]["v"] = .2
        payload["decision"]["reason"] = "linear_brake_preserve_requested_turn"
        payload["decision"]["component_filter"] = {"rotation_check": rotation}
        self.assertTrue(consumer.audit_records(**data, require_use=True)["passed"])
        payload["request"]["w"] = .8
        with self.assertRaises(ValueError):
            consumer.audit_records(**data, require_use=True)

    def test_future_qualified_violation_cannot_be_cleared_out_of_history(self):
        self.reject(lambda d: odoms(d)[3]["payload"]["message"]["twist"]["twist"]["linear"].update(x=.010000000000000002), "invariant")

    def test_future_lateral_drift_is_not_hidden_by_zero_vx(self):
        self.reject(lambda d: odoms(d)[4]["payload"]["message"]["twist"]["twist"]["linear"].update(x=0., y=.011), "invariant")

    def test_model_failure_event_always_fails_even_no_more_grants(self):
        def edit(d):
            d["motion"].append({"epoch": "synthetic-epoch", "record_sequence": len(d["motion"]) + 1,
                "kind": "settled_turn_model_failure", "payload": {"robot": "tb1", "reason": "drift"}})
        self.reject(edit, "model failure")

    def test_future_active_gap_and_missing_tail_fail(self):
        self.reject(lambda d: d.update(physics_end=3_200_000_000), "final fresh")
        self.reject(lambda d: odoms(d)[4]["payload"]["message"]["header"]["stamp"].update(nanosec=170_000_000))

    def test_wrong_native_value_and_target_sequence_rejected(self):
        self.reject(lambda d: d["native"]["tb1"][-1].update(desired_w=.8))
        self.reject(lambda d: d["native"]["tb1"][-1].update(target_decision_sequence=99))

    def test_wrong_native_robot_never_borrowed(self):
        self.reject(lambda d: d["native"]["tb1"][-1].update(robot="tb2"))

    def test_raw_source_rewind_and_conflict_fail(self):
        self.reject(lambda d: odoms(d)[1]["payload"]["message"]["header"]["stamp"].update(nanosec=910_000_000))
        self.reject(lambda d: odoms(d)[1]["payload"]["message"]["header"]["stamp"].update(nanosec=920_000_000))

    def test_accel_upper_bound_cannot_prove_a_speed_scaled_stop(self):
        u, maximum, acceleration = .001, .30, 1.2
        up, down = (maximum - u) / acceleration, maximum / acceleration
        path = (u + maximum) * up / 2 + maximum * down / 2
        self.assertLess(up + down, .78)
        self.assertLess(path, .144)
        self.assertGreater(path, 100 * (u * .18 + u * u))

    def test_no_trigger_is_not_new_model_validation(self):
        data = fixture()
        payload = grant(data)
        payload["decision"]["reason"] = "clear"
        result = consumer.audit_records(**data)
        self.assertTrue(result["passed"])
        self.assertFalse(result["stimulus_coverage_passed"])
        required = consumer.audit_records(**data, require_use=True)
        self.assertFalse(required["passed"])
        self.assertTrue(required["integrity_and_sampled_model_bounds_passed"])
        self.assertFalse(required["stimulus_coverage_passed"])

    def test_whole_zero_interval_budget_cannot_be_refreshed_by_long_low_speed(self):
        def edit(data):
            # 9 mm/s is below the rest-speed bound but exceeds 7.8 mm total.
            base_position = odoms(data)[2]["payload"]["message"]["pose"]["pose"]["position"]["x"]
            data["motion"] = data["motion"][:-2]
            for index in range(1, 22):
                stamp = 3_000_000_000 + index * 50_000_000
                msg = message(stamp, .009)
                msg["pose"]["pose"]["position"]["x"] = base_position + .009 * (stamp - 2_980_000_000) / 1e9
                data["motion"].append({"epoch": "synthetic-epoch", "record_sequence": len(data["motion"]) + 1,
                    "kind": "own_odom", "payload": {"robot": "tb1", "input_sequence": index + 3, "message": msg}})
            data["physics_end"] = 4_070_000_000
        self.reject(edit, "cumulative odom drift")

    def test_raw_pose_not_tf_or_map_pose_must_bind_drift(self):
        self.reject(lambda d: odoms(d)[3]["payload"]["message"]["pose"]["pose"]["position"].update(y=.008), "chord speed")
        self.reject(lambda d: odoms(d)[3]["payload"]["message"]["pose"]["pose"]["position"].update(x=float("nan")))

    def test_boolean_is_not_an_input_sequence(self):
        self.reject(lambda d: grant(d)["own_state"]["settled_turn"]["samples"][0].update(input_sequence=True))

    def test_actual_nonzero_storage_not_publication_ends_active_invariant(self):
        data = fixture()
        # Publication is at3.04, native receipt at3.06. The3.05 raw sample is
        # still in the actual zero segment and may not be discarded.
        payload = {"robot": "tb1", "clock_ns": 3_040_000_000, "decision_sequence": 4,
                   "decision": {"allow": True, "reason": "clear", "output": [.1, 0.]}}
        row = {"epoch": "synthetic-epoch", "kind": "decision", "payload": payload}
        data["motion"].insert(-1, row)
        for index, record in enumerate(data["motion"], 1):
            record["record_sequence"] = index
        target = {"epoch": "synthetic-epoch", "robot": "tb1", "decision_sequence": 4,
                  "clock_ns": 3_040_000_000, "linear_x": .1, "angular_z": 0.}
        data["publications"].append({"epoch": "synthetic-epoch", "target_json": json.dumps(target)})
        receipt = copy.deepcopy(data["native"]["tb1"][-1])
        receipt.update(record_sequence=4, cmd_seq=4, target_decision_sequence=4,
                       target_clock_ns=3_040_000_000, sim_time_ns=3_060_000_000,
                       desired_v=.1, desired_w=0.)
        data["native"]["tb1"].append(receipt)
        last = odoms(data)[-1]
        last["payload"]["message"]["header"]["stamp"]["nanosec"] = 50_000_000
        last["payload"]["message"]["twist"]["twist"]["linear"]["y"] = .011
        with self.assertRaisesRegex(ValueError, "invariant"):
            consumer.audit_records(**data, require_use=True)
        # A sample beyond actual storage is new commanded movement and is
        # outside this zero-only conditional invariant.
        last["payload"]["message"]["header"]["stamp"]["nanosec"] = 70_000_000
        self.assertTrue(consumer.audit_records(**data, require_use=True)["passed"])

    def test_repeated_grants_keep_one_anchor_and_one_total_budget(self):
        data = fixture()
        prior = grant(data)
        payload = copy.deepcopy(prior)
        payload.update(clock_ns=3_060_000_000, decision_sequence=4)
        own = payload["own_state"]
        own.update(source_stamp=3.06, odom_source_stamp=3.06, tf_source_stamp=3.06)
        certificate = own["settled_turn"]
        actual = [consumer.odom_sample(row, index) for index, row in enumerate(data["motion"], 1)
                  if row["kind"] == "own_odom"]
        certificate.update(last_zero_decision_sequence=3, active_since_ns=3_000_000_000,
                           active_anchor_source_ns=2_980_000_000,
                           active_path_m=(actual[-1]["position_xy"][0] - actual[-3]["position_xy"][0]),
                           samples=[{key: row[key] for key in ("source_ns", "input_sequence",
                            "planar_speed_mps", "odom_sha256")} for row in actual[-3:]])
        payload["decision"]["settled_turn_check"]["certificate"] = certificate
        data["motion"].append({"epoch": "synthetic-epoch", "record_sequence": len(data["motion"]) + 1,
                               "kind": "decision", "payload": payload})
        target = {"epoch": "synthetic-epoch", "robot": "tb1", "decision_sequence": 4,
                  "clock_ns": 3_060_000_000, "linear_x": 0., "angular_z": -.8}
        data["publications"].append({"epoch": "synthetic-epoch", "target_json": json.dumps(target)})
        receipt = copy.deepcopy(data["native"]["tb1"][-1])
        receipt.update(record_sequence=4, cmd_seq=4, target_decision_sequence=4,
                       target_clock_ns=3_060_000_000, sim_time_ns=3_060_000_000)
        data["native"]["tb1"].append(receipt)
        result = consumer.audit_records(**data, require_use=True)
        self.assertEqual(len(result["qualification_intervals"]), 1)
        certificate["active_path_m"] = 0.
        with self.assertRaisesRegex(ValueError, "active anchor/path"):
            consumer.audit_records(**data, require_use=True)

    def test_input_changed_during_audit_retains_binding_and_fails(self):
        from unittest import mock
        data = fixture()
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            values = {"metadata.json": data["metadata"], "motion_safety.jsonl": data["motion"],
                      "drive_targets.jsonl": data["publications"],
                      "physics.jsonl": [{"epoch": "synthetic-epoch", "end_time_ns": data["physics_end"]}]}
            values.update({"drive_" + robot + ".jsonl": records for robot, records in data["native"].items()})
            for filename, value in values.items():
                raw = ("".join(json.dumps(row) + "\n" for row in value) if filename.endswith("jsonl") else json.dumps(value)).encode()
                (directory / filename).write_bytes(raw)
            original = Path.read_bytes
            calls = 0
            def changing(path):
                nonlocal calls
                raw = original(path)
                if path == directory / "metadata.json":
                    calls += 1
                    if calls > 1:
                        return raw + b" "
                return raw
            with mock.patch.object(Path, "read_bytes", changing):
                result = consumer.audit_episode(directory, "a" * 40, True)
            self.assertFalse(result["passed"])
            self.assertIn("changed while auditing", result["error"])
            self.assertEqual(result["final_physics_time_ns"], data["physics_end"])
            self.assertEqual(len(result["inputs"]), 7)

    def test_raw_speed_violation_at_exact_final_physics_endpoint_is_not_dropped(self):
        def edit(data):
            msg = odoms(data)[-1]["payload"]["message"]
            msg["header"]["stamp"]["nanosec"] = 80_000_000
            msg["twist"]["twist"]["linear"]["x"] = .011
        self.reject(edit, "invariant")

    def test_total_budget_breach_at_exact_final_endpoint_is_not_dropped(self):
        def edit(data):
            anchor = odoms(data)[2]["payload"]["message"]["pose"]["pose"]["position"]["x"]
            data["motion"] = data["motion"][:-2]
            for index in range(1, 18):
                stamp = 3_000_000_000 + index * 50_000_000
                msg = message(stamp, .009)
                msg["pose"]["pose"]["position"]["x"] = anchor + .009 * (stamp - 2_980_000_000) / 1e9
                data["motion"].append({"epoch": "synthetic-epoch", "record_sequence": len(data["motion"]) + 1,
                    "kind": "own_odom", "payload": {"robot": "tb1", "input_sequence": index + 3, "message": msg}})
            data["physics_end"] = 3_850_000_000
        self.reject(edit, "cumulative odom drift")

    def test_late_source_between_anchor_and_grant_is_not_dropped(self):
        def edit(data):
            data["motion"].insert(6, {"epoch": "synthetic-epoch", "kind": "own_odom",
                "payload": {"robot": "tb1", "message": message(2_990_000_000, .011)}})
            own_sequence = 0
            for index, row in enumerate(data["motion"], 1):
                row["record_sequence"] = index
                if row["kind"] == "own_odom":
                    own_sequence += 1
                    row["payload"]["input_sequence"] = own_sequence
        self.reject(edit, "invariant")

    def test_plain_and_gzip_archives_and_end_input_recheck(self):
        import gzip
        data = fixture()
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            values = {"metadata.json": data["metadata"],
                      "motion_safety.jsonl": data["motion"],
                      "drive_targets.jsonl": data["publications"],
                      "physics.jsonl": [{"epoch": "synthetic-epoch", "end_time_ns": data["physics_end"]}]}
            values.update({"drive_" + robot + ".jsonl": records for robot, records in data["native"].items()})
            for filename, value in values.items():
                raw = ("".join(json.dumps(row) + "\n" for row in value) if filename.endswith("jsonl") else json.dumps(value)).encode()
                (directory / (filename + ".gz")).write_bytes(gzip.compress(raw))
            result = consumer.audit_episode(directory, "a" * 40, True)
            self.assertTrue(result["passed"])
            self.assertEqual(len(result["inputs"]), 7)
            failed = consumer.audit_episode(directory, "b" * 40, True)
            self.assertFalse(failed["passed"])
            self.assertIn("metadata.json.gz", next(iter(failed["inputs"])))


if __name__ == "__main__":
    unittest.main()
