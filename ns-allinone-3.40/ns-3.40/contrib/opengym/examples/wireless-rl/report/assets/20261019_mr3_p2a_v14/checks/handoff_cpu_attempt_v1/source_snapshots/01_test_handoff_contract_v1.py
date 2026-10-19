"""Written only; root's finite CPU runner owns actual execution/FAIL/waits."""
from dataclasses import FrozenInstanceError, replace
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import handoff_contract_v1 as h


EPOCH = "cpu-conditional-epoch"
START = 1_000_000_000
Q20 = 20_000_000
FRAMES = ("map", "odom", "base_footprint")


def token(number):
    return "%064x" % number


def raw(source, sequence, *, xy=(0, 0), velocity=(0, 0), frames=FRAMES):
    return h.RawSample(source, sequence, frames, xy, xy, velocity, (0, 0, 0), token(sequence))


def witness(c, mode="disk", target=None):
    return h.ConditionalWitness(mode, EPOCH, "tb1", c.now_ns,
        c._latest.payload_sha256, c.now_ns, c.now_ns + h.H_NS,
        token(200), token(201), token(202), token(203),
        c.intent.sha256 if target else "", target.sha256 if target else "",
        c.intent.transition_reach_sha256 if target else "")


def clock(c, when, sample):
    c.stage_raw(sample)
    c.drain(when, raw_complete_ns=when, actuation_complete_ns=when)


def disk_fixture():
    c = h.HandoffContract(EPOCH, "tb1", START)
    zero = h.Target(EPOCH, "tb1", START, 1, 0., 0.)
    c.publish(zero); c.store(zero, START)
    c.stage_actuation(h.Actuation(START, 1, zero))
    for i in range(50):
        c.stage_raw(raw(START + i*Q20, i+1))
    end = START + 49*Q20
    c.drain(end, raw_complete_ns=end, actuation_complete_ns=end)
    c.activate(witness(c))
    return c


def intent_fixture():
    c = disk_fixture()
    zero = h.Target(EPOCH, "tb1", c.now_ns, 2, 0., .3)
    c.announce_normal(zero, token(300)); c.store(zero, c.now_ns)
    clock(c, c.now_ns+Q20, raw(c.now_ns+Q20, 51))
    return c


def delivered(c, peers=("tb2", "tb3")):
    envelope = h.StateEnvelope(EPOCH, "tb1", c.now_ns, c.now_ns//Q20,
                              token(c.now_ns), c.intent.sha256, token(300))
    for i, peer in enumerate(peers):
        c.receive_envelope(peer, envelope)
        c.peer_phase(h.PeerWatermark(peer, envelope, c.now_ns,
                                    "boundary"+str(c.now_ns), token(400+i)))
    return envelope


def publish_normal(c, sequence=3, v=.1):
    target = h.Target(EPOCH, "tb1", c.now_ns, sequence, v, .3)
    output = c.publish(target, witness(c, "normal" if c.mode == "NORMAL" else "transition", target))
    c.store(target, c.now_ns)
    return target, output


