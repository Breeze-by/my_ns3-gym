"""Wire counterexamples only; root owns finite execution and actual receipts."""
import copy
import math
import unittest

from multi_robot_exploration import mr3_safety_intent as s

EPOCH, ROBOT, NOW = "wire-fixture", "tb1", 2_000_000_000


def odometry(clock=NOW):
    vector = {"x": 0., "y": 0., "z": 0.}
    return {"header": {"stamp": {"sec": clock//10**9, "nanosec": clock%10**9}, "frame_id": "tb1/odom"},
            "child_frame_id": "tb1/base_footprint",
            "pose": {"pose": {"position": dict(vector), "orientation": dict(vector, w=1.)}, "covariance": [0.]*36},
            "twist": {"twist": {"linear": dict(vector), "angular": dict(vector)}, "covariance": [0.]*36}}


def target(v=0., w=0., clock=NOW):
    return {"schema": s.TARGET_SCHEMA, "epoch": EPOCH, "robot": ROBOT, "clock_ns": clock,
            "decision_sequence": 7, "linear_x": v, "angular_z": w}


def intent(role="D"):
    anchor = {"source_clock_ns": 1_000_000_000, "odometry": odometry(1_000_000_000)}
    lineage = {"anchor_intent_sequence": 2}
    signs, output = [], target(w=.3)
    if role == "HOLD":
        lineage, output = {"release_clock_ns": 1_100_000_000}, target()
    elif role in ("X", "N"):
        lineage["transition_intent_sequence"] = 3
        signs, output = [1], target(.1)
        if role == "N":
            lineage.update(actuation_sequence=12, actuation_source_clock_ns=1_200_000_000,
                           causal_source_clock_ns=1_900_000_000, cmd_seq=4)
    elif role == "STOP":
        lineage, signs, output = {"previous_intent_sequence": 9, "previous_role": "N"}, [1], target()
    return {"schema": s.INTENT_SCHEMA, "epoch": EPOCH, "robot": ROBOT, "intent_sequence": 10,
            "source_clock_ns": NOW, "role": role, "anchor": anchor,
            "admitted_signs": signs, "lineage": lineage, "target": output}


def calibration(clock=NOW):
    return {"schema": s.CALIBRATION_SCHEMA, "epoch": EPOCH, "robot": ROBOT, "source_clock_ns": clock,
            "publication_sequence": 100, "coefficient_c": 1., "coefficient_s": 0.,
            "odometry": odometry(clock), "conversion_contract": s.CONVERSION_CONTRACT,
            "producer_frame": s.PRODUCER_FRAME}


def applied():
    return {"schema": s.APPLIED_SCHEMA, "epoch": EPOCH, "robot": ROBOT, "source_clock_ns": NOW,
            "actuation_sequence": 80, "cmd_seq": 7, "dt_ns": 34_000_000, "target": target(.1, clock=NOW-20_000_000),
            "pairs": [{"pair_index": 0, "current_rim_mps": [.05, -.05], "desired_rim_mps": [.1, .1],
                       "applied_rim_mps": [.07, .01], "alpha": .4, "max_acceleration_mps2": 1.}]}


class SafetyIntentTests(unittest.TestCase):
    def validate(self, value):
        return s.validate_intent(value, epoch=EPOCH, robot=ROBOT, now_ns=NOW)

    def test_all_roles_and_old_anchor_are_valid_without_refreshing_history(self):
        for role in ("HOLD", "D", "X", "N", "STOP"):
            with self.subTest(role=role):
                value = intent(role)
                result = self.validate(value)
                self.assertEqual(result, value)
                self.assertIsNot(result, value)
        pre = intent("HOLD")
        pre.update(anchor=None, target=None, lineage={"release_clock_ns": None})
        self.validate(pre)
        braking = intent("N"); braking["target"] = target()
        self.assertEqual(self.validate(braking)["admitted_signs"], [1])

    def test_full_json_identity_is_detached_and_canonical_not_truthy(self):
        value = intent()
        result = self.validate(value)
        value["anchor"]["odometry"]["pose"]["covariance"][0] = 99.
        self.assertEqual(result["anchor"]["odometry"]["pose"]["covariance"][0], 0.)
        self.assertEqual(s.payload_sha256({"b": 2, "a": 1}), s.payload_sha256({"a": 1, "b": 2}))
        self.assertNotEqual(s.payload_sha256({"n": 1}), s.payload_sha256({"n": True}))
        for text in ('{"a":1,"a":2}', '{"x":NaN}', '{"x":1e999}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                s.parse_json(text)

    def test_schema_identity_unknown_fields_and_boolean_integer_substitution_reject(self):
        for key, bad in (("epoch", "old"), ("robot", "tb2"), ("schema", "v0"),
                         ("intent_sequence", True), ("source_clock_ns", False), ("role", "normal")):
            value = intent(); value[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(value)
        value = intent(); value["passed"] = True
        with self.assertRaises(ValueError):
            self.validate(value)

    def test_role_specific_lineage_and_permanent_stop_cannot_erase_previous_reach(self):
        cases = []
        v = intent("D"); v["admitted_signs"] = [1]; cases.append(v)
        v = intent("D"); v["target"]["linear_x"] = .001; cases.append(v)
        v = intent("X"); v["admitted_signs"] = []; cases.append(v)
        v = intent("N"); v["target"]["linear_x"] = -.001; cases.append(v)
        v = intent("X"); v["lineage"]["transition_intent_sequence"] = 2; cases.append(v)
        v = intent("STOP"); v["anchor"] = None; cases.append(v)
        v = intent("STOP"); v["admitted_signs"] = []; cases.append(v)
        v = intent("STOP"); v["lineage"]["previous_role"] = "STOP"; cases.append(v)
        v = intent("HOLD"); v["lineage"]["release_clock_ns"] = 900_000_000; cases.append(v)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.validate(value)

    def test_freshness_is_closed_but_future_and_one_ns_stale_fail(self):
        value = intent(); value["source_clock_ns"] = NOW-500_000_000
        value["target"]["clock_ns"] = value["source_clock_ns"]
        self.validate(value)
        for stamp in (NOW+1, NOW-500_000_001):
            value["source_clock_ns"] = stamp; value["target"]["clock_ns"] = min(stamp, NOW)
            with self.assertRaises(ValueError):
                self.validate(value)
        value = intent("N"); value["lineage"]["causal_source_clock_ns"] = NOW-500_000_001
        with self.assertRaises(ValueError):
            self.validate(value)
        value = intent("N"); value["lineage"]["causal_source_clock_ns"] = value["lineage"]["actuation_source_clock_ns"]
        with self.assertRaises(ValueError):
            self.validate(value)

    def test_target_is_exact_seven_fields_and_sign_family_does_not_ignore_tiny_v(self):
        s.validate_target(target(.20), epoch=EPOCH, robot=ROBOT, now_ns=NOW)
        with self.assertRaises(ValueError):
            s.validate_target(target(math.nextafter(.20, math.inf)), epoch=EPOCH, robot=ROBOT, now_ns=NOW)
        for mutate in (lambda x: x.update(linear_x=True), lambda x: x.update(angular_z=math.nan),
                       lambda x: x.update(clock_ns=NOW+1), lambda x: x.update(extra=1)):
            value = intent(); mutate(value["target"])
            with self.assertRaises(ValueError):
                self.validate(value)
        value = intent("X"); value["target"]["linear_x"] = -math.nextafter(0., math.inf)
        with self.assertRaises(ValueError):
            self.validate(value)

    def test_calibration_exact_full_selected_odometry_includes_covariance_and_types(self):
        value = {"intent": intent("N"), "calibration": calibration()}
        selected = odometry()
        s.validate_safety(value, epoch=EPOCH, robot=ROBOT, selected_odom=selected, now_ns=NOW)
        for replacement in (1., 0):
            selected = odometry(); selected["pose"]["covariance"][0] = replacement
            with self.assertRaises(ValueError):
                s.validate_safety(value, epoch=EPOCH, robot=ROBOT, selected_odom=selected, now_ns=NOW)
        value["calibration"] = calibration(NOW-200_000_000)
        with self.assertRaisesRegex(ValueError, "newer than"):
            s.validate_safety(value, epoch=EPOCH, robot=ROBOT,
                              selected_odom=value["calibration"]["odometry"], now_ns=NOW)

    def test_calibration_cannot_substitute_yaw_estimate_wrong_contract_or_unbound_source(self):
        for key, bad in (("coefficient_c", math.nan), ("coefficient_c", True),
                         ("coefficient_c", .70710678), ("conversion_contract", "estimated"),
                         ("producer_frame", "local"), ("publication_sequence", False), ("source_clock_ns", NOW+1)):
            value = calibration(); value[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                s.validate_calibration(value, epoch=EPOCH, robot=ROBOT, now_ns=NOW)
        value = calibration(); value["coefficient_c"] = value["coefficient_s"] = 0.
        with self.assertRaises(ValueError):
            s.validate_calibration(value, epoch=EPOCH, robot=ROBOT, now_ns=NOW)

    def test_native_applied_real_first_sequence_need_not_be_one_but_no_fictional_precommand(self):
        value = applied()
        self.assertEqual(s.validate_native_applied(value, epoch=EPOCH, robot=ROBOT, now_ns=NOW), value)
        for key, bad in (("cmd_seq", 0), ("target", None), ("dt_ns", 0), ("actuation_sequence", True)):
            value = applied(); value[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                s.validate_native_applied(value, epoch=EPOCH, robot=ROBOT, now_ns=NOW)
        for key, bad in (("alpha", True), ("alpha", 1.0001), ("pair_index", 1),
                         ("current_rim_mps", [0.]), ("max_acceleration_mps2", -1.)):
            value = applied(); value["pairs"][0][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                s.validate_native_applied(value, epoch=EPOCH, robot=ROBOT, now_ns=NOW)

    def test_refs_require_all_three_exact_identities_and_sha_fields(self):
        refs = {name: {"intent_sequence": 1, "payload_sha256": s.payload_sha256({"robot": name})} for name in s.ROBOTS}
        self.assertEqual(s.validate_intent_refs(refs, robots=s.ROBOTS), refs)
        for mutation in (lambda x: x.pop("tb3"), lambda x: x["tb1"].update(intent_sequence=True),
                         lambda x: x["tb2"].update(sha256="0"*64),
                         lambda x: x["tb3"].update(payload_sha256="x"*64)):
            value = copy.deepcopy(refs); mutation(value)
            with self.assertRaises(ValueError):
                s.validate_intent_refs(value, robots=s.ROBOTS)


if __name__ == "__main__":
    unittest.main()
