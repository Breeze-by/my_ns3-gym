"""Cross-topic receipt ordering, with literal commands and synthetic feeds only.

An applied callback is not a substitute for its real storage receipt. Missing
delivery must leave the physical frontier pending; contradictory delivery is
permanent failure. These tests establish neither ROS delivery nor plant proof.
"""
import copy
import unittest

from test_mr3_reach_handoff_review import Timeline
from test_mr3_reach_runtime_independent import (
    STEP, ACT, odometry, calibration, target, storage, applied,
)


def stage_phase(timeline, pending=None):
    """Queue literal raw and complete phased actual writes, without deciding."""
    timeline.now += STEP
    timeline.raw_sequence += 1
    timeline.raw = odometry(timeline.now)
    timeline.r.receive_raw(timeline.raw, timeline.raw_sequence)
    timeline.r.receive_calibration(calibration(timeline.raw, timeline.raw_sequence))
    while timeline.next_actuation <= timeline.now:
        candidates = list(timeline.stored)
        if pending is not None:
            candidates.append(pending)
        value, cmd = max((item for item in candidates
                          if item[0]["clock_ns"] <= timeline.next_actuation),
                         key=lambda item: item[1])
        timeline.r.receive_applied(applied(
            value, timeline.next_actuation, timeline.actuation_sequence, cmd))
        timeline.actuation_sequence += 1
        timeline.next_actuation += ACT


def applied_before_storage():
    """A valid X command is really applied; only its storage callback is late."""
    timeline = Timeline().disk()
    timeline.step((.1, 0.), (0., 0.))  # Announce X while the real target is zero.
    stage_phase(timeline)
    if not timeline.r.synchronize(timeline.now):
        raise AssertionError("complete preceding zero phase expected")
    decision = timeline.r.decide((.1, 0.), timeline.own(), timeline.peers(),
                                 timeline.now, timeline.r.current_intent)
    if decision["output"] != [.1, 0.]:
        raise AssertionError("literal preannounced translation must be allowed")
    timeline.target_sequence += 1
    timeline.command_sequence += 1
    value = target(timeline.now, timeline.target_sequence, (.1, 0.))
    timeline.r.publish_target(value)
    pending = (copy.deepcopy(value), timeline.command_sequence)
    frontier = timeline.r.last_clock
    previous_applied = copy.deepcopy(timeline.r.last_applied)
    stage_phase(timeline, pending)
    return timeline, pending, frontier, previous_applied


class ReachDeliveryOrderTests(unittest.TestCase):
    def assert_pending(self, timeline, frontier, previous_applied):
        self.assertFalse(timeline.r.synchronize(timeline.now))
        self.assertIsNone(timeline.r.fault)
        self.assertEqual(timeline.r.last_clock, frontier)
        self.assertEqual(timeline.r.last_applied, previous_applied)
        self.assertEqual(timeline.r.role, "X")
        self.assertFalse(timeline.r.actual_normal)
        self.assertIsNone(timeline.r.first_takeover)

    def test_applied_first_waits_then_real_storage_recovers_without_early_normal(self):
        timeline, pending, frontier, previous = applied_before_storage()
        anchor = copy.deepcopy(timeline.r.anchor)
        self.assert_pending(timeline, frontier, previous)
        value, cmd = pending
        applied_event = next(entry for entry in timeline.r.events if entry[1] == 1)
        self.assertNotIn(applied_event[:2], timeline.r.processed)
        timeline.r.receive_storage(storage(value, cmd))
        self.assertTrue(timeline.r.synchronize(timeline.now))
        self.assertEqual(timeline.r.last_applied["target"], value)
        # Same-source raw is before actual application; it cannot retire D.
        self.assertEqual(timeline.r.latest_raw[0], timeline.r.last_applied["source_clock_ns"])
        self.assertFalse(timeline.r.actual_normal)
        self.assertEqual(timeline.r.role, "X")
        self.assertEqual(timeline.r.anchor, anchor)
        stage_phase(timeline)  # No next actual write yet; raw is strictly later.
        self.assertTrue(timeline.r.synchronize(timeline.now))
        self.assertTrue(timeline.r.actual_normal)
        self.assertEqual(timeline.r.role, "N")
        self.assertEqual(timeline.r.anchor, anchor)

    def test_permanently_missing_storage_never_closes_frontier_or_retires_disk(self):
        timeline, _, frontier, previous = applied_before_storage()
        anchor = copy.deepcopy(timeline.r.anchor)
        for _ in range(3):
            self.assert_pending(timeline, frontier, previous)
        stage_phase(timeline)  # A newer raw cannot bypass the missing proof.
        tail = copy.deepcopy(timeline.raw)
        self.assert_pending(timeline, frontier, previous)
        self.assertEqual(timeline.r.anchor, anchor)
        self.assertTrue(any(kind == "raw" and value == tail
                            for kind, value in timeline.r.ingress))
        self.assertTrue(any(entry[1] == 1 for entry in timeline.r.events))

    def test_conflicting_command_identity_is_a_latched_fault_not_pending(self):
        timeline, pending, _, _ = applied_before_storage()
        value, cmd = pending
        # A real ACK for this publication with a different command identity
        # contradicts the already delivered applied receipt.
        timeline.r.receive_storage(storage(value, cmd+1))
        with self.assertRaises(ValueError):
            timeline.r.synchronize(timeline.now)
        fault = timeline.r.fault
        self.assertIsNotNone(fault)
        self.assertFalse(timeline.r.actual_normal)
        with self.assertRaises(ValueError):
            timeline.r.receive_storage(storage(value, cmd))
        with self.assertRaises(ValueError):
            timeline.r.synchronize(timeline.now)
        self.assertEqual(timeline.r.fault, fault)

    def test_foreign_epoch_storage_cannot_complete_local_application(self):
        timeline, pending, _, _ = applied_before_storage()
        value, cmd = pending
        foreign = storage(value, cmd)
        foreign["epoch"] = "different-episode"
        with self.assertRaises(ValueError):
            timeline.r.receive_storage(foreign)
        fault = timeline.r.fault
        self.assertIsNotNone(fault)
        with self.assertRaises(ValueError):
            timeline.r.synchronize(timeline.now)
        self.assertEqual(timeline.r.fault, fault)
        self.assertFalse(timeline.r.actual_normal)
        self.assertNotIn(value["decision_sequence"], timeline.r.storage.pending["tb1"])


if __name__ == "__main__":
    unittest.main()