class HandoffContractTests(unittest.TestCase):
    def test_qualification_is_distinct_from_immutable_protection(self):
        c = disk_fixture(); anchor = c.protected_anchor
        with self.assertRaises(FrozenInstanceError):
            anchor.epoch = "changed"
        zero = h.Target(EPOCH, "tb1", c.now_ns, 2, 0., .3)
        c.publish(zero); c.store(zero, c.now_ns)
        with self.assertRaises(h.ContractError):
            c.activate(witness(c))
        self.assertIs(c.protected_anchor, anchor)
        self.assertEqual(c.episode_anchors, (anchor,))

    def test_intent_keeps_zero_and_missing_peer_delivery_rejects_translation(self):
        c = intent_fixture(); anchor = c.protected_anchor
        self.assertEqual(c.intent.zero_target.v, 0.)
        delivered(c, ("tb2",))
        with self.assertRaisesRegex(h.ContractError, "all relevant peers"):
            publish_normal(c)
        self.assertIs(c.protected_anchor, anchor)
        self.assertTrue(c.disk_active)
        self.assertEqual(c.mode, "INTENT_PENDING")

    def test_central_intent_or_forged_passed_does_not_substitute_delivery_and_witness(self):
        c = intent_fixture()
        env = h.StateEnvelope(EPOCH, "tb1", c.now_ns, 20, token(10), c.intent.sha256, token(300))
        with self.assertRaisesRegex(h.ContractError, "actual delivered"):
            c.peer_phase(h.PeerWatermark("tb2", env, c.now_ns, "boundary"+str(c.now_ns), token(400)))
        delivered(c)
        target = h.Target(EPOCH, "tb1", c.now_ns, 3, .1, .3)
        with self.assertRaisesRegex(h.ContractError, "full conditional"):
            c.publish(target, {"passed": True, "accepted": True, "native_admission": True})
        with self.assertRaises(h.ContractError):
            replace(witness(c, "transition", target), terminal_sha256="")
        self.assertFalse(c.status()["native_admission"])

    def test_phase_watermark_binds_exact_delivered_envelope_and_peer(self):
        c = intent_fixture(); env = delivered(c)
        changed = replace(env, bundle_sha256=token(99))
        with self.assertRaises(h.ContractError):
            c.peer_phase(h.PeerWatermark("tb2", changed, c.now_ns, "boundary"+str(c.now_ns), token(900)))
        with self.assertRaisesRegex(h.ContractError, "another peer"):
            c.peer_phase(h.PeerWatermark("tb3", env, c.now_ns, "boundary"+str(c.now_ns), token(400)))

    def test_real_translation_handoff_needs_applied_seq_and_strict_later_source(self):
        c = intent_fixture(); delivered(c); anchor = c.protected_anchor
        target, output = publish_normal(c)
        self.assertEqual(len(output["target"]), 7)
        self.assertTrue(output["conditional_cpu_translation"])
        self.assertFalse(output["native_admission"])
        self.assertTrue(c.disk_active)
        at = c.now_ns+10_000_000
        c.stage_raw(raw(at, 52))
        c.stage_actuation(h.Actuation(at, 2, target))
        c.drain(at, raw_complete_ns=at, actuation_complete_ns=at)
        self.assertTrue(c.disk_active)
        later = at+10_000_000
        clock(c, later, raw(later, 53, xy=(.001, 0), velocity=(.1, 0)))
        self.assertEqual(c.mode, "NORMAL")
        self.assertFalse(c.disk_active)
        self.assertIs(c.protected_anchor, anchor)
        self.assertEqual(c.episode_anchors, (anchor,))

    def test_successor_seq_can_actuate_without_first_seq_deadlock(self):
        c = intent_fixture(); delivered(c)
        first, _ = publish_normal(c)
        next_clock = c.now_ns+Q20
        clock(c, next_clock, raw(next_clock, 52))
        delivered(c)
        successor, _ = publish_normal(c, sequence=4)
        self.assertNotEqual(first.sequence, successor.sequence)
        at = c.now_ns+10_000_000
        c.stage_actuation(h.Actuation(at, 2, successor))
        c.stage_raw(raw(at, 53))
        c.stage_raw(raw(at+10_000_000, 54, xy=(.001, 0), velocity=(.1, 0)))
        c.drain(at+10_000_000, raw_complete_ns=at+10_000_000, actuation_complete_ns=at+10_000_000)
        self.assertEqual(c.mode, "NORMAL")
        self.assertEqual(len(c.episode_anchors), 1)

    def test_same_stamp_odom_is_before_actuation_and_cannot_hide_rest_peak(self):
        c = intent_fixture(); delivered(c); target, _ = publish_normal(c)
        at = c.now_ns+10_000_000
        c.stage_actuation(h.Actuation(at, 2, target))
        c.stage_raw(raw(at, 52, velocity=(.02, 0)))
        with self.assertRaisesRegex(h.ContractError, "rest peak"):
            c.drain(at, raw_complete_ns=at, actuation_complete_ns=at)
        self.assertEqual(c.mode, "FAULT")

    def test_tiny_stored_but_never_applied_then_stop_cannot_reanchor(self):
        c = intent_fixture(); delivered(c); anchor = c.protected_anchor
        tiny, _ = publish_normal(c, v=math.nextafter(0., math.inf))
        c.request_stop()
        zero = h.Target(EPOCH, "tb1", c.now_ns, tiny.sequence+1, 0., 0.)
        c.publish(zero); c.store(zero, c.now_ns)
        at = c.now_ns+Q20
        c.stage_actuation(h.Actuation(at, 2, zero))
        clock(c, at, raw(at, 52))
        self.assertTrue(c.disk_active)
        self.assertIs(c.protected_anchor, anchor)
        self.assertEqual(c.mode, "STOPPING")
        with self.assertRaises(h.ContractError):
            c.activate(witness(c))
        self.assertEqual(c.episode_anchors, (anchor,))

    def test_future_raw_waits_for_both_stream_watermarks_then_peak_is_not_dropped(self):
        c = disk_fixture(); future = c.now_ns+Q20
        c.stage_raw(raw(future, 51, velocity=(0, .02)))
        c.drain(future, raw_complete_ns=c.now_ns, actuation_complete_ns=c.now_ns)
        self.assertIsNone(c.fault)
        self.assertLess(c.checked_through_ns, c.now_ns)
        with self.assertRaisesRegex(h.ContractError, "rest peak"):
            c.drain(future, raw_complete_ns=future, actuation_complete_ns=future)
        self.assertEqual(c.mode, "FAULT")

    def test_source_gap_frame_conflict_and_global_peak_cannot_be_hidden_by_application(self):
        for failure in ("gap", "frame", "peak"):
            with self.subTest(failure=failure):
                c = intent_fixture(); delivered(c); target, _ = publish_normal(c)
                at = c.now_ns+10_000_000
                c.stage_actuation(h.Actuation(at, 2, target))
                later = c.now_ns+h.GAP_NS+1 if failure == "gap" else c.now_ns+Q20
                sample = raw(later, 52, velocity=(.31, 0) if failure == "peak" else (0, 0),
                             frames=("map", "different_odom", "base") if failure == "frame" else FRAMES)
                c.stage_raw(sample)
                with self.assertRaises(h.ContractError):
                    c.drain(later, raw_complete_ns=later, actuation_complete_ns=later)
                self.assertEqual(c.mode, "FAULT")
                self.assertEqual(len(c.episode_anchors), 1)

    def test_unregistered_or_superseded_actual_target_is_not_an_application_proof(self):
        c = intent_fixture(); delivered(c); target, _ = publish_normal(c)
        zero = h.Target(EPOCH, "tb1", c.now_ns, 4, 0., 0.)
        c.publish(zero); c.store(zero, c.now_ns)
        at = c.now_ns+10_000_000
        c.stage_actuation(h.Actuation(at, 2, target))
        c.stage_raw(raw(at, 52))
        with self.assertRaisesRegex(h.ContractError, "latest registered"):
            c.drain(at, raw_complete_ns=at, actuation_complete_ns=at)
        self.assertTrue(c.disk_active)

    def test_conflicting_equal_source_and_fixed_disk_excursion_are_not_renewed(self):
        c = disk_fixture()
        conflicting = raw(c.now_ns, 51, xy=(.001, 0))
        with self.assertRaisesRegex(h.ContractError, "conflicting same-stamp"):
            c.stage_raw(conflicting)
        c = disk_fixture(); later = c.now_ns+Q20
        c.stage_raw(raw(later, 51, xy=(.008, 0)))
        with self.assertRaisesRegex(h.ContractError, "disk excursion"):
            c.drain(later, raw_complete_ns=later, actuation_complete_ns=later)
        self.assertEqual(len(c.episode_anchors), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
