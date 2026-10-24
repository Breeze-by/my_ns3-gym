"""Independent handoff timelines; fixed commands are not guard-generated oracles.

Pure JSON fixture constructors are reused from the independent runtime suite.
Every command/application below comes from a predeclared timeline. Guard
results are assertions, never the input to the next simulated command. None
of these synthetic receipts proves a continuous physical plant or delivery.
"""
import copy
import unittest

from multi_robot_exploration import mr3_reach_runtime as reach
from test_mr3_reach_runtime_independent import (
    EPOCH, ROBOT, START, STEP, ACT, odometry, calibration, target,
    storage, applied, state, peer,
)


class Timeline:
    def __init__(self):
        self.r = reach.ReachTracker(EPOCH, ROBOT)
        self.now = START
        self.raw_sequence = 1
        self.command_sequence = self.target_sequence = 0
        self.actuation_sequence, self.next_actuation = 40, START+STEP
        self.stored = []
        self.raw = odometry(START)
        self.emit((0., 0.))
        self.r.receive_raw(self.raw, 1)
        self.r.receive_calibration(calibration(self.raw, 1))
        if not self.r.synchronize(START):
            raise AssertionError("complete initial raw and calibration expected")
        self.r.release(START)
        self.emit((0., 0.))

    def emit(self, output):
        self.target_sequence += 1
        self.command_sequence += 1
        value = target(self.now, self.target_sequence, output)
        self.r.publish_target(value)
        self.r.receive_storage(storage(value, self.command_sequence))
        self.stored.append((copy.deepcopy(value), self.command_sequence))
        return value

    def own(self):
        row = state(self.raw, self.r.current_intent)
        row["safety"]["calibration"] = copy.deepcopy(self.r.calibrations[self.now])
        return row

    def peers(self):
        return {"tb2": peer("tb2", self.now, (3., 0.)), "tb3": peer("tb3", self.now, (0., 3.))}

    def step(self, requested=(0., 0.), declared_output=(0., 0.)):
        self.now += STEP; self.raw_sequence += 1
        self.raw = odometry(self.now)
        self.r.receive_raw(self.raw, self.raw_sequence)
        self.r.receive_calibration(calibration(self.raw, self.raw_sequence))
        while self.next_actuation <= self.now:
            value, cmd = max((item for item in self.stored if item[0]["clock_ns"] <= self.next_actuation),
                             key=lambda item: item[1])
            self.r.receive_applied(applied(value, self.next_actuation, self.actuation_sequence, cmd))
            self.actuation_sequence += 1; self.next_actuation += ACT
        if not self.r.synchronize(self.now):
            raise AssertionError("complete causal timeline expected")
        decision = self.r.decide(requested, self.own(), self.peers(), self.now, self.r.current_intent)
        if decision["output"] != list(declared_output):
            raise AssertionError("guard differs from independently declared timeline: "+repr(decision))
        self.emit(declared_output)
        return decision

    def disk(self):
        for _ in range(49):
            self.step()
        if self.r.role != "D":
            raise AssertionError("complete full-zero qualification should produce D")
        return self

    def normal(self):
        self.disk()
        self.step((.1, 0.), (0., 0.))
        self.step((.1, 0.), (.1, 0.))
        self.step((.1, 0.), (.1, 0.))
        if self.r.actual_normal:
            raise AssertionError("same-stamp raw must be before actual application")
        self.step((.1, 0.), (.1, 0.))
        if self.r.role != "N":
            raise AssertionError("strict causal sample must complete actual handoff")
        return self


