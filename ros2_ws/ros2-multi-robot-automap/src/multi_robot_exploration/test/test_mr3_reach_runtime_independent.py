"""Independent runtime counterexamples; root owns execution and source receipts.

Synthetic feeds exercise necessary causal/model checks. They never prove a
continuous physical plant, true delivery, native admission or task success.
This author does not execute this file while writing/reviewing it.
"""
import copy
import unittest

from multi_robot_exploration import mr3_reach_runtime as reach


EPOCH, ROBOT = "independent-runtime-epoch", "tb1"
START = 1_000_000_000
STEP, ACT = 20_000_000, 34_000_000


def odometry(clock, *, robot=ROBOT, xy=(0., 0.), velocity=(0., 0.), angular=0.):
    return {
        "header": {"stamp": {"sec": clock//10**9, "nanosec": clock%10**9},
                   "frame_id": robot+"/odom"},
        "child_frame_id": robot+"/base_footprint",
        "pose": {"pose": {"position": {"x": xy[0], "y": xy[1], "z": 0.},
                          "orientation": {"x": 0., "y": 0., "z": 0., "w": 1.}},
                 "covariance": [0.]*36},
        "twist": {"twist": {"linear": {"x": velocity[0], "y": velocity[1], "z": 0.},
                            "angular": {"x": 0., "y": 0., "z": angular}},
                  "covariance": [0.]*36},
    }


def calibration(raw, sequence, *, robot=ROBOT):
    stamp = raw["header"]["stamp"]
    return {"schema": "mr3-odom-calibration-v1", "epoch": EPOCH, "robot": robot,
            "source_clock_ns": stamp["sec"]*10**9+stamp["nanosec"],
            "publication_sequence": sequence, "coefficient_c": 1., "coefficient_s": 0.,
            "odometry": copy.deepcopy(raw), "conversion_contract": "float32-trig-binary64-rn-v1",
            "producer_frame": "world-common-model-origin-v1"}


def target(clock, sequence, output=(0., 0.), *, robot=ROBOT):
    return {"schema": "mr3-drive-target-v1", "epoch": EPOCH, "robot": robot,
            "clock_ns": clock, "decision_sequence": sequence,
            "linear_x": output[0], "angular_z": output[1]}


def storage(value, cmd_seq):
    return {"schema": "mr3-drive-target-consumed-v1", "epoch": EPOCH,
            "robot": value["robot"], "clock_ns": value["clock_ns"],
            "decision_sequence": value["decision_sequence"],
            "source_clock_ns": value["clock_ns"], "cmd_seq": cmd_seq,
            "linear_x": value["linear_x"], "angular_z": value["angular_z"]}


def applied(value, source, actuation_sequence, cmd_seq):
    desired = [value["linear_x"]+value["angular_z"]*.287/2,
               value["linear_x"]-value["angular_z"]*.287/2]
    error = max(abs(x) for x in desired)
    alpha = min(1., .034/error) if error else 1.
    return {"schema": "mr3-drive-applied-v1", "epoch": EPOCH, "robot": ROBOT,
            "source_clock_ns": source, "actuation_sequence": actuation_sequence,
            "cmd_seq": cmd_seq, "dt_ns": ACT, "target": copy.deepcopy(value),
            "pairs": [{"pair_index": 0, "current_rim_mps": [0., 0.],
                       "desired_rim_mps": desired,
                       "applied_rim_mps": [alpha*x for x in desired],
                       "alpha": alpha, "max_acceleration_mps2": 1.}]}


def state(raw, intent, *, name=ROBOT, map_xy=None):
    stamp = raw["header"]["stamp"]
    clock = stamp["sec"]*10**9+stamp["nanosec"]
    p = raw["pose"]["pose"]["position"]
    xy = (p["x"], p["y"]) if map_xy is None else map_xy
    return {"epoch": EPOCH, "name": name, "valid": True, "x": xy[0], "y": xy[1],
            "yaw": 0., "v": raw["twist"]["twist"]["linear"]["x"],
            "w": raw["twist"]["twist"]["angular"]["z"],
            "source_stamp": clock/10**9, "odom_source_stamp": clock/10**9,
            "tf_source_stamp": clock/10**9, "odometry": copy.deepcopy(raw),
            "transform": {"header": {"stamp": copy.deepcopy(stamp), "frame_id": "map"},
                          "child_frame_id": name+"/odom",
                          "transform": {"translation": {"x": 0., "y": 0., "z": 0.},
                                        "rotation": {"x": 0., "y": 0., "z": 0., "w": 1.}}},
            "safety": {"intent": copy.deepcopy(intent),
                       "calibration": calibration(raw, 1, robot=name)}}


def peer(name, clock, xy, *, map_xy=None):
    raw = odometry(clock, robot=name, xy=xy)
    intent = {"schema": "mr3-safety-intent-v1", "epoch": EPOCH, "robot": name,
              "intent_sequence": 1, "source_clock_ns": clock, "role": "HOLD",
              "anchor": {"source_clock_ns": START,
                         "odometry": odometry(START, robot=name, xy=xy)},
              "admitted_signs": [], "lineage": {"release_clock_ns": START},
              "target": target(clock, 1, robot=name)}
    return state(raw, intent, name=name, map_xy=map_xy)


class Feed:
    """20ms own raw/calibration and complete, independently phased 34ms writes.

    First actual write is 20ms after the release clock; subsequent writes are
    34ms apart. Every command phase publishes and really stores a fresh target.
    These are declared synthetic receipts, not evidence of ROS execution.
    """
    def __init__(self):
        self.r = reach.ReachTracker(EPOCH, ROBOT)
        self.now = START
        self.raw_sequence = self.calibration_sequence = 1
        self.sequence = self.command_sequence = 0
        self.actuation_sequence = 40
        self.next_actuation = START+STEP
        self.stored = []
        self.last_raw = odometry(START)
        self.publish()
        self.r.receive_raw(self.last_raw, self.raw_sequence)
        self.r.receive_calibration(calibration(self.last_raw, self.calibration_sequence))
        if self.r.synchronize(START) is not True:
            raise AssertionError("healthy initial source should synchronize")
        self.r.release(START)
        self.publish()  # Real full-zero target for the post-release HOLD.

    def publish(self, output=(0., 0.), *, store=True):
        self.sequence += 1
        value = target(self.now, self.sequence, output)
        self.r.publish_target(value)
        if store:
            self.command_sequence += 1
            self.r.receive_storage(storage(value, self.command_sequence))
            self.stored.append((copy.deepcopy(value), self.command_sequence))
        return value

    def actuations(self, through):
        while self.next_actuation <= through:
            value, cmd = max((item for item in self.stored
                              if item[0]["clock_ns"] <= self.next_actuation),
                             key=lambda item: item[1])
            self.r.receive_applied(applied(value, self.next_actuation,
                                           self.actuation_sequence, cmd))
            self.actuation_sequence += 1
            self.next_actuation += ACT

    def own(self):
        value = state(self.last_raw, self.r.current_intent)
        value["safety"]["calibration"] = copy.deepcopy(self.r.calibrations[self.now])
        return value

    def peers(self):
        return {"tb2": peer("tb2", self.now, (3., 0.)),
                "tb3": peer("tb3", self.now, (0., 3.))}

    def stage_next_raw(self, *, xy=(0., 0.), velocity=(0., 0.), with_calibration=True):
        self.now += STEP
        self.raw_sequence += 1
        self.calibration_sequence += 1
        self.last_raw = odometry(self.now, xy=xy, velocity=velocity)
        self.r.receive_raw(self.last_raw, self.raw_sequence)
        if with_calibration:
            self.r.receive_calibration(calibration(self.last_raw, self.calibration_sequence))
        self.actuations(self.now)

    def tick(self, request=(0., 0.), *, xy=(0., 0.), velocity=(0., 0.)):
        self.stage_next_raw(xy=xy, velocity=velocity)
        if self.r.synchronize(self.now) is not True:
            raise AssertionError("complete healthy streams should synchronize")
        result = self.r.decide(request, self.own(), self.peers(), self.now,
                               self.r.current_intent)
        self.publish(tuple(result["output"]))
        return result

    def disk(self):
        for _ in range(49):
            self.tick()
        if self.r.role != "D":
            raise AssertionError("release-based .98s full-zero qualification should reach D")
        return self

    def normal(self):
        self.disk()
        self.tick((.1, 0.))  # Delivered next-phase X, first target remains zero.
        self.tick((.1, 0.))  # Nonzero stored at START+1020ms, not yet actuated.
        if self.r.actual_normal:
            raise AssertionError("storage alone cannot be actual normal")
        self.tick((.1, 0.))  # Raw and actual both 1040ms; raw is not strictly later.
        if self.r.actual_normal:
            raise AssertionError("same-source raw cannot retire old disk responsibility")
        self.tick((.1, 0.))  # Strictly later causal raw at 1060ms.
        if self.r.role != "N":
            raise AssertionError("real stored/applied target plus later raw should reach N")
        return self


class IndependentReachRuntimeTests(unittest.TestCase):
    def test_startup_storage_retains_actual_later_clock_without_qualification(self):
        r = reach.ReachTracker(EPOCH, ROBOT)
        for source, stored_at, sequence, command in (
                (420_000_000, 430_000_000, 21, 1),
                (440_000_000, 444_000_000, 22, 2)):
            value = target(source, sequence)
            r.publish_target(value)
            ack = {**storage(value, command), "clock_ns": stored_at}
            r.receive_storage(ack)
            self.assertEqual(r.storage.latest[ROBOT], ack)
            self.assertEqual(r.storage.pending[ROBOT][sequence], ack)
            self.assertEqual(r.ingress[-1], ("storage", ack))
        self.assertEqual(r.zero_publication, 420_000_000)
        self.assertEqual(r.zero_storage, 430_000_000)
        self.assertEqual(r.role, "HOLD")
        self.assertIsNone(r.release_ns)
        self.assertIsNone(r.anchor)
        self.assertFalse(r.actual_normal)
        self.assertFalse(r.qualified(2_000_000_000))
        self.assertIsNone(r.fault)

    def test_release_cannot_borrow_later_storage_or_pre_release_rest(self):
        r = reach.ReachTracker(EPOCH, ROBOT)
        value = target(420_000_000, 21)
        r.publish_target(value)
        ack = {**storage(value, 1), "clock_ns": 430_000_000}
        r.receive_storage(ack)
        release = 1_400_000_000
        for sequence, source in enumerate((release-2*STEP, release-STEP, release), 1):
            raw = odometry(source)
            r.receive_raw(raw, sequence)
            r.receive_calibration(calibration(raw, sequence))
        r.receive_applied(applied(value, release-1_000_000, 1, 1))
        self.assertTrue(r.synchronize(release))
        self.assertEqual(len(r.rest), 3)
        self.assertIsNotNone(r.causal_applied)
        self.assertFalse(r.qualified(release))
        r.release(release)
        self.assertEqual(r.zero_publication, release)
        self.assertEqual(r.zero_storage, release)
        self.assertEqual(r.rest, [])
        self.assertEqual(r.role, "HOLD")
        self.assertIsNone(r.anchor_sequence)
        self.assertFalse(r.qualified(release))
        self.assertEqual(r.storage.latest[ROBOT], ack)

    def test_delayed_storage_keeps_exact_target_binding_and_latches_bad_receipts(self):
        cases = (
            ("source", {"source_clock_ns": 419_000_000}, "unpublished target"),
            ("linear", {"linear_x": .01}, "unpublished target"),
            ("angular", {"angular_z": .01}, "unpublished target"),
            ("epoch", {"epoch": "foreign-epoch"}, "robot/epoch"),
            ("robot", {"robot": "tb2"}, "robot/epoch"),
            ("unpublished", {"decision_sequence": 22}, "unpublished target"),
            ("source_after_storage", {"source_clock_ns": 430_000_001},
             "invalid native drive receipt"),
        )
        for name, mutation, error in cases:
            with self.subTest(name=name):
                r = reach.ReachTracker(EPOCH, ROBOT)
                value = target(420_000_000, 21)
                r.publish_target(value)
                ack = {**storage(value, 1), "clock_ns": 430_000_000, **mutation}
                with self.assertRaisesRegex(ValueError, error):
                    r.receive_storage(ack)
                fault = r.fault
                self.assertIsNotNone(fault)
                self.assertEqual(r.ingress[-1], ("storage", ack))
                successor = target(440_000_000, 23)
                r.publish_target(successor)
                r.receive_storage({**storage(successor, 2), "clock_ns": 444_000_000})
                with self.assertRaises(ValueError) as raised:
                    r.synchronize(444_000_000)
                self.assertEqual(str(raised.exception), fault)
                self.assertEqual(r.fault, fault)
                self.assertEqual(r.role, "HOLD")
                self.assertFalse(r.actual_normal)

    def test_startup_later_ack_still_cannot_acknowledge_a_paused_control_boundary(self):
        r = reach.ReachTracker(EPOCH, ROBOT)
        value = target(420_000_000, 21)
        r.publish_target(value)
        ack = {**storage(value, 1), "clock_ns": 430_000_000}
        r.receive_storage(ack)
        for name in ("tb2", "tb3"):
            r.storage.receive(storage(target(420_000_000, 21, robot=name), 1))
        boundary = {"epoch": EPOCH, "clock_ns": 420_000_000,
                    "decision_sequences": {name: 21 for name in reach.ROBOTS},
                    "outputs": {name: {"linear_x": 0., "angular_z": 0.}
                                for name in reach.ROBOTS}}
        with self.assertRaisesRegex(ValueError, "paused guard target"):
            r.storage.matching(boundary)
        self.assertEqual(r.storage.pending[ROBOT][21], ack)
        self.assertIsNone(r.fault)

    def test_complete_healthy_pipeline_reaches_disk_and_real_normal(self):
        a = Feed().normal()
        self.assertEqual(a.r.role, "N")
        self.assertEqual(len(a.r.status()["anchor_history"]), 2)
        self.assertFalse(a.r.status()["continuous_physical_model_proved"])

    def test_future_bad_sample_is_retained_but_not_blamed_before_its_clock(self):
        a = Feed().disk(); previous = a.now
        a.stage_next_raw(velocity=(.02, 0.))
        self.assertIsNone(a.r.fault)
        self.assertTrue(a.r.synchronize(previous))
        self.assertIsNone(a.r.fault)
        with self.assertRaises(ValueError):
            a.r.synchronize(a.now)
        self.assertIsNotNone(a.r.fault)

    def test_missing_matching_calibration_waits_and_cannot_close_frontier(self):
        a = Feed().disk(); previous = a.r.last_clock
        a.stage_next_raw(with_calibration=False)
        self.assertFalse(a.r.synchronize(a.now))
        self.assertEqual(a.r.last_clock, previous)
        self.assertIsNone(a.r.fault)
        a.r.receive_calibration(calibration(a.last_raw, a.calibration_sequence))
        self.assertTrue(a.r.synchronize(a.now))

    def test_calibration_must_bind_entire_original_payload_not_only_twist_and_stamp(self):
        a = Feed().disk()
        a.stage_next_raw(with_calibration=False)
        altered = calibration(a.last_raw, a.calibration_sequence)
        altered["odometry"]["pose"]["covariance"][35] = .1
        a.r.receive_calibration(altered)
        with self.assertRaises(ValueError):
            a.r.synchronize(a.now)
        self.assertIsNotNone(a.r.fault)

    def test_first_bad_causal_sample_and_healthy_tail_are_not_replaced_or_deleted(self):
        a = Feed().disk()
        a.stage_next_raw(velocity=(0., .02)); bad = copy.deepcopy(a.last_raw)
        a.stage_next_raw(); healthy = copy.deepcopy(a.last_raw)
        with self.assertRaises(ValueError):
            a.r.synchronize(a.now)
        retained = repr(a.r.events)+repr(a.r.ingress)
        self.assertIn(repr(bad), retained)
        self.assertIn(repr(healthy), retained)
        with self.assertRaises(ValueError):
            a.r.synchronize(a.now)

    def test_malformed_native_calibration_latches_fault_instead_of_allowing_recovery(self):
        a = Feed().disk()
        invalid = calibration(odometry(a.now+STEP), a.calibration_sequence+1)
        invalid["robot"] = "tb2"
        with self.assertRaises(ValueError):
            a.r.receive_calibration(invalid)
        self.assertIsNotNone(a.r.fault)
        with self.assertRaises(ValueError):
            a.r.synchronize(a.now)

    def test_raw_callback_sequence_gap_cannot_be_presented_as_complete_history(self):
        a = Feed().disk()
        with self.assertRaises(ValueError):
            a.r.receive_raw(odometry(a.now+STEP), a.raw_sequence+2)
        self.assertIsNotNone(a.r.fault)

    def test_native_twenty_ms_source_hole_is_not_hidden_by_consecutive_calibration_ids(self):
        a = Feed().disk()
        end = a.now+2*STEP
        raw = odometry(end)
        try:
            a.r.receive_raw(raw, a.raw_sequence+1)
            a.r.receive_calibration(calibration(raw, a.calibration_sequence+1))
            a.actuations(end)
            ready = a.r.synchronize(end)
        except ValueError:
            return
        self.assertFalse(ready)

    def test_permanent_stop_preserves_anchor_history_and_never_requalifies(self):
        a = Feed().disk(); anchors = a.r.status()["anchor_history"]
        a.r.stop()
        for _ in range(55):
            self.assertEqual(a.tick((.1, .3))["output"], [0., 0.])
        self.assertEqual(a.r.role, "STOP")
        self.assertEqual(a.r.status()["anchor_history"], anchors)
        self.assertTrue(a.r.status()["permanent_stop"])

    def test_stop_does_not_discard_future_physical_peak_or_old_anchor_responsibility(self):
        a = Feed().disk(); anchor = copy.deepcopy(a.r.anchor)
        a.r.stop(); a.publish()
        a.stage_next_raw(velocity=(.02, 0.))
        with self.assertRaises(ValueError):
            a.r.synchronize(a.now)
        self.assertEqual(a.r.anchor, anchor)
        self.assertTrue(a.r.stopped)

    def test_tiny_nonzero_stored_then_overwritten_without_actual_handoff_keeps_anchor(self):
        a = Feed().disk(); anchors = a.r.status()["anchor_history"]
        a.tick((1e-300, 0.))  # X announcement is full zero.
        a.tick((1e-300, 0.))  # Tiny nonzero is stored, actual still old zero.
        self.assertFalse(a.r.actual_normal)
        a.publish()  # Same pause, supersedes the tiny target before next write.
        a.tick()
        self.assertFalse(a.r.actual_normal)
        self.assertIsNone(a.r.first_takeover)
        self.assertEqual(a.r.status()["anchor_history"], anchors)

    def test_actual_handoff_needs_registered_real_storage_not_only_a_plausible_receipt(self):
        a = Feed().disk()
        a.tick((.1, 0.))
        a.stage_next_raw()
        self.assertTrue(a.r.synchronize(a.now))
        decision = a.r.decide((.1, 0.), a.own(), a.peers(), a.now, a.r.current_intent)
        value = a.publish(tuple(decision["output"]), store=False)
        source = a.next_actuation
        fake = applied(value, source, a.actuation_sequence, a.command_sequence+1)
        a.r.receive_applied(fake)
        # Missing ACK is not a contradictory ACK: cross-topic callbacks may
        # be reordered. It still cannot borrow evidence, close or enter N.
        before = a.r.last_clock
        self.assertFalse(a.r.synchronize(source))
        self.assertEqual(a.r.last_clock, before)
        self.assertFalse(a.r.actual_normal)

    def test_normal_zero_can_requalify_only_after_new_full_qualification(self):
        a = Feed().normal(); anchors = a.r.status()["anchor_history"]
        a.tick()
        self.assertEqual(a.r.role, "N")
        for _ in range(48):
            a.tick()
            self.assertEqual(a.r.status()["anchor_history"], anchors)
        a.tick()
        self.assertEqual(a.r.role, "D")
        self.assertEqual(len(a.r.status()["anchor_history"]), len(anchors)+1)
        self.assertEqual(a.r.status()["anchor_history"][:len(anchors)], anchors)

    def test_global_H_is_measured_from_last_motion_guard_and_not_zero_actuation(self):
        a = Feed().normal()
        # The final nonzero guard at this literal T has already been really
        # stored. Its first actual application can still occur before the
        # next20ms all-zero publication. That legal old/new bridge belongs to
        # the same H from T, never a new H from its later actuation or zero.
        origin = a.now
        x = 0.
        failed = False
        for _ in range(45):
            x += .0004
            try:
                a.tick(xy=(x, 0.), velocity=(.02, 0.))
            except ValueError as error:
                self.assertIn("global H", str(error))
                failed = True
                break
        self.assertTrue(failed)
        self.assertEqual(a.r.backup_from, origin)
        self.assertLessEqual(a.now, origin+reach.H_NS+2*STEP)

    def test_terminal_anchor_is_fixed_until_new_qualified_disk_not_moving_with_samples(self):
        a = Feed().normal()
        for _ in range(10):
            if a.r.terminal_anchor is not None:
                break
            a.tick()
        self.assertIsNotNone(a.r.terminal_anchor)
        terminal = copy.deepcopy(a.r.terminal_anchor)
        x = 0.
        with self.assertRaisesRegex(ValueError, "terminal disk radius"):
            for _ in range(45):
                x += .00018
                a.tick(xy=(x, 0.), velocity=(.009, 0.))
        self.assertEqual(a.r.terminal_anchor, terminal)

    def test_empty_or_incomplete_peer_set_never_turns_all_empty_into_clearance(self):
        for missing in ({}, {"tb2": (3., 0.)}):
            with self.subTest(missing=missing):
                a = Feed().disk()
                peers = {name: peer(name, a.now, xy) for name, xy in missing.items()}
                try:
                    decision = a.r.decide((0., .1), a.own(), peers, a.now,
                                           a.r.current_intent)
                except ValueError:
                    continue
                self.assertFalse(decision["allow"])
                self.assertEqual(decision["output"], [0., 0.])

    def test_each_frame_certificate_must_pass_with_its_own_distance(self):
        for raw_xy, map_xy in (((.54, 0.), (3., 0.)), ((3., 0.), (.54, 0.))):
            with self.subTest(raw_xy=raw_xy, map_xy=map_xy):
                a = Feed().disk()
                peers = a.peers()
                peers["tb2"] = peer("tb2", a.now, raw_xy, map_xy=map_xy)
                decision = a.r.decide((0., .1), a.own(), peers, a.now,
                                       a.r.current_intent)
                self.assertFalse(decision["allow"])
                self.assertEqual(decision["output"], [0., 0.])

    def test_unrenewed_angular_target_is_not_authorized_for_the_whole_H(self):
        a = Feed().disk()
        a.publish((0., .3))
        # Deliberately omit the next true20ms target/storage renewal. Complete
        # zero-speed raw observations do not authorize stale actuator input.
        end = a.now+100_000_000
        for _ in range(5):
            a.stage_next_raw()
        with self.assertRaises(ValueError):
            a.r.synchronize(end)

    def test_disk_oscillation_retains_old_L1_diagnostic_without_reanchoring(self):
        a = Feed().disk(); anchors = a.r.status()["anchor_history"]
        for _ in range(40):
            a.tick(xy=(.0001, 0.), velocity=(.005, 0.))
            a.tick(xy=(0., 0.), velocity=(-.005, 0.))
        self.assertGreater(a.r.status()["cumulative_path_diagnostic_m"], .0078)
        self.assertEqual(a.r.status()["anchor_history"], anchors)
        self.assertEqual(a.r.role, "D")
        self.assertIsNone(a.r.fault)


if __name__ == "__main__":
    unittest.main(verbosity=2)