class ReachHandoffReviewTests(unittest.TestCase):
    def test_initial_hold_without_real_matching_evidence_cannot_open_a_frontier(self):
        tracker = reach.ReachTracker(EPOCH, ROBOT)
        self.assertFalse(tracker.synchronize(START))
        with self.assertRaises(ValueError):
            tracker.release(START)
        self.assertIsNotNone(tracker.fault)

    def test_release_cannot_publish_a_disk_promise_from_a_known_nonrest_source(self):
        tracker = reach.ReachTracker(EPOCH, ROBOT)
        zero = target(START, 1)
        tracker.publish_target(zero); tracker.receive_storage(storage(zero, 1))
        raw = odometry(START, velocity=(.02, 0.))
        tracker.receive_raw(raw, 1); tracker.receive_calibration(calibration(raw, 1))
        self.assertTrue(tracker.synchronize(START))
        with self.assertRaises(ValueError):
            tracker.release(START)
        self.assertIsNotNone(tracker.fault)

    def test_unused_nonzero_publication_cannot_move_actual_stop_responsibility(self):
        timeline = Timeline().normal()
        actual_origin = timeline.r.last_applied["target"]["clock_ns"]
        self.assertLess(actual_origin, timeline.now)
        timeline.emit((1e-300, 0.))
        timeline.emit((0., 0.))  # Both writes are superseded while physics remains paused.
        self.assertEqual(timeline.r.last_motion_clock, actual_origin)
        self.assertEqual(timeline.r.backup_from, actual_origin)

    def test_normal_existing_terminal_survives_stored_tiny_without_actual_consumption(self):
        timeline = Timeline().normal()
        for _ in range(5):
            timeline.step()
            if timeline.r.terminal_anchor is not None:
                break
        self.assertIsNotNone(timeline.r.terminal_anchor)
        terminal = copy.deepcopy(timeline.r.terminal_anchor)
        origin = timeline.r.backup_from
        anchors = timeline.r.status()["anchor_history"]
        timeline.emit((1e-300, 0.)); timeline.emit((0., 0.))
        for _ in range(2):
            timeline.step()
        self.assertEqual(timeline.r.backup_from, origin)
        self.assertEqual(timeline.r.terminal_anchor, terminal)
        self.assertEqual(timeline.r.status()["anchor_history"], anchors)

    def test_x_unused_tiny_cancel_requires_actual_zero_and_keeps_same_disk_anchor(self):
        timeline = Timeline().disk()
        anchor = copy.deepcopy(timeline.r.anchor)
        anchors = timeline.r.status()["anchor_history"]
        timeline.step((1e-300, 0.), (0., 0.))
        timeline.step((1e-300, 0.), (1e-300, 0.))
        timeline.emit((0., 0.))
        self.assertEqual(timeline.r.role, "X")
        timeline.step(); timeline.step()
        self.assertEqual(timeline.r.role, "D")
        self.assertFalse(timeline.r.actual_normal)
        self.assertIsNone(timeline.r.first_takeover)
        self.assertEqual(timeline.r.anchor, anchor)
        self.assertEqual(timeline.r.status()["anchor_history"], anchors)

    def test_prospective_transition_checks_four_R_before_any_nonzero_publication(self):
        timeline = Timeline().disk()
        peers = timeline.peers(); peers["tb2"] = peer("tb2", timeline.now, (.56, 0.))
        # D+D needs .5512m; X+D needs .5668m even when the away sector's
        # longitudinal term is discounted. This isolates the extra bridge2R.
        decision = timeline.r.decide((-.1, 0.), timeline.own(), peers, timeline.now, timeline.r.current_intent)
        self.assertEqual(decision["output"], [0., 0.])
        self.assertFalse(decision["allow"])
        self.assertEqual(decision["reason"], "reach_transition_envelope")
        self.assertEqual(timeline.r.role, "D")

    def test_stop_cannot_resume_or_replace_the_last_fixed_anchor(self):
        timeline = Timeline().normal()
        anchors = timeline.r.status()["anchor_history"]
        timeline.r.stop()
        timeline.emit((0., 0.))
        for _ in range(50):
            timeline.step((.1, .3), (0., 0.))
        self.assertEqual(timeline.r.role, "STOP")
        self.assertTrue(timeline.r.stopped)
        self.assertEqual(timeline.r.status()["anchor_history"], anchors)


if __name__ == "__main__":
    unittest.main()
